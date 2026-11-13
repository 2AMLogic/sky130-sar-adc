"""One `klt sim` submit path for every batch campaign driver (issue #865).

A campaign driver's job is to build a deck and a request and to decode the
report it gets back. The part in between -- write the request, run `klt sim`,
read the JSON report off stdout (or off stderr, where the client writes its
error envelope), refuse an error envelope rather than read it as zero
corners, cache the report so a resumed campaign does not re-spend fleet
capacity -- is identical for every campaign, and lives here.

It is here because the four drivers that had their own copy had already
drifted apart on the one thing a shared dispatch host cannot get wrong:
**fleet-capacity policy**. The Spot batch fleet is vCPU-budgeted (CLAUDE.md),
so a burst of submits is refused with `batch_no_capacity`; that refusal is
"no capacity right now", never "the design failed". Of the four copies, two
passed `--wait-for-capacity`, one set `batch.capacity_wait_s` plus a private
retry loop, and one passed nothing at all, which made a capacity refusal a
hard campaign failure. `submit()` below gives every non-`local` submit the
flag by default, so a new campaign inherits the policy instead of re-deciding
it.

Stdlib only, and the subprocess runner is injectable (`runner=`), so these
paths are unit-testable without `klt`, the PDK or the fleet.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

#: Seconds a non-`local` submit waits for fleet capacity instead of failing
#: the step. CLAUDE.md's host rule ("pass `--wait-for-capacity 600` on every
#: batch `klt sim`", 2am#6872); a caller that genuinely wants the old
#: fail-fast behaviour passes `capacity_wait_s=None`.
DEFAULT_CAPACITY_WAIT_S = 600.0

#: How much of a non-JSON `klt sim` failure is quoted in `SubmitError`. One
#: value for every campaign: the four private copies truncated at 600, 800,
#: 1200 and 600 characters respectively, which was drift, not a decision.
ERROR_TEXT_CHARS = 1200

#: A shared fleet refuses a launch while it is at its concurrency cap, and
#: `klt sim` does not wait that refusal out itself in every pairing of client
#: and runner. Re-submitting to the SAME batch backend is the correct
#: response to these; any other submit error stops the campaign.
CAPACITY_MARKERS = ("BATCH_MAX_CONCURRENT_INSTANCES", "batch_no_capacity", "no capacity")


class SubmitError(RuntimeError):
    """A `klt sim` submission produced no usable report."""


def is_capacity_refusal(message: str) -> bool:
    """True when `message` is the fleet saying "not right now"."""
    return any(m.lower() in message.lower() for m in CAPACITY_MARKERS)


def default_runner(argv: list[str]) -> tuple[int, str, str]:
    """Run `argv`, returning `(returncode, stdout, stderr)`."""
    done = subprocess.run(argv, capture_output=True, text=True, check=False)
    return done.returncode, done.stdout, done.stderr


def submit_argv(
    request_path: Path | str,
    outdir: Path | str,
    backend: str | None = None,
    *,
    capacity_wait_s: float | None = DEFAULT_CAPACITY_WAIT_S,
) -> list[str]:
    """The `klt sim` argv for one request.

    `--wait-for-capacity` is passed unless the backend is explicitly `local`
    (there is no fleet to wait for) or `capacity_wait_s` is None. With no
    explicit backend, `$KLT_SIM_BACKEND` decides -- which on a dispatch host
    is `batch`, so the flag must still be there.
    """
    argv = ["klt", "sim", str(request_path), "--format", "json", "-o", str(outdir)]
    if backend:
        argv += ["--backend", backend]
    if backend != "local" and capacity_wait_s is not None:
        argv += ["--wait-for-capacity", f"{capacity_wait_s:g}"]
    return argv


def submit(
    request_path: Path | str,
    outdir: Path | str,
    *,
    backend: str | None = None,
    capacity_wait_s: float | None = DEFAULT_CAPACITY_WAIT_S,
    report_path: Path | str | None = None,
    label: str | None = None,
    runner=default_runner,
    capacity_retries: int = 0,
    retry_wait_s: float = 120.0,
    sleep=None,
    echo: bool = True,
) -> dict:
    """Submit `request_path` through `klt sim` and return its JSON report.

    An existing report at `report_path` (default: `report.json` beside the
    request) is REUSED rather than re-simulated, so a campaign that died
    partway resumes without re-spending completed fleet jobs. The report is
    written there on a successful submit.

    Raises `SubmitError` when the client produced no JSON at all, or when it
    produced an error ENVELOPE (`error` present and no `corners`). An `error`
    key ALONGSIDE `corners` is a partially-failed run, not an envelope, and
    is returned for the caller's own reader to decode.

    `capacity_retries` adds a bounded client-side retry on a capacity refusal
    *on top of* `--wait-for-capacity`, for the client/runner pairings where
    the flag alone does not wait a refusal out; it re-submits to the same
    backend, never to `local`.
    """
    req_path = Path(request_path)
    rep_path = Path(report_path) if report_path is not None else req_path.parent / "report.json"
    if rep_path.is_file():
        return json.loads(rep_path.read_text())

    argv = submit_argv(req_path, outdir, backend, capacity_wait_s=capacity_wait_s)
    tag = f"klt sim ({label})" if label else "klt sim"
    nap = sleep or time.sleep
    if echo:
        print("+ " + " ".join(argv), flush=True)

    for attempt in range(capacity_retries + 1):
        rc, out, err = runner(argv)
        try:
            try:
                report = json.loads(out)
            except json.JSONDecodeError:
                report = json.loads(err)  # `klt` writes its error envelope to stderr (rc 1)
        except json.JSONDecodeError as exc:
            raise SubmitError(
                f"{tag} returned no JSON report (rc={rc}): "
                f"{(err or out)[:ERROR_TEXT_CHARS]}"
            ) from exc
        if "error" in report and "corners" not in report:
            msg = json.dumps(report["error"])
            if is_capacity_refusal(msg) and attempt < capacity_retries:
                print(f"fleet at capacity; retrying {tag} in {retry_wait_s:.0f}s "
                      f"({attempt + 1}/{capacity_retries})", file=sys.stderr, flush=True)
                nap(retry_wait_s)
                continue
            raise SubmitError(f"{tag}: {msg}")
        break

    rep_path.parent.mkdir(parents=True, exist_ok=True)
    rep_path.write_text(json.dumps(report, indent=1) + "\n")
    return report


def ngspice_from_banner(banner: str) -> str | None:
    """The `ngspice-NN` token out of a worker's version banner, or None."""
    for line in (banner or "").splitlines():
        token = next((t for t in line.replace("*", " ").split() if t.startswith("ngspice-")), None)
        if token:
            return token.strip(":,")
    return None


def run_info(report: dict) -> dict:
    """Run-level facts, from EITHER batch report shape.

    A one-job batch run carries `job_id` and `worker_environment` directly on
    `environment.remote`; a SHARDED run (`remote.hosts > 1`) carries one
    entry per shard under `environment.remote.fleet[]` instead, and the
    single-job keys are absent. Reading only the single-job shape is how a
    sharded record ends up reporting `job None` -- so both are handled here,
    and the executing PDK/simulator are only reported when EVERY shard
    agrees on them.
    """
    remote = ((report.get("environment") or {}).get("remote")) or {}
    shards = remote.get("fleet")
    entries = shards if isinstance(shards, list) and shards else [remote]
    jobs = []
    pdks, ngs, features = set(), set(), set()
    for entry in entries:
        worker = entry.get("worker_environment") or {}
        pdk_stamp = (worker.get("pdk") or {}).get("stamp_text")
        variant = (worker.get("pdk") or {}).get("variant")
        ng = ngspice_from_banner((worker.get("simulator") or {}).get("version_banner") or "")
        if pdk_stamp:
            pdks.add(f"{variant} @ {pdk_stamp.split()[-1]}" if variant else pdk_stamp)
        if ng:
            ngs.add(ng)
        feats = entry.get("runner_request_features") or {}
        if feats.get("status"):
            features.add(str(feats["status"]))
        if entry.get("job_id"):
            jobs.append({
                "job_id": entry.get("job_id"),
                "state": entry.get("state"),
                "exit_code": entry.get("exit_code"),
                "instance_type": entry.get("instance_type"),
                "elapsed_seconds": entry.get("elapsed_seconds"),
                "runner_klt_version": entry.get("runner_klt_version"),
            })
    backend = (report.get("environment") or {}).get("backend")
    if isinstance(backend, dict):
        backend = backend.get("resolved") or backend.get("requested")
    return {
        "status": report.get("status"),
        "jobs": jobs,
        "job_id": jobs[0]["job_id"] if len(jobs) == 1 else None,
        "sharded": bool(isinstance(shards, list) and shards),
        "remote": remote or None,
        "resolved_backend": backend,
        # Only when every shard agrees; a mixed fleet reports None rather than
        # letting one shard's environment stand for the whole run.
        "worker_pdk": next(iter(pdks)) if len(pdks) == 1 else None,
        "worker_ngspice": next(iter(ngs)) if len(ngs) == 1 else None,
        "worker_pdks_seen": sorted(pdks),
        "worker_ngspice_seen": sorted(ngs),
        "request_feature_status": next(iter(features)) if len(features) == 1 else None,
    }

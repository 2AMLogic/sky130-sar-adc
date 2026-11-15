"""One `klt sim` submit path for every batch campaign driver (issue #865).

A campaign driver's job is to build a deck and a request and to decode the
report it gets back. The part in between -- write the request, run `klt sim`,
read the JSON report off stdout (or scan stderr for the error envelope the
client writes there, behind its own warnings), refuse an error envelope
rather than read it as zero
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

Stdlib plus one pure harness sibling (`corners.corner_id` -- string
formatting, still no PDK), and the subprocess runner is injectable
(`runner=`), so these paths are unit-testable without `klt`, the PDK or
the fleet.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import time
from pathlib import Path

from .corners import corner_id

#: Seconds a non-`local` submit waits for fleet capacity instead of failing
#: the step. CLAUDE.md's host rule ("pass `--wait-for-capacity 600` on every
#: batch `klt sim`", 2am#6872); a caller that genuinely wants the old
#: fail-fast behaviour passes `capacity_wait_s=None`.
DEFAULT_CAPACITY_WAIT_S = 600.0

#: How much of a non-JSON `klt sim` failure is quoted in `SubmitError`. One
#: value for every campaign: the four private copies truncated at 600, 800,
#: 1200 and 600 characters respectively, which was drift, not a decision.
#: It is the TAIL that is quoted (issue #892): `klt` leads with install
#: warnings and per-job progress, so the head of a long stderr is the part
#: that says least about the failure.
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


def envelope_from_stderr(text: str) -> dict | None:
    """The `klt` error envelope carried somewhere in `text`, or None.

    `klt` writes its error envelope to stderr, but not necessarily ALONE:
    install warnings and per-job progress lines are written there first, so
    `json.loads(stderr)` raises on a stream that does plainly contain an
    envelope (issue #892). That mattered twice over -- the refusal was
    reported as "no JSON report" (a client malfunction) instead of as the
    fleet's own `batch_no_capacity`, and `submit()`'s capacity retry, which
    is gated on a DECODED envelope, could never fire on that shape.

    So the stream is scanned rather than assumed: every line that opens a
    JSON object is a candidate, and the first one that decodes to a dict
    carrying an `"error"` key wins. Trailing text after the envelope is
    ignored; a candidate line that does not decode (a progress line that
    happens to start with `{`) is skipped rather than ending the scan.
    Deliberately not a strip-the-known-`klt:`-prefixes rule, which would
    be brittle against new wording.

    The `"error"` requirement is the point (issue #898): a report is a
    stdout artifact, so the only dict stderr has a documented reason to
    carry is an envelope. A non-envelope JSON object -- a progress or
    status dict at column 0 -- must neither stand in for a report nor mask
    a real envelope further down the stream; the scan walks past it to the
    envelope behind it, and a stream carrying no envelope yields None.
    """
    decoder = json.JSONDecoder()
    offset = 0
    for line in (text or "").splitlines(keepends=True):
        if line.startswith("{"):
            try:
                value, _ = decoder.raw_decode(text, offset)
            except ValueError:
                pass
            else:
                if isinstance(value, dict) and "error" in value:
                    return value
        offset += len(line)
    return None


def error_excerpt(text: str) -> str:
    """The `ERROR_TEXT_CHARS`-character TAIL of a failed client's output.

    Quoted only when no envelope decoded at all. The tail, not the head:
    see `ERROR_TEXT_CHARS`.
    """
    text = text or ""
    if len(text) <= ERROR_TEXT_CHARS:
        return text
    return "..." + text[-ERROR_TEXT_CHARS:]


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

    A JSON dict on stderr that carries NO `error` key is a third outcome and
    is refused as "no JSON report" (issue #898): a report is a stdout
    artifact, so a stderr dict that is not an envelope never becomes one --
    it is raised over, not cached.

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
            # A successful report is on stdout and is STRICT json: a report
            # that does not parse whole is not a report.
            report = json.loads(out)
        except json.JSONDecodeError as exc:
            # `klt` writes its error envelope to stderr (rc 1), behind its
            # own warning and progress lines -- so stderr is scanned for the
            # envelope, never required to BE it (issue #892).
            report = envelope_from_stderr(err)
            if report is None:
                raise SubmitError(
                    f"{tag} returned no JSON report (rc={rc}): "
                    f"{error_excerpt(err or out)}"
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

    `jobs[]` carries one entry per shard (one entry for a single-job run),
    including that shard's `runner_klt_version` / `client_klt_version` /
    `runner_compatibility` -- the version-skew facts a disclosure section is
    rendered from. Read them from `jobs[]`, never off `remote`: on the
    sharded shape `remote` has no key but `fleet`.
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
                # Runner/client version skew is a PER-SHARD fact: a sharded
                # run carries these two keys only inside `fleet[]`, never on
                # `environment.remote`, so a campaign that reads them off
                # `remote` reports no skew however the shards disagree
                # (issue #888). They are normalised here so no campaign has
                # to walk `fleet[]` to find them.
                "client_klt_version": entry.get("client_klt_version"),
                "runner_compatibility": entry.get("runner_compatibility"),
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


def finite(x) -> bool:
    """True when `x` is a real, finite JSON number.

    Never `True`/`False` (a JSON boolean is a status, not a measurement) and
    never NaN/inf. One definition for every campaign: the drivers had drifted
    to two, with the bool guard missing from the copy the others were taken
    from (issue #904).
    """
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def measurements_by_corner(
    report: dict, supply_key: str
) -> tuple[dict[str, dict[str, float | None]], dict]:
    """`({corner_id: {"<step>.<name>": value}}, run_info(report))`.

    Refuses a `klt sim` error ENVELOPE rather than inventing numbers, and
    nulls a corner whose own status is `error`/`inconclusive` so a partial
    solve is never read as a measurement. One copy for every campaign: three
    drivers carried byte-identical private readers of this block (issue
    #904, extending #865's `run_info()` consolidation to the one identical
    decoding block it had deliberately left per-driver).

    `supply_key` selects the corner's supply out of its `supply_v` map; the
    campaign's module constant (`SUPPLY_KEY` = "vsup" today) moves to this
    argument rather than being baked into yet another module.
    """
    if not isinstance(report, dict):
        raise ValueError("klt sim report is not a JSON object")
    if "error" in report and "corners" not in report:
        raise ValueError(f"klt sim error envelope: {report['error']}")
    out: dict[str, dict[str, float | None]] = {}
    for c in report.get("corners") or []:
        sv = (c.get("supply_v") or {}).get(supply_key)
        cid = corner_id(c["process"], float(c["temperature_c"]), float(sv))
        vals = {
            m["name"]: m.get("value")
            for m in (c.get("measurements") or [])
            if isinstance(m, dict) and "name" in m
        }
        if c.get("status") in ("error", "inconclusive"):
            vals = {k: None for k in vals}
        out[cid] = vals
    return out, run_info(report)

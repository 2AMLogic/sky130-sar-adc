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

The deck side of a request is shared here for the same reason (issue #1030):
`split_fragment()` cuts a committed stimulus/measurement fragment into the
three pieces a `klt sim` request needs them in (circuit body, `.meas` cards,
`.tran` arguments), asserted against the expected measurement names the
CALLING campaign passes in, and `saved_vectors()` reduces those cards to the
sorted save set. The reference-drive budget and the input sweep had each
carried a private copy of both, so a correction to card handling had to
reach two campaigns at once.

The request side of an OAT corners campaign is shared here for the same
reason (issues #1052, #1054): `oat_corners()` expands a list of corner-id
strings into the `corners` axis block plus the Cartesian-complement
`exclude` list (`klt sim` has no one-at-a-time axis form), and
`build_oat_request()` assembles the `klt sim` request dict around them.
The six drivers that had each carried a private copy of that assembly are
thin wrappers over it now, so a request-schema change is one edit, not six.

The local `klt --version` metadata probe used during record rendering is
shared here for the same reason (issue #1086): `client_version()` returns
the stripped version string when available and `CLIENT_VERSION_UNAVAILABLE`
when the client is absent, fails, or writes empty stdout, so a missing
local executable cannot abort record generation after a simulation report
already exists.

The executing-worker attribution a record renders right after `run_info()`
is shared here for the same reason (issue #1094): `executing_environment()`
takes the submitting host's provenance and one or more `run_info()` dicts and
returns the Environment block's PDK / ngspice lines, the two extras that say
whose they are, and the sentence that says the same in prose. The seven
batch drivers that had each carried a private copy had drifted four ways:
two filled the block's two lines independently and so labelled a half-known
run by the wrong host, four said in prose that the block named the
SUBMITTING host while it stamped the worker's values, six re-parsed and
re-hardcoded `"sky130A @ ..."` over a string `run_info()` had already
formatted, and two compared the host's ngspice version by different rules.

Stdlib plus one pure harness sibling (`corners.corner_id` -- string
formatting, still no PDK), and the subprocess runner is injectable
(`runner=`), so these paths are unit-testable without `klt`, the PDK or
the fleet.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from .corners import corner_id, parse_corner_id

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

#: A full SHA-256 digest as `klt sim` reports one: 64 lowercase hex
#: characters and nothing else. Anything shorter, upper-case or prefixed is
#: not a digest a record may cite as the executing worker's binary.
SHA256_HEX = re.compile(r"[0-9a-f]{64}")

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


#: Placeholder recorded in a simulation record's local client metadata field
#: when `klt --version` cannot be probed or returns empty stdout (issue #1086).
CLIENT_VERSION_UNAVAILABLE = "(klt --version unavailable)"


def default_runner(argv: list[str]) -> tuple[int, str, str]:
    """Run `argv`, returning `(returncode, stdout, stderr)`."""
    done = subprocess.run(argv, capture_output=True, text=True, check=False)
    return done.returncode, done.stdout, done.stderr


def client_version(*, runner=default_runner) -> str:
    """Local `klt --version`, or `CLIENT_VERSION_UNAVAILABLE` when absent.

    Used only for the submitting/rendering host's metadata field in evidence
    records -- never for worker-reported versions (`run_info(report)["jobs"]`)
    and never for simulation submission (where a missing client must still
    fail). Falling back on `OSError`, non-zero exit, or empty stdout ensures
    record rendering cannot abort after a simulation report already exists
    (issue #1086).
    """
    try:
        rc, out, _err = runner(["klt", "--version"])
    except OSError:
        return CLIENT_VERSION_UNAVAILABLE
    if rc != 0:
        return CLIENT_VERSION_UNAVAILABLE
    return (out or "").strip() or CLIENT_VERSION_UNAVAILABLE


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


def write_inputs(workdir: Path, files: dict[str, str]) -> bool:
    """Write the named input files under `workdir` and fence the report cache.

    `submit()` reuses a `report.json` found beside the request by path alone,
    so a work directory re-used after the deck or request changed would
    attach the OLD report to the NEW inputs. This records a fingerprint of
    every input in `inputs.sha256`; when an existing fingerprint differs (or
    a report exists with none), the stale `report.json` is renamed to
    `report.stale-<fingerprint>.json` -- never deleted -- so the next
    `submit()` re-simulates. Returns True when a stale report was set aside.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    for name in sorted(files):
        h.update(name.encode() + b"\0" + files[name].encode() + b"\0")
    fp = h.hexdigest()
    stamp = workdir / "inputs.sha256"
    report = workdir / "report.json"
    previous = stamp.read_text().strip() if stamp.is_file() else None
    stale = report.is_file() and previous != fp
    if stale:
        report.rename(workdir / f"report.stale-{(previous or 'unfingerprinted')[:12]}.json")
    for name, text in files.items():
        (workdir / name).write_text(text)
    stamp.write_text(fp + "\n")
    return stale


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
        # A LOST shard reports as a null fleet entry (a real campaign hit
        # this: 5 of 9 corners `lost_shard`, and reading the report crashed
        # run_info before the campaign could report the loss). A missing
        # shard has unknown environment values and cannot establish consensus.
        if not isinstance(entry, dict):
            entry = {}
        worker = entry.get("worker_environment") or {}
        pdk_stamp = ((worker.get("pdk") or {}).get("stamp_text") or "").strip()
        variant = (worker.get("pdk") or {}).get("variant")
        ng = ngspice_from_banner((worker.get("simulator") or {}).get("version_banner") or "")
        pdk = f"{variant} @ {pdk_stamp.split()[-1]}" if variant and pdk_stamp else pdk_stamp
        pdks.add(pdk or None)
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
    engine_host = (report.get("environment") or {}).get("engine_host")
    build = (report.get("environment") or {}).get("engine_build")
    build = build if isinstance(build, dict) else {}
    digest = build.get("binary_sha256")
    digest = digest if isinstance(digest, str) and SHA256_HEX.fullmatch(digest) else None
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
        "worker_pdks_seen": sorted(pdks - {None}),
        "worker_ngspice_seen": sorted(ngs - {None}),
        "request_feature_status": next(iter(features)) if len(features) == 1 else None,
        # The engine that executed the run (`worker` on a batch job, `local`
        # for a one-unit local run) and the sha256 of ITS ngspice executable.
        # `klt sim`'s collector reports a single digest only when every
        # worker hashed the binary it selected and all agreed (klayout-tools
        # #7356); an older or incomplete capture, or two distinct digests,
        # is a null plus a `reason`. So None here means "no single worker
        # digest was reported" -- which a record must say, never fill in
        # from the submitting host's own ngspice (issue #811).
        "engine_host": engine_host,
        "worker_ngspice_binary_sha256": (
            digest if digest is not None and engine_host == "worker" else None
        ),
        "worker_ngspice_binary_sha256_reason": (
            build.get("reason") if digest is None else None
        ),
    }


def pdk_commit_token(text) -> str:
    """The commit token of a PDK line: the last whitespace-separated token
    after the last `@`.

    That is the token `run_info()` reads off a worker's own stamp
    (`stamp.split()[-1]`), so the forms a line takes compare by commit:
    `"{variant} @ {sha}"`, a stamp the worker reported without a variant,
    and the submitting host's own line. A host line carrying
    `pdk.resolved_commit()`'s "(unverified -- ...)" suffix ends in that
    suffix and never in the commit, so an unverifiable install never
    compares equal to a worker's.
    """
    tokens = str(text or "").rsplit("@", 1)[-1].split()
    return tokens[-1] if tokens else ""


def executing_environment(prov, info) -> dict:
    """Resolve the worker environment for a record, with a labelled fallback
    to the submitting host's provenance (issue #1094).

    `info` is one `run_info()` dict, any iterable of them (a campaign that
    submits one request per variant gets one per variant, and its numbers
    come from several workers), or None. `prov` is the submitting host's own
    provenance, read for `pdk_line` and `ng_version` only.

    The worker's environment is `known` only when every run reported BOTH
    its PDK and its simulator and they all agree. One all-or-nothing rule,
    because the Environment block's PDK and ngspice lines are one claim. Two
    of the seven private copies this replaces filled those lines
    independently and then labelled the PAIR by whether both were present,
    so a run reporting one of the two stamped the worker's value under a
    submitting-host label.

    `pdk` is the worker's `worker_pdk` verbatim: `run_info()` already
    formats it `"{variant} @ {sha}"`, so no campaign re-prefixes it.
    `matches_host` compares the PDK commit (`pdk_commit_token()`) and the
    whole ngspice version string. It is true only for a confirmed match.
    A difference in either known field proves a mismatch. If neither field
    proves a mismatch and host provenance is incomplete, the note reports
    that the comparison is undetermined.

    Returns `{known, pdk, ngspice, runner_klt, matches_host,
    attribution_extra, note}`: `pdk` / `ngspice` are the
    `evidence.environment_block()` arguments, `attribution_extra` the two
    block extras saying whose they are, and `note` the sentence saying the
    same in prose. A record renders all three from this one dict, so its
    prose cannot contradict its block.
    """
    if info is None:
        runs: list = []
    elif isinstance(info, Mapping):
        runs = [info]
    else:
        runs = list(info)
    infos = [run if isinstance(run, Mapping) else {} for run in runs]
    pdks = {run.get("worker_pdk") or None for run in infos}
    ngs = {run.get("worker_ngspice") or None for run in infos}
    worker_pdk = next(iter(pdks)) if len(pdks) == 1 else None
    worker_ng = next(iter(ngs)) if len(ngs) == 1 else None
    known = worker_pdk is not None and worker_ng is not None
    runner_klt = next(
        (job.get("runner_klt_version")
         for run in infos for job in (run.get("jobs") or [])
         if job.get("runner_klt_version")),
        None,
    )
    matches_host = False
    if known:
        host_commit = pdk_commit_token(prov.pdk_line)
        pdk_match = None
        # resolved_commit() can display the expected pin of an unverified install.
        if host_commit not in ("", "unknown") and "(unverified" not in prov.pdk_line:
            pdk_match = host_commit == pdk_commit_token(worker_pdk)
        host_ng = (prov.ng_version or "").strip()
        ng_match = host_ng == worker_ng.strip() if ngspice_from_banner(host_ng) else None
        matches_host = pdk_match is True and ng_match is True
        note = ("The Environment block below names the PDK and ngspice of the "
                "EXECUTING worker. The submitting host recorded "
                f"`{prov.pdk_line}` / `{prov.ng_version}`. ")
        if matches_host:
            note += "They are the same for this run."
        elif pdk_match is False or ng_match is False:
            note += ("**They differ for this run**. A comparison with a run on the "
                     "submitting host cannot isolate the effect of a design change.")
        else:
            note += "The host-to-worker comparison is undetermined."
    else:
        note = ("The worker reports do not establish a single PDK and simulator pair. "
                "The Environment block below names the SUBMITTING host's PDK and ngspice.")
    return {
        "known": known,
        "pdk": worker_pdk if known else prov.pdk_line,
        "ngspice": worker_ng if known else prov.ng_version,
        "runner_klt": runner_klt,
        "matches_host": matches_host,
        "attribution_extra": {
            "PDK / ngspice above": "as run by the executing worker" if known
            else "submitting host (worker environment unknown)",
            "submitting host PDK / ngspice": f"{prov.pdk_line} / {prov.ng_version}",
        },
        "note": note,
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
    report: dict, supply_key: str, *, null_error_corners: bool = True
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

    `null_error_corners=False` keeps each MEASUREMENT's own value at a corner
    whose status is `error`/`inconclusive`. A corner can carry that status
    because ONE measurement produced no value while every other measurement
    solved -- the crossing-search case, where a threshold that is never
    crossed is itself evidence the campaign must RETAIN (a settling study's
    small-swing row), not a reason to throw away the corner's other values.
    `klt` already reports per-measurement values and statuses; the default
    nulling stays the safe read for campaigns where "any error" means "the
    solve is suspect". (Found by the DR-027 candidate campaign: two corners
    lost their whole measured grid to one legitimately-missing bit-0
    crossing.)
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
        if null_error_corners and c.get("status") in ("error", "inconclusive"):
            vals = {k: None for k in vals}
        out[cid] = vals
    return out, run_info(report)


def budget_row(
    rows: list[dict],
    threshold_lsb: float,
    err_key: str,
    *,
    skip_control: bool = True,
) -> dict | None:
    """The LAST row of an ascending sweep whose `err_key` error magnitude is
    still within `threshold_lsb` -- None when no candidate row passes.

    One copy of the largest-passing-value budget rule the drive-budget
    campaigns report by (issue #939, extending #904's reader consolidation):
    the budget is the largest swept value that still passes, NOT the last
    value before the first failure -- sweep error is not monotonic in the
    swept axis, which each campaign's tests assert rather than assume. A
    result equal to the largest swept value is RIGHT-CENSORED (every swept
    value passed, so the true budget is >= that value, not equal to it), and
    a None means even the smallest non-control point already exceeds the
    threshold; callers render both as such ("< first_nonzero", ">= last"),
    never as a budget of 0.

    `skip_control` excludes the sweep's own FIRST row -- the control row
    every later row's error is measured against, whose own error is
    identically zero by construction and would otherwise pass every
    threshold, turning "no swept value works" into a reported budget of "0"
    that only restates the arithmetic. The exclusion is POSITIONAL (the
    first row), not by swept value: the same helper grades a `C_decouple`
    axis as well as an `R_source` axis, and the control row is the sweep's
    own first row on both. Issue #874 is the history: before it the vcm
    copy could not return None at all, and every downstream "none found" /
    "unrescued" branch was dead.
    """
    candidates = rows[1:] if skip_control else rows
    ok = [r for r in candidates if abs(r[err_key]) <= threshold_lsb]
    return ok[-1] if ok else None


#: A `.meas` card's measured-signal reference (`v(node)` / `I(vsrc)`), which
#: saved_vectors() scans the committed cards for.
_VECTOR_RE = re.compile(r"\b([vi])\(([^)]+)\)", re.IGNORECASE)


def split_fragment(
    fragment_text: str, expected_measure_names: list[str]
) -> tuple[str, list[str], str]:
    """Split a committed stimulus/measurement fragment into the three pieces
    a `klt sim` request needs them in: the circuit BODY (sources only --
    `klt sim` owns the `.control`/`.end` wrapper), the `.meas` cards (which
    become `measurements[].spice` entries), and the `.tran` card's arguments
    (which become `analysis.args`).

    Asserted rather than assumed: exactly one `.tran` card, and the `.meas`
    card names must be exactly the CALLING campaign's
    `expected_measure_names`, compared as sorted lists so a missing, an
    extra or a repeated name all fail. A fragment that changes shape fails
    here instead of silently producing a deck that measures something else.
    """
    body: list[str] = []
    meas: list[str] = []
    tran_args: str | None = None
    for line in fragment_text.splitlines():
        stripped = line.strip()
        low = stripped.lower()
        if low.startswith(".meas"):
            meas.append(stripped)
            continue
        if low.startswith(".tran"):
            if tran_args is not None:
                raise RuntimeError(
                    "expected exactly one .tran card in the committed fragment, "
                    "found more -- the fragment changed shape; re-derive the "
                    "campaign that reads it."
                )
            tran_args = stripped.split(None, 1)[1].strip()
            continue
        body.append(line)
    if not tran_args:
        raise RuntimeError(
            "no .tran card found in the committed fragment -- the fragment "
            "changed shape; re-derive the campaign that reads it."
        )
    names = sorted(card.split()[2] for card in meas)
    expected = sorted(expected_measure_names)
    if names != expected:
        raise RuntimeError(
            f"committed fragment declares {len(names)} .meas cards, the "
            f"campaign's expected measurement names number {len(expected)}, "
            "and the two sorted lists differ -- the fragment changed shape; "
            "re-derive the campaign that reads it."
        )
    return "\n".join(body) + "\n", meas, tran_args


def saved_vectors(meas_cards: list[str]) -> list[str]:
    """Exactly the vectors the `.meas` cards read, as one sorted,
    de-duplicated `v(node)` / `i(source)` name per measured signal, so a
    whole-ADC transient over ~2000 devices does not carry a `save all`
    rawfile per unit."""
    found = set()
    for card in meas_cards:
        for kind, node in _VECTOR_RE.findall(card):
            found.add(f"{kind.lower()}({node.strip().lower()})")
    return sorted(found)


def oat_corners(
    corner_ids: Sequence[str], supply_key: str
) -> tuple[dict, list[dict]]:
    """The `corners` axis block and `exclude` list for a one-at-a-time PVT
    grid given as corner-id strings.

    `klt sim` has no OAT axis form, so a campaign declares the full cross
    product of its distinct process / temperature / supply values and lists
    the points the grid omits under `exclude`. Six drivers carried
    byte-identical private copies of this expansion (issues #1052, #1054);
    this is the one copy. `exclude` is empty when the ids already cover the
    full product (a single corner, or a complete grid).
    """
    pts = [parse_corner_id(c) for c in corner_ids]
    procs = sorted({p for p, _, _ in pts})
    temps = sorted({t for _, t, _ in pts})
    vdds = sorted({v for _, _, v in pts})
    want = set(pts)
    exclude = [
        {"process": p, "temperature_c": t, "supply_v": {supply_key: v}}
        for p in procs
        for t in temps
        for v in vdds
        if (p, t, v) not in want
    ]
    corners = {
        "process": procs,
        "supply_v": {supply_key: vdds},
        "temperature_c": temps,
    }
    return corners, exclude


def build_oat_request(
    netlist_name: str,
    corner_ids: Sequence[str],
    supply_key: str,
    *,
    analysis_steps: list[dict] | None = None,
    analysis: dict | None = None,
    measurements: list[dict] | None = None,
    timeout_s: float = 900.0,
    keep_artifacts: bool = True,
    pdk: str = "sky130A",
    models_lib: str = "libs.tech/combined/sky130.lib.spice",
    backend: str | None = None,
    batch: dict | None = None,
    hosts: int | None = None,
) -> dict:
    """One `klt sim` request for an OAT corners campaign (issues #1052,
    #1054).

    Two request shapes, one per campaign family, and never both or neither:
    `analysis_steps=` (a step-per-point campaign) or the `analysis=` +
    `measurements=` pair (a single-analysis campaign). The dict this
    returns -- keys, values and insertion order -- is byte-for-byte what
    the consolidated drivers assembled privately, so no committed request
    artifact changes shape. `hosts` > 1 appends a `remote` block (the
    shared-fleet sharding knob) after every other conditional key.
    """
    has_steps = analysis_steps is not None
    if has_steps and (analysis is not None or measurements is not None):
        raise ValueError(
            "build_oat_request() takes analysis_steps= or the analysis= + "
            "measurements= pair, never both at once"
        )
    if not has_steps and not (analysis is not None and measurements is not None):
        raise ValueError(
            "build_oat_request() takes analysis_steps= or the analysis= + "
            "measurements= pair -- one of the two is required, and the pair "
            "is all-or-nothing"
        )
    corners, exclude = oat_corners(corner_ids, supply_key)
    req: dict = {
        "netlist": netlist_name,
        "engine": "ngspice",
        "models": {"pdk": pdk, "lib": models_lib},
        "corners": corners,
    }
    if has_steps:
        req["analysis_steps"] = analysis_steps
    else:
        req["analysis"] = analysis
        req["measurements"] = measurements
    req["options"] = {"timeout_s": timeout_s, "keep_artifacts": keep_artifacts}
    if exclude:
        req["exclude"] = exclude
    if backend:
        req["backend"] = backend
    if batch:
        req["batch"] = dict(batch)
    if hosts and hosts > 1:
        req["remote"] = {"hosts": hosts}
    return req

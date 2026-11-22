"""Toolchain version pin checks against sim/toolchain.json.

Exit-code convention (mirrors gf180-sar-adc's sim/harness/toolchain.py):
  0 -- everything installed and within pin (warnings may still be reported).
  1 -- something installed but DRIFTED from the pin (real problem: results
       would not be comparable with existing records).
  3 -- a required tool (ngspice) or the PDK itself is simply MISSING
       (skippable on a machine that hasn't been bootstrapped yet).

Drift is fatal; a *warning* is not. The distinction is which tool the
evidence actually depends on. Every number recorded under sim/ comes out of
ngspice reading the PDK model library, so an ngspice or open_pdks drift makes
records incomparable and must stop the run. xschem only converts a schematic
into a netlist, and each record already pins the exact netlist it ran by
SHA-256 (see evidence.py) -- so an xschem version difference is recorded and
reported, but does not invalidate anything and must not block a PVT run.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import pdk

SIM_DIR = Path(__file__).resolve().parent.parent

# Wall-clock budget for a single toolchain subprocess invocation (ngspice
# transient/op run, or an experiment's own xschem netlisting step -- see
# TIMEOUT_ENV_VAR below). A single knob rather than one literal per call
# site (issue #133): a genuinely hung run must still fail fast, but the
# fixed 120s default previously hardcoded here (and duplicated at
# sim/sar-sequencer-behavioral/run_testbench.py's own xschem subprocess.run
# call) made the documented cold-start invocation fail on a slower-but-
# still-progressing host.
DEFAULT_TOOLCHAIN_TIMEOUT_S = 120
TIMEOUT_ENV_VAR = "SIM_NGSPICE_TIMEOUT_S"


def toolchain_timeout_s() -> float:
    """Wall-clock budget (seconds) for one toolchain subprocess invocation
    (ngspice -b, or an experiment's own xschem netlisting step).

    Defaults to DEFAULT_TOOLCHAIN_TIMEOUT_S. Overridable via the
    SIM_NGSPICE_TIMEOUT_S environment variable so a slow-but-progressing
    host (see issue #133) does not require editing this file -- a
    genuinely hung run still fails, just against whatever budget is set
    here rather than a hardcoded literal.
    """
    raw = os.environ.get(TIMEOUT_ENV_VAR, "").strip()
    if not raw:
        return DEFAULT_TOOLCHAIN_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        raise RuntimeError(
            f"{TIMEOUT_ENV_VAR}={raw!r} is not a number of seconds "
            f"(e.g. {TIMEOUT_ENV_VAR}=300)"
        ) from None
    if value <= 0:
        raise RuntimeError(f"{TIMEOUT_ENV_VAR}={raw!r} must be > 0 seconds")
    return value


@dataclass
class CheckResult:
    status: int  # 0 ok, 1 drift, 3 missing
    messages: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _load() -> dict:
    with (SIM_DIR / "toolchain.json").open() as f:
        return json.load(f)


def _ngspice_version() -> str | None:
    if shutil.which("ngspice") is None:
        return None
    out = subprocess.run(["ngspice", "--version"], capture_output=True, text=True).stdout
    m = re.search(r"ngspice-(\d+)", out)
    return m.group(0) if m else out.splitlines()[0].strip()


def _ngspice_major(version_str: str) -> int | None:
    m = re.search(r"ngspice-(\d+)", version_str)
    return int(m.group(1)) if m else None


def run_ngspice(netlist_text: str, scratch_dir: Path, log_name: str) -> str:
    """Write `netlist_text` into `scratch_dir` and invoke ngspice on it,
    enforcing the toolchain_timeout_s() budget (default
    DEFAULT_TOOLCHAIN_TIMEOUT_S = 120s, overridable via the
    SIM_NGSPICE_TIMEOUT_S env var -- see toolchain_timeout_s()) and raising
    RuntimeError on a nonzero exit.

    Shared by sim/harness/runner.py (PVT corner sweeps) and
    sim/harness/mc_runner.py (Monte Carlo sweeps) -- both shell out to
    ngspice identically, so the invocation lives here alongside the other
    ngspice-adjacent helpers (_ngspice_version() / _ngspice_major()).
    """
    scratch_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SIM_DIR / "spiceinit", scratch_dir / ".spiceinit")
    netlist_path = scratch_dir / f"{log_name}.spice"
    netlist_path.write_text(netlist_text)
    timeout_s = toolchain_timeout_s()
    try:
        proc = subprocess.run(
            ["ngspice", "-b", str(netlist_path)],
            cwd=scratch_dir,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        # exc.stdout/exc.stderr can surface as bytes here even though this
        # call passes text=True: CPython's subprocess.run() only re-decodes
        # them on the Windows retry path: on POSIX, TimeoutExpired's own
        # partial-output attributes (captured inside Popen.communicate()
        # before the timeout fired) are not guaranteed to have gone through
        # the text-mode decode step the successful-completion path does.
        # str(...) is a safe, minimal normalization -- bytes.__str__ 's
        # b'...'-quoted form is acceptable for the last-output message
        # below, since this is a timeout diagnostic, not a value comparison
        # (found via a real, reproducible ngspice timeout while gathering
        # evidence for issue #61, not a hypothetical).
        def _text(part: str | bytes | None) -> str:
            if part is None:
                return ""
            return part.decode(errors="replace") if isinstance(part, bytes) else part

        out = _text(exc.stdout) + _text(exc.stderr)
        raise RuntimeError(
            f"ngspice timed out after {timeout_s:g}s running {netlist_path.name} "
            f"(last output:\n{out[-2000:]})\n"
            f"If ngspice was still making progress (not hung), raise the budget "
            f"with e.g. {TIMEOUT_ENV_VAR}=300 (seconds) in the environment before "
            f"re-running."
        ) from exc
    output = proc.stdout + proc.stderr
    if proc.returncode != 0:
        # A crashed/erroring ngspice must not be allowed to silently read as
        # "ran fine, just produced no measurement" -- that only surfaces
        # today when the measurement in question has a `checks` entry, and
        # is otherwise invisible. Fail loudly instead.
        raise RuntimeError(
            f"ngspice exited {proc.returncode} running {netlist_path.name} "
            f"(output:\n{output[-2000:]})"
        )
    return output


def run_ngspice_with_retry(
    netlist_text: str, scratch_dir: Path, log_name: str, attempts: int = 4
) -> str:
    """run_ngspice() with a few bounded retries and backoff on timeout,
    returning the same raw log text run_ngspice() itself returns.

    run_ngspice() enforces a hard toolchain_timeout_s() budget (default
    DEFAULT_TOOLCHAIN_TIMEOUT_S = 120s) per invocation. On a shared/
    contended machine (e.g. another concurrent agent's own PVT corner
    sweep pegging every CPU core) that budget has been observed to push
    individual runs well past it despite nothing about the netlist itself
    changing (confirmed by re-running the identical netlist in isolation
    once the machine was quieter and seeing it finish quickly again). A
    few bounded retries with a short backoff absorb that transient
    contention without masking a genuine, reproducible slowdown --
    exhausting every retry on the same netlist still raises.

    Consolidated from six byte-for-byte-identical copies across
    sim/*/run_*.py's own `_run()`/`_run_ngspice()` helpers (issue #299),
    each of which re-implemented this same attempt-count/backoff/warning
    loop. `attempts` defaults to 4 (five of the six original call sites);
    pass a lower value (e.g. 3, as
    sim/full-conversion-transient/run_conversion.py's own call does) when a
    single attempt is expensive enough that a full 4 retries would blow
    past that campaign's own wall-clock budget.
    """
    for attempt in range(1, attempts + 1):
        try:
            return run_ngspice(netlist_text, scratch_dir, log_name)
        except RuntimeError as exc:
            if "timed out" not in str(exc) or attempt == attempts:
                raise
            print(
                f"  (warning: {log_name} timed out (attempt {attempt}/{attempts}), "
                f"retrying after a short backoff -- machine likely contended)",
                file=sys.stderr,
            )
            time.sleep(15 * attempt)
    raise AssertionError("unreachable")  # loop always returns or raises above


def netlist_is_complete(out_path: Path) -> bool:
    """True when `out_path` looks like a netlist xschem finished writing:
    the commented `**.subckt` header line is present and the last non-blank
    card is `.end`.

    This is the structural test `netlist_with_xschem(...,
    accept_complete_on_nonzero=True)` substitutes for the exit code; see that
    function's docstring for which schematics need it and why. A file that
    does not exist is not complete (False, not an exception), so callers can
    use it as a plain predicate.
    """
    if not out_path.is_file():
        return False
    cards = [line for line in out_path.read_text().splitlines() if line.strip()]
    if not cards:
        return False
    return (
        any(line.startswith("**.subckt") for line in cards)
        and cards[-1].strip() == ".end"
    )


def netlist_with_xschem(
    design_sch: Path,
    scratch_dir: Path,
    xschemrc: Path,
    out_name: str,
    *,
    accept_complete_on_nonzero: bool = False,
) -> Path:
    """Netlist `design_sch` with xschem (headless), returning the path to the
    generated `out_name` file under `scratch_dir`. Raises RuntimeError on any
    xschem error/nonzero exit, or if the expected output file is missing.

    Shares its timeout budget with run_ngspice()'s own ngspice invocations
    (issue #133) via toolchain_timeout_s()/TIMEOUT_ENV_VAR, so
    SIM_NGSPICE_TIMEOUT_S raises both this step's and any subsequent .tran
    run's budget together on a slower-but-still-progressing host.

    Extracted from two byte-identical call sites (issue #205):
    sim/sar-sequencer-behavioral/run_testbench.py's and
    sim/sequencer-logic-delay/run_sequencer_logic_delay.py's own
    `netlist_dut()` functions, both netlisting design/sar_sequencer.sch this
    same way. Parameterized over the design schematic, xschemrc path, and
    expected output filename so it is not tied to any one DUT.

    `accept_complete_on_nonzero` (issue #860) opts a caller into the one
    documented xschem quirk this repo hits: xschem's exit code reflects its
    electrical-rule check, not whether netlisting succeeded, so a schematic
    that deliberately leaves nets open exits nonzero having written a
    complete, correct netlist. Measured with the pinned xschem 3.4.7 on this
    repo's own schematics, `design/sampling_frontend.sch`,
    `design/sar_sequencer.sch` and `design/cdac/cdac_unit_cell.sch` all
    netlist with exit 0, while `design/cdac/cdac_array.sch` and
    `design/sar_adc_top.sch` exit **10** with empty stdout/stderr -- having
    written a netlist whose device lines are byte-identical to the committed
    fragment, ending with the `**.ends` / `.end` pair xschem emits last.
    With the keyword set, such a run is accepted ONLY when
    netlist_is_complete() holds for the output file -- a genuinely truncated
    netlist still raises, and so does a missing one. The default stays
    strict, so the two `netlist_dut()` callers above are unaffected.

    Consolidated (issue #860) from two private re-implementations that each
    answered "xschem exited nonzero; was the netlist good?" differently:
    sim/sampling-cdac-handoff/run_handoff.py's `_netlist_schematic()` (this
    completeness test, in a try/except around this helper) and
    layout/cdac-array/bin/generate-lvs-reference.py's `netlist_schematic()`
    (a bare `subprocess.run(..., check=False)` with no timeout and no
    completeness test at all, so a hung xschem hung the LVS-reference step
    and a truncated netlist was accepted as the LVS reference).
    """
    scratch_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "xschem", "-x", "-n", "-s", "-q",
        "--rcfile", str(xschemrc),
        "-o", str(scratch_dir),
        str(design_sch),
    ]
    timeout_s = toolchain_timeout_s()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"xschem netlisting of {design_sch} timed out after {timeout_s:g}s. "
            f"If xschem was still making progress (not hung), raise the budget "
            f"with e.g. {TIMEOUT_ENV_VAR}=300 (seconds) in the environment "
            f"before re-running."
        ) from exc
    out_path = scratch_dir / out_name
    if proc.returncode != 0 and accept_complete_on_nonzero:
        if netlist_is_complete(out_path):
            print(
                f"  (note: xschem exited {proc.returncode} on {design_sch.name} but "
                f"wrote a complete netlist -- accepted, see netlist_with_xschem()'s "
                f"docstring on accept_complete_on_nonzero)"
            )
            return out_path
    if proc.returncode != 0 or not out_path.is_file():
        raise RuntimeError(
            f"xschem netlisting of {design_sch} failed (exit {proc.returncode}):\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
    return out_path


def deck_preamble(
    corner: str, temp_c: float, title: str, *, extra_lines: list[str] | None = None
) -> list[str]:
    """Common leading lines of a hand-assembled (non sim/run_corners.py)
    transient deck: a title comment, `.lib <corner>`, `.temp`, any
    `extra_lines` (e.g. a `.model` card), then a blank separator line.

    Extracted from three call sites' own `_preamble()` (issue #205):
    sim/sampling-frontend/run_hold_kick.py and
    sim/vcm-drive-budget/run_vcm_drive_budget.py were byte-identical;
    sim/cdac-bit-trial-settling/run_bit_trial_settling.py added one extra
    `.model SWMOD ...` card, now expressed via `extra_lines` instead of a
    third near-duplicate copy.
    """
    info = pdk.resolve()
    return [
        f"* {title}",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        *(extra_lines or []),
        "",
    ]


def read_wrdata_csv(path: Path, n_vectors: int) -> list[list[float]]:
    """Parse an ngspice `wrdata` output file: one row per timestep, with
    each requested vector contributing its OWN (time, value) column pair --
    ngspice repeats the time column once per vector rather than sharing a
    single time column (verified empirically: `wrdata f.csv v(a) v(b) v(c)`
    writes 2*3=6 columns per row, `time0 a time1 b time2 c`, not 1+3=4).
    Returns `n_vectors + 1` lists: the shared time axis (taken from the
    first vector's own time column) first, then one value list per
    requested vector, in the order they were named in the `wrdata`
    command."""
    series: list[list[float]] = [[] for _ in range(n_vectors + 1)]
    expected_cols = 2 * n_vectors
    for line in path.read_text().splitlines():
        parts = line.split()
        if not parts:
            continue
        try:
            vals = [float(x) for x in parts]
        except ValueError:
            continue
        if len(vals) < expected_cols:
            continue
        series[0].append(vals[0])
        for i in range(n_vectors):
            series[i + 1].append(vals[2 * i + 1])
    return series


def _xschem_version() -> str | None:
    if shutil.which("xschem") is None:
        return None
    out = subprocess.run(["xschem", "-v"], capture_output=True, text=True)
    text = (out.stdout or "") + (out.stderr or "")
    m = re.search(r"XSCHEM V([\d.]+)", text)
    return m.group(1) if m else None


def check_env(allow_drift: bool = False) -> CheckResult:
    cfg = _load()
    msgs: list[str] = []
    warns: list[str] = []

    py_min = tuple(int(x) for x in cfg["python_min"].split("."))
    py_have = sys.version_info[:2]
    if py_have < py_min:
        msgs.append(
            f"python {py_have[0]}.{py_have[1]} < required floor "
            f"{py_min[0]}.{py_min[1]}"
        )

    ng_version = _ngspice_version()
    if ng_version is None:
        return CheckResult(status=3, messages=["ngspice not found on PATH"])
    ng_major = _ngspice_major(ng_version)
    if ng_major is None or ng_major < cfg["ngspice_min_major"]:
        msgs.append(
            f"ngspice version '{ng_version}' below floor "
            f"ngspice-{cfg['ngspice_min_major']}"
        )

    # xschem drift is a warning, not drift-fatal: see this module's docstring
    # for why the netlist SHA-256 in each record already covers it. Left out
    # of `msgs` deliberately, so a machine with a differently-versioned xschem
    # can still produce comparable ngspice-level evidence.
    xs_version = _xschem_version()
    if xs_version is not None and xs_version != cfg["xschem_tag"]:
        warns.append(
            f"xschem {xs_version} != pinned tag {cfg['xschem_tag']} -- "
            "recorded, not fatal: PVT/MC evidence is ngspice-level and each "
            "record pins its netlist by SHA-256. Re-netlist and re-record if "
            "you need a schematic-level claim from this machine."
        )

    info = pdk.resolve()
    if not info.found:
        return CheckResult(status=3, messages=[*msgs, info.error], warnings=warns)

    if cfg["open_pdks"] is not None:
        # Fail closed: resolved_commit_verified() returns None for any
        # install whose provenance can't be confirmed (no SOURCES file at the
        # tree root and no volare-shaped path). Such an install
        # must NEVER read as "on pin" just because pdk.resolved_commit()'s
        # display fallback happens to start with the pin string -- that was
        # exactly the gap this branch used to have.
        verified = pdk.resolved_commit_verified(info)
        if verified is None:
            warns.append(
                f"PDK commit provenance unverifiable at {info.variant_dir} "
                "(no SOURCES file, non-volare layout) -- cannot confirm it matches pinned "
                f"'{cfg['open_pdks']}' (sim/toolchain.json / sim/pdk.json); "
                "evidence records from this install are marked unverified"
            )
        elif verified != cfg["open_pdks"] and not verified.startswith(cfg["open_pdks"]):
            msgs.append(
                f"installed PDK commit '{verified}' != pinned "
                f"'{cfg['open_pdks']}' (sim/toolchain.json / sim/pdk.json)"
            )

    if msgs and not allow_drift:
        return CheckResult(status=1, messages=msgs, warnings=warns)
    return CheckResult(status=0, messages=msgs, warnings=warns)


def preflight(check: CheckResult | None = None) -> int | None:
    """Apply this module's exit-code convention at a driver entry point.

    Returns the exit code the caller should return immediately, or None
    when the run may proceed:

      status 3 (a required tool or the PDK is MISSING) -> print SKIP with
        every message, return 0. A machine that has not been bootstrapped
        is not a failure.
      status 1 (something is installed but DRIFTED from the pin) -> print
        FAIL with every message, return 1. Results would not be comparable
        with the existing records.
      otherwise -> print every check.warnings entry as `WARNING: <text>`
        and return None. A warning is recorded and reported, never fatal
        (see this module's docstring for the drift/warning split).

    Pass an already-computed `check` when the caller needs the same
    CheckResult for something else -- e.g. run_conversion.py and
    run_supply_impedance.py share one with their `--check-env` report
    branch, and probing twice would both cost a second round of
    subprocess/PDK probes and break the tests that assert check_env() is
    called exactly once per main(). Otherwise the helper probes itself.

    Issue #854: ten driver entry points each re-implemented this inline, in
    three spellings, and two of them never read check.warnings at all --
    so a run on a machine with an xschem drift or an unverifiable PDK
    provenance proceeded without telling the operator.
    """
    if check is None:
        check = check_env()
    if check.status == 3:
        print("SKIP: ngspice or the pinned PDK is not installed on this machine.")
        for m in check.messages:
            print(f"  {m}")
        return 0
    if check.status == 1:
        print("FAIL: toolchain drifted from sim/toolchain.json pin.")
        for m in check.messages:
            print(f"  {m}")
        return 1
    for w in check.warnings:
        print(f"WARNING: {w}")
    return None


def summary() -> str:
    cfg = _load()
    ng = _ngspice_version() or "MISSING"
    xs = _xschem_version() or "MISSING"
    info = pdk.resolve()
    pdk_line = (
        f"{info.variant} @ {pdk.resolved_commit(info)} ({info.variant_dir})"
        if info.found
        else f"NOT FOUND ({info.error})"
    )
    return (
        f"ngspice: {ng} (floor ngspice-{cfg['ngspice_min_major']})\n"
        f"xschem: {xs} (pinned {cfg['xschem_tag']})\n"
        f"python: {sys.version.split()[0]} (floor {cfg['python_min']})\n"
        f"PDK: {pdk_line}\n"
    )

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
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import pdk

SIM_DIR = Path(__file__).resolve().parent.parent


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
    enforcing a 120s timeout and raising RuntimeError on a nonzero exit.

    Shared by sim/harness/runner.py (PVT corner sweeps) and
    sim/harness/mc_runner.py (Monte Carlo sweeps) -- both shell out to
    ngspice identically, so the invocation lives here alongside the other
    ngspice-adjacent helpers (_ngspice_version() / _ngspice_major()).
    """
    scratch_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SIM_DIR / "spiceinit", scratch_dir / ".spiceinit")
    netlist_path = scratch_dir / f"{log_name}.spice"
    netlist_path.write_text(netlist_text)
    try:
        proc = subprocess.run(
            ["ngspice", "-b", str(netlist_path)],
            cwd=scratch_dir,
            capture_output=True,
            text=True,
            timeout=120,
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
            f"ngspice timed out after 120s running {netlist_path.name} "
            f"(last output:\n{out[-2000:]})"
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
        # install whose provenance can't be confirmed through volare's path
        # layout (e.g. a hand-installed / non-volare PDK). Such an install
        # must NEVER read as "on pin" just because pdk.resolved_commit()'s
        # display fallback happens to start with the pin string -- that was
        # exactly the gap this branch used to have.
        verified = pdk.resolved_commit_verified(info)
        if verified is None:
            warns.append(
                f"PDK commit provenance unverifiable at {info.variant_dir} "
                "(non-volare layout) -- cannot confirm it matches pinned "
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

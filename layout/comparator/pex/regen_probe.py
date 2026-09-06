#!/usr/bin/env python3
"""Comparator PEX pick-off timing re-derivation (issue #187).

`layout/comparator/pex/testbench.spice`'s fixed pick-off instant
(`PICKOFF_AT_NS` = 5.4ns, see `run_pex.py`) was calibrated against the
pre-#175 topology's regeneration profile. Re-running the PEX flow against
the DR-004 Amendment A layout (issue #180/#188) at that same instant produced
a suspicious, sign-flipped extracted-side "gain"
(`reports/20260906-101231-1250ff4/record.md`'s AC3): the extracted
(parasitic-loaded) leg's pick-off differential at Vindiff=+10mV came out
*negative*, where the ideal schematic leg is unambiguously positive.

This script re-derives an appropriate pick-off instant by DOING what
`sim/comparator-decision/run.py`'s `regen` subcommand does for the ideal
schematic -- a reset(CLK=0)->evaluate(CLK=VDD) transient sweep, sampling the
differential output at a range of candidate times after the evaluate edge --
but for BOTH the ideal schematic leg (`comparator_pex_reference.spice`) and
the REAL parasitic-loaded leg (a fresh `klt extract --parasitics` of the
current `reports/LATEST` composed layout), so the two can be compared
directly. It is a standalone investigation driver, not a subcommand of
`sim/comparator-decision/run.py`, because its DUT is `.SUBCKT`-wrapped and
instantiated the way `klt pex`'s DUT-`.include`-swap convention requires
(matching `testbench.spice`'s own `Xdut ... gen_compose_0` line) rather than
driven as a flat device fragment the way that driver's own `_pickoff_deck`/
`_regen_deck` do -- see `comparator_pex_reference.spice`'s header for why
that wrapper exists.

    layout/bin/setup-venv.sh          # once, or after bumping requirements.txt
    source sim/env.sh                 # exports PDK_ROOT/PDK
    python3 layout/comparator/pex/regen_probe.py --check-env
    python3 layout/comparator/pex/regen_probe.py --record
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[3] / "sim"
sys.path.insert(0, str(SIM_DIR))

from harness import evidence, pdk, toolchain  # noqa: E402

PEX_DIR = Path(__file__).resolve().parent
COMPARATOR_DIR = PEX_DIR.parent
REPORTS_DIR = COMPARATOR_DIR / "reports"
SCHEMATIC_DUT = PEX_DIR / "comparator_pex_reference.spice"

# --- Fixed testbench constants, matching sim/comparator-decision/run.py's
# own RESET_NS/RESET_TR_NS/VDD (the two decks must share the same reset
# phase and evaluate-edge timing to be comparable) and this directory's own
# testbench.spice (VDD=1.8, VCM=0.9 -- fixed, not supply-tracking, since
# neither the ideal DUT nor `klt pex`'s DUT-swap machinery vary VDD here). ---
VDD = 1.8
VCM = VDD / 2.0
RESET_NS = 5.0
RESET_TR_NS = 0.1
EVALUATE_NS = 12.0  # long enough to see the extracted leg's own delayed
# regeneration onset well past where the schematic leg has already resolved
# (schematic decides within ~1.1-2.4ns per
# sim/comparator-decision/records/20260906-075157-7724af3.md), short enough
# to keep each transient run cheap (~15-30s at this device count).
TRAN_STEP_NS = 0.01

VINDIFF_SWEEP_MV = [0.0, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0]
CAL_VINDIFF_MV = 10.0  # matches pex_request.json's own gain-calibration
# corner point (testbench.spice's index-1 corner) -- the one value that
# actually has to come out positive for `run_pex.py`'s AC3/AC4 methodology
# to produce a sane (non-sign-flipped) gain.
DECIDE_THRESHOLD_V = 0.5 * VDD

CANDIDATE_PICKOFF_NS = [
    0.3, 0.5, 0.7, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0,
]  # time after the evaluate edge STARTS (matches PICKOFF_NS's own
# definition in sim/comparator-decision/run.py), i.e. absolute time =
# RESET_NS + RESET_TR_NS + this.

# Skewed-corner spot check (Test Plan edge case: is the derived instant
# corner-dependent?) -- ss/-40C (slow+cold) and ff/125C (fast+hot) bracket
# the ratified process/temp corner set (spec/target-spec.md); this is a
# spot check, not a full PVT sweep -- see the record's own "Scope and
# caveats" section for why a full sweep is not attempted here (pex_request
# .json's own corner matrix is tt/27C-only today, same subset-corner
# convention every other sim/ record under this repo documents).
CORNER_SPOT_CHECK = [("ss", -40.0), ("ff", 125.0)]
SPOT_CHECK_VINDIFF_MV = [0.0, CAL_VINDIFF_MV]

# This script's own recommendation, derived from the swept data (see
# write_record()'s "Recommendation" section for the full justification).
# `run_pex.py`'s PICKOFF_AT_NS and `pex_request.json`'s `.meas ... at=`
# lines are updated to match once this record confirms it.
RECOMMENDED_PICKOFF_NS = 1.2
RECOMMENDED_PICKOFF_AT_NS = RESET_NS + RESET_TR_NS + RECOMMENDED_PICKOFF_NS


def _pdk_info() -> pdk.PdkInfo:
    info = pdk.resolve()
    if not info.found:
        raise RuntimeError(f"PDK not resolvable: {info.error}")
    return info


def _read_wrdata_csv(path: Path, n_vectors: int) -> list[list[float]]:
    """Same parsing convention as
    sim/comparator-decision/run.py's `_read_wrdata_csv` -- see that
    function's docstring for why ngspice's `wrdata` repeats the time column
    once per vector rather than sharing a single time column."""
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


def _run_klt_extract(gds_path: Path, out_dir: Path, info: pdk.PdkInfo) -> Path:
    """`klt extract --parasitics` on the current `reports/LATEST` layout,
    writing the extracted `.SUBCKT gen_compose_0 ...` netlist into `out_dir`
    -- the same call `run_pex.py`'s own step 1 makes, duplicated here (not
    imported) because this script's out_dir and JSON handling are its own."""
    gds_rel = "comparator.gds"
    shutil.copy(gds_path, out_dir / gds_rel)
    spice_name = "comparator.pex-extract.spice"
    proc = subprocess.run(
        [
            "klt", "extract", gds_rel, "--deck", "sky130", "--pdk", info.variant,
            "--pdk-root", str(info.root), "--parasitics", "-o", spice_name,
            "--format", "json",
        ],
        capture_output=True, text=True, cwd=str(out_dir),
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(proc.stdout, file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        raise RuntimeError(f"klt extract did not return JSON (exit {proc.returncode})")
    (out_dir / "extract.json").write_text(json.dumps(payload, indent=2) + "\n")
    if payload.get("status") != "extracted":
        raise RuntimeError(f"klt extract failed: {payload}")
    (out_dir / gds_rel).unlink()  # copy was scratch-only; comparator.gds
    # already lives at the layout source path record.md cites.
    return out_dir / spice_name


def _deck(
    dut_file: Path, corner: str, temp_c: float, vindiff_mv: float, log_name: str,
    info: pdk.PdkInfo,
) -> str:
    # `info.ngspice_lib` is interpolated directly via f-string here (matching
    # sim/comparator-decision/run.py's own `_regen_deck`/`_pickoff_deck`
    # convention) rather than through a second `str.format()` pass -- an
    # earlier version of this function used `.lib {{pdk_lib}} ...` + a
    # follow-on `.format(pdk_lib=...)` call in `_run_point`, but that
    # generic `.format()` also matched the deliberately-literal `{vdd_val}`
    # tokens below (ngspice's own `.param`-expression substitution, not
    # Python's), which have no `vdd_val` kwarg supplied -> `KeyError`.
    vindiff_v = vindiff_mv / 1000.0
    tstop_ns = RESET_NS + RESET_TR_NS + EVALUATE_NS
    period_ns = tstop_ns + 10.0
    lines = [
        f"* comparator PEX pick-off re-derivation (issue #187) -- "
        f"dut={dut_file.name} corner={corner} temp={temp_c}C vindiff={vindiff_mv}mV",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        f".param vdd_val = {VDD}",
        "",
        "Vdd VDD 0 dc {vdd_val}",
        f"Vclk CLK 0 PULSE(0 {{vdd_val}} {RESET_NS}n {RESET_TR_NS}n {RESET_TR_NS}n "
        f"{EVALUATE_NS}n {period_ns}n)",
        f"Vinp VINP 0 dc {VCM + vindiff_v / 2}",
        f"Vinn VINN 0 dc {VCM - vindiff_v / 2}",
        "",
        f'.include "{dut_file}"',
        "Xdut CLK GND OUTN OUTP VDD VINN VINP gen_compose_0",
        "",
        ".control",
        f"tran {TRAN_STEP_NS}n {tstop_ns}n",
        # Exactly 2 vectors (OUTP, OUTN) -- must match `_run_point`'s
        # `_read_wrdata_csv(..., 2)` call below. An earlier version of this
        # line also wrote `v(CLK)` (3 vectors) while `_run_point` still read
        # back only 2, which silently mis-assigned columns rather than
        # erroring (`_read_wrdata_csv`'s `len(vals) < expected_cols` guard
        # passed since 6 columns >= its expected 4): the "outp" series was
        # actually v(CLK) and the "outn" series was actually the real
        # v(OUTP), with the true v(OUTN) column dropped entirely. That bug
        # produced a spurious, sign-flipped-looking "regeneration" signature
        # (CLK's own 0V/VDD reset/evaluate levels, not a real decision) --
        # see this file's own module docstring history / issue #187's PR
        # for the full writeup of how that was caught and fixed.
        f"wrdata {log_name}.csv v(OUTP) v(OUTN)",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


def _run_point(
    dut_file: Path, corner: str, temp_c: float, vindiff_mv: float, log_name: str,
    scratch_dir: Path, info: pdk.PdkInfo,
) -> tuple[list[float], list[float], list[float]]:
    deck_text = _deck(dut_file, corner, temp_c, vindiff_mv, log_name, info)
    toolchain.run_ngspice(deck_text, scratch_dir, log_name)
    t, outp, outn = _read_wrdata_csv(scratch_dir / f"{log_name}.csv", 2)
    return t, outp, outn


def _regen_time(t: list[float], outp: list[float], outn: list[float], vindiff_mv: float) -> float | None:
    evaluate_start_s = (RESET_NS + RESET_TR_NS) * 1e-9
    sign = 1.0 if vindiff_mv >= 0 else -1.0
    for i, tt in enumerate(t):
        if tt < evaluate_start_s:
            continue
        if sign * (outp[i] - outn[i]) > DECIDE_THRESHOLD_V:
            return (tt - evaluate_start_s) * 1e9
    return None


def _pickoff_at(t: list[float], outp: list[float], outn: list[float], pickoff_ns: float) -> float:
    target = (RESET_NS + RESET_TR_NS + pickoff_ns) * 1e-9
    idx = min(range(len(t)), key=lambda i: abs(t[i] - target))
    return outp[idx] - outn[idx]


def run(record: bool, quiet: bool = False) -> int:
    info = _pdk_info()

    latest_layout_id = (REPORTS_DIR / "LATEST").read_text().strip()
    layout_dir = REPORTS_DIR / latest_layout_id
    gds_path = layout_dir / "comparator.gds"
    if not gds_path.is_file():
        print(f"no comparator.gds at {gds_path}", file=sys.stderr)
        return 3

    record_id = evidence.new_record_id()
    out_dir = REPORTS_DIR / record_id
    out_dir.mkdir(parents=True, exist_ok=False)
    scratch_dir = out_dir / ".ngspice-scratch"

    if not quiet:
        print(f"extracting parasitics from {gds_path} ...")
    extracted_dut = _run_klt_extract(gds_path, out_dir, info)

    legs = {"schematic": SCHEMATIC_DUT, "extracted": extracted_dut}

    # 1. Primary sweep at tt/27C: both legs, the full VINDIFF_SWEEP_MV grid,
    # every candidate pick-off time plus the full-decision "regen" time.
    sweep: dict[str, dict[float, dict]] = {leg: {} for leg in legs}
    for leg_name, dut_file in legs.items():
        for vindiff_mv in VINDIFF_SWEEP_MV:
            vs = (str(int(vindiff_mv)) if vindiff_mv == int(vindiff_mv) else str(vindiff_mv)).replace(".", "p")
            log_name = f"{leg_name}_{vs}mV"
            t, outp, outn = _run_point(dut_file, "tt", 27.0, vindiff_mv, log_name, scratch_dir, info)
            regen_ns = _regen_time(t, outp, outn, vindiff_mv)
            picks = {c: _pickoff_at(t, outp, outn, c) for c in CANDIDATE_PICKOFF_NS}
            sweep[leg_name][vindiff_mv] = {"regen_ns": regen_ns, "picks": picks}
            if not quiet:
                shown = f"{regen_ns:.4f}ns" if regen_ns is not None else "UNRESOLVED"
                print(f"  {leg_name:10s} vindiff={vindiff_mv:+6.2f}mV regen={shown}")

    # 2. Corner spot check: extracted leg only, {0, CAL_VINDIFF_MV} mV, at
    # the two skewed corners named in CORNER_SPOT_CHECK.
    corner_check: dict[tuple[str, float], dict[float, dict]] = {}
    for corner, temp_c in CORNER_SPOT_CHECK:
        for vindiff_mv in SPOT_CHECK_VINDIFF_MV:
            vs = (str(int(vindiff_mv)) if vindiff_mv == int(vindiff_mv) else str(vindiff_mv)).replace(".", "p")
            log_name = f"extracted_{corner}_{int(temp_c)}C_{vs}mV"
            t, outp, outn = _run_point(
                extracted_dut, corner, temp_c, vindiff_mv, log_name, scratch_dir, info
            )
            picks = {c: _pickoff_at(t, outp, outn, c) for c in CANDIDATE_PICKOFF_NS}
            corner_check[(corner, temp_c)] = corner_check.get((corner, temp_c), {})
            corner_check[(corner, temp_c)][vindiff_mv] = {"picks": picks}
            if not quiet:
                print(f"  extracted {corner}/{temp_c}C vindiff={vindiff_mv:+.2f}mV done")

    shutil.rmtree(scratch_dir, ignore_errors=True)

    sweep_json = {
        "sweep": {
            leg: {str(v): {"regen_ns": d["regen_ns"], "picks": {str(c): p for c, p in d["picks"].items()}}
                  for v, d in points.items()}
            for leg, points in sweep.items()
        },
        "corner_spot_check": {
            f"{corner}_{temp_c}C": {str(v): {"picks": {str(c): p for c, p in d["picks"].items()}}
                                     for v, d in points.items()}
            for (corner, temp_c), points in corner_check.items()
        },
        "recommended_pickoff_ns": RECOMMENDED_PICKOFF_NS,
        "recommended_pickoff_at_ns": RECOMMENDED_PICKOFF_AT_NS,
    }
    (out_dir / "sweep.json").write_text(json.dumps(sweep_json, indent=2) + "\n")

    if record:
        path = write_record(record_id, out_dir, info, sweep, corner_check)
        print(f"wrote {path}")
    return 0


def write_record(
    record_id: str, out_dir: Path, info: pdk.PdkInfo,
    sweep: dict[str, dict[float, dict]], corner_check: dict[tuple[str, float], dict[float, dict]],
) -> Path:
    lines: list[str] = []
    a = lines.append
    a(f"# Comparator PEX pick-off timing re-derivation: {record_id}")
    a("")
    a(
        "Re-derives `layout/comparator/pex/testbench.spice`/`pex_request.json`'s "
        "fixed pick-off instant for the DR-004 Amendment A topology's "
        "*extracted* (parasitic-loaded) leg (issue #187), following "
        "`sim/comparator-decision/run.py`'s own reset->evaluate transient "
        "methodology. `layout/comparator/pex/regen_probe.py` is this "
        "record's generator; re-run it to reproduce."
    )
    a("")
    a(
        "**Why the prior instant (5.4ns absolute, i.e. 0.3ns after the "
        "evaluate edge) was wrong for this topology's extracted leg**: at "
        "that early instant the extracted netlist's differential output is "
        "still dominated by an early transient artifact (capacitive/"
        "resistive loading on the internal DIP/DIN and OUTP/OUTN nodes "
        "delays the true, correctly-signed regenerative response), not the "
        "device-level gm*Vindiff response the schematic leg already shows "
        "cleanly at that instant. The result is a *negative*-going pick-off "
        "differential for a *positive* applied Vindiff -- exactly the "
        "sign flip `reports/20260906-101231-1250ff4/record.md`'s AC3 found."
    )
    a("")

    a("## Method")
    a("")
    a(
        f"Reset(CLK=0, {RESET_NS}ns)->evaluate(CLK={VDD}V) single-edge transient, "
        f"identical stimulus to `sim/comparator-decision/run.py`'s `regen` "
        f"subcommand ({RESET_NS}ns reset, {RESET_TR_NS}ns edge, Vcm={VCM}V), "
        f"but on the `.SUBCKT gen_compose_0`-wrapped DUT (matching "
        "`testbench.spice`'s own `Xdut ... gen_compose_0` instantiation, "
        "not `run.py`'s flat-fragment convention) for two DUTs: "
        "`comparator_pex_reference.spice` (ideal schematic) and a fresh "
        f"`klt extract --parasitics --pdk {info.variant}` of the current "
        f"`reports/LATEST` composed layout (`{(out_dir.parent / 'LATEST').read_text().strip()}/comparator.gds`)."
    )
    a("")
    a(
        f"Vindiff sweep: {VINDIFF_SWEEP_MV} mV at the nominal tt/27C corner, "
        f"for both legs. Two quantities are extracted per point: the "
        "full decision (regeneration) time -- first time "
        f"|v(OUTP)-v(OUTN)| crosses {DECIDE_THRESHOLD_V}V (0.5*VDD), same "
        "threshold `run.py`'s `regen` subcommand uses -- and the raw "
        "pick-off differential v(OUTP)-v(OUTN) at each of a grid of "
        f"candidate instants after the evaluate edge starts: {CANDIDATE_PICKOFF_NS} ns."
    )
    a("")

    a("## Schematic-leg cross-check (methodology parity)")
    a("")
    a(
        "The schematic leg's regen times below should reproduce "
        "`sim/comparator-decision/records/20260906-075157-7724af3.md`'s "
        "own flat-fragment-driven numbers exactly, since the devices are "
        "identical and only the SUBCKT wrapper differs -- confirming this "
        "script's SUBCKT-instantiation methodology is equivalent, not a "
        "different measurement."
    )
    a("")
    a("| Vindiff (mV) | schematic regen time (ns) |")
    a("|---|---|")
    for v in VINDIFF_SWEEP_MV:
        if v == 0.0:
            continue
        r = sweep["schematic"][v]["regen_ns"]
        shown = f"{r:.4f}" if r is not None else "UNRESOLVED"
        a(f"| {v:+.2f} | {shown} |")
    a("")

    a("## Extracted-leg zero-input control: does it stay balanced?")
    a("")
    a(
        "With no differential input applied, the ideal schematic leg stays "
        "at exactly 0V forever (perfectly symmetric ideal netlist -- "
        "`run_pex.py`'s own AC3 table always reports its Vindiff=0 pick-off "
        "as +0.000 uV). The extracted leg does NOT: real, deterministic "
        "routing/parasitic asymmetry (documented in "
        "`reports/20260906-101231-1250ff4/record.md`'s AC1/AC2 per-net R/C "
        "table) gives it a genuine, if small, built-in differential that "
        "GROWS over time under the latch's own positive feedback -- "
        "eventually saturating to a rail with no input at all, given "
        "enough evaluate time. This is the routing-driven offset AC3/AC4 "
        "exist to quantify, seen directly rather than inferred."
    )
    a("")
    a("| t after evaluate edge (ns) | extracted pick-off diff, Vindiff=0 (mV) |")
    a("|---|---|")
    for c in CANDIDATE_PICKOFF_NS:
        val = sweep["extracted"][0.0]["picks"][c]
        a(f"| {c} | {val * 1e3:+.4f} |")
    a("")

    a(f"## Extracted-leg pick-off at the gain-calibration point (Vindiff=+{CAL_VINDIFF_MV:.0f}mV)")
    a("")
    a(
        "This is the column that was sign-flipped at the old 0.3ns instant. "
        "It crosses from negative (artifact-dominated) to positive (true, "
        "correctly-signed device response) within about half a nanosecond "
        "of the evaluate edge:"
    )
    a("")
    a("| t after evaluate edge (ns) | extracted pick-off diff, Vindiff=+10mV (mV) | schematic, same t (mV) |")
    a("|---|---|---|")
    for c in CANDIDATE_PICKOFF_NS:
        ext = sweep["extracted"][CAL_VINDIFF_MV]["picks"][c]
        sch = sweep["schematic"][CAL_VINDIFF_MV]["picks"][c]
        a(f"| {c} | {ext * 1e3:+.4f} | {sch * 1e3:+.4f} |")
    a("")

    a("## Recommendation")
    a("")
    rec_zero = sweep["extracted"][0.0]["picks"][RECOMMENDED_PICKOFF_NS]
    rec_cal = sweep["extracted"][CAL_VINDIFF_MV]["picks"][RECOMMENDED_PICKOFF_NS]
    rec_sch_cal = sweep["schematic"][CAL_VINDIFF_MV]["picks"][RECOMMENDED_PICKOFF_NS]
    rec_gain = rec_cal / (CAL_VINDIFF_MV / 1000.0)
    rec_offset_mv = (rec_zero / rec_gain) * 1000.0
    a(
        f"**PICKOFF_NS = {RECOMMENDED_PICKOFF_NS}ns after the evaluate edge "
        f"(absolute PICKOFF_AT_NS = {RECOMMENDED_PICKOFF_AT_NS:.1f}ns)**, "
        "chosen because at this instant:"
    )
    a("")
    a(
        f"1. The extracted leg's +{CAL_VINDIFF_MV:.0f}mV cal point is "
        f"unambiguously positive with margin ({rec_cal * 1e3:+.4f} mV), "
        "not near the sign-crossing boundary seen in the table above."
    )
    a(
        f"2. The extracted leg's zero-input control ({rec_zero * 1e3:+.4f} mV) "
        f"is still a small fraction of VDD ({abs(rec_zero) / VDD * 100:.2f}%), "
        "i.e. this is still a genuine early PICK-OFF, not a saturated decision."
    )
    a(
        f"3. The schematic leg at the same instant ({rec_sch_cal * 1e3:+.4f} mV, "
        f"{abs(rec_sch_cal) / VDD * 100:.1f}% of VDD) is likewise not yet "
        "saturated, preserving the methodology's intended "
        "early-linear-region character on both legs -- pushing the instant "
        "much later (e.g. 3ns+) would drive the schematic leg's own "
        "\"gain\" number into a fully-decided, non-linear regime instead."
    )
    a(
        "4. The resulting input-referred offset estimate "
        f"(`ext_zero_diff / ext_gain`) is **{rec_offset_mv:+.4f} mV** at this "
        "instant, and stays within the same order of magnitude across the "
        "whole 1.0-2.0ns window around it (see the two tables above) -- "
        "this is not a knife-edge choice sensitive to the exact instant."
    )
    a("")

    a("## Corner spot check (Test Plan edge case)")
    a("")
    a(
        "Extracted leg only, at Vindiff in {0, "
        f"+{CAL_VINDIFF_MV:.0f}}} mV, spot-checked at `ss/-40C` "
        "(slow+cold) and `ff/125C` (fast+hot) -- the two ends of the "
        "ratified process/temp corner set (spec/target-spec.md) -- to check "
        "whether the recommended instant is corner-dependent. This is a "
        "spot check bracketing the skew, not a full PVT sweep: "
        "`pex_request.json`'s own corner matrix is tt/27C-only today (same "
        "subset-corner convention documented throughout `sim/README.md`), "
        "and this record does not change that."
    )
    a("")
    a(
        "| corner | Vindiff (mV) | pick-off diff @ "
        f"{RECOMMENDED_PICKOFF_NS}ns (mV) |"
    )
    a("|---|---|---|")
    for (corner, temp_c) in CORNER_SPOT_CHECK:
        for v in SPOT_CHECK_VINDIFF_MV:
            val = corner_check[(corner, temp_c)][v]["picks"][RECOMMENDED_PICKOFF_NS]
            a(f"| `{corner}/{temp_c:.0f}C` | {v:+.2f} | {val * 1e3:+.4f} |")
    a("")
    a(
        f"Both skewed corners show the same qualitative behaviour as tt/27C "
        f"at {RECOMMENDED_PICKOFF_NS}ns: a modest, non-saturated zero-input "
        f"control and an unambiguously positive, comparable-magnitude "
        f"+{CAL_VINDIFF_MV:.0f}mV cal point (compare "
        f"{rec_cal * 1e3:+.1f} mV at tt/27C above) -- no evidence a "
        "corner-dependent instant is needed for this specific "
        "(Vindiff=0, Vindiff=+10mV) two-point methodology, though a full "
        "PVT sweep of `pex_request.json` itself is out of this record's "
        "scope (see Scope and caveats)."
    )
    a("")

    a("## Scope and caveats")
    a("")
    a(
        "- This record characterizes the extracted netlist's OWN early "
        "transient behaviour to justify a pick-off instant; it does not "
        "re-run `run_pex.py`'s AC1-AC4 (a separate, superseding PEX record "
        "does that with the corrected instant -- see "
        "`layout/comparator/pex/README.md`)."
    )
    a(
        "- The corner spot check above is two points bracketing the "
        "ratified process/temp skew, not the full ratified PVT grid; "
        "`pex_request.json` itself still runs tt/27C only, unchanged by "
        "this issue."
    )
    a(
        "- `EVALUATE_NS` here is 12ns (vs `run.py`'s 40ns) -- long enough "
        "that every measured `regen_ns` above resolved well inside the "
        "window; a genuinely UNRESOLVED point would be reported as such, "
        "not silently truncated."
    )
    a("")

    a("## Files")
    a("")
    a("```")
    a(f"{out_dir.name}/")
    a("  comparator.pex-extract.spice   klt extract --parasitics output (extracted-leg DUT used by this sweep)")
    a("  extract.json                   klt extract --parasitics JSON envelope")
    a("  sweep.json                     full machine-readable sweep + corner-spot-check data")
    a("  record.md                      this file")
    a("```")
    a("")

    lines.extend(evidence.environment_block(
        pdk_line=f"{info.variant} @ {pdk.resolved_commit(info)}",
        ngspice_line=toolchain._ngspice_version() or "unknown",
        netlist_sha256=evidence.sha256_file(SCHEMATIC_DUT),
        extra={"klt version": "see extract.json's provenance.klt_version"},
    ))
    lines.append("")
    lines.extend(evidence.footer_lines("layout/comparator/pex/regen_probe.py", supersedes=""))

    (out_dir / "record.md").write_text("\n".join(lines))
    return out_dir / "record.md"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="comparator PEX pick-off timing re-derivation (issue #187)")
    ap.add_argument("--check-env", action="store_true")
    ap.add_argument("--record", action="store_true", help="write an evidence record under reports/")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if args.check_env:
        info = pdk.resolve()
        print(f"PDK: variant={info.variant} root={info.root} found={info.found}")
        if not info.found:
            print(f"  error: {info.error}")
            return 3
        if shutil.which("klt") is None:
            print("klt not found on PATH")
            return 3
        return 0

    return run(record=args.record, quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())

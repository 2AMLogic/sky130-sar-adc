#!/usr/bin/env python3
"""Standalone driver for the comparator-decision experiment (issue #54).

Exercises design/comparator.sch's dynamic (StrongARM-class) latched
comparator core -- via the xschem-generated device fragment
sim/comparator-decision/testbench/comparator_core.spice -- for its decision
behavior in isolation: offset, input-referred noise, and regeneration time
vs. differential input. No sampling front end, CDAC array, or SAR logic is
required; every source here is an ideal differential DC/pulse stimulus.

    python3 sim/comparator-decision/run.py --check-env
    python3 sim/comparator-decision/run.py regen --record
    python3 sim/comparator-decision/run.py offset --record --n 16 --seed 1
    python3 sim/comparator-decision/run.py noise --record
    python3 sim/comparator-decision/run.py noise-corners --record
        # full ratified PVT corner sweep of the noise measurement (issue #28)

Why this is a bespoke driver, not sim/run_corners.py or sim/monte_carlo.py:
those two runners are deliberately built around a single ngspice analysis
type -- a plain `.op` operating point, with measurements taken via a
`.control ... op ... let/print ... .endc` block (see
sim/harness/testbench.py's `_render_body()` and sim/harness/measure.py's
docstring on why `.measure op` itself is not usable at all). A dynamic
latched comparator has no static DC operating point during regeneration --
it is a clocked, bistable circuit -- so "offset" and "regeneration time"
are inherently transient-analysis quantities, and "input-referred noise"
needs an AC `.noise` analysis on a linearized sub-model (see the `noise`
subcommand below). Reusing the op-only runners here would silently produce
meaningless single-point snapshots rather than a clear failure, so this
experiment gets its own driver instead -- see sim/README.md's directory
convention, which this driver still follows (testbench/, netlist-snapshots/,
corners/, mc-draws/, records/), and sim/harness/{pdk,toolchain,evidence}.py,
which it reuses directly for PDK resolution, the ngspice invocation +
timeout, and the evidence-record scaffolding (record IDs, netlist SHA-256,
git/environment block) -- so records from this experiment are directly
comparable in format to every other record under sim/.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import corners as corners_mod, evidence, measure, pdk, toolchain  # noqa: E402

EXPERIMENT_DIR = Path(__file__).resolve().parent
TESTBENCH_DIR = EXPERIMENT_DIR / "testbench"
DUT_FRAGMENT = TESTBENCH_DIR / "comparator_core.spice"

# --- Fixed testbench constants (all provisional -- see
# spec/decision-records/DR-004-comparator-topology-and-noise-budget.md) ---
VDD = 1.8  # V -- DR-003 Item 1's recommended V_REF = V_DD, cited here as a
# provisional planning value, NOT a ratified spec/target-spec.md row (issue
# #1/#27 have not ratified it). This testbench does not depend on
# ratification -- it characterizes the comparator core against whatever
# supply is asserted here, and would simply need this constant updated if a
# different value is ever ratified.
VCM = VDD / 2  # 0.9V -- common-mode input, matching a differential
# top-plate CDAC's bottom-plate-switching common mode (DR-003 Item 1).
RESET_NS = 5.0  # reset (CLK=0) duration before the single evaluate edge --
# empirically verified sufficient for a clean, symmetric start from an
# uninitialized circuit (see design/comparator.sch's header comment on the
# W=16um reset-device sizing this relied on).
RESET_TR_NS = 0.1  # clock edge rise/fall time
DECIDE_THRESHOLD_V = 0.5 * VDD  # |v(outp)-v(outn)| crossing this = "decided"
PICKOFF_NS = 0.3  # time after evaluate-start used as the "decision
# statistic" pick-off point for offset extraction (see `offset` subcommand
# docstring) -- chosen empirically as the point where the early
# differential-output-vs-Vindiff relationship is cleanly linear (verified
# for Vindiff in [1, 10] mV; see the decision record's derivation).
NOISE_FSTART_HZ = 1e3
NOISE_FSTOP_HZ = 1e9  # ~1/regeneration-time-constant order of magnitude
# (regen-sweep records below resolve sub-mV differentials within ~1-2 ns),
# not an arbitrary round number -- see the decision record.

# --- Ratified corner-set axes (issue #28), per spec/target-spec.md's
# "Numeric rows -- RATIFIED 2026-08-19" section: -40/27/125C, +-10% supply,
# sky130 process corners. VDD above (1.8V) is now also the ratified V_REF/
# V_DD value (DR-003 Item 1), not only a provisional planning constant.
SUPPLY_TOLERANCE = 0.10
TEMPS_C = [-40, 27, 125]
PROCESS_CORNERS = ["tt", "ss", "ff", "sf", "fs"]
# Ratified comparator input-referred noise budget (DR-003 Item 4 /
# spec/target-spec.md's ratified row): baseline (ENOB>9.0) and stretch
# (ENOB>9.5) thresholds, in V rms (differential, input-referred).
NOISE_BUDGET_BASELINE_V = 1.0148e-3
NOISE_BUDGET_STRETCH_V = 0.5859e-3


def _dut_lines() -> str:
    return DUT_FRAGMENT.read_text()


def _pdk_info() -> pdk.PdkInfo:
    info = pdk.resolve()
    if not info.found:
        raise RuntimeError(f"PDK not resolvable: {info.error}")
    return info


def _read_wrdata_csv(path: Path, n_vectors: int) -> list[list[float]]:
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


def _run(deck_text: str, scratch_dir: Path, log_name: str) -> str:
    return toolchain.run_ngspice(deck_text, scratch_dir, log_name)


# ---------------------------------------------------------------------------
# regen: regeneration time vs. differential input (deterministic sweep)
# ---------------------------------------------------------------------------

DEFAULT_VINDIFF_SWEEP_MV = [0.5, 1, 2, 5, 10, 20, 50, -10]
EVALUATE_NS = 40.0


def _regen_deck(info: pdk.PdkInfo, corner: str, temp_c: float, vindiff_mv: float, log_name: str) -> str:
    vindiff_v = vindiff_mv / 1000.0
    period_ns = RESET_NS + RESET_TR_NS + EVALUATE_NS + 10.0
    tstop_ns = RESET_NS + RESET_TR_NS + EVALUATE_NS
    lines = [
        f"* comparator-decision regen-time sweep -- vindiff={vindiff_mv}mV "
        f"corner={corner} temp={temp_c}C (issue #54)",
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
        _dut_lines(),
        "",
        ".control",
        f"tran 0.005n {tstop_ns}n",
        f"wrdata {log_name}.csv v(CLK) v(OUTP) v(OUTN)",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


@dataclass
class RegenPoint:
    vindiff_mv: float
    regen_time_ns: float | None
    log_text: str


def run_regen_sweep(
    corner: str = "tt", temp_c: float = 27.0,
    vindiff_sweep_mv: list[float] | None = None, quiet: bool = False,
) -> tuple[list[RegenPoint], str]:
    info = _pdk_info()
    vindiff_sweep_mv = vindiff_sweep_mv or DEFAULT_VINDIFF_SWEEP_MV
    evaluate_start_ns = RESET_NS + RESET_TR_NS
    points: list[RegenPoint] = []
    with tempfile.TemporaryDirectory(prefix="comparator-decision-regen-") as scratch:
        scratch_dir = Path(scratch)
        for vindiff_mv in vindiff_sweep_mv:
            log_name = f"regen_{vindiff_mv}mV".replace("-", "neg").replace(".", "p")
            deck = _regen_deck(info, corner, temp_c, vindiff_mv, log_name)
            log_text = _run(deck, scratch_dir, log_name)
            csv_path = scratch_dir / f"{log_name}.csv"
            t, clk, outp, outn = _read_wrdata_csv(csv_path, 3)
            sign = 1.0 if vindiff_mv >= 0 else -1.0
            regen_ns = None
            for i, tt in enumerate(t):
                if tt < evaluate_start_ns * 1e-9:
                    continue
                diff = sign * (outp[i] - outn[i])
                if diff > DECIDE_THRESHOLD_V:
                    regen_ns = (tt - evaluate_start_ns * 1e-9) * 1e9
                    break
            points.append(RegenPoint(vindiff_mv=vindiff_mv, regen_time_ns=regen_ns, log_text=log_text))
            if not quiet:
                shown = f"{regen_ns:.4f}ns" if regen_ns is not None else "UNRESOLVED"
                print(f"  vindiff={vindiff_mv:+.2f}mV -> regen_time={shown}")
    netlist_sha = evidence.sha256_file(DUT_FRAGMENT)
    return points, netlist_sha


def _finalize_record(
    lines: list[str],
    record_path: Path,
    info: pdk.PdkInfo,
    netlist_sha: str,
    cmd: str,
    extra: dict[str, str] | None = None,
) -> Path:
    """Shared tail for the write_*_evidence() functions below: append the
    environment block + footer boilerplate and write the record. `cmd` is
    the subcommand name (e.g. "regen", "offset", "noise"), used to build
    the "Written by" attribution."""
    lines.extend(evidence.environment_block(
        pdk_line=f"{info.variant} @ {pdk.resolved_commit(info)}",
        ngspice_line=toolchain._ngspice_version() or "unknown",
        netlist_sha256=netlist_sha,
        extra=extra,
    ))
    lines.append("")
    lines.extend(evidence.footer_lines(f"sim/comparator-decision/run.py {cmd}", ""))
    record_path.write_text("\n".join(lines))
    return record_path


def write_regen_evidence(points: list[RegenPoint], netlist_sha: str, corner: str, temp_c: float, note: str = "") -> Path:
    record_id = evidence.new_record_id()
    corners_dir = EXPERIMENT_DIR / "corners" / record_id
    corners_dir.mkdir(parents=True, exist_ok=True)
    for p in points:
        safe = f"{p.vindiff_mv}mV".replace("-", "neg").replace(".", "p")
        (corners_dir / f"vindiff_{safe}.log").write_text(p.log_text)

    record_path = evidence.write_netlist_snapshot(EXPERIMENT_DIR, record_id, DUT_FRAGMENT)

    info = pdk.resolve()
    lines: list[str] = []
    a = lines.append
    a(f"# Record {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    a(
        "- **Claim**: pending #1/#27 -- characterizes design/comparator.sch's "
        "regeneration time vs. differential input at one PVT point. Not a "
        "spec/target-spec.md row (no sample-rate/settling row is ratified "
        "yet); informational for the future comparator-topology decision "
        "record and #28's corner campaign."
    )
    a(f"- **Netlist provenance**: schematic (`{DUT_FRAGMENT.relative_to(evidence.REPO_ROOT)}`)")
    a(
        f"- **Corner matrix run**: process=['{corner}'], temperature_c=[{temp_c}], "
        f"supply_v=[{VDD}] (1 PVT point -- **subset-corner justification**: this "
        "is a first-pass characterization at the nominal corner only; a full "
        "PVT sweep of this same Vindiff grid is deferred to #28's corner "
        "campaign once a comparator-topology decision record exists, per "
        "sim/README.md's 'Subset-corner justification')"
    )
    a(
        f"- **Stimulus**: single reset({RESET_NS}ns, CLK=0)->evaluate(CLK={VDD}V) "
        f"edge per run (not a repeating clock -- each ngspice invocation starts "
        f"from an uninitialized circuit, so there is no multi-cycle state to "
        f"carry); decision threshold |v(outp)-v(outn)| > {DECIDE_THRESHOLD_V}V "
        f"(0.5*VDD); Vcm={VCM}V"
    )
    if note:
        a(f"- **Note**: {note}")
    unresolved = [p for p in points if p.regen_time_ns is None]
    a(f"- **Overall**: {'PASS' if not unresolved else 'INCOMPLETE'} "
      f"({len(points) - len(unresolved)}/{len(points)} points resolved within the "
      f"{EVALUATE_NS}ns evaluate window)")
    a("")
    a("## Regeneration time vs. differential input")
    a("")
    a("| Vindiff (mV) | regen time (ns) |")
    a("|---|---|")
    for p in sorted(points, key=lambda p: p.vindiff_mv):
        shown = f"{p.regen_time_ns:.4f}" if p.regen_time_ns is not None else "UNRESOLVED (> evaluate window)"
        a(f"| {p.vindiff_mv:+.2f} | {shown} |")
    a("")
    a(
        "Expected shape: regeneration time grows roughly as `ln(V_decided/Vindiff)` "
        "(standard positive-feedback latch behavior) as Vindiff shrinks -- the "
        "monotonic growth from 50mV to 0.5mV above is the qualitative check for "
        "that, not a quantitative claim against any ratified settling-time row."
    )
    a("")
    return _finalize_record(lines, record_path, info, netlist_sha, "regen")


# ---------------------------------------------------------------------------
# offset: Monte Carlo mismatch-induced offset, via a linearized pick-off
# statistic calibrated against an ideal-device Vindiff sweep
# ---------------------------------------------------------------------------
#
# Methodology (documented in full in the decision record): a StrongARM latch
# has no static DC operating point once CLK evaluates, so offset cannot be
# read off a `.op` node voltage the way a static comparator's could. Instead:
#
#  1. "Gain calibration" -- at the plain `tt` corner (no mismatch), sweep a
#     few small ideal Vindiff points and record the differential output
#     v(outp)-v(outn) at a fixed early pick-off time (PICKOFF_NS after the
#     evaluate edge, well before the latch saturates to the rails). This
#     relationship is empirically linear in this window (verified during
#     development for Vindiff in [1, 10] mV) -- fit a zero-intercept slope
#     ("gain", V/V) through it via least squares.
#  2. "Draws" -- at the `tt_mm` mismatch corner, run N single-shot
#     transients with Vindiff FIXED AT 0 and a distinct rndseed per draw,
#     each measuring the same pick-off statistic. Per-device mismatch
#     breaks the ideal symmetry, producing a nonzero pick-off value whose
#     input-referred equivalent is (pick-off value) / gain -- this is the
#     random/mismatch-driven offset for that draw.
#  3. "Negative control" -- N draws at the plain `tt` corner (mismatch
#     disabled), same seed sequence: must reproduce the SAME pick-off value
#     on every draw (stdev == 0), the same negative-control contract every
#     other Monte Carlo record in this repo uses (sim/README.md).


VINDIFF_GAIN_CAL_MV = [1, 2, 5, 10]
PICKOFF_TSTOP_NS = RESET_NS + RESET_TR_NS + 1.5  # short deck: only need the
# early pick-off sample, not a full regeneration


def _pickoff_deck(
    info: pdk.PdkInfo, corner: str, temp_c: float, vindiff_mv: float,
    log_name: str, rndseed: int | None = None,
) -> str:
    vindiff_v = vindiff_mv / 1000.0
    period_ns = RESET_NS + RESET_TR_NS + (PICKOFF_TSTOP_NS - RESET_NS - RESET_TR_NS) + 10.0
    lines = [
        f"* comparator-decision offset pick-off -- vindiff={vindiff_mv}mV "
        f"corner={corner} temp={temp_c}C seed={rndseed} (issue #54)",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        f".param vdd_val = {VDD}",
    ]
    if rndseed is not None:
        lines.append(f".option rndseed={rndseed}")
    lines += [
        "",
        "Vdd VDD 0 dc {vdd_val}",
        f"Vclk CLK 0 PULSE(0 {{vdd_val}} {RESET_NS}n {RESET_TR_NS}n {RESET_TR_NS}n "
        f"{PICKOFF_TSTOP_NS - RESET_NS - RESET_TR_NS}n {period_ns}n)",
        f"Vinp VINP 0 dc {VCM + vindiff_v / 2}",
        f"Vinn VINN 0 dc {VCM - vindiff_v / 2}",
        "",
        _dut_lines(),
        "",
        ".control",
        f"tran 0.002n {PICKOFF_TSTOP_NS}n",
        f"wrdata {log_name}.csv v(OUTP) v(OUTN)",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


def _pickoff_value(csv_path: Path) -> float:
    t, outp, outn = _read_wrdata_csv(csv_path, 2)
    target = (RESET_NS + RESET_TR_NS + PICKOFF_NS) * 1e-9
    idx = min(range(len(t)), key=lambda i: abs(t[i] - target))
    return outp[idx] - outn[idx]


@dataclass
class OffsetResult:
    gain_v_per_v: float
    gain_cal_points: list[tuple[float, float]]  # (vindiff_v, pickoff_diff)
    draws_pickoff: list[float]
    draws_offset_v: list[float]
    negctrl_pickoff: list[float]
    negctrl_offset_v: list[float]
    seed: int
    n: int
    corner: str
    mismatch_corner: str
    logs: dict[str, str] = field(default_factory=dict)


def run_offset_mc(
    corner: str = "tt", temp_c: float = 27.0, seed: int = 1, n: int = 16, quiet: bool = False,
) -> tuple[OffsetResult, str]:
    info = _pdk_info()
    mismatch_corner = corners_mod.mismatch_corner_for(corner)
    logs: dict[str, str] = {}

    with tempfile.TemporaryDirectory(prefix="comparator-decision-offset-") as scratch:
        scratch_dir = Path(scratch)

        # 1. Gain calibration (ideal devices, plain corner).
        cal_points: list[tuple[float, float]] = []
        for vindiff_mv in VINDIFF_GAIN_CAL_MV:
            log_name = f"gaincal_{vindiff_mv}mV"
            deck = _pickoff_deck(info, corner, temp_c, vindiff_mv, log_name)
            log_text = _run(deck, scratch_dir, log_name)
            logs[log_name] = log_text
            diff = _pickoff_value(scratch_dir / f"{log_name}.csv")
            cal_points.append((vindiff_mv / 1000.0, diff))
            if not quiet:
                print(f"  gain-cal vindiff={vindiff_mv}mV -> pickoff_diff={diff:.6g}")
        # Zero-intercept least-squares slope: gain = sum(x*y) / sum(x*x).
        sxy = sum(x * y for x, y in cal_points)
        sxx = sum(x * x for x, y in cal_points)
        gain = sxy / sxx if sxx else float("nan")
        if not quiet:
            print(f"  gain = {gain:.4f} V/V (from {len(cal_points)} calibration points)")

        # 2. Mismatch-enabled draws at Vindiff=0.
        draws_pickoff: list[float] = []
        for i in range(n):
            this_seed = seed + i
            log_name = f"draw_{i}"
            deck = _pickoff_deck(info, mismatch_corner, temp_c, 0.0, log_name, rndseed=this_seed)
            log_text = _run(deck, scratch_dir, log_name)
            logs[log_name] = log_text
            diff = _pickoff_value(scratch_dir / f"{log_name}.csv")
            draws_pickoff.append(diff)
            if not quiet:
                print(f"  draw {i} (seed={this_seed}, {mismatch_corner}): pickoff_diff={diff:.6g}")

        # 3. Negative control at the plain corner, same seed sequence.
        negctrl_pickoff: list[float] = []
        for i in range(n):
            this_seed = seed + i
            log_name = f"negctrl_{i}"
            deck = _pickoff_deck(info, corner, temp_c, 0.0, log_name, rndseed=this_seed)
            log_text = _run(deck, scratch_dir, log_name)
            logs[log_name] = log_text
            diff = _pickoff_value(scratch_dir / f"{log_name}.csv")
            negctrl_pickoff.append(diff)
            if not quiet:
                print(f"  negctrl {i} (seed={this_seed}, {corner}): pickoff_diff={diff:.6g}")

    draws_offset_v = [d / gain for d in draws_pickoff]
    negctrl_offset_v = [d / gain for d in negctrl_pickoff]

    result = OffsetResult(
        gain_v_per_v=gain, gain_cal_points=cal_points,
        draws_pickoff=draws_pickoff, draws_offset_v=draws_offset_v,
        negctrl_pickoff=negctrl_pickoff, negctrl_offset_v=negctrl_offset_v,
        seed=seed, n=n, corner=corner, mismatch_corner=mismatch_corner, logs=logs,
    )
    netlist_sha = evidence.sha256_file(DUT_FRAGMENT)
    return result, netlist_sha


def write_offset_evidence(result: OffsetResult, netlist_sha: str, note: str = "") -> Path:
    record_id = evidence.new_record_id()
    draws_dir = EXPERIMENT_DIR / "mc-draws" / record_id
    draws_dir.mkdir(parents=True, exist_ok=True)
    for name, text in result.logs.items():
        (draws_dir / f"{name}.log").write_text(text)

    record_path = evidence.write_netlist_snapshot(EXPERIMENT_DIR, record_id, DUT_FRAGMENT)

    negctrl_stdev = statistics.pstdev(result.negctrl_offset_v) if len(result.negctrl_offset_v) > 1 else 0.0
    negctrl_ok = negctrl_stdev == 0.0
    draws_stdev = statistics.pstdev(result.draws_offset_v) if len(result.draws_offset_v) > 1 else 0.0
    draws_mean = statistics.fmean(result.draws_offset_v) if result.draws_offset_v else float("nan")

    info = pdk.resolve()
    lines: list[str] = []
    a = lines.append
    a(f"# Monte Carlo record {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    a(
        "- **Claim**: None numeric -- characterizes design/comparator.sch's "
        "mismatch-driven input offset for issue #29's statistical-evidence "
        "campaign (T1 item 6: ENOB, INL/DNL, comparator/ADC offset). "
        "spec/target-spec.md carries no numeric offset row (ratified or "
        "DRAFT) to grade this against -- DR-003 characterizes noise, not "
        "offset, as the comparator's ratified budget line -- so this record "
        "is a distribution-only characterization, informational for the "
        "future comparator-topology decision record, not a pass/fail claim."
    )
    a(f"- **Netlist provenance**: schematic (`{DUT_FRAGMENT.relative_to(evidence.REPO_ROOT)}`)")
    rel_se_pct = 100.0 / (2 * (result.n - 1)) ** 0.5 if result.n > 1 else float("inf")
    a(
        f"- **Statistical convention**: mismatch corner `{result.mismatch_corner}`, "
        f"N={result.n}, seed={result.seed} (draws use seed, seed+1, ..., "
        f"seed+N-1), PVT point process={result.corner} temp=27.0C supply={VDD}V. "
        f"**N justification**: relative standard error on the estimated offset "
        f"stdev, SE(s)/s ~= 1/sqrt(2(N-1)) for an approximately-Gaussian "
        f"per-draw statistic (same formula sim/cdac-array-transfer/run_mc.py's "
        f"own N-justification uses) -- N={result.n} gives {rel_se_pct:.1f}%. This "
        "is a distribution-SHAPE-adequate sample, not a sample size adequate for "
        "a tight yield-fraction claim at high confidence (that needs O(100s)); "
        "no numeric offset spec row exists to compute a yield/Cpk claim against "
        "in the first place (see Overall note below), so this record reports the "
        "distribution itself rather than a `klt yield` verdict."
    )
    a(
        f"- **Methodology**: linearized pick-off statistic at "
        f"t=evaluate_start+{PICKOFF_NS}ns, calibrated to an input-referred "
        f"gain of {result.gain_v_per_v:.4f} V/V via a {len(result.gain_cal_points)}-point "
        "ideal-device Vindiff sweep (zero-intercept least-squares fit) -- "
        "see sim/comparator-decision/run.py's `offset` docstring for the "
        "full derivation. This measures OFFSET (a deterministic per-draw "
        "quantity, converted from a continuous pick-off statistic), not a "
        "'wins/loses' decision count."
    )
    a(
        f"- **Negative control**: N={result.n} draws at the plain `{result.corner}` "
        f"corner (mismatch DISABLED), same seed sequence -- "
        f"{'PASS (stdev == 0 on the pick-off-derived offset)' if negctrl_ok else f'FAIL: stdev={negctrl_stdev:.6g} != 0'}"
    )
    a(
        f"- **Positive control**: N={result.n} draws at the `{result.mismatch_corner}` "
        f"corner (mismatch ENABLED) offset stdev={draws_stdev:.6g} V "
        f"({'> 0, shows genuine spread -- PASS' if draws_stdev > 0 else 'FAIL: zero spread despite mismatch enabled'})"
    )
    if note:
        a(f"- **Note**: {note}")
    overall_ok = negctrl_ok and draws_stdev > 0
    a(f"- **Overall**: {'PASS' if overall_ok else 'FAIL'}")
    a("")
    a("## Gain calibration (ideal devices, ${}$ corner)".format(result.corner))
    a("")
    a("| Vindiff (mV) | pick-off diff (V) |")
    a("|---|---|")
    for x, y in result.gain_cal_points:
        a(f"| {x * 1000:.2f} | {y:.6g} |")
    a(f"\nFitted gain (zero-intercept least squares): **{result.gain_v_per_v:.4f} V/V**")
    a("")
    a("## Offset distribution (mismatch-enabled draws, input-referred)")
    a("")
    a("| N | mean (mV) | stdev (mV) | min (mV) | max (mV) |")
    a("|---|---|---|---|---|")
    a(
        f"| {len(result.draws_offset_v)} | {draws_mean * 1000:.4f} | "
        f"{draws_stdev * 1000:.4f} | {min(result.draws_offset_v) * 1000:.4f} | "
        f"{max(result.draws_offset_v) * 1000:.4f} |"
    )
    a("")
    a("## Negative control (mismatch-disabled, same seed sequence)")
    a("")
    negctrl_mean = statistics.fmean(result.negctrl_offset_v) if result.negctrl_offset_v else float("nan")
    a("| N | mean (mV) | stdev (mV, must be 0) |")
    a("|---|---|---|")
    a(f"| {len(result.negctrl_offset_v)} | {negctrl_mean * 1000:.4f} | {negctrl_stdev * 1000:.6g} |")
    a("")
    return _finalize_record(
        lines, record_path, info, netlist_sha, "offset",
        extra={"MC seed": str(result.seed), "MC N": str(result.n)},
    )


# ---------------------------------------------------------------------------
# noise: input-referred noise via a linearized, loop-broken AC .noise model
# ---------------------------------------------------------------------------
#
# Methodology (documented in full in the decision record): the full latch
# has no stable small-signal operating point once regeneration begins (the
# cross-coupled pair is a positive-feedback loop), so a direct `.noise`
# analysis on the full comparator_core.spice fragment is not meaningful
# (ngspice would either fail to converge on `.op`, or converge to a rail
# where the devices are far outside their useful small-signal region).
# Instead this uses a REDUCED sub-model: the same tail + input pair, but
# with the cross-coupled latch pair's gates DIODE-CONNECTED to their own
# drains (self-biased) instead of cross-coupled to the opposite side's drain
# -- this removes the positive-feedback loop (no more regeneration) while
# keeping a physically-motivated nonlinear load impedance at each output
# node, self-consistently finding its own DC bias point (no external bias
# voltage guess required). This is a standard "break the loop for small-
# signal analysis" technique (generic circuit-analysis practice, not
# specific to any implementation).
#
# The AC stimulus is single-ended (Vinp gets AC=1, Vinn stays pure DC), and
# ngspice's `inoise_total` (referred back through Vinp) is reported as a
# SINGLE-ENDED input-referred rms noise voltage. For a symmetric
# differential pair with uncorrelated per-side noise contributions, the
# standard diff-pair noise-doubling result gives
# differential-input-referred variance = 2x the single-ended value, i.e.
# rms_differential = sqrt(2) * rms_single_ended -- this repo does not derive
# that identity from scratch here; it is applied as a named, flagged
# approximation and stated as such in the record, per DR-003 Item 4's own
# deferral of the noise-verification methodology to "the future comparator-
# topology DR."

VBIAS_NOTE = (
    "reduced sub-model: cross-coupled latch pair replaced by diode-connected "
    "(self-biased) loads; CLK held at VDD (steady evaluate bias, tail on)"
)


def _noise_deck(info: pdk.PdkInfo, corner: str, temp_c: float, supply_v: float = VDD) -> str:
    vcm = supply_v / 2.0
    lines = [
        f"* comparator-decision input-referred noise ({VBIAS_NOTE}) "
        f"corner={corner} temp={temp_c}C supply={supply_v}V (issue #54/#28)",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        f".param vdd_val = {supply_v}",
        "",
        "Vdd VDD 0 dc {vdd_val}",
        "Vclkfix CLK 0 dc {vdd_val}",
        f"Vinp VINP 0 dc {vcm} AC 1",
        f"Vinn VINN 0 dc {vcm}",
        "",
        "XM_TAIL TAIL CLK GND GND sky130_fd_pr__nfet_01v8 L=0.5 W=8 nf=1",
        "XM_INN OUTP VINN TAIL GND sky130_fd_pr__nfet_01v8 L=0.5 W=4 nf=1",
        "XM_INP OUTN VINP TAIL GND sky130_fd_pr__nfet_01v8 L=0.5 W=4 nf=1",
        "XM_LATN_P OUTP OUTP GND GND sky130_fd_pr__nfet_01v8 L=0.5 W=4 nf=1",
        "XM_LATN_N OUTN OUTN GND GND sky130_fd_pr__nfet_01v8 L=0.5 W=4 nf=1",
        "XM_LATP_P OUTP OUTP VDD VDD sky130_fd_pr__pfet_01v8 L=0.5 W=8 nf=1",
        "XM_LATP_N OUTN OUTN VDD VDD sky130_fd_pr__pfet_01v8 L=0.5 W=8 nf=1",
        "",
        ".control",
        # sim/spiceinit sets 'option klu' repo-wide for corner-sweep speed,
        # but ngspice's KLU solver does not support .noise analysis
        # ("Error: Noise simulation is not (yet) supported with 'option
        # KLU'. Use 'option sparse' instead.", verified empirically). This
        # switches the solver back to SPARSE for THIS invocation only (a
        # runtime .control command, not an edit to the shared spiceinit
        # file) -- op-point/transient results elsewhere in this repo are
        # unaffected.
        "option sparse",
        "op",
        "print v(TAIL) v(OUTP) v(OUTN)",
        f"noise v(outp,outn) Vinp dec 20 {NOISE_FSTART_HZ:g} {NOISE_FSTOP_HZ:g} 20",
        "print inoise_total onoise_total",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


@dataclass
class NoiseResult:
    single_ended_rms_v: float
    differential_rms_v: float
    op_tail_v: float
    op_outp_v: float
    op_outn_v: float
    log_text: str
    corner: str
    temp_c: float
    supply_v: float = VDD


def run_noise(
    corner: str = "tt", temp_c: float = 27.0, supply_v: float = VDD, quiet: bool = False,
) -> tuple[NoiseResult, str]:
    info = _pdk_info()
    with tempfile.TemporaryDirectory(prefix="comparator-decision-noise-") as scratch:
        scratch_dir = Path(scratch)
        log_name = "noise"
        deck = _noise_deck(info, corner, temp_c, supply_v)
        log_text = _run(deck, scratch_dir, log_name)

    parsed = measure.parse(log_text, ["inoise_total", "onoise_total", "v(tail)", "v(outp)", "v(outn)"])
    # ngspice's `print` echoes lowercased vector names for v(...) forms;
    # measure.parse's regex requires the LHS to look like an identifier
    # (letters/digits/underscore), which `v(tail)` does not match (parens)
    # -- so parse those three directly here instead of relying on
    # measure.parse for them.
    op_tail = op_outp = op_outn = float("nan")
    for line in log_text.splitlines():
        s = line.strip()
        if s.startswith("v(tail)"):
            op_tail = float(s.split("=")[1])
        elif s.startswith("v(outp)"):
            op_outp = float(s.split("=")[1])
        elif s.startswith("v(outn)"):
            op_outn = float(s.split("=")[1])
    single_ended = parsed.get("inoise_total", float("nan"))
    differential = single_ended * (2 ** 0.5)
    if not quiet:
        print(f"  op: TAIL={op_tail:.4f}V OUTP={op_outp:.4f}V OUTN={op_outn:.4f}V")
        print(f"  inoise_total (single-ended) = {single_ended * 1000:.4f} mV rms")
        print(f"  differential estimate (x sqrt(2)) = {differential * 1000:.4f} mV rms")
    result = NoiseResult(
        single_ended_rms_v=single_ended, differential_rms_v=differential,
        op_tail_v=op_tail, op_outp_v=op_outp, op_outn_v=op_outn,
        log_text=log_text, corner=corner, temp_c=temp_c, supply_v=supply_v,
    )
    netlist_sha = evidence.sha256_text(_noise_deck(info, corner, temp_c, supply_v))
    return result, netlist_sha


def run_noise_corners(quiet: bool = False) -> tuple[list[NoiseResult], str]:
    """Full ratified-corner-set sweep of run_noise() (issue #28): the OAT PVT
    grid built from the ratified corner set (spec/target-spec.md's "Numeric
    rows -- RATIFIED 2026-08-19" section: -40/27/125C, +-10% supply, sky130
    process corners), substantiating the ratified comparator input-referred
    noise-budget row rather than the single nominal-point record alone."""
    info = _pdk_info()
    supply_pts = corners_mod.supply_points(VDD, SUPPLY_TOLERANCE)
    grid = corners_mod.oat_grid("tt", 27.0, VDD, PROCESS_CORNERS, TEMPS_C, supply_pts)
    results: list[NoiseResult] = []
    for process_corner, temp_c, supply_v in grid:
        result, _ = run_noise(corner=process_corner, temp_c=temp_c, supply_v=supply_v, quiet=quiet)
        results.append(result)
        if not quiet:
            cid = corners_mod.corner_id(process_corner, temp_c, supply_v)
            print(f"  {cid}: differential noise = {result.differential_rms_v * 1000:.4f} mV rms")
    netlist_sha = evidence.sha256_text(_noise_deck(info, "tt", 27.0, VDD))
    return results, netlist_sha


def write_noise_campaign_evidence(results: list[NoiseResult], netlist_sha: str, note: str = "") -> Path:
    record_id = evidence.new_record_id()
    corners_dir = EXPERIMENT_DIR / "corners" / record_id
    corners_dir.mkdir(parents=True, exist_ok=True)
    info = pdk.resolve()
    for r in results:
        cid = corners_mod.corner_id(r.corner, r.temp_c, r.supply_v)
        (corners_dir / f"{cid}.log").write_text(r.log_text)

    record_path = evidence.write_netlist_snapshot_text(
        EXPERIMENT_DIR, record_id, _noise_deck(info, "tt", 27.0, VDD)
    )

    binding = max(results, key=lambda r: r.differential_rms_v)
    binding_cid = corners_mod.corner_id(binding.corner, binding.temp_c, binding.supply_v)
    overall_ok = binding.differential_rms_v <= NOISE_BUDGET_BASELINE_V
    meets_stretch = binding.differential_rms_v <= NOISE_BUDGET_STRETCH_V

    process_corners_run = sorted({r.corner for r in results})
    temps_run = sorted({r.temp_c for r in results})
    supplies_run = sorted({r.supply_v for r in results})

    lines: list[str] = []
    a = lines.append
    a(f"# Record {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    a(
        "- **Claim**: `spec/target-spec.md#numeric-rows--ratified-2026-08-19` -- "
        "Comparator input-referred noise `<=1.0148 mV rms` (baseline, ENOB>9.0) / "
        "`<=0.5859 mV rms` (stretch, ENOB>9.5) (RATIFIED, DR-003 via #27). Measures "
        "design/comparator.sch's (reduced sub-model, see Methodology) differential "
        "input-referred noise across the full ratified corner set and grades it "
        "against the ratified baseline threshold -- a genuine pass/fail against a "
        "ratified spec/target-spec.md line, distinct from the prior single-point "
        "nominal-corner record (informational at the time it was written, DR-003 "
        "then being only `proposed`)."
    )
    a("- **Netlist provenance**: schematic, reduced sub-model (see Methodology)")
    a(
        f"- **Corner matrix run**: process={process_corners_run}, "
        f"temperature_c={temps_run}, supply_v={supplies_run} "
        f"({len(results)} points, one-at-a-time per sim/README.md)"
    )
    a(
        f"- **Noise methodology**: `ac-based`, integration bandwidth "
        f"{NOISE_FSTART_HZ:g}Hz-{NOISE_FSTOP_HZ:g}Hz (see sim/comparator-decision/run.py "
        "module docstring for the bandwidth choice's derivation from the "
        "regen-time-vs-Vindiff record). REDUCED SUB-MODEL, not the full "
        f"comparator_core.spice fragment: {VBIAS_NOTE}. This is a named, "
        "flagged simplification (excludes the cross-coupled latch pair's "
        "own regenerative-phase noise contribution) -- see "
        "spec/decision-records/DR-004-comparator-topology-and-noise-budget.md "
        "for the full derivation and its limitations. This simplification carries "
        "over unchanged from the prior nominal-point record; it is a methodology "
        "limitation, not something this corner campaign relaxes to force a pass."
    )
    if note:
        a(f"- **Note**: {note}")
    a(
        f"- **Binding corner**: `{binding_cid}` (worst-case differential "
        f"input-referred noise = {binding.differential_rms_v * 1000:.4f} mV rms) -- "
        "recorded regardless of pass/fail, per sim/README.md's per-row "
        "binding-corner convention."
    )
    a(
        f"- **Overall**: {'PASS' if overall_ok else 'FAIL'} vs. the ratified baseline "
        f"threshold ({NOISE_BUDGET_BASELINE_V * 1000:.4f} mV rms); "
        f"{'also meets' if meets_stretch else 'does NOT meet'} the stretch threshold "
        f"({NOISE_BUDGET_STRETCH_V * 1000:.4f} mV rms) at the binding corner."
    )
    a("")
    a("## Per-corner differential input-referred noise")
    a("")
    a("| corner-id | single-ended noise (mV rms) | differential noise (mV rms) | vs. baseline (<=1.0148 mV) |")
    a("|---|---|---|---|")
    for r in sorted(results, key=lambda r: -r.differential_rms_v):
        cid = corners_mod.corner_id(r.corner, r.temp_c, r.supply_v)
        ok = r.differential_rms_v <= NOISE_BUDGET_BASELINE_V
        a(
            f"| `{cid}` | {r.single_ended_rms_v * 1000:.4f} | {r.differential_rms_v * 1000:.4f} | "
            f"{'PASS' if ok else 'FAIL'} |"
        )
    a("")
    a(
        "No spec row is relaxed to make this result pass or fail -- the ratified "
        "baseline/stretch thresholds above are quoted verbatim from "
        "spec/target-spec.md, per CLAUDE.md's 'do not relax a spec line to make a "
        "result pass' rule."
    )
    a("")
    a("- **Data provenance**: model-card-monte-carlo (sky130A BSIM4 device noise "
      "models via ngspice's `.noise` analysis; no literature/foundry-doc noise figure used)")
    a("")
    return _finalize_record(lines, record_path, info, netlist_sha, "noise-corners")


def write_noise_evidence(result: NoiseResult, netlist_sha: str, note: str = "") -> Path:
    record_id = evidence.new_record_id()
    runs_dir = EXPERIMENT_DIR / "corners" / record_id
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / "noise.log").write_text(result.log_text)

    info = pdk.resolve()
    record_path = evidence.write_netlist_snapshot_text(
        EXPERIMENT_DIR, record_id, _noise_deck(info, result.corner, result.temp_c)
    )

    lines: list[str] = []
    a = lines.append
    a(f"# Record {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    a(
        "- **Claim**: pending #1/#27 -- measures design/comparator.sch's "
        "(reduced sub-model, see below) input-referred noise, compared "
        "INFORMATIONALLY against "
        "spec/decision-records/DR-003-numeric-spec-derivation.md Item 4's "
        "provisional budget (<=1.0148 mV rms baseline / <=0.5859 mV rms "
        "stretch) -- DR-003 is itself `proposed`, not ratified, so this is "
        "not a pass/fail against a ratified line."
    )
    a("- **Netlist provenance**: schematic, reduced sub-model (see Methodology)")
    a(f"- **Corner matrix run**: process=['{result.corner}'], temperature_c=[{result.temp_c}], supply_v=[{VDD}] (1 point)")
    a(
        f"- **Noise methodology**: `ac-based`, integration bandwidth "
        f"{NOISE_FSTART_HZ:g}Hz-{NOISE_FSTOP_HZ:g}Hz (see sim/comparator-decision/run.py "
        "module docstring for the bandwidth choice's derivation from the "
        "regen-time-vs-Vindiff record). REDUCED SUB-MODEL, not the full "
        f"comparator_core.spice fragment: {VBIAS_NOTE}. This is a named, "
        "flagged simplification (excludes the cross-coupled latch pair's "
        "own regenerative-phase noise contribution) -- see "
        "spec/decision-records/DR-004-comparator-topology-and-noise-budget.md "
        "for the full derivation and its limitations."
    )
    if note:
        a(f"- **Note**: {note}")
    a("- **Overall**: measured value recorded (informational, not pass/fail -- see Claim)")
    a("")
    a("## Measured value(s)")
    a("")
    a("| Quantity | Value | Corner condition |")
    a("|---|---|---|")
    a(f"| Op point: v(TAIL) | {result.op_tail_v:.4f} V | {result.corner}/{result.temp_c}C/{VDD}V |")
    a(f"| Op point: v(OUTP)=v(OUTN) | {result.op_outp_v:.4f} V | {result.corner}/{result.temp_c}C/{VDD}V |")
    a(
        f"| Single-ended input-referred noise (`inoise_total`, referred through Vinp) | "
        f"{result.single_ended_rms_v * 1000:.4f} mV rms | {result.corner}/{result.temp_c}C/{VDD}V |"
    )
    a(
        f"| **Differential input-referred noise estimate** (`sqrt(2) x` single-ended, "
        f"diff-pair noise-doubling approximation) | **{result.differential_rms_v * 1000:.4f} mV rms** | "
        f"{result.corner}/{result.temp_c}C/{VDD}V |"
    )
    a("")
    a(
        f"DR-003 Item 4's provisional budget: <=1.0148 mV rms (baseline, ENOB>9.0) / "
        f"<=0.5859 mV rms (stretch, ENOB>9.5). This record's differential estimate "
        f"({result.differential_rms_v * 1000:.4f} mV rms) is reported as-is, without "
        "adjusting the topology or sizing to force a particular pass/fail outcome, "
        "per CLAUDE.md's 'no claim without a testbench' / 'do not relax a spec line "
        "to make a result pass' rules."
    )
    a("")
    a("- **Data provenance**: model-card-monte-carlo (sky130A BSIM4 device noise "
      "models via ngspice's `.noise` analysis; no literature/foundry-doc noise figure used)")
    a("")
    return _finalize_record(lines, record_path, info, netlist_sha, "noise")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="comparator-decision standalone testbench driver (issue #54)")
    ap.add_argument(
        "mode", nargs="?", choices=["regen", "offset", "noise", "noise-corners"],
        help="which characterization to run",
    )
    ap.add_argument("--check-env", action="store_true", help="check toolchain + PDK, print summary, exit")
    ap.add_argument("--corner", default="tt")
    ap.add_argument("--temp", type=float, default=27.0)
    ap.add_argument("--seed", type=int, default=1, help="offset: MC base seed")
    ap.add_argument("--n", type=int, default=16, help="offset: MC sample count")
    ap.add_argument("--record", action="store_true", help="write an evidence record under records/")
    ap.add_argument("--note", default="")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if args.check_env:
        result = toolchain.check_env()
        print(toolchain.summary())
        for w in result.warnings:
            print(f"  ! warning: {w}")
        for m in result.messages:
            print(f"  - {m}")
        return result.status

    if not args.mode:
        ap.print_help()
        return 2

    if args.mode == "regen":
        points, netlist_sha = run_regen_sweep(corner=args.corner, temp_c=args.temp, quiet=args.quiet)
        if args.record:
            path = write_regen_evidence(points, netlist_sha, args.corner, args.temp, note=args.note)
            print(f"wrote {path}")
        unresolved = [p for p in points if p.regen_time_ns is None]
        return 0 if not unresolved else 1

    if args.mode == "offset":
        result, netlist_sha = run_offset_mc(
            corner=args.corner, temp_c=args.temp, seed=args.seed, n=args.n, quiet=args.quiet
        )
        if args.record:
            path = write_offset_evidence(result, netlist_sha, note=args.note)
            print(f"wrote {path}")
        negctrl_stdev = statistics.pstdev(result.negctrl_offset_v) if len(result.negctrl_offset_v) > 1 else 0.0
        draws_stdev = statistics.pstdev(result.draws_offset_v) if len(result.draws_offset_v) > 1 else 0.0
        return 0 if (negctrl_stdev == 0.0 and draws_stdev > 0) else 1

    if args.mode == "noise":
        result, netlist_sha = run_noise(corner=args.corner, temp_c=args.temp, quiet=args.quiet)
        if args.record:
            path = write_noise_evidence(result, netlist_sha, note=args.note)
            print(f"wrote {path}")
        return 0

    if args.mode == "noise-corners":
        results, netlist_sha = run_noise_corners(quiet=args.quiet)
        if args.record:
            path = write_noise_campaign_evidence(results, netlist_sha, note=args.note)
            print(f"wrote {path}")
        binding = max(results, key=lambda r: r.differential_rms_v)
        return 0 if binding.differential_rms_v <= NOISE_BUDGET_BASELINE_V else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""pickoff offset campaign for the comparator-decision driver (issue #613 split of run.py)."""
from __future__ import annotations

import statistics
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .common import (
    DUT_FRAGMENT,
    EXPERIMENT_DIR,
    PICKOFF_NS,
    RESET_NS,
    RESET_TR_NS,
    VCM,
    VDD,
    _dut_lines,
    _run,
)
from .regen import (
    _finalize_record,
)
from harness import corners as corners_mod, evidence, pdk, toolchain

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
    t, outp, outn = toolchain.read_wrdata_csv(csv_path, 2)
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
) -> OffsetResult:
    info = pdk.resolve_or_raise()
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
    return result


def write_offset_evidence(
    result: OffsetResult, note: str = "", supersedes: str = "",
) -> Path:
    # Left on the manual resolve_provenance() path rather than
    # evidence.open_record() (issue #476): this is a Monte Carlo record, and
    # its `# Monte Carlo record {record_id}` title line matches the
    # repo-wide convention every other Monte Carlo writer uses
    # (sim/harness/mc_runner.py:292, sim/cdac-array-transfer/run_mc.py:336) --
    # open_record() hardcodes `# Record {record_id}`, so migrating would
    # trade that convention for a cosmetic mismatch rather than remove any.
    prov = evidence.resolve_provenance(EXPERIMENT_DIR, _dut_lines())
    record_id = prov.record_id
    record_path = prov.record_path
    draws_dir = EXPERIMENT_DIR / "mc-draws" / record_id
    draws_dir.mkdir(parents=True, exist_ok=True)
    for name, text in result.logs.items():
        (draws_dir / f"{name}.log").write_text(text)

    negctrl_stdev = statistics.pstdev(result.negctrl_offset_v) if len(result.negctrl_offset_v) > 1 else 0.0
    negctrl_ok = negctrl_stdev == 0.0
    draws_stdev = statistics.pstdev(result.draws_offset_v) if len(result.draws_offset_v) > 1 else 0.0
    draws_mean = statistics.fmean(result.draws_offset_v) if result.draws_offset_v else float("nan")

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
        lines, record_path, prov.pdk_line, prov.ng_version, prov.netlist_sha, "offset",
        extra={"MC seed": str(result.seed), "MC N": str(result.n)},
        supersedes=supersedes,
    )

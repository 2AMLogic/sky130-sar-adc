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
    python3 sim/comparator-decision/run.py regen-corners --record
        # full ratified PVT corner sweep of the decision-delay measurement
        # (issue #121 -- the comparator half of the bit-trial timing budget
        # docs/chipalooza/challenge-4-proposal.md Section 7 Item 2 names)
    python3 sim/comparator-decision/run.py offset --record --n 16 --seed 1
    python3 sim/comparator-decision/run.py noise --record
    python3 sim/comparator-decision/run.py noise-corners --record
        # full ratified PVT corner sweep of the noise measurement (issue #28)
    python3 sim/comparator-decision/run.py kickback --record
        # single-corner (tt/27C) kickback probe: 1kOhm series source
        # impedance into VINP/VINN, measuring the peak pin disturbance
        # across the CLK reset->evaluate transition (issue #346), plus its
        # common-mode / differential decomposition and later recovery
        # pick-offs (issue #390, DR-014's first gate) -- informational:
        # spec/target-spec.md's Kickback row is DRAFT (DR-011 via #361) and
        # spec/README.md forbids grading against a DRAFT value
    python3 sim/comparator-decision/run.py kickback-neutralized --record
        # identical probe, against the EXPERIMENTAL cross-coupled-
        # neutralization DUT variant (testbench/comparator_core_neutralized.
        # spice) instead of the adopted design -- issue #434, DR-014
        # Consequences Sec.4 / Open items' headroom-neutral mitigation-class
        # follow-on. Also informational; does not touch design/comparator.sch

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
# EXPERIMENTAL mitigation-class variant (issue #434, DR-014 Consequences
# Sec.4 / Open items): the same 11-device latch plus two cross-coupled
# neutralization capacitors on the input pair. NOT the adopted design --
# see the file's own header for why a hand-authored (non-xschem-derived)
# fragment is appropriate here, same as sim/harness-corner-smoke's own
# testbenches. Used only by the `kickback-neutralized` subcommand below.
DUT_FRAGMENT_NEUTRALIZED = TESTBENCH_DIR / "comparator_core_neutralized.spice"

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


def _dut_lines(fragment: Path = DUT_FRAGMENT) -> str:
    return fragment.read_text()


def _run(deck_text: str, scratch_dir: Path, log_name: str) -> str:
    return toolchain.run_ngspice(deck_text, scratch_dir, log_name)


# ---------------------------------------------------------------------------
# regen: regeneration time vs. differential input (deterministic sweep)
# ---------------------------------------------------------------------------

DEFAULT_VINDIFF_SWEEP_MV = [0.5, 1, 2, 5, 10, 20, 50, -10]
EVALUATE_NS = 40.0

# kickback probe stimulus (issue #346). The 1 kOhm series source impedance
# and the "worst-case overdrive edge" framing are the STIMULUS SHAPE named
# by the 2AMLogic/sky130-comparator prior-art finding (issue #346's Finding
# section, its own DR-003) -- a same-PDK, same-topology-class sibling canary
# whose cross-pollination is sanctioned by CLAUDE.md. Only the methodology
# (series-impedance probe + peak-pin-disturbance measurement across the CLK
# reset->evaluate transition) is reused; the deck below is re-derived from
# scratch against THIS repo's own design/comparator.sch (DR-004 Amendment A,
# the 11-device topology) -- no netlist, sizing, or measured VALUE from that
# other repo is introduced here, per CLAUDE.md's clean-room policy.
KICKBACK_RSRC_OHM = 1000.0  # 1 kOhm, matching the prior-art stimulus shape
KICKBACK_VINDIFF_SWEEP_MV = [0.0, 1.7578, 50.0]
#  * 0 mV is the SYMMETRY CONTROL. With no differential input the testbench
#    is symmetric by construction, so whatever pin disturbance is measured
#    there is common-mode: VINP and VINN move together (the same Vindiff=0
#    control idea `regen-corners` already uses, CORNERS_VINDIFF_SWEEP_MV
#    below). It is NOT a clock/reset-coupled-vs-decision-coupled split --
#    see the common-mode/differential decomposition columns below, which
#    measure that separation directly instead of inferring it from a
#    subtraction of two per-pin extrema (issue #390, DR-014 Decision (a)).
#  * 1.7578 mV is HALF A DIFFERENTIAL LSB (DR-003 Item 3's
#    2*V_REF/2^N = 3.5156 mV at V_REF = 1.8 V, N = 10 -- the same half-LSB
#    point CORNERS_VINDIFF_SWEEP_MV below sweeps, and for the same reason).
#    It is the SAR-relevant overdrive: the decisions whose accuracy a
#    differential kickback actually costs are the marginal ones near the
#    quantization band, not the large-overdrive ones that resolve fast.
#  * 50 mV is this experiment's OWN largest/worst-case overdrive point
#    (DEFAULT_VINDIFF_SWEEP_MV's top value above) -- a clean, fast decision
#    edge, the "worst-case overdrive edge" issue #346 called for.
# None of the three values is taken from the other repo's own sweep.
KICKBACK_EVALUATE_NS = EVALUATE_NS  # reuse the same 40ns evaluate window as
# `regen` -- the disturbance must be tracked THROUGH the full evaluate/
# regeneration transient, not just the ~100ps CLK ramp itself: the Finding
# this issue was filed from reports that the dominant kickback charge on a
# same-PDK sibling topology kept flowing PAST THE END of the clock ramp, so
# truncating the measurement window at the ramp alone would risk clipping
# the true peak on this design too.
KICKBACK_RECOVERY_PICKOFF_NS = [6.0, 10.0, 20.0]  # intermediate pick-off(s),
# in ns of absolute transient time, at which the common-mode and
# differential deviations are ALSO reported (issue #390). The end of the
# evaluate window is always appended to this list by run_kickback_sweep(),
# so the recovery table always closes on it. The evaluate edge starts at
# RESET_NS = 5 ns and the CLK ramp ends at 5.1 ns, so these three sit ~0.9,
# ~4.9 and ~14.9 ns past it: far enough out to say whether the disturbance
# is a transient that settles or a level that persists into the next bit
# trial, and spread widely enough to straddle the latch's own resolution
# instant, which moves by ~10 ns across this Vindiff grid. A pick-off is a
# RECOVERY INDICATOR, not a settling-time measurement -- the in-loop
# residual-at-next-decision quantity DR-011's Open items name needs a
# different (floating-top-plate) testbench and is deliberately out of
# scope here.


def _regen_deck(
    info: pdk.PdkInfo,
    corner: str,
    temp_c: float,
    vindiff_mv: float,
    log_name: str,
    supply_v: float = VDD,
    evaluate_ns: float = EVALUATE_NS,
    probe_supply_current: bool = False,
) -> str:
    """Single reset->evaluate transient deck for one (corner, temp, supply,
    Vindiff) point.

    `supply_v` and `evaluate_ns` default to the module constants, so the
    original `regen` subcommand's deck text is byte-identical to what it was
    before those two parameters existed. The `regen-corners` campaign below
    varies both.

    The input common mode tracks the supply (`Vcm = supply/2`) rather than
    staying pinned at the nominal 0.9 V: in THIS design `V_REF = V_DD`
    (DR-003 Item 1) and the CDAC's bottom-plate-switched common mode is
    `V_REF/2`, so a +-10% supply excursion moves the comparator's own input
    common mode with it. Holding Vcm fixed while the rail moved would
    simulate an operating point this design never presents to the
    comparator.

    `probe_supply_current` appends `i(Vdd)` to the `wrdata` vector list so
    the caller can read the supply current drawn during the CLK=0 reset
    phase. It is off by default so that the `regen` subcommand's deck text
    stays byte-identical to what produced its already-committed records."""
    vindiff_v = vindiff_mv / 1000.0
    vcm = supply_v / 2.0
    period_ns = RESET_NS + RESET_TR_NS + evaluate_ns + 10.0
    tstop_ns = RESET_NS + RESET_TR_NS + evaluate_ns
    lines = [
        f"* comparator-decision regen-time sweep -- vindiff={vindiff_mv}mV "
        f"corner={corner} temp={temp_c}C (issue #54)",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        f".param vdd_val = {supply_v}",
        "",
        "Vdd VDD 0 dc {vdd_val}",
        f"Vclk CLK 0 PULSE(0 {{vdd_val}} {RESET_NS}n {RESET_TR_NS}n {RESET_TR_NS}n "
        f"{evaluate_ns}n {period_ns}n)",
        f"Vinp VINP 0 dc {vcm + vindiff_v / 2}",
        f"Vinn VINN 0 dc {vcm - vindiff_v / 2}",
        "",
        _dut_lines(),
        "",
        ".control",
        f"tran 0.005n {tstop_ns}n",
        f"wrdata {log_name}.csv v(CLK) v(OUTP) v(OUTN)"
        + (" i(Vdd)" if probe_supply_current else ""),
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


# Fraction of the supply that |v(OUTP) - v(OUTN)| must stay BELOW at the last
# sample before the evaluate edge for the reset phase to count as having held
# the latch balanced. 5% of the rail (90 mV at 1.8 V) is ~25x the largest
# differential input this campaign applies (10 mV) and ~51x the half-LSB input
# (1.7578 mV), so a point inside it cannot have been pre-decided in any sense
# that would bias the measured decision delay; a point outside it has already
# separated by more than any input could account for.
RESET_HOLD_TOLERANCE_FRAC = 0.05


@dataclass
class RegenPoint:
    vindiff_mv: float
    regen_time_ns: float | None
    log_text: str
    # Reset-phase integrity instrumentation. `pre_edge_diff_v` is
    # v(OUTP) - v(OUTN) at the last sample strictly BEFORE the CLK edge
    # begins rising; on a latch whose reset actually holds it is ~0 V.
    # `reset_divergence_onset_ns` is the first time during the reset phase at
    # which |v(OUTP) - v(OUTN)| exceeded the same tolerance (None if it never
    # did). `reset_static_idd_a` is the supply current at that same pre-edge
    # sample (None unless the deck was built with probe_supply_current).
    pre_edge_diff_v: float | None = None
    final_diff_v: float | None = None
    reset_divergence_onset_ns: float | None = None
    reset_static_idd_a: float | None = None


def run_regen_sweep(
    corner: str = "tt", temp_c: float = 27.0,
    vindiff_sweep_mv: list[float] | None = None, quiet: bool = False,
    supply_v: float = VDD, evaluate_ns: float = EVALUATE_NS,
    probe_supply_current: bool = False,
) -> list[RegenPoint]:
    info = pdk.resolve_or_raise()
    vindiff_sweep_mv = vindiff_sweep_mv or DEFAULT_VINDIFF_SWEEP_MV
    evaluate_start_ns = RESET_NS + RESET_TR_NS
    # The "decided" threshold tracks the rail (0.5*supply), the same fraction
    # DECIDE_THRESHOLD_V encodes at the nominal supply -- a fixed 0.9 V
    # threshold would be a different fraction of a decided output at 1.62 V
    # or 1.98 V, so the per-corner numbers would not be comparable.
    decide_threshold_v = 0.5 * supply_v
    reset_hold_tol_v = RESET_HOLD_TOLERANCE_FRAC * supply_v
    points: list[RegenPoint] = []
    with tempfile.TemporaryDirectory(prefix="comparator-decision-regen-") as scratch:
        scratch_dir = Path(scratch)
        for vindiff_mv in vindiff_sweep_mv:
            log_name = f"regen_{vindiff_mv}mV".replace("-", "neg").replace(".", "p")
            deck = _regen_deck(
                info, corner, temp_c, vindiff_mv, log_name,
                supply_v=supply_v, evaluate_ns=evaluate_ns,
                probe_supply_current=probe_supply_current,
            )
            log_text = _run(deck, scratch_dir, log_name)
            csv_path = scratch_dir / f"{log_name}.csv"
            if probe_supply_current:
                t, clk, outp, outn, idd = toolchain.read_wrdata_csv(csv_path, 4)
            else:
                t, clk, outp, outn = toolchain.read_wrdata_csv(csv_path, 3)
                idd = None
            sign = 1.0 if vindiff_mv >= 0 else -1.0
            regen_ns = None
            for i, tt in enumerate(t):
                if tt < evaluate_start_ns * 1e-9:
                    continue
                diff = sign * (outp[i] - outn[i])
                if diff > decide_threshold_v:
                    regen_ns = (tt - evaluate_start_ns * 1e-9) * 1e9
                    break

            # Reset-phase integrity: everything strictly before the CLK edge
            # STARTS rising (RESET_NS, not evaluate_start_ns -- the 100 ps edge
            # itself already belongs to the evaluate transition).
            pre_edge_diff_v = None
            reset_static_idd_a = None
            onset_ns = None
            reset_idx = [i for i, tt in enumerate(t) if tt < RESET_NS * 1e-9]
            if reset_idx:
                last = reset_idx[-1]
                pre_edge_diff_v = outp[last] - outn[last]
                if idd is not None:
                    reset_static_idd_a = idd[last]
                for i in reset_idx:
                    if abs(outp[i] - outn[i]) > reset_hold_tol_v:
                        onset_ns = t[i] * 1e9
                        break

            points.append(RegenPoint(
                vindiff_mv=vindiff_mv, regen_time_ns=regen_ns, log_text=log_text,
                pre_edge_diff_v=pre_edge_diff_v,
                final_diff_v=(outp[-1] - outn[-1]) if t else None,
                reset_divergence_onset_ns=onset_ns,
                reset_static_idd_a=reset_static_idd_a,
            ))
            if not quiet:
                shown = f"{regen_ns:.4f}ns" if regen_ns is not None else "UNRESOLVED"
                extra = ""
                if pre_edge_diff_v is not None and abs(pre_edge_diff_v) > reset_hold_tol_v:
                    extra = (
                        f"  [RESET NOT HELD: pre-edge diff={pre_edge_diff_v:+.4f}V"
                        + (f", onset={onset_ns:.3f}ns" if onset_ns is not None else "")
                        + "]"
                    )
                print(f"  vindiff={vindiff_mv:+.4f}mV -> regen_time={shown}{extra}")
    return points


def _finalize_record(
    lines: list[str],
    record_path: Path,
    pdk_line: str,
    ng_version: str,
    netlist_sha: str,
    cmd: str,
    extra: dict[str, str] | None = None,
    supersedes: str = "",
) -> Path:
    """Shared tail for the write_*_evidence() functions below: append the
    environment block + footer boilerplate and write the record. `cmd` is
    the subcommand name (e.g. "regen", "offset", "noise"), used to build
    the "Written by" attribution.

    `supersedes` is the prior `<record-id>` this record REPLACES for the same
    claim, per sim/README.md's "Correction-supersession vs distinct-claim"
    rule -- empty (rendered "(none)") for a record that tests a different
    claim, however closely related. It is machine-load-bearing, not
    decoration: `sim/report/generate.py --check`'s freshness gate
    (`find_superseding_sibling()`) fails the build when a record cited by
    `sim/report/manifest.py` has been superseded by a sibling in the same
    `records/` directory, and it discovers that ONLY through the sibling's own
    **Supersedes** field. A re-characterization that mints new records without
    filling this in leaves the superseded ones citable forever with nothing to
    detect it. It is a CLI argument rather than a constant because which
    record is superseded is a per-run fact.
    """
    lines.extend(evidence.environment_block(
        pdk_line=pdk_line,
        ngspice_line=ng_version,
        netlist_sha256=netlist_sha,
        extra=extra,
    ))
    lines.append("")
    lines.extend(evidence.footer_lines(f"sim/comparator-decision/run.py {cmd}", supersedes))
    record_path.write_text("\n".join(lines))
    return record_path


def write_regen_evidence(
    points: list[RegenPoint], corner: str, temp_c: float,
    note: str = "", supersedes: str = "",
) -> Path:
    prov = evidence.resolve_provenance(EXPERIMENT_DIR, _dut_lines())
    record_id = prov.record_id
    record_path = prov.record_path
    corners_dir = EXPERIMENT_DIR / "corners" / record_id
    corners_dir.mkdir(parents=True, exist_ok=True)
    for p in points:
        safe = f"{p.vindiff_mv}mV".replace("-", "neg").replace(".", "p")
        (corners_dir / f"vindiff_{safe}.log").write_text(p.log_text)

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
    return _finalize_record(
        lines, record_path, prov.pdk_line, prov.ng_version, prov.netlist_sha,
        "regen", supersedes=supersedes,
    )


# ---------------------------------------------------------------------------
# kickback: peak pin disturbance on VINP/VINN into a 1 kOhm series source
# impedance, across the CLK reset->evaluate transition (issue #346)
#
# WHY THIS EXISTS. Issue #346 is a cross-pollinated prior-art Finding from
# the sky130-comparator canary (2AMLogic/sky130-comparator): a same-PDK
# (sky130A, 1.8V), same-topology-class (StrongARM/dynamic-latch) sibling
# measured a real kickback decomposition + mitigation option table for ITS
# OWN comparator, and flagged that THIS repo's embedded comparator
# (design/comparator.sch, DR-004) had never been given a dedicated kickback
# measurement of its own. This subcommand closes exactly that gap: an
# ORIGINAL kickback probe against this repo's own 11-device (DR-004
# Amendment A) netlist, using the sibling's STIMULUS SHAPE (1 kOhm series
# source impedance, worst-case overdrive edge) as reusable methodology --
# no netlist, sizing, or measured value crosses the repo boundary, per
# CLAUDE.md's clean-room / no-reverse-engineering rule.
#
# INFORMATIONAL, NOT GRADED. spec/target-spec.md's Kickback row is DRAFT
# (added by DR-011 via issue #361, after this subcommand's first record), and
# spec/README.md forbids encoding any value from that DRAFT table as a
# pass/fail threshold in sim/ -- so this subcommand still grades nothing, and
# it neither adds nor edits a spec row (CLAUDE.md: "the spec is a gate"; spec
# rows are a ratification act, not a Builder decision). The measurement below
# is reported exactly as-is, the same "exercised, not budgeted" treatment
# DR-004 Decision Sec.3 already gives `regen`/`offset`.
#
# WHAT ISSUE #390 ADDED. The per-pin peak the first record reported is the
# quantity DR-011's row bounds, and it is unchanged here. But it says nothing
# about how much of the disturbance is COMMON-MODE (which a differential
# top-plate CDAC rejects to first order) versus DIFFERENTIAL (which lands on
# the decision). DR-014 -- which decided NOT to adopt a static preamp and
# left DR-004 Decision Sec.1 standing -- names that split as the first gate
# on revisiting the call, because the mitigation class worth evaluating
# depends on which component dominates. This subcommand therefore also
# reports, per Vindiff point, the peak common-mode and peak differential
# deviation with their instants, plus later recovery pick-offs of both, and
# sweeps a half-LSB Vindiff point so the split is measured at the marginal
# decisions it actually costs rather than only at a large overdrive.
#
# METHOD. Each input pin is driven by an ideal DC source in series with a
# KICKBACK_RSRC_OHM resistor landing on the DUT's own VINP/VINN pin -- the
# standard "bench source impedance" kickback-probe topology: any charge the
# switching latch pushes back onto that pin through the input pair's own
# Cgd/Cgs shows up as an I*R voltage drop across the resistor, i.e. exactly
# the "pin disturbance" a real (non-ideal) driving source would see. The
# transient covers the full reset->evaluate->regeneration window (not just
# the CLK ramp) -- see KICKBACK_EVALUATE_NS's comment above for why.
# ---------------------------------------------------------------------------


def _kickback_deck(
    info: pdk.PdkInfo,
    corner: str,
    temp_c: float,
    vindiff_mv: float,
    log_name: str,
    supply_v: float = VDD,
    evaluate_ns: float = KICKBACK_EVALUATE_NS,
    rsrc_ohm: float = KICKBACK_RSRC_OHM,
    dut_text: str | None = None,
) -> str:
    """Single reset->evaluate transient deck for one (corner, temp, supply,
    Vindiff) kickback point: identical stimulus shape to `_regen_deck`
    except VINP/VINN are driven through a `rsrc_ohm` series resistor from an
    ideal DC source rather than directly, so the DUT pin's own voltage can
    depart from the ideal source's target under switching-induced current.

    `dut_text` lets a caller swap in a different DUT fragment (e.g. issue
    #434's `DUT_FRAGMENT_NEUTRALIZED` mitigation-class variant) without
    touching this deck's stimulus shape at all -- defaults to `_dut_lines()`
    (the adopted `DUT_FRAGMENT`), byte-identical to this function's behavior
    before `dut_text` existed."""
    vindiff_v = vindiff_mv / 1000.0
    vcm = supply_v / 2.0
    period_ns = RESET_NS + RESET_TR_NS + evaluate_ns + 10.0
    tstop_ns = RESET_NS + RESET_TR_NS + evaluate_ns
    lines = [
        f"* comparator-decision kickback probe -- vindiff={vindiff_mv}mV "
        f"corner={corner} temp={temp_c}C rsrc={rsrc_ohm}ohm (issue #346)",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        f".param vdd_val = {supply_v}",
        "",
        "Vdd VDD 0 dc {vdd_val}",
        f"Vclk CLK 0 PULSE(0 {{vdd_val}} {RESET_NS}n {RESET_TR_NS}n {RESET_TR_NS}n "
        f"{evaluate_ns}n {period_ns}n)",
        f"Vinp_ideal VINP_IDEAL 0 dc {vcm + vindiff_v / 2}",
        f"Vinn_ideal VINN_IDEAL 0 dc {vcm - vindiff_v / 2}",
        f"Rsrc_p VINP_IDEAL VINP {rsrc_ohm}",
        f"Rsrc_n VINN_IDEAL VINN {rsrc_ohm}",
        "",
        dut_text if dut_text is not None else _dut_lines(),
        "",
        ".control",
        f"tran 0.005n {tstop_ns}n",
        f"wrdata {log_name}.csv v(CLK) v(VINP) v(VINN) v(OUTP) v(OUTN)",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


@dataclass
class KickbackRecoveryPoint:
    """One later pick-off of the common-mode / differential deviations.

    `requested_ns` is the pick-off the caller asked for; `time_ns` is the
    actual transient sample used (the nearest one, since ngspice's adaptive
    timestep does not land exactly on a requested instant). `label` is what
    the record's recovery table prints in its first column."""

    label: str
    requested_ns: float
    time_ns: float
    cm_dev_v: float
    diff_dev_v: float


@dataclass
class KickbackPoint:
    vindiff_mv: float
    target_p_v: float
    target_n_v: float
    # Peak signed deviation of EITHER pin's actual voltage from its own
    # ideal-source target, over the full transient -- `peak_pos_*` is the
    # largest positive excursion, `peak_neg_*` the largest negative one
    # (most negative, i.e. minimum), each independently tracking which pin
    # (VINP or VINN) and what time it occurred at.
    #
    # These two are UNCHANGED by issue #390 and stay the record's primary
    # figures: they are the quantity DR-011's DRAFT Kickback row bounds
    # ("peak pin disturbance"), and the quantity the 20260924-041815-afcb1b5
    # baseline reported, so they are what a superseding record has to
    # reproduce.
    peak_pos_dev_v: float
    peak_pos_time_ns: float | None
    peak_pos_pin: str
    peak_neg_dev_v: float
    peak_neg_time_ns: float | None
    peak_neg_pin: str
    # The common-mode / differential DECOMPOSITION of the same disturbance
    # (issue #390, DR-014's first gate). Per sample:
    #
    #     cm(t)   = ((v(VINP) - target_p) + (v(VINN) - target_n)) / 2
    #     diff(t) =  (v(VINP) - target_p) - (v(VINN) - target_n)
    #
    # Each series gets its largest POSITIVE and largest NEGATIVE excursion
    # with the instant it occurred at, the same both-signs convention the
    # per-pin peaks above already use -- and for a stronger reason here:
    # diff(t) is not single-lobed. It carries an early excursion during the
    # CLK ramp, which grows with overdrive, and a later one as the latch
    # resolves, which is what dominates at small overdrive. A single
    # largest-magnitude figure would silently report a different lobe at
    # different points of the Vindiff grid and read as one trend.
    #
    # These do not replace the per-pin peaks: a differential top-plate CDAC
    # rejects cm(t) to first order, so diff(t) is the component that lands on
    # a SAR decision, while the per-pin peaks are an extremum over either pin
    # independently and therefore bound neither component on their own.
    peak_cm_pos_dev_v: float
    peak_cm_pos_time_ns: float | None
    peak_cm_neg_dev_v: float
    peak_cm_neg_time_ns: float | None
    peak_diff_pos_dev_v: float
    peak_diff_pos_time_ns: float | None
    peak_diff_neg_dev_v: float
    peak_diff_neg_time_ns: float | None
    # Later pick-offs of the same two series -- a first recovery indicator
    # (see KICKBACK_RECOVERY_PICKOFF_NS).
    recovery: list[KickbackRecoveryPoint]
    log_text: str

    @property
    def peak_cm_dev_v(self) -> float:
        """The larger-magnitude of the two common-mode excursions, signed."""
        return max(
            (self.peak_cm_pos_dev_v, self.peak_cm_neg_dev_v), key=abs
        )

    @property
    def peak_cm_time_ns(self) -> float | None:
        return (
            self.peak_cm_pos_time_ns
            if self.peak_cm_dev_v == self.peak_cm_pos_dev_v
            else self.peak_cm_neg_time_ns
        )

    @property
    def peak_diff_dev_v(self) -> float:
        """The larger-magnitude of the two differential excursions, signed."""
        return max(
            (self.peak_diff_pos_dev_v, self.peak_diff_neg_dev_v), key=abs
        )

    @property
    def peak_diff_time_ns(self) -> float | None:
        return (
            self.peak_diff_pos_time_ns
            if self.peak_diff_dev_v == self.peak_diff_pos_dev_v
            else self.peak_diff_neg_time_ns
        )


def _nearest_sample(t: list[float], target_ns: float) -> int:
    """Index of the transient sample nearest `target_ns` (absolute ns).

    ngspice's adaptive timestep does not land on a requested instant, so a
    pick-off names the nearest sample rather than interpolating -- the
    record then prints the instant actually read, not the one asked for."""
    return min(range(len(t)), key=lambda i: abs(t[i] * 1e9 - target_ns))


def run_kickback_sweep(
    corner: str = "tt", temp_c: float = 27.0,
    vindiff_sweep_mv: list[float] | None = None, quiet: bool = False,
    supply_v: float = VDD, evaluate_ns: float = KICKBACK_EVALUATE_NS,
    rsrc_ohm: float = KICKBACK_RSRC_OHM,
    recovery_pickoff_ns: list[float] | None = None,
    dut_fragment: Path = DUT_FRAGMENT,
) -> list[KickbackPoint]:
    """`dut_fragment` lets a caller run this exact sweep against a different
    DUT netlist fragment (issue #434's mitigation-class variants) without
    touching the stimulus shape, decomposition, or recovery pick-off logic
    below at all -- defaults to the adopted `DUT_FRAGMENT`, so this
    function's behavior is unchanged for every existing caller."""
    info = pdk.resolve_or_raise()
    vindiff_sweep_mv = vindiff_sweep_mv or KICKBACK_VINDIFF_SWEEP_MV
    if recovery_pickoff_ns is None:
        recovery_pickoff_ns = list(KICKBACK_RECOVERY_PICKOFF_NS)
    vcm = supply_v / 2.0
    dut_text = _dut_lines(dut_fragment)
    points: list[KickbackPoint] = []
    with tempfile.TemporaryDirectory(prefix="comparator-decision-kickback-") as scratch:
        scratch_dir = Path(scratch)
        for vindiff_mv in vindiff_sweep_mv:
            log_name = f"kickback_{vindiff_mv}mV".replace("-", "neg").replace(".", "p")
            deck = _kickback_deck(
                info, corner, temp_c, vindiff_mv, log_name,
                supply_v=supply_v, evaluate_ns=evaluate_ns, rsrc_ohm=rsrc_ohm,
                dut_text=dut_text,
            )
            log_text = _run(deck, scratch_dir, log_name)
            csv_path = scratch_dir / f"{log_name}.csv"
            t, clk, vinp, vinn, outp, outn = toolchain.read_wrdata_csv(csv_path, 5)
            vindiff_v = vindiff_mv / 1000.0
            target_p = vcm + vindiff_v / 2
            target_n = vcm - vindiff_v / 2

            best_pos_dev, best_pos_ns, best_pos_pin = float("-inf"), None, ""
            best_neg_dev, best_neg_ns, best_neg_pin = float("inf"), None, ""
            for i, tt in enumerate(t):
                for dev, pin in (
                    (vinp[i] - target_p, "VINP"),
                    (vinn[i] - target_n, "VINN"),
                ):
                    if dev > best_pos_dev:
                        best_pos_dev, best_pos_ns, best_pos_pin = dev, tt * 1e9, pin
                    if dev < best_neg_dev:
                        best_neg_dev, best_neg_ns, best_neg_pin = dev, tt * 1e9, pin

            # Common-mode / differential decomposition of the SAME two
            # deviation series the per-pin peaks above are taken from
            # (issue #390) -- see KickbackPoint's field comment for the
            # definitions and for why both are needed.
            cm_series = [
                ((vinp[i] - target_p) + (vinn[i] - target_n)) / 2.0
                for i in range(len(t))
            ]
            diff_series = [
                (vinp[i] - target_p) - (vinn[i] - target_n)
                for i in range(len(t))
            ]
            cm_pos_i = max(range(len(t)), key=lambda i: cm_series[i])
            cm_neg_i = min(range(len(t)), key=lambda i: cm_series[i])
            diff_pos_i = max(range(len(t)), key=lambda i: diff_series[i])
            diff_neg_i = min(range(len(t)), key=lambda i: diff_series[i])

            recovery: list[KickbackRecoveryPoint] = []
            end_ns = t[-1] * 1e9
            pickoffs: list[tuple[str, float]] = [
                (f"{req:g} ns", req)
                for req in recovery_pickoff_ns
                if req < end_ns
            ]
            pickoffs.append(("end of window", end_ns))
            for label, req_ns in pickoffs:
                i = _nearest_sample(t, req_ns)
                recovery.append(KickbackRecoveryPoint(
                    label=label, requested_ns=req_ns, time_ns=t[i] * 1e9,
                    cm_dev_v=cm_series[i], diff_dev_v=diff_series[i],
                ))

            points.append(KickbackPoint(
                vindiff_mv=vindiff_mv, target_p_v=target_p, target_n_v=target_n,
                peak_pos_dev_v=best_pos_dev, peak_pos_time_ns=best_pos_ns,
                peak_pos_pin=best_pos_pin,
                peak_neg_dev_v=best_neg_dev, peak_neg_time_ns=best_neg_ns,
                peak_neg_pin=best_neg_pin,
                peak_cm_pos_dev_v=cm_series[cm_pos_i],
                peak_cm_pos_time_ns=t[cm_pos_i] * 1e9,
                peak_cm_neg_dev_v=cm_series[cm_neg_i],
                peak_cm_neg_time_ns=t[cm_neg_i] * 1e9,
                peak_diff_pos_dev_v=diff_series[diff_pos_i],
                peak_diff_pos_time_ns=t[diff_pos_i] * 1e9,
                peak_diff_neg_dev_v=diff_series[diff_neg_i],
                peak_diff_neg_time_ns=t[diff_neg_i] * 1e9,
                recovery=recovery,
                log_text=log_text,
            ))
            if not quiet:
                print(
                    f"  vindiff={vindiff_mv:+.4f}mV -> "
                    f"peak+={best_pos_dev * 1000:+.4f}mV ({best_pos_pin}@{best_pos_ns:.3f}ns)  "
                    f"peak-={best_neg_dev * 1000:+.4f}mV ({best_neg_pin}@{best_neg_ns:.3f}ns)"
                )
                print(
                    f"      CM  += {cm_series[cm_pos_i] * 1000:+.4f}mV "
                    f"(@{t[cm_pos_i] * 1e9:.3f}ns)  "
                    f"-= {cm_series[cm_neg_i] * 1000:+.4f}mV "
                    f"(@{t[cm_neg_i] * 1e9:.3f}ns)"
                )
                print(
                    f"      diff+= {diff_series[diff_pos_i] * 1000:+.4f}mV "
                    f"(@{t[diff_pos_i] * 1e9:.3f}ns)  "
                    f"-= {diff_series[diff_neg_i] * 1000:+.4f}mV "
                    f"(@{t[diff_neg_i] * 1e9:.3f}ns)"
                )
                print(
                    "      recovery: "
                    + "  ".join(
                        f"[{r.label} @{r.time_ns:.3f}ns: "
                        f"CM={r.cm_dev_v * 1000:+.4f}mV "
                        f"diff={r.diff_dev_v * 1000:+.4f}mV]"
                        for r in recovery
                    )
                )
    return points


def write_kickback_evidence(
    points: list[KickbackPoint], corner: str, temp_c: float,
    note: str = "", supersedes: str = "",
) -> Path:
    prov = evidence.resolve_provenance(EXPERIMENT_DIR, _dut_lines())
    record_id = prov.record_id
    record_path = prov.record_path
    corners_dir = EXPERIMENT_DIR / "corners" / record_id
    corners_dir.mkdir(parents=True, exist_ok=True)
    for p in points:
        safe = f"{p.vindiff_mv}mV".replace("-", "neg").replace(".", "p")
        (corners_dir / f"kickback_{safe}.log").write_text(p.log_text)

    worst = max(points, key=lambda p: max(abs(p.peak_pos_dev_v), abs(p.peak_neg_dev_v)))
    worst_abs_v = max(abs(worst.peak_pos_dev_v), abs(worst.peak_neg_dev_v))
    worst_cm = max(points, key=lambda p: abs(p.peak_cm_dev_v))
    # The Vindiff=0 symmetry control is excluded from the DIFFERENTIAL worst
    # case on purpose: at exactly zero input the latch resolves on solver
    # asymmetry alone, so its differential columns report a metastable-
    # resolution artifact rather than a disturbance any bit trial pays. The
    # prose under the table says so; this keeps the Overall line from
    # quoting it as the headline number. Falls back to the full set if the
    # grid happens to hold nothing but the control.
    _diff_candidates = [p for p in points if p.vindiff_mv != 0.0] or list(points)
    worst_diff = max(_diff_candidates, key=lambda p: abs(p.peak_diff_dev_v))

    lines: list[str] = []
    a = lines.append
    a(f"# Record {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    a(
        "- **Claim**: none -- INFORMATIONAL. spec/target-spec.md's Kickback "
        "row is DRAFT (added by DR-011 via issue #361, with its bound adopted "
        "verbatim from a sibling canary rather than derived from this block's "
        "own budget), and spec/README.md forbids encoding any value from that "
        "DRAFT table as a pass/fail threshold in sim/ -- so nothing below is "
        "graded against it. This record measures design/comparator.sch's own "
        f"peak pin disturbance into a {KICKBACK_RSRC_OHM:g}Ohm series source "
        "impedance, and -- new here, per issue #390 -- the common-mode / "
        "differential decomposition of that disturbance, for a future "
        "mitigation/ratification decision to weigh, per DR-004 Decision "
        "Sec.3's 'exercised, not budgeted' treatment of regen/offset -- this "
        "record gives kickback the same status. The per-pin peaks originate "
        "in issue #346, a cross-pollinated prior-art report from the "
        "sky130-comparator canary (2AMLogic/sky130-comparator); the "
        "decomposition is DR-014's own first gate (issue #390), the "
        "measurement that record names as the input a kickback-mitigation "
        "choice must be re-taken on. See Methodology below for what was and "
        "was not reused from the sibling canary."
    )
    a(f"- **Netlist provenance**: schematic (`{DUT_FRAGMENT.relative_to(evidence.REPO_ROOT)}`)")
    a(
        f"- **Corner matrix run**: process=['{corner}'], temperature_c=[{temp_c}], "
        f"supply_v=[{VDD}] (1 PVT point -- **subset-corner justification**: "
        "first-pass, nominal-corner-only characterization, consistent with "
        "how DR-004's own `regen`/`offset`/`noise` records each landed "
        "single-corner first; a PVT sweep is deferred to future work, see "
        "the record's closing note)"
    )
    a(
        f"- **Stimulus**: {KICKBACK_RSRC_OHM:g}Ohm series source impedance on each of "
        f"VINP/VINN (ideal DC source -> resistor -> DUT pin); single "
        f"reset({RESET_NS}ns, CLK=0)->evaluate(CLK={VDD}V) edge per run "
        f"over a {KICKBACK_EVALUATE_NS:g}ns evaluate window; Vcm={VCM}V. "
        "Methodology (series-impedance probe + peak-pin-disturbance-over-"
        "the-transition measurement) follows the stimulus shape named by "
        "2AMLogic/sky130-comparator's DR-003 kickback probe -- a same-PDK, "
        "same-topology-class sibling canary, cross-pollination sanctioned "
        "by CLAUDE.md. This record's netlist, device sizing, Vindiff grid, "
        "and every measured number below are re-derived from scratch "
        "against THIS repo's own design/comparator.sch; no value from the "
        "other repo is introduced, cited, or reconstructed here, per "
        "CLAUDE.md's clean-room policy."
    )
    if note:
        a(f"- **Note**: {note}")
    a(
        f"- **Overall**: measured (informational, see Claim above) -- worst-case "
        f"peak pin disturbance across the {len(points)} Vindiff point(s) run: "
        f"{worst_abs_v * 1000:.4f} mV (at Vindiff={worst.vindiff_mv:+.4f}mV). "
        f"Decomposed (issue #390, DR-014's first gate): worst-case peak "
        f"COMMON-MODE deviation {worst_cm.peak_cm_dev_v * 1000:+.4f} mV "
        f"(at Vindiff={worst_cm.vindiff_mv:+.4f}mV, "
        f"t={worst_cm.peak_cm_time_ns:.3f}ns); worst-case peak DIFFERENTIAL "
        f"deviation {worst_diff.peak_diff_dev_v * 1000:+.4f} mV "
        f"(at Vindiff={worst_diff.vindiff_mv:+.4f}mV, "
        f"t={worst_diff.peak_diff_time_ns:.3f}ns), excluding the "
        f"Vindiff=0mV symmetry-control row, whose differential columns are a "
        f"metastable-resolution artifact rather than a kickback (see below)"
    )
    a("")
    a("## Measured value(s)")
    a("")
    a(
        "| Vindiff (mV) | peak+ (mV) | pin / time (ns) | peak- (mV) | "
        "pin / time (ns) | CM+ (mV) @ t (ns) | CM- (mV) @ t (ns) | "
        "diff+ (mV) @ t (ns) | diff- (mV) @ t (ns) |"
    )
    a("|---|---|---|---|---|---|---|---|---|")

    def _at(dev_v: float | None, time_ns: float | None) -> str:
        if dev_v is None:
            return "n/a"
        when = f"{time_ns:.3f}" if time_ns is not None else "n/a"
        return f"{dev_v * 1000:+.4f} @ {when}"

    for p in sorted(points, key=lambda p: p.vindiff_mv):
        pos_ns = f"{p.peak_pos_time_ns:.3f}" if p.peak_pos_time_ns is not None else "n/a"
        neg_ns = f"{p.peak_neg_time_ns:.3f}" if p.peak_neg_time_ns is not None else "n/a"
        a(
            f"| {p.vindiff_mv:+.4f} | {p.peak_pos_dev_v * 1000:+.4f} | "
            f"{p.peak_pos_pin} @ {pos_ns} | {p.peak_neg_dev_v * 1000:+.4f} | "
            f"{p.peak_neg_pin} @ {neg_ns} | "
            f"{_at(p.peak_cm_pos_dev_v, p.peak_cm_pos_time_ns)} | "
            f"{_at(p.peak_cm_neg_dev_v, p.peak_cm_neg_time_ns)} | "
            f"{_at(p.peak_diff_pos_dev_v, p.peak_diff_pos_time_ns)} | "
            f"{_at(p.peak_diff_neg_dev_v, p.peak_diff_neg_time_ns)} |"
        )
    a("")
    a(
        "`peak+`/`peak-` are the largest positive and largest negative "
        "deviation of EITHER pin from its own ideal-source target, taken over "
        "VINP and VINN independently -- unchanged from this measurement's "
        "baseline record, because that per-pin extremum is the quantity "
        "spec/target-spec.md's DRAFT Kickback row bounds and therefore what a "
        "superseding record has to reproduce. The `CM`/`diff` columns are the "
        "largest positive and largest negative excursion, each with the "
        "instant it occurred at, of the two DECOMPOSED series taken over the "
        "same transient:"
    )
    a("")
    a("```")
    a("cm(t)   = ((v(VINP) - target_p) + (v(VINN) - target_n)) / 2")
    a("diff(t) =  (v(VINP) - target_p) -  (v(VINN) - target_n)")
    a("```")
    a("")
    a(
        "Why the decomposition and not the per-pin peaks alone: a "
        "differential top-plate CDAC rejects a common-mode pin disturbance to "
        "first order, so `cm(t)` is largely not paid for by the conversion, "
        "while `diff(t)` lands directly on the decision the comparator is "
        "about to make. The per-pin peaks bound neither component on their "
        "own -- they are an extremum over either pin independently -- so a "
        "subtraction between two per-pin rows is NOT a common-mode / "
        "differential split, and this record does not read it as one "
        "(issue #390, DR-014 Decision (a))."
    )
    a("")
    a(
        "Why both signs of each decomposed series rather than one "
        "largest-magnitude figure: `diff(t)` is not single-lobed. It carries "
        "an early excursion while the CLK ramp is still moving, and a later "
        "one as the latch resolves; which of the two is larger changes across "
        "the Vindiff grid, so a single magnitude-extremum column would report "
        "a different physical event at different rows and read as one trend. "
        "Reading the two lobes separately is the point of the split."
    )
    a("")
    a(
        "The Vindiff=0mV row (if present) is the SYMMETRY CONTROL: with no "
        "differential input the deck is symmetric by construction, so its "
        "common-mode column IS its whole per-pin disturbance. Its "
        "differential columns are NOT a zero reference, and this record does "
        "not present them as one: at exactly zero input the latch has no "
        "correct answer to resolve to, so it resolves on solver asymmetry "
        "alone, and once the outputs diverge they couple back differentially "
        "onto the input pins through the input pair's own Cgd. That is a "
        "metastable-resolution artifact of a zero-input transient, not a "
        "kickback this converter ever pays -- a real bit trial always "
        "presents a nonzero residual. The nonzero Vindiff rows are the ones "
        "to read a differential component off."
    )
    a("")
    a(
        f"The half-LSB row (Vindiff=+{0.5 * DIFFERENTIAL_LSB_MV:.4f}mV, half of "
        f"DR-003 Item 3's {DIFFERENTIAL_LSB_MV:.4f} mV differential LSB) is "
        "the SAR-relevant overdrive: it is the scale of the marginal "
        "decisions whose accuracy a differential kickback actually costs. "
        "The large-overdrive row resolves fast and is the worst case for the "
        "per-pin peak, not necessarily for the decision."
    )
    a("")
    a("### Recovery pick-offs")
    a("")
    a(
        "Both decomposed series, re-read at one or more later instants -- a "
        "first indicator of whether the disturbance is a transient that "
        "settles inside the evaluate window or a level that persists. The "
        "instant printed is the nearest transient sample to the pick-off "
        "asked for (ngspice's adaptive timestep does not land exactly on a "
        "requested time). This is NOT the in-loop residual-at-next-decision "
        "measurable DR-011's Open items name: that quantity needs a floating "
        "top plate and a following bit trial, neither of which this "
        "ideal-source bench has."
    )
    a("")
    a("| Vindiff (mV) | pick-off | t (ns) | CM deviation (mV) | differential deviation (mV) |")
    a("|---|---|---|---|---|")
    for p in sorted(points, key=lambda p: p.vindiff_mv):
        for r in p.recovery:
            a(
                f"| {p.vindiff_mv:+.4f} | {r.label} | {r.time_ns:.3f} | "
                f"{r.cm_dev_v * 1000:+.4f} | {r.diff_dev_v * 1000:+.4f} |"
            )
    a("")
    a(
        "No spec/target-spec.md line is added, edited, relaxed, or graded "
        "against by this record -- see Claim above. The Kickback row's bound "
        "and DRAFT status are DR-011's and are untouched here; weighing this "
        "measurement (and any mitigation option) against a ratification act "
        "is a decision record's job, not this testbench's. DR-014 is the "
        "record that asked for the decomposition above, and its Consequences "
        "Sec.4 states what a differential component above the row's bound "
        "obliges: the headroom-neutral mitigation classes it names must be "
        "measured before a static preamp is reconsidered. This record "
        "supplies the input; it does not make that call."
    )
    a("")
    a(
        "- **Data provenance**: model-card-monte-carlo (sky130A BSIM4 "
        "compact device models via ngspice transient analysis; no "
        "literature/foundry-doc figure used, and no measured value from "
        "`2AMLogic/sky130-comparator` transferred, per CLAUDE.md's "
        "clean-room policy)"
    )
    a("")
    return _finalize_record(
        lines, record_path, prov.pdk_line, prov.ng_version, prov.netlist_sha,
        "kickback", supersedes=supersedes,
    )


# ---------------------------------------------------------------------------
# kickback-neutralized: the same kickback probe against the EXPERIMENTAL
# cross-coupled-neutralization DUT variant (issue #434, DR-014 Consequences
# Sec.4 / Open items)
#
# WHY THIS EXISTS. DR-014 kept DR-004 Decision Sec.1 (no static preamp) and
# named its own "first gate" on revisiting that call: issue #390's
# common-mode/differential split of the kickback measurement. #390 has since
# closed and measured a differential component above DR-011's DRAFT bound at
# the large-overdrive point (record 20260925-050027-0259924, cited by
# write_kickback_evidence() above) -- the condition DR-014 Consequences
# Sec.4 named as the trigger for measuring its (c) "headroom-neutral"
# mitigation classes before a preamp is reconsidered again. This subcommand
# measures the first of those classes named as unevaluated anywhere in this
# program: cross-coupled neutralization, which DR-014 (c) says targets the
# differential component specifically. It is NOT a topology change to
# design/comparator.sch -- see DUT_FRAGMENT_NEUTRALIZED's own header for
# what was added and why, and why a hand-authored (non-xschem) fragment is
# appropriate for a mitigation-class scoping measurement that has not been
# adopted.
#
# METHOD. Byte-identical stimulus, decomposition, and recovery pick-off
# machinery to `kickback` above (this reuses `_kickback_deck()` and
# `run_kickback_sweep()` unchanged, just pointed at
# `DUT_FRAGMENT_NEUTRALIZED` via the `dut_fragment` parameter both gained
# for this purpose) -- so this record's numbers are directly comparable to
# #390's, which is the whole point: same stimulus, same decomposition, only
# the DUT differs by the two added neutralization capacitors.
# ---------------------------------------------------------------------------

# Baseline figures this record compares itself against, cited from
# sim/comparator-decision/records/20260925-050027-0259924.md (issue #390's
# closing measurement, DR-014's first gate) -- NOT re-derived here, quoted
# so the comparison in the record text below is traceable to that record
# without re-opening it. If a later baseline record supersedes that one,
# this module constant is what needs updating, not the prose below.
BASELINE_RECORD_390 = "20260925-050027-0259924"
BASELINE_390_PEAK_NEG_MV = -73.3673  # Vindiff=+50mV, VINP@5.108ns
BASELINE_390_DIFF_NEG_50MV_MV = -10.9153  # Vindiff=+50mV, t=5.083ns
BASELINE_390_DIFF_POS_HALFLSB_MV = 4.1918  # Vindiff=+1.7578mV, t=7.077ns


def write_kickback_neutralized_evidence(
    points: list[KickbackPoint], corner: str, temp_c: float,
    note: str = "", supersedes: str = "",
) -> Path:
    """Evidence record for the cross-coupled-neutralization mitigation-class
    measurement (issue #434). Structured like write_kickback_evidence()
    above (same table shape, same recovery-pickoff section) but a distinct
    function rather than a parameterized shared one: this record's Claim,
    netlist provenance, and comparison prose are specific to a mitigation
    CLASS measurement against an unadopted DUT variant, not to
    design/comparator.sch's own baseline -- keeping them separate avoids
    quietly repurposing the baseline record's own carefully-scoped Claim
    text for a different claim (sim/README's distinct-claim-vs-correction
    distinction)."""
    dut_text = _dut_lines(DUT_FRAGMENT_NEUTRALIZED)
    prov = evidence.resolve_provenance(EXPERIMENT_DIR, dut_text)
    record_id = prov.record_id
    record_path = prov.record_path
    corners_dir = EXPERIMENT_DIR / "corners" / record_id
    corners_dir.mkdir(parents=True, exist_ok=True)
    for p in points:
        safe = f"{p.vindiff_mv}mV".replace("-", "neg").replace(".", "p")
        (corners_dir / f"kickback_neutralized_{safe}.log").write_text(p.log_text)

    worst = max(points, key=lambda p: max(abs(p.peak_pos_dev_v), abs(p.peak_neg_dev_v)))
    worst_abs_v = max(abs(worst.peak_pos_dev_v), abs(worst.peak_neg_dev_v))
    worst_cm = max(points, key=lambda p: abs(p.peak_cm_dev_v))
    _diff_candidates = [p for p in points if p.vindiff_mv != 0.0] or list(points)
    worst_diff = max(_diff_candidates, key=lambda p: abs(p.peak_diff_dev_v))
    # Tolerance widened from 1e-6 to 1e-3 mV: KICKBACK_VINDIFF_SWEEP_MV's
    # half-LSB point is the rounded literal 1.7578 (see that constant's own
    # comment), while 0.5 * DIFFERENTIAL_LSB_MV computes to 1.7578125 -- an
    # exact-match tolerance of 1e-6 mV silently matched nothing and dropped
    # the "Half-LSB point" comparison paragraph below without erroring.
    half_lsb_candidates = [p for p in points if abs(p.vindiff_mv - 0.5 * DIFFERENTIAL_LSB_MV) < 1e-3]
    half_lsb = half_lsb_candidates[0] if half_lsb_candidates else None

    diff_delta_pct = (
        (abs(worst_diff.peak_diff_dev_v) * 1000.0 - abs(BASELINE_390_DIFF_NEG_50MV_MV))
        / abs(BASELINE_390_DIFF_NEG_50MV_MV) * 100.0
    )
    peak_delta_pct = (
        (worst_abs_v * 1000.0 - abs(BASELINE_390_PEAK_NEG_MV))
        / abs(BASELINE_390_PEAK_NEG_MV) * 100.0
    )

    lines: list[str] = []
    a = lines.append
    a(f"# Record {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    a(
        "- **Claim**: none -- INFORMATIONAL, and NOT a measurement of "
        "design/comparator.sch (the adopted design). This record measures "
        "the SAME kickback probe as "
        f"`sim/comparator-decision/records/{BASELINE_RECORD_390}.md` "
        "(issue #390's baseline, DR-014's first gate) run instead against "
        "`sim/comparator-decision/testbench/comparator_core_neutralized.spice`, "
        "an EXPERIMENTAL variant that adds two cross-coupled neutralization "
        "capacitors to the same 11-device StrongARM-class latch. This is "
        "issue #434's mitigation-class measurement, per DR-014 Consequences "
        "Sec.4 / Open items ('cross-coupled neutralization ... targets the "
        "differential component ... unmeasured anywhere in this program'). "
        "spec/target-spec.md's Kickback row remains DRAFT and nothing here "
        "is graded against it (spec/README.md), and no design/*.sch file is "
        "touched by this measurement -- adopting this or any mitigation "
        "class is a future decision record's job, not this testbench's. See "
        "the DUT fragment's own header for the neutralization technique, "
        "sizing rationale, and what was NOT attempted (a PDK-realistic MiM "
        "capacitor, a full PVT sweep, or a hand-tuned cap value)."
    )
    a(
        f"- **Netlist provenance**: hand-authored EXPERIMENTAL variant "
        f"(`{DUT_FRAGMENT_NEUTRALIZED.relative_to(evidence.REPO_ROOT)}`), "
        "not netlisted from any design/*.sch schematic -- see that file's "
        "own header for why a hand-authored fragment is appropriate here "
        "(same convention as sim/harness-corner-smoke/testbench/*.spice)."
    )
    a(
        f"- **Corner matrix run**: process=['{corner}'], temperature_c=[{temp_c}], "
        f"supply_v=[{VDD}] (1 PVT point -- **subset-corner justification**: "
        "first-pass, nominal-corner-only mitigation-class scoping "
        "measurement, matching #390's own single-corner scope so the two "
        "are directly comparable; a PVT sweep is out of scope here and "
        "would only be warranted if this class were adopted)"
    )
    a(
        f"- **Stimulus**: identical to "
        f"`sim/comparator-decision/records/{BASELINE_RECORD_390}.md` -- "
        f"{KICKBACK_RSRC_OHM:g}Ohm series source impedance on each of "
        f"VINP/VINN (ideal DC source -> resistor -> DUT pin); single "
        f"reset({RESET_NS}ns, CLK=0)->evaluate(CLK={VDD}V) edge per run "
        f"over a {KICKBACK_EVALUATE_NS:g}ns evaluate window; Vcm={VCM}V; "
        "same Vindiff grid (0mV symmetry control, half-LSB, and +50mV "
        "large-overdrive), same common-mode/differential decomposition "
        "method. Only the DUT netlist differs."
    )
    if note:
        a(f"- **Note**: {note}")
    a(
        f"- **Overall**: measured (informational, see Claim above) -- "
        f"worst-case peak pin disturbance across the {len(points)} Vindiff "
        f"point(s) run: {worst_abs_v * 1000:.4f} mV (at "
        f"Vindiff={worst.vindiff_mv:+.4f}mV), vs. "
        f"{abs(BASELINE_390_PEAK_NEG_MV):.4f} mV in the unmitigated baseline "
        f"({peak_delta_pct:+.1f}% -- a positive number is WORSE, since this "
        "is a peak-magnitude comparison). Decomposed (same method as #390): "
        f"worst-case peak COMMON-MODE deviation {worst_cm.peak_cm_dev_v * 1000:+.4f} mV "
        f"(at Vindiff={worst_cm.vindiff_mv:+.4f}mV, "
        f"t={worst_cm.peak_cm_time_ns:.3f}ns) -- this mitigation class targets "
        "the differential component (DR-014 (c)), not the common-mode one, so "
        "little change here is expected. Worst-case peak DIFFERENTIAL "
        f"deviation (excluding the Vindiff=0mV symmetry control, same "
        f"caveat as the baseline): {worst_diff.peak_diff_dev_v * 1000:+.4f} mV "
        f"(at Vindiff={worst_diff.vindiff_mv:+.4f}mV, "
        f"t={worst_diff.peak_diff_time_ns:.3f}ns), vs. "
        f"{BASELINE_390_DIFF_NEG_50MV_MV:.4f} mV in the baseline at the "
        f"same Vindiff=+50mV point ({diff_delta_pct:+.1f}%)."
    )
    a("")
    a("## Measured value(s)")
    a("")
    a(
        "| Vindiff (mV) | peak+ (mV) | pin / time (ns) | peak- (mV) | "
        "pin / time (ns) | CM+ (mV) @ t (ns) | CM- (mV) @ t (ns) | "
        "diff+ (mV) @ t (ns) | diff- (mV) @ t (ns) |"
    )
    a("|---|---|---|---|---|---|---|---|---|")

    def _at(dev_v: float | None, time_ns: float | None) -> str:
        if dev_v is None:
            return "n/a"
        when = f"{time_ns:.3f}" if time_ns is not None else "n/a"
        return f"{dev_v * 1000:+.4f} @ {when}"

    for p in sorted(points, key=lambda p: p.vindiff_mv):
        pos_ns = f"{p.peak_pos_time_ns:.3f}" if p.peak_pos_time_ns is not None else "n/a"
        neg_ns = f"{p.peak_neg_time_ns:.3f}" if p.peak_neg_time_ns is not None else "n/a"
        a(
            f"| {p.vindiff_mv:+.4f} | {p.peak_pos_dev_v * 1000:+.4f} | "
            f"{p.peak_pos_pin} @ {pos_ns} | {p.peak_neg_dev_v * 1000:+.4f} | "
            f"{p.peak_neg_pin} @ {neg_ns} | "
            f"{_at(p.peak_cm_pos_dev_v, p.peak_cm_pos_time_ns)} | "
            f"{_at(p.peak_cm_neg_dev_v, p.peak_cm_neg_time_ns)} | "
            f"{_at(p.peak_diff_pos_dev_v, p.peak_diff_pos_time_ns)} | "
            f"{_at(p.peak_diff_neg_dev_v, p.peak_diff_neg_time_ns)} |"
        )
    a("")
    a(
        "Column definitions are unchanged from #390's baseline record -- see "
        f"`sim/comparator-decision/records/{BASELINE_RECORD_390}.md` for the "
        "full derivation and rationale of the peak+/peak-/CM/diff columns "
        "and the both-signs convention. Repeated verbatim here only where "
        "the comparison below depends on it."
    )
    a("")
    if half_lsb is not None:
        a(
            f"**Half-LSB point (Vindiff=+{0.5 * DIFFERENTIAL_LSB_MV:.4f}mV), "
            "the SAR-relevant overdrive the baseline record singles out**: "
            f"measured differential deviations here are "
            f"{half_lsb.peak_diff_pos_dev_v * 1000:+.4f} mV / "
            f"{half_lsb.peak_diff_neg_dev_v * 1000:+.4f} mV, vs. "
            f"{BASELINE_390_DIFF_POS_HALFLSB_MV:+.4f} mV in the unmitigated "
            "baseline at the same point."
        )
        a("")
    a(
        "**What this comparison does and does not show.** Both this "
        "record's DUT and the baseline's run the identical stimulus and "
        "decomposition, so a like-for-like reading of the table above "
        "against the baseline record's own table is valid without further "
        "normalization. It does NOT by itself establish that neutralization "
        "is (or is not) a viable mitigation class in general -- only that "
        "THIS sizing, at THIS one PVT point, produces the comparison stated "
        "in Overall above. A decision record weighing whether this class "
        "closes DR-014's gap is the next step (see DR-014's Open items and "
        "this record's own citation trail), not a conclusion this testbench "
        "draws for itself."
    )
    a("")
    a("### Recovery pick-offs")
    a("")
    a(
        "Same method as the baseline record: both decomposed series, "
        "re-read at one or more later instants. NOT the in-loop "
        "residual-at-next-decision measurable DR-011's Open items name."
    )
    a("")
    a("| Vindiff (mV) | pick-off | t (ns) | CM deviation (mV) | differential deviation (mV) |")
    a("|---|---|---|---|---|")
    for p in sorted(points, key=lambda p: p.vindiff_mv):
        for r in p.recovery:
            a(
                f"| {p.vindiff_mv:+.4f} | {r.label} | {r.time_ns:.3f} | "
                f"{r.cm_dev_v * 1000:+.4f} | {r.diff_dev_v * 1000:+.4f} |"
            )
    a("")
    a(
        "No spec/target-spec.md line is added, edited, relaxed, or graded "
        "against by this record -- see Claim above. This record measures an "
        "EXPERIMENTAL, unadopted DUT variant; it does not itself decide "
        "whether cross-coupled neutralization is worth adopting -- that "
        "weighing, against this measurement and any sibling measurements of "
        "the other headroom-neutral classes DR-014 (c) names, belongs in a "
        "follow-on decision record (issue #434)."
    )
    a("")
    a(
        "- **Data provenance**: model-card-monte-carlo (sky130A BSIM4 "
        "compact device models via ngspice transient analysis for the 11 "
        "sky130_fd_pr__{n,p}fet_01v8 devices; the two added neutralization "
        "capacitors are IDEALIZED SPICE capacitor primitives, not a PDK "
        "device model -- see the DUT fragment's header. No literature/"
        "foundry-doc figure used, and no measured value from "
        "`2AMLogic/sky130-comparator` transferred, per CLAUDE.md's "
        "clean-room policy)"
    )
    a("")
    return _finalize_record(
        lines, record_path, prov.pdk_line, prov.ng_version, prov.netlist_sha,
        "kickback-neutralized", supersedes=supersedes,
    )


# ---------------------------------------------------------------------------
# regen-corners: decision (regeneration) delay over the full ratified OAT
# PVT grid -- the comparator half of the bit-trial timing budget
# ---------------------------------------------------------------------------
#
# WHY THIS EXISTS. docs/chipalooza/challenge-4-proposal.md Section 7 Item 2
# names the two mechanisms that must be quantified before the DRAFT
# 100 kS/s-1 MS/s sample-rate row can be re-derived from evidence rather
# than asserted: (a) the CDAC array's own bottom-plate-switch settling, and
# (b) the comparator's own decision (regeneration) delay. (a) was quantified
# at one corner by sim/cdac-bit-trial-settling/ (issue #121, PR #156). (b)
# had exactly one committed data point -- the single-corner
# `regen` record 20260821-065653-433a294 (tt/27C/1.8V, issue #54) -- whose
# own text defers "a full PVT sweep of this same Vindiff grid ... to #28's
# corner campaign". #28's campaign covered the NOISE row only
# (`noise-corners`); the regeneration-time sweep was never taken to the full
# corner set. This subcommand closes that specific gap: it is to `regen`
# exactly what `noise-corners` is to `noise`.
#
# WHY IT NEEDS ITS OWN CONSTANTS RATHER THAN REUSING `regen`'s.
#  * Vindiff grid. `regen`'s 8-point grid spans 0.5-50 mV to SHOW THE SHAPE
#    of regeneration time vs. input (the ln(1/Vindiff) latch behaviour). A
#    PVT campaign does not need the shape re-measured at nine corners; it
#    needs the WORST CASE and enough of the trend to confirm the shape did
#    not invert somewhere on the grid. Three points do that at 1/3 the cost:
#    0.5 mV (a deliberately harder input than this converter ever has to
#    resolve -- see below), the half-LSB point, and 10 mV.
#  * Half-LSB is the physically meaningful worst case for THIS converter.
#    The differential LSB is 2*V_REF/2^N = 3.5156 mV (DR-003 Item 3), so the
#    smallest differential a correct bit trial must resolve is half of that,
#    1.7578 mV. 0.5 mV is carried as a deliberately conservative bound: it
#    is ~3.5x smaller than the half-LSB input, so its (longer) decision
#    delay upper-bounds the delay at any input this design actually presents.
#    Inputs below half an LSB are, by construction, inside the converter's
#    own quantization band -- a wrong decision there is not a timing failure.
#  * Evaluate window. `regen` allows 40 ns for the decision to resolve. Every
#    committed data point resolves inside 1.4 ns, so 15 ns is ~10x headroom
#    over the slowest measured point while cutting each transient's cost
#    roughly in half. A point that does NOT resolve inside the window is
#    reported as UNRESOLVED and fails the subcommand -- it is never silently
#    dropped or back-filled.
#  * A Vindiff = 0 mV RESET-INTEGRITY CONTROL at every corner. This is not a
#    decision measurement -- at zero input there is no correct answer to
#    decide -- it is the negative control that tells the other three columns
#    apart from an artifact. If the outputs separate during the CLK=0 reset
#    phase with NO input applied, then whatever they do after the evaluate
#    edge is not attributable to the input, and no decision delay can be
#    extracted at that corner. Without this column a pre-decided point is
#    indistinguishable from a genuinely fast one (it reports 0.0000 ns), which
#    is exactly the kind of fabricated number CLAUDE.md's "no claim without a
#    testbench" rule exists to prevent.
CORNERS_VINDIFF_SWEEP_MV = [0.0, 0.5, 1.7578, 10.0]
CORNERS_EVALUATE_NS = 15.0

# Provisional bit-trial phase budget the measured delays are COMPARED against
# (never graded against): DR-006 derives a 1.2-12 MHz f_clk range as a
# mechanical consequence of spec/target-spec.md's DRAFT 100 kS/s-1 MS/s
# sample-rate row, one clock period per phase. The worst case (fastest clock)
# phase is therefore 1/12 MHz = 83.333 ns. Because the row upstream of it is
# DRAFT, this number is reported for context only -- it is NOT a pass/fail
# threshold, per CLAUDE.md's rule against encoding an unratified spec value
# as one. sim/cdac-bit-trial-settling/ quotes the identical figure for the
# same reason.
BIT_TRIAL_PHASE_BUDGET_NS = 1000.0 / 12.0
# Differential LSB, DR-003 Item 3: 2*V_REF/2^N with V_REF = 1.8 V, N = 10.
DIFFERENTIAL_LSB_MV = 2 * VDD / (2 ** 10) * 1000.0


@dataclass
class RegenCornerPoint:
    corner: str
    temp_c: float
    supply_v: float
    vindiff_mv: float
    regen_time_ns: float | None
    log_text: str
    pre_edge_diff_v: float | None = None
    final_diff_v: float | None = None
    reset_divergence_onset_ns: float | None = None
    reset_static_idd_a: float | None = None

    @property
    def corner_id(self) -> str:
        return corners_mod.corner_id(self.corner, self.temp_c, self.supply_v)

    @property
    def reset_held(self) -> bool | None:
        """Did the CLK=0 reset phase leave the latch balanced at the moment
        the evaluate edge began? None if the point produced no waveform."""
        if self.pre_edge_diff_v is None:
            return None
        return abs(self.pre_edge_diff_v) <= RESET_HOLD_TOLERANCE_FRAC * self.supply_v

    def classify(self) -> str:
        """One of five outcomes. The distinction between them is the whole
        point of this campaign -- collapsing RESET-NOT-HELD into a numeric
        delay is what made the first draft of this subcommand report a
        physically meaningless `0.0000 ns` at four of nine corners."""
        held = self.reset_held
        if held is None:
            return "NO-DATA"
        if not held:
            # The latch had already separated by more than the input could
            # account for BEFORE the clock edge: whatever it does afterwards
            # is not a response to the input, so no delay is extractable.
            return "RESET-NOT-HELD"
        if self.vindiff_mv == 0.0:
            return "CONTROL-OK"
        if self.regen_time_ns is not None:
            return "DECIDED"
        if (
            self.final_diff_v is not None
            and abs(self.final_diff_v) > 0.5 * self.supply_v
        ):
            # Reset held, but the latch resolved AGAINST the applied input --
            # an offset/asymmetry failure, not a timing one.
            return "WRONG-POLARITY"
        return "NO-DECISION"


def run_regen_corners(
    vindiff_sweep_mv: list[float] | None = None, quiet: bool = False,
) -> list[RegenCornerPoint]:
    """Full ratified-corner-set sweep of run_regen_sweep(): the OAT PVT grid
    built from the ratified corner set (spec/target-spec.md's "Numeric rows
    -- RATIFIED 2026-08-19" section: -40/27/125C, +-10% supply, sky130
    process corners), at CORNERS_VINDIFF_SWEEP_MV."""
    # Fail fast on an unresolvable PDK before spending the corner grid's
    # runtime -- the returned PdkInfo is unused here (run_regen_sweep()
    # re-resolves it for each point), so the call is kept, not the binding.
    pdk.resolve_or_raise()
    sweep = vindiff_sweep_mv or CORNERS_VINDIFF_SWEEP_MV
    grid = corners_mod.ratified_oat_grid(VDD, SUPPLY_TOLERANCE, PROCESS_CORNERS, TEMPS_C)
    points: list[RegenCornerPoint] = []
    for process_corner, temp_c, supply_v in grid:
        cid = corners_mod.corner_id(process_corner, temp_c, supply_v)
        if not quiet:
            print(f"{cid}:")
        sweep_points = run_regen_sweep(
            corner=process_corner, temp_c=temp_c, vindiff_sweep_mv=sweep,
            quiet=quiet, supply_v=supply_v, evaluate_ns=CORNERS_EVALUATE_NS,
            probe_supply_current=True,
        )
        for p in sweep_points:
            points.append(RegenCornerPoint(
                corner=process_corner, temp_c=temp_c, supply_v=supply_v,
                vindiff_mv=p.vindiff_mv, regen_time_ns=p.regen_time_ns,
                log_text=p.log_text,
                pre_edge_diff_v=p.pre_edge_diff_v,
                final_diff_v=p.final_diff_v,
                reset_divergence_onset_ns=p.reset_divergence_onset_ns,
                reset_static_idd_a=p.reset_static_idd_a,
            ))
    return points


def write_regen_corners_evidence(
    points: list[RegenCornerPoint], note: str = "",
    supersedes: str = "",
) -> Path:
    prov = evidence.resolve_provenance(EXPERIMENT_DIR, _dut_lines())
    record_id = prov.record_id
    record_path = prov.record_path
    corners_dir = EXPERIMENT_DIR / "corners" / record_id
    corners_dir.mkdir(parents=True, exist_ok=True)
    for p in points:
        cid = corners_mod.corner_id(p.corner, p.temp_c, p.supply_v)
        safe = f"{p.vindiff_mv}mV".replace("-", "neg").replace(".", "p")
        (corners_dir / f"{cid}__vindiff_{safe}.log").write_text(p.log_text)

    controls = [p for p in points if p.vindiff_mv == 0.0]
    measured = [p for p in points if p.vindiff_mv != 0.0]
    decided = [p for p in measured if p.classify() == "DECIDED"]
    not_held = [p for p in measured if p.classify() == "RESET-NOT-HELD"]
    failed_controls = [p for p in controls if p.classify() != "CONTROL-OK"]
    bad_corner_ids = sorted({p.corner_id for p in failed_controls})
    process_corners_run = sorted({p.corner for p in points})
    temps_run = sorted({p.temp_c for p in points})
    supplies_run = sorted({p.supply_v for p in points})
    n_corner_points = len({(p.corner, p.temp_c, p.supply_v) for p in points})
    n_corners = len(controls)
    clean_corner_ids = sorted({p.corner_id for p in controls if p.classify() == "CONTROL-OK"})

    lines: list[str] = []
    a = lines.append
    a(f"# Record {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    a(
        "- **Claim**: pending #1/#27 -- attempts to characterize "
        "design/comparator.sch's decision (regeneration) delay vs. differential "
        "input across the FULL ratified PVT corner set, and reports what that "
        "attempt actually found. There is no ratified spec/target-spec.md row "
        "for decision delay, settling, or sample rate to grade against (the "
        "100 kS/s-1 MS/s sample-rate row is still DRAFT, #1/#27), so nothing "
        "here asserts a pass against a ratified line. Extends the single-corner "
        "record `20260821-065653-433a294` (tt/27C/1.8V, issue #54), whose own "
        "text deferred this sweep, and is the comparator counterpart of the "
        "CDAC-side settling budget "
        "`sim/cdac-bit-trial-settling/records/20260905-220919-bbf06dd.md` -- "
        "together they are the two mechanisms "
        "`docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2 names."
    )
    a(f"- **Netlist provenance**: schematic (`{DUT_FRAGMENT.relative_to(evidence.REPO_ROOT)}`)")
    a(
        corners_mod.corner_matrix_summary_line(
            process_corners_run, temps_run, supplies_run, n_corner_points
        )
    )
    a(
        f"- **Vindiff grid**: {CORNERS_VINDIFF_SWEEP_MV} mV at every corner point "
        f"({len(points)} transient runs total). The differential LSB is "
        f"{DIFFERENTIAL_LSB_MV:.4f} mV (DR-003 Item 3), so the half-LSB point -- "
        "the smallest differential a correct bit trial must resolve -- is "
        f"{DIFFERENTIAL_LSB_MV / 2:.4f} mV; the 0.5 mV point is a deliberately "
        "conservative bound ~3.5x below it, and 10 mV is a large-overdrive "
        "reference. The 0.0 mV column is not a decision measurement at all: it "
        "is the reset-integrity NEGATIVE CONTROL described below."
    )
    a(
        f"- **Stimulus**: single reset({RESET_NS}ns, CLK=0)->evaluate(CLK=supply) "
        "edge per run (not a repeating clock -- each ngspice invocation starts "
        "from an uninitialized circuit); decision threshold |v(outp)-v(outn)| > "
        "0.5*supply; Vcm = supply/2, tracking the rail because V_REF = V_DD in "
        "this design (DR-003 Item 1) and the CDAC's switched common mode is "
        f"V_REF/2; evaluate window {CORNERS_EVALUATE_NS}ns"
    )
    if note:
        a(f"- **Note**: {note}")
    affected_corner_ids = sorted({p.corner_id for p in not_held} | set(bad_corner_ids))
    if failed_controls:
        a(
            f"- **Overall**: FAIL (DESIGN FINDING) -- the reset-integrity control "
            f"fails at {len(bad_corner_ids)} of {n_corners} ratified corner "
            f"points ({', '.join('`' + c + '`' for c in bad_corner_ids)}). At "
            "those corners the comparator's differential output has already "
            "separated to the rails DURING the CLK=0 reset phase with ZERO "
            "differential input applied, so the post-edge output is not a "
            "response to the input and NO decision delay is extractable there. "
            f"Counting the applied-input points too, {len(affected_corner_ids)} "
            f"of {n_corners} corner points show at least one reset-not-held "
            f"run ({len(not_held)} of {len(measured)} input-driven runs). "
            "A PVT-complete decision-delay figure therefore does not exist yet "
            "and is NOT reported by this record."
        )
    else:
        a(
            f"- **Overall**: {'PASS' if len(decided) == len(measured) else 'INCOMPLETE'} "
            f"({len(decided)}/{len(measured)} input-driven points decided within "
            f"the {CORNERS_EVALUATE_NS}ns evaluate window; "
            f"{n_corners}/{n_corners} reset-integrity controls held)"
        )
    if decided:
        binding = max(decided, key=lambda p: p.regen_time_ns or 0.0)
        a(
            f"- **Binding corner (among the {len(clean_corner_ids)} corner points "
            f"whose reset control held)**: `{binding.corner_id}` at Vindiff = "
            f"{binding.vindiff_mv:+.4f} mV, decision delay "
            f"{binding.regen_time_ns:.4f} ns -- recorded regardless of pass/fail, "
            "per sim/README.md's per-row binding-corner convention. This is a "
            "worst case over a SUBSET of the ratified grid, not over the grid, "
            "and must not be quoted as a PVT-complete number."
        )
    a("")

    a("## Reset-integrity control (Vindiff = 0 mV): does the reset phase hold?")
    a("")
    a(
        "With no differential input applied there is no correct decision to "
        "make, so the latch must remain balanced until the evaluate edge. "
        "`pre-edge diff` is v(OUTP) - v(OUTN) at the last sample strictly "
        f"before the CLK edge begins rising (t = {RESET_NS} ns); `onset` is the "
        "first time during the reset phase at which |v(OUTP) - v(OUTN)| exceeded "
        f"{RESET_HOLD_TOLERANCE_FRAC:.0%} of the rail; `reset I(VDD)` is the "
        "static supply current at that same pre-edge sample."
    )
    a("")
    a(
        "| corner-id | pre-edge v(OUTP)-v(OUTN) (V) | onset during reset (ns) | "
        "reset I(VDD) (uA) | verdict |"
    )
    a("|---|---|---|---|---|")
    for p in controls:
        onset = (
            f"{p.reset_divergence_onset_ns:.3f}"
            if p.reset_divergence_onset_ns is not None else "-- (never)"
        )
        idd = (
            f"{abs(p.reset_static_idd_a) * 1e6:.2f}"
            if p.reset_static_idd_a is not None else "n/a"
        )
        verdict = "HELD" if p.classify() == "CONTROL-OK" else "**NOT HELD**"
        pre = f"{p.pre_edge_diff_v:+.4f}" if p.pre_edge_diff_v is not None else "n/a"
        a(f"| `{p.corner_id}` | {pre} | {onset} | {idd} | {verdict} |")
    a("")

    a("## Decision outcome per corner and differential input")
    a("")
    a(
        "Cells are the measured decision delay in ns where one exists. Where "
        "one does not, the cell names WHY rather than substituting a number:"
    )
    a("")
    a(
        "- `RESET-NOT-HELD` -- the outputs had already separated by more than "
        f"{RESET_HOLD_TOLERANCE_FRAC:.0%} of the rail before the evaluate edge. "
        "Any apparent delay here would be an artifact (a naive threshold-crossing "
        "search reports 0.0000 ns for exactly these points), so no number is given."
    )
    a(
        "- `WRONG-POLARITY` -- the reset held, but the latch resolved AGAINST the "
        "applied differential. That is an offset/asymmetry failure, not a timing "
        "one, and a decision delay is not meaningful for it."
    )
    a(
        "- `NO-DECISION` -- the reset held and the latch never crossed the "
        f"decision threshold within the {CORNERS_EVALUATE_NS} ns evaluate window."
    )
    a("")
    delay_cols = [v for v in CORNERS_VINDIFF_SWEEP_MV if v != 0.0]
    a(
        "| corner-id | "
        + " | ".join(f"Vindiff {v:+.4f} mV" for v in delay_cols)
        + " |"
    )
    a("|---" * (1 + len(delay_cols)) + "|")
    by_corner: dict[str, dict[float, RegenCornerPoint]] = {}
    order: list[str] = []
    for p in measured:
        if p.corner_id not in by_corner:
            by_corner[p.corner_id] = {}
            order.append(p.corner_id)
        by_corner[p.corner_id][p.vindiff_mv] = p
    for cid in order:
        cells = []
        for v in delay_cols:
            p = by_corner[cid].get(v)
            if p is None:
                cells.append("n/a")
            elif p.classify() == "DECIDED":
                cells.append(f"{p.regen_time_ns:.4f}")
            else:
                cells.append(p.classify())
        a(f"| `{cid}` | " + " | ".join(cells) + " |")
    a("")

    a("## What this means")
    a("")
    if failed_controls:
        worst_control = min(
            (p for p in failed_controls if p.reset_divergence_onset_ns is not None),
            key=lambda p: p.reset_divergence_onset_ns,
            default=None,
        )
        a(
            f"**The intended measurement could not be completed, and this record "
            f"says so instead of reporting the {len(decided)} delays it did obtain "
            "as if they covered the grid.** The reset-integrity control above "
            f"fails at {len(bad_corner_ids)} of {n_corners} ratified corner points "
            "with the inputs shorted to the common mode. A latch that separates "
            "to the rails before its clock edge, with no input, has not been "
            "reset; its subsequent output carries no information about the input."
        )
        a("")
        if worst_control is not None:
            a(
                f"Earliest observed divergence: `{worst_control.corner_id}` at "
                f"t = {worst_control.reset_divergence_onset_ns:.3f} ns into a "
                f"{RESET_NS} ns reset phase, reaching "
                f"{worst_control.pre_edge_diff_v:+.4f} V by the evaluate edge."
            )
            a("")
        a(
            "**Mechanism, read off this same data rather than assumed.** In "
            "`design/comparator.sch` the cross-coupled NMOS pair (`XM_LATN_P` / "
            "`XM_LATN_N`) has both sources tied directly to GND, so it is "
            "conducting throughout the CLK=0 reset phase, in opposition to the "
            "reset PMOS pair (`XM_RST_P` / `XM_RST_N`, W=16). Two independent "
            "measurements in the control table above are consequences of that "
            "and of nothing else:"
        )
        a("")
        a(
            "1. The reset-phase output level is NOT the rail. A precharge that "
            "won would sit at v(OUTP) = v(OUTN) = VDD; the reset-phase static "
            "supply current column is non-zero precisely because a DC path "
            "VDD -> reset PMOS -> output node -> latch NMOS -> GND is open the "
            "whole time."
        )
        a(
            "2. That balanced level is an UNSTABLE equilibrium, not a resting "
            "state. Both latch NMOS devices sit well above threshold there, so "
            "the cross-coupled loop gain exceeds unity and any asymmetry -- "
            "process skew between the NMOS and PMOS corners, temperature, or "
            "the input pair's own subthreshold conduction -- is amplified to "
            "the rails within the reset window. The corners where the control "
            "fails are the skewed and cold ones, which is the signature of an "
            "amplified asymmetry rather than of a slow settle."
        )
        a("")

        # A corner can pass the zero-input control and still fail with an
        # input applied -- worth naming explicitly, because the two counts
        # otherwise look inconsistent between the control table and the
        # decision table above.
        control_ok_ids = {
            p.corner_id for p in controls if p.classify() == "CONTROL-OK"
        }
        sneaky = sorted({
            p.corner_id for p in not_held if p.corner_id in control_ok_ids
        })
        if sneaky:
            at_t0 = [
                p for p in not_held
                if p.corner_id in control_ok_ids
                and p.reset_divergence_onset_ns == 0.0
            ]
            plural = "corner point passes" if len(sneaky) == 1 else "corner points pass"
            a(
                f"**A held control is necessary, not sufficient.** "
                f"{len(sneaky)} {plural} the Vindiff = 0 mV control "
                f"yet still fail with an input applied "
                f"({', '.join('`' + c + '`' for c in sneaky)}) -- which is why "
                "the control table and the decision table above do not report "
                "the same count."
            )
            if at_t0:
                worst = min(at_t0, key=lambda p: p.pre_edge_diff_v or 0.0)
                a("")
                a(
                    "At those points the divergence onset is t = 0.000 ns: the "
                    "separation is present in the very first transient sample, "
                    "so it is not something the reset phase failed to suppress "
                    "over time -- the reset phase's own DC operating point, the "
                    "solution ngspice starts the transient from before any clock "
                    "edge exists, is ALREADY a decided state. A bistable "
                    "operating point is the same defect seen from the DC side "
                    "rather than the transient side, and it is resolved by the "
                    "solver rather than by the circuit. Worst case here: "
                    f"`{worst.corner_id}` with {worst.vindiff_mv:+.4f} mV "
                    f"applied starts the evaluate phase at "
                    f"{worst.pre_edge_diff_v:+.4f} V -- committed AGAINST the "
                    "applied input."
                )
            a("")
        a(
            "**Consequence for the ADC, stated plainly.** This is a functional "
            "finding, not only a timing one: at the affected corners the "
            "comparator enters each bit trial already committed to an output, "
            "so the bit it produces is not determined by the charge on the CDAC "
            "top plate. No ADC-level transient simulation in this repository has "
            "exercised the real comparator inside the full hierarchy yet (the "
            "sequencer campaign is behavioural and the ENOB estimate composes a "
            "noise term rather than simulating the latch), which is why this had "
            "not previously surfaced."
        )
        a("")
        a(
            "**Not fixed here, by design.** Repairing this means changing "
            "`design/comparator.sch` (the textbook remedy is to stop the NMOS "
            "latch conducting during reset -- e.g. return its sources to a "
            "clocked internal node rather than hard-wiring them to GND), which "
            "is a topology change: it needs its own decision record amending "
            "DR-004, a re-netlist, and re-running every committed "
            "comparator-decision record (offset, noise, noise-corners) against "
            "the new device set. That is deliberately out of this record's "
            "scope; this record's job is to establish, with a negative control, "
            "that the problem is real and to say exactly which corners show it."
        )
    else:
        binding = max(decided, key=lambda p: p.regen_time_ns or 0.0) if decided else None
        if binding is not None:
            a(
                f"**Context, not a graded verdict**: the worst decision delay "
                f"({binding.regen_time_ns:.4f} ns) is "
                f"{BIT_TRIAL_PHASE_BUDGET_NS / (binding.regen_time_ns or 1):.1f}x "
                f"inside DR-006's provisional worst-case (12 MHz) bit-trial phase "
                f"budget of {BIT_TRIAL_PHASE_BUDGET_NS:.3f} ns. That budget is a "
                "mechanical consequence of spec/target-spec.md's DRAFT "
                "sample-rate row, not a ratified number, so this is headroom "
                "against a provisional figure and NOT a pass against a spec line."
            )
            a("")
        a(
            "Expected shape: decision delay grows roughly as "
            "`ln(V_decided/Vindiff)` (standard positive-feedback latch "
            "behaviour) as Vindiff shrinks, and grows with slower process / "
            "lower supply. Both trends are checkable row-by-row above."
        )
    a("")
    a(
        "**Scope limits, stated rather than implied.** This exercises the "
        "comparator core in isolation, driven by ideal DC differential sources: "
        "it excludes the CDAC array's own settling (measured separately, "
        "`sim/cdac-bit-trial-settling/`), the SAR sequencer's logic delay, the "
        "sampling front end's acquisition, and any load the real top-plate "
        "network presents to the comparator inputs. It is one term of a "
        "bit-trial timing budget, not the budget. It is also a nominal-device "
        "run: no Monte Carlo mismatch is applied, so the reset-phase asymmetry "
        "reported above is the corner-model asymmetry alone -- per-device "
        "mismatch would only add to it."
    )
    a("")
    return _finalize_record(
        lines, record_path, prov.pdk_line, prov.ng_version, prov.netlist_sha,
        "regen-corners", supersedes=supersedes,
    )


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
# Instead this uses a REDUCED sub-model: the tail + input pair, with the
# devices on the input pair's own drain nodes DIODE-CONNECTED (self-biased)
# so the stage finds its own DC bias point without an external bias-voltage
# guess, and with the positive-feedback cross-coupling removed. This is a
# standard "break the loop for small-signal analysis" technique (generic
# circuit-analysis practice, not specific to any implementation).
#
# ISSUE #175 / DR-004 AMENDMENT A -- WHICH DEVICES THE SUB-MODEL KEEPS, AND
# WHY THAT CHANGED WITH THE TOPOLOGY.
#
# The selection rule, stated once so it can be checked rather than trusted:
# model the phase in which a StrongARM latch's input-referred noise is
# actually generated -- the INTEGRATION phase, from the evaluate edge until
# the latch NMOS pair turns on. During that phase the tail is on and the
# input pair is in saturation, converting Vindiff into the differential
# current that discharges the DIP/DIN nodes; every other device is off (the
# latch NMOS pair sits at Vgs = v(OUT) - v(DI) ~ 0 because both nodes are
# still precharged, the latch PMOS pair likewise, and all four reset PMOS are
# off at CLK = VDD). So the sub-model keeps the tail + input pair and, purely
# to give the DIP/DIN nodes a DC bias that a `.op`-based `.noise` analysis
# needs at all, diode-connects the one VDD-side device already attached to
# each of those nodes -- the DI-node precharge PMOS (XM_RST_DIP/XM_RST_DIN).
#
# Before #175 that same rule selected the cross-coupled latch pair itself,
# because the input pair's drains WERE the OUTP/OUTN nodes and those devices
# were what sat on them. The amendment moved the input-pair drains onto
# DIP/DIN, so the rule now selects the DI-node precharge devices. The
# methodology is unchanged; the device list it picks out changed because the
# netlist did.
#
# TWO ALTERNATIVES WERE MEASURED AND REJECTED (both at tt/27C/1.8V, so the
# rejection is checkable rather than asserted):
#
#  * A LITERAL loop-break of all nine core devices -- keep the latch pairs,
#    diode-connect them in place, leave them in series between OUTP/OUTN and
#    DIP/DIN. This is well-defined but DISQUALIFIED BY ITS OWN OPERATING
#    POINT, not by its answer: the amended stack is four devices tall
#    (VDD -> diode PMOS -> OUT -> diode NMOS -> DI -> input NMOS -> TAIL ->
#    tail NMOS -> GND), which does not fit in 1.8 V, so the whole network
#    settles subthreshold -- v(TAIL) = 4.4 mV, v(DIP) = 21.9 mV, i.e. the
#    input pair is off rather than saturated. Its 8.6921 mV rms single-ended
#    result describes a bias point the comparator never occupies.
#  * The same literal loop-break PLUS diode-connected DI precharge devices to
#    restore the bias (all eleven devices). This DOES bias sensibly
#    (v(TAIL) = 28.7 mV, v(DIP) = 383.1 mV -- the input pair saturated,
#    matching the model actually used) and gives 1.0867 mV rms single-ended.
#    It is rejected on the selection rule above rather than on that number:
#    it forces the latch NMOS pair to CONDUCT, which is exactly what they do
#    not do during integration, so its extra noise term is not "the
#    regenerative contribution measured properly" -- it is a different
#    artifact, and a larger departure from the modelled phase than the
#    omission it purports to fix. The genuine regenerative-noise gap stays
#    open, named in DR-004's Open items exactly as before.
#
# Recording the rejected numbers here is deliberate: the model this file uses
# yields a SMALLER figure than one of the alternatives, so the reason for the
# choice must be inspectable. It is the operating-point/phase argument above,
# and it would have selected the same model had the numbers come out the
# other way round.
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
    "reduced sub-model of the INTEGRATION phase (DR-004 Amendment A, issue "
    "#175): tail + input pair, with the DI-node precharge PMOS pair "
    "diode-connected (self-biased) as the loads on the input pair's own drain "
    "nodes DIP/DIN, and the cross-coupled latch pairs omitted because they are "
    "off (Vgs ~ 0) until regeneration begins; CLK held at VDD (steady evaluate "
    "bias, tail on); noise taken at v(DIP,DIN)"
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
        "XM_INN DIP VINN TAIL GND sky130_fd_pr__nfet_01v8 L=0.5 W=4 nf=1",
        "XM_INP DIN VINP TAIL GND sky130_fd_pr__nfet_01v8 L=0.5 W=4 nf=1",
        "XM_RST_DIP DIP DIP VDD VDD sky130_fd_pr__pfet_01v8 L=0.5 W=4 nf=1",
        "XM_RST_DIN DIN DIN VDD VDD sky130_fd_pr__pfet_01v8 L=0.5 W=4 nf=1",
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
        "print v(TAIL) v(DIP) v(DIN)",
        f"noise v(dip,din) Vinp dec 20 {NOISE_FSTART_HZ:g} {NOISE_FSTOP_HZ:g} 20",
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
    # The sub-model's own output nodes. Before DR-004 Amendment A (issue #175)
    # the input pair's drains were OUTP/OUTN; the amendment moved them to the
    # internal nodes DIP/DIN, which are what this deck now biases, probes and
    # takes `noise v(dip,din)` across.
    op_dip_v: float
    op_din_v: float
    log_text: str
    corner: str
    temp_c: float
    supply_v: float = VDD


def run_noise(
    corner: str = "tt", temp_c: float = 27.0, supply_v: float = VDD, quiet: bool = False,
) -> NoiseResult:
    info = pdk.resolve_or_raise()
    with tempfile.TemporaryDirectory(prefix="comparator-decision-noise-") as scratch:
        scratch_dir = Path(scratch)
        log_name = "noise"
        deck = _noise_deck(info, corner, temp_c, supply_v)
        log_text = _run(deck, scratch_dir, log_name)

    parsed = measure.parse(log_text, ["inoise_total", "onoise_total", "v(tail)", "v(dip)", "v(din)"])
    # ngspice's `print` echoes lowercased vector names for v(...) forms;
    # measure.parse's regex requires the LHS to look like an identifier
    # (letters/digits/underscore), which `v(tail)` does not match (parens)
    # -- so parse those three directly here instead of relying on
    # measure.parse for them.
    op_tail = op_dip = op_din = float("nan")
    for line in log_text.splitlines():
        s = line.strip()
        if s.startswith("v(tail)"):
            op_tail = float(s.split("=")[1])
        elif s.startswith("v(dip)"):
            op_dip = float(s.split("=")[1])
        elif s.startswith("v(din)"):
            op_din = float(s.split("=")[1])
    single_ended = parsed.get("inoise_total", float("nan"))
    differential = single_ended * (2 ** 0.5)
    if not quiet:
        print(f"  op: TAIL={op_tail:.4f}V DIP={op_dip:.4f}V DIN={op_din:.4f}V")
        print(f"  inoise_total (single-ended) = {single_ended * 1000:.4f} mV rms")
        print(f"  differential estimate (x sqrt(2)) = {differential * 1000:.4f} mV rms")
    result = NoiseResult(
        single_ended_rms_v=single_ended, differential_rms_v=differential,
        op_tail_v=op_tail, op_dip_v=op_dip, op_din_v=op_din,
        log_text=log_text, corner=corner, temp_c=temp_c, supply_v=supply_v,
    )
    return result


def run_noise_corners(quiet: bool = False) -> list[NoiseResult]:
    """Full ratified-corner-set sweep of run_noise() (issue #28): the OAT PVT
    grid built from the ratified corner set (spec/target-spec.md's "Numeric
    rows -- RATIFIED 2026-08-19" section: -40/27/125C, +-10% supply, sky130
    process corners), substantiating the ratified comparator input-referred
    noise-budget row rather than the single nominal-point record alone."""
    pdk.resolve_or_raise()
    grid = corners_mod.ratified_oat_grid(VDD, SUPPLY_TOLERANCE, PROCESS_CORNERS, TEMPS_C)
    results: list[NoiseResult] = []
    for process_corner, temp_c, supply_v in grid:
        result = run_noise(corner=process_corner, temp_c=temp_c, supply_v=supply_v, quiet=quiet)
        results.append(result)
        if not quiet:
            cid = corners_mod.corner_id(process_corner, temp_c, supply_v)
            print(f"  {cid}: differential noise = {result.differential_rms_v * 1000:.4f} mV rms")
    return results


def write_noise_campaign_evidence(
    results: list[NoiseResult], note: str = "",
    supersedes: str = "",
) -> Path:
    info = pdk.resolve()
    netlist_text = _noise_deck(info, "tt", 27.0, VDD)
    prov = evidence.resolve_provenance(EXPERIMENT_DIR, netlist_text)
    record_id = prov.record_id
    record_path = prov.record_path
    corners_dir = EXPERIMENT_DIR / "corners" / record_id
    corners_dir.mkdir(parents=True, exist_ok=True)
    for r in results:
        cid = corners_mod.corner_id(r.corner, r.temp_c, r.supply_v)
        (corners_dir / f"{cid}.log").write_text(r.log_text)

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
        corners_mod.corner_matrix_summary_line(
            process_corners_run, temps_run, supplies_run, len(results)
        )
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
        "for the full derivation and its limitations. The EXCLUSION is unchanged "
        "from every prior record in this experiment -- it is a standing "
        "methodology limitation, not something this corner campaign relaxes to "
        "force a pass. The DEVICE LIST implementing it did change with DR-004 "
        "Amendment A (issue #175): the sub-model's selection rule picks the "
        "VDD-side devices sitting on the input pair's own drain nodes, which the "
        "amendment moved from OUTP/OUTN to DIP/DIN. See that amendment's section "
        "A2 for the rule, and for the two alternative sub-models measured and "
        "rejected against it."
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
    return _finalize_record(
        lines, record_path, prov.pdk_line, prov.ng_version, prov.netlist_sha,
        "noise-corners", supersedes=supersedes,
    )


def write_noise_evidence(
    result: NoiseResult, note: str = "", supersedes: str = "",
) -> Path:
    info = pdk.resolve()
    netlist_text = _noise_deck(info, result.corner, result.temp_c)
    prov = evidence.resolve_provenance(EXPERIMENT_DIR, netlist_text)
    record_id = prov.record_id
    record_path = prov.record_path
    runs_dir = EXPERIMENT_DIR / "corners" / record_id
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / "noise.log").write_text(result.log_text)

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
    a(f"| Op point: v(DIP)=v(DIN) | {result.op_dip_v:.4f} V | {result.corner}/{result.temp_c}C/{VDD}V |")
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
    return _finalize_record(
        lines, record_path, prov.pdk_line, prov.ng_version, prov.netlist_sha,
        "noise", supersedes=supersedes,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="comparator-decision standalone testbench driver (issue #54)")
    ap.add_argument(
        "mode", nargs="?",
        choices=[
            "regen", "regen-corners", "offset", "noise", "noise-corners",
            "kickback", "kickback-neutralized",
        ],
        help="which characterization to run",
    )
    ap.add_argument("--check-env", action="store_true", help="check toolchain + PDK, print summary, exit")
    ap.add_argument("--corner", default="tt")
    ap.add_argument("--temp", type=float, default=27.0)
    ap.add_argument("--seed", type=int, default=1, help="offset: MC base seed")
    ap.add_argument("--n", type=int, default=16, help="offset: MC sample count")
    ap.add_argument("--record", action="store_true", help="write an evidence record under records/")
    ap.add_argument("--note", default="")
    ap.add_argument(
        "--supersedes", default="",
        help=(
            "prior <record-id> this run REPLACES for the same claim (e.g. a "
            "re-characterization after a topology change). Written into the "
            "record's **Supersedes** field, which sim/report/generate.py "
            "--check reads to detect a manifest still citing the superseded "
            "record. Omit for a record making a different claim."
        ),
    )
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
        points = run_regen_sweep(corner=args.corner, temp_c=args.temp, quiet=args.quiet)
        if args.record:
            path = write_regen_evidence(
                points, args.corner, args.temp, note=args.note,
                supersedes=args.supersedes,
            )
            print(f"wrote {path}")
        unresolved = [p for p in points if p.regen_time_ns is None]
        return 0 if not unresolved else 1

    if args.mode == "regen-corners":
        points = run_regen_corners(quiet=args.quiet)
        if args.record:
            path = write_regen_corners_evidence(
                points, note=args.note, supersedes=args.supersedes,
            )
            print(f"wrote {path}")
        problems = [p for p in points if p.classify() not in ("DECIDED", "CONTROL-OK")]
        for p in problems:
            print(f"{p.classify()}: {p.corner_id} at vindiff={p.vindiff_mv:+.4f}mV")
        if problems:
            print(
                f"\n{len(problems)}/{len(points)} points did not yield a valid "
                "decision-delay measurement. This is a reported finding, not a "
                "harness error -- see the record's 'What this means' section."
            )
        return 0 if not problems else 1

    if args.mode == "offset":
        result = run_offset_mc(
            corner=args.corner, temp_c=args.temp, seed=args.seed, n=args.n, quiet=args.quiet
        )
        if args.record:
            path = write_offset_evidence(
                result, note=args.note, supersedes=args.supersedes,
            )
            print(f"wrote {path}")
        negctrl_stdev = statistics.pstdev(result.negctrl_offset_v) if len(result.negctrl_offset_v) > 1 else 0.0
        draws_stdev = statistics.pstdev(result.draws_offset_v) if len(result.draws_offset_v) > 1 else 0.0
        return 0 if (negctrl_stdev == 0.0 and draws_stdev > 0) else 1

    if args.mode == "noise":
        result = run_noise(corner=args.corner, temp_c=args.temp, quiet=args.quiet)
        if args.record:
            path = write_noise_evidence(
                result, note=args.note, supersedes=args.supersedes,
            )
            print(f"wrote {path}")
        return 0

    if args.mode == "noise-corners":
        results = run_noise_corners(quiet=args.quiet)
        if args.record:
            path = write_noise_campaign_evidence(
                results, note=args.note, supersedes=args.supersedes,
            )
            print(f"wrote {path}")
        binding = max(results, key=lambda r: r.differential_rms_v)
        return 0 if binding.differential_rms_v <= NOISE_BUDGET_BASELINE_V else 1

    if args.mode == "kickback":
        points = run_kickback_sweep(corner=args.corner, temp_c=args.temp, quiet=args.quiet)
        if args.record:
            path = write_kickback_evidence(
                points, args.corner, args.temp, note=args.note,
                supersedes=args.supersedes,
            )
            print(f"wrote {path}")
        # Informational only (no ratified/DRAFT spec/target-spec.md Kickback
        # row to grade against -- see write_kickback_evidence()'s Claim
        # field) -- always succeeds if the sweep itself completed.
        return 0

    if args.mode == "kickback-neutralized":
        points = run_kickback_sweep(
            corner=args.corner, temp_c=args.temp, quiet=args.quiet,
            dut_fragment=DUT_FRAGMENT_NEUTRALIZED,
        )
        if args.record:
            path = write_kickback_neutralized_evidence(
                points, args.corner, args.temp, note=args.note,
                supersedes=args.supersedes,
            )
            print(f"wrote {path}")
        # Informational only, same as `kickback` -- see
        # write_kickback_neutralized_evidence()'s Claim field.
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""kickback neutralized campaign for the comparator-decision driver (issue #613 split of run.py)."""
from __future__ import annotations

from pathlib import Path

from .common import (
    DUT_FRAGMENT_NEUTRALIZED,
    EXPERIMENT_DIR,
    RESET_NS,
    VCM,
    VDD,
    _dut_lines,
)
from .kickback import (
    KICKBACK_EVALUATE_NS,
    KICKBACK_RSRC_OHM,
    KickbackPoint,
)
from .regen import (
    _finalize_record,
)
from .regen_corners import (
    DIFFERENTIAL_LSB_MV,
)
from harness import evidence

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
    raw_logs: dict[str, str] = {}
    for p in points:
        safe = f"{p.vindiff_mv}mV".replace("-", "neg").replace(".", "p")
        raw_logs[f"kickback_neutralized_{safe}.log"] = p.log_text
    prov, lines = evidence.open_record(EXPERIMENT_DIR, dut_text, "corners", raw_logs)
    record_path = prov.record_path
    a = lines.append

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

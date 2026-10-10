"""kickback campaign for the comparator-decision driver (issue #613 split of run.py)."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from .common import (
    DUT_FRAGMENT,
    EXPERIMENT_DIR,
    RESET_NS,
    RESET_TR_NS,
    VCM,
    VDD,
    _dut_lines,
    _run,
)
from .regen import (
    EVALUATE_NS,
    _finalize_record,
)
from .regen_corners import (
    DIFFERENTIAL_LSB_MV,
)
from harness import evidence, pdk, toolchain

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
    raw_logs: dict[str, str] = {}
    for p in points:
        safe = f"{p.vindiff_mv}mV".replace("-", "neg").replace(".", "p")
        raw_logs[f"kickback_{safe}.log"] = p.log_text
    prov, lines = evidence.open_record(EXPERIMENT_DIR, _dut_lines(), "corners", raw_logs)
    record_path = prov.record_path
    a = lines.append

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

"""offset bisect campaign for the comparator-decision driver (issue #613 split of run.py)."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .common import (
    DUT_FRAGMENT,
    RESET_NS,
    RESET_TR_NS,
    VDD,
)
from .regen import (
    RESET_HOLD_TOLERANCE_FRAC,
    _regen_deck,
)
from .regen_corners import (
    DIFFERENTIAL_LSB_MV,
)
from harness import corners as corners_mod, pdk, toolchain

# ---------------------------------------------------------------------------
# offset-bisect: decision-boundary bisection over Vindiff -- separates a
# SYSTEMATIC DECISION OFFSET from a genuine NON-DECISION (dead) BAND
# (issue #515)
#
# WHY THIS EXISTS, AND WHAT IT IS NOT.
#
# `offset` above reports ONE number per draw: a linearized pick-off statistic
# at t = evaluate_start + PICKOFF_NS, divided by a gain fitted over ideal
# Vindiff in [1, 10] mV. DR-004 Decision Sec.3 already names that method's own
# limit -- several `tt_mm` draws extrapolate to ~225 mV, far outside the range
# the calibration validates, where the pick-off relationship is compressive
# rather than linear -- and DR-004's Open items name two escalations
# ("narrow PICKOFF_NS further" / "fit the calibration curve nonlinearly").
# This subcommand takes NEITHER of those. It changes the question instead:
# rather than inferring an input-referred voltage from an early-time output
# amplitude, it measures WHERE THE DECISION ITSELF CHANGES ANSWER, by
# bisecting the two boundaries of the Vindiff axis directly. A boundary in
# Vindiff is a decision-referred quantity with no calibration curve in it at
# all, so it has no linear-regime validity range to fall outside of.
#
# It does NOT replace `offset`, and nothing here supersedes
# `records/20260821-071918-433a294`. The two measure different things:
#
#   * `offset` measures the RANDOM / mismatch-driven spread (corner `tt_mm`,
#     N draws at Vindiff = 0, one rndseed each). Its stdev is the sigma this
#     repo already characterizes.
#   * `offset-bisect` measures the SYSTEMATIC / deterministic term (plain
#     corner, mismatch DISABLED, Vindiff swept): the per-corner boundary a
#     mismatch-free DUT already has before any per-device draw is applied,
#     plus whether a Vindiff interval exists that resolves on NEITHER
#     polarity. A sigma-only characterization cannot express either.
#
# THE CONFLATION THIS CLOSES (issue #515's methodology half). Everywhere else
# in this driver a decision is tested SIGN-CORRECTED against the applied
# input: `run_regen_sweep()` computes `sign * (outp - outn) > threshold` with
# `sign` taken from the input's own polarity. That test cannot distinguish
# "the latch resolved the WRONG way" from "the latch did not resolve at all"
# -- both fail it identically, and both read `UNRESOLVED`.
# `RegenCornerPoint.classify()` already fixed that for the TIMING sweep by
# re-examining `final_diff_v` and splitting out `WRONG-POLARITY`; the
# `offset` subcommand has no equivalent because it never classifies a
# decision at all. `_BisectProbe` below classifies each probe by its ABSOLUTE
# resolved polarity (`DECIDED-POS` / `DECIDED-NEG`), never relative to the
# input, and exposes `relative_outcome()` to render the same probe in
# classify()'s input-relative taxonomy -- so a record can show both views
# side by side and the reader can see which input-relative "no decision"
# cells are really wrong-polarity decisions.
#
# ALGORITHM (three phases; the shape is cross-pollinated methodology from the
# sibling canary 2AMLogic/sky130-comparator -- its issue #66 / PR #119 --
# re-derived here against THIS repo's own `_regen_deck()` stimulus and
# RESET_HOLD_TOLERANCE_FRAC primitives. No netlist, sizing, or measured value
# from that repo is introduced, per CLAUDE.md's clean-room rule; their own
# implementation was described secondhand in #515 and was not inspected.)
#
#  A. COARSE SCAN over a fixed symmetric signed grid (BISECT_SCAN_MV),
#     including Vindiff = 0 and both signs of the half-LSB point. Symmetry is
#     deliberate: it makes the polarity classification falsifiable (a sign
#     bug would show as a one-sided ladder), and the zero point is the
#     metastability control.
#  B. OUTWARD EXPANSION, doubling the outermost probe on whichever side has
#     not yet produced a resolved decision, capped at BISECT_MAX_MV. Needed
#     because a dead band can be wider than the scan grid; an uncapped search
#     is not allowed to run forever.
#  C. TWO INDEPENDENT BISECTIONS, one per edge:
#       - the POSITIVE edge, between the nearest probed non-`DECIDED-POS`
#         point and the smallest `DECIDED-POS` point;
#       - the NEGATIVE edge, between the largest `DECIDED-NEG` point and the
#         nearest probed non-`DECIDED-NEG` point above it.
#     Each halves its own bracket to BISECT_TOL_MV. From the two converged
#     brackets:
#       systematic offset = midpoint of (negative edge, positive edge)
#       dead-band width   = positive edge - negative edge
#     and each carries the explicit +-uncertainty its bracket leaves.
#
# WHY TWO EDGES RATHER THAN ONE CROSSING. A single sign-crossing bisection
# assumes the answer flips directly from one polarity to the other, which is
# exactly the assumption a dead band violates: with a band present there is
# no Vindiff at which the sign flips, and a one-edge search either converges
# on an arbitrary interior point or never terminates. Two edges also handle
# the Vindiff = 0 metastability the sibling flagged without needing it
# resolved: an ideally symmetric mismatch-free DUT at exactly zero input is
# metastable by construction, and no amount of extra evaluate window fixes
# that -- but both bisections approach their edge from OUTSIDE, so neither
# depends on classifying the zero point at all. It is reported as data, not
# consumed as a bracket.
#
# WHAT A "NON-DECISION" MEANS HERE -- WINDOW-RELATIVE, STATED NOT ASSUMED. A
# regenerative latch's decision time grows as ln(1/Vindiff), so for a FINITE
# evaluate window there is always some small-enough input that does not
# finish. "Dead band" here therefore means "does not resolve within
# BISECT_EVALUATE_NS", and that window is named in every record this writes.
# BISECT_EVALUATE_NS is longer than `regen-corners`' own 15 ns and ~14x the
# slowest decision delay any committed record measured, and it sits well
# inside DR-006's worst-case 83.333 ns bit-trial phase -- so a band measured
# here is a band the SAR would actually see, not a window artifact. It is not
# a property of the circuit alone, and this driver does not claim it is.
#
# SOLVER FLOOR, NOT A CIRCUIT OUTCOME. A probe landing within a few tens of
# microvolts of a boundary drives ngspice's adaptive step control into a
# crawl (the sibling reported the same effect around ~100 uV). That is a
# numerical budget limit, so it is classified `SOLVER-FLOOR` and ends the
# refinement with the bracket reported as-is -- it is never recorded as
# "the circuit did not decide". BISECT_TOL_MV is the stated floor on every
# number this produces. Distinguishing a genuine crawl from ordinary host
# contention is a real hazard rather than a theoretical one: the identical
# probe deck has been measured on this host at both ~18 s and >5 min of CPU
# with no change to its text, which is the same effect
# run_ngspice_with_retry()'s own docstring documents. So each probe gets that
# helper's full four attempts, and the per-attempt budget is meant to be
# raised via SIM_NGSPICE_TIMEOUT_S for this campaign -- only a probe that
# exhausts all four at a budget sized for a fine-step transient is called a
# solver floor.
# ---------------------------------------------------------------------------

BISECT_EVALUATE_NS = 20.0
#  * Longer than `regen-corners`' CORNERS_EVALUATE_NS = 15 ns, because a
#    non-decision claim must not be a short-window artifact; shorter than
#    `regen`'s 40 ns, because every committed decision delay in this
#    experiment resolves inside 1.4 ns and each probe here is a full
#    0.005 ns-step transient paid ~25-50 times per corner.
#  * Both bounds are inside DR-006's 83.333 ns worst-case bit-trial phase
#    (BIT_TRIAL_PHASE_BUDGET_NS), so the window is SAR-relevant either way.

# Symmetric signed coarse grid. The half-LSB point is DERIVED from
# DIFFERENTIAL_LSB_MV / 2 (DR-003 Item 3) rather than written out as a literal,
# so it cannot drift from the resolution constant it is supposed to track -- it
# is the smallest differential a correct bit trial must resolve, and the
# overdrive at which a systematic offset or a dead band first costs a real
# conversion. +-50 mV is this experiment's own largest overdrive
# (DEFAULT_VINDIFF_SWEEP_MV's top value). 0.0 is the metastability control
# described above.
BISECT_HALF_LSB_MV = DIFFERENTIAL_LSB_MV / 2.0
BISECT_SCAN_MV = [
    -50.0, -10.0, -BISECT_HALF_LSB_MV, 0.0, BISECT_HALF_LSB_MV, 10.0, 50.0,
]
BISECT_MAX_MV = 400.0  # hard cap on phase B's outward expansion. 400 mV is
# ~114x the differential LSB and ~4x the largest extrapolated `offset` draw
# (~225 mV): a boundary beyond it would not be a marginal-decision finding at
# all, it would be a broken comparator, and the record says so rather than
# spending unbounded transients to pin it down.
BISECT_TOL_MV = 0.1  # 100 uV bracket floor -- see SOLVER FLOOR above. Also
# ~1/35 of the differential LSB, so it resolves the quantities that matter
# (half-LSB-scale offsets, dead bands) with ~17x margin.
BISECT_MAX_ITERS = 14  # per edge. log2(BISECT_MAX_MV / BISECT_TOL_MV) = 12,
# so 14 covers the widest bracket phase B can hand over, with slack.


@dataclass
class _BisectProbe:
    """One (corner, temp, supply, Vindiff) transient, classified by ABSOLUTE
    resolved polarity rather than relative to the applied input."""

    vindiff_mv: float
    outcome: str
    final_diff_v: float | None
    pre_edge_diff_v: float | None
    decide_time_ns: float | None
    log_text: str

    def relative_outcome(self) -> str:
        """The same probe rendered in `RegenCornerPoint.classify()`'s
        INPUT-RELATIVE taxonomy, so one table can show both views.

        This is the conflation issue #515 is about, made visible: a probe
        whose `relative_outcome()` is `WRONG-POLARITY` and one whose is
        `NO-DECISION` are indistinguishable to a sign-corrected crossing
        test, and only the first is a boundary this subcommand can bisect."""
        if self.outcome in ("NO-DATA", "RESET-NOT-HELD", "SOLVER-FLOOR",
                            "NON-MONOTONIC"):
            return self.outcome
        if self.vindiff_mv == 0.0:
            # No correct answer exists at zero input, so neither polarity is
            # "wrong" -- same treatment classify() gives its own 0 mV column.
            return "CONTROL-OK" if self.outcome == "NO-DECISION" else "CONTROL-RESOLVED"
        if self.outcome == "NO-DECISION":
            return "NO-DECISION"
        want_pos = self.vindiff_mv > 0.0
        got_pos = self.outcome == "DECIDED-POS"
        return "DECIDED" if want_pos == got_pos else "WRONG-POLARITY"


def _bisect_probe(
    info: pdk.PdkInfo, corner: str, temp_c: float, supply_v: float,
    vindiff_mv: float, scratch_dir: Path, dut_fragment: Path = DUT_FRAGMENT,
    rndseed: int | None = None,
) -> _BisectProbe:
    """Run one probe and classify it. Reuses `_regen_deck()` unchanged (only
    its comment-line `title`/`issue_ref` differ), so a boundary measured here
    and a decision delay measured by `regen`/`regen-corners` at the same
    Vindiff come from the same stimulus."""
    log_name = (
        "bisect_" + f"{vindiff_mv:.6f}mV".replace("-", "neg").replace(".", "p")
    )
    deck = _regen_deck(
        info, corner, temp_c, vindiff_mv, log_name,
        supply_v=supply_v, evaluate_ns=BISECT_EVALUATE_NS,
        title="offset-bisect decision-boundary probe", issue_ref="(issue #515)",
        dut_fragment=dut_fragment,
        rndseed=rndseed,
    )
    try:
        # run_ngspice_with_retry()'s default four attempts, deliberately: its
        # own docstring records that an unchanged netlist on a contended host
        # can blow the per-invocation budget and then finish quickly once the
        # machine is quieter, and that is reproducible here (the same 25.1 ns
        # probe deck has been measured at both ~18 s and >5 min of CPU on this
        # host with no change to its text). A single retry would therefore
        # mislabel ordinary contention as a near-boundary solver crawl, which
        # is exactly the misattribution SOLVER FLOOR above exists to avoid.
        # Raise the per-attempt budget itself with SIM_NGSPICE_TIMEOUT_S
        # (toolchain.TIMEOUT_ENV_VAR) when running this campaign -- the
        # default 120 s is sized for the `op`-based runners, not for tens of
        # fine-step transients; every record this writes names the value used.
        log_text = toolchain.run_ngspice_with_retry(
            deck, scratch_dir, log_name, attempts=4
        )
    except RuntimeError as exc:
        if "timed out" not in str(exc):
            raise
        return _BisectProbe(
            vindiff_mv=vindiff_mv, outcome="SOLVER-FLOOR", final_diff_v=None,
            pre_edge_diff_v=None, decide_time_ns=None, log_text=str(exc),
        )

    t, _clk, outp, outn = toolchain.read_wrdata_csv(
        scratch_dir / f"{log_name}.csv", 3
    )
    if not t:
        return _BisectProbe(
            vindiff_mv=vindiff_mv, outcome="NO-DATA", final_diff_v=None,
            pre_edge_diff_v=None, decide_time_ns=None, log_text=log_text,
        )

    decide_threshold_v = 0.5 * supply_v
    reset_hold_tol_v = RESET_HOLD_TOLERANCE_FRAC * supply_v
    evaluate_start_s = (RESET_NS + RESET_TR_NS) * 1e-9

    # Reset-phase integrity, identical rule to run_regen_sweep(): the last
    # sample strictly before the CLK edge STARTS rising (RESET_NS, not
    # evaluate_start -- the 100 ps edge already belongs to the evaluate
    # transition).
    pre_edge_diff_v = None
    reset_idx = [i for i, tt in enumerate(t) if tt < RESET_NS * 1e-9]
    if reset_idx:
        last = reset_idx[-1]
        pre_edge_diff_v = outp[last] - outn[last]

    final_diff_v = outp[-1] - outn[-1]

    # ABSOLUTE polarity: the first post-edge sample whose |differential|
    # exceeds the threshold, and the sign it had THERE -- never sign-corrected
    # against the applied input.
    decide_time_ns = None
    crossing_sign = 0.0
    for i, tt in enumerate(t):
        if tt < evaluate_start_s:
            continue
        diff = outp[i] - outn[i]
        if abs(diff) > decide_threshold_v:
            decide_time_ns = (tt - evaluate_start_s) * 1e9
            crossing_sign = 1.0 if diff > 0 else -1.0
            break

    if pre_edge_diff_v is not None and abs(pre_edge_diff_v) > reset_hold_tol_v:
        outcome = "RESET-NOT-HELD"
    elif decide_time_ns is None:
        outcome = "NO-DECISION"
    elif crossing_sign * final_diff_v <= 0:
        # Crossed the threshold one way and ended up the other: not a
        # decision in any usable sense. Reported, never silently signed.
        outcome = "NON-MONOTONIC"
    else:
        outcome = "DECIDED-POS" if crossing_sign > 0 else "DECIDED-NEG"

    return _BisectProbe(
        vindiff_mv=vindiff_mv, outcome=outcome, final_diff_v=final_diff_v,
        pre_edge_diff_v=pre_edge_diff_v, decide_time_ns=decide_time_ns,
        log_text=log_text,
    )


@dataclass
class BisectCornerResult:
    """The two boundaries (and everything that prevented finding them) at one
    PVT point."""

    corner: str
    temp_c: float
    supply_v: float
    evaluate_ns: float
    tol_mv: float
    probes: list[_BisectProbe]  # in the order they were run
    # Converged brackets. `*_lo`/`*_hi` are the final bracket ENDPOINTS, both
    # of them actually probed, so every number below is traceable to a row of
    # the probe ladder rather than to an interpolation.
    neg_lo_mv: float | None = None  # largest Vindiff observed DECIDED-NEG
    neg_hi_mv: float | None = None  # nearest probed point above it that is not
    pos_lo_mv: float | None = None  # nearest probed point below pos_hi that is not POS
    pos_hi_mv: float | None = None  # smallest Vindiff observed DECIDED-POS
    status: str = "NOT-RUN"
    notes: list[str] = field(default_factory=list)

    @property
    def corner_id(self) -> str:
        return corners_mod.corner_id(self.corner, self.temp_c, self.supply_v)

    @property
    def bounded(self) -> bool:
        return self.status == "BOUNDED"

    @property
    def neg_edge_mv(self) -> float | None:
        if self.neg_lo_mv is None or self.neg_hi_mv is None:
            return None
        return 0.5 * (self.neg_lo_mv + self.neg_hi_mv)

    @property
    def neg_edge_unc_mv(self) -> float | None:
        if self.neg_lo_mv is None or self.neg_hi_mv is None:
            return None
        return 0.5 * (self.neg_hi_mv - self.neg_lo_mv)

    @property
    def pos_edge_mv(self) -> float | None:
        if self.pos_lo_mv is None or self.pos_hi_mv is None:
            return None
        return 0.5 * (self.pos_lo_mv + self.pos_hi_mv)

    @property
    def pos_edge_unc_mv(self) -> float | None:
        if self.pos_lo_mv is None or self.pos_hi_mv is None:
            return None
        return 0.5 * (self.pos_hi_mv - self.pos_lo_mv)

    @property
    def offset_mv(self) -> float | None:
        """SYSTEMATIC DECISION OFFSET: the Vindiff about which the resolved
        polarity turns over, i.e. the midpoint of the two edges. Zero for a
        DUT whose decision is symmetric in its input."""
        if self.neg_edge_mv is None or self.pos_edge_mv is None:
            return None
        return 0.5 * (self.neg_edge_mv + self.pos_edge_mv)

    @property
    def offset_unc_mv(self) -> float | None:
        if self.neg_edge_unc_mv is None or self.pos_edge_unc_mv is None:
            return None
        return 0.5 * (self.neg_edge_unc_mv + self.pos_edge_unc_mv)

    @property
    def offset_resolved(self) -> bool:
        """True only when |offset| exceeds the uncertainty the two brackets
        leave. False means "indistinguishable from zero at this bisection
        floor", which is the CORRECT answer for a symmetric mismatch-free DUT
        and must be reported as a BOUND, never as a measured displacement.

        This exists as a property rather than as a comparison inlined in the
        record writer on purpose: the writer's headline sentence turns on it,
        and a headline that asserted "indistinguishable from zero"
        unconditionally would state a conclusion the data need not support --
        the exact plausible-looking-but-wrong failure mode issue #515 flags.
        A property is testable (sim/tests/test_offset_bisect.py); a literal in
        a long f-string is not."""
        o = self.offset_mv
        u = self.offset_unc_mv
        return o is not None and u is not None and abs(o) > u

    @property
    def dead_band_mv(self) -> float | None:
        """NON-DECISION (DEAD) BAND WIDTH: the Vindiff interval that resolves
        on NEITHER polarity within `evaluate_ns`. Compare against
        `dead_band_unc_mv` before calling it nonzero -- see
        `dead_band_resolved`."""
        if self.neg_edge_mv is None or self.pos_edge_mv is None:
            return None
        return self.pos_edge_mv - self.neg_edge_mv

    @property
    def dead_band_unc_mv(self) -> float | None:
        if self.neg_edge_unc_mv is None or self.pos_edge_unc_mv is None:
            return None
        return self.neg_edge_unc_mv + self.pos_edge_unc_mv

    @property
    def dead_band_resolved(self) -> bool:
        """True only when the measured band exceeds the uncertainty the two
        brackets leave. False is the CORRECT, non-crashing answer for a DUT
        that resolves at every tested Vindiff -- issue #515's edge case: the
        band is then reported as "below the floor", not as a misleading
        number and not as an error."""
        w = self.dead_band_mv
        u = self.dead_band_unc_mv
        return w is not None and u is not None and w > u

    @property
    def no_decision_probes_in_band(self) -> list[_BisectProbe]:
        """Probes that actually landed inside the measured band and resolved
        on neither polarity -- direct corroboration of a band wider than the
        bisection floor, independent of the arithmetic above.

        The Vindiff = 0 probe is DELIBERATELY EXCLUDED even when it lands
        inside the band. An ideally symmetric mismatch-free DUT at exactly zero
        input is metastable by construction (see this section's header), so a
        `NO-DECISION` there is expected whether or not a band exists and is
        therefore not evidence of one. Counting it would make even a
        zero-width band look like it had one corroborating probe -- a
        plausible-looking number that means nothing, which is the exact failure
        mode this subcommand exists to avoid. It is still reported in the probe
        ladder, as `CONTROL-OK`, the same treatment
        `RegenCornerPoint.classify()` gives its own 0 mV column."""
        if self.neg_edge_mv is None or self.pos_edge_mv is None:
            return []
        return [
            p for p in self.probes
            if p.outcome == "NO-DECISION"
            and p.vindiff_mv != 0.0
            and self.neg_edge_mv <= p.vindiff_mv <= self.pos_edge_mv
        ]


def run_offset_bisect(
    corner: str = "tt", temp_c: float = 27.0, supply_v: float = VDD,
    scan_mv: list[float] | None = None, tol_mv: float = BISECT_TOL_MV,
    max_mv: float = BISECT_MAX_MV, max_iters: int = BISECT_MAX_ITERS,
    quiet: bool = False, dut_fragment: Path = DUT_FRAGMENT,
    rndseed: int | None = None,
) -> BisectCornerResult:
    """Phases A-C of this section's header, at one PVT point.

    `rndseed` (issue #524): when given, every probe of this one search carries
    the SAME `.option rndseed`, so on a `*_mm` corner the search sees ONE fixed
    mismatch draw throughout (the boundary of that draw is a well-defined
    quantity only if the device instance does not change between probes).
    On a plain corner the seed has no effect -- that is the negative control."""
    info = pdk.resolve_or_raise()
    scan = sorted(scan_mv if scan_mv is not None else BISECT_SCAN_MV)
    result = BisectCornerResult(
        corner=corner, temp_c=temp_c, supply_v=supply_v,
        evaluate_ns=BISECT_EVALUATE_NS, tol_mv=tol_mv, probes=[],
    )
    seen: dict[float, _BisectProbe] = {}

    with tempfile.TemporaryDirectory(prefix="comparator-decision-bisect-") as scratch:
        scratch_dir = Path(scratch)

        def probe(v_mv: float) -> _BisectProbe:
            key = round(v_mv, 6)
            if key in seen:
                return seen[key]
            p = _bisect_probe(
                info, corner, temp_c, supply_v, key, scratch_dir,
                dut_fragment=dut_fragment, rndseed=rndseed,
            )
            seen[key] = p
            result.probes.append(p)
            if not quiet:
                extra = ""
                if p.final_diff_v is not None:
                    extra = f"  final_diff={p.final_diff_v:+.4f}V"
                if p.decide_time_ns is not None:
                    extra += f"  t_decide={p.decide_time_ns:.4f}ns"
                print(f"  vindiff={key:+.6f}mV -> {p.outcome}{extra}")
            return p

        # --- Phase A: coarse symmetric scan -------------------------------
        for v in scan:
            probe(v)

        zero = seen.get(0.0)
        if zero is not None and zero.outcome == "RESET-NOT-HELD":
            # Same rule RegenCornerPoint.classify() applies: a latch that
            # separated before its own clock edge with no input applied has
            # not been reset, so nothing after the edge is a response to the
            # input and no boundary is extractable here.
            result.status = "RESET-NOT-HELD"
            result.notes.append(
                "the Vindiff = 0 mV reset-integrity control did not hold "
                f"(pre-edge v(OUTP)-v(OUTN) = {zero.pre_edge_diff_v:+.4f} V, "
                f"tolerance {RESET_HOLD_TOLERANCE_FRAC:.0%} of the rail), so "
                "no decision boundary is extractable at this corner"
            )
            return result
        not_held = [p for p in result.probes if p.outcome == "RESET-NOT-HELD"]
        if not_held:
            result.notes.append(
                f"{len(not_held)} probe(s) show RESET-NOT-HELD and are excluded "
                "from edge determination (the zero-input control itself held)"
            )

        # --- Phase B: outward expansion -----------------------------------
        def have(outcome: str) -> bool:
            return any(p.outcome == outcome for p in result.probes)

        hi = max(scan)
        while not have("DECIDED-POS") and hi < max_mv:
            hi = min(hi * 2.0, max_mv) if hi > 0 else 1.0
            probe(hi)
        lo = min(scan)
        while not have("DECIDED-NEG") and lo > -max_mv:
            lo = max(lo * 2.0, -max_mv) if lo < 0 else -1.0
            probe(lo)

        pos_vals = sorted(v for v, p in seen.items() if p.outcome == "DECIDED-POS")
        neg_vals = sorted(v for v, p in seen.items() if p.outcome == "DECIDED-NEG")
        if not pos_vals or not neg_vals:
            missing = []
            if not pos_vals:
                missing.append("positive")
            if not neg_vals:
                missing.append("negative")
            result.status = "UNBOUNDED"
            result.notes.append(
                f"no {' or '.join(missing)}-polarity decision anywhere out to "
                f"+-{max_mv:g} mV, so that edge does not exist within the "
                f"searched range: the non-decision band is WIDER than the "
                f"search, and this record reports the search bound rather than "
                "a width"
            )
            return result
        if max(neg_vals) > min(pos_vals):
            result.status = "NON-MONOTONIC"
            result.notes.append(
                f"resolved polarity is not monotonic in Vindiff: a DECIDED-NEG "
                f"probe at {max(neg_vals):+.6f} mV sits ABOVE a DECIDED-POS "
                f"probe at {min(pos_vals):+.6f} mV. A single pair of boundaries "
                "does not describe this corner and none is reported"
            )
            return result

        # --- Phase C: two independent bisections --------------------------
        # An initial bracket endpoint must itself be a CIRCUIT outcome, never a
        # measurement-limit one: the whole claim "the boundary lies inside
        # [lo, hi]" rests on both endpoints having been classified, and a
        # SOLVER-FLOOR / NO-DATA / RESET-NOT-HELD / NON-MONOTONIC probe has
        # not been. (`refine()` below already refuses to ACCEPT such a probe as
        # a bracket; this is the same rule applied to the bracket it starts
        # from, which the Phase-A/B ladder could otherwise supply.) Both
        # comprehensions are non-empty by construction: the monotonicity test
        # just above guarantees at least one DECIDED-NEG strictly below
        # min(pos_vals) and at least one DECIDED-POS strictly above
        # max(neg_vals).
        _CIRCUIT_OUTCOMES = ("DECIDED-POS", "DECIDED-NEG", "NO-DECISION")
        pos_hi = min(pos_vals)
        pos_lo = max(
            v for v, p in seen.items()
            if v < pos_hi and p.outcome in _CIRCUIT_OUTCOMES
        )
        neg_lo = max(neg_vals)
        neg_hi = min(
            v for v, p in seen.items()
            if v > neg_lo and p.outcome in _CIRCUIT_OUTCOMES
        )

        def refine(
            lo_v: float, hi_v: float, hold_outcome: str, label: str,
        ) -> tuple[float, float]:
            """Halve (lo_v, hi_v) until narrower than tol_mv, keeping the
            invariant `probe(lo_v)`/`probe(hi_v)` on the `hold_outcome` side.

            `hold_outcome` is the outcome that must stay attached to the
            endpoint being pushed INWARD -- `DECIDED-POS` for the positive
            edge (pushing hi down) and `DECIDED-NEG` for the negative edge
            (pushing lo up)."""
            for _ in range(max_iters):
                if hi_v - lo_v <= tol_mv:
                    break
                mid = 0.5 * (lo_v + hi_v)
                p = probe(mid)
                if p.outcome in ("SOLVER-FLOOR", "RESET-NOT-HELD", "NO-DATA",
                                 "NON-MONOTONIC"):
                    result.notes.append(
                        f"{label}-edge refinement stopped at bracket width "
                        f"{hi_v - lo_v:.6f} mV: the probe at {mid:+.6f} mV "
                        f"returned {p.outcome}, which is a measurement limit, "
                        "not a circuit outcome, so it is not used as a bracket"
                    )
                    break
                if hold_outcome == "DECIDED-POS":
                    if p.outcome == "DECIDED-POS":
                        hi_v = mid
                    else:
                        lo_v = mid
                else:
                    if p.outcome == "DECIDED-NEG":
                        lo_v = mid
                    else:
                        hi_v = mid
            else:
                result.notes.append(
                    f"{label}-edge refinement hit the {max_iters}-iteration cap "
                    f"at bracket width {hi_v - lo_v:.6f} mV"
                )
            return lo_v, hi_v

        pos_lo, pos_hi = refine(pos_lo, pos_hi, "DECIDED-POS", "positive")
        neg_lo, neg_hi = refine(neg_lo, neg_hi, "DECIDED-NEG", "negative")

        # Re-check monotonicity over the FULL probe ladder, refinement probes
        # included. The Phase-B test above only saw the coarse ladder; each
        # refinement adds up to BISECT_MAX_ITERS new classified points, any of
        # which could in principle place a DECIDED-NEG above a DECIDED-POS and
        # falsify the single-boundary-pair model the edges assume. Cheap to
        # verify (no extra transients) and the only check that covers the points
        # the bisection itself introduced.
        pos_vals = sorted(v for v, p in seen.items() if p.outcome == "DECIDED-POS")
        neg_vals = sorted(v for v, p in seen.items() if p.outcome == "DECIDED-NEG")
        if max(neg_vals) > min(pos_vals):
            result.status = "NON-MONOTONIC"
            result.notes.append(
                f"resolved polarity is not monotonic in Vindiff once the "
                f"refinement probes are included: a DECIDED-NEG probe at "
                f"{max(neg_vals):+.6f} mV sits ABOVE a DECIDED-POS probe at "
                f"{min(pos_vals):+.6f} mV. A single pair of boundaries does not "
                "describe this corner and none is reported"
            )
            return result

        result.pos_lo_mv, result.pos_hi_mv = pos_lo, pos_hi
        result.neg_lo_mv, result.neg_hi_mv = neg_lo, neg_hi
        result.status = "BOUNDED"

    return result


# Default PVT points for `offset-bisect` (issue #515's acceptance criteria):
# the nominal corner and the slow/cold one. Nominal supply at both -- the
# supply axis is deliberately NOT swept here (see the record's subset-corner
# justification).
BISECT_DEFAULT_POINTS = [("tt", 27.0), ("ss", -40.0)]

# The schematic-level `offset-bisect` record an extracted-DUT run (issue #525)
# is compared against, and the BOUNDS that record measured (both points:
# |offset| < 0.0275 mV, band < 0.0549 mV -- neither resolved). Cited, not
# re-derived: they are a committed record's numbers, quoted so the post-layout
# record can state the comparison in one place without re-reading markdown.
BISECT_SCHEMATIC_RECORD_ID = "20261002-203719-c898d06"
BISECT_SCHEMATIC_OFFSET_BOUND_MV = 0.0275
BISECT_SCHEMATIC_BAND_BOUND_MV = 0.0549


def run_offset_bisect_points(
    points: list[tuple[str, float]] | None = None, supply_v: float = VDD,
    quiet: bool = False, dut_fragment: Path = DUT_FRAGMENT,
) -> list[BisectCornerResult]:
    pdk.resolve_or_raise()  # fail fast before spending the grid's runtime
    out: list[BisectCornerResult] = []
    for process_corner, temp_c in (points or BISECT_DEFAULT_POINTS):
        if not quiet:
            print(f"{corners_mod.corner_id(process_corner, temp_c, supply_v)}:")
        out.append(run_offset_bisect(
            corner=process_corner, temp_c=temp_c, supply_v=supply_v, quiet=quiet,
            dut_fragment=dut_fragment,
        ))
    return out

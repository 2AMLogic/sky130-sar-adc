"""Correctness tests for `offset-bisect`'s boundary-bisection algorithm in
sim/comparator-decision/run.py (issue #515) -- pure algorithm, no ngspice and
no PDK (mirrors sim/tests/test_run_hold_kick.py's PDK-free unit-test
convention; see sim/selftest.sh stage 1/4).

WHY THIS FILE EXISTS. Issue #515 is explicitly flagged complex for one reason:
the bisection's correctness -- boundary DIRECTION, polarity classification,
dead-band detection -- is a judgement call on analog simulation data where a
subtle sign or bracket bug produces a *plausible-looking but wrong* number
that then gets written into a decision record as fact. Nothing about an
ngspice run can catch that: a wrong answer and a right answer are both just a
float. The only way to falsify the algorithm is to drive it with SYNTHETIC
DUTs whose true boundaries are known by construction and assert it recovers
them, which is what every test below does.

Each test replaces `run._bisect_probe` with a closed-form oracle -- an
`outcome(vindiff_mv)` rule -- so the test asserts the SEARCH, not the circuit.
The numbers used as synthetic boundaries are arbitrary test fixtures chosen to
exercise the shapes the search must handle (symmetric, offset, dead band,
unbounded, non-monotonic, measurement-limited); they are NOT measurements and
nothing here is evidence about the comparator. The measured values live in
`sim/comparator-decision/records/`."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
COMPARATOR_DIR = SIM_DIR / "comparator-decision"
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(COMPARATOR_DIR))

import run as cd  # noqa: E402


def _install_oracle(test: unittest.TestCase, outcome_of) -> list[float]:
    """Point `run._bisect_probe` at a synthetic `outcome_of(vindiff_mv) -> str`
    oracle and `run.pdk.resolve_or_raise` at a stub, restoring both on
    teardown. Returns the (mutable) list of probed Vindiff values, so a test
    can also assert on the SEARCH ITSELF (probe count, symmetry, that a
    classified bracket endpoint was really simulated) rather than only on the
    extracted edges."""
    probed: list[float] = []
    probe_fragments: list[Path] = []
    test.probe_fragments = probe_fragments

    def fake_probe(
        info, corner, temp_c, supply_v, vindiff_mv, scratch_dir,
        dut_fragment=cd.DUT_FRAGMENT,
    ):
        probed.append(vindiff_mv)
        probe_fragments.append(dut_fragment)
        outcome = outcome_of(vindiff_mv)
        decided = outcome in ("DECIDED-POS", "DECIDED-NEG")
        sign = 1.0 if outcome == "DECIDED-POS" else -1.0
        return cd._BisectProbe(
            vindiff_mv=vindiff_mv,
            outcome=outcome,
            # A decided probe ends saturated at the rail it chose; an
            # undecided one ends near zero differential. Only the sign and
            # magnitude pattern matter to anything downstream.
            final_diff_v=(sign * cd.VDD) if decided else (0.0 if outcome == "NO-DECISION" else None),
            pre_edge_diff_v=0.0 if outcome != "NO-DATA" else None,
            decide_time_ns=1.0 if decided else None,
            log_text=f"synthetic oracle probe at {vindiff_mv:+.6f} mV -> {outcome}",
        )

    real_probe = cd._bisect_probe
    real_resolve = cd.pdk.resolve_or_raise
    cd._bisect_probe = fake_probe
    cd.pdk.resolve_or_raise = lambda: None

    def restore():
        cd._bisect_probe = real_probe
        cd.pdk.resolve_or_raise = real_resolve

    test.addCleanup(restore)
    return probed


def _sign_flip_at(boundary_mv: float):
    """A DUT with NO dead band: it resolves to the correct-side polarity on
    either side of a single `boundary_mv`, and is metastable exactly on it.
    The true systematic offset is `boundary_mv`; the true band is zero."""

    def outcome_of(v_mv: float) -> str:
        if v_mv > boundary_mv:
            return "DECIDED-POS"
        if v_mv < boundary_mv:
            return "DECIDED-NEG"
        return "NO-DECISION"

    return outcome_of


def _dead_band(neg_edge_mv: float, pos_edge_mv: float):
    """A DUT with a genuine dead band: nothing resolves on `(neg_edge_mv,
    pos_edge_mv)`. True offset is the midpoint, true width the separation."""

    def outcome_of(v_mv: float) -> str:
        if v_mv >= pos_edge_mv:
            return "DECIDED-POS"
        if v_mv <= neg_edge_mv:
            return "DECIDED-NEG"
        return "NO-DECISION"

    return outcome_of


class TestSymmetricDutIsTheNegativeControl(unittest.TestCase):
    """A mismatch-free symmetric DUT must come back at ~0 mV offset with NO
    resolved dead band. This is the control the measurement campaign leans on:
    a non-zero answer here would indict the search, not the circuit."""

    def setUp(self):
        self.probed = _install_oracle(self, _sign_flip_at(0.0))
        self.result = cd.run_offset_bisect(quiet=True)

    def test_status_is_bounded(self):
        self.assertEqual(self.result.status, "BOUNDED")

    def test_offset_is_zero_within_the_bisection_floor(self):
        self.assertIsNotNone(self.result.offset_mv)
        self.assertLessEqual(abs(self.result.offset_mv), cd.BISECT_TOL_MV)

    def test_dead_band_is_not_resolved_and_is_not_a_crash(self):
        """Issue #515's named edge case: a DUT that resolves at (almost) every
        tested Vindiff must report a band BELOW THE FLOOR -- not a crash, and
        not a misleading number presented as a real width."""
        self.assertIsNotNone(self.result.dead_band_mv)
        self.assertFalse(self.result.dead_band_resolved)
        self.assertLessEqual(self.result.dead_band_mv, self.result.dead_band_unc_mv)

    def test_the_metastable_zero_probe_is_not_counted_as_band_corroboration(self):
        """Caught during development: the Vindiff = 0 control is `NO-DECISION`
        on a symmetric DUT by construction, so including it in the
        "corroborating probes inside the band" count made a ZERO-width band
        look like it had one supporting probe. It must not count -- but it must
        still appear in the ladder, as the control."""
        self.assertEqual(self.result.no_decision_probes_in_band, [])
        zero = [p for p in self.result.probes if p.vindiff_mv == 0.0]
        self.assertEqual(len(zero), 1)
        self.assertEqual(zero[0].relative_outcome(), "CONTROL-OK")

    def test_brackets_straddle_the_true_boundary(self):
        """Direction check: the positive edge's bracket must contain the true
        boundary from above and the negative edge's from below. A flipped
        comparison in `refine()` would converge to the wrong side and this is
        what catches it."""
        self.assertLess(self.result.neg_lo_mv, 0.0 + cd.BISECT_TOL_MV)
        self.assertGreater(self.result.pos_hi_mv, 0.0 - cd.BISECT_TOL_MV)
        self.assertLessEqual(self.result.pos_hi_mv - self.result.pos_lo_mv, cd.BISECT_TOL_MV)
        self.assertLessEqual(self.result.neg_hi_mv - self.result.neg_lo_mv, cd.BISECT_TOL_MV)

    def test_coarse_scan_was_symmetric_and_included_the_zero_control(self):
        """A one-sided ladder is the tell for a sign bug in the search setup,
        so assert the symmetry the algorithm's Phase A claims."""
        for v in cd.BISECT_SCAN_MV:
            self.assertIn(round(v, 6), [round(p, 6) for p in self.probed])
        self.assertIn(0.0, [round(p, 6) for p in self.probed])

    def test_half_lsb_scan_point_tracks_the_resolution_constant(self):
        self.assertAlmostEqual(
            cd.BISECT_HALF_LSB_MV, cd.DIFFERENTIAL_LSB_MV / 2.0, places=12
        )
        self.assertIn(cd.BISECT_HALF_LSB_MV, cd.BISECT_SCAN_MV)
        self.assertIn(-cd.BISECT_HALF_LSB_MV, cd.BISECT_SCAN_MV)


class TestSystematicOffsetIsRecoveredWithTheRightSign(unittest.TestCase):
    """A pure sign-flip DUT displaced off zero: the search must recover the
    displacement, WITH ITS SIGN, and still report no dead band. Both signs are
    tested -- a sign error that happens to cancel on a symmetric DUT cannot
    survive both of these."""

    def _measure(self, boundary_mv: float) -> cd.BisectCornerResult:
        _install_oracle(self, _sign_flip_at(boundary_mv))
        return cd.run_offset_bisect(quiet=True)

    def test_positive_offset(self):
        r = self._measure(+1.84)
        self.assertEqual(r.status, "BOUNDED")
        self.assertAlmostEqual(r.offset_mv, +1.84, delta=cd.BISECT_TOL_MV)
        self.assertFalse(r.dead_band_resolved)

    def test_negative_offset(self):
        r = self._measure(-7.25)
        self.assertEqual(r.status, "BOUNDED")
        self.assertAlmostEqual(r.offset_mv, -7.25, delta=cd.BISECT_TOL_MV)
        self.assertFalse(r.dead_band_resolved)

    def test_offset_uncertainty_is_the_bracket_half_width_not_zero(self):
        r = self._measure(+1.84)
        self.assertGreater(r.offset_unc_mv, 0.0)
        self.assertLessEqual(r.offset_unc_mv, cd.BISECT_TOL_MV)

    def test_a_real_displacement_is_reported_as_resolved(self):
        """`offset_resolved` is what the record's headline sentence turns on, so
        it must be True for a displacement far above the bracket floor and
        False for one indistinguishable from zero. A writer that hardcoded
        either conclusion would state a finding the data need not support."""
        self.assertTrue(self._measure(+1.84).offset_resolved)

    def test_a_symmetric_dut_is_not_reported_as_having_a_resolved_offset(self):
        _install_oracle(self, _sign_flip_at(0.0))
        r = cd.run_offset_bisect(quiet=True)
        self.assertFalse(r.offset_resolved)
        self.assertLessEqual(abs(r.offset_mv), r.offset_unc_mv)

    def test_offset_resolved_is_false_when_no_boundary_pair_exists(self):
        _install_oracle(self, _dead_band(-1e9, +1e9))
        r = cd.run_offset_bisect(quiet=True, max_mv=50.0)
        self.assertIsNone(r.offset_mv)
        self.assertFalse(r.offset_resolved)


class TestDeadBandIsMeasuredSeparatelyFromOffset(unittest.TestCase):
    """The whole point of issue #515: a DUT with a genuine non-decision band
    must yield BOTH a systematic offset (the band's midpoint) AND the band's
    width, as two separate numbers -- not one conflated figure."""

    def setUp(self):
        # Asymmetric on purpose, so a bug that reports the width as the offset
        # (or vice versa) cannot pass: midpoint +6, width 28.
        _install_oracle(self, _dead_band(-8.0, +20.0))
        self.result = cd.run_offset_bisect(quiet=True)

    def test_status_is_bounded(self):
        self.assertEqual(self.result.status, "BOUNDED")

    def test_both_edges_are_recovered(self):
        self.assertAlmostEqual(self.result.neg_edge_mv, -8.0, delta=cd.BISECT_TOL_MV)
        self.assertAlmostEqual(self.result.pos_edge_mv, +20.0, delta=cd.BISECT_TOL_MV)

    def test_offset_is_the_midpoint_and_band_is_the_separation(self):
        self.assertAlmostEqual(self.result.offset_mv, +6.0, delta=cd.BISECT_TOL_MV)
        self.assertAlmostEqual(self.result.dead_band_mv, 28.0, delta=2 * cd.BISECT_TOL_MV)

    def test_band_is_reported_resolved_and_corroborated_by_probes_inside_it(self):
        self.assertTrue(self.result.dead_band_resolved)
        self.assertGreater(self.result.dead_band_mv, self.result.dead_band_unc_mv)
        # Independent of the arithmetic: real probes landed inside the band and
        # resolved on neither polarity.
        self.assertGreater(len(self.result.no_decision_probes_in_band), 0)
        for p in self.result.no_decision_probes_in_band:
            self.assertEqual(p.outcome, "NO-DECISION")


class TestWrongPolarityIsNotConflatedWithNonDecision(unittest.TestCase):
    """`relative_outcome()` must render a wrong-polarity DECISION and a
    genuine NON-decision as two DIFFERENT labels. A sign-corrected crossing
    test cannot, and that conflation is the methodology half of issue #515."""

    def test_a_decision_on_the_wrong_side_reads_wrong_polarity(self):
        p = cd._BisectProbe(
            vindiff_mv=+10.0, outcome="DECIDED-NEG", final_diff_v=-cd.VDD,
            pre_edge_diff_v=0.0, decide_time_ns=1.0, log_text="",
        )
        self.assertEqual(p.relative_outcome(), "WRONG-POLARITY")

    def test_a_decision_on_the_right_side_reads_decided(self):
        for v, outcome in ((+10.0, "DECIDED-POS"), (-10.0, "DECIDED-NEG")):
            p = cd._BisectProbe(
                vindiff_mv=v, outcome=outcome, final_diff_v=cd.VDD,
                pre_edge_diff_v=0.0, decide_time_ns=1.0, log_text="",
            )
            self.assertEqual(p.relative_outcome(), "DECIDED")

    def test_no_decision_stays_no_decision(self):
        p = cd._BisectProbe(
            vindiff_mv=+10.0, outcome="NO-DECISION", final_diff_v=0.0,
            pre_edge_diff_v=0.0, decide_time_ns=None, log_text="",
        )
        self.assertEqual(p.relative_outcome(), "NO-DECISION")

    def test_the_zero_input_control_has_no_wrong_side(self):
        """At Vindiff = 0 no polarity is "wrong" (the DUT is ideally
        metastable), so neither resolved sign may be reported as an error --
        the same treatment `RegenCornerPoint.classify()` gives its own 0 mV
        column."""
        undecided = cd._BisectProbe(
            vindiff_mv=0.0, outcome="NO-DECISION", final_diff_v=0.0,
            pre_edge_diff_v=0.0, decide_time_ns=None, log_text="",
        )
        self.assertEqual(undecided.relative_outcome(), "CONTROL-OK")
        for outcome in ("DECIDED-POS", "DECIDED-NEG"):
            resolved = cd._BisectProbe(
                vindiff_mv=0.0, outcome=outcome, final_diff_v=cd.VDD,
                pre_edge_diff_v=0.0, decide_time_ns=1.0, log_text="",
            )
            self.assertEqual(resolved.relative_outcome(), "CONTROL-RESOLVED")

    def test_measurement_limits_pass_through_unchanged(self):
        for outcome in ("NO-DATA", "RESET-NOT-HELD", "SOLVER-FLOOR", "NON-MONOTONIC"):
            p = cd._BisectProbe(
                vindiff_mv=+10.0, outcome=outcome, final_diff_v=None,
                pre_edge_diff_v=None, decide_time_ns=None, log_text="",
            )
            self.assertEqual(p.relative_outcome(), outcome)


class TestSearchFailuresAreReportedNotGuessed(unittest.TestCase):
    """Every way the search can fail to establish a boundary pair must produce
    a NAMED status with `offset_mv`/`dead_band_mv` left `None` -- never a
    fabricated number and never an exception."""

    def test_a_band_wider_than_the_search_is_unbounded(self):
        _install_oracle(self, _dead_band(-1e9, +1e9))  # never resolves
        r = cd.run_offset_bisect(quiet=True, max_mv=50.0)
        self.assertEqual(r.status, "UNBOUNDED")
        self.assertIsNone(r.offset_mv)
        self.assertIsNone(r.dead_band_mv)
        self.assertFalse(r.dead_band_resolved)
        self.assertTrue(any("WIDER than the search" in n for n in r.notes))

    def test_a_one_sided_band_is_also_unbounded(self):
        """No POSITIVE-polarity decision anywhere in range (the shape the
        cross-pollinated slow/cold finding described) must not be silently
        collapsed into a symmetric answer."""
        _install_oracle(self, _dead_band(-8.0, +1e9))
        r = cd.run_offset_bisect(quiet=True, max_mv=50.0)
        self.assertEqual(r.status, "UNBOUNDED")
        self.assertIsNone(r.offset_mv)
        self.assertTrue(any("positive" in n for n in r.notes))

    def test_a_non_monotonic_dut_is_refused(self):
        """Polarity that is not monotonic in Vindiff is not describable by one
        pair of boundaries, so no pair may be reported."""

        def inverted(v_mv: float) -> str:
            if v_mv > 0:
                return "DECIDED-NEG"
            if v_mv < 0:
                return "DECIDED-POS"
            return "NO-DECISION"

        _install_oracle(self, inverted)
        r = cd.run_offset_bisect(quiet=True)
        self.assertEqual(r.status, "NON-MONOTONIC")
        self.assertIsNone(r.offset_mv)
        self.assertIsNone(r.dead_band_mv)

    def test_a_failed_zero_input_reset_control_aborts_the_corner(self):
        _install_oracle(self, lambda v_mv: "RESET-NOT-HELD")
        r = cd.run_offset_bisect(quiet=True)
        self.assertEqual(r.status, "RESET-NOT-HELD")
        self.assertIsNone(r.offset_mv)

    def test_a_solver_floor_probe_is_never_used_as_a_bracket(self):
        """A near-boundary solver crawl is a measurement limit, not a circuit
        outcome. It must end the refinement with the bracket reported as-is --
        never be recorded as "the circuit did not decide", and never become a
        bracket endpoint the offset is then derived from."""

        def crawls_near_zero(v_mv: float) -> str:
            if abs(v_mv) < 1.0 and v_mv != 0.0:
                return "SOLVER-FLOOR"
            if v_mv > 0:
                return "DECIDED-POS"
            if v_mv < 0:
                return "DECIDED-NEG"
            return "NO-DECISION"

        _install_oracle(self, crawls_near_zero)
        r = cd.run_offset_bisect(quiet=True)
        self.assertEqual(r.status, "BOUNDED")
        self.assertTrue(any("measurement limit" in n for n in r.notes))
        # The reported bracket endpoints must each be a probe that was
        # CLASSIFIED as a circuit outcome, not one that hit the solver floor.
        by_v = {round(p.vindiff_mv, 6): p for p in r.probes}
        for endpoint in (r.pos_lo_mv, r.pos_hi_mv, r.neg_lo_mv, r.neg_hi_mv):
            self.assertIn(round(endpoint, 6), by_v)
            self.assertIn(
                by_v[round(endpoint, 6)].outcome,
                ("DECIDED-POS", "DECIDED-NEG", "NO-DECISION"),
            )
        # And it is still reported in the ladder, as its own outcome.
        self.assertTrue(any(p.outcome == "SOLVER-FLOOR" for p in r.probes))
        for p in r.probes:
            if p.outcome == "SOLVER-FLOOR":
                self.assertNotEqual(p.relative_outcome(), "NO-DECISION")


class TestSearchIsBounded(unittest.TestCase):
    """The search must terminate on its own budget, never run away: an
    uncapped expansion or a non-converging bisection on a pathological DUT is
    exactly the failure `.loom/docs/long-running-compute.md` forbids."""

    def test_expansion_never_probes_beyond_the_cap(self):
        probed = _install_oracle(self, _dead_band(-1e9, +1e9))
        cd.run_offset_bisect(quiet=True, max_mv=100.0)
        for v in probed:
            self.assertLessEqual(abs(v), 100.0)

    def test_probe_count_is_bounded_by_scan_plus_expansion_plus_two_bisections(self):
        probed = _install_oracle(self, _sign_flip_at(0.0))
        cd.run_offset_bisect(quiet=True)
        cap = len(cd.BISECT_SCAN_MV) + 2 * cd.BISECT_MAX_ITERS + 2 * 16
        self.assertLessEqual(len(probed), cap)

    def test_repeated_vindiff_values_are_not_re_simulated(self):
        """Probes are memoized by Vindiff: a bisection that re-probes a point
        it already has would double the campaign's ngspice cost for nothing."""
        probed = _install_oracle(self, _sign_flip_at(0.0))
        cd.run_offset_bisect(quiet=True)
        rounded = [round(v, 6) for v in probed]
        self.assertEqual(len(rounded), len(set(rounded)))


class TestWindowAndFloorConstantsAreSelfConsistent(unittest.TestCase):
    """The non-decision claim is WINDOW-RELATIVE, and the record says so. These
    assert the stated relationships actually hold in the constants, so a later
    retune cannot quietly invalidate the record's own justification."""

    def test_evaluate_window_is_longer_than_the_corner_sweeps(self):
        self.assertGreater(cd.BISECT_EVALUATE_NS, cd.CORNERS_EVALUATE_NS)

    def test_evaluate_window_fits_inside_the_bit_trial_phase_budget(self):
        self.assertLess(cd.BISECT_EVALUATE_NS, cd.BIT_TRIAL_PHASE_BUDGET_NS)

    def test_bisection_floor_is_well_below_half_an_lsb(self):
        self.assertLess(cd.BISECT_TOL_MV, cd.DIFFERENTIAL_LSB_MV / 2.0)

    def test_iteration_cap_covers_the_widest_bracket_expansion_can_hand_over(self):
        import math
        needed = math.ceil(math.log2(2 * cd.BISECT_MAX_MV / cd.BISECT_TOL_MV))
        self.assertGreaterEqual(cd.BISECT_MAX_ITERS, needed)


class TestDutFragmentSelector(unittest.TestCase):
    """Issue #525: `offset-bisect --dut extracted` swaps in the post-layout
    fragment without touching the schematic path. PDK-free, no ngspice."""

    class _Info:
        ngspice_lib = "/stub/sky130.lib.spice"

    def _deck(self, **kw):
        return cd._regen_deck(self._Info(), "tt", 27.0, 1.0, "x", **kw)

    def test_default_deck_embeds_the_schematic_fragment_unchanged(self):
        self.assertEqual(self._deck(), self._deck(dut_fragment=cd.DUT_FRAGMENT))
        self.assertIn(cd.DUT_FRAGMENT.read_text(), self._deck())
        self.assertNotIn("gen_compose_0", self._deck())

    def test_extracted_deck_embeds_extracted_fragment_not_schematic(self):
        deck = self._deck(dut_fragment=cd.DUT_FRAGMENT_EXTRACTED)
        self.assertIn(cd.DUT_FRAGMENT_EXTRACTED.read_text(), deck)
        self.assertNotIn("XM_TAIL", deck)

    def test_extracted_ports_match_schematic_ports_and_instantiation_order(self):
        import re
        want = {"VDD", "GND", "CLK", "VINP", "VINN", "OUTP", "OUTN"}
        text = cd.DUT_FRAGMENT_EXTRACTED.read_text()
        ports = re.search(r"^\.SUBCKT\s+\S+\s+(.+)$", text, re.M).group(1).split()
        self.assertEqual(set(ports), want)
        # the schematic fragment's own header names the same seven ports
        self.assertIn("VDD, GND (auto-tied", cd.DUT_FRAGMENT.read_text())
        inst = re.search(r"^Xdut\s+(.+)\s+(\S+)$", text, re.M)
        self.assertEqual(inst.group(1).split(), ports)  # nets tied by name
        self.assertEqual(inst.group(2), "gen_compose_0")
        self.assertRegex(text, r"(?m)^\.ENDS\s+gen_compose_0")

    def test_extracted_fragment_carries_parasitics(self):
        import re
        text = cd.DUT_FRAGMENT_EXTRACTED.read_text()
        self.assertGreater(len(re.findall(r"(?m)^[RC]\S+ ", text)), 50)

    def test_provenance_names_the_fragment_that_ran(self):
        sch = cd._dut_provenance(cd.DUT_FRAGMENT)
        ext = cd._dut_provenance(cd.DUT_FRAGMENT_EXTRACTED)
        self.assertTrue(sch.startswith("schematic"))
        self.assertIn("comparator_core.spice", sch)
        self.assertTrue(ext.startswith("post-layout extracted"))
        self.assertIn("comparator_core_extracted.spice", ext)
        self.assertNotIn("schematic", ext.split("(")[0])

    def test_cli_choices_default_to_schematic(self):
        self.assertIs(cd.DUT_CHOICES["schematic"], cd.DUT_FRAGMENT)
        self.assertIs(cd.DUT_CHOICES["extracted"], cd.DUT_FRAGMENT_EXTRACTED)

    def test_fragment_is_threaded_to_every_probe(self):
        _install_oracle(self, _sign_flip_at(0.0))
        cd.run_offset_bisect(quiet=True, dut_fragment=cd.DUT_FRAGMENT_EXTRACTED)
        self.assertTrue(self.probe_fragments)
        self.assertTrue(all(f == cd.DUT_FRAGMENT_EXTRACTED for f in self.probe_fragments))

    def test_default_run_uses_schematic_fragment(self):
        _install_oracle(self, _sign_flip_at(0.0))
        cd.run_offset_bisect(quiet=True)
        self.assertTrue(all(f == cd.DUT_FRAGMENT for f in self.probe_fragments))


class TestPostLayoutHalfLsbVerdict(unittest.TestCase):
    """Issue #525: an extracted-DUT record must state explicitly whether a
    systematic offset or dead band appears at half-LSB scale -- DR-020's
    supersession trigger. Synthetic DUTs again; nothing here is evidence."""

    HALF = cd.DIFFERENTIAL_LSB_MV / 2.0

    def _results(self, *oracles):
        out = []
        for oracle in oracles:
            _install_oracle(self, oracle)
            out.append(cd.run_offset_bisect(quiet=True))
        return out

    def _section(self, results) -> str:
        lines: list[str] = []
        cd._offset_bisect_postlayout_comparison(lines.append, results, self.HALF)
        return "\n".join(lines)

    def test_symmetric_dut_corroborates_dr020(self):
        rs = self._results(_sign_flip_at(0.0), _sign_flip_at(0.0))
        verdict, reasons = cd._postlayout_half_lsb_verdict(rs, self.HALF)
        self.assertEqual(verdict, "NOT-TRIGGERED")
        self.assertEqual(reasons, [])
        text = self._section(rs)
        self.assertIn("NOT MET", text)
        self.assertIn("CORROBORATED", text)
        self.assertIn("appear post-layout? NO", text)
        self.assertIn(cd.BISECT_SCHEMATIC_RECORD_ID, text)

    def test_small_resolved_offset_appears_but_does_not_trigger(self):
        # resolved (far above the 0.1 mV floor) but well under half-LSB
        rs = self._results(_sign_flip_at(0.6))
        self.assertTrue(rs[0].offset_resolved)
        verdict, _ = cd._postlayout_half_lsb_verdict(rs, self.HALF)
        self.assertEqual(verdict, "NOT-TRIGGERED")
        text = self._section(rs)
        self.assertIn("appear post-layout? YES", text)
        self.assertIn("NOT MET", text)

    def test_half_lsb_offset_triggers_supersession(self):
        rs = self._results(_sign_flip_at(0.0), _sign_flip_at(-2.5))
        verdict, reasons = cd._postlayout_half_lsb_verdict(rs, self.HALF)
        self.assertEqual(verdict, "TRIGGERED")
        self.assertTrue(any("systematic offset" in r for r in reasons))
        self.assertIn("SUPERSEDED BY A NEW DECISION RECORD", self._section(rs))

    def test_half_lsb_dead_band_triggers_supersession(self):
        rs = self._results(_dead_band(-1.5, +1.5))  # 3 mV wide, centred
        self.assertFalse(rs[0].offset_resolved)
        verdict, reasons = cd._postlayout_half_lsb_verdict(rs, self.HALF)
        self.assertEqual(verdict, "TRIGGERED")
        self.assertTrue(any("dead band" in r for r in reasons))

    def test_unbounded_point_is_undetermined_not_corroborating(self):
        _install_oracle(self, _dead_band(-1e9, +1e9))
        rs = [cd.run_offset_bisect(quiet=True, max_mv=50.0)]
        verdict, reasons = cd._postlayout_half_lsb_verdict(rs, self.HALF)
        self.assertEqual(verdict, "UNDETERMINED")
        self.assertIn("UNDETERMINED", self._section(rs))

    def test_half_lsb_constant_matches_dr020_figure(self):
        self.assertAlmostEqual(self.HALF, 1.7578, places=4)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for sim/sampling-cdac-handoff/run_handoff.py's `--corners` mode
(issue #469) -- deck text generation and grid construction only, no ngspice run
(mirrors sim/tests/test_harness.py's and sim/tests/test_run_hold_kick.py's
PDK-free unit-test convention; see sim/selftest.sh stage 1/4).

Two classes of mistake these tests exist to catch, both of which produce a
plausible-looking record rather than an error:

1. **A hand-rolled corner grid.** Several `sim/*/run_*.py --corners` drivers in
   this tree assemble `supply_points()` + `oat_grid("tt", 27.0, ...)` by hand
   instead of calling the shared `corners.ratified_oat_grid()` wrapper, which is
   how a fifth, subtly-different "ratified grid" gets into the tree. The grid
   test below pins this campaign's grid to BOTH the shared helper's output and
   to `sim/sampling-acquisition-settling/`'s own grid -- the campaign whose
   front-end-only residuals this one is meant to be directly comparable with.

2. **A stimulus that drifts from the campaign being compared against.** To
   compare acquisition with the two loads on `TOP_P`/`TOP_N`, both decks
   must emit the established input and SAMPLE waveforms and read each top
   plate at the DR-006 budget and confirm times.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
HANDOFF_DIR = SIM_DIR / "sampling-cdac-handoff"
ACQUISITION_DIR = SIM_DIR / "sampling-acquisition-settling"
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(HANDOFF_DIR))
sys.path.insert(0, str(ACQUISITION_DIR))

from harness import corners as corners_mod  # noqa: E402
import run_handoff as rh  # noqa: E402
import run_acquisition_settling as ras  # noqa: E402


class TestCornerGridIsTheSharedRatifiedGrid(unittest.TestCase):
    def test_grid_is_the_shared_helper_output(self):
        grid = corners_mod.ratified_oat_grid(
            rh.VDD, rh.SUPPLY_TOLERANCE, rh.PROCESS_CORNERS, rh.TEMPS_C
        )
        self.assertEqual(len(grid), 9, "the ratified OAT star is 9 points")
        ids = [corners_mod.corner_id(*point) for point in grid]
        self.assertEqual(ids[0], "tt_27c_1.80v", "baseline is the OAT star centre")
        self.assertEqual(len(set(ids)), 9, "OAT points must be deduplicated")

    def test_grid_matches_the_front_end_only_campaign_point_for_point(self):
        """The comparison this campaign exists to make is only valid if the two
        campaigns sweep the same 9 points."""
        mine = corners_mod.ratified_oat_grid(
            rh.VDD, rh.SUPPLY_TOLERANCE, rh.PROCESS_CORNERS, rh.TEMPS_C
        )
        theirs = corners_mod.ratified_oat_grid(
            ras.VDD, ras.SUPPLY_TOLERANCE, ras.PROCESS_CORNERS, ras.TEMPS_C
        )
        self.assertEqual(mine, theirs)

    def test_axes_are_the_ratified_axes(self):
        self.assertEqual(sorted(rh.TEMPS_C), [-40, 27, 125])
        self.assertEqual(sorted(rh.PROCESS_CORNERS), ["ff", "fs", "sf", "ss", "tt"])
        self.assertEqual(
            corners_mod.supply_points(rh.VDD, rh.SUPPLY_TOLERANCE),
            [1.62, 1.8, 1.98],
        )


class TestAcquisitionStimulus(unittest.TestCase):
    def test_rendered_waveforms_and_fixed_time_probes(self):
        bits = rh.CODE_STATES[rh.CORNERS_CODE_STATE]
        prefixes = (
            "Vinp ",
            "Vinn ",
            "Vsample ",
            "meas tran budget_",
            "meas tran confirm_",
        )
        for vdd in (1.62, 1.8, 1.98):
            expected = [
                "Vinp VINP 0 pwl(0n 0.2 130n 0.2 130.2n 1.6 330n 1.6)",
                "Vinn VINN 0 pwl(0n 1.6 130n 1.6 130.2n 0.2 330n 0.2)",
                (
                    f"Vsample SAMPLE 0 pwl(0n 0 10n 0 10.2n {vdd} 110n {vdd} "
                    f"110.2n 0 160n 0 160.2n {vdd} 310n {vdd} 310.2n 0 330n 0)"
                ),
                "meas tran budget_p find v(TOP_P) at=243.43333333333334n",
                "meas tran confirm_p find v(TOP_P) at=305.0n",
                "meas tran budget_n find v(TOP_N) at=243.43333333333334n",
                "meas tran confirm_n find v(TOP_N) at=305.0n",
            ]
            for runner, deck in (
                ("front end", ras.build_transient("tt", 27.0, vdd)),
                ("handoff", rh.build_acquisition_netlist(bits, "tt", 27.0, vdd)),
            ):
                with self.subTest(runner=runner, vdd=vdd):
                    actual = [
                        line for line in deck.splitlines() if line.startswith(prefixes)
                    ]
                    self.assertEqual(actual, expected)

    def test_campaigns_use_the_same_voltage_references(self):
        self.assertEqual(rh.VCM, ras.VCM)
        self.assertEqual(rh.VDD, ras.VDD)
        self.assertEqual(rh.LSB_DIFF_MV_PROVISIONAL, ras.LSB_DIFF_MV_PROVISIONAL)

    def test_transient_step_ceiling_is_documented_as_the_one_divergence(self):
        """Deliberately different (see TRAN_STEP_NS's own comment): this mode
        reads two fixed-time probes, not sub-ns crossings, and the combined load
        makes the finer ceiling unaffordable for a 9-point grid. Asserted rather
        than left implicit so an accidental convergence back to 0.02 -- or a
        drift to something coarser still -- is visible."""
        self.assertEqual(rh.TRAN_STEP_NS, 0.2)
        self.assertEqual(ras.TRAN_STEP_NS, 0.02)


class TestAcquisitionDeck(unittest.TestCase):
    def _deck(self, **kwargs) -> str:
        return rh.build_acquisition_netlist(
            rh.CODE_STATES[rh.CORNERS_CODE_STATE], "tt", 27.0, 1.8, **kwargs
        )

    def test_returns_a_runnable_looking_deck(self):
        deck = self._deck()
        self.assertIn(".lib", deck)
        self.assertIn(".temp 27.0", deck)
        self.assertTrue(deck.rstrip().endswith(".end"))

    def test_budget_measure_names_cover_both_top_plates(self):
        self.assertEqual(
            sorted(rh.BUDGET_MEASURE_NAMES),
            ["budget_n", "budget_p", "confirm_n", "confirm_p"],
        )

    def test_loads_both_sub_blocks_at_the_same_top_plate_nodes(self):
        """The assembled load is the entire point: the front end's own Csamp
        AND the array's bit caps must both hang on TOP_P/TOP_N."""
        deck = self._deck()
        self.assertIn("XCsamp_p TOP_P BPREF_P", deck)
        self.assertIn("XCsamp_n TOP_N BPREF_N", deck)
        self.assertIn("XCp0 BOT_p0 TOP_P", deck)
        self.assertIn("XCn0 BOT_n0 TOP_N", deck)
        # ...and BPREF_x must stay dead-ended (no source drives it), matching
        # design/sar_adc_top.sch's BPREF_P_NC/BPREF_N_NC wiring.
        for line in deck.splitlines():
            self.assertFalse(
                line.startswith("V") and (" BPREF_P " in line or " BPREF_N " in line),
                f"BPREF_x must not be driven by a testbench source: {line}",
            )

    def test_every_cdac_select_bit_gets_a_complementary_ideal_driver(self):
        deck = self._deck()
        for i in range(9):
            self.assertIn(f"Vselp{i} SELp{i} 0 dc ", deck)
            self.assertIn(f"Vseln{i} SELn{i} 0 dc ", deck)

    def test_supply_scaling_reaches_the_rails_the_corner_point_sets(self):
        deck = rh.build_acquisition_netlist(
            rh.CODE_STATES["prev_code_one"], "ss", -40, 1.62
        )
        self.assertIn("Vdd VDD 0 dc 1.62", deck)
        self.assertIn("Vrefp VREFP 0 dc 1.62", deck)
        self.assertIn("Vrefn VREFN 0 dc 0", deck)
        self.assertIn(".temp -40", deck)
        self.assertIn(".lib", deck)

    def test_tran_step_ceiling_is_overridable(self):
        self.assertIn(f"tran {rh.TRAN_STEP_NS}n", self._deck())
        self.assertIn("tran 0.02n", self._deck(tran_step_ns=0.02))


class TestFragmentCurrencyHelper(unittest.TestCase):
    def test_device_lines_drops_comments_and_the_end_card(self):
        text = "\n".join([
            "* a hand-written provenance header",
            "**.subckt foo A B",
            "*.ipin A",
            "XM1 A B C D sky130_fd_pr__nfet_01v8 L=0.15 W=1",
            "+ m=1",
            "**.ends",
            ".end",
        ])
        self.assertEqual(
            rh._device_lines(text),
            ["XM1 A B C D sky130_fd_pr__nfet_01v8 L=0.15 W=1", "+ m=1"],
        )

    def test_committed_fragments_have_device_content(self):
        """A regression guard on the comparison itself: if the strip ever
        removed everything, assert_fragments_current() would compare two empty
        lists and pass vacuously."""
        for frag in (rh.FE_FRAG, rh.CDAC_FRAG):
            with self.subTest(fragment=frag.name):
                self.assertTrue(rh._device_lines(frag.read_text()))

    def test_schematic_paths_resolve(self):
        for sch in (rh.FE_SCH, rh.CDAC_SCH):
            with self.subTest(schematic=sch.name):
                self.assertTrue(sch.is_file(), f"{sch} must exist to be re-netlisted")


class TestDR027CandidateFragment(unittest.TestCase):
    """issue #1033: the candidate deck is the committed production fragment
    with ONLY the unit-cap plates resized -- switch devices byte-identical,
    exactly 20 caps swapped, and the result identified as experimental."""

    def test_swaps_exactly_twenty_plates_and_announces_itself(self):
        text, n = rh.candidate_cdac_fragment()
        self.assertEqual(n, 20, "9 P-side + 9 N-side bit caps + 2 termination units")
        self.assertIn("EXPERIMENTAL DR-027 CANDIDATE STUDY FRAGMENT", text)
        self.assertEqual(text.count(f"W={rh.CANDIDATE_UNIT_CAP_WL_UM:.4f} "
                                    f"L={rh.CANDIDATE_UNIT_CAP_WL_UM:.4f}"), 20)
        self.assertNotIn(f"W={rh.PRODUCTION_UNIT_CAP_WL_UM:.4f} "
                         f"L={rh.PRODUCTION_UNIT_CAP_WL_UM:.4f}", text)

    def test_every_non_cap_device_line_is_byte_identical(self):
        """The resize-the-plate-only rule, enforced structurally: diffing the
        candidate against the committed fragment (as device/card lines, so
        both hand-written headers are out of the comparison) may show ONLY
        the 20 cap cards' W/L differing."""
        committed = rh._device_lines(rh.CDAC_FRAG.read_text())
        candidate = rh._device_lines(rh.candidate_cdac_fragment()[0])
        self.assertEqual(len(candidate), len(committed))
        diffs = [
            (c, k) for c, k in zip(committed, candidate) if c != k
        ]
        self.assertEqual(len(diffs), 20)
        for c, k in diffs:
            self.assertTrue(k.startswith("XC") and "cap_mim_m3_1" in k)
            self.assertEqual(
                k, c.replace(
                    f"W={rh.PRODUCTION_UNIT_CAP_WL_UM:.4f} "
                    f"L={rh.PRODUCTION_UNIT_CAP_WL_UM:.4f}",
                    f"W={rh.CANDIDATE_UNIT_CAP_WL_UM:.4f} "
                    f"L={rh.CANDIDATE_UNIT_CAP_WL_UM:.4f}",
                ),
            )

    def test_refuses_a_fragment_that_is_not_twenty_production_plates(self):
        """If the production fragment drifts (a different plate count or
        size), the candidate must refuse to be generated rather than
        silently measure something else."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "cdac_array_dut.spice"
            bad.write_text(
                rh.CDAC_FRAG.read_text().replace(
                    f"W={rh.PRODUCTION_UNIT_CAP_WL_UM:.4f} L="
                    f"{rh.PRODUCTION_UNIT_CAP_WL_UM:.4f}",
                    "W=2.0000 L=2.0000", 1,
                )
            )
            saved = rh.CDAC_FRAG
            try:
                rh.CDAC_FRAG = bad
                with self.assertRaises(RuntimeError):
                    rh.candidate_cdac_fragment()
            finally:
                rh.CDAC_FRAG = saved


class TestDR027CandidateStimulusWindows(unittest.TestCase):
    """issue #1033: BOTH DR-006 deadlines must fall inside the active SAMPLE
    pulse #2 and ahead of switch turn-off, and the fast deadline must stay
    at the baseline records' own budget-probe instant so the candidate's
    fast column is corner-for-corner comparable with them."""

    def test_fast_deadline_is_the_baseline_budget_probe_instant(self):
        self.assertAlmostEqual(
            rh.CAND_FAST_AT_NS, rh.BUDGET_PROBE_AT_NS, places=9,
        )
        self.assertAlmostEqual(
            rh.CAND_FAST_AT_NS, rh.TRIG_AT_NS + rh.T_PHASE_WORST_NS, places=9,
        )
        self.assertAlmostEqual(
            rh.CAND_SLOW_AT_NS, rh.TRIG_AT_NS + rh.T_PHASE_SLOW_NS, places=9,
        )

    def test_both_deadlines_and_late_read_are_inside_pulse_two(self):
        # pulse #2 spans T_SAMPLE2_RISE_NS (+ its 0.2 ns edge) to
        # CAND_T_SAMPLE2_FALL_NS; every probe must sit strictly inside it.
        active_from = rh.T_SAMPLE2_RISE_NS + rh.EDGE_TR_NS
        for at in (rh.CAND_FAST_AT_NS, rh.CAND_SLOW_AT_NS, rh.CAND_LATE_AT_NS):
            self.assertGreater(at, active_from)
            self.assertLess(at, rh.CAND_T_SAMPLE2_FALL_NS,
                            "probe must be ahead of switch turn-off")
        # and the late read uses the baseline CONFIRM_AT_NS's own convention
        self.assertAlmostEqual(
            rh.CAND_LATE_AT_NS, rh.CAND_T_SAMPLE2_FALL_NS - 5.0, places=9,
        )
        # the deadline must land with margin, not on the turn-off edge itself
        self.assertGreater(
            rh.CAND_T_SAMPLE2_FALL_NS - rh.CAND_SLOW_AT_NS, 20.0,
        )

    def test_pwl_points_extend_the_pulse_and_inputs_to_the_window_end(self):
        sample, vinp, vinn = rh._candidate_pwl_points()
        self.assertEqual(max(t for t, _v in sample), rh.CAND_TRAN_STOP_NS)
        self.assertEqual(max(t for t, _v in vinp), rh.CAND_TRAN_STOP_NS)
        self.assertEqual(max(t for t, _v in vinn), rh.CAND_TRAN_STOP_NS)
        # SAMPLE pulse #2: normalised 1 between its rise edge and the
        # widened fall, 0 elsewhere after pulse #1 ends.
        def level(points, t):
            pts = sorted(points)
            for (t0, v0), (t1, _v1) in zip(pts, pts[1:]):
                if t0 <= t <= t1:
                    return v0
            return pts[-1][1]
        self.assertEqual(level(sample, rh.CAND_FAST_AT_NS), 1.0)
        self.assertEqual(level(sample, rh.CAND_SLOW_AT_NS), 1.0)
        self.assertEqual(level(sample, rh.CAND_LATE_AT_NS), 1.0)
        self.assertEqual(level(sample, rh.CAND_T_SAMPLE2_FALL_NS + 1.0), 0.0)


class TestDR027CandidateBodyAndRequest(unittest.TestCase):
    def test_body_keeps_the_front_end_and_its_own_sampling_capacitor(self):
        body = rh.build_candidate_body(rh.CORNERS_CODE_STATE)
        self.assertIn("XCsamp_p TOP_P BPREF_P", body)
        self.assertIn("XCsamp_n TOP_N BPREF_N", body)
        # BPREF_x must stay dead-ended (no testbench source drives it)
        for line in body.splitlines():
            self.assertFalse(
                line.startswith(("V", "B")) and (" BPREF_P " in line or " BPREF_N " in line),
                f"BPREF_x must not be driven: {line}",
            )

    def test_body_is_a_circuit_body_not_a_deck(self):
        body = rh.build_candidate_body()
        for line in body.splitlines():
            self.assertFalse(
                line.startswith((".control", ".tran", ".meas", ".lib", ".temp", ".end")),
                f"circuit body must not carry analysis cards: {line}",
            )

    def test_supply_scaled_sources_replace_corner_baked_levels(self):
        body = rh.build_candidate_body()
        self.assertIn(f"{rh.CAND_SUPPLY_KEY} VDD 0 DC {rh.VDD}", body)
        self.assertIn("Bsample SAMPLE 0 V=v(SMPN)*v(VDD)", body)
        self.assertIn("Bvrefp VREFP 0 V=v(VDD)", body)
        # the baseline campaign's fixed levels stay fixed
        self.assertIn(f"Vvcm VCM 0 DC {rh.VCM}", body)

    def test_previous_code_drivers_present_for_every_bit(self):
        body = rh.build_candidate_body(rh.CORNERS_CODE_STATE)
        for i in range(9):
            self.assertTrue(
                f"Bselp{i} SELp{i} " in body or f"Vselp{i} SELp{i} " in body
            )
            self.assertTrue(
                f"Bseln{i} SELn{i} " in body or f"Vseln{i} SELn{i} " in body
            )

    def test_steps_carry_the_two_deadlines_with_documented_ceilings(self):
        steps = {s["name"]: s for s in rh.candidate_analysis_steps()}
        self.assertEqual(
            steps["fast"]["analysis"]["args"],
            f"{rh.TRAN_STEP_NS:g}n {rh.CAND_FAST_TRAN_STOP_NS:g}n",
        )
        self.assertEqual(
            steps["slow"]["analysis"]["args"],
            f"{rh.CAND_SLOW_TRAN_STEP_NS:g}n {rh.CAND_TRAN_STOP_NS:g}n",
        )
        fast_spice = " ".join(m["spice"] for m in steps["fast"]["measurements"])
        slow_spice = " ".join(m["spice"] for m in steps["slow"]["measurements"])
        self.assertIn(f"at={rh.CAND_FAST_AT_NS:.6f}n", fast_spice)
        self.assertIn(f"at={rh.CAND_SLOW_AT_NS:.6f}n", slow_spice)
        self.assertIn(f"at={rh.CAND_LATE_AT_NS:.6f}n", slow_spice)
        # measurement names never collide with node names (klt-sim #5446)
        nodes = set()
        for line in rh.build_candidate_body().splitlines():
            if line and line[0].isalpha() and not line.startswith("*"):
                nodes.update(line.split()[1].split("[")[0].split(":"))
        for s in steps.values():
            for m in s["measurements"]:
                self.assertNotIn(m["name"], nodes)

    def test_request_shapes_the_oat_grid_via_exclude(self):
        cids = rh.candidate_corner_ids()
        req = rh.build_candidate_request("tb.spice", cids)
        self.assertEqual(len(cids), 9)
        self.assertEqual(len(req["exclude"]), 45 - 9)
        self.assertEqual(len(req["corners"]["process"]), 5)
        self.assertEqual(req["corners"]["supply_v"], {rh.CAND_SUPPLY_KEY: [1.62, 1.8, 1.98]})


if __name__ == "__main__":
    unittest.main()


class TestCandidateReviewFixes(unittest.TestCase):
    """Regressions for the PR #1041 review findings."""

    def test_candidate_body_grounds_vss(self):
        body = rh.build_candidate_body()
        self.assertIn("Vvss VSS 0 dc 0", body)

    def _grid(self, cids, complete_ids):
        grid = {}
        for c in cids:
            row = {"complete": c in complete_ids}
            for st in ("fast", "slow"):
                row[f"{st}_diff_err_mv"] = 0.0
                row[f"{st}_p_err_mv"] = 0.0
                row[f"{st}_n_err_mv"] = 0.0
            grid[c] = row
        return grid

    def test_positive_verdict_requires_full_corner_set(self):
        cids = ["a", "b", "c"]
        bt = {"a": [{"t99_ns": 1.0, "test_bit": 0, "direction": "rise"}]}
        full = "\n".join(rh.verdict_lines(self._grid(cids, cids), cids, "r", bt, cids))
        self.assertIn("HOLDS", full)
        sub = "\n".join(rh.verdict_lines(self._grid(cids, ["a"]), cids, "r", bt, cids))
        self.assertNotIn(": HOLDS", sub)
        self.assertIn("incomplete evidence", sub)
        nobt = "\n".join(rh.verdict_lines(self._grid(cids, cids), cids, "r", bt, []))
        self.assertNotIn(": HOLDS", nobt)
        self.assertIn("incomplete evidence", nobt)

    def test_per_endpoint_worst_node_and_sign(self):
        vals = {}
        for st, p, n in (("fast", -2e-3, -1e-3), ("slow", -1e-5, -5e-5)):
            vals[f"{st}.acq_{st}_p"] = rh.V_FINAL_P + p
            vals[f"{st}.acq_{st}_n"] = rh.V_FINAL_N + n
        vals["slow.acq_late_p"] = rh.V_FINAL_P
        vals["slow.acq_late_n"] = rh.V_FINAL_N
        row = rh.candidate_corner_row(vals, "zero")
        self.assertEqual(row["worst_node_fast"], "p")
        self.assertEqual(row["worst_node_slow"], "n")
        self.assertAlmostEqual(row["fast_p_err_mv"], -2.0, places=6)  # read - target


class TestInputsFence(unittest.TestCase):
    def test_changed_inputs_set_stale_report_aside(self):
        import tempfile
        from harness import klt_sim
        with tempfile.TemporaryDirectory() as t:
            wd = Path(t)
            self.assertFalse(klt_sim.write_inputs(wd, {"tb.spice": "A", "request.json": "{}"}))
            (wd / "report.json").write_text("{}")
            self.assertFalse(klt_sim.write_inputs(wd, {"tb.spice": "A", "request.json": "{}"}))
            self.assertTrue((wd / "report.json").is_file())
            self.assertTrue(klt_sim.write_inputs(wd, {"tb.spice": "B", "request.json": "{}"}))
            self.assertFalse((wd / "report.json").exists())
            self.assertEqual(len(list(wd.glob("report.stale-*.json"))), 1)

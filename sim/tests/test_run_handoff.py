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


if __name__ == "__main__":
    unittest.main()

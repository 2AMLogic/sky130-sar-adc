"""PDK-free deck-builder tests for runners not covered by #591 (issue #593).

Same failure class as sim/tests/test_run_hold_kick.py (#296): a shared-helper
migration can leave a deck builder calling a deleted name, and nothing notices
until someone runs ngspice with the PDK. Each test below CALLS the builder with
a stub PdkInfo (no ngspice, no PDK) and asserts the deck's structure. Covers:

  - sim/cdac-array-transfer/run_transfer.py  build_netlist
  - sim/cdac-array-transfer/run_mc.py        build_netlist
  - sim/sampling-acquisition-settling/run_acquisition_settling.py  build_transient
  - sim/comparator-decision/run.py  _kickback_deck, _pickoff_deck, _noise_deck
    plus a table test of RegenCornerPoint.classify()'s five outcomes.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))
for _d in ("cdac-array-transfer", "sampling-acquisition-settling", "comparator-decision"):
    sys.path.insert(0, str(SIM_DIR / _d))

import run as cd  # noqa: E402
import run_acquisition_settling as acq  # noqa: E402
import run_mc  # noqa: E402
import run_transfer  # noqa: E402


class _Info:
    ngspice_lib = "/stub/sky130.lib.spice"
    found = True


def _assert_tran_deck(test, deck, corner):
    test.assertIsInstance(deck, str)
    test.assertTrue(deck.endswith(".end\n"))
    test.assertIn(f".lib {_Info.ngspice_lib} {corner}", deck)
    test.assertIn(".control", deck)
    test.assertIn(".endc", deck)


class TestCdacArrayTransfer(unittest.TestCase):
    def test_run_transfer_build_netlist(self):
        deck = run_transfer.build_netlist(_Info(), "tt", 27.0, 1.8)
        _assert_tran_deck(self, deck, "tt")
        self.assertIn(".param vdd_val = 1.8", deck)
        self.assertIn(f"tran {run_transfer.TRAN_STEP} {run_transfer.SETTLE_T}", deck)
        self.assertIn(run_transfer.FRAGMENT.read_text(), deck)
        for name in run_transfer.measure_names():
            self.assertIn(f"meas tran {name} find", deck)

    def test_run_mc_build_netlist(self):
        deck = run_mc.build_netlist(_Info(), "tt_mm", 27.0, 1.8, 7)
        _assert_tran_deck(self, deck, "tt_mm")
        self.assertIn(".option rndseed=7", deck)
        self.assertIn(f"tran {run_mc.TRAN_STEP} {run_mc.SETTLE_T}", deck)
        for name in run_mc.measure_names():
            self.assertIn(f"meas tran {name} find", deck)

    def test_run_mc_build_netlist_without_seed_omits_rndseed(self):
        deck = run_mc.build_netlist(_Info(), "tt", 27.0, 1.8, None)
        self.assertNotIn("rndseed", deck.replace("seed=None", ""))


class TestAcquisitionSettling(unittest.TestCase):
    def test_build_transient(self):
        real = acq.pdk.resolve
        acq.pdk.resolve = lambda: _Info()
        self.addCleanup(setattr, acq.pdk, "resolve", real)
        deck = acq.build_transient()
        _assert_tran_deck(self, deck, acq.CORNER)
        self.assertIn(f"tran {acq.TRAN_STEP_NS}n {acq.TRAN_STOP_NS}n", deck)
        self.assertIn("Vsample SAMPLE 0 pwl(", deck)
        for name in acq.TRIG_TARG_NAMES + acq.MEASURE_NAMES:
            self.assertIn(f"meas tran {name} ", deck)


class TestComparatorDecks(unittest.TestCase):
    def test_kickback_deck(self):
        deck = cd._kickback_deck(_Info(), "tt", 27.0, 5.0, "kb")
        _assert_tran_deck(self, deck, "tt")
        self.assertIn("Rsrc_p VINP_IDEAL VINP", deck)
        self.assertIn("wrdata kb.csv", deck)
        self.assertIn(cd._dut_lines(), deck)

    def test_kickback_deck_dut_text_override(self):
        deck = cd._kickback_deck(_Info(), "tt", 27.0, 5.0, "kb", dut_text="* MARKER_DUT")
        self.assertIn("* MARKER_DUT", deck)

    def test_pickoff_deck(self):
        deck = cd._pickoff_deck(_Info(), "tt", 27.0, 1.0, "po")
        _assert_tran_deck(self, deck, "tt")
        self.assertIn(f"tran 0.002n {cd.PICKOFF_TSTOP_NS}n", deck)
        self.assertIn("wrdata po.csv", deck)
        self.assertNotIn(".option rndseed", deck)
        seeded = cd._pickoff_deck(_Info(), "tt", 27.0, 0.0, "po", rndseed=3)
        self.assertIn(".option rndseed=3", seeded)

    def test_noise_deck(self):
        deck = cd._noise_deck(_Info(), "tt", 27.0)
        _assert_tran_deck(self, deck, "tt")
        self.assertIn("option sparse", deck)
        self.assertIn("noise v(dip,din) Vinp dec", deck)
        self.assertIn("print inoise_total onoise_total", deck)


class TestRegenCornerPointClassify(unittest.TestCase):
    SUPPLY = 1.8

    def _pt(self, vindiff_mv=1.0, regen=None, pre=0.0, final=None):
        return cd.RegenCornerPoint(
            corner="tt", temp_c=27.0, supply_v=self.SUPPLY, vindiff_mv=vindiff_mv,
            regen_time_ns=regen, log_text="", pre_edge_diff_v=pre, final_diff_v=final,
        )

    def test_five_outcomes(self):
        big = 0.9 * self.SUPPLY
        table = [
            ("NO-DATA", self._pt(pre=None)),
            ("RESET-NOT-HELD", self._pt(pre=big, regen=0.0)),
            ("CONTROL-OK", self._pt(vindiff_mv=0.0)),
            ("DECIDED", self._pt(regen=0.4)),
            ("WRONG-POLARITY", self._pt(final=-big)),
            ("NO-DECISION", self._pt(final=0.0)),
        ]
        for expected, point in table:
            with self.subTest(expected=expected):
                self.assertEqual(point.classify(), expected)


if __name__ == "__main__":
    unittest.main()

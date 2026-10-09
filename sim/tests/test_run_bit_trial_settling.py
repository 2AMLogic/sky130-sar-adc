"""PDK-free deck-builder call test for sim/cdac-bit-trial-settling/run_bit_trial_settling.py (issue #591).

Same failure class as issue #296 (see test_run_hold_kick.py): a shared-helper
migration can leave a builder calling an undefined name, which only surfaces
when someone runs ngspice with the PDK. This test actually calls the builder
and checks the deck structure; no ngspice, no PDK."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import pdk  # noqa: E402

RUNNER = SIM_DIR / "cdac-bit-trial-settling/run_bit_trial_settling.py"
_spec = importlib.util.spec_from_file_location("run_bit_trial_settling_under_test", RUNNER)
rt = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rt
_spec.loader.exec_module(rt)


class TestBuildTransient(unittest.TestCase):
    def test_both_directions_return_deck_and_analytics(self):
        for direction in ("fall", "rise"):
            with self.subTest(direction=direction):
                deck, analytics = rt.build_transient(test_bit=8, direction=direction)
                self.assertIsInstance(deck, str)
                self.assertIn(".control", deck)
                self.assertIn("\ntran ", deck)
                self.assertIn(".end", deck)
                self.assertIn(".lib", deck)
                self.assertIsInstance(analytics, dict)
                self.assertTrue(analytics)

    def test_non_default_corner_and_window(self):
        deck, _ = rt.build_transient(
            test_bit=0, direction="rise", corner="ss", temp_c=-40.0,
            vdd=1.62, tran_stop_ns=rt.CORNERS_TRAN_STOP_NS,
        )
        self.assertIn(".control", deck)
        self.assertIn("\ntran ", deck)

    def test_bad_direction_raises_value_error(self):
        with self.assertRaises(ValueError):
            rt.build_transient(test_bit=8, direction="sideways")


if __name__ == "__main__":
    unittest.main()

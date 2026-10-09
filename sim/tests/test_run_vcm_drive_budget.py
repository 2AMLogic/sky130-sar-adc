"""PDK-free deck-builder call test for sim/vcm-drive-budget/run_vcm_drive_budget.py (issue #591).

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

RUNNER = SIM_DIR / "vcm-drive-budget/run_vcm_drive_budget.py"
_spec = importlib.util.spec_from_file_location("run_vcm_drive_budget_under_test", RUNNER)
rt = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rt
_spec.loader.exec_module(rt)


class TestBuildTransient(unittest.TestCase):
    def test_returns_deck_with_tran(self):
        deck = rt.build_transient(
            vinp=1.6, vinn=0.2, sample_width_ns=100.0, r_source_ohm=1000.0,
        )
        self.assertIsInstance(deck, str)
        self.assertIn(".control", deck)
        self.assertIn("\ntran ", deck)
        self.assertIn(".end", deck)
        self.assertIn(".lib", deck)

    def test_with_decoupling_cap_and_corner(self):
        deck = rt.build_transient(
            vinp=1.6, vinn=0.2, sample_width_ns=100.0, r_source_ohm=1000.0,
            c_decouple_f=1e-12, corner="ss", temp_c=125.0, vdd=1.62,
        )
        self.assertIn(".control", deck)
        self.assertIn("\ntran ", deck)


if __name__ == "__main__":
    unittest.main()

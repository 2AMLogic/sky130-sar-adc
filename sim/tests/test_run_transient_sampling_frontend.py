"""PDK-free deck-builder call test for sim/sampling-frontend/run_transient.py (issue #591).

Same failure class as issue #296 (see test_run_hold_kick.py): a shared-helper
migration can leave a builder calling an undefined name, which only surfaces
when someone runs ngspice with the PDK. This test actually calls the builder
and checks the deck structure; no ngspice, no PDK."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))


RUNNER = SIM_DIR / "sampling-frontend/run_transient.py"
_spec = importlib.util.spec_from_file_location("run_transient_under_test", RUNNER)
rt = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rt
_spec.loader.exec_module(rt)


class TestBuildNetlist(unittest.TestCase):
    def test_returns_deck_with_tran(self):
        deck = rt.build_netlist(vinp=1.6, vinn=0.2, corner="tt")
        self.assertIsInstance(deck, str)
        self.assertIn(".control", deck)
        self.assertIn("\ntran ", deck)
        self.assertIn(".end", deck)
        self.assertIn(".lib", deck)

    def test_other_corner_and_temp(self):
        deck = rt.build_netlist(vinp=0.2, vinn=1.6, corner="ff", temp_c=-40.0)
        self.assertIn(".temp -40.0", deck)


if __name__ == "__main__":
    unittest.main()

"""Regression test for sim/sampling-frontend/run_hold_kick.py's deck-builder
functions -- pure text generation, no ngspice/PDK required (mirrors
sim/tests/test_harness.py's PDK-free unit-test convention; see
sim/selftest.sh stage 1/4).

Issue #296: PR #289 (issue #205) consolidated every deck-builder's own
``_preamble()`` helper onto the shared ``toolchain.deck_preamble()`` and
deleted the local ``def _preamble(...)`` from this file, but migrated only
the ``build_transient()`` call site -- leaving ``build_ac_capacitance()``
and ``build_full_load_transient()`` calling the now-undefined ``_preamble``
name. Both are live, CLI-reachable via this script's own ``argparse
choices=`` list (``cap-extract`` and ``full-load``), so the bug was a
``NameError`` the instant either experiment ran -- not caught by any
existing test because nothing actually called these two functions.

This module closes that gap by calling every ``build_*`` deck assembler in
sim/sampling-frontend/run_hold_kick.py at least once and asserting each
returns deck text, rather than raising."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
HOLD_KICK_DIR = SIM_DIR / "sampling-frontend"
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(HOLD_KICK_DIR))

import run_hold_kick as hk  # noqa: E402


class TestDeckBuildersDoNotRaise(unittest.TestCase):
    """Every experiment's netlist-assembly function must at least run to
    completion and hand back a non-empty deck -- the class of bug #296 fixed
    (an undefined name inside the function body) is only caught by actually
    calling it, not merely importing the module."""

    def test_build_transient_returns_a_deck(self):
        deck = hk.build_transient(vinp=1.6, vinn=0.2)
        self.assertIsInstance(deck, str)
        self.assertIn(".lib", deck)
        self.assertIn(".end", deck)

    def test_build_ac_capacitance_returns_a_deck(self):
        # Regression for #296: this call site referenced the deleted
        # module-local _preamble() and raised NameError before the fix.
        bias = {node: 0.9 for node in hk.DUT_NODES}
        deck = hk.build_ac_capacitance(bias=bias, driven=["TOP_P", "TOP_N"])
        self.assertIsInstance(deck, str)
        self.assertIn(".lib", deck)
        self.assertIn("ac lin 1", deck)

    def test_build_full_load_transient_returns_a_deck(self):
        # Regression for #296: this call site also referenced the deleted
        # module-local _preamble() and raised NameError before the fix.
        deck = hk.build_full_load_transient(
            vinp=1.6, vinn=0.2, code_bits=[0] * 9,
        )
        self.assertIsInstance(deck, str)
        self.assertIn(".lib", deck)
        self.assertIn(".end", deck)


if __name__ == "__main__":
    unittest.main()

"""Unit test for sim/enob-estimate/run_enob.py's `achieved_enob()` -- pure
math, no ngspice/PDK required (mirrors sim/tests/test_harness.py's PDK-free
unit-test convention; see sim/selftest.sh stage 1/4).

`achieved_enob()` is documented as the algebraic inverse of
spec/dr-003-support/calc.py's `total_budget()` (target ENOB -> required
noise budget). This test re-implements `total_budget()`'s formula
independently (not by importing calc.py, whose top-level prints make it
unsuitable as a library import) and checks the round trip: for a range of
target ENOB values, `total_budget()` -> `achieved_enob()` must recover the
original target exactly. A round-trip failure here would mean the two
scripts' formulas have silently diverged -- exactly the failure mode a
"combine with the ratified/DR-003 methodology, don't reinvent it" claim
needs caught mechanically, not by inspection."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
ENOB_DIR = SIM_DIR / "enob-estimate"
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(ENOB_DIR))

from run_enob import LSB_V, achieved_enob, sigma_quant  # noqa: E402


def _total_budget_reference(lsb: float, enob_target: float, n_bits: int = 10) -> float:
    """Independent re-implementation of spec/dr-003-support/calc.py's
    total_budget(), for round-trip testing only."""
    sq = sigma_quant(lsb)
    db_backoff = 6.02 * (n_bits - enob_target)
    power_ratio = 10 ** (db_backoff / 10)
    n_nonquant_over_n_quant = power_ratio - 1
    return sq * math.sqrt(n_nonquant_over_n_quant)


class TestAchievedEnobRoundTrip(unittest.TestCase):
    def test_round_trips_dr003_targets(self):
        for target in (8.0, 8.5, 9.0, 9.5, 10.0):
            sigma = _total_budget_reference(LSB_V, target)
            back = achieved_enob(sigma, LSB_V)
            self.assertAlmostEqual(back, target, places=9)

    def test_zero_nonquant_noise_gives_ideal_enob(self):
        # With sigma_nonquant = 0, achieved ENOB must equal N bits exactly
        # (an ideal quantizer's SNR IS the N-bit ideal).
        self.assertAlmostEqual(achieved_enob(0.0, LSB_V, n_bits=10), 10.0, places=9)

    def test_more_noise_means_fewer_bits(self):
        low = achieved_enob(0.1e-3, LSB_V)
        high = achieved_enob(1.0e-3, LSB_V)
        self.assertGreater(low, high)


if __name__ == "__main__":
    unittest.main()

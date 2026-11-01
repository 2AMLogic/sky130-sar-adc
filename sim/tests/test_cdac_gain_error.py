"""Unit tests for run_mc.py's mismatch gain-error statistic (issue #756).
Pure arithmetic on synthetic endpoints / committed logs; no ngspice."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
CDAC_DIR = SIM_DIR / "cdac-array-transfer"
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(CDAC_DIR))

from run_mc import (  # noqa: E402
    ENDPOINT_HI, ENDPOINT_LO, RATIFIED_LSB_V, Draw, McResult,
    gain_error_lsb, gain_error_summary, reanalyze_from_logs,
)

SOURCE_RECORD_ID = "20261001-124049-5207381"


def _draw(seed, v_lo, v_hi):
    return Draw(seed=seed, vdiff={ENDPOINT_LO: v_lo, ENDPOINT_HI: v_hi}, dnl_lsb={}, inl_lsb={},
                dnl_max_lsb=0.0, inl_max_lsb=0.0, log_text="")


def _result(mm, plain):
    return McResult(seed=1, n=len(mm), corner="tt", mismatch_corner="tt_mm", draws=mm, negctrl=plain)


class TestGainError(unittest.TestCase):
    def test_one_lsb_span_deviation(self):
        plain = _draw(1, 0.0, 3.0)
        mm = _draw(1, 0.0, 3.0 + RATIFIED_LSB_V)
        self.assertAlmostEqual(gain_error_lsb(mm, plain), 1.0, places=9)

    def test_sign_negative_when_span_shrinks(self):
        self.assertLess(gain_error_lsb(_draw(1, 0.0, 2.99), _draw(1, 0.0, 3.0)), 0)

    def test_systematic_offset_cancels(self):
        # a common offset in both spans (systematic term) must not appear
        self.assertEqual(gain_error_lsb(_draw(1, 0.1, 3.1), _draw(1, 0.1, 3.1)), 0.0)

    def test_stdev_of_known_set(self):
        plain = [_draw(i, 0.0, 3.0) for i in range(4)]
        mm = [_draw(i, 0.0, 3.0 + e * RATIFIED_LSB_V) for i, e in enumerate([-1, 1, -1, 1])]
        s = gain_error_summary(_result(mm, plain))
        self.assertEqual(s["n_used"], 4)
        self.assertAlmostEqual(s["mean_lsb"], 0.0, places=9)
        self.assertAlmostEqual(s["stdev_lsb"], math.sqrt(4 / 3), places=9)  # n-1 stdev
        self.assertAlmostEqual(s["three_sigma_lsb"], 3 * math.sqrt(4 / 3), places=9)

    def test_plain_corner_stdev_exactly_zero(self):
        plain = [_draw(i, 0.0, 3.0) for i in range(5)]
        s = gain_error_summary(_result(list(plain), plain))
        self.assertEqual(s["stdev_lsb"], 0.0)

    def test_missing_endpoint_reported_not_dropped_silently(self):
        plain = [_draw(i, 0.0, 3.0) for i in range(3)]
        mm = [_draw(0, 0.0, 3.0), _draw(1, 0.0, float("nan")), _draw(2, 0.0, 3.0)]
        s = gain_error_summary(_result(mm, plain))
        self.assertEqual(s["missing_seeds"], [1])
        self.assertEqual(s["n_used"] + len(s["missing_seeds"]), 3)

    def test_committed_campaign(self):
        if not (CDAC_DIR / "mc-draws" / SOURCE_RECORD_ID).is_dir():
            self.skipTest("source mc-draws not present")
        s = gain_error_summary(reanalyze_from_logs(SOURCE_RECORD_ID))
        self.assertEqual(s["n_used"], 40)
        self.assertEqual(s["missing_seeds"], [])
        self.assertEqual(len(s["plain_span_v"]), 1)  # negative control: one identical plain span
        self.assertAlmostEqual(s["stdev_lsb"], 0.00931, places=5)


if __name__ == "__main__":
    unittest.main()

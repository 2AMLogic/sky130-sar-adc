"""Unit test for sim/cdac-array-transfer/run_mc.py's `reanalyze_from_logs()`
(issue #129) -- pure log re-parsing, NO ngspice/PDK required (mirrors
sim/tests/test_harness.py's PDK-free unit-test convention; see
sim/selftest.sh stage 1/4).

`reanalyze_from_logs()` re-derives DNL/INL statistics from a PRIOR record's
already-committed `mc-draws/<record-id>/*.log` files without re-running
ngspice -- this is the mechanism DR-007 (issue #129) uses to evidence a
candidate revised INL/DNL target against the SAME draws issue #29 already
collected. This test asserts the reanalysis reproduces issue #29's own
committed record (`sim/cdac-array-transfer/records/20260828-005006-0c70212.md`)
exactly: a divergence here would mean the reanalysis path silently computes
different numbers than the original run, undermining DR-007's evidence."""

from __future__ import annotations

import statistics
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
CDAC_DIR = SIM_DIR / "cdac-array-transfer"
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(CDAC_DIR))

from run_mc import reanalyze_from_logs  # noqa: E402

SOURCE_RECORD_ID = "20260828-005006-0c70212"


class TestReanalyzeFromLogs(unittest.TestCase):
    def setUp(self):
        draws_dir = CDAC_DIR / "mc-draws" / SOURCE_RECORD_ID
        if not draws_dir.is_dir():
            self.skipTest(f"source mc-draws directory not present: {draws_dir}")

    def test_reproduces_issue_29_recorded_statistics(self):
        result = reanalyze_from_logs(SOURCE_RECORD_ID)
        self.assertEqual(result.n, 40)
        self.assertEqual(result.source_record_id, SOURCE_RECORD_ID)
        self.assertEqual(result.mismatch_corner, "tt_mm")

        dnl = [d.dnl_max_lsb for d in result.draws]
        inl = [d.inl_max_lsb for d in result.draws]

        # From sim/cdac-array-transfer/records/20260828-005006-0c70212.md's
        # own "DNL/INL distributions" table (mean/stdev/min/max, 4 s.f.).
        self.assertAlmostEqual(statistics.fmean(dnl), 0.7833, places=4)
        self.assertAlmostEqual(statistics.pstdev(dnl), 0.3083, places=4)
        self.assertAlmostEqual(min(dnl), 0.3275, places=4)
        self.assertAlmostEqual(max(dnl), 1.9716, places=4)

        self.assertAlmostEqual(statistics.fmean(inl), 0.7191, places=4)
        self.assertAlmostEqual(statistics.pstdev(inl), 0.2058, places=4)
        self.assertAlmostEqual(min(inl), 0.3818, places=4)
        self.assertAlmostEqual(max(inl), 1.3147, places=4)

    def test_negative_control_reproduces_zero_spread(self):
        result = reanalyze_from_logs(SOURCE_RECORD_ID)
        dnl_neg = [d.dnl_max_lsb for d in result.negctrl]
        inl_neg = [d.inl_max_lsb for d in result.negctrl]
        self.assertEqual(statistics.pstdev(dnl_neg), 0.0)
        self.assertEqual(statistics.pstdev(inl_neg), 0.0)

    def test_missing_source_record_raises(self):
        with self.assertRaises(FileNotFoundError):
            reanalyze_from_logs("no-such-record-id")


if __name__ == "__main__":
    unittest.main()

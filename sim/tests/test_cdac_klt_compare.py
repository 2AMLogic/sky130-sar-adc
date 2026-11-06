"""Unit test for sim/cdac-array-transfer/compare_klt_envelope.py (issue #564):
hand-made envelope, no ngspice/klt required."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
CDAC_DIR = SIM_DIR / "cdac-array-transfer"
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(CDAC_DIR))

import compare_klt_envelope as cmp  # noqa: E402

CORNERS = [("tt", 27.0, 1.8), ("ss", 27.0, 1.8)]


def _baseline():
    return {
        f"{p}_{t:g}c_{v:.2f}v": {n: 0.9 + 0.01 * i for i, n in enumerate(cmp.NAMES)}
        for p, t, v in CORNERS
    }


def _report(baseline, bump=None, drop=None):
    corners = []
    for p, t, v in CORNERS:
        cid = f"{p}_{t:g}c_{v:.2f}v"
        meas = [{"name": n, "value": x} for n, x in baseline[cid].items()]
        if bump and bump[0] == cid:
            for m in meas:
                if m["name"] == bump[1]:
                    m["value"] += bump[2]
        if drop and drop == cid:
            meas = meas[:-1]
        corners.append({"process": p, "temperature_c": t, "params": {"vdd_val": v}, "measurements": meas})
    return {"corners": corners}


class CompareTest(unittest.TestCase):
    def test_pass(self):
        b = _baseline()
        r = cmp.compare(_report(b), b)
        self.assertTrue(r["passed"])
        self.assertEqual(r["pairs_compared"], 20)

    def test_exactly_at_tolerance_passes(self):
        b = _baseline()
        r = cmp.compare(_report(b, bump=("tt_27c_1.80v", "vtop_p_0", 1.5e-5)), b)
        self.assertTrue(r["passed"])

    def test_fail_beyond_tolerance(self):
        b = _baseline()
        r = cmp.compare(_report(b, bump=("tt_27c_1.80v", "vtop_p_0", 5e-5)), b)
        self.assertFalse(r["passed"])
        self.assertEqual(r["max_at"], "tt_27c_1.80v/vtop_p_0")

    def test_missing_measurement_fails(self):
        b = _baseline()
        r = cmp.compare(_report(b, drop="ss_27c_1.80v"), b)
        self.assertFalse(r["passed"])

    def test_corner_set_mismatch_fails(self):
        b = _baseline()
        rep = _report(b)
        rep["corners"].pop()
        self.assertFalse(cmp.compare(rep, b)["passed"])

    def test_nonfinite_fails(self):
        b = _baseline()
        rep = _report(b)
        rep["corners"][0]["measurements"][0]["value"] = float("nan")
        self.assertFalse(cmp.compare(rep, b)["passed"])

    def test_failed_batch_envelope_fails(self):
        b = _baseline()
        rep = _report(b)
        for c in rep["corners"]:
            for m in c["measurements"]:
                m["value"] = None
        self.assertFalse(cmp.compare(rep, b)["passed"])


if __name__ == "__main__":
    unittest.main()

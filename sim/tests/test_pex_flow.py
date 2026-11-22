"""Corner IDs emitted by klt for the analog PEX reports."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "layout" / "bin"))

import pex_flow


class CornerIdTests(unittest.TestCase):
    def test_bare_vdd(self):
        self.assertEqual(
            pex_flow.parse_corner_id("tt/1.620V/-40C"), ("tt", -40, {"vdd": 1.62})
        )

    def test_named_supplies(self):
        self.assertEqual(
            pex_flow.parse_corner_id("ff/vcm=0.900_vdd=1.800V/27C"),
            ("ff", 27, {"vcm": 0.9, "vdd": 1.8}),
        )

    def test_malformed_supply_is_rejected(self):
        for supplies in ("missing", "vcm=0.900_vdd=bad", "1.620junk", "vdd=1.8_vdd=1.62"):
            with self.subTest(supplies=supplies), self.assertRaises(pex_flow.PexFlowError):
                pex_flow.parse_corner_id(f"tt/{supplies}V/27C")

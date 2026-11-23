"""Unit coverage for layout/bin/pex_flow.py's shared PEX helpers."""

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


class RatifiedOatPointsTests(unittest.TestCase):
    def test_nine_point_star_with_center_and_oat_legs(self):
        pts = pex_flow.ratified_oat_points({})
        self.assertEqual(len(pts), 9)
        rails = {(p.process, p.temp_c, p.supply_v) for p in pts}
        self.assertIn(("tt", 27.0, 1.8), rails)
        for proc in ("ss", "ff", "sf", "fs"):
            self.assertIn((proc, 27.0, 1.8), rails)
        for temp in (-40.0, 125.0):
            self.assertIn(("tt", temp, 1.8), rails)
        for v in (1.62, 1.98):
            self.assertIn(("tt", 27.0, v), rails)

    def test_rail_always_present_under_vdd(self):
        for p in pex_flow.ratified_oat_points({}):
            self.assertEqual(p.supply_sources["vdd"], p.supply_v)

    def test_paired_sources_track_their_rail_in_order(self):
        pts = pex_flow.ratified_oat_points(
            {"vinp": lambda v: round(v / 2, 6), "vinn": lambda v: round(v / 2 - 0.005, 6)}
        )
        for p in pts:
            self.assertEqual(list(p.supply_sources), ["vdd", "vinp", "vinn"])
            self.assertEqual(p.supply_sources["vinp"], round(p.supply_v / 2, 6))
            self.assertEqual(p.supply_sources["vinn"], round(p.supply_v / 2 - 0.005, 6))


class NetTableTests(unittest.TestCase):
    EXTRACT_JSON = {
        "parasitics": {
            "nets": [
                {
                    "net": "OUTP",
                    "resistance_ohm": 12.5,
                    "capacitance_ff": 1.25,
                    "coupled": [
                        {"capacitance_ff": 0.5},
                        {"capacitance_ff": 0.25},
                    ],
                },
                {"net": "OUTN", "resistance_ohm": 13.0, "capacitance_ff": 2.0},
                {"net": "VDD", "resistance_ohm": 0.1, "capacitance_ff": 100.0},
            ]
        }
    }

    def test_wanted_nets_with_and_without_coupled_terms(self):
        table = pex_flow.net_table(self.EXTRACT_JSON, {"OUTP", "OUTN"})
        self.assertEqual(set(table), {"OUTP", "OUTN"})
        self.assertEqual(
            table["OUTP"],
            {
                "r_ohm": 12.5,
                "c_ground_ff": 1.25,
                "c_coupled_total_ff": 0.75,
                "c_total_ff": 2.0,
            },
        )
        self.assertEqual(
            table["OUTN"],
            {
                "r_ohm": 13.0,
                "c_ground_ff": 2.0,
                "c_coupled_total_ff": 0,
                "c_total_ff": 2.0,
            },
        )

    def test_escaped_net_names_are_matched_after_unescaping(self):
        extract_json = {
            "parasitics": {
                "nets": [
                    {
                        "net": "\\OUT_P\\",
                        "resistance_ohm": 1.0,
                        "capacitance_ff": 3.0,
                    }
                ]
            }
        }
        table = pex_flow.net_table(extract_json, {"OUT_P"})
        self.assertEqual(set(table), {"OUT_P"})
        self.assertEqual(table["OUT_P"]["c_total_ff"], 3.0)

    def test_absent_wanted_net_is_simply_missing(self):
        self.assertEqual(pex_flow.net_table(self.EXTRACT_JSON, {"NOWHERE"}), {})

"""Unit coverage for layout/bin/pex_flow.py's shared PEX helpers."""

import dataclasses
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "layout" / "bin"))

import pex_flow

FAKE_PDK = pex_flow.pdk.PdkInfo(
    root=Path("/pdkroot"),
    variant="sky130A",
    variant_dir=Path("/pdkroot/sky130A"),
    ngspice_lib=Path("/pdkroot/sky130A/libs.tech/combined/sky130.lib.spice"),
    open_pdks_commit_expected="0" * 40,
    found=True,
)


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


class KltPexArgvTests(unittest.TestCase):
    def test_shared_argv_pinned_deck_and_absolute_scratch_paths(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            argv = pex_flow.klt_pex_argv(
                "/abs/gds/cdac_array.gds",
                "pex_request.json",
                FAKE_PDK,
                work,
                extracted_name="pex-extracted.spice",
                outdir_name="pex",
                backend="batch",
            )
            self.assertEqual(
                argv,
                [
                    "pex",
                    "/abs/gds/cdac_array.gds",
                    "pex_request.json",
                    "--deck",
                    "sky130",
                    "--pdk",
                    "sky130A",
                    "--pdk-root",
                    "/pdkroot",
                    "-o",
                    str((work / ".klt" / "pex-extracted.spice").resolve()),
                    "--outdir",
                    str((work / ".klt" / "pex").resolve()),
                    "--backend",
                    "batch",
                ],
            )

    def test_scratch_names_carry_the_per_call_tag(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            argv = pex_flow.klt_pex_argv(
                Path("/abs/gds/comparator.gds"),
                "pex_request_zero.json",
                FAKE_PDK,
                work,
                extracted_name="pex-extracted-zero.spice",
                outdir_name="pex-zero",
                backend="local",
            )
            self.assertEqual(argv[2], "pex_request_zero.json")
            self.assertEqual(Path(argv[argv.index("-o") + 1]).name, "pex-extracted-zero.spice")
            self.assertEqual(Path(argv[argv.index("--outdir") + 1]).name, "pex-zero")
            self.assertEqual(argv[argv.index("--backend") + 1], "local")


class PexMainTests(unittest.TestCase):
    """The shared --check-env/--pilot/--record CLI driver (issue #1069):
    comparator's richer semantics, one copy for every block flow."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.block = Path(self.tmp.name) / "block"
        self.record = self.block / "reports" / "20260101-000000-aabbccdd"
        self.record.mkdir(parents=True)
        (self.record / "block.gds").write_text("gds")
        (self.block / "reports" / "LATEST").write_text("20260101-000000-aabbccdd\n")
        self.calls = []

    def fake_run(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return 42

    def pex_main(self, argv):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = pex_flow.pex_main(
                self.block,
                "block.gds",
                self.block / "reports",
                self.fake_run,
                tmp_prefix="xx-pex-pilot-",
                description="block PEX flow (issue #0)",
                argv=argv,
            )
        return rc, out.getvalue()

    def test_check_env_reports_found_and_latest_layout(self):
        with mock.patch.object(pex_flow.pdk, "resolve", return_value=FAKE_PDK), mock.patch.object(
            pex_flow, "klt_bin", return_value=Path("/bin/true")
        ):
            rc, out = self.pex_main(["--check-env"])
        self.assertEqual(rc, 0)
        self.assertIn("PDK: variant=sky130A root=/pdkroot found=True", out)
        self.assertIn("layout: reports/20260101-000000-aabbccdd/block.gds", out)
        self.assertEqual(self.calls, [])

    def test_check_env_missing_pdk_prints_error_and_returns_3(self):
        missing = dataclasses.replace(
            FAKE_PDK, found=False, error="no PDK variant directory at /pdkroot/sky130A"
        )
        with mock.patch.object(pex_flow.pdk, "resolve", return_value=missing), mock.patch.object(
            pex_flow, "klt_bin", return_value=Path("/bin/true")
        ):
            rc, out = self.pex_main(["--check-env"])
        self.assertEqual(rc, 3)
        self.assertIn("found=False", out)
        self.assertIn("  error: no PDK variant directory at /pdkroot/sky130A", out)
        self.assertEqual(self.calls, [])

    def test_pilot_and_record_are_mutually_exclusive(self):
        rc, out = self.pex_main(["--pilot", "--record"])
        self.assertEqual(rc, 2)
        self.assertEqual(self.calls, [])

    def test_no_mode_prints_help_and_returns_2(self):
        rc, out = self.pex_main([])
        self.assertEqual(rc, 2)
        self.assertIn("usage:", out)
        self.assertEqual(self.calls, [])

    def test_pilot_dispatches_local_backend_in_a_prefixed_tempdir(self):
        rc, _ = self.pex_main(["--pilot"])
        self.assertEqual(rc, 42)
        (args, kwargs) = self.calls[0]
        self.assertEqual(args[1], "local")
        self.assertTrue(args[0].name.startswith("xx-pex-pilot-"), args[0])
        self.assertEqual(kwargs, {"pilot": True, "record": False, "quiet": False})

    def test_pilot_quiet_is_forwarded(self):
        self.pex_main(["--pilot", "--quiet"])
        self.assertEqual(self.calls[0][1]["quiet"], True)

    def test_record_dispatches_batch_backend_into_a_new_record_id(self):
        with mock.patch.object(
            pex_flow.evidence, "new_record_id", return_value="20260102-000000-00000000"
        ):
            rc, _ = self.pex_main(["--record"])
        self.assertEqual(rc, 42)
        (args, kwargs) = self.calls[0]
        self.assertEqual(args[0], self.block / "reports" / "20260102-000000-00000000")
        self.assertEqual(args[1], "batch")
        self.assertEqual(kwargs, {"pilot": False, "record": True, "quiet": False})

    def test_record_backend_override_is_forwarded(self):
        with mock.patch.object(
            pex_flow.evidence, "new_record_id", return_value="20260102-000000-00000000"
        ):
            self.pex_main(["--record", "--backend", "weird"])
        self.assertEqual(self.calls[0][0][1], "weird")

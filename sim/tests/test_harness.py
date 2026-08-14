"""Unit tests for sim/harness/*.py -- pure logic only, no ngspice/PDK
required (mirrors gf180-sar-adc's sim/tests/test_harness.py convention of a
PDK-free unit-test stage ahead of the end-to-end simulation stages; see
sim/selftest.sh stage 1/4)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import corners, evidence, measure, runner  # noqa: E402
from harness import mc_runner, testbench  # noqa: E402


class TestMeasureParse(unittest.TestCase):
    def test_parses_let_print_lines(self):
        log = "\n".join(
            [
                "Doing analysis at TEMP = 27.000000 and TNOM = 27.000000",
                "vgs_nfet = 7.036455e-01",
                "vdiv_ratio = 5.000000e-01",
                "not a measurement line",
            ]
        )
        parsed = measure.parse(log, ["vgs_nfet", "vdiv_ratio", "missing"])
        self.assertAlmostEqual(parsed["vgs_nfet"], 0.7036455)
        self.assertAlmostEqual(parsed["vdiv_ratio"], 0.5)
        self.assertNotIn("missing", parsed)

    def test_missing_reports_unparsed_names(self):
        parsed = measure.parse("vgs_nfet = 1.0", ["vgs_nfet", "vdiv_ratio"])
        self.assertEqual(measure.missing(parsed, ["vgs_nfet", "vdiv_ratio"]), ["vdiv_ratio"])

    def test_first_occurrence_wins(self):
        log = "x = 1.0\nx = 2.0\n"
        parsed = measure.parse(log, ["x"])
        self.assertEqual(parsed["x"], 1.0)


class TestCorners(unittest.TestCase):
    def test_default_process_corners_from_pdk_json(self):
        pcs = corners.default_process_corners()
        self.assertIn("tt", pcs)
        self.assertIn("ss", pcs)
        self.assertIn("ff", pcs)

    def test_mismatch_corner_for(self):
        self.assertEqual(corners.mismatch_corner_for("tt"), "tt_mm")
        with self.assertRaises(ValueError):
            corners.mismatch_corner_for("not_a_corner")

    def test_corner_id_format(self):
        self.assertEqual(corners.corner_id("ss", -40, 1.62), "ss_-40c_1.62v")
        self.assertEqual(corners.corner_id("tt", 27, 1.8), "tt_27c_1.80v")

    def test_supply_points_tolerance(self):
        pts = corners.supply_points(1.8, 0.10)
        self.assertEqual(pts, [1.62, 1.8, 1.98])

    def test_supply_points_zero_tolerance(self):
        self.assertEqual(corners.supply_points(1.8, 0.0), [1.8])


class TestEvidence(unittest.TestCase):
    def test_sha256_is_deterministic(self):
        a = evidence.sha256_text("hello")
        b = evidence.sha256_text("hello")
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)

    def test_sha256_differs_on_content_change(self):
        self.assertNotEqual(evidence.sha256_text("a"), evidence.sha256_text("b"))

    def test_record_id_shape(self):
        rid = evidence.new_record_id()
        # <YYYYMMDD>-<HHMMSS>-<short-sha-or-nogit>
        parts = rid.split("-")
        self.assertGreaterEqual(len(parts), 3)
        self.assertEqual(len(parts[0]), 8)
        self.assertEqual(len(parts[1]), 6)


class TestRunnerHelpers(unittest.TestCase):
    def test_spread_pct(self):
        self.assertAlmostEqual(runner._spread_pct([0.9, 0.9, 0.9]), 0.0)
        self.assertAlmostEqual(runner._spread_pct([0.81, 0.9, 0.99]), 20.0)

    def test_spread_pct_empty(self):
        self.assertEqual(runner._spread_pct([]), 0.0)

    def test_evaluate_checks_min_max(self):
        failures = runner._evaluate_checks("x", {"min": 0.5, "max": 1.0}, 0.3, {})
        self.assertEqual(len(failures), 1)
        self.assertIn("< min", failures[0])

    def test_evaluate_checks_axis_floor(self):
        checks = {"min_spread_pct_by_axis": {"process": 5.0}}
        ok = runner._evaluate_checks("x", checks, 1.0, {"process": 10.0})
        self.assertEqual(ok, [])
        bad = runner._evaluate_checks("x", checks, 1.0, {"process": 1.0})
        self.assertEqual(len(bad), 1)

    def test_evaluate_checks_axis_ceiling(self):
        checks = {"max_spread_pct_by_axis": {"process": 1.0}}
        bad = runner._evaluate_checks("x", checks, 1.0, {"process": 5.0})
        self.assertEqual(len(bad), 1)


class TestTestbenchManifest(unittest.TestCase):
    def test_load_manifest_and_build_netlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            experiment_dir = tmp_path / "fake-experiment"
            tb_dir = experiment_dir / "testbench"
            tb_dir.mkdir(parents=True)
            fragment = tb_dir / "fake.spice"
            fragment.write_text("Vdd vdd 0 dc {vdd_val}\nR1 vdd 0 1k\n")
            manifest_json = tb_dir / "tb.json"
            manifest_json.write_text(
                """
                {
                  "name": "fake-experiment",
                  "claim": "test fixture only",
                  "netlist_fragment": "fake.spice",
                  "nominal_supply_v": 1.8,
                  "supply_tolerance": 0.1,
                  "temperatures_c": [27],
                  "process_corners": ["tt"],
                  "measure": {"v": "v(vdd)"},
                  "checks": {}
                }
                """
            )
            manifest = testbench.load(manifest_json)
            self.assertEqual(manifest.name, "fake-experiment")
            self.assertEqual(manifest.nominal_supply_v, 1.8)
            self.assertEqual(manifest.measure, {"v": "v(vdd)"})

            class FakePdkInfo:
                ngspice_lib = "/fake/sky130.lib.spice"

            netlist = testbench.build_netlist(manifest, FakePdkInfo(), "tt", 27, 1.8)
            self.assertIn(".lib /fake/sky130.lib.spice tt", netlist)
            self.assertIn(".temp 27", netlist)
            self.assertIn(".param vdd_val = 1.8", netlist)
            self.assertIn("let v = v(vdd)", netlist)
            self.assertIn("print v", netlist)

    def test_sabotage_forces_tt_but_not_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tb_dir = tmp_path / "fake" / "testbench"
            tb_dir.mkdir(parents=True)
            (tb_dir / "fake.spice").write_text("R1 vdd 0 1k\n")
            (tb_dir / "tb.json").write_text(
                """
                {"name": "fake", "netlist_fragment": "fake.spice",
                 "nominal_supply_v": 1.8, "measure": {"v": "v(vdd)"}}
                """
            )
            manifest = testbench.load(tb_dir / "tb.json")

            class FakePdkInfo:
                ngspice_lib = "/fake/sky130.lib.spice"

            netlist = testbench.build_netlist(
                manifest, FakePdkInfo(), "ss", 125, 1.8, sabotage=True
            )
            self.assertIn(".lib /fake/sky130.lib.spice tt", netlist)
            self.assertIn(".temp 125", netlist)


class TestMcRunner(unittest.TestCase):
    def test_distribution_stats(self):
        draws = [
            mc_runner.Draw(seed=1, measures={"x": 1.0}, log_text=""),
            mc_runner.Draw(seed=2, measures={"x": 3.0}, log_text=""),
        ]
        dists = mc_runner.distributions(draws, ["x"])
        self.assertEqual(dists["x"].n, 2)
        self.assertAlmostEqual(dists["x"].mean, 2.0)
        self.assertAlmostEqual(dists["x"].minimum, 1.0)
        self.assertAlmostEqual(dists["x"].maximum, 3.0)

    def test_negative_control_ok_when_deterministic(self):
        class FakeResult:
            negative_control_draws = [
                mc_runner.Draw(seed=1, measures={"x": 5.0}, log_text=""),
                mc_runner.Draw(seed=2, measures={"x": 5.0}, log_text=""),
            ]

        ok, failures = mc_runner.negative_control_ok(FakeResult(), ["x"])
        self.assertTrue(ok)
        self.assertEqual(failures, [])

    def test_negative_control_fails_when_seed_leaks_variance(self):
        class FakeResult:
            negative_control_draws = [
                mc_runner.Draw(seed=1, measures={"x": 5.0}, log_text=""),
                mc_runner.Draw(seed=2, measures={"x": 5.1}, log_text=""),
            ]

        ok, failures = mc_runner.negative_control_ok(FakeResult(), ["x"])
        self.assertFalse(ok)
        self.assertEqual(len(failures), 1)


if __name__ == "__main__":
    unittest.main()

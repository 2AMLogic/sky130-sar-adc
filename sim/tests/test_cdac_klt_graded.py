"""Full-grid evidence regressions for the graded CDAC campaign."""

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[1] / "cdac-array-transfer"
sys.path.insert(0, str(BENCH))
import run_klt_graded as graded  # noqa: E402

ARCHIVE = BENCH / "klt-sim/20261122-103440-000e61e7/report.json"


class GradedRecordTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)
        self.report = json.loads(ARCHIVE.read_text())
        self.stdout = io.StringIO()
        # The output tree is temporary. Baseline comparison reads its frozen input.
        (self.work / "records").mkdir()
        baseline = f"{graded.BASELINE_RECORD}.md"
        (self.work / "records" / baseline).symlink_to(BENCH / "records" / baseline)

    def record(self, *args):
        with (
            patch.object(graded, "EXPERIMENT_DIR", self.work),
            patch.object(graded.klt_sim, "submit", return_value=self.report) as submit,
            patch.object(graded.evidence, "new_record_id", return_value="test"),
            redirect_stdout(self.stdout),
        ):
            self.status = graded.main(["--record", *args])
        return submit

    def assert_refused(self):
        self.assertEqual(self.status, 3, self.stdout.getvalue())
        self.assertFalse((self.work / "records/test.md").exists())
        self.assertFalse((self.work / "netlist-snapshots").exists())

    def test_debug_request_refused_before_submission(self):
        quick = self.work / "quick.json"
        req = json.loads(graded.REQUEST.read_text())
        req["corners"] = {"process": ["tt"], "temperature_c": [27],
                          "params": {"vdd_val": [1.8]}}
        quick.write_text(json.dumps(req))
        submit = self.record("--request", str(quick))
        self.assert_refused()
        submit.assert_not_called()

    def test_edited_request_at_canonical_path_refused_before_submission(self):
        request = self.work / "request-graded.json"
        original = graded.REQUEST.read_text()
        with patch.object(graded, "REQUEST", request):
            for name in ("vref_ratio", "v_vrefn"):
                for field in ("spec_row", "limits"):
                    with self.subTest(name=name, field=field):
                        data = json.loads(original)
                        meas = next(m for m in data["measurements"] if m["name"] == name)
                        del meas[field]
                        request.write_text(json.dumps(data))
                        submit = self.record()
                        self.assert_refused()
                        submit.assert_not_called()

    def test_report_must_grade_both_references_with_the_documented_limits(self):
        for name in ("vref_ratio", "v_vrefn"):
            for fault in ("informational", "wrong tag", "widened limits", "duplicate"):
                with self.subTest(name=name, fault=fault):
                    self.report = json.loads(ARCHIVE.read_text())
                    definitions = self.report["measurements"]
                    meas = next(m for m in definitions if m["name"] == name)
                    if fault == "informational":
                        del meas["limits"], meas["spec_row"]
                        for corner in self.report["corners"]:
                            result = next(m for m in corner["measurements"] if m["name"] == name)
                            result["margin"] = None  # klt still reports status "pass"
                    elif fault == "wrong tag":
                        meas["spec_row"] = "lsb"
                    elif fault == "widened limits":
                        meas["limits"]["min"] -= 0.1
                    else:
                        definitions.append(meas.copy())
                    self.record()
                    self.assert_refused()

    def test_passing_corner_requires_finite_in_range_reference_measurements(self):
        for name, value in (("vref_ratio", 0.9), ("vref_ratio", 1.00002),
                            ("v_vrefn", -2e-5), ("v_vrefn", 2e-5),
                            ("vref_ratio", True), ("v_vrefn", None),
                            ("vref_ratio", float("nan")), ("v_vrefn", float("inf"))):
            with self.subTest(name=name, value=value):
                self.report = json.loads(ARCHIVE.read_text())
                measurements = self.report["corners"][-1]["measurements"]
                next(m for m in measurements if m["name"] == name)["value"] = value
                self.record()
                self.assert_refused()

    def test_reference_limit_endpoints_pass(self):
        for corner, ratio, vrefn in zip(self.report["corners"], (0.99999, 1.00001),
                                        (-1e-5, 1e-5)):
            measurements = {m["name"]: m for m in corner["measurements"]}
            measurements["vref_ratio"].update(value=ratio, margin=0)
            measurements["v_vrefn"].update(value=vrefn, margin=0)
        self.record()
        self.assertEqual(self.status, 0, self.stdout.getvalue())

    def test_in_range_informational_corner_refused_even_with_graded_definitions(self):
        results = self.report["corners"][-1]["measurements"]
        next(m for m in results if m["name"] == "vref_ratio")["margin"] = None
        self.record()
        self.assert_refused()
        self.assertIn("margin", self.stdout.getvalue())

    def test_genuine_reference_failure_is_recorded(self):
        self.report.update(status="fail", passed=8, failed=1)
        corner = self.report["corners"][-1]
        corner["status"] = "fail"
        result = next(m for m in corner["measurements"] if m["name"] == "vref_ratio")
        result.update(value=0.9, status="fail", margin=-0.09999)
        definition = next(m for m in self.report["measurements"] if m["name"] == "vref_ratio")
        definition["status"] = "fail"
        self.record()
        self.assertEqual(self.status, 1, self.stdout.getvalue())
        record = (self.work / "records/test.md").read_text()
        self.assertIn("**Overall**: FAIL", record)
        self.assertNotIn("FAIL at all 9 corners", record)

    def test_missing_duplicate_and_wrong_corner_refused(self):
        for fault in ("subset", "duplicate", "wrong supply"):
            with self.subTest(fault=fault):
                self.report = json.loads(ARCHIVE.read_text())
                corners = self.report["corners"]
                if fault == "subset":
                    del corners[1:]
                elif fault == "duplicate":
                    corners[0] = copy.deepcopy(corners[-1])
                else:
                    corners[0]["params"]["vdd_val"] += 0.001
                self.report["passed"] = self.report["corner_count"] = len(corners)
                self.record()
                self.assert_refused()

    def test_ideal_five_codes_have_zero_interval_error(self):
        for corner in self.report["corners"]:
            vdd = corner["params"]["vdd_val"]
            measurements = {m["name"]: m for m in corner["measurements"]}
            for code in graded.CODES:
                measurements[f"vtop_p_{code}"]["value"] = graded.run_transfer.ideal_vdiff(code, vdd)
                measurements[f"vtop_n_{code}"]["value"] = 0.0
        self.record()
        self.assertEqual(self.status, 0, self.stdout.getvalue())
        record = (self.work / "records/test.md").read_text()
        rows = [line.split("|") for line in record.splitlines() if line.startswith("| `")]
        self.assertEqual([row[5].strip() for row in rows], ["0.000"] * 9)

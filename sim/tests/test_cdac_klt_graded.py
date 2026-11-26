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

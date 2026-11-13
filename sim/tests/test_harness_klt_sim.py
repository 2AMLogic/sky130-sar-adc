"""PDK-free unit tests for sim/harness/klt_sim.py (issue #865) -- the one
`klt sim` submit path every batch campaign driver goes through.

No `klt`, no PDK, no fleet: the subprocess runner is injected, and every
report here is a dict this file builds.

The last class is a STRUCTURAL guard rather than a behaviour test: the four
drivers consolidated in #865 had each copied the previous campaign's submit
block, and the copies had drifted to three different fleet-capacity policies
(one of them none at all). A fifth campaign that copies instead of importing
would re-open exactly that, so it is asserted against here, where the next
campaign's author will see it fail.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import klt_sim  # noqa: E402

REPORT = {"status": "pass", "corners": [{"process": "tt"}], "environment": {}}


def _runner(rc=0, out="", err="", calls=None):
    def run(argv):
        if calls is not None:
            calls.append(argv)
        return rc, out, err
    return run


class TestSubmitArgv(unittest.TestCase):
    def test_batch_submit_waits_for_capacity(self):
        """CLAUDE.md's fleet rule: a vCPU-budgeted fleet refuses a burst with
        `batch_no_capacity` unless the submit may wait with backoff."""
        argv = klt_sim.submit_argv(Path("/w/request.json"), Path("/w/out"), "batch")
        self.assertEqual(argv[:2], ["klt", "sim"])
        self.assertIn("--wait-for-capacity", argv)
        self.assertEqual(argv[argv.index("--wait-for-capacity") + 1], "600")
        self.assertEqual(argv[argv.index("--backend") + 1], "batch")
        self.assertEqual(argv[argv.index("-o") + 1], "/w/out")

    def test_default_backend_still_waits_for_capacity(self):
        """With no explicit backend, `$KLT_SIM_BACKEND` decides -- which on a
        dispatch host is `batch`, so the flag must still be there."""
        argv = klt_sim.submit_argv(Path("/w/request.json"), Path("/w/out"))
        self.assertIn("--wait-for-capacity", argv)
        self.assertNotIn("--backend", argv)

    def test_local_backend_does_not_wait_for_a_fleet(self):
        argv = klt_sim.submit_argv(Path("/w/request.json"), Path("/w/out"), "local")
        self.assertNotIn("--wait-for-capacity", argv)
        self.assertEqual(argv[argv.index("--backend") + 1], "local")

    def test_an_explicit_none_wait_opts_out(self):
        argv = klt_sim.submit_argv(Path("/w/r.json"), Path("/w/out"), "batch",
                                   capacity_wait_s=None)
        self.assertNotIn("--wait-for-capacity", argv)

    def test_a_non_integer_wait_is_not_rendered_in_exponent_form(self):
        argv = klt_sim.submit_argv(Path("/w/r.json"), Path("/w/out"), "batch",
                                   capacity_wait_s=3600.0)
        self.assertEqual(argv[argv.index("--wait-for-capacity") + 1], "3600")


class TestSubmit(unittest.TestCase):
    def _submit(self, d: Path, **kw):
        (d / "request.json").write_text("{}")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return klt_sim.submit(d / "request.json", d / "out", **kw)

    def test_reads_the_report_off_stdout_and_caches_it(self):
        calls = []
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            report = self._submit(d, backend="batch",
                                  runner=_runner(out=json.dumps(REPORT), calls=calls))
            self.assertEqual(report, REPORT)
            self.assertTrue((d / "report.json").is_file())
            # a completed submit is served from the cache, not re-spent
            again = self._submit(d, backend="batch",
                                 runner=_runner(out="not json", calls=calls))
            self.assertEqual(again, REPORT)
            self.assertEqual(len(calls), 1)

    def test_reads_the_error_envelope_off_stderr(self):
        """`klt` writes its error envelope to stderr with rc 1."""
        envelope = json.dumps({"error": {"code": "batch_no_capacity"}})
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(klt_sim.SubmitError) as ctx:
                self._submit(Path(td), backend="batch",
                             runner=_runner(rc=1, out="", err=envelope))
            self.assertIn("batch_no_capacity", str(ctx.exception))
            self.assertFalse((Path(td) / "report.json").exists())

    def test_no_json_at_all_is_a_submit_error_quoting_the_client(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(klt_sim.SubmitError) as ctx:
                self._submit(Path(td), backend="batch", label="grid",
                             runner=_runner(rc=2, out="", err="Traceback: boom"))
            msg = str(ctx.exception)
            self.assertIn("klt sim (grid)", msg)
            self.assertIn("rc=2", msg)
            self.assertIn("boom", msg)

    def test_an_error_envelope_is_refused_not_cached(self):
        envelope = json.dumps({"error": {"message": "models missing"}})
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(klt_sim.SubmitError):
                self._submit(Path(td), backend="batch", runner=_runner(out=envelope))

    def test_error_beside_corners_is_a_partial_run_and_is_returned(self):
        """`error` AND `corners` means a partially-failed run, not an
        envelope: the caller's own reader decodes the usable corners."""
        partial = dict(REPORT, error={"code": "partial"})
        with tempfile.TemporaryDirectory() as td:
            report = self._submit(Path(td), backend="batch",
                                  runner=_runner(out=json.dumps(partial)))
            self.assertEqual(report["corners"], REPORT["corners"])

    def test_the_report_cache_may_live_elsewhere(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            cache = d / "cached" / "report.json"
            (d / "request.json").write_text("{}")
            with redirect_stdout(io.StringIO()):
                klt_sim.submit(d / "request.json", d / "out", backend="batch",
                               report_path=cache, runner=_runner(out=json.dumps(REPORT)))
            self.assertTrue(cache.is_file())
            self.assertFalse((d / "report.json").exists())


class TestCapacityRetry(unittest.TestCase):
    REFUSAL = json.dumps({"error": {"message": "launch failed: 8 instance(s) already running "
                                    "+ 1 requested exceeds BATCH_MAX_CONCURRENT_INSTANCES=8"}})

    def test_markers(self):
        self.assertTrue(klt_sim.is_capacity_refusal("BATCH_MAX_CONCURRENT_INSTANCES=8"))
        self.assertTrue(klt_sim.is_capacity_refusal("batch_no_capacity"))
        self.assertTrue(klt_sim.is_capacity_refusal("No Capacity right now"))
        self.assertFalse(klt_sim.is_capacity_refusal("nonconvergence"))

    def test_a_refusal_is_retried_on_the_same_backend_only(self):
        outs = [self.REFUSAL, self.REFUSAL, json.dumps(REPORT)]
        calls, naps = [], []

        def runner(argv):
            calls.append(argv)
            o = outs.pop(0)
            # the real client writes its error envelope to STDERR with rc 1
            return (1, "", o) if o is self.REFUSAL else (0, o, "")

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "request.json").write_text("{}")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                report = klt_sim.submit(
                    d / "request.json", d / "out", backend="batch", runner=runner,
                    capacity_retries=5, retry_wait_s=7, sleep=naps.append)
            self.assertEqual(report, REPORT)
            self.assertEqual(naps, [7, 7])
            self.assertTrue(all(c[c.index("--backend") + 1] == "batch" for c in calls))

    def test_retries_are_bounded_then_the_fleets_own_message_stops_it(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "request.json").write_text("{}")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), \
                    self.assertRaises(klt_sim.SubmitError) as ctx:
                klt_sim.submit(d / "request.json", d / "out", backend="batch",
                               runner=_runner(rc=1, err=self.REFUSAL),
                               capacity_retries=2, sleep=lambda s: None)
            self.assertIn("BATCH_MAX_CONCURRENT_INSTANCES", str(ctx.exception))

    def test_a_non_capacity_error_is_never_retried(self):
        calls = []
        envelope = json.dumps({"error": {"code": "nonconvergence"}})
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "request.json").write_text("{}")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), \
                    self.assertRaises(klt_sim.SubmitError):
                klt_sim.submit(d / "request.json", d / "out", backend="batch",
                               runner=_runner(rc=1, err=envelope, calls=calls),
                               capacity_retries=9, sleep=lambda s: None)
            self.assertEqual(len(calls), 1)

    def test_no_retry_by_default(self):
        calls = []
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "request.json").write_text("{}")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), \
                    self.assertRaises(klt_sim.SubmitError):
                klt_sim.submit(d / "request.json", d / "out", backend="batch",
                               runner=_runner(rc=1, err=self.REFUSAL, calls=calls))
            self.assertEqual(len(calls), 1)


class TestRunInfo(unittest.TestCase):
    """A sharded batch run carries job identity under
    `environment.remote.fleet[]`, not on `environment.remote` itself."""

    def _shard(self, job, pdk="f6eeac7", ng="ngspice-47"):
        return {
            "job_id": job, "state": "done", "exit_code": "0",
            "instance_type": "c7i.8xlarge", "elapsed_seconds": 258,
            "runner_klt_version": "0.9.0",
            "runner_request_features": {"status": "supported"},
            "worker_environment": {
                "pdk": {"variant": "sky130A", "stamp_text": f"open_pdks {pdk}"},
                "simulator": {"version_banner": f"** {ng} : Circuit level simulation"},
            },
        }

    def _info(self, remote, backend="batch"):
        return klt_sim.run_info({"status": "pass", "corners": [],
                                 "environment": {"remote": remote,
                                                 "backend": {"resolved": backend}}})

    def test_sharded_run_reports_every_job_id(self):
        info = self._info({"fleet": [self._shard("a"), self._shard("b")]})
        self.assertTrue(info["sharded"])
        self.assertEqual([j["job_id"] for j in info["jobs"]], ["a", "b"])
        self.assertIsNone(info["job_id"], "no single job id for a sharded run")
        self.assertEqual(info["worker_pdk"], "sky130A @ f6eeac7")
        self.assertEqual(info["worker_ngspice"], "ngspice-47")
        self.assertEqual(info["resolved_backend"], "batch")
        self.assertEqual(info["request_feature_status"], "supported")

    def test_single_job_run_still_reads(self):
        info = self._info(dict(self._shard("solo")))
        self.assertFalse(info["sharded"])
        self.assertEqual(info["job_id"], "solo")
        self.assertEqual([j["job_id"] for j in info["jobs"]], ["solo"])

    def test_disagreeing_shards_report_no_single_environment(self):
        """One shard's PDK must not stand for the whole run."""
        info = self._info({"fleet": [self._shard("a"), self._shard("b", pdk="deadbee")]})
        self.assertIsNone(info["worker_pdk"])
        self.assertEqual(len(info["worker_pdks_seen"]), 2)
        info = self._info({"fleet": [self._shard("a"), self._shard("b", ng="ngspice-46")]})
        self.assertIsNone(info["worker_ngspice"])

    def test_no_fleet_and_no_job_id_yields_no_jobs(self):
        info = self._info({})
        self.assertEqual(info["jobs"], [])
        self.assertIsNone(info["job_id"])
        self.assertIsNone(info["remote"])

    def test_a_local_run_has_no_remote_at_all(self):
        info = klt_sim.run_info({"status": "pass", "environment": {"backend": "local"}})
        self.assertEqual(info["jobs"], [])
        self.assertEqual(info["resolved_backend"], "local")
        self.assertIsNone(info["worker_pdk"])

    def test_requested_backend_is_used_when_nothing_resolved(self):
        info = klt_sim.run_info({"environment": {"backend": {"requested": "batch"}}})
        self.assertEqual(info["resolved_backend"], "batch")

    def test_ngspice_banner_parsing(self):
        self.assertEqual(
            klt_sim.ngspice_from_banner("******\n** ngspice-47 : Circuit level\n******"),
            "ngspice-47")
        self.assertIsNone(klt_sim.ngspice_from_banner(""))
        self.assertIsNone(klt_sim.ngspice_from_banner("no version here"))


class TestNoDriverKeepsItsOwnSubmitBlock(unittest.TestCase):
    """Issue #865: the drivers import the submit path, they do not re-copy it.

    Each assertion below is one of the drifts the four private copies had
    actually accumulated. A new campaign that copies a sibling's block
    instead of calling `harness.klt_sim.submit()` fails here.
    """

    @staticmethod
    def _drivers() -> list[Path]:
        """Every campaign driver that submits to `klt sim` -- discovered by
        content (it calls the helper, or it builds the argv itself), never a
        hand-kept list, so a new campaign is covered the day it is written."""
        return [p for p in sorted(SIM_DIR.glob("*/run_*.py"))
                if "klt_sim.submit(" in p.read_text() or '"klt", "sim"' in p.read_text()]

    def test_at_least_the_four_consolidated_drivers_are_covered(self):
        names = {p.parent.name for p in self._drivers()}
        self.assertLessEqual(
            {"top-plate-cpar", "reference-drive-budget", "input-drive-budget",
             "digital-partition"}, names, f"scan found only {sorted(names)}")

    def test_no_driver_builds_its_own_klt_sim_argv(self):
        for p in self._drivers():
            with self.subTest(driver=p.parent.name):
                self.assertNotIn('"klt", "sim"', p.read_text(),
                                 "build the argv with harness.klt_sim.submit_argv()")

    def test_no_driver_defines_a_private_submit_error(self):
        for p in self._drivers():
            with self.subTest(driver=p.parent.name):
                self.assertNotIn("class SubmitError", p.read_text(),
                                 "alias harness.klt_sim.SubmitError instead")

    def test_no_driver_carries_a_private_capacity_marker_list(self):
        for p in self._drivers():
            with self.subTest(driver=p.parent.name):
                self.assertNotIn("CAPACITY_MARKERS =", p.read_text(),
                                 "harness.klt_sim.is_capacity_refusal() owns this")

    def test_no_driver_reads_only_the_single_job_report_shape(self):
        """`remote.job_id` without `fleet` is how a sharded record ends up
        reporting `job None`; `harness.klt_sim.run_info()` reads both."""
        for p in self._drivers():
            text = p.read_text()
            with self.subTest(driver=p.parent.name):
                if 'remote.get("job_id")' in text:
                    self.assertIn("fleet", text,
                                  "use harness.klt_sim.run_info() for run-level facts")


if __name__ == "__main__":
    unittest.main()

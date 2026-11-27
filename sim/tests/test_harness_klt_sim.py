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

import ast
import io
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import klt_sim  # noqa: E402

REPORT = {"status": "pass", "corners": [{"process": "tt"}], "environment": {}}

#: The real shape behind issue #892: `klt` prints human warning and progress
#: lines to stderr BEFORE its error envelope, so stderr is not pure JSON.
#: Transcribed from the submit that died during the #881 batch grid.
KLT_STDERR_PREAMBLE = (
    "klt: warning: 2 installs provide PDK variant 'sky130A'; "
    "read /home/ubuntu/.ciel\n"
    "klt: batch job klt-sim-b4c5875b12ef submitting to "
    "s3://<bucket>/jobs/klt-sim-b4c5875b12ef\n"
    "klt sim: batch job klt-sim-b4c5875b12ef: submitted\n"
)

NO_CAPACITY_MESSAGE = (
    "batch backend failed: BATCH_MAX_VCPU=224 (capacity wait budget of 600s "
    "exhausted after 6 launch attempt(s))"
)


def _stderr_behind_warnings(code="batch_no_capacity", message=NO_CAPACITY_MESSAGE):
    """Warning/progress lines, then a pretty-printed `klt` error envelope."""
    envelope = {"schema_version": 1,
                "error": {"command": "sim", "message": message, "code": code}}
    return KLT_STDERR_PREAMBLE + json.dumps(envelope, indent=1) + "\n"


def _reads_sharded_envelope(text):
    """Every structural read of the sharded `fleet` envelope: a `Subscript`
    keyed on the constant `"fleet"` (`remote["fleet"]`, whatever the accessor
    chain) or any call whose first positional argument is the constant
    `"fleet"` (`remote.get("fleet")`, `remote.pop("fleet")`,
    `itemgetter("fleet")`, ...). Keys on the parsed AST rather than on an
    enumeration of accessor spellings (the defect class #888/#918/#944 each
    had to patch one spelling at a time), and the broad `Call` arm
    deliberately restores the old literal-tuple breadth, erring toward firing
    so a human looks. Deliberately NOT caught: variable-key indirection
    (`remote.get(key)`) -- out of scope on #918/#944. Prose that does not
    parse yields no read; the scan loop asserts real modules parse, so a
    syntactically broken module cannot slip past silently. Tested against
    the full table (and the decoys it must stay quiet on) by
    `test_envelope_matcher_fires_on_every_spelling_of_the_read`."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    reads = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Constant) and node.slice.value == "fleet":
                reads.append(ast.unparse(node))
        elif isinstance(node, ast.Call):
            if (node.args
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == "fleet"):
                reads.append(ast.unparse(node))
    return reads


def _runner(rc=0, out="", err="", calls=None):
    def run(argv):
        if calls is not None:
            calls.append(argv)
        return rc, out, err
    return run


def _oat_axis_dicts(text):
    """Dict literals whose keys are exactly the OAT corner-axis triple
    (`process`, `temperature_c`, `supply_v`) -- the artifacts a private copy
    of the OAT expansion necessarily carries, in the `corners` block AND in
    every `exclude` entry alike. Keyed on the parsed AST, like
    `_reads_sharded_envelope` before it. The deliberately-unconsolidated
    shapes do not match: reference-drive-budget keys its axes on `params`
    (zipped VDD x R_ref rows), and the full-conversion input sweep is a
    single-corner `params` sweep with no `exclude` at all. Prose that does
    not parse yields no hit; the guard's scan loop asserts real modules
    parse, so a broken module cannot slip past silently."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
            if len(keys) == len(node.keys) and keys == {
                "process", "temperature_c", "supply_v"
            }:
                found.append(ast.unparse(node))
    return found


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

    def test_a_non_envelope_dict_on_stderr_is_refused_not_cached(self):
        """Issue #898: a stderr dict with no `error` key is neither a report
        nor an envelope -- refused as "no JSON report", never cached."""
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(klt_sim.SubmitError) as ctx:
                self._submit(Path(td), backend="batch",
                             runner=_runner(rc=1, out="",
                                            err='{"job": 1, "status": "running"}\n'))
            self.assertIn("returned no JSON report", str(ctx.exception))
            # caching is the actual harm -- assert on the file's absence
            self.assertFalse((Path(td) / "report.json").exists())

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


class TestEnvelopeFromStderr(unittest.TestCase):
    """`klt`'s error envelope arrives on stderr BEHIND warning and progress
    lines (issue #892), so stderr must be SCANNED for the envelope rather
    than assumed to BE it."""

    def test_an_envelope_behind_warning_lines_is_found(self):
        env = klt_sim.envelope_from_stderr(_stderr_behind_warnings())
        self.assertEqual(env["error"]["code"], "batch_no_capacity")

    def test_a_pure_json_envelope_is_still_found(self):
        env = klt_sim.envelope_from_stderr(json.dumps({"error": {"code": "x"}}))
        self.assertEqual(env["error"]["code"], "x")

    def test_stderr_with_no_json_object_yields_none(self):
        self.assertIsNone(klt_sim.envelope_from_stderr("Traceback: boom\nbye\n"))

    def test_empty_stderr_yields_none(self):
        self.assertIsNone(klt_sim.envelope_from_stderr(""))

    def test_a_brace_line_that_does_not_decode_is_skipped_for_the_real_one(self):
        """A progress line may itself begin with `{` -- the scan keeps going
        rather than giving up at the first candidate."""
        text = "{ not json at all\n" + _stderr_behind_warnings()
        self.assertEqual(
            klt_sim.envelope_from_stderr(text)["error"]["code"], "batch_no_capacity")

    def test_trailing_text_after_the_envelope_is_ignored(self):
        text = _stderr_behind_warnings() + "klt: exiting with status 1\n"
        self.assertEqual(
            klt_sim.envelope_from_stderr(text)["error"]["code"], "batch_no_capacity")

    def test_a_json_array_on_stderr_is_not_an_envelope(self):
        self.assertIsNone(klt_sim.envelope_from_stderr("[1, 2, 3]\n"))

    def test_a_non_envelope_dict_yields_none(self):
        """Issue #898: a JSON dict with no `error` key -- a progress or
        status object at column 0 -- is not an envelope, and must not be
        returned as one."""
        self.assertIsNone(
            klt_sim.envelope_from_stderr('{"job": 1, "status": "running"}\n'))

    def test_a_non_envelope_dict_does_not_mask_the_real_envelope(self):
        """Issue #898: the scan keeps walking past a non-envelope dict to
        the envelope behind it."""
        text = ('{"job": 1, "status": "running"}\n'
                '{"error": {"code": "batch_no_capacity"}}\n')
        env = klt_sim.envelope_from_stderr(text)
        self.assertEqual(env["error"]["code"], "batch_no_capacity")


class TestSubmitEnvelopeBehindWarnings(unittest.TestCase):
    """Issue #892: the two consequences of assuming stderr is pure JSON --
    the wrong error class, and a capacity refusal that skips the retry."""

    def _submit(self, d: Path, **kw):
        (d / "request.json").write_text("{}")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return klt_sim.submit(d / "request.json", d / "out", **kw)

    def test_the_error_names_the_envelopes_own_code_and_message(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(klt_sim.SubmitError) as ctx:
                self._submit(Path(td), backend="batch",
                             runner=_runner(rc=1, err=_stderr_behind_warnings()))
            msg = str(ctx.exception)
            self.assertIn("batch_no_capacity", msg)
            self.assertIn("capacity wait budget", msg)
            # NOT the "client malfunctioned" class, and not the PDK warning
            self.assertNotIn("returned no JSON report", msg)
            self.assertNotIn("2 installs provide PDK variant", msg)
            self.assertFalse((Path(td) / "report.json").exists())

    def test_capacity_retry_fires_for_an_envelope_behind_warning_lines(self):
        """The retry is gated on an envelope that PARSED; behind a warning
        line it never parsed, so `capacity_retries` silently did not apply."""
        outs = [_stderr_behind_warnings(), _stderr_behind_warnings(),
                json.dumps(REPORT)]
        calls, naps = [], []

        def runner(argv):
            calls.append(argv)
            o = outs.pop(0)
            return (0, o, "") if o.startswith("{") else (1, "", o)

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "request.json").write_text("{}")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                report = klt_sim.submit(d / "request.json", d / "out",
                                        backend="batch", runner=runner,
                                        capacity_retries=5, retry_wait_s=7,
                                        sleep=naps.append)
            self.assertEqual(report, REPORT)
            self.assertEqual(len(calls), 3)
            self.assertEqual(naps, [7, 7])

    def test_a_non_envelope_dict_does_not_mask_the_envelope_behind_it(self):
        """Issue #898: a column-0 progress object in front of the envelope
        must not swallow the refusal -- it is named as its own code, and
        the capacity retry still fires."""
        stderr = ('{"job": 1, "status": "running"}\n'
                  + _stderr_behind_warnings())
        calls, naps = [], []

        def runner(argv):
            calls.append(argv)
            return 1, "", stderr

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            with self.assertRaises(klt_sim.SubmitError) as ctx:
                self._submit(d, backend="batch", runner=runner,
                             capacity_retries=1, retry_wait_s=7, sleep=naps.append)
            msg = str(ctx.exception)
            self.assertIn("batch_no_capacity", msg)
            self.assertNotIn("returned no JSON report", msg)
            self.assertEqual(len(calls), 2)
            self.assertEqual(naps, [7])
            self.assertFalse((d / "report.json").exists())

    def test_an_error_beside_corners_on_stderr_is_still_a_partial_run(self):
        """`error` AND `corners` on stderr is a partially-failed run, not an
        envelope: returned for the caller's own reader, never refused."""
        partial = dict(REPORT, error={"code": "partial"})
        with tempfile.TemporaryDirectory() as td:
            report = self._submit(Path(td), backend="batch",
                                  runner=_runner(rc=1, out="", err=json.dumps(partial)))
            self.assertEqual(report["corners"], REPORT["corners"])

    def test_a_non_capacity_envelope_behind_warnings_is_not_retried(self):
        calls = []
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            with self.assertRaises(klt_sim.SubmitError) as ctx:
                self._submit(d, backend="batch", capacity_retries=9,
                             sleep=lambda s: None,
                             runner=_runner(rc=1, calls=calls, err=_stderr_behind_warnings(
                                 code="nonconvergence", message="tran failed to converge")))
            self.assertIn("nonconvergence", str(ctx.exception))
            self.assertEqual(len(calls), 1)

    def test_genuinely_non_json_stderr_still_raises_the_no_report_error(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(klt_sim.SubmitError) as ctx:
                self._submit(Path(td), backend="batch", label="grid",
                             runner=_runner(rc=2, out="", err=KLT_STDERR_PREAMBLE))
            msg = str(ctx.exception)
            self.assertIn("klt sim (grid) returned no JSON report (rc=2)", msg)
            self.assertIn("batch job klt-sim-b4c5875b12ef: submitted", msg)

    def test_the_fallback_excerpt_quotes_the_tail_not_the_head(self):
        """The useful part of a failed `klt` run is at the END of stderr."""
        noise = "\n".join(f"klt: progress line {i}" for i in range(400))
        err = "FIRST-LINE-OF-STDERR\n" + noise + "\nLAST-LINE-OF-STDERR"
        self.assertGreater(len(err), klt_sim.ERROR_TEXT_CHARS)
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(klt_sim.SubmitError) as ctx:
                self._submit(Path(td), backend="batch", runner=_runner(rc=1, err=err))
            msg = str(ctx.exception)
            self.assertIn("LAST-LINE-OF-STDERR", msg)
            self.assertNotIn("FIRST-LINE-OF-STDERR", msg)

    def test_a_short_fallback_excerpt_is_quoted_whole(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(klt_sim.SubmitError) as ctx:
                self._submit(Path(td), backend="batch",
                             runner=_runner(rc=1, err="Traceback: boom"))
            self.assertIn("Traceback: boom", str(ctx.exception))


class TestRunInfo(unittest.TestCase):
    """A sharded batch run carries job identity under
    `environment.remote.fleet[]`, not on `environment.remote` itself."""

    def _shard(self, job, pdk="f6eeac7", ng="ngspice-47", runner="0.9.0",
               client="0.9.0", compat="match"):
        return {
            "job_id": job, "state": "done", "exit_code": "0",
            "instance_type": "c7i.8xlarge", "elapsed_seconds": 258,
            "runner_klt_version": runner,
            "client_klt_version": client,
            "runner_compatibility": compat,
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

    def test_a_lost_shard_prevents_consensus_and_preserves_reported_values(self):
        info = self._info({"fleet": [self._shard("a"), None]})
        self.assertIsNone(info["worker_pdk"])
        self.assertIsNone(info["worker_ngspice"])
        self.assertEqual(info["worker_pdks_seen"], ["sky130A @ f6eeac7"])
        self.assertEqual(info["worker_ngspice_seen"], ["ngspice-47"])
        self.assertEqual([j["job_id"] for j in info["jobs"]], ["a"])

    def test_every_shards_version_skew_facts_reach_jobs(self):
        """Issue #888: `runner_compatibility` / `client_klt_version` are
        PER-SHARD and absent from `environment.remote` on a sharded run, so a
        campaign that reads them off `remote` sees no skew however the shards
        disagree. `jobs[]` carries them, one entry per shard."""
        remote = {"fleet": [self._shard("a"),
                            self._shard("b", runner="0.5.0", compat="mismatch")]}
        info = self._info(remote)
        self.assertEqual(
            [(j["runner_klt_version"], j["client_klt_version"], j["runner_compatibility"])
             for j in info["jobs"]],
            [("0.9.0", "0.9.0", "match"), ("0.5.0", "0.9.0", "mismatch")])
        for key in ("runner_klt_version", "client_klt_version", "runner_compatibility"):
            self.assertNotIn(key, info["remote"],
                             "the sharded envelope carries no run-level version keys")

    def test_single_job_version_skew_facts_also_reach_jobs(self):
        info = self._info(dict(self._shard("solo", runner="0.5.0", compat="mismatch")))
        self.assertEqual(info["jobs"][0]["client_klt_version"], "0.9.0")
        self.assertEqual(info["jobs"][0]["runner_compatibility"], "mismatch")

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

    # -- the executing worker's ngspice binary digest (issue #811) -----------
    # `klt sim`'s collector reports ONE digest for the workers that executed
    # the run, and only when every worker supplied the same 64-hex value; a
    # missing or disagreeing capture is a null digest plus a reason.

    WORKER_DIGEST = "39ca1adb826660324c3626f72bd946ec40704f0f3fc8e243c623f76e24b3eee2"

    def _engine_report(self, digest, host="worker", reason=None):
        report = {"status": "pass", "corners": [], "environment": {
            "engine_host": host,
            "engine_build": {"probe": "ok", "binary_sha256": digest,
                             "reason": reason},
            "remote": self._shard("solo"),
            "backend": {"resolved": "batch"},
        }}
        return klt_sim.run_info(report)

    def test_a_single_worker_digest_is_reported_whole(self):
        info = self._engine_report(self.WORKER_DIGEST)
        self.assertEqual(info["engine_host"], "worker")
        self.assertEqual(info["worker_ngspice_binary_sha256"], self.WORKER_DIGEST)
        self.assertIsNone(info["worker_ngspice_binary_sha256_reason"])

    def test_a_null_digest_is_none_and_keeps_the_collectors_reason(self):
        """A missing or mixed worker digest leaves the record's worker-hash
        condition unmet: None, never the host's own binary standing in."""
        for reason in ("worker_digest_disagreement", None):
            with self.subTest(reason=reason):
                info = self._engine_report(None, reason=reason)
                self.assertIsNone(info["worker_ngspice_binary_sha256"])
                self.assertEqual(info["worker_ngspice_binary_sha256_reason"], reason)

    def test_anything_but_a_lowercase_64_hex_string_is_not_a_digest(self):
        for bad in (self.WORKER_DIGEST[:32], self.WORKER_DIGEST.upper(),
                    f"sha256:{self.WORKER_DIGEST}", 39, True, ""):
            with self.subTest(bad=bad):
                info = self._engine_report(bad)
                self.assertIsNone(info["worker_ngspice_binary_sha256"])

    def test_an_engine_that_ran_on_the_submitting_host_is_not_a_worker(self):
        info = self._engine_report(self.WORKER_DIGEST, host="local")
        self.assertIsNone(info["worker_ngspice_binary_sha256"])

    def test_the_clients_own_digest_is_never_read_as_the_workers(self):
        """klayout-tools#7356 preserves the submitting build beside the
        workers' (same banner, possibly a different executable)."""
        info = klt_sim.run_info({"status": "pass", "environment": {
            "engine_host": "worker",
            "engine_build": {"binary_sha256": None},
            "client_engine_build": {"binary_sha256": self.WORKER_DIGEST},
            "remote": self._shard("solo"),
        }})
        self.assertIsNone(info["worker_ngspice_binary_sha256"])

    def test_a_report_without_an_engine_build_reports_no_digest(self):
        info = klt_sim.run_info({"status": "pass", "environment": {}})
        self.assertIsNone(info["engine_host"])
        self.assertIsNone(info["worker_ngspice_binary_sha256"])
        self.assertIsNone(info["worker_ngspice_binary_sha256_reason"])


class TestExecutingEnvironment(unittest.TestCase):
    """Issue #1094: ONE worker-vs-submitting-host resolution for every batch
    driver, so a record's Environment block and the prose beside it are
    rendered from the same dict and cannot disagree.

    `prov` is the submitting host's own provenance; the helper reads
    `pdk_line` and `ng_version` off it and nothing else, so a stand-in
    object stands in for the PDK here.
    """

    HOST = ("sky130A @ f6eeac7", "ngspice-47")

    @staticmethod
    def _prov(*host) -> object:
        return types.SimpleNamespace(pdk_line=host[0], ng_version=host[1])

    @staticmethod
    def _info(pdk="sky130A @ deadbeef", ng="ngspice-47", runner="klt 9.9.9") -> dict:
        jobs = [{"job_id": "job-42", "runner_klt_version": runner}] if runner else []
        return {"worker_pdk": pdk, "worker_ngspice": ng, "jobs": jobs}

    def _env(self, info, *host) -> dict:
        return klt_sim.executing_environment(self._prov(*(host or self.HOST)), info)

    def test_a_run_that_reported_itself_is_named_verbatim(self):
        env = self._env(self._info())
        self.assertTrue(env["known"])
        self.assertEqual(env["pdk"], "sky130A @ deadbeef")
        self.assertEqual(env["ngspice"], "ngspice-47")
        self.assertEqual(env["runner_klt"], "klt 9.9.9")
        self.assertEqual(env["attribution_extra"], {
            "PDK / ngspice above": "as run by the executing worker",
            "submitting host PDK / ngspice": "sky130A @ f6eeac7 / ngspice-47",
        })
        self.assertFalse(env["matches_host"], "deadbeef is not the host's commit")

    def test_a_worker_stamp_that_names_no_variant_is_not_re_prefixed(self):
        """`run_info()` already formats `"{variant} @ {sha}"`. Six private
        copies re-split that and re-hardcoded `"sky130A @ ..."`, naming a
        variant the worker never reported."""
        env = self._env(self._info(pdk="other_pdks deadbeef"))
        self.assertEqual(env["pdk"], "other_pdks deadbeef")
        self.assertEqual(env["ngspice"], "ngspice-47", "the token, not re-split")

    def test_a_run_that_reported_no_runner_version_reports_none(self):
        env = self._env(self._info(runner=None))
        self.assertIsNone(env["runner_klt"])

    def test_several_runs_that_agree_are_one_known_environment(self):
        """One request per variant: every run's worker must report the same
        pair before the campaign's numbers are attributed to a known one."""
        env = self._env([self._info(), self._info(runner=None), self._info()])
        self.assertTrue(env["known"])
        self.assertEqual(env["pdk"], "sky130A @ deadbeef")
        self.assertEqual(env["runner_klt"], "klt 9.9.9",
                         "the first runner version any run reported")
        env = self._env(self._info() for _ in range(2))
        self.assertTrue(env["known"], "any iterable of run-info dicts")

    def test_one_disagreeing_run_makes_the_whole_campaign_unknown(self):
        for disagreeing in (self._info(pdk="sky130A @ caffee"),
                           self._info(ng="ngspice-46")):
            with self.subTest(run=disagreeing):
                env = self._env([self._info(), disagreeing])
                self.assertFalse(env["known"])
                self.assertEqual(env["pdk"], self.HOST[0])
                self.assertEqual(env["ngspice"], self.HOST[1])

    def test_a_run_that_is_not_a_run_info_dict_reports_nothing(self):
        """A missing entry is a run that reported nothing, not a run to skip:
        skipping it would let the remaining runs stand for the campaign."""
        env = self._env([self._info(), None])
        self.assertFalse(env["known"])
        self.assertEqual(env["pdk"], self.HOST[0])

    def test_a_half_known_run_falls_back_on_both_lines(self):
        """The defect two private copies carried: they filled the PDK line
        from the worker and the ngspice line from the submitting host, then
        labelled the PAIR by whether both were present."""
        for half in (self._info(ng=None), self._info(pdk=None)):
            with self.subTest(run=half):
                env = self._env(half)
                self.assertFalse(env["known"])
                self.assertEqual(env["pdk"], self.HOST[0],
                                 "the worker's PDK is not stamped alone")
                self.assertEqual(env["ngspice"], self.HOST[1])
                self.assertEqual(
                    env["attribution_extra"]["PDK / ngspice above"],
                    "submitting host (worker environment unknown)")
                self.assertIn("The worker reports do not establish a single PDK and simulator pair",
                              env["note"])

    def test_no_run_info_falls_back_to_the_submitting_host(self):
        for info in (None, {}, []):
            with self.subTest(info=info):
                env = self._env(info)
                self.assertFalse(env["known"])
                self.assertEqual(env["pdk"], self.HOST[0])
                self.assertEqual(env["ngspice"], self.HOST[1])
                self.assertIsNone(env["runner_klt"])
                self.assertFalse(env["matches_host"])

    def test_an_empty_report_is_not_a_report(self):
        for blank in (None, ""):
            with self.subTest(blank=blank):
                env = self._env(self._info(pdk=blank, ng=blank))
                self.assertFalse(env["known"])
                self.assertEqual(env["attribution_extra"]["PDK / ngspice above"],
                                 "submitting host (worker environment unknown)")

    def test_matches_host_compares_the_pdk_commit_and_the_whole_version(self):
        def matches(*host, pdk="sky130A @ deadbeef", ng="ngspice-47") -> bool:
            return self._env(self._info(pdk=pdk, ng=ng), *host)["matches_host"]

        same = ("sky130A @ deadbeef", "ngspice-47")
        self.assertTrue(matches(*same))
        self.assertTrue(matches(" sky130A @  deadbeef ", " ngspice-47 \n"),
                        "surrounding whitespace is not a difference")
        self.assertTrue(matches(*same, pdk="open_pdks deadbeef"),
                        "the stamp `run_info()` emits when no variant is named")
        self.assertFalse(matches("sky130A @ cafe", "ngspice-47"))
        self.assertFalse(matches("sky130A @ deadbeef", "ngspice-46"))
        self.assertFalse(matches("sky130A @ deadbeef", "ngspice-47 (custom build)"),
                         "a version is compared whole, not by its last token")
        self.assertFalse(
            matches("sky130A @ deadbeef (unverified -- no SOURCES file or volare layout)",
                    "ngspice-47"),
            "an unverifiable host install never equals a worker's commit")

    def test_an_unknown_worker_never_counts_as_a_match(self):
        for half in (self._info(ng=None), self._info(pdk=None)):
            with self.subTest(run=half):
                self.assertFalse(self._env(half, "sky130A @ deadbeef", "ngspice-47")
                                 ["matches_host"])

    def test_pdk_commit_token(self):
        for text, token in (
            ("sky130A @ deadbeef", "deadbeef"),
            ("open_pdks deadbeef", "deadbeef"),
            (" sky130A @  deadbeef ", "deadbeef"),
            ("sky130A @ deadbeef (unverified -- no SOURCES file or volare layout)",
             "layout)"),
        ):
            with self.subTest(text=text):
                self.assertEqual(klt_sim.pdk_commit_token(text), token)

    def test_the_note_says_what_the_block_label_says(self):
        env = self._env(self._info(pdk="sky130A @ f6eeac7"))
        self.assertIn("names the PDK and ngspice of the EXECUTING worker", env["note"])
        self.assertIn("They are the same for this run.", env["note"])
        self.assertNotIn("differ", env["note"].lower())
        self.assertEqual(env["attribution_extra"]["PDK / ngspice above"],
                         "as run by the executing worker")

        env = self._env(self._info())
        self.assertIn("**They differ for this run**", env["note"])
        self.assertNotIn("same for this run", env["note"])
        self.assertEqual(env["attribution_extra"]["PDK / ngspice above"],
                         "as run by the executing worker")

        env = self._env(None)
        self.assertIn("The worker reports do not establish a single PDK and simulator pair", env["note"])
        self.assertIn("names the SUBMITTING host's PDK and ngspice", env["note"])
        self.assertNotIn("differ", env["note"].lower())
        self.assertTrue(env["attribution_extra"]["PDK / ngspice above"]
                        .startswith("submitting host"))


class TestMeasurementsByCorner(unittest.TestCase):
    """Issue #904: the per-corner transcription is ONE harness function.

    TestReportReader (input-drive-budget) and TestReadCornersReport (vcm)
    keep pinning it through their campaigns' delegations; these pin the
    helper's own contract directly -- including the `supply_key` argument
    the campaign module constants used to bake in.
    """

    @staticmethod
    def _report(**corner):
        base = {
            "process": "tt",
            "temperature_c": 27.0,
            "supply_v": {"vsup": 1.8},
            "status": "pass",
            "measurements": [{"name": "step.ctop", "value": 1.5}],
        }
        base.update(corner)
        return {"status": "pass", "corners": [base], "environment": {}}

    def test_keys_by_corner_id_and_threads_run_info(self):
        out, info = klt_sim.measurements_by_corner(self._report(), "vsup")
        self.assertEqual(out, {"tt_27c_1.80v": {"step.ctop": 1.5}})
        self.assertEqual(info["status"], "pass")

    def test_supply_key_selects_which_supply_to_key_on(self):
        out, _info = klt_sim.measurements_by_corner(
            self._report(supply_v={"vdig": 3.3}), "vdig")
        self.assertEqual(list(out), ["tt_27c_3.30v"])

    def test_an_error_envelope_is_refused_not_read_as_zero_corners(self):
        with self.assertRaises(ValueError):
            klt_sim.measurements_by_corner({"error": {"code": "batch_no_capacity"}}, "vsup")

    def test_an_error_corner_is_nulled_not_partially_read(self):
        for status in ("error", "inconclusive"):
            out, _info = klt_sim.measurements_by_corner(
                self._report(status=status), "vsup")
            self.assertEqual(out["tt_27c_1.80v"], {"step.ctop": None}, status)

    def test_an_envelope_beside_corners_is_still_readable(self):
        report = self._report()
        report["error"] = {"code": "partial"}
        out, _info = klt_sim.measurements_by_corner(report, "vsup")
        self.assertEqual(out["tt_27c_1.80v"], {"step.ctop": 1.5})

    def test_a_non_object_report_is_refused(self):
        with self.assertRaises(ValueError):
            klt_sim.measurements_by_corner([{"process": "tt"}], "vsup")


class TestFinite(unittest.TestCase):
    def test_real_finite_numbers_only(self):
        cases = [(1.5, True), (3, True), (True, False), (False, False),
                 (float("nan"), False), (float("inf"), False),
                 (None, False), ("1.5", False)]
        for v, want in cases:
            self.assertIs(klt_sim.finite(v), want, v)


class TestSplitFragment(unittest.TestCase):
    """Issue #1030: the fragment split the deck-building campaigns were each
    re-copying. Synthetic fragments here; each campaign's own suite also
    drives this parser through its wrapper against its real committed
    fragment, including the rejection paths below."""

    FRAGMENT = (
        "* committed stimulus\n"
        "VSUP SUP 0 DC {vdd_val}\n"
        ".meas tran v_a avg v(na) from=1n to=2n\n"
        ".meas tran i_s avg i(vsup) from=1n to=2n\n"
        ".tran 0.5n 2.5u\n"
    )

    def test_splits_body_meas_cards_and_tran_args(self):
        body, meas, tran = klt_sim.split_fragment(self.FRAGMENT, ["i_s", "v_a"])
        self.assertEqual(body, "* committed stimulus\nVSUP SUP 0 DC {vdd_val}\n")
        self.assertEqual(meas, [
            ".meas tran v_a avg v(na) from=1n to=2n",
            ".meas tran i_s avg i(vsup) from=1n to=2n",
        ])
        self.assertEqual(tran, "0.5n 2.5u")

    def test_cards_are_recognized_indented_and_case_insensitive(self):
        text = self.FRAGMENT.replace(".meas tran i_s", "  .MEAS tran i_s")
        _body, meas, _tran = klt_sim.split_fragment(text, ["i_s", "v_a"])
        self.assertEqual(meas[-1], ".MEAS tran i_s avg i(vsup) from=1n to=2n")

    def test_a_second_tran_card_is_refused(self):
        with self.assertRaises(RuntimeError):
            klt_sim.split_fragment(self.FRAGMENT + ".tran 1n 2n\n", ["i_s", "v_a"])

    def test_no_tran_card_is_refused(self):
        text = "\n".join(ln for ln in self.FRAGMENT.splitlines()
                         if not ln.strip().lower().startswith(".tran")) + "\n"
        with self.assertRaises(RuntimeError):
            klt_sim.split_fragment(text, ["i_s", "v_a"])

    def test_a_missing_expected_name_is_refused(self):
        text = self.FRAGMENT.replace(".meas tran i_s avg i(vsup) from=1n to=2n\n", "")
        with self.assertRaises(RuntimeError):
            klt_sim.split_fragment(text, ["i_s", "v_a"])

    def test_an_extra_expected_name_is_refused(self):
        with self.assertRaises(RuntimeError):
            klt_sim.split_fragment(self.FRAGMENT, ["i_s", "v_a", "v_b"])

    def test_a_repeated_card_name_is_refused(self):
        text = self.FRAGMENT + ".meas tran v_a avg v(nb) from=1n to=2n\n"
        with self.assertRaises(RuntimeError):
            klt_sim.split_fragment(text, ["i_s", "v_a"])


class TestSavedVectors(unittest.TestCase):
    """Issue #1030: the `.meas`-card save-set scan, shared with
    split_fragment(). Sorted, de-duplicated, lowercased -- the exact
    normalization both private copies performed."""

    def test_sorted_deduplicated_and_lowercased(self):
        cards = [
            ".meas tran v_a avg V(Dout9) from=1n to=2n",
            ".meas tran v_a2 avg v(dout9) from=1n to=2n",
            ".meas tran i_s avg I(VSUP) from=1n to=2n",
            ".meas tran i_s2 avg i(vsup) from=1n to=2n",
        ]
        self.assertEqual(klt_sim.saved_vectors(cards),
                         ["i(vsup)", "v(dout9)"])

    def test_a_card_without_a_vector_reference_contributes_nothing(self):
        self.assertEqual(klt_sim.saved_vectors([".meas tran t1 param=1"]), [])

    def test_no_cards_means_no_vectors(self):
        self.assertEqual(klt_sim.saved_vectors([]), [])


class TestOatCorners(unittest.TestCase):
    """Issue #1052: the OAT `corners`/`exclude` expansion is ONE harness
    function. The four consolidated campaigns keep pinning their full
    request shapes through their own suites; these pin the helper's own
    contract directly, on small grids small enough to eyeball."""

    def test_a_single_corner_covers_its_product_so_exclude_is_empty(self):
        corners, exclude = klt_sim.oat_corners(["tt_27c_1.80v"], "vsup")
        self.assertEqual(corners, {
            "process": ["tt"],
            "supply_v": {"vsup": [1.8]},
            "temperature_c": [27.0],
        })
        self.assertEqual(exclude, [])

    def test_an_oat_subset_excludes_the_exact_cartesian_complement(self):
        corners, exclude = klt_sim.oat_corners(
            ["tt_27c_1.80v", "tt_125c_1.80v", "ss_27c_1.80v"], "vsup")
        self.assertEqual(corners, {
            "process": ["ss", "tt"],
            "supply_v": {"vsup": [1.8]},
            "temperature_c": [27.0, 125.0],
        })
        self.assertEqual(exclude, [
            {"process": "ss", "temperature_c": 125.0, "supply_v": {"vsup": 1.8}},
        ])

    def test_the_complement_walks_sorted_axes_in_product_order(self):
        _, exclude = klt_sim.oat_corners(
            ["tt_27c_1.80v", "ss_-40c_1.80v", "tt_125c_1.62v"], "vsup")
        self.assertEqual(
            [(e["process"], e["temperature_c"], e["supply_v"]["vsup"]) for e in exclude],
            [("ss", -40.0, 1.62), ("ss", 27.0, 1.62), ("ss", 27.0, 1.8),
             ("ss", 125.0, 1.62), ("ss", 125.0, 1.8),
             ("tt", -40.0, 1.62), ("tt", -40.0, 1.8), ("tt", 27.0, 1.62),
             ("tt", 125.0, 1.8)],
        )

    def test_supply_key_threads_through_to_both_blocks(self):
        corners, exclude = klt_sim.oat_corners(
            ["tt_27c_1.80v", "tt_125c_1.80v", "ss_27c_1.80v"], "vdig")
        self.assertEqual(list(corners["supply_v"]), ["vdig"])
        self.assertEqual(exclude[0]["supply_v"], {"vdig": 1.8})

    def test_an_unparseable_corner_id_is_refused(self):
        with self.assertRaises(ValueError):
            klt_sim.oat_corners(["not-a-corner-id"], "vsup")


class TestBuildOatRequest(unittest.TestCase):
    """Issues #1052/#1054: the `klt sim` request assembly around
    `oat_corners()`. The exact dicts below -- values AND insertion order --
    are what the six consolidated drivers emitted privately; the order half
    is what makes the serialized request byte-for-byte identical."""

    STEPS = [{"name": "s0", "analysis": {"kind": "ac", "args": "lin 1 1e6 1e6"}}]

    def test_analysis_steps_mode_builds_the_exact_driver_shape(self):
        req = klt_sim.build_oat_request(
            "tb.spice", ["tt_27c_1.80v", "ss_27c_1.80v", "tt_125c_1.80v"],
            "vsup", analysis_steps=self.STEPS, timeout_s=300.0,
            backend="batch")
        self.assertEqual(req, {
            "netlist": "tb.spice",
            "engine": "ngspice",
            "models": {"pdk": "sky130A",
                       "lib": "libs.tech/combined/sky130.lib.spice"},
            "corners": {"process": ["ss", "tt"],
                        "supply_v": {"vsup": [1.8]},
                        "temperature_c": [27.0, 125.0]},
            "analysis_steps": self.STEPS,
            "options": {"timeout_s": 300.0, "keep_artifacts": True},
            "exclude": [{"process": "ss", "temperature_c": 125.0,
                         "supply_v": {"vsup": 1.8}}],
            "backend": "batch",
        })
        self.assertEqual(list(req), ["netlist", "engine", "models", "corners",
                                     "analysis_steps", "options", "exclude",
                                     "backend"])

    def test_analysis_and_measurements_mode_builds_the_exact_driver_shape(self):
        analysis = {"kind": "tran", "args": "0.8n 2.5u 0 0.8n"}
        measurements = [{"name": "t_hi", "spice": ".meas tran t_hi ...", "unit": "s"}]
        req = klt_sim.build_oat_request(
            "tb.spice", ["tt_27c_1.80v"], "vdig", analysis=analysis,
            measurements=measurements, pdk="sky130B", models_lib="x/y.lib",
            batch={"capacity_wait_s": 5})
        self.assertEqual(req, {
            "netlist": "tb.spice",
            "engine": "ngspice",
            "models": {"pdk": "sky130B", "lib": "x/y.lib"},
            "corners": {"process": ["tt"], "supply_v": {"vdig": [1.8]},
                        "temperature_c": [27.0]},
            "analysis": analysis,
            "measurements": measurements,
            "options": {"timeout_s": 900.0, "keep_artifacts": True},
            "batch": {"capacity_wait_s": 5},
        })
        self.assertEqual(list(req), ["netlist", "engine", "models", "corners",
                                     "analysis", "measurements", "options",
                                     "batch"])

    def test_a_covering_grid_omits_exclude_and_none_omits_backend(self):
        req = klt_sim.build_oat_request(
            "tb.spice", ["tt_27c_1.80v"], "vsup", analysis_steps=self.STEPS)
        self.assertNotIn("exclude", req)
        self.assertNotIn("backend", req)
        self.assertNotIn("batch", req)

    def test_batch_is_copied_not_shared(self):
        batch = {"capacity_wait_s": 5}
        req = klt_sim.build_oat_request(
            "tb.spice", ["tt_27c_1.80v"], "vsup",
            analysis_steps=self.STEPS, batch=batch)
        self.assertEqual(req["batch"], batch)
        self.assertIsNot(req["batch"], batch)

    def test_hosts_over_one_appends_remote_last(self):
        """Issue #1054: the two `remote.hosts` drivers' `remote` block came
        after `backend`, so the helper must append it after every other
        conditional key to keep the serialized request identical."""
        req = klt_sim.build_oat_request(
            "tb.spice", ["tt_27c_1.80v", "ss_27c_1.80v", "tt_125c_1.80v"],
            "vsup", analysis_steps=self.STEPS, backend="batch", hosts=2)
        self.assertEqual(req["remote"], {"hosts": 2})
        self.assertEqual(list(req), ["netlist", "engine", "models", "corners",
                                     "analysis_steps", "options", "exclude",
                                     "backend", "remote"])

    def test_hosts_of_none_zero_or_one_omits_remote(self):
        for hosts in (None, 0, 1):
            with self.subTest(hosts=hosts):
                req = klt_sim.build_oat_request(
                    "tb.spice", ["tt_27c_1.80v"], "vsup",
                    analysis_steps=self.STEPS, hosts=hosts)
                self.assertNotIn("remote", req)
                self.assertNotIn("backend", req)

    def test_both_modes_at_once_is_refused(self):
        with self.assertRaises(ValueError):
            klt_sim.build_oat_request(
                "tb.spice", ["tt_27c_1.80v"], "vsup", analysis_steps=self.STEPS,
                analysis={"kind": "tran"}, measurements=[])

    def test_neither_mode_is_refused(self):
        with self.assertRaises(ValueError):
            klt_sim.build_oat_request("tb.spice", ["tt_27c_1.80v"], "vsup")

    def test_half_of_the_pair_is_refused(self):
        for kwargs in ({"analysis": {"kind": "tran"}},
                       {"measurements": []}):
            with self.subTest(kwargs=sorted(kwargs)):
                with self.assertRaises(ValueError):
                    klt_sim.build_oat_request(
                        "tb.spice", ["tt_27c_1.80v"], "vsup", **kwargs)


class TestNoCampaignModuleKeepsItsOwnFragmentScan(unittest.TestCase):
    """Issue #1030: the fragment split and the saved-vector scan live in
    `harness.klt_sim`; a campaign module re-copies them at its own risk.
    Keyed on the artifacts a private copy necessarily carries: the
    vector-reference regex (`_VECTOR_RE =`) and the card-classification scan
    of `.tran` lines. (`common.py`'s legitimate `startswith(".meas")` filter
    over its own GENERATED measure lines is why `.meas` is not a marker --
    that is a name filter, not a fragment parser.)"""

    def test_no_campaign_module_rescans_the_fragment_itself(self):
        for p in sorted(SIM_DIR.glob("*/*.py")) + sorted(SIM_DIR.glob("*/*/*.py")):
            if p.parent.name in ("harness", "tests") or "harness/" in p.as_posix():
                continue
            text = p.read_text()
            for marker in ('_VECTOR_RE =',
                           'startswith(".tran")', "startswith('.tran')"):
                with self.subTest(module=f"{p.parent.name}/{p.name}", marker=marker):
                    self.assertNotIn(
                        marker, text,
                        f"{p.parent.name}/{p.name} re-copies the fragment scan -- "
                        "call harness.klt_sim.split_fragment() / "
                        "harness.klt_sim.saved_vectors() instead (issue #1030)")


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

    def test_only_the_harness_walks_the_sharded_envelope(self):
        """Issue #888: `run_info()` is the ONE place that knows the sharded
        report shape, so no campaign has to recognise it.

        The driver scan above cannot see this class of defect -- the read it
        was written for lived in a campaign LIBRARY module, not a `run_*.py`
        driver, and it reached for the version keys rather than `job_id`. So
        this assertion covers every campaign module and keys on the envelope
        itself: a file that names `remote["fleet"]` is a second reader of the
        shape, whatever keys it goes on to pull out of it. Since #944 the
        matcher parses each module, so a module that does not parse fails
        here too -- a syntactically broken module must not slip past the
        guard silently.
        """
        for p in sorted(SIM_DIR.glob("*/*.py")) + sorted(SIM_DIR.glob("*/*/*.py")):
            if p.parent.name in ("harness", "tests") or "harness/" in p.as_posix():
                continue
            text = p.read_text()
            try:
                ast.parse(text)
            except SyntaxError as exc:
                self.fail(f"{p.parent.name}/{p.name} does not parse ({exc}) -- "
                          "the sharded-envelope guard cannot see through a "
                          "broken module; fix or remove it")
            reads = _reads_sharded_envelope(text)
            with self.subTest(module=f"{p.parent.name}/{p.name}"):
                self.assertEqual(
                    reads, [],
                    f"{p.parent.name}/{p.name} reads {reads} itself -- read run-level "
                    "facts through harness.klt_sim.run_info() instead; its jobs[] "
                    "already carries one entry per shard")

    def test_envelope_matcher_fires_on_every_spelling_of_the_read(self):
        """Issue #918: the envelope matcher keys on the read, not on
        spellings -- assert it, so the next spelling gap is a failure here
        rather than a silent pass. Issue #944: the four accessor spellings
        the `get`-only regex missed (`.pop`, `.setdefault`, plus
        `itemgetter`) are positives too. Decoys keep the broadening honest:
        text that merely mentions `fleet` must not fire, and the list
        literal the regex era flagged (`KEYS = ["fleet", "pdk"]`) must stay
        quiet -- a `List` is not a `Subscript`."""
        positives = [
            'remote["fleet"]',
            "remote['fleet']",
            'remote.get("fleet")',
            "remote.get('fleet')",
            'remote.get("fleet", [])',
            "remote.get('fleet', [])",
            'remote[ "fleet" ]',
            'remote[\n    "fleet"\n]',
            'remote.pop("fleet")',
            "remote.pop('fleet')",
            'remote.setdefault("fleet", [])',
            'r.pop("fleet", None)',
            'itemgetter("fleet")',
        ]
        for sample in positives:
            with self.subTest(sample=sample):
                self.assertTrue(_reads_sharded_envelope(sample), sample)
        for decoy in ['FLEET_KEY = "fleet"',
                      'remote.get(key)',
                      'KEYS = ["fleet", "pdk"]',
                      "a fleet of ships",
                      '# the record names "fleet" twice',
                      "# walks the fleet envelope"]:
            with self.subTest(decoy=decoy):
                self.assertEqual(_reads_sharded_envelope(decoy), [], decoy)

    def test_no_driver_carries_its_own_corner_measurements_reader(self):
        """Issue #904: the per-corner transcription (`corner_id` plus the
        `error`/`inconclusive` null-out) is
        `harness.klt_sim.measurements_by_corner()`, not a per-driver copy.

        The marker is the reader's own null-out test -- a corner DICT's
        `.get("status")` compared against that pair -- which the two
        deliberately-unconsolidated readers do not match: they key by a
        different tuple and decode UnitResult objects, never corner dicts.
        """
        for p in sorted(SIM_DIR.glob("*/run_*.py")):
            with self.subTest(driver=p.parent.name):
                self.assertNotIn(
                    '.get("status") in ("error", "inconclusive")',
                    p.read_text(),
                    "use harness.klt_sim.measurements_by_corner() for the "
                    "per-corner transcription",
                )


class TestNoCampaignModuleKeepsItsOwnOatExpansion(unittest.TestCase):
    """Issues #1052/#1054: the OAT `corners`/`exclude` expansion and the
    request assembly around it live in `harness.klt_sim.oat_corners()` /
    `build_oat_request()`; a campaign module re-copies them at its own risk.
    A new campaign that copies a sibling's block instead of calling the
    helper fails here -- this is the request-side counterpart of
    TestNoDriverKeepsItsOwnSubmitBlock above (#865) and of the fragment-scan
    guard (#1030).

    The marker is the axis-triple dict literal itself (see
    `_oat_axis_dicts`): both the `corners` block and every `exclude` entry
    of a private copy carry it, and the deliberately-unconsolidated shapes
    (reference-drive-budget's zipped `params` rows, the input sweep's
    single-corner `params` sweep) do not.
    """

    #: The six drivers #1052 and #1054 migrated; they must stay delegated
    #: forever.
    CONSOLIDATED = {
        "input-drive-budget", "vcm-drive-budget",
        "top-plate-cpar", "digital-partition",
        "cdac-bit-trial-settling", "sampling-cdac-handoff",
    }

    #: Campaigns that still carry a private copy. #1054 migrated the last
    #: two, so the set is empty and must stay empty: the exactness test
    #: below fails on any drift in either direction, and a NEW private copy
    #: is not coverable by adding to it.
    STILL_PRIVATE: set[str] = set()

    @staticmethod
    def _campaign_modules() -> list[Path]:
        return [p for p in sorted(SIM_DIR.glob("*/*.py"))
                + sorted(SIM_DIR.glob("*/*/*.py"))
                if p.parent.name not in ("harness", "tests")
                and "harness/" not in p.as_posix()]

    def test_every_consolidated_driver_delegates(self):
        for name in self.CONSOLIDATED:
            mods = [p for p in self._campaign_modules()
                    if p.parent.name == name]
            self.assertTrue(mods, f"no campaign modules found under {name}/")
            for p in mods:
                with self.subTest(module=f"{name}/{p.name}"):
                    self.assertEqual(
                        _oat_axis_dicts(p.read_text()), [],
                        f"{name}/{p.name} re-copies the OAT corners/exclude "
                        "expansion -- call harness.klt_sim.oat_corners() / "
                        "build_oat_request() instead (issue #1052)")

    def test_no_other_campaign_module_re_copies_the_expansion(self):
        for p in self._campaign_modules():
            if p.parent.name in self.STILL_PRIVATE:
                continue
            text = p.read_text()
            try:
                ast.parse(text)
            except SyntaxError as exc:
                self.fail(f"{p.parent.name}/{p.name} does not parse ({exc}) -- "
                          "the OAT-expansion guard cannot see through a "
                          "broken module; fix or remove it")
            with self.subTest(module=f"{p.parent.name}/{p.name}"):
                self.assertEqual(
                    _oat_axis_dicts(text), [],
                    f"{p.parent.name}/{p.name} re-copies the OAT "
                    "corners/exclude expansion -- call "
                    "harness.klt_sim.build_oat_request() instead "
                    "(issue #1052)")

    def test_no_campaign_still_carries_a_private_copy(self):
        """Keeps the migration complete: #1054 emptied the allowlist, so any
        campaign found re-copying the expansion is a regression (or a fresh
        copy) and must be migrated onto the helper, not allowlisted."""
        private = {p.parent.name for p in self._campaign_modules()
                   if _oat_axis_dicts(p.read_text())}
        self.assertEqual(
            private, self.STILL_PRIVATE,
            "campaigns are still carrying a private OAT copy "
            f"({sorted(private)}) -- migrate them onto "
            "harness.klt_sim.build_oat_request() (#1054 left none behind)")

    def test_the_axis_triple_matcher_fires_on_both_artifacts_of_a_copy(self):
        """The matcher keys on the dict literal's key set, so both halves of
        a private copy fire (the `corners` block and the `exclude` entry),
        while the neighboring legitimate shapes stay quiet."""
        fires = [
            'exclude = [{"process": p, "temperature_c": t, "supply_v": {k: v}}]',
            'corners = {"process": procs, "supply_v": {k: vdds}, "temperature_c": temps}',
            "{'process': p, 'temperature_c': t, 'supply_v': {k: v}}",
        ]
        for sample in fires:
            with self.subTest(sample=sample):
                self.assertTrue(_oat_axis_dicts(sample), sample)
        for decoy in [
            'exclude = [{"process": p, "temperature_c": t, "params": {k: v}}]',
            '"corners": {"process": ps, "temperature_c": ts, "params": {}}',
            '{"process": p, "temperature_c": t}',
            '{"process": p, "temperature_c": t, "supply_v": sv, "extra": 1}',
            'c.get("supply_v")',
        ]:
            with self.subTest(decoy=decoy):
                self.assertEqual(_oat_axis_dicts(decoy), [], decoy)


class TestClientVersion(unittest.TestCase):
    """Issue #1086: one local `klt --version` probe for record metadata."""

    def test_returns_stripped_version_string_when_available(self):
        calls = []
        ver = klt_sim.client_version(runner=_runner(rc=0, out="  klt 0.9.3\n", calls=calls))
        self.assertEqual(ver, "klt 0.9.3")
        self.assertEqual(calls, [["klt", "--version"]])

    def test_returns_placeholder_when_executable_is_missing(self):
        def missing(argv):
            raise FileNotFoundError(argv[0])

        self.assertEqual(
            klt_sim.client_version(runner=missing),
            "(klt --version unavailable)",
        )
        self.assertEqual(
            klt_sim.CLIENT_VERSION_UNAVAILABLE,
            "(klt --version unavailable)",
        )

    def test_returns_placeholder_on_other_os_errors(self):
        def denied(argv):
            raise PermissionError(argv[0])

        self.assertEqual(
            klt_sim.client_version(runner=denied),
            klt_sim.CLIENT_VERSION_UNAVAILABLE,
        )

    def test_returns_placeholder_when_stdout_is_empty_or_whitespace(self):
        for out in ("", "   \n\t "):
            with self.subTest(out=out):
                self.assertEqual(
                    klt_sim.client_version(runner=_runner(rc=0, out=out)),
                    klt_sim.CLIENT_VERSION_UNAVAILABLE,
                )

    def test_returns_placeholder_when_probe_exits_nonzero(self):
        self.assertEqual(
            klt_sim.client_version(runner=_runner(rc=1, out="klt: usage error\n")),
            klt_sim.CLIENT_VERSION_UNAVAILABLE,
        )


class TestNoConsolidatedWriterProbesKltVersionDirectly(unittest.TestCase):
    """Issue #1086: record writers read local `klt --version` through
    `harness.klt_sim.client_version()` rather than probing `klt` inline."""

    CONSOLIDATED = (
        "vcm-drive-budget/run_vcm_drive_budget.py",
        "full-conversion-transient/full_conversion_campaigns/input_sweep.py",
        "reference-drive-budget/run_reference_drive_budget.py",
        "input-drive-budget/run_input_drive_budget.py",
        "top-plate-cpar/run_top_plate_cpar.py",
        "sampling-cdac-handoff/run_handoff.py",
        "cdac-bit-trial-settling/run_bit_trial_settling.py",
        "digital-partition/run_digital_partition.py",
    )

    def test_every_consolidated_writer_delegates_to_klt_sim_client_version(self):
        for rel in self.CONSOLIDATED:
            text = (SIM_DIR / rel).read_text()
            with self.subTest(module=rel):
                self.assertIn(
                    "klt_sim.client_version(",
                    text,
                    f"{rel} must call klt_sim.client_version() (issue #1086)",
                )
                self.assertNotIn(
                    '"klt", "--version"',
                    text,
                    f"{rel} still probes klt --version directly (issue #1086)",
                )
                self.assertNotIn(
                    "def klt_client_version",
                    text,
                    f"{rel} still defines a private klt_client_version() helper",
                )


class TestNoConsolidatedWriterResolvesTheExecutingEnvironmentItself(unittest.TestCase):
    """Issue #1094: the seven batch drivers resolve the executing worker's
    PDK and simulator through `harness.klt_sim.executing_environment()`,
    never from a private copy.

    Keyed on the artifacts a private copy necessarily carries, each one a
    drift the seven copies had actually accumulated: the Environment block's
    two attribution labels, a private all-or-nothing gate, a private
    host-vs-worker comparison, the re-parsed and re-prefixed `"sky130A @ ..."`
    line, and the sentence that said the block names the SUBMITTING host
    while the block stamped the worker's values.
    """

    CONSOLIDATED = (
        "vcm-drive-budget/run_vcm_drive_budget.py",
        "full-conversion-transient/full_conversion_campaigns/input_sweep.py",
        "reference-drive-budget/run_reference_drive_budget.py",
        "input-drive-budget/run_input_drive_budget.py",
        "top-plate-cpar/run_top_plate_cpar.py",
        "sampling-cdac-handoff/run_handoff.py",
        "cdac-bit-trial-settling/run_bit_trial_settling.py",
    )

    PRIVATE_COPY_MARKERS = (
        '"PDK / ngspice above"',
        '"submitting host PDK / ngspice"',
        "exec_known =",
        "exec_matches_host =",
        'f"sky130A @ {',
        "resolved on the SUBMITTING host",
    )

    def test_every_consolidated_writer_delegates_to_klt_sim_executing_environment(self):
        for rel in self.CONSOLIDATED:
            text = (SIM_DIR / rel).read_text()
            with self.subTest(module=rel):
                self.assertIn(
                    "klt_sim.executing_environment(",
                    text,
                    f"{rel} must call klt_sim.executing_environment() (issue #1094)",
                )
                self.assertNotIn(
                    "def executing_environment",
                    text,
                    f"{rel} still defines its own executing_environment()",
                )

    def test_no_consolidated_writer_keeps_a_private_copy(self):
        for rel in self.CONSOLIDATED:
            text = (SIM_DIR / rel).read_text()
            for marker in self.PRIVATE_COPY_MARKERS:
                with self.subTest(module=rel, marker=marker):
                    self.assertNotIn(
                        marker, text,
                        f"{rel} carries '{marker}' -- render the block from "
                        "klt_sim.executing_environment() instead (issue #1094)")

    def test_the_markers_are_what_a_private_copy_actually_carries(self):
        """The guard keys on text, so assert each marker against a sketch of
        the copies it was written for -- a marker that matches none of them
        would make the two tests above pass vacuously."""
        private_copy = (
            'exec_known = bool(worker_pdk and worker_ng)\n'
            'exec_matches_host = exec_known and host.split("@")[-1] == worker.split()[-1]\n'
            'pdk = f"sky130A @ {worker_pdk.split()[-1]}" if exec_known else prov.pdk_line\n'
            '"PDK / ngspice above": "as run by the executing worker" if exec_known else "x",\n'
            '"submitting host PDK / ngspice": f"{prov.pdk_line} / {prov.ng_version}",\n'
            'names the PDK and ngspice resolved on the SUBMITTING host;\n'
        )
        for marker in self.PRIVATE_COPY_MARKERS:
            with self.subTest(marker=marker):
                self.assertIn(marker, private_copy)

    def test_no_campaign_module_outside_the_harness_renders_the_attribution_itself(self):
        """The list above cannot see a NEW campaign. Discovered by content:
        any campaign module that carries the block's attribution label or
        the re-prefixed PDK line is a private copy, whatever it calls it."""
        for p in sorted(SIM_DIR.glob("*/*.py")) + sorted(SIM_DIR.glob("*/*/*.py")):
            if p.parent.name in ("harness", "tests") or "harness/" in p.as_posix():
                continue
            text = p.read_text()
            for marker in ('"PDK / ngspice above"', '"submitting host PDK / ngspice"',
                           'f"sky130A @ {'):
                with self.subTest(module=f"{p.parent.name}/{p.name}", marker=marker):
                    self.assertNotIn(
                        marker, text,
                        f"{p.parent.name}/{p.name} renders the executing-worker "
                        "attribution itself -- use harness.klt_sim."
                        "executing_environment() (issue #1094)")


if __name__ == "__main__":
    unittest.main()

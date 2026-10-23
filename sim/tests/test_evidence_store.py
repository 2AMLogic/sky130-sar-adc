"""Fail-closed tests for sim/harness/evidence_store.py (issue #717).

No klt, broker or network beyond a loopback fake broker: `klt` is a stub
callable and the broker probe talks to a local http.server.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import evidence_store as es  # noqa: E402

REPO = "2AMLogic/sky130-sar-adc"


def _fake_klt(fail_on=None, tamper=False):
    """A `run` stub emulating `klt artifact put ... --manifest M`."""

    def run(cmd, **kw):
        if cmd[:3] == ["klt", "artifact", "put"] and "--help" in cmd:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        path, name, mpath = cmd[3], cmd[5], cmd[7]
        if fail_on and name.endswith(fail_on):
            return SimpleNamespace(returncode=1, stdout="", stderr=json.dumps(
                {"error": {"code": "broker_unreachable", "message": "down"}}))
        data = Path(path).read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        try:
            m = json.loads(Path(mpath).read_text())
        except OSError:
            m = {"schema_version": 1, "entries": []}
        m["entries"].append({
            "sha256": sha, "size": len(data) + 1 if tamper else len(data), "kind": "evidence",
            "producer": {"tool": "klt", "version": "x", "loom.repo": REPO, "commit": None},
            "uri": f"artifact:evidence/2AMLogic__sky130-sar-adc/{sha[:2]}/{sha}",
            "name": name})
        Path(mpath).write_text(json.dumps(m))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    return run


class _Broker(http.server.BaseHTTPRequestHandler):
    status = 200

    def do_POST(self):
        self.send_response(type(self).status)
        self.end_headers()
        self.wfile.write(b'{"error": "not_granted"}')

    def log_message(self, *a):
        pass


class TestPreflight(unittest.TestCase):
    def test_broker_unset(self):
        with self.assertRaisesRegex(es.StoreError, "unset"):
            es.preflight(Path("."), env={}, which=lambda _: "/x/klt")

    def test_klt_missing(self):
        with self.assertRaisesRegex(es.StoreError, "not on PATH"):
            es.preflight(Path("."), env={es.ENV_BROKER: "http://b"}, which=lambda _: None)

    def test_verb_missing(self):
        run = lambda *a, **k: SimpleNamespace(returncode=2, stdout="", stderr="")  # noqa: E731
        with self.assertRaisesRegex(es.StoreError, "no `artifact put` verb"):
            es.preflight(Path("."), env={es.ENV_BROKER: "http://b", es.ENV_REPO: REPO},
                         which=lambda _: "/x/klt", run=run)

    def test_broker_unreachable(self):
        srv = http.server.HTTPServer(("127.0.0.1", 0), _Broker)
        port = srv.server_address[1]
        srv.server_close()  # nothing listens on this port now
        with self.assertRaisesRegex(es.StoreError, "unreachable"):
            es.probe_broker(f"http://127.0.0.1:{port}", REPO, timeout=2)

    def _serve(self, status):
        _Broker.status = status
        srv = http.server.HTTPServer(("127.0.0.1", 0), _Broker)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_address[1]}"

    def test_broker_refusal(self):
        with self.assertRaisesRegex(es.StoreError, "refused.*403.*not_granted"):
            es.probe_broker(self._serve(403), REPO)

    def test_broker_ok(self):
        es.probe_broker(self._serve(404), REPO)

    def test_bad_broker_url(self):
        with self.assertRaisesRegex(es.StoreError, "plain http"):
            es.probe_broker("s3://bucket", REPO)


class TestStoreFiles(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        stage = self.root / "stage"
        stage.mkdir()
        (stage / "a.log").write_text("alpha\n")
        (stage / "b.log").write_text("beta\n")
        self.files = [(stage / "a.log", "sim/exp/corners/r1/a.log"),
                      (stage / "b.log", "sim/exp/corners/r1/b.log")]
        self.summary = self.root / "sim" / "exp" / "records" / "r1.md"

    def _store(self, run):
        put = lambda files, root: es.put_files(files, root, run=run)  # noqa: E731
        return es.store_files(self.files, repo_root=self.root, bench="exp", rid="r1",
                              summary_text="# Record r1", summary_path=self.summary, put=put)

    def _assert_nothing_written(self):
        self.assertFalse((self.root / "manifests").exists())
        self.assertFalse((self.root / "sim").exists())

    def test_success_writes_manifest_and_record_only(self):
        mpath = self._store(_fake_klt())
        m = json.loads(mpath.read_text())
        self.assertEqual(len(m["entries"]), 2)
        for e in m["entries"]:
            self.assertTrue(e["uri"].startswith("artifact:"))
        text = self.summary.read_text()
        self.assertIn("## Stored evidence", text)
        for e in m["entries"]:
            self.assertIn(e["sha256"], text)
        self.assertEqual(sorted(p.name for p in self.root.rglob("*.log")), ["a.log", "b.log"])
        self.assertFalse(list((self.root / "sim").rglob("*.log")))

    def test_put_failure_midway_writes_nothing(self):
        with self.assertRaisesRegex(es.StoreError, "broker_unreachable"):
            self._store(_fake_klt(fail_on="b.log"))
        self._assert_nothing_written()

    def test_manifest_mismatching_local_bytes_writes_nothing(self):
        with self.assertRaisesRegex(es.StoreError, "does not match"):
            self._store(_fake_klt(tamper=True))
        self._assert_nothing_written()

    def test_klt_oserror_writes_nothing(self):
        def run(*a, **k):
            raise FileNotFoundError("klt")
        with self.assertRaises(es.StoreError):
            self._store(run)
        self._assert_nothing_written()

    def test_existing_manifest_is_never_replaced(self):
        self._store(_fake_klt())
        with self.assertRaisesRegex(es.StoreError, "already exists"):
            self._store(_fake_klt())

    def test_empty_files_listed_not_stored(self):
        (self.root / "stage" / "e.log").write_text("")
        self.files.append((self.root / "stage" / "e.log", "sim/exp/corners/r1/e.log"))
        mpath = self._store(_fake_klt())
        self.assertEqual(len(json.loads(mpath.read_text())["entries"]), 2)
        self.assertIn("empty, not stored", self.summary.read_text())

    def test_invalid_bench_rejected(self):
        with self.assertRaises(ValueError):
            es.manifest_path(self.root, "../x", "r1")


class TestCliFailClosed(unittest.TestCase):
    def test_store_without_broker_exits_nonzero_before_running(self):
        import contextlib
        import io
        import os
        from unittest import mock

        from harness import cli

        with mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch.object(cli, "runner") as runner, \
                mock.patch.object(cli, "testbench"), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            os.environ.pop(es.ENV_BROKER, None)
            rc = cli.main(["exp", "--record", "--store"])
        self.assertEqual(rc, 1)
        self.assertIn("unset", err.getvalue())
        runner.run.assert_not_called()

    def test_store_requires_record(self):
        import contextlib
        import io

        from harness import cli

        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["exp", "--store"]), 2)


if __name__ == "__main__":
    unittest.main()


class TestRunnerStoreMode(unittest.TestCase):
    """runner.write_evidence(store=True): bytes go to the store, not sim/."""

    def _go(self, tmp, run):
        from unittest import mock

        from harness import evidence, runner

        root = Path(tmp)
        exp = root / "sim" / "exp"
        exp.mkdir(parents=True)
        frag = exp / "dut.spice"
        frag.write_text(".subckt d a b\n.ends\n")
        manifest = SimpleNamespace(experiment_dir=exp, netlist_fragment=frag,
                                   claim="c", measure={"m": {}})
        pt = SimpleNamespace(process_corner="tt", temp_c=27.0, supply_v=1.8,
                             corner_id="tt_27c_1.80v", measures={"m": 1.0},
                             log_text="log\n", ok=True, check_failures=[])
        result = SimpleNamespace(manifest=manifest, points=[pt], record_id="rid-1",
                                 netlist_sha256="0" * 64, overall_ok=True)
        info = SimpleNamespace(variant="v")
        real_put = es.put_files
        put = lambda files, r: real_put(files, r, run=run)  # noqa: E731
        with mock.patch.object(runner, "SIM_DIR", root / "sim"), \
                mock.patch.object(evidence, "REPO_ROOT", root), \
                mock.patch.object(runner.pdk, "resolve", return_value=info), \
                mock.patch.object(runner.pdk, "resolved_commit", return_value="c0"), \
                mock.patch.object(runner.toolchain, "_ngspice_version", return_value="45"), \
                mock.patch.object(evidence, "git_info", return_value=evidence.GitInfo("abc1234", "b", False)), \
                mock.patch.object(es, "put_files", put):
            return root, runner.write_evidence(result, {}, store=True)

    def test_store_mode_commits_only_manifest_and_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, rec = self._go(tmp, _fake_klt())
            self.assertTrue((root / "manifests/artifacts/exp-rid-1.manifest.json").is_file())
            self.assertIn("## Stored evidence", rec.read_text())
            self.assertIn("DUT netlist sha256", rec.read_text())
            self.assertFalse((root / "sim/exp/corners").exists())
            self.assertFalse((root / "sim/exp/netlist-snapshots").exists())
            self.assertTrue((root / "sim/.work/exp/rid-1/corners/rid-1/tt_27c_1.80v.log").is_file())

    def test_store_failure_writes_no_record_or_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(es.StoreError):
                self._go(tmp, _fake_klt(fail_on=".log"))
            root = Path(tmp)
            self.assertFalse((root / "manifests").exists())
            self.assertFalse((root / "sim/exp/records").exists())
            self.assertTrue((root / "sim/.work").exists())

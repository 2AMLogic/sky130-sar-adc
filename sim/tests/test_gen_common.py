"""Behavioral tests for `layout/bin/_gen_common.py` (issue #612).

Pure stdlib; `subprocess.run` is mocked at the helper module boundary, so no
`klt` is ever invoked.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "layout" / "bin"))

import _gen_common as gen_common  # noqa: E402

RUN = "_gen_common.subprocess.run"


class TestRunGen(unittest.TestCase):
    def test_argv_flags_and_output_forwarding(self):
        params = {"w": 1.5, "nested": {"a": [1, 2]}, "name": "x y"}
        with mock.patch(RUN, return_value=mock.Mock(stdout="OUT", stderr="ERR")) as run:
            result = gen_common.run_gen(
                "/bin/klt", "sky130A", "mos_array", params, "cell1", Path("o/c.gds")
            )
        self.assertEqual(result, ("OUT", "ERR"))
        run.assert_called_once()
        cmd = run.call_args.args[0]
        self.assertEqual(
            cmd[:4] + cmd[5:],
            ["/bin/klt", "gen", "mos_array", "--params", "--pdk", "sky130A",
             "--cell-name", "cell1", "-o", "o/c.gds", "--format", "json"],
        )  # fmt: skip
        self.assertEqual(json.loads(cmd[4]), params)
        self.assertEqual(
            run.call_args.kwargs,
            {"capture_output": True, "text": True, "check": False},
        )

    def test_params_flag_precedes_json(self):
        with mock.patch(RUN, return_value=mock.Mock(stdout="", stderr="")) as run:
            gen_common.run_gen("klt", "p", "g", {"a": 1}, "c", Path("c.gds"))
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[cmd.index("--params") + 1], json.dumps({"a": 1}))

    def test_nonzero_returncode_is_not_an_error(self):
        # Pins the existing contract: check=False, returncode is ignored.
        proc = mock.Mock(stdout='{"error": "boom"}', stderr="bad", returncode=3)
        with mock.patch(RUN, return_value=proc):
            result = gen_common.run_gen("klt", "p", "g", {}, "c", Path("c.gds"))
        self.assertEqual(result, ('{"error": "boom"}', "bad"))


class TestWriteAndCheck(unittest.TestCase):
    def _call(self, stdout, stderr="", block_id="blk"):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                ret = gen_common.write_and_check(block_id, stdout, stderr, path)
            written = path.read_text()
        return ret, written, err.getvalue()

    def test_success_returns_parsed_report(self):
        out = json.dumps({"cells": 2})
        ret, written, err = self._call(out)
        self.assertEqual(ret, {"cells": 2})
        self.assertEqual(written, out)
        self.assertEqual(err, "")

    def test_falsy_error_values_accepted(self):
        for val in (None, "", 0, False, []):
            with self.subTest(error=val):
                out = json.dumps({"error": val, "ok": 1})
                ret, written, err = self._call(out)
                self.assertEqual(ret, {"error": val, "ok": 1})
                self.assertEqual(written, out)
                self.assertEqual(err, "")

    def test_absent_error_field_accepted(self):
        ret, _, err = self._call("{}")
        self.assertEqual(ret, {})
        self.assertEqual(err, "")

    def test_truthy_error_rejected_but_stdout_still_written(self):
        out = json.dumps({"error": "bad params"})
        ret, written, err = self._call(out, block_id="blkA")
        self.assertIsNone(ret)
        self.assertEqual(written, out)
        self.assertIn("gen_blocks.py: blkA: generator error: bad params", err)

    def test_malformed_json_rejected_with_diagnostics(self):
        ret, written, err = self._call("garbage", stderr="tool died", block_id="blkB")
        self.assertIsNone(ret)
        self.assertEqual(written, "garbage")
        self.assertIn("gen_blocks.py: blkB: non-JSON output:", err)
        self.assertIn("garbage", err)
        self.assertIn("tool died", err)

    def test_write_failure_propagates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing_dir" / "r.json"
            with self.assertRaises(FileNotFoundError):
                gen_common.write_and_check("b", "{}", "", path)


class TestAddKltPdkArgs(unittest.TestCase):
    def test_returns_same_parser(self):
        parser = argparse.ArgumentParser()
        self.assertIs(gen_common.add_klt_pdk_args(parser), parser)

    def test_defaults_and_path_conversion(self):
        ns = gen_common.add_klt_pdk_args(argparse.ArgumentParser()).parse_args(["outd"])
        self.assertEqual(ns.out_dir, Path("outd"))
        self.assertIsInstance(ns.out_dir, Path)
        self.assertEqual(ns.klt, "klt")
        self.assertEqual(ns.pdk, "sky130A")

    def test_explicit_values(self):
        ns = gen_common.add_klt_pdk_args(argparse.ArgumentParser()).parse_args(
            ["outd", "--klt", "/x/klt", "--pdk", "sky130B"]
        )
        self.assertEqual(ns.klt, "/x/klt")
        self.assertEqual(ns.pdk, "sky130B")

    def test_out_dir_required(self):
        parser = gen_common.add_klt_pdk_args(argparse.ArgumentParser())
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit) as cm:
            parser.parse_args([])
        self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

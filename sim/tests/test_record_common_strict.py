"""Behavioral tests for `layout/bin/_record_common_strict.py` (issue #612).

Pure stdlib; every subprocess call is mocked at the helper module boundary, so
no git/klt/PDK is ever invoked.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "layout" / "bin"))

import _record_common_strict as rcs  # noqa: E402

RUN = "_record_common_strict.subprocess.run"


def _completed(stdout: str) -> mock.Mock:
    return mock.Mock(stdout=stdout)


class TestLoadJsonStrict(unittest.TestCase):
    def test_valid_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.json"
            p.write_text(json.dumps({"k": [1, 2]}), encoding="utf-8")
            self.assertEqual(rcs.load_json_strict(p), {"k": [1, 2]})

    def test_missing_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                rcs.load_json_strict(Path(tmp) / "nope.json")

    def test_malformed_json_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.json"
            p.write_text("{not json", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                rcs.load_json_strict(p)


class TestGitField(unittest.TestCase):
    def test_argv_flags_and_strip(self):
        with mock.patch(RUN, return_value=_completed("abc123\n")) as run:
            out = rcs.git_field(Path("/repo"), "rev-parse", "HEAD")
        self.assertEqual(out, "abc123")
        run.assert_called_once_with(
            ["git", "-C", "/repo", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_failure_propagates(self):
        err = subprocess.CalledProcessError(128, ["git"])
        with mock.patch(RUN, side_effect=err):
            with self.assertRaises(subprocess.CalledProcessError):
                rcs.git_field(Path("/repo"), "status")

    def test_missing_executable_propagates(self):
        with mock.patch(RUN, side_effect=FileNotFoundError("git")):
            with self.assertRaises(FileNotFoundError):
                rcs.git_field(Path("/repo"), "status")


class TestToolVersionStrict(unittest.TestCase):
    def test_argv_flags_and_strip(self):
        with mock.patch(RUN, return_value=_completed("  klt 1.2.3\n")) as run:
            out = rcs.tool_version_strict("klt", "--version")
        self.assertEqual(out, "klt 1.2.3")
        run.assert_called_once_with(
            ["klt", "--version"], check=True, capture_output=True, text=True
        )

    def test_argv_is_a_list(self):
        with mock.patch(RUN, return_value=_completed("x")) as run:
            rcs.tool_version_strict("a", "b")
        self.assertIsInstance(run.call_args.args[0], list)

    def test_failure_propagates(self):
        err = subprocess.CalledProcessError(1, ["klt", "--version"])
        with mock.patch(RUN, side_effect=err):
            with self.assertRaises(subprocess.CalledProcessError):
                rcs.tool_version_strict("klt", "--version")

    def test_missing_executable_propagates(self):
        with mock.patch(RUN, side_effect=FileNotFoundError("klt")):
            with self.assertRaises(FileNotFoundError):
                rcs.tool_version_strict("klt", "--version")


class TestResolvePdkInfoStrict(unittest.TestCase):
    def test_argv_and_envelope(self):
        env = {"variant": "sky130A", "version": "abc", "resolved_via": "env"}
        with mock.patch(RUN, return_value=_completed(json.dumps(env))) as run:
            out = rcs.resolve_pdk_info_strict("/bin/klt", "sky130A")
        self.assertEqual(out, env)
        run.assert_called_once_with(
            ["/bin/klt", "pdk", "find", "--pdk", "sky130A", "--format", "json"],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_subprocess_failure_propagates(self):
        err = subprocess.CalledProcessError(2, ["klt"])
        with mock.patch(RUN, side_effect=err):
            with self.assertRaises(subprocess.CalledProcessError):
                rcs.resolve_pdk_info_strict("klt", "sky130A")

    def test_malformed_json_raises(self):
        with mock.patch(RUN, return_value=_completed("not json")):
            with self.assertRaises(json.JSONDecodeError):
                rcs.resolve_pdk_info_strict("klt", "sky130A")


class TestBuildArgparserStrict(unittest.TestCase):
    ARGV = [
        "--out-dir", "out",
        "--record-id", "rec-1",
        "--repo-root", "/repo",
        "--klt", "klt",
        "--pdk-variant", "sky130A",
    ]  # fmt: skip

    def test_parses_all_five_flags(self):
        ns = rcs.build_argparser_strict().parse_args(self.ARGV)
        self.assertEqual(ns.out_dir, Path("out"))
        self.assertIsInstance(ns.out_dir, Path)
        self.assertEqual(ns.record_id, "rec-1")
        self.assertEqual(ns.repo_root, Path("/repo"))
        self.assertIsInstance(ns.repo_root, Path)
        self.assertEqual(ns.klt, "klt")
        self.assertIsInstance(ns.klt, str)
        self.assertEqual(ns.pdk_variant, "sky130A")

    def test_each_flag_is_required(self):
        flags = self.ARGV[0::2]
        for i, flag in enumerate(flags):
            argv = self.ARGV[: 2 * i] + self.ARGV[2 * i + 2 :]
            with self.subTest(missing=flag):
                with mock.patch("sys.stderr"), self.assertRaises(SystemExit) as cm:
                    rcs.build_argparser_strict().parse_args(argv)
                self.assertEqual(cm.exception.code, 2)


class TestRenderProvenanceHeader(unittest.TestCase):
    DRC = {"provenance": {"klayout_version": "0.29.1"}}
    PDK = {"variant": "sky130A", "version": "deadbeef", "resolved_via": "env:PDK_ROOT"}

    def _render(self, dirty):
        return rcs.render_provenance_header(
            "klt 9.9", self.DRC, self.PDK, "cafe123", "feature/x", dirty
        )

    def test_supplied_values_clean(self):
        lines = self._render(False)
        self.assertEqual(lines[0], "## Provenance")
        self.assertEqual(lines[1], "")
        self.assertIn("- `klt` version: klt 9.9", lines)
        self.assertIn("- KLayout engine: 0.29.1", lines)
        self.assertIn("- PDK: sky130A (deadbeef)", lines)
        self.assertIn("- PDK root: resolved via `env:PDK_ROOT`", lines)
        self.assertIn("- repo commit: `cafe123` on `feature/x`", lines)
        self.assertFalse(any("dirty" in line for line in lines))

    def test_dirty_marker(self):
        lines = self._render(True)
        commit = [ln for ln in lines if ln.startswith("- repo commit:")]
        self.assertEqual(len(commit), 1)
        self.assertTrue(commit[0].endswith(" (dirty working tree)"))
        self.assertIn("`cafe123`", commit[0])

    def test_missing_optional_fields_do_not_raise(self):
        lines = rcs.render_provenance_header("v", {}, {}, "s", "b", False)
        self.assertIn("- KLayout engine: None", lines)


class TestRenderNetCorrespondence(unittest.TestCase):
    HEADER = ["## Net correspondence (layout <-> reference)", ""]

    def test_empty(self):
        self.assertEqual(rcs.render_net_correspondence({}), self.HEADER + [""])
        self.assertEqual(
            rcs.render_net_correspondence({"net_correspondence": []}),
            self.HEADER + [""],
        )

    def test_pin_and_internal_in_order(self):
        lvs = {
            "net_correspondence": [
                {"layout": "VIN", "reference": "vin", "pin": True},
                {"layout": "n1", "reference": "net_1", "pin": False},
                {"layout": "n2", "reference": "net_2"},
            ]
        }
        lines = rcs.render_net_correspondence(lvs)
        self.assertEqual(lines[:2], self.HEADER)
        self.assertEqual(
            lines[2:5],
            [
                "- `VIN` <-> `vin` (pin)",
                "- `n1` <-> `net_1` (internal)",
                "- `n2` <-> `net_2` (internal)",
            ],
        )
        self.assertEqual(lines[-1], "")
        self.assertEqual(len(lines), 6)


class TestRenderLvsFindings(unittest.TestCase):
    def test_no_findings_non_match(self):
        lines = rcs.render_lvs_findings({"status": "mismatch"})
        self.assertEqual(lines, ["## Reported LVS findings", "", "- none", ""])

    def test_populated_finding_and_match_status(self):
        lvs = {
            "status": "match",
            "error_count": 3,
            "mismatches": [
                {"severity": "warning", "category": "net", "description": "floating"}
            ],
        }
        lines = rcs.render_lvs_findings(lvs)
        self.assertIn("- [warning] net: floating", lines)
        self.assertNotIn("- none", lines)
        closing = [ln for ln in lines if "error_count" in ln]
        self.assertEqual(len(closing), 1)
        self.assertIn("`error_count = 3`", closing[0])
        self.assertIn("overall verdict for this run is `match`", closing[0])
        self.assertEqual(lines[-1], "")

    def test_non_match_has_no_closing_sentence(self):
        lvs = {
            "status": "mismatch",
            "error_count": 5,
            "mismatches": [{"severity": "error", "category": "c", "description": "d"}],
        }
        lines = rcs.render_lvs_findings(lvs)
        self.assertIn("- [error] c: d", lines)
        self.assertFalse(any("error_count" in ln for ln in lines))

    def test_custom_title(self):
        lines = rcs.render_lvs_findings({}, title="Reported LVS findings (good reference)")
        self.assertEqual(lines[0], "## Reported LVS findings (good reference)")


if __name__ == "__main__":
    unittest.main()

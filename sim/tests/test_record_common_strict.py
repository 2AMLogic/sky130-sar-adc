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


class TestGitIdentity(unittest.TestCase):
    def test_three_probes_in_provenance_order(self):
        with mock.patch(
            RUN,
            side_effect=[_completed("cafe123\n"), _completed("feature/x\n"), _completed("")],
        ) as run:
            self.assertEqual(
                rcs.git_identity(Path("/repo")), ("cafe123", "feature/x", False)
            )
        self.assertEqual(
            [call.args[0][3:] for call in run.call_args_list],
            [["rev-parse", "HEAD"], ["rev-parse", "--abbrev-ref", "HEAD"], ["status", "--porcelain"]],
        )
        for call in run.call_args_list:
            self.assertEqual(call.args[0][:3], ["git", "-C", "/repo"])

    def test_any_porcelain_output_is_dirty(self):
        for porcelain in (" M a.py", "?? untracked.txt", " M a.py\n?? b.txt\n"):
            with self.subTest(porcelain=porcelain):
                with mock.patch(
                    RUN,
                    side_effect=[
                        _completed("s\n"),
                        _completed("b\n"),
                        _completed(porcelain),
                    ],
                ):
                    self.assertIs(rcs.git_identity(Path("/repo"))[2], True)

    def test_failure_propagates(self):
        err = subprocess.CalledProcessError(128, ["git"])
        with mock.patch(RUN, side_effect=err):
            with self.assertRaises(subprocess.CalledProcessError):
                rcs.git_identity(Path("/repo"))


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


class TestRenderVerdictChecklist(unittest.TestCase):
    def test_all_ok_is_pass(self):
        lines = rcs.render_verdict_checklist([("first", True), ("second", True)])
        self.assertEqual(
            lines,
            [
                "## Overall verdict: PASS",
                "",
                "- [x] first",
                "- [x] second",
                "",
            ],
        )

    def test_any_failure_is_fail_and_marks_only_that_box(self):
        lines = rcs.render_verdict_checklist(
            [("ok one", True), ("broken", False), ("ok two", True)]
        )
        self.assertEqual(lines[0], "## Overall verdict: FAIL")
        self.assertEqual(
            lines[2:5], ["- [x] ok one", "- [ ] broken", "- [x] ok two"]
        )

    def test_empty_checks_is_vacuous_pass(self):
        # `all([])` is True, matching the callers' own exit-status expression.
        self.assertEqual(
            rcs.render_verdict_checklist([]), ["## Overall verdict: PASS", "", ""]
        )

    def test_check_order_preserved(self):
        checks = [(f"check {i}", True) for i in range(5)]
        lines = rcs.render_verdict_checklist(checks)
        self.assertEqual(
            lines[2:-1], [f"- [x] check {i}" for i in range(5)]
        )


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


class TestRenderBlocksTable(unittest.TestCase):
    HEADER = [
        "## Blocks (`klt gen`)",
        "",
        "| Block | Cell | Devices | bbox (um) | own DRC |",
        "| --- | --- | --- | --- | --- |",
    ]

    def _write(self, tmp, block, payload):
        (Path(tmp) / f"{block}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def test_row_per_block_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "tail", {
                "cell_name": "gen_tail", "device_count": 4,
                "bbox_um": {"x0": 0.0, "y0": 0.1, "x1": 2.5, "y1": 3.0},
            })
            self._write(tmp, "inpair", {
                "cell_name": "gen_inpair", "device_count": 2,
                "bbox_um": {"x0": 0, "y0": 0, "x1": 1, "y1": 1},
            })
            lines = rcs.render_blocks_table(
                Path(tmp),
                ("tail", "inpair"),
                {"tail": {"status": "clean"}, "inpair": {"status": "violations"}},
            )
        self.assertEqual(lines[:4], self.HEADER)
        self.assertEqual(
            lines[4:6],
            [
                "| `tail` | `gen_tail` | 4 | 0.0,0.1 .. 2.5,3.0 | clean |",
                "| `inpair` | `gen_inpair` | 2 | 0,0 .. 1,1 | violations |",
            ],
        )
        self.assertEqual(lines[-1], "")
        self.assertEqual(len(lines), 7)

    def test_block_absent_from_block_drc_renders_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "rst", {"cell_name": "c", "device_count": 1,
                                     "bbox_um": {}})
            lines = rcs.render_blocks_table(Path(tmp), ("rst",), {})
        self.assertEqual(
            lines[4], "| `rst` | `c` | 1 | None,None .. None,None | None |"
        )

    def test_empty_blocks_still_renders_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = rcs.render_blocks_table(Path(tmp), (), {})
        self.assertEqual(lines, self.HEADER + [""])

    def test_missing_envelope_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                rcs.render_blocks_table(Path(tmp), ("absent",), {})


class TestRenderLvsCountsRow(unittest.TestCase):
    LVS = {
        "status": "match",
        "counts": {
            "devices": {"matched": 30, "reference": 30},
            "nets": {"matched": 12, "reference": 12},
            "pins": {"matched": 6, "reference": 6},
        },
    }

    def test_single_row_with_label_and_counts(self):
        lines = rcs.render_lvs_counts_row(self.LVS, "good reference")
        self.assertEqual(
            lines,
            [
                "| LVS (good reference) | match | devices 30/30 matched, "
                "nets 12/12 matched, pins 6/6 matched |"
            ],
        )

    def test_label_is_the_only_difference(self):
        good = rcs.render_lvs_counts_row(self.LVS, "good reference")[0]
        schematic = rcs.render_lvs_counts_row(
            self.LVS, "schematic-derived reference"
        )[0]
        self.assertNotEqual(good, schematic)
        self.assertEqual(
            good.replace("(good reference)", "(X)"),
            schematic.replace("(schematic-derived reference)", "(X)"),
        )

    def test_unmatched_counts_are_reported_not_hidden(self):
        lvs = {
            "status": "mismatch",
            "counts": {
                "devices": {"matched": 29, "reference": 30},
                "nets": {"matched": 12, "reference": 12},
                "pins": {"matched": 5, "reference": 6},
            },
        }
        row = rcs.render_lvs_counts_row(lvs, "good reference")[0]
        self.assertIn("| mismatch |", row)
        self.assertIn("devices 29/30 matched", row)
        self.assertIn("pins 5/6 matched", row)

    def test_missing_counts_block_renders_none(self):
        row = rcs.render_lvs_counts_row({}, "good reference")[0]
        self.assertEqual(
            row,
            "| LVS (good reference) | None | devices None/None matched, "
            "nets None/None matched, pins None/None matched |",
        )


class TestRenderDrcCoverage(unittest.TestCase):
    COVERAGE = {
        "deck_scope": ["width", "spacing"],
        "layers_checked": ["met1", "met2"],
        "layers_in_stream_without_rules": ["capm"],
        "rules_skipped": 7,
    }

    def test_heading_prose_and_four_bullets(self):
        lines = rcs.render_drc_coverage(self.COVERAGE)
        self.assertEqual(
            lines[0], "## DRC coverage (what the deck did and did not check)"
        )
        self.assertEqual(lines[1], "")
        self.assertIn("`klt drc`'s own `coverage` block", lines[2])
        self.assertEqual(lines[3], "")
        self.assertEqual(
            lines[4:8],
            [
                "- rule families in scope: ['width', 'spacing']",
                "- layers checked: ['met1', 'met2']",
                "- layers present in the stream with **no** rule: ['capm']",
                "- rules skipped (layer absent from the stream): 7",
            ],
        )
        self.assertEqual(lines[-1], "")
        self.assertEqual(len(lines), 9)

    def test_empty_coverage_renders_none_rather_than_omitting_bullets(self):
        lines = rcs.render_drc_coverage({})
        bullets = [ln for ln in lines if ln.startswith("- ")]
        self.assertEqual(len(bullets), 4)
        self.assertTrue(all(ln.endswith("None") for ln in bullets))


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


class TestPrecheckEnvelopeHelpers(unittest.TestCase):
    ENVELOPE = {
        "checks": [
            {"name": "offgrid", "status": "fail", "violations": [
                {"cell": "a", "layer": "capm"},
                {"cell": "a", "layer": "capm"},
                {"cell": "b", "layer": "met1"},
            ]},
            {"name": "antenna", "status": "pass", "violations": []},
            {"name": "floating", "status": "fail", "violations": []},
        ]
    }

    def test_failing_checks_names_sorted(self):
        self.assertEqual(rcs.failing_checks(self.ENVELOPE), ["floating", "offgrid"])

    def test_failing_checks_all_pass_and_empty(self):
        self.assertEqual(rcs.failing_checks({"checks": [{"name": "x", "status": "pass"}]}), [])
        self.assertEqual(rcs.failing_checks({}), [])

    def test_offgrid_census(self):
        self.assertEqual(
            rcs.offgrid_census(self.ENVELOPE), {("a", "capm"): 2, ("b", "met1"): 1}
        )
        self.assertEqual(rcs.offgrid_census({}), {})


if __name__ == "__main__":
    unittest.main()

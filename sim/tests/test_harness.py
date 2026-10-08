"""Unit tests for sim/harness/*.py -- pure logic only, no ngspice/PDK
required (mirrors gf180-sar-adc's sim/tests/test_harness.py convention of a
PDK-free unit-test stage ahead of the end-to-end simulation stages; see
sim/selftest.sh stage 1/4)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import corners, evidence, measure, runner  # noqa: E402
from harness import mc_runner, pdk, testbench, toolchain  # noqa: E402


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

    def test_anchored_default_rejects_trailing_trig_targ_context(self):
        # ngspice's TRIG/TARG crossing `.meas` prints extra " targ=...
        # trig=..." context on the same line -- the default anchored match
        # must reject it (issue #229).
        log = "t_settle_50 = 1.234500e-09 targ= 1.2345e-09 trig=0"
        parsed = measure.parse(log, ["t_settle_50"])
        self.assertNotIn("t_settle_50", parsed)

    def test_unanchored_parses_trig_targ_trailing_context(self):
        log = "t_settle_50 = 1.234500e-09 targ= 1.2345e-09 trig=0"
        parsed = measure.parse(log, ["t_settle_50"], anchored=False)
        self.assertAlmostEqual(parsed["t_settle_50"], 1.2345e-09)

    def test_unanchored_still_matches_plain_lines(self):
        parsed = measure.parse("vgs_nfet = 1.0", ["vgs_nfet"], anchored=False)
        self.assertAlmostEqual(parsed["vgs_nfet"], 1.0)

    # -- issue #569: non-finite values are rejected at the parser boundary --
    def test_exponent_overflow_is_rejected_in_plain_lines(self):
        for anchored in (True, False):
            with self.subTest(anchored=anchored):
                log = "pos = 1e999\nneg = -1e999\nok = 2.5e-03\n"
                names = ["pos", "neg", "ok"]
                parsed = measure.parse(log, names, anchored=anchored)
                self.assertNotIn("pos", parsed)
                self.assertNotIn("neg", parsed)
                self.assertAlmostEqual(parsed["ok"], 2.5e-03)
                self.assertEqual(measure.missing(parsed, names), ["pos", "neg"])

    def test_exponent_overflow_is_rejected_in_trig_targ_lines(self):
        log = (
            "t_pos = 1e999 targ= 1.2345e-09 trig=0\n"
            "t_neg = -1e999 targ= 1.2345e-09 trig=0\n"
            "t_ok = 1.234500e-09 targ= 1.2345e-09 trig=0\n"
        )
        names = ["t_pos", "t_neg", "t_ok"]
        parsed = measure.parse(log, names, anchored=False)
        self.assertEqual(measure.missing(parsed, names), ["t_pos", "t_neg"])
        self.assertAlmostEqual(parsed["t_ok"], 1.2345e-09)

    def test_finite_exponent_tokens_keep_their_values(self):
        log = "a = 1e300\nb = -1e-300\nc = 1.8E+00\nd = -3.0e-6\n"
        for anchored in (True, False):
            with self.subTest(anchored=anchored):
                parsed = measure.parse(log, ["a", "b", "c", "d"], anchored=anchored)
                self.assertEqual(parsed["a"], 1e300)
                self.assertEqual(parsed["b"], -1e-300)
                self.assertEqual(parsed["c"], 1.8)
                self.assertEqual(parsed["d"], -3.0e-6)

    def test_nan_and_inf_tokens_never_parse(self):
        log = "a = nan\nb = inf\nc = -inf\n"
        for anchored in (True, False):
            with self.subTest(anchored=anchored):
                parsed = measure.parse(log, ["a", "b", "c"], anchored=anchored)
                self.assertEqual(parsed, {})

    def test_non_finite_first_occurrence_falls_through_to_a_later_finite_one(self):
        # first-*successful*-value rule: a rejected value does not claim the name
        for anchored in (True, False):
            with self.subTest(anchored=anchored):
                parsed = measure.parse("x = 1e999\nx = 2.0\nx = 3.0\n", ["x"], anchored=anchored)
                self.assertEqual(parsed["x"], 2.0)

    def test_finite_first_occurrence_still_wins_over_a_later_overflow(self):
        parsed = measure.parse("x = 1.0\nx = 1e999\n", ["x"])
        self.assertEqual(parsed["x"], 1.0)

    def test_repeated_overflow_only_stays_missing(self):
        parsed = measure.parse("x = 1e999\nx = -1e999\n", ["x"], anchored=False)
        self.assertEqual(measure.missing(parsed, ["x"]), ["x"])


class TestCorners(unittest.TestCase):
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

    def test_corner_matrix_summary_line_format(self):
        # Exact string shared by every experiment driver's "Corner matrix
        # run" evidence-record bullet (issue #127) -- must stay
        # byte-identical to the inline format it replaced.
        line = corners.corner_matrix_summary_line(
            ["ff", "ss", "tt"], [-40.0, 27.0, 125.0], [1.62, 1.8, 1.98], 9
        )
        self.assertEqual(
            line,
            "- **Corner matrix run**: process=['ff', 'ss', 'tt'], "
            "temperature_c=[-40.0, 27.0, 125.0], supply_v=[1.62, 1.8, 1.98] "
            "(9 points, one-at-a-time per sim/README.md)",
        )

    def test_oat_grid_baseline_only(self):
        # All axes collapse to a single (baseline-only) value -> just the
        # baseline point, no duplicates.
        grid = corners.oat_grid("tt", 27, 1.8, ["tt"], [27], [1.8])
        self.assertEqual(grid, [("tt", 27, 1.8)])

    def test_oat_grid_single_axis_sweep(self):
        # Sweeping only the process axis: baseline point plus the other
        # process corners, each with temp/supply held at baseline.
        grid = corners.oat_grid("tt", 27, 1.8, ["tt", "ss", "ff"], [27], [1.8])
        self.assertEqual(
            grid,
            [
                ("tt", 27, 1.8),
                ("ss", 27, 1.8),
                ("ff", 27, 1.8),
            ],
        )

    def test_oat_grid_dedup_when_axis_value_equals_baseline(self):
        # The baseline process corner ("tt") also appears in the swept
        # process-corner list -- it must not be added twice.
        grid = corners.oat_grid("tt", 27, 1.8, ["tt", "ss"], [27], [1.8])
        self.assertEqual(grid, [("tt", 27, 1.8), ("ss", 27, 1.8)])
        self.assertEqual(len(grid), len(set(grid)))

    def test_oat_grid_full_three_axis_shape(self):
        # Full three-axis OAT star: 1 baseline + (|process|-1) +
        # (|temp|-1) + (|supply|-1) points, matching the star-not-factorial
        # shape the docstring describes.
        process_corners = ["tt", "ss", "ff", "sf", "fs"]
        temps_c = [-40, 27, 125]
        supply_v = [1.62, 1.8, 1.98]
        grid = corners.oat_grid("tt", 27, 1.8, process_corners, temps_c, supply_v)
        self.assertEqual(len(grid), 1 + 4 + 2 + 2)
        self.assertEqual(len(grid), len(set(grid)))
        self.assertEqual(grid[0], ("tt", 27, 1.8))

    def test_ratified_oat_grid_matches_manual_supply_points_plus_oat_grid_chain(self):
        # ratified_oat_grid() is the "tt"/27C-baseline supply_points() +
        # oat_grid() chain every --corners driver hand-repeated (issue #211)
        # -- must return byte-identical grids to that manual two-call chain.
        process_corners = ["tt", "ss", "ff", "sf", "fs"]
        temps_c = [-40, 27, 125]
        nominal_v = 1.8
        tolerance = 0.10

        supply_pts = corners.supply_points(nominal_v, tolerance)
        expected = corners.oat_grid(
            "tt", 27.0, nominal_v, process_corners, temps_c, supply_pts
        )
        actual = corners.ratified_oat_grid(nominal_v, tolerance, process_corners, temps_c)
        self.assertEqual(actual, expected)

    def test_sweep_matches_ratified_grid_and_ids(self):
        pcs, temps = ["tt", "ss", "ff"], [-40, 27, 125]
        got = list(corners.sweep(1.8, 0.10, pcs, temps, quiet=True))
        grid = corners.ratified_oat_grid(1.8, 0.10, pcs, temps)
        self.assertEqual([g[:3] for g in got], grid)
        self.assertEqual(
            [g[3] for g in got], [corners.corner_id(*p) for p in grid]
        )
        self.assertEqual(got[0][3], "tt_27c_1.80v")

    def test_sweep_nondefault_nominal_and_collapsed_supply(self):
        got = list(corners.sweep(1.2, 0.0, ["tt", "ss"], [27], quiet=True))
        self.assertEqual(
            [g[:3] for g in got], [("tt", 27.0, 1.2), ("ss", 27.0, 1.2)]
        )

    def test_sweep_progress_and_quiet_modes(self):
        import contextlib
        import io

        def run(**kw):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ids = [g[3] for g in corners.sweep(1.8, 0.10, ["tt"], [27], **kw)]
            return ids, buf.getvalue()

        ids, out = run()
        self.assertEqual(out, "".join(f"{c}:\n" for c in ids))
        self.assertEqual(run(quiet=True)[1], "")
        self.assertEqual(run(announce=False)[1], "")


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


class TestWriteLatestPointer(unittest.TestCase):
    """evidence.write_latest_pointer() -- the records/LATEST pointer write the
    `sim/*/run_*.py` drivers each hand-rolled as the same two lines before
    issue #482 folded it into the harness next to close_record()."""

    def test_writes_record_id_dot_md_with_a_trailing_newline(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment_dir = Path(tmp)
            (experiment_dir / "records").mkdir()
            path = evidence.write_latest_pointer(experiment_dir, "20260927-010203-abc1234")
            self.assertEqual(path.read_text(), "20260927-010203-abc1234.md\n")

    def test_returns_the_pointer_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment_dir = Path(tmp)
            (experiment_dir / "records").mkdir()
            path = evidence.write_latest_pointer(experiment_dir, "20260927-010203-abc1234")
            self.assertEqual(path, experiment_dir / "records" / "LATEST")

    def test_overwrites_a_prior_pointer_rather_than_appending(self):
        """The pointer names the CURRENT record; records themselves are
        append-only, the pointer is not."""
        with tempfile.TemporaryDirectory() as tmp:
            experiment_dir = Path(tmp)
            (experiment_dir / "records").mkdir()
            evidence.write_latest_pointer(experiment_dir, "20260101-000000-old0000")
            path = evidence.write_latest_pointer(experiment_dir, "20260927-010203-new0000")
            self.assertEqual(path.read_text(), "20260927-010203-new0000.md\n")

    def test_does_not_create_a_missing_records_dir(self):
        """Every caller writes its record into records/ first, so a missing
        records/ means the caller is mis-wired -- surface that rather than
        minting a pointer into an empty directory."""
        with tempfile.TemporaryDirectory() as tmp:
            experiment_dir = Path(tmp)
            with self.assertRaises(FileNotFoundError):
                evidence.write_latest_pointer(experiment_dir, "20260927-010203-abc1234")
            self.assertFalse((experiment_dir / "records").exists())


class TestRunKltYield(unittest.TestCase):
    """evidence.run_klt_yield() -- shared plumbing extracted (issue #131)
    from the two byte-identical `_run_klt_yield` private helpers PR #130
    introduced independently in sim/cdac-array-transfer/run_mc.py and
    sim/enob-estimate/run_enob.py. Mirrors those two helpers' own behavior
    exactly: `klt` missing / a malformed report / an `"error"` key all
    return None rather than raising, so a missing/broken toolchain becomes
    an honest evidence-record gap instead of a crash."""

    def _measurements(self):
        return [
            {
                "name": "x",
                "unit": "LSB",
                "samples": [0.1, 0.2, 0.3],
                "limits": {"min": -1.0, "max": 1.0, "target_yield": 0.99},
            },
        ]

    def test_missing_klt_binary_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "yield-reports" / "rec.json"
            with mock.patch.object(evidence.subprocess, "run", side_effect=FileNotFoundError()):
                report = evidence.run_klt_yield(self._measurements(), out_path)
        self.assertIsNone(report)
        self.assertFalse(out_path.exists())

    def test_timeout_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "yield-reports" / "rec.json"
            with mock.patch.object(
                evidence.subprocess, "run",
                side_effect=subprocess.TimeoutExpired(cmd=["klt"], timeout=60),
            ):
                report = evidence.run_klt_yield(self._measurements(), out_path)
        self.assertIsNone(report)
        self.assertFalse(out_path.exists())

    def test_malformed_json_output_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "yield-reports" / "rec.json"
            fake_proc = subprocess.CompletedProcess(args=["klt"], returncode=0, stdout="not json", stderr="")
            with mock.patch.object(evidence.subprocess, "run", return_value=fake_proc):
                report = evidence.run_klt_yield(self._measurements(), out_path)
        self.assertIsNone(report)
        self.assertFalse(out_path.exists())

    def test_error_key_in_report_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "yield-reports" / "rec.json"
            fake_proc = subprocess.CompletedProcess(
                args=["klt"], returncode=1, stdout=json.dumps({"error": "no native extension"}), stderr="",
            )
            with mock.patch.object(evidence.subprocess, "run", return_value=fake_proc):
                report = evidence.run_klt_yield(self._measurements(), out_path)
        self.assertIsNone(report)

    def test_valid_report_is_returned_and_written_to_out_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "yield-reports" / "rec.json"
            fake_report = {"measurements": [{"name": "x", "n": 3}]}
            fake_proc = subprocess.CompletedProcess(
                args=["klt"], returncode=0, stdout=json.dumps(fake_report), stderr="",
            )
            with mock.patch.object(evidence.subprocess, "run", return_value=fake_proc) as run_mock:
                report = evidence.run_klt_yield(self._measurements(), out_path)
            self.assertEqual(report, fake_report)
            self.assertTrue(out_path.is_file())
            self.assertEqual(json.loads(out_path.read_text()), fake_report)
            called_args = run_mock.call_args.args[0]
            self.assertEqual(called_args[:2], ["klt", "yield"])
            self.assertEqual(called_args[3], "--format")
            self.assertTrue(called_args[2].endswith(".json"))

    def test_samples_document_persisted_and_cited(self):
        import hashlib

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "yield-reports" / "rec.json"
            captured = {}

            def fake_run(cmd, **kw):
                sp = Path(cmd[2])
                if not sp.is_absolute():
                    sp = Path(kw["cwd"]) / sp
                captured["bytes"] = sp.read_bytes()
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout=json.dumps({"samples": cmd[2]}), stderr="",
                )

            with mock.patch.object(evidence.subprocess, "run", side_effect=fake_run):
                report = evidence.run_klt_yield(self._measurements(), out_path)
            cited = Path(report["samples"])
            self.assertTrue(cited.is_absolute())  # tmp is outside the repo
            self.assertTrue(cited.is_file())
            self.assertEqual(cited.parent, out_path.parent.resolve())
            self.assertEqual(
                hashlib.sha256(cited.read_bytes()).hexdigest(),
                hashlib.sha256(captured["bytes"]).hexdigest(),
            )
            self.assertEqual(json.loads(cited.read_text()), {"measurements": self._measurements()})


class TestResolveCornersProvenance(unittest.TestCase):
    """evidence.resolve_corners_provenance() -- the corners-campaign layer
    above resolve_provenance() that sim/sampling-acquisition-settling/,
    sim/sequencer-logic-delay/, and sim/cdac-bit-trial-settling/ each
    repeated verbatim in write_corners_record() before issue #283. Pure
    file/dict plumbing: resolve_provenance() itself is faked so no PDK or
    ngspice is needed."""

    def _point(self, corner: str, temp_c: float, supply_v: float, complete: bool = True):
        corner_id = corners.corner_id(corner, temp_c, supply_v)
        return {
            "corner": corner,
            "temp_c": temp_c,
            "supply_v": supply_v,
            "corner_id": corner_id,
            "netlist": f"* deck for {corner_id}\n",
            "complete": complete,
        }

    def _fake_resolve(self, seen: list):
        def fake(experiment_dir: Path, netlist_text: str):
            seen.append(netlist_text)
            (experiment_dir / "netlist-snapshots").mkdir(parents=True, exist_ok=True)
            (experiment_dir / "records").mkdir(parents=True, exist_ok=True)
            return evidence.ProvenanceInfo(
                record_id="REC",
                record_path=experiment_dir / "records" / "REC.md",
                netlist_sha="0" * 64,
                pdk_line="sky130A @ testing",
                ng_version="ngspice-46",
            )

        return fake

    def test_baseline_snapshot_decks_and_run_summary(self):
        points = [
            self._point("ss", 27.0, 1.8),
            self._point("tt", 27.0, 1.8),
            self._point("tt", 125.0, 1.62, complete=False),
        ]
        seen: list = []
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            with mock.patch.object(evidence, "resolve_provenance", self._fake_resolve(seen)):
                info = evidence.resolve_corners_provenance(tmp_dir, points, 1.8)

            # the tt/27C/nominal point is the one snapshotted, not points[0]
            self.assertEqual(seen, ["* deck for tt_27c_1.80v\n"])
            # the five ProvenanceInfo fields pass through unchanged
            self.assertEqual(info.record_id, "REC")
            self.assertEqual(info.record_path, tmp_dir / "records" / "REC.md")
            self.assertEqual(info.netlist_sha, "0" * 64)
            self.assertEqual(info.pdk_line, "sky130A @ testing")
            self.assertEqual(info.ng_version, "ngspice-46")
            # every point's own deck lands in corners/<record-id>/
            self.assertEqual(info.corners_dir, tmp_dir / "corners" / "REC")
            for p in points:
                deck = info.corners_dir / f"{p['corner_id']}.spice"
                self.assertTrue(deck.is_file(), f"missing deck for {p['corner_id']}")
                self.assertEqual(deck.read_text(), p["netlist"])

        self.assertEqual(info.process_corners_run, ["ss", "tt"])
        self.assertEqual(info.temps_run, [27.0, 125.0])
        self.assertEqual(info.supplies_run, [1.62, 1.8])
        self.assertEqual([p["corner_id"] for p in info.incomplete], ["tt_125c_1.62v"])
        self.assertEqual(
            [p["corner_id"] for p in info.complete_points], ["ss_27c_1.80v", "tt_27c_1.80v"]
        )

    def test_baseline_falls_back_to_first_point(self):
        # a campaign whose grid has no tt/27C/nominal point at all (e.g. a
        # supply-axis-only re-run) still snapshots a deck rather than raising
        points = [self._point("ss", -40.0, 1.62), self._point("ff", 125.0, 1.98)]
        seen: list = []
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(evidence, "resolve_provenance", self._fake_resolve(seen)):
                evidence.resolve_corners_provenance(Path(tmp), points, 1.8)
        self.assertEqual(seen, [points[0]["netlist"]])


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

    def test_run_ngspice_raises_on_nonzero_return_code(self):
        """A crashed/erroring ngspice must surface as an explicit harness
        error, not silently fall through to "no measurement parsed" (issue
        #8). Both runner.py and mc_runner.py delegate to the shared
        toolchain.run_ngspice() (issue #10), so this exercises it once via
        the shared location on behalf of both call sites."""
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp)
            with mock.patch.object(toolchain.shutil, "copyfile"):
                with mock.patch.object(
                    toolchain.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess(
                        args=["ngspice"], returncode=1, stdout="", stderr="fatal error"
                    ),
                ):
                    with self.assertRaises(RuntimeError) as ctx:
                        toolchain.run_ngspice("* netlist\n.end\n", scratch, "corner_0")
        self.assertIn("exited 1", str(ctx.exception))

    def test_run_ngspice_raises_on_timeout(self):
        """Both runner.py and mc_runner.py delegate to the shared
        toolchain.run_ngspice() (issue #10), so this exercises it once via
        the shared location on behalf of both call sites."""
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp)
            with mock.patch.object(toolchain.shutil, "copyfile"):
                with mock.patch.object(
                    toolchain.subprocess,
                    "run",
                    side_effect=subprocess.TimeoutExpired(cmd=["ngspice"], timeout=120),
                ):
                    with self.assertRaises(RuntimeError) as ctx:
                        toolchain.run_ngspice("* netlist\n.end\n", scratch, "corner_0")
        self.assertIn("timed out", str(ctx.exception))

    def test_run_ngspice_timeout_with_bytes_output_does_not_crash(self):
        """Regression test (found while gathering evidence for issue #61):
        a REAL subprocess timeout can populate TimeoutExpired.stdout with
        bytes while .stderr stays None (or vice versa) even though
        subprocess.run() was called with text=True -- CPython only
        re-decodes those attributes on the Windows retry path; on POSIX,
        TimeoutExpired's own partial-output attributes (captured inside
        Popen.communicate() before the timeout fired) are not guaranteed to
        have gone through the text-mode decode step the successful-
        completion path does, and ngspice -b's stderr is very often empty
        (None) while stdout is not. The prior implementation's `(exc.stdout
        or "") + (exc.stderr or "")` raised `TypeError: can't concat str to
        bytes` in exactly this MIXED-types case (`"" + bytes` or `bytes +
        ""`) -- concatenating two REAL bytes values, or two None values,
        both happen to work fine in plain Python, which is why this needs
        the mixed case specifically to reproduce. Masked the real "ngspice
        timed out" RuntimeError with an unrelated crash -- reproduced live
        via sim/sampling-frontend/run_hold_kick.py (#61) hitting a genuine
        ngspice timeout on a contended machine. test_run_ngspice_raises_
        on_timeout() above does not catch this: it constructs
        TimeoutExpired with no output at all (both attributes default to
        None), which the buggy code also handled fine -- only a bytes/None
        mix was broken."""
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp)
            with mock.patch.object(toolchain.shutil, "copyfile"):
                with mock.patch.object(
                    toolchain.subprocess,
                    "run",
                    side_effect=subprocess.TimeoutExpired(
                        cmd=["ngspice"], timeout=120,
                        output=b"partial stdout\n", stderr=None,
                    ),
                ):
                    with self.assertRaises(RuntimeError) as ctx:
                        toolchain.run_ngspice("* netlist\n.end\n", scratch, "corner_0")
        self.assertIn("timed out", str(ctx.exception))
        self.assertIn("partial stdout", str(ctx.exception))

    def test_toolchain_timeout_s_defaults_when_unset(self):
        """No SIM_NGSPICE_TIMEOUT_S override -> the historical 120s default
        (issue #133)."""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(toolchain.TIMEOUT_ENV_VAR, None)
            self.assertEqual(toolchain.toolchain_timeout_s(), toolchain.DEFAULT_TOOLCHAIN_TIMEOUT_S)

    def test_toolchain_timeout_s_honors_env_override(self):
        """SIM_NGSPICE_TIMEOUT_S raises (or lowers) the budget without
        touching source (issue #133)."""
        with mock.patch.dict(os.environ, {toolchain.TIMEOUT_ENV_VAR: "300"}):
            self.assertEqual(toolchain.toolchain_timeout_s(), 300.0)

    def test_toolchain_timeout_s_rejects_non_numeric_override(self):
        with mock.patch.dict(os.environ, {toolchain.TIMEOUT_ENV_VAR: "not-a-number"}):
            with self.assertRaises(RuntimeError) as ctx:
                toolchain.toolchain_timeout_s()
        self.assertIn(toolchain.TIMEOUT_ENV_VAR, str(ctx.exception))

    def test_toolchain_timeout_s_rejects_non_positive_override(self):
        with mock.patch.dict(os.environ, {toolchain.TIMEOUT_ENV_VAR: "0"}):
            with self.assertRaises(RuntimeError):
                toolchain.toolchain_timeout_s()

    def test_run_ngspice_uses_env_override_and_reports_it_in_the_timeout(self):
        """The timeout diagnostic message reports the ACTUAL (overridden)
        budget used, and tells the user how to raise it further (issue
        #133) -- not the old hardcoded '120s' literal."""
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp)
            with mock.patch.dict(os.environ, {toolchain.TIMEOUT_ENV_VAR: "7"}):
                with mock.patch.object(toolchain.shutil, "copyfile"):
                    with mock.patch.object(
                        toolchain.subprocess,
                        "run",
                        side_effect=subprocess.TimeoutExpired(cmd=["ngspice"], timeout=7),
                    ) as mock_run:
                        with self.assertRaises(RuntimeError) as ctx:
                            toolchain.run_ngspice("* netlist\n.end\n", scratch, "corner_0")
        self.assertEqual(mock_run.call_args.kwargs["timeout"], 7.0)
        self.assertIn("timed out after 7s", str(ctx.exception))
        self.assertIn(toolchain.TIMEOUT_ENV_VAR, str(ctx.exception))

    def test_run_ngspice_with_retry_retries_on_timeout_then_succeeds(self):
        """Issue #299: the retry/backoff policy previously hand-rolled at
        six sim/*/run_*.py call sites now lives once in
        run_ngspice_with_retry(). A timeout on the first attempt is
        absorbed with a backoff sleep, then the second attempt succeeds."""
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp)
            with mock.patch.object(
                toolchain,
                "run_ngspice",
                side_effect=[RuntimeError("ngspice timed out after 120s"), "ok log"],
            ) as mock_run_ngspice:
                with mock.patch.object(toolchain.time, "sleep") as mock_sleep:
                    result = toolchain.run_ngspice_with_retry(
                        "* netlist\n.end\n", scratch, "corner_0"
                    )
        self.assertEqual(result, "ok log")
        self.assertEqual(mock_run_ngspice.call_count, 2)
        mock_sleep.assert_called_once_with(15 * 1)

    def test_run_ngspice_with_retry_reraises_non_timeout_immediately(self):
        """A non-timeout RuntimeError (e.g. a real ngspice crash) must not
        be retried -- only "timed out" failures are transient-contention
        candidates."""
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp)
            with mock.patch.object(
                toolchain, "run_ngspice", side_effect=RuntimeError("ngspice exited 1")
            ) as mock_run_ngspice:
                with mock.patch.object(toolchain.time, "sleep") as mock_sleep:
                    with self.assertRaises(RuntimeError) as ctx:
                        toolchain.run_ngspice_with_retry(
                            "* netlist\n.end\n", scratch, "corner_0"
                        )
        self.assertIn("exited 1", str(ctx.exception))
        self.assertEqual(mock_run_ngspice.call_count, 1)
        mock_sleep.assert_not_called()

    def test_run_ngspice_with_retry_raises_after_exhausting_attempts(self):
        """Exhausting every retry on the same netlist still raises -- a
        genuine, reproducible timeout is not masked forever."""
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp)
            with mock.patch.object(
                toolchain,
                "run_ngspice",
                side_effect=RuntimeError("ngspice timed out after 120s"),
            ) as mock_run_ngspice:
                with mock.patch.object(toolchain.time, "sleep"):
                    with self.assertRaises(RuntimeError) as ctx:
                        toolchain.run_ngspice_with_retry(
                            "* netlist\n.end\n", scratch, "corner_0", attempts=3
                        )
        self.assertIn("timed out", str(ctx.exception))
        self.assertEqual(mock_run_ngspice.call_count, 3)

    def test_run_ngspice_with_retry_honors_custom_attempts_param(self):
        """sim/full-conversion-transient/run_conversion.py passes attempts=3
        (not the default 4) -- the shared helper must honor a caller-
        supplied attempts value rather than hardcoding it (issue #299)."""
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp)
            with mock.patch.object(
                toolchain,
                "run_ngspice",
                side_effect=[
                    RuntimeError("ngspice timed out after 120s"),
                    RuntimeError("ngspice timed out after 120s"),
                    "ok log",
                ],
            ) as mock_run_ngspice:
                with mock.patch.object(toolchain.time, "sleep"):
                    result = toolchain.run_ngspice_with_retry(
                        "* netlist\n.end\n", scratch, "corner_0", attempts=3
                    )
        self.assertEqual(result, "ok log")
        self.assertEqual(mock_run_ngspice.call_count, 3)


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

    def test_positive_control_ok_when_draws_vary(self):
        class FakeResult:
            draws = [
                mc_runner.Draw(seed=1, measures={"x": 5.0}, log_text=""),
                mc_runner.Draw(seed=2, measures={"x": 5.1}, log_text=""),
            ]

        ok, failures = mc_runner.positive_control_ok(FakeResult(), ["x"])
        self.assertTrue(ok)
        self.assertEqual(failures, [])

    def test_positive_control_fails_when_draws_are_degenerate(self):
        """The exact regression issue #8 describes: if MC_MM_SWITCH ever
        stopped taking effect, the mismatch-enabled draws would collapse to
        a point -- stdev == 0 -- just like the negative control. This must
        fail, not silently pass as "a perfectly plausible distribution of
        width zero"."""

        class FakeResult:
            draws = [
                mc_runner.Draw(seed=1, measures={"x": 5.0}, log_text=""),
                mc_runner.Draw(seed=2, measures={"x": 5.0}, log_text=""),
            ]

        ok, failures = mc_runner.positive_control_ok(FakeResult(), ["x"])
        self.assertFalse(ok)
        self.assertEqual(len(failures), 1)
        self.assertIn("not >", failures[0])

    def test_positive_control_no_samples_parsed_fails(self):
        class FakeResult:
            draws: list = []

        ok, failures = mc_runner.positive_control_ok(FakeResult(), ["x"])
        self.assertFalse(ok)
        self.assertIn("no mismatch-enabled samples parsed", failures[0])

    def test_positive_control_honors_manifest_min_stdev_floor(self):
        """A manifest-declared `min_stdev` floor (kept out of harness code,
        per corners.py's convention) is enforced even when the bare
        stdev > 0 check would have passed -- guards against a spread that
        is technically nonzero but too small to trust (e.g. floating-point
        noise)."""

        class FakeResult:
            draws = [
                mc_runner.Draw(seed=1, measures={"x": 5.0}, log_text=""),
                mc_runner.Draw(seed=2, measures={"x": 5.0 + 1e-9}, log_text=""),
            ]

        ok, failures = mc_runner.positive_control_ok(
            FakeResult(), ["x"], checks={"x": {"min_stdev": 1e-6}}
        )
        self.assertFalse(ok)
        self.assertIn("min_stdev floor", failures[0])

        # The same draws pass with no floor declared (default 0.0).
        ok2, failures2 = mc_runner.positive_control_ok(FakeResult(), ["x"])
        self.assertTrue(ok2)
        self.assertEqual(failures2, [])


class TestToolchainDriftVsWarning(unittest.TestCase):
    """The status-1 (drift, fatal) vs warning (recorded, non-fatal) split.

    check_env() reaches out to the real ngspice/xschem/PDK on the machine, so
    these tests patch the three probes rather than requiring any of them --
    the point under test is the classification, not the probing.
    """

    def setUp(self):
        self._saved = (
            toolchain._ngspice_version,
            toolchain._xschem_version,
            toolchain.pdk.resolve,
            toolchain.pdk.resolved_commit_verified,
        )
        cfg = toolchain._load()
        self.pinned_pdk = cfg["open_pdks"]
        self.pinned_xschem = cfg["xschem_tag"]
        self.ngspice_floor = cfg["ngspice_min_major"]

        class FakeInfo:
            found = True
            variant = "sky130A"
            variant_dir = Path("/fake/sky130A")
            error = ""

        toolchain.pdk.resolve = lambda: FakeInfo()
        toolchain.pdk.resolved_commit_verified = lambda info: self.pinned_pdk

    def tearDown(self):
        (
            toolchain._ngspice_version,
            toolchain._xschem_version,
            toolchain.pdk.resolve,
            toolchain.pdk.resolved_commit_verified,
        ) = self._saved

    def test_xschem_drift_is_a_warning_not_a_failure(self):
        toolchain._ngspice_version = lambda: f"ngspice-{self.ngspice_floor}"
        toolchain._xschem_version = lambda: "0.0.1-definitely-not-the-pin"
        result = toolchain.check_env()
        self.assertEqual(result.status, 0)
        self.assertEqual(result.messages, [])
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("not fatal", result.warnings[0])

    def test_ngspice_below_floor_is_fatal_drift(self):
        toolchain._ngspice_version = lambda: f"ngspice-{self.ngspice_floor - 1}"
        toolchain._xschem_version = lambda: self.pinned_xschem
        result = toolchain.check_env()
        self.assertEqual(result.status, 1)
        self.assertEqual(len(result.messages), 1)
        self.assertIn("below floor", result.messages[0])

    def test_missing_ngspice_is_skippable_not_drift(self):
        toolchain._ngspice_version = lambda: None
        toolchain._xschem_version = lambda: self.pinned_xschem
        self.assertEqual(toolchain.check_env().status, 3)

    def test_pdk_commit_drift_is_fatal(self):
        toolchain._ngspice_version = lambda: f"ngspice-{self.ngspice_floor}"
        toolchain._xschem_version = lambda: self.pinned_xschem
        toolchain.pdk.resolved_commit_verified = lambda info: "0" * 40
        result = toolchain.check_env()
        self.assertEqual(result.status, 1)
        self.assertIn("!= pinned", result.messages[0])

    def test_unverifiable_pdk_provenance_is_a_warning_not_a_silent_pass(self):
        """A PDK install whose commit can't be verified through volare's
        path layout (resolved_commit_verified() returns None) must NOT
        satisfy the pin -- it should warn, not pass silently, and must
        never appear in `messages` (which would make it drift-fatal) nor
        be omitted entirely (issue #8: this used to silently pass because
        pdk.resolved_commit()'s "<pin> (unverified -- ...)" display string
        happens to startswith() the pin)."""
        toolchain._ngspice_version = lambda: f"ngspice-{self.ngspice_floor}"
        toolchain._xschem_version = lambda: self.pinned_xschem
        toolchain.pdk.resolved_commit_verified = lambda info: None
        result = toolchain.check_env()
        self.assertEqual(result.status, 0)
        self.assertEqual(result.messages, [])
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("unverifiable", result.warnings[0])
        self.assertIn(self.pinned_pdk, result.warnings[0])

    def test_allow_drift_downgrades_to_ok_but_keeps_the_message(self):
        toolchain._ngspice_version = lambda: f"ngspice-{self.ngspice_floor - 1}"
        toolchain._xschem_version = lambda: self.pinned_xschem
        result = toolchain.check_env(allow_drift=True)
        self.assertEqual(result.status, 0)
        self.assertEqual(len(result.messages), 1)


class TestPdkResolve(unittest.TestCase):
    """Direct coverage of resolve()'s three return paths -- missing variant
    dir, missing ngspice lib, and success -- previously only exercised
    indirectly via toolchain.check_env() (TestToolchainDriftVsWarning
    above), per issue #34."""

    def _resolve_with_root(self, root: Path) -> pdk.PdkInfo:
        with mock.patch.dict(os.environ, {"PDK_ROOT": str(root), "PDK": "sky130A"}):
            return pdk.resolve()

    def test_missing_variant_dir_is_not_found_with_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            info = self._resolve_with_root(Path(tmp))
            self.assertFalse(info.found)
            self.assertIn("no PDK variant directory", info.error)

    def test_missing_ngspice_lib_is_not_found_with_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "sky130A").mkdir()
            info = self._resolve_with_root(Path(tmp))
            self.assertFalse(info.found)
            self.assertIn("no ngspice model library", info.error)

    def test_fully_present_pdk_resolves_found_with_no_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = pdk.load_pdk_json()
            variant_dir = Path(tmp) / "sky130A"
            ngspice_lib = variant_dir / cfg["ngspice_lib"]
            ngspice_lib.parent.mkdir(parents=True)
            ngspice_lib.write_text("")

            info = self._resolve_with_root(Path(tmp))
            self.assertTrue(info.found)
            self.assertEqual(info.error, "")


class TestPdkResolveOrRaise(unittest.TestCase):
    """resolve_or_raise() -- the resolve()-or-RuntimeError helper shared by
    sim/comparator-decision/run.py and layout/comparator/pex/regen_probe.py
    (issue #195), previously defined identically in both."""

    def _resolve_with_root(self, root: Path) -> pdk.PdkInfo:
        with mock.patch.dict(os.environ, {"PDK_ROOT": str(root), "PDK": "sky130A"}):
            return pdk.resolve_or_raise()

    def test_missing_pdk_raises_runtime_error_with_resolve_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError) as ctx:
                self._resolve_with_root(Path(tmp))
            self.assertIn("no PDK variant directory", str(ctx.exception))

    def test_fully_present_pdk_returns_the_resolved_info(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = pdk.load_pdk_json()
            variant_dir = Path(tmp) / "sky130A"
            ngspice_lib = variant_dir / cfg["ngspice_lib"]
            ngspice_lib.parent.mkdir(parents=True)
            ngspice_lib.write_text("")

            info = self._resolve_with_root(Path(tmp))
            self.assertTrue(info.found)
            self.assertEqual(info.error, "")


class TestReadWrdataCsv(unittest.TestCase):
    """toolchain.read_wrdata_csv() -- the ngspice `wrdata` CSV parser
    shared by sim/comparator-decision/run.py and
    layout/comparator/pex/regen_probe.py (issue #195), previously defined
    identically in both."""

    def test_parses_repeated_time_column_per_vector(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "out.csv"
            # 2 vectors -> 4 columns per row: time0 outp time1 outn
            csv_path.write_text(
                "0.0 0.9 0.0 0.9\n"
                "1e-9 1.1 1e-9 0.7\n"
                "2e-9 1.7 2e-9 0.1\n"
            )
            t, outp, outn = toolchain.read_wrdata_csv(csv_path, 2)
            self.assertEqual(t, [0.0, 1e-9, 2e-9])
            self.assertEqual(outp, [0.9, 1.1, 1.7])
            self.assertEqual(outn, [0.9, 0.7, 0.1])

    def test_skips_blank_and_non_numeric_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "out.csv"
            csv_path.write_text(
                "\n"
                "Values in table:\n"
                "0.0 0.5 0.0 0.5\n"
                "\n"
                "1e-9 0.6 1e-9 0.4\n"
            )
            t, outp, outn = toolchain.read_wrdata_csv(csv_path, 2)
            self.assertEqual(t, [0.0, 1e-9])
            self.assertEqual(outp, [0.5, 0.6])
            self.assertEqual(outn, [0.5, 0.4])

    def test_short_rows_below_expected_columns_are_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "out.csv"
            # expected_cols = 2*3 = 6; a stray 4-column row must be skipped,
            # not misread as a valid (but wrong) row.
            csv_path.write_text(
                "0.0 0.1 0.0 0.1\n"
                "1e-9 0.2 1e-9 0.3 1e-9 0.4\n"
            )
            t, a_vec, b_vec, c_vec = toolchain.read_wrdata_csv(csv_path, 3)
            self.assertEqual(t, [1e-9])
            self.assertEqual(a_vec, [0.2])
            self.assertEqual(b_vec, [0.3])
            self.assertEqual(c_vec, [0.4])


class TestPdkResolvedCommit(unittest.TestCase):
    """pdk.resolved_commit() (display) vs. resolved_commit_verified()
    (fail-closed gate input) -- issue #8: these used to be the same
    function, and the fallback's "<pin> (unverified -- ...)" display
    string happened to startswith() the pin, silently satisfying
    toolchain.check_env()'s drift gate for an install of unknown
    provenance."""

    def test_verified_commit_found_via_volare_shaped_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            commit = "a" * 40
            versions_dir = Path(tmp) / "sky130" / "versions" / commit / "sky130A"
            versions_dir.mkdir(parents=True)

            class FakeInfo:
                variant_dir = versions_dir
                open_pdks_commit_expected = "b" * 40

            self.assertEqual(pdk.resolved_commit_verified(FakeInfo()), commit)
            self.assertEqual(pdk.resolved_commit(FakeInfo()), commit)

    def test_non_volare_layout_is_unverifiable(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain_dir = Path(tmp) / "some-hand-install" / "sky130A"
            plain_dir.mkdir(parents=True)

            class FakeInfo:
                variant_dir = plain_dir
                open_pdks_commit_expected = "b" * 40

            self.assertIsNone(pdk.resolved_commit_verified(FakeInfo()))
            display = pdk.resolved_commit(FakeInfo())
            self.assertTrue(display.startswith("b" * 40))
            self.assertIn("unverified", display)

    def test_nonexistent_path_is_unverifiable_not_an_error(self):
        class FakeInfo:
            variant_dir = Path("/definitely/does/not/exist/sky130A")
            open_pdks_commit_expected = "c" * 40

        self.assertIsNone(pdk.resolved_commit_verified(FakeInfo()))
        self.assertTrue(pdk.resolved_commit(FakeInfo()).startswith("c" * 40))


if __name__ == "__main__":
    unittest.main()

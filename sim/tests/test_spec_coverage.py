"""Unit tests for sim/check_spec_coverage.py -- the spec-row coverage check
(T1 item 9, issue #31). Pure file reads, no ngspice/PDK required (mirrors
sim/tests/test_harness.py's PDK-free unit-test convention; see sim/selftest.sh
stage 1/4).

Two kinds of test here, and both matter:

  1. The REAL tree must pass. `test_repo_tree_passes` runs the checker against
     this checkout, so a drifted index fails the unit stage as well as the
     dedicated `npm run check:spec-coverage` step.

  2. Every failure mode must actually FAIL. A completeness check that cannot
     be made to fail proves nothing -- so each test below builds a minimal
     synthetic repo, breaks exactly one property, and asserts the specific
     failure code. The headline case is `test_claimed_row_without_bench_fails`:
     the regression this whole check exists to prevent (a spec row gains a
     claim, no bench is committed for it, and every individual campaign still
     looks green)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
sys.path.insert(0, str(SIM_DIR))

from check_spec_coverage import (  # noqa: E402
    CoverageCheck,
    SpecTableError,
    normalize_status,
    parse_target_table,
    render_markdown,
)

SPEC_TEMPLATE = """# fake spec

## Target table

| Parameter | Target | Status | Note |
|---|---|---|---|
{rows}

## Something else
"""

RECORD_TEMPLATE = """# Record {rid}

- **Record ID**: {rid}
- **Claim**: `spec/target-spec.md#target-table` -- fake claim for tests.
- **Corner matrix run**: process={processes}, temperature_c=[-40, 27, 125], supply_v=[1.62, 1.8, 1.98] (9 points, one-at-a-time per sim/README.md)

## Environment

- PDK: {variant} @ {commit}
- ngspice: ngspice-{ngspice}
- DUT netlist sha256: `{sha}`

Written by `{written_by}`.
"""

PDK_JSON = {
    "variant": "fakeA",
    "open_pdks_commit": "c6d73a35f524070e85faff4a6a9eef49553ebc2b",
    "process_corners": ["tt", "ss", "ff"],
    "mismatch_corners": ["tt_mm", "ss_mm", "ff_mm"],
}
TOOLCHAIN_JSON = {"open_pdks": PDK_JSON["open_pdks_commit"], "ngspice_min_major": 46}

RUNNER_SRC = '''#!/usr/bin/env python3
"""Fake runner.

    python3 sim/widget/run.py --record
"""
import argparse

ap = argparse.ArgumentParser()
ap.add_argument("mode", nargs="?", choices=["sweep"])
ap.add_argument("--record", action="store_true")
'''


class FakeRepo:
    """A minimal synthetic repo: one spec row, one bench, one record. Each
    test mutates exactly one thing before running the checker."""

    def __init__(self, tmp: Path) -> None:
        self.root = tmp
        (self.root / "spec").mkdir(parents=True, exist_ok=True)
        (self.root / "sim").mkdir(parents=True, exist_ok=True)
        self.write_spec([("Widget size", "**RATIFIED** (DR-fake)")])
        self.write_json("sim/pdk.json", PDK_JSON)
        self.write_json("sim/toolchain.json", TOOLCHAIN_JSON)
        self.write("sim/widget/run.py", RUNNER_SRC)
        self.write("sim/widget/testbench/widget.spice", "* fake deck\n")
        self.write_record("sim/widget/records/20260101-000000-abc1234.md")
        self.write("sim/harness-corner-smoke/testbench/tb.json", json.dumps({"claim": "None -- harness self-test"}))
        self.write("sim/harness-corner-smoke/records/20260101-000000-abc1234.md", "harness proof record\n")
        self.write("sim/mc-smoke/testbench/tb.json", json.dumps({"claim": "None -- harness self-test"}))
        self.write("sim/mc-smoke/records/20260101-000000-abc1234.md", "harness proof record\n")
        self.index = {
            "schema_version": 1,
            "spec_file": "spec/target-spec.md",
            "pins": {"pdk_json": "sim/pdk.json", "toolchain_json": "sim/toolchain.json"},
            "cold_start_preamble": ["source sim/env.sh"],
            "harness_proofs": [
                {"experiment": "harness-corner-smoke", "why": "harness proof"},
                {"experiment": "mc-smoke", "why": "harness proof"},
            ],
            "rows": [
                {
                    "parameter": "Widget size",
                    "status": "RATIFIED",
                    "claim_class": "ratified-measured",
                    "note": "fake",
                    "benches": [
                        {
                            "experiment": "widget",
                            "runner": "sim/widget/run.py",
                            "testbench": ["sim/widget/testbench/widget.spice"],
                            "cold_start": "python3 sim/widget/run.py --record",
                            "documented_in": "sim/widget/run.py",
                            "covers": "fake",
                            "records": ["sim/widget/records/20260101-000000-abc1234.md"],
                        }
                    ],
                }
            ],
        }

    # ------------------------------------------------------------- utilities

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def write_json(self, rel: str, obj) -> None:
        self.write(rel, json.dumps(obj, indent=2) + "\n")

    def write_spec(self, rows: list[tuple[str, str]]) -> None:
        body = "\n".join(f"| {param} | some target | {status} | note |" for param, status in rows)
        self.write("spec/target-spec.md", SPEC_TEMPLATE.format(rows=body))

    def write_record(
        self,
        rel: str,
        *,
        variant: str = PDK_JSON["variant"],
        commit: str = PDK_JSON["open_pdks_commit"],
        ngspice: int = 46,
        written_by: str = "sim/widget/run.py",
        processes: str = "['ff', 'ss', 'tt']",
        sha: str = "0" * 64,
    ) -> None:
        self.write(
            rel,
            RECORD_TEMPLATE.format(
                rid=Path(rel).stem,
                variant=variant,
                commit=commit,
                ngspice=ngspice,
                written_by=written_by,
                processes=processes,
                sha=sha,
            ),
        )

    def flush(self) -> None:
        """Write the (possibly mutated) index and its rendering to disk."""
        self.write_json("sim/spec-coverage.json", self.index)
        self.write("sim/spec-coverage.md", render_markdown(self.index))

    def codes(self) -> list[str]:
        self.flush()
        return [f.code for f in CoverageCheck(self.root).run()]


class TestTargetTableParse(unittest.TestCase):
    def test_parses_parameter_and_status(self):
        text = SPEC_TEMPLATE.format(
            rows="| Alpha | 1 | DRAFT | n |\n| Beta | 2 | **RATIFIED** (DR-9) | n |"
        )
        self.assertEqual(
            parse_target_table(text), [("Alpha", "DRAFT"), ("Beta", "**RATIFIED** (DR-9)")]
        )

    def test_missing_heading_raises(self):
        with self.assertRaises(SpecTableError):
            parse_target_table("# spec\n\nno table here\n")

    def test_normalize_status(self):
        self.assertEqual(normalize_status("**RATIFIED** (DR-003 via #27)"), "RATIFIED")
        self.assertEqual(normalize_status("DRAFT (target value)"), "DRAFT")

    def test_real_spec_table_parses(self):
        rows = parse_target_table((REPO_ROOT / "spec/target-spec.md").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(rows), 5)
        self.assertIn("Resolution `N`", [param for param, _ in rows])


class TestRealRepo(unittest.TestCase):
    def test_repo_tree_passes(self):
        failures = CoverageCheck(REPO_ROOT).run()
        self.assertEqual([f.render() for f in failures], [])

    def test_rendered_doc_is_current(self):
        index = json.loads((REPO_ROOT / "sim/spec-coverage.json").read_text(encoding="utf-8"))
        self.assertEqual(
            (REPO_ROOT / "sim/spec-coverage.md").read_text(encoding="utf-8"),
            render_markdown(index),
            "sim/spec-coverage.md is stale -- run python3 sim/check_spec_coverage.py --render",
        )

    def test_every_ratified_row_is_benched(self):
        """The property the check exists to guarantee, asserted directly against
        the real tree rather than only through the checker's own codes."""
        index = json.loads((REPO_ROOT / "sim/spec-coverage.json").read_text(encoding="utf-8"))
        for row in index["rows"]:
            if row["status"] == "RATIFIED":
                self.assertTrue(
                    row["benches"],
                    f"ratified spec row {row['parameter']!r} has no committed bench",
                )


class TestFailureModes(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = FakeRepo(Path(self._tmp.name))
        self.addCleanup(self._tmp.cleanup)

    def test_baseline_synthetic_repo_passes(self):
        self.assertEqual(self.repo.codes(), [])

    # -- the headline regression: a claimed row with no bench ---------------

    def test_claimed_row_without_bench_fails(self):
        self.repo.index["rows"][0]["benches"] = []
        self.assertIn("row-has-no-bench", self.repo.codes())

    def test_new_spec_row_not_in_index_fails(self):
        self.repo.write_spec(
            [("Widget size", "**RATIFIED** (DR-fake)"), ("Widget speed", "**RATIFIED** (DR-fake)")]
        )
        self.assertIn("spec-row-missing-from-index", self.repo.codes())

    def test_index_row_absent_from_spec_fails(self):
        self.repo.index["rows"].append(
            {"parameter": "Ghost row", "status": "DRAFT", "claim_class": "unbenched",
             "reason": "x" * 50, "benches": []}
        )
        self.assertIn("index-row-not-in-spec", self.repo.codes())

    def test_ratified_row_cannot_be_unbenched(self):
        row = self.repo.index["rows"][0]
        row["claim_class"] = "unbenched"
        row["reason"] = "y" * 50
        row["benches"] = []
        self.assertIn("ratified-row-unbenched", self.repo.codes())

    def test_unbenched_row_needs_a_reason(self):
        self.repo.write_spec([("Widget size", "DRAFT")])
        row = self.repo.index["rows"][0]
        row["status"] = "DRAFT"
        row["claim_class"] = "unbenched"
        row["benches"] = []
        self.assertIn("unbenched-row-missing-reason", self.repo.codes())

    def test_status_drift_between_spec_and_index_fails(self):
        self.repo.write_spec([("Widget size", "DRAFT")])
        self.assertIn("status-drift", self.repo.codes())

    # -- artifacts ----------------------------------------------------------

    def test_missing_record_file_fails(self):
        (self.repo.root / "sim/widget/records/20260101-000000-abc1234.md").unlink()
        self.assertIn("missing-path", self.repo.codes())

    def test_missing_testbench_deck_fails(self):
        (self.repo.root / "sim/widget/testbench/widget.spice").unlink()
        self.assertIn("missing-path", self.repo.codes())

    def test_bench_without_record_fails(self):
        self.repo.index["rows"][0]["benches"][0]["records"] = []
        self.assertIn("bench-has-no-record", self.repo.codes())

    def test_deck_less_bench_needs_an_explicit_note(self):
        self.repo.index["rows"][0]["benches"][0]["testbench"] = []
        self.assertIn("bench-has-no-deck", self.repo.codes())

    # -- cold start ---------------------------------------------------------

    def test_undocumented_cold_start_fails(self):
        self.repo.index["rows"][0]["benches"][0]["cold_start"] = "python3 sim/widget/run.py --record --quiet"
        codes = self.repo.codes()
        self.assertIn("cold-start-undocumented", codes)

    def test_cold_start_with_unknown_flag_fails(self):
        self.repo.write(
            "sim/widget/README.md", "python3 sim/widget/run.py --nonexistent-flag\n"
        )
        bench = self.repo.index["rows"][0]["benches"][0]
        bench["cold_start"] = "python3 sim/widget/run.py --nonexistent-flag"
        bench["documented_in"] = "sim/widget/README.md"
        self.assertIn("cold-start-unknown-flag", self.repo.codes())

    def test_cold_start_with_unknown_subcommand_fails(self):
        self.repo.write("sim/widget/README.md", "python3 sim/widget/run.py teleport --record\n")
        bench = self.repo.index["rows"][0]["benches"][0]
        bench["cold_start"] = "python3 sim/widget/run.py teleport --record"
        bench["documented_in"] = "sim/widget/README.md"
        self.assertIn("cold-start-unknown-subcommand", self.repo.codes())

    def test_documented_command_must_match_the_one_that_minted_the_record(self):
        """The 'no undocumented private path' clause: a record minted by
        `run.py sweep` while the docs advertise plain `run.py` is a failure."""
        self.repo.write_record(
            "sim/widget/records/20260101-000000-abc1234.md",
            written_by="sim/widget/run.py sweep",
        )
        self.assertIn("cold-start-record-mismatch", self.repo.codes())

    def test_record_written_by_a_different_runner_fails(self):
        self.repo.write_record(
            "sim/widget/records/20260101-000000-abc1234.md",
            written_by="sim/widget/other.py",
        )
        self.assertIn("record-runner-mismatch", self.repo.codes())

    # -- pinning ------------------------------------------------------------

    def test_pdk_commit_drift_fails(self):
        self.repo.write_record(
            "sim/widget/records/20260101-000000-abc1234.md", commit="d" * 40
        )
        self.assertIn("pdk-pin-drift", self.repo.codes())

    def test_pdk_variant_drift_fails(self):
        self.repo.write_record(
            "sim/widget/records/20260101-000000-abc1234.md", variant="otherB"
        )
        self.assertIn("pdk-pin-drift", self.repo.codes())

    def test_ngspice_below_floor_fails(self):
        self.repo.write_record("sim/widget/records/20260101-000000-abc1234.md", ngspice=42)
        self.assertIn("ngspice-pin-drift", self.repo.codes())

    def test_missing_pdk_line_fails(self):
        self.repo.write("sim/widget/records/20260101-000000-abc1234.md", "no environment here\n")
        codes = self.repo.codes()
        self.assertIn("pdk-pin-missing", codes)
        self.assertIn("ngspice-pin-missing", codes)
        self.assertIn("netlist-pin-missing", codes)

    # -- harness proofs and orphans ----------------------------------------

    def test_harness_proof_counted_as_a_bench_fails(self):
        self.repo.index["rows"][0]["benches"].append(
            {
                "experiment": "mc-smoke",
                "runner": "sim/widget/run.py",
                "testbench": ["sim/widget/testbench/widget.spice"],
                "cold_start": "python3 sim/widget/run.py --record",
                "documented_in": "sim/widget/run.py",
                "records": ["sim/widget/records/20260101-000000-abc1234.md"],
            }
        )
        self.assertIn("harness-proof-counted", self.repo.codes())

    def test_harness_proof_claiming_a_spec_row_fails(self):
        self.repo.write(
            "sim/mc-smoke/testbench/tb.json",
            json.dumps({"claim": "spec/target-spec.md#target-table -- widget size"}),
        )
        self.assertIn("harness-proof-claims-spec-row", self.repo.codes())

    def test_orphan_experiment_fails(self):
        self.repo.write("sim/stray/records/20260101-000000-abc1234.md", "stray evidence\n")
        self.assertIn("orphan-experiment", self.repo.codes())

    # -- methodology rows ---------------------------------------------------

    def test_methodology_row_missing_a_process_corner_fails(self):
        row = self.repo.index["rows"][0]
        row["claim_class"] = "methodology"
        self.repo.write_record(
            "sim/widget/records/20260101-000000-abc1234.md", processes="['tt', 'ss']"
        )
        self.assertIn("corner-set-incomplete", self.repo.codes())

    # -- generated rendering ------------------------------------------------

    def test_stale_rendered_doc_fails(self):
        self.repo.flush()
        self.repo.write("sim/spec-coverage.md", "hand-edited\n")
        self.assertIn("doc-stale", [f.code for f in CoverageCheck(self.repo.root).run()])


if __name__ == "__main__":
    unittest.main()

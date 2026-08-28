"""Unit tests for sim/report/generate.py (issue #30, T1 item 8: aggregated
characterization report). No ngspice/PDK required -- pure text/filesystem
logic, mirroring sim/tests/test_harness.py's PDK-free unit-test convention.

Covers the two acceptance criteria that are directly mechanically checkable:

- "Freshness is mechanical": find_superseding_sibling()/check_freshness()
  must detect a record that a sibling's own Supersedes field names, using a
  synthetic fixture directory (independent of this repo's real sim/ state,
  so this test cannot pass by accident just because nothing is stale today).
- "covering every ratified spec row": every Parameter row in
  spec/target-spec.md's own Target table must appear in
  sim/report/manifest.ROWS -- this is the guard against a future spec-table
  edit silently going un-aggregated.

Also regression-tests that the committed docs/characterization-report.md is
exactly what sim/report/generate.py would currently produce (the same check
`npm run check:report` runs in CI), so `test:unit` catches drift too.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
sys.path.insert(0, str(SIM_DIR))

from report import generate, manifest  # noqa: E402


class TestExtractField(unittest.TestCase):
    def test_extracts_simple_field(self):
        text = "- **Record ID**: 20260101-000000-abcdef1\n- **Overall**: PASS\n"
        self.assertEqual(generate.extract_field(text, "Record ID"), "20260101-000000-abcdef1")
        self.assertEqual(generate.extract_field(text, "Overall"), "PASS")

    def test_missing_field_returns_none(self):
        text = "- **Record ID**: 20260101-000000-abcdef1\n"
        self.assertIsNone(generate.extract_field(text, "Overall"))

    def test_field_name_with_parens_is_escaped(self):
        text = "- **Measured value(s)**: achieved ENOB = 8.491 bit\n"
        self.assertEqual(
            generate.extract_field(text, "Measured value(s)"),
            "achieved ENOB = 8.491 bit",
        )


class TestFindSupersedingSibling(unittest.TestCase):
    """Synthetic records/ directory -- does not touch this repo's real sim/
    state, so a future real supersession event cannot silently make this
    test start (or stop) exercising the code path it's checking."""

    def _write(self, records_dir: Path, record_id: str, supersedes: str = "(none)") -> Path:
        records_dir.mkdir(parents=True, exist_ok=True)
        path = records_dir / f"{record_id}.md"
        path.write_text(
            f"# Record {record_id}\n\n"
            f"- **Record ID**: {record_id}\n"
            "- **Claim**: synthetic fixture record, not real evidence\n"
            "- **Overall**: PASS\n"
            f"- **Supersedes**: {supersedes}\n"
        )
        return path

    def test_no_superseder_returns_none(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            records_dir = Path(tmp) / "records"
            old = self._write(records_dir, "20260101-000000-aaaaaaa")
            self._write(records_dir, "20260102-000000-bbbbbbb")  # unrelated, does not supersede
            self.assertIsNone(generate.find_superseding_sibling(old))

    def test_detects_direct_superseder(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            records_dir = Path(tmp) / "records"
            old = self._write(records_dir, "20260101-000000-aaaaaaa")
            newer = self._write(
                records_dir, "20260102-000000-bbbbbbb", supersedes="20260101-000000-aaaaaaa"
            )
            found = generate.find_superseding_sibling(old)
            self.assertEqual(found, newer)

    def test_check_freshness_reports_stale_citation(self):
        """End-to-end through check_freshness() with a fabricated Row
        pointing at the synthetic fixture, proving the CI-facing entry
        point (not just the low-level helper) surfaces the problem.
        `REPO_ROOT / <absolute path>` collapses to the absolute path
        (stdlib pathlib join semantics), so an absolute fixture path works
        as a "sim_citations" entry without needing to monkeypatch
        generate.REPO_ROOT."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            records_dir = Path(tmp) / "records"
            old = self._write(records_dir, "20260101-000000-aaaaaaa")
            self._write(
                records_dir, "20260102-000000-bbbbbbb", supersedes="20260101-000000-aaaaaaa"
            )
            fake_row = manifest.Row(
                id="fixture-row",
                spec_row="Fixture row",
                status="RATIFIED",
                spec_anchor="spec/target-spec.md#target-table",
                conditions="n/a",
                verdict="n/a",
                notes="",
                sim_citations=(str(old),),
            )
            problems = generate.check_freshness(rows=(fake_row,))
            self.assertEqual(len(problems), 1, problems)
            self.assertIn("superseded", problems[0])
            self.assertIn("fixture-row", problems[0])

    def test_check_freshness_reports_missing_citation(self):
        fake_row = manifest.Row(
            id="missing-row",
            spec_row="Missing row",
            status="RATIFIED",
            spec_anchor="spec/target-spec.md#target-table",
            conditions="n/a",
            verdict="n/a",
            notes="",
            sim_citations=("sim/does-not-exist/records/nope.md",),
        )
        problems = generate.check_freshness(rows=(fake_row,))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("does not exist", problems[0])


class TestManifestAgainstRealRepo(unittest.TestCase):
    """These touch the real repo state (unlike TestFindSupersedingSibling
    above) -- they are the "does the manifest still describe reality"
    regression tests."""

    def test_no_stale_citations_in_committed_manifest(self):
        problems = generate.check_freshness()
        self.assertEqual(problems, [], "\n".join(problems))

    def test_every_target_table_row_is_covered(self):
        spec_path = REPO_ROOT / "spec" / "target-spec.md"
        text = spec_path.read_text()
        section = text.split("## Target table", 1)[1]
        section = section.split("\n## ", 1)[0]
        rows = []
        for line in section.splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not cells or cells[0] in ("Parameter", ""):
                continue
            if re.match(r"^-+$", cells[0].replace(" ", "")):
                continue
            rows.append(cells[0])
        self.assertTrue(rows, "failed to parse any rows out of spec/target-spec.md's Target table")

        manifest_rows = {row.spec_row for row in manifest.ROWS}
        missing = [r for r in rows if r not in manifest_rows]
        self.assertEqual(
            missing,
            [],
            f"spec/target-spec.md Target-table row(s) not covered by "
            f"sim/report/manifest.ROWS: {missing}",
        )

    def test_report_file_matches_generator_output(self):
        self.assertTrue(
            generate.REPORT_PATH.is_file(),
            f"{generate.REPORT_PATH} does not exist -- run "
            "`python3 sim/report/generate.py --write`",
        )
        committed = generate.REPORT_PATH.read_text()
        current = generate.render_report()
        self.assertEqual(
            committed,
            current,
            "docs/characterization-report.md is out of date -- run "
            "`python3 sim/report/generate.py --write` and commit the result",
        )

    def test_every_sim_citation_file_exists(self):
        for row in manifest.ROWS:
            for rel_path in row.sim_citations:
                self.assertTrue(
                    (REPO_ROOT / rel_path).is_file(), f"[{row.id}] missing citation {rel_path}"
                )
            for rel_path in row.layout_citations:
                self.assertTrue(
                    (REPO_ROOT / rel_path).is_file(),
                    f"[{row.id}] missing layout citation {rel_path}",
                )


if __name__ == "__main__":
    unittest.main()

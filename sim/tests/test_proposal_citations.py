"""Unit tests for docs/chipalooza/check_proposal_citations.py -- pure file
reads, no ngspice/PDK required (mirrors sim/tests/test_harness.py's PDK-free
unit-test convention; see sim/selftest.sh stage 1/4).

These live under sim/tests/ because that is this repo's only unittest root
(`npm run test:unit` discovers from there), not because the checker belongs to
the simulation harness -- it checks docs/chipalooza/challenge-4-proposal.md.

The load-bearing tests are the ones that reproduce the defect *shapes* the
checker exists to catch, each taken from a real after-the-fact correction in
the proposal document's own history:

  - a Section 4 spec row citing a layout flow only at a superseded record
    while that flow's `reports/LATEST` has moved on (PR #239/#242/#276/#282,
    and one instance still live in the document when this checker landed);
  - a citation naming `reports/LATEST` for a `sim/` campaign, whose pointer
    file is `records/LATEST` (PR #295/#300).

A checker that cannot fail on those two fixtures is a vacuous gate, so they
are asserted directly rather than only through the real document.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
CHIPALOOZA_DIR = REPO_ROOT / "docs" / "chipalooza"
sys.path.insert(0, str(CHIPALOOZA_DIR))

import check_proposal_citations as checker  # noqa: E402


class FixtureTree:
    """A throwaway repo-shaped tree the checker can be pointed at.

    The checker resolves relative references against the document's own
    directory and `LATEST` pointers against its module-level REPO_ROOT, so a
    fixture needs both: a `docs/chipalooza/` document and sibling
    `sim/`/`layout/` evidence trees.
    """

    def __init__(self, stack: unittest.TestCase):
        self._tmp = tempfile.TemporaryDirectory()
        stack.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "docs" / "chipalooza").mkdir(parents=True)
        original_root = checker.REPO_ROOT
        checker.REPO_ROOT = self.root
        stack.addCleanup(lambda: setattr(checker, "REPO_ROOT", original_root))

    def add_layout_record(self, block: str, stamp: str, *, latest: bool = False):
        report = self.root / "layout" / block / "reports" / stamp
        report.mkdir(parents=True, exist_ok=True)
        (report / "record.md").write_text("fixture record\n")
        if latest:
            (report.parent / "LATEST").write_text(stamp + "\n")

    def add_sim_record(self, campaign: str, stamp: str, *, latest: bool = False):
        records = self.root / "sim" / campaign / "records"
        records.mkdir(parents=True, exist_ok=True)
        (records / f"{stamp}.md").write_text("fixture record\n")
        if latest:
            (records / "LATEST").write_text(f"{stamp}.md\n")

    def document(self, body: str) -> Path:
        doc = self.root / "docs" / "chipalooza" / "fixture.md"
        doc.write_text(body)
        return doc

    def check(self, body: str) -> list[str]:
        return checker.check_document(self.document(body))


def spec_table(*rows: str) -> str:
    """A minimal Section 4 spec table wrapping the given verdict rows."""
    header = [
        "## 4. Target specification",
        "",
        "| Parameter | Target | Status | Verdict | Source (dated) |",
        "|---|---|---|---|---|",
    ]
    return "\n".join(header + list(rows) + ["", "## 5. Next section", ""])


class TestPathResolution(unittest.TestCase):
    def setUp(self):
        self.tree = FixtureTree(self)

    def test_broken_markdown_link_is_reported(self):
        misses = self.tree.check("See [the record](../../sim/nope/records/x.md).\n")
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("broken link target", misses[0])

    def test_resolvable_markdown_link_passes(self):
        self.tree.add_sim_record("enob-estimate", "20260906-173830-6f04f59")
        misses = self.tree.check(
            "See [the record]"
            "(../../sim/enob-estimate/records/20260906-173830-6f04f59.md).\n"
        )
        self.assertEqual(misses, [])

    def test_bare_backticked_path_into_our_tree_is_checked(self):
        misses = self.tree.check("Cited as `layout/sar-sequencer/reports/gone/x.md`.\n")
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("does not exist", misses[0])

    def test_upstream_path_outside_our_top_level_dirs_is_left_alone(self):
        # klayout-tools' own source path -- not ours to resolve.
        self.assertEqual(self.tree.check("`src/klayout_tools/lvs.py` changed.\n"), [])

    def test_glob_pattern_is_not_treated_as_a_path(self):
        self.assertEqual(
            self.tree.check("audited every `layout/*/reports/LATEST` pointer\n"), []
        )

    def test_path_wrapped_across_lines_is_rejoined_before_resolving(self):
        self.tree.add_sim_record("vcm-drive-budget", "20260908-115336-f3e2914")
        body = "see `sim/vcm-drive-\n   budget/records/20260908-115336-f3e2914.md` for\n"
        self.assertEqual(self.tree.check(body), [])

    def test_anchor_only_and_http_links_are_ignored(self):
        body = "[a](#section-4) and [b](https://example.invalid/x.md)\n"
        self.assertEqual(self.tree.check(body), [])


class TestSpecTableFreshness(unittest.TestCase):
    """The PR #239/#242/#276/#282 defect shape."""

    def setUp(self):
        self.tree = FixtureTree(self)
        self.tree.add_layout_record("sar-adc-top", "20260906-101939-1250ff4")
        self.tree.add_layout_record("sar-adc-top", "20260907-110058-a546200", latest=True)

    def _row(self, *stamps: str) -> str:
        cites = " ".join(
            f"[`layout/sar-adc-top/reports/{s}/record.md`]"
            f"(../../layout/sar-adc-top/reports/{s}/record.md)"
            for s in stamps
        )
        return f"| Area | max | Not a spec row yet | informational | {cites} |"

    def test_row_citing_only_a_superseded_record_is_reported(self):
        misses = self.tree.check(spec_table(self._row("20260906-101939-1250ff4")))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn('spec row "Area"', misses[0])
        self.assertIn("20260907-110058-a546200", misses[0])

    def test_row_citing_the_current_record_passes(self):
        self.assertEqual(
            self.tree.check(spec_table(self._row("20260907-110058-a546200"))), []
        )

    def test_row_may_also_keep_the_supersession_trail_visible(self):
        misses = self.tree.check(
            spec_table(
                self._row("20260907-110058-a546200", "20260906-101939-1250ff4")
            )
        )
        self.assertEqual(misses, [])

    def test_flow_with_no_latest_pointer_is_skipped(self):
        self.tree.add_sim_record("enob-estimate", "20260906-082749-7724af3")
        row = (
            "| ENOB | > 7.5 bit | DRAFT | informational | "
            "[`sim/enob-estimate/records/20260906-082749-7724af3.md`]"
            "(../../sim/enob-estimate/records/20260906-082749-7724af3.md) |"
        )
        self.assertEqual(self.tree.check(spec_table(row)), [])

    def test_section_7_prose_may_cite_a_superseded_record(self):
        # Section 7 deliberately narrates supersession trails paragraph by
        # paragraph; only Section 4's graded rows are held to current evidence.
        body = (
            "## 7. Open items\n\n"
            "Both citations were re-pointed to "
            "[`layout/sar-adc-top/reports/20260906-101939-1250ff4/record.md`]"
            "(../../layout/sar-adc-top/reports/20260906-101939-1250ff4/record.md)"
            " then.\n"
        )
        self.assertEqual(self.tree.check(body), [])


class TestPointerClaims(unittest.TestCase):
    def setUp(self):
        self.tree = FixtureTree(self)
        self.tree.add_layout_record("cdac-array", "20260905-220338-9fb9b04")
        self.tree.add_layout_record("cdac-array", "20260906-020815-38cdbd3", latest=True)
        self.tree.add_sim_record("full-conversion-transient", "20260912-002315-9aaf1ca",
                                 latest=True)

    def test_attached_claim_naming_a_superseded_record_is_reported(self):
        body = (
            "cited as "
            "[`layout/cdac-array/reports/20260905-220338-9fb9b04/record.md`]"
            "(../../layout/cdac-array/reports/20260905-220338-9fb9b04/record.md)"
            " (current `reports/LATEST`)\n"
        )
        misses = self.tree.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("resolves to `20260906-020815-38cdbd3`", misses[0])

    def test_attached_claim_naming_the_current_record_passes(self):
        body = (
            "cited as "
            "[`layout/cdac-array/reports/20260906-020815-38cdbd3/record.md`]"
            "(../../layout/cdac-array/reports/20260906-020815-38cdbd3/record.md)"
            " (current `reports/LATEST`)\n"
        )
        self.assertEqual(self.tree.check(body), [])

    def test_sim_campaign_claimed_as_reports_latest_is_reported(self):
        """The PR #295/#300 defect shape: `sim/` records under `records/`."""
        body = (
            "which is also what "
            "[`sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md`]"
            "(../../sim/full-conversion-transient/records/"
            "20260912-002315-9aaf1ca.md)"
            " (current `reports/LATEST`) resolves to\n"
        )
        misses = self.tree.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("`records/LATEST`", misses[0])

    def test_sim_campaign_claimed_as_records_latest_passes(self):
        body = (
            "which is also what "
            "[`sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md`]"
            "(../../sim/full-conversion-transient/records/"
            "20260912-002315-9aaf1ca.md)"
            " (current `records/LATEST`) resolves to\n"
        )
        self.assertEqual(self.tree.check(body), [])

    def test_prose_discussion_of_a_pointer_is_not_an_attached_claim(self):
        # The document's own style: narrating a correction it already made.
        body = (
            "left the Area row still citing the superseded "
            "[`layout/cdac-array/reports/20260905-220338-9fb9b04/record.md`]"
            "(../../layout/cdac-array/reports/20260905-220338-9fb9b04/record.md)"
            " -- that citation is now corrected to the current "
            "`reports/LATEST` artefact.\n"
        )
        self.assertEqual(self.tree.check(body), [])


class TestAgainstTheRealProposal(unittest.TestCase):
    def test_committed_proposal_document_passes(self):
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        self.assertTrue(doc.is_file(), doc)
        self.assertEqual(checker.check_document(doc), [])

    def test_section_4_spec_table_is_actually_found(self):
        """Guard against the scoping silently matching zero rows."""
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        rows = checker.spec_table_rows(doc.read_text())
        self.assertGreaterEqual(len(rows), 11, "Section 4's spec table went unparsed")
        parameters = [row.strip("|").split("|")[0].strip() for _, row in rows]
        self.assertIn("Resolution `N`", parameters)
        self.assertIn("Sample rate", parameters)


if __name__ == "__main__":
    unittest.main()

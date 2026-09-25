"""Unit tests for layout/bin/check_drc_evidence.py -- pure file reads, no
`klt`/PDK required (same PDK-free unit-test convention as
sim/tests/test_proposal_citations.py and sim/tests/test_harness.py).

These live under sim/tests/ because that is this repo's only unittest root
(`npm run test:unit` discovers from there), not because the checker belongs to
the simulation harness -- it checks the `layout/` evidence tree.

The load-bearing tests reproduce the defect *shape* the checker exists to
catch, taken from a real upstream defect rather than invented:
klayout-tools#1941 (fixed by klayout-tools#1951, merged 2026-09-16, not in any
release as of this commit) showed `klt drc --engine klayout` reporting
`status: "clean"` on a PDK-native deck that aborted part-way through -- a
report file covering only the rules that ran before the abort, presented as a
clean verdict. Every DRC-clean claim in this repo's `layout/` records, and
every verdict `docs/chipalooza/challenge-4-proposal.md` grades on them, is
exposed to that shape unless something checks which path produced them.

A checker that cannot fail on those fixtures is a vacuous gate, so each is
asserted directly rather than only through the real evidence tree.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
LAYOUT_BIN = REPO_ROOT / "layout" / "bin"
sys.path.insert(0, str(LAYOUT_BIN))

import check_drc_evidence as checker  # noqa: E402

CURATED_CLEAN = {
    "schema_version": 1,
    "deck": "sky130",
    "status": "clean",
    "violation_count": 0,
    "coverage": {"layers_checked": ["64/20", "67/20"]},
    "provenance": {"klt_version": "0.5.0"},
}


class FixtureTree:
    """A throwaway `layout/`-shaped tree the checker can be pointed at."""

    def __init__(self, stack: unittest.TestCase):
        self._tmp = tempfile.TemporaryDirectory()
        stack.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        original_root = checker.REPO_ROOT
        checker.REPO_ROOT = self.root
        stack.addCleanup(lambda: setattr(checker, "REPO_ROOT", original_root))

    def add_report(
        self,
        flow: str,
        stamp: str,
        payloads: dict[str, object],
        *,
        latest: bool = True,
    ) -> Path:
        report = self.root / "layout" / flow / "reports" / stamp
        report.mkdir(parents=True, exist_ok=True)
        for name, payload in payloads.items():
            (report / name).write_text(json.dumps(payload, indent=1))
        if latest:
            (report.parent / "LATEST").write_text(stamp + "\n")
        return report


def _dup(**overrides) -> dict:
    payload = json.loads(json.dumps(CURATED_CLEAN))
    payload.update(overrides)
    return payload


class CheckDrcEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.tree = FixtureTree(self)

    def test_curated_deck_clean_report_passes(self):
        self.tree.add_report("alpha", "20260916-120000-abc1234", {"drc.json": CURATED_CLEAN})
        self.assertEqual(checker.check_tree(), [])

    def test_engine_klayout_deck_file_run_fails(self):
        """The klayout-tools#1941 shape: a `--engine klayout --deck-file` run.

        This is exactly the payload committed at
        layout/sampling-frontend-wells/reports/20260825-231908-3e02f7e/
        drc.wells.json (klt 0.3.0) -- superseded there, and therefore out of
        this gate's scope, but the shape must fail when it is a flow's current
        evidence.
        """
        self.tree.add_report(
            "alpha",
            "20260916-120000-abc1234",
            {
                "drc.wells.json": _dup(
                    deck="nwell_isolation.drc",
                    engine="klayout",
                    coverage={"layers_checked": []},
                )
            },
        )
        misses = checker.check_tree()
        # That real payload trips two of the three checks at once: the
        # provenance check and the vacuous-clean check. Both are reported, so a
        # reader of the failure sees the whole reason rather than the first one.
        self.assertEqual(len(misses), 2, misses)
        self.assertIn("--engine klayout", misses[0])
        self.assertIn("no layer", misses[1])

    def test_tolerated_deck_errors_fail(self):
        """`engine_deck_errors` is klayout-tools#1951's `--allow-deck-errors`
        marker: the run knowingly accepted a partially-executed deck."""
        self.tree.add_report(
            "alpha",
            "20260916-120000-abc1234",
            {"drc.json": _dup(engine_deck_errors={"exit_status": 1, "error_lines": ["ERROR: x"]})},
        )
        misses = checker.check_tree()
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("engine_deck_errors", misses[0])

    def test_clean_verdict_over_zero_checked_layers_fails(self):
        """A clean verdict that checked no layer at all is vacuous."""
        self.tree.add_report(
            "alpha",
            "20260916-120000-abc1234",
            {"drc.json": _dup(coverage={"layers_checked": []})},
        )
        misses = checker.check_tree()
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("no layer", misses[0])

    def test_violations_verdict_needs_no_layer_coverage(self):
        """Only a *clean* verdict is vacuous without coverage -- a violation
        report is self-evidently the product of a deck that ran."""
        self.tree.add_report(
            "alpha",
            "20260916-120000-abc1234",
            {
                "drc.json": CURATED_CLEAN,
                "drc.fixture.json": _dup(
                    status="violations",
                    violation_count=3,
                    coverage={"layers_checked": []},
                ),
            },
        )
        self.assertEqual(checker.check_tree(), [])

    def test_superseded_report_is_out_of_scope(self):
        """`layout/` evidence is append-only: a superseded record documents
        history and is not what any verdict stands on."""
        self.tree.add_report(
            "alpha",
            "20260825-120000-old1234",
            {"drc.wells.json": _dup(deck="nwell_isolation.drc", engine="klayout")},
            latest=False,
        )
        self.tree.add_report("alpha", "20260916-120000-abc1234", {"drc.json": CURATED_CLEAN})
        self.assertEqual(checker.check_tree(), [])

    def test_nested_payload_map_is_traversed(self):
        """`drc.blocks.json` is a map of per-block payloads, not one payload."""
        self.tree.add_report(
            "alpha",
            "20260916-120000-abc1234",
            {
                "drc.json": CURATED_CLEAN,
                "drc.blocks.json": {
                    "good": CURATED_CLEAN,
                    "bad": _dup(coverage={"layers_checked": []}),
                },
            },
        )
        misses = checker.check_tree()
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("drc.blocks.json", misses[0])

    def test_empty_tree_fails_rather_than_passing_vacuously(self):
        """A glob that matches nothing must be a failure, not a silent pass."""
        misses = checker.check_tree()
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("no DRC", misses[0])

    def test_missing_current_report_directory_fails(self):
        """A LATEST pointer naming a directory that is not committed."""
        report = self.tree.add_report(
            "alpha", "20260916-120000-abc1234", {"drc.json": CURATED_CLEAN}
        )
        (report / "drc.json").unlink()
        misses = checker.check_tree()
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("no DRC", misses[0])


class RealEvidenceTreeTest(unittest.TestCase):
    """The gate must be non-vacuous on this repo's own evidence tree."""

    def test_repo_evidence_passes(self):
        self.assertEqual(checker.check_tree(), [])

    def test_repo_evidence_is_actually_inspected(self):
        payloads = list(checker.current_payloads())
        self.assertGreaterEqual(len(payloads), 8, "expected every layout flow's current report")
        flows = {flow for flow, _path, _key, _payload in payloads}
        self.assertIn("sar-adc-top", flows)


if __name__ == "__main__":
    unittest.main()

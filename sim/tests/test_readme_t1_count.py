"""Guard the T1 met-count transcribed into README.md (issue #911).

The README carries a hand-written copy of the verdict of record,
``signoff/t1-report.json``'s ``t1_met_count`` / ``t1_item_count``, and nothing
checked it: it said **6 of 22 rows met** while the report graded 13 of 22.
``docs/t1-gap.md`` deleted its own hand-maintained item table for exactly this
reason — a hand-kept count goes stale the moment either the report or the tier
definition moves — and ``npm run check:ci`` runs no markdown text checker, so
this module is the mechanical gate.

The report fields are read **directly**, never recomputed: ``items[]`` holds 25
entries (the 22 T1 rows plus three unpartitioned T2/T3/T4 placeholders), so
counting ``items[]`` would yield 13/25 and 12 unmet instead of the published
13/22 and 9 unmet.

Per this repo's test convention the gate is proven to **bite on synthetic
fixtures**, not merely to agree with the live tree: a checker that cannot fail
on a mismatched or missing count is a vacuous gate that keeps passing if its
detection logic is gutted.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
README_PATH = REPO_ROOT / "README.md"
REPORT_PATH = REPO_ROOT / "signoff" / "t1-report.json"

COUNT_PATTERN = re.compile(r"\*\*(\d+) of (\d+) rows met\*\*")


def extract_readme_count(readme_text: str) -> tuple[int, int]:
    """Return the ``(met, items)`` count stated in ``readme_text``.

    Fails loudly when the count pattern is absent or ambiguous: a regex that
    silently matches nothing would leave the transcription unguarded.
    """
    matches = COUNT_PATTERN.findall(readme_text)
    if len(matches) == 0:
        raise AssertionError(
            "README states no '**<met> of <items> rows met**' count; the "
            "transcription of signoff/t1-report.json is unguarded"
        )
    if len(matches) > 1:
        raise AssertionError(
            f"README states {len(matches)} 'rows met' counts; which one is "
            "the T1 verdict is ambiguous"
        )
    met, items = (int(group) for group in matches[0])
    return met, items


def assert_count_matches_report(readme_text: str, report: dict) -> None:
    """Assert the README count equals the report's verdict fields."""
    met, items = extract_readme_count(readme_text)
    expected_met = report["t1_met_count"]
    expected_items = report["t1_item_count"]
    if (met, items) != (expected_met, expected_items):
        raise AssertionError(
            f"README says '{met} of {items} rows met' but "
            f"signoff/t1-report.json grades {expected_met} of "
            f"{expected_items}: the README's hand-kept count is stale"
        )


class TestReadmeT1Count(unittest.TestCase):
    def test_real_tree_count_matches_report(self) -> None:
        report = json.loads(REPORT_PATH.read_text())
        readme_text = README_PATH.read_text()
        assert_count_matches_report(readme_text, report)

    def test_agreeing_fixture_passes(self) -> None:
        text = "Current state: **13 of 22 rows met**, tier `null`."
        report = {"t1_met_count": 13, "t1_item_count": 22}
        self.assertEqual(extract_readme_count(text), (13, 22))
        assert_count_matches_report(text, report)

    def test_stale_fixture_fails(self) -> None:
        text = "Current state: **6 of 22 rows met**, tier `null`."
        report = {"t1_met_count": 13, "t1_item_count": 22}
        with self.assertRaises(AssertionError):
            assert_count_matches_report(text, report)

    def test_missing_pattern_fails(self) -> None:
        text = "Current state: thirteen of twenty-two rows met, tier `null`."
        with self.assertRaises(AssertionError):
            extract_readme_count(text)


if __name__ == "__main__":
    unittest.main()

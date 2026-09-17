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

import json
import re
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

    def add_layout_record(
        self,
        block: str,
        stamp: str,
        *,
        latest: bool = False,
        drc: dict | None = None,
        lvs: dict | None = None,
    ):
        report = self.root / "layout" / block / "reports" / stamp
        report.mkdir(parents=True, exist_ok=True)
        (report / "record.md").write_text("fixture record\n")
        # `klt`'s own machine-readable verdicts, which check 9 reads out.
        # Written only when asked for: a record without them is the "nothing
        # to compare against" condition check 9 reports separately.
        if drc is not None:
            (report / "drc.json").write_text(json.dumps(drc))
        if lvs is not None:
            (report / "lvs.json").write_text(json.dumps(lvs))
        if latest:
            (report.parent / "LATEST").write_text(stamp + "\n")

    def add_sim_record(
        self,
        campaign: str,
        stamp: str,
        *,
        latest: bool = False,
        power: dict[str, float] | None = None,
    ):
        records = self.root / "sim" / campaign / "records"
        records.mkdir(parents=True, exist_ok=True)
        body = "fixture record\n"
        if power is not None:
            # The per-corner Power table check 12 reads, in the shape
            # sim/full-conversion-transient/run_conversion.py writes it: the
            # corner id backticked in the first column, the total power in the
            # last. A fixture that wrote only the total would pass while the
            # real multi-column table went unparsed.
            body += "\n## Power (informational)\n\n"
            body += "| corner-id | I(VDD) (uA) | total power (uW) |\n|---|---|---|\n"
            for corner, total in power.items():
                body += f"| `{corner}` | 2.097 | {total:.3f} |\n"
            body += "\n## Findings\n\n- fixture\n"
        (records / f"{stamp}.md").write_text(body)
        if latest:
            (records / "LATEST").write_text(f"{stamp}.md\n")

    def add_coverage_index(self, *rows: dict):
        """A `sim/spec-coverage.json` in the shape check 11 reads.

        Each row is `{"parameter", "claim_class", "experiments"}`; the nested
        bench shape the real index uses is built here so a test states only
        what it is about.
        """
        sim = self.root / "sim"
        sim.mkdir(parents=True, exist_ok=True)
        (sim / "spec-coverage.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "rows": [
                        {
                            "parameter": row["parameter"],
                            "claim_class": row["claim_class"],
                            "benches": [
                                {"experiment": experiment}
                                for experiment in row.get("experiments", ())
                            ],
                        }
                        for row in rows
                    ],
                }
            )
        )

    def add_top_netlist(self, *ports: str):
        """A `design/sar_adc_top.spice` with the given top-level port list.

        Written in the shape xschem really emits for the *top* cell -- the
        `.subckt` line commented out, since the top level is netlisted flat.
        A fixture that wrote a bare `.subckt` would pass while the real file
        shape went unparsed.
        """
        design = self.root / "design"
        design.mkdir(parents=True, exist_ok=True)
        (design / "sar_adc_top.spice").write_text(
            "* fixture netlist\n**.subckt sar_adc_top " + " ".join(ports) + "\n"
        )

    def add_spec_table(self, *rows: str):
        """A `spec/target-spec.md` with the Target table check 7 reads."""
        spec = self.root / "spec"
        spec.mkdir(parents=True, exist_ok=True)
        body = "\n".join(
            [
                "# fixture spec",
                "",
                "## Target table",
                "",
                "| Parameter | Target | Status | Carried from / note |",
                "|---|---|---|---|",
                *rows,
                "",
                "## Non-goals",
                "",
                "| Parameter | Target | Status | note |",
                "|---|---|---|---|",
                "| Decoy | `≤ 99 kV` | **RATIFIED** | not the Target table |",
                "",
            ]
        )
        (spec / "target-spec.md").write_text(body)

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

    def test_the_connector_claim_naming_a_superseded_record_is_reported(self):
        """The "(the current `reports/LATEST`)" phrasing -- §4's own wording.

        `_unwrap_backticked` strips the connector before it is matched, so a
        connector pattern anchored on trailing whitespace after "the" (e.g.
        `(?:the\\s+)?$`) silently never matches and the whole check goes
        vacuous for this phrasing, which the real document uses. Asserted
        separately from the bare "(current ...)" form above so the branch
        cannot go dead again.
        """
        body = (
            "folded into one record, "
            "[`layout/cdac-array/reports/20260905-220338-9fb9b04/record.md`]"
            "(../../layout/cdac-array/reports/20260905-220338-9fb9b04/record.md)"
            "\n(the current `reports/LATEST`; its `compose.json` is unchanged)\n"
        )
        misses = self.tree.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("resolves to `20260906-020815-38cdbd3`", misses[0])

    def test_the_connector_claim_naming_the_current_record_passes(self):
        body = (
            "folded into one record, "
            "[`layout/cdac-array/reports/20260906-020815-38cdbd3/record.md`]"
            "(../../layout/cdac-array/reports/20260906-020815-38cdbd3/record.md)"
            "\n(the current `reports/LATEST`; its `compose.json` is unchanged)\n"
        )
        self.assertEqual(self.tree.check(body), [])

    def test_record_and_the_connectors_combined_are_reported(self):
        """Both connectors at once -- the same dead-branch shape as above.

        `record:` on its own was always reachable; `record:` *followed by*
        "the" was not, for the identical reason. This document does not use
        the combination today, but the connector pattern advertises it, so it
        is asserted rather than left as an untested claim.
        """
        body = (
            "see record: "
            "`layout/cdac-array/reports/20260905-220338-9fb9b04/record.md`"
            " record: the current `reports/LATEST`\n"
        )
        misses = self.tree.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("resolves to `20260906-020815-38cdbd3`", misses[0])

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


class TestPointerClaimCensus(unittest.TestCase):
    """Check 6: the document's stated coverage census must be the real one.

    The defect shape here is one level up from a stale citation: the document
    (and, before this check, `.github/workflows/ci.yml` and the checker's own
    docstring) stated in prose how many of its pointer claims checks 4/5 cover.
    PR #312 added two claims of the skipped kind and all three statements
    silently became wrong -- a volatile fact nothing re-derived.
    """

    def setUp(self):
        self.tree = FixtureTree(self)
        self.tree.add_layout_record("cdac-array", "20260906-020815-38cdbd3", latest=True)

    def _body(self, census: str) -> str:
        # One attached claim (checked), one trailing-stamp claim, one
        # narration claim -- i.e. total=3, attached=1, skipped=2,
        # trailing_stamp=1, narration=1.
        return (
            "cited as "
            "[`layout/cdac-array/reports/20260906-020815-38cdbd3/record.md`]"
            "(../../layout/cdac-array/reports/20260906-020815-38cdbd3/record.md)"
            " (current `reports/LATEST`)\n\n"
            "re-pointed onto the current `reports/LATEST`, "
            "`20260906-020815-38cdbd3`\n\n"
            "that citation is now corrected to the current `reports/LATEST`\n\n"
            + census
            + "\n"
        )

    def test_census_of_a_known_document_is_computed_as_documented(self):
        census = checker.pointer_claim_census(self._body(""))
        self.assertEqual(
            {k: v for k, v in census.items() if k != "window"},
            {
                "total": 3,
                "attached": 1,
                "skipped": 2,
                "trailing_stamp": 1,
                "narration": 1,
            },
            census,
        )

    def _census_sentence(self, total, attached, skipped, trailing, narration):
        return (
            f'of the **{total}** "current `…/LATEST`" phrases in this '
            f"document, **{attached}** are attached and therefore checked; of "
            f"the **{skipped}** skipped, **{trailing}** name a record stamp "
            f"within {checker.TRAILING_STAMP_WINDOW} characters after the "
            f"phrase, and **{narration}** name none at all."
        )

    def test_a_truthful_census_passes(self):
        body = self._body(self._census_sentence(3, 1, 2, 1, 1))
        self.assertEqual(self.tree.check(body), [])

    def test_a_drifted_census_is_reported_field_by_field(self):
        # The PR #312 shape: the document grew, the stated census did not.
        body = self._body(self._census_sentence(2, 1, 1, 0, 1))
        misses = self.tree.check(body)
        self.assertEqual(len(misses), 3, misses)
        self.assertTrue(any("total=2" in miss and "total=3" in miss for miss in misses))
        self.assertTrue(any("skipped=1" in miss and "skipped=2" in miss for miss in misses))

    def test_a_census_stating_a_window_the_checker_does_not_apply_is_reported(self):
        body = self._body(
            self._census_sentence(3, 1, 2, 1, 1).replace(
                f"within {checker.TRAILING_STAMP_WINDOW} characters", "within 40 characters"
            )
        )
        misses = self.tree.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("window=40", misses[0])

    def test_a_document_stating_no_census_is_not_failed_for_it(self):
        # Fixtures (and any future chipalooza doc) need not carry a census.
        self.assertEqual(self.tree.check(self._body("")), [])


class TestSpecRowParity(unittest.TestCase):
    """Check 7: Section 4 restates every ratified spec row, unrelaxed.

    The defect shape is the one the repo's standing rule names -- "agents do
    not relax a spec line to make a result pass" (CLAUDE.md) -- plus its
    cheaper cousin, dropping the row from the proposal entirely. Neither had
    any mechanical guard: both tables were compared by hand every pass.
    """

    def setUp(self):
        self.tree = FixtureTree(self)

    def test_spec_row_absent_from_section_4_is_reported(self):
        self.tree.add_spec_table(
            "| ENOB | > 7.5 bit | DRAFT | note |",
            "| Power | provisional | DRAFT | note |",
        )
        misses = self.tree.check(
            spec_table("| ENOB | > 7.5 bit | DRAFT | **MET** — x | schematic |")
        )
        self.assertEqual(len(misses), 1, misses)
        self.assertIn('spec row "Power"', misses[0])
        self.assertIn("no Section 4 row", misses[0])

    def test_relaxed_bound_is_reported_and_names_the_bound(self):
        self.tree.add_spec_table("| INL / DNL | `≤ ±2.0 LSB` | DRAFT | note |")
        misses = self.tree.check(
            spec_table("| INL / DNL | `≤ ±3.0 LSB` | DRAFT | **MET** — x | schematic |")
        )
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("`≤±2.0`", misses[0])
        self.assertIn("may not be relaxed", misses[0])

    def test_softened_comparator_alone_is_reported(self):
        """`≥ 7.5` is not `> 7.5` -- the subtlest relaxation shape."""
        self.tree.add_spec_table("| ENOB | > 7.5 bit | DRAFT | note |")
        misses = self.tree.check(
            spec_table("| ENOB | ≥ 7.5 bit | DRAFT | **MET** — x | schematic |")
        )
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("`>7.5`", misses[0])

    def test_section_4_may_also_state_the_superseded_bound(self):
        """The document's style is to keep the revision trail visible."""
        self.tree.add_spec_table("| ENOB | > 7.5 bit, stretch > 8.0 | DRAFT | note |")
        body = spec_table(
            "| ENOB | > 7.5 bit, stretch > 8.0 (DR-007 candidate, was > 9.0/9.5) "
            "| DRAFT | **MET** — x | schematic |"
        )
        self.assertEqual(self.tree.check(body), [])

    def test_status_drift_is_reported(self):
        """DR-007 ratifying upstream must fail this document, not pass it."""
        self.tree.add_spec_table("| ENOB | > 7.5 bit | **RATIFIED** (DR-007) | note |")
        misses = self.tree.check(
            spec_table(
                "| ENOB | > 7.5 bit | DRAFT (target value, not ratified) "
                "| **MET** — x | schematic |"
            )
        )
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("`RATIFIED`", misses[0])
        self.assertIn("`DRAFT`", misses[0])

    def test_parameter_names_compare_past_backticks_and_bold(self):
        self.tree.add_spec_table("| Resolution `N` | 10 bit | **RATIFIED** | note |")
        body = spec_table(
            "| **Resolution `N`** | 10 bit | **RATIFIED** | **MET** — x | schematic |"
        )
        self.assertEqual(self.tree.check(body), [])

    def test_issue_and_record_references_are_not_read_as_bounds(self):
        self.tree.add_spec_table("| Power | provisional (#28) | DRAFT | note |")
        body = spec_table(
            "| Power | provisional | DRAFT | **BLOCKED** — see §7 | schematic |"
        )
        self.assertEqual(self.tree.check(body), [])

    def test_check_is_inert_without_a_spec_target_table(self):
        # No spec/target-spec.md in the fixture tree at all.
        body = spec_table("| Whatever | 1 | DRAFT | **MET** — x | schematic |")
        self.assertEqual(self.tree.check(body), [])


def verdict_preamble(*kinds: str) -> str:
    """A Section 4 preamble defining the given verdict kinds."""
    bullets = "\n".join(f"- **{kind}** — definition of {kind}." for kind in kinds)
    return "## 4. Target specification\n\nThe verdict column states:\n" + bullets + "\n\n"


def graded_table(preamble: str, *rows: str) -> str:
    """`verdict_preamble` output followed by a Section 4 table."""
    return preamble + spec_table(*rows).split("\n", 2)[2]


class TestVerdictVocabulary(unittest.TestCase):
    """Check 8: every row opens with a verdict kind the preamble defines."""

    def setUp(self):
        self.tree = FixtureTree(self)

    def test_row_opening_with_an_undefined_kind_is_reported(self):
        """The live defect: Architecture's verdict read "Implemented as described"."""
        body = graded_table(
            verdict_preamble("MET"),
            "| A | 1 mV | RATIFIED | **MET** — passes | schematic |",
            "| Architecture | topology | DRAFT | Implemented as described | schematic |",
        )
        misses = self.tree.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn('row "Architecture"', misses[0])
        self.assertIn("not one of the kinds", misses[0])

    def test_defined_kind_no_row_uses_is_reported(self):
        body = graded_table(
            verdict_preamble("MET", "DRAFT / not ratified"),
            "| Architecture | topology | DRAFT | **MET** — implemented | schematic |",
        )
        misses = self.tree.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn('"DRAFT / not ratified" that no row uses', misses[0])

    def test_every_kind_defined_and_used_passes(self):
        body = graded_table(
            verdict_preamble("MET", "UNMET", "Informational only"),
            "| A | topology | DRAFT | **MET** — implemented | schematic |",
            "| B | 1 mV | RATIFIED | **UNMET** — falls short at `ss` | schematic |",
            "| C | 2 mV | DRAFT | **Informational only**: no ratified line | schematic |",
        )
        self.assertEqual(self.tree.check(body), [])

    def test_longest_kind_wins_over_its_own_prefix(self):
        """`UNMET` must not be graded as `MET`, nor the reverse."""
        body = graded_table(
            verdict_preamble("MET", "UNMET"),
            "| A | 1 mV | RATIFIED | **MET** — passes | schematic |",
            "| B | 2 mV | RATIFIED | **UNMET** — falls short | schematic |",
        )
        self.assertEqual(self.tree.check(body), [])

    def test_kind_opening_a_longer_bold_span_still_counts(self):
        """§4's Sample rate row bolds a whole sentence, not just the kind."""
        body = graded_table(
            verdict_preamble("UNMEASURED"),
            "| A | 1 MS/s | DRAFT | **UNMEASURED as an end-to-end figure** — see §7 "
            "| schematic |",
        )
        self.assertEqual(self.tree.check(body), [])

    def test_check_is_inert_without_a_definition_list(self):
        body = spec_table("| A | 1 mV | DRAFT | anything at all | schematic |")
        self.assertEqual(self.tree.check(body), [])


def lvs_json(
    status: str = "mismatch",
    mismatch_count: int = 98,
    error_count: int = 97,
    categories: dict | None = None,
    **counts: tuple[int, int, int],
) -> dict:
    """A `klt lvs` verdict file in the shape check 9 reads."""
    shaped = {
        kind: dict(zip(("layout", "reference", "matched"), values))
        for kind, values in counts.items()
    }
    return {
        "status": status,
        "mismatch_count": mismatch_count,
        "error_count": error_count,
        "category_counts": {"device.unmatched": 75} if categories is None else categories,
        "counts": shaped,
    }


class TestSignoffReadout(unittest.TestCase):
    """Check 9: a stated DRC/LVS readout must be the record's own numbers.

    The defect shape is one check 3 cannot see: a flow re-runs, the row's
    *citation* is dutifully re-pointed at the new record (check 3 forces
    that), and every figure quoted out of the old one is left behind. That
    really happened to this document's sign-off-bar numbers, repeatedly --
    98 -> 128 -> 124 -> 98 across successive `klt` builds -- with only a
    human re-read carrying them forward each time.
    """

    STAMP = "20260915-234004-76f48b9"

    def setUp(self):
        self.tree = FixtureTree(self)
        self.tree.add_layout_record(
            "sar-adc-top",
            self.STAMP,
            latest=True,
            drc={"status": "clean", "violation_count": 0},
            lvs=lvs_json(
                devices=(869, 869, 794), nets=(444, 446, 412), pins=(19, 19, 19)
            ),
        )

    def _sentence(self, **overrides) -> str:
        fields = {
            "drc_status": "clean",
            "violation_count": 0,
            "lvs_status": "mismatch",
            "mismatch_count": 98,
            "error_count": 97,
            "devices": (869, 869, 794),
            "nets": (444, 446, 412),
            "pins": (19, 19, 19),
            "tail": "by category `device.unmatched: 75`",
        }
        fields.update(overrides)
        return (
            "on the record `layout/sar-adc-top/reports/LATEST` resolves to, "
            f"`klt drc` reports status **{fields['drc_status']}** with "
            f"**{fields['violation_count']}** violations, and `klt lvs` reports "
            f"status **{fields['lvs_status']}** with **{fields['mismatch_count']}** "
            f"mismatches and **{fields['error_count']}** errors; devices "
            f"**{fields['devices'][0]}** layout / **{fields['devices'][1]}** "
            f"reference / **{fields['devices'][2]}** matched; nets "
            f"**{fields['nets'][0]}** / **{fields['nets'][1]}** / "
            f"**{fields['nets'][2]}** matched; pins **{fields['pins'][0]}** / "
            f"**{fields['pins'][1]}** / **{fields['pins'][2]}** matched; "
            f"{fields['tail']}.\n"
        )

    def test_a_truthful_readout_passes(self):
        self.assertEqual(self.tree.check(self._sentence()), [])

    def test_a_stale_mismatch_count_is_reported(self):
        """The 124 -> 98 move, with the citation already re-pointed."""
        misses = self.tree.check(self._sentence(mismatch_count=124))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("mismatch_count=124", misses[0])
        self.assertIn("mismatch_count=98", misses[0])
        self.assertIn("--stats", misses[0])

    def test_each_drifted_field_is_reported_separately(self):
        misses = self.tree.check(
            self._sentence(violation_count=3, devices=(869, 869, 795))
        )
        self.assertEqual(len(misses), 2, misses)
        self.assertTrue(any("violation_count=3" in miss for miss in misses))
        self.assertTrue(any("devices_matched=795" in miss for miss in misses))

    def test_a_status_word_that_drifted_is_reported(self):
        """The most consequential drift: `mismatch` silently read as `match`."""
        misses = self.tree.check(self._sentence(lvs_status="match"))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("lvs_status=match", misses[0])
        self.assertIn("lvs_status=mismatch", misses[0])

    def test_a_category_the_readout_omits_is_reported(self):
        self.tree.add_layout_record(
            "sar-adc-top",
            self.STAMP,
            latest=True,
            drc={"status": "clean", "violation_count": 0},
            lvs=lvs_json(
                categories={"device.unmatched": 75, "net.merged": 12},
                devices=(869, 869, 794),
                nets=(444, 446, 412),
                pins=(19, 19, 19),
            ),
        )
        misses = self.tree.check(self._sentence())
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("`net.merged` as None", misses[0])
        self.assertIn("reports 12", misses[0])

    def test_a_category_the_readout_invents_is_reported(self):
        misses = self.tree.check(
            self._sentence(
                tail="by category `device.unmatched: 75`, `topology.flattened: 1`"
            )
        )
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("`topology.flattened` as 1", misses[0])
        self.assertIn("reports None", misses[0])

    def test_a_clean_flow_states_no_categories(self):
        self.tree.add_layout_record(
            "seln-inverters",
            "20260906-002022-a36e06f",
            latest=True,
            drc={"status": "clean", "violation_count": 0},
            lvs=lvs_json(
                status="match",
                mismatch_count=0,
                error_count=0,
                categories={},
                devices=(18, 18, 18),
                nets=(20, 20, 20),
                pins=(20, 20, 20),
            ),
        )
        body = (
            "on the record `layout/seln-inverters/reports/LATEST` resolves to, "
            "`klt drc` reports status **clean** with **0** violations, and "
            "`klt lvs` reports status **match** with **0** mismatches and **0** "
            "errors; devices **18** layout / **18** reference / **18** matched; "
            "nets **20** / **20** / **20** matched; pins **20** / **20** / **20** "
            "matched; no mismatch categories.\n"
        )
        self.assertEqual(self.tree.check(body), [])

    def test_a_blockquoted_readout_is_still_matched(self):
        """The document sets the readout as a blockquote.

        A plain whitespace collapse leaves each line's `> ` marker embedded
        mid-sentence and the pattern then matches nothing -- a vacuous check
        that still exits 0, which is the failure this project has already hit
        twice (check 4's dead connector branch, check 6's hand census).
        """
        quoted = "\n".join(
            "> " + line for line in self._sentence(mismatch_count=124).splitlines()
        )
        misses = self.tree.check("> **Readout:**\n" + quoted + "\n")
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("mismatch_count=124", misses[0])

    def test_a_readout_naming_a_flow_with_no_verdict_files_is_reported(self):
        self.tree.add_layout_record("cdac-array", "20260906-020815-38cdbd3", latest=True)
        body = self._sentence().replace("sar-adc-top", "cdac-array")
        misses = self.tree.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("no `reports/LATEST` record carrying both", misses[0])

    def test_a_document_stating_no_readout_is_not_failed_for_it(self):
        self.assertEqual(self.tree.check("Nothing to read out here.\n"), [])

    def test_stats_sentence_round_trips_through_the_checker(self):
        """`--stats` output must be pasteable: what it prints must pass.

        If the generator and the pattern ever disagree, the documented fix for
        a check-9 failure silently stops working.
        """
        readout = checker.signoff_readout("sar-adc-top")
        self.assertIsNotNone(readout)
        sentence = checker.readout_sentence("sar-adc-top", readout)
        self.assertEqual(self.tree.check(sentence + "\n"), [])


def io_section(*rows: str, totals: str = "", quoted: str | None = None) -> str:
    """A minimal Section 2 I/O table, optional Totals sentence and quote."""
    parts = [
        "## 2. I/O list",
        "",
        "| Signal | Dir | Assumed Challenge slot | Count used | Notes |",
        "|---|---|---|---|---|",
        *rows,
        "",
    ]
    if totals:
        parts += [totals, ""]
    if quoted is not None:
        parts += ["```", f".subckt sar_adc_top {quoted}", "```", ""]
    return "\n".join(parts + ["## 3. Next section", ""])


class TestIoTableParity(unittest.TestCase):
    """Check 10: Section 2's I/O list is the netlist's own, fully categorised.

    The defect shape here is not one this document has *already* suffered --
    it is the one it is exposed to: `design/sar_adc_top.spice` is regenerated
    from a schematic this repo really does edit, and every claim in Section 2
    (the quoted port list, the per-signal rows, the slot totals) is a hand
    restatement of it. Issue #121's acceptance criterion 1 is exactly this
    mapping, so it is graded mechanically rather than re-read.
    """

    def setUp(self):
        self.tree = FixtureTree(self)

    def test_port_with_no_table_row_is_reported(self):
        self.tree.add_top_netlist("VINP", "CLK", "BUSY")
        misses = self.tree.check(
            io_section(
                "| `VINP` | in | dedicated pad (budget: 0–4) | 1 | analog in |",
                "| `CLK` | in | digital control input (budget: ≤24) | 1 | clock |",
            )
        )
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("port `BUSY`", misses[0])
        self.assertIn("no row in Section 2's I/O table", misses[0])

    def test_table_signal_that_is_not_a_port_is_reported(self):
        self.tree.add_top_netlist("CLK")
        misses = self.tree.check(
            io_section(
                "| `CLK` | in | digital control input (budget: ≤24) | 1 | clock |",
                "| `MODE` | in | digital control input | 1 | not in the netlist |",
            )
        )
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("names `MODE`", misses[0])
        self.assertIn("not a port", misses[0])

    def test_quoted_port_list_must_match_port_for_port_and_in_order(self):
        self.tree.add_top_netlist("VINP", "VINN")
        body = io_section(
            "| `VINP`, `VINN` | in | dedicated pad (budget: 0–4) | 2 | in |",
            quoted="VINN VINP",
        )
        misses = self.tree.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("quoted `.subckt sar_adc_top` port list", misses[0])

    def test_quoted_port_list_may_wrap_with_a_continuation(self):
        self.tree.add_top_netlist("VINP", "VINN")
        body = io_section(
            "| `VINP`, `VINN` | in | dedicated pad (budget: 0–4) | 2 | in |",
            quoted="VINP \\\n  VINN",
        )
        self.assertEqual(self.tree.check(body), [])

    def test_row_count_that_disagrees_with_the_ports_it_names_is_reported(self):
        self.tree.add_top_netlist("VINP", "VINN")
        misses = self.tree.check(
            io_section("| `VINP`, `VINN` | in | dedicated pad (budget: 0–4) | 1 | in |")
        )
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("states a count of 1, but names 2 port(s)", misses[0])

    def test_a_range_signal_cell_is_expanded_to_the_ports_it_names(self):
        """`DOUT9..DOUT0` is ten ports, and the row's count must say so."""
        self.tree.add_top_netlist(*[f"DOUT{i}" for i in range(9, -1, -1)])
        body = io_section(
            "| `DOUT9..DOUT0` | out | digital test output (budget: ≤12) | 10 | out |"
        )
        self.assertEqual(self.tree.check(body), [])

    def test_rail_row_claiming_no_count_is_exempt(self):
        self.tree.add_top_netlist("VDD", "CLK")
        body = io_section(
            "| `VDD` | supply | 1.8 V rail (shared) | — (rail, not a slot) | rail |",
            "| `CLK` | in | digital control input (budget: ≤24) | 1 | clock |",
            totals="**Totals**: **1** of ≤24 digital control inputs (`CLK`).",
        )
        self.assertEqual(self.tree.check(body), [])

    def test_counted_row_matching_no_slot_category_is_reported(self):
        self.tree.add_top_netlist("CLK")
        misses = self.tree.check(
            io_section("| `CLK` | in | clock slot (budget: ≤24) | 1 | clock |")
        )
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("matches 0 of the categories", misses[0])

    def test_totals_sentence_is_recomputed_per_category(self):
        self.tree.add_top_netlist("CLK", "RST_B", "BUSY")
        misses = self.tree.check(
            io_section(
                "| `CLK` | in | digital control input (budget: ≤24) | 1 | clock |",
                "| `RST_B` | in | digital control input | 1 | reset |",
                "| `BUSY` | out | digital test output (budget: ≤12) | 1 | strobe |",
                totals=(
                    "**Totals**: **3** of ≤24 digital control inputs, "
                    "**1** of ≤12 digital test outputs."
                ),
            )
        )
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("claims 3 digital control inputs", misses[0])
        self.assertIn("counts 2", misses[0])

    def test_conditional_total_is_the_dedicated_pads_plus_the_reference_lines(self):
        self.tree.add_top_netlist("VINP", "VREFP", "VREFN")
        body = io_section(
            "| `VINP` | in | dedicated pad (budget: 0–4) | 1 | analog in |",
            "| `VREFP`, `VREFN` | in | harness-supplied bandgap reference | 2 | ref |",
            totals=(
                "**Totals**: **1** of 0–4 dedicated pads and **2** "
                "harness-supplied reference lines — **4 dedicated pads against "
                "a 0–4 ceiling** if the harness cannot supply the pair."
            ),
        )
        misses = self.tree.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("conditional dedicated-pad total claims 4", misses[0])
        self.assertIn("come to 3", misses[0])

    def test_check_is_inert_without_the_top_netlist(self):
        # No design/sar_adc_top.spice in the fixture tree at all.
        body = io_section("| `NOPE` | in | digital control input | 9 | invented |")
        self.assertEqual(self.tree.check(body), [])


class TestCoverageIndexParity(unittest.TestCase):
    """Check 11: no Section 4 row ignores a campaign indexed under it.

    The defect shape is the one no other check here can see, because it is an
    *absence*: the real document's Power row was graded "BLOCKED / UNMEASURED
    -- no full-block power campaign exists" for five days after
    `sim/full-conversion-transient/` started carrying a 9-corner whole-ADC
    power table, indexed under that very row. Its one citation was current,
    its bounds matched, its status word agreed -- checks 3 to 9 all passed,
    because a row that cites nothing has nothing stale to find.
    """

    def setUp(self):
        self.tree = FixtureTree(self)
        self.tree.add_sim_record(
            "full-conversion-transient", "20260912-002315-9aaf1ca", latest=True
        )

    CITATION = (
        "[`sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md`]"
        "(../../sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md)"
    )

    def test_an_indexed_campaign_the_row_never_cites_is_reported(self):
        self.tree.add_coverage_index(
            {
                "parameter": "Power",
                "claim_class": "draft-informational",
                "experiments": ["full-conversion-transient"],
            }
        )
        misses = self.tree.check(
            spec_table(
                "| Power | provisional | DRAFT | **UNMEASURED** — no campaign exists "
                "| `layout/sar-sequencer/reports/x/record.md` |"
            )
        )
        reported = [miss for miss in misses if "spec-coverage.json" in miss]
        self.assertEqual(len(reported), 1, misses)
        self.assertIn("full-conversion-transient", reported[0])
        self.assertIn("draft-informational", reported[0])

    def test_a_row_citing_the_indexed_campaign_passes(self):
        self.tree.add_coverage_index(
            {
                "parameter": "Power",
                "claim_class": "draft-informational",
                "experiments": ["full-conversion-transient"],
            }
        )
        misses = self.tree.check(
            spec_table(f"| Power | provisional | DRAFT | **UNMEASURED** | {self.CITATION} |")
        )
        self.assertEqual(misses, [])

    def test_a_superseded_citation_of_the_indexed_campaign_still_satisfies_this_check(self):
        """Check 11 grades *which campaign*, check 3 grades *which record*.

        Overlapping them would report the same drift twice with two different
        fixes; the record-level staleness is check 3's finding.
        """
        self.tree.add_sim_record("full-conversion-transient", "20260911-204111-a6df3bb")
        self.tree.add_coverage_index(
            {
                "parameter": "Power",
                "claim_class": "draft-informational",
                "experiments": ["full-conversion-transient"],
            }
        )
        stale = (
            "[`sim/full-conversion-transient/records/20260911-204111-a6df3bb.md`]"
            "(../../sim/full-conversion-transient/records/20260911-204111-a6df3bb.md)"
        )
        misses = self.tree.check(
            spec_table(f"| Power | provisional | DRAFT | **UNMEASURED** | {stale} |")
        )
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("only at superseded record(s)", misses[0])

    def test_structural_and_methodology_rows_are_excluded_by_class(self):
        """Their Section 4 rows cite schematics and harness dirs, not records."""
        self.tree.add_coverage_index(
            {
                "parameter": "Architecture",
                "claim_class": "structural",
                "experiments": ["full-conversion-transient"],
            },
            {
                "parameter": "Corners",
                "claim_class": "methodology",
                "experiments": ["full-conversion-transient"],
            },
        )
        misses = self.tree.check(
            spec_table(
                "| Architecture | SAR | DRAFT | **MET** | the schematics |",
                "| Corners | −40/27/125 °C | **RATIFIED** | **MET** | harness self-test |",
            )
        )
        self.assertEqual(misses, [])

    def test_an_unbenched_row_is_excluded(self):
        self.tree.add_coverage_index(
            {"parameter": "Power", "claim_class": "unbenched", "experiments": []}
        )
        misses = self.tree.check(
            spec_table("| Power | provisional | DRAFT | **UNMEASURED** | none yet |")
        )
        self.assertEqual(misses, [])

    def test_a_same_record_deferral_inherits_the_row_above(self):
        """The LSB/Sampling-cap shape: deferring is not the same as ignoring."""
        self.tree.add_coverage_index(
            {
                "parameter": "`V_REF`",
                "claim_class": "ratified-measured",
                "experiments": ["full-conversion-transient"],
            },
            {
                "parameter": "LSB (differential)",
                "claim_class": "ratified-measured",
                "experiments": ["full-conversion-transient"],
            },
        )
        misses = self.tree.check(
            spec_table(
                f"| `V_REF` | `1.8 V` | **RATIFIED** | **MET** | {self.CITATION} |",
                "| LSB (differential) | `3.5156 mV` | **RATIFIED** | **MET** — same "
                "record as `V_REF` | same record |",
            )
        )
        self.assertEqual(misses, [])

    def test_a_row_that_defers_to_a_row_citing_nothing_is_still_reported(self):
        self.tree.add_coverage_index(
            {
                "parameter": "LSB (differential)",
                "claim_class": "ratified-measured",
                "experiments": ["full-conversion-transient"],
            }
        )
        misses = self.tree.check(
            spec_table(
                "| `V_REF` | `1.8 V` | **RATIFIED** | **MET** | prose only |",
                "| LSB (differential) | `3.5156 mV` | **RATIFIED** | **MET** | same record |",
            )
        )
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("LSB (differential)", misses[0])

    def test_check_is_inert_without_the_coverage_index(self):
        # No sim/spec-coverage.json in the fixture tree at all.
        misses = self.tree.check(
            spec_table("| Power | provisional | DRAFT | **UNMEASURED** | prose |")
        )
        self.assertEqual(misses, [])


class TestPowerReadout(unittest.TestCase):
    """Check 12: a stated power readout must be the record's own figures.

    Same defect shape as check 9, one table over: check 3 forces the citation
    forward when the campaign re-runs, and every figure quoted out of the old
    record stays behind. This campaign has already carried four different
    power sets (issue #257, DR-008, DR-009).
    """

    STAMP = "20260912-002315-9aaf1ca"
    POWER = {
        "tt_27c_1.80v": 27.971,
        "ss_27c_1.80v": 26.971,
        "tt_125c_1.80v": 31.199,
        "tt_27c_1.62v": 21.600,
        "tt_27c_1.98v": 34.237,
    }
    CITATION = (
        "[`sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md`]"
        "(../../sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md)"
    )

    def setUp(self):
        self.tree = FixtureTree(self)
        self.tree.add_sim_record(
            "full-conversion-transient", self.STAMP, latest=True, power=self.POWER
        )

    def _row(self, readout: str, *, citation: str | None = None) -> str:
        cite = self.CITATION if citation is None else citation
        return spec_table(
            f"| Power | provisional | DRAFT | **UNMEASURED** — {readout} | {cite} |"
        )

    def _readout(self, **overrides) -> str:
        fields = {
            "min": "21.600",
            "min_corner": "tt_27c_1.62v",
            "typ": "27.971",
            "typ_corner": "tt_27c_1.80v",
            "max": "34.237",
            "max_corner": "tt_27c_1.98v",
            "corners": "5",
        }
        fields.update(overrides)
        return (
            f"min **{fields['min']} µW** at `{fields['min_corner']}`, "
            f"typ **{fields['typ']} µW** at `{fields['typ_corner']}`, "
            f"max **{fields['max']} µW** at `{fields['max_corner']}`, "
            f"over **{fields['corners']}** corners"
        )

    def test_a_truthful_readout_passes(self):
        self.assertEqual(self.tree.check(self._row(self._readout())), [])

    def test_a_drifted_figure_is_reported_with_its_field_name(self):
        misses = self.tree.check(self._row(self._readout(typ="21.874")))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("typ=21.874", misses[0])
        self.assertIn("typ=27.971", misses[0])
        self.assertIn("--stats", misses[0])

    def test_a_figure_attributed_to_the_wrong_corner_is_reported(self):
        misses = self.tree.check(self._row(self._readout(max_corner="tt_125c_1.80v")))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("max_corner=`tt_125c_1.80v`", misses[0])
        self.assertIn("max_corner=`tt_27c_1.98v`", misses[0])

    def test_each_drifted_field_is_reported_separately(self):
        misses = self.tree.check(self._row(self._readout(min="16.750", corners="9")))
        self.assertEqual(len(misses), 2, misses)
        self.assertTrue(any("min=16.750" in miss for miss in misses))
        self.assertTrue(any("over 9 corners" in miss for miss in misses))

    def test_the_grid_shape_is_part_of_the_claim(self):
        """Three right figures off a four-corner run is not this claim."""
        misses = self.tree.check(self._row(self._readout(corners="3")))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("has 5", misses[0])

    def test_a_readout_whose_row_cites_no_power_campaign_is_reported(self):
        misses = self.tree.check(
            self._row(self._readout(), citation="`layout/sar-sequencer/reports/x/record.md`")
        )
        reported = [miss for miss in misses if "power readout" in miss]
        self.assertEqual(len(reported), 1, misses)
        self.assertIn("Power table", reported[0])

    def test_a_record_with_no_power_table_yields_no_readout(self):
        self.tree.add_sim_record("enob-estimate", "20260828-005033-0c70212", latest=True)
        self.assertIsNone(checker.power_readout("enob-estimate"))

    def test_a_power_table_without_the_nominal_corner_yields_no_readout(self):
        """"typ" is the grid's own centre point, not the median measurement."""
        self.tree.add_sim_record(
            "cdac-bit-trial-settling",
            "20260907-013225-5f176a6",
            latest=True,
            power={"ss_27c_1.80v": 26.971, "tt_27c_1.98v": 34.237},
        )
        self.assertIsNone(checker.power_readout("cdac-bit-trial-settling"))

    def test_a_document_stating_no_readout_is_not_failed_for_it(self):
        misses = self.tree.check(
            self._row("no figures stated here").replace("µW", "microwatts")
        )
        self.assertEqual(misses, [])

    def test_stats_sentence_round_trips_through_the_checker(self):
        """`--stats` output must be pasteable: what it prints must pass.

        The same guard check 9 needed -- if the generator and the pattern
        disagree, the documented fix for a check-12 failure silently stops
        working.
        """
        readout = checker.power_readout("full-conversion-transient")
        self.assertIsNotNone(readout)
        self.assertEqual(self.tree.check(self._row(checker.power_sentence(readout))), [])


class TestAgainstTheRealProposal(unittest.TestCase):
    def test_committed_proposal_document_passes(self):
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        self.assertTrue(doc.is_file(), doc)
        self.assertEqual(checker.check_document(doc), [])

    def test_pointer_claims_are_actually_evaluated_on_the_real_document(self):
        """Guard against check 4 going vacuous against the live document.

        The defect this test exists for did not produce a wrong verdict -- it
        produced no verdict: `CONNECTOR_RE`'s "the" branch could not match
        post-strip text, so the `(the current \\`reports/LATEST\\`)` phrasing
        §4 uses was silently skipped and a stale stamp there passed the gate.
        A count assertion is the only thing that catches that class of bug on
        the real document, since a vacuous check still exits 0.
        """
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        claims = checker.attached_pointer_claims(doc.read_text())
        self.assertGreaterEqual(
            len(claims), 5, "check 4 evaluates almost nothing in this document"
        )
        # At least one of them must be matched via the "the" connector, i.e.
        # the branch that was dead.
        the_forms = [
            connector for _claim, _cited, connector in claims if "the" in connector
        ]
        self.assertTrue(the_forms, "the `the` connector branch matches nothing")

    def test_the_real_proposal_states_a_parseable_census(self):
        """Check 6 is opt-in per document, so assert the real one opts in.

        Without this, deleting the proposal's census sentence would disable
        check 6 silently and still exit 0 -- the same vacuity trap check 4's
        dead connector branch fell into.
        """
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        stated = checker.CENSUS_RE.search(re.sub(r"\s+", " ", doc.read_text()))
        self.assertIsNotNone(
            stated, "the proposal no longer states a census check 6 can verify"
        )

    def test_section_4_spec_table_is_actually_found(self):
        """Guard against the scoping silently matching zero rows."""
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        rows = checker.spec_table_rows(doc.read_text())
        self.assertGreaterEqual(len(rows), 11, "Section 4's spec table went unparsed")
        parameters = [row.strip("|").split("|")[0].strip() for _, row in rows]
        self.assertIn("Resolution `N`", parameters)
        self.assertIn("Sample rate", parameters)

    def test_the_real_ratified_spec_table_is_actually_found(self):
        """Check 7 is inert on an unparsed spec table, and still exits 0.

        `spec/target-spec.md` is the input side of the comparison; if its
        `## Target table` heading is renamed or the parse otherwise goes
        vacuous, every relaxation check silently stops firing.
        """
        rows = checker.spec_target_rows()
        self.assertGreaterEqual(len(rows), 11, "the ratified spec table went unparsed")
        parameters = [checker._normalise_parameter(row[0]) for row in rows]
        self.assertIn("ENOB", parameters)
        self.assertIn("Comparator input-referred noise", parameters)

    def test_every_ratified_spec_row_is_graded_in_section_4(self):
        """The positive form of check 7 on the live document.

        Check 7 reports what is missing; this asserts the set is complete, so
        a pass that is green because nothing was compared is still a failure.
        """
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        _header, rows = checker.section_4_table(doc.read_text())
        graded = {checker._normalise_parameter(cells[0]) for _line, cells in rows}
        spec = {checker._normalise_parameter(row[0]) for row in checker.spec_target_rows()}
        self.assertTrue(spec, "no ratified spec rows to compare against")
        self.assertEqual(spec - graded, set())

    def test_the_real_proposal_defines_its_verdict_vocabulary(self):
        """Check 8 is opt-in per document, so assert the real one opts in.

        Deleting the preamble's definition list would disable check 8 and
        still exit 0 -- the same vacuity trap checks 4 and 6 each needed a
        guard for.
        """
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        vocabulary = checker.verdict_vocabulary(doc.read_text())
        self.assertGreaterEqual(len(vocabulary), 4, vocabulary)
        # `BLOCKED` was defined here until 2026-09-17 and is deliberately
        # gone: the Power row was its last user and that row turned out to
        # have had whole-ADC evidence all along (check 11). These three are
        # the kinds the table cannot express itself without.
        for kind in ("MET", "UNMET", "UNMEASURED"):
            self.assertIn(kind, vocabulary)

    def test_the_real_proposal_states_a_parseable_signoff_readout(self):
        """Check 9 is opt-in per document, so assert the real one opts in.

        Deleting or re-wording the readout sentence would disable check 9 and
        still exit 0 -- the same vacuity trap checks 4, 6 and 8 each needed a
        guard for. The flow asserted is the one the brief's two sign-off-bar
        rows are graded on.
        """
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        collapsed, _offsets = checker._collapse_quoted_prose(doc.read_text())
        stated = list(checker.READOUT_RE.finditer(collapsed))
        self.assertEqual(
            [match.group("flow") for match in stated], ["layout/sar-adc-top"], stated
        )

    def test_the_real_top_netlist_port_list_is_actually_found(self):
        """Check 10 is inert on an unparsed netlist, and still exits 0.

        `design/sar_adc_top.spice` is the input side of the comparison; if
        xschem's commented-`.subckt` shape or the cell name changes and the
        parse goes vacuous, every Section 2 parity check silently stops
        firing -- the same trap checks 4, 6, 8 and 9 each needed a guard for.
        """
        ports = checker.netlist_ports()
        self.assertGreaterEqual(len(ports), 19, ports)
        for port in ("VINP", "VINN", "VREFP", "VREFN", "VCM", "CLK", "RST_B", "BUSY"):
            self.assertIn(port, ports)
        self.assertEqual(len(ports), len(set(ports)), "duplicate top-level port")

    def test_the_real_io_table_and_its_totals_are_actually_evaluated(self):
        """The positive form of check 10 on the live document.

        Asserts that the table parses, that its rows cover the netlist's whole
        port list, and that the Totals sentence really is in the gated form --
        a document whose totals lost their bold markers would be graded
        against nothing while still exiting 0.
        """
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        text = doc.read_text()
        rows = checker.io_table(text)
        self.assertGreaterEqual(len(rows), 8, "Section 2's I/O table went unparsed")
        mapped = {port for _line, cells in rows for port in checker._cell_ports(cells[0])}
        self.assertEqual(set(checker.netlist_ports()), mapped)

        quoted = checker.quoted_port_lists(text)
        self.assertEqual([ports for _line, ports in quoted], [checker.netlist_ports()])

        collapsed, _offsets = checker._collapse_quoted_prose(text)
        claimed = {match.group("category") for match in checker.IO_TOTAL_RE.finditer(collapsed)}
        self.assertEqual(claimed, set(checker.IO_SLOT_CATEGORIES))
        self.assertTrue(
            checker.IO_CONDITIONAL_RE.search(collapsed),
            "the conditional dedicated-pad total is no longer in the gated form",
        )

    def test_the_real_coverage_index_is_actually_found_and_graded(self):
        """Check 11 is inert on an unparsed index, and still exits 0.

        `sim/spec-coverage.json` is the input side of the comparison; if its
        `rows`/`benches`/`claim_class` shape changes and this parse goes
        vacuous, every "row ignores its own campaign" check silently stops
        firing -- the same trap checks 4, 6, 8, 9 and 10 each needed a guard
        for. Also asserts the *graded* subset is non-empty: an index whose
        rows all fell outside the measured classes would parse fine and check
        nothing.
        """
        rows = checker.coverage_index_rows()
        self.assertGreaterEqual(len(rows), 11, "the coverage index went unparsed")
        graded = [
            (parameter, experiments)
            for parameter, claim_class, experiments in rows
            if claim_class in checker.MEASURED_CLAIM_CLASSES and experiments
        ]
        self.assertGreaterEqual(len(graded), 5, graded)
        self.assertIn("Power", [parameter for parameter, _experiments in graded])

    def test_every_indexed_campaign_is_cited_by_its_own_section_4_row(self):
        """The positive form of check 11 on the live document.

        Check 11 reports what is missing; this asserts the compared set is
        non-empty, so a pass that is green because nothing was compared is
        still a failure.
        """
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        flows = checker.section_4_flows(doc.read_text())
        self.assertGreaterEqual(len(flows), 11, "Section 4's rows went unparsed")
        compared = 0
        for parameter, claim_class, experiments in checker.coverage_index_rows():
            if claim_class not in checker.MEASURED_CLAIM_CLASSES:
                continue
            row = flows.get(parameter)
            self.assertIsNotNone(row, f"{parameter} has no Section 4 row")
            for experiment in experiments:
                self.assertIn(("sim", experiment), row[1], parameter)
                compared += 1
        self.assertGreaterEqual(compared, 8, "check 11 compared almost nothing")

    def test_the_real_proposal_states_a_parseable_power_readout(self):
        """Check 12 is opt-in per row, so assert the real Power row opts in.

        Deleting or re-wording the readout would disable check 12 and still
        exit 0.
        """
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        stated = [
            checker._normalise_parameter(checker._row_cells(row)[0])
            for _line, row in checker.spec_table_rows(doc.read_text())
            if checker.POWER_READOUT_RE.search(row)
        ]
        self.assertEqual(stated, ["Power"], stated)

    def test_the_real_power_readout_is_checked_against_a_real_record(self):
        """The record side of check 12 must be readable, not silently absent.

        `power_readout` returns None when the campaign's current record
        carries no Power table; on the real tree that would turn every field
        comparison into one generic finding instead of a per-field one.
        """
        readout = checker.power_readout("full-conversion-transient")
        self.assertIsNotNone(readout, "the campaign's current record has no Power table")
        self.assertEqual(readout["typ_corner"], checker.NOMINAL_CORNER)
        self.assertEqual(readout["corners"], 9, "the ratified OAT grid is 9 points")
        self.assertLess(readout["min"], readout["max"])

    def test_the_real_signoff_readout_is_checked_against_real_verdict_files(self):
        """The record side of check 9 must be readable, not silently absent.

        `signoff_readout` returns None when the flow's current record carries
        no `drc.json`/`lvs.json`; on the real tree that would turn every
        field comparison into one generic finding instead of a per-field one.
        """
        readout = checker.signoff_readout("sar-adc-top")
        self.assertIsNotNone(readout, "sar-adc-top's current record has no klt verdicts")
        self.assertIn(readout["drc_status"], ("clean", "violations"))
        self.assertIn(readout["lvs_status"], ("match", "mismatch"))
        for field in ("devices_layout", "nets_reference", "pins_matched"):
            self.assertIsInstance(readout[field], int, field)


if __name__ == "__main__":
    unittest.main()

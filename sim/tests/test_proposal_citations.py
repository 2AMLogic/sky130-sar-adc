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

import hashlib
import inspect
import json
import re
import struct
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
        compose: dict | None = None,
        gds: dict[str, bytes] | None = None,
    ):
        report = self.root / "layout" / block / "reports" / stamp
        report.mkdir(parents=True, exist_ok=True)
        (report / "record.md").write_text("fixture record\n")
        # The GDS artefacts check 14 fingerprints: for a composing flow, the
        # `<block>.gds` copies `run-flow.sh` pulled in; for a sub-block flow,
        # its own top-cell GDS. Keyed by file stem so one call can write both
        # shapes.
        for stem, payload in (gds or {}).items():
            (report / f"{stem}.gds").write_bytes(payload)
        # `klt`'s own machine-readable verdicts, which check 9 reads out.
        # Written only when asked for: a record without them is the "nothing
        # to compare against" condition check 9 reports separately.
        if drc is not None:
            (report / "drc.json").write_text(json.dumps(drc))
        if lvs is not None:
            (report / "lvs.json").write_text(json.dumps(lvs))
        # `klt gen-compose`'s own report, which check 13 reads the bounding
        # box out of. Same convention: absent unless asked for, so the "no
        # composition to compare against" condition stays reachable.
        if compose is not None:
            (report / "compose.json").write_text(json.dumps(compose))
        if latest:
            (report.parent / "LATEST").write_text(stamp + "\n")

    def add_sim_record(
        self,
        campaign: str,
        stamp: str,
        *,
        latest: bool = False,
        power: dict[str, float] | None = None,
        power_terms: tuple[str, ...] = ("VDD",),
        kickback: tuple[tuple[float, float, str, str, float, str, str], ...] | None = None,
        kickback_split: bool = False,
    ):
        records = self.root / "sim" / campaign / "records"
        records.mkdir(parents=True, exist_ok=True)
        body = "fixture record\n"
        if kickback is not None:
            # The `Measured value(s)` table check 21 re-derives the Kickback
            # row's figures from, in the shape
            # `sim/comparator-decision/run.py kickback` writes it: one row per
            # `Vindiff` point, each carrying a signed positive and a signed
            # negative peak with the pin and instant it occurred at. Both are
            # extrema over EITHER pin, which is the whole point -- a fixture
            # carrying one per-pin column pair would not reproduce the
            # conflation the check exists for.
            #
            # `kickback_split` grows the table the two columns issue #390's
            # successor record adds, which is the direction check 21 part (c)
            # must flip on.
            extra = (" CM peak (mV) |", " differential peak (mV) |") if kickback_split else ()
            body += "\n## Measured value(s)\n\n"
            body += (
                "| Vindiff (mV) | peak+ (mV) | pin / time (ns) "
                "| peak- (mV) | pin / time (ns) |" + "".join(extra) + "\n"
            )
            body += "|---|" * (5 + len(extra)) + "\n"
            for vindiff, pos, pos_pin, pos_time, neg, neg_pin, neg_time in kickback:
                body += (
                    f"| {vindiff:+.2f} | {pos:+.4f} | {pos_pin} @ {pos_time} "
                    f"| {neg:+.4f} | {neg_pin} @ {neg_time} |"
                    + (" -1.0000 | -1.0000 |" if kickback_split else "")
                    + "\n"
                )
            body += "\n## Findings\n\n- fixture\n"
        if power is not None:
            # The per-corner Power table check 12 reads, in the shape
            # sim/full-conversion-transient/run_conversion.py writes it: the
            # corner id backticked in the first column, the total power in the
            # last. A fixture that wrote only the total would pass while the
            # real multi-column table went unparsed.
            #
            # `power_terms` is the set of per-source current columns between
            # those two, which check 19 part (c) reads out of the header row --
            # the real table carries one per independent source the testbench
            # drives, and that set moves when the block's interface does.
            columns = "".join(f" I({net}) (uA) |" for net in power_terms)
            body += "\n## Power (informational)\n\n"
            body += f"| corner-id |{columns} total power (uW) |\n"
            body += "|---|" + "---|" * (len(power_terms) + 1) + "\n"
            for corner, total in power.items():
                body += f"| `{corner}` |" + " 2.097 |" * len(power_terms)
                body += f" {total:.3f} |\n"
            body += "\n## Findings\n\n- fixture\n"
        (records / f"{stamp}.md").write_text(body)
        if latest:
            (records / "LATEST").write_text(f"{stamp}.md\n")

    def add_erc_record(
        self,
        block: str,
        stamp: str,
        *,
        latest: bool = False,
        graded: str | None = None,
        artefact: str = "sar_adc_top.gds",
        supplies: dict[str, int] | None = None,
        erc_status: str = "clean",
        content_hash: str | None = None,
    ):
        """A `layout/<block>/erc-reports/<stamp>/erc.json` in check 16's shape.

        Written the way `klt erc` really writes it, which is what makes the
        fixture load-bearing: a passing supply carries NO island count of its
        own -- it appears only in `erc_coverage.checked` -- and a failing one
        carries its islands inside an `erc.unconnected_net` finding. A fixture
        that stored a per-net count directly would pass while the real
        report's shape went unparsed.

        `graded` is the `reports/` stamp the run graded, recorded as the
        repo-relative path `klt erc` was invoked with. `content_hash` defaults
        to the real sha256 of that record's own artefact when it exists, which
        is the `current` case; pass an explicit one to reproduce a layout
        record rebuilt underneath a stale ERC verdict.
        """
        report = self.root / "layout" / block / "erc-reports" / stamp
        report.mkdir(parents=True, exist_ok=True)
        (report / "record.md").write_text("fixture erc record\n")
        supplies = {"VDD": 1} if supplies is None else supplies
        findings = [
            {
                "rule": "erc.unconnected_net",
                "net": net,
                "islands": [{"layer": "met1", "shape_count": 1}] * islands,
            }
            for net, islands in supplies.items()
            if islands != 1
        ]
        if content_hash is None and graded is not None:
            stream = self.root / "layout" / block / "reports" / graded / artefact
            content_hash = (
                "sha256:" + hashlib.sha256(stream.read_bytes()).hexdigest()
                if stream.is_file()
                else "sha256:" + "0" * 64
            )
        (report / "erc.json").write_text(
            json.dumps(
                {
                    "file": (
                        f"layout/{block}/reports/{graded}/{artefact}"
                        if graded is not None
                        else None
                    ),
                    "erc_status": erc_status,
                    "erc_finding_count": len(findings),
                    "erc_findings": findings,
                    "erc_coverage": {
                        "checked": [
                            f'erc.net_connectivity:["{net}"]' for net in supplies
                        ]
                        + ['erc.floating_gate:["gate0"]'],
                        "inapplicable": [{"id": "erc.missing_tie:[]"}],
                    },
                    "provenance": {"input": {"content_hash": content_hash}},
                }
            )
        )
        if latest:
            (report.parent / "LATEST").write_text(stamp + "\n")

    def add_coverage_index(self, *rows: dict):
        """A `sim/spec-coverage.json` in the shape check 11 reads.

        Each row is `{"parameter", "claim_class", "experiments"}`, plus an
        optional `"tracking"` -- the free-prose field check 22 reads the
        governing decision records out of. The nested bench shape the real
        index uses is built here so a test states only what it is about.
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
                            **(
                                {"tracking": row["tracking"]}
                                if "tracking" in row
                                else {}
                            ),
                        }
                        for row in rows
                    ],
                }
            )
        )

    def add_decision_record(self, name: str, status: str | None = "proposed"):
        """A `spec/decision-records/<name>` in the shape check 15 reads.

        Written in the real records' own shape -- a `- **Status**:` bullet
        whose word may be bolded or bare, followed by an em-dash rationale the
        check must not read. `status=None` writes a record with no Status
        field at all, which is the "nothing to compare against" condition
        check 15 reports separately from a disagreement.
        """
        records = self.root / "spec" / "decision-records"
        records.mkdir(parents=True, exist_ok=True)
        body = [f"# {name.removesuffix('.md')}", ""]
        if status is not None:
            body.append(
                f"- **Status**: {status} — this fixture record ratifies nothing."
            )
        body += ["- **Date**: 2026-09-18", ""]
        (records / name).write_text("\n".join(body))

    def add_signoff(
        self,
        *,
        items: list[dict] | None = None,
        evidence: dict | None = None,
        met: int = 3,
        total: int = 22,
        tier: str | None = None,
        version: str = "0.6.0",
        report: bool = True,
        manifest: bool = True,
    ):
        """A `signoff/` pair in the shape check 17 reads (issue #345).

        Written the way `klt signoff` really writes it, which is what makes
        the fixture load-bearing: an `unmet` item renders `citation: null`
        even when the manifest cited real evidence for it, so the records the
        verdict rests on can only be recovered from the MANIFEST. A fixture
        that carried citations on the report side would pass while the real
        two-file read went untested.
        """
        signoff = self.root / "signoff"
        signoff.mkdir(parents=True, exist_ok=True)
        if report:
            (signoff / "t1-report.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "block": "fixture",
                        "tier": tier,
                        "t1_item_count": total,
                        "t1_met_count": met,
                        "build": {"package_version": version, "is_release": True},
                        "items": [
                            {
                                "tier": item.get("tier", "T1"),
                                "id": item["id"],
                                "title": item.get("title", "fixture item"),
                                "partition": item["partition"],
                                "status": item.get("status", "unmet"),
                                "reason": item.get("reason"),
                                "citation": None,
                            }
                            for item in (items or [])
                        ],
                    }
                )
            )
        if manifest:
            (signoff / "block-manifest.json").write_text(
                json.dumps(
                    {
                        "block": "fixture",
                        "kind": "mixed-signal",
                        "evidence": evidence or {},
                    }
                )
            )

    def add_top_netlist(
        self,
        *ports: str,
        glue: tuple[str, ...] = (),
        subblocks: tuple[str, ...] = (),
    ):
        """A `design/sar_adc_top.spice` with the given top-level port list.

        Written in the shape xschem really emits for the *top* cell -- the
        `.subckt` line commented out, since the top level is netlisted flat.
        A fixture that wrote a bare `.subckt` would pass while the real file
        shape went unparsed.

        `glue` is the instance lines *inside* that flat top cell, which check
        20 part (b) censuses; `subblocks` is instance lines placed after the
        top cell's `**.ends`, inside a sub-block `.subckt`, which part (b)
        must NOT count and part (a) must.
        """
        design = self.root / "design"
        design.mkdir(parents=True, exist_ok=True)
        body = [
            "* fixture netlist -- a header naming sky130_fd_pr__nfet_01v8 in",
            "* prose, which a census over raw text would miscount as an instance",
            "**.subckt sar_adc_top " + " ".join(ports),
            "*.ipin " + (ports[0] if ports else "NONE"),
            *glue,
            "**.ends",
        ]
        if subblocks:
            body += [".subckt fixture_block A B", *subblocks, ".ends"]
        (design / "sar_adc_top.spice").write_text("\n".join(body) + "\n")
        # The schematic the netlist is regenerated from. Present so a document
        # that cites it by path (as the real one does, and as check 20's own
        # census sentence must) is not failed by check 2 for the fixture's sake.
        (design / "sar_adc_top.sch").write_text("* fixture schematic\n")

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


def compose_json(
    *,
    cell: str = "gen_compose_0",
    x0: float = -20.2,
    y0: float = -161.6,
    x1: float = 260.2,
    y1: float = 223.9,
    blocks: list[dict] | None = None,
) -> dict:
    """A `klt gen-compose` report in the shape checks 13 and 14 read.

    Defaults are `layout/sar-adc-top/`'s own real extent, so a fixture states
    only the field it is about. `blocks` is what check 14 enumerates the
    composed inputs from; `composed_block()` builds an entry in the real
    report's shape.
    """
    return {
        "schema_version": 1,
        "generator": "gen-compose",
        "cell_name": cell,
        "dbu_um": 0.001,
        "bbox_um": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        "blocks": [] if blocks is None else blocks,
    }


def composed_block(block_id: str, *, source: str = "cell") -> dict:
    """One `blocks[]` entry of a `compose.json`.

    `source` is the field check 14 filters on: `"cell"` for an already-drawn
    sub-block composed in (and therefore copied in as `<id>.gds`, with an
    upstream record to trace to), `"generator_report"` for the routing cell
    the run generates and which has no upstream record at all.
    """
    return {
        "id": block_id,
        "source": source,
        "cell_name": block_id,
        "offset_um": {"x": 0.0, "y": 0.0},
        "bbox_um": {"x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 1.0},
        "orientation": "none",
    }


def gds_bytes(
    *,
    cell: str = "fixture_cell",
    layer: int = 68,
    datatype: int = 20,
    corner: int = 1000,
    timestamp: int = 0,
) -> bytes:
    """A minimal but structurally real GDS stream, in record form.

    Check 14 fingerprints GDS by hashing its record stream with the two
    timestamp-bearing record types (BGNLIB/BGNSTR) dropped, so a fixture has
    to be able to vary the timestamp *independently* of the geometry -- a
    synthetic blob would make the one guarantee that matters (a re-write of
    identical geometry still fingerprints equal) untestable.
    """

    def record(rtype: int, dtype: int, payload: bytes) -> bytes:
        return struct.pack(">HBB", 4 + len(payload), rtype, dtype) + payload

    stamp = struct.pack(">12h", *([timestamp] * 12))

    def name(text: str) -> bytes:
        encoded = text.encode("ascii")
        return encoded + (b"\0" if len(encoded) % 2 else b"")

    box = (0, 0, corner, 0, corner, corner, 0, corner, 0, 0)
    return b"".join(
        (
            record(0x00, 0x02, struct.pack(">h", 600)),  # HEADER
            record(0x01, 0x02, stamp),  # BGNLIB
            record(0x02, 0x06, name("FIXTURE.DB")),  # LIBNAME
            record(0x03, 0x05, b"\x00" * 16),  # UNITS
            record(0x05, 0x02, stamp),  # BGNSTR
            record(0x06, 0x06, name(cell)),  # STRNAME
            record(0x08, 0x00, b""),  # BOUNDARY
            record(0x0D, 0x02, struct.pack(">h", layer)),  # LAYER
            record(0x0E, 0x02, struct.pack(">h", datatype)),  # DATATYPE
            record(0x10, 0x03, struct.pack(">10i", *box)),  # XY
            record(0x11, 0x00, b""),  # ENDEL
            record(0x07, 0x00, b""),  # ENDSTR
            record(0x04, 0x00, b""),  # ENDLIB
        )
    )


class TestAreaReadout(unittest.TestCase):
    """Check 13: a stated area readout must be the composition's own extent.

    The same defect shape as checks 9 and 12, on the one figure in Section 4
    still carried by hand: `layout/sar-adc-top/` has been re-run five times,
    and on each re-run check 3 moved the citation while a human established by
    `cmp` that the box had not moved. A re-run that moves geometry without
    moving the composed extent has already happened here (`sampling_frontend`'s
    own `bbox_um.y1`, 146.3 -> 147.22 um, under klayout-tools v0.5.0).
    """

    STAMP = "20260915-234004-76f48b9"
    CITATION = (
        "[`layout/sar-adc-top/reports/20260915-234004-76f48b9/compose.json`]"
        "(../../layout/sar-adc-top/reports/20260915-234004-76f48b9/compose.json)"
    )

    def setUp(self):
        self.tree = FixtureTree(self)
        self.tree.add_layout_record(
            "sar-adc-top", self.STAMP, latest=True, compose=compose_json()
        )

    def _row(self, readout: str, *, citation: str | None = None) -> str:
        cite = self.CITATION if citation is None else citation
        return spec_table(
            f"| Area | not yet specified | Not a spec row yet | "
            f"**Informational only** — {readout} | {cite} |"
        )

    def _readout(self, **overrides) -> str:
        fields = {
            "cell": "gen_compose_0",
            "flow": "layout/sar-adc-top",
            "x0": "-20.200",
            "x1": "260.200",
            "y0": "-161.600",
            "y1": "223.900",
            "width": "280.400",
            "height": "385.500",
            "area_mm2": "0.108",
        }
        fields.update(overrides)
        return (
            f"the composed cell `{fields['cell']}` on the record "
            f"`{fields['flow']}/reports/LATEST` resolves to spans "
            f"**{fields['x0']}** µm to **{fields['x1']}** µm in x and "
            f"**{fields['y0']}** µm to **{fields['y1']}** µm in y, i.e. "
            f"**{fields['width']}** µm × **{fields['height']}** µm ≈ "
            f"**{fields['area_mm2']}** mm²"
        )

    def test_a_truthful_readout_passes(self):
        self.assertEqual(self.tree.check(self._row(self._readout())), [])

    def test_a_drifted_coordinate_is_reported_with_its_field_name(self):
        misses = self.tree.check(self._row(self._readout(y1="224.820")))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("y1=224.820", misses[0])
        self.assertIn("y1=223.900", misses[0])
        self.assertIn("--stats", misses[0])

    def test_a_derived_figure_the_coordinates_do_not_support_is_reported(self):
        """An arithmetic slip in the "i.e." clause is as wrong as a stale box."""
        misses = self.tree.check(self._row(self._readout(area_mm2="0.180")))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("area_mm2=0.180", misses[0])
        self.assertIn("area_mm2=0.108", misses[0])

    def test_each_drifted_field_is_reported_separately(self):
        misses = self.tree.check(self._row(self._readout(x0="-19.200", width="279.400")))
        self.assertEqual(len(misses), 2, misses)
        self.assertTrue(any("x0=-19.200" in miss for miss in misses))
        self.assertTrue(any("width=279.400" in miss for miss in misses))

    def test_a_renamed_composed_cell_is_reported(self):
        misses = self.tree.check(self._row(self._readout(cell="SAR_ADC_TOP")))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("`SAR_ADC_TOP`", misses[0])
        self.assertIn("`gen_compose_0`", misses[0])

    def test_a_unicode_minus_sign_is_read_as_the_same_figure(self):
        """This document sets temperatures with U+2212 and coordinates with `-`."""
        self.assertEqual(
            self.tree.check(self._row(self._readout(x0="−20.200", y0="−161.600"))), []
        )

    def test_a_readout_for_a_flow_the_row_does_not_cite_is_reported(self):
        self.tree.add_layout_record(
            "comparator", "20260910-120000-abcdef0", latest=True, compose=compose_json()
        )
        misses = self.tree.check(
            self._row(
                self._readout(flow="layout/comparator"),
                citation=self.CITATION,
            )
        )
        reported = [miss for miss in misses if "cites no record of that flow" in miss]
        self.assertEqual(len(reported), 1, misses)

    def test_a_readout_naming_a_flow_with_no_composition_is_reported(self):
        self.tree.add_layout_record("sar-sequencer", "20260910-120000-abcdef0", latest=True)
        misses = self.tree.check(
            self._row(
                self._readout(flow="layout/sar-sequencer"),
                citation="`layout/sar-sequencer/reports/20260910-120000-abcdef0/record.md`",
            )
        )
        reported = [miss for miss in misses if "bbox_um" in miss]
        self.assertEqual(len(reported), 1, misses)

    def test_a_degenerate_box_yields_no_readout(self):
        self.tree.add_layout_record(
            "trivial-cell",
            "20260910-120000-abcdef0",
            latest=True,
            compose=compose_json(x0=10.0, x1=10.0),
        )
        self.assertIsNone(checker.area_readout("trivial-cell"))

    def test_a_compose_report_without_a_bbox_yields_no_readout(self):
        broken = compose_json()
        del broken["bbox_um"]
        self.tree.add_layout_record(
            "seln-inverters", "20260910-120000-abcdef0", latest=True, compose=broken
        )
        self.assertIsNone(checker.area_readout("seln-inverters"))

    def test_a_document_stating_no_readout_is_not_failed_for_it(self):
        self.assertEqual(self.tree.check(self._row("no extent stated here")), [])

    def test_stats_sentence_round_trips_through_the_checker(self):
        """`--stats` output must be pasteable: what it prints must pass.

        The same guard checks 9 and 12 needed. Figures are compared as
        formatted strings precisely so this can never fail on a rounding
        boundary.
        """
        readout = checker.area_readout("sar-adc-top")
        self.assertIsNotNone(readout)
        self.assertEqual(
            self.tree.check(self._row(checker.area_sentence("sar-adc-top", readout))), []
        )


class TestCompositionInputs(unittest.TestCase):
    """Check 14: a composed input must trace to a record of its own flow.

    The defect shape checks 3-13 structurally cannot see. Each of those grades
    a claim against the record it cites; none looks at what that record was
    built *from*. `layout/sar-adc-top/bin/run-flow.sh` resolves each
    sub-block's `reports/LATEST` at run time and `compose.json` keeps no
    provenance for what it took, so a sub-block re-run advances Section 3's
    readouts while the composition silently keeps grading the superseded
    geometry -- which is the tree's real state as of 2026-09-18 for two of the
    five inputs (issue #323's re-run, PR #327).
    """

    TOP = "20260915-234004-76f48b9"
    SUB = "20260917-180601-527ec73"

    def setUp(self):
        self.tree = FixtureTree(self)
        self.embedded = gds_bytes(cell="sar_sequencer")
        self.tree.add_layout_record(
            "sar-adc-top",
            self.TOP,
            latest=True,
            compose=compose_json(
                blocks=[
                    composed_block("sar_sequencer"),
                    composed_block("route", source="generator_report"),
                ]
            ),
            gds={"sar_sequencer": self.embedded},
        )
        self.tree.add_layout_record(
            "sar-sequencer", self.SUB, latest=True, gds={"sar_sequencer": self.embedded}
        )

    def _readout(self, **overrides) -> str:
        fields = {
            "composition": "layout/sar-adc-top",
            "cell": "sar_sequencer",
            "matched": "1",
            "flow": "layout/sar-sequencer",
            "newest": self.SUB,
            "latest": self.SUB,
            "status": "current",
        }
        fields.update(overrides)
        plural = "" if fields["matched"] == "1" else "s"
        return (
            f"> the composition on `{fields['composition']}/reports/LATEST` embeds a\n"
            f"> `{fields['cell']}.gds` that reproduces **{fields['matched']}** "
            f"record{plural} of `{fields['flow']}/`,\n"
            f"> newest `{fields['newest']}`, while `reports/LATEST` there names\n"
            f"> `{fields['latest']}`: **{fields['status']}**.\n"
        )

    def test_a_truthful_readout_passes(self):
        self.assertEqual(self.tree.check(self._readout()), [])

    def test_a_timestamp_only_rewrite_still_counts_as_the_same_record(self):
        """The one guarantee the fingerprint exists for.

        `klt` stamps BGNLIB/BGNSTR at write time, so an input re-written with
        identical geometry is byte-different. Hashing those in would report
        every input as unmatched and make the check useless.
        """
        self.tree.add_layout_record(
            "sar-sequencer",
            self.SUB,
            latest=True,
            gds={"sar_sequencer": gds_bytes(cell="sar_sequencer", timestamp=1234)},
        )
        self.assertEqual(self.tree.check(self._readout()), [])

    def test_a_geometry_change_is_not_a_reproduction(self):
        """The conservative direction: different geometry is never "current"."""
        self.tree.add_layout_record(
            "sar-sequencer",
            "20260918-090000-abcdef0",
            latest=True,
            gds={"sar_sequencer": gds_bytes(cell="sar_sequencer", corner=2000)},
        )
        misses = self.tree.check(
            self._readout(latest="20260918-090000-abcdef0", status="superseded")
        )
        self.assertEqual(misses, [])

    def test_a_superseded_input_stated_as_current_is_reported(self):
        """The live defect this check was written for."""
        self.tree.add_layout_record(
            "sar-sequencer",
            "20260918-090000-abcdef0",
            latest=True,
            gds={"sar_sequencer": gds_bytes(cell="sar_sequencer", corner=2000)},
        )
        misses = self.tree.check(self._readout(latest="20260918-090000-abcdef0"))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("status=current", misses[0])
        self.assertIn("status=superseded", misses[0])
        self.assertIn("--stats", misses[0])

    def test_a_drifted_match_count_is_reported_with_its_field_name(self):
        misses = self.tree.check(self._readout(matched="2"))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("matched=2", misses[0])
        self.assertIn("matched=1", misses[0])

    def test_a_stale_pointer_stamp_is_reported(self):
        misses = self.tree.check(self._readout(latest="20260101-000000-0000000"))
        self.assertTrue(any("latest=20260101-000000-0000000" in miss for miss in misses))

    def test_a_stale_newest_stamp_is_reported(self):
        misses = self.tree.check(self._readout(newest="20260101-000000-0000000"))
        self.assertTrue(any("newest=20260101-000000-0000000" in miss for miss in misses))

    def test_an_input_the_composition_does_not_embed_is_reported(self):
        misses = self.tree.check(self._readout(cell="comparator"))
        reported = [miss for miss in misses if "composes no such block" in miss]
        self.assertEqual(len(reported), 1, misses)

    def test_a_flow_the_copy_reproduces_nothing_in_is_reported(self):
        """Attributing an input to the wrong flow must not pass silently."""
        self.tree.add_layout_record(
            "comparator",
            "20260915-120705-1e90b14",
            latest=True,
            gds={"sar_sequencer": gds_bytes(cell="sar_sequencer", corner=2000)},
        )
        misses = self.tree.check(
            self._readout(flow="layout/comparator", latest="20260915-120705-1e90b14")
        )
        reported = [miss for miss in misses if "reproduces NO record" in miss]
        self.assertEqual(len(reported), 1, misses)

    def test_a_composed_input_with_no_stated_readout_is_reported(self):
        """Both directions: dropping the line for the stale input is the cheat."""
        self.tree.add_layout_record(
            "sar-adc-top",
            self.TOP,
            latest=True,
            compose=compose_json(
                blocks=[composed_block("sar_sequencer"), composed_block("seln_inverters")]
            ),
            gds={"sar_sequencer": self.embedded},
        )
        misses = self.tree.check(self._readout())
        reported = [miss for miss in misses if "states no composition-input readout" in miss]
        self.assertEqual(len(reported), 1, misses)
        self.assertIn("seln_inverters.gds", reported[0])

    def test_a_generated_block_needs_no_readout(self):
        """The routing cell is produced by the run; it has no upstream record."""
        self.assertEqual(self.tree.check(self._readout()), [])
        self.assertEqual(checker.composition_inputs("sar-adc-top"), ["sar_sequencer"])

    def test_a_document_stating_no_readout_is_not_failed_for_it(self):
        self.assertEqual(self.tree.check("no composition inputs stated here\n"), [])

    def test_an_unreadable_embedded_copy_is_reported_not_matched(self):
        self.tree.add_layout_record(
            "sar-adc-top",
            self.TOP,
            latest=True,
            compose=compose_json(blocks=[composed_block("sar_sequencer")]),
            gds={"sar_sequencer": b"not a gds stream"},
        )
        self.tree.add_layout_record(
            "sar-sequencer", self.SUB, latest=True, gds={"sar_sequencer": b"nor is this"}
        )
        misses = self.tree.check(self._readout())
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("no readable `sar_sequencer.gds` to fingerprint", misses[0])

    def test_a_truncated_stream_yields_no_fingerprint(self):
        """A parse failure must never read as equality against another failure."""
        truncated = self.tree.root / "truncated.gds"
        truncated.write_bytes(gds_bytes()[:-3])
        self.assertIsNone(checker._gds_fingerprint(truncated))
        empty = self.tree.root / "empty.gds"
        empty.write_bytes(b"")
        self.assertIsNone(checker._gds_fingerprint(empty))

    def test_a_flow_with_no_composition_yields_no_inputs(self):
        self.tree.add_layout_record("comparator", "20260915-120705-1e90b14", latest=True)
        self.assertIsNone(checker.composition_inputs("comparator"))

    def test_stats_sentence_round_trips_through_the_checker(self):
        """`--stats` output must be pasteable: what it prints must pass."""
        provenance = checker.composition_input_provenance(
            "sar-adc-top", "sar_sequencer", "sar-sequencer"
        )
        self.assertIsNotNone(provenance)
        sentence = checker.composition_input_sentence(
            "sar-adc-top", "sar_sequencer", "sar-sequencer", provenance
        )
        self.assertEqual(self.tree.check(f"> {sentence}\n"), [])

    def test_stats_resolves_the_source_flow_without_being_told_it(self):
        """`--stats` has no document to read the flow name off.

        It must also not resolve to the composing flow itself, whose own older
        records hold copies of exactly these input files.
        """
        self.tree.add_layout_record(
            "sar-adc-top",
            "20260908-072857-80df05e",
            gds={"sar_sequencer": self.embedded},
        )
        self.assertEqual(
            checker._source_flow_of("sar-adc-top", "sar_sequencer"), "sar-sequencer"
        )


class TestDecisionRecordStatus(unittest.TestCase):
    """Check 15: a stated decision-record status must be the record's own.

    The tree checks 3-14 never reach. Check 7 compares Section 4's Status
    column to `spec/target-spec.md`, but this repo ratifies a numeric row by
    the operator approving the PR that carries its *decision record*, so the
    record's own Status field moves first and the spec table follows. In that
    window every other check is green and the document is wrong -- which is
    exactly the state Section 7 Item 4 had been hand-re-reading DR-007 to
    detect ("DR-007's status was re-checked live -- still `proposed`").
    """

    ENOB = "DR-007-revised-enob-inl-dnl-targets.md"
    NWELL = "DR-007-sampling-frontend-nwell-domains.md"

    def setUp(self):
        self.tree = FixtureTree(self)
        self.tree.add_decision_record("DR-003-numeric-spec-derivation.md", "**accepted**")
        self.tree.add_decision_record(self.ENOB, "proposed")

    def _readout(self, *lines: str) -> str:
        return "".join(f"> {line}\n" for line in lines)

    def _line(self, name: str, status: str, *, number: str | None = None) -> str:
        if number is None:
            number = name.split("-")[1]
        return f"**DR-{number}** (`spec/decision-records/{name}`) is **{status}**."

    def _truthful(self) -> str:
        return self._readout(
            self._line("DR-003-numeric-spec-derivation.md", "accepted"),
            self._line(self.ENOB, "proposed"),
        )

    def test_a_truthful_readout_passes(self):
        self.assertEqual(self.tree.check(self._truthful()), [])

    def test_the_readout_survives_a_prose_line_wrap(self):
        """Real lines are long enough that the document must wrap them.

        A check that only matched an unwrapped line would be vacuous against
        the real document, where every path is ~60 characters on its own.
        """
        wrapped = (
            "> **DR-003**\n"
            "> (`spec/decision-records/DR-003-numeric-spec-derivation.md`)\n"
            "> is **accepted**.\n"
            f"> **DR-007** (`spec/decision-records/{self.ENOB}`)\n"
            "> is **proposed**.\n"
        )
        self.assertEqual(self.tree.check(wrapped), [])

    def test_a_status_that_moved_is_reported(self):
        """The defect this check exists for: the record ratifies, prose doesn't.

        `spec/target-spec.md` is deliberately left untouched here, so check 7
        stays green -- the whole point is that no other check can see this.
        """
        self.tree.add_decision_record(self.ENOB, "accepted")
        misses = self.tree.check(self._truthful())
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("**proposed**", misses[0])
        self.assertIn("**accepted**", misses[0])
        self.assertIn(self.ENOB, misses[0])

    def test_a_record_with_no_stated_line_is_reported(self):
        """Both directions: dropping the line for the record that moved."""
        self.tree.add_decision_record(self.NWELL, "accepted")
        misses = self.tree.check(self._truthful())
        reported = [miss for miss in misses if "states no decision-record status" in miss]
        self.assertEqual(len(reported), 1, misses)
        self.assertIn(self.NWELL, reported[0])

    def test_a_line_naming_a_record_this_repo_does_not_carry_is_reported(self):
        misses = self.tree.check(
            self._truthful() + self._readout(self._line("DR-042-invented.md", "accepted"))
        )
        reported = [miss for miss in misses if "does not carry" in miss]
        self.assertEqual(len(reported), 1, misses)
        self.assertIn("--stats", reported[0])

    def test_a_number_paired_with_the_wrong_file_is_reported(self):
        """Two DR-004s and two DR-007s make this a live defect shape here."""
        misses = self.tree.check(
            self._readout(
                self._line("DR-003-numeric-spec-derivation.md", "accepted"),
                self._line(self.ENOB, "proposed", number="003"),
            )
        )
        reported = [miss for miss in misses if "that file's own number is" in miss]
        self.assertEqual(len(reported), 1, misses)
        self.assertIn("**DR-003**", reported[0])

    def test_a_record_stating_no_status_field_is_reported_not_matched(self):
        self.tree.add_decision_record(self.ENOB, None)
        misses = self.tree.check(self._truthful())
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("states no `- **Status**:` field", misses[0])

    def test_colliding_numbers_that_disagree_are_reported_for_bare_references(self):
        """A bare `DR-007` is unresolvable once the two DR-007s disagree."""
        self.tree.add_decision_record(self.NWELL, "accepted")
        misses = self.tree.check(
            self._truthful()
            + self._readout(self._line(self.NWELL, "accepted"))
            + "\nUntil DR-007 ratifies, those rows stay informational.\n"
        )
        reported = [miss for miss in misses if "by bare number" in miss]
        self.assertEqual(len(reported), 1, misses)
        self.assertIn(self.ENOB, reported[0])
        self.assertIn(self.NWELL, reported[0])

    def test_colliding_numbers_that_agree_are_not_reported(self):
        """The collision is only a defect once the statuses diverge.

        Both DR-007s are `proposed` in the real tree today, so firing here
        would force a document-wide rewrite for a harmless collision.
        """
        self.tree.add_decision_record(self.NWELL, "proposed")
        misses = self.tree.check(
            self._truthful()
            + self._readout(self._line(self.NWELL, "proposed"))
            + "\nUntil DR-007 ratifies, those rows stay informational.\n"
        )
        self.assertEqual(misses, [])

    def test_a_bare_number_with_no_local_record_is_not_reported(self):
        """`DR-002` is a tripwire clause; `DR-0005` is the sibling repo's."""
        misses = self.tree.check(
            self._truthful()
            + "\nA higher rail would trip the ratified DR-002 tripwire, and no\n"
            "interface-scope record like `gf180-sar-adc`'s DR-0005 exists here.\n"
        )
        self.assertEqual(misses, [])

    def test_the_template_is_not_a_record(self):
        """Excluded by its file-name shape, not by a name list.

        Its own Status field is a vocabulary enumeration rather than a status,
        so counting it would demand a readout line for a value that is not one.
        """
        (self.tree.root / "spec" / "decision-records" / "TEMPLATE.md").write_text(
            "- **Status**: proposed | ratified | superseded by DR-NNN\n"
        )
        self.assertEqual(self.tree.check(self._truthful()), [])
        self.assertNotIn("TEMPLATE.md", checker.decision_records())

    def test_a_document_stating_no_readout_is_not_failed_for_it(self):
        self.assertEqual(self.tree.check("no decision-record statuses stated\n"), [])

    def test_a_tree_with_no_decision_records_is_inert_for_a_silent_document(self):
        """Absent source data plus no stated readout is not a finding.

        This is what keeps check 15 inert against every other fixture in this
        file, none of which builds a `spec/decision-records/` tree.
        """
        empty = FixtureTree(self)
        self.assertEqual(checker.decision_records(), {})
        doc = empty.document("Section 7 mentions no decision records.\n")
        self.assertEqual(checker.check_decision_record_status(doc, doc.read_text()), [])

    def test_a_readout_stated_against_an_absent_tree_is_reported(self):
        """Reported, not silently skipped -- the same rule as checks 13 and 14.

        A document that states a status for a record this repository does not
        carry has made a claim nothing can support; skipping it would let the
        readout survive the directory being renamed or emptied.
        """
        empty = FixtureTree(self)
        doc = empty.document(self._truthful())
        misses = checker.check_decision_record_status(doc, doc.read_text())
        self.assertEqual(len(misses), 2, misses)
        self.assertTrue(all("does not carry" in miss for miss in misses), misses)

    def test_only_the_status_word_is_read_not_the_rationale_after_it(self):
        self.tree.add_decision_record(
            self.ENOB, "proposed — accepted by nobody, ratified by nothing"
        )
        self.assertEqual(self.tree.check(self._truthful()), [])

    def test_stats_sentence_round_trips_through_the_checker(self):
        """`--stats` output must be pasteable: what it prints must pass."""
        stated = "".join(
            f"> {checker.decision_record_sentence(name, status)}\n"
            for name, status in checker.decision_records().items()
        )
        self.assertEqual(self.tree.check(stated), [])


class TestErcReadout(unittest.TestCase):
    """Check 16: a stated ERC supply readout must be the current record's own.

    The second evidence tree a `layout/` flow keeps, and the one no earlier
    check can reach: `EVIDENCE_PATH_RE` matches `records|reports` only, so
    `layout/<block>/erc-reports/<stamp>/` is invisible to checks 3 and 4
    however the document cites it. Section 7 item 9's per-supply island table
    was hand-transcribed once against a failing run (2026-09-23) and
    re-transcribed by hand when issue #355 moved every number in it
    (2026-09-24) -- the drift shape this check turns into a CI failure.
    """

    BLOCK = "sar-adc-top"
    LAYOUT = "20260924-190817-f3622fc"
    OLDER = "20260923-131726-fa1e0af"
    ERC = "20260924-190825-f3622fc"
    SUPPLIES = {"VDD": 1, "GND": 1, "VPWR": 1, "VGND": 1}

    def setUp(self):
        self.tree = FixtureTree(self)
        self.tree.add_layout_record(
            self.BLOCK, self.OLDER, gds={"sar_adc_top": b"older stream"}
        )
        self.tree.add_layout_record(
            self.BLOCK, self.LAYOUT, latest=True, gds={"sar_adc_top": b"graded stream"}
        )

    def _erc(self, **kwargs):
        options = {
            "latest": True,
            "graded": self.LAYOUT,
            "supplies": dict(self.SUPPLIES),
        }
        options.update(kwargs)
        self.tree.add_erc_record(self.BLOCK, self.ERC, **options)

    def _readout(self, **overrides) -> str:
        stated = {
            "erc_status": "clean",
            "finding_count": 0,
            "supplies": dict(self.SUPPLIES),
            "graded": self.LAYOUT,
            "latest": self.LAYOUT,
            "status": "current",
        }
        stated.update(overrides)
        islands = ", ".join(
            f"`{net}` **{count}**" for net, count in sorted(stated["supplies"].items())
        )
        return (
            f"> on the record `layout/{self.BLOCK}/erc-reports/LATEST` resolves to,\n"
            f"> `klt erc` reports `erc_status` **{stated['erc_status']}** with\n"
            f"> **{stated['finding_count']}** findings; the declared supplies resolve\n"
            f"> to {islands} electrical islands; and it grades\n"
            f"> `{stated['graded']}`, while `reports/LATEST` there names\n"
            f"> `{stated['latest']}`: **{stated['status']}**.\n"
        )

    def test_a_truthful_readout_passes(self):
        """Also the wrap test: the fixture readout is set across six lines.

        A check that only matched an unwrapped sentence would be vacuous
        against the real document, where this sentence cannot fit on one line.
        """
        self._erc()
        self.assertEqual(self.tree.check(self._readout()), [])

    def test_an_island_count_that_moved_is_reported(self):
        """The 2026-09-24 defect shape: the layout moved, the table did not."""
        self._erc(supplies={"VDD": 1, "GND": 1, "VPWR": 2, "VGND": 2}, erc_status="violations")
        misses = self.tree.check(self._readout())
        stated = [miss for miss in misses if "island(s)" in miss]
        self.assertEqual(len(stated), 2, misses)
        self.assertTrue(any("`VPWR`" in miss for miss in stated), stated)
        self.assertTrue(any("`VGND`" in miss for miss in stated), stated)

    def test_a_supply_dropped_from_the_readout_is_reported(self):
        """Both directions: shrinking the table is not a way to keep it clean."""
        self._erc()
        thinned = dict(self.SUPPLIES)
        del thinned["VGND"]
        misses = self.tree.check(self._readout(supplies=thinned))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("`VGND`", misses[0])
        self.assertIn("at None island(s)", misses[0])

    def test_a_supply_the_run_never_graded_is_reported(self):
        """The other direction: a net stated but absent from the coverage list."""
        self._erc(supplies={"VDD": 1, "GND": 1, "VPWR": 1})
        misses = self.tree.check(self._readout())
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("`VGND`", misses[0])

    def test_a_moved_status_word_is_reported(self):
        self._erc(erc_status="violations")
        misses = self.tree.check(self._readout())
        reported = [miss for miss in misses if "erc_status" in miss]
        self.assertEqual(len(reported), 1, misses)

    def test_a_layout_rerun_without_a_fresh_erc_run_goes_stale(self):
        """The record's own staleness rule, which nothing else evaluates.

        `run-flow.sh` mints a new `reports/<id>/`; until `run-erc.sh` runs
        again the committed ERC verdict grades bytes that are no longer this
        flow's current layout, and the document's supply table is about a
        superseded stream.
        """
        self._erc(graded=self.OLDER)
        self.assertEqual(
            self.tree.check(self._readout(graded=self.OLDER, status="stale")), []
        )
        misses = self.tree.check(self._readout(graded=self.OLDER))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("status=current", misses[0])
        self.assertIn("status=stale", misses[0])

    def test_a_layout_rebuilt_under_the_erc_record_goes_stale(self):
        """The half a stamp comparison alone would miss.

        Same stamp, different bytes: the ERC verdict is about a stream this
        repository no longer carries, and only the content hash shows it.
        """
        self._erc(content_hash="sha256:" + "b" * 64)
        misses = self.tree.check(self._readout())
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("status=stale", misses[0])

    def test_a_readout_for_a_flow_with_no_erc_record_is_reported(self):
        """Not silently skipped: a readout must outlive its own evidence.

        Check 2 reports the unresolvable pointer path as well, which is
        correct and not what this test is about -- check 16's own finding is
        asserted, rather than the total count, so the two do not fight.
        """
        misses = self.tree.check(self._readout())
        reported = [miss for miss in misses if "the ERC supply readout names" in miss]
        self.assertEqual(len(reported), 1, misses)
        self.assertIn("erc-reports/LATEST", reported[0])

    def test_a_document_stating_no_readout_is_not_failed_for_it(self):
        self._erc()
        self.assertEqual(self.tree.check("No ERC readout here.\n"), [])

    def test_stats_sentence_round_trips_through_the_checker(self):
        """What `--stats` prints must be what the document can paste."""
        self._erc()
        readout = checker.erc_readout(self.BLOCK)
        sentence = checker.erc_sentence(self.BLOCK, readout)
        self.assertEqual(self.tree.check(f"> {sentence}\n"), [])


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

    def test_stamped_currency_claims_are_evaluated_on_the_real_document(self):
        """Guard against check 23 going vacuous against the live document.

        The claim shape it grades is prose, not a table cell: a pass that
        rewords Section 3's `klt erc` bullet or Section 7 item 9 away from
        "the current run, <record>" would leave check 23 inert with nothing
        failing, exactly as the `CONNECTOR_RE` defect left check 4 inert
        above. Both of those passages carry an `erc-reports/` citation that
        checks 3/4 structurally cannot see, so nothing else would notice.
        """
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        text = doc.read_text()
        attached = checker.attached_currency_citations(text)
        self.assertGreaterEqual(
            len(attached),
            2,
            "check 23 evaluates almost nothing in this document",
        )
        trees = {records[0].group("tree") for _claim, _citation, records in attached}
        self.assertIn(
            "erc-reports",
            trees,
            "check 23 no longer reaches the `erc-reports/` tree -- the one "
            "checks 3/4 cannot see, and the one its own defect came from",
        )

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

    def test_the_real_proposal_states_a_parseable_freshness_coverage_census(self):
        """Check 18 is opt-in per document too, so assert the real one opts in.

        Deleting the sentence would disable the check silently and still exit
        0 -- the same vacuity trap check 4's dead connector branch fell into,
        and the reason check 6 carries the assertion above.
        """
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        collapsed, _ = checker._collapse_quoted_prose(doc.read_text())
        self.assertIsNotNone(
            checker.FRESHNESS_COVERAGE_RE.search(collapsed),
            "the proposal no longer states a freshness-coverage census check 18 "
            "can verify",
        )

    def test_check_18_grades_a_nonempty_set_of_the_real_documents_pairs(self):
        """A census over zero pairs would be a green that means nothing.

        Check 18's whole subject is Section 4's citation pairs; if the table
        scoping or `EVIDENCE_PATH_RE` ever stopped matching, the stated census
        would collapse to 0/0/0 and the document could be restated to match it
        while saying nothing at all.
        """
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        coverage = checker.freshness_coverage(doc.read_text())
        self.assertGreaterEqual(
            coverage["pairs"], 10, "Section 4's citation pairs went unparsed"
        )
        self.assertEqual(
            coverage["pairs"], coverage["graded"] + coverage["ungraded"], coverage
        )
        # Every flow the census names must really publish no pointer, and hold
        # at least one record -- otherwise the list is naming a flow that does
        # not exist rather than one this gate cannot grade.
        for flow, records in coverage["flows"]:
            with self.subTest(flow=flow):
                top, block = flow.split("/", 1)
                self.assertIsNone(checker._pointer_stamp(top, block))
                self.assertGreaterEqual(records, 1)

    def test_the_real_proposal_states_parseable_check_19_sentences(self):
        """Check 19's parts (b) and (c) are opt-in, so assert the real one opts in.

        Deleting either sentence would disable that half of the check silently
        and still exit 0 -- the same vacuity trap checks 6 and 18 carry an
        assertion for.
        """
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        section = checker.test_plan_section(doc.read_text())
        self.assertIsNotNone(section, "Section 5 went unparsed")
        flat = re.sub(r"\s+", " ", section[1])
        self.assertIsNotNone(
            checker.TEST_PLAN_SUPPLIES_RE.search(flat),
            "Section 5 no longer states a supply-terminal list check 19 can verify",
        )
        self.assertIsNotNone(
            checker.TEST_PLAN_POWER_RE.search(flat),
            "Section 5 no longer states a power-term list check 19 can verify",
        )

    def test_check_19_grades_the_real_documents_whole_interface(self):
        """A check over zero ports, zero rails or zero power terms means nothing."""
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        text = doc.read_text()
        ports = checker.netlist_ports()
        self.assertGreaterEqual(len(ports), 20, "the top-level port list went unparsed")
        rails = checker.rail_ports(text)
        # Every rail must be a real port, and the rails must be a strict subset
        # of them -- a rail set that swallowed the whole table would make part
        # (b) tautological.
        self.assertTrue(rails, "Section 2's rail rows went unparsed")
        self.assertTrue(rails < set(ports), sorted(rails))
        terms = checker.record_power_terms("full-conversion-transient")
        self.assertGreaterEqual(len(terms), 2, "the Power table's columns went unparsed")
        # The defect check 19 part (c) exists for: `VDD` alone is not the sum.
        self.assertIn("VDD", terms)
        self.assertIn("VPWR", terms)

    def test_the_real_proposal_states_parseable_check_20_sentences(self):
        """Check 20's three sentences are opt-in, so assert the real one opts in.

        Deleting any of them would disable that part of the check silently and
        still exit 0 -- the same vacuity trap checks 6, 18 and 19 each carry an
        assertion for.
        """
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        flat, _offsets = checker._collapse_quoted_prose(doc.read_text())
        for name, pattern in (
            ("Section 1's primitive-flavour inventory", checker.PRIMITIVE_INVENTORY_RE),
            ("Section 3's standard-cell glue census", checker.GLUE_CELL_CENSUS_RE),
            ("Section 3's top-level primitive census", checker.GLUE_PRIMITIVE_CENSUS_RE),
        ):
            with self.subTest(sentence=name):
                self.assertIsNotNone(
                    pattern.search(flat),
                    f"the proposal no longer states {name}, which check 20 grades",
                )

    def test_check_20_grades_a_nonempty_inventory_of_the_real_netlist(self):
        """A census over zero cells, or over the whole file, would mean nothing."""
        netlist = checker.top_netlist_text()
        self.assertTrue(netlist, "design/sar_adc_top.spice went unread")
        flavours = checker.cell_census(
            checker._netlist_instance_lines(netlist), "pr"
        )
        # The ratified set DR-001 gates and design/regen_netlist.sh enforces.
        self.assertEqual(
            sorted(flavours), ["cap_mim_m3_1", "nfet_01v8", "pfet_01v8"], flavours
        )
        glue = checker.top_level_glue(netlist)
        self.assertTrue(glue.strip(), "the top-level region went unparsed")
        top_cells = checker.cell_census(glue, "sc_hd")
        whole = checker.cell_census(
            checker._netlist_instance_lines(netlist), "sc_hd"
        )
        self.assertTrue(top_cells, "the top-level glue census is empty")
        # A region that swallowed the sub-blocks would make part (b)'s scope
        # claim ("outside every sub-block") false while still passing: the
        # sequencer's own standard cells must NOT be in it.
        self.assertIn("dfrtp_1", whole)
        self.assertNotIn("dfrtp_1", top_cells)
        self.assertLess(sum(top_cells.values()), sum(whole.values()))
        # The DR-008 shape this check exists for: eighteen decision-directed
        # AND gates at the top level, and no `SELn<i>` inverter bank behind them.
        self.assertEqual(top_cells.get("and2_1"), 18, top_cells)
        self.assertNotIn("xinv_seln0", glue)

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

        Deleting or re-wording a readout sentence would disable check 9 for
        that flow and still exit 0 -- the same vacuity trap checks 4, 6 and 8
        each needed a guard for. The flows asserted are every one this
        design's sign-off rests on: the composed top level the brief's two
        sign-off-bar rows are graded on (Section 4), and the five sub-blocks
        that composition is built from (Section 3), whose own "DRC-clean and
        LVS-clean" verdicts were prose until 2026-09-17.

        Asserted as a set with an explicit expected membership, not merely a
        non-empty list: a sub-block flow whose readout is dropped is exactly
        the regression this guards, and a *new* sub-block flow gaining a
        readout should be a deliberate edit here rather than a silent pass.
        """
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        collapsed, _offsets = checker._collapse_quoted_prose(doc.read_text())
        stated = [
            match.group("flow")
            for match in checker.READOUT_RE.finditer(collapsed)
        ]
        self.assertEqual(
            sorted(stated),
            [
                "layout/cdac-array",
                "layout/comparator",
                "layout/sampling-frontend",
                "layout/sar-adc-top",
                "layout/sar-sequencer",
                "layout/seln-inverters",
            ],
            stated,
        )
        self.assertEqual(len(stated), len(set(stated)), f"a flow is stated twice: {stated}")

    def test_every_stated_signoff_readout_is_backed_by_real_verdict_files(self):
        """The record side of check 9 must be readable for every stated flow.

        `signoff_readout` returns None when a flow's current record carries no
        `drc.json`/`lvs.json`; check 9 then reports one generic finding
        instead of comparing field by field, which would make a whole flow's
        readout unenforced while CI stayed green on the real tree.
        """
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        collapsed, _offsets = checker._collapse_quoted_prose(doc.read_text())
        flows = [
            match.group("flow").split("/", 1)[1]
            for match in checker.READOUT_RE.finditer(collapsed)
        ]
        self.assertTrue(flows, "the document states no readout at all")
        for flow in flows:
            readout = checker.signoff_readout(flow)
            self.assertIsNotNone(readout, f"{flow} has no current klt verdict files")
            self.assertIn(readout["drc_status"], ("clean", "violations"), flow)
            self.assertIn(readout["lvs_status"], ("match", "mismatch"), flow)

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

    def test_the_real_coverage_index_really_tracks_decision_records(self):
        """Check 22 is opt-in per row, so assert at least one row opts in.

        The `tracking` field is free prose and optional; if every row dropped
        its `DR-<n>` tokens -- or the field were renamed -- check 22 would go
        inert and its green would mean nothing was compared. It is the Kickback
        row that carries them today, because DR-014 repointed that field onto
        itself and #390 when it closed #349.
        """
        tracked = checker.coverage_index_tracking()
        self.assertTrue(tracked, "no indexed row tracks a decision record")
        by_parameter = dict(tracked)
        self.assertIn("Kickback", by_parameter)
        self.assertIn("DR-014", by_parameter["Kickback"])

    def test_every_tracked_record_is_named_by_its_own_section_4_row(self):
        """The positive form of check 22 on the live document."""
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        rows = {
            checker._normalise_parameter(cells[0]): " | ".join(cells)
            for _line, cells in checker.section_4_table(doc.read_text())[1]
        }
        compared = 0
        for parameter, records in checker.coverage_index_tracking():
            row = rows.get(parameter)
            self.assertIsNotNone(row, f"{parameter} has no Section 4 row")
            for record in records:
                self.assertRegex(row, rf"{record}(?!\d)", parameter)
                compared += 1
        self.assertGreaterEqual(compared, 3, "check 22 compared almost nothing")

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

    def test_the_real_proposal_states_a_parseable_area_readout(self):
        """Check 13 is opt-in per row, so assert the real Area row opts in.

        Deleting or re-wording the readout would disable check 13 and still
        exit 0 -- the same vacuity trap every opt-in check here needs a guard
        for. The flow is asserted by name too: a readout silently re-pointed
        at some other composition would gate the wrong extent.
        """
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        stated = [
            (
                checker._normalise_parameter(checker._row_cells(row)[0]),
                checker.AREA_READOUT_RE.search(row).group("flow"),
            )
            for _line, row in checker.spec_table_rows(doc.read_text())
            if checker.AREA_READOUT_RE.search(row)
        ]
        self.assertEqual(stated, [("Area", "layout/sar-adc-top")], stated)

    def test_the_real_area_readout_is_checked_against_a_real_composition(self):
        """The record side of check 13 must be readable, not silently absent.

        `area_readout` returns None when the flow's current record carries no
        `compose.json` with a top-level `bbox_um`; on the real tree that would
        turn every field comparison into one generic finding instead of a
        per-field one.
        """
        readout = checker.area_readout("sar-adc-top")
        self.assertIsNotNone(readout, "sar-adc-top's current record has no composition")
        self.assertEqual(readout["cell"], "gen_compose_0")
        self.assertGreater(readout["width"], 0.0)
        self.assertGreater(readout["height"], 0.0)
        # The composed top level is a real ADC, not a test cell: a box that
        # has collapsed to a few microns, or grown past a reticle, is a
        # misparse rather than a design change.
        self.assertGreater(readout["area_mm2"], 0.001)
        self.assertLess(readout["area_mm2"], 10.0)

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

    def test_the_real_proposal_states_every_composed_input(self):
        """Check 14 is opt-in per input, so assert the real document opts in.

        A document that states none is not failed by check 14 (that is what
        keeps it inert against a document with no composition), so a pass that
        deleted the readouts would disable the check and still exit 0 -- and
        deleting exactly the *superseded* line is the cheat the both-directions
        arm exists for. Both sides are asserted here: every composed input has
        a line, and every line names an input the composition really embeds.
        """
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        collapsed, _offsets = checker._collapse_quoted_prose(doc.read_text())
        stated = {
            claim.group("cell"): claim.group("flow")
            for claim in checker.COMPOSITION_INPUT_RE.finditer(collapsed)
        }
        composed = checker.composition_inputs("sar-adc-top")
        self.assertIsNotNone(composed, "sar-adc-top's current record has no composition")
        self.assertEqual(sorted(stated), sorted(composed), stated)
        # Each input is attributed to its own flow, not to the composition it
        # sits in -- `layout/sar-adc-top/`'s own older records hold copies of
        # exactly these files, so a self-attribution would always "match".
        for cell, flow in stated.items():
            self.assertNotEqual(flow, "layout/sar-adc-top", cell)

    def test_the_real_composed_inputs_are_distinguishable_by_fingerprint(self):
        """The record side of check 14 must be readable and discriminating.

        Two failure modes would both leave the check green: a fingerprint that
        cannot read these files (every input then reports as unreadable), and
        one that collapses different files onto one digest (every input then
        "reproduces" every record). Neither is caught by the document side.
        """
        stamp = checker._pointer_stamp("layout", "sar-adc-top")
        self.assertIsNotNone(stamp)
        report = REPO_ROOT / "layout" / "sar-adc-top" / "reports" / stamp
        fingerprints = {}
        for cell in checker.composition_inputs("sar-adc-top") or []:
            fingerprint = checker._gds_fingerprint(report / f"{cell}.gds")
            self.assertIsNotNone(fingerprint, cell)
            fingerprints[cell] = fingerprint
        self.assertGreater(len(fingerprints), 1)
        self.assertEqual(
            len(set(fingerprints.values())), len(fingerprints), "digests collapsed"
        )


    def test_the_real_proposal_states_every_decision_record_status(self):
        """Check 15 is opt-in per document, so assert the real document opts in.

        A document that states no readout is not failed by check 15 (that is
        what keeps it inert against a fixture with no `spec/decision-records/`),
        so a pass that deleted the block would disable the check and still exit
        0. Both sides are asserted: every record in the tree has a line, and
        every line names a record the tree really carries.
        """
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        collapsed, _offsets = checker._collapse_quoted_prose(doc.read_text())
        stated = {
            claim.group("file"): claim.group("status")
            for claim in checker.DECISION_RECORD_READOUT_RE.finditer(collapsed)
        }
        records = checker.decision_records()
        self.assertTrue(records, "spec/decision-records/ carries no records")
        self.assertEqual(sorted(stated), sorted(records), stated)

    def test_the_real_decision_records_all_state_a_readable_status(self):
        """The record side of check 15 must be readable, not silently absent.

        `decision_record_status` returns None when a record states no Status
        field; on the real tree that would turn a status comparison into one
        generic finding. The vocabulary is asserted too -- an unexpected word
        means the field was misparsed, since this repo only moves a record
        between these three states.
        """
        records = checker.decision_records()
        for name, status in records.items():
            with self.subTest(record=name):
                self.assertIsNotNone(status, name)
                self.assertIn(status, ("proposed", "accepted", "superseded"), name)
        # The trail this document's verdicts rest on: DR-003 is what ratified
        # the numeric rows Section 4 grades against, and DR-007 is what Section
        # 7 Item 4 is waiting on. A parser that read every record as the same
        # word would pass every test above.
        self.assertEqual(records["DR-003-numeric-spec-derivation.md"], "accepted")
        self.assertEqual(records["DR-007-revised-enob-inl-dnl-targets.md"], "proposed")

    def test_the_real_tree_really_carries_colliding_decision_record_numbers(self):
        """The collision arm is not defensive programming -- it is this tree.

        Two DR-004s and two DR-007s, which is why check 15 compares the stated
        number against the file's own and reports a bare reference once a
        colliding pair's statuses diverge.
        """
        numbers = {}
        for name in checker.decision_records():
            number = checker.DECISION_RECORD_FILE_RE.fullmatch(name).group("number")
            numbers.setdefault(number, []).append(name)
        collisions = {n: names for n, names in numbers.items() if len(names) > 1}
        self.assertEqual(sorted(collisions), ["004", "007"], collisions)

    def test_the_real_proposal_states_a_parseable_erc_readout(self):
        """Check 16 is opt-in per document, so assert the real document opts in.

        A document that states no ERC readout is not failed by check 16 (that
        is what keeps it inert against a fixture with no `erc-reports/` tree),
        so a pass that deleted the sentence would disable the check and still
        exit 0.
        """
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        collapsed, _offsets = checker._collapse_quoted_prose(doc.read_text())
        stated = list(checker.ERC_READOUT_RE.finditer(collapsed))
        self.assertEqual(len(stated), 1, "the proposal states no ERC supply readout")

    def test_the_real_erc_readout_is_checked_against_a_real_record(self):
        """The record side must be readable, and it must grade real bytes.

        Three assertions, because each half of check 16 can go vacuous on its
        own: the flow has an `erc-reports/LATEST`, that record names the
        supplies this block declares, and the verdict word is computed from a
        layout stream that really exists (a `stale` produced by an unreadable
        file would be indistinguishable from one produced by a real re-run).
        """
        readout = checker.erc_readout("sar-adc-top")
        self.assertIsNotNone(readout, "layout/sar-adc-top/ has no ERC record")
        self.assertEqual(
            sorted(readout["islands"]), ["GND", "VDD", "VGND", "VPWR"], readout
        )
        self.assertIsNotNone(readout["graded"], readout)
        stream = (
            REPO_ROOT
            / "layout"
            / "sar-adc-top"
            / "reports"
            / readout["graded"]
            / "sar_adc_top.gds"
        )
        self.assertTrue(stream.is_file(), stream)

    def test_the_real_erc_tree_is_invisible_to_the_earlier_freshness_checks(self):
        """Why check 16 exists at all, re-derived rather than asserted in prose.

        `EVIDENCE_PATH_RE` matches `records|reports` only. If a future change
        widened it to cover `erc-reports/` too, check 3's spec-row freshness
        would start grading ERC citations under a `layout/<block>/` flow key
        that has no `reports/LATEST` relationship to them -- so this is a
        tripwire on the assumption check 16 is built on, not decoration.
        """
        cited = "layout/sar-adc-top/erc-reports/20260924-190825-f3622fc/record.md"
        self.assertIsNone(checker.EVIDENCE_PATH_RE.search(cited), cited)

    def test_the_real_proposal_states_a_parseable_t1_readout(self):
        """Check 17 is opt-in per document, so assert the real document opts in.

        A document that states no T1 readout is not failed by check 17 (that
        is what keeps it inert against a fixture with no `signoff/` pair), so
        a pass that deleted the sentence would disable the check and still
        exit 0.
        """
        doc = CHIPALOOZA_DIR / "challenge-4-proposal.md"
        collapsed, _offsets = checker._collapse_quoted_prose(doc.read_text())
        stated = list(checker.T1_READOUT_RE.finditer(collapsed))
        self.assertEqual(len(stated), 1, "the proposal states no T1 sign-off readout")

    def test_the_real_t1_readout_is_checked_against_a_real_record(self):
        """The record side must be readable, and it must cite real evidence.

        A `stale`/`None` produced by an unreadable `signoff/` pair is
        otherwise indistinguishable from one produced by real drift -- so
        both halves are asserted here, not just the document's prose side.
        """
        readout = checker.t1_readout()
        self.assertIsNotNone(
            readout, "signoff/t1-report.json and signoff/block-manifest.json "
            "have no readable T1 verdict"
        )
        self.assertTrue(readout["cited"], readout)


class TestT1Readout(unittest.TestCase):
    """Check 17: a stated T1 sign-off readout must be the committed report's own.

    The third evidence tree, and the first that is not a `layout/` flow's at
    all. `signoff/t1-report.json` is this repo's T1 verdict of record (issue
    #345), and no earlier check can see it: it is neither a `records/`/
    `reports/` path (checks 3, 4) nor an `erc-reports/` one (check 16).
    Section 7 item 9 quoted two of its twenty-two rows by hand -- the drift
    shape this check turns into a CI failure, one tree over from where the
    gate was already guarding.
    """

    BLOCK = "sar-adc-top"
    LAYOUT = "20260924-190817-f3622fc"
    OLDER = "20260923-131726-fa1e0af"
    ERC = "20260924-190825-f3622fc"
    REPORTS = f"layout/{BLOCK}/reports/LATEST"
    ERC_REPORTS = f"layout/{BLOCK}/erc-reports/LATEST"
    FAILED = [(4, "analog"), (4, "digital"), (11, "analog"), (11, "digital")]

    def setUp(self):
        self.tree = FixtureTree(self)
        self.tree.add_layout_record(self.BLOCK, self.OLDER)
        self.tree.add_layout_record(self.BLOCK, self.LAYOUT, latest=True)
        self.tree.add_erc_record(self.BLOCK, self.ERC, latest=True, graded=self.LAYOUT)

    def _items(self, failed=None) -> list[dict]:
        """The report's own item list: three met, four graded-and-failed."""
        rows = [
            {"id": 3, "partition": "analog", "status": "met"},
            {"id": 3, "partition": "digital", "status": "met"},
            {"id": 8, "partition": "analog", "status": "met"},
            {"id": 8, "partition": "digital", "reason": "no_evidence"},
        ]
        for item, partition in self.FAILED if failed is None else failed:
            rows.append(
                {"id": item, "partition": partition, "reason": "check_failed"}
            )
        # The tier rows `klt signoff` renders with no partition at all: they
        # carry a reason of their own and must not be read as T1 items.
        rows.append({"id": None, "partition": None, "reason": "tier_not_supported"})
        return rows

    def _evidence(self, layout: str | None = None, erc: str | None = None) -> dict:
        """The manifest's evidence tree, in both shapes the real one uses."""
        layout = layout or self.LAYOUT
        erc = erc or self.ERC
        return {
            "3": {"file": f"layout/{self.BLOCK}/reports/{layout}/drc.json"},
            "4": {"file": f"layout/{self.BLOCK}/reports/{layout}/lvs.json"},
            "11": [
                {"file": f"layout/{self.BLOCK}/erc-reports/{erc}/erc.json"},
                {"file": f"layout/{self.BLOCK}/reports/{layout}/lvs.json"},
            ],
            "8.analog": {"file": "signoff/evidence/characterization.generic.json"},
        }

    def _signoff(self, **kwargs):
        options = {"items": self._items(), "evidence": self._evidence()}
        options.update(kwargs)
        self.tree.add_signoff(**options)

    def _readout(self, **overrides) -> str:
        stated = {
            "version": "0.6.0",
            "met": 3,
            "total": 22,
            "tier": "none",
            "failed": list(self.FAILED),
            "cited": [
                (self.ERC_REPORTS, self.ERC, self.ERC),
                (self.REPORTS, self.LAYOUT, self.LAYOUT),
            ],
            "status": "current",
        }
        stated.update(overrides)
        failed = (
            ", ".join(f"`{item} {part}`" for item, part in stated["failed"])
            or "**none**"
        )
        cited = (
            ", ".join(
                f"`{pointer}` at **{stamp}** against a pointer naming **{latest}**"
                for pointer, stamp, latest in stated["cited"]
            )
            or "**none**"
        )
        return (
            "> on the report `signoff/t1-report.json`, `klt signoff`\n"
            f"> **{stated['version']}** grades **{stated['met']}** of\n"
            f"> **{stated['total']}** T1 items met, block tier\n"
            f"> **{stated['tier']}**; the items whose cited evidence was read\n"
            f"> and still failed are {failed}; and its manifest cites\n"
            f"> {cited}: **{stated['status']}**.\n"
        )

    def test_a_truthful_readout_passes(self):
        """Also the wrap test: the fixture readout is set across six lines."""
        self._signoff()
        self.assertEqual(self.tree.check(self._readout()), [])

    def test_a_met_count_that_moved_is_reported(self):
        self._signoff(met=4)
        misses = self.tree.check(self._readout())
        reported = [miss for miss in misses if "met=" in miss]
        self.assertEqual(len(reported), 1, misses)

    def test_a_grader_version_bump_is_reported(self):
        """The version is part of the verdict: a re-render can move numbers."""
        self._signoff(version="0.7.0")
        misses = self.tree.check(self._readout())
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("version=", misses[0])

    def test_a_tier_award_is_reported(self):
        """`null` renders as `none`, so a real tier appearing is visible."""
        self._signoff(tier="T1")
        misses = self.tree.check(self._readout())
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("tier=", misses[0])

    def test_a_failing_row_outside_t1_is_not_read_as_a_t1_failure(self):
        """The list is scoped to T1, like the `met`/`total` counts beside it."""
        rows = self._items()
        rows.append(
            {"tier": "T2", "id": 19, "partition": "analog", "reason": "check_failed"}
        )
        self._signoff(items=rows)
        self.assertNotIn((19, "analog"), checker.t1_readout()["failed"])
        self.assertEqual(self.tree.check(self._readout()), [])

    def test_a_newly_failing_row_left_out_of_the_readout_is_reported(self):
        """Both directions: shrinking the list is not a way to keep it clean."""
        self._signoff(items=self._items(failed=self.FAILED + [(7, "analog")]))
        misses = self.tree.check(self._readout())
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("omits item 7 (analog)", misses[0])

    def test_a_row_that_has_since_stopped_failing_is_reported(self):
        """The other direction: a listed row the report no longer fails."""
        self._signoff(items=self._items(failed=self.FAILED[:-1]))
        misses = self.tree.check(self._readout())
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("lists item 11 (digital)", misses[0])

    def test_no_evidence_is_not_read_as_graded_and_failed(self):
        """`check_failed` and `no_evidence` are different statements.

        Item 8's digital row is `no_evidence` in every fixture here; a check
        that read "unmet" instead of the reason would enrol it and fail the
        truthful readout.
        """
        self._signoff()
        self.assertEqual(self.tree.check(self._readout()), [])
        self.assertNotIn((8, "digital"), checker.t1_readout()["failed"])

    def test_a_readout_that_states_an_extra_citation_the_manifest_never_made_is_reported(self):
        """The other direction: a stated citation with nothing behind it.

        `test_a_manifest_pinned_to_a_superseded_record_goes_stale` below
        exercises a *mismatched* pair (both a "states" and an "omits" miss
        fire together), which does not catch a mutation that drops the
        "states" arm of the symmetric difference entirely -- narrowing
        `claimed_cited ^ set(actual["cited"])` to `set(actual["cited"]) -
        claimed_cited` still passes it. This fixture adds a citation that has
        no counterpart in `actual["cited"]` at all, so only the "states" arm
        can report it.
        """
        self._signoff()
        extra = (self.REPORTS, "bogus-stamp", "bogus-stamp")
        misses = self.tree.check(
            self._readout(
                cited=[
                    (self.ERC_REPORTS, self.ERC, self.ERC),
                    (self.REPORTS, self.LAYOUT, self.LAYOUT),
                    extra,
                ]
            )
        )
        reported = [
            miss for miss in misses if "states" in miss and "bogus-stamp" in miss
        ]
        self.assertEqual(len(reported), 1, misses)

    def test_a_manifest_pinned_to_a_superseded_record_goes_stale(self):
        """The half `signoff/check_evidence_hashes.py` cannot cover.

        Every cited artefact still hashes perfectly -- the record is
        committed, its bytes unchanged. It is simply not the one
        `reports/LATEST` names any more.
        """
        self._signoff(evidence=self._evidence(layout=self.OLDER))
        stale = self._readout(
            cited=[
                (self.ERC_REPORTS, self.ERC, self.ERC),
                (self.REPORTS, self.OLDER, self.LAYOUT),
            ],
            status="stale",
        )
        self.assertEqual(self.tree.check(stale), [])
        misses = self.tree.check(self._readout())
        self.assertTrue(any("status=stale" in miss for miss in misses), misses)

    def test_a_manifest_citing_no_layout_record_is_not_current(self):
        """A sign-off resting on nothing cannot be current with anything."""
        self._signoff(evidence={"8.analog": {"file": "signoff/evidence/x.json"}})
        self.assertEqual(
            self.tree.check(self._readout(cited=[], status="stale")), []
        )

    def test_a_readout_with_no_committed_signoff_pair_is_reported(self):
        """Not silently skipped: a readout must outlive its own evidence."""
        self.tree.add_signoff(report=False, items=self._items())
        misses = self.tree.check(self._readout())
        reported = [miss for miss in misses if "T1 sign-off readout names" in miss]
        self.assertEqual(len(reported), 1, misses)

    def test_a_document_stating_no_readout_is_not_failed_for_it(self):
        self._signoff()
        self.assertEqual(self.tree.check("No T1 readout here.\n"), [])

    def test_stats_sentence_round_trips_through_the_checker(self):
        """What `--stats` prints must be what the document can paste."""
        self._signoff()
        sentence = checker.t1_sentence(checker.t1_readout())
        self.assertEqual(self.tree.check(f"> {sentence}\n"), [])

    def test_the_erc_tree_is_reachable_from_the_manifest(self):
        """A tripwire on the assumption check 17 is built on.

        `EVIDENCE_PATH_RE` matches `records|reports` only, so an
        `erc-reports/` citation is invisible to checks 3 and 4 -- which is
        exactly why this check walks the manifest with its own pattern. If
        `T1_CITED_PATH_RE` were ever narrowed to match the older one, item
        11's ERC evidence would silently drop out of the freshness verdict.
        """
        cited = f"layout/{self.BLOCK}/erc-reports/{self.ERC}/erc.json"
        self.assertIsNone(checker.EVIDENCE_PATH_RE.match(cited), cited)
        self.assertIsNotNone(checker.T1_CITED_PATH_RE.match(cited), cited)


class TestFreshnessCoverage(unittest.TestCase):
    """Check 18: the stated coverage of check 3 over Section 4 must be real.

    Check 3 grades a row's citation only when the flow it names publishes a
    `LATEST` pointer; a flow that publishes none is skipped, and the cell
    reads exactly like a graded one. The proposal's own summary of the gate
    said "every row of the table above cites the *current* record of each
    `sim/`/`layout/` flow it draws on" while 7 of its 21 (row, flow) pairs
    were not graded at all -- the same prose-overstates-the-gate shape check 6
    exists for, one table over.

    The load-bearing fixtures here are the two directions: a pointerless flow
    left OUT of the stated list (the gate reading better than it is) and a
    flow left IN after it starts publishing a pointer.
    """

    GRADED = "20260917-180543-527ec73"
    UNGRADED_A = "20260827-213107-e13bc1e"
    UNGRADED_B = "20260828-022618-f36913e"

    def setUp(self):
        self.tree = FixtureTree(self)
        # One graded flow: a `layout/` flow that publishes a pointer.
        self.tree.add_layout_record("cdac-array", self.GRADED, latest=True)
        # One ungraded flow holding two records and no pointer -- the shape
        # that matters, since the row is choosing between them unchecked.
        self.tree.add_sim_record("cdac-array-transfer", self.UNGRADED_A)
        self.tree.add_sim_record("cdac-array-transfer", self.UNGRADED_B)

    def _table(self) -> str:
        return spec_table(
            f"| `V_REF` | 1.8 V | RATIFIED | **MET** | "
            f"`sim/cdac-array-transfer/records/{self.UNGRADED_A}.md` |",
            f"| INL / DNL | ≤ ±2.0 LSB | DRAFT | **Informational only** | "
            f"`sim/cdac-array-transfer/records/{self.UNGRADED_A}.md`; "
            f"`sim/cdac-array-transfer/records/{self.UNGRADED_B}.md` |",
            f"| Sampling cap | 8.65 fF | RATIFIED | **MET** | "
            f"`layout/cdac-array/reports/{self.GRADED}/record.md` |",
        )

    def _sentence(self, pairs, graded, ungraded, flows) -> str:
        rendered = (
            ", ".join(
                f"`{flow}` (**{count}** record{'' if count == 1 else 's'})"
                for flow, count in flows
            )
            or checker.FRESHNESS_NONE
        )
        return (
            f"of the **{pairs}** (spec row, evidence flow) citation pairs in "
            f"Section 4's table, **{graded}** name a flow that publishes a "
            "`LATEST` pointer and are therefore freshness-checked by check 3; "
            f"the remaining **{ungraded}** name a flow that publishes none, "
            f"whose current record nothing grades: {rendered}.\n"
        )

    def _body(self, sentence: str = "") -> str:
        return self._table() + "\n" + sentence

    def test_coverage_of_a_known_table_is_computed_per_row_flow_pair(self):
        """Two rows citing one flow are two pairs; three stamps are not three."""
        coverage = checker.freshness_coverage(self._body())
        self.assertEqual(coverage["pairs"], 3, coverage)
        self.assertEqual(coverage["graded"], 1, coverage)
        self.assertEqual(coverage["ungraded"], 2, coverage)
        self.assertEqual(coverage["flows"], [("sim/cdac-array-transfer", 2)], coverage)

    def test_a_truthful_census_passes(self):
        body = self._body(
            self._sentence(3, 1, 2, [("sim/cdac-array-transfer", 2)])
        )
        self.assertEqual(self.tree.check(body), [])

    def test_an_omitted_ungraded_flow_is_reported(self):
        """The direction that matters: the gate reading better than it is."""
        body = self._body(self._sentence(3, 1, 2, []))
        misses = self.tree.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("omits `sim/cdac-array-transfer`", misses[0])

    def test_a_flow_that_starts_publishing_a_pointer_must_leave_the_list(self):
        # Pointed at the record both rows cite, so the only findings are
        # check 18's -- a check-3 staleness here would mask what this asserts.
        (self.tree.root / "sim" / "cdac-array-transfer" / "records" / "LATEST").write_text(
            f"{self.UNGRADED_A}.md\n"
        )
        body = self._body(
            self._sentence(3, 1, 2, [("sim/cdac-array-transfer", 2)])
        )
        misses = self.tree.check(body)
        self.assertTrue(any("lists `sim/cdac-array-transfer`" in m for m in misses), misses)
        self.assertTrue(any("graded=1" in m and "graded=3" in m for m in misses), misses)

    def test_a_drifted_record_count_is_reported_in_both_directions(self):
        """A stated count that is not the tree's own is two findings, not none."""
        body = self._body(
            self._sentence(3, 1, 2, [("sim/cdac-array-transfer", 1)])
        )
        misses = self.tree.check(body)
        self.assertEqual(len(misses), 2, misses)
        self.assertTrue(any("lists" in m and "**1** record(s)" in m for m in misses), misses)
        self.assertTrue(any("omits" in m and "**2** record(s)" in m for m in misses), misses)

    def test_a_fully_graded_table_renders_and_accepts_none(self):
        # Pointed at the record both rows cite, so check 3 stays quiet and the
        # only thing this test is about is check 18's empty-list rendering.
        (self.tree.root / "sim" / "cdac-array-transfer" / "records" / "LATEST").write_text(
            f"{self.UNGRADED_A}.md\n"
        )
        coverage = checker.freshness_coverage(self._body())
        self.assertEqual(coverage["flows"], [], coverage)
        self.assertIn(
            checker.FRESHNESS_NONE, checker.freshness_coverage_sentence(coverage)
        )
        self.assertEqual(self.tree.check(self._body(self._sentence(3, 3, 0, []))), [])

    def test_the_stats_sentence_is_what_the_check_accepts(self):
        """A `--stats` paste must pass, or the documented fix does not work."""
        body = self._body()
        sentence = checker.freshness_coverage_sentence(checker.freshness_coverage(body))
        self.assertEqual(self.tree.check(body + sentence + "\n"), [])

    def test_a_document_stating_no_census_is_not_failed_for_it(self):
        # Opt-in per document, like check 6: fixtures need not carry one.
        self.assertEqual(self.tree.check(self._body()), [])

    def test_the_sentence_is_not_counted_as_a_pointer_claim(self):
        """It must not enrol itself in check 4/6's census, as check 17's does not."""
        sentence = self._sentence(3, 1, 2, [("sim/cdac-array-transfer", 2)])
        self.assertEqual(checker.pointer_claim_census(sentence)["total"], 0)


def bench_plan(*steps: str, supplies: str = "", power: str = "") -> str:
    """A minimal Section 5 bench plan, with optional gated sentences."""
    parts = ["## 5. Test-plan outline", ""]
    if supplies:
        parts += [supplies, ""]
    if power:
        parts += [power, ""]
    parts += list(steps)
    return "\n".join(parts + ["", "## 6. Next section", ""])


class TestTestPlanPorts(unittest.TestCase):
    """Check 19: Section 5's bench plan is written against the current interface.

    The defect shape is a real one this document suffered: `VPWR`/`VGND`
    (DR-010, issue #355) and `GND` (DR-012, issue #362) joined the block's
    interface on 2026-09-24, taking it from 19 ports to 22, and Section 5's
    bring-up step went on powering the 19-port block -- under a lede claiming
    the section was written against the *current* port list. Check 10 was
    grading Section 2's table, which had been updated correctly, so nothing
    fired.
    """

    def setUp(self):
        self.tree = FixtureTree(self)

    def _supplies(self, count: int, *terminals: str) -> str:
        return (
            f"This part presents **{count}** supply terminals — "
            + ", ".join(f"`{net}`" for net in terminals)
            + " — and that set is recomputed from §2.2's own rail rows."
        )

    def _rails(self, *rows: str) -> str:
        return io_section(*rows)

    def test_port_named_nowhere_in_the_bench_plan_is_reported(self):
        self.tree.add_top_netlist("VDD", "CLK", "VPWR")
        misses = self.tree.check(
            bench_plan("1. **Bring-up.** Apply `VDD` = 1.8 V, `CLK` free-running.")
        )
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("port `VPWR`", misses[0])
        self.assertIn("named nowhere in Section 5", misses[0])

    def test_a_range_form_covers_every_line_of_the_bus(self):
        self.tree.add_top_netlist(*[f"DOUT{i}" for i in range(9, -1, -1)])
        self.assertEqual(
            self.tree.check(bench_plan("2. Capture `DOUT9..0` on each conversion.")), []
        )

    def test_a_glob_does_not_stand_in_for_naming_the_bus(self):
        """`DOUT*` discusses the bus; it does not name DOUT9..DOUT0."""
        self.tree.add_top_netlist("DOUT9", "DOUT8")
        misses = self.tree.check(bench_plan("2. FFT-derive ENOB from a `DOUT*` record."))
        self.assertEqual(len(misses), 2, misses)
        self.assertIn("port `DOUT9`", misses[0])

    def test_an_unbackticked_port_name_does_not_count_as_naming_it(self):
        self.tree.add_top_netlist("VPWR")
        misses = self.tree.check(bench_plan("1. Apply VPWR = 1.8 V to the macros."))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("port `VPWR`", misses[0])

    def test_supply_terminal_count_that_disagrees_with_section_2_is_reported(self):
        self.tree.add_top_netlist("VDD", "VPWR")
        body = self._rails(
            "| `VDD` | supply | 1.8 V analog rail | — (rail, not a slot) | rail |",
            "| `VPWR` | supply | 1.8 V digital rail | — (rail, not a slot) | rail |",
        ) + bench_plan(
            "1. Feed `VDD` and `VPWR`.", supplies=self._supplies(3, "VDD", "VPWR")
        )
        misses = self.tree.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("feeds 3 supply terminal(s)", misses[0])
        self.assertIn("charges 2 port(s) to no slot", misses[0])

    def test_supply_terminal_omitted_from_the_list_is_reported(self):
        self.tree.add_top_netlist("VDD", "VGND")
        body = self._rails(
            "| `VDD` | supply | 1.8 V analog rail | — (rail, not a slot) | rail |",
            "| `VGND` | supply | digital return | — (rail, not a slot) | rail |",
        ) + bench_plan("1. Feed `VDD`, return `VGND`.", supplies=self._supplies(1, "VDD"))
        misses = self.tree.check(body)
        self.assertEqual(len(misses), 2, misses)
        self.assertIn("feeds 1 supply terminal(s)", misses[0])
        self.assertIn("omits `VGND`", misses[1])

    def test_supply_terminal_that_is_not_a_rail_row_is_reported(self):
        """The reverse direction: a terminal invented in Section 5."""
        self.tree.add_top_netlist("VDD", "VCM")
        body = self._rails(
            "| `VDD` | supply | 1.8 V analog rail | — (rail, not a slot) | rail |",
            "| `VCM` | in | dedicated pad (budget: 0–4) | 1 | bias |",
        ) + bench_plan(
            "1. Feed `VDD`; bias `VCM`.", supplies=self._supplies(2, "VDD", "VCM")
        )
        misses = self.tree.check(body)
        self.assertEqual(len(misses), 2, misses)
        self.assertIn("feeds 2 supply terminal(s)", misses[0])
        self.assertIn("names `VCM`", misses[1])
        self.assertIn("is not a rail row", misses[1])

    def _power(self, campaign: str, count: int, *terms: str) -> str:
        return (
            f"that figure is a sum over the **{count}** current columns of "
            f"`sim/{campaign}/records/LATEST`'s own Power table — "
            + ", ".join(f"`I({net})`" for net in terms)
            + " — of which `VDD` is one term."
        )

    def test_power_step_metering_fewer_terminals_than_the_record_is_reported(self):
        """The load-bearing case: a `VDD`-only reading against a five-source sum."""
        self.tree.add_sim_record(
            "full-conversion-transient",
            "20260912-002315-9aaf1ca",
            latest=True,
            power={"tt_27c_1.80v": 27.971},
            power_terms=("VDD", "VPWR", "VREFP", "VCM", "VREFN"),
        )
        self.tree.add_top_netlist("VDD")
        body = bench_plan(
            "6. **Power.** Measure `VDD` supply current.",
            power=self._power("full-conversion-transient", 1, "VDD"),
        )
        misses = self.tree.check(body)
        self.assertEqual(len(misses), 2, misses)
        self.assertIn("says that table carries 1 current column(s)", misses[0])
        self.assertIn("carries 5", misses[0])
        self.assertIn("meters ['VDD']", misses[1])

    def test_power_step_term_order_must_be_the_records_own(self):
        self.tree.add_sim_record(
            "full-conversion-transient",
            "20260912-002315-9aaf1ca",
            latest=True,
            power={"tt_27c_1.80v": 27.971},
            power_terms=("VDD", "VPWR"),
        )
        self.tree.add_top_netlist("VDD")
        body = bench_plan(
            "6. Meter each feed.",
            power=self._power("full-conversion-transient", 2, "VPWR", "VDD"),
        )
        misses = self.tree.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("meters ['VPWR', 'VDD']", misses[0])

    def test_power_step_matching_the_record_passes(self):
        self.tree.add_sim_record(
            "full-conversion-transient",
            "20260912-002315-9aaf1ca",
            latest=True,
            power={"tt_27c_1.80v": 27.971},
            power_terms=("VDD", "VPWR", "VREFP", "VCM", "VREFN"),
        )
        self.tree.add_top_netlist("VDD")
        body = bench_plan(
            "6. Meter each feed: `VDD`.",
            power=self._power(
                "full-conversion-transient", 5, "VDD", "VPWR", "VREFP", "VCM", "VREFN"
            ),
        )
        self.assertEqual(self.tree.check(body), [])

    def test_power_step_citing_a_campaign_with_no_power_table_is_reported(self):
        self.tree.add_sim_record("vcm-drive-budget", "20260908-074408-80df05e", latest=True)
        self.tree.add_top_netlist("VDD")
        body = bench_plan(
            "6. Meter `VDD`.", power=self._power("vcm-drive-budget", 1, "VDD")
        )
        misses = self.tree.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("no readable Power table", misses[0])

    def test_the_stats_sentence_is_what_the_check_accepts(self):
        """A `--stats` paste must pass, or the documented fix does not work."""
        self.tree.add_sim_record(
            "full-conversion-transient",
            "20260912-002315-9aaf1ca",
            latest=True,
            power={"tt_27c_1.80v": 27.971},
            power_terms=("VDD", "VPWR", "VREFP", "VCM", "VREFN"),
        )
        self.tree.add_top_netlist("VDD")
        terms = checker.record_power_terms("full-conversion-transient")
        sentence = checker.power_terms_sentence("full-conversion-transient", terms)
        body = bench_plan("6. Meter each feed: `VDD`.", power=sentence)
        self.assertEqual(self.tree.check(body), [])

    def test_check_is_inert_without_the_top_netlist(self):
        # No design/sar_adc_top.spice in the fixture tree at all.
        self.assertEqual(self.tree.check(bench_plan("1. Apply nothing.")), [])

    def test_check_is_inert_on_a_document_with_no_section_5(self):
        self.tree.add_top_netlist("VDD", "VPWR", "GND")
        self.assertEqual(self.tree.check("# fixture\n\nNo numbered sections.\n"), [])

    def test_a_document_stating_no_gated_sentences_is_not_failed_for_them(self):
        # Parts (b) and (c) are opt-in per document, like checks 6 and 18.
        self.tree.add_top_netlist("VDD")
        self.assertEqual(self.tree.check(bench_plan("1. Apply `VDD`.")), [])


class TestTopCellInventory(unittest.TestCase):
    """Check 20: the stated device/cell inventory is the netlist's own.

    The defect shape is a real one this document suffered, and for two weeks:
    DR-008 (issue #263, PR #266, 2026-09-11) replaced the nine
    `SELn<i> = NOT(DOUT<i>)` inverters issue #56 drew at the integration level
    with eighteen decision-directed `and2_1` gates, plus a `xor2_1` readout
    recode and DR-009's eight-device half-LSB offset network. None of it moved
    a port, so check 10 -- which grades the port list -- had nothing to say,
    and Sections 1, 3 and 7 went on describing the inverter bank as the glue
    this schematic adds.
    """

    def setUp(self):
        self.tree = FixtureTree(self)

    SC_HD = "sky130_fd_sc_hd__"
    PR = "sky130_fd_pr__"

    def _glue(self, *cells: str) -> tuple[str, ...]:
        """One instance line per named cell, in the two card shapes both families use."""
        lines = []
        for index, cell in enumerate(cells):
            if cell.startswith(self.SC_HD):
                lines.append(f"xg{index} A B VGND VGND VPWR VPWR Y {cell}")
            else:
                lines.append(f"XM{index} D G S B {cell} L=0.15 W=1 m=1")
        return tuple(lines)

    def _flavours(self, *flavours: str) -> str:
        return (
            f"This design instantiates **{len(flavours)}** `sky130_fd_pr` "
            "primitive flavours — "
            + ", ".join(f"`{flavour}`" for flavour in flavours)
            + " — re-derived from the netlist's own instance lines."
        )

    def _census(self, cells: dict[str, int], primitives: dict[str, int]) -> str:
        def listed(entries: dict[str, int]) -> str:
            return ", ".join(
                f"`{cell}` **×{count}**" for cell, count in sorted(entries.items())
            )

        return (
            f"Outside every sub-block, `design/sar_adc_top.sch` adds "
            f"**{sum(cells.values())}** `sky130_fd_sc_hd` instances of "
            f"**{len(cells)}** cell types — {listed(cells)} — "
            f"and **{sum(primitives.values())}** `sky130_fd_pr` instances of "
            f"**{len(primitives)}** device types — {listed(primitives)}."
        )

    def test_a_truthful_inventory_passes(self):
        self.tree.add_top_netlist(
            "CLK",
            glue=self._glue(self.SC_HD + "and2_1", self.PR + "nfet_01v8"),
            subblocks=self._glue(self.PR + "cap_mim_m3_1"),
        )
        body = "# fixture\n\n" + self._flavours("cap_mim_m3_1", "nfet_01v8")
        body += "\n\n" + self._census({"and2_1": 1}, {"nfet_01v8": 1})
        self.assertEqual(self.tree.check(body), [])

    def test_a_flavour_the_netlist_carries_but_section_1_omits_is_reported(self):
        """The DR-002 tripwire direction: the design reads smaller than it is."""
        self.tree.add_top_netlist(
            "CLK", glue=self._glue(self.PR + "nfet_01v8", self.PR + "nfet_g5v0d10v5")
        )
        misses = self.tree.check("# fixture\n\n" + self._flavours("nfet_01v8"))
        self.assertEqual(len(misses), 2, misses)
        self.assertTrue(any("instantiates 1 `sky130_fd_pr`" in m for m in misses), misses)
        self.assertTrue(
            any("omits `nfet_g5v0d10v5`" in m for m in misses), misses
        )

    def test_a_flavour_section_1_names_that_no_instance_carries_is_reported(self):
        self.tree.add_top_netlist("CLK", glue=self._glue(self.PR + "nfet_01v8"))
        misses = self.tree.check(
            "# fixture\n\n" + self._flavours("nfet_01v8", "pfet_g5v0d10v5")
        )
        self.assertEqual(len(misses), 2, misses)
        self.assertTrue(any("names `pfet_g5v0d10v5`" in m for m in misses), misses)

    def test_the_flavour_set_spans_the_whole_hierarchy_not_just_the_top_cell(self):
        """A sub-block's own devices count: part (a) is a hierarchy-wide claim."""
        self.tree.add_top_netlist(
            "CLK", subblocks=self._glue(self.PR + "cap_mim_m3_1")
        )
        misses = self.tree.check("# fixture\n\n" + self._flavours("nfet_01v8"))
        self.assertTrue(any("omits `cap_mim_m3_1`" in m for m in misses), misses)

    def test_a_cell_type_swapped_in_equal_number_is_reported(self):
        """The DR-008 shape: nine inverters become nine gates, total unmoved."""
        self.tree.add_top_netlist(
            "CLK", glue=self._glue(*([self.SC_HD + "and2_1"] * 9))
        )
        misses = self.tree.check(
            "# fixture\n\n" + self._census({"inv_1": 9}, {})
        )
        self.assertTrue(any("`inv_1` at 9 instance(s)" in m for m in misses), misses)
        self.assertTrue(any("`and2_1` at 0 instance(s)" in m for m in misses), misses)
        # The instance total is unchanged, which is exactly why a total-only
        # census would have passed straight through this.
        self.assertFalse(any("instance(s), but" in m and "census says" in m for m in misses), misses)

    def test_a_drifted_instance_count_is_reported(self):
        self.tree.add_top_netlist(
            "CLK", glue=self._glue(*([self.SC_HD + "and2_1"] * 18))
        )
        misses = self.tree.check("# fixture\n\n" + self._census({"and2_1": 17}, {}))
        self.assertTrue(any("census says 17 instance(s)" in m for m in misses), misses)

    def test_a_subblock_instance_is_not_counted_as_top_level_glue(self):
        """Part (b)'s whole point: sub-block cells belong to a sub-block flow."""
        self.tree.add_top_netlist(
            "CLK",
            glue=self._glue(self.SC_HD + "inv_1"),
            subblocks=self._glue(*([self.SC_HD + "dfrtp_1"] * 21)),
        )
        self.assertEqual(
            self.tree.check("# fixture\n\n" + self._census({"inv_1": 1}, {})), []
        )

    def test_the_netlists_own_prose_header_is_not_counted_as_an_instance(self):
        """The fixture header names a flavour in prose; a census must not see it."""
        self.tree.add_top_netlist("CLK", glue=self._glue(self.PR + "pfet_01v8"))
        self.assertEqual(
            self.tree.check("# fixture\n\n" + self._flavours("pfet_01v8")), []
        )

    def test_check_is_inert_without_the_top_netlist(self):
        # No design/sar_adc_top.spice in the fixture tree at all.
        self.assertEqual(
            self.tree.check("# fixture\n\n" + self._flavours("nfet_01v8")), []
        )

    def test_a_document_stating_no_inventory_is_not_failed_for_it(self):
        # Opt-in per document, like checks 6, 18 and 19's parts (b)/(c).
        self.tree.add_top_netlist("CLK", glue=self._glue(self.PR + "nfet_01v8"))
        self.assertEqual(self.tree.check("# fixture\n\nNo inventory here.\n"), [])

    def test_stats_sentences_round_trip_through_the_checker(self):
        """A `--stats` paste must pass, or the documented fix does not work."""
        self.tree.add_top_netlist(
            "CLK",
            glue=self._glue(self.SC_HD + "and2_1", self.PR + "nfet_01v8"),
            subblocks=self._glue(self.PR + "cap_mim_m3_1"),
        )
        netlist = checker.top_netlist_text()
        glue = checker.top_level_glue(netlist)
        body = "# fixture\n\nThis design " + checker.primitive_inventory_sentence(
            sorted(checker.cell_census(checker._netlist_instance_lines(netlist), "pr"))
        )
        body += (
            ".\n\nOutside every sub-block, `design/sar_adc_top.sch` "
            + checker.glue_census_sentence(checker.cell_census(glue, "sc_hd"), "sc_hd")
            + " "
            + checker.glue_census_sentence(checker.cell_census(glue, "pr"), "pr")
            + ".\n"
        )
        self.assertEqual(self.tree.check(body), [])


class TestKickbackDecomposition(unittest.TestCase):
    """Check 21: the Kickback row's derived figures are its record's own.

    The defect shape is a real one, and it was in the direction that makes the
    row read better than the evidence supports: the row subtracted the cited
    record's `Vindiff = 0` control peak from its worst-case peak and called the
    `3.0254 mV` residual "the decision transient itself". Both figures are
    extrema over *either* pin (`run_kickback_sweep` tracks one maximum and one
    minimum across `VINP` and `VINN` together), so the difference bounds neither
    the common-mode part of the disturbance nor the differential part -- which
    is what issue #390 (filed from #349, 2026-09-25) exists to measure. DR-011's
    own Context and Consequences §3 carried the same reading, so a reader had no
    reason to doubt it.
    """

    # The real record's two points, which every fixture below is a mutation of.
    POINTS = (
        (0.0, 16.5447, "VINP", "5.037", -70.3419, "VINP", "5.108"),
        (50.0, 16.6241, "VINP", "5.037", -73.3673, "VINP", "5.108"),
    )
    CAMPAIGN = "comparator-decision"
    STAMP = "20260924-041815-afcb1b5"

    def setUp(self):
        self.tree = FixtureTree(self)

    def _record(self, *, points=None, split: bool = False):
        self.tree.add_sim_record(
            self.CAMPAIGN,
            self.STAMP,
            kickback=self.POINTS if points is None else points,
            kickback_split=split,
        )

    def _row(
        self,
        *,
        target: str = "`≤ 5 mV` peak pin disturbance; stretch `≤ 2 mV`",
        peak: str = "73.3673",
        target_mult: str = "14.7",
        stretch_mult: str = "36.7",
        control: str = "70.3419",
        baseline_pct: str = "95.9",
        residual: str = "3.0254",
        residual_pct: str = "4.1",
        columns: str = (
            "`Vindiff (mV)`, `peak+ (mV)`, `pin / time (ns)`, `peak- (mV)`, "
            "`pin / time (ns)`"
        ),
        column_count: str = "5",
        verdict: str = checker.KICKBACK_NO_SPLIT_CLAUSE,
        verdict_cell: str | None = None,
    ) -> str:
        if verdict_cell is None:
            verdict_cell = (
                f"INFORMATIONAL — the cited record measures **{peak} mV** "
                f"worst-case peak pin disturbance (`Vindiff = +50 mV`, `VINP` at "
                f"5.108 ns), i.e. `≈ {target_mult}×` the `≤ 5 mV` target and "
                f"`≈ {stretch_mult}×` the `≤ 2 mV` stretch. Against the record's "
                f"own `Vindiff = 0 mV` control row (**−{control} mV**, `VINP` at "
                f"5.108 ns): `≈ {baseline_pct} %` of that peak is already present "
                f"with no decision to make, and `{residual} mV` "
                f"(`≈ {residual_pct} %`) is what the `+50 mV` point adds on top "
                f"of it. The record's own `Measured value(s)` table carries "
                f"**{column_count}** columns — {columns} — {verdict}: so much for "
                f"that"
            )
        return (
            f"| Kickback | {target} | DRAFT | {verdict_cell} | "
            f"[`sim/{self.CAMPAIGN}/records/{self.STAMP}.md`]"
            f"(../../sim/{self.CAMPAIGN}/records/{self.STAMP}.md) |"
        )

    def check(self, row: str) -> list[str]:
        return checker.check_kickback_decomposition(
            self.tree.document(spec_table(row)), spec_table(row)
        )

    def test_a_truthful_row_passes(self):
        self._record()
        self.assertEqual(self.check(self._row()), [])

    def test_a_document_with_no_kickback_row_is_not_failed_for_it(self):
        self._record()
        self.assertEqual(self.check("| ENOB | `≥ 9.0 bits` | DRAFT | UNMET | — |"), [])

    def test_a_relaxed_target_does_not_shrink_the_multiple_silently(self):
        """Acceptance criterion 2's teeth: the multiple is derived, not quoted."""
        self._record()
        misses = self.check(
            self._row(target="`≤ 50 mV` peak pin disturbance; stretch `≤ 2 mV`")
        )
        self.assertTrue(
            any("the target bound" in miss for miss in misses), misses
        )
        self.assertTrue(
            any("the multiple over target" in miss for miss in misses), misses
        )

    def test_an_understated_multiple_is_reported(self):
        self._record()
        misses = self.check(self._row(target_mult="1.5"))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("the multiple over target at `1.5`", misses[0])
        self.assertIn("it is `14.7`", misses[0])

    def test_a_peak_that_is_not_the_records_own_is_reported(self):
        self._record()
        misses = self.check(self._row(peak="7.3673"))
        self.assertTrue(any("worst-case peak at `7.3673`" in m for m in misses), misses)

    def test_an_understated_residual_is_reported(self):
        """The direction the row actually drifted: the decision term reads smaller."""
        self._record()
        misses = self.check(self._row(residual="0.5000", residual_pct="0.7"))
        self.assertTrue(any("the residual at `0.5000`" in m for m in misses), misses)
        self.assertTrue(any("the residual's share at `0.7`" in m for m in misses), misses)

    def test_the_worst_case_is_recomputed_when_the_record_grows_a_point(self):
        """A new `Vindiff` point that is worse must move the row's figures."""
        self._record(
            points=self.POINTS
            + ((1.7578, 16.6000, "VINP", "5.037", -90.0000, "VINN", "5.110"),)
        )
        misses = self.check(self._row())
        self.assertTrue(any("worst-case peak at `73.3673`" in m for m in misses), misses)
        self.assertTrue(any("`VINN`" in m for m in misses), misses)

    def test_a_record_with_no_control_row_is_reported(self):
        """The subtraction rests on the `Vindiff = 0` row; without it, say so."""
        self._record(points=self.POINTS[1:] + ((25.0, 1.0, "VINP", "5.0", -2.0, "VINP", "5.1"),))
        misses = self.check(self._row())
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("`Vindiff = 0` control row", misses[0])

    def test_a_row_citing_no_record_is_reported(self):
        self._record()
        row = "| Kickback | `≤ 5 mV`; stretch `≤ 2 mV` | DRAFT | INFORMATIONAL | — |"
        misses = self.check(row)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("cites no `sim/", misses[0])

    def test_a_record_with_no_measured_table_is_reported(self):
        self.tree.add_sim_record(self.CAMPAIGN, self.STAMP)
        misses = self.check(self._row())
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("`Measured value(s)` table", misses[0])

    def test_a_row_stating_only_a_target_bound_is_reported(self):
        self._record()
        misses = self.check(self._row(target="`≤ 5 mV` peak pin disturbance"))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("1 `≤ <n> mV` bound(s)", misses[0])

    def test_a_row_dropping_the_derived_clauses_entirely_is_reported(self):
        """The vacuity guard: silence must not read as agreement."""
        self._record()
        misses = self.check(
            self._row(verdict_cell="INFORMATIONAL — kickback is large. Mitigation is #349's")
        )
        self.assertEqual(len(misses), 3, misses)
        self.assertTrue(any("no re-derivable measurement clause" in m for m in misses))
        self.assertTrue(any("no re-derivable control-row clause" in m for m in misses))
        self.assertTrue(any("no column list" in m for m in misses))

    def test_a_drifted_column_list_is_reported(self):
        self._record()
        misses = self.check(
            self._row(
                column_count="4",
                columns="`Vindiff (mV)`, `peak+ (mV)`, `peak- (mV)`, `pin / time (ns)`",
            )
        )
        self.assertTrue(any("carries 4 column(s)" in m for m in misses), misses)
        self.assertTrue(any("lists that table's columns as" in m for m in misses), misses)

    def test_dropping_the_no_split_clause_is_reported(self):
        """Without it the subtraction reads as a split it is not."""
        self._record()
        misses = self.check(self._row(verdict="a table of two peaks"))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("does not state that", misses[0])

    def test_a_record_that_grows_the_split_retires_the_clause(self):
        """The #390 direction: the qualification must not outlive its own expiry."""
        self._record(split=True)
        misses = self.check(
            self._row(
                column_count="7",
                columns=(
                    "`Vindiff (mV)`, `peak+ (mV)`, `pin / time (ns)`, "
                    "`peak- (mV)`, `pin / time (ns)`, `CM peak (mV)`, "
                    "`differential peak (mV)`"
                ),
            )
        )
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("now carries one", misses[0])

    def test_stats_clauses_round_trip_through_the_checker(self):
        """A `--stats` paste must pass, or the documented fix does not work."""
        self._record()
        record = (
            self.tree.root / "sim" / self.CAMPAIGN / "records" / f"{self.STAMP}.md"
        )
        readout = checker.kickback_readout(record)
        self.assertIsNotNone(readout)
        # The `--stats` arm joins the three clauses with an ellipsis so each is
        # readable on its own; a document carries them in prose with its own
        # connectives in between. Dropping the ellipses is what a reader pasting
        # them does, so that is what must pass.
        clauses = checker.kickback_sentences(readout, [5.0, 2.0]).replace("… ", "")
        self.assertEqual(self.check(self._row(verdict_cell="INFORMATIONAL — " + clauses)), [])

    def test_the_real_row_is_checked_against_the_real_record(self):
        """The real document's Kickback row must be reachable by this check.

        Guards the vacuity trap directly: every fixture above could pass while
        the real row's phrasing matched no pattern, leaving check 21 inert on
        the only document it exists for.
        """
        text = (CHIPALOOZA_DIR / "challenge-4-proposal.md").read_text()
        row = checker._kickback_row(text)
        self.assertIsNotNone(row, "the real Section 4 table has no Kickback row")
        _line, cells = row
        self.assertEqual(len(checker._kickback_bounds(cells[1])), 2, cells[1])
        self.assertRegex(cells[3], checker.KICKBACK_PEAK_RE)
        self.assertRegex(cells[3], checker.KICKBACK_SPLIT_RE)
        self.assertRegex(cells[3], checker.KICKBACK_COLUMNS_RE)

    def test_the_real_record_still_reports_no_split(self):
        """If #390's successor record has landed, this row is overdue a re-derive."""
        readout = checker.kickback_readout(
            REPO_ROOT / "sim" / self.CAMPAIGN / "records" / f"{self.STAMP}.md"
        )
        self.assertIsNotNone(readout)
        self.assertFalse(
            readout["has_split"],
            "the cited record now carries a common-mode/differential column -- "
            "restate the Kickback row's split from it (issue #390)",
        )


class TestTrackedRecords(unittest.TestCase):
    """Check 22: a Section 4 row names the records its index tracks for it.

    The defect shape is check 11's, moved from the campaign tree to the
    decision-record tree, and it is an *absence* for the same reason: a row
    that never mentions a record has nothing stale for the earlier checks to
    find. DR-014 (issue #349, 2026-09-25) answered DR-011's "Mitigation
    selection" open item for the Kickback row and repointed that row's
    `tracking` field off #349 onto itself and #390; `spec/target-spec.md`'s
    Kickback note moved in the same PR. Section 4's Kickback row did not -- it
    went on restating the open item verbatim and pointing at a closed issue,
    while check 7 (Status column), check 15 (DR-014's own status) and check 21
    (the row's arithmetic) all passed.
    """

    TRACKING = (
        "DR-014 (#349: static preamp not adopted, DR-004 Decision 1 stands); "
        "#390 (the common-mode/differential split); DR-011's Open items"
    )

    def setUp(self):
        self.tree = FixtureTree(self)

    def check(self, row: str) -> list[str]:
        body = spec_table(row)
        return checker.check_tracked_records(self.tree.document(body), body)

    def _index(self, tracking: str | None = None, parameter: str = "Kickback"):
        row = {
            "parameter": parameter,
            "claim_class": "draft-informational",
            "experiments": ["comparator-decision"],
        }
        if tracking is not None:
            row["tracking"] = tracking
        self.tree.add_coverage_index(row)

    def test_a_row_that_names_every_tracked_record_passes(self):
        self._index(self.TRACKING)
        self.assertEqual(
            self.check(
                "| Kickback | `≤ 5 mV` | DRAFT | **Informational only** — DR-011's "
                "row, whose mitigation question DR-014 answers by keeping DR-004 "
                "Decision §1 | a record |"
            ),
            [],
        )

    def test_the_record_the_row_fell_behind_is_reported(self):
        """The exact drift: the row still cites the answered open item's owner."""
        self._index(self.TRACKING)
        misses = self.check(
            "| Kickback | `≤ 5 mV` | DRAFT | **Informational only** — DR-011's row. "
            "Mitigation selection is #349's, unblocked by this row's existence "
            "| a record |"
        )
        self.assertEqual(len(misses), 2, misses)
        self.assertTrue(any("`DR-004`" in miss for miss in misses), misses)
        self.assertTrue(any("`DR-014`" in miss for miss in misses), misses)
        self.assertIn("spec-coverage.json", misses[0])

    def test_a_row_may_name_records_the_index_does_not_track(self):
        """Forward direction only -- provenance is not outstanding work."""
        self._index("DR-011's Open items")
        self.assertEqual(
            self.check(
                "| Kickback | `≤ 5 mV` | **RATIFIED** (DR-003 via #27) | **MET** — "
                "DR-011, DR-014, DR-004 and DR-007 all named here | a record |"
            ),
            [],
        )

    def test_a_row_tracking_no_decision_record_is_not_graded(self):
        """`Sample rate` and `Power` track issues and a future record today."""
        self._index("#24 (CDAC/switch netlist); the future sample-rate record")
        self.assertEqual(
            self.check("| Kickback | `≤ 5 mV` | DRAFT | no record named at all | — |"),
            [],
        )

    def test_a_row_with_no_tracking_field_is_not_graded(self):
        self._index(None)
        self.assertEqual(
            self.check("| Kickback | `≤ 5 mV` | DRAFT | no record named at all | — |"),
            [],
        )

    def test_a_tracked_row_absent_from_section_4_is_left_to_check_7(self):
        self._index(self.TRACKING)
        self.assertEqual(
            self.check("| ENOB | `> 7.5 bit` | DRAFT | **Informational only** | — |"),
            [],
        )

    def test_a_longer_record_number_does_not_satisfy_a_shorter_one(self):
        """`DR-01` must not be answered by a row that happens to name `DR-011`."""
        self._index("DR-01 governs this row")
        misses = self.check(
            "| Kickback | `≤ 5 mV` | DRAFT | DR-011 and DR-014 are named | — |"
        )
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("`DR-01`", misses[0])

    def test_check_is_inert_without_the_coverage_index(self):
        # No sim/spec-coverage.json in the fixture tree at all.
        self.assertEqual(
            self.check("| Kickback | `≤ 5 mV` | DRAFT | DR-011 only | — |"), []
        )


class TestStampedCurrencyClaims(unittest.TestCase):
    """Check 23: "the current run, <record>" must name the pointer's record.

    The mirror of checks 4/5: a currency claim stated BEFORE its citation,
    naming a record by stamp rather than through a `LATEST` pointer. The real
    defect it is taken from is the one shape that can rot invisibly -- Section
    3's `klt erc` bullet and Section 7 item 9 both introduced #355's supply fix
    as "the current run" with a stamped `erc-reports/` citation, and issues
    #362 and #377 each minted a successor record WITHOUT MOVING A SINGLE
    NUMBER in the table either passage carries (four supplies, one island each,
    `clean`, 0 findings). Every figure around the citation still read correct
    while the citation named a superseded run; item 9's prose ended up
    contradicting check 16's machine-generated readout three paragraphs below
    it. Check 16 reads the pointer and never looks at the prose's path; checks
    3/4 cannot see `erc-reports/` at all.
    """

    BLOCK = "sar-adc-top"
    CURRENT = "20260924-234116-66dca3c"
    SUPERSEDED = "20260924-214731-b323061"
    LAYOUT = "20260924-234053-66dca3c"

    def setUp(self):
        self.tree = FixtureTree(self)
        self.tree.add_layout_record(
            self.BLOCK, self.LAYOUT, latest=True, gds={"sar_adc_top": b"stream"}
        )
        self.tree.add_erc_record(
            self.BLOCK, self.SUPERSEDED, graded=self.LAYOUT, supplies={"VDD": 1}
        )
        self.tree.add_erc_record(
            self.BLOCK,
            self.CURRENT,
            latest=True,
            graded=self.LAYOUT,
            supplies={"VDD": 1},
        )

    def _erc_link(self, stamp: str, *, display: str | None = None) -> str:
        target = f"../../layout/{self.BLOCK}/erc-reports/{stamp}/record.md"
        shown = display or f"layout/{self.BLOCK}/erc-reports/{stamp}/record.md"
        return f"[`{shown}`]({target})"

    def check(self, body: str) -> list[str]:
        doc = self.tree.document(body)
        return checker.check_stamped_currency_claims(doc, doc.read_text())

    def test_a_claim_naming_the_current_record_passes(self):
        body = f"The current run, {self._erc_link(self.CURRENT)}, reports clean.\n"
        self.assertEqual(self.check(body), [])

    def test_a_claim_naming_a_superseded_record_is_reported(self):
        """The real defect: a stale stamp behind a table of unmoved numbers."""
        body = f"The current run, {self._erc_link(self.SUPERSEDED)}, reports clean.\n"
        misses = self.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn(self.SUPERSEDED, misses[0])
        self.assertIn(self.CURRENT, misses[0])

    def test_one_stale_link_is_reported_once_not_once_per_half(self):
        """Both halves of the link are graded; the message is not duplicated."""
        body = f"The current run, {self._erc_link(self.SUPERSEDED)}, reports clean.\n"
        self.assertEqual(len(self.check(body)), 1)

    def test_a_link_whose_two_halves_disagree_is_reported(self):
        body = (
            "The current run, "
            + self._erc_link(
                self.CURRENT,
                display=f"layout/{self.BLOCK}/erc-reports/{self.SUPERSEDED}/record.md",
            )
            + ", reports clean.\n"
        )
        misses = self.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn(self.SUPERSEDED, misses[0])

    def test_a_display_text_that_elides_the_block_is_still_graded(self):
        """This document's own form: display `erc-reports/<stamp>/…`, full target."""
        body = (
            "the current run "
            + f"({self._erc_link(self.SUPERSEDED, display=f'erc-reports/{self.SUPERSEDED}/record.md')})"
            + " reports clean.\n"
        )
        misses = self.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn(self.SUPERSEDED, misses[0])

    def test_a_wrapped_claim_is_still_attached(self):
        """The real document wraps between the claim and its citation."""
        body = (
            "and the current run\n"
            f"  ({self._erc_link(self.SUPERSEDED)})\n"
            "  reports clean.\n"
        )
        self.assertEqual(len(self.check(body)), 1)

    def test_a_word_between_the_claim_and_the_path_makes_it_unattached(self):
        """"The current ERC record *grades* <gds>" cites the graded stream."""
        body = (
            "The current ERC record grades "
            f"`layout/{self.BLOCK}/reports/{self.LAYOUT}/sar_adc_top.gds`.\n"
        )
        self.assertEqual(self.check(body), [])

    def test_a_distant_citation_is_narration_and_is_skipped(self):
        body = (
            "The current run reports clean. "
            + "Filler. " * 80
            + self._erc_link(self.SUPERSEDED)
            + "\n"
        )
        self.assertEqual(self.check(body), [])

    def test_a_claim_citing_no_record_at_all_is_skipped(self):
        body = "The current run reports `erc_status: clean` and 0 findings.\n"
        self.assertEqual(self.check(body), [])

    def test_a_document_with_no_currency_claim_is_not_failed_for_it(self):
        body = f"See {self._erc_link(self.SUPERSEDED)} for the 2026-09-24 run.\n"
        self.assertEqual(self.check(body), [])

    def test_the_layout_reports_tree_is_covered_too(self):
        """Not scoped to `erc-reports/`: the pointer is read from the cited tree."""
        self.tree.add_layout_record(self.BLOCK, "20260101-000000-0000000")
        body = (
            "The current record, "
            f"[`layout/{self.BLOCK}/reports/20260101-000000-0000000/record.md`]"
            f"(../../layout/{self.BLOCK}/reports/20260101-000000-0000000/record.md)"
            ", is clean.\n"
        )
        misses = self.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn(self.LAYOUT, misses[0])

    def test_a_tree_with_no_pointer_is_reported(self):
        body = (
            "The current record, "
            "[`sim/nowhere/records/20260101-000000-0000000.md`]"
            "(../../sim/nowhere/records/20260101-000000-0000000.md)"
            ", is it.\n"
        )
        misses = self.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("no `LATEST` pointer", misses[0])

    def test_a_citation_naming_no_flow_is_reported(self):
        body = f"The current run, `erc-reports/{self.CURRENT}/record.md`, is it.\n"
        misses = self.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("names no", misses[0])


class TestRationaleDocumentCoverage(unittest.TestCase):
    """Every check in the chain must carry its rationale in docs/citation-gate.md.

    The checker's rationale used to live in its own ~300-line module
    docstring; issue #321 moved it to `docs/citation-gate.md` so the script
    reads as code. Nothing then stopped a later pass from adding check N+1
    to the chain and leaving its rationale unwritten -- which is exactly the
    prose-drifts-away-from-behaviour shape check 6 exists for, one level up.
    So the coverage is re-derived here rather than trusted.
    """

    RATIONALE_DOC = REPO_ROOT / "docs" / "citation-gate.md"

    def chained_checks(self) -> list[str]:
        """The `check_*` functions `check_document` actually calls."""
        source = inspect.getsource(checker.check_document)
        names = re.findall(r"\b(check_[a-z_]+)\(doc, text\)", source)
        self.assertTrue(names, "no checks found in the check_document chain")
        return names

    def test_the_rationale_document_exists_and_is_linked_from_the_module(self):
        self.assertTrue(self.RATIONALE_DOC.is_file(), self.RATIONALE_DOC)
        self.assertIn("docs/citation-gate.md", checker.__doc__)

    def test_every_chained_check_is_documented_in_the_rationale_document(self):
        headings = [
            line
            for line in self.RATIONALE_DOC.read_text().splitlines()
            if line.startswith("### ")
        ]
        for name in self.chained_checks():
            with self.subTest(check=name):
                self.assertTrue(
                    any(f"`{name}`" in heading for heading in headings),
                    f"docs/citation-gate.md has no `### ` heading naming `{name}` -- "
                    "a check landed without its rationale",
                )

    def test_the_rationale_document_is_not_itself_a_checked_document(self):
        """It lives one directory up on purpose, not by accident.

        `main()` checks every `docs/chipalooza/*.md`, so a rationale document
        placed beside the proposal would become a checked document and change
        this script's own `--stats` and `OK:` output.
        """
        self.assertEqual(self.RATIONALE_DOC.parent, checker.CHIPALOOZA_DIR.parent)
        self.assertNotIn(self.RATIONALE_DOC, set(checker.CHIPALOOZA_DIR.glob("*.md")))

    # -- Check 2's directory list: a prose claim about the gate's own coverage.
    #
    # `docs/citation-gate.md`'s check 2 entry names, in prose, the set of
    # top-level directories whose backticked paths check 2 resolves -- i.e.
    # `checker.OWN_TOP_LEVEL`. A directory missing from the frozenset is a whole
    # tree whose bare citations the gate silently does not resolve, so the
    # sentence is load-bearing, not decorative. The two had already drifted
    # once: check 17 added `signoff` to the frozenset and left the sentence
    # naming seven directories. Re-derived here in both directions rather than
    # trusted, same discipline the checks themselves apply to the proposal.

    CHECK_2_HEADING = "### Check 2 -- bare path references"
    CHECK_2_LIST_RE = re.compile(r"top-level directories \(([^)]*)\)", re.DOTALL)

    @classmethod
    def parse_check_2_directories(cls, section: str) -> set[str] | None:
        """The directories check 2's parenthesised list names, or None.

        Anchored on the parenthetical specifically, NOT on the whole section:
        the section deliberately also backticks an *upstream* path
        (klayout-tools' `src/klayout_tools/lvs.py`) as its counter-example, and
        a parser that swept the section would demand `src` in `OWN_TOP_LEVEL`
        to pass -- exactly backwards. None means the parenthetical is gone.
        """
        match = cls.CHECK_2_LIST_RE.search(section)
        if match is None:
            return None
        return set(re.findall(r"`([A-Za-z0-9_.-]+)/`", match.group(1)))

    def check_2_section(self) -> str:
        text = self.RATIONALE_DOC.read_text()
        start = text.find(self.CHECK_2_HEADING)
        self.assertNotEqual(
            start,
            -1,
            f"docs/citation-gate.md has no {self.CHECK_2_HEADING!r} heading",
        )
        end = text.find("\n### ", start + len(self.CHECK_2_HEADING))
        return text[start:] if end == -1 else text[start:end]

    def test_the_check_2_directory_list_matches_own_top_level(self):
        prose = self.parse_check_2_directories(self.check_2_section())
        self.assertIsNotNone(
            prose,
            "check 2's entry no longer states a parenthesised 'top-level "
            "directories (...)' list, so nothing re-derives what the prose "
            "claims the gate covers",
        )
        frozen = set(checker.OWN_TOP_LEVEL)
        self.assertEqual(
            sorted(frozen - prose),
            [],
            "OWN_TOP_LEVEL carries directories docs/citation-gate.md's check 2 "
            "entry does not name -- the prose understates the gate's coverage",
        )
        self.assertEqual(
            sorted(prose - frozen),
            [],
            "docs/citation-gate.md's check 2 entry names directories "
            "OWN_TOP_LEVEL does not carry -- the prose overstates the gate's "
            "coverage, and citations under them are silently unresolved",
        )

    def test_the_check_2_prose_list_is_not_vacuously_satisfiable(self):
        """The parser must actually be able to fail, and on the real shapes."""
        real = self.check_2_section()
        self.assertTrue(
            self.parse_check_2_directories(real),
            "parsed an empty set from the real section -- set equality against "
            "a non-empty OWN_TOP_LEVEL would be the only thing keeping the "
            "gate above honest",
        )

        # The exact drift check 17 left behind: one entry dropped from the
        # prose must be reported, not absorbed.
        dropped = real.replace(", `signoff/`)", ")")
        self.assertNotEqual(dropped, real, "fixture no longer matches the prose")
        self.assertEqual(
            checker.OWN_TOP_LEVEL - (self.parse_check_2_directories(dropped) or set()),
            {"signoff"},
        )

        # An entry the frozenset does not carry must be reported too.
        added = real.replace("`signoff/`)", "`signoff/`, `bench/`)")
        self.assertNotEqual(added, real, "fixture no longer matches the prose")
        self.assertEqual(
            (self.parse_check_2_directories(added) or set()) - checker.OWN_TOP_LEVEL,
            {"bench"},
        )

        # A section with the parenthetical removed must read as absent, not as
        # an empty set that trivially compares equal to nothing.
        self.assertIsNone(
            self.parse_check_2_directories(
                real.replace("top-level directories (", "top-level directories: ")
            )
        )

        # And the anchor must not be the whole section: the upstream
        # counter-example is present and must not be parsed as one of ours.
        self.assertIn("`src/klayout_tools/lvs.py`", real)
        self.assertNotIn("src", self.parse_check_2_directories(real))


if __name__ == "__main__":
    unittest.main()

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
        provenance: str = "",
    ):
        report = self.root / "layout" / block / "reports" / stamp
        report.mkdir(parents=True, exist_ok=True)
        # `provenance` is the record's own "## Provenance" prose, which check
        # 26 counts the tool versions and PDK commit out of. Empty by default,
        # so every other check's fixtures keep the shape they were written
        # against and a record that pins nothing stays the reachable case.
        (report / "record.md").write_text("fixture record\n" + provenance)
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
        provenance: str = "",
        corners: str = "",
        arms: tuple[str, ...] | None = None,
        arm_count: int | None = None,
        sweep_points: int | None = None,
        ladder_rungs: int | None = None,
        excursions: tuple[tuple[str, str], ...] | None = None,
        excursion_layout: str = "arm",
        excursion_column: str | None = None,
        excursion_dut: str = "a" * 64,
        excursion_undecoupled: bool = True,
        excursion_prose: str = "",
    ):
        records = self.root / "sim" / campaign / "records"
        records.mkdir(parents=True, exist_ok=True)
        # See `add_layout_record` for what `provenance` is and why it is empty
        # by default.
        #
        # `corners` is the record header line check 28 reads the declared PVT
        # point set out of, passed verbatim (the three real shapes are built
        # by `corner_matrix_line` / `point_matrix_line` / `stat_point_line`
        # below). Empty by default, which is the "declares no PVT point set of
        # its own" case -- a real one, and the one a fixture must be able to
        # reach without saying anything.
        body = "fixture record\n" + corners + ("\n" if corners else "") + provenance
        if arms is not None:
            # The `- **Arms**:` header line check 31 reads the run arm set out
            # of, in the shape `sim/supply-impedance-sensitivity/
            # run_supply_impedance.py` writes it. `arm_count` defaults to the
            # length of `arms` -- the only shape the real renderer can emit --
            # and is overridable so a fixture can make the printed count and
            # the printed list disagree, which is the case the check is
            # deliberately graded on the list for.
            printed = len(arms) if arm_count is None else arm_count
            body += (
                f"\n- **Arms**: {printed} supply-return networks "
                + ", ".join(f"`{arm}`" for arm in arms)
                + " x 1 corner point(s) = "
                + f"{printed} transient runs.\n"
            )
        if sweep_points is not None:
            # The `- **Grid**:` header line check 32 identifies a SWEEP record
            # by, in the shape `write_sweep_record()` emits it -- and the only
            # thing that distinguishes one from the arm-comparison record in
            # the same tree. The two factors in front of the `=` are fixed at
            # 3 x 3 rather than derived from `sweep_points`, deliberately: the
            # check reads the TOTAL and never the factors, so a fixture must
            # be able to state a total the factors do not multiply out to.
            body += (
                f"\n- **Grid**: 3 bond-inductance multipliers x 3 "
                f"substrate-link resistances = {sweep_points} swept points, "
                f"plus the `ideal` control, at 1 corner point(s) = "
                f"{sweep_points + 1} whole-ADC transients.\n"
            )
        if ladder_rungs is not None:
            # The `- **Ladder**:` header line check 34 identifies a NULL-SWEEP
            # record by, in the shape `write_null_sweep_record()` emits it --
            # the third and last record shape this one `records/` tree holds.
            # The `=` total is deliberately NOT `ladder_rungs`: the real
            # renderer counts the `ideal` control in it, and the check must
            # read the leading rung count rather than that total, because the
            # control is not a swept magnitude.
            body += (
                f"\n- **Ladder**: {ladder_rungs} substrate-return resistances "
                f"plus the `ideal` control, at 1 corner point(s) = "
                f"{ladder_rungs + 1} whole-ADC transients.\n"
            )
        if excursions is not None:
            # The die-side rail-excursion table check 35 reads the campaign's
            # own `gnd_die pp (mV)` column out of, in BOTH the shapes this
            # campaign's writers emit: `excursion_layout="arm"` is the
            # arm-comparison/corner-grid table (`| corner-id | arm | ... |`,
            # the excursion column third) and `"point"` is the sweep/ladder
            # table (`| point | ... |`, second). A fixture that could only
            # write one of them would leave the column-by-header parse
            # untested against the layout it does not write, which is exactly
            # the half that makes the check readable across both writers.
            #
            # `excursion_column` overrides the header text so a fixture can
            # reach the "this records tree carries no excursion column at all"
            # condition -- a silence the check must report as nothing to
            # compare against rather than as an empty set of figures.
            header = checker.EXCURSION_COLUMN if excursion_column is None else excursion_column
            lead = "corner-id | arm" if excursion_layout == "arm" else "point"
            width = 3 if excursion_layout == "arm" else 2
            # The two lines that decide whether these figures are UNDECOUPLED
            # upper bounds, written the way the real records write them: the
            # assumption bullet a record that is the undecoupled case states of
            # itself, and the DUT netlist sha256 by which every other record of
            # the same netlist inherits it. `excursion_prose` is free text for
            # the cost-section boilerplate every record of this campaign carries
            # ("an undecoupled series inductance ..."), which a word search --
            # rather than a bullet match -- would misread as a declaration.
            if excursion_undecoupled:
                body += (
                    "\n## Assumptions\n\n"
                    "- **No decoupling, on-die or on-board** (DR-015 item 6). "
                    "Every point here is the undecoupled case.\n"
                )
            if excursion_prose:
                body += f"\n{excursion_prose}\n"
            body += f"\n- DUT netlist sha256: `{excursion_dut}`\n"
            body += "\n## Die-side rail excursion over one steady-state conversion\n\n"
            body += f"| {lead} | {header} | vgnd_die pp (mV) |\n"
            body += "|---|" * (width + 1) + "\n"
            for label, figure in excursions:
                cells = (
                    f"| `tt_27c_1.80v` | `{label}` |"
                    if excursion_layout == "arm"
                    else f"| `{label}` |"
                )
                body += f"{cells} {figure} | 0.000 |\n"
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
        provenance: str = "",
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
        (report / "record.md").write_text("fixture erc record\n" + provenance)
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

    def add_renderer(self, path: str, body: str):
        """A record-minting entry point under `layout/`, for check 30.

        Written as a path relative to the fixture root rather than keyed by
        flow, because the entry point a record tree resolves to is exactly
        what the check derives -- a helper that placed it for the caller
        would hide the half of the behaviour under test.
        """
        entry = self.root / path
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(body)

    def add_arm_runner(self, *arms: str, table: str | None = None):
        """The supply-impedance runner's own `ARMS` table, for check 31.

        Written as real Python in the runner's own shape -- an `ARMS: tuple`
        annotation, one `Arm(...)` per arm with its `name=` on its own line
        and a nested `bonds=` mapping -- because the parse under test is a
        source-text read, and a fixture that flattened the arms to a bare list
        of strings would pass while the real table went unrecognised. `table`
        overrides the whole body, for the "shape this parse does not
        recognise" case.
        """
        runner = self.root / checker.ARM_RUNNER
        runner.parent.mkdir(parents=True, exist_ok=True)
        if table is None:
            table = "ARMS: tuple[Arm, ...] = (\n"
            for arm in arms:
                table += (
                    "    Arm(\n"
                    f'        name="{arm}",\n'
                    '        summary="fixture arm",\n'
                    '        bonds={"VDD": IDEAL, "GND": IDEAL},\n'
                    "    ),\n"
                )
            table += ")\n"
        runner.write_text('"""fixture runner."""\n\n' + table)

    def add_sweep_axes(
        self,
        l_mults: tuple[float, ...] = (0.0, 1.0, 10.0),
        rsubx: tuple[float, ...] = (3.0, 30.0, 300.0),
        *,
        axes: str | None = None,
    ):
        """The runner's own `--sweep` box constants, for check 32.

        Appended to the runner rather than written over it: the real file
        carries both the `ARMS` table check 31 parses and these two tuples,
        and a fixture that could only hold one of them would let the two
        source-text parses pass tests they never share a file in. Written as
        real annotated tuple literals for `add_arm_runner`'s reason. `axes`
        overrides the whole block, for the "shape this parse does not
        recognise" case (a computed box).
        """
        runner = self.root / checker.SWEEP_RUNNER
        runner.parent.mkdir(parents=True, exist_ok=True)
        if axes is None:
            axes = (
                "SWEEP_L_MULTIPLIERS: tuple[float, ...] = ("
                + ", ".join(f"{m:g}" for m in l_mults)
                + ")\n"
                "SWEEP_RSUBX_OHM: tuple[float, ...] = ("
                + ", ".join(f"{r:g}" for r in rsubx)
                + ")\n"
            )
        existing = runner.read_text() if runner.is_file() else '"""fixture runner."""\n'
        runner.write_text(existing + "\n" + axes)

    def add_null_sweep_axis(
        self,
        rsubx: tuple[float, ...] = (3.0, 30.0, 300.0),
        *,
        axis: str | None = None,
    ):
        """The runner's own `--null-sweep` ladder constant, for check 34.

        Appended for `add_sweep_axes`' reason -- the real file carries the
        `ARMS` table, the 2-D box's two tuples AND this one, and a fixture
        that could only hold one of them would let three source-text parses
        pass tests they never share a file in. That matters more here than
        anywhere else in this tree: `SWEEP_RSUBX_OHM` and
        `NULL_SWEEP_RSUBX_OHM` share a suffix, so only a fixture carrying both
        can show that neither regex captures the other's tuple. `axis`
        overrides the block, for the "shape this parse does not recognise"
        case (a computed ladder).
        """
        runner = self.root / checker.NULL_SWEEP_RUNNER
        runner.parent.mkdir(parents=True, exist_ok=True)
        if axis is None:
            axis = (
                "NULL_SWEEP_RSUBX_OHM: tuple[float, ...] = ("
                + ", ".join(f"{r:g}" for r in rsubx)
                + ")\n"
            )
        existing = runner.read_text() if runner.is_file() else '"""fixture runner."""\n'
        runner.write_text(existing + "\n" + axis)

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

    def add_decision_record(
        self,
        name: str,
        status: str | None = "proposed",
        open_items: list[str] | None = None,
    ):
        """A `spec/decision-records/<name>` in the shape check 15 reads.

        Written in the real records' own shape -- a `- **Status**:` bullet
        whose word may be bolded or bare, followed by an em-dash rationale the
        check must not read. `status=None` writes a record with no Status
        field at all, which is the "nothing to compare against" condition
        check 15 reports separately from a disagreement.

        `open_items` appends a `## Open items` section carrying the given
        bullets verbatim (each written as `- <bullet>`), which is what check
        33 censuses. Absent by default, so every other check's fixtures keep
        the shape they were written against and a record declaring nothing
        open stays the reachable case.
        """
        records = self.root / "spec" / "decision-records"
        records.mkdir(parents=True, exist_ok=True)
        body = [f"# {name.removesuffix('.md')}", ""]
        if status is not None:
            body.append(
                f"- **Status**: {status} — this fixture record ratifies nothing."
            )
        body += ["- **Date**: 2026-09-18", ""]
        if open_items is not None:
            body += ["## Open items", ""]
            body += [f"- {item}" for item in open_items]
            body.append("")
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

    def add_report_manifest(self, rows: int, *, restructured: bool = False):
        """A `sim/report/manifest.py` in the shape check 24 counts.

        Written the way the real manifest is written -- a module-level
        `ROWS: tuple[Row, ...] = (` tuple holding one `Row(` constructor per
        characterization-report row, with a decoy `Row(` in a docstring above
        it and a second tuple below, both of which a whole-file count would
        swallow.

        `restructured=True` builds the same rows without that tuple literal,
        which is the "no `ROWS` tuple this gate can count" condition the check
        reports separately from a disagreement.
        """
        report = self.root / "sim" / "report"
        report.mkdir(parents=True, exist_ok=True)
        body = [
            '"""Fixture manifest.',
            "",
            "Each entry below is a Row( ... ) this docstring must not be counted as.",
            '"""',
            "",
            "from dataclasses import dataclass",
            "",
            "",
            "@dataclass(frozen=True)",
            "class Row:",
            "    id: str",
            "",
            "",
        ]
        if restructured:
            body += [f"ROWS = tuple(Row(id=str(n)) for n in range({rows}))", ""]
        else:
            body += ["ROWS: tuple[Row, ...] = ("]
            body += [f'    Row(\n        id="row{n}",\n    ),' for n in range(rows)]
            body += [")", ""]
        body += [
            "SUPERSEDED_ROWS: tuple[Row, ...] = (",
            '    Row(\n        id="not-a-report-row",\n    ),',
            ")",
            "",
        ]
        (report / "manifest.py").write_text("\n".join(body))

    def add_sim_deck(self, path: str, *, inductor: bool = False):
        """A `sim/<path>` SPICE deck in the shape check 25 scans.

        Always carries the decoys a naive line scan would miss on: a comment
        line and a `.lib` dot-command that both begin with the letter the
        inductor card is recognised by, an `L`-initial *continuation* line,
        and a `.control` block body whose `let` line has the same
        `L<word> <field> <field> <field>` shape as an inductor card. Only
        `inductor=True` writes a real `L<name> <n+> <n-> <value>` card, which
        is the one shape that may be counted.
        """
        deck = self.root / "sim" / path
        deck.parent.mkdir(parents=True, exist_ok=True)
        body = [
            "* Lbond -- a comment naming the card this deck does not carry",
            ".lib /pdk/sky130.lib.spice tt",
            "VVDD VDD 0 DC 1.8",
            "Xdut VDD 0 fixture_dut",
            "+ Lfoo not_a_card here",
        ]
        if inductor:
            body.append("Lbond VDD VDD_DIE 2n")
        body += [
            ".control",
            "let verr = v(a) - v(b)",
            ".endc",
            ".tran 1p 1n",
            ".end",
            "",
        ]
        deck.write_text("\n".join(body))

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

    def graded(self, misses: list[str]) -> list[str]:
        """Check 11's own findings out of the whole chain's output.

        These fixtures deliberately hold a campaign record the fixture
        document does not cite, which is *also* check 37's finding -- the two
        checks cover the same absence at different scopes (per row, and
        document-wide), so a test about one filters out the other rather than
        asserting on the union.
        """
        return [miss for miss in misses if "spec-coverage.json" in miss]

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
        self.assertEqual(self.graded(misses), [])

    def test_an_unbenched_row_is_excluded(self):
        self.tree.add_coverage_index(
            {"parameter": "Power", "claim_class": "unbenched", "experiments": []}
        )
        misses = self.tree.check(
            spec_table("| Power | provisional | DRAFT | **UNMEASURED** | none yet |")
        )
        self.assertEqual(self.graded(misses), [])

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
        reported = self.graded(misses)
        self.assertEqual(len(reported), 1, misses)
        self.assertIn("LSB (differential)", reported[0])

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


class TestReportRowCount(unittest.TestCase):
    """Check 24: the quoted `generate.py --check` row count is re-derived.

    The defect shape is check 6's and check 18's -- a machine output
    transcribed into prose, with nothing re-deriving it -- moved off the
    evidence trees onto a command's own closing line. The real drift: the
    proposal quoted `11 rows` from its first pass (PR #140, 2026-09-05), which
    was true then and stopped being true on 2026-09-24 when PR #366 added the
    DRAFT Kickback row to `sim/report/manifest.py`. Three later passes edited
    that very row in Section 4 without the count one paragraph above the table
    moving.
    """

    COMMAND = "`python3 sim/report/generate.py --check` verifies the report"
    QUOTED = "(`OK: ... is fresh and up to date ({rows} rows)`)"

    def setUp(self):
        self.tree = FixtureTree(self)

    def check(self, body: str) -> list[str]:
        return checker.check_report_row_count(self.tree.document(body), body)

    def body(self, *, rows: int | None = 12, command: bool = True) -> str:
        text = "## 4. Reproducing this table\n\n"
        if command:
            text += self.COMMAND + "\n"
        if rows is not None:
            text += self.QUOTED.format(rows=rows) + "\n"
        return text

    def test_a_quotation_matching_the_manifest_passes(self):
        self.tree.add_report_manifest(12)
        self.assertEqual(self.check(self.body(rows=12)), [])

    def test_the_real_drift_is_reported(self):
        """Eleven quoted against a twelve-row manifest -- the exact defect."""
        self.tree.add_report_manifest(12)
        misses = self.check(self.body(rows=11))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("is fresh and up to date (11 rows)", misses[0])
        self.assertIn("carries 12 rows", misses[0])

    def test_every_quotation_is_graded_not_only_the_first(self):
        self.tree.add_report_manifest(12)
        body = self.body(rows=12) + self.QUOTED.format(rows=9) + "\n"
        misses = self.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("(9 rows)", misses[0])

    def test_quoting_none_of_the_output_is_reported(self):
        """Deleting the quotation must not be a way to pass."""
        self.tree.add_report_manifest(12)
        misses = self.check(self.body(rows=None))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("quotes none of", misses[0])
        self.assertIn("(12 rows)", misses[0])

    def test_a_document_that_does_not_name_the_command_is_not_graded(self):
        self.tree.add_report_manifest(12)
        self.assertEqual(self.check("Nothing about the report here.\n"), [])

    def test_a_restructured_manifest_is_reported_not_counted_as_zero(self):
        self.tree.add_report_manifest(12, restructured=True)
        misses = self.check(self.body(rows=12))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("no longer states a `ROWS` tuple", misses[0])

    def test_check_is_inert_without_the_manifest(self):
        # No sim/report/manifest.py in the fixture tree at all.
        self.assertEqual(self.check(self.body(rows=11)), [])

    def test_the_count_ignores_rows_outside_the_rows_tuple(self):
        """A docstring's `Row(` and a second tuple must not inflate the count."""
        self.tree.add_report_manifest(3)
        self.assertEqual(checker.report_row_count(), 3)

    def test_the_real_manifest_and_the_real_document_agree(self):
        """The live pair, not a fixture: this is what CI actually grades."""
        FixtureTree_root = checker.REPO_ROOT
        self.assertTrue((REPO_ROOT / checker.REPORT_MANIFEST).is_file())
        # Point the checker back at the real tree for this one assertion.
        checker.REPO_ROOT = REPO_ROOT
        self.addCleanup(lambda: setattr(checker, "REPO_ROOT", FixtureTree_root))
        derived = checker.report_row_count()
        self.assertGreater(derived, 0)
        doc = REPO_ROOT / "docs" / "chipalooza" / "challenge-4-proposal.md"
        text = doc.read_text()
        quoted = [
            int(match.group("rows"))
            for match in checker.REPORT_ROW_COUNT_RE.finditer(text)
        ]
        self.assertTrue(quoted, "the proposal quotes no row count at all")
        self.assertEqual(set(quoted), {derived})


class TestGroundReturn(unittest.TestCase):
    """Check 25: the stated ground-return census is the `sim/` tree's own.

    Every other check grades a claim about something the repository *has*.
    This one grades a disclaimer -- DR-012's own "no `sim/` campaign models
    the ground return at all", which Section 7 Item 9 restates -- and the
    event that falsifies it moves no pointer, no island count and no Section
    4 number. Hence a census counted from the tree rather than a sentence
    re-read by hand.
    """

    ANCHOR = "See [DR-012](../../spec/decision-records/DR-012-analog-ground-pad.md).\n"

    def setUp(self):
        self.tree = FixtureTree(self)

    def check(self, body: str) -> list[str]:
        return checker.check_ground_return(self.tree.document(body), body)

    def body(self, sentence: str | None, *, anchor: bool = True) -> str:
        text = "## 7. Open items\n\n"
        if anchor:
            text += self.ANCHOR
        if sentence is not None:
            text += f"\n> {sentence}\n"
        return text

    def test_a_truthful_census_passes(self):
        self.tree.add_sim_deck("full-conversion-transient/testbench/tb.spice")
        self.tree.add_sim_deck("comparator-decision/records/rec.spice")
        self.assertEqual(
            self.check(
                self.body("across the **2** SPICE decks under `sim/`, **0** carry an inductor card")
            ),
            [],
        )

    def test_a_control_block_let_line_is_not_an_inductor_card(self):
        """A `.control` body's `let` line has an inductor card's shape.

        `let verr = v(a) - v(b)` matches `L<word> <field> <field> <field>`
        on a naive line scan, but it is ngspice's interactive command
        language, not a device card -- reproduced directly against the
        module's own deck scanner rather than through the sentence check, so
        a regression here fails as close to the cause as possible.
        """
        deck = self.tree.root / "sim" / "zz-control-probe.spice"
        deck.parent.mkdir(parents=True, exist_ok=True)
        deck.write_text(
            "* probe\n"
            "VVDD VDD 0 DC 1.8\n"
            ".control\n"
            "tran 1p 1n\n"
            "let verr = v(a) - v(b)\n"
            ".endc\n"
            ".end\n"
        )
        cards = checker._deck_device_cards(deck)
        self.assertEqual(cards, [(2, "VVDD VDD 0 DC 1.8")], cards)

    def test_a_deck_that_models_an_inductance_is_reported(self):
        """The direction that matters: the gap closes, the disclaimer must go."""
        self.tree.add_sim_deck("ground-return/testbench/tb.spice", inductor=True)
        misses = self.check(
            self.body("across the **1** SPICE deck under `sim/`, **0** carry an inductor card")
        )
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("inductors=0", misses[0])
        self.assertIn("inductors=1", misses[0])
        self.assertIn("sim/ground-return/testbench/tb.spice:6", misses[0])
        self.assertIn("rewrite the qualification", misses[0])

    def test_a_drifted_deck_count_is_reported(self):
        self.tree.add_sim_deck("a/tb.spice")
        self.tree.add_sim_deck("b/tb.spice")
        misses = self.check(
            self.body("across the **1** SPICE deck under `sim/`, **0** carry an inductor card")
        )
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("decks=1", misses[0])
        self.assertIn("decks=2", misses[0])

    def test_stating_no_census_at_all_is_reported(self):
        """Deleting an inconvenient qualification must not be a way to pass."""
        self.tree.add_sim_deck("a/tb.spice")
        misses = self.check(self.body(None))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("states no census of its own", misses[0])
        self.assertIn("**1** SPICE deck under `sim/`, **0**", misses[0])

    def test_a_document_that_does_not_cite_dr_012_is_not_graded(self):
        self.tree.add_sim_deck("a/tb.spice", inductor=True)
        self.assertEqual(self.check(self.body(None, anchor=False)), [])

    def test_check_is_inert_without_a_sim_tree(self):
        self.assertEqual(self.check(self.body(None)), [])

    def test_comments_continuations_and_dot_commands_are_not_cards(self):
        """Every fixture deck carries all three decoys; none may be counted."""
        self.tree.add_sim_deck("a/tb.spice")
        self.assertEqual(checker.ground_return_census()["inductors"], 0)

    def test_the_census_reads_the_whole_tree_not_one_directory(self):
        self.tree.add_sim_deck("a/testbench/tb.spice")
        self.tree.add_sim_deck("b/corners/tt_27c_1.80v.spice")
        self.tree.add_sim_deck("c/netlist-snapshots/snap.spice", inductor=True)
        census = checker.ground_return_census()
        self.assertEqual(census["decks"], 3)
        self.assertEqual(census["inductors"], 1)

    def test_the_stats_sentence_is_what_the_check_matches(self):
        """A --stats paste must pass, which is how every readout check is fixed."""
        self.tree.add_sim_deck("a/tb.spice")
        sentence = checker.ground_return_sentence(checker.ground_return_census())
        self.assertEqual(self.check(self.body(sentence)), [])

    def test_the_real_tree_and_the_real_document_agree(self):
        """The live pair, not a fixture: this is what CI actually grades."""
        fixture_root = checker.REPO_ROOT
        checker.REPO_ROOT = REPO_ROOT
        self.addCleanup(lambda: setattr(checker, "REPO_ROOT", fixture_root))
        doc = REPO_ROOT / "docs" / "chipalooza" / "challenge-4-proposal.md"
        self.assertEqual(checker.check_ground_return(doc, doc.read_text()), [])


class TestProvenanceCensus(unittest.TestCase):
    """Check 26: the stated toolchain/PDK provenance census is this tree's own.

    Section 8's reproducibility claim speaks for the whole evidence tree at
    once, so no pointer moves and no Section 4 number budges when it goes
    false -- which it already had, for 33 of the 67 layout records, when this
    check replaced the prose assertion with a census (issue #407).
    """

    ANCHOR = "Pinned by `sim/toolchain.json`.\n"
    SIM_PINNED = "\n## Environment\n\n- PDK: sky130A @ " + "c" * 40 + "\n- ngspice: ngspice-46\n"
    LAYOUT_PINNED = (
        "\n## Provenance\n\n- `klt` version: klt 0.6.0\n- PDK: sky130A (open_pdks "
        + "c" * 40
        + ")\n"
    )
    LAYOUT_VARIANT_ONLY = (
        "\n## Provenance\n\n- `klt` version: klt 0.6.0\n- PDK variant: sky130A\n"
        "- repo commit: `" + "d" * 40 + "` (dirty)\n"
    )

    def setUp(self):
        self.tree = FixtureTree(self)

    def check(self, body: str) -> list[str]:
        return checker.check_provenance_census(self.tree.document(body), body)

    def body(self, sentence: str | None, *, anchor: bool = True) -> str:
        text = "## 8. Licensing and EDA flow\n\n"
        if anchor:
            text += self.ANCHOR
        if sentence is not None:
            text += f"\n> {sentence}\n"
        return text

    def sentence(self, sim_pinned, sim_records, layout_records, layout_klt, layout_pdk) -> str:
        return checker.provenance_sentence(
            {
                "sim_pinned": sim_pinned,
                "sim_records": sim_records,
                "layout_records": layout_records,
                "layout_klt": layout_klt,
                "layout_pdk": layout_pdk,
            }
        )

    def test_a_truthful_census_passes(self):
        self.tree.add_sim_record("full-conversion-transient", "s1", provenance=self.SIM_PINNED)
        self.tree.add_layout_record("comparator", "l1", provenance=self.LAYOUT_PINNED)
        self.assertEqual(self.check(self.body(self.sentence(1, 1, 1, 1, 1))), [])

    def test_a_layout_record_that_pins_nothing_is_counted_as_such(self):
        """The real shortfall's shape: a `klt` version, but only a variant name."""
        self.tree.add_layout_record("comparator", "l1", provenance=self.LAYOUT_PINNED)
        self.tree.add_layout_record("sar-adc-top", "l2", provenance=self.LAYOUT_VARIANT_ONLY)
        self.assertEqual(self.check(self.body(self.sentence(0, 0, 2, 2, 1))), [])

    def test_the_repo_commit_line_is_not_counted_as_pdk_provenance(self):
        """`- repo commit: <40-hex>` is the hash a bare hex search miscounts."""
        self.tree.add_layout_record("sar-adc-top", "l1", provenance=self.LAYOUT_VARIANT_ONLY)
        misses = self.check(self.body(self.sentence(0, 0, 1, 1, 1)))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("layout_pdk=1", misses[0])
        self.assertIn("layout_pdk=0", misses[0])
        self.assertIn("layout/sar-adc-top/reports: 1 of 1", misses[0])

    def test_a_record_stamp_beside_the_word_pdk_is_not_counted(self):
        """The other miscount: a 7-hex stamp abbreviation prose quotes."""
        self.tree.add_layout_record(
            "sar-adc-top",
            "l1",
            provenance="\n- `klt` version: klt 0.6.0\n- PDK deck run on 20260924-234053-66dca3c\n",
        )
        self.assertEqual(self.check(self.body(self.sentence(0, 0, 1, 1, 0))), [])

    def test_a_sim_record_naming_no_ngspice_version_is_not_counted_as_pinned(self):
        self.tree.add_sim_record(
            "full-conversion-transient",
            "s1",
            provenance="\n- PDK: sky130A @ " + "c" * 40 + "\n- each ngspice run is one corner\n",
        )
        misses = self.check(self.body(self.sentence(1, 1, 0, 0, 0)))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("sim_pinned=1", misses[0])
        self.assertIn("sim_pinned=0", misses[0])

    def test_the_erc_record_tree_is_counted_too(self):
        """`erc-reports/` is a record tree of the same kind, and pins nothing."""
        self.tree.add_layout_record("sar-adc-top", "l1", provenance=self.LAYOUT_PINNED)
        self.tree.add_erc_record("sar-adc-top", "e1", provenance="\n- `klt` version: klt 0.6.0\n")
        self.assertEqual(self.check(self.body(self.sentence(0, 0, 2, 2, 1))), [])

    def test_a_drifted_record_count_is_reported(self):
        self.tree.add_sim_record("a", "s1", provenance=self.SIM_PINNED)
        self.tree.add_sim_record("b", "s2", provenance=self.SIM_PINNED)
        misses = self.check(self.body(self.sentence(2, 1, 0, 0, 0)))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("sim_records=1", misses[0])
        self.assertIn("sim_records=2", misses[0])

    def test_stating_no_census_at_all_is_reported(self):
        """Deleting the numbers must not be a way back to "every record"."""
        self.tree.add_layout_record("sar-adc-top", "l1", provenance=self.LAYOUT_VARIANT_ONLY)
        misses = self.check(self.body(None))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("states no census", misses[0])
        self.assertIn("**0** name the `open_pdks` commit", misses[0])

    def test_a_document_that_does_not_cite_the_pin_file_is_not_graded(self):
        self.tree.add_layout_record("sar-adc-top", "l1", provenance=self.LAYOUT_VARIANT_ONLY)
        self.assertEqual(self.check(self.body(None, anchor=False)), [])

    def test_check_is_inert_without_an_evidence_tree(self):
        self.assertEqual(self.check(self.body(None)), [])

    def test_the_stats_sentence_is_what_the_check_matches(self):
        """A --stats paste must pass, which is how every readout check is fixed."""
        self.tree.add_sim_record("a", "s1", provenance=self.SIM_PINNED)
        self.tree.add_layout_record("sar-adc-top", "l1", provenance=self.LAYOUT_VARIANT_ONLY)
        sentence = checker.provenance_sentence(checker.provenance_census())
        self.assertEqual(self.check(self.body(sentence)), [])

    def test_the_real_tree_and_the_real_document_agree(self):
        """The live pair, not a fixture: this is what CI actually grades."""
        fixture_root = checker.REPO_ROOT
        checker.REPO_ROOT = REPO_ROOT
        self.addCleanup(lambda: setattr(checker, "REPO_ROOT", fixture_root))
        doc = REPO_ROOT / "docs" / "chipalooza" / "challenge-4-proposal.md"
        self.assertEqual(checker.check_provenance_census(doc, doc.read_text()), [])

    def test_the_real_layout_shortfall_is_not_vacuous(self):
        """The finding this check was added for, asserted against the live tree.

        A census that could only ever read "all of them" would be a check that
        never fires. The gap issue #407 tracks is real today: some `layout/`
        record names no `open_pdks` commit, and every `sim/` record does.
        """
        fixture_root = checker.REPO_ROOT
        checker.REPO_ROOT = REPO_ROOT
        self.addCleanup(lambda: setattr(checker, "REPO_ROOT", fixture_root))
        census = checker.provenance_census()
        self.assertEqual(census["sim_pinned"], census["sim_records"])
        self.assertLess(census["layout_pdk"], census["layout_records"])
        self.assertTrue(census["unpinned"])


class TestLabelClaimSection(unittest.TestCase):
    """Check 27: a live forge label is stated in one section, not copied.

    The defect shape, taken from the document's own history (2026-09-25):
    Section 3 read "#103 ... still open and `loom:blocked`", Section 4's two
    sign-off-bar rows read "back in the ready queue (`loom:issue`)", and
    Section 7 Item 1 carried the 2026-09-24 escalation to
    `loom:operator-only` -- three readings of one issue, none of which any
    other check here can see, because a forge label is backed by nothing in
    this repository.
    """

    HOME = "## 7. Open items before this design would be ready for the brief's sign-off bar\n"

    def setUp(self):
        self.tree = FixtureTree(self)

    def check(self, body: str) -> list[str]:
        return checker.check_label_claim_section(self.tree.document(body), body)

    def test_a_label_stated_only_in_section_7_passes(self):
        body = self.HOME + "\n1. #103 carries `loom:operator-only` as of 2026-09-24.\n"
        self.assertEqual(self.check(body), [])

    def test_the_real_defect_shape_is_reported(self):
        """Section 3 keeping its own copy of an issue's label -- the live bug."""
        body = (
            "## 3. Functional description\n\n"
            "Tracked as issue #103, still open and `loom:blocked`.\n\n"
            + self.HOME
            + "\n1. #103 carries `loom:operator-only` as of 2026-09-24.\n"
        )
        misses = self.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("Section 3 states `loom:blocked`", misses[0])
        self.assertIn("Section 7", misses[0])

    def test_a_section_4_verdict_row_is_reported_too(self):
        """The copy that misleads hardest: a sign-off-bar row's own cell."""
        body = (
            "## 4. Target specification\n\n"
            "| Post-layout PVT | bar | — | **UNMET** — #103 is back in the ready "
            "queue (`loom:issue`, no `loom:blocked`) | `layout/x/reports/y` |\n\n"
            + self.HOME
        )
        misses = self.check(body)
        self.assertEqual(len(misses), 2, misses)
        self.assertTrue(all("Section 4 states" in miss for miss in misses), misses)

    def test_dropping_the_backticks_is_not_an_escape(self):
        body = "## 3. Functional description\n\n#103 is still loom:blocked.\n\n" + self.HOME
        misses = self.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("`loom:blocked`", misses[0])

    def test_a_loom_directory_path_is_not_a_label(self):
        """`.loom/` has no colon -- the word boundary is what keeps it out."""
        body = "## 3. Functional description\n\nSee `.loom/config.json` and heirloom:\n\n" + self.HOME
        self.assertEqual(self.check(body), [])

    def test_a_fenced_command_example_is_not_a_claim(self):
        """A quoted `gh issue edit` line instructs a reader; it claims nothing."""
        body = (
            "## 3. Functional description\n\n"
            "```bash\ngh issue edit 103 --add-label loom:blocked\n```\n\n" + self.HOME
        )
        self.assertEqual(self.check(body), [])

    def test_section_7s_own_supersession_trail_is_not_graded(self):
        """Section 7 narrates dated history in the present tense, by design."""
        body = (
            self.HOME
            + "\n1. #103 was `loom:blocked` on 2026-09-16 and is `loom:operator-only`"
            " as of 2026-09-24.\n"
        )
        self.assertEqual(self.check(body), [])

    def test_the_front_matter_is_named_rather_than_attributed_to_no_section(self):
        body = "Preamble: #103 is `loom:blocked`.\n\n" + self.HOME
        misses = self.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("The front matter states", misses[0])

    def test_a_document_with_no_section_7_is_not_graded(self):
        body = "## 3. Functional description\n\n#103 is `loom:blocked`.\n"
        self.assertEqual(self.check(body), [])

    def test_stating_no_label_at_all_passes(self):
        """Silence is not a false claim -- the check must not demand a claim."""
        self.assertEqual(self.check("## 3. Functional description\n\nNo labels.\n" + self.HOME), [])

    def test_the_real_document_agrees(self):
        """The live document, not a fixture: this is what CI actually grades."""
        doc = REPO_ROOT / "docs" / "chipalooza" / "challenge-4-proposal.md"
        self.assertEqual(checker.check_label_claim_section(doc, doc.read_text()), [])

    def test_the_real_document_still_states_the_label_somewhere(self):
        """A check satisfied by deleting every claim would be vacuous.

        The document is not required to state a label (see
        `test_stating_no_label_at_all_passes`), but this one does, and the
        point of check 27 is that the surviving copy is the maintained one --
        so assert it is there, in Section 7, rather than that it is gone.
        """
        doc = REPO_ROOT / "docs" / "chipalooza" / "challenge-4-proposal.md"
        claims = checker.label_claims(doc.read_text())
        self.assertTrue(claims)
        self.assertTrue(all(section == 7 for _line, _label, section in claims))
        self.assertIn("operator-only", {label for _line, label, _section in claims})


def corner_matrix_line(
    process: tuple[str, ...],
    temps: tuple[float, ...],
    supplies: tuple[float, ...],
    points: int | None = None,
    *,
    pvt: bool = False,
) -> str:
    """Shape (a): the corner-campaign driver's own header line.

    Written the way `sim/harness/corners.py:corner_matrix_summary_line()`
    writes it, `repr()`-formatted lists and all -- a fixture that wrote a
    tidied-up version would pass while the real line went unparsed. `pvt`
    switches to the "1 PVT point -- **subset-corner justification**: ..."
    wording the single-corner comparator runs use, which is the same field
    with a different noun and must parse identically.
    """
    count = len(process) + len(temps) + len(supplies) - 2 if points is None else points
    tail = (
        f"({count} PVT point -- **subset-corner justification**: first-pass, "
        "nominal-corner-only)"
        if pvt
        else f"({count} points, one-at-a-time per sim/README.md)"
    )
    return (
        f"- **Corner matrix run**: process={list(process)}, "
        f"temperature_c={list(temps)}, supply_v={list(supplies)} {tail}"
    )


def point_matrix_line(*points: str) -> str:
    """Shape (b): the mechanism-budget drivers' `Point/corner matrix` line."""
    return (
        f"- **Point/corner matrix**: {', '.join(points)} only -- a "
        "mechanism-isolating, single-corner first-pass budget"
    )


def stat_point_line(process: str = "tt", temp: float = 27.0, supply: float = 1.8) -> str:
    """Shape (c): the Monte Carlo drivers' `Statistical convention` line."""
    return (
        f"- **Statistical convention**: mismatch corner `{process}_mm`, N=40, "
        f"seed=1, PVT point process={process} temp={temp}C supply={supply}V. "
        "**Subset-corner justification**: nominal PVT point only"
    )


class TestCornerGridCensus(unittest.TestCase):
    """Check 28: Section 4's PVT-grid claim must be counted, not asserted.

    The defect this reproduces is the live one: Section 4 opened "Every row
    below is reported at this repository's own ratified PVT grid ... (9
    points)", and 10 of its 22 (spec row, `sim/` record) citation pairs named
    a record that declares fewer points than that, or none at all. No other
    check here could see it -- checks 3/4/5/23 grade WHICH record a row
    cites, never what corner coverage that record claims for itself.

    The load-bearing fixtures are the three directions a census can lie in:
    a subset record left OUT of the list (the table reading better than it
    is), a record left IN after it grows to the full grid, and the grid
    sentence itself weakened until every citation "meets" it.
    """

    FULL = "20260827-213107-e13bc1e"
    SUBSET = "20260925-050027-0259924"
    MONTE = "20260828-005006-0c70212"
    SILENT = "20260906-173830-6f04f59"

    PROCESS = ("ff", "fs", "sf", "ss", "tt")
    TEMPS = (-40, 27.0, 125)
    SUPPLIES = (1.62, 1.8, 1.98)

    def setUp(self):
        self.tree = FixtureTree(self)
        (self.tree.root / "sim").mkdir(exist_ok=True)
        (self.tree.root / "sim" / "pdk.json").write_text(
            json.dumps({"process_corners": list(self.PROCESS)})
        )
        self.tree.add_sim_record(
            "cdac-array-transfer",
            self.FULL,
            latest=True,
            corners=corner_matrix_line(self.PROCESS, self.TEMPS, self.SUPPLIES),
        )
        self.tree.add_sim_record(
            "comparator-decision",
            self.SUBSET,
            latest=True,
            corners=corner_matrix_line(("tt",), (27.0,), (1.8,), points=1, pvt=True),
        )
        self.tree.add_sim_record(
            "cdac-bit-trial-settling",
            self.MONTE,
            latest=True,
            corners=stat_point_line(),
        )
        # No `corners=` at all: the derived re-analysis that runs no ngspice.
        self.tree.add_sim_record("enob-estimate", self.SILENT, latest=True)

    GRID = (
        "process corners `{ff, fs, sf, ss, tt}`, temperature "
        "`{−40, 27, 125} °C`, supply `{1.62, 1.80, 1.98} V`, "
        "one-at-a-time (9 points)"
    )

    def _table(self) -> str:
        return spec_table(
            f"| `V_REF` | 1.8 V | RATIFIED | **MET** | "
            f"`sim/cdac-array-transfer/records/{self.FULL}.md` |",
            # Deliberately NOT named "Kickback": that row has a check of its
            # own (21), and a fixture that tripped it would report two
            # findings where this class asserts one.
            f"| Comparator input-referred noise | ≤ 1.0148 mV rms | RATIFIED "
            f"| **MET** | `sim/comparator-decision/records/{self.SUBSET}.md` |",
            f"| INL / DNL | ≤ ±2.0 LSB | DRAFT | **Informational only** | "
            f"`sim/cdac-bit-trial-settling/records/{self.MONTE}.md` |",
            f"| ENOB | > 7.5 bit | DRAFT | **Informational only** | "
            f"`sim/enob-estimate/records/{self.SILENT}.md` |",
        )

    def _sentence(self, pairs, full, subset, unstated, records, points=9) -> str:
        rendered = (
            ", ".join(
                f"`{record}` (no PVT point set)"
                if count is None
                else f"`{record}` (**{count}** point{'' if count == 1 else 's'})"
                for record, count in records
            )
            or checker.CORNER_GRID_NONE
        )
        return (
            f"of the **{pairs}** (spec row, `sim/` record) citation pairs in "
            f"Section 4's table, **{full}** name a record that declares the "
            f"full **{points}**-point grid, **{subset}** name one that "
            f"declares a smaller PVT point set, and **{unstated}** name one "
            f"that declares no PVT point set of its own: {rendered}.\n"
        )

    def _exceptions(self):
        return [
            (f"sim/cdac-bit-trial-settling/records/{self.MONTE}.md", 1),
            (f"sim/comparator-decision/records/{self.SUBSET}.md", 1),
            (f"sim/enob-estimate/records/{self.SILENT}.md", None),
        ]

    def _body(self, sentence: str = "", grid: str = "") -> str:
        return f"{self._table()}\n{grid or self.GRID}\n\n{sentence}"

    def test_all_three_record_shapes_are_parsed(self):
        """Keying on the campaign line alone would misreport two of the three."""
        full = checker.declared_pvt_points(
            corner_matrix_line(self.PROCESS, self.TEMPS, self.SUPPLIES)
        )
        self.assertEqual(full["points"], 9, full)
        self.assertEqual(full["process"], self.PROCESS, full)
        self.assertEqual(full["temps"], (-40.0, 27.0, 125.0), full)

        budget = checker.declared_pvt_points(point_matrix_line("`tt`/27C/1.8V"))
        self.assertEqual(budget["points"], 1, budget)
        self.assertEqual(budget["process"], ("tt",), budget)

        monte = checker.declared_pvt_points(stat_point_line())
        self.assertEqual(monte["points"], 1, monte)

        self.assertIsNone(checker.declared_pvt_points("fixture record\n"))

    def test_census_of_a_known_table_is_computed_per_row_record_pair(self):
        census = checker.corner_grid_census(self._body())
        self.assertEqual(census["pairs"], 4, census)
        self.assertEqual(census["full"], 1, census)
        self.assertEqual(census["subset"], 2, census)
        self.assertEqual(census["unstated"], 1, census)
        self.assertEqual(census["records"], self._exceptions(), census)

    def test_a_truthful_census_passes(self):
        body = self._body(self._sentence(4, 1, 2, 1, self._exceptions()))
        self.assertEqual(self.tree.check(body), [])

    def test_an_absent_census_is_a_finding_not_a_silence(self):
        """The blanket sentence must not be able to stand alone again."""
        misses = self.tree.check(self._body())
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("states no census", misses[0])

    def test_an_omitted_subset_record_is_reported(self):
        """The direction that matters: the table reading better than it is."""
        kept = [item for item in self._exceptions() if "comparator" not in item[0]]
        misses = self.tree.check(self._body(self._sentence(4, 1, 2, 1, kept)))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn(
            f"omits `sim/comparator-decision/records/{self.SUBSET}.md`", misses[0]
        )

    def test_a_record_that_grows_to_the_full_grid_must_leave_the_list(self):
        (
            self.tree.root
            / "sim"
            / "comparator-decision"
            / "records"
            / f"{self.SUBSET}.md"
        ).write_text(
            "fixture record\n"
            + corner_matrix_line(self.PROCESS, self.TEMPS, self.SUPPLIES)
            + "\n"
        )
        misses = self.tree.check(self._body(self._sentence(4, 1, 2, 1, self._exceptions())))
        self.assertTrue(
            any(f"lists `sim/comparator-decision/records/{self.SUBSET}.md`" in m for m in misses),
            misses,
        )
        self.assertTrue(any("full=1" in m and "full=2" in m for m in misses), misses)

    def test_a_weakened_process_axis_is_reported_against_the_pdk_pin(self):
        """Redefining "the full grid" must not be a way to pass the census."""
        weakened = self.GRID.replace("{ff, fs, sf, ss, tt}", "{ss, tt}")
        misses = self.tree.check(
            self._body(self._sentence(4, 0, 3, 1, self._exceptions()), grid=weakened)
        )
        self.assertTrue(any("`sim/pdk.json` pins" in m for m in misses), misses)
        self.assertTrue(any("|P| + |T| + |S| - 2" in m for m in misses), misses)

    def test_the_point_count_must_match_the_axes_the_sentence_names(self):
        mismatched = self.GRID.replace("(9 points)", "(45 points)")
        misses = self.tree.check(
            self._body(self._sentence(4, 0, 3, 1, self._exceptions(), points=45), grid=mismatched)
        )
        self.assertTrue(any("which is 9 points" in m for m in misses), misses)

    def test_a_document_stating_no_grid_is_not_graded(self):
        """Opt-in per document, like checks 6 and 18: a fixture invents none."""
        self.assertIsNone(checker.corner_grid_census(self._table()))
        self.assertEqual(self.tree.check(self._table()), [])

    def test_a_fully_covered_table_renders_and_accepts_none(self):
        for campaign, stamp in (
            ("comparator-decision", self.SUBSET),
            ("cdac-bit-trial-settling", self.MONTE),
            ("enob-estimate", self.SILENT),
        ):
            (self.tree.root / "sim" / campaign / "records" / f"{stamp}.md").write_text(
                "fixture record\n"
                + corner_matrix_line(self.PROCESS, self.TEMPS, self.SUPPLIES)
                + "\n"
            )
        census = checker.corner_grid_census(self._body())
        self.assertEqual(census["records"], [], census)
        self.assertIn(checker.CORNER_GRID_NONE, checker.corner_grid_sentence(census))
        self.assertEqual(self.tree.check(self._body(self._sentence(4, 4, 0, 0, []))), [])

    def test_the_stats_sentence_is_what_the_check_accepts(self):
        """A `--stats` paste must pass, or the documented fix does not work."""
        body = self._body()
        sentence = checker.corner_grid_sentence(checker.corner_grid_census(body))
        self.assertEqual(self.tree.check(body + sentence + "\n"), [])

    def test_the_sentence_is_not_counted_as_a_pointer_claim(self):
        """It must not enrol itself in check 4/6's census, as check 18's does not."""
        sentence = self._sentence(4, 1, 2, 1, self._exceptions())
        self.assertEqual(checker.pointer_claim_census(sentence)["total"], 0)


class TestAbsentPaths(unittest.TestCase):
    """Check 29: a path asserted to be absent from this tree really is absent.

    The defect shape, taken from the document's own history (2026-09-25):
    Section 7 had to report that a sub-block existed only in an unmerged PR,
    but check 2 fails on any own-tree path that does not resolve -- so the
    only sayable form was a gesture at the parent directory ("no such flow
    exists under `layout/`"), which names nothing the gate can re-evaluate
    and therefore still reads true on the day the PR merges.
    """

    def setUp(self):
        self.tree = FixtureTree(self)

    def check(self, body: str) -> list[str]:
        return checker.check_absent_paths(self.tree.document(body), body)

    def bare_paths(self, body: str) -> list[str]:
        return checker.check_bare_paths(self.tree.document(body), body)

    def test_a_genuinely_absent_path_passes(self):
        body = "The flow `layout/top-glue/` (not in this tree) has not landed.\n"
        self.assertEqual(self.check(body), [])

    def test_the_absence_ending_is_reported(self):
        """The whole point: the day the work lands, this passage must fail."""
        self.tree.add_layout_record("top-glue", "20260925-000000-abc1234", latest=True)
        body = "The flow `layout/top-glue/` (not in this tree) has not landed.\n"
        misses = self.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("`layout/top-glue/`", misses[0])
        self.assertIn("asserted absent", misses[0])

    def test_check_2_skips_what_check_29_grades(self):
        """Otherwise the document could not name an absent path at all."""
        body = "The flow `layout/top-glue/` (not in this tree) has not landed.\n"
        self.assertEqual(self.bare_paths(body), [])

    def test_check_2_still_grades_an_unmarked_missing_path(self):
        """The exemption is opt-in; dropping the marker restores check 2."""
        body = "The flow `layout/top-glue/` has not landed.\n"
        misses = self.bare_paths(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("does not exist", misses[0])

    def test_the_marker_must_be_attached(self):
        """Prose discussing an absence near a path is not a claim about it."""
        body = (
            "The flow `layout/top-glue/` is one of three pieces, and the "
            "other two are (not in this tree) either.\n"
        )
        self.assertEqual(self.check(body), [])
        # ...and check 2 still grades it, so nothing escaped both checks.
        self.assertEqual(len(self.bare_paths(body)), 1)

    def test_a_single_line_wrap_between_path_and_marker_is_tolerated(self):
        body = "The flow `layout/top-glue/`\n(not in this tree) has not landed.\n"
        self.assertEqual(self.check(body), [])
        self.assertEqual(self.bare_paths(body), [])

    def test_a_marker_spent_on_a_glob_is_reported(self):
        """Else the marker exempts a reference from check 2 AND check 29."""
        body = "Every `layout/*/top-glue/` (not in this tree) is missing.\n"
        misses = self.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("not a concrete path", misses[0])

    def test_a_marker_spent_on_an_upstream_path_is_reported(self):
        body = "Upstream's `src/klayout_tools/lvs.py` (not in this tree) is gone.\n"
        misses = self.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("not a concrete path", misses[0])

    def test_stating_no_absence_at_all_passes(self):
        """Silence is not a false claim -- the check must not demand a marker."""
        self.assertEqual(self.check("No absences are claimed here.\n"), [])

    def test_the_scan_reports_line_and_offset(self):
        """`absent_claims` is shared with check 2, so its offsets must line up."""
        body = "Intro.\n\nThe flow `layout/top-glue/` (not in this tree).\n"
        claims = checker.absent_claims(body)
        self.assertEqual(len(claims), 1, claims)
        line, offset, path = claims[0]
        self.assertEqual(line, 3)
        self.assertEqual(path, "layout/top-glue/")
        self.assertEqual(body[offset], "`")

    def test_the_real_document_agrees(self):
        """The live document, not a fixture: this is what CI actually grades."""
        doc = REPO_ROOT / "docs" / "chipalooza" / "challenge-4-proposal.md"
        self.assertEqual(checker.check_absent_paths(doc, doc.read_text()), [])

    def test_the_real_document_still_makes_an_absence_claim(self):
        """A check satisfied by deleting every claim would be vacuous."""
        doc = REPO_ROOT / "docs" / "chipalooza" / "challenge-4-proposal.md"
        claims = checker.absent_claims(doc.read_text())
        self.assertTrue(claims)
        self.assertTrue(
            all(checker._own_tree_path(path) for _line, _offset, path in claims),
            claims,
        )


class TestRendererCensus(unittest.TestCase):
    """Check 30: the stated record-renderer census is this tree's own.

    Check 26 counts records, which are append-only -- so its census is a
    lagging indicator that reads identically whether a shortfall is live or
    is already-fixed history awaiting a re-run. The document explained which
    in prose, and the prose went false the day PR #420 (issue #407) fixed the
    four renderers that printed only a PDK variant name, with every number
    beside it still true. This check grades that explanation.
    """

    # The two real renderer shapes, reduced to the line each is recognised by.
    INLINE = 'pdk_info = json.loads(run([klt, "pdk", "find", "--format", "json"]))\n'
    DELEGATING = "from _record_common import build_argparser, render_pnr_drc_lvs_record\n"
    VARIANT_ONLY = 'a(f"- PDK variant: {args.pdk_variant}")\n'
    SHARED_PINNED = "def resolve_pdk_commit(klt, pdk_variant):\n    ...\n"
    SHARED_UNPINNED = "def render_pnr_drc_lvs_record(title, args):\n    ...\n"

    # Check 30 is anchored on the document stating check 26's record census,
    # so every fixture body carries one. The numbers in it are never graded
    # here (that is check 26's own test); only its presence is.
    ANCHOR = (
        "> **1** of the **1** records under `sim/*/records/` name both an "
        "`ngspice` version and a 40-hex `open_pdks` commit, while of the "
        "**1** records under `layout/*/reports/` and `layout/*/erc-reports/` "
        "**1** name a `klt` version and **1** name the `open_pdks` commit\n"
    )

    def setUp(self):
        self.tree = FixtureTree(self)

    def check(self, body: str) -> list[str]:
        return checker.check_renderer_census(self.tree.document(body), body)

    def body(self, sentence: str | None, *, anchor: bool = True) -> str:
        text = "## 8. Licensing and EDA flow\n\n"
        if anchor:
            text += self.ANCHOR
        if sentence is not None:
            text += f"\n> {sentence}\n"
        return text

    def sentence(self, entry_points, pinning, naming, unpinned=()) -> str:
        return checker.renderer_sentence(
            {
                "entry_points": entry_points,
                "pinning": pinning,
                "naming": naming,
                "unpinned": list(unpinned),
            }
        )

    def test_a_truthful_all_pinned_census_passes(self):
        self.tree.add_layout_record("comparator", "l1")
        self.tree.add_renderer("layout/comparator/bin/render-record.py", self.INLINE)
        self.assertEqual(self.check(self.body(self.sentence(1, 1, 0))), [])

    def test_a_renderer_that_prints_only_the_variant_name_is_counted_as_such(self):
        """The real pre-#420 shortfall's shape."""
        self.tree.add_layout_record("comparator", "l1")
        self.tree.add_renderer("layout/comparator/bin/render-record.py", self.INLINE)
        self.tree.add_layout_record("sar-adc-top", "l2")
        self.tree.add_renderer("layout/sar-adc-top/bin/render-record.py", self.VARIANT_ONLY)
        self.assertEqual(
            self.check(
                self.body(
                    self.sentence(2, 1, 1, ("layout/sar-adc-top/bin/render-record.py",))
                )
            ),
            [],
        )

    def test_a_drifted_count_is_reported(self):
        self.tree.add_layout_record("sar-adc-top", "l1")
        self.tree.add_renderer("layout/sar-adc-top/bin/render-record.py", self.VARIANT_ONLY)
        misses = self.check(self.body(self.sentence(1, 1, 0)))
        self.assertTrue(misses)
        self.assertTrue(any("pinning=1" in miss and "pinning=0" in miss for miss in misses))

    def test_a_drifted_offender_list_is_reported_even_when_the_counts_agree(self):
        """The failure a count-only census would absorb: right total, wrong file."""
        self.tree.add_layout_record("sar-adc-top", "l1")
        self.tree.add_renderer("layout/sar-adc-top/bin/render-record.py", self.VARIANT_ONLY)
        misses = self.check(
            self.body(self.sentence(1, 0, 1, ("layout/cdac-array/bin/render-record.py",)))
        )
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("layout/cdac-array/bin/render-record.py", misses[0])
        self.assertIn("layout/sar-adc-top/bin/render-record.py", misses[0])

    def test_delegation_to_the_shared_record_builder_is_followed(self):
        """sar-sequencer/seln-inverters are a title and a shared call, nothing else."""
        self.tree.add_layout_record("sar-sequencer", "l1")
        self.tree.add_renderer("layout/sar-sequencer/bin/render-record.py", self.DELEGATING)
        self.tree.add_renderer("layout/bin/_record_common.py", self.SHARED_PINNED)
        self.assertEqual(self.check(self.body(self.sentence(1, 1, 0))), [])

    def test_delegation_to_an_unpinned_shared_builder_is_counted_as_unpinned(self):
        """Following the delegation must be able to report a miss, not only a hit."""
        self.tree.add_layout_record("sar-sequencer", "l1")
        self.tree.add_renderer("layout/sar-sequencer/bin/render-record.py", self.DELEGATING)
        self.tree.add_renderer("layout/bin/_record_common.py", self.SHARED_UNPINNED)
        self.assertEqual(
            self.check(
                self.body(
                    self.sentence(1, 0, 1, ("layout/sar-sequencer/bin/render-record.py",))
                )
            ),
            [],
        )

    def test_importing_the_shared_module_without_delegating_inherits_no_pin(self):
        """`build_argparser` alone delegates no provenance and must not count."""
        self.tree.add_layout_record("cdac-array", "l1")
        self.tree.add_renderer(
            "layout/cdac-array/bin/render-record.py",
            "from _record_common import build_argparser\n" + self.VARIANT_ONLY,
        )
        self.tree.add_renderer("layout/bin/_record_common.py", self.SHARED_PINNED)
        self.assertEqual(
            self.check(
                self.body(
                    self.sentence(1, 0, 1, ("layout/cdac-array/bin/render-record.py",))
                )
            ),
            [],
        )

    def test_a_flow_without_its_own_renderer_falls_back_to_the_shared_one(self):
        """`layout/trivial-cell/` has no `bin/` of its own."""
        self.tree.add_layout_record("trivial-cell", "l1")
        self.tree.add_renderer("layout/bin/render-record.py", self.INLINE)
        self.assertEqual(self.check(self.body(self.sentence(1, 1, 0))), [])

    def test_the_erc_tree_is_graded_against_its_own_driver(self):
        """`erc-reports/record.md` is hand-written from what run-erc.sh prints."""
        self.tree.add_erc_record("sar-adc-top", "e1")
        self.tree.add_renderer(
            "layout/sar-adc-top/bin/run-erc.sh", "python3 -c 'from _record_common import "
            "resolve_pdk_commit'\n"
        )
        self.assertEqual(self.check(self.body(self.sentence(1, 1, 0))), [])

    def test_a_comment_only_pdk_find_mention_is_not_counted_as_resolving(self):
        """Issue #424: a comment *spelling out* `klt pdk find` is not a call.

        `RENDERER_PIN_RE` used to have a third, unanchored alternative,
        `\\bpdk find\\b`, that matched the phrase anywhere in the file --
        including inside a `#` comment explaining an approach the script does
        *not* take. A renderer whose only mention of the phrase is such a
        comment, with no real invocation anywhere, must be counted unpinned.
        """
        self.tree.add_layout_record("sar-adc-top", "l1")
        self.tree.add_renderer(
            "layout/sar-adc-top/bin/render-record.py",
            "# rather than re-parsing 'klt pdk find --format json' here\n"
            + self.VARIANT_ONLY,
        )
        self.assertEqual(
            self.check(
                self.body(
                    self.sentence(1, 0, 1, ("layout/sar-adc-top/bin/render-record.py",))
                )
            ),
            [],
        )

    def test_a_comment_only_resolve_pdk_commit_mention_is_not_counted_as_resolving(
        self,
    ):
        """The same failure shape one alternative over: naming, not calling.

        `resolve_pdk_commit` is a real Python identifier, so even the
        narrower, argv-anchored form of `RENDERER_PIN_RE` is satisfied by a
        comment that merely *names* it -- e.g. explaining that the pin is
        obtained elsewhere -- unless comments are stripped before matching.
        """
        self.tree.add_layout_record("sar-adc-top", "l1")
        self.tree.add_renderer(
            "layout/sar-adc-top/bin/render-record.py",
            "# Reuses layout/bin/_record_common.py's own `resolve_pdk_commit`\n"
            + self.VARIANT_ONLY,
        )
        self.assertEqual(
            self.check(
                self.body(
                    self.sentence(1, 0, 1, ("layout/sar-adc-top/bin/render-record.py",))
                )
            ),
            [],
        )

    def test_the_run_erc_comment_only_repro_is_counted_as_unpinned(self):
        """The literal regression this issue reproduced.

        `run-erc.sh`'s real comment (issue #407) explains, in prose, why it
        reuses `resolve_pdk_commit` instead of re-parsing `klt pdk find`
        itself -- naming both pin spellings without calling either. Stripped
        of the real call, this entry point must flip from pinned to unpinned.
        """
        self.tree.add_erc_record("sar-adc-top", "e1")
        self.tree.add_renderer(
            "layout/sar-adc-top/bin/run-erc.sh",
            "# Reuses layout/bin/_record_common.py's own `resolve_pdk_commit`\n"
            "# (issue #407) rather than re-parsing `klt pdk find --format json`\n"
            "# here, so this script's PDK pin can never drift.\n"
            + self.VARIANT_ONLY,
        )
        self.assertEqual(
            self.check(
                self.body(
                    self.sentence(1, 0, 1, ("layout/sar-adc-top/bin/run-erc.sh",))
                )
            ),
            [],
        )

    def test_one_renderer_minting_two_record_trees_is_counted_once(self):
        """Entry points, not record trees: a fix is made in one place."""
        self.tree.add_layout_record("trivial-cell", "l1")
        self.tree.add_layout_record("cdac-array", "l2")
        self.tree.add_renderer("layout/bin/render-record.py", self.INLINE)
        self.assertEqual(self.check(self.body(self.sentence(1, 1, 0))), [])

    def test_a_record_tree_with_no_entry_point_at_all_is_reported(self):
        self.tree.add_layout_record("ghost-flow", "l1")
        self.assertEqual(
            self.check(
                self.body(self.sentence(1, 0, 1, ("layout/bin/render-record.py",)))
            ),
            [],
        )

    def test_stating_no_renderer_census_at_all_is_reported(self):
        """Dropping it must not be a way back to an unqualified record census."""
        self.tree.add_layout_record("sar-adc-top", "l1")
        self.tree.add_renderer("layout/sar-adc-top/bin/render-record.py", self.VARIANT_ONLY)
        misses = self.check(self.body(None))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("states check 26's record census but not the renderer census", misses[0])
        self.assertIn("layout/sar-adc-top/bin/render-record.py", misses[0])

    def test_a_document_without_the_record_census_is_not_graded(self):
        self.tree.add_layout_record("sar-adc-top", "l1")
        self.tree.add_renderer("layout/sar-adc-top/bin/render-record.py", self.VARIANT_ONLY)
        self.assertEqual(self.check(self.body(None, anchor=False)), [])

    def test_check_is_inert_without_a_layout_tree(self):
        self.assertEqual(self.check(self.body(None)), [])

    def test_the_stats_sentence_is_what_the_check_matches(self):
        """A --stats paste must pass, which is how every readout check is fixed."""
        self.tree.add_layout_record("comparator", "l1")
        self.tree.add_renderer("layout/comparator/bin/render-record.py", self.INLINE)
        self.tree.add_layout_record("sar-adc-top", "l2")
        self.tree.add_renderer("layout/sar-adc-top/bin/render-record.py", self.VARIANT_ONLY)
        sentence = checker.renderer_sentence(checker.renderer_census())
        self.assertEqual(self.check(self.body(sentence)), [])

    def test_the_real_tree_and_the_real_document_agree(self):
        """The live pair, not a fixture: this is what CI actually grades."""
        fixture_root = checker.REPO_ROOT
        checker.REPO_ROOT = REPO_ROOT
        self.addCleanup(lambda: setattr(checker, "REPO_ROOT", fixture_root))
        doc = REPO_ROOT / "docs" / "chipalooza" / "challenge-4-proposal.md"
        self.assertEqual(checker.check_renderer_census(doc, doc.read_text()), [])

    def test_the_real_census_covers_every_record_tree_in_the_tree(self):
        """Not vacuous: the census must span the real record trees, not a subset.

        A discovery rule that silently resolved nothing would make this check
        pass by counting zero entry points -- the same vacuity trap checks 4
        and 6 each needed a guard for.
        """
        fixture_root = checker.REPO_ROOT
        checker.REPO_ROOT = REPO_ROOT
        self.addCleanup(lambda: setattr(checker, "REPO_ROOT", fixture_root))
        trees = sorted(
            path
            for glob in (checker.RENDERER_REPORT_GLOB, checker.RENDERER_ERC_GLOB)
            for path in REPO_ROOT.glob(glob)
            if path.is_dir()
        )
        self.assertTrue(trees, "no layout record trees found")
        census = checker.renderer_census()
        self.assertGreaterEqual(census["entry_points"], 1)
        self.assertLessEqual(census["entry_points"], len(trees))
        self.assertEqual(census["pinning"] + census["naming"], census["entry_points"])
        # Every entry point the census resolved is a file that exists -- the
        # "no entry point at all" arm must be reachable but not silently live.
        self.assertEqual(census["unpinned"], [])


class TestArmCensus(unittest.TestCase):
    """Check 31: the stated supply-return arm census is this tree's own.

    Check 28 censuses the PVT grid a cited record covers. This campaign's
    records are a subset of a second axis its *runner* defines -- the
    supply-return arms -- and Section 7's DR-012 retirement is bounded by the
    arm it left unrun ("no priced-rejected-option claim may be read from this
    record"). Nothing graded that sentence, so a record pricing the null
    option would leave it reading "not run" with every number beside it still
    true: check 30's defect shape, one axis over.
    """

    ARMS = ("ideal", "package-r-only", "package", "substrate", "no-gnd-pad")

    def setUp(self):
        self.tree = FixtureTree(self)

    def check(self, body: str) -> list[str]:
        return checker.check_arm_census(self.tree.document(body), body)

    def body(self, sentence: str | None, *, anchor: bool = True) -> str:
        text = "## 7. Open items\n\n"
        if anchor:
            text += f"See [the campaign](../../{checker.ARM_POINTER}).\n"
        if sentence is not None:
            text += f"\n> {sentence}\n"
        return text

    def sentence(self, offered, ran, unrun, unrun_arms=()) -> str:
        return checker.arm_sentence(
            {
                "offered": offered,
                "ran": ran,
                "unrun": unrun,
                "unrun_arms": list(unrun_arms),
            }
        )

    def campaign(self, *, ran=ARMS[:4], offered=ARMS, **kwargs):
        self.tree.add_arm_runner(*offered)
        self.tree.add_sim_record(
            checker.ARM_CAMPAIGN, "20260925-073912-0e385e5", latest=True, arms=ran, **kwargs
        )

    def test_a_truthful_census_with_one_unrun_arm_passes(self):
        """Today's real shape: four arms run, `no-gnd-pad` priced by nothing."""
        self.campaign()
        self.assertEqual(self.check(self.body(self.sentence(5, 4, 1, ("no-gnd-pad",)))), [])

    def test_a_truthful_all_run_census_passes(self):
        """The case #409 item 2 creates: the null option finally priced."""
        self.campaign(ran=self.ARMS)
        self.assertEqual(self.check(self.body(self.sentence(5, 5, 0))), [])

    def test_a_record_that_prices_the_unrun_arm_falsifies_the_old_census(self):
        """The drift this check exists for, stated as the failure it must be."""
        self.campaign(ran=self.ARMS)
        misses = self.check(self.body(self.sentence(5, 4, 1, ("no-gnd-pad",))))
        self.assertTrue(misses)
        self.assertTrue(any("ran=4" in miss and "ran=5" in miss for miss in misses))
        self.assertTrue(any("no-gnd-pad" in miss and "none" in miss for miss in misses))

    def test_a_new_arm_in_the_runner_widens_the_census(self):
        """The other direction: an arm added to the runner and never run."""
        self.campaign(offered=self.ARMS + ("bondwire-sweep",))
        misses = self.check(self.body(self.sentence(5, 4, 1, ("no-gnd-pad",))))
        self.assertTrue(misses)
        self.assertTrue(any("offered=5" in miss and "offered=6" in miss for miss in misses))

    def test_a_drifted_arm_list_is_reported_even_when_the_counts_agree(self):
        """Right total, wrong arm -- the failure a count-only census absorbs."""
        self.campaign()
        misses = self.check(self.body(self.sentence(5, 4, 1, ("substrate",))))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("`substrate`", misses[0])
        self.assertIn("`no-gnd-pad`", misses[0])

    def test_the_unrun_list_keeps_the_runner_s_own_order(self):
        """Not alphabetical: the record's omission section reads in this order."""
        self.campaign(ran=("ideal",))
        census = checker.arm_census()
        self.assertEqual(
            census["unrun_arms"], ["package-r-only", "package", "substrate", "no-gnd-pad"]
        )

    def test_an_absent_census_is_itself_a_finding(self):
        """Deleting the sentence must not widen what the citation may claim."""
        self.campaign()
        misses = self.check(self.body(None))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("states no arm census", misses[0])
        self.assertIn("`no-gnd-pad`", misses[0])

    def test_a_document_that_does_not_cite_the_campaign_is_not_graded(self):
        self.campaign()
        self.assertEqual(self.check(self.body(None, anchor=False)), [])

    def test_the_arms_are_read_from_the_list_not_from_the_printed_count(self):
        """A count and a list that disagree are graded on the names."""
        self.campaign(arm_count=99)
        self.assertEqual(self.check(self.body(self.sentence(5, 4, 1, ("no-gnd-pad",)))), [])

    def test_a_runner_whose_table_is_unrecognised_grades_nothing(self):
        """No tree-side number to compare against is a silence, not a zero."""
        self.tree.add_arm_runner(table="ARMS = build_arms()\n")
        self.tree.add_sim_record(
            checker.ARM_CAMPAIGN, "20260925-073912-0e385e5", latest=True, arms=self.ARMS[:4]
        )
        self.assertIsNone(checker.arm_census())
        self.assertEqual(self.check(self.body(None)), [])

    def test_a_record_without_an_arms_line_grades_nothing(self):
        self.tree.add_arm_runner(*self.ARMS)
        self.tree.add_sim_record(
            checker.ARM_CAMPAIGN, "20260925-073912-0e385e5", latest=True
        )
        self.assertIsNone(checker.arm_census())
        self.assertEqual(self.check(self.body(None)), [])

    def test_a_campaign_without_a_latest_pointer_grades_nothing(self):
        self.tree.add_arm_runner(*self.ARMS)
        self.tree.add_sim_record(
            checker.ARM_CAMPAIGN, "20260925-073912-0e385e5", arms=self.ARMS[:4]
        )
        self.assertIsNone(checker.arm_census())
        self.assertEqual(self.check(self.body(None)), [])

    def test_check_is_inert_without_the_campaign_at_all(self):
        self.assertEqual(self.check(self.body(None)), [])

    def test_the_stats_sentence_is_what_the_check_matches(self):
        """A --stats paste must pass, which is how every readout check is fixed."""
        self.campaign()
        self.assertEqual(self.check(self.body(checker.arm_sentence(checker.arm_census()))), [])

    def test_the_real_tree_and_the_real_document_agree(self):
        """The live pair, not a fixture: this is what CI actually grades."""
        fixture_root = checker.REPO_ROOT
        checker.REPO_ROOT = REPO_ROOT
        self.addCleanup(lambda: setattr(checker, "REPO_ROOT", fixture_root))
        doc = REPO_ROOT / "docs" / "chipalooza" / "challenge-4-proposal.md"
        self.assertEqual(checker.check_arm_census(doc, doc.read_text()), [])

    def test_the_real_census_parses_the_real_runner_and_record(self):
        """Not vacuous: both halves must resolve against the live tree.

        A parse that silently resolved nothing would make the check pass by
        comparing two empty sets -- the vacuity trap checks 4, 6 and 30 each
        needed a guard for.
        """
        fixture_root = checker.REPO_ROOT
        checker.REPO_ROOT = REPO_ROOT
        self.addCleanup(lambda: setattr(checker, "REPO_ROOT", fixture_root))
        offered = checker.runner_arms()
        ran = checker.record_arms()
        self.assertIn("no-gnd-pad", offered)
        self.assertIn("ideal", offered)
        self.assertTrue(ran)
        self.assertTrue(set(ran) <= set(offered), (ran, offered))
        census = checker.arm_census()
        self.assertEqual(census["ran"] + census["unrun"], census["offered"])
        self.assertEqual(census["offered"], len(offered))


class TestSweepCensus(unittest.TestCase):
    """Check 32: the stated `--sweep` box census is this tree's own.

    Check 31 grades which ARMS a record ran. This grades a MODE of the same
    runner that has no record at all and, by design, cannot acquire one any
    other check here would see: a sweep record never becomes
    `records/LATEST` (checks 3/4/6/23), runs at one corner (check 28) and
    carries no `- **Arms**:` line (check 31). Section 7 Item 11 bounds its
    DR-012 retirement on the box being unwalked, so walking it would leave
    that sentence false with every number beside it still true.
    """

    def setUp(self):
        self.tree = FixtureTree(self)

    def check(self, body: str) -> list[str]:
        return checker.check_sweep_census(self.tree.document(body), body)

    def body(self, sentence: str | None, *, anchor: bool = True) -> str:
        text = "## 7. Open items\n\n"
        if anchor:
            text += f"See [the campaign](../../{checker.SWEEP_RECORDS}/LATEST).\n"
        if sentence is not None:
            text += f"\n> {sentence}\n"
        return text

    def sentence(self, points, l_mults, rsubx, covered, records, record_ids=()) -> str:
        return checker.sweep_sentence(
            {
                "points": points,
                "l_mults": l_mults,
                "rsubx": rsubx,
                "covered": covered,
                "records": records,
                "record_ids": list(record_ids),
            }
        )

    def campaign(self, **kwargs):
        """Today's real shape: a 3x3 box defined, an arm record, no sweep."""
        self.tree.add_sweep_axes(**kwargs)
        self.tree.add_sim_record(
            checker.ARM_CAMPAIGN,
            "20260925-073912-0e385e5",
            latest=True,
            arms=("ideal", "package-r-only", "package", "substrate"),
        )

    def test_a_truthful_unwalked_census_passes(self):
        self.campaign()
        self.assertEqual(self.check(self.body(self.sentence(9, 3, 3, 0, 0))), [])

    def test_a_sweep_record_falsifies_the_unwalked_census(self):
        """The drift this check exists for, stated as the failure it must be."""
        self.campaign()
        self.tree.add_sim_record(checker.ARM_CAMPAIGN, "20260926-101010-abcdef0", sweep_points=9)
        misses = self.check(self.body(self.sentence(9, 3, 3, 0, 0)))
        self.assertTrue(misses)
        self.assertTrue(any("covered=0" in miss and "covered=9" in miss for miss in misses))
        self.assertTrue(any("records=0" in miss and "records=1" in miss for miss in misses))
        self.assertTrue(any("20260926-101010-abcdef0" in miss for miss in misses))

    def test_a_truthful_walked_census_passes(self):
        """The case #409 item 3 creates: the box finally paid for."""
        self.campaign()
        self.tree.add_sim_record(checker.ARM_CAMPAIGN, "20260926-101010-abcdef0", sweep_points=9)
        self.assertEqual(
            self.check(self.body(self.sentence(9, 3, 3, 9, 1, ("20260926-101010-abcdef0",)))),
            [],
        )

    def test_a_wider_box_in_the_runner_widens_the_census(self):
        """The other direction: an axis lengthened and nothing run."""
        self.campaign(l_mults=(0.0, 1.0, 10.0, 100.0))
        misses = self.check(self.body(self.sentence(9, 3, 3, 0, 0)))
        self.assertTrue(misses)
        self.assertTrue(any("points=9" in miss and "points=12" in miss for miss in misses))
        self.assertTrue(any("l_mults=3" in miss and "l_mults=4" in miss for miss in misses))

    def test_a_drifted_record_list_is_reported_even_when_the_counts_agree(self):
        """Right totals, wrong record -- what a count-only census absorbs."""
        self.campaign()
        self.tree.add_sim_record(checker.ARM_CAMPAIGN, "20260926-101010-abcdef0", sweep_points=9)
        misses = self.check(self.body(self.sentence(9, 3, 3, 9, 1, ("20260101-000000-0000000",))))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("20260101-000000-0000000", misses[0])
        self.assertIn("20260926-101010-abcdef0", misses[0])

    def test_covered_is_the_largest_box_not_the_sum(self):
        """Two records of the same box are two runs of one experiment."""
        self.campaign()
        self.tree.add_sim_record(checker.ARM_CAMPAIGN, "20260926-101010-abcdef0", sweep_points=9)
        self.tree.add_sim_record(checker.ARM_CAMPAIGN, "20260927-101010-abcdef1", sweep_points=4)
        census = checker.sweep_census()
        self.assertEqual(census["covered"], 9)
        self.assertEqual(census["records"], 2)
        self.assertEqual(
            census["record_ids"], ["20260926-101010-abcdef0", "20260927-101010-abcdef1"]
        )

    def test_an_arm_comparison_record_is_not_a_sweep_record(self):
        """The two writers share a tree; only one emits a `- **Grid**:` line."""
        self.campaign()
        census = checker.sweep_census()
        self.assertEqual(census["records"], 0)
        self.assertEqual(census["covered"], 0)

    def test_the_points_are_read_from_the_total_not_from_the_factors(self):
        """A total and its factors that disagree are graded on the total."""
        self.campaign()
        self.tree.add_sim_record(checker.ARM_CAMPAIGN, "20260926-101010-abcdef0", sweep_points=4)
        self.assertEqual(checker.sweep_census()["covered"], 4)

    def test_an_absent_census_is_itself_a_finding(self):
        """Deleting the sentence must not widen what the citation may claim."""
        self.campaign()
        misses = self.check(self.body(None))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("states no sweep census", misses[0])
        self.assertIn("the box is unrun", misses[0])

    def test_a_document_that_does_not_cite_the_campaign_is_not_graded(self):
        self.campaign()
        self.assertEqual(self.check(self.body(None, anchor=False)), [])

    def test_a_runner_whose_box_is_computed_grades_nothing(self):
        """No tree-side number to compare against is a silence, not a zero."""
        self.tree.add_sweep_axes(axes="SWEEP_L_MULTIPLIERS = build_ladder()\n")
        self.tree.add_sim_record(
            checker.ARM_CAMPAIGN, "20260925-073912-0e385e5", latest=True, arms=("ideal",)
        )
        self.assertIsNone(checker.sweep_census())
        self.assertEqual(self.check(self.body(None)), [])

    def test_a_runner_with_only_one_of_the_two_axes_grades_nothing(self):
        """Half a box is not a box: both axes must parse or neither counts."""
        self.tree.add_sweep_axes(
            axes="SWEEP_L_MULTIPLIERS: tuple[float, ...] = (0, 1, 10)\n"
        )
        self.assertIsNone(checker.sweep_census())
        self.assertEqual(self.check(self.body(None)), [])

    def test_check_is_inert_without_the_runner_at_all(self):
        self.assertIsNone(checker.sweep_census())
        self.assertEqual(self.check(self.body(None)), [])

    def test_the_stats_sentence_is_what_the_check_matches(self):
        """A --stats paste must pass, which is how every readout check is fixed."""
        self.campaign()
        self.assertEqual(
            self.check(self.body(checker.sweep_sentence(checker.sweep_census()))), []
        )

    def test_the_stats_sentence_singularises_one_record(self):
        """`1 sweep records` would be the paste a reader has to hand-fix."""
        self.campaign()
        self.tree.add_sim_record(checker.ARM_CAMPAIGN, "20260926-101010-abcdef0", sweep_points=9)
        sentence = checker.sweep_sentence(checker.sweep_census())
        self.assertIn("in **1** sweep record:", sentence)
        self.assertEqual(self.check(self.body(sentence)), [])

    def test_the_real_tree_and_the_real_document_agree(self):
        """The live pair, not a fixture: this is what CI actually grades."""
        fixture_root = checker.REPO_ROOT
        checker.REPO_ROOT = REPO_ROOT
        self.addCleanup(lambda: setattr(checker, "REPO_ROOT", fixture_root))
        doc = REPO_ROOT / "docs" / "chipalooza" / "challenge-4-proposal.md"
        self.assertEqual(checker.check_sweep_census(doc, doc.read_text()), [])

    def test_the_real_census_parses_the_real_runner(self):
        """Not vacuous: the box must resolve against the live runner.

        A parse that silently resolved nothing would make the check pass by
        censusing an empty box -- the vacuity trap checks 4, 6, 30 and 31 each
        needed a guard for. The live record tree is asserted too: its arm
        record must NOT be counted as a sweep record, which is the half of
        this parse a record-less tree could not exercise.
        """
        fixture_root = checker.REPO_ROOT
        checker.REPO_ROOT = REPO_ROOT
        self.addCleanup(lambda: setattr(checker, "REPO_ROOT", fixture_root))
        census = checker.sweep_census()
        self.assertIsNotNone(census)
        self.assertGreaterEqual(census["l_mults"], 2)
        self.assertGreaterEqual(census["rsubx"], 2)
        self.assertEqual(census["points"], census["l_mults"] * census["rsubx"])
        self.assertTrue((REPO_ROOT / checker.SWEEP_RECORDS).is_dir())
        self.assertTrue(list((REPO_ROOT / checker.SWEEP_RECORDS).glob("*.md")))
        self.assertEqual(census["records"], len(census["record_ids"]))


class TestNullSweepCensus(unittest.TestCase):
    """Check 34: the stated `--null-sweep` ladder census is this tree's own.

    The THIRD axis of one campaign. Check 31 grades which arms a record ran,
    check 32 how much of the bounded 2-D box any record walked; this grades a
    ladder that moves the same lumped substrate constant over the same decade
    on a DIFFERENT topology -- DR-012's rejected `no-gnd-pad` arm, where that
    resistor carries the whole analog-ground return instead of shunting a
    bond. A ladder record is the union of the other two checks' blind spots:
    it never becomes `records/LATEST` (checks 3/4/6/23), runs at one corner
    (check 28), carries no `- **Arms**:` line (check 31) and no `- **Grid**:`
    line (check 32).
    """

    def setUp(self):
        self.tree = FixtureTree(self)

    def check(self, body: str) -> list[str]:
        return checker.check_null_sweep_census(self.tree.document(body), body)

    def body(self, sentence: str | None, *, anchor: bool = True) -> str:
        text = "## 7. Open items\n\n"
        if anchor:
            text += f"See [the campaign](../../{checker.NULL_SWEEP_RECORDS}/LATEST).\n"
        if sentence is not None:
            text += f"\n> {sentence}\n"
        return text

    def sentence(self, rungs, covered, records, record_ids=()) -> str:
        return checker.null_sweep_sentence(
            {
                "rungs": rungs,
                "covered": covered,
                "records": records,
                "record_ids": list(record_ids),
            }
        )

    def campaign(self, **kwargs):
        """Today's real shape: a 3-rung ladder defined, an arm record, no ladder."""
        self.tree.add_null_sweep_axis(**kwargs)
        self.tree.add_sim_record(
            checker.ARM_CAMPAIGN,
            "20260925-073912-0e385e5",
            latest=True,
            arms=("ideal", "package-r-only", "package", "substrate"),
        )

    def test_a_truthful_unwalked_census_passes(self):
        self.campaign()
        self.assertEqual(self.check(self.body(self.sentence(3, 0, 0))), [])

    def test_a_ladder_record_falsifies_the_unwalked_census(self):
        """The drift this check exists for, stated as the failure it must be."""
        self.campaign()
        self.tree.add_sim_record(checker.ARM_CAMPAIGN, "20260926-101010-abcdef0", ladder_rungs=3)
        misses = self.check(self.body(self.sentence(3, 0, 0)))
        self.assertTrue(misses)
        self.assertTrue(any("covered=0" in miss and "covered=3" in miss for miss in misses))
        self.assertTrue(any("records=0" in miss and "records=1" in miss for miss in misses))
        self.assertTrue(any("20260926-101010-abcdef0" in miss for miss in misses))

    def test_a_truthful_walked_census_passes(self):
        """The case PR #445 creates: the ladder finally walked."""
        self.campaign()
        self.tree.add_sim_record(checker.ARM_CAMPAIGN, "20260926-101010-abcdef0", ladder_rungs=3)
        self.assertEqual(
            self.check(self.body(self.sentence(3, 3, 1, ("20260926-101010-abcdef0",)))),
            [],
        )

    def test_a_longer_ladder_in_the_runner_widens_the_census(self):
        """The other direction: a rung added to the runner and nothing re-run."""
        self.campaign(rsubx=(1.0, 3.0, 30.0, 300.0))
        misses = self.check(self.body(self.sentence(3, 0, 0)))
        self.assertTrue(misses)
        self.assertTrue(any("rungs=3" in miss and "rungs=4" in miss for miss in misses))

    def test_a_drifted_record_list_is_reported_even_when_the_counts_agree(self):
        """Right totals, wrong record -- what a count-only census absorbs."""
        self.campaign()
        self.tree.add_sim_record(checker.ARM_CAMPAIGN, "20260926-101010-abcdef0", ladder_rungs=3)
        misses = self.check(self.body(self.sentence(3, 3, 1, ("20260101-000000-0000000",))))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("20260101-000000-0000000", misses[0])
        self.assertIn("20260926-101010-abcdef0", misses[0])

    def test_covered_is_the_longest_ladder_not_the_sum(self):
        """Two records of the same ladder are two runs of one experiment."""
        self.campaign()
        self.tree.add_sim_record(checker.ARM_CAMPAIGN, "20260926-101010-abcdef0", ladder_rungs=3)
        self.tree.add_sim_record(checker.ARM_CAMPAIGN, "20260927-101010-abcdef1", ladder_rungs=2)
        census = checker.null_sweep_census()
        self.assertEqual(census["covered"], 3)
        self.assertEqual(census["records"], 2)
        self.assertEqual(
            census["record_ids"], ["20260926-101010-abcdef0", "20260927-101010-abcdef1"]
        )

    def test_neither_of_the_other_two_record_shapes_is_a_ladder_record(self):
        """Three writers share one `records/` tree; each emits its own header."""
        self.campaign()
        self.tree.add_sim_record(checker.ARM_CAMPAIGN, "20260926-101010-abcdef0", sweep_points=9)
        census = checker.null_sweep_census()
        self.assertEqual(census["records"], 0)
        self.assertEqual(census["covered"], 0)

    def test_the_rungs_are_read_from_the_leading_count_not_the_transient_total(self):
        """The `=` total counts the `ideal` control, which is not a magnitude."""
        self.campaign()
        self.tree.add_sim_record(checker.ARM_CAMPAIGN, "20260926-101010-abcdef0", ladder_rungs=2)
        self.assertEqual(checker.null_sweep_census()["covered"], 2)

    def test_an_absent_census_is_itself_a_finding(self):
        """Deleting the sentence must not widen what the citation may claim."""
        self.campaign()
        misses = self.check(self.body(None))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("states no ladder census", misses[0])
        self.assertIn("the ladder is unwalked", misses[0])

    def test_a_document_that_does_not_cite_the_campaign_is_not_graded(self):
        self.campaign()
        self.assertEqual(self.check(self.body(None, anchor=False)), [])

    def test_a_runner_whose_ladder_is_computed_grades_nothing(self):
        """No tree-side number to compare against is a silence, not a zero."""
        self.tree.add_null_sweep_axis(axis="NULL_SWEEP_RSUBX_OHM = decade_around(30)\n")
        self.tree.add_sim_record(
            checker.ARM_CAMPAIGN, "20260925-073912-0e385e5", latest=True, arms=("ideal",)
        )
        self.assertIsNone(checker.null_sweep_census())
        self.assertEqual(self.check(self.body(None)), [])

    def test_check_is_inert_without_the_runner_at_all(self):
        self.assertIsNone(checker.null_sweep_census())
        self.assertEqual(self.check(self.body(None)), [])

    def test_the_two_rsubx_constants_do_not_capture_each_other(self):
        """`SWEEP_RSUBX_OHM` and `NULL_SWEEP_RSUBX_OHM` share a suffix.

        Only a fixture carrying BOTH can show that neither source-text parse
        reads the other's tuple -- and it is the exact confusion that would
        make checks 32 and 34 silently census one axis twice.
        """
        self.tree.add_sweep_axes(l_mults=(0.0, 1.0, 10.0), rsubx=(3.0, 30.0, 300.0))
        self.tree.add_null_sweep_axis(rsubx=(1.0, 3.0, 30.0, 300.0, 3000.0))
        self.assertEqual(checker.null_sweep_ladder(), 5)
        box = checker.sweep_box()
        self.assertEqual(box, (3, 3))

    def test_the_stats_sentence_is_what_the_check_matches(self):
        """A --stats paste must pass, which is how every readout check is fixed."""
        self.campaign()
        self.assertEqual(
            self.check(self.body(checker.null_sweep_sentence(checker.null_sweep_census()))), []
        )

    def test_the_stats_sentence_singularises_one_record(self):
        """`1 ladder records` would be the paste a reader has to hand-fix."""
        self.campaign()
        self.tree.add_sim_record(checker.ARM_CAMPAIGN, "20260926-101010-abcdef0", ladder_rungs=3)
        sentence = checker.null_sweep_sentence(checker.null_sweep_census())
        self.assertIn("in **1** ladder record:", sentence)
        self.assertEqual(self.check(self.body(sentence)), [])

    def test_the_real_tree_and_the_real_document_agree(self):
        """The live pair, not a fixture: this is what CI actually grades."""
        fixture_root = checker.REPO_ROOT
        checker.REPO_ROOT = REPO_ROOT
        self.addCleanup(lambda: setattr(checker, "REPO_ROOT", fixture_root))
        doc = REPO_ROOT / "docs" / "chipalooza" / "challenge-4-proposal.md"
        self.assertEqual(checker.check_null_sweep_census(doc, doc.read_text()), [])

    def test_the_real_census_parses_the_real_runner_and_record(self):
        """Not vacuous: both halves must resolve against the live tree.

        A parse that silently resolved nothing would make the check pass by
        censusing an empty ladder -- the vacuity trap checks 4, 6 and 30--32
        each needed a guard for. The live record tree is asserted too: the
        campaign's arm and sweep records must NOT be counted as ladder
        records, which is the half a record-less tree could not exercise.
        """
        fixture_root = checker.REPO_ROOT
        checker.REPO_ROOT = REPO_ROOT
        self.addCleanup(lambda: setattr(checker, "REPO_ROOT", fixture_root))
        census = checker.null_sweep_census()
        self.assertIsNotNone(census)
        self.assertGreaterEqual(census["rungs"], 2)
        self.assertEqual(census["records"], len(census["record_ids"]))
        records = REPO_ROOT / checker.NULL_SWEEP_RECORDS
        self.assertTrue(records.is_dir())
        # More `.md` records exist in that tree than are ladder records: the
        # three shapes share it, and counting them all would be the vacuity.
        self.assertLess(census["records"], len(list(records.glob("*.md"))))


class TestDecouplingCensus(unittest.TestCase):
    """Check 33: the stated on-die-decoupling ownership census is this tree's own.

    Three decision records carry the same open item -- on-die decoupling is
    not designed, budgeted, or measured -- and DR-012 makes every excursion
    figure it states an *undecoupled* upper bound by deferring to it. Section
    7's rule is that an open item points at the issue that tracks it, and no
    other check here can see that pointer move: check 15 reads a Status line
    and nothing else, checks 3/4/22/23 grade evidence citations, checks 31/32
    grade one campaign's axes.
    """

    CARRIER = "**On-die decoupling** for either domain is not designed."
    OTHER = "**The pad's position is provisional.** No pad ring exists yet."

    def setUp(self):
        self.tree = FixtureTree(self)

    def check(self, body: str) -> list[str]:
        return checker.check_decoupling_census(self.tree.document(body), body)

    def body(self, sentence: str | None, *, anchor: str | None = None) -> str:
        text = "## 7. Open items\n\n"
        if anchor is not None:
            text += f"See `spec/decision-records/{anchor}`.\n"
        if sentence is not None:
            text += f"\n> {sentence}\n"
        return text

    def sentence(self, carrying, tracked, untracked=()) -> str:
        return checker.decoupling_sentence(
            {
                "carrying": carrying,
                "tracked": tracked,
                "untracked": [
                    f"spec/decision-records/{name}" for name in untracked
                ],
            }
        )

    def tree_with(self, *records):
        """`records` as (filename, open-item bullets) pairs."""
        for name, items in records:
            self.tree.add_decision_record(name, open_items=list(items))

    def test_a_truthful_untracked_census_passes(self):
        self.tree_with(
            ("DR-010-a.md", [self.CARRIER]),
            ("DR-012-b.md", [self.OTHER, self.CARRIER]),
        )
        body = self.body(
            self.sentence(2, 0, ("DR-010-a.md", "DR-012-b.md")),
            anchor="DR-010-a.md",
        )
        self.assertEqual(self.check(body), [])

    def test_a_record_that_names_its_tracker_falsifies_the_census(self):
        """The drift this check exists for, stated as the failure it must be."""
        self.tree_with(
            ("DR-010-a.md", [self.CARRIER + " Tracked as #431."]),
            ("DR-012-b.md", [self.CARRIER]),
        )
        body = self.body(
            self.sentence(2, 0, ("DR-010-a.md", "DR-012-b.md")),
            anchor="DR-012-b.md",
        )
        misses = self.check(body)
        self.assertTrue(misses)
        self.assertTrue(any("tracked=0" in miss for miss in misses), misses)

    def test_a_struck_item_no_longer_carries_the_gap(self):
        self.tree_with(
            ("DR-010-a.md", ["~~" + self.CARRIER + "~~ **CLOSED** by DR-016."]),
            ("DR-012-b.md", [self.CARRIER]),
        )
        body = self.body(self.sentence(1, 0, ("DR-012-b.md",)), anchor="DR-012-b.md")
        self.assertEqual(self.check(body), [])

    def test_the_word_alone_inside_a_bullet_is_not_a_carrier(self):
        """`ARM_RECORD_RE`'s discipline: the lead names it, or it does not count.

        DR-012's real rejected-null-option item quotes "undecoupled upper
        bounds" while being about the `no-gnd-pad` arm. An unanchored search
        for the word would report it as a carrier.
        """
        self.tree_with(
            (
                "DR-012-b.md",
                [
                    "**The rejected null option now has a price.** The "
                    "excursion figures are undecoupled upper bounds.",
                    self.CARRIER,
                ],
            ),
        )
        body = self.body(self.sentence(1, 0, ("DR-012-b.md",)), anchor="DR-012-b.md")
        self.assertEqual(self.check(body), [])

    def test_an_upstream_reference_is_not_a_tracker(self):
        """`klayout-tools#2400` names somebody else's tracker, not this gap's."""
        self.tree_with(
            ("DR-010-a.md", [self.CARRIER + " See klayout-tools#2400."]),
        )
        body = self.body(self.sentence(1, 0, ("DR-010-a.md",)), anchor="DR-010-a.md")
        self.assertEqual(self.check(body), [])

    def test_a_drifted_record_list_is_reported_even_when_the_counts_agree(self):
        self.tree_with(
            ("DR-010-a.md", [self.CARRIER]),
            ("DR-015-c.md", [self.CARRIER]),
        )
        body = self.body(
            self.sentence(2, 0, ("DR-010-a.md", "DR-012-b.md")),
            anchor="DR-010-a.md",
        )
        misses = self.check(body)
        self.assertTrue(any("sends a reader to the wrong file" in m for m in misses), misses)

    def test_a_fully_tracked_census_passes_and_states_itself(self):
        self.tree_with(("DR-010-a.md", [self.CARRIER + " Tracked as #431."]))
        sentence = checker.decoupling_sentence(checker.decoupling_census())
        self.assertIn(checker.DECOUPLING_CENSUS_NONE, sentence)
        self.assertEqual(self.check(self.body(sentence, anchor="DR-010-a.md")), [])

    def test_an_absent_census_is_itself_a_finding(self):
        self.tree_with(("DR-010-a.md", [self.CARRIER]))
        misses = self.check(self.body(None, anchor="DR-010-a.md"))
        self.assertTrue(misses)
        self.assertIn("states no ownership census", misses[0])

    def test_a_document_that_cites_no_carrier_is_not_graded(self):
        self.tree_with(("DR-010-a.md", [self.CARRIER]))
        self.assertEqual(self.check(self.body(None)), [])

    def test_a_record_with_no_open_items_section_carries_nothing(self):
        self.tree.add_decision_record("DR-010-a.md")
        self.assertEqual(checker.decoupling_census()["carrying"], 0)

    def test_the_stats_sentence_is_what_the_check_matches(self):
        """A `--stats` paste must pass, or the fix is a hand transcription."""
        self.tree_with(
            ("DR-010-a.md", [self.CARRIER]),
            ("DR-012-b.md", [self.CARRIER]),
        )
        sentence = checker.decoupling_sentence(checker.decoupling_census())
        self.assertEqual(self.check(self.body(sentence, anchor="DR-010-a.md")), [])

    def test_the_real_tree_and_the_real_document_agree(self):
        """The live pair, not a fixture: this is what CI actually grades."""
        fixture_root = checker.REPO_ROOT
        checker.REPO_ROOT = REPO_ROOT
        self.addCleanup(lambda: setattr(checker, "REPO_ROOT", fixture_root))
        doc = REPO_ROOT / "docs" / "chipalooza" / "challenge-4-proposal.md"
        self.assertEqual(checker.check_decoupling_census(doc, doc.read_text()), [])

    def test_the_real_census_finds_the_real_carriers(self):
        """Not vacuous: the census must resolve against the live records.

        A parse that silently found nothing would make the check pass by
        censusing an empty set -- the vacuity trap checks 4, 6, 30, 31 and 32
        each needed a guard for.
        """
        fixture_root = checker.REPO_ROOT
        checker.REPO_ROOT = REPO_ROOT
        self.addCleanup(lambda: setattr(checker, "REPO_ROOT", fixture_root))
        census = checker.decoupling_census()
        self.assertGreaterEqual(census["carrying"], 1)
        self.assertEqual(
            census["carrying"], census["tracked"] + len(census["untracked"])
        )
        for record in census["untracked"]:
            self.assertTrue((REPO_ROOT / record).is_file(), record)


class TestExcursionEnumeration(unittest.TestCase):
    """Check 35: the *undecoupled* enumeration names every figure it must.

    Check 33 grades who OWNS the on-die-decoupling gap; this grades the one
    sentence that applies that gap's qualifier to a hand-written list of
    die-side ground-excursion figures. That list went stale twice in one day
    (PR #446 wrote eight figures four minutes before PR #445 merged with three
    more in it; PR #447 then narrated all three in the same item and left the
    list alone), and no check read it -- check 34 grades the ladder AXIS that
    stales it, never the list.

    Two parse hazards were measured against the live document before this
    check was written, and both are regression-tested here:

      - **unit-eliding chains**: the document writes `` `72.130` ->
        `67.307` -> `137.093 mV` ``, so a three-decimal-plus-`mV` scan finds
        one of three figures and misses exactly the ones that went stale;
      - **unrelated `mV` figures at the same precision**: the same section
        states `0.001`, `0.380` and `67.190 mV`, none of which is a
        supply-return excursion, so a scan that required them would fail on
        correct prose -- worse than the hand-maintained note, because it
        teaches the next pass to reword around the gate.
    """

    def setUp(self):
        self.tree = FixtureTree(self)

    def check(self, body: str) -> list[str]:
        return checker.check_excursion_enumeration(self.tree.document(body), body)

    def enumeration(self, *figures: str) -> str:
        """The list as the document writes it: only the LAST figure carries `mV`.

        Hazard 1 in the enumeration's own voice -- the sentence under test is
        itself a unit-eliding chain, which is why the check parses both sides
        of the comparison with the same chain reader.
        """
        quoted = [f"`{figure}`" for figure in figures[:-1]]
        tail = f"`{figures[-1]} mV`"
        joined = ", ".join(quoted)
        return f"{joined} and {tail}" if quoted else tail

    def body(
        self,
        narrative: str = "",
        enumeration: str | None = None,
        *,
        item: bool = True,
        other_item: str = "",
        anchor: bool = True,
    ) -> str:
        """A Section 7 shaped document: one numbered item, then the sentence.

        `other_item` is a SECOND numbered item placed above the first, which is
        how the region bound is exercised: a figure stated there is outside the
        narrative the enumeration says "above" of, and must not be required.
        """
        text = "## 7. Open items before sign-off\n\n"
        if anchor:
            text += f"See [the campaign](../../{checker.EXCURSION_RECORDS}/LATEST).\n\n"
        if other_item:
            text += f"8. **Some other gap.** {other_item}\n\n"
        if item:
            text += "9. **Power delivery is structurally graded.**\n"
        if narrative:
            text += f"   {narrative}\n"
        if enumeration is not None:
            text += (
                f"\n   {enumeration} are each an **undecoupled** upper bound, and\n"
                "   that is not this document's gloss on them.\n"
            )
        return text

    def campaign(self, *excursions: str, **kwargs):
        """One arm-comparison record carrying `excursions` plus the control."""
        rows = tuple(
            (f"arm-{index}", figure) for index, figure in enumerate(excursions)
        )
        self.tree.add_sim_record(
            checker.ARM_CAMPAIGN,
            "20260925-073912-0e385e5",
            latest=True,
            arms=("ideal", "package"),
            excursions=(("ideal", "0.000"),) + rows,
            **kwargs,
        )

    # -- The claim itself, in both directions of the one it makes.

    def test_a_complete_enumeration_passes(self):
        self.campaign("37.333", "10.779")
        body = self.body(
            "the excursion is **37.333 mV**, of which **10.779 mV** is substrate.",
            self.enumeration("10.779", "37.333"),
        )
        self.assertEqual(self.check(body), [])

    def test_a_dropped_figure_is_reported(self):
        """The mutation the acceptance criteria name: one figure removed."""
        self.campaign("37.333", "10.779")
        body = self.body(
            "the excursion is **37.333 mV**, of which **10.779 mV** is substrate.",
            self.enumeration("37.333"),
        )
        misses = self.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("10.779", misses[0])

    # -- Hazard 1: a chain in which only the last figure carries its unit.

    def test_a_unit_eliding_chain_is_followed(self):
        """The exact shape PR #445's ladder is narrated in.

        A `\\d+\\.\\d{3}\\s*mV` scan sees only `137.093` here, so the two
        figures that actually went stale would be invisible to it.
        """
        self.campaign("72.130", "67.307", "137.093")
        body = self.body(
            "the excursion goes `72.130` -> `67.307` -> `137.093 mV` peak-to-peak.",
            self.enumeration("137.093"),
        )
        misses = self.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("67.307", misses[0])
        self.assertIn("72.130", misses[0])

    def test_the_chain_reader_follows_every_separator_the_document_uses(self):
        """Arrow, slash, comma and "and" -- all four are live in the document."""
        for span in (
            "`1.111` -> `2.222` -> `3.333 mV`",
            "`1.111`/`2.222`/`3.333 mV`",
            "`1.111`, `2.222`, `3.333 mV`",
            "`1.111`, `2.222` and `3.333 mV`",
            "**1.111**, **2.222** and **3.333 mV**",
        ):
            with self.subTest(span=span):
                self.assertEqual(
                    checker.excursion_chain_figures(span),
                    ["1.111", "2.222", "3.333"],
                )

    def test_a_figure_in_no_unit_bearing_chain_is_not_read_as_mv(self):
        """Prose separates these two, so the unitless one states no excursion.

        The live shape this is taken from: `**37.274 mV** of it to the bond
        inductance alone (`0.059 mV` remains with `L = 0`)` -- the words between
        the two figures are what must end the chain, so a figure that carries no
        unit of its own and is not chained to one states no mV value at all.
        """
        self.assertEqual(
            checker.excursion_chain_figures(
                "`1.111 mV` remains with `L = 0`, and the ratio was `2.222` there."
            ),
            ["1.111"],
        )

    def test_a_figure_at_another_precision_is_not_a_row_value(self):
        """`+27.6 mV` is a difference the renderer never prints as a row."""
        self.assertEqual(checker.excursion_chain_figures("**+27.6 mV** of excursion"), [])

    # -- Hazard 2: same-precision `mV` figures that are NOT excursions.

    def test_an_unrelated_mv_figure_at_the_same_precision_is_not_required(self):
        """The `0.001`/`0.380`/`67.190 mV` class, measured in the live document."""
        self.campaign("37.333")
        body = self.body(
            "the excursion is **37.333 mV**, and the reference settles to "
            "`0.380 mV` of ripple with `67.190 mV` of headroom.",
            self.enumeration("37.333"),
        )
        self.assertEqual(self.check(body), [])

    def test_a_derived_difference_is_not_required(self):
        """The live `2.070 mV` case: a subtraction no record row carries.

        The document states it precisely to say it is NOT a measurement, so a
        gate that demanded it be qualified as an excursion upper bound would
        be requiring the document to contradict itself.
        """
        self.campaign("67.307", "65.237")
        body = self.body(
            "the ladder's `67.307 mV` rung against the arm's `65.237 mV` -- "
            "do not read that `2.070 mV` as a measurement.",
            self.enumeration("65.237", "67.307"),
        )
        self.assertEqual(self.check(body), [])

    def test_the_ideal_controls_zero_is_not_required(self):
        """`0.000` is mechanical: an ideal source holds the die node at 0 V."""
        self.campaign("37.333")
        body = self.body(
            "the `ideal` control reads `0.000 mV` and the arm **37.333 mV**.",
            self.enumeration("37.333"),
        )
        self.assertEqual(self.check(body), [])

    # -- The region bound, and its vacuity trap.

    def test_a_figure_in_another_numbered_item_is_not_required(self):
        """"Above" means this item's own narrative, not the whole section."""
        self.campaign("37.333", "10.779")
        body = self.body(
            "the excursion is **37.333 mV**.",
            self.enumeration("37.333"),
            other_item="An unrelated `10.779 mV` figure lives here.",
        )
        self.assertEqual(self.check(body), [])

    def test_an_enumeration_with_no_narrative_figures_above_it_is_a_finding(self):
        """The vacuity trap, made loud instead of silent.

        If the region anchor ever drifts -- the item renumbered away, the
        narrative moved out from under the sentence -- the derived set goes
        empty and a superset check would pass by grading nothing. That must be
        the one case it reports instead.
        """
        self.campaign("37.333")
        misses = self.check(self.body("", self.enumeration("37.333")))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("grades nothing", misses[0])

    def test_an_absent_enumeration_is_itself_a_finding(self):
        """Deleting the sentence must not unqualify the figures above it."""
        self.campaign("37.333", "10.779")
        misses = self.check(
            self.body("the excursion is **37.333 mV**, of which **10.779 mV** is substrate.")
        )
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("qualifies none of them", misses[0])
        self.assertIn("10.779", misses[0])
        self.assertIn("37.333", misses[0])

    def test_a_document_with_no_supply_return_narrative_is_not_graded(self):
        """The vacuity-trap guard's other side: silence on an unrelated doc."""
        self.campaign("37.333")
        self.assertEqual(self.check(self.body("Nothing about supply returns here.")), [])
        self.assertEqual(self.check("# A document with no Section 7 at all\n"), [])

    def test_a_document_that_does_not_cite_the_campaign_is_not_graded(self):
        """Checks 31, 32 and 34's anchor, for their reason."""
        self.campaign("37.333", "10.779")
        body = self.body(
            "the excursion is **37.333 mV**, of which **10.779 mV** is substrate.",
            anchor=False,
        )
        self.assertEqual(self.check(body), [])

    def test_a_single_quoted_figure_does_not_demand_the_qualifier(self):
        """One figure in passing is a citation, not a narrative.

        Measured against the live tree before this bound was added: the gate's
        own rationale document quotes `65.237 mV` once, and a check that
        demanded the whole qualifier sentence of it would be firing on correct
        prose -- the failure mode this issue was filed rather than rushed to
        avoid.
        """
        self.campaign("65.237")
        self.assertEqual(
            self.check(self.body("DR-012 attaches the word to its `65.237 mV` figure.")),
            [],
        )

    # -- One-directional by design.

    def test_an_interior_sweep_point_the_document_never_quotes_is_not_required(self):
        """The committed set is larger than the document legitimately quotes."""
        self.campaign("37.590", "22.556", "40.688")
        body = self.body(
            "the worst column point is **37.590 mV**.", self.enumeration("37.590")
        )
        self.assertEqual(self.check(body), [])

    def test_an_enumerated_figure_no_record_carries_is_not_a_finding(self):
        """`37.274` is a one-element ablation, not a row -- and legitimate."""
        self.campaign("37.333")
        body = self.body(
            "the excursion is **37.333 mV**, of which **37.274 mV** is inductance.",
            self.enumeration("37.274", "37.333"),
        )
        self.assertEqual(self.check(body), [])

    # -- The third narrowing: only an UNDECOUPLED netlist's figures are owed.

    def test_a_decoupled_netlists_figures_are_not_required(self):
        """The live shape PR #457 created, caught by this check on the day it landed.

        DR-017 landed on-die decoupling, and this campaign's newest record runs
        the decoupled netlist -- a different DUT sha256 -- at nine corners across
        five arms. Its excursion figures are real and are stated in the same §7
        item, and they are NOT undecoupled upper bounds. Requiring them would
        make the gate demand the document assert something false.
        """
        self.campaign("37.333")
        self.tree.add_sim_record(
            checker.ARM_CAMPAIGN,
            "20260926-050045-8e62675",
            arms=("ideal", "package"),
            excursions=(("ideal", "0.000"), ("package", "13.964")),
            excursion_dut="b" * 64,
            excursion_undecoupled=False,
        )
        self.assertEqual(checker.excursion_row_figures(), {"37.333"})
        body = self.body(
            "the undecoupled excursion is **37.333 mV**; with DR-017's "
            "decoupling in the netlist it is **13.964 mV** at the worst corner.",
            self.enumeration("37.333"),
        )
        self.assertEqual(self.check(body), [])

    def test_a_record_that_does_not_repeat_the_declaration_inherits_it_by_dut_sha(self):
        """Three of the five live undecoupled records never state it themselves."""
        self.campaign("37.333")
        self.tree.add_sim_record(
            checker.ARM_CAMPAIGN,
            "20260925-204633-7339971",
            arms=("ideal", "no-gnd-pad"),
            excursions=(("ideal", "0.000"), ("no-gnd-pad", "65.237")),
            excursion_undecoupled=False,
        )
        self.assertEqual(checker.excursion_row_figures(), {"37.333", "65.237"})

    def test_the_word_undecoupled_in_prose_is_not_a_declaration(self):
        """Every record narrates "an undecoupled series inductance", decoupled or not.

        Check 33's `DECOUPLING_LEAD_RE` made the same distinction for the same
        reason: a word search over the record body would put the decoupled DUT
        in the undecoupled set and silently re-admit its figures.
        """
        self.tree.add_sim_record(
            checker.ARM_CAMPAIGN,
            "20260926-050045-8e62675",
            latest=True,
            arms=("ideal", "package"),
            excursions=(("ideal", "0.000"), ("package", "13.964")),
            excursion_dut="b" * 64,
            excursion_undecoupled=False,
            excursion_prose=(
                "Reported because an undecoupled series inductance against the "
                "die's own capacitance rings above the clock rate, so a bonded "
                "arm costs more than the ideal one. No decoupling is cheap."
            ),
        )
        self.assertEqual(checker.excursion_undecoupled_duts(), set())
        self.assertIsNone(checker.excursion_row_figures())

    def test_a_tree_with_no_undecoupled_declaration_grades_nothing(self):
        self.campaign("37.333", excursion_undecoupled=False)
        self.assertIsNone(checker.excursion_row_figures())
        self.assertEqual(self.check(self.body("the excursion is **37.333 mV**.")), [])

    # -- Both record layouts, and the silences.

    def test_both_record_layouts_are_read_by_column_name(self):
        """Two writers, two table shapes, one column header."""
        self.tree.add_sim_record(
            checker.ARM_CAMPAIGN,
            "20260925-073912-0e385e5",
            latest=True,
            arms=("ideal", "package"),
            excursions=(("ideal", "0.000"), ("package", "37.333")),
        )
        self.tree.add_sim_record(
            checker.ARM_CAMPAIGN,
            "20260925-164447-722fcb0",
            sweep_points=9,
            excursions=(("ideal", "0.000"), ("sweep-l10x-rsubx300", "111.622")),
            excursion_layout="point",
        )
        self.assertEqual(checker.excursion_row_figures(), {"37.333", "111.622"})

    def test_check_is_inert_without_the_campaign_records(self):
        self.assertIsNone(checker.excursion_row_figures())
        self.assertEqual(
            self.check(self.body("the excursion is **37.333 mV**.")), []
        )

    def test_a_records_tree_with_no_excursion_column_grades_nothing(self):
        """No tree-side figures to compare against is a silence, not a zero."""
        self.campaign("37.333", excursion_column="gnd_die swing (mV)")
        self.assertIsNone(checker.excursion_row_figures())
        self.assertEqual(self.check(self.body("the excursion is **37.333 mV**.")), [])

    # -- The live pair.

    def test_the_real_tree_and_the_real_document_agree(self):
        """The live pair, not a fixture: this is what CI actually grades."""
        fixture_root = checker.REPO_ROOT
        checker.REPO_ROOT = REPO_ROOT
        self.addCleanup(lambda: setattr(checker, "REPO_ROOT", fixture_root))
        doc = REPO_ROOT / "docs" / "chipalooza" / "challenge-4-proposal.md"
        self.assertEqual(checker.check_excursion_enumeration(doc, doc.read_text()), [])

    def test_the_real_check_is_not_vacuous(self):
        """The mutation test, automated: drop one figure and the live doc fails.

        This is what keeps the check from passing by deriving an empty set
        against the real tree -- the vacuity trap checks 4, 6 and 30--34 each
        needed a guard for, and the one an "enumeration is a superset" claim
        is most exposed to.
        """
        fixture_root = checker.REPO_ROOT
        checker.REPO_ROOT = REPO_ROOT
        self.addCleanup(lambda: setattr(checker, "REPO_ROOT", fixture_root))
        doc = REPO_ROOT / "docs" / "chipalooza" / "challenge-4-proposal.md"
        text = doc.read_text()
        required = checker.excursion_enumeration_figures(text)
        self.assertIsNotNone(required)
        self.assertGreaterEqual(
            len(required),
            8,
            "the live document's supply-return narrative states almost no "
            "record excursion figure -- the region anchor has drifted and the "
            "check is grading nothing",
        )
        # The enumeration's own figure list, located the way the check locates
        # it, so the mutation lands in the LIST and not on some earlier
        # occurrence of the same figure elsewhere in the document -- most of
        # these figures are stated several times over.
        collapsed, offsets = checker._collapse_quoted_prose(text)
        match = checker.EXCURSION_ENUM_RE.search(collapsed)
        self.assertIsNotNone(match, "the live enumeration sentence no longer parses")
        window = offsets[match.start("figures")]
        anchor = offsets[match.end("figures") - 1] + 1
        for figure in sorted(required):
            with self.subTest(dropped=figure):
                span = text[window:anchor]
                dropped = re.sub(
                    r"`" + re.escape(figure) + r"(?: mV)?`(?:,?\s+and)?[,\s]*",
                    "",
                    span,
                    count=1,
                )
                self.assertNotEqual(
                    dropped, span, f"{figure} is not in the enumeration sentence"
                )
                mutated = text[:window] + dropped + text[anchor:]
                misses = checker.check_excursion_enumeration(doc, mutated)
                self.assertTrue(misses, f"dropping {figure} was not reported")
                self.assertTrue(
                    any(figure in miss for miss in misses),
                    f"dropping {figure} was reported without naming it: {misses}",
                )

    def test_the_real_documents_unrelated_mv_figures_are_not_required(self):
        """Hazard 2 against the live document, not only against a fixture."""
        fixture_root = checker.REPO_ROOT
        checker.REPO_ROOT = REPO_ROOT
        self.addCleanup(lambda: setattr(checker, "REPO_ROOT", fixture_root))
        doc = REPO_ROOT / "docs" / "chipalooza" / "challenge-4-proposal.md"
        required = checker.excursion_enumeration_figures(doc.read_text())
        self.assertIsNotNone(required)
        for figure in ("0.001", "0.380", "67.190", "2.070", "0.000"):
            self.assertNotIn(figure, required)

    def test_the_real_tree_carries_two_dut_generations_and_only_one_is_owed(self):
        """The undecoupled narrowing, non-vacuous against the live tree.

        If this assertion ever fails because the tree holds ONE DUT generation
        again, the narrowing is untested by the live half and only the fixtures
        above hold it -- which is worth knowing, because it is the half that
        keeps the gate from demanding the document call a decoupled figure an
        undecoupled upper bound.
        """
        fixture_root = checker.REPO_ROOT
        checker.REPO_ROOT = REPO_ROOT
        self.addCleanup(lambda: setattr(checker, "REPO_ROOT", fixture_root))
        records = REPO_ROOT / checker.EXCURSION_RECORDS
        duts = {
            match.group("sha")
            for record in records.glob("*.md")
            for match in checker.EXCURSION_DUT_RE.finditer(record.read_text())
        }
        self.assertGreaterEqual(len(duts), 2, "only one DUT generation in the tree")
        undecoupled = checker.excursion_undecoupled_duts()
        self.assertTrue(undecoupled)
        self.assertTrue(duts - undecoupled, "every DUT reads as undecoupled")
        # And the decoupled generation's own figures really are excluded.
        owed = checker.excursion_row_figures()
        self.assertIsNotNone(owed)
        for figure in ("13.964", "17.055", "9.709", "7.710", "0.070"):
            self.assertNotIn(figure, owed)

    def test_a_checked_document_without_the_narrative_is_ungraded(self):
        """The vacuity-trap guard against the LIVE records tree, not a fixture.

        `main()` grades every `docs/chipalooza/*.md`, and today that set is one
        document -- so the exposure is the *next* one: a chipalooza document
        that cites this campaign, or quotes one of its figures, without
        narrating them must not be asked for a qualifier it never claimed.
        Graded against the live records tree, because it is the live figure set
        that decides.

        (`docs/citation-gate.md` is deliberately NOT in that glob -- it
        discusses these figures at length, and would fire. That it lives one
        directory up on purpose is asserted by `TestRationaleDocumentCoverage`,
        in `test_the_rationale_document_is_not_itself_a_checked_document`.)
        """
        fixture_root = checker.REPO_ROOT
        checker.REPO_ROOT = REPO_ROOT
        self.addCleanup(lambda: setattr(checker, "REPO_ROOT", fixture_root))
        documents = [
            (doc.name, doc.read_text())
            for doc in sorted(CHIPALOOZA_DIR.glob("*.md"))
            if doc.name != "challenge-4-proposal.md"
        ] + [
            (
                "challenge-5-proposal.md",
                "# A later challenge\n\nNo supply-return narrative at all.\n",
            ),
            (
                "campaign-notes.md",
                "# Notes\n\nSee `sim/supply-impedance-sensitivity/records/LATEST`.\n",
            ),
            (
                "one-figure.md",
                "## 7. Open items\n\n1. **A gap.** The `package` arm reads "
                "`37.590 mV` at the baseline corner, per "
                "`sim/supply-impedance-sensitivity/records/LATEST`.\n",
            ),
        ]
        for name, text in documents:
            with self.subTest(doc=name):
                self.assertEqual(
                    checker.check_excursion_enumeration(CHIPALOOZA_DIR / name, text), []
                )


class TestPresentTenseMismatch(unittest.TestCase):
    """Check 36: a present-tense prose mismatch count is the current record's.

    Check 9 grades the readout blockquote, which Section 4 introduces as the
    document's "single present-tense statement" of the composed top level's
    DRC/LVS numbers. That claim was false about the document that made it: six
    passages in Sections 3 and 7 restated the mismatch count in prose, in three
    present-tense forms check 9 cannot see, and when issue #440's decoupling
    placement (PR #466, 2026-09-26) moved the compare 88 -> 89, the readout and
    the Section 4 row moved while all six still read 88.

    The prose figures that must stay UNGRADED are tested as carefully as the
    ones that must not: Section 7 narrates superseded records paragraph by
    paragraph, and a gate that fired on `88 mismatches at the 2026-09-24 hop`
    would fail on correct prose and teach the next pass to reword around it.
    """

    STAMP = "20260926-081248-203cca3"
    CURRENT = 89

    def setUp(self):
        self.tree = FixtureTree(self)
        self.add_top(self.CURRENT)

    def add_top(self, mismatch_count: int, *, composing: bool = True):
        """The composed top level's current record, at `mismatch_count`."""
        self.tree.add_layout_record(
            "sar-adc-top",
            self.STAMP,
            latest=True,
            drc={"status": "clean", "violation_count": 0},
            lvs=lvs_json(
                mismatch_count=mismatch_count,
                error_count=mismatch_count - 1,
                devices=(871, 871, 804),
                nets=(443, 444, 411),
                pins=(21, 22, 22),
            ),
            compose=compose_json(
                blocks=[composed_block("cdac_array")]
                if composing
                else [composed_block("route", source="generator_report")]
            ),
        )

    def readout(self, block: str = "sar-adc-top", mismatch_count: int | None = None) -> str:
        """The check-9 readout sentence, as `--stats` prints it for `block`."""
        live = checker.signoff_readout(block)
        self.assertIsNotNone(live, block)
        if mismatch_count is not None:
            live = dict(live, mismatch_count=mismatch_count)
        return "> " + checker.readout_sentence(block, live) + "\n"

    def body(self, prose: str, *, readout: bool = True) -> str:
        text = "## 7. Open items before sign-off\n\n"
        if readout:
            text += self.readout() + "\n"
        return text + f"1. **Top-level layout.** {prose}\n"

    def check(self, body: str) -> list[str]:
        return checker.check_present_tense_mismatch(self.tree.document(body), body)

    # -- The three present-tense forms, each graded.

    def test_the_current_count_passes_in_every_form(self):
        for prose in (
            "Stays UNMET/BLOCKED (89 mismatches on the current record).",
            "A device-level match is missing (currently 89 mismatches).",
            "Closing the upstream issue is not the same as clearing "
            "the 89-mismatch LVS gap.",
        ):
            with self.subTest(prose=prose):
                self.assertEqual(self.check(self.body(prose)), [])

    def test_the_real_drift_is_reported_in_every_form(self):
        """88 left behind in prose against an 89-mismatch record: PR #466's gap."""
        for prose in (
            "Stays UNMET/BLOCKED (88 mismatches on the current record).",
            "A device-level match is missing (currently 88 mismatches).",
            "Closing the upstream issue is not the same as clearing "
            "the 88-mismatch LVS gap.",
        ):
            with self.subTest(prose=prose):
                misses = self.check(self.body(prose))
                self.assertEqual(len(misses), 1, misses)
                self.assertIn("88", misses[0])
                self.assertIn(
                    "`layout/sar-adc-top/reports/LATEST` reports 89 mismatches",
                    misses[0],
                )

    def test_the_finding_names_both_dispositions(self):
        """Restate it, or date it -- never delete it."""
        misses = self.check(self.body("(88 mismatches on the current record)."))
        self.assertIn("--stats", misses[0])
        self.assertIn("dated historical", misses[0])

    # -- What must stay ungraded, so the gate cannot fire on correct prose.

    def test_a_dated_historical_figure_is_not_graded(self):
        prose = (
            "Every hop through 2026-09-23 reported 98 mismatches, the "
            "2026-09-24 hop 88 mismatches, and `20260924-214710-b323061` the "
            "same 88 mismatches at 21/22/22 pins."
        )
        self.assertEqual(self.check(self.body(prose)), [])

    def test_the_readout_itself_is_not_graded_twice(self):
        """Check 9 owns the blockquote; this check must not double-report it."""
        self.assertEqual(self.check(self.body("Nothing stated in prose.")), [])

    def test_a_document_stating_no_present_tense_figure_is_not_failed_for_it(self):
        prose = "See §4's machine-checked sign-off-bar readout for the count."
        self.assertEqual(self.check(self.body(prose)), [])

    # -- Parse shapes measured against the live document.

    def test_a_figure_wrapped_across_lines_is_still_graded(self):
        """The live document wraps this very phrase mid-sentence."""
        prose = "Stays UNMET/BLOCKED (88 mismatches on the\n   current record)."
        misses = self.check(self.body(prose))
        self.assertEqual(len(misses), 1, misses)

    def test_a_bold_wrapped_figure_is_graded(self):
        misses = self.check(self.body("Still **88** mismatches on the current record."))
        self.assertEqual(len(misses), 1, misses)

    def test_every_occurrence_is_graded_not_only_the_first(self):
        body = self.body(
            "Stays UNMET/BLOCKED (88 mismatches on the current record), and a "
            "device-level match is still missing (currently 88 mismatches)."
        )
        self.assertEqual(len(self.check(body)), 2)

    # -- Which flow the claim is graded against.

    def test_a_sub_block_count_cannot_become_the_grading_basis(self):
        """`layout/comparator/` reports 1 mismatch and composes no cell."""
        self.tree.add_layout_record(
            "comparator",
            "20260924-120000-abcdef0",
            latest=True,
            drc={"status": "clean", "violation_count": 0},
            lvs=lvs_json(
                mismatch_count=1,
                error_count=0,
                status="match",
                devices=(11, 11, 11),
                nets=(9, 9, 9),
                pins=(6, 6, 6),
            ),
            compose=compose_json(blocks=[composed_block("route", source="generator_report")]),
        )
        body = (
            "## 7. Open items\n\n"
            + self.readout()
            + "\n"
            + self.readout("comparator")
            + "\n1. **Top-level layout.** Still 1 mismatches on the current record.\n"
        )
        misses = self.check(body)
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("reports 89 mismatches", misses[0])
        self.assertNotIn("comparator", misses[0])

    def test_a_present_tense_figure_with_no_composing_readout_is_reported(self):
        """The vacuity guard: silence here would make deleting the readout a pass."""
        self.add_top(self.CURRENT, composing=False)
        misses = self.check(self.body("(89 mismatches on the current record)."))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("reads out no composing", misses[0])

    def test_a_figure_stated_without_any_readout_is_reported(self):
        misses = self.check(
            self.body("(89 mismatches on the current record).", readout=False)
        )
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("reads out no composing", misses[0])

    def test_composed_mismatch_counts_names_only_the_composing_flow(self):
        body = self.body("Nothing stated in prose.")
        self.assertEqual(checker.composed_mismatch_counts(body), {"sar-adc-top": 89})

    # -- The live pair, not a fixture: this is what CI actually grades.

    def test_the_real_document_and_the_real_tree_agree(self):
        fixture_root = checker.REPO_ROOT
        checker.REPO_ROOT = REPO_ROOT
        self.addCleanup(lambda: setattr(checker, "REPO_ROOT", fixture_root))
        doc = REPO_ROOT / "docs" / "chipalooza" / "challenge-4-proposal.md"
        text = doc.read_text()
        counts = checker.composed_mismatch_counts(text)
        self.assertEqual(
            list(counts),
            ["sar-adc-top"],
            "the composing flow is no longer identified from the tree as the "
            "single flow whose composition takes in a cell",
        )
        stated = list(
            checker.PRESENT_TENSE_MISMATCH_RE.finditer(
                checker._collapse_quoted_prose(text)[0]
            )
        )
        self.assertTrue(
            stated,
            "the document states none of the three present-tense forms, so this "
            "check grades nothing on the live pair -- if that is deliberate, "
            "retire the check rather than leaving it vacuous",
        )
        self.assertEqual(checker.check_present_tense_mismatch(doc, text), [])


class TestCampaignCensus(unittest.TestCase):
    """Check 37: which `sim/` campaigns holding evidence the document cites at all.

    The gap this was written for: `sim/spec-coverage.json`'s one `structural`
    row (**Architecture**) indexes four benches, check 11 skips rows outside
    `MEASURED_CLAIM_CLASSES`, and two of those benches are indexed nowhere
    else -- so `sim/sampling-frontend/` and `sim/sampling-cdac-handoff/` were
    cited nowhere in the document, and every other check here grades citations
    that exist rather than ones that are missing.

    The two things that must NOT be gradeable as a citation are tested as
    carefully as the ones that must: a mention of the campaign *directory*
    (this document names `sim/vcm-drive-budget/` in prose a dozen times) and a
    `records/` directory with no stamp (which is how the **Corners** row cited
    the two smoke campaigns). Accepting either would have passed the document
    the check was written against.
    """

    STAMP = "20260824-231304-144edeb"
    OTHER = "20260825-021113-a237c79"

    def setUp(self):
        self.tree = FixtureTree(self)
        # Check 37 is anchored on the tree (a coverage index) AND on the
        # document (a Section 4 table); both are built by default so a test
        # states only what it is about, and the two inert cases get their own
        # tests below.
        self.tree.add_coverage_index(
            {"parameter": "Architecture", "claim_class": "structural"}
        )

    def body(self, *rows: str, census: str | None = None) -> str:
        text = spec_table(*rows)
        if census is not None:
            text += "\n> " + census + "\n"
        return text

    def check(self, body: str) -> list[str]:
        return checker.check_campaign_census(self.tree.document(body), body)

    def cite(self, campaign: str, stamp: str) -> str:
        return f"`sim/{campaign}/records/{stamp}.md`"

    def row(self, *citations: str) -> str:
        return "| Architecture | topology | DRAFT | **MET** | " + ", ".join(citations) + " |"

    # -- The omission, in the shape it really occurred.

    def test_an_uncited_campaign_with_no_census_is_reported(self):
        self.tree.add_sim_record("sampling-cdac-handoff", self.STAMP)
        misses = self.check(self.body(self.row("`design/sar_adc_top.sch`")))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("sim/sampling-cdac-handoff/", misses[0])
        self.assertIn("**1** record", misses[0])
        self.assertIn("states no campaign-citation census", misses[0])

    def test_citing_the_campaign_by_path_clears_it(self):
        self.tree.add_sim_record("sampling-cdac-handoff", self.STAMP)
        body = self.body(self.row(self.cite("sampling-cdac-handoff", self.STAMP)))
        self.assertEqual(self.check(body), [])

    def test_the_record_count_sizes_the_hole(self):
        """Two records is a wider hole than one, and the message says which."""
        self.tree.add_sim_record("sampling-frontend", self.STAMP)
        self.tree.add_sim_record("sampling-frontend", self.OTHER)
        misses = self.check(self.body(self.row("`design/sampling_frontend.sch`")))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("**2** records", misses[0])

    # -- The two near-miss citation shapes that must still count as uncited.

    def test_naming_the_campaign_directory_is_not_a_citation(self):
        """`sim/vcm-drive-budget/` in prose says a campaign exists, not which record."""
        self.tree.add_sim_record("vcm-drive-budget", self.STAMP)
        misses = self.check(
            self.body(self.row("see `sim/vcm-drive-budget/` for the drive budget"))
        )
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("sim/vcm-drive-budget/", misses[0])

    def test_naming_the_records_directory_without_a_stamp_is_not_a_citation(self):
        """The shape the Corners row used: `sim/mc-smoke/records/`, no stamp."""
        self.tree.add_sim_record("mc-smoke", self.STAMP)
        misses = self.check(self.body(self.row("`sim/mc-smoke/records/`")))
        self.assertEqual(len(misses), 1, misses)
        self.assertIn("sim/mc-smoke/", misses[0])

    def test_a_records_latest_pointer_is_not_a_stamp_citation(self):
        self.tree.add_sim_record("mc-smoke", self.STAMP, latest=True)
        misses = self.check(self.body(self.row("`sim/mc-smoke/records/LATEST`")))
        self.assertEqual(len(misses), 1, misses)

    # -- A LATEST pointer file must not be counted as a record.

    def test_the_latest_pointer_is_not_counted_as_a_record(self):
        self.tree.add_sim_record("mc-smoke", self.STAMP, latest=True)
        census = checker.campaign_census("")
        self.assertEqual(census["record_counts"]["mc-smoke"], 1)

    # -- The census sentence, graded in both directions.

    def test_the_correct_census_passes(self):
        self.tree.add_sim_record("sampling-cdac-handoff", self.STAMP)
        self.tree.add_sim_record("sampling-frontend", self.OTHER)
        body = self.body(
            self.row(self.cite("sampling-cdac-handoff", self.STAMP)),
            census=checker.campaign_sentence(checker.campaign_census("")),
        )
        # The sentence is derived from a document citing nothing, so it must
        # be re-derived against the body it lands in -- which is the point.
        body = self.body(
            self.row(self.cite("sampling-cdac-handoff", self.STAMP)),
            census=checker.campaign_sentence(checker.campaign_census(body)),
        )
        self.assertEqual(self.check(body), [])

    def test_a_stale_count_in_the_census_is_reported(self):
        self.tree.add_sim_record("sampling-cdac-handoff", self.STAMP)
        self.tree.add_sim_record("sampling-frontend", self.OTHER)
        row = self.row(self.cite("sampling-cdac-handoff", self.STAMP))
        live = checker.campaign_sentence(checker.campaign_census(self.body(row)))
        stale = live.replace("**2** campaigns", "**1** campaigns")
        self.assertNotEqual(stale, live, "fixture no longer matches the sentence")
        misses = self.check(self.body(row, census=stale))
        self.assertTrue(any("campaigns=1" in miss for miss in misses), misses)

    def test_naming_the_wrong_uncited_campaign_is_reported(self):
        self.tree.add_sim_record("sampling-cdac-handoff", self.STAMP)
        self.tree.add_sim_record("sampling-frontend", self.OTHER)
        row = self.row(self.cite("sampling-cdac-handoff", self.STAMP))
        live = checker.campaign_sentence(checker.campaign_census(self.body(row)))
        self.assertIn("`sim/sampling-frontend/`", live)
        wrong = live.replace("`sim/sampling-frontend/`", "`sim/mc-smoke/`")
        misses = self.check(self.body(row, census=wrong))
        self.assertTrue(any("misstates which evidence" in miss for miss in misses), misses)

    def test_a_wrong_record_count_in_the_exception_clause_is_reported(self):
        self.tree.add_sim_record("sampling-frontend", self.STAMP)
        self.tree.add_sim_record("sampling-frontend", self.OTHER)
        row = self.row("`design/sampling_frontend.sch`")
        live = checker.campaign_sentence(checker.campaign_census(self.body(row)))
        self.assertIn("(**2** records)", live)
        wrong = live.replace("(**2** records)", "(**1** records)")
        misses = self.check(self.body(row, census=wrong))
        self.assertTrue(any("how large the hole is" in miss for miss in misses), misses)

    def test_a_census_claiming_none_uncited_against_a_real_hole_is_reported(self):
        """Deleting the exception list must not be a way to unstate the hole."""
        self.tree.add_sim_record("sampling-frontend", self.STAMP)
        misses = self.check(
            self.body(
                self.row("`design/sampling_frontend.sch`"),
                census=(
                    "of the **1** campaigns under `sim/` holding at least one "
                    "committed record, **1** are cited by path in this document "
                    "and **0** are not: " + checker.CAMPAIGN_CENSUS_NONE
                ),
            )
        )
        self.assertTrue(misses, "a census claiming full coverage went ungraded")
        self.assertTrue(any("cited=1" in miss for miss in misses), misses)

    # -- Inertness, and the two anchors that hold it.

    def test_no_coverage_index_makes_the_check_inert(self):
        tree = FixtureTree(self)
        tree.add_sim_record("sampling-frontend", self.STAMP)
        body = spec_table(self.row("`design/sampling_frontend.sch`"))
        self.assertEqual(checker.check_campaign_census(tree.document(body), body), [])

    def test_no_section_4_table_makes_the_check_inert(self):
        self.tree.add_sim_record("sampling-frontend", self.STAMP)
        body = "## 7. Open items\n\n1. **Something.** No spec table here.\n"
        self.assertEqual(self.check(body), [])

    def test_full_coverage_needs_no_census_sentence(self):
        """Nothing to size means the census is optional, not owed."""
        self.tree.add_sim_record("sampling-cdac-handoff", self.STAMP)
        body = self.body(self.row(self.cite("sampling-cdac-handoff", self.STAMP)))
        self.assertEqual(self.check(body), [])

    def test_a_campaign_with_no_committed_record_is_not_demanded(self):
        (self.tree.root / "sim" / "empty-campaign" / "records").mkdir(parents=True)
        body = self.body(self.row("`design/sar_adc_top.sch`"))
        self.assertEqual(self.check(body), [])


class TestCampaignCensusAgainstTheRealTree(unittest.TestCase):
    """Check 37 on the live document and the live `sim/` tree.

    A separate class from `TestCampaignCensus` on purpose: `FixtureTree`
    monkeypatches `checker.REPO_ROOT` for the lifetime of the test that builds
    one, so a live-tree assertion made in that class would silently resolve
    against the fixture's empty tree and pass vacuously.
    """

    def test_the_real_document_cites_every_campaign_holding_a_record(self):
        """The positive form on the real tree: this is what the pass fixed.

        Asserted as a floor on the campaign count too, so a `sim/` tree that
        stopped being walked would fail here rather than pass vacuously with
        zero campaigns and zero holes.
        """
        text = (checker.CHIPALOOZA_DIR / "challenge-4-proposal.md").read_text()
        census = checker.campaign_census(text)
        self.assertGreaterEqual(census["campaigns"], 14, census)
        self.assertEqual(census["uncited"], [], census)

    def test_the_two_campaigns_the_check_was_written_for_are_cited_by_path(self):
        text = (checker.CHIPALOOZA_DIR / "challenge-4-proposal.md").read_text()
        for campaign in ("sampling-frontend", "sampling-cdac-handoff"):
            with self.subTest(campaign=campaign):
                self.assertTrue(
                    any(
                        match.group("block") == campaign
                        for match in checker.EVIDENCE_PATH_RE.finditer(text)
                        if match.group("top") == "sim"
                    ),
                    f"sim/{campaign}/ is no longer cited by path",
                )

    def test_the_stats_sentence_round_trips_on_the_real_document(self):
        """`--stats` output must be pasteable: what it prints, the check accepts."""
        text = (checker.CHIPALOOZA_DIR / "challenge-4-proposal.md").read_text()
        sentence = checker.campaign_sentence(checker.campaign_census(text))
        match = checker.CAMPAIGN_CENSUS_RE.search(sentence)
        self.assertIsNotNone(match, sentence)
        self.assertEqual(int(match.group("campaigns")), len(checker.sim_campaigns_with_records()))

    def test_the_real_document_states_the_census(self):
        """A stated census is what makes a future hole a graded finding.

        Without the sentence the check still fires -- but only via its
        no-census branch, which reports the omission rather than the drift.
        With it, a newly-uncited campaign is reported against a number a
        reader can diff.
        """
        text = (checker.CHIPALOOZA_DIR / "challenge-4-proposal.md").read_text()
        collapsed, _offsets = checker._collapse_quoted_prose(text)
        self.assertTrue(
            checker.CAMPAIGN_CENSUS_RE.search(collapsed),
            "challenge-4-proposal.md no longer states the campaign-citation census",
        )


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

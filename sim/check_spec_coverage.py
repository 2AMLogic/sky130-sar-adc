#!/usr/bin/env python3
"""Spec-row coverage check -- T1 item 9's completeness / cold-start / pinning
contract, enforced instead of asserted (issue #31).

    python3 sim/check_spec_coverage.py            # check (exit 1 on any failure)
    python3 sim/check_spec_coverage.py --render   # regenerate sim/spec-coverage.md
    python3 sim/check_spec_coverage.py --print    # write that rendering to stdout

`klayout-tools/docs/design-evidence-tiers.md` item 9 asks for "every claimed
measurement's testbench committed, with a documented cold-start invocation a
third party can run; pinned PDK revision". Three properties, none of which any
one campaign owns, and all three of which regress SILENTLY -- adding one more
claimed spec row without its bench fails the item while every individual
campaign still looks green. So they are checked mechanically here rather than
described in prose:

  COMPLETENESS  every row of spec/target-spec.md's "## Target table" appears in
                sim/spec-coverage.json with a matching status, and every row
                that carries a claim has at least one committed bench and at
                least one committed evidence record. The one class permitted to
                have no bench ("unbenched") is permitted only on a DRAFT row, so
                RATIFYING a row mechanically forces a bench to exist for it.

  COLD START    each bench's documented invocation appears VERBATIM in the file
                the index says documents it (a runner docstring or an experiment
                README), every flag/subcommand in that invocation is really
                accepted by the runner, and the invocation names the same script
                the record's own "Written by" footer names -- so the documented
                command cannot drift away from the private one an agent actually
                ran.

  PINNING       every indexed record states, in its own Environment section, a
                PDK variant + open_pdks commit matching sim/pdk.json and an
                ngspice major at or above sim/toolchain.json's floor, plus the
                DUT netlist SHA-256 that is the per-record xschem-side
                provenance (sim/selftest.sh stage 2's rule: an xschem version
                difference is a warning, the netlist hash is the real pin).

Two further properties keep the index itself honest: the two harness proofs
(sim/README.md "Harness self-test experiments") may never be listed as a bench
for any row, and any experiment directory that has minted records but appears
nowhere in the index is reported as an orphan -- a bench that exists but is
indexed by nothing is exactly the gap this file is here to prevent.

No spec VALUE is encoded here. The check compares row names and statuses
against spec/target-spec.md itself and the corner-set expectation against the
process-corner list in sim/pdk.json plus the SHAPE of an axis sweep (three
points: low/nominal/high), never against a hardcoded -40/27/125 or 1.62/1.8/1.98
-- sim/harness/corners.py's own docstring rules out putting ratified spec
numbers in harness code, and this check follows the same rule.

Pure file reads: no ngspice, no PDK, no network. It runs in the headless
`checks` CI job (npm run check:ci), not the PDK-gated one.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable, NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent

INDEX_REL = "sim/spec-coverage.json"
DOC_REL = "sim/spec-coverage.md"
SPEC_REL = "spec/target-spec.md"
PDK_REL = "sim/pdk.json"
TOOLCHAIN_REL = "sim/toolchain.json"

TARGET_TABLE_HEADING = "## Target table"

# claim_class -> (needs at least one bench?, must the row be DRAFT?)
CLAIM_CLASSES = {
    "ratified-measured": True,
    "draft-informational": True,
    "methodology": True,
    "structural": True,
    "unbenched": False,
}
# Classes whose records must cite the spec file in their own Claim field.
CLASSES_CITING_SPEC = {"ratified-measured", "draft-informational"}

RE_PDK_LINE = re.compile(r"^- PDK:\s*(\S+)\s*@\s*([0-9a-fA-F]{7,40})\s*$", re.M)
RE_NGSPICE_LINE = re.compile(r"^- ngspice:\s*ngspice-(\d+)", re.M)
RE_NETLIST_SHA = re.compile(r"^- DUT netlist sha256:\s*`?([0-9a-f]{64})`?", re.M)
RE_WRITTEN_BY = re.compile(r"Written by `([^`]+)`")
RE_CLAIM = re.compile(r"^- \*\*Claim\*\*:\s*(.*)$", re.M)
RE_CORNER_MATRIX = re.compile(r"^- \*\*Corner matrix run\*\*:\s*(.*)$", re.M)
RE_AXIS_LIST = re.compile(r"(process|temperature_c|supply_v)=\[([^\]]*)\]")


class Failure(NamedTuple):
    code: str
    where: str
    message: str

    def render(self) -> str:
        return f"[{self.code}] {self.where}: {self.message}"


class SpecTableError(Exception):
    """spec/target-spec.md's target table could not be parsed at all."""


def parse_target_table(text: str) -> list[tuple[str, str]]:
    """Return [(parameter cell, status cell)] from the "## Target table"
    markdown table, in document order.

    Parsing the spec table (rather than trusting the index to list the right
    rows) is what makes a newly-added spec row fail this check until it is
    indexed -- the silent-regression path T1 item 9 grades."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip().lower() == TARGET_TABLE_HEADING.lower():
            start = i
            break
    if start is None:
        raise SpecTableError(f"no '{TARGET_TABLE_HEADING}' heading found")

    table: list[str] = []
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if stripped.startswith("## "):
            break
        if stripped.startswith("|"):
            table.append(stripped)
        elif table:
            break  # blank line after the table ends it
    if len(table) < 3:
        raise SpecTableError(
            f"'{TARGET_TABLE_HEADING}' has no parseable rows (found {len(table)} table lines)"
        )

    header = [c.strip().lower() for c in table[0].strip("|").split("|")]
    for required in ("parameter", "target", "status"):
        if required not in header:
            raise SpecTableError(
                f"'{TARGET_TABLE_HEADING}' header is missing a '{required}' column: {header}"
            )
    p_idx, s_idx = header.index("parameter"), header.index("status")

    rows: list[tuple[str, str]] = []
    for line in table[2:]:  # table[1] is the |---|---| separator
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) <= max(p_idx, s_idx):
            continue
        if not cells[p_idx]:
            continue
        rows.append((cells[p_idx], cells[s_idx]))
    if not rows:
        raise SpecTableError(f"'{TARGET_TABLE_HEADING}' contains no data rows")
    return rows


def normalize_status(status_cell: str) -> str:
    """RATIFIED if the spec's own status cell says so, else DRAFT. The cell
    carries decoration ('**RATIFIED** (DR-003 via #27)', 'DRAFT (target
    value)'); only the ratified/not distinction gates anything here."""
    return "RATIFIED" if "RATIFIED" in status_cell.upper() else "DRAFT"


def split_invocation(command: str) -> list[str]:
    return [tok for tok in command.split() if tok]


class CoverageCheck:
    def __init__(
        self,
        root: Path,
        index_rel: str = INDEX_REL,
        doc_rel: str = DOC_REL,
        spec_rel: str = SPEC_REL,
    ) -> None:
        self.root = Path(root)
        self.index_rel = index_rel
        self.doc_rel = doc_rel
        self.spec_rel = spec_rel
        self.failures: list[Failure] = []
        self.index: dict = {}

    # ---------------------------------------------------------------- helpers

    def fail(self, code: str, where: str, message: str) -> None:
        self.failures.append(Failure(code, where, message))

    def read(self, rel: str) -> str | None:
        path = self.root / rel
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    def exists(self, rel: str, code: str, where: str, what: str) -> bool:
        path = self.root / rel
        if not path.is_file():
            self.fail(code, where, f"{what} does not exist: {rel}")
            return False
        if path.stat().st_size == 0:
            self.fail(code, where, f"{what} is empty: {rel}")
            return False
        return True

    # ------------------------------------------------------------------- main

    def run(self, check_doc: bool = True) -> list[Failure]:
        self.failures = []

        raw_index = self.read(self.index_rel)
        if raw_index is None:
            self.fail("index-missing", self.index_rel, "coverage index not found")
            return self.failures
        try:
            self.index = json.loads(raw_index)
        except json.JSONDecodeError as exc:
            self.fail("index-unparseable", self.index_rel, f"invalid JSON: {exc}")
            return self.failures

        spec_text = self.read(self.spec_rel)
        if spec_text is None:
            self.fail("spec-missing", self.spec_rel, "spec file not found")
            return self.failures
        try:
            spec_rows = parse_target_table(spec_text)
        except SpecTableError as exc:
            self.fail("spec-table-unparseable", self.spec_rel, str(exc))
            return self.failures

        self._check_rows_against_spec(spec_rows)
        self._check_harness_proofs()
        self._check_orphan_experiments()
        if check_doc:
            self._check_rendered_doc()
        return self.failures

    # --------------------------------------------------------- row / bench

    def _check_rows_against_spec(self, spec_rows: list[tuple[str, str]]) -> None:
        spec_status = {param: normalize_status(status) for param, status in spec_rows}
        index_rows = self.index.get("rows", [])
        indexed = {row.get("parameter", ""): row for row in index_rows}

        for param in spec_status:
            if param not in indexed:
                self.fail(
                    "spec-row-missing-from-index",
                    param,
                    f"{self.spec_rel}'s target table names this row but "
                    f"{self.index_rel} does not index it -- a claimed row with no "
                    "bench entry is exactly the regression T1 item 9 grades",
                )
        for param in indexed:
            if param not in spec_status:
                self.fail(
                    "index-row-not-in-spec",
                    param,
                    f"{self.index_rel} indexes a row that {self.spec_rel}'s target "
                    "table does not contain (renamed or removed?)",
                )

        for param, row in indexed.items():
            if param not in spec_status:
                continue
            self._check_row(param, row, spec_status[param])

    def _check_row(self, param: str, row: dict, spec_status: str) -> None:
        if row.get("status") != spec_status:
            self.fail(
                "status-drift",
                param,
                f"index says status={row.get('status')!r} but {self.spec_rel} says "
                f"{spec_status!r}",
            )

        claim_class = row.get("claim_class")
        if claim_class not in CLAIM_CLASSES:
            self.fail(
                "unknown-claim-class",
                param,
                f"claim_class={claim_class!r} is not one of {sorted(CLAIM_CLASSES)}",
            )
            return

        benches = row.get("benches", [])

        if claim_class == "unbenched":
            if spec_status == "RATIFIED":
                self.fail(
                    "ratified-row-unbenched",
                    param,
                    "a RATIFIED spec row may never be claim_class 'unbenched' -- "
                    "ratifying a row obliges a committed testbench for it",
                )
            if benches:
                self.fail(
                    "unbenched-row-has-bench",
                    param,
                    f"claim_class 'unbenched' but {len(benches)} bench(es) listed -- "
                    "reclassify the row instead",
                )
            if len(str(row.get("reason", "")).strip()) < 40:
                self.fail(
                    "unbenched-row-missing-reason",
                    param,
                    "claim_class 'unbenched' requires a substantive 'reason' saying "
                    "why no bench is owed yet",
                )
            return

        if not benches:
            self.fail(
                "row-has-no-bench",
                param,
                f"claim_class {claim_class!r} requires at least one committed bench "
                "under sim/ -- no spec claim may rest on prose",
            )
            return

        for bench in benches:
            self._check_bench(param, claim_class, bench)

        if claim_class in CLASSES_CITING_SPEC:
            cited = False
            for bench in benches:
                for rec_rel in bench.get("records", []):
                    text = self.read(rec_rel)
                    if text is None:
                        continue
                    claim = RE_CLAIM.search(text)
                    if claim and self.spec_rel in claim.group(1):
                        cited = True
            if not cited:
                self.fail(
                    "record-claim-not-cited",
                    param,
                    f"no indexed record's Claim field cites {self.spec_rel} -- the "
                    "index links a record to this row that the record itself does "
                    "not claim",
                )

        if claim_class == "methodology":
            for bench in benches:
                for rec_rel in bench.get("records", []):
                    self._check_corner_set(param, rec_rel)

    def _check_bench(self, param: str, claim_class: str, bench: dict) -> None:
        experiment = bench.get("experiment", "<unnamed>")
        where = f"{param} -> {experiment}"

        exp_dir = self.root / "sim" / experiment
        if not exp_dir.is_dir():
            self.fail("missing-path", where, f"experiment directory not found: sim/{experiment}")
            return

        runner_rel = bench.get("runner", "")
        runner_ok = self.exists(runner_rel, "missing-path", where, "runner")

        decks = bench.get("testbench", [])
        if not decks and not bench.get("testbench_note"):
            self.fail(
                "bench-has-no-deck",
                where,
                "no SPICE deck listed and no 'testbench_note' explaining why "
                "(a composite/derived experiment must say so explicitly)",
            )
        for deck in decks:
            self.exists(deck, "missing-path", where, "testbench deck")

        records = bench.get("records", [])
        if not records:
            self.fail(
                "bench-has-no-record",
                where,
                "bench lists no evidence record -- a committed testbench with no "
                "record does not substantiate the row",
            )

        runner_src = self.read(runner_rel) if runner_ok else None
        self._check_cold_start(where, bench, runner_src)

        for rec_rel in records:
            if not self.exists(rec_rel, "missing-path", where, "evidence record"):
                continue
            self._check_record_pins(where, rec_rel)
            self._check_record_runner(where, bench, rec_rel)

    # ------------------------------------------------------------ cold start

    def _check_cold_start(self, where: str, bench: dict, runner_src: str | None) -> None:
        cold_start = bench.get("cold_start", "").strip()
        if not cold_start:
            self.fail(
                "cold-start-missing",
                where,
                "no cold_start invocation -- T1 item 9 requires a documented "
                "command a third party can run",
            )
            return

        documented_in = bench.get("documented_in", "")
        doc_text = self.read(documented_in) if documented_in else None
        if doc_text is None:
            self.fail(
                "cold-start-undocumented",
                where,
                f"documented_in file not found: {documented_in!r}",
            )
        elif cold_start not in doc_text:
            self.fail(
                "cold-start-undocumented",
                where,
                f"the cold-start command is not documented verbatim in "
                f"{documented_in} -- a third party cannot run what is written down "
                f"nowhere. Missing line: {cold_start}",
            )

        tokens = split_invocation(cold_start)
        runner_rel = bench.get("runner", "")
        if runner_rel and runner_rel not in tokens:
            self.fail(
                "cold-start-runner-mismatch",
                where,
                f"cold_start does not invoke the bench's own runner ({runner_rel}): "
                f"{cold_start}",
            )
        if runner_src is None:
            return

        # Every flag and every bare subcommand in the documented invocation must
        # actually be accepted by the runner. This is what catches a renamed flag
        # leaving the documented command un-runnable.
        skip_next = False
        seen_script = False
        for token in tokens:
            if skip_next:
                skip_next = False
                continue
            if token == runner_rel:
                seen_script = True
                continue
            if not seen_script:
                continue  # interpreter / env prefix
            if token.startswith("--"):
                if token not in runner_src:
                    self.fail(
                        "cold-start-unknown-flag",
                        where,
                        f"{runner_rel} does not define {token}, but the documented "
                        "cold-start command passes it",
                    )
                skip_next = True  # its value, if any (a following --flag re-checks)
                continue
            if f'"{token}"' not in runner_src and f"'{token}'" not in runner_src:
                self.fail(
                    "cold-start-unknown-subcommand",
                    where,
                    f"{runner_rel} does not define the subcommand {token!r} used by "
                    "the documented cold-start command",
                )

    # --------------------------------------------------------------- records

    def _check_record_pins(self, where: str, rec_rel: str) -> None:
        text = self.read(rec_rel) or ""
        pdk_raw = self.read(PDK_REL)
        tc_raw = self.read(TOOLCHAIN_REL)
        if pdk_raw is None or tc_raw is None:
            self.fail("pins-missing", where, f"{PDK_REL} / {TOOLCHAIN_REL} not readable")
            return
        pdk = json.loads(pdk_raw)
        toolchain = json.loads(tc_raw)

        pdk_match = RE_PDK_LINE.search(text)
        if not pdk_match:
            self.fail(
                "pdk-pin-missing",
                where,
                f"{rec_rel} states no '- PDK: <variant> @ <commit>' line -- the "
                "record does not pin the PDK revision it was claimed against",
            )
        else:
            variant, commit = pdk_match.group(1), pdk_match.group(2).lower()
            if variant != pdk.get("variant"):
                self.fail(
                    "pdk-pin-drift",
                    where,
                    f"{rec_rel} pins PDK variant {variant!r}, {PDK_REL} pins "
                    f"{pdk.get('variant')!r}",
                )
            if commit != str(pdk.get("open_pdks_commit", "")).lower():
                self.fail(
                    "pdk-pin-drift",
                    where,
                    f"{rec_rel} pins open_pdks {commit}, {PDK_REL} pins "
                    f"{pdk.get('open_pdks_commit')} -- records from different model "
                    "libraries are not comparable",
                )

        ng_match = RE_NGSPICE_LINE.search(text)
        floor = toolchain.get("ngspice_min_major")
        if not ng_match:
            self.fail(
                "ngspice-pin-missing",
                where,
                f"{rec_rel} states no '- ngspice: ngspice-<major>' line",
            )
        elif floor is not None and int(ng_match.group(1)) < int(floor):
            self.fail(
                "ngspice-pin-drift",
                where,
                f"{rec_rel} was produced with ngspice-{ng_match.group(1)}, below "
                f"{TOOLCHAIN_REL}'s floor of {floor}",
            )

        if not RE_NETLIST_SHA.search(text):
            self.fail(
                "netlist-pin-missing",
                where,
                f"{rec_rel} states no 'DUT netlist sha256' line -- that hash is the "
                "per-record netlisting (xschem-side) provenance",
            )

    def _check_record_runner(self, where: str, bench: dict, rec_rel: str) -> None:
        text = self.read(rec_rel) or ""
        match = RE_WRITTEN_BY.search(text)
        if not match:
            self.fail(
                "record-runner-missing",
                where,
                f"{rec_rel} has no 'Written by `...`' footer naming the invocation "
                "that produced it",
            )
            return
        written_tokens = split_invocation(match.group(1))
        runner_rel = bench.get("runner", "")
        if written_tokens and written_tokens[0] != runner_rel:
            self.fail(
                "record-runner-mismatch",
                where,
                f"{rec_rel} was written by {written_tokens[0]}, but the index lists "
                f"this record under the bench whose runner is {runner_rel}",
            )
            return
        cold_tokens = set(split_invocation(bench.get("cold_start", "")))
        missing = [tok for tok in written_tokens[1:] if tok not in cold_tokens]
        if missing:
            self.fail(
                "cold-start-record-mismatch",
                where,
                f"{rec_rel} was minted by an invocation carrying {missing}, which the "
                "documented cold-start command does not include -- the documented "
                "command is not the one actually used",
            )

    def _check_corner_set(self, param: str, rec_rel: str) -> None:
        text = self.read(rec_rel) or ""
        where = f"{param} -> {rec_rel}"
        match = RE_CORNER_MATRIX.search(text)
        if not match:
            self.fail(
                "corner-set-missing",
                where,
                "record states no 'Corner matrix run' line, so it cannot evidence "
                "the ratified corner-set row",
            )
            return
        axes = {name: values for name, values in RE_AXIS_LIST.findall(match.group(1))}
        pdk_raw = self.read(PDK_REL)
        expected_processes = json.loads(pdk_raw)["process_corners"] if pdk_raw else []
        listed = axes.get("process", "")
        for corner in expected_processes:
            if f"'{corner}'" not in listed and f'"{corner}"' not in listed:
                self.fail(
                    "corner-set-incomplete",
                    where,
                    f"process corner {corner!r} (from {PDK_REL}) is absent from the "
                    f"record's corner matrix: process=[{listed}]",
                )
        # Shape, not values: a low/nominal/high sweep on each of the other two
        # axes. The numbers themselves live in the spec and in the record --
        # restating them here would put a ratified spec value in harness code,
        # which sim/harness/corners.py deliberately refuses to do.
        for axis in ("temperature_c", "supply_v"):
            values = [v for v in axes.get(axis, "").split(",") if v.strip()]
            if len(values) < 3:
                self.fail(
                    "corner-set-incomplete",
                    where,
                    f"axis {axis} lists {len(values)} point(s); the ratified corner "
                    "row sweeps low/nominal/high on each axis",
                )

    # -------------------------------------------------------- index hygiene

    def _check_harness_proofs(self) -> None:
        proofs = self.index.get("harness_proofs", [])
        if not proofs:
            self.fail(
                "harness-proofs-undeclared",
                self.index_rel,
                "no harness_proofs declared -- sim/README.md's harness self-tests "
                "must be named explicitly so they are visibly excluded",
            )
        proof_names = {p.get("experiment", "") for p in proofs}
        for proof in proofs:
            name = proof.get("experiment", "")
            tb_rel = f"sim/{name}/testbench/tb.json"
            text = self.read(tb_rel)
            if text is None:
                self.fail(
                    "missing-path",
                    name,
                    f"declared harness proof has no manifest at {tb_rel}",
                )
                continue
            claim = json.loads(text).get("claim", "")
            if not claim.strip().lower().startswith("none"):
                self.fail(
                    "harness-proof-claims-spec-row",
                    name,
                    f"{tb_rel}'s claim must start with 'None' -- a harness proof "
                    "never substantiates a spec row",
                )

        for row in self.index.get("rows", []):
            for bench in row.get("benches", []):
                if bench.get("experiment") in proof_names:
                    self.fail(
                        "harness-proof-counted",
                        row.get("parameter", "<row>"),
                        f"harness proof {bench.get('experiment')!r} is listed as a "
                        "bench for a spec row -- harness self-tests are never "
                        "counted toward T1 item 9",
                    )

    def _check_orphan_experiments(self) -> None:
        proof_names = {p.get("experiment", "") for p in self.index.get("harness_proofs", [])}
        indexed = {
            bench.get("experiment")
            for row in self.index.get("rows", [])
            for bench in row.get("benches", [])
        }
        sim_dir = self.root / "sim"
        if not sim_dir.is_dir():
            return
        for child in sorted(sim_dir.iterdir()):
            if not child.is_dir():
                continue
            records_dir = child / "records"
            if not records_dir.is_dir():
                continue
            if not any(records_dir.glob("*.md")):
                continue
            name = child.name
            if name in proof_names or name in indexed:
                continue
            self.fail(
                "orphan-experiment",
                name,
                f"sim/{name}/records/ holds evidence but the experiment appears "
                f"nowhere in {self.index_rel} -- index it under the row it "
                "substantiates, or declare it a harness proof",
            )

    def _check_rendered_doc(self) -> None:
        expected = render_markdown(self.index)
        actual = self.read(self.doc_rel)
        if actual is None:
            self.fail(
                "doc-missing",
                self.doc_rel,
                "rendered index not found -- run python3 sim/check_spec_coverage.py --render",
            )
        elif actual != expected:
            self.fail(
                "doc-stale",
                self.doc_rel,
                f"rendered index is out of date with {self.index_rel} -- run "
                "python3 sim/check_spec_coverage.py --render",
            )


# ------------------------------------------------------------------ rendering

COVERAGE_LABEL = {
    "ratified-measured": "benched (ratified, graded pass/fail)",
    "draft-informational": "benched (DRAFT row, evidence informational)",
    "methodology": "benched (methodology row, evidenced by the campaigns that ran it)",
    "structural": "benched (structural row, exercised block by block)",
    "unbenched": "NOT benched -- deliberately, see reason",
}


def _bullets(lines: Iterable[str]) -> str:
    return "\n".join(lines)


def render_markdown(index: dict) -> str:
    """Render the index as the committed human-readable table. Deterministic:
    the check compares this byte-for-byte against sim/spec-coverage.md, so a
    hand-edited rendering (or a stale one) fails."""
    out: list[str] = []
    out.append("<!-- GENERATED FILE -- do not edit by hand.")
    out.append("     Source of truth: sim/spec-coverage.json")
    out.append("     Regenerate:      python3 sim/check_spec_coverage.py --render")
    out.append("     Checked by:      npm run check:spec-coverage (part of npm run check:ci) -->")
    out.append("")
    out.append("# Spec-row coverage index")
    out.append("")
    out.append(
        "Which `spec/target-spec.md` row is addressed by which committed testbench, "
        "which evidence record it rests on, and the exact command a third party runs "
        "to reproduce it. This answers \"is this row addressed?\" without reading "
        "every directory under `sim/`."
    )
    out.append("")
    out.append(
        "Generated from `sim/spec-coverage.json` and enforced by "
        "`sim/check_spec_coverage.py` (T1 item 9: testbench completeness, cold-start "
        "invocation, pinned PDK revision). A claimed spec row with no bench fails the "
        "check; so does a stale copy of this file."
    )
    out.append("")

    out.append("## Cold start")
    out.append("")
    out.append(
        "One-time machine bootstrap: `docs/environment-setup.md` sections 1-3. Then, "
        "from the repo root:"
    )
    out.append("")
    out.append("```sh")
    for line in index.get("cold_start_preamble", []):
        out.append(line)
    out.append("```")
    out.append("")
    out.append(
        "followed by the per-bench command in the table below. Each of those commands "
        "is checked to appear verbatim in the file named under \"documented in\", to "
        "use only flags its runner actually accepts, and to name the same script the "
        "record's own `Written by` footer names."
    )
    out.append("")

    out.append("## Coverage summary")
    out.append("")
    out.append("| Spec row | Status | Coverage | Testbench(es) | Evidence record(s) |")
    out.append("|---|---|---|---|---|")
    for row in index.get("rows", []):
        param = row.get("parameter", "")
        status = row.get("status", "")
        klass = row.get("claim_class", "")
        coverage = COVERAGE_LABEL.get(klass, klass)
        benches = row.get("benches", [])
        if benches:
            bench_cell = "<br>".join(f"`sim/{b.get('experiment')}`" for b in benches)
            record_cell = "<br>".join(
                f"`{Path(rec).name}`" for b in benches for rec in b.get("records", [])
            )
        else:
            bench_cell = "—"
            record_cell = "—"
        out.append(f"| {param} | {status} | {coverage} | {bench_cell} | {record_cell} |")
    out.append("")

    out.append("## Per-row detail")
    out.append("")
    for row in index.get("rows", []):
        param = row.get("parameter", "")
        out.append(f"### {param}")
        out.append("")
        out.append(f"- **Status**: {row.get('status', '')}")
        out.append(f"- **Claim class**: `{row.get('claim_class', '')}`")
        if row.get("note"):
            out.append(f"- **Note**: {row['note']}")
        if row.get("reason"):
            out.append(f"- **Why no bench**: {row['reason']}")
        if row.get("tracking"):
            out.append(f"- **Tracking**: {row['tracking']}")
        out.append("")
        for bench in row.get("benches", []):
            out.append(f"**`sim/{bench.get('experiment')}`** — {bench.get('covers', '')}")
            out.append("")
            decks = bench.get("testbench", [])
            if decks:
                out.append("- Testbench: " + ", ".join(f"`{d}`" for d in decks))
            if bench.get("testbench_note"):
                out.append(f"- Deck note: {bench['testbench_note']}")
            out.append(f"- Runner: `{bench.get('runner')}`")
            out.append(f"- Cold start: `{bench.get('cold_start')}`")
            out.append(f"- Documented in: `{bench.get('documented_in')}`")
            for rec in bench.get("records", []):
                out.append(f"- Evidence: `{rec}`")
            out.append("")
    out.append("## Harness proofs (never counted toward a spec row)")
    out.append("")
    out.append(
        "`sim/README.md` states these two experiments \"will never substantiate a "
        "spec row\". The check enforces it: each one's `tb.json` claim must start "
        "with `None`, and listing either as a bench for any row is a failure."
    )
    out.append("")
    for proof in index.get("harness_proofs", []):
        out.append(f"- **`sim/{proof.get('experiment')}`** — {proof.get('why', '')}")
    out.append("")
    out.append("## Pinning")
    out.append("")
    note = index.get("pins", {}).get("note", [])
    out.append(" ".join(note) if isinstance(note, list) else str(note))
    out.append("")
    out.append(
        f"- PDK pin: `{index.get('pins', {}).get('pdk_json')}`\n"
        f"- Toolchain pin: `{index.get('pins', {}).get('toolchain_json')}`\n"
        f"- Cold-start bootstrap: `{index.get('pins', {}).get('cold_start_doc')}`"
    )
    out.append("")
    return _bullets(out)


# ----------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--render", action="store_true", help=f"regenerate {DOC_REL}")
    ap.add_argument("--print", dest="print_only", action="store_true", help="print the rendering")
    ap.add_argument("--root", default=str(REPO_ROOT), help="repo root (default: this checkout)")
    args = ap.parse_args(argv)

    root = Path(args.root)
    checker = CoverageCheck(root)

    if args.render or args.print_only:
        raw = (root / INDEX_REL).read_text(encoding="utf-8")
        rendered = render_markdown(json.loads(raw))
        if args.print_only:
            sys.stdout.write(rendered)
            return 0
        (root / DOC_REL).write_text(rendered, encoding="utf-8")
        print(f"wrote {DOC_REL}")
        return 0

    failures = checker.run()
    if failures:
        print(f"FAIL: spec-row coverage check ({len(failures)} problem(s))", file=sys.stderr)
        for failure in failures:
            print(f"  {failure.render()}", file=sys.stderr)
        print(
            "\nSee sim/spec-coverage.md and sim/check_spec_coverage.py's module "
            "docstring for what each check enforces.",
            file=sys.stderr,
        )
        return 1

    rows = checker.index.get("rows", [])
    benched = [r for r in rows if r.get("benches")]
    n_benches = sum(len(r.get("benches", [])) for r in rows)
    n_records = sum(
        len(b.get("records", [])) for r in rows for b in r.get("benches", [])
    )
    print(
        f"OK: {len(rows)} spec rows indexed, {len(benched)} benched "
        f"({n_benches} bench entries, {n_records} evidence records), "
        f"{len(rows) - len(benched)} deliberately unbenched (all DRAFT); "
        f"{len(checker.index.get('harness_proofs', []))} harness proofs excluded."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

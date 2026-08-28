#!/usr/bin/env python3
"""Aggregated characterization report generator (issue #30, T1 item 8).

Ties every `spec/target-spec.md` "Target table" row (RATIFIED or DRAFT --
including rows that fail or are unmeasured) to the specific `sim/*/records/
*.md` evidence record(s) its verdict rests on, per
`klayout-tools/docs/design-evidence-tiers.md` item 8.

    python3 sim/report/generate.py            # print the report to stdout
    python3 sim/report/generate.py --write     # (re)write docs/characterization-report.md
    python3 sim/report/generate.py --check     # freshness + drift check (CI), no write

## Why this counts as "generating from the records", not hand-maintaining

`sim/report/manifest.py` names which record(s) substantiate each row (an
editorial decision -- the report generator cannot know *which* record answers
a spec row without a human/agent reading the record's `Claim` field and
deciding). What this module does NOT let a human hand-transcribe is the
record's own content: every citation's `Record ID`, `Overall` (or
`Statistical convention`, when `Overall` is absent), and `Supersedes` fields
are *extracted* from the record file at generation time via
`extract_field()`, not copied by hand. A stale or mistyped transcription is
therefore impossible by construction -- the report always says what the cited
record file itself currently says.

## Mechanical freshness (the acceptance criterion this exists to satisfy)

Per `sim/README.md`, a record's own `Supersedes` field is the *only* place
the append-only convention encodes "this replaces an earlier result for the
same claim". `check_freshness()` therefore does the mechanical check the
other direction: for every `sim/*/records/*.md` file cited by
`manifest.ROWS`, it scans every *other* record in that same experiment's
`records/` directory for a `Supersedes` field naming the cited record's ID.
If one is found, the citation is stale -- the report is citing a record a
newer one has explicitly superseded, and `--check` (and `main()`'s default
"write" path) exits non-zero rather than rendering a stale claim silently.

Layout citations (`manifest.Row.layout_citations`) are pinned paths, not
resolved against a supersession scheme -- `layout/` has none (see
`manifest.BLIND_SPOTS`, which says so explicitly rather than pretending
otherwise).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REPORT_PATH = REPO_ROOT / "docs" / "characterization-report.md"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # sim/ on path
from report import manifest  # noqa: E402  (path setup must precede this import)


def extract_field(text: str, field_name: str) -> str | None:
    """Pull a `- **<field_name>**: <value>` line's value out of a record's
    markdown text (sim/README.md's "Base fields" convention). Returns None
    if the field is absent -- callers decide whether that's fatal."""
    pattern = r"^-\s*\*\*" + re.escape(field_name) + r"\*\*:\s*(.+)$"
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(1).strip() if m else None


def truncate(text: str, limit: int = 220) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


class Citation:
    """A resolved, field-extracted view of one cited evidence record."""

    def __init__(self, rel_path: str, kind: str):
        self.rel_path = rel_path
        self.kind = kind
        self.abs_path = REPO_ROOT / rel_path
        if not self.abs_path.is_file():
            raise FileNotFoundError(
                f"citation {rel_path!r} in sim/report/manifest.py does not exist "
                "-- fix the manifest (typo, or the record path moved)."
            )
        self.text = self.abs_path.read_text()
        self.record_id = extract_field(self.text, "Record ID") or self.abs_path.stem
        self.overall = extract_field(self.text, "Overall")
        self.corner_matrix = extract_field(self.text, "Corner matrix run")
        self.statistical_convention = extract_field(self.text, "Statistical convention")
        # sim/README.md's "Characterization-record variant": records that report
        # measured values under stated conditions replace Overall/Result with
        # this field instead.
        self.measured_values = extract_field(self.text, "Measured value(s)")
        self.claim = extract_field(self.text, "Claim")
        self.supersedes = extract_field(self.text, "Supersedes")


def find_superseding_sibling(record_path: Path) -> Path | None:
    """If some OTHER `*.md` file in `record_path`'s own directory names it
    via that other record's own `Supersedes` field, return that sibling's
    path. Otherwise None. This is sim/'s append-only convention
    (sim/README.md "Supersedes") read in the direction a citation needs:
    "has anything superseded the specific record I'm citing?" Pure
    filesystem + regex, independent of sim/report/manifest.py, so it is
    directly unit-testable against a synthetic directory (see
    sim/tests/test_report.py)."""
    record_id = extract_field(record_path.read_text(), "Record ID") or record_path.stem
    for sibling in sorted(record_path.parent.glob("*.md")):
        if sibling == record_path:
            continue
        sibling_supersedes = extract_field(sibling.read_text(), "Supersedes")
        if sibling_supersedes and record_id in sibling_supersedes:
            return sibling
    return None


def check_freshness(rows: tuple[manifest.Row, ...] = manifest.ROWS) -> list[str]:
    """Return a list of human-readable problems (empty == fresh). A cited
    `sim/*/records/*.md` file is stale if `find_superseding_sibling()` finds
    a newer record in the same `records/` directory that supersedes it."""
    problems: list[str] = []
    for row in rows:
        for rel_path in row.sim_citations:
            abs_path = REPO_ROOT / rel_path
            if not abs_path.is_file():
                problems.append(
                    f"[{row.id}] citation {rel_path!r} in sim/report/manifest.py does not "
                    "exist -- fix the manifest (typo, or the record path moved)."
                )
                continue
            superseder = find_superseding_sibling(abs_path)
            if superseder is not None:
                try:
                    superseder_display = superseder.relative_to(REPO_ROOT)
                except ValueError:
                    superseder_display = superseder
                problems.append(
                    f"[{row.id}] {rel_path} has been superseded by "
                    f"{superseder_display} -- update the citation in sim/report/manifest.py."
                )
        for rel_path in row.layout_citations:
            if not (REPO_ROOT / rel_path).is_file():
                problems.append(
                    f"[{row.id}] layout citation {rel_path!r} in sim/report/manifest.py "
                    "does not exist."
                )
    return problems


def render_row(row: manifest.Row) -> list[str]:
    lines = [f"### {row.spec_row}", "", f"- **Status**: {row.status}", f"- **Conditions**: {row.conditions}", f"- **Verdict**: {row.verdict}"]
    if row.notes:
        lines.append(f"- **Notes**: {row.notes}")
    lines.append("")
    if row.sim_citations or row.layout_citations:
        lines.append("**Evidence:**")
        lines.append("")
    for rel_path in row.sim_citations:
        c = Citation(rel_path, kind="sim")
        detail = (
            c.overall
            or c.statistical_convention
            or (f"Measured value(s): {c.measured_values}" if c.measured_values else None)
            or "(no Overall/Statistical convention/Measured value(s) field found)"
        )
        label = "Overall" if c.overall else "Result"
        lines.append(f"- `{rel_path}` (Record ID `{c.record_id}`, Supersedes: {c.supersedes or '(none)'})")
        lines.append(f"  - {label}: {detail}")
        if c.corner_matrix:
            lines.append(f"  - Corner matrix run: {c.corner_matrix}")
        if c.claim:
            lines.append(f"  - Claim: {truncate(c.claim)}")
    for rel_path in row.layout_citations:
        abs_path = REPO_ROOT / rel_path
        lines.append(f"- `{rel_path}` (layout evidence -- see manifest.BLIND_SPOTS for the caveat on layout freshness)")
        if abs_path.is_file():
            first_line = abs_path.read_text().splitlines()[0].lstrip("# ").strip()
            lines.append(f"  - {first_line}")
    lines.append("")
    return lines


def render_summary_table(rows: tuple[manifest.Row, ...]) -> list[str]:
    lines = [
        "| Spec row | Status | Verdict | Evidence |",
        "|---|---|---|---|",
    ]
    for row in rows:
        n_citations = len(row.sim_citations) + len(row.layout_citations)
        evidence = f"{n_citations} record(s), see detail below" if n_citations else "(none -- see detail below)"
        lines.append(f"| {row.spec_row} | {row.status} | {truncate(row.verdict, 100)} | {evidence} |")
    lines.append("")
    return lines


def render_report() -> str:
    lines: list[str] = []
    lines.append("# sky130-sar-adc — Characterization Report")
    lines.append("")
    lines.append(
        "Aggregated, generated artifact tying every `spec/target-spec.md` "
        "Target-table row's verdict to the specific evidence record(s) it "
        "rests on, per `klayout-tools/docs/design-evidence-tiers.md` item 8 "
        "(T1 item 8, tracked in issue #30, part of #23). Every row appears, "
        "including rows that fail or are unmeasured -- coverage honesty is "
        "part of the claim."
    )
    lines.append("")
    lines.append(
        "**Do not hand-edit this file.** Regenerate it with "
        "`python3 sim/report/generate.py --write` after any `sim/` or "
        "`layout/` evidence changes, and re-run "
        "`python3 sim/report/generate.py --check` (wired into `npm run "
        "check:ci` as `npm run check:report`) before committing -- it fails "
        "if a cited record has been superseded, if a citation path no "
        "longer exists, or if this file has drifted from what the current "
        "records/manifest would regenerate."
    )
    lines.append("")
    lines.append("## Coverage summary")
    lines.append("")
    lines.extend(render_summary_table(manifest.ROWS))
    lines.append("## Per-row detail")
    lines.append("")
    for row in manifest.ROWS:
        lines.extend(render_row(row))
    lines.append("## Post-layout re-sim (T1 item 7)")
    lines.append("")
    lines.append(manifest.POST_LAYOUT_NOTE)
    lines.append("")
    lines.append("## Known blind spots")
    lines.append("")
    lines.append(
        "Enumerated, not omitted: deck coverage gaps, warning-level LVS "
        "findings (and one non-warning LVS mismatch), uncombined evidence "
        "legs, and modelled-but-not-extracted items."
    )
    lines.append("")
    for spot in manifest.BLIND_SPOTS:
        lines.append(f"- {spot}")
    lines.append("")
    lines.append("## No-grant statement")
    lines.append("")
    lines.append(manifest.NO_GRANT_STATEMENT)
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "Generated by `sim/report/generate.py` from `sim/report/manifest.py` "
        "and the evidence records it cites. Append-only evidence convention: "
        "`sim/README.md`. Freshness check: `check_freshness()` in "
        "`sim/report/generate.py`."
    )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write docs/characterization-report.md")
    parser.add_argument(
        "--check",
        action="store_true",
        help="freshness + drift check only (CI mode): exit non-zero without writing",
    )
    args = parser.parse_args(argv)

    problems = check_freshness()
    if problems:
        print("STALE CITATIONS:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    content = render_report()

    if args.check:
        if not REPORT_PATH.is_file():
            print(f"{REPORT_PATH} does not exist -- run --write first.", file=sys.stderr)
            return 1
        committed = REPORT_PATH.read_text()
        if committed != content:
            print(
                f"{REPORT_PATH} is out of date with sim/report/manifest.py and its "
                "cited records. Run `python3 sim/report/generate.py --write` and "
                "commit the result.",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {REPORT_PATH} is fresh and up to date ({len(manifest.ROWS)} rows).")
        return 0

    if args.write:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(content)
        print(f"wrote {REPORT_PATH}")
        return 0

    print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

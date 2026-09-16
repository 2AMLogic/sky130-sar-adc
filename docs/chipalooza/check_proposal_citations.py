#!/usr/bin/env python3
"""Headless citation check for docs/chipalooza/challenge-4-proposal.md.

WHY THIS EXISTS
---------------
The Chipalooza Challenge #4 proposal (issue #121) is a hand-maintained
evidence ledger: every spec-row verdict in its Section 4 cites a dated
`sim/<campaign>/records/<stamp>.md` or `layout/<block>/reports/<stamp>/`
record by path, and many citations additionally assert that the record they
name is the *current* one (i.e. what that flow's `LATEST` pointer file
resolves to). Nothing checked those two claims mechanically, and the
document's own revision history is dominated by after-the-fact corrections
of exactly that class of drift:

  - PR #239 / #276 / #282 — Section 4 rows left citing a superseded
    `layout/sar-adc-top/reports/` record after a newer flow run landed.
  - PR #242 — three superseded layout-record citations corrected at once.
  - PR #295 / #300 — citations naming `reports/LATEST` for a `sim/` campaign,
    whose pointer file is `records/LATEST` (`sim/` campaigns record under
    `records/`; `reports/` is the `layout/` flows' convention), plus
    Section 7 ledes gone stale against the records they cited.

Each of those was found by a human/agent re-reading 2000 lines of prose. This
script turns that re-read into a gate, and is the automated form of issue
#121's own Test Plan line: "every spec-row verdict traces to ... a dated
`sim/`/`layout/` record cited by path -- no row asserted from prose alone."

It is deliberately PDK-free and network-free (pure file reads), like
`sim/check_spec_coverage.py` and `layout/bin/check-klt-pin-evidence.sh`, so it
runs in the always-on headless `checks` CI job rather than the PDK-gated one.

WHAT IT CHECKS
--------------
1. Link resolution -- every relative Markdown link target in the document
   resolves to a path that exists in this repository.

2. Bare path references -- every backticked, whitespace-free reference whose
   first segment is one of this repo's own top-level directories (`sim/`,
   `layout/`, `spec/`, `design/`, `docs/`, `measurements/`, `ratification/`)
   resolves too. Not every evidence citation is a Markdown link: Section 4's
   Power row, for instance, cites its record as a bare backticked path.
   References whose first segment is NOT one of ours (e.g. klayout-tools'
   `src/klayout_tools/lvs.py`) are upstream paths and are left alone.

3. Spec-row freshness -- this is the load-bearing check. In the Section 4
   spec table, each row is one graded verdict, and each row must cite the
   *current* evidence for every flow it draws on: for each `layout/<block>/`
   or `sim/<campaign>/` flow a row cites, at least one of that row's cited
   record stamps must be what the flow's own `LATEST` pointer resolves to.
   A row may additionally cite superseded records (this document's style is
   to keep the supersession trail visible, and that is not a defect) -- what
   it may not do is cite *only* superseded ones, which is exactly the drift
   PR #239, #242, #276 and #282 each had to correct after the fact. Flows
   with no `LATEST` pointer are skipped: there is nothing to be stale
   against.

4. Pointer freshness -- wherever the document says a cited record is the
   "current `reports/LATEST`" / "current `records/LATEST`", the record named
   immediately before that phrase must be the one the pointer file actually
   resolves to.

5. Pointer naming -- a `sim/` campaign's pointer must be claimed as
   `records/LATEST` and a `layout/` flow's as `reports/LATEST`. This is the
   check for PR #295/#300's defect class.

6. Census freshness -- checks 4 and 5 do not cover every pointer claim in the
   document (see below), so the document states, in prose, how many of its
   claims they *do* cover. That census is itself a volatile fact about a
   document several passes a day append to, and it went stale the first time
   it was hand-written: PR #312 added two pointer claims of the skipped kind
   and the "9 of 19" census three files carried (this docstring, the
   proposal's own "Reproducing this table" note, and `.github/workflows/ci.yml`'s
   inventory comment) silently became "9 of 21" without any of the three
   moving. Check 6 recomputes the census and fails if the document's stated
   one disagrees, so the coverage claim cannot drift away from the coverage.
   It fires only on a document that states a census -- absence is not a
   failure here, because `check_document` also runs against test fixtures;
   that the real proposal states one is asserted by
   `sim/tests/test_proposal_citations.py` instead.

7. Spec-row parity -- checks 3 to 6 all verify how a Section 4 row cites its
   evidence; nothing verified that the row is *about the same spec line* the
   ratified spec states. Issue #121's acceptance criterion 2 is "every spec
   row states met/unmet against the brief; no row is relaxed to make it
   pass", and the repo's own standing rule is blunter: "agents do not relax a
   spec line to make a result pass" (CLAUDE.md). Both were hand-verified
   every pass. Check 7 makes them mechanical -- for each row of
   `spec/target-spec.md`'s own Target table:

     a. Coverage -- a Section 4 row with that parameter name exists. A spec
        row silently dropped from the proposal is the cheapest possible way
        to make the table look clean.
     b. No relaxation -- every numeric bound the spec row states (comparator
        and sign included, so `>= 7.5` is not accepted for `> 7.5`, nor
        `<= +-3.0` for `<= +-2.0`) also
        appears in the Section 4 row's Target cell. Section 4 may state
        *more* bounds than the spec row -- it routinely carries the
        superseded bound a decision record revised, e.g. "was `> 9.0`/`9.5`"
        -- but it may never drop or re-number one. This is the load-bearing
        direction: a relaxation is precisely a bound that changed on one side
        only.
     c. Status parity -- the leading status word (`RATIFIED` / `DRAFT`)
        agrees. This is what makes DR-007's eventual ratification a CI
        failure rather than a silent staleness: the moment `spec/` grades
        ENOB/INL-DNL as RATIFIED, Section 4's "DRAFT (target value, not
        ratified)" rows fail until they are re-graded from informational to a
        verdict -- exactly the edge case issue #121's own Test Plan names.

   Skipped when `spec/target-spec.md` has no Target table (test fixtures);
   that the real one is found and non-empty is asserted by the tests.

8. Verdict vocabulary -- acceptance criterion 2's other half, "every spec row
   *states* met/unmet". Section 4's preamble defines the verdict kinds the
   table uses, and each row's verdict cell must open with one of them. Both
   directions are enforced, so neither list can drift from the other: a row
   opening with an undefined kind fails, and a defined kind no row uses fails
   too. The preamble had already drifted when this check landed -- it
   announced "three cases", listed four bullets, and the table used six
   distinct kinds, of which one bullet (`DRAFT / not ratified`) was really a
   *Status* value rather than a verdict. Skipped on a document whose Section
   4 defines no kinds (test fixtures), like check 6.

Checks 4 and 5 fire only on an *attached* claim: the phrase must follow the
cited path with nothing between them but link/quote punctuation and an
optional "the"/"record:" connector. A claim that merely *discusses* a pointer
in prose ("... left Section 4's Area row still citing the superseded
`20260906-101939-1250ff4/compose.json` -- that citation is now corrected to
the current `reports/LATEST`") is not a citation of the preceding path and is
skipped, by design: over-eager matching there would make the gate unusable on
a document whose whole style is to narrate its own corrections.

The connector test is directional, so a *stamp-after-claim* citation -- one
that names its record only after the phrase ("re-pointed onto the current
`reports/LATEST`, `20260915-213439-bf2256f`"), or as a bare stamp rather than
a full path -- is unattached too, and is likewise skipped. Those are genuine
forward citations that this check does NOT cover -- do not describe check 4
as verifying every pointer claim in the document; run `--stats` for the live
breakdown rather than quoting a number from here.

Extending checks 4/5 *to* the stamp-after-claim form is not the obvious win
it looks like, and is recorded here so it is not re-proposed blind: in this
document the trailing stamp is often a **dated historical** statement ("Re-cited
again 2026-09-15 (later) onto the current `reports/LATEST`,
`20260915-213439-bf2256f`") that was true when written and is superseded by a
later paragraph in the same item, or a *contrast* with the superseded record
rather than a citation of the current one. Evaluating either as a present-tense
claim would fail the gate on prose that is correct, and the fix would be to
rewrite the document's supersession trail -- the opposite of what this gate is
for. The verdicts those paragraphs support are already held to current evidence
as Section 4 *rows*, by check 3. What check 6 adds instead is that the *size* of
the uncovered set cannot drift silently.

Check 3 is scoped to the spec table rather than the whole document for the
same reason: Section 7's prose deliberately narrates superseded records
paragraph by paragraph, whereas a Section 4 row is a verdict that must stand
on current evidence -- which is also how issue #121's own acceptance criteria
and Test Plan frame it ("every spec-row verdict ... traces to ... a dated
`sim/`/`layout/` record cited by path").

USAGE
-----
    python3 docs/chipalooza/check_proposal_citations.py [--stats] [DOC ...]

With no arguments it checks every `docs/chipalooza/*.md`. `--stats` prints each
document's live pointer-claim census (the numbers check 6 compares against)
instead of checking, which is what to run when check 6 reports a drift.
Exit status:

    0 - every citation checks out
    1 - one or more citations are stale/broken (each one listed on stdout)
    2 - usage error (a named document does not exist)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHIPALOOZA_DIR = REPO_ROOT / "docs" / "chipalooza"

# Top-level directories whose paths this repo owns, and can therefore resolve.
# A reference whose first segment is not one of these belongs to some other
# project (e.g. klayout-tools' own `src/`) and is not checked.
OWN_TOP_LEVEL = frozenset(
    ("sim", "layout", "spec", "design", "docs", "measurements", "ratification")
)

# `sim/` campaigns keep their append-only evidence under `records/`; the
# `layout/` flows keep theirs under `reports/`. The pointer file in each is
# named LATEST, so the *phrase* a citation uses is the tell for which
# convention the author had in mind -- and mixing them up is a real, recurring
# defect in this document (PR #295/#300).
POINTER_DIR_BY_TOP_LEVEL = {"sim": "records", "layout": "reports"}

# Characters that mark a backticked reference as a pattern/placeholder rather
# than a concrete path.
GLOB_CHARS = "*?<>[]{}"

# `](target)`, target not a URL and not an in-page anchor.
MD_LINK_RE = re.compile(r"\]\((?!https?://)(?!#)([^)\s]+)\)")

# A backticked span. Spans may wrap across lines in this document's prose.
BACKTICK_SPAN_RE = re.compile(r"`([^`]*)`")

# "current `reports/LATEST`" / "current `records/LATEST`", possibly wrapped.
POINTER_CLAIM_RE = re.compile(r"current\s+`(reports|records)/LATEST`")

# An evidence-record path: `layout/<block>/reports/<stamp>/<file>` or
# `sim/<campaign>/records/<stamp>.md`. <stamp> is this repo's
# `YYYYMMDD-HHMMSS-<sha>` record-naming convention. The trailing artefact name
# is part of the match on purpose: the attached-claim test below measures what
# sits between the END of a citation and the claim, and a `/record.md` left
# unconsumed would make every link-form citation look unattached.
STAMP = r"\d{8}-\d{6}-[0-9a-f]+"
EVIDENCE_PATH_RE = re.compile(
    r"(?P<top>sim|layout)/(?P<block>[A-Za-z0-9._-]+)/"
    r"(?P<pointer_dir>records|reports)/(?P<stamp>" + STAMP + r")"
    r"(?:\.md)?(?:/[A-Za-z0-9._-]+)?"
)

# A record stamp on its own, for the census's trailing-stamp classification: a
# skipped claim that names *some* record after the phrase is a different (and
# potentially checkable) shape from one that names none at all.
STAMP_RE = re.compile(STAMP)

# How far after a skipped pointer claim the census looks for a record stamp.
# Same order as the 400-character window check 4 scans *before* a claim, and
# deliberately on a plateau: the classification of this document is identical
# at 200 and at 300 characters, and only shifts by one claim at 120, so the
# census does not balance on the exact constant.
TRAILING_STAMP_WINDOW = 200

# The census sentence the document states about itself, matched against
# whitespace-collapsed text so a prose line wrap cannot break it. Every number
# check 6 compares is a named group here; the window is included so a document
# cannot state a coverage rule this script does not actually apply.
CENSUS_RE = re.compile(
    r"of the \*\*(?P<total>\d+)\*\* [\"“]current `…/LATEST`[\"”] "
    r"phrases in this document, \*\*(?P<attached>\d+)\*\* are attached and "
    r"therefore checked; of the \*\*(?P<skipped>\d+)\*\* skipped, "
    r"\*\*(?P<trailing_stamp>\d+)\*\* name a record stamp within "
    r"(?P<window>\d+) characters after the phrase, and "
    r"\*\*(?P<narration>\d+)\*\* name none at all"
)

# What may sit between a cited path and an attached pointer claim: link and
# quote punctuation, whitespace, and an optional "the" / "record:" connector.
# Every quantifier here must tolerate the connector ENDING at that token:
# `_unwrap_backticked` strips the text before this match, so a `the\s+` (one or
# more trailing spaces) branch can never fire -- `") (the "` arrives as
# `") (the"`. That made check 4 silently vacuous for `(the current
# \`reports/LATEST\`)`, which is the phrasing Section 4 actually uses.
CONNECTOR_RE = re.compile(r"^[\s`)\](,;]*(?:record:\s*)?(?:the\s*)?$")

# The ratified spec this document's Section 4 restates, and the heading of the
# one Markdown table in it that carries the spec rows.
SPEC_DOC = Path("spec") / "target-spec.md"
SPEC_TABLE_HEADING = "## Target table"

# A Markdown table cell boundary. Section 4's INL/DNL row writes `max\|DNL\|`,
# so an unescaped-pipe split is the only one that keeps its cells aligned.
CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")

# A numeric bound as these tables state them: an optional comparator, an
# optional sign, and the number. Compared with whitespace removed, so `≤ ±2.0`
# and `≤±2.0` are the same bound -- but `> 7.5` and `≥ 7.5` are not, which is
# the point.
BOUND_RE = re.compile(r"(?:[<>≤≥]\s*)?(?:±\s*)?\d+(?:\.\d+)?")

# Digits that are references rather than bounds: decision records, issue
# numbers, section numbers, and PDK names.
NON_BOUND_RE = re.compile(r"DR-\d+|#\d+|§\d+|\b(?:sky|gf)\d+\b")

# `- **MET** — spec row is ratified and ...`: one verdict kind, as Section 4's
# own preamble defines it.
VERDICT_DEFINITION_RE = re.compile(r"^- \*\*([^*]+?)\*\*\s+[—-]", re.M)


def _unwrap_backticked(span: str) -> str:
    """Rejoin a backticked span that prose wrapped across lines.

    A path wrapped after `/` or `-` rejoins with no separator (the wrap point
    is inside a single token); anything else rejoins with one space, which
    leaves the result non-path-shaped so it is skipped rather than guessed at.
    """
    span = re.sub(r"(?<=[/-])\n\s*", "", span)
    return re.sub(r"\s*\n\s*", " ", span).strip()


def _resolve(doc: Path, reference: str) -> Path:
    """Resolve a reference as written in `doc` to a filesystem path."""
    target = reference.split("#", 1)[0].split("?", 1)[0]
    if target.startswith("/"):
        return REPO_ROOT / target.lstrip("/")
    return (doc.parent / target).resolve()


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def check_links(doc: Path, text: str) -> list[str]:
    """Check 1: every relative Markdown link target exists."""
    misses = []
    for match in MD_LINK_RE.finditer(text):
        reference = match.group(1)
        if not _resolve(doc, reference).exists():
            misses.append(
                f"{doc.name}:{_line_of(text, match.start())}: broken link target "
                f"`{reference}` does not exist in this repository"
            )
    return misses


def check_bare_paths(doc: Path, text: str) -> list[str]:
    """Check 2: every backticked path into this repo's own trees exists."""
    misses = []
    for match in BACKTICK_SPAN_RE.finditer(text):
        span = _unwrap_backticked(match.group(1))
        if not span or re.search(r"\s", span) or "/" not in span:
            continue
        if span.split("/", 1)[0] not in OWN_TOP_LEVEL:
            continue
        # A glob/placeholder is a pattern the prose is talking *about* (e.g.
        # "every `layout/*/reports/LATEST` pointer"), not a path it cites.
        if any(ch in span for ch in GLOB_CHARS) or "..." in span:
            continue
        if not _resolve(doc, "../../" + span).exists():
            misses.append(
                f"{doc.name}:{_line_of(text, match.start())}: cited path "
                f"`{span}` does not exist in this repository"
            )
    return misses


def _read_pointer(top: str, block: str, pointer_dir: str) -> str | None:
    pointer = REPO_ROOT / top / block / pointer_dir / "LATEST"
    if not pointer.is_file():
        return None
    return pointer.read_text().strip()


def _pointer_stamp(top: str, block: str) -> str | None:
    """The record stamp `<top>/<block>/`'s LATEST pointer resolves to."""
    value = _read_pointer(top, block, POINTER_DIR_BY_TOP_LEVEL[top])
    if value is None:
        return None
    # `layout/` pointers name a report directory, `sim/` pointers a record file.
    return value.split("/")[0].removesuffix(".md")


def spec_table_rows(text: str) -> list[tuple[int, str]]:
    """The `(line_number, row_text)` pairs of the Section 4 spec table.

    Section 4 is delimited by its own `## 4.` heading and the next `## `
    heading. Within it, the spec table is the Markdown table whose rows start
    with `|`; the header and the `|---|` separator are not verdict rows.
    """
    lines = text.split("\n")
    in_section = False
    rows = []
    for index, line in enumerate(lines, start=1):
        if line.startswith("## "):
            in_section = line.startswith("## 4.")
            continue
        if not in_section or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells or all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
            continue
        if cells[0] == "Parameter":
            continue
        rows.append((index, line))
    return rows


def check_spec_table_freshness(doc: Path, text: str) -> list[str]:
    """Check 3: every Section 4 verdict row cites current evidence."""
    misses = []
    for line_number, row in spec_table_rows(text):
        cited_stamps: dict[tuple[str, str], set[str]] = {}
        for cite in EVIDENCE_PATH_RE.finditer(row):
            flow = (cite.group("top"), cite.group("block"))
            cited_stamps.setdefault(flow, set()).add(cite.group("stamp"))
        parameter = row.strip("|").split("|")[0].strip().replace("**", "")
        for (top, block), stamps in sorted(cited_stamps.items()):
            current = _pointer_stamp(top, block)
            if current is None or current in stamps:
                continue
            misses.append(
                f"{doc.name}:{line_number}: spec row \"{parameter}\" cites "
                f"`{top}/{block}/` only at superseded record(s) "
                f"{', '.join('`' + s + '`' for s in sorted(stamps))} -- that "
                f"flow's current "
                f"{POINTER_DIR_BY_TOP_LEVEL[top]}/LATEST is `{current}`"
            )
    return misses


def attached_pointer_claims(text: str) -> list[tuple[re.Match, re.Match, str]]:
    """The `(claim, cited_path, connector)` triples checks 4 and 5 evaluate.

    Exposed separately from `check_pointer_claims` so both the *count* of
    evaluated claims and the connector each one matched on are testable: the
    failure mode this checker had was not a wrong verdict but no verdict at
    all -- a connector branch that could never match, leaving check 4
    silently vacuous for a phrasing the document really uses. `cited` is a
    match against the 400-character window before the claim, not against
    `text`, so the connector is returned rather than left to be recomputed
    from mismatched offsets.
    """
    triples = []
    for claim in POINTER_CLAIM_RE.finditer(text):
        preceding = text[max(0, claim.start() - 400) : claim.start()]
        cited = None
        for cite in EVIDENCE_PATH_RE.finditer(preceding):
            cited = cite
        if cited is None:
            continue
        # Only an *attached* claim cites the path before it (see module
        # docstring). The connector is unwrapped first so a claim the prose
        # broke across a line still reads as attached.
        connector = _unwrap_backticked(preceding[cited.end() :])
        if not CONNECTOR_RE.match(connector):
            continue
        triples.append((claim, cited, connector))
    return triples


def check_pointer_claims(doc: Path, text: str) -> list[str]:
    """Checks 4 and 5: an attached "current LATEST" claim must be true."""
    misses = []
    for claim, cited, _connector in attached_pointer_claims(text):
        claimed_dir = claim.group(1)
        line = _line_of(text, claim.start())
        top, block = cited.group("top"), cited.group("block")
        expected_dir = POINTER_DIR_BY_TOP_LEVEL[top]
        if claimed_dir != expected_dir:
            misses.append(
                f"{doc.name}:{line}: citation of `{top}/{block}/` claims "
                f"`{claimed_dir}/LATEST`, but a `{top}/` flow's pointer file is "
                f"`{expected_dir}/LATEST`"
            )
            continue

        current = _pointer_stamp(top, block)
        if current is None:
            misses.append(
                f"{doc.name}:{line}: citation claims the current "
                f"`{expected_dir}/LATEST` of `{top}/{block}/`, but no such "
                f"pointer file exists"
            )
            continue

        stamp = cited.group("stamp")
        if current != stamp:
            misses.append(
                f"{doc.name}:{line}: citation names `{stamp}` as the current "
                f"`{expected_dir}/LATEST` of `{top}/{block}/`, but that pointer "
                f"resolves to `{current}`"
            )
    return misses


def pointer_claim_census(text: str) -> dict[str, int]:
    """How many "current `…/LATEST`" claims checks 4 and 5 actually evaluate.

    Four counts plus the window constant, keyed by the names `CENSUS_RE`
    captures. `attached` is the checked set; the rest are skipped, split by
    whether a record stamp appears within `TRAILING_STAMP_WINDOW` characters
    *after* the phrase (`trailing_stamp` -- the forward-citation form) or not
    (`narration` -- prose about a correction, naming no record the claim could
    be checked against).
    """
    claims = list(POINTER_CLAIM_RE.finditer(text))
    attached = {claim.start() for claim, _cited, _connector in attached_pointer_claims(text)}
    trailing = 0
    for claim in claims:
        if claim.start() in attached:
            continue
        window = text[claim.end() : claim.end() + TRAILING_STAMP_WINDOW]
        if STAMP_RE.search(_unwrap_backticked(window)):
            trailing += 1
    skipped = len(claims) - len(attached)
    return {
        "total": len(claims),
        "attached": len(attached),
        "skipped": skipped,
        "trailing_stamp": trailing,
        "narration": skipped - trailing,
        "window": TRAILING_STAMP_WINDOW,
    }


def check_census(doc: Path, text: str) -> list[str]:
    """Check 6: the document's stated coverage census must be the real one."""
    stated = CENSUS_RE.search(re.sub(r"\s+", " ", text))
    if stated is None:
        return []
    anchor = re.search(r"phrases in this\s+document", text)
    line = _line_of(text, anchor.start()) if anchor else 1
    actual = pointer_claim_census(text)
    misses = []
    for field, value in sorted(actual.items()):
        if int(stated.group(field)) != value:
            misses.append(
                f"{doc.name}:{line}: the stated pointer-claim census says "
                f"{field}={stated.group(field)}, but this document's live census "
                f"is {field}={value} -- restate it from `python3 "
                f"docs/chipalooza/check_proposal_citations.py --stats`"
            )
    return misses


def _row_cells(line: str) -> list[str]:
    """The cells of one Markdown table row, honouring escaped pipes."""
    return [cell.strip() for cell in CELL_SPLIT_RE.split(line.strip().strip("|"))]


def _normalise_parameter(cell: str) -> str:
    """A parameter name as the two tables can be compared on it."""
    return re.sub(r"\s+", " ", cell.replace("**", "").replace("`", "")).strip()


def _bounds(cell: str) -> set[str]:
    """Every numeric bound stated in a Target cell, comparator included."""
    cleaned = NON_BOUND_RE.sub(" ", cell)
    return {re.sub(r"\s+", "", m.group(0)) for m in BOUND_RE.finditer(cleaned)}


def _status_kind(cell: str) -> str | None:
    """The leading word of a Status cell -- `RATIFIED` or `DRAFT` here."""
    match = re.match(r"[A-Za-z]+", cell.replace("**", "").strip())
    return match.group(0).upper() if match else None


def section_4_table(text: str) -> tuple[list[str], list[tuple[int, list[str]]]]:
    """Section 4's spec table as `(header_cells, [(line_number, cells)])`."""
    header: list[str] = []
    rows = [(line_number, _row_cells(line)) for line_number, line in spec_table_rows(text)]
    in_section = False
    for line in text.split("\n"):
        if line.startswith("## "):
            if header:
                break
            in_section = line.startswith("## 4.")
            continue
        if in_section and line.startswith("|") and _row_cells(line)[:1] == ["Parameter"]:
            header = _row_cells(line)
    return header, rows


def spec_target_rows() -> list[list[str]]:
    """The rows of `spec/target-spec.md`'s own Target table.

    Empty when that table is absent, which is how check 7 stays inert against
    the test fixtures (their REPO_ROOT has no `spec/` tree at all).
    """
    path = REPO_ROOT / SPEC_DOC
    if not path.is_file():
        return []
    rows: list[list[str]] = []
    in_table = False
    for line in path.read_text().split("\n"):
        if line.startswith("## "):
            in_table = line.strip() == SPEC_TABLE_HEADING
            continue
        if not in_table or not line.startswith("|"):
            continue
        cells = _row_cells(line)
        if cells[:1] == ["Parameter"]:
            continue
        if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows


def check_spec_row_parity(doc: Path, text: str) -> list[str]:
    """Check 7: Section 4 restates every ratified spec row, unrelaxed."""
    spec_rows = spec_target_rows()
    if not spec_rows:
        return []
    header, rows = section_4_table(text)
    if not rows:
        return []
    proposal = {
        _normalise_parameter(cells[0]): (line_number, cells)
        for line_number, cells in rows
        if len(cells) >= 3
    }
    misses = []
    for spec_cells in spec_rows:
        parameter = _normalise_parameter(spec_cells[0])
        found = proposal.get(parameter)
        if found is None:
            misses.append(
                f"{doc.name}: spec row \"{parameter}\" of `{SPEC_DOC}` has no "
                f"Section 4 row -- every ratified spec row must state a verdict "
                f"here (issue #121 acceptance criterion 2)"
            )
            continue
        line_number, cells = found
        dropped = _bounds(spec_cells[1]) - _bounds(cells[1])
        if dropped:
            misses.append(
                f"{doc.name}:{line_number}: spec row \"{parameter}\" states "
                f"bound(s) {', '.join('`' + b + '`' for b in sorted(dropped))} in "
                f"`{SPEC_DOC}` that this row's Target cell does not -- a spec "
                f"line may not be relaxed or re-numbered to make a verdict pass"
            )
        spec_status = _status_kind(spec_cells[2])
        row_status = _status_kind(cells[2])
        if spec_status != row_status:
            misses.append(
                f"{doc.name}:{line_number}: spec row \"{parameter}\" is "
                f"`{spec_status}` in `{SPEC_DOC}` but `{row_status}` here -- "
                f"re-grade this row against the spec's current status"
            )
    if header and not any(cell.startswith("Verdict") for cell in header):
        misses.append(
            f"{doc.name}: Section 4's table has no Verdict column "
            f"(header: {header}) -- checks 7 and 8 grade that column"
        )
    return misses


def verdict_vocabulary(text: str) -> list[str]:
    """The verdict kinds Section 4's preamble defines, longest name first.

    Scoped to the prose between the Section 4 heading and its table, which is
    where the definition list lives; the bullets later in the section (under
    "Reproducing this table") do not open with a bolded term, so they are not
    mistaken for definitions.
    """
    start = re.search(r"^## 4\..*$", text, re.M)
    if start is None:
        return []
    table = re.search(r"^\|", text[start.end() :], re.M)
    preamble = text[start.end() : start.end() + table.start()] if table else ""
    kinds = [match.group(1).strip() for match in VERDICT_DEFINITION_RE.finditer(preamble)]
    return sorted(set(kinds), key=len, reverse=True)


def _leading_verdict(cell: str, vocabulary: list[str]) -> str | None:
    opening = cell.lstrip("*").lstrip()
    for kind in vocabulary:
        if opening.upper().startswith(kind.upper()):
            return kind
    return None


def check_verdict_vocabulary(doc: Path, text: str) -> list[str]:
    """Check 8: every Section 4 row opens with a defined verdict kind."""
    vocabulary = verdict_vocabulary(text)
    if not vocabulary:
        return []
    header, rows = section_4_table(text)
    try:
        column = next(i for i, cell in enumerate(header) if cell.startswith("Verdict"))
    except StopIteration:
        return []
    misses = []
    used = set()
    for line_number, cells in rows:
        if len(cells) <= column:
            continue
        parameter = _normalise_parameter(cells[0])
        kind = _leading_verdict(cells[column], vocabulary)
        if kind is None:
            misses.append(
                f"{doc.name}:{line_number}: row \"{parameter}\" opens its verdict "
                f"with \"{cells[column][:40]}...\", which is not one of the kinds "
                f"Section 4 defines ({', '.join(sorted(vocabulary))}) -- every row "
                f"must state met/unmet in the document's own vocabulary"
            )
            continue
        used.add(kind)
    for kind in sorted(set(vocabulary) - used):
        misses.append(
            f"{doc.name}: Section 4 defines the verdict kind \"{kind}\" that no "
            f"row uses -- delete the definition or grade a row with it"
        )
    return misses


def check_document(doc: Path) -> list[str]:
    text = doc.read_text()
    return (
        check_links(doc, text)
        + check_bare_paths(doc, text)
        + check_spec_table_freshness(doc, text)
        + check_pointer_claims(doc, text)
        + check_census(doc, text)
        + check_spec_row_parity(doc, text)
        + check_verdict_vocabulary(doc, text)
    )


def main(argv: list[str]) -> int:
    stats_only = "--stats" in argv
    argv = [arg for arg in argv if arg != "--stats"]
    if argv:
        docs = [Path(arg) if Path(arg).is_absolute() else REPO_ROOT / arg for arg in argv]
        for doc in docs:
            if not doc.is_file():
                print(f"ERROR: document not found: {doc}", file=sys.stderr)
                return 2
    else:
        docs = sorted(CHIPALOOZA_DIR.glob("*.md"))
        if not docs:
            print(f"ERROR: no documents found under {CHIPALOOZA_DIR}", file=sys.stderr)
            return 2

    if stats_only:
        for doc in docs:
            census = pointer_claim_census(doc.read_text())
            print(
                f"{doc.name}: of the {census['total']} \"current `…/LATEST`\" "
                f"phrases in this document, {census['attached']} are attached and "
                f"therefore checked; of the {census['skipped']} skipped, "
                f"{census['trailing_stamp']} name a record stamp within "
                f"{census['window']} characters after the phrase, and "
                f"{census['narration']} name none at all"
            )
        return 0

    misses: list[str] = []
    for doc in docs:
        misses.extend(check_document(doc))

    if misses:
        print(f"FAIL: {len(misses)} stale or broken citation(s):")
        for miss in misses:
            print(f"  - {miss}")
        print()
        print(
            "Each citation above names a path or a `LATEST` pointer that does not\n"
            "match this repository's current evidence tree. Re-point the citation\n"
            "at the record that is actually current -- do not delete the check."
        )
        return 1

    names = ", ".join(doc.name for doc in docs)
    print(f"OK: every citation in {names} resolves and names the current record")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

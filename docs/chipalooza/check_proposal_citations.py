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

9. Sign-off-bar readout parity -- checks 3 to 5 gate which record a row
   *cites*; nothing gated the numbers the document quotes *out of* that
   record. That is a real gap on exactly the two rows the brief's sign-off
   bar grades ("Post-layout PVT simulation, full ADC" and "DRC/LVS-clean
   GDS, full ADC, in-repo"), whose verdicts rest on figures hand-copied out
   of `layout/sar-adc-top/`'s `drc.json` / `lvs.json`: the mismatch count,
   the device/net/pin correspondence, the category breakdown. Those figures
   really do move -- this document has already carried 98, then 128, then
   124, then 98 again as the flow was re-run -- and when they move, check 3
   forces the *citation* forward while leaving every quoted number behind it
   untouched.

   So the document states the current readout once, in a fixed sentence
   form, and check 9 recomputes it from the record that flow's
   `reports/LATEST` actually resolves to and compares field by field: DRC
   status and violation count, LVS status, mismatch and error counts, the
   three-way device/net/pin counts, and the full `category_counts` mapping
   (both directions -- a category the document omits and one it invents are
   both reported). `--stats` prints the live sentence for every `layout/`
   flow, so the fix for a check-9 failure is a paste, not a hand
   transcription. Like checks 6 to 8 it is opt-in per document and inert
   when no readout is stated; that the real proposal states one is asserted
   by `sim/tests/test_proposal_citations.py`.

   What it does NOT do, stated rather than glossed: it does not parse the
   numbers out of Section 4's or Section 7's prose. Those sections are full
   of *dated historical* figures ("moved from the pre-bump 98 mismatches to
   128 ... then to 124") that were true when written and are correct as
   written -- the same reason checks 4 and 5 skip the stamp-after-claim form
   (see below). The readout is the document's single present-tense
   statement of those numbers, and it is the one that is gated.

10. I/O table parity -- checks 3 to 9 all grade Section 4. Section 2 carries
    the document's other mechanically checkable claim, and issue #121's
    acceptance criterion 1 states it directly: "I/O mapped to the slot
    budget". That mapping is a hand-maintained restatement of
    `design/sar_adc_top.spice`'s own `.subckt sar_adc_top` port list -- and
    that netlist is regenerated from `design/sar_adc_top.sch`, whose contents
    this repo really does change (DR-004 Amendment A moved the comparator's
    device count; DR-008 and DR-009 changed the CDAC and comparator
    interfaces). A port added, renamed, or dropped at the schematic level
    would leave Section 2 silently describing a block this repo no longer
    builds, with nothing but a re-read to catch it -- the same drift class as
    every other check here, one section up. Check 10 compares:

      a. The quoted port list -- Section 2.3 quotes the `.subckt` line and
         asserts "Nothing is added or dropped ... it is exactly this
         netlist's own external port list". That is now compared port for
         port, in order, rather than taken on the word "exactly".
      b. Coverage, both directions -- every netlist port has a row in the I/O
         table, and every signal the table names is a netlist port. A port
         with no row is the cheapest way to make a slot budget fit.
      c. Per-row counts -- each row's "Count used" cell must equal the number
         of ports its Signal cell names, ranges (`DOUT9..DOUT0`) expanded. A
         row claiming no count (the shared rail) is exempt, since it is not
         charged against any slot.
      d. The Totals sentence -- each bolded per-category total must be the
         sum of the rows the table itself assigns to that category (read off
         the "Assumed Challenge slot" column, never a list in this file), and
         the conditional dedicated-pad total must be the dedicated pads plus
         the harness-supplied reference lines. A row that is charged against
         the budget but matches no category is reported too, so a new row
         cannot slip past the totals by being uncategorised.

    Inert when the netlist or the table is absent (test fixtures); that the
    real ones are found is asserted by `sim/tests/test_proposal_citations.py`.

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
document's live pointer-claim census (the numbers check 6 compares against) and
the live sign-off-bar readout of every `layout/` flow (the sentence check 9
compares against) instead of checking, which is what to run when check 6 or
check 9 reports a drift. Exit status:

    0 - every citation checks out
    1 - one or more citations are stale/broken (each one listed on stdout)
    2 - usage error (a named document does not exist)
"""

from __future__ import annotations

import json
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

# The sign-off-bar readout sentence check 9 gates, matched against
# whitespace-collapsed text so a prose line wrap cannot break it. Every field
# compared against the record's own JSON is a named group. Deliberately free of
# em dashes and other prose punctuation: the sentence is a data statement, and
# every separator in it is one a `--stats` paste reproduces exactly.
READOUT_RE = re.compile(
    r"on the record `(?P<flow>layout/[A-Za-z0-9._-]+)/reports/LATEST` resolves to, "
    r"`klt drc` reports status \*\*(?P<drc_status>[a-z]+)\*\* with "
    r"\*\*(?P<violation_count>\d+)\*\* violations, and `klt lvs` reports status "
    r"\*\*(?P<lvs_status>[a-z]+)\*\* with \*\*(?P<mismatch_count>\d+)\*\* mismatches "
    r"and \*\*(?P<error_count>\d+)\*\* errors; devices "
    r"\*\*(?P<devices_layout>\d+)\*\* layout / \*\*(?P<devices_reference>\d+)\*\* "
    r"reference / \*\*(?P<devices_matched>\d+)\*\* matched; nets "
    r"\*\*(?P<nets_layout>\d+)\*\* / \*\*(?P<nets_reference>\d+)\*\* / "
    r"\*\*(?P<nets_matched>\d+)\*\* matched; pins \*\*(?P<pins_layout>\d+)\*\* / "
    r"\*\*(?P<pins_reference>\d+)\*\* / \*\*(?P<pins_matched>\d+)\*\* matched; "
    r"(?:by category (?P<categories>(?:`[A-Za-z][A-Za-z0-9._]*: \d+`(?:, )?)+)"
    r"|(?P<no_categories>no mismatch categories))\."
)

# One `name: count` pair inside the readout's category clause. Category names
# carry dots (`device.unmatched`), so the clause cannot be delimited on the
# sentence's own full stop -- each pair is backticked instead, which makes the
# clause self-delimiting however many categories a record reports.
READOUT_CATEGORY_RE = re.compile(r"`(?P<name>[A-Za-z][A-Za-z0-9._]*): (?P<count>\d+)`")

# The regenerated top-level netlist Section 2's I/O table is a categorisation
# of. xschem emits the *top* cell's own `.subckt` line commented out (the top
# level is netlisted flat), so the leading asterisks are part of the line as
# committed -- tolerating them is not leniency, it is the file's real shape.
TOP_NETLIST = Path("design") / "sar_adc_top.spice"
SUBCKT_RE = re.compile(r"^\*{0,2}\.subckt\s+sar_adc_top\s+(?P<ports>.+)$", re.M)

# The Markdown table Section 2 maps that port list onto the slot budget with,
# identified by its own first header cell.
IO_TABLE_HEADER = "Signal"

# A fenced code block, which is how Section 2.3 quotes the netlist's port list.
FENCED_BLOCK_RE = re.compile(r"^```[^\n]*\n(?P<body>.*?)^```", re.M | re.S)

# `DOUT9..DOUT0` (the I/O table's Signal cell) or `DOUT9..0` (the prose form) --
# a contiguous port range, written descending or ascending.
PORT_RANGE_RE = re.compile(
    r"^(?P<prefix>[A-Za-z_]+)(?P<high>\d+)\.\.(?P=prefix)?(?P<low>\d+)$"
)

# A bare port name, as both the netlist and the table's backticks spell it.
PORT_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Each slot category the Totals sentence claims a count for, mapped to the
# substring that identifies a table row as belonging to it. Matched against the
# row's "Assumed Challenge slot" cell, which is the column the budget is stated
# in -- so a row's category comes from the table, never from this file.
IO_SLOT_CATEGORIES = {
    "digital control inputs": "digital control input",
    "digital test outputs": "digital test output",
    "dedicated pads": "dedicated pad",
    "harness-supplied reference lines": "harness-supplied bandgap reference",
}

# One claim in the Totals sentence: a bolded count, an optional "of <budget>"
# clause (the harness reference has no stated budget), and the category. The
# bold is required so a count that is gated cannot be confused with one of the
# many unbolded numbers the surrounding prose carries.
IO_TOTAL_RE = re.compile(
    r"\*\*(?P<count>\d+)\*\* (?:of (?:≤\s*)?\d+(?:\s*[–-]\s*\d+)?\s+)?"
    r"(?P<category>" + "|".join(sorted(IO_SLOT_CATEGORIES, key=len, reverse=True)) + r")"
)

# The conditional total: the same dedicated-pad count with the harness
# reference's own lines folded in, which is the slot-budget risk Section 2
# flags. Phrased distinctly from the claims above on purpose -- stated as
# another "N of 0-4 dedicated pads" it would be indistinguishable from the
# unconditional one, and each would be graded against the other's number.
IO_CONDITIONAL_RE = re.compile(
    r"\*\*(?P<conditional>\d+) dedicated pads against a 0\s*[–-]\s*4 ceiling\*\*"
)

# The scalar readout fields, paired with how each is read out of the record's
# own JSON. `drc.json` and `lvs.json` are `klt`'s own machine-readable output,
# so these are field paths into them, never re-derived numbers.
READOUT_SCALARS = (
    ("drc_status", ("drc", "status")),
    ("violation_count", ("drc", "violation_count")),
    ("lvs_status", ("lvs", "status")),
    ("mismatch_count", ("lvs", "mismatch_count")),
    ("error_count", ("lvs", "error_count")),
)

# The three-way correspondence counts, as `lvs.json` nests them under `counts`.
READOUT_COUNT_KINDS = ("devices", "nets", "pins")
READOUT_COUNT_SIDES = ("layout", "reference", "matched")


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


def _load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def signoff_readout(block: str) -> dict | None:
    """The live DRC/LVS readout of `layout/<block>/`'s current report.

    `None` when the flow has no `reports/LATEST`, or that record carries no
    readable `drc.json`/`lvs.json` -- there is nothing for check 9 to compare
    against, which is a different (and separately reported) condition from a
    readout that disagrees.
    """
    stamp = _pointer_stamp("layout", block)
    if stamp is None:
        return None
    report = REPO_ROOT / "layout" / block / "reports" / stamp
    sources = {"drc": _load_json(report / "drc.json"), "lvs": _load_json(report / "lvs.json")}
    if any(source is None for source in sources.values()):
        return None
    readout: dict = {
        field: sources[source].get(key) for field, (source, key) in READOUT_SCALARS
    }
    counts = sources["lvs"].get("counts") or {}
    for kind in READOUT_COUNT_KINDS:
        side_counts = counts.get(kind) or {}
        for side in READOUT_COUNT_SIDES:
            readout[f"{kind}_{side}"] = side_counts.get(side)
    readout["categories"] = dict(sources["lvs"].get("category_counts") or {})
    return readout


def readout_sentence(block: str, readout: dict) -> str:
    """The readout in exactly the sentence form `READOUT_RE` matches.

    Used by `--stats` so the fix for a check-9 failure is a paste. The bold
    markers the document wraps each number in are added here, so what
    `--stats` prints is what the document carries verbatim.
    """
    categories = readout["categories"]
    tail = (
        "by category "
        + ", ".join(f"`{name}: {count}`" for name, count in sorted(categories.items()))
        if categories
        else "no mismatch categories"
    )
    return (
        f"on the record `layout/{block}/reports/LATEST` resolves to, `klt drc` "
        f"reports status **{readout['drc_status']}** with "
        f"**{readout['violation_count']}** violations, and `klt lvs` reports status "
        f"**{readout['lvs_status']}** with **{readout['mismatch_count']}** mismatches "
        f"and **{readout['error_count']}** errors; devices "
        f"**{readout['devices_layout']}** layout / **{readout['devices_reference']}** "
        f"reference / **{readout['devices_matched']}** matched; nets "
        f"**{readout['nets_layout']}** / **{readout['nets_reference']}** / "
        f"**{readout['nets_matched']}** matched; pins **{readout['pins_layout']}** / "
        f"**{readout['pins_reference']}** / **{readout['pins_matched']}** matched; "
        f"{tail}."
    )


def _stated_categories(stated: re.Match) -> dict[str, int]:
    clause = stated.group("categories")
    if clause is None:
        return {}
    return {
        pair.group("name"): int(pair.group("count"))
        for pair in READOUT_CATEGORY_RE.finditer(clause)
    }


def _collapse_quoted_prose(text: str) -> tuple[str, list[int]]:
    """Whitespace-collapse `text`, dropping Markdown blockquote markers first.

    The readout is set as a blockquote, which is what a data statement should
    look like in this document -- but a plain whitespace collapse leaves each
    line's `> ` marker embedded mid-sentence, and `READOUT_RE` then matches
    nothing. A check that silently matches nothing is the vacuity trap checks
    4 and 6 each already needed a guard for, so the marker is stripped here
    rather than the blockquote given up.

    Returns the collapsed text and, per collapsed character, the offset it
    came from in `text`, so a finding can be reported at the line the reader
    has to edit rather than at the first unrelated occurrence of some token
    in it.
    """
    collapsed: list[str] = []
    offsets: list[int] = []
    at_line_start = True
    index = 0
    while index < len(text):
        if at_line_start:
            at_line_start = False
            marker = re.compile(r"[ \t]*>[ \t]?").match(text, index)
            if marker is not None:
                index = marker.end()
                continue
        if text[index].isspace():
            run = index
            while index < len(text) and text[index].isspace():
                at_line_start = at_line_start or text[index] == "\n"
                index += 1
            collapsed.append(" ")
            offsets.append(run)
            continue
        collapsed.append(text[index])
        offsets.append(index)
        index += 1
    return "".join(collapsed), offsets


def check_signoff_readout(doc: Path, text: str) -> list[str]:
    """Check 9: a stated DRC/LVS readout must be the record's own numbers."""
    collapsed, offsets = _collapse_quoted_prose(text)
    misses = []
    for stated in READOUT_RE.finditer(collapsed):
        block = stated.group("flow").split("/", 1)[1]
        where = f"{doc.name}:{_line_of(text, offsets[stated.start()])}"
        actual = signoff_readout(block)
        if actual is None:
            misses.append(
                f"{where}: the sign-off-bar readout names `layout/{block}/`, but "
                f"that flow has no `reports/LATEST` record carrying both a "
                f"`drc.json` and an `lvs.json` to read it out of"
            )
            continue

        fields = [field for field, _source in READOUT_SCALARS]
        fields += [
            f"{kind}_{side}" for kind in READOUT_COUNT_KINDS for side in READOUT_COUNT_SIDES
        ]
        for field in fields:
            expected = actual[field]
            claimed: object = stated.group(field)
            if isinstance(expected, int):
                claimed = int(claimed)
            if claimed != expected:
                misses.append(
                    f"{where}: the sign-off-bar readout for `layout/{block}/` says "
                    f"{field}={claimed}, but that flow's current record reports "
                    f"{field}={expected} -- restate it from `python3 "
                    f"docs/chipalooza/check_proposal_citations.py --stats`"
                )

        claimed_categories = _stated_categories(stated)
        for name in sorted(set(claimed_categories) | set(actual["categories"])):
            claimed_count = claimed_categories.get(name)
            actual_count = actual["categories"].get(name)
            if claimed_count == actual_count:
                continue
            misses.append(
                f"{where}: the sign-off-bar readout for `layout/{block}/` states "
                f"category `{name}` as {claimed_count}, but that flow's current "
                f"record reports {actual_count} -- restate it from `python3 "
                f"docs/chipalooza/check_proposal_citations.py --stats`"
            )
    return misses


def netlist_ports() -> list[str]:
    """`design/sar_adc_top.spice`'s own top-level port list, in order.

    Empty when the netlist is absent, which is how check 10 stays inert
    against the test fixtures (their REPO_ROOT has no `design/` tree); that
    the real one is found and non-empty is asserted by the tests.
    """
    path = REPO_ROOT / TOP_NETLIST
    if not path.is_file():
        return []
    match = SUBCKT_RE.search(path.read_text())
    return match.group("ports").split() if match else []


def _expand_range(token: str) -> list[str] | None:
    """`DOUT9..DOUT0` -> the ten ports it names, MSB first; else None."""
    ranged = PORT_RANGE_RE.match(token)
    if ranged is None:
        return None
    prefix = ranged.group("prefix")
    high, low = int(ranged.group("high")), int(ranged.group("low"))
    indices = range(high, low - 1, -1) if high >= low else range(high, low + 1)
    return [f"{prefix}{index}" for index in indices]


def _cell_ports(cell: str) -> list[str]:
    """Every port a table cell names, with `A9..A0` ranges expanded.

    Only backticked tokens count: the Signal column spells every port in
    backticks, and prose words in the same cell are not ports.
    """
    ports: list[str] = []
    for span in BACKTICK_SPAN_RE.finditer(cell):
        token = _unwrap_backticked(span.group(1))
        expanded = _expand_range(token)
        if expanded is not None:
            ports.extend(expanded)
        elif PORT_NAME_RE.match(token):
            ports.append(token)
    return ports


def io_table(text: str) -> list[tuple[int, list[str]]]:
    """Section 2's I/O table as `[(line_number, cells)]`, header excluded."""
    rows: list[tuple[int, list[str]]] = []
    in_table = False
    for index, line in enumerate(text.split("\n"), start=1):
        if not line.startswith("|"):
            in_table = False
            continue
        cells = _row_cells(line)
        if cells[:1] == [IO_TABLE_HEADER]:
            in_table = True
            continue
        if not in_table or all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
            continue
        rows.append((index, cells))
    return rows


def quoted_port_lists(text: str) -> list[tuple[int, list[str]]]:
    """Every `.subckt sar_adc_top` port list quoted in a fenced code block."""
    quoted: list[tuple[int, list[str]]] = []
    for block in FENCED_BLOCK_RE.finditer(text):
        body = block.group("body")
        match = re.search(r"\.subckt\s+sar_adc_top\s+(?P<ports>.*)", body, re.S)
        if match is None:
            continue
        # A quoted list wraps with a trailing backslash; the ports are the
        # tokens, not the continuation markers.
        ports = match.group("ports").replace("\\", " ").split()
        quoted.append((_line_of(text, block.start()), ports))
    return quoted


def check_io_table_parity(doc: Path, text: str) -> list[str]:
    """Check 10: Section 2's I/O list is the netlist's own, fully categorised."""
    ports = netlist_ports()
    if not ports:
        return []
    misses = []

    # (a) The quoted port list is the netlist's, port for port and in order.
    for line, quoted in quoted_port_lists(text):
        if quoted != ports:
            misses.append(
                f"{doc.name}:{line}: the quoted `.subckt sar_adc_top` port list "
                f"is not `{TOP_NETLIST}`'s own -- quoted {quoted}, netlist "
                f"{ports}; regenerate the quote rather than editing it by hand"
            )

    rows = io_table(text)
    if not rows:
        return misses

    # (b) Every port is mapped, and nothing is mapped that is not a port.
    mapped: dict[str, int] = {}
    for line, cells in rows:
        for port in _cell_ports(cells[0]):
            mapped.setdefault(port, line)
    for port in ports:
        if port not in mapped:
            misses.append(
                f"{doc.name}: port `{port}` of `{TOP_NETLIST}` has no row in "
                f"Section 2's I/O table -- every port must be mapped to a slot "
                f"(issue #121 acceptance criterion 1)"
            )
    for port, line in sorted(mapped.items(), key=lambda item: item[1]):
        if port not in ports:
            misses.append(
                f"{doc.name}:{line}: Section 2's I/O table names `{port}`, which "
                f"is not a port of `{TOP_NETLIST}` -- the table is a "
                f"categorisation of that port list, not a superset of it"
            )

    # (c) Each row's stated count is the number of ports it actually names.
    for line, cells in rows:
        if len(cells) < 4:
            continue
        named = len(_cell_ports(cells[0]))
        stated = re.match(r"\d+", cells[3])
        if stated is None:
            continue
        if int(stated.group(0)) != named:
            misses.append(
                f"{doc.name}:{line}: I/O row `{cells[0]}` states a count of "
                f"{stated.group(0)}, but names {named} port(s)"
            )

    # (d) The Totals sentence is the sum of those counts, per slot category.
    totals: dict[str, int] = {category: 0 for category in IO_SLOT_CATEGORIES}
    for line, cells in rows:
        if len(cells) < 4:
            continue
        stated = re.match(r"\d+", cells[3])
        if stated is None:
            # A row claiming no slot (the shared rail) is not counted against
            # any budget -- but it may not claim a category either.
            continue
        matched = [
            category
            for category, keyword in IO_SLOT_CATEGORIES.items()
            if keyword in cells[2]
        ]
        if len(matched) != 1:
            misses.append(
                f"{doc.name}:{line}: I/O row `{cells[0]}` counts "
                f"{stated.group(0)} against the slot budget, but its slot cell "
                f"matches {len(matched)} of the categories the Totals sentence "
                f"states ({', '.join(sorted(IO_SLOT_CATEGORIES))})"
            )
            continue
        totals[matched[0]] += int(stated.group(0))

    collapsed, offsets = _collapse_quoted_prose(text)
    for claim in IO_TOTAL_RE.finditer(collapsed):
        category = claim.group("category")
        where = f"{doc.name}:{_line_of(text, offsets[claim.start()])}"
        if int(claim.group("count")) != totals[category]:
            misses.append(
                f"{where}: the Totals sentence claims {claim.group('count')} "
                f"{category}, but Section 2's I/O table counts "
                f"{totals[category]}"
            )
    for claim in IO_CONDITIONAL_RE.finditer(collapsed):
        where = f"{doc.name}:{_line_of(text, offsets[claim.start()])}"
        expected = totals["dedicated pads"] + totals["harness-supplied reference lines"]
        if int(claim.group("conditional")) != expected:
            misses.append(
                f"{where}: the conditional dedicated-pad total claims "
                f"{claim.group('conditional')}, but the table's dedicated pads "
                f"plus its harness-supplied reference lines come to {expected}"
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
        + check_signoff_readout(doc, text)
        + check_io_table_parity(doc, text)
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
        # Every `layout/` flow, not only the one the document happens to state
        # today: this is also what to paste when ADDING a readout for a flow
        # that has none yet, and a flow with no readout prints nothing useful
        # if it has to be named first.
        for pointer in sorted(REPO_ROOT.glob("layout/*/reports/LATEST")):
            block = pointer.parent.parent.name
            readout = signoff_readout(block)
            if readout is None:
                continue
            print(f"layout/{block}/: {readout_sentence(block, readout)}")
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

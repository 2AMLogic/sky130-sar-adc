#!/usr/bin/env python3
"""Headless citation check for docs/chipalooza/challenge-4-proposal.md.

The Chipalooza Challenge #4 proposal (issue #121) is a hand-maintained
evidence ledger whose Section 4 verdicts cite dated `sim/<campaign>/records/`,
`layout/<block>/reports/` and `layout/<block>/erc-reports/` records by path,
and whose prose asserts that some of those records are the *current* ones --
both by pointer ("the current `reports/LATEST`", checks 4/5) and by stamp
("the current run, `<record>`", check 23). This script gates both claims
mechanically, so that drift is a CI failure rather than something a human or
agent has to find by re-reading 2000 lines of prose. It is deliberately
PDK-free and network-free (pure file reads), like `sim/check_spec_coverage.py`
and `layout/bin/check-klt-pin-evidence.sh`, so it runs in the always-on
headless `checks` CI job rather than the PDK-gated one.

WHAT IT CHECKS
--------------
Each check's own one-line docstring below states what it checks; the chain
`check_document` runs is the authoritative list. Every *rationale* -- why a
check exists, what it deliberately does NOT cover, and why several tempting
extensions were rejected -- lives in one place instead of here:

    docs/citation-gate.md

Read that before adding, narrowing, or widening a check; several passes have
recorded there why NOT to extend a given check, so that the idea is not
re-proposed blind. It is one directory up from this script on purpose: this
script checks every `docs/chipalooza/*.md`, so a rationale document placed
beside the proposal would itself become a checked document and change this
script's own output. `sim/tests/test_proposal_citations.py` asserts that every
check in the `check_document` chain is documented there, so a new check
cannot land without its rationale.

USAGE
-----
    python3 docs/chipalooza/check_proposal_citations.py [--stats] [DOC ...]

With no arguments it checks every `docs/chipalooza/*.md`. `--stats` prints each
document's live pointer-claim census (the numbers check 6 compares against),
the live sign-off-bar readout of every `layout/` flow (the sentence check 9
compares against), the live area readout of every `layout/` flow whose current
record carries a composition (the sentence check 13 compares against), the provenance of every
input that composition embeds (the sentence check 14 compares against) and the
live power readout of every `sim/` campaign whose current record carries a
Power table (the sentence check 12 compares against), the live status of
every `spec/decision-records/` record (the sentence check 15 compares
against), the live `klt erc` supply readout of every `layout/` flow that
has one (the sentence check 16 compares against), the live T1 sign-off
verdict `signoff/` records for the block as a whole (the sentence check 17
compares against), each document's live Section 4 freshness-coverage census
(the sentence check 18 compares against) and the live per-source current
columns of every `sim/` campaign's Power table (the term list check 19
compares Section 5's power step against), the live device/cell inventory of
`design/sar_adc_top.spice` (the sentences check 20 compares against), each
document's live Kickback readout re-derived from the record its own Section 4
row cites (the clauses check 21 compares against), the live row count
`sim/report/generate.py --check` closes with (the line check 24 compares
against), the live inductor-card census of every SPICE deck under `sim/`
(the sentence check 25 compares against) and the live toolchain/PDK
provenance census of every `sim/` and `layout/` record (the sentence check 26
compares against), each document's live Section 4 corner-grid census (the
sentence check 28 compares against) and the live record-renderer census of
every `layout/` record tree (the sentence check 30 compares against) instead
of checking, which is what to run when check 6, 9, 12, 13, 14, 15, 16, 17, 18,
19, 20, 21, 24, 25, 26, 28 or 30 reports a drift. Exit status:

    0 - every citation checks out
    1 - one or more citations are stale/broken (each one listed on stdout)
    2 - usage error (a named document does not exist)
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHIPALOOZA_DIR = REPO_ROOT / "docs" / "chipalooza"

# Top-level directories whose paths this repo owns, and can therefore resolve.
# A reference whose first segment is not one of these belongs to some other
# project (e.g. klayout-tools' own `src/`) and is not checked.
#
# `signoff/` joined the set with check 17 (issue #121): the block manifest and
# the `klt signoff` report it renders to are this repository's own tree, and
# this document now cites both by path. Before that entry, a backticked
# `signoff/...` path was silently unchecked by check 2 -- the same
# not-my-directory hole `erc-reports/` had at checks 3/4 before check 16.
#
# ADDING AN ENTRY? Name it in `docs/citation-gate.md`'s check 2 parenthetical
# too. That sentence is a claim about this gate's own coverage, so it is
# gated: TestRationaleDocumentCoverage compares it to this frozenset in both
# directions, and a one-sided edit fails `npm run test:unit`. (Check 17 added
# `signoff` and left that list naming seven directories -- the drift this gate
# now catches.)
OWN_TOP_LEVEL = frozenset(
    (
        "sim",
        "layout",
        "spec",
        "design",
        "docs",
        "measurements",
        "ratification",
        "signoff",
    )
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

# Check 11's basis: this repo's own spec-row -> bench -> evidence-record index
# (T1 item 9, issue #31), whose own completeness/pinning is gated by
# `sim/check_spec_coverage.py`. Using it rather than a list in this file means
# a campaign indexed under a spec row is discovered here automatically.
COVERAGE_INDEX = Path("sim") / "spec-coverage.json"

# The two `claim_class` values that index defines as resting on committed
# evidence (">=1 bench, >=1 record"). `structural` and `methodology` rows name
# no DUT quantity -- their Section 4 rows cite schematics and corner-harness
# directories, not records -- and `unbenched` rows have no evidence at all.
MEASURED_CLAIM_CLASSES = frozenset(("ratified-measured", "draft-informational"))

# Section 4's evidence-deferral idiom: a row whose Source cell is `same record`
# (the LSB and Sampling-cap rows inherit `V_REF`'s campaign rather than
# re-citing it). Resolved by check 11 rather than skipped, so deferring cannot
# become a hole in the parity.
DEFERRAL_RE = re.compile(r"\bsame (?:record|as)\b", re.I)

# The per-corner power table a `sim/` campaign's record carries, identified by
# its own heading and read by check 12. The corner id is backticked in the
# record's first column and the total is its last numeric column, which is the
# shape `sim/full-conversion-transient/run_conversion.py` writes.
POWER_TABLE_HEADING_RE = re.compile(r"^##+\s+Power\b", re.M)
POWER_TABLE_ROW_RE = re.compile(r"^\|\s*`(?P<corner>[^`|]+)`\s*\|(?P<rest>.+\|)\s*$", re.M)

# The nominal PVT point of this repo's ratified one-at-a-time grid, which is
# the "typ" of the readout's min/typ/max. Named here rather than derived by
# sorting: "typ" is the grid's own centre point, not the median measurement.
NOMINAL_CORNER = "tt_27c_1.80v"

# The power readout sentence check 12 gates, stated inside the Section 4 Power
# row (one physical line, so no whitespace collapsing is involved). Each figure
# is bolded and immediately followed by the corner it was measured at, so a
# number cannot drift away from its corner id; the corner count closes the
# grid-shape hole (three right figures off a 4-corner run is not this claim).
POWER_READOUT_RE = re.compile(
    r"min \*\*(?P<min>\d+(?:\.\d+)?) µW\*\* at `(?P<min_corner>[^`]+)`, "
    r"typ \*\*(?P<typ>\d+(?:\.\d+)?) µW\*\* at `(?P<typ_corner>[^`]+)`, "
    r"max \*\*(?P<max>\d+(?:\.\d+)?) µW\*\* at `(?P<max_corner>[^`]+)`, "
    r"over \*\*(?P<corners>\d+)\*\* corners"
)

# Which readout fields are figures (compared numerically, at the record's own
# three-decimal resolution) and which are names (compared literally).
POWER_READOUT_FIGURES = ("min", "typ", "max")
POWER_READOUT_NAMES = ("min_corner", "typ_corner", "max_corner")

# The composition artefact check 13 reads the Area row's bounding box out of,
# and the `bbox_um` keys it carries. `klt gen-compose` writes both, so these
# are field paths into its own output rather than numbers re-derived here.
COMPOSE_ARTEFACT = "compose.json"
AREA_BBOX_KEYS = ("x0", "y0", "x1", "y1")

# How many decimals the area readout is stated and compared at. This is the
# `dbu_um` these compositions are written on (0.001 um), so a figure that
# differs at this resolution is a real geometry move, not a formatting one.
AREA_DECIMALS = 3

# A figure in the area readout. Accepts either minus sign: this document sets
# temperatures with U+2212 and coordinates with ASCII `-`, and a readout that
# silently failed to match because of which one an author typed would be the
# vacuity trap checks 4, 6 and 8 each already needed a guard for.
AREA_FIGURE = r"[-−]?\d+(?:\.\d+)?"

# The area readout sentence check 13 gates, stated inside the Section 4 Area
# row (one physical line, like the power readout, so no whitespace collapsing
# is involved). Every field compared against `compose.json` is a named group,
# the composed cell included: the extent means nothing without the cell it is
# the extent *of*, and that name has already changed once in this flow's
# routing block (`ROUTE` -> `SAR_ADC_TOP_ROUTE`).
AREA_READOUT_RE = re.compile(
    r"the composed cell `(?P<cell>[A-Za-z_][A-Za-z0-9_]*)` on the record "
    r"`(?P<flow>layout/[A-Za-z0-9._-]+)/reports/LATEST` resolves to spans "
    r"\*\*(?P<x0>" + AREA_FIGURE + r")\*\* µm to \*\*(?P<x1>" + AREA_FIGURE + r")\*\* "
    r"µm in x and \*\*(?P<y0>" + AREA_FIGURE + r")\*\* µm to "
    r"\*\*(?P<y1>" + AREA_FIGURE + r")\*\* µm in y, i\.e\. "
    r"\*\*(?P<width>" + AREA_FIGURE + r")\*\* µm × \*\*(?P<height>" + AREA_FIGURE + r")\*\* "
    r"µm ≈ \*\*(?P<area_mm2>" + AREA_FIGURE + r")\*\* mm²"
)

# Every figure the area readout states, in the order a finding reports them:
# the record's own four coordinates first, then the three the document derives
# from them.
AREA_READOUT_FIGURES = AREA_BBOX_KEYS + ("width", "height", "area_mm2")

# `compose.json`'s own word for a block that is an already-drawn cell composed
# in, as opposed to one generated during the run (the routing block's
# `generator_report`). Only the former is copied in as a `<id>.gds` file, so
# only the former has an upstream record to trace back to.
COMPOSITION_CELL_SOURCE = "cell"

# A GDS record header: a big-endian byte count (header included), a record
# type, and a data type.
GDS_HEADER = struct.Struct(">HBB")
GDS_HEADER_SIZE = GDS_HEADER.size

# BGNLIB and BGNSTR, the two record types whose payload is a wall-clock
# modification/access timestamp. `klt` stamps those at write time, so two runs
# that produce identical geometry still produce byte-different files; check 14
# would report every input as unmatched if they were hashed in. Nothing else
# in the stream is dropped -- the comparison stays exact on everything that
# describes geometry, layers, cell names or properties.
GDS_TIMESTAMP_RECORDS = frozenset((0x01, 0x05))

# The composition-input readout check 14 gates, stated in Section 3 as a
# blockquote (so it is read off the same whitespace-collapsed text check 9
# uses). Every field compared is a named group: which cell, how many records
# of the named flow reproduce it, the newest of those, what that flow's
# pointer names today, and the verdict word those two imply.
COMPOSITION_INPUT_RE = re.compile(
    r"the composition on `(?P<composition>layout/[A-Za-z0-9._-]+)/reports/LATEST` "
    r"embeds a `(?P<cell>[A-Za-z_][A-Za-z0-9_]*)\.gds` that reproduces "
    r"\*\*(?P<matched>\d+)\*\* records? of `(?P<flow>layout/[A-Za-z0-9._-]+)/`, "
    r"newest `(?P<newest>" + STAMP + r")`, while `reports/LATEST` there names "
    r"`(?P<latest>" + STAMP + r")`: \*\*(?P<status>current|superseded)\*\*"
)

# The two verdict words the composition-input readout may end in, keyed on
# whether the flow's own pointer is among the records the embedded copy
# reproduces. There is deliberately no third word for "reproduces nothing":
# that is reported as a finding, because it is also what a broken fingerprint
# would look like, and a document must not be able to state its way past it.
COMPOSITION_INPUT_CURRENT = "current"
COMPOSITION_INPUT_SUPERSEDED = "superseded"

# This repo's ratification trail, relative to REPO_ROOT. A decision record
# moves `proposed` -> `accepted` by the operator's approval of the PR that
# carries it, and `spec/target-spec.md` follows -- so the record's own Status
# field moves first and is the earlier signal. Kept as path *segments* rather
# than a joined Path, because REPO_ROOT is rebound per fixture tree.
DECISION_RECORDS_DIR = ("spec", "decision-records")

# A decision record's own file name, which carries its number. `TEMPLATE.md`
# is excluded by this shape rather than by a name list here: it is not a
# record, and its own Status field is a vocabulary enumeration rather than a
# status.
DECISION_RECORD_FILE_RE = re.compile(r"^DR-(?P<number>\d+)-[A-Za-z0-9._-]+\.md$")

# The `- **Status**: <word>` field every decision record opens with. The word
# is bolded in some records and bare in others, and is followed by an em-dash
# rationale this check deliberately does not read -- the status is the word.
DECISION_RECORD_STATUS_RE = re.compile(
    r"^-\s+\*\*Status\*\*:\s*\**\s*(?P<status>[A-Za-z]+)", re.MULTILINE
)

# The decision-record status readout check 15 gates, stated in Section 7 as a
# blockquote (so it is read off the same whitespace-collapsed text checks 9
# and 14 use). The number is a group of its own and is compared against the
# named file's own number: this tree carries two DR-004s and two DR-007s, so a
# line that pairs one number with the other's file is a real defect shape.
DECISION_RECORD_READOUT_RE = re.compile(
    r"\*\*DR-(?P<number>\d+)\*\* \(`spec/decision-records/"
    r"(?P<file>DR-\d+-[A-Za-z0-9._-]+\.md)`\) is \*\*(?P<status>[a-z]+)\*\*"
)

# A bare `DR-<number>` reference, which is how this document names a decision
# record in running prose. Ambiguous whenever two records share that number
# AND disagree about their status -- see check 15.
BARE_DECISION_RECORD_RE = re.compile(r"\bDR-(\d+)\b")

# Where a `layout/` flow keeps its `klt erc` supply verdicts. They are a
# SEPARATE append-only tree from `reports/`, with a pointer file of their own,
# which is exactly why no earlier check can see them: `EVIDENCE_PATH_RE`
# matches `records|reports` only, so `layout/<block>/erc-reports/<stamp>/` is
# invisible to checks 3 and 4 however the document cites it.
ERC_POINTER_DIR = "erc-reports"

# One declared supply `klt erc` actually graded for connectivity, as its own
# coverage list states it. Read from the record rather than from the spec file
# the run was driven by: the spec is a live, editable input, the record is
# evidence -- and "which nets were graded" is a property of the run.
ERC_NET_COVERAGE_RE = re.compile(r'^erc\.net_connectivity:\["(?P<net>[^"]+)"\]$')

# The finding `klt erc` writes when a declared supply resolves to more than one
# electrical island, carrying the island list its count comes from. A supply
# with no such finding resolved to exactly one island: the report states no
# per-net island count on the passing side, so one is the only reading.
ERC_UNCONNECTED_RULE = "erc.unconnected_net"

# The graded layout record inside `erc.json`'s own `file` field. That field is
# the path `klt erc` was invoked with, verbatim -- repo-relative since #355,
# absolute inside an ephemeral worktree before it -- so the stamp is matched
# out of it rather than the whole path being resolved.
ERC_GRADED_RE = re.compile(
    r"reports/(?P<stamp>" + STAMP + r")/(?P<artefact>[A-Za-z0-9._-]+)$"
)

# `klt`'s own content-hash prefix, as `provenance.input.content_hash` writes it.
ERC_HASH_PREFIX = "sha256:"

# The two verdict words the ERC readout may end in, keyed on whether the ERC
# record grades the bytes the flow's `reports/LATEST` carries today. This is
# the record's own "Staleness rule" ("a new `reports/<id>/` makes this one
# stale, not wrong"), which nothing else in this repository evaluates.
ERC_CURRENT = "current"
ERC_STALE = "stale"

# The ERC supply readout check 16 gates, stated in Section 7 as a blockquote
# (so it is read off the same whitespace-collapsed text checks 9, 14 and 15
# use). Deliberately free of the phrase "current `reports/LATEST`": this
# sentence names a pointer *and* a verdict word, and spelling it that way
# would enrol the sentence in check 4/6's census as well, where it is not a
# citation of anything.
ERC_READOUT_RE = re.compile(
    r"on the record `(?P<flow>layout/[A-Za-z0-9._-]+)/erc-reports/LATEST` resolves "
    r"to, `klt erc` reports `erc_status` \*\*(?P<erc_status>[a-z_]+)\*\* with "
    r"\*\*(?P<finding_count>\d+)\*\* findings; the declared supplies resolve to "
    r"(?P<islands>(?:`[A-Za-z][A-Za-z0-9_]*` \*\*\d+\*\*(?:, )?)+) electrical "
    r"islands; and it grades `(?P<graded>" + STAMP + r")`, while `reports/LATEST` "
    r"there names `(?P<latest>" + STAMP + r")`: "
    r"\*\*(?P<status>" + ERC_CURRENT + r"|" + ERC_STALE + r")\*\*\."
)

# One `<net> <islands>` pair inside that sentence's island clause. Each net is
# backticked and each count bolded, which makes the clause self-delimiting
# however many supplies a spec declares.
ERC_ISLAND_RE = re.compile(r"`(?P<net>[A-Za-z][A-Za-z0-9_]*)` \*\*(?P<islands>\d+)\*\*")

# This repository's THIRD evidence tree, and the first that is not a `layout/`
# flow's at all: `signoff/` holds the block manifest and the machine-graded
# `klt signoff` report it renders to -- the T1 verdict of record (issue #345).
# Both files are read by check 17, for different reasons. The report states the
# verdict; the manifest names the records that verdict rests on, which the
# rendered report DROPS for every item it grades `unmet` (an unmet item renders
# `citation: null`), so the report alone cannot say what evidence it read.
T1_REPORT = Path("signoff") / "t1-report.json"
T1_MANIFEST = Path("signoff") / "block-manifest.json"

# The reason `klt signoff` gives when an item's cited evidence WAS read and
# graded, and failed -- as distinct from `no_evidence`, where nothing was cited
# at all. The distinction is the whole reason this readout is worth stating:
# "the ERC ran, the supplies are continuous, and the item still is not met" is
# a materially more useful sentence than silence, and it is exactly the
# transition Section 7 item 9 currently narrates by hand.
T1_CHECK_FAILED = "check_failed"

# The tier whose rows the failed-row list is drawn from. The readout's `met`
# and `total` are `t1_met_count` and `t1_item_count` -- T1 counts -- so the
# list beside them must be T1 rows too. Without this scope, a T2/T3/T4 row the
# grader ever fails for a real reason (today it grades every one of them
# `tier_not_supported`) would be enrolled as a T1 failure, and the sentence
# would silently mix two tiers' rows under one T1 headline.
T1_TIER = "T1"

# An evidence path inside the manifest that names a `layout/` flow's own
# append-only tree -- EITHER of them. `reports/` and `erc-reports/` both appear
# in this manifest, which is why this is not `EVIDENCE_PATH_RE`: that one
# matches `records|reports` only, and would miss the ERC citation item 11
# rests on.
T1_CITED_PATH_RE = re.compile(
    r"^(?P<pointer>layout/(?P<block>[A-Za-z0-9._-]+)/(?:reports|erc-reports))/"
    r"(?P<stamp>" + STAMP + r")/"
)

# How a null `tier` renders in prose. `klt signoff` writes JSON `null` for a
# block that has reached no tier at all; stating it as a word is what makes a
# tier appearing later a visible change rather than a silent one.
T1_NO_TIER = "none"

# How a pointer that names no record at all renders, on either side of a cited
# pair. Never stamp-shaped, so it cannot be mistaken for one.
T1_NO_RECORD = "none"

# The two verdict words the T1 readout may end in, keyed on whether every
# `layout/` record the manifest cites is the one that tree's own `LATEST`
# names today. A signoff resting on a superseded-but-still-committed record
# hashes perfectly -- `signoff/check_evidence_hashes.py` passes on it -- and is
# still a verdict about a layout this repository has moved on from.
T1_CURRENT = "current"
T1_STALE = "stale"

# The T1 sign-off readout check 17 gates, stated in Section 7 as a blockquote
# (so it is read off the same whitespace-collapsed text checks 9, 14, 15 and 16
# use). Deliberately free of the phrase "current `reports/LATEST`", for check
# 16's own reason: spelling it that way would enrol the sentence in check 4/6's
# pointer-claim census, where it is not a citation of anything.
T1_READOUT_RE = re.compile(
    r"on the report `signoff/t1-report\.json`, `klt signoff` "
    r"\*\*(?P<version>[0-9][0-9A-Za-z.+-]*)\*\* grades \*\*(?P<met>\d+)\*\* of "
    r"\*\*(?P<total>\d+)\*\* T1 items met, block tier \*\*(?P<tier>[A-Za-z0-9]+)\*\*; "
    r"the items whose cited evidence was read and still failed are "
    r"(?P<failed>\*\*none\*\*|(?:`\d+ [a-z]+`(?:, )?)+); and its manifest cites "
    r"(?P<cited>\*\*none\*\*|(?:`layout/[A-Za-z0-9._/-]+/LATEST` at \*\*[0-9a-z-]+\*\* "
    r"against a pointer naming \*\*[0-9a-z-]+\*\*(?:, )?)+): "
    r"\*\*(?P<status>" + T1_CURRENT + r"|" + T1_STALE + r")\*\*\."
)

# One `<item> <partition>` pair inside that sentence's failed-item clause.
# Backticked, so the clause is self-delimiting however many items fail.
T1_FAILED_ITEM_RE = re.compile(r"`(?P<item>\d+) (?P<partition>[a-z]+)`")

# One cited-record triple inside that sentence's manifest clause: the pointer,
# the stamp the manifest cites, and the stamp that pointer names today. Both
# stamps are stated so a reader sees the comparison the verdict word rests on,
# rather than having to take it on trust.
T1_CITED_RE = re.compile(
    r"`(?P<pointer>layout/[A-Za-z0-9._/-]+/LATEST)` at \*\*(?P<cited>[0-9a-z-]+)\*\* "
    r"against a pointer naming \*\*(?P<latest>[0-9a-z-]+)\*\*"
)

# How an empty uncovered-flow clause renders in check 18's sentence. Never
# path-shaped, so it cannot be mistaken for a flow -- same convention as
# `T1_NO_RECORD`.
FRESHNESS_NONE = "**none**"

# Check 18's coverage census of check 3, matched against the same
# blockquote-aware collapsed text checks 9, 14, 15, 16 and 17 read. Check 3
# can only ask "is this the current record?" of a flow that publishes a
# `LATEST` pointer; `_pointer_stamp()` returns None for one that does not and
# the pair is skipped in silence. This sentence states how large that skipped
# set is and which flows are in it, so neither can drift unnoticed -- exactly
# what check 6 does for checks 4/5, one table over.
#
# Deliberately free of the phrase "current `records/LATEST`", for check 17's
# reason: spelling it that way would enrol this sentence in check 4/6's
# pointer-claim census, where it is not a citation of anything.
FRESHNESS_COVERAGE_RE = re.compile(
    r"of the \*\*(?P<pairs>\d+)\*\* \(spec row, evidence flow\) citation pairs "
    r"in Section 4's table, \*\*(?P<graded>\d+)\*\* name a flow that publishes a "
    r"`LATEST` pointer and are therefore freshness-checked by check 3; the "
    r"remaining \*\*(?P<ungraded>\d+)\*\* name a flow that publishes none, whose "
    r"current record nothing grades: (?P<flows>" + re.escape(FRESHNESS_NONE)
    + r"|(?:`(?:sim|layout)/[A-Za-z0-9._-]+` \(\*\*\d+\*\* records?\)(?:, )?)+)\."
)

# One flow inside that sentence's uncovered-flow clause: the flow path and how
# many records it holds. The count is load-bearing rather than decorative -- a
# pointerless flow holding one record is a far smaller hole than one holding
# twelve, and it is the twelve-record case where the document is picking a
# citation out of a set nothing re-derives.
FRESHNESS_FLOW_RE = re.compile(
    r"`(?P<flow>(?:sim|layout)/[A-Za-z0-9._-]+)` "
    r"\(\*\*(?P<records>\d+)\*\* records?\)"
)

# Section 5 is the bench test plan, identified by its own numbered heading. Its
# lede claims to be "written against this design's *current* port list (§2)" --
# check 19 is what makes that claim mechanical instead of asserted.
TEST_PLAN_HEADING_RE = re.compile(r"^##\s+5\.\s", re.M)

# Section 5's supply-terminal sentence: how many supply terminals the bench has
# to feed, and which. Bolded count for IO_TOTAL_RE's reason -- Section 5 carries
# plenty of unbolded numbers (rail voltages, clock rates, LSB counts) and a
# gated count must not be confused with one of them.
TEST_PLAN_SUPPLIES_RE = re.compile(
    r"\*\*(?P<count>\d+)\*\* supply terminals? — "
    r"(?P<terminals>(?:`[A-Za-z_][A-Za-z0-9_]*`(?:, )?)+)"
)

# Section 5's power-step sentence: the campaign whose Power table the simulated
# figure is summed over, how many current columns that table carries, and which.
# Naming the campaign in the sentence rather than in this file is what keeps the
# check pointed at the record Section 4 actually quotes.
TEST_PLAN_POWER_RE = re.compile(
    r"\*\*(?P<count>\d+)\*\* current columns of "
    r"`sim/(?P<campaign>[A-Za-z0-9._-]+)/records/LATEST`'s own Power table — "
    r"(?P<terms>(?:`I\([A-Za-z0-9_]+\)`(?:, )?)+)"
)

# One backticked `I(<net>)` column name inside that sentence's term list.
POWER_TERM_RE = re.compile(r"`I\((?P<net>[A-Za-z0-9_]+)\)`")

# The Power table's own header cell for a per-source current column, as
# `sim/full-conversion-transient/run_conversion.py` writes it: `I(VDD) (uA)`.
POWER_COLUMN_RE = re.compile(r"^I\((?P<net>[A-Za-z0-9_]+)\)")

# One instantiated PDK cell of either family, as it appears on a netlist
# instance line. A net name never has this shape, so counting these tokens IS
# the instance census -- no SPICE card grammar needs parsing (a subcircuit call
# names its cell last, a device card names its model before the first
# `key=value`, and this covers both).
PDK_CELL_RE = re.compile(
    r"\bsky130_fd_(?P<family>pr|sc_hd)__(?P<cell>[A-Za-z0-9_]+)\b"
)

# `design/sar_adc_top.spice`'s top-level region ends at the `**.ends` xschem
# writes for the flat top cell; everything after it is a sub-block `.subckt`.
# The region between is exactly the glue `design/sar_adc_top.sch` adds at the
# integration level, which is what check 20 part (b) grades.
TOP_REGION_END_RE = re.compile(r"^\*{0,2}\.ends\b", re.M)

# Section 1's primitive-flavour inventory: WHICH `sky130_fd_pr` flavours this
# design instantiates anywhere in its hierarchy. Bolded count for IO_TOTAL_RE's
# reason. This is the sentence that makes Section 2.1's rail position
# mechanical -- a `g5v0d10v5` device entering the netlist has to move it.
PRIMITIVE_INVENTORY_RE = re.compile(
    r"instantiates \*\*(?P<count>\d+)\*\* `sky130_fd_pr` primitive flavours? — "
    r"(?P<cells>(?:`[A-Za-z0-9_]+`(?:, )?)+)"
)

# Section 3's top-level glue census, one sentence per family. Each states its
# own instance total, its own type count, and the per-type counts -- so a cell
# type swapped for another of the same total cannot pass.
GLUE_CELL_CENSUS_RE = re.compile(
    r"adds \*\*(?P<instances>\d+)\*\* `sky130_fd_sc_hd` instances of "
    r"\*\*(?P<types>\d+)\*\* cell types? — "
    r"(?P<cells>(?:`[A-Za-z0-9_]+` \*\*×\d+\*\*(?:, )?)+)"
)
GLUE_PRIMITIVE_CENSUS_RE = re.compile(
    r"and \*\*(?P<instances>\d+)\*\* `sky130_fd_pr` instances of "
    r"\*\*(?P<types>\d+)\*\* device types? — "
    r"(?P<cells>(?:`[A-Za-z0-9_]+` \*\*×\d+\*\*(?:, )?)+)"
)

# One `<cell> ×<count>` entry inside either census list.
GLUE_CELL_RE = re.compile(r"`(?P<cell>[A-Za-z0-9_]+)` \*\*×(?P<count>\d+)\*\*")

# The Kickback row's cited record keeps its per-`Vindiff` figures under its own
# `## Measured value(s)` heading, written by
# `sim/comparator-decision/run.py kickback`.
MEASURED_TABLE_HEADING_RE = re.compile(r"^#+\s+Measured value\(s\)\s*$", re.M)

# One row of that table: the `Vindiff` point, then the two signed peak
# deviations, each with the pin and instant it occurred at. Both peaks are
# extrema over *either* pin independently (`run_kickback_sweep` tracks one
# maximum and one minimum across VINP and VINN together), which is the whole
# reason check 21 exists -- see docs/citation-gate.md.
KICKBACK_ROW_RE = re.compile(
    r"^\|\s*(?P<vindiff>[+-]?[0-9.]+)\s*"
    r"\|\s*(?P<pos>[+-][0-9.]+)\s*\|\s*(?P<pos_pin>[A-Za-z0-9_]+) @ (?P<pos_time>[0-9.]+)\s*"
    r"\|\s*(?P<neg>[+-][0-9.]+)\s*\|\s*(?P<neg_pin>[A-Za-z0-9_]+) @ (?P<neg_time>[0-9.]+)\s*\|",
    re.M,
)

# Section 4's Kickback row states three things check 21 re-derives, in three
# separate sentences: the measurement and its two multiples against the row's
# own bounds, the control-row subtraction, and the cited table's own column
# list. Three patterns rather than one -- a single pattern spanning all three
# would go vacuous the moment a pass wrote a clause between any two of them.
KICKBACK_PEAK_RE = re.compile(
    r"the cited record measures \*\*(?P<peak>[0-9.]+) mV\*\* worst-case peak pin "
    r"disturbance \(`Vindiff = (?P<vindiff>[+-][0-9.]+) mV`, `(?P<pin>[A-Za-z0-9_]+)` "
    r"at (?P<time>[0-9.]+) ns\), i\.e\. `≈ (?P<target_mult>[0-9.]+)×` the "
    r"`≤ (?P<target>[0-9.]+) mV` target and `≈ (?P<stretch_mult>[0-9.]+)×` the "
    r"`≤ (?P<stretch>[0-9.]+) mV` stretch"
)
KICKBACK_SPLIT_RE = re.compile(
    r"`Vindiff = 0 mV` control row \(\*\*[−-](?P<control>[0-9.]+) mV\*\*, "
    r"`(?P<pin>[A-Za-z0-9_]+)` at (?P<time>[0-9.]+) ns\): "
    r"`≈ (?P<baseline_pct>[0-9.]+) %` of that peak is already present with no "
    r"decision to make, and `(?P<residual>[0-9.]+) mV` "
    r"\(`≈ (?P<residual_pct>[0-9.]+) %`\) is what the "
    r"`(?P<worst_vindiff>[+-][0-9.]+) mV` point adds on top of it"
)
KICKBACK_COLUMNS_RE = re.compile(
    r"`Measured value\(s\)` table carries \*\*(?P<count>\d+)\*\* columns? — "
    r"(?P<columns>(?:`[^`]+`(?:, )?)+) — (?P<verdict>[^.]*)"
)

# The clause that trailing `verdict` group must carry while the cited record
# reports no common-mode or differential quantity -- and must NOT carry once it
# does. That flip is the point of the check: the successor record #390 mints
# (`Supersedes: 20260924-041815-afcb1b5`) adds exactly those columns, and this
# row must then be re-derived rather than keep a qualification that has stopped
# being true.
KICKBACK_NO_SPLIT_CLAUSE = "none of them is a common-mode or differential quantity"

# A Measured-value column name that IS such a quantity.
KICKBACK_SPLIT_COLUMN_RE = re.compile(
    r"common[-\s]?mode|differential|\bCM\b|\bdiff\b", re.I
)

# Check 23. Checks 4 and 5 grade the claim-AFTER-path direction and only the
# phrase "current `<tree>/LATEST`". This is the mirror: a present-tense
# currency claim stated BEFORE the citation, naming a record by STAMP rather
# than through a pointer. `record` and `run` both appear in this document;
# `ERC`/`layout`/`sim` are optional qualifiers the prose puts in between.
STAMPED_CURRENCY_CLAIM_RE = re.compile(
    r"[Tt]he current (?:ERC |layout |sim(?:ulation)? )?(?:run|record|report)\b"
)

# What may sit between that claim and the citation it introduces: whitespace,
# an opening paren/bracket/backtick, and the comma or colon the prose uses to
# hang the citation off the claim. Deliberately NOT tolerant of any word --
# "The current ERC record *grades* `layout/.../reports/<stamp>/...`" cites the
# graded stream, not the record making the claim, and must stay unattached.
STAMPED_CURRENCY_CONNECTOR_RE = re.compile(r"^[\s,:;`(\[]*$")

# How far after the claim the citation may start. A claim whose citation is
# further away than this is narration, not an attached citation (same
# reasoning, and the same order, as check 4's 400-character look-behind).
STAMPED_CURRENCY_WINDOW = 400

# The citation construct itself: a Markdown link (this document's usual form,
# whose display text and target each carry the stamp) or a bare backticked
# path. Both alternatives are graded on every stamp they carry, so a link
# whose display text and target name different records fails here rather than
# half-passing.
STAMPED_CITATION_RE = re.compile(
    r"\[`?(?P<display>[^\]`]+)`?\]\((?P<target>[^)\s]+)\)" r"|`(?P<bare>[^`]+)`"
)

# A stamped evidence-record path in any of the three trees this repo keeps --
# including `erc-reports/`, which `EVIDENCE_PATH_RE` deliberately does not
# match (checks 3/4 are scoped to the `records/`/`reports/` trees). The
# `layout/<block>/` prefix is optional because this document's link *display*
# text routinely elides it ("`erc-reports/<stamp>/record.md`") while the link
# target spells it out; the block is then taken from whichever form has it.
STAMPED_RECORD_RE = re.compile(
    r"(?:(?P<top>sim|layout)/(?P<block>[A-Za-z0-9._-]+)/)?"
    r"(?P<tree>records|reports|erc-reports)/(?P<stamp>" + STAMP + r")"
)


# Check 24. `docs/characterization-report.md` is generated from the row table
# in this module, and `sim/report/generate.py --check` closes by printing how
# many rows it carries. The proposal quotes that line verbatim as the evidence
# that it ran the command, so the number inside it is a transcribed machine
# output living in prose -- the exact shape checks 6 and 18 exist for, one
# artefact over.
REPORT_MANIFEST = "sim/report/manifest.py"

# The command whose output the document quotes. Used as the anchor for the
# "quoted nothing at all" direction: a document that leans on this command
# must state what it reports, or the check has nothing to grade.
REPORT_CHECK_COMMAND = "sim/report/generate.py --check"

# `sim/report/generate.py`'s own closing line, as the document quotes it. The
# prefix is deliberately not anchored on `OK:` -- the document elides the
# report's path with an ellipsis -- so the match starts at the fixed phrase.
REPORT_ROW_COUNT_RE = re.compile(r"is fresh and up to date \((?P<rows>\d+) rows?\)")

# `ROWS: tuple[Row, ...] = (` ... `)` in `sim/report/manifest.py`, and one
# `Row(` constructor per entry inside it. Counted textually rather than by
# importing the module: this gate is a pure file reader by design (see the
# module docstring), and importing a sibling tree's module to count a tuple
# would make a citation check execute repository code.
REPORT_MANIFEST_ROWS_RE = re.compile(r"^ROWS\b[^\n]*=\s*\(\s*$", re.M)
REPORT_MANIFEST_ROW_RE = re.compile(r"^    Row\(", re.M)

# Check 25. DR-012 (the drawn analog ground pad) and DR-013 (the met3/met4
# mesh that joins all three analog sub-blocks to it) both rest on an impedance
# argument each record states, in its own words, is *unmeasured*: "no `sim/`
# campaign in this repo models the ground return at all -- no package
# parasitics, no substrate resistance, no bond-wire inductance" (DR-012, "Open
# items", tracked as issue #378). Section 7 Item 9 owes a reader that
# qualification beside its four others, and it is the only one of the five
# whose truth is a property of this repository's evidence *tree* rather than
# of one report -- so it is the only one that goes silently false the day a
# campaign lands that does model the return, with no citation moving and no
# number in the island table changing. An inductor card is what such a
# campaign must add: neither bond-wire inductance nor any package model can be
# written in SPICE without one. Counting them is therefore a mechanical
# stand-in that fails in the direction that matters -- the gate goes red and
# the qualification is rewritten, rather than the document going on
# disclaiming a measurement it now has.
#
# The deck it scans (`.spice` under `sim/`) is a file-tree read, not a `git
# ls-files` read: this gate is network-free and subprocess-free by design, so
# an untracked scratch deck left under `sim/` counts here exactly as a
# committed one does. That is the conservative direction -- it can only make
# the census look less clean than the tree is.
SIM_DECK_ROOT = "sim"
SIM_DECK_GLOB = "**/*.spice"

# An ngspice inductor card: `L<name> <n+> <n-> <value>`, at the start of a
# (possibly indented) deck line. Comments (`*`), continuations (`+`) and
# dot-commands (`.tran`, `.lib`, ...) are stripped by the reader before this
# is applied, so the only way to match is an actual device card. Deliberately
# matched case-insensitively: this tree writes both `Vdd` and `VVDD`.
SPICE_INDUCTOR_CARD_RE = re.compile(r"^[Ll]\w*\s+\S+\s+\S+\s+\S")

# The ground-return census sentence check 25 grades, stated in Section 7 as a
# blockquote (so it is read off the same whitespace-collapsed text checks 9,
# 16 and 17 use). Deliberately free of the phrase "current `…/LATEST`", for
# check 17's reason: spelling it that way would enrol this sentence in checks
# 4/6's pointer-claim census, where it is not a pointer claim.
GROUND_RETURN_RE = re.compile(
    r"across the \*\*(?P<decks>\d+)\*\* SPICE decks? under `sim/`, "
    r"\*\*(?P<inductors>\d+)\*\* carry an inductor card"
)

# The anchor that makes an *absent* census a finding rather than a silence,
# the shape check 24 uses for `sim/report/generate.py --check`: a document
# that cites the decision record whose open item this qualifies must state
# the census. Deleting an inconvenient qualification is the drift this half
# guards -- the other checks' "grade it when stated" rule would let it go.
GROUND_RETURN_ANCHOR = "DR-012-analog-ground-pad.md"

# Check 26. Section 8's provenance sentence is the only one in this document
# that speaks for the *whole* evidence tree at once -- it tells a reader of
# the brief that any record cited above can be re-run against the same tools.
# Like check 25's disclaimer that makes it a property of the tree rather than
# of any one report, so no pointer moves and no Section 4 number budges when
# it stops being true; unlike check 25's, it had already stopped. The sentence
# this check replaced ("every layout record cites the `klt` version and PDK
# commit it ran against") was false for 33 of the 67 layout records on the day
# it was graded: only four of the eight `layout/` flows' record renderers
# resolve the PDK commit at all (`klt pdk find`), and `klt` stamps no PDK in
# its own provenance for the `--deck`-invoked DRC/LVS/extract runs or the
# built-in-PDK ERC run these flows use. Issue #407 tracks closing that gap;
# this check keeps the document's statement of it true meanwhile, in both
# directions, so neither a flow that starts pinning the commit nor one that
# stops can drift away from the census unnoticed.
PROVENANCE_SIM_GLOB = "sim/*/records/*.md"
PROVENANCE_LAYOUT_GLOBS = (
    "layout/*/reports/*/record.md",
    "layout/*/erc-reports/*/record.md",
)

# A 40-hex commit on a line that also names the PDK. Both halves are
# load-bearing. Every layout record carries a `repo commit:` line whose hash
# is NOT a PDK commit, so the line test is what stops this counting the repo's
# own sha as provenance it does not have; and every record stamp ends in a
# 7-hex abbreviation (`20260924-234053-66dca3c`), so the full 40 is what stops
# a stamp quoted beside the word "PDK" counting as one.
PROVENANCE_COMMIT_RE = re.compile(r"\b[0-9a-f]{40}\b")

# The two tool-version forms the trees actually write: `- ngspice: ngspice-46`
# on the `sim/` side (a digit must follow, so prose about "each ngspice run"
# is not a version), and a `klt`-adjacent semver on the `layout/` side
# (`- `klt` version: klt 0.6.0`, `- `klt` version: `klt 0.4.0` (pinned, ...)`).
PROVENANCE_NGSPICE_RE = re.compile(r"\bngspice[-\s]*v?\d", re.I)
PROVENANCE_KLT_RE = re.compile(r"\bklt`?\s*(?:version)?[^\n]{0,30}?\b\d+\.\d+\.\d+", re.I)

# The census sentence check 26 grades. Deliberately free of the phrase
# "current `…/LATEST`", for check 17's reason: spelling it that way would
# enrol this sentence in checks 4/6's pointer-claim census, where it is not a
# pointer claim.
PROVENANCE_CENSUS_RE = re.compile(
    r"\*\*(?P<sim_pinned>\d+)\*\* of the \*\*(?P<sim_records>\d+)\*\* records "
    r"under `sim/\*/records/` name both an `ngspice` version and a 40-hex "
    r"`open_pdks` commit, while of the \*\*(?P<layout_records>\d+)\*\* records "
    r"under `layout/\*/reports/` and `layout/\*/erc-reports/` "
    r"\*\*(?P<layout_klt>\d+)\*\* name a `klt` version and "
    r"\*\*(?P<layout_pdk>\d+)\*\* name the `open_pdks` commit"
)

# The anchor that makes an *absent* census a finding rather than a silence,
# check 25's shape: a document that cites the pin file while describing its
# own flow as reproducible must state how far that pin actually reaches.
PROVENANCE_ANCHOR = "sim/toolchain.json"

# Check 27. A `loom:` label is LIVE FORGE STATE -- the one class of claim this
# gate structurally cannot verify, because it is network-free by design (see
# this module's header). So the check does not grade what a label claim says;
# it grades how many copies of it the document keeps. Section 7 narrates
# tracking state paragraph by paragraph and date, and is maintained every
# pass; a label restated in Section 3's functional description or a Section 4
# verdict row is a second copy that nothing updates, and it rots. It had:
# on 2026-09-25 Section 3 read "#103 ... still open and `loom:blocked`" and
# Section 4's newest word on the same issue was "back in the ready queue
# (`loom:issue`)", while Section 7 Item 1 already carried the 2026-09-24
# escalation to `loom:operator-only`/`loom:operator-decision` -- three
# mutually contradictory readings of one issue, in one document, none of them
# detectable by any other check here.
LABEL_STATE_SECTION = 7

# Backticks optional on purpose: dropping them must not be a way to keep a
# second copy. `\b` before `loom` is what keeps a path segment (`.loom/`,
# which has no colon) and a prose word ending in "loom" out of the match.
LABEL_CLAIM_RE = re.compile(r"`?\bloom:(?P<label>[a-z][a-z0-9-]*)`?")

# `## 4. Target specification ...` -- the numbered top-level headings this
# document is built from. An unnumbered `##` (the front matter has none, but
# a future one is cheap) leaves the section unchanged rather than resetting
# it, so a claim is never silently attributed to no section at all.
SECTION_HEADING_RE = re.compile(r"^##\s+(?P<number>\d+)\.\s*(?P<title>.*)$")

# Check 28. Section 4 opens by naming the PVT grid its rows are reported at,
# and that sentence is the widest claim in the table: it speaks for every row
# at once, before a reader reaches any of them. Until 2026-09-25 it read
# "Every row below is reported at this repository's own ratified PVT grid",
# and measured against the records the table actually cites that was false for
# 10 of 22 (spec row, `sim/` record) pairs -- eight naming a record that
# declares a single nominal point (both of the Kickback row's comparator runs,
# the Power row's supply-impedance campaign, the two Monte Carlo linearity
# records, and three superseded single-corner mechanism budgets) and two
# naming one that declares no PVT point set of its own (the two derived ENOB
# re-analyses). None of those records hides it -- each states its own
# subset-corner justification -- but the document spoke over them, and no
# other check here could see it: checks 3/4/5/23 grade WHICH record a row
# cites, never what corner coverage that record claims for itself.
#
# The grid sentence itself, matched against the same whitespace-collapsed text
# checks 9 and 14--18 read (it spans three lines in the document).
CORNER_GRID_RE = re.compile(
    r"process corners `\{(?P<process>[^}]*)\}`, "
    r"temperature `\{(?P<temps>[^}]*)\} °C`, "
    r"supply `\{(?P<supplies>[^}]*)\} V`, "
    r"one-at-a-time \((?P<points>\d+) points\)"
)

# The PDK pin the process axis of that grid is checked against, in both
# directions. Without it the claim could be weakened into truth -- drop `sf`
# and `fs` from the sentence and a four-corner campaign starts reading as the
# full grid. `sim/pdk.json` is this repo's own list of the sections that exist
# in the PDK library, so it is the one anchor that is not the document's.
SIM_PDK_JSON = "sim/pdk.json"

# The three shapes in which a record under `sim/*/records/` declares the PVT
# points it ran at. All three are real and in use; keying on only the first
# would misreport five records that DO declare a single nominal point as
# declaring nothing, in a check whose whole subject is overstatement.
#
# (a) the corner-campaign driver's own line, written by
#     `sim/harness/corners.py:corner_matrix_summary_line()`.
RECORD_CORNER_MATRIX_RE = re.compile(
    r"\*\*Corner matrix run\*\*:\s*process=\[(?P<process>[^\]]*)\],\s*"
    r"temperature_c=\[(?P<temps>[^\]]*)\],\s*supply_v=\[(?P<supplies>[^\]]*)\]\s*"
    r"\((?P<points>\d+)\s+(?:PVT\s+)?points?\b"
)

# (b) the mechanism-budget drivers' line (`tt`/27C/1.8V only, ...).
RECORD_POINT_MATRIX_RE = re.compile(r"\*\*Point/corner matrix\*\*:(?P<body>[^\n]*)")

# (c) the Monte Carlo drivers' line, where the PVT point is stated inside the
#     statistical convention because the sampled axis is mismatch, not PVT.
RECORD_STAT_POINT_RE = re.compile(
    r"PVT point\s+process=(?P<process>\w+)\s+temp=(?P<temp>-?[\d.]+)\s*C\s+"
    r"supply=(?P<supply>[\d.]+)\s*V"
)

# One `<process>`/<temp>C/<supply>V triple, as shape (b) writes it.
RECORD_CORNER_TRIPLE_RE = re.compile(
    r"`?(?P<process>tt|ss|ff|sf|fs)`?\s*/\s*(?P<temp>-?\d+(?:\.\d+)?)\s*C\s*/\s*"
    r"(?P<supply>\d+(?:\.\d+)?)\s*V",
    re.I,
)

# What the census renders when every cited record declares the full grid --
# i.e. when the blanket sentence this check exists for would be true. Spelled
# out rather than left as an empty clause, so the true case is a statement
# too, `FRESHNESS_NONE`'s reason.
CORNER_GRID_NONE = "**none** -- every cited record declares the full grid"

_CORNER_GRID_ENTRY = (
    r"`sim/[A-Za-z0-9._-]+/records/[A-Za-z0-9._-]+\.md` "
    r"\((?:\*\*\d+\*\* points?|no PVT point set)\)"
)

# The census sentence check 28 grades. Deliberately free of the phrase
# "current `records/LATEST`", for check 17's reason: spelling it that way
# would enrol this sentence in checks 4/6's pointer-claim census, where it is
# not a citation of anything.
CORNER_GRID_CENSUS_RE = re.compile(
    r"of the \*\*(?P<pairs>\d+)\*\* \(spec row, `sim/` record\) citation pairs "
    r"in Section 4's table, \*\*(?P<full>\d+)\*\* name a record that declares "
    r"the full \*\*(?P<points>\d+)\*\*-point grid, \*\*(?P<subset>\d+)\*\* name "
    r"one that declares a smaller PVT point set, and \*\*(?P<unstated>\d+)\*\* "
    r"name one that declares no PVT point set of its own: (?P<records>"
    + re.escape(CORNER_GRID_NONE)
    + r"|(?:" + _CORNER_GRID_ENTRY + r"(?:, )?)+)\."
)

# One record inside that sentence's exception clause: the record it names and
# the point count it declares, or the absence of one. The count is
# load-bearing rather than decorative -- a row resting on a single nominal
# point is a different claim from one resting on nine, and it is exactly the
# difference the blanket sentence used to erase.
CORNER_GRID_ENTRY_RE = re.compile(
    r"`(?P<record>sim/[A-Za-z0-9._-]+/records/[A-Za-z0-9._-]+\.md)` "
    r"\((?:\*\*(?P<points>\d+)\*\* points?|no PVT point set)\)"
)


# Check 29. The mirror image of check 2. Check 2 grades a path the document
# CITES -- it must exist. This document also, necessarily, makes the opposite
# claim, because Section 7's whole job is to report work that has NOT landed:
# a sub-block that lives only in an unmerged PR, a flow whose records there is
# therefore nothing in this tree to cite. Check 2 made that claim unsayable
# precisely: naming the path would fail it, so the only sayable form was a
# gesture at the parent directory ("no such flow exists under `layout/`") --
# and the vague form is the one that rots silently, because on the day the PR
# merges and the path appears, nothing in this gate can tell.
#
# The marker below buys the precision back. A backticked path immediately
# followed by it is an ASSERTED-ABSENT path: check 2 skips it (it is not a
# citation) and check 29 asserts the absence, so a passage describing work as
# not yet landed fails CI on the day it lands instead of quietly describing a
# tree this repository has moved past.
ABSENT_MARKER = "(not in this tree)"

# The marker must follow the closing backtick immediately -- at most one line
# wrap, no intervening prose -- for the same directional reason checks 4/5
# require an *attached* pointer claim: prose that merely discusses an absence
# somewhere near a path is not this document asserting that path is absent.
ABSENT_CLAIM_RE = re.compile(
    r"`(?P<path>[^`]*)`(?:[ \t]*\n)?[ \t]*" + re.escape(ABSENT_MARKER)
)


# Check 30. Check 26's census is a LAGGING indicator, and on its own it cannot
# tell a reader which of two very different worlds they are in. `layout/`
# records are append-only evidence (`CLAUDE.md`), so "34 of the 67 name the
# `open_pdks` commit" reads identically whether the flows still mint records
# without the pin, or whether every flow was fixed this morning and the 33
# shortfall is history no re-run has yet retired. Section 8 answered that by
# naming the cause in prose -- "four of the eight `layout/` flows' record
# renderers resolve the commit ... and four print only the variant name" --
# and prose is what rots: PR #420 (issue #407, merged 2026-09-25) fixed the
# other four and the ERC flow, and nothing in this gate could see that the
# explanation had gone false while every number beside it stayed true. This
# check grades the LEADING indicator instead, in both directions, so neither
# an entry point that starts resolving the commit nor one that stops can drift
# away from the sentence that explains check 26's numbers.
RENDERER_REPORT_GLOB = "layout/*/reports"
RENDERER_ERC_GLOB = "layout/*/erc-reports"

# Which file mints a record tree's `record.md`, by the convention this
# repository follows uniformly: a flow-local renderer where the flow has one,
# the shared renderer otherwise (`layout/trivial-cell/` has no `bin/` of its
# own), and the ERC driver for an `erc-reports/` tree -- that record.md is
# written by hand from what the script prints, so the script is what has to
# resolve the pin. A record tree whose entry point does not exist is counted
# as not resolving and named in the census, rather than skipped: an
# unattributable record tree is exactly the gap this check is for.
RENDERER_LOCAL = "layout/{flow}/bin/render-record.py"
RENDERER_SHARED = "layout/bin/render-record.py"
RENDERER_ERC = "layout/{flow}/bin/run-erc.sh"

# The shared module a renderer may delegate the whole record body to.
RENDERER_SHARED_MODULE = "layout/bin/_record_common.py"

# That delegation, matched explicitly rather than by "mentions the shared
# module": a renderer importing only `build_argparser` from it delegates no
# provenance at all and must not inherit the shared module's pin.
RENDERER_DELEGATE_RE = re.compile(r"\brender_pnr_drc_lvs_record\b")

# What counts as resolving the commit: a `klt pdk find` invocation (in either
# the argv-list or the shell spelling) or a call to the shared helper that
# wraps one. Deliberately NOT a search for the word "pdk" -- every one of
# these files names a PDK variant, and printing only the variant name is the
# defect.
RENDERER_PIN_RE = re.compile(
    r"\bresolve_pdk_commit\b|[\"']pdk[\"']\s*,\s*[\"']find[\"']|\bpdk find\b"
)

# What the census renders when every entry point resolves the commit -- i.e.
# when the shortfall check 26 counts is purely historical. Spelled out rather
# than left as an empty clause, `CORNER_GRID_NONE`'s reason: the true case has
# to be a statement too, or it reads as a sentence someone forgot to finish.
# The em dash is the document's own punctuation, not this module's: the
# sentence is quoted verbatim into Section 8, and `--stats` has to print
# exactly what the document must contain for the paste to pass.
RENDERER_CENSUS_NONE = "**none** — every entry point resolves it"

_RENDERER_ENTRY = r"`layout/[A-Za-z0-9._/-]+`"

# The census sentence check 30 grades. Deliberately free of the phrase
# "current `…/LATEST`", for check 17's reason: spelling it that way would
# enrol this sentence in checks 4/6's pointer-claim census, where it is not a
# pointer claim.
RENDERER_CENSUS_RE = re.compile(
    r"of the \*\*(?P<entry_points>\d+)\*\* record-minting entry points under "
    r"`layout/`, \*\*(?P<pinning>\d+)\*\* resolve the `open_pdks` commit "
    r"before writing a record and \*\*(?P<naming>\d+)\*\* do not: "
    r"(?P<offenders>"
    + re.escape(RENDERER_CENSUS_NONE)
    + r"|(?:" + _RENDERER_ENTRY + r"(?:, )?)+)"
)

# One entry point inside that sentence's exception clause.
RENDERER_ENTRY_RE = re.compile(r"`(?P<entry>layout/[A-Za-z0-9._/-]+)`")

# Check 31. One `sim/` campaign publishes records that are a subset of an axis
# its RUNNER defines rather than of the PVT grid check 28 grades: the
# supply-impedance campaign's *arms*, the supply-return networks it drives one
# DUT through. `sim/README.md` requires a corner subset to be justified, and
# that campaign's renderer applies the same rule to arms -- it emits an "Arms
# this record does not contain" section, and since issue #409's first
# increment a standing omission note per arm. Section 7's DR-012 item leans on
# exactly that subset: it retires DR-012's "the impedance argument is
# unmeasured" open item by citation while stating that DR-012's *rejected*
# `no-gnd-pad` null option is implemented but never run, so no
# priced-rejected-option claim may be read from the record. Nothing graded
# that sentence. On the day a record prices the null option (issue #409 item
# 2, whose ablation machinery landed 2026-09-25 in PR #429 while the
# several-hour measurement stayed owed) the document would still say the claim
# cannot be read, with every number beside it still true -- check 30's defect
# shape on a different axis, graded the same way and in both directions.
ARM_CAMPAIGN = "supply-impedance-sensitivity"
ARM_RUNNER = f"sim/{ARM_CAMPAIGN}/run_supply_impedance.py"
ARM_POINTER = f"sim/{ARM_CAMPAIGN}/records/LATEST"

# The runner's own arm table, read as source text rather than imported, for
# `report_row_count`'s reason: this gate is a pure file reader. The `name=`
# keyword is anchored to its own line so the nested `bonds=`/`substrate=`
# mappings inside each arm contribute nothing.
ARM_TABLE_RE = re.compile(r"^ARMS\b[^\n]*=\s*\(\s*$", re.M)
ARM_NAME_RE = re.compile(r'^\s+name="(?P<arm>[A-Za-z0-9._-]+)",\s*$', re.M)

# The header line every record of this campaign carries, written by its
# renderer: `- **Arms**: 4 supply-return networks `ideal`, ... x 1 corner
# point(s) = 4 transient runs.` The arms are read from the LIST, never from
# the count in front of it -- the list is what names what ran, and a record
# whose count disagreed with its list must be graded on the names.
ARM_RECORD_RE = re.compile(
    r"- \*\*Arms\*\*: \d+ supply-return networks (?P<arms>[^\n]*?) x \d+ corner"
)
ARM_TOKEN_RE = re.compile(r"`(?P<arm>[A-Za-z0-9._-]+)`")

# What the census renders once every arm has been run -- spelled out rather
# than left as an empty clause, `RENDERER_CENSUS_NONE`'s reason. The em dash
# is the document's own punctuation: `--stats` prints exactly what the
# document must contain for the paste to pass.
ARM_CENSUS_NONE = "**none** — every arm the runner implements has been run"

# The census sentence check 31 grades. Deliberately free of the phrase
# "current `records/LATEST`", for check 17's reason: spelling it that way
# would enrol this sentence in checks 4/6's pointer-claim census, where it is
# not a pointer claim.
ARM_CENSUS_RE = re.compile(
    r"of the \*\*(?P<offered>\d+)\*\* supply-return arms `"
    + re.escape(ARM_RUNNER)
    + r"` implements, the record `"
    + re.escape(ARM_POINTER)
    + r"` names runs \*\*(?P<ran>\d+)\*\* and leaves \*\*(?P<unrun>\d+)\*\* unrun: "
    r"(?P<arms>"
    + re.escape(ARM_CENSUS_NONE)
    + r"|(?:`[A-Za-z0-9._-]+`(?:, )?)+)"
)

# The anchor that makes an *absent* arm census a finding rather than a
# silence, the shape checks 25, 28 and 30 each use: a document that cites this
# campaign at all is citing a record that ran a subset of the runner's arms,
# and the subset is what bounds what the record may be read for. Deleting the
# inconvenient sentence is not a way to widen the citation.
ARM_CENSUS_ANCHOR = f"sim/{ARM_CAMPAIGN}/"


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


def _add_once(misses: list[str], seen: set[str], miss: str) -> None:
    """Append `miss` unless an identical one was already reported here.

    Check 23 grades both halves of a Markdown link (display text and target),
    which agree in the ordinary case -- so the same drift would otherwise be
    reported twice for one citation. A link whose halves genuinely disagree
    still reports both, because the two messages differ.
    """
    if miss not in seen:
        seen.add(miss)
        misses.append(miss)


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


def _own_tree_path(span: str) -> bool:
    """Is `span` a concrete path into one of this repo's own top-level trees?

    Single-sourced because checks 2 and 29 grade the same shape from opposite
    directions -- one demands the path exist, the other demands it not -- and
    a shape one of them recognised and the other did not would be a hole in
    whichever half missed it.
    """
    if not span or re.search(r"\s", span) or "/" not in span:
        return False
    if span.split("/", 1)[0] not in OWN_TOP_LEVEL:
        return False
    # A glob/placeholder is a pattern the prose is talking *about* (e.g.
    # "every `layout/*/reports/LATEST` pointer"), not a path it cites.
    return not (any(ch in span for ch in GLOB_CHARS) or "..." in span)


def absent_claims(text: str) -> list[tuple[int, int, str]]:
    """Every `(line, offset, path)` triple check 29 grades.

    Returned rather than checked inline so check 2 can ask the same scan
    which backticked spans are not citations, and so the test suite can
    exercise the scan directly, as it does for `attached_pointer_claims` and
    `label_claims`. `offset` is the position of the opening backtick, which
    is what `BACKTICK_SPAN_RE` reports for the same span.
    """
    return [
        (
            _line_of(text, match.start()),
            match.start(),
            _unwrap_backticked(match.group("path")),
        )
        for match in ABSENT_CLAIM_RE.finditer(text)
    ]


def check_bare_paths(doc: Path, text: str) -> list[str]:
    """Check 2: every backticked path into this repo's own trees exists."""
    misses = []
    # A path the document asserts is NOT in the tree is not a citation of it,
    # and is check 29's to grade rather than this one's.
    asserted_absent = {offset for _line, offset, _path in absent_claims(text)}
    for match in BACKTICK_SPAN_RE.finditer(text):
        if match.start() in asserted_absent:
            continue
        span = _unwrap_backticked(match.group(1))
        if not _own_tree_path(span):
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


def coverage_index_rows() -> list[tuple[str, str, list[str]]]:
    """`(parameter, claim_class, [experiment])` per row of the coverage index.

    Empty when `sim/spec-coverage.json` is absent or carries no rows, which is
    how check 11 stays inert against the test fixtures; that the real index is
    found and non-empty is asserted by `sim/tests/test_proposal_citations.py`.
    """
    index = _load_json(REPO_ROOT / COVERAGE_INDEX)
    if index is None or not isinstance(index.get("rows"), list):
        return []
    rows: list[tuple[str, str, list[str]]] = []
    for row in index["rows"]:
        if not isinstance(row, dict):
            continue
        benches = row.get("benches")
        experiments = [
            str(bench["experiment"])
            for bench in (benches if isinstance(benches, list) else [])
            if isinstance(bench, dict) and bench.get("experiment")
        ]
        rows.append(
            (
                _normalise_parameter(str(row.get("parameter", ""))),
                str(row.get("claim_class", "")),
                experiments,
            )
        )
    return rows


def _cited_flows(cells: list[str]) -> set[tuple[str, str]]:
    """Every `(top, block)` evidence flow a Section 4 row's cells cite."""
    row = " | ".join(cells)
    return {(cite.group("top"), cite.group("block")) for cite in EVIDENCE_PATH_RE.finditer(row)}


def section_4_flows(text: str) -> dict[str, tuple[int, set[tuple[str, str]]]]:
    """Each Section 4 row's cited flows, with `same record` deferrals resolved.

    A deferring row inherits the flows of the row above it (which may itself
    have inherited), so `| same record |` is read as the citation it stands
    for rather than as no citation at all.
    """
    resolved: dict[str, tuple[int, set[tuple[str, str]]]] = {}
    previous: set[tuple[str, str]] = set()
    for line_number, cells in section_4_table(text)[1]:
        flows = _cited_flows(cells)
        if DEFERRAL_RE.search(" | ".join(cells)):
            flows = flows | previous
        resolved[_normalise_parameter(cells[0])] = (line_number, flows)
        previous = flows
    return resolved


def check_coverage_index_parity(doc: Path, text: str) -> list[str]:
    """Check 11: no Section 4 row ignores a campaign indexed under it."""
    index_rows = coverage_index_rows()
    if not index_rows:
        return []
    rows = section_4_flows(text)
    if not rows:
        return []
    misses = []
    for parameter, claim_class, experiments in index_rows:
        if claim_class not in MEASURED_CLAIM_CLASSES:
            continue
        found = rows.get(parameter)
        if found is None:
            # A spec row absent from Section 4 entirely is check 7's finding.
            continue
        line_number, flows = found
        for experiment in experiments:
            if ("sim", experiment) in flows:
                continue
            misses.append(
                f'{doc.name}:{line_number}: spec row "{parameter}" cites no record '
                f"of `sim/{experiment}/`, which `{COVERAGE_INDEX}` indexes as "
                f"{claim_class} evidence for it -- a row may not be graded while "
                f"ignoring a campaign this repo has indexed under it"
            )
    return misses


def _power_table_section(experiment: str) -> str | None:
    """The `## Power` section of `sim/<experiment>/`'s current record, or None.

    `None` covers all three "nothing to compare against" conditions -- no
    `records/LATEST`, a pointer naming a record that is gone, and a record with
    no Power table -- which checks 12 and 19 report rather than pass silently.
    """
    stamp = _read_pointer("sim", experiment, "records")
    if stamp is None:
        return None
    record = REPO_ROOT / "sim" / experiment / "records" / stamp
    if not record.is_file():
        return None
    text = record.read_text()
    heading = POWER_TABLE_HEADING_RE.search(text)
    if heading is None:
        return None
    section = text[heading.end() :]
    end = re.search(r"^##+\s", section, re.M)
    return section[: end.start()] if end is not None else section


def record_power_terms(experiment: str) -> list[str]:
    """The per-source current columns of a campaign's current Power table.

    `["VDD", "VPWR", ...]` in the record's own column order, read out of the
    table's header row rather than named here -- the terminals a bench has to
    meter are whatever the testbench really sources, and that set moves when
    the block's interface does (DR-010 added `VPWR`, DR-012 added `GND`).
    Empty under the same conditions `_power_table_section` returns None for,
    plus a table whose header carries no `I(<net>)` column at all.
    """
    section = _power_table_section(experiment)
    if section is None:
        return []
    header = re.search(r"^\|(?P<cells>.+)\|\s*$", section.strip(), re.M)
    if header is None:
        return []
    terms = []
    for cell in header.group("cells").split("|"):
        column = POWER_COLUMN_RE.match(cell.strip())
        if column is not None:
            terms.append(column.group("net"))
    return terms


def record_power_table(experiment: str) -> dict[str, float]:
    """`{corner_id: total_power_uW}` from a campaign's current record.

    Read out of the record's own Power table (its last numeric column), so the
    figures check 12 compares against are the record's, never re-derived here.
    Empty when the campaign has no `records/LATEST`, no Power table, or a table
    this parse does not recognise -- all three are "nothing to compare", which
    check 12 reports rather than passing silently.
    """
    section = _power_table_section(experiment)
    if section is None:
        return {}
    table: dict[str, float] = {}
    for row in POWER_TABLE_ROW_RE.finditer(section):
        figures = [cell.strip() for cell in row.group("rest").strip().strip("|").split("|")]
        if not figures:
            continue
        try:
            table[row.group("corner").strip()] = float(figures[-1])
        except ValueError:
            continue
    return table


def power_readout(experiment: str) -> dict | None:
    """The min/typ/max power readout of `sim/<experiment>/`'s current record."""
    table = record_power_table(experiment)
    if not table or NOMINAL_CORNER not in table:
        return None
    lowest = min(table, key=lambda corner: table[corner])
    highest = max(table, key=lambda corner: table[corner])
    return {
        "min": table[lowest],
        "min_corner": lowest,
        "typ": table[NOMINAL_CORNER],
        "typ_corner": NOMINAL_CORNER,
        "max": table[highest],
        "max_corner": highest,
        "corners": len(table),
    }


def power_terms_sentence(experiment: str, terms: list[str]) -> str:
    """That term list in exactly the form check 19 part (c) matches."""
    return (
        f"a sum over the **{len(terms)}** current columns of "
        f"`sim/{experiment}/records/LATEST`'s own Power table — "
        + ", ".join(f"`I({net})`" for net in terms)
    )


def power_sentence(readout: dict) -> str:
    """The readout in the form check 12 matches -- `--stats` prints this."""
    return (
        f"min **{readout['min']:.3f} µW** at `{readout['min_corner']}`, "
        f"typ **{readout['typ']:.3f} µW** at `{readout['typ_corner']}`, "
        f"max **{readout['max']:.3f} µW** at `{readout['max_corner']}`, "
        f"over **{readout['corners']}** corners"
    )


def check_power_readout(doc: Path, text: str) -> list[str]:
    """Check 12: a stated power readout must be the record's own figures."""
    misses = []
    for line_number, row in spec_table_rows(text):
        stated = POWER_READOUT_RE.search(row)
        if stated is None:
            continue
        cells = _row_cells(row)
        parameter = _normalise_parameter(cells[0])
        readouts = [
            (block, power_readout(block))
            for top, block in sorted(_cited_flows(cells))
            if top == "sim"
        ]
        live = [(block, readout) for block, readout in readouts if readout is not None]
        if not live:
            misses.append(
                f'{doc.name}:{line_number}: row "{parameter}" states a power '
                f"readout, but none of the `sim/` campaigns it cites has a current "
                f"`records/LATEST` record carrying a Power table to check it "
                f"against -- cite the campaign the figures came from"
            )
            continue
        experiment, readout = live[0]
        for field in POWER_READOUT_FIGURES:
            if abs(float(stated.group(field)) - readout[field]) > 5e-4:
                misses.append(
                    f'{doc.name}:{line_number}: row "{parameter}" states '
                    f"{field}={stated.group(field)} µW, but "
                    f"`sim/{experiment}/`'s current record reports "
                    f"{field}={readout[field]:.3f} µW -- restate it from `python3 "
                    f"docs/chipalooza/check_proposal_citations.py --stats`"
                )
        for field in POWER_READOUT_NAMES:
            if stated.group(field) != readout[field]:
                misses.append(
                    f'{doc.name}:{line_number}: row "{parameter}" states '
                    f"{field}=`{stated.group(field)}`, but `sim/{experiment}/`'s "
                    f"current record reports {field}=`{readout[field]}`"
                )
        if int(stated.group("corners")) != readout["corners"]:
            misses.append(
                f'{doc.name}:{line_number}: row "{parameter}" states the readout is '
                f"over {stated.group('corners')} corners, but `sim/{experiment}/`'s "
                f"current record's Power table has {readout['corners']}"
            )
    return misses


def area_readout(block: str) -> dict | None:
    """The live bounding-box readout of `layout/<block>/`'s current report.

    `None` when the flow has no `reports/LATEST`, or that record carries no
    readable `compose.json` with a top-level `bbox_um` -- there is nothing for
    check 13 to compare against, which is a different (and separately
    reported) condition from a readout that disagrees. A degenerate box (zero
    or negative extent) is treated the same way: it is not a composition this
    document could be quoting.
    """
    stamp = _pointer_stamp("layout", block)
    if stamp is None:
        return None
    report = REPO_ROOT / "layout" / block / "reports" / stamp
    compose = _load_json(report / COMPOSE_ARTEFACT)
    if compose is None:
        return None
    cell = compose.get("cell_name")
    bbox = compose.get("bbox_um")
    if not isinstance(cell, str) or not cell or not isinstance(bbox, dict):
        return None
    try:
        coords = {key: float(bbox[key]) for key in AREA_BBOX_KEYS}
    except (KeyError, TypeError, ValueError):
        return None
    width = coords["x1"] - coords["x0"]
    height = coords["y1"] - coords["y0"]
    if width <= 0 or height <= 0:
        return None
    return {
        **coords,
        "cell": cell,
        "width": width,
        "height": height,
        # µm × µm -> mm², which is the unit the document quotes the area in.
        "area_mm2": width * height / 1e6,
    }


def _area_figure(value: float | str) -> str:
    """One area figure as it is stated and compared -- a formatted string.

    Comparing formatted text rather than floats with a tolerance is what makes
    a `--stats` paste unconditionally safe: a figure that lands exactly on a
    rounding boundary formats one way and only one way, so the sentence the
    generator prints can never be the sentence the checker rejects.
    """
    if isinstance(value, str):
        value = float(value.replace("−", "-"))
    return f"{value:.{AREA_DECIMALS}f}"


def area_sentence(block: str, readout: dict) -> str:
    """The area readout in the form check 13 matches -- `--stats` prints this."""
    return (
        f"the composed cell `{readout['cell']}` on the record "
        f"`layout/{block}/reports/LATEST` resolves to spans "
        f"**{_area_figure(readout['x0'])}** µm to **{_area_figure(readout['x1'])}** "
        f"µm in x and **{_area_figure(readout['y0'])}** µm to "
        f"**{_area_figure(readout['y1'])}** µm in y, i.e. "
        f"**{_area_figure(readout['width'])}** µm × "
        f"**{_area_figure(readout['height'])}** µm ≈ "
        f"**{_area_figure(readout['area_mm2'])}** mm²"
    )


def check_area_readout(doc: Path, text: str) -> list[str]:
    """Check 13: a stated area readout must be the composition's own extent."""
    misses = []
    for line_number, row in spec_table_rows(text):
        stated = AREA_READOUT_RE.search(row)
        if stated is None:
            continue
        cells = _row_cells(row)
        parameter = _normalise_parameter(cells[0])
        block = stated.group("flow").split("/", 1)[1]
        where = f"{doc.name}:{line_number}"
        actual = area_readout(block)
        if actual is None:
            misses.append(
                f'{where}: row "{parameter}" states an area readout for '
                f"`layout/{block}/`, but that flow has no `reports/LATEST` record "
                f"carrying a `{COMPOSE_ARTEFACT}` with a top-level `bbox_um` to "
                f"read it out of"
            )
            continue
        if ("layout", block) not in _cited_flows(cells):
            misses.append(
                f'{where}: row "{parameter}" states an area readout for '
                f"`layout/{block}/`, but cites no record of that flow -- cite the "
                f"composition the figures were read out of"
            )
        if stated.group("cell") != actual["cell"]:
            misses.append(
                f'{where}: row "{parameter}" states the composed cell is '
                f"`{stated.group('cell')}`, but `layout/{block}/`'s current "
                f"`{COMPOSE_ARTEFACT}` names `{actual['cell']}`"
            )
        for field in AREA_READOUT_FIGURES:
            claimed = _area_figure(stated.group(field))
            expected = _area_figure(actual[field])
            if claimed == expected:
                continue
            misses.append(
                f'{where}: row "{parameter}" states {field}={claimed} for '
                f"`layout/{block}/`, but that flow's current `{COMPOSE_ARTEFACT}` "
                f"gives {field}={expected} -- restate it from `python3 "
                f"docs/chipalooza/check_proposal_citations.py --stats`"
            )
    return misses


def _gds_fingerprint(path: Path) -> str | None:
    """A timestamp-independent digest of a GDS stream, or `None` if unreadable.

    GDS is a flat sequence of length-prefixed records. Every one of them is
    hashed verbatim except the two whose payload is a wall-clock timestamp
    (`GDS_TIMESTAMP_RECORDS`), whose payload is dropped -- those move on every
    write and describe nothing about the layout.

    The digest is deliberately *exact* on everything else, element ordering
    included: two records of the same flow that hold geometrically equivalent
    but differently-ordered GDS are reported as different here, which is the
    conservative direction (a false "superseded" is re-checked by hand; a
    false "current" would hide a real input drift). Confirming that two such
    records really are geometrically equivalent needs a layer-by-layer XOR,
    which needs `klayout` -- not available in the headless CI job this script
    runs in, and not what this check claims to do.

    `None` on any malformed or truncated stream, so a file this parser cannot
    read is never silently equal to another one it also cannot read.
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if not raw:
        return None
    digest = hashlib.sha256()
    offset = 0
    while offset < len(raw):
        if offset + GDS_HEADER_SIZE > len(raw):
            return None
        length, record, datatype = GDS_HEADER.unpack_from(raw, offset)
        if length < GDS_HEADER_SIZE or offset + length > len(raw):
            return None
        payload = (
            b""
            if record in GDS_TIMESTAMP_RECORDS
            else raw[offset + GDS_HEADER_SIZE : offset + length]
        )
        digest.update(GDS_HEADER.pack(len(payload) + GDS_HEADER_SIZE, record, datatype))
        digest.update(payload)
        offset += length
    return digest.hexdigest()


def composition_inputs(block: str) -> list[str] | None:
    """The cells `layout/<block>/`'s current composition composes in, in order.

    Read off `compose.json`'s own `blocks` list rather than a list here, so a
    sub-block added to (or dropped from) the composition is discovered instead
    of remembered. Generated blocks (the routing cell) are excluded by their
    own `source` field: they are produced during the run and have no upstream
    record to trace back to.

    `None` when the flow has no `reports/LATEST` or no readable composition --
    the same "nothing to compare against" condition check 13 reports.
    """
    stamp = _pointer_stamp("layout", block)
    if stamp is None:
        return None
    compose = _load_json(REPO_ROOT / "layout" / block / "reports" / stamp / COMPOSE_ARTEFACT)
    if compose is None:
        return None
    blocks = compose.get("blocks")
    if not isinstance(blocks, list):
        return None
    cells = []
    for entry in blocks:
        if not isinstance(entry, dict) or entry.get("source") != COMPOSITION_CELL_SOURCE:
            continue
        cell = entry.get("id")
        if isinstance(cell, str) and cell:
            cells.append(cell)
    return cells


def composition_input_provenance(block: str, cell: str, flow: str) -> dict | None:
    """Which records of `layout/<flow>/` the composed `<cell>.gds` reproduces.

    `block` is the *composing* flow; `flow` is the sub-block flow the document
    says that input came from. Returns the record stamps whose own `<cell>.gds`
    fingerprints identically, the newest of them, and what `layout/<flow>/`'s
    pointer names today. `None` when the composed copy itself cannot be read --
    distinct from reading it and matching nothing, which is a finding.
    """
    stamp = _pointer_stamp("layout", block)
    if stamp is None:
        return None
    fingerprint = _gds_fingerprint(
        REPO_ROOT / "layout" / block / "reports" / stamp / f"{cell}.gds"
    )
    if fingerprint is None:
        return None
    reports = REPO_ROOT / "layout" / flow / "reports"
    matches = []
    if reports.is_dir():
        for record in sorted(entry for entry in reports.iterdir() if entry.is_dir()):
            candidate = record / f"{cell}.gds"
            if candidate.is_file() and _gds_fingerprint(candidate) == fingerprint:
                matches.append(record.name)
    latest = _pointer_stamp("layout", flow)
    return {
        "matched": len(matches),
        "matches": matches,
        # Record stamps are `YYYYMMDD-HHMMSS-<sha>`, so lexical order is
        # chronological order; the newest match is the one a reader would
        # otherwise have to find by hand.
        "newest": matches[-1] if matches else None,
        "latest": latest,
        "status": (
            COMPOSITION_INPUT_CURRENT
            if latest is not None and latest in matches
            else COMPOSITION_INPUT_SUPERSEDED
        ),
    }


def composition_input_sentence(block: str, cell: str, flow: str, provenance: dict) -> str:
    """The provenance in exactly the sentence form `COMPOSITION_INPUT_RE` matches.

    Used by `--stats`, so the fix for a check-14 finding is a paste rather than
    a hand transcription -- the same guard checks 9, 12 and 13 each carry.
    """
    return (
        f"the composition on `layout/{block}/reports/LATEST` embeds a `{cell}.gds` "
        f"that reproduces **{provenance['matched']}** "
        f"record{'' if provenance['matched'] == 1 else 's'} of `layout/{flow}/`, "
        f"newest `{provenance['newest']}`, while `reports/LATEST` there names "
        f"`{provenance['latest']}`: **{provenance['status']}**."
    )


def _source_flow_of(block: str, cell: str) -> str | None:
    """Which `layout/` flow's own records a composed `<cell>.gds` comes from.

    Used only by `--stats`, which has no document to read the flow name off.
    Every flow but the composing one is searched -- its own older records hold
    copies of the same input files, and would match ambiguously. A flow whose
    pointer is among the matches wins over one that only matches an older
    record, so the sentence `--stats` prints names the flow the input is
    actually current against when there is one.
    """
    best: str | None = None
    for pointer in sorted(REPO_ROOT.glob("layout/*/reports/LATEST")):
        flow = pointer.parent.parent.name
        if flow == block:
            continue
        provenance = composition_input_provenance(block, cell, flow)
        if provenance is None or not provenance["matches"]:
            continue
        if provenance["status"] == COMPOSITION_INPUT_CURRENT:
            return flow
        if best is None:
            best = flow
    return best


def check_composition_inputs(doc: Path, text: str) -> list[str]:
    """Check 14: a composed input must be traced to a record of its own flow."""
    collapsed, offsets = _collapse_quoted_prose(text)
    misses = []
    stated: dict[str, set[str]] = {}
    for claim in COMPOSITION_INPUT_RE.finditer(collapsed):
        block = claim.group("composition").split("/", 1)[1]
        flow = claim.group("flow").split("/", 1)[1]
        cell = claim.group("cell")
        where = f"{doc.name}:{_line_of(text, offsets[claim.start()])}"
        stated.setdefault(block, set()).add(cell)

        cells = composition_inputs(block)
        if cells is None:
            misses.append(
                f"{where}: the composition-input readout names `layout/{block}/`, but "
                f"that flow has no `reports/LATEST` record carrying a "
                f"`{COMPOSE_ARTEFACT}` whose composed blocks could be listed"
            )
            continue
        if cell not in cells:
            misses.append(
                f"{where}: the composition-input readout states `{cell}.gds` for "
                f"`layout/{block}/`, but that flow's current `{COMPOSE_ARTEFACT}` "
                f"composes no such block ({', '.join(cells) or 'none'})"
            )
            continue

        provenance = composition_input_provenance(block, cell, flow)
        if provenance is None:
            misses.append(
                f"{where}: the composition-input readout states `{cell}.gds` for "
                f"`layout/{block}/`, but that flow's current record carries no "
                f"readable `{cell}.gds` to fingerprint"
            )
            continue
        if not provenance["matches"]:
            misses.append(
                f"{where}: the `{cell}.gds` embedded in `layout/{block}/`'s current "
                f"composition reproduces NO record of `layout/{flow}/` -- it was "
                f"composed from something this repository does not keep, or from "
                f"another flow entirely; do not restate the readout without "
                f"establishing where it came from"
            )
            continue

        for field in ("matched", "newest", "latest", "status"):
            claimed: object = claim.group(field)
            expected = provenance[field]
            if field == "matched":
                claimed = int(claimed)
            if claimed != expected:
                misses.append(
                    f"{where}: the composition-input readout for `{cell}.gds` says "
                    f"{field}={claimed}, but `layout/{block}/`'s current composition "
                    f"against `layout/{flow}/` gives {field}={expected} -- restate it "
                    f"from `python3 docs/chipalooza/check_proposal_citations.py "
                    f"--stats`"
                )

    # Both directions, as checks 8 and 10 do: a document that states some of a
    # composition's inputs must state all of them. Dropping the line for the
    # one input that went superseded is otherwise the cheapest way to make this
    # readout look clean.
    for block, named in stated.items():
        cells = composition_inputs(block)
        for cell in cells or []:
            if cell in named:
                continue
            misses.append(
                f"{doc.name}: `layout/{block}/`'s current composition embeds "
                f"`{cell}.gds`, but this document states no composition-input "
                f"readout for it -- state every composed input or none"
            )
    return misses


def decision_record_status(name: str) -> str | None:
    """The status word `spec/decision-records/<name>` states about itself.

    Read off the record's own `- **Status**:` field, lower-cased, with the
    bold markers and the em-dash rationale after it dropped. `None` when the
    file is absent or states no status field at all -- distinct from stating
    one this document disagrees with, which is a finding.
    """
    path = REPO_ROOT.joinpath(*DECISION_RECORDS_DIR, name)
    if not path.is_file():
        return None
    stated = DECISION_RECORD_STATUS_RE.search(path.read_text())
    return stated.group("status").lower() if stated else None


def decision_records() -> dict[str, str | None]:
    """Every decision record in the tree, mapped to its own status word.

    Enumerated from the directory rather than from a list here, so a record
    added (or renamed) is discovered instead of remembered. `TEMPLATE.md` is
    excluded by its own file-name shape -- it carries no DR number.
    """
    directory = REPO_ROOT.joinpath(*DECISION_RECORDS_DIR)
    if not directory.is_dir():
        return {}
    return {
        entry.name: decision_record_status(entry.name)
        for entry in sorted(directory.iterdir())
        if entry.is_file() and DECISION_RECORD_FILE_RE.fullmatch(entry.name)
    }


def decision_record_sentence(name: str, status: str | None) -> str:
    """A record's status in exactly the form `DECISION_RECORD_READOUT_RE` matches.

    Used by `--stats`, so the fix for a check-15 finding is a paste rather
    than a hand transcription -- the same guard checks 9, 12, 13 and 14 carry.
    """
    number = DECISION_RECORD_FILE_RE.fullmatch(name).group("number")
    return (
        f"**DR-{number}** (`spec/decision-records/{name}`) is "
        f"**{status if status else 'unstated'}**."
    )


def check_decision_record_status(doc: Path, text: str) -> list[str]:
    """Check 15: a stated decision-record status must be the record's own."""
    collapsed, offsets = _collapse_quoted_prose(text)
    records = decision_records()
    misses = []
    stated: set[str] = set()

    for claim in DECISION_RECORD_READOUT_RE.finditer(collapsed):
        name = claim.group("file")
        where = f"{doc.name}:{_line_of(text, offsets[claim.start()])}"
        stated.add(name)

        if name not in records:
            misses.append(
                f"{where}: the decision-record readout names "
                f"`spec/decision-records/{name}`, which this repository does "
                f"not carry -- restate it from `python3 "
                f"docs/chipalooza/check_proposal_citations.py --stats`"
            )
            continue

        # The number and the file are stated separately on purpose: this tree
        # carries two DR-004s and two DR-007s, so a line that pairs one
        # number with the other's file reads as true and is not.
        number = DECISION_RECORD_FILE_RE.fullmatch(name).group("number")
        if claim.group("number") != number:
            misses.append(
                f"{where}: the decision-record readout calls "
                f"`{name}` **DR-{claim.group('number')}**, but that file's own "
                f"number is {number}"
            )

        actual = records[name]
        if actual is None:
            misses.append(
                f"{where}: the decision-record readout states a status for "
                f"`{name}`, but that record states no `- **Status**:` field of "
                f"its own to compare against"
            )
            continue
        if claim.group("status") != actual:
            misses.append(
                f"{where}: the decision-record readout says `{name}` is "
                f"**{claim.group('status')}**, but that record's own Status "
                f"field says **{actual}** -- a decision record's status moves "
                f"before `spec/target-spec.md` follows it, so re-grade the rows "
                f"that rest on it rather than restating the old word"
            )

    # Both directions, as checks 8, 10 and 14 do: a document that states one
    # record's status must state them all. Dropping the line for the record
    # that just moved is otherwise the cheapest way to keep the readout clean.
    if stated:
        for name in records:
            if name in stated:
                continue
            misses.append(
                f"{doc.name}: `spec/decision-records/{name}` exists, but this "
                f"document states no decision-record status readout for it -- "
                f"state every record or none"
            )

    # A bare `DR-<n>` in prose names a number, not a file. That is unambiguous
    # only while every record sharing the number agrees about its status; the
    # moment they disagree, every bare reference in this document is a claim
    # the reader cannot resolve.
    by_number: dict[str, set[str | None]] = {}
    for name, status in records.items():
        number = DECISION_RECORD_FILE_RE.fullmatch(name).group("number")
        by_number.setdefault(number, set()).add(status)
    for number in sorted(set(BARE_DECISION_RECORD_RE.findall(text))):
        statuses = by_number.get(number)
        if statuses is None or len(statuses) < 2:
            continue
        files = sorted(
            name
            for name in records
            if DECISION_RECORD_FILE_RE.fullmatch(name).group("number") == number
        )
        misses.append(
            f"{doc.name}: this document refers to `DR-{number}` by bare number, "
            f"but {len(files)} records share it and they no longer agree about "
            f"their status ({', '.join(files)}) -- name the file each reference "
            f"means"
        )
    return misses


def erc_readout(block: str) -> dict | None:
    """The live `klt erc` supply readout of `layout/<block>/`'s current record.

    `None` when the flow has no `erc-reports/LATEST`, or that record carries no
    readable `erc.json` -- there is nothing for check 16 to compare against,
    and that condition is reported by the check rather than silently skipped.

    Per-supply island counts are reconstructed rather than read: `klt erc`
    states an island count only on the failing side, inside the
    `erc.unconnected_net` finding that carries the islands themselves. A
    declared net that was graded (it appears in `erc_coverage.checked`) and has
    no such finding resolved to exactly one island. Reconstructing it here is
    what lets the readout state a PASSING supply table at all -- which is the
    table this document actually carries, and the one that goes stale silently.
    """
    stamp = _read_pointer("layout", block, ERC_POINTER_DIR)
    if stamp is None:
        return None
    stamp = stamp.split("/")[0]
    report = _load_json(
        REPO_ROOT / "layout" / block / ERC_POINTER_DIR / stamp / "erc.json"
    )
    if report is None:
        return None

    coverage = report.get("erc_coverage") or {}
    islands = {}
    for entry in coverage.get("checked") or []:
        graded_net = ERC_NET_COVERAGE_RE.fullmatch(str(entry))
        if graded_net is not None:
            islands[graded_net.group("net")] = 1
    for finding in report.get("erc_findings") or []:
        if not isinstance(finding, dict):
            continue
        net = finding.get("net")
        if finding.get("rule") != ERC_UNCONNECTED_RULE or net not in islands:
            continue
        islands[net] = len(finding.get("islands") or [])

    graded = ERC_GRADED_RE.search(str(report.get("file") or ""))
    latest = _pointer_stamp("layout", block)
    return {
        "erc_status": report.get("erc_status"),
        "finding_count": report.get("erc_finding_count"),
        "islands": islands,
        "graded": graded.group("stamp") if graded else None,
        "latest": latest,
        "status": _erc_status_word(block, report, graded, latest),
    }


def _erc_status_word(
    block: str, report: dict, graded: re.Match | None, latest: str | None
) -> str:
    """`current` only if the ERC verdict grades the bytes `reports/LATEST` holds.

    Both halves are required, and the second is the one that matters: a stamp
    comparison alone would call an ERC record current while the layout record
    it names had been rebuilt under it. `klt erc` records the graded stream's
    own sha256, and `run-erc.sh` asserts it at run time, so the comparison here
    is against the same number the tool itself pinned -- not a re-derivation.

    Anything unreadable (a missing `file` field, a stream this checker cannot
    open, an absent hash) reads as `stale`: the conservative direction, since a
    false `current` would let an ungraded layout pass as power-delivery-checked
    while a false `stale` is re-checked by hand.
    """
    if graded is None or latest is None or graded.group("stamp") != latest:
        return ERC_STALE
    stated_hash = ((report.get("provenance") or {}).get("input") or {}).get(
        "content_hash"
    )
    if not isinstance(stated_hash, str) or not stated_hash.startswith(ERC_HASH_PREFIX):
        return ERC_STALE
    stream = (
        REPO_ROOT / "layout" / block / "reports" / latest / graded.group("artefact")
    )
    try:
        digest = hashlib.sha256(stream.read_bytes()).hexdigest()
    except OSError:
        return ERC_STALE
    return (
        ERC_CURRENT
        if digest == stated_hash[len(ERC_HASH_PREFIX) :]
        else ERC_STALE
    )


def erc_sentence(block: str, readout: dict) -> str:
    """The ERC readout in exactly the sentence form `ERC_READOUT_RE` matches.

    Used by `--stats` so the fix for a check-16 failure is a paste, as it is
    for checks 9, 12, 13, 14 and 15.
    """
    islands = ", ".join(
        f"`{net}` **{count}**" for net, count in sorted(readout["islands"].items())
    )
    return (
        f"on the record `layout/{block}/erc-reports/LATEST` resolves to, `klt erc` "
        f"reports `erc_status` **{readout['erc_status']}** with "
        f"**{readout['finding_count']}** findings; the declared supplies resolve "
        f"to {islands} electrical islands; and it grades "
        f"`{readout['graded']}`, while `reports/LATEST` there names "
        f"`{readout['latest']}`: **{readout['status']}**."
    )


def check_erc_readout(doc: Path, text: str) -> list[str]:
    """Check 16: a stated ERC supply readout must be the current record's own."""
    collapsed, offsets = _collapse_quoted_prose(text)
    misses = []
    for stated in ERC_READOUT_RE.finditer(collapsed):
        block = stated.group("flow").split("/", 1)[1]
        where = f"{doc.name}:{_line_of(text, offsets[stated.start()])}"
        actual = erc_readout(block)
        if actual is None:
            misses.append(
                f"{where}: the ERC supply readout names `layout/{block}/`, but "
                f"that flow has no `{ERC_POINTER_DIR}/LATEST` record carrying a "
                f"readable `erc.json` to read it out of"
            )
            continue

        for field in ("erc_status", "finding_count", "graded", "latest", "status"):
            expected = actual[field]
            claimed: object = stated.group(field)
            if isinstance(expected, int):
                claimed = int(claimed)
            if claimed != expected:
                misses.append(
                    f"{where}: the ERC supply readout for `layout/{block}/` says "
                    f"{field}={claimed}, but that flow's current ERC record "
                    f"reports {field}={expected} -- restate it from `python3 "
                    f"docs/chipalooza/check_proposal_citations.py --stats`"
                )

        # Both directions, as checks 8, 10, 14 and 15 do. A supply that drops
        # out of the spec's `nets[]` -- the cheapest way to make a failing
        # continuity table read clean -- is a finding here, not a silence.
        claimed_islands = {
            pair.group("net"): int(pair.group("islands"))
            for pair in ERC_ISLAND_RE.finditer(stated.group("islands"))
        }
        for net in sorted(set(claimed_islands) | set(actual["islands"])):
            claimed_count = claimed_islands.get(net)
            actual_count = actual["islands"].get(net)
            if claimed_count == actual_count:
                continue
            misses.append(
                f"{where}: the ERC supply readout for `layout/{block}/` states "
                f"supply `{net}` at {claimed_count} island(s), but that flow's "
                f"current ERC record reports {actual_count} -- restate it from "
                f"`python3 docs/chipalooza/check_proposal_citations.py --stats`"
            )
    return misses


def _t1_pointer_stamp(pointer: str) -> str | None:
    """The record stamp a `layout/<block>/<tree>/LATEST` pointer names.

    Not `_pointer_stamp`: that one resolves a tree from a top-level directory
    name (`sim` -> `records`, `layout` -> `reports`) and so cannot address
    `erc-reports/` at all. Here the pointer path is already known -- it came
    out of the manifest's own citation -- so it is read directly.
    """
    path = REPO_ROOT / pointer
    if not path.is_file():
        return None
    value = path.read_text().strip()
    return value.split("/")[0].removesuffix(".md") or None


def _t1_manifest_citations(manifest: dict) -> list[tuple[str, str]]:
    """Every `(pointer, stamp)` pair the manifest's evidence entries cite.

    Walked rather than indexed by item id: `evidence` is keyed by item in one
    of two shapes here (a single citation object, or a list of them), and a
    future item may add either. Unique and sorted, so the sentence's order is
    stable -- and a pointer cited twice at two different stamps states both
    pairs, each then compared against that pointer on its own, where at most
    one of them can be current.
    """
    found: set[tuple[str, str]] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            named = node.get("file")
            if isinstance(named, str):
                cited = T1_CITED_PATH_RE.match(named)
                if cited is not None:
                    found.add(
                        (cited.group("pointer") + "/LATEST", cited.group("stamp"))
                    )
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(manifest.get("evidence"))
    return sorted(found)


def t1_readout() -> dict | None:
    """The live T1 sign-off verdict `signoff/` currently records.

    `None` when either half is missing or unparseable -- there is nothing for
    check 17 to compare against, and that condition is reported by the check
    rather than silently skipped, exactly as check 16 handles a flow with no
    ERC record.

    The verdict word is deliberately `stale` when the manifest cites no
    `layout/` record at all: a sign-off that rests on nothing from this
    repository's layout trees cannot be *current* with them, and calling it so
    would be a vacuous green.
    """
    report = _load_json(REPO_ROOT / T1_REPORT)
    manifest = _load_json(REPO_ROOT / T1_MANIFEST)
    if report is None or manifest is None:
        return None

    failed = sorted(
        (item["id"], item["partition"])
        for item in report.get("items") or []
        if isinstance(item, dict)
        and item.get("reason") == T1_CHECK_FAILED
        and item.get("tier") == T1_TIER
        and isinstance(item.get("id"), int)
        and isinstance(item.get("partition"), str)
    )
    cited = [
        (pointer, stamp, _t1_pointer_stamp(pointer) or T1_NO_RECORD)
        for pointer, stamp in _t1_manifest_citations(manifest)
    ]
    tier = report.get("tier")
    return {
        "version": str((report.get("build") or {}).get("package_version")),
        "met": report.get("t1_met_count"),
        "total": report.get("t1_item_count"),
        "tier": T1_NO_TIER if tier is None else str(tier),
        "failed": failed,
        "cited": cited,
        "status": (
            T1_CURRENT
            if cited and all(stamp == latest for _, stamp, latest in cited)
            else T1_STALE
        ),
    }


def t1_sentence(readout: dict) -> str:
    """The T1 readout in exactly the sentence form `T1_READOUT_RE` matches.

    Used by `--stats` so the fix for a check-17 failure is a paste, as it is
    for checks 9, 12, 13, 14, 15 and 16.
    """
    failed = (
        ", ".join(f"`{item} {partition}`" for item, partition in readout["failed"])
        or "**none**"
    )
    cited = (
        ", ".join(
            f"`{pointer}` at **{stamp}** against a pointer naming **{latest}**"
            for pointer, stamp, latest in readout["cited"]
        )
        or "**none**"
    )
    return (
        f"on the report `signoff/t1-report.json`, `klt signoff` "
        f"**{readout['version']}** grades **{readout['met']}** of "
        f"**{readout['total']}** T1 items met, block tier **{readout['tier']}**; "
        f"the items whose cited evidence was read and still failed are {failed}; "
        f"and its manifest cites {cited}: **{readout['status']}**."
    )


def check_t1_readout(doc: Path, text: str) -> list[str]:
    """Check 17: a stated T1 sign-off readout must be the committed report's own."""
    collapsed, offsets = _collapse_quoted_prose(text)
    misses = []
    for stated in T1_READOUT_RE.finditer(collapsed):
        where = f"{doc.name}:{_line_of(text, offsets[stated.start()])}"
        actual = t1_readout()
        if actual is None:
            misses.append(
                f"{where}: the T1 sign-off readout names "
                f"`{T1_REPORT.as_posix()}`, but this repository has no readable "
                f"`{T1_REPORT.as_posix()}` and `{T1_MANIFEST.as_posix()}` pair "
                f"to read it out of"
            )
            continue

        for field in ("version", "met", "total", "tier", "status"):
            expected = actual[field]
            claimed: object = stated.group(field)
            if isinstance(expected, int):
                claimed = int(claimed)
            if claimed != expected:
                misses.append(
                    f"{where}: the T1 sign-off readout says {field}={claimed}, "
                    f"but `{T1_REPORT.as_posix()}` reports {field}={expected} -- "
                    f"restate it from `python3 "
                    f"docs/chipalooza/check_proposal_citations.py --stats`"
                )

        # Both directions, as checks 8, 10, 14, 15 and 16 do. An item that
        # starts failing and is left out of the list is as much a finding as a
        # listed item that has since started passing: dropping a row is the
        # cheapest way to make a scorecard read better than it is.
        claimed_failed = {
            (int(pair.group("item")), pair.group("partition"))
            for pair in T1_FAILED_ITEM_RE.finditer(stated.group("failed"))
        }
        for item, partition in sorted(claimed_failed ^ set(actual["failed"])):
            stated_here = (item, partition) in claimed_failed
            misses.append(
                f"{where}: the T1 sign-off readout "
                f"{'lists' if stated_here else 'omits'} item {item} "
                f"({partition}) as graded-and-failed, but "
                f"`{T1_REPORT.as_posix()}` reports its reason as "
                f"{'not ' if stated_here else ''}`{T1_CHECK_FAILED}` -- restate "
                f"it from `python3 "
                f"docs/chipalooza/check_proposal_citations.py --stats`"
            )

        # Likewise both directions on the records the verdict rests on. This
        # is the half `signoff/check_evidence_hashes.py` structurally cannot
        # cover: it re-hashes each cited artefact against the file on disk, so
        # a manifest pinned to a superseded-but-still-committed record passes
        # it, every hash intact, while the sign-off grades a layout this
        # repository no longer builds.
        claimed_cited = {
            (pair.group("pointer"), pair.group("cited"), pair.group("latest"))
            for pair in T1_CITED_RE.finditer(stated.group("cited"))
        }
        for pointer, cited, latest in sorted(claimed_cited ^ set(actual["cited"])):
            stated_here = (pointer, cited, latest) in claimed_cited
            misses.append(
                f"{where}: the T1 sign-off readout "
                f"{'states' if stated_here else 'omits'} `{pointer}` cited at "
                f"{cited} against a pointer naming {latest}, which is not what "
                f"`{T1_MANIFEST.as_posix()}` and that pointer report -- restate "
                f"it from `python3 "
                f"docs/chipalooza/check_proposal_citations.py --stats`"
            )
    return misses


def _flow_record_count(top: str, block: str) -> int:
    """How many records `<top>/<block>/` holds, in that tree's own shape.

    A `sim/` campaign's records are `records/<stamp>.md` files; a `layout/`
    flow's are `reports/<stamp>/` directories. Counted rather than taken on
    trust because it is the number that says how big an ungraded citation
    really is: one record is a flow with nothing to be stale against, twelve
    is a flow whose cited record nothing re-derives.
    """
    pointer_dir = REPO_ROOT / top / block / POINTER_DIR_BY_TOP_LEVEL[top]
    if not pointer_dir.is_dir():
        return 0
    if top == "sim":
        return sum(1 for path in pointer_dir.glob("*.md") if path.is_file())
    return sum(1 for path in pointer_dir.iterdir() if path.is_dir())


def freshness_coverage(text: str) -> dict:
    """How much of Section 4's table check 3 actually grades.

    Check 3 resolves "the current record" of a cited flow from that flow's own
    `LATEST` pointer, and skips -- silently, and correctly, since there is
    nothing to be stale against -- any flow that publishes none. That makes
    the *scope* of the document's headline freshness claim a volatile fact
    about this repository's trees rather than about the document, and nothing
    re-derived it: a row citing a pointerless campaign reads exactly like a
    graded one.

    Counted per (row, flow) pair rather than per citation, because that is the
    unit check 3 evaluates: a row citing three stamps of one flow is one
    verdict about one flow, not three.
    """
    pairs = {
        (line_number, cite.group("top"), cite.group("block"))
        for line_number, row in spec_table_rows(text)
        for cite in EVIDENCE_PATH_RE.finditer(row)
    }
    ungraded = [
        (top, block) for _, top, block in pairs if _pointer_stamp(top, block) is None
    ]
    return {
        "pairs": len(pairs),
        "graded": len(pairs) - len(ungraded),
        "ungraded": len(ungraded),
        "flows": [
            (f"{top}/{block}", _flow_record_count(top, block))
            for top, block in sorted(set(ungraded))
        ],
    }


def freshness_coverage_sentence(coverage: dict) -> str:
    """That census in exactly the sentence form `FRESHNESS_COVERAGE_RE` matches.

    Used by `--stats` so the fix for a check-18 failure is a paste, as it is
    for checks 6, 9, 12, 13, 14, 15, 16 and 17.
    """
    flows = (
        ", ".join(
            f"`{flow}` (**{count}** record{'' if count == 1 else 's'})"
            for flow, count in coverage["flows"]
        )
        or FRESHNESS_NONE
    )
    return (
        f"of the **{coverage['pairs']}** (spec row, evidence flow) citation "
        f"pairs in Section 4's table, **{coverage['graded']}** name a flow "
        "that publishes a `LATEST` pointer and are therefore freshness-checked "
        f"by check 3; the remaining **{coverage['ungraded']}** name a flow that "
        f"publishes none, whose current record nothing grades: {flows}."
    )


def check_freshness_coverage(doc: Path, text: str) -> list[str]:
    """Check 18: the stated coverage of check 3 over Section 4 must be the real one."""
    collapsed, offsets = _collapse_quoted_prose(text)
    misses = []
    for stated in FRESHNESS_COVERAGE_RE.finditer(collapsed):
        where = f"{doc.name}:{_line_of(text, offsets[stated.start()])}"
        actual = freshness_coverage(text)
        for field in ("pairs", "graded", "ungraded"):
            claimed = int(stated.group(field))
            if claimed != actual[field]:
                misses.append(
                    f"{where}: the Section 4 freshness-coverage census says "
                    f"{field}={claimed}, but this document's live census is "
                    f"{field}={actual[field]} -- restate it from `python3 "
                    f"docs/chipalooza/check_proposal_citations.py --stats`"
                )

        # Both directions, as checks 8, 10, 14, 15, 16 and 17 do. A flow that
        # starts publishing a pointer and is left in the list overstates the
        # hole; a flow that loses its pointer -- or that a newly added row
        # starts citing -- and is left out understates it, which is the
        # direction that matters. Shrinking this list is the cheapest way to
        # make the gate's coverage read better than it is.
        claimed_flows = {
            (flow.group("flow"), int(flow.group("records")))
            for flow in FRESHNESS_FLOW_RE.finditer(stated.group("flows"))
        }
        for flow, count in sorted(claimed_flows ^ set(actual["flows"])):
            stated_here = (flow, count) in claimed_flows
            misses.append(
                f"{where}: the Section 4 freshness-coverage census "
                f"{'lists' if stated_here else 'omits'} `{flow}` at **{count}** "
                f"record(s) as cited-but-ungraded, which is not what this "
                f"repository's own trees report -- restate it from `python3 "
                f"docs/chipalooza/check_proposal_citations.py --stats`"
            )
    return misses


def test_plan_section(text: str) -> tuple[int, str] | None:
    """`(heading_line, body)` of Section 5, the bench test plan, or None."""
    heading = TEST_PLAN_HEADING_RE.search(text)
    if heading is None:
        return None
    body = text[heading.end() :]
    following = re.search(r"^##\s", body, re.M)
    if following is not None:
        body = body[: following.start()]
    return _line_of(text, heading.start()), body


def _named_ports(body: str) -> set[str]:
    """Every port a prose body names in backticks, `DOUT9..0` ranges expanded.

    The same rule `_cell_ports` applies to a table cell: only backticked tokens
    count, so a prose word that happens to spell a port name does not stand in
    for naming the port. A glob (`DOUT*`) matches neither form and is ignored
    rather than expanded -- it says the section discusses the bus, not that it
    named each line of it.
    """
    named: set[str] = set()
    for span in BACKTICK_SPAN_RE.finditer(body):
        token = _unwrap_backticked(span.group(1))
        expanded = _expand_range(token)
        if expanded is not None:
            named.update(expanded)
        elif PORT_NAME_RE.match(token):
            named.add(token)
    return named


def rail_ports(text: str) -> set[str]:
    """The ports Section 2's I/O table charges to no slot -- the supply rails.

    Read off the same Count column check 10 part (d) treats as the rail
    exemption (a cell that does not begin with a digit), so the two checks
    cannot disagree about which rows are rails.
    """
    rails: set[str] = set()
    for _line, cells in io_table(text):
        if len(cells) < 4 or re.match(r"\d", cells[3]):
            continue
        rails.update(_cell_ports(cells[0]))
    return rails


def check_test_plan_ports(doc: Path, text: str) -> list[str]:
    """Check 19: Section 5's bench plan is written against the current interface."""
    section = test_plan_section(text)
    if section is None:
        return []
    line_number, body = section
    where = f"{doc.name}:{line_number}"
    flat = re.sub(r"\s+", " ", body)
    named = _named_ports(body)
    misses = []

    # (a) Every port of the netlist is named somewhere in the bench plan. This
    # is the direction that goes stale: three supply ports joined this
    # interface on 2026-09-24 (DR-010's `VPWR`/`VGND`, DR-012's `GND`) and
    # Section 5 went on describing the 19-port block for a day afterwards.
    for port in netlist_ports():
        if port not in named:
            misses.append(
                f"{where}: port `{port}` of `{TOP_NETLIST}` is named nowhere in "
                f"Section 5's bench test plan, which states that it is written "
                f"against this design's current port list -- a bench plan that "
                f"omits a terminal is not executable on the part this repo builds"
            )

    # (b) The supply terminals the plan feeds are exactly Section 2's rail rows,
    # graded in both directions like checks 8, 10, 14, 15, 16, 17 and 18: a rail
    # dropped from this sentence leaves the bench under-powered, and one added
    # that Section 2 does not carry invents a terminal the part does not have.
    rails = rail_ports(text)
    for stated in TEST_PLAN_SUPPLIES_RE.finditer(flat):
        claimed = set(BACKTICK_SPAN_RE.findall(stated.group("terminals")))
        if int(stated.group("count")) != len(rails):
            misses.append(
                f"{where}: Section 5 says the bench feeds "
                f"{stated.group('count')} supply terminal(s), but Section 2's "
                f"I/O table charges {len(rails)} port(s) to no slot"
            )
        for port in sorted(claimed ^ rails):
            stated_here = port in claimed
            misses.append(
                f"{where}: Section 5's supply-terminal list "
                f"{'names' if stated_here else 'omits'} `{port}`, which "
                f"{'is not' if stated_here else 'is'} a rail row of Section 2's "
                f"I/O table -- the two must be the same set"
            )

    # (c) The power step's metered terminals are the cited record's own Power
    # table columns. The defect here is not a wrong number, it is a wrong
    # protocol: instructing a bench to meter `VDD` alone against a figure that
    # is a sum over five sources produces a reading that is not comparable,
    # and nothing about it looks stale on the page.
    for stated in TEST_PLAN_POWER_RE.finditer(flat):
        campaign = stated.group("campaign")
        terms = record_power_terms(campaign)
        if not terms:
            misses.append(
                f"{where}: Section 5's power step cites "
                f"`sim/{campaign}/records/LATEST`, whose current record carries "
                f"no readable Power table to check its metered terminals "
                f"against -- cite the campaign the figures came from"
            )
            continue
        claimed = [term.group("net") for term in POWER_TERM_RE.finditer(stated.group("terms"))]
        if int(stated.group("count")) != len(terms):
            misses.append(
                f"{where}: Section 5's power step says that table carries "
                f"{stated.group('count')} current column(s), but "
                f"`sim/{campaign}/`'s current record carries {len(terms)}"
            )
        if claimed != terms:
            misses.append(
                f"{where}: Section 5's power step meters {claimed}, but "
                f"`sim/{campaign}/`'s current Power table carries {terms} -- "
                f"restate it from `python3 "
                f"docs/chipalooza/check_proposal_citations.py --stats`"
            )
    return misses


def _netlist_instance_lines(region: str) -> str:
    """`region` with its comment lines dropped.

    xschem writes the top cell's own `.subckt`/`.ends`/`.ipin`/`.opin` lines
    as comments, and this file's header names the very flavour set check 20
    part (a) grades -- so a census taken over raw text would count prose about
    the netlist as instances of it.
    """
    return "\n".join(
        line for line in region.split("\n") if not line.lstrip().startswith("*")
    )


def top_netlist_text() -> str:
    """`design/sar_adc_top.spice`, or `""` when it is absent.

    Empty keeps check 20 inert against the fixtures the same way an empty
    `netlist_ports()` keeps check 10 inert; that the real one is found and
    non-empty is asserted by the tests.
    """
    path = REPO_ROOT / TOP_NETLIST
    return path.read_text() if path.is_file() else ""


def top_level_glue(text: str) -> str:
    """The instance lines that live outside every sub-block `.subckt`.

    This is the integration-level glue `design/sar_adc_top.sch` owns -- the
    SEL drive, the readout recode, the comparator dummy loads and the half-LSB
    offset network -- as distinct from anything a sub-block's own schematic
    (and therefore a sub-block's own layout flow) is responsible for.
    """
    header = SUBCKT_RE.search(text)
    if header is None:
        return ""
    body = text[header.end() :]
    end = TOP_REGION_END_RE.search(body)
    return _netlist_instance_lines(body[: end.start()] if end else body)


def cell_census(spice: str, family: str) -> dict[str, int]:
    """`{cell: instances}` for one PDK family over the given netlist text."""
    census: dict[str, int] = {}
    for match in PDK_CELL_RE.finditer(spice):
        if match.group("family") != family:
            continue
        cell = match.group("cell")
        census[cell] = census.get(cell, 0) + 1
    return census


def primitive_inventory_sentence(flavours: list[str]) -> str:
    """The Section 1 clause in exactly the form `PRIMITIVE_INVENTORY_RE` matches."""
    listed = ", ".join(f"`{flavour}`" for flavour in flavours)
    return (
        f"instantiates **{len(flavours)}** `sky130_fd_pr` primitive flavours — "
        f"{listed}"
    )


def glue_census_sentence(census: dict[str, int], family: str) -> str:
    """The Section 3 clause in exactly the form that family's regex matches."""
    listed = ", ".join(
        f"`{cell}` **×{count}**" for cell, count in sorted(census.items())
    )
    total = sum(census.values())
    if family == "sc_hd":
        return (
            f"adds **{total}** `sky130_fd_sc_hd` instances of "
            f"**{len(census)}** cell types — {listed}"
        )
    return (
        f"and **{total}** `sky130_fd_pr` instances of "
        f"**{len(census)}** device types — {listed}"
    )


def _stated_census(stated: re.Match) -> dict[str, int]:
    """The per-cell counts one census sentence lists."""
    return {
        entry.group("cell"): int(entry.group("count"))
        for entry in GLUE_CELL_RE.finditer(stated.group("cells"))
    }


def check_top_cell_inventory(doc: Path, text: str) -> list[str]:
    """Check 20: the stated device/cell inventory is the netlist's own."""
    netlist = top_netlist_text()
    if not netlist:
        return []
    collapsed, offsets = _collapse_quoted_prose(text)
    misses = []

    # (a) Section 1's primitive-flavour set, over the whole hierarchy. Graded
    # in both directions: a flavour dropped from the sentence hides what the
    # design is built from, and one added that no instance line carries claims
    # a device this repo has never drawn. This is the sentence that holds
    # Section 2.1's "no rail above 1.8 V core" position up -- a thick-oxide
    # `g5v0d10v5` pass device entering the netlist (the DR-002 tripwire) is a
    # CI failure here rather than a reader's job to notice.
    flavours = set(cell_census(_netlist_instance_lines(netlist), "pr"))
    for stated in PRIMITIVE_INVENTORY_RE.finditer(collapsed):
        where = f"{doc.name}:{_line_of(text, offsets[stated.start()])}"
        listed = set(BACKTICK_SPAN_RE.findall(stated.group("cells")))
        if int(stated.group("count")) != len(flavours):
            misses.append(
                f"{where}: Section 1 says this design instantiates "
                f"{stated.group('count')} `sky130_fd_pr` primitive flavour(s), "
                f"but `{TOP_NETLIST}` instantiates {len(flavours)}"
            )
        for flavour in sorted(listed ^ flavours):
            stated_here = flavour in listed
            misses.append(
                f"{where}: Section 1's primitive inventory "
                f"{'names' if stated_here else 'omits'} `{flavour}`, which "
                f"{'no' if stated_here else 'at least one'} instance line of "
                f"`{TOP_NETLIST}` instantiates -- restate it from `python3 "
                f"docs/chipalooza/check_proposal_citations.py --stats`"
            )

    # (b) Section 3's top-level glue census, per family. This is the direction
    # that has already gone stale: issue #263/DR-008 replaced the nine
    # `SELn<i> = NOT(DOUT<i>)` inverters issue #56 drew with decision-directed
    # `and2_1` pairs, and Sections 3 and 7 went on describing the inverter
    # bank as the glue this schematic adds. Nothing in the chain could see it:
    # check 10 grades the *ports*, which that change did not move.
    glue = top_level_glue(netlist)
    for pattern, family, label in (
        (GLUE_CELL_CENSUS_RE, "sc_hd", "standard-cell"),
        (GLUE_PRIMITIVE_CENSUS_RE, "pr", "primitive"),
    ):
        actual = cell_census(glue, family)
        for stated in pattern.finditer(collapsed):
            where = f"{doc.name}:{_line_of(text, offsets[stated.start()])}"
            listed = _stated_census(stated)
            if int(stated.group("instances")) != sum(actual.values()):
                misses.append(
                    f"{where}: Section 3's top-level {label} census says "
                    f"{stated.group('instances')} instance(s), but "
                    f"`{TOP_NETLIST}`'s top-level region carries "
                    f"{sum(actual.values())}"
                )
            if int(stated.group("types")) != len(actual):
                misses.append(
                    f"{where}: Section 3's top-level {label} census says "
                    f"{stated.group('types')} type(s), but "
                    f"`{TOP_NETLIST}`'s top-level region carries {len(actual)}"
                )
            for cell in sorted(set(listed) | set(actual)):
                if listed.get(cell) == actual.get(cell):
                    continue
                misses.append(
                    f"{where}: Section 3's top-level {label} census puts "
                    f"`{cell}` at {listed.get(cell, 0)} instance(s), but "
                    f"`{TOP_NETLIST}`'s top-level region carries "
                    f"{actual.get(cell, 0)} -- restate it from `python3 "
                    f"docs/chipalooza/check_proposal_citations.py --stats`"
                )
    return misses


def _measured_value_table(record: Path) -> str | None:
    """The `## Measured value(s)` section of a `sim/` record, or None.

    `None` is "nothing to compare against" -- the record is gone, or carries no
    such table -- which check 21 reports rather than passing silently.
    """
    if not record.is_file():
        return None
    text = record.read_text()
    heading = MEASURED_TABLE_HEADING_RE.search(text)
    if heading is None:
        return None
    section = text[heading.end() :]
    end = re.search(r"^#+\s", section, re.M)
    return section[: end.start()] if end is not None else section


def _measured_columns(section: str) -> list[str]:
    """That table's own header cells, in its own order."""
    header = re.search(r"^\|(?P<cells>.+)\|\s*$", section.strip(), re.M)
    if header is None:
        return []
    return [cell.strip() for cell in header.group("cells").split("|")]


def _measured_extremum(point: re.Match) -> tuple[float, str, str]:
    """The larger-magnitude of one row's two peaks, with its pin and instant.

    This is the same selection `sim/comparator-decision/run.py` makes for its
    own `Overall` line (`max(abs(peak_pos), abs(peak_neg))`), so the figure
    this check re-derives is the record's own worst case rather than a second
    opinion about it.
    """
    pos, neg = float(point.group("pos")), float(point.group("neg"))
    if abs(neg) >= abs(pos):
        return abs(neg), point.group("neg_pin"), point.group("neg_time")
    return abs(pos), point.group("pos_pin"), point.group("pos_time")


def kickback_readout(record: Path) -> dict | None:
    """The Kickback row's figures, re-derived from its cited record's table.

    `None` when there is nothing to compare against: no readable
    `Measured value(s)` table, fewer than two `Vindiff` points, or no
    `Vindiff = 0` control row for the subtraction to rest on.
    """
    section = _measured_value_table(record)
    if section is None:
        return None
    points = list(KICKBACK_ROW_RE.finditer(section))
    if len(points) < 2:
        return None
    control = next(
        (point for point in points if float(point.group("vindiff")) == 0.0), None
    )
    if control is None:
        return None
    worst = max(points, key=lambda point: _measured_extremum(point)[0])
    worst_mv, worst_pin, worst_time = _measured_extremum(worst)
    control_mv, control_pin, control_time = _measured_extremum(control)
    columns = _measured_columns(section)
    return {
        "columns": columns,
        "has_split": any(
            KICKBACK_SPLIT_COLUMN_RE.search(column) for column in columns
        ),
        "peak": worst_mv,
        "vindiff": float(worst.group("vindiff")),
        "pin": worst_pin,
        "time": worst_time,
        "control": control_mv,
        "control_pin": control_pin,
        "control_time": control_time,
        "residual": worst_mv - control_mv,
        "baseline_pct": control_mv / worst_mv * 100 if worst_mv else 0.0,
        "residual_pct": (worst_mv - control_mv) / worst_mv * 100 if worst_mv else 0.0,
    }


def kickback_sentences(readout: dict, bounds: list[float]) -> str:
    """The three Section 4 clauses in exactly the form check 21 accepts."""
    columns = ", ".join(f"`{column}`" for column in readout["columns"])
    verdict = (
        "at least one of them is a common-mode or differential quantity, so "
        "restate the split from the record instead of subtracting per-pin peaks"
        if readout["has_split"]
        else KICKBACK_NO_SPLIT_CLAUSE
    )
    return (
        f"the cited record measures **{readout['peak']:.4f} mV** worst-case peak "
        f"pin disturbance (`Vindiff = {readout['vindiff']:+g} mV`, "
        f"`{readout['pin']}` at {readout['time']} ns), i.e. "
        f"`≈ {readout['peak'] / bounds[0]:.1f}×` the `≤ {bounds[0]:g} mV` target "
        f"and `≈ {readout['peak'] / bounds[1]:.1f}×` the `≤ {bounds[1]:g} mV` "
        f"stretch. … `Vindiff = 0 mV` control row "
        f"(**−{readout['control']:.4f} mV**, `{readout['control_pin']}` at "
        f"{readout['control_time']} ns): `≈ {readout['baseline_pct']:.1f} %` of "
        f"that peak is already present with no decision to make, and "
        f"`{readout['residual']:.4f} mV` "
        f"(`≈ {readout['residual_pct']:.1f} %`) is what the "
        f"`{readout['vindiff']:+g} mV` point adds on top of it. … "
        f"`Measured value(s)` table carries **{len(readout['columns'])}** "
        f"columns — {columns} — {verdict}"
    )


def _kickback_row(text: str) -> tuple[int, list[str]] | None:
    """Section 4's Kickback row, as `(line_number, cells)`."""
    _header, rows = section_4_table(text)
    for line_number, cells in rows:
        if cells and _normalise_parameter(cells[0]).lower() == "kickback":
            return line_number, cells
    return None


def _kickback_bounds(cell: str) -> list[float]:
    """The `≤ <n> mV` bounds the row's own Target cell states, in its order."""
    return [float(match.group(1)) for match in re.finditer(r"≤\s*([0-9.]+) mV", cell)]


def check_kickback_decomposition(doc: Path, text: str) -> list[str]:
    """Check 21: the Kickback row's figures are its cited record's own."""
    row = _kickback_row(text)
    if row is None:
        return []
    line_number, cells = row
    where = f"{doc.name}:{line_number}"
    if len(cells) < 4:
        return [
            f"{where}: the Kickback row has {len(cells)} cell(s) -- check 21 "
            f"grades its Target, Verdict and Source columns"
        ]
    # The Verdict column carries the figures; the Source column carries the
    # record they are re-derived from (check 7 asserts the header shape).
    notes = cells[3]
    bounds = _kickback_bounds(cells[1])
    if len(bounds) < 2:
        return [
            f"{where}: the Kickback row's Target cell states "
            f"{len(bounds)} `≤ <n> mV` bound(s) -- this row's multiples are "
            f"derived against its own target and stretch, so both must be stated "
            f"there"
        ]
    cited = [
        match
        for match in EVIDENCE_PATH_RE.finditer(" ".join(cells[3:]))
        if match.group("top") == "sim"
    ]
    if not cited:
        return [
            f"{where}: the Kickback row states measured figures but cites no "
            f"`sim/<campaign>/records/<stamp>` record they can be re-derived "
            f"from"
        ]
    stamp = cited[-1].group("stamp")
    campaign = cited[-1].group("block")
    record = REPO_ROOT / "sim" / campaign / "records" / f"{stamp}.md"
    readout = kickback_readout(record)
    if readout is None:
        return [
            f"{where}: the Kickback row cites "
            f"`sim/{campaign}/records/{stamp}.md`, which carries no "
            f"`Measured value(s)` table with a `Vindiff = 0` control row and at "
            f"least one other point -- the row's subtraction rests on both"
        ]
    misses = []

    # (a) The measurement, and both multiples -- re-derived against the bounds
    # the row's OWN Target cell states rather than against numbers repeated in
    # the prose. That is this check's acceptance-criterion-2 teeth: relaxing the
    # target to make `≈ 14.7×` read smaller moves the derived multiple with it
    # and fails here, instead of leaving the row quietly softened.
    stated = KICKBACK_PEAK_RE.search(notes)
    if stated is None:
        misses.append(
            f"{where}: the Kickback row states no re-derivable measurement "
            f"clause -- restate it from `python3 "
            f"docs/chipalooza/check_proposal_citations.py --stats`"
        )
    else:
        for label, said, actual in (
            ("worst-case peak", stated.group("peak"), f"{readout['peak']:.4f}"),
            ("that peak's `Vindiff` point", stated.group("vindiff"), f"{readout['vindiff']:+g}"),
            ("that peak's pin", stated.group("pin"), readout["pin"]),
            ("that peak's instant", stated.group("time"), readout["time"]),
            ("the target bound", stated.group("target"), f"{bounds[0]:g}"),
            ("the stretch bound", stated.group("stretch"), f"{bounds[1]:g}"),
            (
                "the multiple over target",
                stated.group("target_mult"),
                f"{readout['peak'] / bounds[0]:.1f}",
            ),
            (
                "the multiple over stretch",
                stated.group("stretch_mult"),
                f"{readout['peak'] / bounds[1]:.1f}",
            ),
        ):
            if said != actual:
                misses.append(
                    f"{where}: the Kickback row puts {label} at `{said}`, "
                    f"re-derived from `sim/{campaign}/records/{stamp}.md` and "
                    f"this row's own Target cell it is `{actual}`"
                )

    # (b) The control-row subtraction. Same arithmetic, stated separately
    # because it is the clause whose *reading* has been the defect: the two
    # figures are per-pin extrema, so their difference is not a
    # common-mode/differential split -- see (c).
    split = KICKBACK_SPLIT_RE.search(notes)
    if split is None:
        misses.append(
            f"{where}: the Kickback row states no re-derivable control-row "
            f"clause -- restate it from `python3 "
            f"docs/chipalooza/check_proposal_citations.py --stats`"
        )
    else:
        for label, said, actual in (
            ("the control-row peak", split.group("control"), f"{readout['control']:.4f}"),
            ("the control-row pin", split.group("pin"), readout["control_pin"]),
            ("the control-row instant", split.group("time"), readout["control_time"]),
            (
                "the share present with no decision",
                split.group("baseline_pct"),
                f"{readout['baseline_pct']:.1f}",
            ),
            ("the residual", split.group("residual"), f"{readout['residual']:.4f}"),
            (
                "the residual's share",
                split.group("residual_pct"),
                f"{readout['residual_pct']:.1f}",
            ),
            (
                "the point that residual is measured at",
                split.group("worst_vindiff"),
                f"{readout['vindiff']:+g}",
            ),
        ):
            if said != actual:
                misses.append(
                    f"{where}: the Kickback row puts {label} at `{said}`, "
                    f"re-derived from `sim/{campaign}/records/{stamp}.md` it is "
                    f"`{actual}`"
                )

    # (c) The cited table's own column list, in its own order, plus the clause
    # that says whether any of them is a common-mode or differential quantity.
    # Both directions: the record reports neither today, so the row must say so
    # -- and once the successor record #390 mints carries them, this flips and
    # forces the row to be re-derived instead of carrying a qualification that
    # has stopped being true.
    columns = KICKBACK_COLUMNS_RE.search(notes)
    if columns is None:
        misses.append(
            f"{where}: the Kickback row states no column list for "
            f"`sim/{campaign}/records/{stamp}.md`'s own `Measured value(s)` "
            f"table -- that list is what says whether the subtraction above is "
            f"a common-mode/differential split; restate it from `python3 "
            f"docs/chipalooza/check_proposal_citations.py --stats`"
        )
    else:
        claimed = BACKTICK_SPAN_RE.findall(columns.group("columns"))
        if int(columns.group("count")) != len(readout["columns"]):
            misses.append(
                f"{where}: the Kickback row says that table carries "
                f"{columns.group('count')} column(s), but "
                f"`sim/{campaign}/records/{stamp}.md`'s carries "
                f"{len(readout['columns'])}"
            )
        if claimed != readout["columns"]:
            misses.append(
                f"{where}: the Kickback row lists that table's columns as "
                f"{claimed}, but they are {readout['columns']} -- restate them "
                f"from `python3 docs/chipalooza/check_proposal_citations.py "
                f"--stats`"
            )
        says_no_split = KICKBACK_NO_SPLIT_CLAUSE in columns.group("verdict")
        if readout["has_split"] and says_no_split:
            misses.append(
                f"{where}: the Kickback row says {KICKBACK_NO_SPLIT_CLAUSE}, but "
                f"`sim/{campaign}/records/{stamp}.md`'s `Measured value(s)` table "
                f"now carries one -- restate the split from the record instead of "
                f"subtracting per-pin peaks"
            )
        if not readout["has_split"] and not says_no_split:
            misses.append(
                f"{where}: the Kickback row does not state that "
                f"{KICKBACK_NO_SPLIT_CLAUSE} in "
                f"`sim/{campaign}/records/{stamp}.md`'s `Measured value(s)` "
                f"table -- without it the subtraction above reads as a "
                f"common-mode/differential split it is not"
            )
    return misses


def coverage_index_tracking() -> list[tuple[str, list[str]]]:
    """`(parameter, [DR-<n>, ...])` per indexed row that tracks decision records.

    Read out of `sim/spec-coverage.json`'s own `tracking` field -- the free-prose
    field each row uses to say what work is still outstanding on it and which
    decision records govern that. Only the `DR-<n>` tokens are taken: the field
    also names issues and document sections, and those are not what this check
    is about (see `docs/citation-gate.md`).

    Empty when the index is absent or no row tracks a record, which is how
    check 22 stays inert against the test fixtures; that the real index tracks
    at least one is asserted by `sim/tests/test_proposal_citations.py`.
    """
    index = _load_json(REPO_ROOT / COVERAGE_INDEX)
    if index is None or not isinstance(index.get("rows"), list):
        return []
    tracked: list[tuple[str, list[str]]] = []
    for row in index["rows"]:
        if not isinstance(row, dict):
            continue
        tracking = row.get("tracking")
        if not isinstance(tracking, str):
            continue
        records = sorted(
            {f"DR-{number}" for number in BARE_DECISION_RECORD_RE.findall(tracking)},
            key=lambda name: int(name.removeprefix("DR-")),
        )
        if records:
            tracked.append((_normalise_parameter(str(row.get("parameter", ""))), records))
    return tracked


def check_tracked_records(doc: Path, text: str) -> list[str]:
    """Check 22: no Section 4 row falls behind the records its index tracks."""
    tracked = coverage_index_tracking()
    if not tracked:
        return []
    rows = {
        _normalise_parameter(cells[0]): (line_number, " | ".join(cells))
        for line_number, cells in section_4_table(text)[1]
    }
    if not rows:
        return []
    misses = []
    for parameter, records in tracked:
        found = rows.get(parameter)
        if found is None:
            # A spec row absent from Section 4 entirely is check 7's finding.
            continue
        line_number, row = found
        for record in records:
            # `(?!\d)` rather than `\b`: `DR-01` must not be satisfied by a row
            # that names `DR-011`.
            if re.search(rf"{re.escape(record)}(?!\d)", row):
                continue
            misses.append(
                f'{doc.name}:{line_number}: spec row "{parameter}" does not name '
                f"`{record}`, which `{COVERAGE_INDEX}` tracks as a decision record "
                f"governing it -- a row may not restate its own disposition while "
                f"ignoring a record this repo has indexed under it"
            )
    return misses


def attached_currency_citations(text: str) -> list[tuple[re.Match, str, list]]:
    """Every `(claim, citation_text, records)` triple check 23 evaluates.

    A triple is produced only for an *attached* claim: the citation construct
    must be the very next thing after the claim, separated by nothing but the
    punctuation `STAMPED_CURRENCY_CONNECTOR_RE` allows. `records` is every
    stamped-record match inside that construct -- display text and link target
    both -- so a link whose two halves name different records is graded on
    both rather than on whichever one is scanned first.

    Returned rather than checked inline for the same reason
    `attached_pointer_claims` is: the test suite exercises the attachment rule
    directly, and `--stats` has a use for the count.
    """
    triples = []
    for claim in STAMPED_CURRENCY_CLAIM_RE.finditer(text):
        window = _unwrap_backticked(text[claim.end() : claim.end() + STAMPED_CURRENCY_WINDOW])
        citation = STAMPED_CITATION_RE.search(window)
        if citation is None:
            continue
        if not STAMPED_CURRENCY_CONNECTOR_RE.match(window[: citation.start()]):
            continue
        cited = citation.group("bare")
        spans = [cited] if cited else [citation.group("display"), citation.group("target")]
        records = [
            record for span in spans for record in STAMPED_RECORD_RE.finditer(span)
        ]
        if not records:
            continue
        triples.append((claim, citation.group(0), records))
    return triples


def check_stamped_currency_claims(doc: Path, text: str) -> list[str]:
    """Check 23: "the current run, <record>" must name the pointer's record."""
    misses = []
    for claim, citation, records in attached_currency_citations(text):
        line = _line_of(text, claim.start())
        # One construct, so one flow: whichever half of the link spells the
        # `<top>/<block>/` prefix out supplies it for the half that elides it.
        top = next((r.group("top") for r in records if r.group("top")), None)
        block = next((r.group("block") for r in records if r.group("block")), None)
        tree = records[0].group("tree")
        if top is None or block is None:
            misses.append(
                f"{doc.name}:{line}: \"{claim.group(0)}\" cites `{citation}`, "
                f"which names no `<sim|layout>/<block>/` flow -- cite the record "
                f"by full path so the claim can be checked against that flow's "
                f"`{tree}/LATEST`"
            )
            continue

        pointer = _read_pointer(top, block, tree)
        if pointer is None:
            misses.append(
                f"{doc.name}:{line}: \"{claim.group(0)}\" cites a record of "
                f"`{top}/{block}/{tree}/`, but that tree has no `LATEST` pointer "
                f"to be current against"
            )
            continue
        current = pointer.split("/")[0].removesuffix(".md")

        # Both halves of a link are graded, but a link whose halves agree (the
        # normal case) must not report the same drift twice.
        seen: set[str] = set()
        for record in records:
            if record.group("tree") != tree:
                _add_once(misses, seen,
                    f"{doc.name}:{line}: \"{claim.group(0)}\" cites `{citation}`, "
                    f"whose two halves name different evidence trees "
                    f"(`{tree}/` and `{record.group('tree')}/`)"
                )
                continue
            if record.group("stamp") != current:
                _add_once(misses, seen,
                    f"{doc.name}:{line}: \"{claim.group(0)}\" names "
                    f"`{record.group('stamp')}` as the current record of "
                    f"`{top}/{block}/{tree}/`, but that tree's `LATEST` resolves "
                    f"to `{current}` -- re-point the citation, and restate "
                    f"whatever the superseded record was quoted for"
                )
    return misses


def report_row_count() -> int | None:
    """How many rows `sim/report/generate.py --check` reports, re-derived.

    That script closes with `len(manifest.ROWS)`, so the number is a property
    of `sim/report/manifest.py`'s own row table and moves the moment a spec row
    joins or leaves the characterization report. Counted from the source text
    (one `Row(` constructor per entry, inside the `ROWS` tuple) rather than by
    importing the module, so this gate stays the pure file reader its module
    docstring claims it is.

    None when the file carries no `ROWS` tuple this can find -- a restructured
    manifest is reported rather than silently counted as zero, since a zero
    would quietly disagree with every number the document could state.
    """
    manifest = REPO_ROOT / REPORT_MANIFEST
    if not manifest.is_file():
        return None
    source = manifest.read_text()
    opening = REPORT_MANIFEST_ROWS_RE.search(source)
    if opening is None:
        return None
    end = source.find("\n)\n", opening.end())
    block = source[opening.end() : end if end != -1 else len(source)]
    return len(REPORT_MANIFEST_ROW_RE.findall(block))


def check_report_row_count(doc: Path, text: str) -> list[str]:
    """Check 24: a quoted report row count is the one the manifest carries."""
    if not (REPO_ROOT / REPORT_MANIFEST).is_file():
        return []
    if REPORT_CHECK_COMMAND not in text:
        # A document that does not lean on that command states no count of
        # its own, and is not made to.
        return []
    derived = report_row_count()
    if derived is None:
        return [
            f"{doc.name}: quotes `{REPORT_CHECK_COMMAND}`, but "
            f"`{REPORT_MANIFEST}` no longer states a `ROWS` tuple this gate "
            f"can count -- re-point this check at whatever replaced it rather "
            f"than leaving the quoted row count ungraded"
        ]
    quoted = list(REPORT_ROW_COUNT_RE.finditer(text))
    if not quoted:
        return [
            f"{doc.name}: names `{REPORT_CHECK_COMMAND}` but quotes none of "
            f"its output -- quote the line it ends with "
            f"(`is fresh and up to date ({derived} rows)` today), so the claim "
            f"that it was run is graded rather than asserted"
        ]
    misses = []
    for match in quoted:
        stated = int(match.group("rows"))
        if stated == derived:
            continue
        misses.append(
            f"{doc.name}:{_line_of(text, match.start())}: quotes "
            f"`{match.group(0)}` from `{REPORT_CHECK_COMMAND}`, but "
            f"`{REPORT_MANIFEST}` carries {derived} rows -- re-run the command "
            f"and restate its output, and check whether the row that moved the "
            f"count belongs in Section 4 too"
        )
    return misses


def _deck_device_cards(deck: Path) -> list[tuple[int, str]]:
    """`(line number, card)` for every device card in one SPICE deck.

    Comments, blank lines, continuations and dot-commands are dropped, and so
    is everything between a `.control` and its `.endc` -- that body is
    ngspice's interactive command language (`let`, `tran`, `meas`, ...), not
    device cards, even though its lines start with neither `*`, `+` nor `.`.
    What is left starts with the device letter its card type is named for.
    """
    cards = []
    in_control = False
    for number, line in enumerate(deck.read_text().splitlines(), 1):
        card = line.strip()
        if not card:
            continue
        lowered = card.lower()
        if lowered.startswith(".control"):
            in_control = True
            continue
        if lowered.startswith(".endc"):
            in_control = False
            continue
        if in_control or card[0] in "*+.":
            continue
        cards.append((number, card))
    return cards


def ground_return_census() -> dict:
    """How many `sim/` decks there are, and how many model an inductance.

    The second number is the graded one -- see this module's check-25
    constants for why an inductor card is the stand-in for "a campaign that
    models the ground return". `cards` names where each one was found, so a
    future failure reads as "this deck now carries one" rather than as a bare
    integer a reader has to go hunting for.
    """
    decks = sorted((REPO_ROOT / SIM_DECK_ROOT).glob(SIM_DECK_GLOB))
    cards = [
        f"{deck.relative_to(REPO_ROOT)}:{number}"
        for deck in decks
        for number, card in _deck_device_cards(deck)
        if SPICE_INDUCTOR_CARD_RE.match(card)
    ]
    return {"decks": len(decks), "inductors": len(cards), "cards": cards}


def ground_return_sentence(census: dict) -> str:
    """That census in exactly the sentence form `GROUND_RETURN_RE` matches.

    Used by `--stats` so the fix for a check-25 failure is a paste, as it is
    for checks 6, 9, 12, 13, 14, 15, 16, 17, 18 and 24.
    """
    decks = census["decks"]
    inductors = census["inductors"]
    return (
        f"across the **{decks}** SPICE deck{'' if decks == 1 else 's'} under "
        f"`sim/`, **{inductors}** carry an inductor card"
    )


def check_ground_return(doc: Path, text: str) -> list[str]:
    """Check 25: the stated ground-return census is this tree's own."""
    if not (REPO_ROOT / SIM_DECK_ROOT).is_dir():
        return []
    if GROUND_RETURN_ANCHOR not in text:
        # A document that does not lean on DR-012 qualifies nothing about that
        # record's open item, and is not made to.
        return []
    actual = ground_return_census()
    collapsed, offsets = _collapse_quoted_prose(text)
    stated = list(GROUND_RETURN_RE.finditer(collapsed))
    if not stated:
        return [
            f"{doc.name}: cites `{GROUND_RETURN_ANCHOR}`, whose own \"Open "
            f"items\" record that nothing in `sim/` models the ground return, "
            f"but states no census of its own -- state it "
            f"(`{ground_return_sentence(actual)}` today), so the qualification "
            f"is graded rather than asserted and cannot be quietly dropped"
        ]
    misses = []
    for match in stated:
        where = f"{doc.name}:{_line_of(text, offsets[match.start()])}"
        for field in ("decks", "inductors"):
            claimed = int(match.group(field))
            if claimed == actual[field]:
                continue
            found = (
                f" ({', '.join(actual['cards'])})"
                if field == "inductors" and actual["cards"]
                else ""
            )
            misses.append(
                f"{where}: the ground-return census says {field}={claimed}, "
                f"but `{SIM_DECK_ROOT}/` reports {field}={actual[field]}"
                f"{found} -- restate it from `python3 "
                f"docs/chipalooza/check_proposal_citations.py --stats`, and if "
                f"a deck now models the return, rewrite the qualification "
                f"rather than the number"
            )
    return misses


def _names_pdk_commit(text: str) -> bool:
    """Does this record name a PDK commit, as opposed to any other hash?

    The test is per line rather than per document on purpose -- see this
    module's check-26 constants for the two hashes that would otherwise be
    miscounted as PDK provenance.
    """
    return any(
        "pdk" in line.lower() and PROVENANCE_COMMIT_RE.search(line)
        for line in text.splitlines()
    )


def provenance_census() -> dict:
    """How far this tree's own records pin the tools that produced them.

    Five numbers, all derived: the `sim/` records and how many of them name
    both an `ngspice` version and a PDK commit, then the `layout/` records
    (both the flow tree and the ERC tree, which are two record trees of the
    same kind) and how many name a `klt` version and a PDK commit. `unpinned`
    groups the shortfall by flow, so a failure reads as "this flow mints
    records without it" rather than as a bare integer a reader has to go
    hunting for -- check 25's `cards` field plays the same role.
    """
    sim = sorted(REPO_ROOT.glob(PROVENANCE_SIM_GLOB))
    layout = sorted(path for glob in PROVENANCE_LAYOUT_GLOBS for path in REPO_ROOT.glob(glob))
    sim_texts = [path.read_text() for path in sim]
    layout_texts = [(path, path.read_text()) for path in layout]

    unpinned: dict[str, list[int]] = {}
    for path, text in layout_texts:
        flow = "/".join(path.relative_to(REPO_ROOT).parts[:3])
        counts = unpinned.setdefault(flow, [0, 0])
        counts[1] += 1
        if not _names_pdk_commit(text):
            counts[0] += 1

    return {
        "sim_records": len(sim),
        "sim_pinned": sum(
            1
            for text in sim_texts
            if PROVENANCE_NGSPICE_RE.search(text) and _names_pdk_commit(text)
        ),
        "layout_records": len(layout),
        "layout_klt": sum(1 for _path, text in layout_texts if PROVENANCE_KLT_RE.search(text)),
        "layout_pdk": sum(1 for _path, text in layout_texts if _names_pdk_commit(text)),
        "unpinned": {flow: tuple(counts) for flow, counts in sorted(unpinned.items()) if counts[0]},
    }


def provenance_sentence(census: dict) -> str:
    """That census in exactly the sentence form `PROVENANCE_CENSUS_RE` matches.

    Used by `--stats` so the fix for a check-26 failure is a paste, as it is
    for checks 6, 9, 12, 13, 14, 15, 16, 17, 18, 24 and 25.
    """
    return (
        f"**{census['sim_pinned']}** of the **{census['sim_records']}** records under "
        f"`sim/*/records/` name both an `ngspice` version and a 40-hex `open_pdks` "
        f"commit, while of the **{census['layout_records']}** records under "
        f"`layout/*/reports/` and `layout/*/erc-reports/` **{census['layout_klt']}** "
        f"name a `klt` version and **{census['layout_pdk']}** name the `open_pdks` commit"
    )


def check_provenance_census(doc: Path, text: str) -> list[str]:
    """Check 26: the stated toolchain/PDK provenance census is this tree's own."""
    if not any((REPO_ROOT / top).is_dir() for top in ("sim", "layout")):
        return []
    if PROVENANCE_ANCHOR not in text:
        # A document that does not lean on the pin file claims nothing about
        # how far the pin reaches, and is not made to.
        return []
    actual = provenance_census()
    collapsed, offsets = _collapse_quoted_prose(text)
    stated = list(PROVENANCE_CENSUS_RE.finditer(collapsed))
    if not stated:
        return [
            f"{doc.name}: cites `{PROVENANCE_ANCHOR}` as the pin its evidence "
            f"was produced under, but states no census of how far that pin "
            f"reaches -- state it (`{provenance_sentence(actual)}` today), so "
            f"the claim is graded rather than asserted and cannot be quietly "
            f"widened back into \"every record\""
        ]
    misses = []
    for match in stated:
        where = f"{doc.name}:{_line_of(text, offsets[match.start()])}"
        for field in ("sim_pinned", "sim_records", "layout_records", "layout_klt", "layout_pdk"):
            claimed = int(match.group(field))
            if claimed == actual[field]:
                continue
            detail = ""
            if field == "layout_pdk" and actual["unpinned"]:
                detail = " (" + ", ".join(
                    f"{flow}: {short} of {total}" for flow, (short, total) in actual["unpinned"].items()
                ) + " mint records naming none)"
            misses.append(
                f"{where}: the provenance census says {field}={claimed}, but "
                f"the evidence tree reports {field}={actual[field]}{detail} -- "
                f"restate it from `python3 "
                f"docs/chipalooza/check_proposal_citations.py --stats`, and if "
                f"a flow now pins the commit, say so rather than only moving "
                f"the number (issue #407)"
            )
    return misses


def numbered_sections(text: str) -> dict[int, str]:
    """`{number: title}` for every `## N. Title` heading, in document order."""
    sections: dict[int, str] = {}
    for line in text.splitlines():
        heading = SECTION_HEADING_RE.match(line)
        if heading is not None:
            sections.setdefault(int(heading.group("number")), heading.group("title").strip())
    return sections


def label_claims(text: str) -> list[tuple[int, str, int | None]]:
    """Every `(line, label, section)` triple check 27 grades.

    Fenced code blocks are skipped: a quoted `gh issue edit ... --add-label`
    command line is an instruction to a reader, not this document's own claim
    about what an issue currently carries. Returned rather than checked
    inline so the test suite can exercise the scan directly, as it does for
    `attached_pointer_claims` and `attached_currency_citations`.
    """
    claims: list[tuple[int, str, int | None]] = []
    section: int | None = None
    fenced = False
    for number, line in enumerate(text.splitlines(), start=1):
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        heading = SECTION_HEADING_RE.match(line)
        if heading is not None:
            section = int(heading.group("number"))
            continue
        for match in LABEL_CLAIM_RE.finditer(line):
            claims.append((number, match.group("label"), section))
    return claims


def check_label_claim_section(doc: Path, text: str) -> list[str]:
    """Check 27: a live forge label is stated in one section, not copied."""
    sections = numbered_sections(text)
    home = sections.get(LABEL_STATE_SECTION)
    if home is None:
        # A document with no tracking-state section states no tracking state
        # in one, and is not made to invent one.
        return []
    misses: list[str] = []
    for line, label, section in label_claims(text):
        if section == LABEL_STATE_SECTION:
            continue
        where = "The front matter" if section is None else f"Section {section}"
        misses.append(
            f"{doc.name}:{line}: {where} states `loom:{label}` -- a forge label "
            f"is live state this network-free gate cannot read, so the document "
            f"may keep exactly one copy of it, in Section {LABEL_STATE_SECTION} "
            f"(\"{home}\"), which is dated and maintained pass by pass. State "
            f"the engineering fact here and defer to that trail (\"see "
            f"§{LABEL_STATE_SECTION} Item N\"), so a second copy cannot rot "
            f"while the maintained one moves on (issue #121)"
        )
    return misses


def _pdk_process_corners() -> list[str] | None:
    """`sim/pdk.json`'s own process-corner list, or None if unreadable.

    The one anchor in check 28 that is not the document's own sentence. A
    missing or malformed pin file leaves the process axis ungraded rather than
    failing the gate on it: the census over the records is the check's
    subject, and a fixture tree that carries no PDK pin must still be able to
    exercise it.
    """
    path = REPO_ROOT / SIM_PDK_JSON
    if not path.is_file():
        return None
    try:
        corners = json.loads(path.read_text())["process_corners"]
    except (json.JSONDecodeError, KeyError, OSError):
        return None
    return [str(corner) for corner in corners] if isinstance(corners, list) else None


def _axis_numbers(raw: str) -> tuple[float, ...]:
    """The numeric axis values in `raw`, normalized for comparison.

    U+2212 MINUS SIGN is what the document sets a negative temperature with
    (`−40`) and U+002D is what a record writes (`-40`); `27` and `27.0` are
    the same point. Comparing sorted floats rather than strings is what makes
    the document's typography and the driver's `repr()` agree.
    """
    values = []
    for token in raw.replace("−", "-").split(","):
        token = token.strip().strip("'\"")
        if not token:
            continue
        try:
            values.append(float(token))
        except ValueError:
            return ()
    return tuple(sorted(values))


def _axis_names(raw: str) -> tuple[str, ...]:
    """The non-numeric axis values in `raw` (the process corners), sorted."""
    return tuple(
        sorted(
            token.strip().strip("'\"")
            for token in raw.split(",")
            if token.strip().strip("'\"")
        )
    )


def stated_corner_grid(text: str) -> dict | None:
    """The PVT grid Section 4 says its rows are reported at, or None.

    Returned as axes plus the point count the document itself states, so both
    can be graded: the axes against `sim/pdk.json` and against the records,
    the count against the one-at-a-time identity |P| + |T| + |S| - 2 that
    `sim/README.md`'s "Corner-grid shape" section describes and
    `sim/harness/corners.py:oat_grid()` implements. Without the identity a
    weakened sentence would simply redefine "full" and pass.
    """
    collapsed, offsets = _collapse_quoted_prose(text)
    stated = CORNER_GRID_RE.search(collapsed)
    if stated is None:
        return None
    return {
        "line": _line_of(text, offsets[stated.start()]),
        "process": _axis_names(stated.group("process")),
        "temps": _axis_numbers(stated.group("temps")),
        "supplies": _axis_numbers(stated.group("supplies")),
        "points": int(stated.group("points")),
    }


def declared_pvt_points(record: str) -> dict | None:
    """The PVT point set a `sim/` record declares for itself, or None.

    Three shapes, all in use in this tree (see `RECORD_*` above). A record
    matching none of them declares no PVT point set of its own -- which is a
    real answer, not a parse failure: the ENOB re-analyses run no ngspice at
    all and inherit their binding corner from the records they combine.
    """
    matrix = RECORD_CORNER_MATRIX_RE.search(record)
    if matrix is not None:
        return {
            "points": int(matrix.group("points")),
            "process": _axis_names(matrix.group("process")),
            "temps": _axis_numbers(matrix.group("temps")),
            "supplies": _axis_numbers(matrix.group("supplies")),
        }

    triples: list[tuple[str, float, float]] = []
    line = RECORD_POINT_MATRIX_RE.search(record)
    if line is not None:
        triples = [
            (point.group("process").lower(), float(point.group("temp")), float(point.group("supply")))
            for point in RECORD_CORNER_TRIPLE_RE.finditer(line.group("body"))
        ]
    if not triples:
        stat = RECORD_STAT_POINT_RE.search(record)
        if stat is not None:
            triples = [
                (
                    stat.group("process").lower(),
                    float(stat.group("temp")),
                    float(stat.group("supply")),
                )
            ]
    if not triples:
        return None
    points = sorted(set(triples))
    return {
        "points": len(points),
        "process": tuple(sorted({point[0] for point in points})),
        "temps": tuple(sorted({point[1] for point in points})),
        "supplies": tuple(sorted({point[2] for point in points})),
    }


def _sim_record_text(block: str, stamp: str) -> str | None:
    record = REPO_ROOT / "sim" / block / "records" / f"{stamp}.md"
    return record.read_text() if record.is_file() else None


def corner_grid_census(text: str) -> dict | None:
    """How much of Section 4's table really stands on the stated grid.

    Counted per (row, record) pair, check 18's unit one level finer: corner
    coverage is a property of the record, not of the flow that minted it, and
    a row citing one flow's nine-point campaign and its single-corner
    first-pass budget is making two different claims.

    None when the document states no grid at all -- there is then nothing to
    be measured against, and a fixture is not made to invent one.
    """
    grid = stated_corner_grid(text)
    if grid is None:
        return None
    pairs = {
        (line_number, cite.group("block"), cite.group("stamp"))
        for line_number, row in spec_table_rows(text)
        for cite in EVIDENCE_PATH_RE.finditer(row)
        if cite.group("top") == "sim"
    }
    counts = {"full": 0, "subset": 0, "unstated": 0}
    records: dict[str, int | None] = {}
    for _line, block, stamp in pairs:
        body = _sim_record_text(block, stamp)
        declared = declared_pvt_points(body) if body is not None else None
        path = f"sim/{block}/records/{stamp}.md"
        if declared is not None and (
            declared["points"] == grid["points"]
            and declared["process"] == grid["process"]
            and declared["temps"] == grid["temps"]
            and declared["supplies"] == grid["supplies"]
        ):
            counts["full"] += 1
            continue
        counts["subset" if declared is not None else "unstated"] += 1
        records[path] = declared["points"] if declared is not None else None
    return {
        "pairs": len(pairs),
        "points": grid["points"],
        "records": sorted(records.items()),
        **counts,
    }


def _corner_grid_entry(record: str, points: int | None) -> str:
    if points is None:
        return f"`{record}` (no PVT point set)"
    return f"`{record}` (**{points}** point{'' if points == 1 else 's'})"


def corner_grid_sentence(census: dict) -> str:
    """That census in exactly the sentence form `CORNER_GRID_CENSUS_RE` matches.

    Used by `--stats` so the fix for a check-28 failure is a paste, as it is
    for checks 6, 9, 12--18 and 26.
    """
    records = (
        ", ".join(
            _corner_grid_entry(record, points) for record, points in census["records"]
        )
        or CORNER_GRID_NONE
    )
    return (
        f"of the **{census['pairs']}** (spec row, `sim/` record) citation pairs "
        f"in Section 4's table, **{census['full']}** name a record that "
        f"declares the full **{census['points']}**-point grid, "
        f"**{census['subset']}** name one that declares a smaller PVT point "
        f"set, and **{census['unstated']}** name one that declares no PVT "
        f"point set of its own: {records}."
    )


def check_corner_grid_census(doc: Path, text: str) -> list[str]:
    """Check 28: Section 4's PVT-grid claim must be counted, not asserted."""
    grid = stated_corner_grid(text)
    if grid is None:
        return []
    misses: list[str] = []
    where = f"{doc.name}:{grid['line']}"

    # (a) The grid itself, against the two anchors that are not the document's
    # own wording -- so it cannot be weakened into truth.
    pinned = _pdk_process_corners()
    if pinned is not None and tuple(sorted(pinned)) != grid["process"]:
        misses.append(
            f"{where}: Section 4 states the PVT grid's process axis as "
            f"{{{', '.join(grid['process'])}}}, but `{SIM_PDK_JSON}` pins "
            f"{{{', '.join(sorted(pinned))}}} -- state the grid this "
            f"repository actually runs, rather than one the cited records "
            f"happen to meet"
        )
    oat = len(grid["process"]) + len(grid["temps"]) + len(grid["supplies"]) - 2
    if grid["points"] != oat:
        misses.append(
            f"{where}: Section 4 states a {grid['points']}-point "
            f"one-at-a-time grid, but the axes it names are "
            f"{len(grid['process'])} process x {len(grid['temps'])} "
            f"temperature x {len(grid['supplies'])} supply, which is {oat} "
            f"points by `sim/README.md`'s own corner-grid shape "
            f"(|P| + |T| + |S| - 2)"
        )

    # (b) The census over the records the table actually cites. An absent one
    # is a finding, check 25's and 26's shape: a document that names the grid
    # for every row at once must say how many of them stand on it.
    actual = corner_grid_census(text)
    collapsed, offsets = _collapse_quoted_prose(text)
    stated = CORNER_GRID_CENSUS_RE.search(collapsed)
    if stated is None:
        return misses + [
            f"{where}: Section 4 names the PVT grid its rows are reported at "
            f"but states no census of how many of them stand on it -- "
            f"{actual['full']} of its {actual['pairs']} (spec row, `sim/` "
            f"record) citation pairs do. Paste the sentence `python3 "
            f"docs/chipalooza/check_proposal_citations.py --stats` prints, "
            f"rather than letting one sentence speak for rows it does not "
            f"cover (issue #121)"
        ]

    at = f"{doc.name}:{_line_of(text, offsets[stated.start()])}"
    for field in ("pairs", "full", "subset", "unstated", "points"):
        claimed = int(stated.group(field))
        if claimed != actual[field]:
            misses.append(
                f"{at}: the Section 4 corner-grid census says {field}="
                f"{claimed}, but this document's live census is "
                f"{field}={actual[field]} -- restate it from `python3 "
                f"docs/chipalooza/check_proposal_citations.py --stats`"
            )

    # Both directions, as checks 8, 10, 14--18 and 26 do. A record that starts
    # running the full grid and is left in the list overstates the hole; one a
    # newly added row starts citing and is left out understates it, which is
    # the direction the blanket sentence already failed in once.
    claimed_records = {
        (
            entry.group("record"),
            int(entry.group("points")) if entry.group("points") else None,
        )
        for entry in CORNER_GRID_ENTRY_RE.finditer(stated.group("records"))
    }
    for record, points in sorted(
        claimed_records ^ set(actual["records"]), key=lambda item: item[0]
    ):
        stated_here = (record, points) in claimed_records
        declared = (
            "no PVT point set" if points is None else f"**{points}** point(s)"
        )
        misses.append(
            f"{at}: the Section 4 corner-grid census "
            f"{'lists' if stated_here else 'omits'} `{record}` as declaring "
            f"{declared}, which is not what that record and this document's "
            f"own table report -- restate it from `python3 "
            f"docs/chipalooza/check_proposal_citations.py --stats`"
        )
    return misses


def check_absent_paths(doc: Path, text: str) -> list[str]:
    """Check 29: a path asserted to be absent from this tree really is absent."""
    misses: list[str] = []
    for line, _offset, span in absent_claims(text):
        if not _own_tree_path(span):
            misses.append(
                f"{doc.name}:{line}: `{span}` carries the "
                f'"{ABSENT_MARKER}" marker but is not a concrete path into one '
                f"of this repository's own top-level trees "
                f"({', '.join(sorted(OWN_TOP_LEVEL))}) -- the marker exempts a "
                f"path from check 2, so it may not be spent on a glob, a "
                f"pattern, or an upstream path check 2 was never going to "
                f"resolve, which would exempt it from both checks at once "
                f"(issue #121)"
            )
            continue
        if _resolve(doc, "../../" + span).exists():
            misses.append(
                f"{doc.name}:{line}: `{span}` is asserted absent "
                f'("{ABSENT_MARKER}") but now exists in this repository -- the '
                f"work this passage describes as not yet landed has landed. "
                f"Update the passage to what the tree now holds and drop the "
                f"marker, so the path becomes an ordinary citation check 2 "
                f"grades (issue #121)"
            )
    return misses


def _renderer_entry_point(tree: Path) -> str:
    """The repo-relative path that mints `record.md` under this record tree."""
    flow = tree.parent.name
    if tree.name == "erc-reports":
        return RENDERER_ERC.format(flow=flow)
    local = RENDERER_LOCAL.format(flow=flow)
    return local if (REPO_ROOT / local).is_file() else RENDERER_SHARED


def renderer_census() -> dict:
    """How many of this tree's record-minting entry points resolve the PDK pin.

    The leading indicator behind `provenance_census`'s lagging one. Counted
    over entry points rather than over record trees, because that is the unit
    a fix is made in: one renderer minting two trees is one place to change,
    and would otherwise be double-counted on both sides of the census.
    """
    shared_module = REPO_ROOT / RENDERER_SHARED_MODULE
    shared_text = shared_module.read_text() if shared_module.is_file() else ""

    entry_points: dict[str, bool] = {}
    trees = sorted(
        path
        for glob in (RENDERER_REPORT_GLOB, RENDERER_ERC_GLOB)
        for path in REPO_ROOT.glob(glob)
        if path.is_dir()
    )
    for tree in trees:
        entry = _renderer_entry_point(tree)
        if entry in entry_points:
            continue
        path = REPO_ROOT / entry
        text = path.read_text() if path.is_file() else ""
        closure = text + (shared_text if RENDERER_DELEGATE_RE.search(text) else "")
        entry_points[entry] = bool(RENDERER_PIN_RE.search(closure))

    unpinned = sorted(entry for entry, pins in entry_points.items() if not pins)
    return {
        "entry_points": len(entry_points),
        "pinning": len(entry_points) - len(unpinned),
        "naming": len(unpinned),
        "unpinned": unpinned,
    }


def renderer_sentence(census: dict) -> str:
    """That census in exactly the sentence form `RENDERER_CENSUS_RE` matches.

    Used by `--stats` so the fix for a check-30 failure is a paste, as it is
    for checks 6, 9, 12--18, 24, 25, 26 and 28.
    """
    offenders = (
        RENDERER_CENSUS_NONE
        if not census["unpinned"]
        else ", ".join(f"`{entry}`" for entry in census["unpinned"])
    )
    return (
        f"of the **{census['entry_points']}** record-minting entry points under "
        f"`layout/`, **{census['pinning']}** resolve the `open_pdks` commit "
        f"before writing a record and **{census['naming']}** do not: {offenders}"
    )


def check_renderer_census(doc: Path, text: str) -> list[str]:
    """Check 30: the stated record-renderer census is this tree's own."""
    if not (REPO_ROOT / "layout").is_dir():
        return []
    collapsed, offsets = _collapse_quoted_prose(text)
    if not PROVENANCE_CENSUS_RE.search(collapsed):
        # A document that does not state check 26's record census states
        # nothing this one qualifies, and is not made to.
        return []
    actual = renderer_census()
    stated = list(RENDERER_CENSUS_RE.finditer(collapsed))
    if not stated:
        return [
            f"{doc.name}: states check 26's record census but not the "
            f"renderer census that explains it -- records are append-only, so "
            f"the record count alone cannot say whether a shortfall is live "
            f"or already-fixed history awaiting a re-run. State it "
            f"(`{renderer_sentence(actual)}` today), so the explanation is "
            f"graded rather than asserted"
        ]
    misses = []
    for match in stated:
        where = f"{doc.name}:{_line_of(text, offsets[match.start()])}"
        for field in ("entry_points", "pinning", "naming"):
            claimed = int(match.group(field))
            if claimed == actual[field]:
                continue
            misses.append(
                f"{where}: the renderer census says {field}={claimed}, but "
                f"`layout/` reports {field}={actual[field]} -- restate it from "
                f"`python3 docs/chipalooza/check_proposal_citations.py "
                f"--stats`, and if an entry point now resolves the commit, say "
                f"so rather than only moving the number"
            )
        listed = sorted(set(RENDERER_ENTRY_RE.findall(match.group("offenders"))))
        if listed != actual["unpinned"]:
            misses.append(
                f"{where}: the renderer census names "
                f"{', '.join(f'`{entry}`' for entry in listed) or 'no entry point'} "
                f"as resolving no `open_pdks` commit, but `layout/` reports "
                f"{', '.join(f'`{entry}`' for entry in actual['unpinned']) or 'none'}"
                f" -- restate the clause from `--stats`; naming the wrong entry "
                f"point sends a reader to the wrong file to fix it"
            )
    return misses


def runner_arms() -> list[str]:
    """The supply-return arms `ARM_RUNNER` implements, in its own order.

    Read out of the source text rather than by importing the module, for
    `report_row_count`'s reason: this gate is a pure file reader, and the
    runner imports the testbench fragment helpers. Empty when the runner is
    absent or its arm table is not in the shape this parse recognises -- both
    are "nothing to compare", which check 31 reports as an ungraded silence
    rather than as a census of zero arms.
    """
    runner = REPO_ROOT / ARM_RUNNER
    if not runner.is_file():
        return []
    source = runner.read_text()
    opening = ARM_TABLE_RE.search(source)
    if opening is None:
        return []
    end = source.find("\n)\n", opening.end())
    block = source[opening.end() : end if end != -1 else len(source)]
    return [match.group("arm") for match in ARM_NAME_RE.finditer(block)]


def record_arms() -> list[str] | None:
    """The arms the campaign's current record ran, in that record's order.

    `None` covers the three "nothing to compare against" conditions this
    module already treats alike -- no `records/LATEST`, a pointer naming a
    record that is gone, and a record whose header carries no `**Arms**` line.
    """
    stamp = _read_pointer("sim", ARM_CAMPAIGN, "records")
    if stamp is None:
        return None
    record = REPO_ROOT / "sim" / ARM_CAMPAIGN / "records" / stamp
    if not record.is_file():
        return None
    stated = ARM_RECORD_RE.search(record.read_text())
    if stated is None:
        return None
    return [match.group("arm") for match in ARM_TOKEN_RE.finditer(stated.group("arms"))]


def arm_census() -> dict | None:
    """How much of the runner's arm axis the campaign's current record covers.

    Three numbers and the unrun arms by name. `unrun` is ordered by the
    RUNNER's table rather than alphabetically, so the census reads in the same
    order as the record's own "Arms this record does not contain" section and
    a diff between the two is about content, not sort order.
    """
    offered = runner_arms()
    ran = record_arms()
    if not offered or ran is None:
        return None
    unrun = [arm for arm in offered if arm not in ran]
    return {
        "offered": len(offered),
        "ran": len(offered) - len(unrun),
        "unrun": len(unrun),
        "unrun_arms": unrun,
    }


def arm_sentence(census: dict) -> str:
    """That census in exactly the sentence form `ARM_CENSUS_RE` matches.

    Used by `--stats` so the fix for a check-31 failure is a paste, as it is
    for checks 6, 9, 12--18, 24, 25, 26, 28 and 30.
    """
    arms = (
        ARM_CENSUS_NONE
        if not census["unrun_arms"]
        else ", ".join(f"`{arm}`" for arm in census["unrun_arms"])
    )
    return (
        f"of the **{census['offered']}** supply-return arms `{ARM_RUNNER}` "
        f"implements, the record `{ARM_POINTER}` names runs "
        f"**{census['ran']}** and leaves **{census['unrun']}** unrun: {arms}"
    )


def check_arm_census(doc: Path, text: str) -> list[str]:
    """Check 31: the stated supply-return arm census is this tree's own."""
    if ARM_CENSUS_ANCHOR not in text:
        # A document that does not cite this campaign qualifies nothing about
        # the arms its records leave unrun, and is not made to.
        return []
    actual = arm_census()
    if actual is None:
        # No runner, no current record, or a record this parse does not
        # recognise: there is nothing to compare a census against, and
        # inventing one would be a claim rather than a check.
        return []
    collapsed, offsets = _collapse_quoted_prose(text)
    stated = list(ARM_CENSUS_RE.finditer(collapsed))
    if not stated:
        return [
            f"{doc.name}: cites `sim/{ARM_CAMPAIGN}/`, whose records run a "
            f"SUBSET of the arms `{ARM_RUNNER}` implements, but states no arm "
            f"census -- state it (`{arm_sentence(actual)}` today), so what the "
            f"cited record may not be read for is graded rather than asserted "
            f"and cannot be quietly dropped"
        ]
    misses = []
    for match in stated:
        where = f"{doc.name}:{_line_of(text, offsets[match.start()])}"
        for field in ("offered", "ran", "unrun"):
            claimed = int(match.group(field))
            if claimed == actual[field]:
                continue
            misses.append(
                f"{where}: the arm census says {field}={claimed}, but "
                f"`sim/{ARM_CAMPAIGN}/` reports {field}={actual[field]} -- "
                f"restate it from `python3 "
                f"docs/chipalooza/check_proposal_citations.py --stats`, and if "
                f"an arm has now been run, say what its record prices rather "
                f"than only moving the number"
            )
        listed = ARM_TOKEN_RE.findall(match.group("arms"))
        if listed != actual["unrun_arms"]:
            misses.append(
                f"{where}: the arm census names "
                f"{', '.join(f'`{arm}`' for arm in listed) or 'no arm'} as "
                f"unrun, but `sim/{ARM_CAMPAIGN}/` reports "
                f"{', '.join(f'`{arm}`' for arm in actual['unrun_arms']) or 'none'}"
                f" -- restate the clause from `--stats`; naming the wrong arm "
                f"misstates which claim the cited record cannot support"
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
        + check_coverage_index_parity(doc, text)
        + check_power_readout(doc, text)
        + check_area_readout(doc, text)
        + check_composition_inputs(doc, text)
        + check_decision_record_status(doc, text)
        + check_erc_readout(doc, text)
        + check_t1_readout(doc, text)
        + check_freshness_coverage(doc, text)
        + check_test_plan_ports(doc, text)
        + check_top_cell_inventory(doc, text)
        + check_kickback_decomposition(doc, text)
        + check_tracked_records(doc, text)
        + check_stamped_currency_claims(doc, text)
        + check_report_row_count(doc, text)
        + check_ground_return(doc, text)
        + check_provenance_census(doc, text)
        + check_label_claim_section(doc, text)
        + check_corner_grid_census(doc, text)
        + check_absent_paths(doc, text)
        + check_renderer_census(doc, text)
        + check_arm_census(doc, text)
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
            # And the other coverage census, about check 3 rather than checks
            # 4/5: how much of Section 4's table names a flow whose current
            # record is resolvable at all.
            print(
                f"{doc.name}: "
                f"{freshness_coverage_sentence(freshness_coverage(doc.read_text()))}"
            )
            # And the third census over the same table, which check 28 grades:
            # not which record a row cites or whether it is current, but how
            # many PVT points that record claims for itself. Printed per
            # document because "the full grid" is the grid the document's own
            # Section 4 states, not a constant of this script.
            corner_grid = corner_grid_census(doc.read_text())
            if corner_grid is not None:
                print(f"{doc.name}: {corner_grid_sentence(corner_grid)}")
            # And the Kickback row's own figures, which check 21 re-derives from
            # the record that row cites -- printed per document because the
            # bounds the multiples are taken against come from the row's own
            # Target cell, not from the record.
            row = _kickback_row(doc.read_text())
            if row is not None:
                bounds = _kickback_bounds(row[1][1])
                cited = [
                    match
                    for match in EVIDENCE_PATH_RE.finditer(" ".join(row[1][3:]))
                    if match.group("top") == "sim"
                ]
                if len(bounds) >= 2 and cited:
                    record = (
                        REPO_ROOT
                        / "sim"
                        / cited[-1].group("block")
                        / "records"
                        / f"{cited[-1].group('stamp')}.md"
                    )
                    readout = kickback_readout(record)
                    if readout is not None:
                        print(f"{doc.name}: {kickback_sentences(readout, bounds)}")
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
        # Likewise the composed extent of every `layout/` flow whose current
        # record carries a composition -- a flow that is a single drawn cell
        # rather than a composition has no `compose.json` and prints nothing.
        for pointer in sorted(REPO_ROOT.glob("layout/*/reports/LATEST")):
            block = pointer.parent.parent.name
            readout = area_readout(block)
            if readout is None:
                continue
            print(f"layout/{block}/: {area_sentence(block, readout)}")
        # Likewise every composed input of every `layout/` flow whose current
        # record carries a composition. The source flow of each input is
        # resolved by fingerprint rather than named here, so this prints the
        # right sentence for a sub-block the document has never mentioned.
        for pointer in sorted(REPO_ROOT.glob("layout/*/reports/LATEST")):
            block = pointer.parent.parent.name
            for cell in composition_inputs(block) or []:
                flow = _source_flow_of(block, cell)
                if flow is None:
                    print(
                        f"layout/{block}/: the composed `{cell}.gds` reproduces no "
                        f"record of any other `layout/` flow -- nothing to state"
                    )
                    continue
                provenance = composition_input_provenance(block, cell, flow)
                if provenance is None:
                    continue
                print(
                    f"layout/{block}/: "
                    f"{composition_input_sentence(block, cell, flow, provenance)}"
                )
        # Likewise every `sim/` campaign whose current record carries a Power
        # table, not only the one the Power row happens to cite today.
        for pointer in sorted(REPO_ROOT.glob("sim/*/records/LATEST")):
            experiment = pointer.parent.parent.name
            readout = power_readout(experiment)
            if readout is None:
                continue
            print(f"sim/{experiment}/: {power_sentence(readout)}")
        # And the *terminals* behind that figure, which check 19 grades in
        # Section 5's power step: the figure above is a sum, and a bench that
        # meters one of its terms is not measuring the same quantity.
        for pointer in sorted(REPO_ROOT.glob("sim/*/records/LATEST")):
            experiment = pointer.parent.parent.name
            terms = record_power_terms(experiment)
            if not terms:
                continue
            print(f"sim/{experiment}/: {power_terms_sentence(experiment, terms)}")
        # Likewise every decision record in the tree, not only the ones the
        # document happens to discuss: check 15 grades the readout in both
        # directions, so a record with no line is as much a finding as a line
        # with the wrong word.
        for name, status in decision_records().items():
            print(f"spec/decision-records/: {decision_record_sentence(name, status)}")
        # Likewise the supply verdict of every `layout/` flow that has one.
        # Keyed on the `erc-reports/` pointer rather than the `reports/` one:
        # an ERC record is minted by a separate run (`run-erc.sh`), so a flow
        # can have a current layout record and no supply verdict at all.
        for pointer in sorted(REPO_ROOT.glob(f"layout/*/{ERC_POINTER_DIR}/LATEST")):
            block = pointer.parent.parent.name
            readout = erc_readout(block)
            if readout is None:
                continue
            print(f"layout/{block}/: {erc_sentence(block, readout)}")
        # And the block-level T1 sign-off verdict, which is a single tree
        # rather than one per flow: `klt signoff` grades the whole block once.
        # Printed unconditionally when it is readable, including when it has
        # nothing failing and nothing cited -- those are the two shapes whose
        # sentence a document would otherwise have to guess at.
        t1 = t1_readout()
        if t1 is not None:
            print(f"signoff/: {t1_sentence(t1)}")
        # And the design's own device/cell inventory, which check 20 grades in
        # Sections 1 and 3: the flavour set over the whole hierarchy, then the
        # per-family census of the glue that lives outside every sub-block.
        netlist = top_netlist_text()
        if netlist:
            print(
                f"{TOP_NETLIST}: this design "
                f"{primitive_inventory_sentence(sorted(cell_census(_netlist_instance_lines(netlist), 'pr')))}"
            )
            glue = top_level_glue(netlist)
            print(
                f"{TOP_NETLIST}: outside every sub-block, "
                f"`design/sar_adc_top.sch` "
                f"{glue_census_sentence(cell_census(glue, 'sc_hd'), 'sc_hd')} "
                f"{glue_census_sentence(cell_census(glue, 'pr'), 'pr')}"
            )
        # And the row count `sim/report/generate.py --check` closes with, which
        # check 24 grades the document's quotation of. Printed as the line the
        # document quotes rather than as a bare integer, so a drifted quotation
        # is fixed by pasting this back in.
        rows = report_row_count()
        if rows is not None:
            print(
                f"{REPORT_MANIFEST}: `{REPORT_CHECK_COMMAND}` reports "
                f"`is fresh and up to date ({rows} rows)`"
            )
        # And the ground-return census check 25 grades: a property of the whole
        # `sim/` tree rather than of any one record, which is why no pointer
        # and no citation moves when it changes.
        if (REPO_ROOT / SIM_DECK_ROOT).is_dir():
            census = ground_return_census()
            print(f"{SIM_DECK_ROOT}/: {ground_return_sentence(census)}")
            for card in census["cards"]:
                print(f"{SIM_DECK_ROOT}/:   inductor card at {card}")
        # And the toolchain/PDK provenance census check 26 grades: the other
        # property of the whole evidence tree, and the one Section 8's
        # reproducibility claim to a reader of the brief rests on.
        if any((REPO_ROOT / top).is_dir() for top in ("sim", "layout")):
            provenance = provenance_census()
            print(f"sim/ + layout/: {provenance_sentence(provenance)}")
            for flow, (short, total) in provenance["unpinned"].items():
                print(
                    f"sim/ + layout/:   {flow}/ mints records naming no "
                    f"`open_pdks` commit: {short} of {total} (issue #407)"
                )
        # And the leading indicator behind that lagging one, which check 30
        # grades: not how many records name the commit, but how many of the
        # entry points that mint them resolve it at all. The two move at
        # different times -- this one on the day a renderer is fixed, the one
        # above only as each flow re-runs -- which is why both are stated.
        if (REPO_ROOT / "layout").is_dir():
            print(f"layout/: {renderer_sentence(renderer_census())}")
        # And the one campaign whose current record covers a subset of an axis
        # its runner defines rather than of the PVT grid check 28 censuses:
        # the supply-return arms, which bound what that record may be cited
        # for. Printed whenever both halves are readable, including when every
        # arm has been run -- that is a statement too, not a silence.
        arms = arm_census()
        if arms is not None:
            print(f"sim/{ARM_CAMPAIGN}/: {arm_sentence(arms)}")
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

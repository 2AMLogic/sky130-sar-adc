#!/usr/bin/env python3
"""Headless citation check for docs/chipalooza/challenge-4-proposal.md.

The Chipalooza Challenge #4 proposal (issue #121) is a hand-maintained
evidence ledger whose Section 4 verdicts cite dated `sim/<campaign>/records/`
and `layout/<block>/reports/` records by path, and whose prose asserts that
some of those records are the *current* ones. This script gates both claims
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
against) and the live `klt erc` supply readout of every `layout/` flow that
has one (the sentence check 16 compares against) instead of checking, which
is what to run when check 6, 9, 12, 13, 14, 15 or 16 reports a drift. Exit
status:

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


def record_power_table(experiment: str) -> dict[str, float]:
    """`{corner_id: total_power_uW}` from a campaign's current record.

    Read out of the record's own Power table (its last numeric column), so the
    figures check 12 compares against are the record's, never re-derived here.
    Empty when the campaign has no `records/LATEST`, no Power table, or a table
    this parse does not recognise -- all three are "nothing to compare", which
    check 12 reports rather than passing silently.
    """
    stamp = _read_pointer("sim", experiment, "records")
    if stamp is None:
        return {}
    record = REPO_ROOT / "sim" / experiment / "records" / stamp
    if not record.is_file():
        return {}
    text = record.read_text()
    heading = POWER_TABLE_HEADING_RE.search(text)
    if heading is None:
        return {}
    section = text[heading.end() :]
    end = re.search(r"^##+\s", section, re.M)
    if end is not None:
        section = section[: end.start()]
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

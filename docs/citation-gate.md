# Citation gate: why `check_proposal_citations.py` checks what it checks

This is the rationale document for
[`docs/chipalooza/check_proposal_citations.py`](chipalooza/check_proposal_citations.py),
the headless citation check for `docs/chipalooza/challenge-4-proposal.md`. The
script's own module docstring carries its purpose, usage and exit codes; every
"why this check exists", "what it deliberately does NOT cover" and "why this
tempting extension was rejected" lives here instead, in one place, so it reads
as one argument rather than as a 300-line block of prose ahead of the first
line of code (issue #321).

**Why this file is not under `docs/chipalooza/`.** The script checks every
`docs/chipalooza/*.md` it finds, so a rationale document placed beside the
proposal would itself become one of the *checked* documents -- changing both
the `--stats` census output and the final `OK: every citation in ...` line.
It lives one directory up for that reason, not by accident. Do not move it
back.

## Why this exists

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

## What it checks

### Check 1 -- link resolution (`check_links`)

Every relative Markdown link target in the document resolves to a path that
exists in this repository.

### Check 2 -- bare path references (`check_bare_paths`)

Every backticked, whitespace-free reference whose first segment is one of
this repo's own top-level directories (`sim/`, `layout/`, `spec/`, `design/`,
`docs/`, `measurements/`, `ratification/`, `signoff/`) resolves too. Not every
evidence citation is a Markdown link: Section 4's Power row, for instance,
cites its record as a bare backticked path. References whose first segment is
NOT one of ours (e.g. klayout-tools' `src/klayout_tools/lvs.py`) are upstream
paths and are left alone.

**That parenthesised list is itself gated, because it is a claim about the
gate's own coverage.** It states `OWN_TOP_LEVEL` in the checker, and a
directory absent from that frozenset is a whole tree whose bare citations
check 2 silently does not resolve -- so a typo'd or dangling `signoff/...`
path would have passed, unread, the way one did until check 17 added
`signoff` (see check 17, and check 16 for the same not-my-directory shape at
checks 3/4 with `erc-reports/`). The sentence above and the frozenset had
already drifted once: check 17 added the eighth entry and left this list
naming seven. Per this document's own discipline, the list is therefore
re-derived rather than trusted --
`TestRationaleDocumentCoverage.test_the_check_2_directory_list_matches_own_top_level`
parses this parenthetical and compares it to `OWN_TOP_LEVEL` **in both
directions**, so adding a directory to the frozenset without naming it here
(or naming one here that the frozenset does not carry) fails
`npm run test:unit`.

**One exemption, and it is not a hole.** A path immediately followed by the
literal marker `(not in this tree)` is the document asserting that path is
*absent*, not citing it, so check 2 skips it -- and check 29 then asserts the
absence, failing if the path ever does exist. The two share one path-shape
test, so nothing falls between them; see check 29 for why the exemption
exists at all.

### Check 3 -- spec-row freshness (`check_spec_table_freshness`)

This is the load-bearing check. In the Section 4 spec table, each row is one
graded verdict, and each row must cite the *current* evidence for every flow
it draws on: for each `layout/<block>/` or `sim/<campaign>/` flow a row
cites, at least one of that row's cited record stamps must be what the flow's
own `LATEST` pointer resolves to. A row may additionally cite superseded
records (this document's style is to keep the supersession trail visible, and
that is not a defect) -- what it may not do is cite *only* superseded ones,
which is exactly the drift PR #239, #242, #276 and #282 each had to correct
after the fact. Flows with no `LATEST` pointer are skipped: there is nothing
to be stale against.

### Check 4 -- pointer freshness (`check_pointer_claims`)

Wherever the document says a cited record is the "current `reports/LATEST`" /
"current `records/LATEST`", the record named immediately before that phrase
must be the one the pointer file actually resolves to.

### Check 5 -- pointer naming (`check_pointer_claims`)

A `sim/` campaign's pointer must be claimed as `records/LATEST` and a
`layout/` flow's as `reports/LATEST`. This is the check for PR #295/#300's
defect class.

### Check 6 -- census freshness (`check_census`)

Checks 4 and 5 do not cover every pointer claim in the document (see "What
the gate deliberately does not cover" below), so the document states, in
prose, how many of its claims they *do* cover. That census is itself a
volatile fact about a document several passes a day append to, and it went
stale the first time it was hand-written: PR #312 added two pointer claims of
the skipped kind and the "9 of 19" census three files carried (the checker's
rationale, the proposal's own "Reproducing this table" note, and
`.github/workflows/ci.yml`'s inventory comment) silently became "9 of 21"
without any of the three moving. Check 6 recomputes the census and fails if
the document's stated one disagrees, so the coverage claim cannot drift away
from the coverage. It fires only on a document that states a census --
absence is not a failure here, because `check_document` also runs against
test fixtures; that the real proposal states one is asserted by
`sim/tests/test_proposal_citations.py` instead.

### Check 7 -- spec-row parity (`check_spec_row_parity`)

Checks 3 to 6 all verify how a Section 4 row cites its evidence; nothing
verified that the row is *about the same spec line* the ratified spec states.
Issue #121's acceptance criterion 2 is "every spec row states met/unmet
against the brief; no row is relaxed to make it pass", and the repo's own
standing rule is blunter: "agents do not relax a spec line to make a result
pass" (CLAUDE.md). Both were hand-verified every pass. Check 7 makes them
mechanical -- for each row of `spec/target-spec.md`'s own Target table:

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

### Check 8 -- verdict vocabulary (`check_verdict_vocabulary`)

Acceptance criterion 2's other half, "every spec row *states* met/unmet".
Section 4's preamble defines the verdict kinds the table uses, and each row's
verdict cell must open with one of them. Both directions are enforced, so
neither list can drift from the other: a row opening with an undefined kind
fails, and a defined kind no row uses fails too. The preamble had already
drifted when this check landed -- it announced "three cases", listed four
bullets, and the table used six distinct kinds, of which one bullet (`DRAFT /
not ratified`) was really a *Status* value rather than a verdict. Skipped on
a document whose Section 4 defines no kinds (test fixtures), like check 6.

### Check 9 -- sign-off-bar readout parity (`check_signoff_readout`)

Checks 3 to 5 gate which record a row *cites*; nothing gated the numbers the
document quotes *out of* that record. That is a real gap on exactly the two
rows the brief's sign-off bar grades ("Post-layout PVT simulation, full ADC"
and "DRC/LVS-clean GDS, full ADC, in-repo"), whose verdicts rest on figures
hand-copied out of `layout/sar-adc-top/`'s `drc.json` / `lvs.json`: the
mismatch count, the device/net/pin correspondence, the category breakdown.
Those figures really do move -- this document has already carried 98, then
128, then 124, then 98 again as the flow was re-run -- and when they move,
check 3 forces the *citation* forward while leaving every quoted number
behind it untouched.

So the document states each flow's current readout once, in a fixed
sentence form, and check 9 recomputes it from the record that flow's
`reports/LATEST` actually resolves to and compares field by field: DRC
status and violation count, LVS status, mismatch and error counts, the
three-way device/net/pin counts, and the full `category_counts` mapping
(both directions -- a category the document omits and one it invents are
both reported). `--stats` prints the live sentence for every `layout/`
flow, so the fix for a check-9 failure is a paste, not a hand
transcription. Like checks 6 to 8 it is opt-in per document and inert
when no readout is stated; that the real proposal states one is asserted
by `sim/tests/test_proposal_citations.py`.

The check is per *stated readout*, not per document, so it covers as many
flows as the document states -- since 2026-09-17 that is six rather than
one: the composed `layout/sar-adc-top/` whose numbers the brief's two
sign-off-bar rows quote (Section 4), plus the five sub-block flows that
composition is built from (Section 3), whose DRC/LVS verdicts had been
prose ("all DRC-clean and LVS-clean") with the one Section 4 row grading
on them citing a README rather than a dated record. That is not a
theoretical drift class here: `layout/cdac-array/`'s first LVS "match"
verdict did not reproduce against its own committed artefacts (#148), and
a hand re-read is what caught it. Which flows the real document must state
a readout for is asserted, by name, in
`sim/tests/test_proposal_citations.py`, so dropping one is a test failure
rather than a silently narrower gate.

What it does NOT do, stated rather than glossed: it does not parse the
numbers out of Section 4's or Section 7's prose. Those sections are full
of *dated historical* figures ("moved from the pre-bump 98 mismatches to
128 ... then to 124") that were true when written and are correct as
written -- the same reason checks 4 and 5 skip the stamp-after-claim form
(see below). The readout is the document's single present-tense
statement of those numbers, and it is the one that is gated.

### Check 10 -- I/O table parity (`check_io_table_parity`)

Checks 3 to 9 all grade Section 4. Section 2 carries the document's other
mechanically checkable claim, and issue #121's acceptance criterion 1 states
it directly: "I/O mapped to the slot budget". That mapping is a
hand-maintained restatement of `design/sar_adc_top.spice`'s own `.subckt
sar_adc_top` port list -- and that netlist is regenerated from
`design/sar_adc_top.sch`, whose contents this repo really does change (DR-004
Amendment A moved the comparator's device count; DR-008 and DR-009 changed
the CDAC and comparator interfaces). A port added, renamed, or dropped at the
schematic level would leave Section 2 silently describing a block this repo
no longer builds, with nothing but a re-read to catch it -- the same drift
class as every other check here, one section up. Check 10 compares:

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
   the "Assumed Challenge slot" column, never a list in the script), and
   the conditional dedicated-pad total must be the dedicated pads plus
   the harness-supplied reference lines. A row that is charged against
   the budget but matches no category is reported too, so a new row
   cannot slip past the totals by being uncategorised.

Inert when the netlist or the table is absent (test fixtures); that the
real ones are found is asserted by `sim/tests/test_proposal_citations.py`.

### Check 11 -- coverage-index parity (`check_coverage_index_parity`)

Checks 3 to 9 all grade a Section 4 row against the evidence it *already
cites*. None of them can see the opposite defect: a row that grades a spec
line while ignoring a campaign this repository has already indexed as that
row's evidence. That is not hypothetical, and it is the worst-shaped drift of
the lot because it *understates* the design --
`sim/full-conversion-transient/` has carried a 9-corner whole-ADC power table
since 2026-09-12, indexed under the Power row of `sim/spec-coverage.json` and
written out in full in `docs/characterization-report.md`, while Section 4's
Power row still read "BLOCKED / UNMEASURED -- no full-block power campaign
exists" and cited only a digital sub-block's PnR estimate. Every other check
passed on that row: its one citation was current, its bounds matched, its
status word agreed.

So the row set is compared against `sim/spec-coverage.json` -- this
repo's own spec-row -> bench -> evidence index (T1 item 9, issue #31),
whose own freshness is gated by `sim/check_spec_coverage.py`. For every
indexed row whose `claim_class` rests on committed evidence
(`ratified-measured` / `draft-informational`), the Section 4 row of the
same parameter must cite a record of every `sim/` campaign indexed under
it. `structural` and `methodology` rows are excluded by class, not by
name: the index's own vocabulary says they name no DUT quantity, and
their Section 4 rows cite schematics and corner-harness directories
rather than records, so there is nothing for them to be stale against.
`unbenched` rows have no evidence at all.

Section 4's `| same record |` deferral (the LSB and Sampling-cap rows
inherit `V_REF`'s campaign rather than re-citing it) is *resolved*, not
skipped -- a deferring row is held to the same parity as one that cites
inline, so the deferral cannot become a hole.

Why the index and not `docs/characterization-report.md`, which Section
4's own preamble names as the authoritative source it mirrors: that
report is the better *content* reference (it is regenerated by
`sim/report/generate.py`), but its per-row Evidence lists mix primary
and incidental flows -- its Resolution row lists the CDAC transfer
campaign, its Corners row lists six flows -- so requiring Section 4 to
cite all of them fails on rows that are correct as written. Its Verdict
fields are free prose, so they cannot be compared to Section 4's verdict
vocabulary either. Recorded here so the idea is not re-proposed blind.

Inert when the index is absent or has no rows (test fixtures); a spec row
missing from Section 4 entirely is check 7's finding, not re-reported
here.

### Check 12 -- power-readout parity (`check_power_readout`)

The numeric half of what check 11 found. Once the Power row reports figures,
those figures are hand-copied out of a record that is re-run every time the
design changes (this campaign has already carried four different power sets
as #257, DR-008 and DR-009 landed), and check 3 would dutifully force the
*citation* forward while leaving the numbers behind -- the exact failure
check 9 exists for on the sign-off-bar rows.

So the Power row states its min/typ/max once, in a fixed form naming the
corner each figure was measured at, and this check recomputes all of it
from the cited campaign's own current record: the lowest and highest
total-power corners, the nominal (`tt_27c_1.80v`) point, and how many
corners the table has. `--stats` prints the live sentence for every
`sim/` campaign whose current record carries a Power table, so a fix is a
paste rather than a transcription.

Inert on a row that states no readout, and reported (not silently
skipped) when a row states one but cites no campaign whose current record
carries a Power table.

### Check 13 -- area-readout parity (`check_area_readout`)

The last hand-transcribed figure left in Section 4, and the third instance
of the same defect shape as checks 9 and 12. The Area row quotes a bounding
box out of `layout/sar-adc-top/`'s own `compose.json` -- four corner
coordinates, the width and height they imply, and the mm^2 that follows --
and nothing recomputed any of it. What check 3 gates there is only *which*
record the row cites; every time that flow re-ran (five times so far:
`20260906-101939-1250ff4` -> `20260907-110058-a546200` ->
`20260908-072857-80df05e` -> `20260915-213439-bf2256f` ->
`20260915-234004-76f48b9`) an agent moved the citation forward and then
established *by hand* -- `cmp`, or a field-by-field diff of the two
artefacts -- that the numbers had not moved. That hand check is exactly
what the gate exists to replace, and it is one that gets skipped precisely
when it matters: the one re-run where the box really did change is the one
where "byte-identical, verified directly" is the wrong sentence to carry
forward. It is not hypothetical either -- the `v0.5.0` rebuild moved a
*sub-block* bbox (`sampling_frontend` `y1` 146.3 -> 147.22 um) while
leaving the top-level box alone, so a re-run that moves geometry without
moving the composed extent has already happened here once.

So the Area row states its readout once, in a fixed form, and this check
recomputes every field of it from the `compose.json` of the record that
flow's `reports/LATEST` actually resolves to: the composed `cell_name`, the
four `bbox_um` coordinates, and the width/height/area derived from them.
Figures are compared as formatted at the document's own stated resolution
(three decimals, which is also the record's own `dbu_um` of 0.001 um)
rather than with a tolerance, so what `--stats` prints is exactly what
passes -- no rounding edge case can make a pasted sentence fail. The
derived width/height/mm^2 are not independent of the coordinates; they are
gated anyway because they are what the document actually quotes, and an
arithmetic slip in a hand-written "i.e." clause is as wrong as a stale
coordinate.

Reported (not silently skipped) when the row states a readout for a flow
with no readable `compose.json`, and when it states one for a flow it cites
no record of -- a readout attributed to a composition this row does not
cite is not this row's evidence.

### Check 14 -- composition-input parity (`check_composition_inputs`)

Checks 3 to 13 all grade a claim against the record it cites. This one grades
the record's own *inputs*, which nothing else in this repository ties to
anything.

`layout/sar-adc-top/bin/run-flow.sh` builds the composed top level by copying
each sub-block's `reports/LATEST` top-cell GDS in as `<block>.gds` and handing
the set to `klt gen-compose`. That resolution happens at run time and is not
recorded anywhere: `compose.json` names each block, its offset and its bounding
box, but nothing about *which record* the geometry came from -- no source path,
no digest, no stamp. (Filed generically upstream, since it is a `klt` output
gap rather than a fact about this design.) The record is therefore a snapshot
of five sub-block records taken on one day, with no trace back to them.

That is exactly where Section 3 and Section 4 can silently disagree. Section
3's five sub-block sign-off readouts are recomputed from each flow's *current*
record by check 9, while Section 4's two sign-off-bar rows and its Area row are
graded on the *composed* record. Re-run a sub-block and check 9 moves Section
3's numbers forward; the composition is untouched and keeps grading geometry
from the superseded record, with every other check green. It is not a
hypothetical: it is the tree's state as of 2026-09-18. Issue #323's
version-parity pass (PR #327) re-ran three sub-block flows under the pinned
`klt 0.5.0` on 2026-09-17, and the composition `reports/LATEST` resolves to was
built on 2026-09-15 -- so two of its five embedded inputs reproduce records
their own flow no longer points at.

So the document states, per composed input, how many records of the named flow
the embedded copy reproduces, the newest of them, what that flow's pointer
names today, and the verdict word those two imply. The verdict is **current**
when the flow's own pointer is among the reproduced records and **superseded**
otherwise -- *not* "the newest match is the pointer", which is a different
claim: `layout/comparator/` today carries a record minted after the one its
pointer names, so its newest match is not its pointer and the input is current
all the same.

Coverage is graded in both directions, like checks 8 and 10: a document that
states one composed input of a composition must state all of them, because
dropping the line for the one input that went superseded is otherwise the
cheapest way to make the readout look clean.

**Records are compared by fingerprint, not by geometry.** The digest hashes
the GDS record stream verbatim except the two record types whose payload is a
wall-clock timestamp (BGNLIB/BGNSTR), which move on every write and describe
nothing. Everything else is exact, element *ordering* included -- so two
records holding geometrically equivalent but differently-ordered GDS (a
re-run of a non-deterministic place-and-route flow produces exactly that) are
reported as different. That is the conservative direction, and deliberate: a
false **superseded** costs one hand check, while a false **current** would
hide a real input drift. Establishing that two such records really are
equivalent needs a layer-by-layer XOR, which needs `klayout`; the always-on
`checks` CI job installs no PDK and no `klayout`, so that comparison cannot be
this gate's job. What the gate can do -- and does -- is make the question
appear at all.

**A composed input that reproduces no record at all is a finding, not a third
verdict word.** There is deliberately no vocabulary for it, because it is also
what a broken fingerprint parser would produce, and a document must not be
able to state its way past its own gate going vacuous.

### Check 15 -- decision-record status parity (`check_decision_record_status`)

Checks 3 to 14 all grade the proposal against `sim/` and `layout/` evidence.
This one grades it against `spec/decision-records/`, the third tree its
verdicts rest on and the only one nothing here reached.

Check 7 already compares Section 4's Status column to `spec/target-spec.md`'s
own words. That is the right comparison, but it is not the *earliest* one.
This repo ratifies a numeric spec row by the operator approving the PR that
carries its decision record (the standing policy `spec/target-spec.md`'s
"Numeric rows -- RATIFIED 2026-08-19" section records), so the sequence is:
the record's own `- **Status**:` field moves `proposed` -> `accepted`, and
`spec/target-spec.md` follows in a later edit. **In the window between those
two, every existing check is green and the document is wrong** -- Section 4
reads `DRAFT` against a spec file that also reads `DRAFT`, while the record
both of them rest on has already been ratified.

That window is not hypothetical for this document. Section 7 Item 4's whole
subject is DR-007's status, and its own text records the hand check it took:
"DR-007's status was re-checked live -- still `proposed`". Every pass that
touched the item repeated that re-read. It is the same manual step checks 9,
12, 13 and 14 each replaced for a different tree.

So the document states every record's status once, in a fixed sentence form,
and this check recomputes it from each record's own Status field. Records are
enumerated from the directory rather than from a list in the script, so one
added by a future pass is discovered instead of remembered; `TEMPLATE.md` is
excluded by its own **file-name shape** (it carries no DR number) rather than
by name, and that matters here beyond tidiness -- its Status field is a
vocabulary enumeration (`proposed | ratified | superseded by DR-NNN`), not a
status, so a name-list exclusion would quietly start comparing against it if
the file were ever renamed. Coverage is graded both directions, like checks 8,
10 and 14: dropping the line for the record that just moved is otherwise the
cheapest way to keep the readout clean.

**The DR number and the file are stated, and compared, separately.** This tree
carries two DR-004s (comparator topology, sampling-front-end sizing) and two
DR-007s (revised ENOB/INL-DNL targets, sampling-front-end n-well domains), and
the proposal names decision records by bare number throughout. A readout line
that pairs one number with the other file's path reads as true and is not, so
the number is checked against the file name's own.

The collision also gets its own finding: when two records share a number and
their statuses **disagree**, every bare `DR-<n>` reference in the document
becomes unresolvable, and the check reports it naming both files. While they
agree -- as all four do today -- a bare reference is unambiguous about status
and nothing is reported, so this does not force a document-wide rewrite for a
collision that is currently harmless.

**A bare `DR-<n>` naming no file is deliberately NOT a finding**, and is
recorded here so a stricter rule is not proposed blind. Two such references in
the proposal are correct as written: `DR-002` is a tripwire *clause* inside
`spec/target-spec.md` rather than a record of its own, and `DR-0005` is the
port-parity sibling `gf180-sar-adc`'s record, named there precisely to say
this repo has no equivalent. Requiring every `DR-<n>` token to resolve to a
local file would fail the gate on both.

Like every opt-in check here it is inert on a document that states no readout
at all -- that the real proposal states one is asserted by
`sim/tests/test_proposal_citations.py`. What it does **not** do is go inert on
a *stated* readout whose records are missing: naming a record this repository
does not carry, or one that states no Status field of its own, is reported,
the same rule checks 13 and 14 apply. Skipping it would let the readout
outlive the directory being renamed or emptied.

What it does not read is the rationale after the status word. A record's
Status field is `proposed -- this record ratifies nothing ...`; only the first
word is the status, and the prose after it is the record's own argument, not a
fact this document restates.

### Check 16 -- ERC supply readout parity (`check_erc_readout`)

The first check to reach a `layout/` flow's **second** evidence tree. A flow's
DRC/LVS verdicts live under `reports/<stamp>/`; its `klt erc` supply verdicts
are minted by a separate run (`layout/<block>/bin/run-erc.sh`) into
`erc-reports/<stamp>/`, with a `LATEST` pointer of its own. `EVIDENCE_PATH_RE`
matches `records|reports` only, so **every ERC citation in this document is
invisible to checks 3 and 4** -- `layout/sar-adc-top/erc-reports/<stamp>/` is
not a `reports/` path, and no amount of citing it made it one. The proposal
carries an ERC readout in two places (Section 3's `klt erc` bullet and Section
7 item 9's per-supply island table), and until this check landed both were
hand-transcribed prose that nothing would have caught going stale -- the exact
drift class this gate exists for, one directory over from where it was already
guarding.

That the drift is real here rather than theoretical is on the record: item 9
was written on 2026-09-23 against a failing run (`VPWR`/`VGND` at two islands
each), and had to be re-transcribed by hand on 2026-09-24 when issue #355's
supply-rail tie moved every number in it. The same item's own text carries the
hand check twice -- "the ERC record is no longer a revision behind" was a
qualification a pass added, then a later pass discharged, both by re-reading.

So item 9 states the readout once, in a fixed sentence form, and this check
recomputes all of it from the record `erc-reports/LATEST` actually resolves
to: `erc_status`, the finding count, the per-supply island counts, the layout
record the run graded, and what that flow's `reports/LATEST` names today.
`--stats` prints the live sentence for every `layout/` flow that has an ERC
record, so a fix is a paste.

**Island counts are reconstructed, not read.** `klt erc` reports an island
count only on the *failing* side, inside the `erc.unconnected_net` finding
that carries the islands themselves; a passing supply produces no per-net
number at all. So the "1" this readout states against each supply comes from
the record's own `erc_coverage.checked` list -- a net that was graded and drew
no finding resolved to exactly one island. Doing it this way is what lets the
readout gate a **passing** table, which is the state this document is actually
in and the one that goes stale silently. Coverage is graded in both directions
like checks 8, 10, 14 and 15: a supply that disappears from the spec's
`nets[]` (the cheapest way to make a failing continuity table read clean) is a
finding, not a shorter table.

**The verdict word is the ERC record's own "Staleness rule" made mechanical.**
Each ERC record states that a newer `reports/<id>/` makes it stale, not wrong.
This check evaluates that: `current` requires both that the ERC run graded the
record `reports/LATEST` names **and** that the stream's sha256 still equals
the `provenance.input.content_hash` `run-erc.sh` pinned at run time. The hash
half is the load-bearing one -- a stamp comparison alone would call an ERC
verdict current while the layout record it names had been rebuilt underneath
it. Nothing is re-derived: the number compared against is the one the tool
itself recorded.

Anything unreadable resolves to `stale` rather than to an error: a missing
`file` field, an absent hash, a stream this checker cannot open. That is the
conservative direction, and it is chosen on the same reasoning as check 14's
fingerprint -- a false `stale` is re-checked by hand, a false `current` would
let an ungraded layout pass as power-delivery-checked.

**What this check deliberately does NOT cover**, stated so it is not read as
more than it is. It does not grade whether item 11 is *met*: continuity is one
half of that item, `erc.missing_tie` is the other, and that check is not
computed at all for this block (disclosed in the record as
`ties_disclosure.kind = "tool_limitation"`, klayout-tools#2169). A green check
16 therefore says "the stated supply readout is the current record's own", not
"power delivery is signed off" -- `signoff/t1-report.json` is what grades the
item, and it reads `unmet`. Nor does it read the antenna half of the same
report: `status: clean_partial` is a different claim about a different subject
(klayout-tools#1994), and item 9 quotes neither.

### Check 17 -- T1 sign-off readout parity (`check_t1_readout`)

The first check to reach a tree that is not a `layout/` flow's at all.
`signoff/` holds this block's `klt signoff` manifest
(`signoff/block-manifest.json`) and the machine-graded report it renders to
(`signoff/t1-report.json`) -- this repository's T1 verdict of record since
issue #345 -- and no earlier check can see either: they are neither a
`records/`/`reports/` path (checks 3 and 4) nor an `erc-reports/` one (check
16), and until this check landed `signoff` was not even in `OWN_TOP_LEVEL`,
so check 2 did not verify a backticked `signoff/...` path existed.

**The drift shape is the one this document was already in.** Section 7 item 9
quoted that report's *two item-11 rows* -- "moved from `no_evidence` to
`check_failed`" -- and nothing else, by hand. A reader got the grade of the
one item that section happened to be discussing and no indication of what the
same report makes of the other ten; and every number in the quote would have
gone stale silently the next time `signoff/run-signoff.sh` re-rendered the
report. Item 10 now states the scorecard once, in a fixed sentence form, and
this check recomputes all of it: the grader version, the met count, the item
total, the block tier, the exact set of rows graded `check_failed`, and every
`layout/` record the manifest cites. `--stats` prints the live sentence, so a
fix is a paste.

**Both files are read, for different reasons.** The report states the verdict;
the manifest names the records that verdict rests on. The rendered report
cannot serve for the second: `klt signoff` drops the citation from every item
it grades `unmet` (an unmet row renders `citation: null`), so items 4 and 11 --
precisely the two whose evidence *was* read -- cite nothing in the report
itself. Walking the manifest's `evidence` tree is what lets this check see the
`reports/` **and** `erc-reports/` records the sign-off actually rests on.

**Rows are graded in both directions**, like checks 8, 10, 14, 15 and 16. A
row that starts failing and is left out of the list is a finding; so is a
listed row that has since started passing. Dropping a row is the cheapest way
to make a scorecard read better than it is, and shrinking the list is not a way
to keep it truthful.

**The failed-row list is scoped to tier T1** (the `T1_TIER` constant), because
the counts beside it are: `met` and `total` are the report's `t1_met_count`
and `t1_item_count`. `klt signoff` grades every T2/T3/T4 row
`tier_not_supported` today, so the scope changes no current readout -- but the
first time the grader fails a higher-tier row for a real reason, an unscoped
list would enrol it as a T1 failure under a T1 headline (issue #379).

**The cited-record clause is graded in both directions too.** A `layout/`
record the manifest cites that the readout omits is a finding, and so is a
stated citation the manifest no longer makes -- the same rule as the rows, for
the same reason: dropping a stale citation from the sentence would otherwise be
the cheapest way to make the verdict word read `current`.

**The verdict word is the half `signoff/check_evidence_hashes.py`
structurally cannot cover.** That script re-hashes every artefact the manifest
cites against the file on disk -- a real freshness gate, and the one the
grader itself cannot do (klayout-tools#2196). But a manifest pinned to a
**superseded yet still committed** record passes it with every hash intact:
the bytes it names are exactly the bytes on disk, and the record is simply no
longer the one that tree's `LATEST` names. Check 17 asks that second question,
for each cited tree, and reads `stale` if either has moved -- including when
the manifest cites no `layout/` record at all, which is the conservative
direction: a sign-off resting on nothing from this repository's layout trees
cannot be *current* with them, and a green there would be vacuous.

**What this check deliberately does NOT cover.** It does not re-grade the
checklist: whether an item *should* be met is `klt signoff`'s judgement
against its own ruleset, and re-deriving it here would be a second, divergent
grader. It does not verify the report is what the manifest currently renders
to either -- `signoff/run-signoff.sh --check` is that gate, and it runs in
CI's own `signoff-check` job with the pinned grader installed. A green check
17 says "the scorecard this document states is the committed report's own, and
that report rests on current layout records", not "the sign-off is correct".

### Check 18 -- Section 4 freshness coverage (`check_freshness_coverage`)

Check 6 gates how much of the *prose* checks 4/5 cover. Nothing gated how
much of the **table** check 3 covers, and check 3 is the load-bearing one.

Check 3's own entry above ends "Flows with no `LATEST` pointer are skipped:
there is nothing to be stale against." That is true, and it is also the
entire uncovered set -- stated only here, in the rationale document, and
nowhere a reader of the proposal would meet it. The proposal's own summary of
the gate said the opposite: "every row of the table above cites the *current*
record of each `sim/`/`layout/` flow it draws on", without qualification. Of
the 21 (row, flow) citation pairs in Section 4 when this check landed, **7 --
spanning six rows and four `sim/` campaigns -- were not graded at all**, and
their cells read exactly like the graded ones. That is the same
prose-overstates-the-gate shape the "What 'attached' excludes" paragraph
already had to correct once for checks 4/5, one table over.

**The pair, not the citation, is the unit**, because it is what check 3
evaluates: a row naming three stamps of one flow is one verdict about one
flow. And each uncovered flow is stated **with its record count**, which is
what says how large its hole is. A pointerless campaign holding one record has
no other record its row could have meant; the twelve-record one is a citation
chosen out of a set nothing re-derives.

**Graded in both directions**, like checks 8, 10, 14, 15, 16 and 17. A
campaign that starts publishing a pointer must leave the list; a flow that
loses its pointer, or that a newly added row starts citing, must join it.
Shrinking the list is the cheapest way to make the gate's coverage read better
than it is.

**Why "just require every cited flow to publish a `LATEST`" is rejected** --
recorded here so it is not re-proposed blind. It reads like the obvious fix
and it is wrong for at least one of the flows it would apply to.
`sim/comparator-decision` holds twelve records that are **not a supersession
chain**: they carry three distinct claims -- input-referred noise, decision
delay, and kickback -- and three different Section 4 rows cite three different
records of it on purpose. There is no single "current" record of that campaign
for a pointer to name, so minting one would not make those three rows graded;
it would make two of them *wrongly* graded, and the fix for the resulting CI
failure would be to re-point a correct citation at an unrelated record. The
same shape can arise in any campaign whose records answer more than one
question. Making the uncovered set visible is the honest gate; making it
empty by fiat is not.

**What this check deliberately does NOT cover.** It says nothing about
whether an ungraded citation is *stale* -- it cannot, which is the point:
that judgement is exactly what no pointer file exists to make. A green check
18 says "the table's ungraded set is the size and membership this document
states", not "every citation in the table is current".

### Check 19 -- Section 5 bench-plan interface parity (`check_test_plan_ports`)

Checks 1-18 all grade Section 4 (the spec table) or Section 2 (the I/O
mapping). **Nothing graded Section 5**, the bench test plan -- which is the
third deliverable issue #121's acceptance criterion 1 names, beside the I/O
mapping and the spec table, and the only one of the three written as a
*procedure* rather than as a verdict.

Section 5's own lede claims it "is written against this design's *current*
port list (§2)". It was not. Three supply ports joined the interface on
2026-09-24 -- `VPWR` and `VGND` by DR-010 (issue #355), `GND` by DR-012 (issue
#362), taking the block from 19 ports to 22 -- and Section 5's bring-up step
went on applying `VDD`, `VREFP`/`VREFN` and `VCM` only. Nothing about the page
looked stale: the step named real ports, the lede named the right section, and
check 10 was busy grading Section 2's table, which had been updated correctly.
A reader following step 1 verbatim would have left both standard-cell macros
unpowered.

**Three parts, because the section makes three separable claims.**

- **(a) Every netlist port is named somewhere in Section 5.** Forward direction
  only: a bench plan that omits a terminal is not executable, whereas a
  backticked token in Section 5 that is not a port is usually a unit, a signal
  name internal to a measurement, or a decision-record id -- graded in reverse
  this would fail on correct prose. `DOUT9..0` expands to the ten ports it
  names (the same `_expand_range` check 10 uses on the Signal column); the glob
  `DOUT*` deliberately does *not* -- it says the section discusses the bus, not
  that it named each line of it.
- **(b) The supply terminals the plan feeds are exactly Section 2's rail rows**
  -- both directions, like checks 8, 10, 14, 15, 16, 17 and 18. "Rail row" is
  read off the same Count column check 10 part (d) already treats as the
  slot-budget exemption (a cell not beginning with a digit), so the two checks
  cannot disagree about which rows are rails. A rail dropped from this sentence
  under-powers the bench; one added that Section 2 does not carry invents a
  terminal the part does not have.
- **(c) The power step meters the cited record's own Power-table columns.**
  This is the part that catches a defect no re-read would: step 6 said "measure
  `VDD` supply current" and compare against Section 4's Power row, but that
  row's figure is a **sum over five** source columns
  (`I(VDD)`, `I(VPWR)`, `I(VREFP)`, `I(VCM)`, `I(VREFN)`) in which `VDD` is not
  the dominant term. The instruction was not a wrong *number* -- it was a wrong
  *protocol*, producing a reading that is not comparable to the figure it is
  told to compare against, and it became wrong the moment DR-010 moved the
  digital current onto its own rail. The campaign is named in the sentence
  rather than in the script, so the check stays pointed at whatever record
  Section 4 actually quotes.

**Why not gate Section 5 against `spec/target-spec.md`'s rows as well** --
recorded here so it is not re-proposed blind. Section 5 has six steps and the
spec table has more rows than that, deliberately: the steps are *bench
procedures* (a code-density sweep covers INL and DNL at once; "bring-up" grades
no row at all), not a row-per-step restatement. Requiring a step per row would
either force the section into a shape that misrepresents how the measurements
are actually taken, or force a row-to-step map that is itself hand-maintained
prose -- one more thing to go stale, gating the wrong claim. What the section
*does* claim mechanically is that it addresses the current **interface**, and
that is what this check grades.

**What this check deliberately does NOT cover.** It says nothing about whether
a step's procedure is correct, sufficient, or the one a bench would really run
-- only that the terminals it names are the ones this part has, and that the
power step meters the terminals the figure it cites is summed over. It also
does not check step *ordering* or that a port is named in a sensible step: a
port named only in a parenthesis somewhere in Section 5 satisfies part (a).
That is the honest limit of a text check against a procedure; the parts that
can be re-derived from this repository's own trees are re-derived, and the
judgement is left where judgement belongs.

### Check 20 -- device/cell inventory parity (`check_top_cell_inventory`)

Check 10 grades the top cell's **ports**. Nothing graded what is *inside* it.
That gap is not hypothetical: DR-008 (issue #263, PR #266, 2026-09-11)
replaced the nine `SELn<i> = NOT(DOUT<i>)` inverters issue #56 drew at the
integration level with eighteen decision-directed `and2_1` gates, added a
nine-gate `xor2_1` readout recode, and DR-009 added a half-LSB
quantizer-offset network of eight `sky130_fd_pr` devices -- none of which
moved a port, so check 10 had nothing to say, and Sections 1, 3 and 7 went on
describing the top level's glue as "the nine `SELn<i> = NOT(DOUT<i>)` glue
inverters" for two weeks. The same staleness is *still* carried by
`layout/seln-inverters/`'s hand-written netlist and by
`layout/sar-adc-top/bin/generate-lvs-reference.py`'s wrapper, both of which
say in their own headers that they mirror instance lines that no longer
exist -- which is Section 7 Item 1's business, not this check's, but it is
what makes the census worth gating rather than narrating.

**Two parts, over two different scopes.**

- **(a) Section 1's `sky130_fd_pr` flavour set, over the whole hierarchy** --
  both directions, like checks 8, 10, 14, 15, 16, 17 and 18. This is the
  sentence Section 2.1's rail position rests on: a thick-oxide
  `nfet_g5v0d10v5`/`pfet_g5v0d10v5` pass device entering the netlist is the
  DR-002 tripwire, and it should fail CI rather than wait for a reader.
  `design/regen_netlist.sh --check` carries its own DR-001 flavour gate over
  the same netlist, but (i) it grades the netlist, not the document, and (ii)
  it runs only in `ci.yml`'s PDK-gated `pdk-smoke` job -- nightly,
  `workflow_dispatch`, or an opt-in label -- whereas this runs on every pull
  request. Neither substitutes for the other.
- **(b) Section 3's per-family census of the glue outside every sub-block** --
  instance total, type count, and the per-type counts, each in both
  directions. Per-type rather than a bare total on purpose: a cell type
  swapped for another in equal number is exactly the DR-008 shape, and a
  total-only census would pass straight through it.

The scope in (b) is the region between `design/sar_adc_top.spice`'s
commented-out `**.subckt sar_adc_top` header and its `**.ends` -- the
integration-level logic `design/sar_adc_top.sch` owns, as distinct from
anything a sub-block schematic (and therefore a sub-block layout flow) is
responsible for. Counting is done by matching `sky130_fd_(pr|sc_hd)__<cell>`
tokens on non-comment lines rather than by parsing SPICE card grammar: a net
name never has that shape, a subcircuit call names its cell last, and a
device card names its model before its first `key=value`, so one token match
per instance line covers both card shapes. Comment lines are dropped first --
this file's own provenance header names the ratified flavour set in prose,
and a census taken over raw text would count that sentence as instances.

**What this check deliberately does NOT cover.** It grades *what* is
instantiated, never *how it is wired*: DR-008's `SELp<i> = DOUT9 AND DOUT<i>`
would still pass if the two inputs were swapped, or if the gate drove the
wrong array side. Connectivity is what `klt lvs` is for, one flow down --
and Section 7 Item 1 records the standing limitation there, that the
top-level LVS reference is generated from the same superseded wiring as the
layout it is compared against, so it is self-consistent rather than checked
against `design/sar_adc_top.spice`. This check is the cheap half: it makes
the document's *inventory* re-derived, which is what caught that.

### Check 21 -- the Kickback row's derived figures (`check_kickback_decomposition`)

Checks 12, 13, 16 and 17 re-derive a Section 4 figure from a machine-readable
artefact (`compose.json`, `erc.json`, a `klt signoff` report). The Kickback row
has no such artefact: its record's figures live in a Markdown table, and the
row's *interpretation* of them is hand-written arithmetic. Both halves went
wrong, and in the direction that makes the row read better than the evidence
supports.

The row quotes a **73.3673 mV** worst-case peak against a DRAFT `≤ 5 mV` target
and then subtracts the record's `Vindiff = 0 mV` control row (`−70.3419 mV`) to
conclude that `≈ 4.1 %` of the disturbance is decision-coupled. Until
2026-09-25 the row stated that `3.0254 mV` residual as **"the decision transient
itself"**. It is not: `sim/comparator-decision/run.py`'s `run_kickback_sweep`
tracks one maximum and one minimum *across `VINP` and `VINN` together*, so both
figures are per-pin extrema and their difference bounds neither the common-mode
part of the disturbance (which a differential top-plate CDAC largely rejects)
nor the differential part (which lands on the decision). Issue #390, filed from
#349 on 2026-09-25, names that gap and mints a successor record carrying the
split. DR-011's own Context and Consequences §3 draw a mitigation *direction*
from the same subtraction, which is why a reader had no reason to doubt it --
and exactly why the document's own restatement of it should be gated rather
than trusted.

**Three parts, all re-derived from the record the row itself cites** (by path,
not through a `records/LATEST` pointer -- `sim/comparator-decision/` publishes
none, so checks 3/4 have nothing to say about this row's freshness):

- **(a) The measurement and both multiples.** The peak, its `Vindiff` point,
  pin and instant, and `≈ 14.7×` / `≈ 36.7×` -- the multiples taken against the
  bounds this row's **own Target cell** states, not against numbers repeated in
  its prose. That is this check's acceptance-criterion-2 teeth: relaxing the
  target so the multiple reads smaller moves the derived multiple with it and
  fails here, rather than leaving the row quietly softened.
- **(b) The control-row subtraction.** The control peak with its own pin and
  instant, the residual, and both percentages. Same arithmetic as (a), graded
  separately because it is the clause whose *reading* was the defect.
- **(c) The cited table's own column list, in its own order, plus a verdict
  clause** -- both directions, like checks 8, 10, 14, 15, 16, 17, 18 and 20.
  While no column is a common-mode or differential quantity the row must say
  so; once one is, that clause must go and the split must be restated from the
  record. This is what keeps the qualification (b) now carries from outliving
  its own expiry: #390's successor record adds exactly those columns, and this
  check fails the row the moment it is cited.

**What this check deliberately does NOT cover.** It does not grade the row's
**verdict** (check 8 owns that vocabulary) and does not turn the DRAFT row into
a pass/fail one -- `spec/README.md` forbids grading against an unratified bound,
so the row stays INFORMATIONAL whatever the arithmetic says. It does not read
`sim/comparator-decision/`'s other records: the row cites one, and a campaign
with no `records/LATEST` has no "current" record for the gate to prefer. And it
is scoped to Kickback rather than generalised to "every derived figure in
Section 4": most rows quote a record's own stated figure, which checks 3 and 7
already hold to current evidence, whereas this row performs arithmetic on two of
them. Generalising would require a convention for marking a figure as derived,
which does not exist -- do not extend this check to other rows without adding
one first.

### Check 22 -- tracked-record parity (`check_tracked_records`)

Check 11 grades a Section 4 row against the *campaigns* `sim/spec-coverage.json`
indexes under it. The same index also records, per row, the **decision records
that govern the row's disposition** -- its `tracking` field -- and nothing
graded that half. The gap is the one check 11 exists for, moved one tree over:
a row whose disposition has been decided elsewhere, still restating the
open-item text that decision answered.

It is not hypothetical. DR-014 (issue #349, 2026-09-25) answered DR-011's
"Mitigation selection" open item for the Kickback row -- no static preamp, no
mitigation adopted, DR-004 Decision §1 stands -- and, in its own "Spec lines
affected" section, repointed that row's `tracking` field off #349 onto itself
and #390. `spec/target-spec.md`'s own Kickback note was updated in the same PR.
Section 4's Kickback row was not: it went on saying "Mitigation selection is
#349's, unblocked by this row's existence", a verbatim restatement of the open
item, pointing at an issue that had just closed. Every check here passed --
check 7 grades the Status column and both said DRAFT, check 21 grades the row's
arithmetic and none of it moved, check 15 grades DR-014's *status* and it was
correctly read out in Section 7. The row's own disposition was the one thing
nothing compared.

So every `DR-<n>` token in an indexed row's `tracking` field must be named in
the Section 4 row of the same parameter. Rows are enumerated from the index
rather than listed here, so a row that starts tracking a record later is
discovered rather than remembered, and a row whose field names no record is
simply not graded (`Sample rate` and `Power` track issues and a future record
today, and neither is forced to name one that does not exist).

**Forward direction only**, unlike checks 8, 10, 14, 15, 16, 17, 18 and 20.
A Section 4 row legitimately names records the index does not track -- the
ratifying DR-003 across most of the table, DR-007's candidate pair in the ENOB
and INL/DNL rows -- because the
`tracking` field is about *outstanding* work, not about provenance. Grading
the reverse direction would fail the gate on rows that are correct as written.

**What this check deliberately does NOT cover.** It grades that the record is
*named*, never what the row says about it: a row naming DR-014 while describing
its decision backwards still passes here. It also compares **bare numbers**, so
it inherits the ambiguity check 15 documents -- this tree carries two DR-004s
and two DR-007s, and naming either satisfies a `tracking` field that meant the
other. Check 15 owns that collision and reports it the moment the two disagree;
duplicating the resolution here would report one drift twice with two different
fixes. And it does not read the `tracking` field's own accuracy: that field is
hand-maintained prose whose rendered form (`sim/spec-coverage.md`) is
regenerated and gated by `sim/check_spec_coverage.py`, one tree up from this
document.

### Check 23 -- stamped currency claims (`check_stamped_currency_claims`)

Checks 4 and 5 grade one shape of currency claim: the phrase *"current
`<tree>/LATEST`"*, with the record named **before** it. This check grades the
mirror shape, which nothing covered: a present-tense claim stated **before**
the citation, naming the record by **stamp** rather than through a pointer --
*"the current run, [`layout/sar-adc-top/erc-reports/<stamp>/record.md`]"*.

That shape went stale in this document for exactly the reason a gate exists.
Section 3's `klt erc` bullet and Section 7 item 9 both introduced #355's supply
fix with "the current run" and a stamped citation. `erc-reports/` is
append-only like every other evidence tree here, so issue #362 minted
`20260924-214731-b323061` beside it and issue #377 then minted
`20260924-234116-66dca3c`, and **neither moved a single number in the table
either passage carries** -- all four supplies stayed at one island,
`erc_status` stayed `clean`, findings stayed 0. So both citations went on
naming a superseded record while every figure around them still read correct,
and item 9's hand-written prose ended up contradicting check 16's
machine-generated readout three paragraphs below it (the readout named
`20260924-234053-66dca3c`; the prose named the run that graded the GDS before
it, and restated that record's ablation table rather than the current one's).
Check 16 could not see it: it reads the pointer and recomputes the readout,
and has nothing to say about what path the surrounding prose cites. Neither
could checks 3/4 -- `EVIDENCE_PATH_RE` matches `records|reports` only.

**What it grades.** For each attached claim: the flow's own
`<tree>/LATEST` must exist, and **every** stamp in the citation construct must
be the one it resolves to. Both halves of a Markdown link are read -- display
text and target -- so a link whose two halves name different records, or
different trees, fails rather than half-passing; identical messages from the
two halves are reported once. `erc-reports/` is in scope here even though
checks 3/4 exclude it, because the pointer is read from the cited path's own
tree rather than inferred from the top-level directory.

**What this check deliberately does NOT cover.** Attachment is strict, and
deliberately stricter than check 4's: nothing but whitespace, an opening
bracket/paren/backtick and a comma or colon may sit between the claim and the
citation. No word is tolerated in between, because in this document the very
next words often introduce a *different* path -- "The current ERC record
**grades** `layout/sar-adc-top/reports/<stamp>/sar_adc_top.gds`" cites the
graded stream, not the record making the claim, and grading that against
`reports/LATEST` would be checking the wrong pointer. A claim whose citation
is further than 400 characters away, or which names no record at all, is
narration and is skipped for the same reason checks 4/5 skip the unattached
forms. And this check grades **currency, not content**: that a re-pointed
passage still describes what the *new* record says is not mechanically
checkable, which is why its failure message says "restate whatever the
superseded record was quoted for" rather than only "re-point the citation".

### Check 24 -- characterization-report row count (`check_report_row_count`)

Every other check grades a claim about an *evidence record*. This one grades a
claim about a **command's output**, which is a different thing the proposal
does in the same breath: Section 4's "Reproducing this table" tells a reader
to run `sim/report/generate.py --check`, and quotes the line it closes with
(`OK: ... is fresh and up to date (N rows)`) as the evidence that it was run
and passed.

That quotation is a machine output transcribed into prose, so it drifts the
way check 6's census and check 18's coverage sentence each drifted before they
were gated. It did: it read `11 rows` from the document's first pass (PR #140,
2026-09-05), which was true then, and stopped being true on 2026-09-24, when
commit `86e905e` (PR #366, issue #361) added the DRAFT Kickback row to
`sim/report/manifest.py` and took the report to twelve. Three later passes
(PRs #393, #395, #396) edited that very Kickback row in Section 4 without the
sentence one paragraph above the table moving, and no check could see it --
checks 3/4/5/23 grade record paths and pointers, and a row count is neither.

**What it grades.** The number in every quoted
`is fresh and up to date (N rows)` must equal the number of `Row(` entries in
`sim/report/manifest.py`'s own `ROWS` tuple -- which is exactly what
`sim/report/generate.py` prints (`len(manifest.ROWS)`). Graded in both
directions, like checks 8, 10, 14--18: a document that names the command and
quotes **none** of its output fails too, so deleting the quotation is not a
way to pass while still telling the reader to run it.

**Counted textually, not by importing the manifest.** The gate is a pure file
reader by design (no PDK, no network, no repository code executed), and
importing a sibling tree's module to measure a tuple would give that up for a
count a regex reads directly. The cost is stated rather than hidden: a
manifest restructured to build its rows some other way -- a loop, a
comprehension -- is reported as "no `ROWS` tuple this gate can count" instead
of being counted wrong.

**What this check deliberately does NOT cover.** It does not run the command,
and says nothing about whether `docs/characterization-report.md` is actually
fresh -- `npm run check:report` is what establishes that, on the same CI run,
and this check would be a worse copy of it. Nor does it grade *which* rows the
manifest carries: the row-by-row correspondence between that report and
Section 4 is check 7's (against `spec/target-spec.md`) and check 11's (against
`sim/spec-coverage.json`). A green check 24 says only that the number this
document quotes is the number the command would print today. It is anchored on
the command string, so a document that stops naming
`sim/report/generate.py --check` entirely is not made to quote it -- Section 4's
verdicts are held to evidence by checks 3 and 7 regardless.

### Check 25 -- ground-return census (`check_ground_return`)

Every other check grades a claim about *something this repository has*: a
record, a pointer, a report's field, a command's output. This one grades a
claim about something it **does not** have -- and that asymmetry is the whole
reason it exists.

Section 7 Item 9 reports a `klt erc`-clean power-delivery structure and four
qualifications of it. A fifth is owed and was missing until 2026-09-25: the
ground plan those verdicts grade
([DR-012](../spec/decision-records/DR-012-analog-ground-pad.md)'s drawn analog
ground pad, [DR-013](../spec/decision-records/DR-013-analog-ground-mesh.md)'s
mesh into it) rests on an impedance argument that **no `sim/` campaign
measures** -- no package parasitics, no substrate resistance, no bond-wire
inductance. Both records say so themselves and DR-012 carries it as a standing
open item ("The impedance argument is unmeasured", tracked as issue #378).

A hand-written disclaimer of that shape rots in the one direction nobody
notices: it stays on the page after it stops being true. Nothing else in the
gate could see it happen, because the event that falsifies it -- a campaign
that *does* model the return -- moves no pointer this document cites, changes
no island count in Item 9's table, and budges no Section 4 number. It is the
only one of Item 9's five qualifications whose truth is a property of the
whole evidence tree rather than of one report.

**What it grades.** The document's census sentence -- `across the **N** SPICE
decks under `sim/`, **M** carry an inductor card` -- against a live read of
every `*.spice` file under `sim/`. `M` is the graded half: an inductor card is
the mechanical stand-in for "models the return", since neither bond-wire
inductance nor any package model can be written in SPICE without one. `N` is
there so the sentence states what was scanned rather than asserting a bare
zero, and it moves whenever a campaign mints new corner decks -- the same
already-existing cost as checks 3 and 18, which a new evidence record moves
too. Graded in both directions, like checks 8, 10, 14--18 and 24: a document
that cites `DR-012-analog-ground-pad.md` and states **no** census fails, so
deleting the qualification is not a way to pass while still leaning on the
record whose open item it discloses.

**Read from the file tree, not from `git ls-files`.** The gate is
subprocess-free and network-free by design, so an untracked scratch deck left
under `sim/` counts exactly as a committed one does. That is the conservative
direction: it can only make the census look less clean than the tree is, never
cleaner.

**What this check deliberately does NOT cover.** It is a floor on the gap, not
a proof of it. A package stand-in written with resistors only -- a substrate
return modelled as an R, with no inductance -- passes this census while
partially closing the very gap the sentence disclaims, and the document says
so where it states the census. Closing that hole properly would mean deciding,
mechanically, which `R` cards are "supply parasitics" and which are the
ordinary bleeders, dividers and source impedances the existing decks are full
of (`sim/comparator-decision`'s own `1 kΩ` kickback source impedance is one,
and grading it as a package model would be simply wrong) -- a classifier this
gate has no basis for. DR-012's open item is retired by #378's testbench and
by a rewritten qualification, never by this count reading zero. Nor does the
check read the *prose* around the census: a document that states the numbers
correctly while describing their meaning backwards passes here, as it does
under checks 15, 16 and 22.

### Check 26 -- provenance census (`check_provenance_census`)

Check 25 grades a claim about something this repository does *not* have. This
one grades the claim a reader of the brief leans on hardest -- that the
evidence above can be **re-run**: Section 8's statement of which tool
versions and which PDK commit each record was produced under.

It is a property of the whole evidence tree, like check 25's census and
unlike every other check, so nothing else here moves when it stops being
true. The difference is that this one had already stopped. Until 2026-09-25
Section 8 asserted, in prose, that "every layout record cites the `klt`
version and PDK commit it ran against". Measured against the tree that
sentence was false for **33 of the 67** records under `layout/*/reports/` and
`layout/*/erc-reports/`, for two independent reasons:

- **Renderer divergence.** Four of the eight `layout/` flows' record
  renderers resolve the commit (`klt pdk find --pdk <variant> --format json`,
  printing its `version`); the other four print `- PDK variant: <variant>` --
  the variant *name*, which is not a pin. `layout/sar-adc-top/`, whose DRC
  and LVS verdicts Section 4's sign-off-bar rows rest on, is one of the four
  that do not.
- **`klt` stamps no PDK for these invocations.** `provenance.pdk` is `null`
  in a `--deck sky130`-invoked `drc.json` / `lvs.json` / `extract.json`, and
  `{"name": "sky130", "source": "built-in", "version": null}` in the ERC
  report -- so the shortfall is not recoverable from the record directory's
  JSON either. Only `compose.json`, the one step that resolves `PDK_ROOT`,
  carries a commit.

The `sim/` half is uniform -- every one of its records, 59 of 59 on the day
this check landed and every record minted since -- because `sim/run_corners.py
--check-env` resolves and enforces the pin before any corner runs, and a
drift there is fatal by default. (Stated that way rather than as a bare live
count on purpose: the count moves with every new record, and the number that
*is* re-derived per run lives in the document's own census, not here.) That asymmetry is the finding, and stating
it is the point: the gap itself is tracked as issue #407, which this check
does not close and must not be read as closing.

**What it grades.** Five numbers in one sentence -- the `sim/` records and
how many name both an `ngspice` version and a 40-hex `open_pdks` commit, then
the `layout/` records and how many name a `klt` version and a commit -- each
re-derived from the tree, in both directions like checks 8, 10, 14--18, 20,
24 and 25. Both directions matter more here than usual: the failure mode this
check exists for is a *widening* of the claim back to "every record", and the
failure mode after #407 lands is a census that stays pessimistic while the
flows have started pinning. An absent census is a finding too, anchored on
the document citing `sim/toolchain.json`, so deleting the inconvenient
numbers is not a way to pass while still describing the flow as reproducible.

**Two hashes it must not miscount, and does not.** A PDK commit is counted
only when a 40-hex token sits on a line that also names the PDK. Every layout
record carries a `repo commit:` line whose hash is the repository's own, and
every record stamp ends in a 7-hex abbreviation (`20260924-234053-66dca3c`)
that prose routinely quotes beside the word "PDK" -- a bare hex search over
the document would count both as provenance the record does not have.

**What this check deliberately does NOT cover.** It counts records that
*name* a commit; it does not check that the commit named is the one
`sim/pdk.json` pins, and it must not be extended to. Records are append-only
(`CLAUDE.md`): a record minted against an earlier `open_pdks` commit is
correct evidence of what was run, and grading it against today's pin would
fail the gate on history it is not allowed to rewrite. Cross-checking the pin
belongs to the flow that mints a record, not to a reader of one -- which is
exactly what `layout/bin/render-record.py`'s own "PDK pin cross-check" line
asks a human to do. Nor does it read the prose around the census: a document
that states the five numbers correctly while describing their meaning
backwards passes here, as it does under checks 15, 16, 22 and 25.

### Check 27 -- single-copy issue-state claims (`check_label_claim_section`)

Every other check here grades a claim against something this repository
*contains* -- a record, a netlist, a manifest, a decision record. This one
grades the single class of claim that has no such backing: a `loom:` label,
which is **live forge state**. The gate is network-free by design (the same
property that lets it run in the always-on `checks` job), so it cannot read
the forge, and no amount of extension will make it able to.

What it can do is bound the damage. A label claim is only as good as the
pass that last read it, so the document may keep **exactly one copy** of it,
in Section 7 -- the section whose whole job is to narrate tracking state
paragraph by paragraph and date, and which is therefore re-read every pass.
A label restated in Section 3's functional description or in a Section 4
verdict row is a second copy that nothing updates.

**This is not hypothetical; it is why the check exists.** On 2026-09-25 the
document held three mutually contradictory readings of one issue, #103, the
tracking issue for both of the brief's sign-off-bar rows:

- Section 3 read "tracked as issue #103, still open and `loom:blocked`";
- Section 4's two sign-off-bar rows' newest word on it, dated 2026-09-15, was
  "#103 is back in the ready queue as of this pass (`loom:issue`, no
  `loom:blocked`)";
- Section 7 Item 1 carried the truth -- the 2026-09-24 escalation to
  `loom:operator-only`/`loom:operator-decision`, i.e. a human ruling rather
  than an automatable dependency check.

No other check here could see it. Checks 3/4/5/23 grade *record* citations,
check 15 grades *decision-record* statuses; an issue label is neither. The
reader worst served was the one Section 4 is written for: a sign-off-bar row
that reads "blocked, back in the queue" describes a materially different
project state from one that reads "blocked on a human ruling", at an
identical verdict.

**What it grades.** Every `loom:<label>` token outside Section 7, with the
section that states it and the line it is on. Backticks are optional in the
match on purpose -- dropping them must not be a way to keep a second copy --
and `\b` before `loom` is what keeps a `.loom/` path segment (no colon) and a
prose word ending in "loom" out of it. Fenced code blocks are skipped: a
quoted `gh issue edit --add-label` command is an instruction to a reader, not
the document's own claim about what an issue carries today. A document with
no numbered Section 7 is not graded rather than being made to invent one.

**What this check deliberately does NOT cover.** It does not grade what a
label claim *says*, in either direction -- it cannot, and a future pass must
not try to teach it to by shelling out to `gh`: that would make the `checks`
job network-dependent and would fail CI on a forge outage, for a document
whose verdicts do not depend on the forge at all. Nor does it require a label
claim to exist: a document that simply stops discussing issue state passes,
because silence is not a false claim. And it is deliberately blind to Section
7's *internal* contradictions -- that section narrates its own supersession
trail in the present tense, paragraph by dated paragraph ("#103 itself was
re-blocked at that pass"), exactly as check 3 is scoped away from Section 7's
prose for the same reason. The claim that governs is the last one in the
item, which is a reading rule for humans, not a rule this gate enforces.

### Check 28 -- Section 4's PVT-grid claim (`check_corner_grid_census`)

Checks 3, 4, 5 and 23 all grade **which** record a Section 4 row cites, and
whether it is the current one. None of them grades what that record claims
for *itself* -- and the widest sentence in the table is exactly such a
claim. Section 4 opens by naming the PVT grid its rows are reported at, and
that sentence speaks for every row at once, before a reader reaches any of
them.

Until 2026-09-25 it read "Every row below is reported at this repository's
own ratified PVT grid ... one-at-a-time (9 points)". Measured against the
records the table actually cites, that was false for **10 of 22** (spec row,
`sim/` record) citation pairs:

- three single-point mechanism budgets under the **Sample rate** row, each
  cited beside the 9-point campaign that superseded it (the benign case);
- both comparator runs under the **Kickback** row, single-point by design and
  already disclosed in that row's own cell;
- two Monte Carlo linearity records under **INL / DNL** and two derived ENOB
  re-analyses under **ENOB**, neither row stating any corner coverage of its
  own;
- the supply-impedance campaign under **Power**, single-point by construction
  (it measures a difference between four supply-return networks at one
  corner).

No record hid it -- each states its own subset-corner justification, in its
own header. The document spoke over them, which is the same
prose-overstates-the-evidence shape checks 6, 18 and 26 exist for, and the
same fix: replace the blanket sentence with a census that is re-derived
rather than asserted.

**What it grades.** Two things, because the census alone could be satisfied
by weakening the claim instead of stating the exceptions.

1. **The grid sentence itself**, against the two anchors that are not the
   document's own wording: its process axis must be `sim/pdk.json`'s
   `process_corners`, in both directions, and its stated point count must be
   the one-at-a-time identity |P| + |T| + |S| - 2 that `sim/README.md`'s
   "Corner-grid shape" section describes and
   `sim/harness/corners.py:oat_grid()` implements. Without those, dropping
   `sf` and `fs` from the sentence would turn a four-corner campaign into
   "the full grid" and the census would read perfectly.
2. **The census over the records the table cites**, per (row, record) pair --
   check 18's unit one level finer, because corner coverage is a property of
   the record and not of the flow that minted it. A row citing one flow's
   nine-point campaign *and* its single-corner first pass is making two
   different claims. Both the four counts and the list of the records behind
   the exceptions are compared in both directions, as checks 8, 10, 14--18
   and 26 do: a record that starts running the full grid and is left in the
   list overstates the hole, and one a newly added row starts citing and is
   left out understates it. An absent census is itself a finding, anchored on
   the grid sentence existing, so deleting the inconvenient numbers is not a
   way to keep the blanket claim.

**Three record shapes, all of them real.** A record declares its PVT points
in one of three forms, and keying on only the first would misreport five
records that *do* declare a single nominal point as declaring nothing -- in a
check whose whole subject is overstatement:

- `- **Corner matrix run**: process=[...], temperature_c=[...],
  supply_v=[...] (9 points, ...)`, written by
  `sim/harness/corners.py:corner_matrix_summary_line()`;
- `- **Point/corner matrix**: `tt`/27C/1.8V only ...`, the mechanism-budget
  drivers' line;
- `... PVT point process=tt temp=27.0C supply=1.8V`, inside the Monte Carlo
  drivers' **Statistical convention** line -- stated there because the axis
  those campaigns sample is mismatch, not PVT.

A record matching none of the three declares no PVT point set of its own,
which is a real answer rather than a parse failure: `sim/enob-estimate/`
runs no ngspice at all and inherits its binding corner from the records it
composes.

**What this check deliberately does NOT cover.** It does not grade whether a
subset-corner citation is *justified* -- only that the document counts it.
Single-corner evidence is legitimate and this repository uses it on purpose
(`sim/README.md`'s own corner-grid section says an OAT grid is a cost choice;
each first-pass budget states why one point is enough for the mechanism it
isolates). Nor does it read the exception list's surrounding prose: a
document that states the four counts correctly while describing them
backwards passes here, as it does under checks 15, 16, 22, 25 and 26. And it
grades no `layout/` citation, because a DRC/LVS verdict has no corner axis at
all -- the sign-off-bar rows' post-layout PVT gap is §7 Item 1's subject and
#103's, not this check's.
### Check 29 -- asserted-absent paths (`check_absent_paths`)

The mirror image of check 2, and the check that makes a whole class of true
statement sayable for the first time.

Check 2 grades a path the document **cites**: it must exist. But Section 7's
whole job is to report work that has *not* landed -- a sub-block that lives
only in an unmerged PR, a flow whose records there is therefore nothing in
this tree to point at. Stating that precisely means naming a path that does
not exist, which is exactly what check 2 fails on. So the document could not
name it, and fell back on gesturing at the parent directory: "no such flow
exists under `layout/`".

**That vague form is the one that rots.** It names nothing the gate can
re-evaluate, so on the day the PR merges and `layout/top-glue/` appears, the
passage still reads "no such flow exists" and no check here can tell. This is
the same defect shape as check 27's -- a claim about state that only a human
re-read could catch -- arriving from the opposite direction: check 27's
problem was a claim nothing could verify, this one's was a claim the document
was structurally discouraged from making at all.

**What it grades.** A backticked path immediately followed by the literal
marker `(not in this tree)` is an *asserted-absent* path rather than a
citation. Check 2 skips it; check 29 asserts it does not exist, and fails if
it does, naming the path and saying what to do (update the passage, drop the
marker, and let the path become an ordinary citation check 2 grades). The
marker must follow the closing backtick immediately -- at most one line wrap,
no intervening prose -- for the same directional reason checks 4/5 require an
*attached* pointer claim: prose that merely discusses an absence near a path
is not the document asserting that path is absent.

The path-shape test itself (`_own_tree_path`) is shared with check 2 rather
than restated, because the two grade the same shape from opposite directions
and a shape one recognised and the other did not would be a hole in whichever
half missed it. A marker spent on something that is *not* a concrete own-tree
path -- a glob, a pattern, an upstream path -- is itself reported: without
that arm the marker would be a way to exempt a reference from check 2 and
check 29 at once, which is strictly worse than either.

**What this check deliberately does NOT cover.** It does not find absence
claims written in prose without the marker, and it is not meant to: inferring
"this path does not exist" from English would fail on the many paragraphs
here that narrate a path's history, and the fix would be to rewrite the
supersession trail -- the opposite of what this gate is for. The marker is
opt-in, so an unmarked vague claim is unchanged, not newly illegal. Nor does
it say anything about *why* a path is absent (unmerged PR, closed proposal,
never filed); that is forge state, which check 27 already establishes this
gate cannot read. What it guarantees is narrower and enough: a passage cannot
keep describing an absence after the absence ends.

## What the gate deliberately does not cover

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

## Adding a check

A new check lands in three places in
`docs/chipalooza/check_proposal_citations.py` -- its constants, its function,
and the `check_document` chain -- and a fourth here: a `### Check N` heading
above naming its function in backticks, stating why the check exists and,
where it applies, what it deliberately does *not* cover. A `--stats` arm, if
the check needs one, is a fifth.

That fifth step is gated rather than remembered:
`sim/tests/test_proposal_citations.py` asserts that every check function
`check_document` calls is named in a heading of this file, so a check added
without its rationale is a test failure, not a silent hole. This is the same
shape as check 6 itself -- a prose claim about the gate is re-derived rather
than trusted.

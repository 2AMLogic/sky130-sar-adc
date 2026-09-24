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
`docs/`, `measurements/`, `ratification/`) resolves too. Not every evidence
citation is a Markdown link: Section 4's Power row, for instance, cites its
record as a bare backticked path. References whose first segment is NOT one
of ours (e.g. klayout-tools' `src/klayout_tools/lvs.py`) are upstream paths
and are left alone.

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

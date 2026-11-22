# Work Plan

<!-- guide:plan-body:start -->
_Generated: 2026-11-21T20:10:48Z (snapshot; compare against live labels)_
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs awaiting an operator decision on a merge hold (`loom:blocked` or `loom:operator`).

- **#842**: docs(spec): state PDK-sourced absolute limits in DR-026 and report them in the proposal
- **#973**: docs: qualify the newest full-conversion pointer and record the #913 boundary sweep

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#103**: T1 item 2 (layout): top-level SAR ADC layout assembly *(held)*
- **#121**: [Epic #542] 4B — Chipalooza Challenge #4 (Sky130) brief document + sign-off
- **#729**: Triage klt 0.8.0 DRC violations on top-level streams (blocks layout pin bump) *(held)*
- **#734**: Bump layout/requirements.txt to klt 0.8.0 and re-run layout flows *(held)*
- **#743**: T1 item 3 (DRC): repoint manifest items 3/4/11 from the superseded 2026-10-01 stream to reports/LATEST and regrade *(held)*
- **#771**: Re-mint digital item 5/7 evidence on the regenerated sar_sequencer netlist *(held)*
- **#784**: layout: move sar-sequencer and seln-inverters PnR io.layer_v off li1 (rejected by klt place-and-route)
- **#785**: layout: re-run sar-adc-top on fully regenerated children and triage DRC met1.space.1 + LVS mismatch *(held)*
- **#790**: Re-mint sim/digital-partition campaign after sar-sequencer re-route (PR #788 check:report)
- **#1013**: Isolate the ff_27c_1.80v 3e-5 V delta that parks #811 (klt sim batch vs baseline 20261001-120402-d24f700)
- **#1014**: T1 item 5 (analog): cite spec_row-tagged klt sim envelopes for the ratified analog rows as a 5.analog manifest entry

## Ready

Human-approved issues (`loom:issue`) ready for implementation — excluding held (`loom:blocked`/`loom:operator`/`loom:frozen`), `loom:building`, and issues closed by an open `loom:pr` PR (listed under Approved).

- **#784**: layout: move sar-sequencer and seln-inverters PnR io.layer_v off li1 (rejected by klt place-and-route) — existing PR #788 awaits the merge of #798 into its branch

## In Progress

Issues currently being built (`loom:building`).

- **#121**: [Epic #542] 4B — Chipalooza Challenge #4 (Sky130) brief document + sign-off
- **#680**: layout/sar-sequencer: sar_sequencer.v is stale against design/sar_sequencer.sch (since #263); regenerate and re-run flows
- **#773**: Restate 53 stale proposal citations after the sar_sequencer regeneration (PR #772)
- **#834**: spec: no absolute maximum ratings exist — Challenge #4's proposal-content list requires "absolute limits"
- **#965**: Hand-kept status texts drifted past the boundary-sweep landing: ROADMAP newest-record bullet, DR-021 Open items, full-conversion records/LATEST
- **#1013**: Isolate the ff_27c_1.80v 3e-5 V delta that parks #811 (klt sim batch vs baseline 20261001-120402-d24f700)
- **#1014**: T1 item 5 (analog): cite spec_row-tagged klt sim envelopes for the ratified analog rows as a 5.analog manifest entry
- **#1016**: CDAC linearity: design iteration toward INL/DNL <= +-1 LSB at 0.99 yield (the redesign path DR-007 left as future work)
- **#1017**: T1 item 7 (analog): klt pex records for the LVS-matching analog sub-blocks (cdac_array, sampling_frontend, refreshed comparator)
- **#1020**: Share the two-pulse acquisition stimulus between the front-end and CDAC handoff runners
- **#1023**: T1 item 5: bind the Resolution N row (sar-sequencer behavioral bench) to the digital partition's item 5 row set
- **#1033**: Re-derive the settling / sample-rate budget at the DR-027 array size (C_tot ~12.4 pF/side) against DR-006
- **#1035**: Read plot data from the record each figure cites
- **#1043**: ci.yml: every PR label write re-runs the full checks job, and the Judge claim label can starve a PR of review

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#1024**: Add cdac-array-transfer ff-corner PDK A/B diagnostic record ruling out the pin bump
- **#1026**: refactor: share acquisition waveforms and probe timing across deck builders
- **#1028**: signoff: declare item-5 analog spec rows and cite the comparator-noise klt sim envelope
- **#1042**: feat(layout): klt pex flows and OAT records for the analog sub-blocks (cdac_array, sampling_frontend, comparator)
- **#1045**: ci: stop re-running required checks on PR label writes; move run-pdk-smoke opt-in to its own workflow

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#798**: sim: re-mint digital-partition campaign for met2 re-routed sar_sequencer — implements #790 on the branch for PR #788
- **#842**: docs(spec): state PDK-sourced absolute limits in DR-026 and report them in the proposal — closes #834
- **#973**: docs: qualify the newest full-conversion pointer and record the #913 boundary sweep — closes #965

## Proposed

Issues carrying `loom:curated`.

- **#103**: T1 item 2 (layout): top-level SAR ADC layout assembly *(curated)* *(held)*
- **#121**: [Epic #542] 4B — Chipalooza Challenge #4 (Sky130) brief document + sign-off *(curated)*
- **#428**: Operator hand-off: create the 'main: required status checks' ruleset that arms the base-freshness guard (from #422 / PR #425) *(curated)* *(held)*
- **#680**: layout/sar-sequencer: sar_sequencer.v is stale against design/sar_sequencer.sch (since #263); regenerate and re-run flows *(curated)*
- **#734**: Bump layout/requirements.txt to klt 0.8.0 and re-run layout flows *(curated)* *(held)*
- **#757**: sim: per-corner gain extraction and corrected-code reporting across all 9 corners *(curated)* *(held)*
- **#773**: Restate 53 stale proposal citations after the sar_sequencer regeneration (PR #772) *(curated)*
- **#784**: layout: move sar-sequencer and seln-inverters PnR io.layer_v off li1 (rejected by klt place-and-route) *(curated)*
- **#790**: Re-mint sim/digital-partition campaign after sar-sequencer re-route (PR #788 check:report) *(curated)*
- **#811**: Re-run multi-corner/MC sim records via klt sim under open_pdks f6eeac7 as superseding records (#709 split) *(curated)* *(held)*
- **#834**: spec: no absolute maximum ratings exist — Challenge #4's proposal-content list requires "absolute limits" *(curated)*
- **#965**: Hand-kept status texts drifted past the boundary-sweep landing: ROADMAP newest-record bullet, DR-021 Open items, full-conversion records/LATEST *(curated)*
- **#1013**: Isolate the ff_27c_1.80v 3e-5 V delta that parks #811 (klt sim batch vs baseline 20261001-120402-d24f700) *(curated)*
- **#1014**: T1 item 5 (analog): cite spec_row-tagged klt sim envelopes for the ratified analog rows as a 5.analog manifest entry *(curated)*
- **#1016**: CDAC linearity: design iteration toward INL/DNL <= +-1 LSB at 0.99 yield (the redesign path DR-007 left as future work) *(curated)*
- **#1017**: T1 item 7 (analog): klt pex records for the LVS-matching analog sub-blocks (cdac_array, sampling_frontend, refreshed comparator) *(curated)*
- **#1021**: T1 item 5 (analog): grade V_REF, LSB and sampling cap as full ratified claims, not just top-plate voltages *(curated)*
- **#1023**: T1 item 5: bind the Resolution N row (sar-sequencer behavioral bench) to the digital partition's item 5 row set *(curated)*
- **#1033**: Re-derive the settling / sample-rate budget at the DR-027 array size (C_tot ~12.4 pF/side) against DR-006 *(curated)*
- **#1043**: ci.yml: every PR label write re-runs the full checks job, and the Judge claim label can starve a PR of review *(curated)*

## Proposed (Architect / Hermit)

- **#121**: [Epic #542] 4B — Chipalooza Challenge #4 (Sky130) brief document + sign-off *(architect)*
- **#903**: refactor(chipalooza): check_proposal_citations.py is now 6617 lines / 37 checks — take #321's deferred split and registry *(hermit)* *(held)*
- **#917**: Wire up or remove GND_MESH_MEMBERS: an inert declaration nothing reads *(hermit)* *(held)*
- **#921**: Remove GND_MESH_MEMBERS: a declared-but-never-read member list the mesh builder does not consult *(hermit)* *(held)*
- **#924**: Remove dead duplicate import os / SETTLE assignment in the two SDF testbenches (needs an evidence re-mint) *(hermit)* *(held)*
- **#928**: Collapse the four digital-functional cocotb benches to two: the SDF variants are 296 duplicated lines of the zero-delay originals *(hermit)* *(held)*
- **#929**: Execute the #820 follow-up: klt 0.9.2 ships `klt evidence claims`, but the swap is vacuous on this repo's records *(hermit)* *(held)*
- **#930**: Remove the three leftover pass-through wrappers in the two schematic-parity gates *(hermit)* *(held)*

## Epics

- **#23**: Gap to T1 (bronze): tracker for the six failing items of the 2026-08-15 checklist re-read *(held)*

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 2 |
| Very important | 0 |
| Important | 11 |
| Ready (`loom:issue`, net of holds/building/merge-pending) | 1 |
| In Progress (`loom:building`) | 14 |
| PRs awaiting review | 5 |
| Approved PRs awaiting merge | 3 |
| Curated | 20 |
| Architect / Hermit proposals | 8 |
| Active epics | 1 |
<!-- guide:plan-body:end -->

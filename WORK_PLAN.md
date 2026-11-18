# Work Plan

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

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
- **#785**: layout: re-run sar-adc-top on fully regenerated children and triage DRC met1.space.1 + LVS mismatch *(held)*

## Ready

Human-approved issues (`loom:issue`) ready for implementation — excluding held (`loom:blocked`/`loom:operator`/`loom:frozen`), `loom:building`, and issues closed by an open `loom:pr` PR (listed under Approved).

_None._

## In Progress

Issues currently being built (`loom:building`).

- **#121**: [Epic #542] 4B — Chipalooza Challenge #4 (Sky130) brief document + sign-off
- **#680**: layout/sar-sequencer: sar_sequencer.v is stale against design/sar_sequencer.sch (since #263); regenerate and re-run flows
- **#773**: Restate 53 stale proposal citations after the sar_sequencer regeneration (PR #772)
- **#784**: layout: move sar-sequencer and seln-inverters PnR io.layer_v off li1 (rejected by klt place-and-route)
- **#790**: Re-mint sim/digital-partition campaign after sar-sequencer re-route (PR #788 check:report)
- **#834**: spec: no absolute maximum ratings exist — Challenge #4's proposal-content list requires "absolute limits"
- **#965**: Hand-kept status texts drifted past the boundary-sweep landing: ROADMAP newest-record bullet, DR-021 Open items, full-conversion records/LATEST

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#798**: sim: re-mint digital-partition campaign for met2 re-routed sar_sequencer

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

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
| Important | 7 |
| Ready (`loom:issue`, net of holds/building/merge-pending) | 0 |
| In Progress (`loom:building`) | 7 |
| PRs awaiting review | 1 |
| Approved PRs awaiting merge | 2 |
| Curated | 12 |
| Architect / Hermit proposals | 8 |
| Active epics | 1 |
<!-- guide:plan-body:end -->

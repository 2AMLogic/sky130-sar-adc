# Work Plan

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#842**: docs(spec): state PDK-sourced absolute limits in DR-026 and report them in the proposal

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#103**: T1 item 2 (layout): top-level SAR ADC layout assembly
- **#121**: [Epic #542] 4B — Chipalooza Challenge #4 (Sky130) brief document + sign-off
- **#729**: Triage klt 0.8.0 DRC violations on top-level streams (blocks layout pin bump)
- **#734**: Bump layout/requirements.txt to klt 0.8.0 and re-run layout flows
- **#743**: T1 item 3 (DRC): repoint manifest items 3/4/11 from the superseded 2026-10-01 stream to reports/LATEST and regrade
- **#771**: Re-mint digital item 5/7 evidence on the regenerated sar_sequencer netlist
- **#785**: layout: re-run sar-adc-top on fully regenerated children and triage DRC met1.space.1 + LVS mismatch
- **#898**: harness/klt_sim: envelope_from_stderr accepts any JSON dict, so a non-envelope object on stderr could be cached as a report

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#875**: Extract the ngspice + sky130 PDK provisioning copied into four ci.yml jobs into one composite action
- **#898**: harness/klt_sim: envelope_from_stderr accepts any JSON dict, so a non-envelope object on stderr could be cached as a report
- **#904**: Consolidate the three byte-identical klt sim read_report bodies onto one harness helper
- **#926**: Remove dead BisectMcResult.draw_seeds: a property no commit has ever read
- **#927**: Remove NoiseResult.op_din_v, or print it: a measured op-point the record's v(DIP)=v(DIN) row never reads

## In Progress

Issues currently being built (`loom:building`).

- **#121**: [Epic #542] 4B — Chipalooza Challenge #4 (Sky130) brief document + sign-off
- **#680**: layout/sar-sequencer: sar_sequencer.v is stale against design/sar_sequencer.sch (since #263); regenerate and re-run flows
- **#773**: Restate 53 stale proposal citations after the sar_sequencer regeneration (PR #772)
- **#784**: layout: move sar-sequencer and seln-inverters PnR io.layer_v off li1 (rejected by klt place-and-route)
- **#790**: Re-mint sim/digital-partition campaign after sar-sequencer re-route (PR #788 check:report)
- **#834**: spec: no absolute maximum ratings exist — Challenge #4's proposal-content list requires "absolute limits"
- **#909**: Fold the duplicated Row-1 PFET well-island floorplan into layout/bin/_geometry_common.py
- **#914**: Consolidate the 13 copied evidence.resolve_provenance stubs in sim/tests onto one shared fixture
- **#915**: Finish the _flow_common.sh factoring: hoist the duplicated run-flow preamble, per-block DRC fan-out and record tail

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#798**: sim: re-mint digital-partition campaign for met2 re-routed sar_sequencer
- **#920**: refactor(layout): share the Row-1 PFET well-island floorplan

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#842**: docs(spec): state PDK-sourced absolute limits in DR-026 and report them in the proposal
- **#910**: docs: roadmap as of 2026-11-13
- **#923**: test: consolidate the 13 inline resolve_provenance stubs onto one fixture

## Proposed

Issues carrying `loom:curated`.

- **#103**: T1 item 2 (layout): top-level SAR ADC layout assembly *(curated)*
- **#121**: [Epic #542] 4B — Chipalooza Challenge #4 (Sky130) brief document + sign-off *(curated)*
- **#428**: Operator hand-off: create the 'main: required status checks' ruleset that arms the base-freshness guard (from #422 / PR #425) *(curated)*
- **#680**: layout/sar-sequencer: sar_sequencer.v is stale against design/sar_sequencer.sch (since #263); regenerate and re-run flows *(curated)*
- **#734**: Bump layout/requirements.txt to klt 0.8.0 and re-run layout flows *(curated)*
- **#757**: sim: per-corner gain extraction and corrected-code reporting across all 9 corners *(curated)*
- **#773**: Restate 53 stale proposal citations after the sar_sequencer regeneration (PR #772) *(curated)*
- **#784**: layout: move sar-sequencer and seln-inverters PnR io.layer_v off li1 (rejected by klt place-and-route) *(curated)*
- **#790**: Re-mint sim/digital-partition campaign after sar-sequencer re-route (PR #788 check:report) *(curated)*
- **#811**: Re-run multi-corner/MC sim records via klt sim under open_pdks f6eeac7 as superseding records (#709 split) *(curated)*
- **#834**: spec: no absolute maximum ratings exist — Challenge #4's proposal-content list requires "absolute limits" *(curated)*
- **#898**: harness/klt_sim: envelope_from_stderr accepts any JSON dict, so a non-envelope object on stderr could be cached as a report *(curated)*
- **#911**: README status section is stale: "6 of 22 rows met", "Private for now", and a closed issue cited as open *(curated)*
- **#913**: sim: converging-range boundary sweep of the current architecture (DR-021 Open items) *(curated)*

## Proposed (Architect / Hermit)

- **#121**: [Epic #542] 4B — Chipalooza Challenge #4 (Sky130) brief document + sign-off *(architect)*
- **#903**: refactor(chipalooza): check_proposal_citations.py is now 6617 lines / 37 checks — take #321's deferred split and registry *(hermit)*
- **#917**: Wire up or remove GND_MESH_MEMBERS: an inert declaration nothing reads *(hermit)*
- **#921**: Remove GND_MESH_MEMBERS: a declared-but-never-read member list the mesh builder does not consult *(hermit)*
- **#924**: Remove dead duplicate import os / SETTLE assignment in the two SDF testbenches (needs an evidence re-mint) *(hermit)*
- **#928**: Collapse the four digital-functional cocotb benches to two: the SDF variants are 296 duplicated lines of the zero-delay originals *(hermit)*
- **#929**: Execute the #820 follow-up: klt 0.9.2 ships `klt evidence claims`, but the swap is vacuous on this repo's records *(hermit)*
- **#930**: Remove the three leftover pass-through wrappers in the two schematic-parity gates *(hermit)*

## Epics

- **#23**: Gap to T1 (bronze): tracker for the six failing items of the 2026-08-15 checklist re-read

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 1 |
| Very important | 0 |
| Important | 8 |
| Ready (`loom:issue`) | 5 |
| In Progress (`loom:building`) | 9 |
| PRs awaiting review | 2 |
| Approved PRs awaiting merge | 3 |
| Curated | 14 |
| Architect / Hermit proposals | 8 |
| Active epics | 1 |
<!-- guide:plan-body:end -->

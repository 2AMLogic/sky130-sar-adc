# Work Plan

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

_None._

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#103**: T1 item 2 (layout): top-level SAR ADC layout assembly
- **#121**: [Epic #542] 4B — Chipalooza Challenge #4 (Sky130) brief document + sign-off

## Ready

Human-approved issues ready for implementation (`loom:issue`).

_None._

## In Progress

Issues currently being built (`loom:building`).

- **#680**: layout/sar-sequencer: sar_sequencer.v is stale against design/sar_sequencer.sch (since #263); regenerate and re-run flows
- **#773**: Restate 53 stale proposal citations after the sar_sequencer regeneration (PR #772)
- **#784**: layout: move sar-sequencer and seln-inverters PnR io.layer_v off li1 (rejected by klt place-and-route)
- **#790**: Re-mint sim/digital-partition campaign after sar-sequencer re-route (PR #788 check:report)
- **#810**: Re-run local single-corner/analytic sim records under open_pdks f6eeac7 as superseding records (#709 split)

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#798**: sim: re-mint digital-partition campaign for met2 re-routed sar_sequencer
- **#812**: sim: record klt sim batch route probe for cdac-array-transfer under a 0.9.0 client

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

_None._

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
- **#810**: Re-run local single-corner/analytic sim records under open_pdks f6eeac7 as superseding records (#709 split) *(curated)*
- **#811**: Re-run multi-corner/MC sim records via klt sim under open_pdks f6eeac7 as superseding records (#709 split) *(curated)*

## Proposed (Architect / Hermit)

- **#121**: [Epic #542] 4B — Chipalooza Challenge #4 (Sky130) brief document + sign-off *(architect)*

## Epics

- **#23**: Gap to T1 (bronze): tracker for the six failing items of the 2026-08-15 checklist re-read

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 0 |
| Important | 2 |
| Ready (`loom:issue`) | 0 |
| In Progress (`loom:building`) | 5 |
| PRs awaiting review | 2 |
| Approved PRs awaiting merge | 0 |
| Curated | 11 |
| Architect / Hermit proposals | 1 |
| Active epics | 1 |
<!-- guide:plan-body:end -->

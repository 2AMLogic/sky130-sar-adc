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

## Ready

Human-approved issues ready for implementation (`loom:issue`).

_None._

## In Progress

Issues currently being built (`loom:building`).

- **#121**: [Epic #542] 4B — Chipalooza Challenge #4 (Sky130) brief document + sign-off
- **#680**: layout/sar-sequencer: sar_sequencer.v is stale against design/sar_sequencer.sch (since #263); regenerate and re-run flows
- **#773**: Restate 53 stale proposal citations after the sar_sequencer regeneration (PR #772)
- **#784**: layout: move sar-sequencer and seln-inverters PnR io.layer_v off li1 (rejected by klt place-and-route)
- **#790**: Re-mint sim/digital-partition campaign after sar-sequencer re-route (PR #788 check:report)
- **#834**: spec: no absolute maximum ratings exist — Challenge #4's proposal-content list requires "absolute limits"
- **#877**: Remove dead parse_ac_print() and two other unread leftovers in sim drivers
- **#884**: Remove dead npm script worktree:return: its target .loom/scripts/worktree-return.sh does not exist
- **#894**: vcm-drive-budget: full-grid records carry fixed-text sentences their own data and sibling records contradict

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#798**: sim: re-mint digital-partition campaign for met2 re-routed sar_sequencer

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#842**: docs(spec): state PDK-sourced absolute limits in DR-026 and report them in the proposal
- **#899**: refactor: drop three unread leftovers from the sim drivers
- **#901**: chore: drop dangling worktree:return npm script
- **#902**: fix(vcm-drive-budget): derive record interpretation sentences from the data

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
- **#894**: vcm-drive-budget: full-grid records carry fixed-text sentences their own data and sibling records contradict *(curated)*

## Proposed (Architect / Hermit)

- **#121**: [Epic #542] 4B — Chipalooza Challenge #4 (Sky130) brief document + sign-off *(architect)*
- **#875**: Extract the ngspice + sky130 PDK provisioning copied into four ci.yml jobs into one composite action *(hermit)*
- **#888**: Put digital-partition's run-info read on harness.klt_sim.run_info(): its private copy makes runner_skew() blind to sharded reports *(hermit)*
- **#889**: check:ci runs the full sim/tests unit suite twice: once via npm run test, again as sim/selftest.sh stage 1 *(hermit)*
- **#903**: refactor(chipalooza): check_proposal_citations.py is now 6617 lines / 37 checks — take #321's deferred split and registry *(hermit)*
- **#904**: Consolidate the three byte-identical klt sim read_report bodies onto one harness helper *(hermit)*

## Epics

- **#23**: Gap to T1 (bronze): tracker for the six failing items of the 2026-08-15 checklist re-read

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 1 |
| Very important | 0 |
| Important | 7 |
| Ready (`loom:issue`) | 0 |
| In Progress (`loom:building`) | 9 |
| PRs awaiting review | 1 |
| Approved PRs awaiting merge | 4 |
| Curated | 12 |
| Architect / Hermit proposals | 6 |
| Active epics | 1 |
<!-- guide:plan-body:end -->

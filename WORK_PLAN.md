# Work Plan

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#530**: docs(spec): DR-022 proposes a systematic gain-error spec row instead of resizing the CDAC or comparator

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

_None._

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#530**: docs(spec): DR-022 proposes a systematic gain-error spec row instead of resizing the CDAC or comparator

## Proposed

Issues carrying `loom:curated`.

- **#103**: T1 item 2 (layout): top-level SAR ADC layout assembly *(curated)*
- **#121**: [Epic #542] 4B — Chipalooza Challenge #4 (Sky130) brief document + sign-off *(curated)*
- **#269**: design: CDAC absolute gain error (~1%) from top-plate parasitic loading -- the array's unit cap is smaller than the parasitic it drives *(curated)*
- **#621**: Coherent-sine capture: root-cause the single +438 LSB outlier (conversion 9) and add a per-code outlier check to the validity gate *(curated)*

## Proposed (Architect / Hermit)

- **#121**: [Epic #542] 4B — Chipalooza Challenge #4 (Sky130) brief document + sign-off *(architect)*
- **#564**: Pilot: express one PVT corner campaign as a klt sim request (first klt sim envelope) *(architect)*
- **#629**: Dedupe repeated testbench entries in the generated spec-coverage index *(architect)*
- **#658**: Refresh stale tracker #23 body to point at signoff/t1-report.json instead of the 2026-08-15 analog/10-item table *(architect)*
- **#588**: Simplify the Chipalooza proposal citation gate: ~16k lines of checker, tests and rationale guard one prose document *(hermit)*

## Epics

- **#23**: Gap to T1 (bronze): tracker for the six failing items of the 2026-08-15 checklist re-read

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 1 |
| Very important | 0 |
| Important | 2 |
| Ready (`loom:issue`) | 0 |
| In Progress (`loom:building`) | 0 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 1 |
| Curated | 4 |
| Architect / Hermit proposals | 5 |
| Active epics | 1 |
<!-- guide:plan-body:end -->

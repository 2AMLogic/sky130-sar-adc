# Work Plan

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs stuck under a `loom:operator` merge-risk hold — implementation work is done, only a human merge decision is missing.

_None._

## Operator Priority

Issues the operator starred (`loom:operator-priority`); land these first.

_None._

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#269**: design: CDAC absolute gain error (~1%) from top-plate parasitic loading -- the array's unit cap is smaller than the parasitic it drives

## In Progress

Issues currently being built (`loom:building`).

- **#621**: Coherent-sine capture: root-cause the single +438 LSB outlier (conversion 9) and add a per-code outlier check to the validity gate
- **#624**: Remove 10 unused imports flagged by ruff F401 (L_MET3/L_MET4 regression, test files)

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
- **#588**: Simplify the Chipalooza proposal citation gate: ~16k lines of checker, tests and rationale guard one prose document *(hermit)*

## Epics

- **#23**: Gap to T1 (bronze): tracker for the six failing items of the 2026-08-15 checklist re-read

## Backlog Balance

| Tier | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Operator priority | 0 |
| Ready (`loom:issue`) | 1 |
| In Progress (`loom:building`) | 2 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 1 |
| Curated | 4 |
| Architect / Hermit proposals | 3 |
| Active epics | 1 |

<!-- guide:plan-body:end -->

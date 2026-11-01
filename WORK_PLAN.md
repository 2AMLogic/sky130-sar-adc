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

- **#103**: T1 item 2 (layout): top-level SAR ADC layout assembly
- **#121**: [Epic #542] 4B — Chipalooza Challenge #4 (Sky130) brief document + sign-off

## In Progress

Issues currently being built (`loom:building`).

- **#676**: Bind T1 items 1, 2, 9 and 10 to audited artifacts (both partitions) with artifact-anchored envelopes
- **#753**: spec: record DR-022 post-#722 status and file its open items
- **#754**: sim: measure CDAC top-plate C_par composition per corner (C(V) extraction, incl. r+c corners)
- **#756**: sim: CDAC gain error, mismatch half (Monte Carlo check of analytic 1.42 LSB 3-sigma)

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#758**: docs(DR-022): record post-#722 status and file open items

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#681**: feat(signoff): bind T1 items 1, 2, 9, 10 to audited artifacts; add sequencer parity check

## Proposed

Issues carrying `loom:curated`.

- **#103**: T1 item 2 (layout): top-level SAR ADC layout assembly *(curated)*
- **#121**: [Epic #542] 4B — Chipalooza Challenge #4 (Sky130) brief document + sign-off *(curated)*
- **#428**: Operator hand-off: create the 'main: required status checks' ruleset that arms the base-freshness guard (from #422 / PR #425) *(curated)*
- **#676**: Bind T1 items 1, 2, 9 and 10 to audited artifacts (both partitions) with artifact-anchored envelopes *(curated)*
- **#734**: Bump layout/requirements.txt to klt 0.8.0 and re-run layout flows *(curated)*
- **#753**: spec: record DR-022 post-#722 status and file its open items *(curated)*
- **#754**: sim: measure CDAC top-plate C_par composition per corner (C(V) extraction, incl. r+c corners) *(curated)*
- **#756**: sim: CDAC gain error, mismatch half (Monte Carlo check of analytic 1.42 LSB 3-sigma) *(curated)*

## Proposed (Architect / Hermit)

- **#121**: [Epic #542] 4B — Chipalooza Challenge #4 (Sky130) brief document + sign-off *(architect)*
- **#564**: Pilot: express one PVT corner campaign as a klt sim request (first klt sim envelope) *(architect)*
- **#658**: Refresh stale tracker #23 body to point at signoff/t1-report.json instead of the 2026-08-15 analog/10-item table *(architect)*
- **#588**: Simplify the Chipalooza proposal citation gate: ~16k lines of checker, tests and rationale guard one prose document *(hermit)*

## Epics

- **#23**: Gap to T1 (bronze): tracker for the six failing items of the 2026-08-15 checklist re-read

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 0 |
| Important | 2 |
| Ready (`loom:issue`) | 2 |
| In Progress (`loom:building`) | 4 |
| PRs awaiting review | 1 |
| Approved PRs awaiting merge | 1 |
| Curated | 8 |
| Architect / Hermit proposals | 4 |
| Active epics | 1 |
<!-- guide:plan-body:end -->

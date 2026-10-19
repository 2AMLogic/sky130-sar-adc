# Work Plan

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#530**: docs(spec): DR-022 proposes a systematic gain-error spec row instead of resizing the CDAC or comparator
- **#671**: build: re-pin open_pdks to f6eeac7 (ciel) and verify PDK SOURCES revision
- **#681**: feat(signoff): bind T1 items 1, 2, 9, 10 to audited artifacts; add sequencer parity check
- **#683**: feat: digital partition STA and functional-verification evidence for T1 item 5

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#103**: T1 item 2 (layout): top-level SAR ADC layout assembly
- **#121**: [Epic #542] 4B — Chipalooza Challenge #4 (Sky130) brief document + sign-off

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#269**: design: CDAC absolute gain error (~1%) from top-plate parasitic loading -- the array's unit cap is smaller than the parasitic it drives

## In Progress

Issues currently being built (`loom:building`).

- **#669**: Re-pin open_pdks to f6eeac7 + ciel 2.6.1 + revision-checked PDK search (#668 phase 1)
- **#676**: Bind T1 items 1, 2, 9 and 10 to audited artifacts (both partitions) with artifact-anchored envelopes
- **#678**: Digital partition, item 5: multi-corner klt sta plus a bit-exact klt functional-verification suite

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#530**: docs(spec): DR-022 proposes a systematic gain-error spec row instead of resizing the CDAC or comparator
- **#671**: build: re-pin open_pdks to f6eeac7 (ciel) and verify PDK SOURCES revision
- **#681**: feat(signoff): bind T1 items 1, 2, 9, 10 to audited artifacts; add sequencer parity check
- **#683**: feat: digital partition STA and functional-verification evidence for T1 item 5

## Proposed

Issues carrying `loom:curated`.

- **#103**: T1 item 2 (layout): top-level SAR ADC layout assembly *(curated)*
- **#121**: [Epic #542] 4B — Chipalooza Challenge #4 (Sky130) brief document + sign-off *(curated)*
- **#269**: design: CDAC absolute gain error (~1%) from top-plate parasitic loading -- the array's unit cap is smaller than the parasitic it drives *(curated)*
- **#621**: Coherent-sine capture: root-cause the single +438 LSB outlier (conversion 9) and add a per-code outlier check to the validity gate *(curated)*
- **#669**: Re-pin open_pdks to f6eeac7 + ciel 2.6.1 + revision-checked PDK search (#668 phase 1) *(curated)*
- **#676**: Bind T1 items 1, 2, 9 and 10 to audited artifacts (both partitions) with artifact-anchored envelopes *(curated)*
- **#678**: Digital partition, item 5: multi-corner klt sta plus a bit-exact klt functional-verification suite *(curated)*

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
| Operator merge-risk holds | 4 |
| Very important | 0 |
| Important | 2 |
| Ready (`loom:issue`) | 1 |
| In Progress (`loom:building`) | 3 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 4 |
| Curated | 7 |
| Architect / Hermit proposals | 5 |
| Active epics | 1 |
<!-- guide:plan-body:end -->

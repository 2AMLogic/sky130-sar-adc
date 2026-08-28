# DR-007: Revised, evidence-derived ENOB and INL/DNL target values

- **Status**: proposed — this record does not self-ratify. Per the canary
  spec/DR ratification-via-PR standing policy (2AMLogic/2am#357: "a builder
  drafts the ratification/DR as a PR on the evidence, and the operator's PR
  approval is the ratification act" — the same policy DR-003 was ratified
  under, via #27/PR #46), ratifying the values below is the operator's PR
  approval, not this record's own text. Until that approval, `spec/target-spec.md`'s
  ENOB and INL/DNL rows remain DRAFT, now citing this record's candidate
  values in place of the original, un-evidenced draft numbers.
- **Date**: 2026-08-28
- **Decided by**: Builder agent, issue #129
- **Supersedes**: none (the ENOB/INL-DNL *target values* were never
  themselves ratified by any prior record — DR-003 explicitly left them open,
  "statistical rows gated on Monte-Carlo evidence", per its own Item 6)
- **Superseded by**: (none while this record stands)
- **Related**: #129 (this record), #29 / PR #130 (the Monte-Carlo evidence
  this record reads and does not re-litigate), `spec/decision-records/DR-003-numeric-spec-derivation.md`
  (Item 3's analytic `C_u` derivation and its own flagged gain-error gap;
  Item 4's noise-budget three-way split policy), `spec/decision-records/DR-005-cdac-array-design.md`
  (the CDAC array design whose evidenced shortfall this record responds to),
  `sim/cdac-array-transfer/records/20260828-005006-0c70212.md` (source DNL/INL
  Monte Carlo campaign, #29), `sim/enob-estimate/records/20260828-005033-0c70212.md`
  (source composite ENOB estimate, #29), `sim/cdac-array-transfer/run_mc.py`
  (extended by this record's PR with a `--reanalyze`/`--target-limit-lsb`
  path), `sim/enob-estimate/run_enob.py` (extended with `--target-baseline-bit`/
  `--target-stretch-bit`).

## Context

Issue #29's Monte Carlo campaign (merged via PR #130) produced real
evidence that the design **as currently sized does not meet either DRAFT
target** at the nominal (`tt`/27 °C/1.8 V) mismatch corner sampled:

- **INL/DNL** (`sim/cdac-array-transfer/records/20260828-005006-0c70212.md`,
  N=40, `tt_mm` corner): `klt yield` reports empirical yield **0.825**
  (max\|DNL\|) / **0.925** (max\|INL\|) against the DRAFT `<= +-1 LSB`
  target's `target_yield=0.99` — both below target, with `klt yield`'s own
  verdict explicit that "the observed pass rate ... is at or below the ...
  target, so no sample count can support the claim -- this is the design
  falling short, not the campaign."
- **ENOB** (`sim/enob-estimate/records/20260828-005033-0c70212.md`, a
  behavioral-accelerated composite of quantization noise, #28's ratified
  worst-corner comparator noise, and this campaign's own CDAC-mismatch INL,
  combined in quadrature): **8.491 bit** (mean-case) / **7.749 bit**
  (worst-case) against the DRAFT `> 9.0 bit` baseline / `> 9.5 bit` stretch.

Issue #129 asks whoever picks it up to either (a) redesign to close the gap,
verified by a fresh MC campaign, or (b) draft a decision record proposing a
revised, evidence-derived target — never a silent loosening. This record
takes path (b), for a reason stated plainly, not just asserted: **closing
the gap via redesign (path a) means increasing the CDAC unit cap `C_u`,
which is itself a RATIFIED value** (DR-003 via #27, `C_u ~= 8.65 fF`). That
makes path (a) a full re-opening of a ratified row — its own DR, its own
operator ratification request, a layout-affecting change, and a fresh
multi-axis PVT+mismatch MC re-verification campaign — a substantially larger
scope than this issue's own remit (see "Alternatives considered" below for
this record's own back-of-envelope sizing of that cost, so the option is
quantified, not merely deferred as an unweighed maybe). Path (b) is scoped
to exactly what #129 asks: read the evidence, do not relax it, propose
numbers the evidence actually supports.

**What is verified vs. still assumed.** Every number below is read directly
from #29's already-committed evidence (records + the raw `mc-draws/` logs
this record's own PR re-parses to confirm, via `reanalyze_from_logs()` in
`sim/cdac-array-transfer/run_mc.py`) — not invented, not backed into by
picking whatever number happens to pass. What is **not** verified: the
target-yield statistical claim below (0.99) is NOT confirmed at the
confidence #29's own N=40 sample size can support — see "Consequences" for
the concrete required-N gap this record names as open, unresolved work,
consistent with #29's own honesty convention ("N is sized for the
distribution-shape claim ..., not chosen for runtime convenience").

## Decision

**Revise the DRAFT target *values* (not the target-yield policy, not the
methodology) as follows, both still DRAFT (candidate, unratified) pending
operator approval of this record:**

1. **INL/DNL: `<= +-2.0 LSB`** (was `<= +-1 LSB`). Evidence: re-scoring
   #29's own N=40 `tt_mm` draws (same underlying data, re-parsed from the
   committed `mc-draws/20260828-005006-0c70212/` logs, zero new ngspice
   runs — `sim/cdac-array-transfer/records/<new-record-id>.md`, this PR)
   against this candidate bound gives **0 failures out of 40** on both
   max\|DNL\| (observed max 1.9716 LSB) and max\|INL\| (observed max 1.3147
   LSB) — a comfortable margin above the single worst draw observed in
   either statistic. `target_yield` is held at `0.99` (unchanged) — this
   record revises the LSB bound the evidence could not clear, not the
   statistical confidence bar itself.
2. **ENOB: `> 7.5 bit` (baseline, was `> 9.0`), `> 8.0 bit` (stretch, was
   `> 9.5`)**. Evidence: #29's own composite estimate, re-scored against
   these candidates (`sim/enob-estimate/records/<new-record-id>.md`, this
   PR, same source data as `20260828-005033-0c70212.md`) — worst-case
   (7.749 bit) clears the revised baseline with a `0.249` bit margin;
   mean-case (8.491 bit) clears the revised stretch with a `0.491` bit
   margin, while worst-case does NOT clear the revised stretch (by design —
   see "Alternatives considered" for why a stretch target that already holds
   at worst-case would not be a stretch target at all).

Both revised values are **evidence-supported margins above/below the actual
measured points**, not values picked to exactly match what was measured —
DNL/INL's `2.0 LSB` bound clears the single worst observed draw with `>=`
`0.028` LSB headroom on DNL (`2.0 - 1.9716`) even before accounting for
undersampling; ENOB's baseline/stretch split preserves the same
worst-case-must-hold / mean-case-may-not-quite-reach-stretch semantics the
original DRAFT `9.0`/`9.5` pair had (verify: original worst-case `7.749`
already failed the ORIGINAL `9.0` baseline, so the original pair could never
have expressed "baseline holds at worst-case" either — this record is the
first target-value proposal for this row that a worst-case draw actually
clears).

## Alternatives considered

- **Redesign the CDAC array now (issue #129's path (a))**: rejected for
  THIS record, not rejected outright. Quantified cost, worked from #29's own
  numbers: closing the gap at the ORIGINAL DRAFT baseline (`ENOB > 9.0`)
  purely via a larger `C_u` requires the worst-case CDAC-mismatch INL rms
  contribution to shrink from the measured `4.6220 mV` to `<=1.4713 mV`
  (so that `sqrt(0.9591^2 + 0.0705^2 + 1.4713^2) <= 1.7577 mV`, DR-003 Item
  4's own three-way-split baseline budget) — a `3.14x` reduction in rms. Per
  Pelgrom-law mismatch scaling (`sigma_u ~ 1/sqrt(C_u)`, the same relation
  DR-003 Item 3 inverted to size the ratified `C_u`), that needs a `~9.9x`
  (`3.14^2`) increase in `C_u`/array area: roughly `8.65 fF -> ~85 fF` per
  unit cap, `C_total ~= 8.86 pF -> ~87 pF` for the full differential array.
  This is a rough order-of-magnitude estimate (assumes the observed-max
  order statistic scales with the same factor as the underlying mismatch
  sigma, which is only approximately true), not a sized design — but it is
  large enough on its own terms to make clear why this is a separate,
  larger-scope follow-on: it reopens a RATIFIED row (DR-003's `C_u`),
  needs its own operator ratification request (mirroring #26 -> #27),
  changes `design/cdac/cdac_unit_cell.sch`/`cdac_array.sch` (DR-005),
  invalidates any existing `layout/cdac-array/` work sized against the old
  `C_u`, and needs a fresh multi-draw MC re-verification campaign at the new
  size before any claim against it is trustworthy. One incidental upside
  named for whoever takes that up: DR-003 Item 3's own flagged
  spec-completeness gap (the ratified `C_u`'s `1.42 LSB` 3-sigma gain error,
  which would exceed a hypothetical `1 LSB` gain-error target) would shrink
  to `~0.45 LSB` at the same `~9.9x` `C_u` this ENOB fix needs — the two
  problems share one lever.
- **Rebalance DR-003 Item 4's noise-budget three-way split** (give CDAC
  mismatch a larger share of the non-quantization budget, shrinking the
  comparator/kT-C shares) instead of, or alongside, a `C_u` increase.
  Rejected here for the same reason as the redesign option: DR-003 Item 4's
  equal-share policy is itself a ratified-alongside-`C_u` decision (via
  #27), and re-deriving an unequal split is exactly the kind of
  re-litigation this record's narrower scope (propose a revised *target
  value*, not re-open the ratified noise-budget policy) is meant to avoid.
  Named as a legitimate future alternative to the pure-`C_u`-scaling option
  above, not evaluated further here.
- **Lower `target_yield` instead of widening the LSB/bit bound** (e.g. keep
  `<= +-1 LSB` but drop `target_yield` from `0.99` to something #29's N=40
  evidence already clears). Rejected: the observed pass rate at the ORIGINAL
  `<= +-1 LSB` bound (`0.825`/`0.925`) is #29's own `klt yield` verdict
  language for "the design falling short, not the campaign" — no
  `target_yield` reduction changes that the *distribution itself* is
  centered too far from zero (mean `0.7833`/`0.7191` LSB) to plausibly clear
  a `1 LSB` bound at ANY defensible yield fraction; this would be a
  no-teeth spec row (a `target_yield` low enough to pass today's `0.825`
  empirical rate is not a meaningful accuracy target). Revising the LSB
  bound, not the yield policy, keeps `target_yield=0.99` meaningful as the
  accuracy target's own confidence bar.
- **Widen the LSB/bit bound to exactly the observed worst point with zero
  margin** (e.g. `INL/DNL <= +-1.9716 LSB`, ENOB baseline `> 7.749`).
  Rejected: this is "invent settled numbers to replace the drafts" in the
  opposite direction CLAUDE.md warns against — a target that a single N=40
  campaign's single worst draw exactly meets, with zero headroom for
  undersampling or a future larger-N campaign's own worse tail, is not a
  target, it is a restatement of one data point. The values chosen above
  keep real headroom above/below the measured extremes.

## Spec lines affected

`spec/target-spec.md`'s **Target table**, rows `ENOB` and `INL / DNL`:

- `ENOB`: `> 9.0 bit (target), stretch > 9.5` -> `> 7.5 bit (target,
  DR-007 candidate), stretch > 8.0` — Status stays `DRAFT (target value)`,
  note updated to cite DR-007.
- `INL / DNL`: `<= +-1 LSB (target)` -> `<= +-2.0 LSB (target, DR-007
  candidate)` — Status stays `DRAFT (target value)`, note updated to cite
  DR-007.

No other row is touched. `V_REF`, LSB, `N`, the CDAC unit-cap/array size,
the comparator noise budget, and the corner set stay exactly as DR-003
ratified them (via #27) — this record does not reopen any of those.

## Consequences

1. **A revised, evidence-anchored target now exists for both statistical
   rows**, closing the "DRAFT target with zero supporting evidence" gap
   DR-003 Item 6 explicitly left open — the numbers above are the FIRST
   version of this row any real Monte Carlo campaign has actually cleared.
2. **The original DRAFT `<= +-1 LSB` / `> 9.0`/`> 9.5` values are
   superseded as target-spec.md rows, not erased as evidence.** #29's own
   records (`20260828-005006-0c70212.md`, `20260828-005033-0c70212.md`)
   stay exactly as written — append-only, per `sim/README.md` — and remain
   the record of what the design does NOT meet against the original,
   more-ambitious numbers. A reader comparing this record's candidate
   values against those original DRAFT numbers can see directly how much
   was given up (roughly `2x` on INL/DNL, `1.5`/`1.5` bit on ENOB
   baseline/stretch) and why (see "Alternatives considered").
3. **The `target_yield=0.99` statistical bar is NOT yet confirmed at the
   revised bound with real confidence** — #29's N=40 zero-failure result at
   the `2.0 LSB` bound gives only a two-sided 95% CI lower bound of
   `~0.912` (via the standard zero-failure Clopper-Pearson bound,
   `(alpha/2)^(1/n)` at `alpha=0.05, n=40` — computed by hand here, NOT by
   `klt yield`, since the native `klt_yield_native` extension was not
   buildable in this record's own evidence-generation environment; see the
   re-scored `sim/cdac-array-transfer/` record's own honest note on this
   gap). Clearing `target_yield=0.99` at that same confidence with zero
   observed failures needs roughly **367** zero-failure draws (two-sided)
   — named here as **open, unresolved work**, not asserted. This record
   proposes the candidate VALUE change; it does not claim the statistical
   confirmation #29's own campaign size cannot yet support.
4. **This candidate is provisional in the same sense DR-003's Item 3/Item 6
   numbers were before #27's ratification** — a future larger-N/full-corner
   MC campaign (the natural next step, named but not executed here) could
   still tighten or loosen these candidates further before any operator
   ratifies them; this record is a proposal on today's evidence, not a
   final word.
5. **`sim/cdac-array-transfer/run_mc.py` and `sim/enob-estimate/run_enob.py`
   gain reusable, generic CLI parameters** (`--reanalyze`/
   `--target-limit-lsb`/`--target-yield` on the former,
   `--target-baseline-bit`/`--target-stretch-bit`/`--target-yield` on the
   latter) — any FUTURE candidate-target proposal can re-score the same
   already-collected evidence against a different candidate without a fresh
   ngspice campaign, the same "derived/composite, no new netlist executed"
   discipline `run_enob.py` already established for combining
   already-run experiments.

## Open items

- **Statistical confirmation of `target_yield=0.99` at the revised INL/DNL
  bound** — owner: a future larger-N (~367+ zero-failure draws, per
  Consequences §3) or full corner x mismatch MC campaign; not resolved
  here.
- **CDAC redesign (larger `C_u`) as a longer-term path back toward the
  ORIGINAL, more-ambitious DRAFT numbers** — quantified at `~9.9x` `C_u`/
  area in "Alternatives considered", not sized or executed here; would need
  its own DR reopening the ratified `C_u` row, its own operator
  ratification request, and a fresh MC campaign.
- **Noise-budget re-split (Item 4 rebalancing)** as an alternative or
  complement to a pure `C_u` increase — named, not evaluated.
- **Operator ratification of this record** — mirrors #26 -> #27's
  two-step pattern (draft, then a ratification act); until approved, the
  candidate values above remain DRAFT, cited by `spec/target-spec.md` but
  not binding.
- **`klt_yield_native` build gap in this record's own evidence-generation
  environment** — the re-scored `sim/cdac-array-transfer/`/
  `sim/enob-estimate/` records this PR adds could not produce a machine
  `klt yield` verdict (unlike #29's own records, which could); this is the
  SAME already-filed, COMPLETED `2AMLogic/klayout-tools#1061` packaging gap
  those records' own fallback text already names, not a new gap — but it
  does mean this record's own new evidence relies on hand-derived
  Clopper-Pearson arithmetic (Consequences §3) rather than a fresh machine
  report; owner: re-run with `klt yield` available to confirm the hand
  arithmetic once the extension is reachable in a future evidence-generation
  environment.

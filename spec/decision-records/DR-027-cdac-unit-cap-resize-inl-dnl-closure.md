# DR-027: CDAC unit-cap resize to 3.3000 µm — the design-side closure of the INL/DNL row that DR-007 left as future work

- **Status**: proposed — this record does not self-ratify and implements
  nothing. Per the canary spec/DR ratification-via-PR standing policy
  (2AMLogic/2am#357, the same mechanism DR-003/DR-019 were ratified under),
  ratifying the resize below is the operator's approval of the PR that
  carries this record, on the same two-key route as DR-022 (EE and market
  reviews posted on the PR first).
- **Date**: 2026-11-21
- **Decided by**: Builder agent, issue #1016 (scope: the bounded study
  DR-007's "Alternatives considered" left open — "named as future work, not
  foreclosed"; decision + evidence only, no implementation)
- **Supersedes**: none (it amends the unit-cap figures DR-003 Item 3 set and
  DR-019 last resized; both records stand — this record proposes the next
  move of the same parameter, on new evidence)
- **Superseded by**: (none while this record stands)
- **Related**: #1016 (this decision), #29 / PR #130 and #912 (the source
  Monte-Carlo campaign and its freshness-pinnable re-mint),
  `sim/cdac-array-transfer/analysis/20261126-034329-5a2e0198.md`
  (the attribution + closure study every number below comes from — the
  "design memo" this record cites, per TEMPLATE.md's decision-vs-derivation
  split),
  `sim/cdac-array-transfer/records/20261121-075027-75b91e85.md` (the
  step-3 pilot: fresh MC of the candidate array, N=16, seed 101),
  `sim/cdac-array-transfer/records/20261121-075334-75b91e85.md` (the
  pilot's `klt yield` envelope, negative control declared),
  `sim/cdac-array-transfer/records/20261123-153432-fe3e3dcf.md` (supersedes
  the envelope record above: same draws and verdicts, the generated
  negative-control sentence corrected to a declaration),
  `sim/cdac-array-transfer/records/20261126-034358-5a2e0198.md` (current
  pilot envelope, with the precision statement corrected from the same draws),
  [DR-003](DR-003-numeric-spec-derivation.md) Item 3 (the matching floor
  this record moves), [DR-005](DR-005-cdac-array-design.md),
  [DR-007](DR-007-revised-enob-inl-dnl-targets.md) (the target-value
  proposal whose alternative path this record is; NOT re-litigated here),
  [DR-019](DR-019-cdac-unit-cap-grid-legal-plate-resize.md) (the current
  1.9000 µm plate), [DR-022](DR-022-cdac-gain-error-specified-not-sized.md)
  / [DR-025](DR-025-cdac-gain-error-closure-path.md) (the gain-error
  problem the resize partially helps, cited not claimed),
  [DR-006](DR-006-sar-sequencer-bit-count-and-timing-budget.md) (the
  timing budget the settling re-derivation must respect). **Port parity**:
  `2AMLogic/gf180-sar-adc` sizes its own unit cap for the gf180 PDK's
  mismatch coefficients; this record's number is sky130-specific and
  creates no parity obligation beyond recording the divergence in `spec/`.

## Context

The committed Monte-Carlo evidence says the CDAC as sized does not meet the
ORIGINAL DRAFT `INL/DNL <= +-1 LSB` row at `target_yield` 0.99: empirical
yield 0.825 (DNL) / 0.925 (INL) at N=40, with `klt yield`'s own verdict
"this is the design falling short, not the campaign". DR-007 answered the
same evidence by proposing relaxed TARGET VALUES (`+-2.0 LSB`, `> 7.5 bit`)
and explicitly left the other path — fix the design — "named as future
work, not foreclosed". Issue #1016 is that path, and its bounds apply here:
throughout, the limit is the original `<= +-1 LSB` at 0.99, never the
`+-2.0 LSB` candidate; no spec row is edited by this record; DR-007's
ratification remains the operator's and is not argued.

**What the study verified (all numbers re-derivable from committed logs by
`sim/cdac-array-transfer/analysis/attribute_1016.py`):**

1. **Attribution.** The spread is unit-cap mismatch, not switch mismatch:
   a caps-only isolation probe (every FET replaced by an ideal drive, caps
   keeping their `tt_mm` AGAUSS; committed under `analysis/probe-caps-only-*`)
   reproduces the committed campaign's per-code level jitter in pattern and
   magnitude (mid-split codes 1.0–1.7 mV rms in both; endpoints quiet). The
   per-transition random sigmas follow the switched-unit-count
   (McCreary–Wooley) shape, Pearson r = 0.859 (DNL) / 0.955 (INL); the
   PDK's Pelgrom figure for the drawn 1.9000 µm plate is
   `sigma(C_u)/C_u = 1.4737 %` (`A_C = 2.8 %·µm`), and under the
   like-for-like differential ADC-LSB convention the draws imply 0.97 % /
   1.16 % — same order, convention-limited agreement.
2. **Structural finding (recorded, not acted on).** The campaign fragment
   gives every code its own array copy, so its per-draw "DNL" conflates
   copy-to-copy level variance with within-die DNL (evidence: the 1-unit
   transition 384→385 carries σ = 0.375 LSB and holds the draw max in 6/40
   draws — static-bit noise a within-die DNL would cancel). The campaign's
   max|DNL| is therefore a CONSERVATIVE structure on within-die DNL; sizing
   the closure against it also closes within-die DNL. Changing the
   methodology is out of this issue's bounds; filed as its own question.
3. **The mismatch-disabled floor is systematic.** max|DNL| 0.2364 /
   max|INL| 0.1534 LSB with mismatch off, growing with the switched block
   (−0.2364 LSB at the 511-unit MSB carry). Area does not remove it; the
   closure model holds it fixed (conservative).
4. **Closure comparison** (predicted by the decomposition model:
   systematic fixed, random × 1.9/p Pelgrom; "margin" = mean + 2.326σ vs
   the 1 LSB limit):
   - **A — larger unit cap**: 3.100 µm (×2.66 unit area) is the first
     5 nm grid point that meets both margins.
     **3.300 µm** carries ~5 % headroom on the binding (DNL) statistic.
   - **B — unary segmentation at constant total C**: fixes DNL only; INL
     margin stays −0.203 at every t. B alone cannot close the row.
   - **D — segmentation (t=2/3) + 2.335 µm plate**: meets both at unit area
     ×1.51 vs ×3.02, but adds a thermometer decoder to the sequencer
     (digital re-composition, DR-006 re-verification), splits the MSB
     column routing, and STILL reopens the Sampling-cap row.
   - **C — layout matching changes**: not evidencable (the PDK's MiM
     mismatch is per-instance random with no spatial term; the floor is
     present with mismatch off). Retained as follow-up-layout good
     practice, no yield number.
5. **Simulated confirmation (not scaling alone).** A fresh MC of the
   candidate array (generated study variant — `design/cdac` untouched),
   N=16, seed 101 (outside the source campaign's seeds, so out-of-sample
   for the model): measured max|DNL| 0.493±0.182 / max|INL| 0.399±0.112 LSB
   vs model-predicted 0.499±0.196 / 0.450±0.126; all 16 draws clear ±1 LSB
   on both; `klt yield` envelope cpk 0.93 (DNL) / 1.79 (INL), required
   N = 368 to claim 0.99 at this pass rate. At N=16 the estimated standard
   deviation has 18.3% relative standard error, above the 10% precision
   target. The batch fleet run is parked
   by #811, so this pilot is the smallest local run the host rules allow
   and the sized run is the stated next step (follow-up issue filed).

## Decision

**Adopt closure option A: resize the CDAC unit capacitor's MiM plate from
`W = L = 1.9000 µm` (DR-019) to `W = L = 3.3000 µm`** (3300 nm — 5
nm-grid-legal, above DR-003's matching floor in the same direction DR-019
rounded), with:

- `C_u = camimc·area + cpmimc·perimeter = 24.29 fF` (from 8.6640 fF;
  ×2.80), `sigma_u = A_C/3.3000 = 0.8485 %` (from 1.4737 %),
- unit-cap area ×3.02; array core 217.7 × 54.4 µm → 307.3 × 76.8 µm
  (×1.99 — the capm-gap pitch rule `plate + 1.502` does not scale with the
  plate), same 64 × 16 topology, `C_tot ≈ 12.4 pF/side`,
- predicted campaign-metric outcome (the metric `klt yield` grades):
  max|DNL| 0.499 ± 0.196 LSB, max|INL| 0.450 ± 0.126 LSB against ±1 LSB —
  both margins met with headroom, confirmed out-of-sample by the pilot.

Rejected: B alone (cannot close INL); D as the FIRST move (saves ×1.51 vs
×3.02 unit area but reopens the same spec row anyway and widens the
re-verification surface across the digital partition — the area saving is
real and D stays the documented fallback if the operator rejects A's area
cost); C (no evidencable mechanism for either contributor). Not taken here:
relaxing any target value (DR-007's own track, the operator's call),
lowering `target_yield`, or any methodology change.

## Spec lines affected (proposed, NOT edited by this record)

`spec/target-spec.md` Target table, row **Sampling cap (CDAC unit ×
array)** — currently RATIFIED (DR-003 via #27; plate resized by DR-019 via
#496):

| Field | Old | Proposed |
|---|---|---|
| Unit-cap plate side | `1.9000 µm` | `3.3000 µm` |
| `C_u` | `≈ 8.66 fF` (`8.6640 fF`) | `≈ 24.29 fF` |
| Array size | `2^9 = 512` positions/side | unchanged |
| Status | RATIFIED | RATIFIED-pending this record's operator approval |

Rows this resize MOVES THE PHYSICS OF, without this record claiming any of
them (each gets its own re-derivation in the follow-ups):

- **kT/C noise** (ratified): improves ×3.02 — the ~415× margin grows.
- **Settling / sample rate** (DRAFT `100 kS/s–1 MS/s`, never re-derived):
  the larger array must be re-derived against DR-006's timing budget —
  follow-up issue filed; the resize must NOT be ratified without that
  answer.
- **ENOB / INL-DNL target rows** (DRAFT, DR-007 candidates): the mismatch
  halves this record's numbers address shrink ×1.74 (`1.9/3.3`); any
  target-value decision stays exactly where DR-007 left it.
- **DR-022/DR-025 gain error** (DRAFT candidate row `<= 1.42 LSB`): the
  systematic `C_par/(512·C_u)` term shrinks with `C_u` — direction noted,
  no number claimed (that is DR-025's closure question, separately open).

## Consequences

1. **Nothing is implemented by this record.** The follow-ups it names are
   filed as separate issues (#1031-#1034, see Open items); until the
   operator approves this record AND they land, `design/`,
   `layout/cdac-array/`, and `layout/halflsb-offset/` still carry 1.9000 µm
   — a known, tracked divergence, not a defect of this record.
2. **The evidence trail this record stands on is pilot-scale.** N=16
   confirms the scaling out-of-sample but cannot CLAIM 0.99 yield (`klt
   yield`'s own verdict: required N = 368; the declared negative control is
   not yet distinguishable from nominal at N=16). The sized fleet run
   (N ≥ 368, `klt sim` `monte_carlo`, `--wait-for-capacity 600`, recorded
   seed, declared negative control) is the citable-envelope step for T1
   item 6 and is filed as its own issue, blocked by #811's park.
3. **The worst-draw caveat is stated, not hidden.** Sizing to make all 40
   source-campaign draws pass would need 4.320 µm (×5.17 unit area), dominated
   by one 3–4σ tail draw (seed 7). This record sizes on the normal-fit
   margin with ~5 % headroom instead — the same reasoning DR-007 itself
   used to reject zero-headroom targets — and names the sized run as the
   empirical resolver.
4. **Friction filed:** none new for klayout-tools out of this study (the
   `klt yield` negative-control declaration and sample-size verdicts worked
   as documented; the PATH-`klt`-lacks-`klt_yield_native` gap is the
   already-filed packaging issue the pin file records).

## Open items

- Operator ratification of this record (the PR carrying it).
- Follow-up issues filed from this record: **#1031** (carry the 3.3000 µm
  resize through `design/cdac/`, `design/sar_adc_top.sch`,
  `layout/cdac-array/`, `layout/halflsb-offset/` and the dependent flows —
  the #498 pattern at the new size; blocked by this record's ratification),
  **#1032** (the sized N ≥ 368 fleet MC campaign + citable `klt yield`
  envelope for T1 item 6; blocked by #811's park), **#1033** (the
  settling/sample-rate re-derivation at `C_tot ≈ 12.4 pF/side` against
  DR-006), **#1034** (the within-die-DNL methodology question raised by the
  attribution study's cross-copy finding — a question, not a change).
- DR-007's ratification (either direction) remains open and independent.

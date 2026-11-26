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
  `sim/cdac-array-transfer/analysis/20261126-051351-2daeef14.md`
  (the attribution + closure study every number below comes from — the
  "design memo" this record cites, per TEMPLATE.md's decision-vs-derivation
  split),
  `sim/cdac-array-transfer/records/20261121-075027-75b91e85.md` (the
  step-3 pilot: fresh MC of the candidate array, N=16, seed 101),
  `sim/cdac-array-transfer/records/20261126-051316-7e91374a.md` (current
  pilot envelope, replayed from the archived draws with the as-built control,
  corrected MiM model and geometry-specific PVT scope),
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

**Study results from the archived draws, the combined MiM card and the
DR-019 design reference**

1. **Attribution.** The eight-seed caps-only probe replaces the FETs with
   ideal drives and retains the capacitors’ `tt_mm` mismatch. Its logs are in
   `analysis/probe-caps-only-20261121-075648-75b91e85/`. At codes 255 and 256,
   the probe gives 1.46 and 1.66 mV of level jitter. The 40-draw campaign
   gives 1.60 mV at both. Across all 11 probe codes the level standard deviations
   correlate with r = 0.979. The DNL sigmas correlate with the square root
   of switched units (r = 0.859).
   INL sigmas correlate with the code-level model (r = 0.955). The
   combined `tt_mm` MiM card gives relative mismatch `0.0047/(W + 0.150)`
   for square plates at `mult=1` (W in µm), or 0.2293% at 1.900 µm and
   0.1362% at 3.300 µm. DR-019’s design reference gives 1.4737% and
   0.8485%, respectively. The deck supplies `MF=m=bit weight` and omits
   `mult`. ngspice multiplies the primitive capacitance and its single
   mismatch draw by `m`. The fitted independent-unit coefficients of
   1.9475% (DNL) and 2.3192% (INL) summarize campaign spread. For the
   ideal weighted divider, summing independent group, copy and P/N
   variances at the 255→256 carry gives σ = 0.6771 ADC LSB. The archived
   draws give 0.5828 LSB. A one-side unit step is 1.8 V / 512 = 3.515625 mV.
2. **Cross-copy DNL.** The campaign gives every code its own array copy,
   so a step includes two independent level errors. The single-unit 384→385 step
   carries σ = 0.375 LSB and holds the draw maximum in 6/40 draws.
   Conversely, the complementary selections at 255→256 give ideal one-side
   variance coefficients of 510.998 on a shared array and 255.998 across
   copies. The operator retained the cross-copy metric for sizing in #1034.
   Within-die DNL remains unmeasured.
3. **Mismatch-disabled controls.** Maximum absolute DNL / INL is
   0.236446 / 0.153445 LSB for the source and 0.122668 / 0.085145 LSB
   for the pilot. The closure model assumes the source systematic terms
   stay fixed. Both plate size and tool versions differ between campaigns.
4. **Closure comparison.** The model holds the source systematic terms
   fixed and scales the random terms by `(1.9 + 0.150)/(p + 0.150)`. The fitted upper bound is
   mean + 2.326σ. The fractional margin is (limit − bound)/limit.
   - **A — larger unit cap**: 3.195 µm (×2.83 unit area) is the first
     5 nm grid point that meets both margins.
     At **3.300 µm** the fitted bounds are 0.976534 LSB DNL and 0.763397 LSB
     INL, leaving 2.35% headroom on DNL.
   - **B — unary segmentation at constant total C**. The worst within-array
     carry switches 511, 511, 255 and 127 units per side for zero through
     three thermometer MSBs. One thermometer MSB is the existing binary MSB.
     Uniformly scaling measured random DNL by the square root of the count
     ratio gives fitted DNL bounds of 1.509, 1.116 and 0.859 LSB for one,
     two and three MSBs. The corresponding sample standard deviations of max|DNL|
     are 0.3120, 0.2290 and 0.1755 LSB. The max|INL| standard deviation stays
     at 0.2085 LSB (margin −0.203).
     This sensitivity calculation cannot establish segmented cross-copy
     yield because independent copies also contribute unchanged-bit errors.
   - **D — segmentation (t=2/3) + 2.370 µm plate**. Under the same
     assumption both depths meet the fitted limits. The DNL margins are
     +0.048 and +0.257, respectively, with INL just at the limit on the
     5 nm grid. The max|DNL| standard deviations are 0.1953 and 0.1494 LSB.
     Both depths give 0.1721 LSB for max|INL|. The projected unit area is ×1.56 vs ×3.02. D adds a
     thermometer decoder to the sequencer
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
   vs model-predicted 0.511±0.200 / 0.461±0.130; all 16 draws clear ±1 LSB
   on both at `tt_mm`, 27 °C, 1.8 V. The five-code PVT transfer sweeps
   tested 1.8988 and 1.9000 µm plates. Across-corner transfer monotonicity
   and mismatch yield remain open at 3.300 µm. The `klt yield` envelope
   gives Cpk 0.93 (DNL) and 1.79 (INL). It requires 368 draws to claim
   0.99 yield at this pass rate. At N=16 the estimated standard
   deviation has 18.3% relative standard error, above the 10% precision
   target. The batch fleet run is parked
   by #811, so this pilot is the smallest local run the host rules allow
   and the sized run is the stated next step (follow-up issue filed).

## Decision

**Adopt closure option A: resize the CDAC unit capacitor's MiM plate from
`W = L = 1.9000 µm` (DR-019) to `W = L = 3.3000 µm`** (3300 nm — 5
nm-grid-legal, above DR-003's matching floor in the same direction DR-019
rounded), with:

- DR-019 design reference for the proposed spec row:
  `C_u = camimc·area + cpmimc·perimeter` gives 8.664 → 24.288 fF and
  `sigma_u = 2.8 %·µm/W` gives 1.4737% → 0.8485%.
  The combined card used for the simulations gives
  `C_u = 2(W + 0.150)²` fF, or 8.405 → 23.805 fF
  (4.303 → 12.188 pF for 512 units/side). The independent
  [unit-cap probes](../../sim/cdac-bit-trial-settling/records/20261123-000415-d1ce38af.md)
  measured those same values.
- unit-cap area ×3.02. Holding the existing 1.500 µm gap gives a pitch of
  3.400 → 4.800 µm and an estimated core of 217.6 × 54.4 → 307.2 × 76.8 µm
  (×1.99) at 64 × 16 units, `C_tot ≈ 12.4 pF/side`. Precheck and spacing
  verification require a candidate layout,
- predicted campaign-metric outcome (the metric `klt yield` grades):
  max|DNL| 0.511 ± 0.200 LSB, max|INL| 0.461 ± 0.130 LSB against ±1 LSB —
  both fitted bounds meet the limit. All 16 out-of-sample pilot draws pass.

Rejected: B alone (misses the modeled INL limit); D as the FIRST move
(the ×1.56 unit-area estimate requires segmented-campaign verification
and reopens the same spec row as A plus the digital partition); C (no
measured yield benefit). D remains a fallback if the operator rejects A's area cost. Not taken here:
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

- **kT/C noise** (ratified). The capacitance margin over DR-003's thermal
  floor grows by 24.288 / 8.664 = 2.8033× from its ~415× design-reference
  baseline. The combined-card capacitances give a factor of
  23.805 / 8.405 = 2.8322. The corresponding reductions in RMS noise at
  fixed temperature are factors of 1.6743 and 1.6829, respectively.
- **Settling / sample rate** (DRAFT `100 kS/s–1 MS/s`). At the candidate
  size, #1033 found the CDAC bit trial settled within 37.4541 ns across
  nine corners. The assembled front end met the half-LSB acquisition
  criterion at 100 kS/s and missed it at all nine corners at 1 MS/s. The
  worst residual at the fast deadline was −23.7933 mV. This limits the
  resize proposal at the fast endpoint with existing switches.
  [Acquisition and bit-trial results](../../sim/sampling-cdac-handoff/records/20261123-002026-730a33ea.md)
- **ENOB / INL-DNL target rows** (DRAFT, DR-007 candidates). The random
  DNL and INL terms scale by 2.05/3.45 = 0.5942 in the closure model.
  DR-007 retains the target-value decision.
- **DR-022/DR-025 gain error** (DRAFT candidate row `<= 1.42 LSB`).
  The half-LSB cell and its opposite-side dummy each load their top plate
  with one tracking unit. On DR-019’s convention that load is 8.664 fF/side
  as built and for B/C, 24.288 fF for A and 13.035 fF for D at 2.370 µm.
  The combined card gives 8.405, 23.805 and 12.701 fF, respectively.
  The tracking load alone gives a span-error floor of 1/513 (0.195% FS,
  about 2 ADC LSB) for all four options. At fixed device sizes, the BPREF
  junction and overlap load coupled through Csamp, the sampling switch
  and the comparator input can shrink relative to the array. Routing,
  dummy coupling and segmentation wiring require candidate-layout
  extraction before assigning a total span error.

## Consequences

1. **Nothing is implemented by this record.** The follow-ups it names are
   filed as separate issues (#1031-#1034, see Open items); until the
   operator approves this record AND they land, `design/`,
   `layout/cdac-array/`, and `layout/halflsb-offset/` still carry 1.9000 µm
   — a known, tracked divergence, not a defect of this record.
2. **The evidence trail this record stands on is pilot-scale.** N=16
   checks the scaling at nominal PVT. The 0.99 yield claim remains open (`klt
   yield`'s own verdict: required N = 368; the declared negative control is
   not yet distinguishable from nominal at N=16). The sized fleet run
   (N ≥ 368, `klt sim` `monte_carlo`, `--wait-for-capacity 600`, recorded
   seed, declared negative control) is the citable-envelope step for T1
   item 6 and is filed as its own issue, blocked by #811's park.
3. **The worst-draw caveat is stated, not hidden.** Sizing to make all 40
   source-campaign draws pass would need 4.510 µm (×5.63 unit area), dominated
   by one 3–4σ tail draw (seed 7). This record sizes on the normal-fit
   margin with 2.35% DNL headroom instead — the same reasoning DR-007 itself
   used to reject zero-headroom targets — and names the sized run as the
   empirical resolver. Issue #1032 names 4.510 µm as the fallback to
   evaluate if the sized 3.300 µm run misses its yield target.
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
  DR-006), **#1034** (resolved by retaining the current cross-copy metric).
- DR-007's ratification (either direction) remains open and independent.

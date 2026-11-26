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
  `sim/cdac-array-transfer/analysis/20261126-041316-5c858a41.md`
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

1. **Attribution.** A caps-only isolation probe (every FET replaced by an ideal drive, caps
   keeping their `tt_mm` AGAUSS; committed under `analysis/probe-caps-only-*`)
   reproduces the committed campaign's per-code level jitter in pattern and
   magnitude (mid-split codes 1.0–1.7 mV rms in both; endpoints quiet). The
   DNL sigmas correlate with the square root of switched units (r = 0.859).
   INL sigmas correlate with the code-level model (r = 0.955). The
   PDK's Pelgrom figure for the drawn 1.9000 µm plate is
   `sigma(C_u)/C_u = 1.4737 %` (`A_C = 2.8 %·µm`), and under the
   study's switched-unit DNL and code-level INL fits the draws imply
   1.9475 % / 2.3192 %. A one-side unit step is 1.8 V / 512 = 3.515625 mV,
   one ADC LSB. Independent P/N mismatch contributions combine in quadrature.
   This gives a modeled DNL sigma of 0.4711 LSB at the 255→256 carry.
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
   fixed and scales the random terms by 1.9/p. The fitted upper bound is
   mean + 2.326σ. The fractional margin is (limit − bound)/limit.
   - **A — larger unit cap**: 3.100 µm (×2.66 unit area) is the first
     5 nm grid point that meets both margins.
     **3.300 µm** carries ~5 % headroom on the binding (DNL) statistic.
   - **B — unary segmentation at constant total C**. The worst within-array
     carry switches 511, 511, 255 and 127 units per side for zero through
     three thermometer MSBs. One thermometer MSB is the existing binary MSB.
     Uniformly scaling measured random DNL by the square root of the count
     ratio gives fitted DNL bounds of 1.509, 1.116 and 0.859 LSB for one,
     two and three MSBs. The model holds INL fixed (margin −0.203).
     This sensitivity calculation cannot establish segmented cross-copy
     yield because independent copies also contribute unchanged-bit errors.
   - **D — segmentation (t=2/3) + 2.335 µm plate**. Under the same
     assumption both depths meet the fitted limits. The DNL margins are
     +0.047 and +0.257, respectively, with INL just at the limit on the
     5 nm grid. The projected unit area is ×1.51 vs ×3.02. D adds a
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
- unit-cap area ×3.02. Holding the existing 1.500 µm gap gives a pitch of
  3.400 → 4.800 µm and an estimated core of 217.6 × 54.4 → 307.2 × 76.8 µm
  (×1.99) at 64 × 16 units, `C_tot ≈ 12.4 pF/side`. Precheck and spacing
  verification require a candidate layout,
- predicted campaign-metric outcome (the metric `klt yield` grades):
  max|DNL| 0.499 ± 0.196 LSB, max|INL| 0.450 ± 0.126 LSB against ±1 LSB —
  both margins met with headroom, confirmed out-of-sample by the pilot.

Rejected: B alone (misses the modeled INL limit); D as the FIRST move
(the ×1.51 unit-area estimate requires segmented-campaign verification
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
  floor grows by 24.288 / 8.664 = 2.8033× from the ~415× baseline.
  At fixed temperature the RMS noise falls by a factor of 1.6743.
- **Settling / sample rate** (DRAFT `100 kS/s–1 MS/s`). At the candidate
  size, #1033 found the CDAC bit trial settled within 37.4541 ns across
  nine corners. The assembled front end met the half-LSB acquisition
  criterion at 100 kS/s and missed it at all nine corners at 1 MS/s. The
  worst residual at the fast deadline was −23.7933 mV. This limits the
  resize proposal at the fast endpoint with existing switches.
  [Acquisition and bit-trial results](../../sim/sampling-cdac-handoff/records/20261123-002026-730a33ea.md)
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
  DR-006), **#1034** (resolved by retaining the current cross-copy metric).
- DR-007's ratification (either direction) remains open and independent.

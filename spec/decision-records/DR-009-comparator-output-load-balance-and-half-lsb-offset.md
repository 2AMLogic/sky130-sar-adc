# DR-009: Comparator differential-output load balancing, and a half-LSB quantizer offset at the top level

- **Status**: proposed — like DR-008 this record settles two integration-level
  wiring/sizing questions in `design/sar_adc_top.sch`, not a numeric row of
  `spec/target-spec.md`. It inherits the same provisional status as every
  record still resting on DR-003's DRAFT numeric inputs.
- **Date**: 2026-09-11
- **Decided by**: Builder agent, issue #263 (second pass)
- **Supersedes**: none
- **Superseded by**: (none while this record stands)
- **Related**: #263 (this fix), #265 (the near-full-scale `±0.78·V_REF`
  non-convergence this record does NOT close — see "Open items"),
  `spec/decision-records/DR-008-cdac-top-level-switching-polarity.md`
  (the first pass of #263, whose own "Open items" named the 2–3 LSB
  mid-scale residual this record closes),
  `spec/decision-records/DR-004-comparator-topology-and-noise-budget.md`
  (the StrongARM-class latch topology whose regeneration this record's
  load-balancing argument rests on; that record's own sizing is UNCHANGED
  here), `spec/decision-records/DR-005-cdac-array-design.md` (the CDAC
  unit cell this record's offset cap copies, and whose array this record
  does NOT modify), `design/sar_adc_top.sch`, `design/comparator.sch`,
  `sim/full-conversion-transient/` (the campaign this record is verified
  against, and the home of the `--decision-margin-trace` probe added for
  it), `sim/comparator-decision/` (the standalone comparator experiment
  that structurally could not have caught the defect below), #269 (the
  array gain error this record identifies and does NOT close).
- **Evidence**:
  `sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md`
  (9-corner campaign, supersedes `20260911-204111-a6df3bb.md`) and
  `sim/full-conversion-transient/records/20260912-011519-9aaf1ca.md`
  (two-variant decision-margin trace: the controlled experiment behind
  the mechanism claim).

## Context

After DR-008's three fixes (trial perturbation, per-conversion clear timing,
decision-directed single-side switching + output recoding), the
`sim/full-conversion-transient` campaign still showed a **corner-invariant
2–3 LSB high** reading at `Vd = +0.00·V_REF` and `+0.25·V_REF`
(`sim/full-conversion-transient/records/20260911-204111-a6df3bb.md`, 9/9
corners). DR-008 recorded that residual as an open item and guessed it was
"plausibly a distinct, easier-to-close residual" from the near-full-scale
failure. That guess is confirmed here, and the mechanism is now measured
rather than hypothesised.

**What was measured.** A diagnostic probe — added to the experiment in this
same pass and committed as
`sim/full-conversion-transient/run_conversion.py --decision-margin-trace`,
so every number below is reproducible from the tree — samples the
comparator's own differential input, `v(TOP_P) - v(TOP_N)`, at the instant
its evaluate half begins (DAC settled for half a CLK period, latch still in
reset), at every one of the 10 bit trials of the three mid-scale
conversions, alongside the decision the latch then produced. The figures in
the table below were taken during the investigation, on the pre-DR-009
netlist, at `tt/27C/1.8V` (ideal `LSB = 3.5156 mV`); the committed record
`sim/full-conversion-transient/records/20260912-011519-9aaf1ca.md`
reproduces the same signature against its `unbalanced-control` variant
(see "Consequences" for that record's own numbers):

| conversion | bit trial | comparator input | common mode | decision | correct? |
| --- | --- | --- | --- | --- | --- |
| `+0.00·V_REF` | 1 | `-7.019 mV` (`-2.00 LSB`) | 897.0 mV | `1` | **no** |
| `+0.00·V_REF` | 0 | `-10.515 mV` (`-2.99 LSB`) | 895.2 mV | `1` | **no** |
| `+0.25·V_REF` | 1 | `-3.287 mV` (`-0.93 LSB`) | 673.3 mV | `1` | **no** |
| `+0.25·V_REF` | 0 | `-6.777 mV` (`-1.93 LSB`) | 671.5 mV | `0` | yes |
| `-0.25·V_REF` | 7 | `-3.706 mV` (`-1.05 LSB`) | 676.8 mV | `1` | **no** |
| `-0.25·V_REF` | 0 | `-7.215 mV` (`-2.05 LSB`) | 678.5 mV | `0` | yes |

The comparator is not mis-timed and its input is not disturbed (the same
probe 40 ns later, deep inside the evaluate half, reads the same value to
within 0.06 mV): it is simply deciding a **negative** input as positive
whenever that input is smaller in magnitude than roughly 5 mV at a ~676 mV
top-plate common mode, or roughly 10 mV at ~896 mV. That is a systematic,
input-referred comparator **offset** of about `-1.5 LSB` to `-3 LSB`,
present in a nominal, mismatch-free netlist — hence its corner invariance.

**Where it comes from.** `design/comparator.sch` is a StrongARM-class
dynamic latch (DR-004): both outputs are pre-charged to VDD each reset
half, and the evaluate half is a *regeneration race* between the two output
nodes. Any capacitive imbalance between `OUTP` and `OUTN` biases that race
directly, with no device mismatch required. As drawn by issue #56,
`design/sar_adc_top.sch` loaded them asymmetrically: `COMP_OUT` (= `OUTP`)
drives two standard-cell input pins inside `xseq` (`xmux9.A1` and
`xxnor_compeff.A`), while `OUTN` was a documented dead-end net (`OUTN_NC`)
with no load at all. The heavier node (`OUTP`) discharges more slowly, so
`OUTN` wins marginal races and `COMP_OUT` is biased toward `1` — the exact
sign observed. The common-mode dependence follows from the same mechanism:
a higher input common mode discharges the tail pair's drains faster,
shortening the window over which the input is integrated before
regeneration takes over, so a *fixed* output-node imbalance refers back to a
*larger* input-equivalent offset.

`sim/comparator-decision/`'s standalone records could not have caught this:
that testbench exercises `design/comparator.sch` on its own, where both
outputs are loaded identically (or not at all). The defect is created by the
integration, exactly like DR-008's `SELp`/`SELn` polarity defect, and it is
fixed at the same level.

**Second, smaller mechanism.** With the offset removed, what remains at
mid-scale is the SAR's own quantization convention. A search that keeps a
trial only while the residual has not changed sign converges to a residual
in `[0, 1)` LSB (the `DOUT9=1` branch) or `(-1, 0]` LSB (the `DOUT9=0`
branch): the captured code behaves like `floor(Vd/LSB)`, with its
transitions at **integer** multiples of the LSB, while the ratified ideal
code (`ideal_code()` in
`sim/full-conversion-transient/gen_full_conversion_tb.py`,
`round(Vd/LSB) + 2^(N-1)`) has its transitions at **half** integers. That is
a systematic `-0.5 LSB` code offset — harmless alone, but it stacks with the
array's gain error (see "Open items") and took `-0.25·V_REF` to `-2 LSB`
once the comparator offset that had been masking it was removed.

## Decision

Two additions, both confined to `design/sar_adc_top.sch`. Neither changes
`design/comparator.sch`, `design/cdac/cdac_array.sch`,
`design/cdac/cdac_unit_cell.sch` or `design/sar_sequencer.sch`, so DR-004's
and DR-005's ratified sizing and every sub-block record stand unaltered.

**1. Balance the comparator's differential-output load.** `OUTN` now carries
a matched dummy load — `xdum_mux_n` (`sky130_fd_sc_hd__mux2_1`) and
`xdum_xnor_n` (`sky130_fd_sc_hd__xnor2_1`): the same two cell types, on the
same two pin positions (`mux2_1.A1`, `xnor2_1.A`) that `COMP_OUT` drives
inside `xseq`, with their other inputs wired to the *same nets* the real
cells see (`mux2_1.A0 = DOUT9`, `mux2_1.S = PH_B9`, `xnor2_1.B = DOUT9`) so
the dummies' state-dependent pin capacitance tracks the real ones cycle by
cycle instead of only on average. Both dummy outputs
(`DUMLOAD_MUX_NC`, `DUMLOAD_XNOR_NC`) are deliberate no-connects: these
cells exist only to present input capacitance. `PH_B9` — one of the ring
phases issue #56 deliberately left unconnected at this level — is named at
the top level for this purpose (and for the enable below).

**2. Add a half-LSB quantizer offset.** `Choff_n`, one CDAC-unit-sized MiM
cap (`W = L = 1.8988`, identical to `design/cdac/cdac_unit_cell.sch`'s
`C_u`), sits between `TOP_N` and its own bottom plate `BOT_OFF_N`, which is
switched between `VREFP` and `VCM` by `Moff_n_refp` / `Moff_n_cmn` /
`Moff_n_cmp` (device flavours and sizes copied from the CDAC unit cell so
the switch parasitics match a real array bit's). One unit cap over **half**
the reference swing (`VREFP -> VCM = V_REF/2`, since `VCM = V_DD/2` and
`V_REF = V_DD` by DR-003) is exactly half the 1-LSB step one unit cap makes
over the full swing under DR-008's single-side switching, so the `+0.5 LSB`
offset is set by a *reference ratio*, not by a sub-unit capacitor whose
ratio to `C_u` would be a matching liability. Lowering `TOP_N` by `0.5 LSB`
raises `TOP_P - TOP_N` by `+0.5 LSB`, which re-centres the quantizer:
captured code becomes `floor(Vd/LSB + 0.5) = round(Vd/LSB)`.

`HALF_LSB_EN = BUSY AND NOT(PH_B9)` (`xand_halflsb`, one `and2b_1`;
`HALF_LSB_ENN` from `xinv_halflsb`). The enable timing is load-bearing: the
offset cap stays at `VREFP` through the whole SAMPLE phase *and* through the
bit-9 trial, switching to `VCM` only at the `PH_B9 -> PH_B8` edge, a full
CLK period after the sampling switch opens. Gating on `BUSY` alone would
switch it on the very edge `SAMPLE_INT` falls on, racing the sampling
switch's own turn-off, and the injected charge would partly drain back into
the input source — a corner-dependent fraction of `0.5 LSB` instead of
`0.5 LSB`. (This is the same race DR-008's per-conversion-clear timing fix
had to avoid, in the opposite direction.) Applying the offset from PH_B8
rather than PH_B9 means the sign decision itself is taken on the un-offset
residual; that only shifts the result for `|Vd| < 1 LSB`, where both
branches land inside the ±1 LSB band regardless.

`Choff_p` + `Moff_p_refp` / `Moff_p_cmn` / `Moff_p_cmp` are the matching
dummy on the other side: identical cap and switch devices with every gate
tied off (`VGND`/`VPWR`), holding `BOT_OFF_P` at `VREFP` for the whole
conversion. They create no offset; they exist so both top plates carry the
same total capacitance and the same switch junction parasitics, i.e. so the
two sign branches have the same gain.

## Alternatives considered

- **Symmetric output buffering (an `inv_1` on each comparator output, with
  `COMP_OUT` taken from the `OUTN` inverter to preserve polarity)** instead
  of a dummy load. It balances by construction rather than by matching, and
  was the stronger candidate on that count. Not adopted: it puts a gate
  delay inside the comparator→register capture path and inverts `COMP_OUT`'s
  *reset-phase* value, so the decision path's post-capture-edge behaviour —
  the exact thing issue #257 had to fix once already — would change. The
  dummy load leaves the capture path bit-for-bit as verified and was
  measured to null the offset to below 0.2 LSB, so the extra robustness was
  not worth re-opening a settled timing question. If a later pass finds the
  dummy match insufficient (e.g. after layout parasitics), this is the
  fallback.
- **Deliberately skewing the output imbalance to cancel the offset** (i.e.
  trimming rather than balancing). Rejected: the offset it produces is
  common-mode dependent (measured: ~5 mV at 676 mV, >10 mV at 896 mV), so a
  fixed skew cannot cancel it across the conversion, let alone across
  corners.
- **Changing `ideal_code()` to a floor convention** so the uncorrected
  transfer function matches. Rejected outright as spec-relaxation: CLAUDE.md
  ("the spec is a gate", "agents do not relax a spec line to make a result
  pass"). The circuit is moved to the spec's convention, not the reverse.
- **Putting the half-LSB offset inside `design/cdac/cdac_array.sch`** — e.g.
  by making the existing per-side termination cap switchable, which would
  cost *no* added capacitance and would leave the array's absolute gain
  error 0.2 percentage points smaller than it is with the added cell.
  Rejected for this pass: it changes the array's port list, which
  invalidates `sim/cdac-array-transfer/`'s testbench and its committed
  record, and re-opens DR-005. Worth revisiting if the gain-error work in
  "Open items" touches the array anyway.
- **Fixing the gain error instead of adding the offset.** The gain error is
  the larger of the two remaining terms, but it cannot be fixed at this
  level at all (see "Open items"): it needs an array unit-cap sizing
  decision. The half-LSB offset is orthogonal to it and is worth having
  either way.

## Spec lines affected

None in `spec/target-spec.md` directly. `N = 10`, `V_REF`, and `LSB` are
unchanged; as with DR-008, this record makes the design's actual transfer
function consistent with those already-drafted numbers rather than changing
them. It does, however, make the case that an explicit **gain error** row —
absent from the table today — is needed before the `±1 LSB` absolute-code
criterion used by `sim/full-conversion-transient/` can be applied across the
whole input range (see "Open items").

## Consequences

- **Verified, controlled, and committed.** The decisive evidence is
  `sim/full-conversion-transient/records/20260912-011519-9aaf1ca.md`, a
  two-variant trace at `tt_27c_1.80v` and `tt_27c_1.62v`: the
  `as-committed` DUT and an `unbalanced-control` copy identical to it
  except that the two balancing dummy instances are deleted at
  deck-assembly time (testbench-only; never written back to `design/`,
  the same discipline `--mechanism-probe` already follows). Across the 30
  graded bit-trial decisions per corner:

  | variant | decisions disagreeing with the sign of the comparator's own input | smallest correctly-resolved input | captured codes (`-0.25` / `+0.00` / `+0.25 · V_REF`) |
  | --- | --- | --- | --- |
  | `as-committed` | **0 of 30** (both corners) | 0.80 / 0.77 LSB | 383 / 511 / 641 |
  | `unbalanced-control` | **4 of 30** (both corners) | 1.79 / 1.76 LSB | 384 / 515 / 643 |

  Every one of the control's 8 mismatches (4 per corner) is a decision of
  `1` on a *negative* input — the single direction an unloaded `OUTN`
  predicts, and the observation that rules out a settling or kickback
  explanation, which would not be signed. The residuals themselves are the
  same in both variants to within a few tenths of an LSB, so what changed
  is the comparator's decision, not the search's arithmetic. The control's
  captured codes also reproduce the pre-fix campaign record
  (`20260911-204111-a6df3bb.md`: 384 / 515 / 642-643), which closes the
  loop between the mechanism and the symptom.
- **Corner campaign**: `20260912-002315-9aaf1ca.md` (9 ratified corners,
  supersedes `20260911-204111-a6df3bb.md`). All three mid-scale inputs are
  now within ±1 LSB at 9/9 corners (`-0.25·V_REF` −1 LSB, `+0.00·V_REF`
  −1/0 LSB, `+0.25·V_REF` +1 LSB), up from one input per corner. The two
  near-full-scale inputs are bit-for-bit unchanged from the pre-fix
  record at all 9 corners — evidence that #265's defect is neither of
  this record's two mechanisms. The campaign's own overall verdict is
  still FAIL, on those two inputs alone.
- `design/sar_adc_top.sch` gains 4 standard cells (`mux2_1`, `xnor2_1`,
  `and2b_1`, `inv_1`), 2 MiM caps and 6 FETs; `design/sar_adc_top.spice` is
  regenerated (`design/regen_netlist.sh --check` clean). `PH_B9` is now a
  named net at the top level, which renumbers the netlister's anonymous
  `net1..net11` — a cosmetic diff in the regenerated netlist, not a
  connectivity change.
- The top level now contains analog devices of its own (the two offset
  cells) for the first time. That is a real cost: it makes
  `sar_adc_top.sch` a mixed schematic rather than a pure
  sub-block-plus-glue-logic integration, and it adds two small
  capacitor+switch structures that layout (#103) must place with the same
  care as an array bit, near the top plates, matched to each other. The
  alternative — a new sub-block schematic + symbol for a two-device cell —
  was judged more machinery than the cell is worth.
- Both top plates gain one unit cap of load (~+0.2% total capacitance per
  side), which makes the array's absolute gain error slightly *worse*
  (~0.8% → ~1.0%). The half-LSB re-centring more than pays for it at the
  inputs this record is verified against, but it is a real trade, not a free
  improvement, and it shrinks the margin discussed under "Open items".
- `sim/full-conversion-transient/`'s prior record is superseded by the new
  campaign this record cites. `sim/sar-sequencer-behavioral/` is unaffected
  (`design/sar_sequencer.sch` is untouched) and still passes.
  `sim/cdac-array-transfer/` is unaffected for the same reason DR-008 gave:
  that experiment drives the array's pins directly and never instantiates
  any top-level cell.
- `layout/sar-adc-top/`'s LVS reference artifacts drift further from the
  schematic. They were already stale (they predate issue #257's `CLKN` and
  DR-008's gating/recoding cells); re-deriving them is issue #103's, not
  this record's.
- The net `OUTN_NC` keeps its historical name despite no longer being a
  no-connect, to avoid churning those same layout artifacts. Named here so a
  reader is not misled.

## Open items

- **Array absolute gain error (~0.8–1.0%), NOT closed here.** The measured
  per-bit step is ~0.99 LSB, not 1.000 LSB: at `Vd = +0.25·V_REF` the DAC's
  ideal 128-unit subtraction leaves `+3.73 mV` (`+1.06 LSB`) of residual
  instead of zero. Cause: a top-plate-sampled CDAC divides its charge
  redistribution by the *total* capacitance on the top plate while the
  sampled input is not divided, so any top-plate parasitic is a direct gain
  error. Inverting the measurement gives a parasitic of ~4 unit caps
  (~30 fF) against the array's 512 `C_u` — and the comparator's own input
  gate area (`W = 4 µm`, `L = 0.5 µm` per side, DR-004) is the dominant
  identifiable contributor, with the bottom-plate-reference switches'
  junctions next. This is 0 LSB at mid-scale, ~1 LSB at `±0.25·V_REF` and
  ~3 LSB at `±0.78·V_REF`; it cannot be removed by any offset, and it cannot
  be removed at the integration level at all — correcting it needs either a
  larger array unit cap (DR-005/DR-003 Item 3, an area decision), a smaller
  comparator input pair (DR-004, a noise decision), or an explicit
  gain-error row in `spec/target-spec.md` that the `±1 LSB` absolute-code
  criterion is then read against. Owner: a future decision record; **filed
  as issue #269**, cross-referenced to #265 (the same parasitic contributes
  to the near-full-scale failure, but the two are separable and #269 is the
  residual that remains once #265 closes).
- **Near-full-scale (`±0.78·V_REF`) non-convergence** remains exactly as
  DR-008 left it — issue #265. The campaign this record cites shows those
  two inputs bit-for-bit unchanged by both fixes above, which is itself
  useful evidence: the near-full-scale defect is neither the comparator's
  output-load offset nor the quantizer's half-LSB alignment.
- **Post-layout re-verification of the dummy match.** The balance above is
  exact only to the extent the dummy cells' pin capacitance equals the real
  ones'. Routing parasitics on `COMP_OUT` and `OUTN_NC` are not in this
  netlist and will not match by default; layout (#103) must treat the two
  comparator output nets as a matched pair, and a post-extraction re-run of
  `sim/full-conversion-transient/` is the check.

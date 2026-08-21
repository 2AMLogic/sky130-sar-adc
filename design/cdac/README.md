# CDAC array — unit cell, array, dummy/termination (issue #53)

This directory holds the differential charge-redistribution CDAC array's
design source: the reusable unit cell, and the full binary-weighted array
built from it. See `spec/decision-records/DR-004-cdac-array-design.md` for
the design decisions this schematic implements (switching scheme, sizing,
divergence from `2AMLogic/gf180-sar-adc`'s MCS/Vcm scheme) and
`spec/decision-records/DR-003-numeric-spec-derivation.md` Item 3 for the
unit-capacitor sizing derivation this design consumes (provisional pending
issue #27's ratification — see "Status" below).

## Files

- `cdac_unit_cell.sch` — one bit position's storage element, shown standalone
  and annotated: a single `sky130_fd_pr__cap_mim_m3_1` unit capacitor whose
  bottom plate (`BOT`) is switched between `VREFP` and `VREFN` by a
  single-control-line CMOS pull-up/pull-down pair (`nfet_01v8` pulls to
  `VREFN` at `SEL=1`; `pfet_01v8` pulls to `VREFP` at `SEL=0` — both gated
  from the *same* net, since the two devices' opposite polarities already
  make them mutually exclusive; see the file's own header comment for the
  full truth table). This is **not** a conventional transmission gate — one
  control line suffices because a PMOS pull-up and an NMOS pull-down never
  conduct from the same gate level.
- `cdac_array.sch` — the full array: two structurally-identical sides (P, N),
  each a 9-bit binary-weighted sub-array (`cdac_unit_cell` pattern replicated
  per bit, weight `w=2^i` for `i=0..8` realized via the `MF` multiplicity
  parameter on `cap_mim_m3_1`) plus one non-switching termination unit per
  side. `TOP_P`/`TOP_N` are this array's two DAC output nodes (the future
  comparator's inputs); every other pin (`SELp0..SELp8`, `SELn0..SELn8`,
  `VREFP`, `VREFN`, `VDD`, `VSS`) is a control or power/reference input.

Both files open cleanly in the flow `docs/environment-setup.md` bootstraps
(`xschem -x -n -s -q --rcfile sim/xschemrc -o <dir> design/cdac/<file>.sch`);
neither references a `_g5v0d10v5` or other non-1.8V-core device flavor
anywhere (DR-001).

## Why "free MSB", 9-bit sub-array, weight-512 total

Per DR-003 Item 3, top-plate sampling gives this differential SAR ADC a
"free" MSB decision resolved directly from the sampled charge, with **no**
array switching at all — that decision (and the sampling front end that
makes it possible) is a different sub-block's scope (issue #53's own
"Dependencies: none" — this array does not require it to exist, and is
tested here without it). This array is therefore the **remaining 9-bit
sub-array**: weights `2^8..2^0` (256..1) sum to 511; a tenth, non-switching
**termination** unit (weight 1, bottom plate hard-wired to `VREFN`, no switch
device at all since it never toggles) brings each side's total to 512 unit
caps — matching DR-003 Item 3's `C_side ≈ 512·C_u ≈ 4.43 pF` derivation.

## Dummy/termination and matching strategy

**Termination (electrical).** Each side's tenth unit — same capacitor as
every other unit cell, `MF=1`, bottom plate wired directly to `VREFN`, no
switch — is what makes the side's total capacitance the power-of-two `512`
DR-003 sized against, rather than the `511` the nine binary-weighted bits
alone would sum to. It participates fully in the array's total capacitance
(and therefore in the kT/C noise floor and the sampling network's transfer
function) but never switches, so it contributes zero charge redistribution
of its own — exactly the standard binary-CDAC termination-cap role.

**Matching / etch-density dummy (structural, layout-stage).** This issue is
schematic-only (no `layout/` work here — see `layout/README.md` for that
flow once it starts); a true common-centroid *placement* is a layout-time
decision this schematic cannot realize yet. The strategy this design commits
to, to be executed when layout starts:

1. **Common-centroid placement is the default plan** for the 9-bit unit-cap
   array (the standard binary-CDAC matching technique — split each weighted
   bit's `MF` unit caps across a symmetric footprint, mirrored about the
   array's center, so linear process gradients (oxide thickness, etch bias)
   affect all codes' effective weight equally rather than biasing specific
   bits). This is a documented *plan*, not yet evidence — DR-004 names it as
   the default and flags the alternative below.
2. **The termination unit doubles as the array's outer etch-density guard**:
   because it is electrically inert with respect to code-dependent switching
   (its bottom plate never moves), it is the natural candidate for placement
   at the array's physical periphery in the eventual layout, buffering the
   active weighted units from edge-of-array etch/density gradients without
   needing a *second*, purely-decorative dummy structure. Whether this single
   termination unit is suficient guard-ring coverage on its own, or whether
   additional non-electrical fill/dummy capacitors are needed at the array's
   physical edges, is a layout-stage question this record does not close —
   see DR-004 "Open items".
3. **What this schematic does NOT claim**: instantiating `MF=w` on one
   `cap_mim_m3_1` symbol is a **netlist-level** shorthand for `w` parallel
   unit-cell instances (electrically identical to `w` separate placements for
   *total capacitance* purposes), not a statement about physical placement.
   A future Monte-Carlo mismatch campaign (issue #29) needs to confirm
   whether ngspice's `m`/`MF` multiplier draws `w` *independent* per-instance
   `AGAUSS()` mismatch terms or one term scaled by `w` — if the latter, MC
   evidence at this schematic's netlist would understate real array mismatch,
   and that campaign will need literal parallel unit-cell instances instead
   of `MF` scaling. Flagged here and in DR-004's "Open items"; not resolved
   by this issue.

## Status

**Provisional, not ratified.** `C_u`, `V_REF`, and every numeric row this
design consumes are DRAFT pending issue #27 (`spec/target-spec.md`). No spec
row is edited and no grant is recorded by this directory's contents (issue
#53's own acceptance criteria). The switching scheme and sizing choices are
recorded in `spec/decision-records/DR-004-cdac-array-design.md`.

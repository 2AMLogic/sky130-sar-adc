# DR-005: CDAC array design — switching scheme, unit-cell sizing, termination/matching strategy

- **Status**: proposed — this record ratifies nothing. Every numeric input it
  consumes (`V_REF`, the unit-cap sizing) is itself DRAFT pending issue #27;
  this record's own decisions (switching scheme, concrete transistor sizing,
  termination/matching strategy) are design choices for `design/cdac/`, not
  spec-table values, and carry the same "provisional" status until the spec
  rows they depend on are ratified.
- **Date**: 2026-08-21
- **Decided by**: Builder agent, issue #53
- **Supersedes**: none
- **Superseded by**: (none while this record stands)
- **Related**: #53 (this design), `spec/decision-records/DR-001-supply-flavor-scope.md`
  (ratified 1.8 V core rail this design locks to), `spec/decision-records/DR-003-numeric-spec-derivation.md`
  Item 3 (unit-cap sizing / kT-C-vs-matching-floor derivation this design
  consumes) and its "Open items" (which explicitly deferred the CDAC
  switching scheme to "a future DR when the CDAC design starts" — this
  record is that DR), `design/cdac/cdac_unit_cell.sch`, `design/cdac/cdac_array.sch`,
  `design/cdac/README.md`, `sim/cdac-array-transfer/` (the standalone
  transfer-characteristic testbench this design's own evidence run
  against), `CLAUDE.md` "Port parity" (the port-parity instruction this
  record's "Alternatives considered" section applies).

## Context

Issue #53 (T1 item 1, sub-block: differential CDAC array) is the first design
source this repo commits for the SAR ADC's charge-redistribution DAC. DR-003
already derived the numeric inputs this design needs (`V_REF = V_DD = 1.8 V`
recommended, `C_u ≈ 8.654 fF`, a 512-unit-cap-per-side array from top-plate
sampling's free MSB) but explicitly left the **CDAC switching scheme** open,
naming it as future work for "a future DR when the CDAC design starts"
(DR-003 "Open items"). This record makes that decision, plus the concrete
transistor sizing and the termination/matching strategy issue #53's own
acceptance criteria require to be recorded, not just implied.

**Port parity.** `CLAUDE.md` instructs aligning this repo's structure with
the ratified `2AMLogic/gf180-sar-adc` sibling. That repo's own CDAC
(`design/cdac/cdac_array.sch`, `spec/decision-records/DR-0011-cdac-switching-scheme.md`)
adopted an **MCS (Merged Capacitor Switching) / Vcm-based three-way scheme**:
each bit cell's bottom plate is releasable to a `Vcm` rail as well as to the
two supply rails, and switching happens in two phases (release-to-Vcm, then
engage-to-target-rail) specifically to reduce switching energy and to support
a top-plate-sampling front end that this repo's front-end sub-block has not
been designed yet (issue #53's own scoping: "without the sampling front end
... existing"). This record does **not** adopt that scheme verbatim for this
sub-block — see "Alternatives considered" for why, and why that is a
documented divergence rather than a silent one.

## Decision

1. **Switching scheme: conventional two-rail bottom-plate switching, not
   MCS/Vcm.** Each unit cell's bottom plate connects to exactly `VREFP` or
   `VREFN` via a single-control-line CMOS pull-up/pull-down pair (one NMOS,
   one PMOS, both gated from the same net `SEL` — see
   `design/cdac/cdac_unit_cell.sch`'s header for the truth table). There is
   no third `Vcm`-release state and no two-phase release/engage sequencing
   in the design source itself.
2. **Unit capacitor: `sky130_fd_pr__cap_mim_m3_1`, `W=L=1.8988` (µm, bare
   sky130_fd_pr xschem-template convention — see "Alternatives considered"
   for the `u`-suffix pitfall this avoids), `MF=1`** for the base unit,
   giving `C_u ≈ 8.654 fF` — DR-003 Item 3's recommended value, reproduced
   to 4 significant figures by the symbol's own `camimc`/`cpmimc`-consistent
   capacitance-estimate formula (verified: `2*1.8988² + 0.38*2*1.8988 =
   8.654 fF`, matching DR-003's `7.2112 + 1.4431 = 8.6544 fF` to within
   rounding). Bit `i` (`i=0..8`) scales this by `MF=2^i` — see
   `design/cdac/README.md` for what that multiplicity parameter does and
   does not claim about physical placement.
3. **Switch sizing: uniform across all bit positions**, `nfet_01v8
   W=1 L=0.15`, `pfet_01v8 W=2 L=0.15` (both minimum-length core devices; the
   2:1 W ratio is a standard planning-level mobility-ratio compensation, not
   a measured result). Not scaled per bit weight. This is a **deliberate
   simplification**, not an oversight: DR-003 Item 5 already left the sample
   rate / settling-time row underived ("needs a switch/CDAC settling deck …
   named as follow-on work"), so no settling budget exists yet to size
   switches against. Uniform sizing is the least-committal choice available
   until that budget exists; per-bit-weight switch sizing (larger MSB
   switches for faster settling, matching `2AMLogic/gf180-sar-adc`'s own
   practice in its `cdac-bit-settling` testbench) is named as follow-on work
   in "Open items", not decided here.
4. **Termination: one non-switching unit cap per side** (`MF=1`, bottom
   plate hard-wired to `VREFN`, no switch devices at all), bringing each
   side's total to the `512`-unit-cap total DR-003 Item 3 sized against. See
   `design/cdac/README.md` "Dummy/termination and matching strategy" for the
   full termination/matching-dummy strategy note issue #53's acceptance
   criteria require.
5. **Matching strategy: common-centroid placement, planned but not yet
   executed** (schematic-only issue; no `layout/` work here). Recorded as a
   commitment for the future layout stage, with the termination unit named
   as the default etch-density guard candidate — see `design/cdac/README.md`
   for the full note. This satisfies issue #53's "documented alternative"
   allowance: the strategy is documented now, even though it cannot be
   physically realized until layout exists.

## Alternatives considered

- **Adopting gf180-sar-adc's MCS/Vcm three-way switching scheme verbatim**
  (port-parity's stated preference). Rejected **for this sub-block**, not in
  general: MCS's release-to-Vcm phase exists specifically to interoperate
  with a top-plate-sampling *front end* (the release phase re-establishes
  the sampled reference state between bit trials) that issue #53 explicitly
  scopes out ("without the sampling front end … existing" is listed as a
  *feature* of this sub-block's independence, not a gap to route around).
  Building the release/engage machinery here would either (a) silently
  assume a front-end sampling protocol this repo has not designed yet, or
  (b) add a `Vcm` rail and two-phase control this array does not need to
  demonstrate its own transfer function. The **switching-energy reduction**
  MCS is chosen for in gf180-sar-adc is real and worth revisiting once this
  repo's own front end and SAR sequencer exist — named in "Open items", not
  foreclosed. This is a recorded, deliberate departure per `CLAUDE.md`'s
  "where sky130 forces a departure, record the divergence" instruction (the
  departure here is scope-forced by issue decomposition, not sky130-forced,
  but the same recording discipline applies).
- **Sizing switches proportionally to bit weight** (matching gf180-sar-adc's
  settling-driven sizing). Rejected for now — no settling budget exists yet
  in this repo to size against (DR-003 Item 5), so any per-bit sizing choice
  today would be an unfounded guess dressed as an engineering result. Named
  in "Open items" as the natural next step once a settling campaign exists.
- **Explicit `u`-suffixed device sizes in the xschem symbol templates**
  (`W=1.8988u` etc.), matching how a human might naturally write a micron
  value. Rejected after direct verification: sky130_fd_pr's own xschem
  templates (and this repo's already-committed `design/smoke_test.sch`) use
  **bare** numbers (`W=1`, `L=0.15`, no unit suffix), relying on the PDK's
  `.options scale=1e-6`. Appending an explicit `u` suffix on top of that
  double-scales the value (`u` × `scale=1e-6` = 1e-12), which was verified
  directly: an `ngspice` run against `sky130_fd_pr__nfet_01v8` with
  `L=0.15u W=1u` fails with `could not find a valid modelname` (the BSIM4
  bin-selection logic finds no valid bin at an effective `L` twelve orders
  of magnitude too small), while the identical device with `L=0.15 W=1`
  (bare) simulates correctly. This is recorded here so a future design
  source in this repo does not reintroduce the same bug.
- **Instantiating literal `512` separate unit-cell symbols per side** rather
  than `MF`-scaled instances. Rejected as impractical for a schematic-level
  first cut (`512×2 = 1024` cap instances plus `2×` that many switch
  transistors) with no matching-Monte-Carlo benefit at the schematic stage
  (mismatch modeling is issue #29's scope) — `MF` scaling is netlist-level
  identical for the *deterministic* transfer-characteristic claim this issue
  tests (`sim/cdac-array-transfer/`), and the open question of whether it is
  *statistically* identical for a future mismatch campaign is named, not
  silently assumed, in `design/cdac/README.md` and "Open items" below.

## Spec lines affected

None. This record changes no line of `spec/target-spec.md` — it is a design
decision for `design/cdac/`, consuming DR-003's still-provisional numbers
(`V_REF`, `C_u`) without altering them, per issue #53's own acceptance
criterion ("No spec row edited, no grant recorded").

## Consequences

1. **A concrete, simulatable CDAC array design source now exists**
   (`design/cdac/cdac_unit_cell.sch`, `design/cdac/cdac_array.sch`), and its
   own DAC transfer characteristic has been measured in isolation
   (`sim/cdac-array-transfer/`) across a 9-point PVT grid (process, temp,
   supply, one-at-a-time per `sim/README.md`): monotonic at the baseline
   corner, with the largest observed deviation from the ideal
   charge-redistribution value `≈ 16.6%` of one array code-step across the
   full grid run (`sim/cdac-array-transfer/records/`) — informational, not a
   pass/fail claim against any ratified spec row.
2. **The sampling-front-end sub-block inherits a concrete bottom-plate
   switch interface** (`SEL`/`SELp<i>`/`SELn<i>`, one control line per bit,
   no `Vcm`-release state) rather than an open question — but also inherits
   the responsibility of implementing its own sampling/reset mechanism
   externally, since this array provides none.
3. **The MCS/Vcm switching-energy question is deferred, not closed.** A
   future revision of this array (once the front end and SAR sequencer
   exist) may find MCS's switching-energy reduction worth adopting; this
   record's simpler two-rail scheme is not represented as final.
4. **Per-bit switch sizing and settling-time verification remain open**,
   inherited by the future settling campaign DR-003 Item 5 already named.
5. **The `MF`-scaling-vs-literal-unit-cell-replication mismatch-modeling
   question is now on record** (`design/cdac/README.md`), for issue #29 to
   resolve before trusting an `MF`-scaled Monte-Carlo mismatch result.

## Open items

- **MCS/Vcm adoption** — revisit once the sampling front end and SAR
  sequencer exist; not decided here (see "Alternatives considered").
- **Per-bit-weight switch sizing**, once a settling-time budget exists
  (DR-003 Item 5's own open item).
- **`MF` vs. literal parallel unit-cell instances for Monte-Carlo mismatch**
  — owner: issue #29 (or whichever issue runs the CDAC mismatch campaign).
- **Common-centroid layout execution** — owner: the future `layout/`
  sub-block for this array; this record only commits to the plan.
- **Whether the termination unit alone is sufficient etch-density guard
  coverage**, or additional non-electrical dummy fill is needed at the
  array's physical edges — owner: the same future layout sub-block.
- **Ratification of the numeric inputs this design consumes** (`V_REF`,
  `C_u`) — owner: issue #27, per DR-003.

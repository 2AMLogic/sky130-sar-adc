# DR-021: Resolve the near-full-scale common-mode droop with a common-mode-neutral (MCS/Vcm) CDAC switching scheme — not a wider-range comparator, not a reduced input range

- **Status**: proposed — a recommendation, not an implementation. This record
  ratifies no spec row and changes no number in `spec/target-spec.md`.
  Ratification is via the operator's approval of the PR resolving #267, per the
  ratification-via-PR standing policy the sibling records DR-011 / DR-018 /
  DR-019 / DR-020 cite (2AMLogic/2am#357). The recommendation is **conditional
  on one verification step named under "Open items"** (the follow-up must show
  the chosen scheme keeps the common mode near `VCM` in simulation before any
  prior record is declared superseded).
- **Date**: 2026-10-03
- **Decided by**: Builder agent, issue #267
- **Supersedes**: none. It closes the "Open items" entry of
  [DR-008](DR-008-cdac-top-level-switching-polarity.md) for the large-input
  defect, and discharges the "MCS/Vcm adoption" open item of
  [DR-005](DR-005-cdac-array-design.md). DR-004, DR-005 and DR-008 stand
  unedited here (they are superseded in part only if and when the follow-up
  implementation lands; see "Consequences").
- **Superseded by**: (none while this record stands)
- **Related**: #267 (this record's issue), #265 (the investigation that
  measured the mechanism), #263, #269 (CDAC absolute gain error: coordinate if
  the array's top-plate capacitance changes), `sim/full-conversion-transient/records/20260912-004251-bace13d.md`
  (the `--cm-trace` evidence this record rests on),
  `sim/full-conversion-transient/records/20261001-105439-c324f80.md` (most
  recent 9-corner campaign, showing the defect still present on main),
  [DR-004](DR-004-comparator-topology-and-noise-budget.md) (the ~23 mV nominal
  common-mode headroom margin, NMOS-input-pair StrongARM-class comparator),
  [DR-005](DR-005-cdac-array-design.md) (two-rail unit cell; MCS/Vcm deferred),
  [DR-008](DR-008-cdac-top-level-switching-polarity.md) (decision-directed
  single-side switching, the source of the frozen side),
  [DR-009](DR-009-comparator-output-load-balance-and-half-lsb-offset.md)
  (mid-scale residual), [DR-014](DR-014-comparator-kickback-mitigation-no-static-preamp.md),
  sibling `2AMLogic/gf180-sar-adc` DR-0011 (MCS/Vcm switching scheme).

## Context

Under DR-008's decision-directed single-side switching, one array side's
bottom plates never move during a conversion, so that side's top plate stays
at the value sampling left it at. The active side must travel to that frozen
value to converge, and the comparator's input common mode (the average of
`TOP_P`/`TOP_N`) therefore follows it away from `VCM`.

**Measured** (`sim/full-conversion-transient/records/20260912-004251-bace13d.md`,
`--cm-trace`, `Vd = ±0.78·V_REF`, ideal codes 113 and 911, 12 MHz):

| corner | frozen side | worst CM deviation from `VCM` | lowest `TOP_*` node |
|---|---|---|---|
| `tt_27c_1.62v` | `TOP_N` ~0.177 V (`+0.78`) / `TOP_P` ~0.177 V (`-0.78`) | `-693.5 mV` (conv. 5), `-600.1 mV` (conv. 1) | `0.0558 V` |
| `ff_27c_1.80v` | ~0.197 V | `-754.7 mV` (conv. 5), `-657.1 mV` (conv. 1) | `0.0936 V` |

These span the issue's "600-755 mV" figure and are roughly 26-33x DR-004's
23.1 mV nominal margin. The first wrong decision in conversion 1 occurs at
`PH_B8` with the common mode already `-402.1 mV` (`tt`) / `-446.7 mV` (`ff`)
from `VCM`. The defect is corner-invariant: the 2026-10-01 campaign
(`20261001-105439-c324f80.md`) still reads `+0.78·V_REF` as 1023 (+112 LSB)
at 9/9 corners and `-0.78·V_REF` off by 101-124 LSB.

**Derived from those numbers (arithmetic, not a new measurement):** the
frozen side sits at `VCM - |Vd|/2` (0.9 V - 0.702 V = 0.198 V for 0.78·V_REF,
matching the ~0.177-0.197 V traced), and the converged active side joins it,
so the common-mode excursion at convergence is `~|Vd|/2`. It scales with the
applied input, which is why it exists at `tt`/27 °C/nominal supply.

**Mid-scale residual ("Also worth a look" in #267).** Checked against main:
DR-009 (PR #270, "balance comparator output load and add a half-LSB
quantizer offset") **is on main** and DR-008's Open items already records the
2-3 LSB mid-scale residual as settled by it. The 2026-10-01 campaign
confirms it: `-0.25`, `0.00`, `+0.25·V_REF` read 383, 511, 641 against
ideal 384, 512, 640, i.e. all within the ±1 LSB band. The mid-scale residual
is therefore closed and is **not** attributed to this record's mechanism.
DR-009 deliberately did not close the ~1% absolute gain error (#269); that
stays separate.

Not verified here: the lowest-input value the comparator can still resolve
(the converging-range boundary). The only data are the five schedule points:
`±0.25·V_REF` converges (steady-state deviation by the `|Vd|/2` rule is
~225 mV, already ~10x DR-004's 23.1 mV figure, so that figure is not a hard
cliff) while `±0.78·V_REF` fails. The boundary lies somewhere between and
has not been swept.

## Decision

**Recommend option 1: a common-mode-neutral CDAC switching scheme, and
specifically adopt the MCS / `Vcm`-release scheme of the sibling
`2AMLogic/gf180-sar-adc` (its DR-0011), in differential mode.** In that
scheme the decided block's bottom plate steps `Vcm -> VREF` on one side while
its mirror steps `Vcm -> GND` on the other, each by a half swing. Both sides
move every trial, charge is balanced, and the comparator common mode stays
at `VCM` by construction rather than drifting with the input. The same
half-swing step gives a 1-LSB differential step at weight 1, which is the
condition whose absence (a native 2-LSB step under two-rail complementary
switching) forced DR-008 to abandon complementary switching for a decode
reason unrelated to common mode. Adopting MCS removes both the decode
mismatch and the frozen side.

This record **scopes the choice only**. The implementation (a third `Vcm`
rail and release state in `design/cdac/cdac_unit_cell.sch`, the matching
sequencer/top-level wiring that replaces DR-008's gating and `COMP_EFF`
recoding as needed, re-derived `sim/cdac-array-transfer/` and
`sim/full-conversion-transient/` records) is a follow-up issue and is
deliberately not done in the PR carrying this record.

Why this option:

1. **It removes the cause, not the symptom.** The excursion is generated by
   the frozen side. A scheme that keeps the pair balanced makes the
   `|Vd|/2` term, and so the 23.1 mV-margin question for large inputs,
   vanish. The other two options leave the excursion in place.
2. **Port parity.** gf180-sar-adc ratified exactly this scheme (its DR-0011:
   differential mode "common mode is constant at `V_cm` for the entire
   conversion"; sibling re-ratified it unchanged under its DR-0014 sampling
   move). DR-005 rejected it for this repo only on scope grounds
   ("scope-forced by issue decomposition, not sky130-forced") and named
   "MCS/Vcm adoption" as an open item to revisit once the front end and
   sequencer exist. They now exist; adopting it closes a recorded
   divergence.
3. **No spec row changes.** Input range, `N`, `V_REF` and LSB stay as
   ratified; this keeps the ENOB / INL-DNL DRAFT rows meaningful.

## Alternatives considered

- **Option 2: wider-common-mode-range comparator (add a PMOS input pair).**
  Rejected. (a) It treats the symptom: the common mode would still travel to
  ~0.06-0.19 V, and the traced `TOP_*` minima (`0.0558 V` tt, `0.0936 V` ff)
  are within ~0.1 V of ground, a region of sampled-node junction leakage
  and switch-off-leakage risk that no comparator change addresses. (b) It
  re-opens DR-004: noise budget (`<= 1.0148 mV rms` baseline), offset and
  regeneration data all re-qualify, while the kickback row is already unmet
  (`73.3673 mV` vs `<= 5 mV`, per `spec/target-spec.md`) and DR-014 declined
  a static preamp on headroom grounds. A second input pair adds input
  capacitance and kickback on the node the CDAC already loads. (c) Mismatch
  between the two pairs adds a common-mode-dependent offset term that would
  correlate with code, the failure mode the MCS comparison avoids. Cost of
  not choosing it: the comparator stays NMOS-only and thin on headroom, which
  Option 1 makes tolerable because the common mode no longer leaves `VCM`.
- **Option 3: documented reduced input range.** Rejected as primary, kept as
  the fallback. With `CM deviation ~ |Vd|/2`, holding DR-004's 23.1 mV
  margin literally would limit `|Vd|` to ~46 mV (~13 LSB, ~2.6% of
  `V_REF`), which is not a converter; the real limit is somewhere between
  `±0.25` and `±0.78·V_REF` and is unmeasured. For scale only: a range cut
  to ±0.3·V_REF at unchanged LSB costs `20·log10(0.3) = -10.5 dB` (~1.7 bit)
  of dynamic range, which against `spec/target-spec.md`'s composite
  behavioral ENOB estimate of `8.491` bit (mean-case) would land near 6.7 bit,
  below the `> 7.5` DRAFT target. That is arithmetic on a different
  experiment's estimate, not a measurement, but it shows option 3 would
  trade a fixable architecture defect for a missed ENOB row. It would also
  require superseding the input-range basis of the spec table by DR, which
  per `CLAUDE.md` is allowed only when a row proves unmeetable; it has not,
  because option 1 is untried. Supersession is only appropriate if the
  follow-up fails, and the table is DRAFT until issue #1 ratifies it, so no
  value is edited here.
- **Keep two-rail complementary switching and shrink the array so the native
  step is 1 LSB.** Not selected: it keeps the common mode neutral but needs
  a half-weight unit or a restructured array (changing the ratified 512
  positions/side and `C_u`, and interacting with #269 and DR-019), and
  diverges from the sibling instead of converging on it. Retained as the
  fallback within option 1 if MCS's third rail proves unworkable.

## Spec lines affected

None edited. `spec/target-spec.md` remains DRAFT pending issue #1. If the
follow-up lands, the "Sampling cap" row's array-size statement and the
architecture row stay as ratified; any change to array total capacitance is
tracked with #269. If option 1 fails and option 3 is taken, a new DR
supersedes the input range at that time.

Port-parity record: sky130 currently **diverges** from gf180 (two-rail cell,
DR-005; decision-directed single-side switching, DR-008). This record's
recommendation **converges** back to the sibling's MCS/Vcm scheme.
Divergence retained until the follow-up lands: gf180 later moved to
bottom-plate sampling (its DR-0014); this repo's front end samples on the
top plate and this record does not change that.

## Consequences

- Follow-up implementation must re-derive `sim/cdac-array-transfer/` and
  DR-005's switch-topology decision, rewrite or retire DR-008's single-side
  gating and `COMP_EFF` recoding, and re-run
  `sim/full-conversion-transient/run_conversion.py --corners --record`
  across the 9-corner grid, with `--cm-trace` at the `±0.78·V_REF` inputs as
  the acceptance evidence. Prior records are append-only and are not edited.
- A `Vcm` rail needs its own drive and decoupling (extra analog supply
  pin/budget, interacting with DR-012 / DR-017); the sibling carries a
  `vcm-drive-source` record (its DR-0026) for the same cost.
- Bad consequences: a unit-cell redesign (third state, more switch area and
  routing per bit), a larger change than DR-008's wiring fix, and a risk that
  top-plate parasitics (#269) shift once the unit cell changes. Switching
  energy improves rather than worsens per the sibling's comparison, but is
  not measured here.
- Does not address the comparator's thin static headroom (DR-004's 23.1 mV
  margin) at `VCM` itself, the slow/cold corner, or the unmet kickback row.

## Open items

- **Verification gate (blocks declaring DR-005/DR-008 superseded).** The
  follow-up must show, by `--cm-trace` at `±0.78·V_REF`, that the common-mode
  deviation stays well inside what the comparator resolves (the `±0.25·V_REF`
  points converge with a ~225 mV derived deviation, so the real tolerance is
  not 23.1 mV, but it is unmeasured) and that both inputs land within the
  ±1 LSB band at the 9 ratified corners.
- **Converging-range boundary sweep** of the current architecture (inputs
  between 0.25 and 0.78·V_REF): not run, needs a `klt sim` batch request,
  not local SPICE. Needed only if option 3 is ever invoked as a fallback.
- Follow-up implementation issue to be filed on ratification; coordinate with
  #269.

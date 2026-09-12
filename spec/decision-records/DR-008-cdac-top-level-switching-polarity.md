# DR-008: Top-level CDAC bottom-plate drive scheme — decision-directed single-side switching, not unconditional complementary drive

- **Status**: proposed — this record settles an integration-level wiring
  question (`design/sar_adc_top.sch`'s `SELp<i>`/`SELn<i>` generation), not a
  `spec/target-spec.md` numeric row. It inherits the same provisional status
  as every record still resting on DR-003's DRAFT numeric inputs.
- **Date**: 2026-09-11
- **Decided by**: Builder agent, issue #263
- **Supersedes**: none
- **Superseded by**: (none while this record stands)
- **Related**: #263 (this fix), #265 (confirms this record's own "Open
  items" leading hypothesis for the large-differential-input residual, with
  a targeted `TOP_P`/`TOP_N` node-level trace — see "Open items" below),
  #267 (the architecture-level follow-up #265's confirmed finding is filed
  into), #56
  (the top-level integration that first drew the `SELp<i>=DOUT<i>` /
  `SELn<i>=NOT(DOUT<i>)` wiring and explicitly flagged it as a "STATED,
  DOCUMENTED WIRING DECISION, not a verified-correct claim" pending a
  closed-loop conversion testbench),
  `spec/decision-records/DR-003-numeric-spec-derivation.md` Item 3 (the
  `2^(N-1)`-per-side free-MSB array-size derivation this record's switching
  scheme must stay compatible with) and its "Open items" (which deferred
  "the exact switching sequence" to "a future DR when the CDAC design
  starts"), `spec/decision-records/DR-004-comparator-topology-and-noise-
  budget.md` (the ~23 mV nominal common-mode headroom margin #265's trace
  measures a much larger, input-magnitude-driven violation of),
  `spec/decision-records/DR-005-cdac-array-design.md` (the CDAC
  *unit-cell* switch topology this record does NOT change — see "Decision"
  below), `design/sar_adc_top.sch`, `design/sar_sequencer.sch`,
  `sim/full-conversion-transient/` (the campaign this decision is verified
  against), `sim/cdac-array-transfer/` (the array's own step-size record
  this decision reconciles).

## Context

Issue #56 wired each CDAC bit's two switches unconditionally and
complementarily off the bit-register value: `SELp<i> = DOUT<i>`,
`SELn<i> = NOT(DOUT<i>)`, via a dedicated inverter per bit
(`xinv_seln0..8`). That header explicitly deferred verification: "no
closed-loop SAR conversion testbench had been run against this exact
top-level netlist... end-to-end functional/polarity verification was
explicitly deferred."

Issue #263's root-cause investigation (following #254/#257/#259/#262's
comparator-timing fixes) ran that closed-loop verification and found the
wiring does not survive it, for a structural reason independent of any
timing defect: driving both array sides unconditionally and
complementarily means every bit decision moves BOTH `BOT_p<i>` and
`BOT_n<i>` by one reference swing, in opposite directions. Per
`design/cdac/cdac_unit_cell.sch`'s truth table (`SEL=0 -> VREFP`,
`SEL=1 -> VREFN`), and confirmed independently by
`sim/cdac-array-transfer/`'s own transfer-characteristic record ("this
array's own ideal code-to-code step is 7.0312 mV = 2x the ratified ADC
LSB"), this makes the array's *native* per-bit step 2 LSB, not 1. Nine
binary bits at a 2-LSB-per-bit step already span the full `+-V_REF` input
range by themselves — the bipolar array already encodes the sign — which
means DOUT9 (this design's "free" MSB per DR-003 Item 3, resolved directly
off the sampled top-plate residual with no CDAC switching of its own)
cannot be reconciled with the committed straight-binary decode
(`code = sum(DOUT_i * 2^i)`, `i=0..9`, `LSB = 2*V_REF/2^N`): the ideal
codes for e.g. `+-0.78*V_REF` are not reachable as a "sign bit + 9-bit
magnitude" pair when every magnitude bit is worth 2 LSB instead of 1. This
is a decode mismatch, not a settling or corner-margin defect — no amount
of timing tuning closes it.

## Decision

**Decision-directed, single-side bottom-plate switching**, gated by DOUT9
(the free sign bit, decided first, with no CDAC switching of its own — see
DR-003 Item 3):

```
SELp<i> = DOUT9  AND DOUT<i>      (i = 0..8)
SELn<i> = DOUT9N AND DOUT<i>       (DOUT9N = NOT(DOUT9), one added inverter)
```

At the shared baseline (`DOUT<i>=0`, which every magnitude bit is forced to
at the start of every conversion by #263's per-conversion CDAC clear in
`design/sar_sequencer.sch`) both expressions evaluate to 0 regardless of
DOUT9, so `BOT_p<i> = BOT_n<i> = VREFP` — a sign-independent zero state.
When DOUT9=1 (Vd >= 0) only `SELp<i>` can ever assert, so only `BOT_p<i>`
moves (toward VREFN) as magnitude bits are decided; `BOT_n<i>` stays pinned
at VREFP. When DOUT9=0 (Vd < 0) the symmetric case holds with the sides
swapped. Exactly one plate moves per bit decision, halving the array's
native step to 1 LSB/bit, matching the `w_i = 2^i` weights
`sim/full-conversion-transient/gen_full_conversion_tb.py`'s `ideal_code()`
already assumes for the ratified `N=10` offset-binary code.

This is a **top-level integration decision** (`design/sar_adc_top.sch`'s
`SELp<i>`/`SELn<i>` generation), not a change to the CDAC array's own
per-unit-cell switch topology: `design/cdac/cdac_unit_cell.sch`'s
single-control-line CMOS pull-up/pull-down pair and its `SEL` truth table
are untouched, so DR-005's Decision item 1 ("conventional two-rail
bottom-plate switching, not MCS/Vcm") stands exactly as ratified there.
DR-005 decided what each unit cell's *own* switch does when driven; this
record decides what top-level signal drives it and when.

A fixed-polarity comparator (`VINP-VINN > 0 => COMP_OUT=1`, unconditional)
cannot directly capture the correct "keep this trial" decision for both
sign branches under single-side switching: for the DOUT9=1 branch, keeping
a trial (a subtraction) is correct when the post-trial residual is still
`>= 0`, i.e. `COMP_OUT=1` — the comparator's natural polarity already means
"keep". For the DOUT9=0 branch, keeping a trial (an addition, moving the
negative residual toward zero) is correct when the post-trial residual is
still `< 0`, i.e. `COMP_OUT=0` — the *opposite* of the comparator's natural
polarity. `design/sar_sequencer.sch` therefore derives
`COMP_EFF = XNOR(COMP_OUT, DOUT9)` and feeds `COMP_EFF` (not raw
`COMP_OUT`) to bits 8..0's capture mux; bit 9's own mux is untouched (the
sign decision needs no correction — it IS the branch selector). Capturing
raw `COMP_OUT` for the DOUT9=0 branch turns that branch's search into
positive feedback; `sim/sar-sequencer-behavioral/`'s updated stimulus
verifies the `COMP_EFF` correction in isolation (a purely digital,
ideal-`COMP_OUT`-driven testbench, decoupled from CDAC/comparator analog
settling) and passes for both a DOUT9=1 and a DOUT9=0 target code.

## Alternatives considered

- **Keep unconditional complementary switching; redefine `ideal_code()`
  instead.** Rejected: Root cause above shows the reachable-code set under
  a 2-LSB/bit native step cannot represent every ratified `N=10`
  offset-binary code (e.g. `+-0.78*V_REF`'s ideal codes are unreachable as
  any sign+magnitude pairing of this array's own bits). Any redefinition
  would either lose resolution (fewer than `N=10` effective bits) or
  require re-deriving the whole numeric spec table DR-003 already ratified
  through issue #27 — a spec change with no forcing evidence that the
  *array itself* cannot deliver `N=10`, only that this particular top-level
  drive polarity cannot.
- **MCS/Vcm-style release-to-common-mode switching.** Already rejected at
  the array level by DR-005 for this sub-block's own reasons (no `Vcm` rail
  or two-phase control in `design/cdac/cdac_unit_cell.sch`); adopting it
  now at the top level would mean re-opening a settled, unrelated decision
  to solve a problem (2x-per-bit step) that plain gating already solves.
- **Correct the polarity mismatch with an analog input swap** (mux
  `TOP_P`/`TOP_N` into the comparator based on DOUT9, instead of an XNOR on
  its digital output) rather than `COMP_EFF`. Not adopted: it would touch
  an already-verified analog block (`design/comparator.sch` or its top-level
  wiring) with an analog switch, a larger and less-isolable change than one
  digital `xnor2_1` gate, for no verification benefit `COMP_EFF` does not
  already provide.

## Spec lines affected

None in `spec/target-spec.md` directly — `N=10`, `V_REF`, and `LSB` are
unchanged; this record is what makes the design's actual decode consistent
with those already-ratified numbers, not a change to them.

## Consequences

- `design/sar_adc_top.sch`'s `xinv_seln0..8` inverters are replaced by
  `xand_seln0..8` / `xand_selp0..8` (18 `sky130_fd_sc_hd__and2_1` instances)
  plus one `xinv_dout9n` inverter and nine `xxor_code0..8`
  (`sky130_fd_sc_hd__xor2_1`) output-recoding gates (see "Correction"
  below); `design/sar_sequencer.sch` gains one `xnor2_1` instance
  (`COMP_EFF`) and rewires bits 8..0's capture mux input from `COMP_OUT`
  to `COMP_EFF` (bit 9's mux is untouched), plus the `BUSY_BITS`
  clear-gating signal (one `or2_1` + one `or3_1`, issue #263's
  per-conversion-clear timing fix — see that issue's own PR for why
  gating the clear on `BUSY` rather than a `PH_EOC`-excluding signal
  raced the sampling switch's own opening).
- `sim/full-conversion-transient/` and `sim/sar-sequencer-behavioral/`'s
  committed records and (for the latter) stimulus are superseded/updated by
  this issue in the same pass — see those experiments' own newest records
  for the post-fix numbers.
- `sim/cdac-array-transfer/`'s own record (the array's *isolated* transfer
  function, exercised directly with its own `SELp`/`SELn` stimulus, not
  through `sar_adc_top.sch`) is unaffected: that experiment drives the
  array's pins directly and never instantiates this record's top-level
  gating logic, so its "2x the ratified LSB" step-size finding remains an
  accurate description of the *array's own* unconditional-drive transfer
  function — it is simply no longer how the array is driven once integrated
  under `sar_adc_top.sch`. A future pass may want a second
  `cdac-array-transfer`-style record exercising the array under
  decision-directed stimulus for direct comparison; not done here (the
  full-conversion campaign already exercises it in situ).

## Correction (issue #263, same pass): output recoding stage added

The first re-run of `sim/full-conversion-transient/` against this record's
switching scheme (trial perturbation + per-conversion clear both landing
correctly) still showed a large, corner-invariant error for every negative
(`DOUT9=0`) input — e.g. `-0.25*V_REF`'s ideal code 384 read back as 127.
Root cause: `DOUT<i>` (`i=0..8`) read directly is **not** the ratified
offset-binary code for that branch. The search's own keep/revert decisions
necessarily track `|residual|` (a single active plate always moves TOWARD
zero from that branch's own starting point), so `DOUT8..0` is a
**sign+true-magnitude** value, not offset binary — the two conventions
coincide for `DOUT9=1` (true magnitude *is* the offset-binary magnitude
field there) but not for `DOUT9=0` (the ratified offset-binary magnitude
there is `512 - true_magnitude`, not `true_magnitude`).

Fix: a read-only recoding stage, `design/sar_adc_top.sch`'s
`ADCOUT<i> = DOUT<i> XOR DOUT9N` (`i=0..8`, nine added
`sky130_fd_sc_hd__xor2_1` instances, `xxor_code0..8`). Passthrough when
`DOUT9=1` (already correct); bitwise-complement when `DOUT9=0`
(`511 - true_magnitude`, off from the exact ratified value
`512 - true_magnitude` by at most 1 LSB — the ones'-complement-vs-512
rounding gap, within the ±1 LSB acceptance tolerance). This does **not**
feed back into `SELp`/`SELn` — `DOUT<i>` remains the internal search
register the array/comparator loop actually operates on; `ADCOUT<i>` is
the final, user-facing code, exactly the role a two's-complement/
offset-binary output converter plays in many real SAR ADCs.
`sim/full-conversion-transient/gen_full_conversion_tb.py` now reads
`ADCOUT8..0` (bit 9: `DOUT9` directly) for the captured code. Empirically:
`-0.25*V_REF` now reads back exactly 384 (0 LSB error) at all 9 corners.

## Open items

- **Large-differential-input (`±0.78·V_REF`) convergence — CONFIRMED (issue
  #265).** Even with the correction above, the two near-full-scale inputs in
  `sim/full-conversion-transient/`'s own schedule fail badly and
  corner-invariantly (worst |error| 71–124 LSB for `-0.78·V_REF`, a
  corner-invariant 112 LSB — captured code pinned at 1023, the all-ones
  saturation value — for `+0.78·V_REF`, at all 9 ratified corners; see
  issue #263's newest `sim/full-conversion-transient/` record). Corner
  invariance again points at a structural, not marginal-settling, effect.
  `sim/cdac-array-transfer/`'s own record shows the array itself is
  monotonic and correctly polarized at its own code 511 in isolation, so
  the defect is specific to the full mixed-signal loop, not the array's
  own transfer function.

  Issue #265's `sim/full-conversion-transient/run_conversion.py --cm-trace`
  (a targeted `TOP_P`/`TOP_N` node-level trace at conversions 1/5, the
  `±0.78·V_REF` inputs themselves) **confirms** the leading hypothesis named
  in this record's prior revision, and finds the mechanism larger than this
  record's own ~23 mV-margin framing suggested: decision-directed
  single-side switching gates one array side's `SEL*<i>` to 0 for the
  *whole* conversion, so that side's top plate — with no other charge path
  once the sampling switch has opened — stays frozen at whatever the
  sampling phase left it at, while the active side must travel all the way
  to the frozen side's own sampled value to converge. For a near-full-scale
  input the frozen side sits near a rail (measured: `TOP_N` pinned at
  ~0.20 V for the whole `+0.78·V_REF` conversion), so the pair's common
  mode droops from `VCM` toward that near-rail value along with it —
  measured worst-case droop **600–755 mV** at both traced corners
  (`sim/full-conversion-transient/records/20260912-004251-bace13d.md`),
  roughly 30× DR-004's own ~23 mV margin figure. This is an
  input-magnitude-driven effect (present even at `tt`/27 °C/nominal supply),
  not a PVT-margin one, and the captured code diverges from the ideal code
  at exactly the bit trial where the droop first flips the comparator's
  decision (confirmed directly in the trace's per-phase data).

  **Not fixed by issue #265** — that record's own recommendation names the
  fix as an architecture-level tradeoff among (1) a common-mode-neutral CDAC
  switching scheme (would require a CDAC unit-cell redesign per DR-005,
  which has no third/`VCM` rail to release onto), (2) a wider-common-mode
  comparator (would require re-qualifying DR-004's noise/offset
  characterization against a new topology), or (3) a documented, reduced
  dynamic range via a new decision record superseding
  `spec/target-spec.md`'s input-range row (CLAUDE.md: "a row that proves
  unmeetable is superseded by a new decision record, never silently
  loosened"). Choosing among these is filed as issue #267 rather than
  attempted in issue #265's own diagnostic-only scope.
- **A smaller, secondary residual**: the two moderate/mid-scale inputs that
  do NOT hit the large-signal defect (`+0.00·V_REF`, `+0.25·V_REF`) still
  read back consistently 2–3 LSB high (not within the ±1 LSB tolerance
  either, though far closer than the large-signal cases) at every corner —
  worth a future, smaller investigation, not blocking, and plausibly a
  distinct, easier-to-close residual from the large-signal one above.
- **A second, decision-directed-stimulus `sim/cdac-array-transfer/` record**
  for direct before/after comparison — owner: future work, not blocking
  (see "Consequences" above).

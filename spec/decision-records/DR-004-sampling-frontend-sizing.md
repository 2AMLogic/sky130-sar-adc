# DR-004: Sampling front-end provisional sizing (Cboot, Csamp, VCM, Sa/Sd length)

- **Status**: proposed -- this record ratifies nothing. Every numeric input it
  draws from DR-003 is itself `proposed`, pending #27's operator ratification;
  this record's own sizing choices are provisional on top of that, pending the
  same act plus the follow-on work named in "Open items" below.
- **Date**: 2026-08-21
- **Decided by**: Builder agent, issue #52
- **Supersedes**: none
- **Superseded by**: (none while this record stands)
- **Related**: #52 (this sub-block), #61 (follow-up: post-edge hold-transition
  droop -- root-caused and resolved for the real integrated ADC, see "Update
  (issue #61)" below), #53 (CDAC array, consumes `Csamp`'s placeholder
  role), #55 (SAR clock/phase generation -- #61's finding turned out not to
  require a design change there, see "Update (issue #61)"), #95 (resolved
  the `BPREF_x`-hand-off assumption in "Open items" below as false, not just
  premature -- see "Update (issue #95)"),
  `spec/decision-records/DR-001-supply-flavor-scope.md` (ratified 1.8V
  core-device scope this record's every instance stays inside),
  `spec/decision-records/DR-003-numeric-spec-derivation.md` (provisional
  `V_REF`/LSB/`C_side` numbers this record's sizing is derived from),
  `design/sampling_frontend.sch`, `sim/sampling-frontend/run_transient.py`,
  `sim/sampling-frontend/records/20260821-072657-433a294.md` (the evidence
  record this decision record explains), `sim/sampling-cdac-handoff/
  records/20260824-231304-144edeb.md` (#95's own evidence record),
  `sim/sampling-frontend/run_hold_kick.py` and its
  `sim/sampling-frontend/records/20260825-021113-a237c79.md` (#61's own
  root-cause/resolution evidence record)

## Context

#52 needed a sampling front-end schematic and a standalone testbench, with any
DRAFT-spec-dependent sizing recorded here rather than asserted. Three sizing
choices in `design/sampling_frontend.sch` rest on DR-003's still-`proposed`
numbers (pending #27):

- **`VCM = 0.9V`** -- DR-003 Item 1's recommended `V_REF/2` at
  `V_REF = V_DD = 1.8V`.
- **`Csamp_{p,n}`** (the lumped placeholder standing in for the not-yet-drawn
  CDAC array's `C_side`, sized `W=46.9um L=46.9um` on
  `sky130_fd_pr__cap_mim_m3_1`) -- DR-003 Item 3's provisional
  `C_side ~= 4.43 pF` recommendation. This is **not** a claim about the
  future CDAC's actual unit-cell/array structure (#53's scope); it exists
  only so this sub-block's testbench has a realistic total sampling
  capacitance to settle into.
- **`Cboot_{p,n}`** (`W=9.8um L=9.8um`, same cap primitive, ~188 fF by the
  same density) -- sized empirically in this record's own derivation below,
  not ported from DR-003 (DR-003 does not size a bootstrap cap; that is this
  sub-block's own design work).

A fourth choice -- **`Sa`/`Sd`'s channel length (`L`)** -- started as a
minimum-length (`L=0.15um`) device, matching every other switch in the
schematic, and was found during this record's own verification to be a real
sizing bug, not a DRAFT-spec dependency. It is documented here anyway because
fixing it is inseparable from characterizing the front end.

**What is verified, and against what.** Every number below comes from an
actual ngspice transient simulation against the installed sky130A PDK
(`open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b`, `sim/pdk.json`'s pin),
driven by `sim/sampling-frontend/run_transient.py` and its diagnostic
variants (netlisted from `design/sampling_frontend.sch` via xschem, not
hand-written) -- reproducible by re-running that script, not asserted from
hand analysis. Every device instance in the schematic is
`nfet_01v8`/`pfet_01v8` (ratified, DR-001) or the `cap_mim_m3_1` MiM
capacitor; zero `_g5v0d10v5` instances (verified by grepping the regenerated
netlist fragment, `sim/sampling-frontend/testbench/sampling_frontend_dut.spice`).

## Decision

### 1. `VCM = 0.9V`, `Csamp_{p,n}` sized to DR-003's provisional `C_side`

Adopted as stated above -- these are direct, unmodified transcriptions of
DR-003 Item 1 / Item 3's recommendations into this sub-block's testbench and
schematic, provisional in exactly the same way DR-003 itself is provisional
(pending #27). No independent re-derivation was needed or performed.

### 2. `Cboot_{p,n} = 188 fF` (`W=9.8um x L=9.8um`, `cap_mim_m3_1`)

Sized so `Cboot` is comfortably larger than the parasitic capacitance at the
`BOOST_x`/`G_x` nodes (the gate capacitance of `Msw_x`, `W=2um L=0.15um`,
plus the junction/overlap capacitance of `Sa`/`Se`/`Sd`), so that Cboot's
charge-conservation bootstrap ratio (`BOOST_x` rising by approximately `VIN`
as `BSBOT_x` jumps from `0` to `VIN`) is not badly degraded by charge sharing
with those smaller parasitics. No formal parasitic extraction was performed
(no layout exists yet, #52's scope is schematic-only); this is a
conservative, order-of-magnitude sizing choice, verified functionally by the
in-sample settling result below rather than by a parasitic-capacitance
calculation.

### 3. `Sa`/`Sd` channel length: `L=0.15um` (as-drawn) is a real sizing bug; `L=0.5um` fixes it

**This was found, not assumed.** The schematic originally drawn for #52
(before this record) used minimum length (`L=0.15um`, matching every other
switch) for `Sa_{p,n}` (the PFET that precharges `BOOST_x` to `VDD` during
hold) and `Sd_{p,n}` (the NFET that pulls `G_x` to `GND` during hold). Both
devices must be solidly OFF while `SAMPLE=1` (sampling phase) so the boosted
`BOOST_x`/`G_x` nodes can float freely; at `L=0.15um` their off-state
subthreshold leakage was large enough to measurably droop the boosted node
over the sample window.

**Diagnosis.** Running the testbench at the `worst_case_pp` point
(`VINP=1.6V`, near the rail, the point with the least bootstrap headroom to
spare) with a long transient (`SAMPLE` held asserted for 19us instead of the
normal 400ns) showed `TOP_P` asymptoting to `~1.514V`, not `1.6V` -- a
persistent ~86mV steady-state gap, not merely slow settling (confirmed by
comparing `TOP_P` at 1us/2us/5us/10us/15us/19us: it flattens well before
19us). `BOOST_P`/`G_P` similarly asymptoted to `~2.03V` instead of an ideal
`~3.4V` (`VIN+VDD`). At the schematic's normal 400ns sample window, this
produced a 120mV settling error at `worst_case_pp` (`TOP_P=1.479V` vs. the
`1.6V` input) -- large enough that an earlier draft of this record's own
evidence-generation script would have printed a false "settles within
simulation resolution" claim had it not been caught here.

**Fix and verification.** Lengthening `Sa_{p,n}`/`Sd_{p,n}` from `L=0.15um`
to `L=0.5um` (holding `W=1um` unchanged) resolves it: the same long-transient
check now asymptotes `TOP_P` to `1.60000V` (exact, to simulation resolution)
within 1us, and at the normal 400ns sample window every test point settles to
within sub-mV of its analog input (see the "Result" section of
`sim/sampling-frontend/records/20260821-072657-433a294.md`). `L=0.5um` was
not tuned further (e.g. to find a minimum sufficient length) -- it is a
conservative value confirmed to work, not an optimized one; a future revision
may narrow it once a layout-area budget exists.

**Root cause, as far as diagnosed.** Sub-threshold leakage current through
`Sa`/`Sd` while nominally OFF (gate-source `Vgs=0` by design, but a short
channel at minimum length has materially higher off-state leakage than a
longer one) provides a slow discharge path off the high-impedance boosted
node, which the bootstrap has no restoring mechanism to fight during the
sample window. This was not verified against per-device leakage-current
measurements (e.g. `i(Xname)` probes did not resolve cleanly against these
subcircuit models in this ngspice version) -- the L-length fix was verified
functionally (does `TOP_x` settle correctly), not by isolating and
quantifying the leakage current itself.

### 4. Every device instance is a ratified flavour; zero `_g5v0d10v5`

Confirmed by regenerating the netlist fragment from the (post-fix) schematic
and grepping for `g5v0d10v5`: zero matches. This satisfies #52's AC #3 and
confirms the DR-002 tripwire (`spec/target-spec.md`) is not triggered by this
sub-block.

## Alternatives considered

- **Leaving `Sa`/`Sd` at minimum length and accepting the settling error as a
  "known limitation."** Rejected -- a 120mV settling error at the sample-window
  boundary (34x the provisional LSB) is not a minor non-ideality worth
  waiving; it would have made every downstream measurement (including the
  hold-transition characterization below) meaningless, since the front end
  would not even be correctly sampling its input in the first place. The fix
  is cheap (a channel-length change, no topology change) and fully verified.
- **Root-causing the leakage down to a specific BSIM4 parameter/mechanism
  before fixing it.** Rejected as disproportionate to this sub-block's scope
  -- the functional fix (longer `L`) is standard practice for a
  leakage-sensitive off-state device and was verified to work; a deeper
  device-physics root-cause would not change the recommended fix, only take
  longer to arrive at it.
- **Also root-causing and fixing the post-edge hold-transition droop (Open
  items below) within this record.** Rejected -- see Open items: the
  diagnostic work performed ruled out the first (dead-time) hypothesis but did
  not converge on a confirmed mechanism or fix, and this sub-block's own
  scope (per #52) does not require the front end's *hold* behavior to be
  clean, only that it be exercised and reported. Filed as issue #61 instead
  of guessed at here.

## Spec lines affected

None. This record does not read or write any row of `spec/target-spec.md`
directly -- it transcribes DR-003's still-`proposed` `V_REF`/`C_side`
recommendations into this sub-block's own schematic/testbench sizing, and
documents two sizing choices (`Cboot`, `Sa`/`Sd` length) that DR-003 does not
cover at all. No grant is recorded by this record or by #52.

## Consequences

1. **#52's schematic settles correctly** (sub-mV, every tested point) once
   the `Sa`/`Sd` fix is applied -- the sub-block's in-sample sampling
   behavior is now a verified, not merely asserted, result.
2. **A new, more severe, and not-yet-closed problem was surfaced in the
   process**: the post-edge (SAMPLE-to-HOLD transition) behavior shows a
   large droop, described in full under "Open items" and tracked in #61.
   Fixing the settling bug did not fix this -- it was independently found
   while re-verifying settling with the fix applied, and remains unresolved.
3. **#53 (CDAC array)** inherits `Csamp`'s placeholder role explicitly, not
   implicitly -- when #53 draws the real array, this sub-block's `Csamp_{p,n}`
   should be understood as "what #53 replaces," not as a claim about the
   array's own structure.
4. **#55 (SAR clock/phase generation)** inherits a concrete, quantified
   requirement from #61's findings (a non-overlap margin alone, even up to
   10ns, did not fully suppress the transition-edge droop measured here) --
   #55 should not assume "add dead time" is sufficient without re-checking
   against this record's numbers.
5. **This sub-block's front end is not yet ready for #28/#29's corner/Monte
   Carlo evidence campaigns** -- #61 must be resolved, or the residual
   quantified against a ratified spec row, first; running a full PVT/MC sweep
   against a front end with an unexplained several-hundred-mV droop would not
   produce a meaningful result.

## Open items

- **The post-edge hold-transition droop (#61).** By ~8ns after the SAMPLE
  falling edge, `TOP_P`/`TOP_N` have moved 337-552 mV single-ended (see
  `sim/sampling-frontend/records/20260821-072657-433a294.md`'s "Test points"
  table) from their correctly-settled in-sample value -- roughly two orders
  of magnitude above the provisional differential LSB (3.5156 mV, DR-003 Item
  2). Diagnostic work performed while drafting this record:
  - **Break-before-make hypothesis, partially ruled out.** The schematic's
    on-die `SAMPLEB` generation (`Invp`/`Invn`, a single inverter, zero dead
    time -- a deliberate simplification, full non-overlap clock generation
    deferred to #55) was suspected to cause a crossover short as `SAMPLE`
    and `SAMPLEB` transition through mid-supply simultaneously. A
    testbench-only diagnostic (schematic unmodified) drove `SAMPLE`/`SAMPLEB`
    from independent sources with an explicit dead time instead of the
    on-die inverter: 2ns of dead time reduced the `worst_case_pp` `TOP_P`
    delta from ~552mV (as-drawn, zero dead time) to ~315mV; 10ns of dead time
    gave ~272mV -- shrinking, but **not vanishing, and not continuing to
    shrink much further between 2ns and 10ns**. Dead time alone is therefore
    not a sufficient fix.
  - **Charge-conservation observation.** Across the transition, the
    differential voltage `TOP_x - BPREF_x` stays essentially constant (e.g.
    `0.698V` immediately before and 19ns after the edge, in one probe run),
    while both nodes shift together by nearly the same amount. This points at
    a **common-mode capacitive kick** onto the floating `TOP_x`/`BPREF_x`
    node pair (both are deliberately left floating during hold in this
    sub-block -- see "Update (issue #95)" below: this floating state is now
    known to be **permanent**, not a temporary gap awaiting a future
    CDAC hand-off) from the switching `SAMPLE`/`SAMPLEB` control signals --
    most plausibly via the gate-overlap / off-state junction capacitance of
    the several devices gated by those signals with a terminal on
    `TOP_x`/`BPREF_x`/`BOOST_x`/`G_x`. This was **not** confirmed by directly
    summing/measuring those parasitic capacitances -- it is the leading
    hypothesis from the two experiments above, not a closed root cause.
  - **Not (fully) an artifact of the isolated testbench's longer float
    window.** This bullet originally assumed "the real ADC's CDAC (#53)
    would take over `BPREF_x` almost immediately after sampling ends" --
    issue #95 found that assumption **false**: the real CDAC array (#53) has
    no combined bottom-plate node to hand off to at all, and
    `design/sar_adc_top.sch` (#56) leaves `BPREF_P`/`BPREF_N` on dead-end
    nets permanently, not just for the remainder of this isolated
    testbench's longer hold window. This does not change this bullet's own
    conclusion, only its premise: the observed jump happens within the first
    few ns of the falling edge regardless of whether or when any hand-off
    was ever coming, so the (now known to be nonexistent) hand-off was never
    going to prevent the corruption either way.
  - Full writeup, suggested next steps, and cross-references: issue #61.
    **Not resolved by #95**: #61's droop finding is about this sub-block's
    own isolated-testbench dynamics in the first few ns after the `SAMPLE`
    edge (a capacitive-kick hypothesis, not yet root-caused) and is
    independent of the bottom-plate-reference question #95 resolved -- see
    "Update (issue #95)" below for the explicit position on this overlap.
- **`Cboot` sizing was not swept or optimized** -- `188 fF` (`W=9.8 x L=9.8um`)
  was chosen to be comfortably larger than estimated parasitics and confirmed
  functional; no sensitivity sweep (smaller/larger `Cboot`) was run to find a
  minimum sufficient value or characterize headroom margin.
- **`Sa`/`Sd`'s `L=0.5um` fix was not corner-swept.** The functional
  verification above is `tt`/`27C` only; whether `L=0.5um` remains sufficient
  at the `ss`/`-40C` corner (where subthreshold leakage behaves differently)
  is not checked here and is deferred to #28's future full corner campaign.
- **Ratification itself.** Every DR-003 number this record transcribes
  remains unratified pending #27; nothing in this record is binding until
  that closes, and until #52's own sizing choices here (`Cboot`, the `Sa`/`Sd`
  length) are independently reviewed.
- **New (issue #95): `ss`-corner settling headroom, once the real CDAC array
  is wired in, is unchecked and appears insufficient.**
  `sim/sampling-cdac-handoff/records/20260824-231304-144edeb.md` (the
  evidence record for #95's resolution) loads `TOP_P`/`TOP_N` with BOTH this
  sub-block's own `Csamp_p`/`Csamp_n` (~4.43pF/side, this record's own
  placeholder) AND the real CDAC array's (#53) own ~4.43pF/side of bit
  capacitors -- roughly double the load this record's `Sa`/`Sd` `L=0.5um` fix
  was verified against. At `tt`/27C this is still sub-mV clean (0.73mV worst
  case, well under the provisional LSB); at the `ss` corner (a single
  directional point, not swept), `worst_case_pp` settles to only 5.33mV of
  its target -- above half the provisional differential LSB. This is a real,
  newly-surfaced residual for a **future** area/timing pass (removing this
  sub-block's own now-provably-redundant `Csamp_p`/`Csamp_n`, see "Update
  (issue #95)" below, would roughly halve the load and is the most direct
  fix) -- not fixed here, and not blocking #95's own resolution (which is
  about `BPREF_x`'s floating-state correctness, unaffected by this loading
  question, per that record's own analysis).

## Update (issue #95, 2026-08-24)

Issue #95 resolved the "Open items" assumption directly above (`BPREF_x`
hand-off to a future combined CDAC bottom-plate node) as **false, not just
premature**: `design/cdac/cdac_array.sch` (#53), as actually built, has no
combined bottom-plate node at all -- every bit's bottom plate is
individually and continuously driven to `VREFP`/`VREFN` by its own `SEL<i>`
switch (`design/cdac/cdac_unit_cell.sch`), and `design/sar_adc_top.sch`
(#56) already leaves `BPREF_P`/`BPREF_N` on dead-end nets
(`BPREF_P_NC`/`BPREF_N_NC`) permanently, not as an interim gap.

**Resolution chosen: path (a) -- retire the hand-off assumption, do NOT
remove the now-provably-inert `Csamp_p`/`Csamp_n`/`BPREF_x`/`Cmswn`/`Cmswp`
circuitry.** `sim/sampling-cdac-handoff/records/20260824-231304-144edeb.md`
verifies (not just argues) that `TOP_P`/`TOP_N` settle to `VINP`/`VINN`
within 0.73mV at `tt`/27C, identically across three different CDAC-array
"previous conversion" bottom-plate code states, when this sub-block's
schematic is instantiated together with the real `design/cdac/cdac_array.sch`
netlist exactly as `design/sar_adc_top.sch` wires them. The circuit argument
behind that result: during `SAMPLE`, `TOP_x` is driven low-impedance by
`Msw_x` regardless of what the CDAC array's (always individually driven,
never floating) bottom plates are doing; once `SAMPLE` ends, `Csamp_p`/
`Csamp_n`'s bottom plate (`BPREF_x`) becomes an isolated two-terminal
capacitor (nothing else touches it, per `design/sar_adc_top.sch`'s dead-end
wiring) and therefore injects zero further current into `TOP_x` for the rest
of the conversion -- it is inert, not merely harmless-because-unused.
`Csamp_p`/`Csamp_n` are left in the schematic rather than removed because
removing them would require re-verifying this record's own `Sa`/`Sd`/`Cboot`
sizing against a different (smaller) load, which issue #95 did not attempt;
the area/loading cost of leaving them in is named as a new Open item above,
not silently accepted.

**Position on the #61 overlap (required by #95's own acceptance criteria):**
independent, not reconciled. #61's droop finding is about this sub-block's
*own isolated testbench*, which floats `BPREF_x` for the remainder of its
400ns hold half-period regardless of anything #53/#56 do -- #95 changed the
*reason* `BPREF_x` floats (permanently dead-ended by design, not "not yet
handed off"), not the fact that it floats within this sub-block's own
testbench, and not the observed few-ns timing of the droop itself (see the
corrected "Not (fully) an artifact..." bullet above). #61 remains open and
independent.

## Update (issue #61, 2026-08-25)

Issue #61 root-caused the post-edge hold-transition droop named in "Open
items" above and resolved it for the real integrated ADC. Full derivation,
the diagnostic methodology (six numbered experiments), and every supporting
number: `sim/sampling-frontend/run_hold_kick.py` and its evidence record
`sim/sampling-frontend/records/20260825-021113-a237c79.md`. Summary:

**Root cause, confirmed (not just hypothesized).** The droop is capacitive
charge injection onto the floating `{TOP_x, BPREF_x}` island from two direct
device-terminal couplings: `Cmswn_x`/`Cmswp_x`'s gate-drain overlap coupling
the full-swing `SAMPLE`/`SAMPLEB` transition onto `BPREF_x`, and the
sampling switch `Msw_x`'s own gate-source overlap coupling its gate
(`G_x`, swinging from its boosted level to 0) onto `TOP_x`. This is exactly
the "common-mode capacitive kick ... gate-overlap/off-state junction
capacitance" hypothesis named above, confirmed (not merely still a leading
hypothesis) by two independent methods that agree with each other and with
the measured droop: small-signal `.ac` capacitance extraction of the
island, and a large-signal added-capacitance sweep whose `dV = Q_inj /
(C_island + C_add)` fit has `R^2 > 0.98`.

**Resolution: the droop is negligible in the real integrated ADC, and no
design change is required.** The severity measured above and in
`sim/sampling-frontend/records/20260821-072657-433a294.md` (hundreds of mV,
tens to ~170x the provisional LSB single-ended) is specific to exercising
`sampling_frontend.sch` in isolation, where the injected charge lands on a
femtofarad-scale island. Attaching the real CDAC array
(`design/cdac/cdac_array.sch`, #53) to `TOP_x` exactly as
`design/sar_adc_top.sch` (#56) wires it -- the same charge-injection
mechanism, unmodified -- loads that same charge onto a node dominated by
the CDAC array's own ~4.43pF/side of always-driven bit capacitors instead,
and `dV = Q_inj/C` collapses the droop to well under 1mV (worst case 0.021
LSB differential error across all 3 standard test points and 3 CDAC
"previous code" states, tt/27C only). `run_transient.py`'s original
hold-delta figures are not retracted -- they remain an accurate
characterization of the isolated testbench; what changes is the answer to
whether that number carries into the real ADC, and it does not.

**#55 (SAR clock/phase generation): informational only, no design change
needed.** #55 closed before this finding landed, so this is recorded here
and as a comment on #55 rather than as a change to its (already-merged)
design. #55's existing on-die `Invp`/`Invn` SAMPLE/SAMPLEB generation (zero
explicit dead time) is exactly what issue #61's Experiment 6 used to get
the negligible full-load result above -- so #55 does not need a
non-overlap-margin change on this account, reversing the direction "Open
items" above implied ("a non-overlap margin alone ... did not fully
suppress the transition-edge droop measured here" -- true in isolation,
not load-bearing once the real CDAC array is attached). The one caveat
carried forward to #55/#53: the CDAC array's bit-trial switching must not
begin moving `SELp<i>`/`SELn<i>` away from the previous-conversion code
during the first few ns of the SAMPLE falling edge itself -- #61's
Experiment 6 held the code fixed through the edge, matching #55's own
sequencing (bit-trial starts only after HOLD is well underway).

**Consequence for the "not yet ready for #28/#29" note above.** This
sub-block's front end no longer carries an unresolved, unexplained
several-hundred-mV droop into a full PVT/Monte-Carlo campaign -- the
isolated-testbench number is now explained and shown not to propagate into
the real ADC. The residual `ss`-corner settling-headroom item #95 surfaced
(new Open items bullet above) remains open and is unaffected by this
update.

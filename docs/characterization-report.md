# sky130-sar-adc — Characterization Report

Aggregated, generated artifact tying every `spec/target-spec.md` Target-table row's verdict to the specific evidence record(s) it rests on, per `klayout-tools/docs/design-evidence-tiers.md` item 8 (T1 item 8, tracked in issue #30, part of #23). Every row appears, including rows that fail or are unmeasured -- coverage honesty is part of the claim.

**Do not hand-edit this file.** Regenerate it with `python3 sim/report/generate.py --write` after any `sim/` or `layout/` evidence changes, and re-run `python3 sim/report/generate.py --check` (wired into `npm run check:ci` as `npm run check:report`) before committing -- it fails if a cited record has been superseded, if a citation path no longer exists, or if this file has drifted from what the current records/manifest would regenerate.

## Coverage summary

| Spec row | Status | Verdict | Evidence |
|---|---|---|---|
| Architecture | DRAFT | N/A (DRAFT, descriptive row) | (none -- see detail below) |
| Resolution `N` | RATIFIED | PASS (9/9 corners) | 1 record(s), see detail below |
| Sample rate | DRAFT | UNMEASURED as an end-to-end sample-rate figure (four mechanisms probed individually, not combined);… | 9 record(s), see detail below |
| ENOB | DRAFT (target value) | DOES NOT MEET the DRAFT baseline target (>9.0 bit), informationally: 8.506 bit (mean-case CDAC mism… | 1 record(s), see detail below |
| INL / DNL | DRAFT (target value) | DOES NOT MEET the DRAFT target (<= +-1 LSB, target_yield=0.99), informationally: empirical yield 0.… | 2 record(s), see detail below |
| `V_REF` | RATIFIED | PASS (structural + functional/monotonicity check, 9/9 corners) | 1 record(s), see detail below |
| LSB (differential) | RATIFIED | PASS (structural + functional/monotonicity check, 9/9 corners) | 1 record(s), see detail below |
| Sampling cap (CDAC unit × array) | RATIFIED | PASS (sim structural check, 9/9 corners) + PASS (layout: DRC clean, LVS match, unit-cap count 1024… | 2 record(s), see detail below |
| Comparator input-referred noise | RATIFIED | PASS vs. baseline (<=1.0148 mV rms) at every corner, binding corner `tt_125c_1.80v` = 0.8643 mV rms… | 1 record(s), see detail below |
| Power | DRAFT | UNMEASURED as a Power-row figure/target (informational first current/power evidence only, not a pas… | 2 record(s), see detail below |
| Corners | RATIFIED | In use, verified: harness self-test PASS (proves the corner runner switches the .lib process-corner… | 4 record(s), see detail below |

## Per-row detail

### Architecture

- **Status**: DRAFT
- **Conditions**: N/A -- descriptive/topology row, not a numeric pass/fail claim.
- **Verdict**: N/A (DRAFT, descriptive row)
- **Notes**: Implemented as charge-redistribution SAR, differential, top-plate sampling (`design/sar_adc_top.sch`, `design/cdac/cdac_array.sch`, `design/sampling_frontend.sch`, `design/comparator.sch`, `design/sar_sequencer.sch`) -- matches the DRAFT row's description. Not ratified, so there is no pass/fail verdict to render; listed here for coverage honesty (every target-spec.md row appears, including unratified/unmeasured ones, per this report's own acceptance criteria).


### Resolution `N`

- **Status**: RATIFIED
- **Conditions**: Full ratified corner set: process {ff, fs, sf, ss, tt} x temperature {-40, 27, 125} C x supply {1.62, 1.8, 1.98} V, 9 one-at-a-time points (sim/README.md 'Corner-grid shape').
- **Verdict**: PASS (9/9 corners)
- **Notes**: Confirms MSB-first bit-by-bit capture of all 10 output bits, correct clock/phase sequencing, and the ring sequencer's auto-restart, at every bound corner. The CDAC array's own 9-bit sub-array realizes only 512 positions/side; the 10th (sign) bit comes from the top-level differential structure, per `sim/cdac-array-transfer/records/20260828-005006-0c70212.md`'s own 'UNITS / scope note' -- not independently re-verified by this row's own citation.

**Evidence:**

- `sim/sar-sequencer-behavioral/records/20260827-211956-e13bc1e.md` (Record ID `20260827-211956-e13bc1e`, Supersedes: (none))
  - Overall: PASS (9/9 corners fully correct)
  - Corner matrix run: process=['ff', 'fs', 'sf', 'ss', 'tt'], temperature_c=[-40, 27.0, 125], supply_v=[1.62, 1.8, 1.98] (9 points, one-at-a-time per sim/README.md)
  - Claim: `spec/target-spec.md#numeric-rows--ratified-2026-08-19` -- Resolution `N = 10 bit` (RATIFIED, DR-003 via #27): confirms correct MSB-first bit-by-bit successive-approximation capture of all 10 output bits, correct clock/…

### Sample rate

- **Status**: DRAFT
- **Conditions**: All four constituent mechanisms have now been probed individually; none of these campaigns is a sample-rate measurement. (a) CDAC-array bottom-plate-switch settling: now PVT-complete (the full ratified OAT grid, 9 one-at-a-time points). (b) Comparator decision (regeneration) delay: the full ratified OAT grid (process {ff, fs, sf, ss, tt} x temperature {-40, 27, 125} C x supply {1.62, 1.8, 1.98} V, 9 one-at-a-time points), now PVT-complete after issue #175's reset-integrity topology fix (DR-004 Amendment A). (c) Sequencer CLK-to-phase-output logic delay: now ALSO PVT-complete (the same full ratified OAT grid, 9 one-at-a-time points), covering all 11 ring-sequencer phase transitions at every point (99 phase measurements). (d) Sampling front end acquisition (a new worst-case, rail-to-rail differential input value acquired once SAMPLE re-asserts): now ALSO PVT-complete (the same full ratified OAT grid, 9 one-at-a-time points), one step direction. All four mechanisms are now PVT-complete. Issue #236 fixed the sampling front end's own acquisition mechanism (the fourth) after it was found to fail the DR-006 phase budget at every ratified corner; re-measured against the full grid, it now clears the budget at all 9.
- **Verdict**: UNMEASURED as an end-to-end sample-rate figure (four mechanisms probed individually, not combined); all four mechanisms are now PVT-complete AND all four now clear the DR-006 worst-case phase budget at every ratified corner -- CDAC settling and sequencer logic delay by a wide margin, comparator decision delay PASSes its own reset-integrity control (9/9 corners HELD) and also clears the budget at every corner, and the sampling front end's own acquisition (the sole mechanism that previously failed at every corner) now also clears it at all 9, after issue #236's circuit fix. Separately (issue #254): the first WHOLE-ADC transient (not a per-mechanism probe) drove the committed `design/sar_adc_top.spice` through complete conversions at the DR-006 worst-case 12 MHz clock across the full ratified 9-corner grid; its 12-CLK-period phase structure (BUSY/PH_SAMPLE timing) PASSED at 8/9 corners (informational -- this experiment binds no spec row), but code correctness FAILED at 9/9 corners (every DC input at every corner captured the saturated code 1023), so no end-to-end sample rate could be derived from it either -- see the Findings entry below and issue #259. After issue #257's capture-timing fix (`comparator.CLK` driven from `CLKN`) the same campaign re-run reports the phase structure at 9/9 corners and an input-tracking (no longer saturated) code, worst error 910 -> 384 LSB -- but still not the correct code at any corner, so this row stays UNMEASURED; the remaining defect is the SAR search itself, tracked in #263.
- **Notes**: No end-to-end sample-rate campaign exists. All four of its input terms have now been probed separately, and this row reports all four honestly rather than adding them up. (a) The CDAC array's own switch-R_on/top-plate settling is now PVT-complete: binding (slowest) corner `tt_27c_1.62v`, bit 8 (rise) at 13.2312 ns, 6.3x inside the DR-006-derived 83.333 ns worst-case phase budget; fastest corner `tt_27c_1.98v` at 10.3019 ns (8.1x); worst-to-best spread across the whole grid only 1.28x, and the tt/27C/1.8V point reproduces the single-corner record's own 11.3861 ns exactly. All 9/9 corners clear the budget. A secondary, non-gating finding: the smallest-swing diagnostic row (bit 0, ~0.2% of VDD swing) failed to produce a 99%-settling crossing at 5/9 corners -- root-caused (not asserted without evidence, confirmed window-invariant out to 300 ns) to a small, genuine, already-converged offset between the real simulated circuit and the analytic closed-form ideal (order 0.1-0.3 mV, plausibly charge-injection/subthreshold-leakage) that is negligible against bit 8's own ~1.8 V swing but exceeds 1% of bit 0's own ~4 mV swing at some corners; bit 8 (the array's own true worst case per its tau_i(i) = R_on * C_i * (1 - C_i/C_total) shape) crossed cleanly at all 9/9 corners, so this curiosity does not affect the worst-case finding. (b) The comparator's own decision delay is now PVT-complete: issue #175 (DR-004 Amendment A) moved the cross-coupled NMOS latch pair's sources off hard-wired GND onto the input pair's own precharged drain nodes, closing the reset-integrity defect the prior pass surfaced (Vindiff = 0 mV control now HELD at all 9 ratified corners, 0.00 uA reset-phase static current at every corner). All 27/27 input-driven decision points resolved within the 15.0 ns evaluate window; binding corner `tt_27c_1.62v` at Vindiff = +0.5 mV, decision delay 4.3575 ns, 19.1x inside the DR-006-derived 83.333 ns worst-case phase budget (headroom against a DRAFT figure, not a pass against a ratified line). (c) The SAR sequencer's own CLK-to-phase-output logic delay is now PVT-complete across all 11 of its own ring-sequencer phase transitions at all 9 ratified corner points (99 phase measurements, all producing a valid crossing): binding (slowest) corner `ss_27c_1.80v`, phase b1 at 0.4237 ns, 196.7x inside the DR-006-derived 83.333 ns worst-case phase budget; fastest corner `ff_27c_1.80v` at 0.2480 ns (336.1x); worst-to-best spread across the whole grid only 1.71x, and the tt/27C/1.8V point reproduces the single-corner record's own 0.3123 ns exactly. Slow process and low supply are the two slow directions; temperature is nearly inert (0.3211 ns at -40 C vs. 0.3038 ns at 125 C). All 9/9 corners clear the budget by more than two orders of magnitude -- by far the smallest of the four mechanisms measured, and not the bottleneck at any ratified corner. (d) The sampling front end's own acquisition of a NEW worst-case (rail-to-rail) differential input value, once SAMPLE re-asserts, was first bounded at ONE corner (tt/27C/1.8V): the fast early settling (50%/90% of the way to the new value) is sub-ns on both nodes, but a slow secondary settling tail -- traced to the bootstrap precharge PFET `Sa`'s imperfect off-state once `BOOST_x` is driven above VDD, letting the boosted gate droop over tens of ns -- left a residual 23.43 mV (single-ended, worst node) still uncorrected 83.333 ns after the acquiring edge, ~13.3x the provisional differential LSB's half-step. That single-corner finding has since been taken to the FULL ratified PVT grid (9 one-at-a-time points): every one of the 9 corners exceeds the half-LSB reference scale, confirming the mechanism is not a corner-specific artifact. Binding corner `tt_27c_1.62v`: TOP_P residual 67.19 mV, 38.2x the half-LSB, 2.9x worse than the tt/27C/1.8V baseline point; best corner `tt_27c_1.98v`: 9.00 mV, 5.1x the half-LSB. Issue #236 fixed this: instrumenting `BOOST_x` directly found two independent limiters. (1) The bootstrap precharge PFET `Sa`'s gate was tied to `SAMPLE` (a VDD-level signal) while `Sa`'s own source is `BOOST_x` (driven to ~VIN+VDD during sampling) -- V_sg = BOOST_x - VDD ~= VIN, an ON device discharging the boosted node throughout the sample phase, not the leaky-off device originally assumed. Re-gating `Sa` from the switch's own gate node `G_x` instead (already GND during hold, shorted to `BOOST_x` during sampling) makes `Sa` genuinely off. (2) With (1) applied, the common-mode reference transmission gate `Cmswn`/`Cmswp` -- in series with `Csamp` via the floating `BPREF_x` node -- was the limiter that remained; widened from W=1um to W=16um. Re-measured against the full ratified PVT grid with both fixes applied: ALL 9/9 corners now clear the DR-006 worst-case (12 MHz) phase budget, worst case `tt_27c_1.62v` at 0.380 mV (~0.2x the half-LSB) vs. that same corner's pre-fix 67.190 mV (~38.2x). This mechanism is no longer the standout bottleneck of the four -- all four now clear the budget at every ratified corner. Three things this fix touches are explicitly NOT yet re-derived: `sim/vcm-drive-budget/`'s R_source/C_decouple budget (a wider `Cmsw` draws more peak current from the shared `VCM` rail), and `layout/sampling-frontend/`'s LVS match and `layout/sar-adc-top/`'s composition of it (both now stale against the new `Sa` gate net and `Cmsw` width) -- tracked as issue #245. Named as open work by spec/target-spec.md's own 'Not ratified by this record' list (#24/#28); DR-006's 1.2-12 MHz clock range remains a mechanical consequence of this DRAFT row, not a derived result. (e) Issue #254's `sim/full-conversion-transient/` campaign is the first to drive the whole assembled `sar_adc_top` netlist (all four sub-blocks together, real comparator, real sequencer) rather than one mechanism in isolation. Its own phase-timing check (BUSY high during EOC, low again by the next conversion's SAMPLE phase -- the same 12-CLK-period structure `sim/sar-sequencer-behavioral/` proved against an IDEAL COMP_OUT stimulus) reproduces at 8/9 ratified corners (`ff_27c_1.80v` is the one exception), corroborating (a)/(c) above at the whole-ADC level. But the captured DOUT9..DOUT0 code itself is wrong at all 9/9 corners (every DC input saturates to code 1023) -- a NEW, whole-ADC-only finding none of the four isolated mechanisms above could have surfaced, since each drives its own sub-block with an ideal stimulus for every OTHER sub-block. A `--mechanism-probe` diagnostic (delaying the comparator's own capture-clock edge relative to its strobe, testbench-only, not a committed design change) produces different, non-saturated codes at the same input set, pointing at a comparator-decision-capture timing relationship in `design/sar_adc_top.sch`'s wiring as the likely mechanism -- filed as issue #259 rather than asserted here as a root cause. This finding does not change (a)-(d)'s own per-mechanism PASS verdicts against the DR-006 phase budget; it shows those four passing budgets are not sufficient for the assembled ADC to produce a correct code, which is exactly why this row remains UNMEASURED rather than closed out. (f) Issue #258 then made `design/sar_adc_top.spice` self-contained -- it now emits `.GLOBAL VPWR` / `.GLOBAL VGND` alongside the analog rails' own cards, so the standard cells nested inside its `xseq` instance are no longer scoped to a private, unpowered copy of the digital rails whenever the netlist is simulated as a whole. The campaign in (e) was re-run against that fixed netlist and reproduces every finding unchanged (same 1023 saturation at 9/9 corners, same 8/9 phase structure, same per-corner power). That is the expected outcome rather than a null result: (e)'s own testbench already supplied the missing declaration at its own deck-assembly step, so #258 moves the declaration into the netlist without changing what this campaign measures. The re-run therefore does NOT supersede (e), and #259 stands exactly where it did. (g) Issue #257 then fixed the capture-timing relationship #259's node-level trace pinned down: `comparator.CLK` is now driven from `CLKN = NOT(CLK)` (`design/sar_adc_top.sch`), so the comparator's evaluate half ends AT the bit-capture registers' own rising capturing edge instead of a half-period after its decision was destroyed. The campaign in (e)/(f) was re-run against that fixed netlist -- the record cited below supersedes (f)'s -- and the phase-timing check now reproduces at 9/9 ratified corners (the `ff_27c_1.80v` exception noted above is gone), strengthening (a)/(c) at the whole-ADC level. The captured code is no longer stuck at 1023: it now tracks the applied differential (`0, 0, 768, 896, 1023` for the five DC inputs) and the worst code error drops 910 -> 384 LSB. It is still WRONG at 9/9 corners, bit-identical at every corner (no PVT dependence at all), for a second and independent reason the fix uncovered and issue #263 now tracks: the SAR search applies no trial perturbation before each decision, never clears the CDAC bits between conversions, and drives both array sides unconditionally. So this row stays UNMEASURED for the same reason as before -- the four per-mechanism budgets still are not sufficient for the assembled ADC to produce a correct code -- but the reason is now a search-algorithm defect, not a capture-timing one. (h) Issue #263 then fixed all three of those: `PRESET<i>` (one added `or2_1` per bit) applies the trial perturbation at the edge that opens each bit's own trial; the CDAC bits now clear at the `PH_EOC -> PH_SAMPLE` edge -- a FULL CLK period before the sampling switch opens, gated by a new `BUSY_BITS` signal (excludes `PH_EOC`, unlike the pre-existing `BUSY` output pin) rather than racing the switch's own opening edge as an earlier draft of this fix did; and `spec/decision-records/DR-008-cdac-top-level-switching-polarity.md` replaces the unconditional complementary `SELp`/`SELn` drive with decision-directed single-side switching plus a `COMP_EFF = XNOR(COMP_OUT, DOUT9)` per-branch polarity correction and an `ADCOUT<i> = DOUT<i> XOR DOUT9N` offset-binary output-recoding stage (DOUT8..0 read directly is a sign+true-magnitude value for the DOUT9=0 branch, not the ratified offset-binary code -- see DR-008's own 'Correction' section). Net effect at the ratified 9-corner grid: the `-0.25*V_REF` input now reads back its exact ideal code (384, 0 LSB error) at all 9 corners; `+0.00*V_REF`/`+0.25*V_REF` read back a small, corner-invariant 2-3 LSB high. The two near-full-scale inputs (`+-0.78*V_REF`) still fail badly and corner-invariantly (worst |error| 71-124 LSB negative side, a flat 112 LSB / code-1023 saturation on the positive side) -- a NEW, large-differential-input-specific defect this pass surfaced but did not resolve, tracked by DR-008's own Open items and a dedicated follow-up issue (leading hypothesis: a top-plate common-mode excursion under single-side switching that the comparator's already-documented ~23 mV nominal headroom margin, DR-004, cannot absorb at large codes -- not yet confirmed by a targeted trace). So this row remains UNMEASURED: 4/5 inputs are at or very near the ratified target now, but the grid is not yet 9/9-at-+-1-LSB. (i) Issue #263's second pass then closed the mid-scale residual from (h). Probing the comparator's OWN differential input at every bit-trial decision instant showed the residual was not a settling or search defect at all but a systematic, corner-invariant, input-referred comparator OFFSET created by this integration level itself: `design/sar_adc_top.sch` loaded `comparator.OUTP` (= `COMP_OUT`) with two standard-cell input pins inside `xseq` while leaving `comparator.OUTN` entirely unloaded, and in a StrongARM-class latch (DR-004) an output-node capacitance imbalance biases the regeneration race directly -- no device mismatch needed. Measured: `COMP_OUT` read `1` at a true input of -7.0 mV (-2.0 LSB) and -10.5 mV (-3.0 LSB) at a ~897 mV top-plate common mode, and at -3.7 mV (-1.05 LSB) at ~676 mV. `spec/decision-records/DR-009-comparator-output-load-balance-and-half-lsb-offset.md` fixes it with a matched dummy load on `OUTN` (the same two cells on the same two pin positions, with the same nets on their other inputs), and adds the classic half-LSB quantizer offset -- one CDAC-unit-sized cap on `TOP_N` switched `VREFP -> VCM` (half the reference swing = exactly 0.5 LSB) from the `PH_B9 -> PH_B8` edge, plus a matching dummy cell on `TOP_P` -- to re-centre the SAR's mid-rise search against the ideal code's mid-tread convention. Net effect at the ratified 9-corner grid (newest record cited below): all three mid-scale inputs are now within +-1 LSB at 9/9 corners (`-0.25*V_REF` -1 LSB, `+0.00*V_REF` -1/0 LSB, `+0.25*V_REF` +1 LSB), up from 1/5 to 3/5 inputs per corner. The two near-full-scale inputs are bit-for-bit UNCHANGED by both fixes, which is itself evidence that their defect (#265) is neither of these two mechanisms. This row therefore still remains UNMEASURED, now for exactly one reason: the `+-0.78*V_REF` non-convergence of issue #265, plus the array's ~1% absolute GAIN error DR-009 identifies and deliberately does not close (a top-plate parasitic of ~4 unit caps, dominated by the comparator's own input gate capacitance; 0 LSB at mid-scale, ~1 LSB at +-0.25*V_REF, ~3 LSB at +-0.78*V_REF -- it needs an array unit-cap sizing decision or an explicit gain-error spec row, neither of which exists yet).

**Evidence:**

- `sim/cdac-bit-trial-settling/records/20260905-220919-bbf06dd.md` (Record ID `20260905-220919-bbf06dd`, Supersedes: (none))
  - Result: (no Overall/Statistical convention/Measured value(s) field found)
  - Claim: quantifies, for the first time in this repo, how long the CDAC array's own shared top-plate node (`design/cdac/cdac_array.sch`) takes to settle after a single bit's SEL toggles at the start of its own bit-trial phase, i…
- `sim/cdac-bit-trial-settling/records/20260907-013225-5f176a6.md` (Record ID `20260907-013225-5f176a6`, Supersedes: (none))
  - Result: (no Overall/Statistical convention/Measured value(s) field found)
  - Corner matrix run: process=['ff', 'fs', 'sf', 'ss', 'tt'], temperature_c=[-40, 27.0, 125], supply_v=[1.62, 1.8, 1.98] (9 points, one-at-a-time per sim/README.md)
  - Claim: extends the single-corner (tt/27C/1.8V) finding in [`records/20260905-220919-bbf06dd.md`](20260905-220919-bbf06dd.md) -- that the CDAC array's own shared top-plate node (`design/cdac/cdac_array.sch`) settles well inside…
- `sim/comparator-decision/records/20260906-074451-7724af3.md` (Record ID `20260906-074451-7724af3`, Supersedes: 20260906-052758-662a84d)
  - Overall: PASS (27/27 input-driven points decided within the 15.0ns evaluate window; 9/9 reset-integrity controls held)
  - Corner matrix run: process=['ff', 'fs', 'sf', 'ss', 'tt'], temperature_c=[-40, 27.0, 125], supply_v=[1.62, 1.8, 1.98] (9 points, one-at-a-time per sim/README.md)
  - Claim: pending #1/#27 -- attempts to characterize design/comparator.sch's decision (regeneration) delay vs. differential input across the FULL ratified PVT corner set, and reports what that attempt actually found. There is no…
- `sim/sequencer-logic-delay/records/20260906-192230-1b5c996.md` (Record ID `20260906-192230-1b5c996`, Supersedes: (none))
  - Result: (no Overall/Statistical convention/Measured value(s) field found)
  - Claim: quantifies, for the first time in this repo, how long `design/sar_sequencer.sch`'s own walking-one ring sequencer takes, after each CLK rising edge, to produce a valid one-hot phase-select output -- isolating the sequen…
- `sim/sequencer-logic-delay/records/20260906-230516-0904419.md` (Record ID `20260906-230516-0904419`, Supersedes: (none))
  - Result: (no Overall/Statistical convention/Measured value(s) field found)
  - Corner matrix run: process=['ff', 'fs', 'sf', 'ss', 'tt'], temperature_c=[-40, 27.0, 125], supply_v=[1.62, 1.8, 1.98] (9 points, one-at-a-time per sim/README.md)
  - Claim: extends the single-corner (tt/27C/1.8V) finding in [`records/20260906-192230-1b5c996.md`](20260906-192230-1b5c996.md) -- that `design/sar_sequencer.sch`'s own walking-one ring sequencer produces a valid one-hot phase-se…
- `sim/sampling-acquisition-settling/records/20260906-202424-cb7e7aa.md` (Record ID `20260906-202424-cb7e7aa`, Supersedes: (none))
  - Result: (no Overall/Statistical convention/Measured value(s) field found)
  - Claim: quantifies, for the first time in this repo, how long `design/sampling_frontend.sch`'s own bootstrapped sampling switch takes, once the SAMPLE phase re-asserts, to acquire a NEW, worst-case (rail-to-rail, near-Nyquist)…
- `sim/sampling-acquisition-settling/records/20260908-051436-6ccd72d.md` (Record ID `20260908-051436-6ccd72d`, Supersedes: [`records/20260906-211700-00d26af.md`](20260906-211700-00d26af.md) -- same stimulus and same 9-point ratified OAT grid, measured against the pre-issue-#236 `design/sampling_frontend.sch`)
  - Result: (no Overall/Statistical convention/Measured value(s) field found)
  - Corner matrix run: process=['ff', 'fs', 'sf', 'ss', 'tt'], temperature_c=[-40, 27.0, 125], supply_v=[1.62, 1.8, 1.98] (9 points, one-at-a-time per sim/README.md)
  - Claim: re-measures, at the FULL ratified PVT corner set (spec/target-spec.md's "Numeric rows -- RATIFIED 2026-08-19" section: -40/27/125C, +-10% supply, sky130 process corners -- the same OAT grid sim/comparator-decision/'s ow…
- `sim/full-conversion-transient/records/20260910-190240-2d1d196.md` (Record ID `20260910-190240-2d1d196`, Supersedes: (none))
  - Overall: FAIL (0/9 corners resolve every input to its ideal code +-1 LSB with a correct 12-period phase structure). This verdict is against this experiment's own informational criterion, NOT against a ratified spec row.
  - Corner matrix run: process=['ff', 'fs', 'sf', 'ss', 'tt'], temperature_c=[-40, 27.0, 125], supply_v=[1.62, 1.8, 1.98] (9 points, one-at-a-time per sim/README.md)
  - Claim: `spec/target-spec.md#target-table` -- **Sample rate** and **Power**, both DRAFT rows, INFORMATIONAL only. This is the first end-to-end campaign that drives the whole transistor-level `design/sar_adc_top.spice` through c…
- `sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md` (Record ID `20260912-002315-9aaf1ca`, Supersedes: 20260911-204111-a6df3bb)
  - Overall: FAIL (0/9 corners resolve every input to its ideal code +-1 LSB with a correct 12-period phase structure). This verdict is against this experiment's own informational criterion, NOT against a ratified spec row.
  - Corner matrix run: process=['ff', 'fs', 'sf', 'ss', 'tt'], temperature_c=[-40, 27.0, 125], supply_v=[1.62, 1.8, 1.98] (9 points, one-at-a-time per sim/README.md)
  - Claim: `spec/target-spec.md#target-table` -- **Sample rate** and **Power**, both DRAFT rows, INFORMATIONAL only. This is the first end-to-end campaign that drives the whole transistor-level `design/sar_adc_top.spice` through c…

### ENOB

- **Status**: DRAFT (target value)
- **Conditions**: Behavioral-accelerated composite (NOT a dynamic-test/FFT measurement): comparator noise term taken from the RATIFIED full-PVT corner campaign's worst-case binding corner (`tt_125c_1.80v`, not re-simulated); CDAC mismatch nonlinearity from a `tt_mm` Monte Carlo campaign, N=40, base seed=1 (draws seed..seed+N-1), PVT point tt/27C/1.8V; kT/C sampling noise analytic at the 125 C worst case; quantization noise analytic (LSB/sqrt(12)).
- **Verdict**: DOES NOT MEET the DRAFT baseline target (>9.0 bit), informationally: 8.506 bit (mean-case CDAC mismatch) / 7.755 bit (worst-case). Target not ratified -- not a pass/fail against a ratified line.
- **Notes**: Excludes dynamic effects (settling, slewing, aperture jitter, reference droop -- needs a future top-level transient/FFT campaign), treats CDAC INL as an rms noise-like term rather than input-correlated distortion, reuses the comparator's REDUCED SUB-MODEL noise figure, and deliberately excludes comparator offset. Re-run this pass (issue #175) against the amended comparator noise figure (0.8643 mV rms, down from 0.9591 mV rms) -- achieved ENOB moved from 8.491/7.749 to 8.506/7.755 bit; the pass/fail outcome is unchanged. See the cited record's own LIMITATIONS field for the full list.

**Evidence:**

- `sim/enob-estimate/records/20260906-082749-7724af3.md` (Record ID `20260906-082749-7724af3`, Supersedes: (none))
  - Result: Measured value(s): achieved ENOB (mean-case CDAC mismatch) = **8.506 bit**; achieved ENOB (worst-case CDAC mismatch) = **7.755 bit** -- both against the DRAFT target row `> 9` (baseline) / `> 9.5` (stretch), reported INFORMATIONALLY, not as pass/fail against a ratified line.
  - Claim: `spec/target-spec.md#target-table` -- ENOB DRAFT target row (`> 9.0 bit` baseline / `> 9.5 bit` stretch, target value, NOT ratified: target-spec.md's own "Not ratified by this record" list names ENOB/INL-DNL target valu…

### INL / DNL

- **Status**: DRAFT (target value)
- **Conditions**: Monte Carlo: `tt_mm` corner, N=40, base seed=1, PVT point tt/27C/1.8V, 22-code reduced set covering every major-carry transition of the 9-bit sub-array. Combined with (not replacing) the deterministic structural/monotonicity PVT campaign for the same DUT, run across the full ratified 9-point corner set.
- **Verdict**: DOES NOT MEET the DRAFT target (<= +-1 LSB, target_yield=0.99), informationally: empirical yield 0.8250 [0.6722, 0.9266] (DNL) / 0.9250 [0.7961, 0.9843] (INL) at 95% CI, N=40. klt yield's own sample-size verdict on both is 'insufficient' for a tight yield-fraction claim. Target not ratified.
- **Notes**: The array-only 9-bit sub-array's own code step is 2x the ratified ADC LSB; DNL/INL are reported in ratified-LSB units per the cited record's own UNITS/scope note, not the array's native step.

**Evidence:**

- `sim/cdac-array-transfer/records/20260828-005006-0c70212.md` (Record ID `20260828-005006-0c70212`, Supersedes: (none))
  - Overall: PASS (harness/negative-control validity; DNL/INL magnitude itself is reported informationally below against the DRAFT target, not gated as pass/fail -- the target row is not yet ratified)
  - Claim: `spec/target-spec.md#target-table` -- DNL/INL DRAFT target row (`<= +-1 LSB`, target value, NOT ratified: target-spec.md's own "Not ratified by this record" list names ENOB/INL-DNL target values as still open pending th…
- `sim/cdac-array-transfer/records/20260827-213107-e13bc1e.md` (Record ID `20260827-213107-e13bc1e`, Supersedes: (none))
  - Overall: PASS
  - Corner matrix run: process=['ff', 'fs', 'sf', 'ss', 'tt'], temperature_c=[-40, 27, 125], supply_v=[1.62, 1.8, 1.98] (9 points, one-at-a-time per sim/README.md)
  - Claim: `spec/target-spec.md#numeric-rows--ratified-2026-08-19` -- `V_REF = V_DD = 1.8 V`, LSB (differential) `2*V_REF/2^N = 3.5156 mV`, and CDAC unit-cap/array size `C_u ~= 8.65 fF`, `512` positions/side (all three RATIFIED, D…

### `V_REF`

- **Status**: RATIFIED
- **Conditions**: Full ratified corner set, 9 OAT points. V_REF is a fixed design constant per DR-003's own scope table, not itself a simulated quantity -- the cited record confirms the CDAC array correctly consumes `VREFP={vdd_val}`/`VREFN=0` at each corner's own supply point, not that a reference-generator circuit meets a tolerance (none is ratified).
- **Verdict**: PASS (structural + functional/monotonicity check, 9/9 corners)
- **Notes**: See spec/decision-records/DR-003-numeric-spec-derivation.md for the full derivation.

**Evidence:**

- `sim/cdac-array-transfer/records/20260827-213107-e13bc1e.md` (Record ID `20260827-213107-e13bc1e`, Supersedes: (none))
  - Overall: PASS
  - Corner matrix run: process=['ff', 'fs', 'sf', 'ss', 'tt'], temperature_c=[-40, 27, 125], supply_v=[1.62, 1.8, 1.98] (9 points, one-at-a-time per sim/README.md)
  - Claim: `spec/target-spec.md#numeric-rows--ratified-2026-08-19` -- `V_REF = V_DD = 1.8 V`, LSB (differential) `2*V_REF/2^N = 3.5156 mV`, and CDAC unit-cap/array size `C_u ~= 8.65 fF`, `512` positions/side (all three RATIFIED, D…

### LSB (differential)

- **Status**: RATIFIED
- **Conditions**: Full ratified corner set, 9 OAT points (same record as `V_REF` above).
- **Verdict**: PASS (structural + functional/monotonicity check, 9/9 corners)
- **Notes**: 3.5156 mV differential; used as the reporting unit for the INL/DNL row above and the ENOB row's quantization-noise term.

**Evidence:**

- `sim/cdac-array-transfer/records/20260827-213107-e13bc1e.md` (Record ID `20260827-213107-e13bc1e`, Supersedes: (none))
  - Overall: PASS
  - Corner matrix run: process=['ff', 'fs', 'sf', 'ss', 'tt'], temperature_c=[-40, 27, 125], supply_v=[1.62, 1.8, 1.98] (9 points, one-at-a-time per sim/README.md)
  - Claim: `spec/target-spec.md#numeric-rows--ratified-2026-08-19` -- `V_REF = V_DD = 1.8 V`, LSB (differential) `2*V_REF/2^N = 3.5156 mV`, and CDAC unit-cap/array size `C_u ~= 8.65 fF`, `512` positions/side (all three RATIFIED, D…

### Sampling cap (CDAC unit × array)

- **Status**: RATIFIED
- **Conditions**: sim: structural check (unit-cap geometry + per-side weight totals) at every corner of the ratified sim record. layout: drawn/extracted physical geometry, DRC + LVS against design/cdac/cdac_array.sch, single-point (no corner sweep -- DRC/LVS are corner-invariant structural checks, not PVT-dependent measurements).
- **Verdict**: PASS (sim structural check, 9/9 corners) + PASS (layout: DRC clean, LVS match, unit-cap count 1024 = 512/side x 2, common-centroid checks all pass). Drawn unit cap 8.6473 fF vs. ratified C_u ~= 8.65 fF.
- **Notes**: Layout evidence is independent, physical confirmation of the sim-only structural check. Supersedes layout/cdac-array/reports/20260825-132454-51cbdd4/, whose LVS 'match' verdict did not reproduce on its own committed artefacts -- see layout/cdac-array/README.md and issue #148.

**Evidence:**

- `sim/cdac-array-transfer/records/20260827-213107-e13bc1e.md` (Record ID `20260827-213107-e13bc1e`, Supersedes: (none))
  - Overall: PASS
  - Corner matrix run: process=['ff', 'fs', 'sf', 'ss', 'tt'], temperature_c=[-40, 27, 125], supply_v=[1.62, 1.8, 1.98] (9 points, one-at-a-time per sim/README.md)
  - Claim: `spec/target-spec.md#numeric-rows--ratified-2026-08-19` -- `V_REF = V_DD = 1.8 V`, LSB (differential) `2*V_REF/2^N = 3.5156 mV`, and CDAC unit-cap/array size `C_u ~= 8.65 fF`, `512` positions/side (all three RATIFIED, D…
- `layout/cdac-array/reports/20260905-220338-9fb9b04/record.md` (layout evidence -- see manifest.BLIND_SPOTS for the caveat on layout freshness)
  - CDAC array layout record: 20260905-220338-9fb9b04

### Comparator input-referred noise

- **Status**: RATIFIED
- **Conditions**: Full ratified corner set, 9 OAT points, `ac-based` noise methodology, integration bandwidth 1 kHz - 1 GHz. REDUCED SUB-MODEL (the input pair's own precharged drain-node PMOS pair diode-connected as loads, cross-coupled latch pairs omitted, CLK held at VDD) -- named, flagged simplification, re-derived against the amended device set by issue #175 (DR-004 Amendment A), see spec/decision-records/DR-004-comparator-topology-and-noise-budget.md.
- **Verdict**: PASS vs. baseline (<=1.0148 mV rms) at every corner, binding corner `tt_125c_1.80v` = 0.8643 mV rms; does NOT meet the stretch threshold (<=0.5859 mV rms) at the binding corner.

**Evidence:**

- `sim/comparator-decision/records/20260906-065109-eedd532.md` (Record ID `20260906-065109-eedd532`, Supersedes: 20260827-212404-e13bc1e)
  - Overall: PASS vs. the ratified baseline threshold (1.0148 mV rms); does NOT meet the stretch threshold (0.5859 mV rms) at the binding corner.
  - Corner matrix run: process=['ff', 'fs', 'sf', 'ss', 'tt'], temperature_c=[-40, 27.0, 125], supply_v=[1.62, 1.8, 1.98] (9 points, one-at-a-time per sim/README.md)
  - Claim: `spec/target-spec.md#numeric-rows--ratified-2026-08-19` -- Comparator input-referred noise `<=1.0148 mV rms` (baseline, ENOB>9.0) / `<=0.5859 mV rms` (stretch, ENOB>9.5) (RATIFIED, DR-003 via #27). Measures design/compa…

### Power

- **Status**: DRAFT
- **Conditions**: Issue #254's `sim/full-conversion-transient/` campaign, full ratified OAT grid (9 one-at-a-time points): average supply/reference current over one steady-state conversion (12 CLK periods at the DR-006 worst-case 12 MHz clock), per rail (`VDD`, `VPWR`, `VREFP`, `VCM`, `VREFN`), `P = sum(V_source * |avg I_source|)`. ADC core only -- no reference buffer, clock generator, or output driver exists in this design yet, so a real system's reference/clock power is not included.
- **Verdict**: UNMEASURED as a Power-row figure/target (informational first current/power evidence only, not a pass/fail against any target -- 'report, don't pre-commit')
- **Notes**: First supply-current measurement of any kind on this block. Binding (highest-power) corner `tt_27c_1.98v`: 14.743 uW; lowest `tt_27c_1.62v`: 8.692 uW; tt/27C/1.80V baseline point: 11.101 uW. NOTE: this same campaign's own code-correctness check FAILS at all 9 ratified corners (see the Sample rate row above and issue #259), so these current/power numbers are measured on a conversion that is NOT resolving to the correct code -- they characterize the circuit's steady-state current draw under the DR-006 12 MHz clock schedule, not the current draw of a functionally-correct conversion. Re-measure once the code-correctness defect is fixed, before treating this figure as durable. One unrelated, non-gating data point also exists outside sim/'s evidence trail: `layout/sar-sequencer/reports/20260825-124031-1a2f7c1/record.md`'s OpenROAD PnR estimate for the digital SAR-sequencer sub-block ONLY (0.0155 mW) -- a static EDA-tool estimate, not a simulated/measured full-ADC number, and not tied to the ratified corner set. Cited for completeness, not as spec-row evidence. Re-measured unchanged after issue #258's netlist-scoping fix (`.GLOBAL VPWR`/`.GLOBAL VGND` now declared by `design/sar_adc_top.spice` itself): every per-corner figure above reproduced to the digit, so the caveat about these numbers being measured on a functionally-incorrect conversion was unchanged too. SUPERSEDED FIGURES (issue #257): the second record cited below re-measures the same campaign on the post-#257 DUT (`comparator.CLK` driven from `CLKN`, so the bit trials now capture live comparator decisions instead of the comparator's reset level), and the power roughly doubles because the CDAC and the SAR register are now actually switching every conversion instead of sitting in a stuck all-ones code: binding (highest-power) corner `tt_27c_1.98v` 26.760 uW, lowest `tt_27c_1.62v` 16.750 uW, tt/27C/1.80V baseline 21.874 uW. The caveat itself still stands and is the reason this row remains UNMEASURED: the conversion still does not resolve to the correct code (see the Sample rate row above and issue #263), so this is the steady-state current draw of a switching-but-not-converging conversion. UPDATE (issue #263): the third record cited below re-measures the same campaign after #263's trial-perturbation, per-conversion-clear, and decision-directed-switching fixes (see the Sample rate row's own (h) paragraph for the full writeup) -- binding (highest-power) corner `tt_27c_1.98v` 35.453 uW, lowest `tt_27c_1.62v` 22.361 uW, tt/27C/1.80V baseline 28.823 uW, a further increase consistent with more of the array now switching correctly per bit trial. The caveat still stands and this row still remains UNMEASURED: 4 of 5 inputs are now at or very near their ideal code, but the two near-full-scale inputs still fail badly (see Sample rate row (h) and DR-008's Open items), so this is still the current draw of a conversion that is not yet correct across its full input range. Re-measure again once the residual large-signal defect is fixed. UPDATE (issue #263, second pass): the newest record cited below (`20260912-002315-9aaf1ca`, which supersedes the `20260911-204111-a6df3bb` figures quoted just above and is cited in its place) re-measures the same campaign again after DR-009's comparator-output load balancing and half-LSB quantizer offset (Sample rate row paragraph (i)) -- binding (highest-power) corner `tt_27c_1.98v` 34.237 uW, lowest `tt_27c_1.62v` 21.600 uW, tt/27C/1.80V baseline 27.971 uW: within ~3% of the previous record at every corner, as expected for a change that adds 4 standard cells, 2 unit capacitors and 6 switch FETs and corrects WHICH way a few marginal bit decisions go rather than how many transitions the array makes. The caveat still stands and this row still remains UNMEASURED: the three mid-scale inputs are now all within +-1 LSB at 9/9 corners, but the two near-full-scale inputs are unchanged and still fail badly (issue #265), so this is still the current draw of a conversion that is not correct across its full input range.

**Evidence:**

- `sim/full-conversion-transient/records/20260910-190240-2d1d196.md` (Record ID `20260910-190240-2d1d196`, Supersedes: (none))
  - Overall: FAIL (0/9 corners resolve every input to its ideal code +-1 LSB with a correct 12-period phase structure). This verdict is against this experiment's own informational criterion, NOT against a ratified spec row.
  - Corner matrix run: process=['ff', 'fs', 'sf', 'ss', 'tt'], temperature_c=[-40, 27.0, 125], supply_v=[1.62, 1.8, 1.98] (9 points, one-at-a-time per sim/README.md)
  - Claim: `spec/target-spec.md#target-table` -- **Sample rate** and **Power**, both DRAFT rows, INFORMATIONAL only. This is the first end-to-end campaign that drives the whole transistor-level `design/sar_adc_top.spice` through c…
- `sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md` (Record ID `20260912-002315-9aaf1ca`, Supersedes: 20260911-204111-a6df3bb)
  - Overall: FAIL (0/9 corners resolve every input to its ideal code +-1 LSB with a correct 12-period phase structure). This verdict is against this experiment's own informational criterion, NOT against a ratified spec row.
  - Corner matrix run: process=['ff', 'fs', 'sf', 'ss', 'tt'], temperature_c=[-40, 27.0, 125], supply_v=[1.62, 1.8, 1.98] (9 points, one-at-a-time per sim/README.md)
  - Claim: `spec/target-spec.md#target-table` -- **Sample rate** and **Power**, both DRAFT rows, INFORMATIONAL only. This is the first end-to-end campaign that drives the whole transistor-level `design/sar_adc_top.spice` through c…

### Corners

- **Status**: RATIFIED
- **Conditions**: The -40/27/125 C x +-10% supply x sky130 process-corner set itself, as exercised by every deterministic-row campaign below.
- **Verdict**: In use, verified: harness self-test PASS (proves the corner runner switches the .lib process-corner section / .temp card / vdd_val independently per axis; sim/selftest.sh Stage 4's sabotage negative control backs this further) plus 3 deterministic-row corner campaigns (27 corner-points total), all PASS.

**Evidence:**

- `sim/harness-corner-smoke/records/20260814-020959-98d9186.md` (Record ID `20260814-020959-98d9186`, Supersedes: (none))
  - Overall: PASS
  - Corner matrix run: process=['ff', 'fs', 'sf', 'ss', 'tt'], temperature_c=[-40, 27, 125], supply_v=[1.62, 1.8, 1.98] (9 points)
  - Claim: None -- harness self-verification, not a spec claim. Proves the PVT plumbing (vdd_val substitution, the process-corner .lib section, .temp) actually takes effect on real sky130 devices, so later records against ratified…
- `sim/cdac-array-transfer/records/20260827-213107-e13bc1e.md` (Record ID `20260827-213107-e13bc1e`, Supersedes: (none))
  - Overall: PASS
  - Corner matrix run: process=['ff', 'fs', 'sf', 'ss', 'tt'], temperature_c=[-40, 27, 125], supply_v=[1.62, 1.8, 1.98] (9 points, one-at-a-time per sim/README.md)
  - Claim: `spec/target-spec.md#numeric-rows--ratified-2026-08-19` -- `V_REF = V_DD = 1.8 V`, LSB (differential) `2*V_REF/2^N = 3.5156 mV`, and CDAC unit-cap/array size `C_u ~= 8.65 fF`, `512` positions/side (all three RATIFIED, D…
- `sim/comparator-decision/records/20260906-065109-eedd532.md` (Record ID `20260906-065109-eedd532`, Supersedes: 20260827-212404-e13bc1e)
  - Overall: PASS vs. the ratified baseline threshold (1.0148 mV rms); does NOT meet the stretch threshold (0.5859 mV rms) at the binding corner.
  - Corner matrix run: process=['ff', 'fs', 'sf', 'ss', 'tt'], temperature_c=[-40, 27.0, 125], supply_v=[1.62, 1.8, 1.98] (9 points, one-at-a-time per sim/README.md)
  - Claim: `spec/target-spec.md#numeric-rows--ratified-2026-08-19` -- Comparator input-referred noise `<=1.0148 mV rms` (baseline, ENOB>9.0) / `<=0.5859 mV rms` (stretch, ENOB>9.5) (RATIFIED, DR-003 via #27). Measures design/compa…
- `sim/sar-sequencer-behavioral/records/20260827-211956-e13bc1e.md` (Record ID `20260827-211956-e13bc1e`, Supersedes: (none))
  - Overall: PASS (9/9 corners fully correct)
  - Corner matrix run: process=['ff', 'fs', 'sf', 'ss', 'tt'], temperature_c=[-40, 27.0, 125], supply_v=[1.62, 1.8, 1.98] (9 points, one-at-a-time per sim/README.md)
  - Claim: `spec/target-spec.md#numeric-rows--ratified-2026-08-19` -- Resolution `N = 10 bit` (RATIFIED, DR-003 via #27): confirms correct MSB-first bit-by-bit successive-approximation capture of all 10 output bits, correct clock/…

## Post-layout re-sim (T1 item 7)

**post-layout: not yet available, because** full-ADC layout is not complete
(#25, open, `loom:epic`) and `klt pex` is not implemented end-to-end upstream
(a `2AMLogic/klayout-tools` tool gap, filed generically per `CLAUDE.md`'s
friction protocol; see `layout/comparator/pex/README.md` for the two
specific bugs hit and worked around by hand for the one sub-block below).

One sub-block exception exists and is disclosed here rather than folded into
a spec-row verdict: `layout/comparator/reports/20260825-151036-aaf3010/record.md`
is a genuine post-layout parasitic-extraction re-sim (`klt extract
--parasitics` + `klt sim` on both legs, working around two `klt pex` bugs by
hand) for the **comparator sub-block only**, at a **single** PVT point
(tt/27C/1.8V), comparing schematic-vs-extracted pick-off offset. It is
**not** corner-swept, is **not** integrated into `sim/`'s append-only
evidence trail (no `Claim` against a `spec/target-spec.md` row, no
`records/` entry), and does **not** cover the CDAC array, sampling front
end, or SAR sequencer. It answers a narrower question -- is the
comparator's routing-parasitic-driven offset material against its
device-mismatch-driven offset? (no, by more than two orders of magnitude) --
and does not substitute for T1 item 7's full-ADC extracted re-sim against
the ratified corner set. Treated here as informational, not as post-layout
spec-row evidence.


## Known blind spots

Enumerated, not omitted: deck coverage gaps, warning-level LVS findings (and one non-warning LVS mismatch), uncombined evidence legs, and modelled-but-not-extracted items.

- Comparator RESET-integrity defect (FIXED by issue #175 / DR-004 Amendment A, kept here as history, not a live gap). Through PR #176, `design/comparator.sch`'s outputs separated to the rails DURING the CLK=0 reset phase at 3 of 9 ratified corner points with the inputs shorted to the common mode (Vindiff = 0 mV negative control), because the cross-coupled NMOS latch pair's sources were tied directly to GND and therefore conducted throughout reset, in opposition to the reset PMOS pair -- an unstable equilibrium that amplified corner/temperature asymmetry to a decision before the clock edge arrived. Issue #175 moved those sources onto the input pair's own precharged drain nodes (DIP/DIN), closing the DC path and the amplification mechanism: the re-run campaign (`sim/comparator-decision/records/20260906-074451-7724af3.md`) shows 9/9 reset-integrity controls HELD and 0.00 uA reset-phase static current at every corner. No ADC-level transient has ever exercised the real comparator inside the full hierarchy (the sequencer campaign is behavioural; the ENOB estimate composes a noise term rather than simulating the latch) -- still true post-fix, and still why a defect of this kind could recur undetected by those two campaigns alone.
- Comparator noise methodology is a REDUCED SUB-MODEL (the input pair's own precharged drain-node PMOS pair diode-connected as loads, cross-coupled latch pairs omitted) -- excludes the latch's own regenerative-phase noise contribution. Carried unchanged (as a methodology limitation) into the ratified corner campaign and into the ENOB composite, across the issue #175 topology amendment. See DR-004.
- ENOB is a behavioral-accelerated composite, not a dynamic-test (FFT) measurement: it excludes settling, slewing, aperture jitter and reference droop; treats CDAC INL as an rms noise-like term rather than input-correlated distortion; and deliberately excludes comparator offset.
- Comparator/ADC offset has no numeric spec row (ratified or DRAFT). `sim/comparator-decision/`'s offset Monte Carlo (N=24, `tt_mm`, seed=1) is a distribution-only characterization with no `klt yield` pass/fail step -- a limit-less measurement is a `klt yield` input error by design, per sim/README.md.
- Both statistical-row Monte Carlo campaigns (CDAC N=40, comparator offset N=24) are sized only for a distribution-SHAPE claim (~10-15% relative standard error on the estimated stdev), not for a tight yield-fraction claim at 95% confidence -- `klt yield`'s own sample-size verdict on the CDAC measurements is 'insufficient' (5547 samples needed for `dnl_max_lsb`, 2666 for `inl_max_lsb`, at +-0.01). Neither campaign's `klt yield` report declares a `negative_control` (the harness-level negative control described in each record's own 'Negative control' section is separate from, and does not substitute for, this `klt yield`-level declaration).
- `dnl_max_lsb`'s N=40 sample set fails an Anderson-Darling normality check (A2*=0.9079 > 0.787) in its `klt yield` report -- the parametric yield/Cpk figures for that measurement are indicative only; this report cites the empirical estimate.
- SAR sequencer layout LVS does **NOT** match (`layout/sar-sequencer/reports/20260825-124031-1a2f7c1/record.md`): device counts match exactly (760/760) but net/device correspondence resolves 0/0, due to a known `klt extract` pin/net-name-promotion bug on OpenROAD DEF->GDS-merged layouts (filed generically upstream). DRC is clean. A real, outstanding LVS gap for one of five layout sub-blocks -- not a warning-level nit.
- Comparator layout LVS is now a MISMATCH against the current schematic (as of issue #175 / DR-004 Amendment A's topology change) -- `reports/LATEST` still records a genuine match, but that was against the pre-amendment 9-device topology. The drawn geometry has not been updated: it still implements 9 devices where the schematic now has 11 (the two DIP/DIN precharge PMOS are not drawn), confirmed via a falsifiability control that reproduces the old match against the superseded reference and a genuine mismatch (8 unmatched devices) against the amended one -- `layout/comparator/reports/20260906-064104-eedd532/`. Re-drawing the block is tracked as issue #180, not bundled into #175's topology fix. See `layout/comparator/README.md`'s status section.
- Uncombined evidence legs: `sim/sampling-frontend/` and `sim/sampling-cdac-handoff/` (interface-correctness diagnostics for the sampling front end <-> CDAC handoff) are not run at the full ratified corner set -- mostly tt/27C/1.8V only, with a single `ss`-corner point run as a directional (non-gating) check that exceeded half an LSB. Neither carries a `spec/target-spec.md#...` `Claim` of its own, so neither is cited against any row above; both remain load-bearing supporting evidence for the front-end/CDAC interface design that has not been folded into a spec-row corner campaign.
- `V_REF` is asserted, not simulated: DR-003's own scope table treats it as a fixed design constant. No record measures a reference-generator circuit's own tolerance (none is ratified).
- Layout evidence cited by this report (sampling-cap row, and the LVS findings above) has no append-only 'Supersedes' convention the way `sim/` does (sim/README.md). This report's mechanical freshness check (see sim/report/generate.py) therefore covers only the `sim/` citations; layout citations are pinned to the specific report-directory path shown and are not automatically re-resolved to 'latest'. Documented gap, not silently assumed current.

## No-grant statement

This report records **no grant**. `2AMLogic/product/everyblock/grants.md` is
the authoritative ledger for tier grants (T1/T2/...) and is maintained by
the operator; nothing in this file should be read as, or substituted for,
that ledger. This report aggregates evidence records and their verdicts
only.


---

Generated by `sim/report/generate.py` from `sim/report/manifest.py` and the evidence records it cites. Append-only evidence convention: `sim/README.md`. Freshness check: `check_freshness()` in `sim/report/generate.py`.

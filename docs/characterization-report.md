# sky130-sar-adc — Characterization Report

Aggregated, generated artifact tying every `spec/target-spec.md` Target-table row's verdict to the specific evidence record(s) it rests on, per `klayout-tools/docs/design-evidence-tiers.md` item 8 (T1 item 8, tracked in issue #30, part of #23). Every row appears, including rows that fail or are unmeasured -- coverage honesty is part of the claim.

**Do not hand-edit this file.** Regenerate it with `python3 sim/report/generate.py --write` after any `sim/` or `layout/` evidence changes, and re-run `python3 sim/report/generate.py --check` (wired into `npm run check:ci` as `npm run check:report`) before committing -- it fails if a cited record has been superseded, if a citation path no longer exists, or if this file has drifted from what the current records/manifest would regenerate.

## Coverage summary

| Spec row | Status | Verdict | Evidence |
|---|---|---|---|
| Architecture | DRAFT | N/A (DRAFT, descriptive row) | (none -- see detail below) |
| Resolution `N` | RATIFIED | PASS (9/9 corners) | 1 record(s), see detail below |
| Sample rate | DRAFT | UNMEASURED | (none -- see detail below) |
| ENOB | DRAFT (target value) | DOES NOT MEET the DRAFT baseline target (>9.0 bit), informationally: 8.491 bit (mean-case CDAC mism… | 1 record(s), see detail below |
| INL / DNL | DRAFT (target value) | DOES NOT MEET the DRAFT target (<= +-1 LSB, target_yield=0.99), informationally: empirical yield 0.… | 2 record(s), see detail below |
| `V_REF` | RATIFIED | PASS (structural + functional/monotonicity check, 9/9 corners) | 1 record(s), see detail below |
| LSB (differential) | RATIFIED | PASS (structural + functional/monotonicity check, 9/9 corners) | 1 record(s), see detail below |
| Sampling cap (CDAC unit × array) | RATIFIED | PASS (sim structural check, 9/9 corners) + PASS (layout: DRC clean, LVS match, unit-cap count 1024… | 2 record(s), see detail below |
| Comparator input-referred noise | RATIFIED | PASS vs. baseline (<=1.0148 mV rms) at every corner, binding corner `tt_125c_1.80v` = 0.9591 mV rms… | 1 record(s), see detail below |
| Power | DRAFT | UNMEASURED | (none -- see detail below) |
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
- **Conditions**: N/A -- no campaign has been run.
- **Verdict**: UNMEASURED
- **Notes**: No switch-R_on/settling-time campaign exists under sim/. It needs a CDAC/switch netlist and a dedicated corner campaign; the completed corner campaigns (issue #28) covered the RATIFIED deterministic rows (V_REF/LSB/N/sizing/comparator noise), not sample rate. Named as open work by spec/target-spec.md's own 'Not ratified by this record' list (#24/#28).


### ENOB

- **Status**: DRAFT (target value)
- **Conditions**: Behavioral-accelerated composite (NOT a dynamic-test/FFT measurement): comparator noise term taken from the RATIFIED full-PVT corner campaign's worst-case binding corner (`tt_125c_1.80v`, not re-simulated); CDAC mismatch nonlinearity from a `tt_mm` Monte Carlo campaign, N=40, base seed=1 (draws seed..seed+N-1), PVT point tt/27C/1.8V; kT/C sampling noise analytic at the 125 C worst case; quantization noise analytic (LSB/sqrt(12)).
- **Verdict**: DOES NOT MEET the DRAFT baseline target (>9.0 bit), informationally: 8.491 bit (mean-case CDAC mismatch) / 7.749 bit (worst-case). Target not ratified -- not a pass/fail against a ratified line.
- **Notes**: Excludes dynamic effects (settling, slewing, aperture jitter, reference droop -- needs a future top-level transient/FFT campaign), treats CDAC INL as an rms noise-like term rather than input-correlated distortion, reuses the comparator's REDUCED SUB-MODEL noise figure, and deliberately excludes comparator offset. See the cited record's own LIMITATIONS field for the full list.

**Evidence:**

- `sim/enob-estimate/records/20260828-005033-0c70212.md` (Record ID `20260828-005033-0c70212`, Supersedes: (none))
  - Result: Measured value(s): achieved ENOB (mean-case CDAC mismatch) = **8.491 bit**; achieved ENOB (worst-case CDAC mismatch) = **7.749 bit** -- both against the DRAFT target row `> 9.0` (baseline) / `> 9.5` (stretch), reported INFORMATIONALLY, not as pass/fail against a ratified line.
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
- **Conditions**: Full ratified corner set, 9 OAT points, `ac-based` noise methodology, integration bandwidth 1 kHz - 1 GHz. REDUCED SUB-MODEL (cross-coupled latch pair replaced by diode-connected loads, CLK held at VDD) -- named, flagged simplification, see spec/decision-records/DR-004-comparator-topology-and-noise-budget.md.
- **Verdict**: PASS vs. baseline (<=1.0148 mV rms) at every corner, binding corner `tt_125c_1.80v` = 0.9591 mV rms; does NOT meet the stretch threshold (<=0.5859 mV rms) at the binding corner.

**Evidence:**

- `sim/comparator-decision/records/20260827-212404-e13bc1e.md` (Record ID `20260827-212404-e13bc1e`, Supersedes: (none))
  - Overall: PASS vs. the ratified baseline threshold (1.0148 mV rms); does NOT meet the stretch threshold (0.5859 mV rms) at the binding corner.
  - Corner matrix run: process=['ff', 'fs', 'sf', 'ss', 'tt'], temperature_c=[-40, 27.0, 125], supply_v=[1.62, 1.8, 1.98] (9 points, one-at-a-time per sim/README.md)
  - Claim: `spec/target-spec.md#numeric-rows--ratified-2026-08-19` -- Comparator input-referred noise `<=1.0148 mV rms` (baseline, ENOB>9.0) / `<=0.5859 mV rms` (stretch, ENOB>9.5) (RATIFIED, DR-003 via #27). Measures design/compa…

### Power

- **Status**: DRAFT
- **Conditions**: N/A -- no full-block power campaign exists.
- **Verdict**: UNMEASURED
- **Notes**: One unrelated, non-gating data point exists outside sim/'s evidence trail: `layout/sar-sequencer/reports/20260825-124031-1a2f7c1/record.md`'s OpenROAD PnR estimate for the digital SAR-sequencer sub-block ONLY (0.0155 mW) -- a static EDA-tool estimate, not a simulated/measured full-ADC number, and not tied to the ratified corner set. Cited for completeness, not as spec-row evidence.


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
- `sim/comparator-decision/records/20260827-212404-e13bc1e.md` (Record ID `20260827-212404-e13bc1e`, Supersedes: (none))
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

- Comparator noise methodology is a REDUCED SUB-MODEL (cross-coupled latch pair replaced by diode-connected loads) -- excludes the latch's own regenerative-phase noise contribution. Carried unchanged into the ratified corner campaign and into the ENOB composite. See DR-004.
- ENOB is a behavioral-accelerated composite, not a dynamic-test (FFT) measurement: it excludes settling, slewing, aperture jitter and reference droop; treats CDAC INL as an rms noise-like term rather than input-correlated distortion; and deliberately excludes comparator offset.
- Comparator/ADC offset has no numeric spec row (ratified or DRAFT). `sim/comparator-decision/`'s offset Monte Carlo (N=24, `tt_mm`, seed=1) is a distribution-only characterization with no `klt yield` pass/fail step -- a limit-less measurement is a `klt yield` input error by design, per sim/README.md.
- Both statistical-row Monte Carlo campaigns (CDAC N=40, comparator offset N=24) are sized only for a distribution-SHAPE claim (~10-15% relative standard error on the estimated stdev), not for a tight yield-fraction claim at 95% confidence -- `klt yield`'s own sample-size verdict on the CDAC measurements is 'insufficient' (5547 samples needed for `dnl_max_lsb`, 2666 for `inl_max_lsb`, at +-0.01). Neither campaign's `klt yield` report declares a `negative_control` (the harness-level negative control described in each record's own 'Negative control' section is separate from, and does not substitute for, this `klt yield`-level declaration).
- `dnl_max_lsb`'s N=40 sample set fails an Anderson-Darling normality check (A2*=0.9079 > 0.787) in its `klt yield` report -- the parametric yield/Cpk figures for that measurement are indicative only; this report cites the empirical estimate.
- SAR sequencer layout LVS does **NOT** match (`layout/sar-sequencer/reports/20260825-124031-1a2f7c1/record.md`): device counts match exactly (760/760) but net/device correspondence resolves 0/0, due to a known `klt extract` pin/net-name-promotion bug on OpenROAD DEF->GDS-merged layouts (filed generically upstream). DRC is clean. A real, outstanding LVS gap for one of five layout sub-blocks -- not a warning-level nit.
- Comparator layout LVS is a genuine MATCH but carries one warning-severity finding ('device class has no counterpart on the other side, but no devices of this class were extracted either -- not a real topology mismatch', error_count=0) -- noted for completeness, not gating.
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

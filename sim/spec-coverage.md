<!-- GENERATED FILE -- do not edit by hand.
     Source of truth: sim/spec-coverage.json
     Regenerate:      python3 sim/check_spec_coverage.py --render
     Checked by:      npm run check:spec-coverage (part of npm run check:ci) -->

# Spec-row coverage index

Which `spec/target-spec.md` row is addressed by which committed testbench, which evidence record it rests on, and the exact command a third party runs to reproduce it. This answers "is this row addressed?" without reading every directory under `sim/`.

Generated from `sim/spec-coverage.json` and enforced by `sim/check_spec_coverage.py` (T1 item 9: testbench completeness, cold-start invocation, pinned PDK revision). A claimed spec row with no bench fails the check; so does a stale copy of this file.

## Cold start

One-time machine bootstrap: `docs/environment-setup.md` sections 1-3. Then, from the repo root:

```sh
# One-time machine bootstrap: docs/environment-setup.md sections 1-3
#   (xschem + ngspice + volare install, `volare enable` of the pinned
#    open_pdks commit, PDK_ROOT/PDK convention).
source sim/env.sh
python3 sim/run_corners.py --check-env   # exit 3 = tools/PDK missing, 1 = pin drifted
```

followed by the per-bench command in the table below. Each of those commands is checked to appear verbatim in the file named under "documented in", to use only flags its runner actually accepts, and to name the same script the record's own `Written by` footer names.

## Coverage summary

| Spec row | Status | Coverage | Testbench(es) | Evidence record(s) |
|---|---|---|---|---|
| Architecture | DRAFT | benched (structural row, exercised block by block) | `sim/sampling-frontend`<br>`sim/sampling-cdac-handoff`<br>`sim/cdac-array-transfer`<br>`sim/sar-sequencer-behavioral` | `20260821-072657-433a294.md`<br>`20260824-231304-144edeb.md`<br>`20260821-062504-433a294.md`<br>`20260823-152752-47640c8.md` |
| Resolution `N` | RATIFIED | benched (ratified, graded pass/fail) | `sim/sar-sequencer-behavioral` | `20260827-211956-e13bc1e.md` |
| Sample rate | DRAFT | benched (DRAFT row, evidence informational) | `sim/cdac-bit-trial-settling`<br>`sim/sequencer-logic-delay`<br>`sim/sampling-acquisition-settling`<br>`sim/vcm-drive-budget`<br>`sim/full-conversion-transient` | `20260907-013225-5f176a6.md`<br>`20260906-230516-0904419.md`<br>`20260908-051436-6ccd72d.md`<br>`20260908-100413-f3e2914.md`<br>`20260912-002315-9aaf1ca.md` |
| ENOB | DRAFT | benched (DRAFT row, evidence informational) | `sim/enob-estimate` | `20260828-005033-0c70212.md` |
| INL / DNL | DRAFT | benched (DRAFT row, evidence informational) | `sim/cdac-array-transfer` | `20260828-005006-0c70212.md` |
| `V_REF` | RATIFIED | benched (ratified, graded pass/fail) | `sim/cdac-array-transfer` | `20260827-213107-e13bc1e.md` |
| LSB (differential) | RATIFIED | benched (ratified, graded pass/fail) | `sim/cdac-array-transfer` | `20260827-213107-e13bc1e.md` |
| Sampling cap (CDAC unit × array) | RATIFIED | benched (ratified, graded pass/fail) | `sim/cdac-array-transfer` | `20260827-213107-e13bc1e.md` |
| Comparator input-referred noise | RATIFIED | benched (ratified, graded pass/fail) | `sim/comparator-decision` | `20260827-212404-e13bc1e.md` |
| Kickback | DRAFT | benched (DRAFT row, evidence informational) | `sim/comparator-decision` | `20260925-050027-0259924.md` |
| Power | DRAFT | benched (DRAFT row, evidence informational) | `sim/full-conversion-transient`<br>`sim/supply-impedance-sensitivity` | `20260912-002315-9aaf1ca.md`<br>`20260925-073912-0e385e5.md` |
| Corners | RATIFIED | benched (methodology row, evidenced by the campaigns that ran it) | `sim/sar-sequencer-behavioral`<br>`sim/cdac-array-transfer`<br>`sim/comparator-decision` | `20260827-211956-e13bc1e.md`<br>`20260827-213107-e13bc1e.md`<br>`20260827-212404-e13bc1e.md` |

## Per-row detail

### Architecture

- **Status**: DRAFT
- **Claim class**: `structural`
- **Note**: A topology statement (charge-redistribution, differential, top-plate sampling), not a measured quantity: it is realized in design/ and kept honest by design/regen_netlist.sh --check (staleness is failure). The benches below exercise the topology block by block -- none of them asserts a numeric spec value, and none is listed under a numeric row.

**`sim/sampling-frontend`** — Top-plate sampling: in-sample settling and the post-edge delta on TOP_P/TOP_N (issue #52).

- Testbench: `sim/sampling-frontend/testbench/sampling_frontend_dut.spice`
- Runner: `sim/sampling-frontend/run_transient.py`
- Cold start: `python3 sim/sampling-frontend/run_transient.py --record`
- Documented in: `sim/sampling-frontend/run_transient.py`
- Evidence: `sim/sampling-frontend/records/20260821-072657-433a294.md`

**`sim/sampling-cdac-handoff`** — The front-end/array bottom-plate interface as design/sar_adc_top.sch actually wires it (issue #95).

- Testbench: `sim/sampling-cdac-handoff/testbench/sampling_frontend_dut.spice`, `sim/sampling-cdac-handoff/testbench/cdac_array_dut.spice`
- Runner: `sim/sampling-cdac-handoff/run_handoff.py`
- Cold start: `python3 sim/sampling-cdac-handoff/run_handoff.py --record`
- Documented in: `sim/sampling-cdac-handoff/run_handoff.py`
- Evidence: `sim/sampling-cdac-handoff/records/20260824-231304-144edeb.md`

**`sim/cdac-array-transfer`** — Charge redistribution: the array's own code-to-output transfer characteristic (issue #53).

- Testbench: `sim/cdac-array-transfer/testbench/tb_cdac_array_transfer.spice`
- Runner: `sim/cdac-array-transfer/run_transfer.py`
- Cold start: `python3 sim/cdac-array-transfer/run_transfer.py --record`
- Documented in: `sim/cdac-array-transfer/README.md`
- Evidence: `sim/cdac-array-transfer/records/20260821-062504-433a294.md`

**`sim/sar-sequencer-behavioral`** — Successive approximation: MSB-first bit-by-bit search and phase sequencing (issue #55).

- Testbench: `sim/sar-sequencer-behavioral/testbench/sar_sequencer_tb_fragment.spice`
- Runner: `sim/sar-sequencer-behavioral/run_testbench.py`
- Cold start: `python3 sim/sar-sequencer-behavioral/run_testbench.py --record`
- Documented in: `sim/sar-sequencer-behavioral/run_testbench.py`
- Evidence: `sim/sar-sequencer-behavioral/records/20260823-152752-47640c8.md`

### Resolution `N`

- **Status**: RATIFIED
- **Claim class**: `ratified-measured`
- **Note**: N = 10 bit, RATIFIED (DR-003 via #27). Graded by issue #28's full ratified-corner campaign: correct MSB-first capture of all 10 bits, correct phase sequencing, and the ring sequencer's auto-restart at every point of the ratified corner set.

**`sim/sar-sequencer-behavioral`** — Ratified N=10 across the full ratified corner set (issue #28).

- Testbench: `sim/sar-sequencer-behavioral/testbench/sar_sequencer_tb_fragment.spice`
- Runner: `sim/sar-sequencer-behavioral/run_testbench.py`
- Cold start: `python3 sim/sar-sequencer-behavioral/run_testbench.py --corners --record`
- Documented in: `sim/sar-sequencer-behavioral/run_testbench.py`
- Evidence: `sim/sar-sequencer-behavioral/records/20260827-211956-e13bc1e.md`

### Sample rate

- **Status**: DRAFT
- **Claim class**: `draft-informational`
- **Note**: DRAFT row (provisional 100 kS/s-1 MS/s), NOT re-derived and NOT closed by anything indexed here. This row was claim_class 'unbenched' until issue #274, on the reason that benching it 'needs a switch-R_on/settling campaign against the integrated signal path'. That campaign has since been run, in pieces: the benches below are the settling/delay mechanism campaigns docs/chipalooza/challenge-4-proposal.md Section 7 Item 2 names, plus the end-to-end whole-ADC transient that Section 7's own summary says a future decision record needs BEFORE the row can be re-derived. So the reason no longer describes the tree, and the evidence is indexed rather than left orphaned -- but the class is 'draft-informational' for the same standard the ENOB and INL/DNL rows are held to: every record below is reported INFORMATIONALLY, each one states in its own Claim field that it is not graded against a ratified row, and not one of them proposes a sample rate. The DR-006 phase budgets they measure against are themselves downstream of this DRAFT row, so they bound mechanisms, they do not close the row. Section 7 Item 2 stays open; a future decision record still ratifies the number first.
- **Tracking**: #24 (CDAC/switch netlist), docs/chipalooza/challenge-4-proposal.md Section 7 Item 2 (end-to-end rate still unmeasured) and Item 6 (no on-chip VCM buffer exists for the budget below to size), and the future sample-rate decision record

**`sim/cdac-bit-trial-settling`** — Mechanism (a) of Section 7 Item 2: how long the CDAC array's own bottom-plate switch network takes to settle the shared top-plate node after one bit's SEL toggles, over the full ratified corner set. Informational against this DRAFT row -- it is compared to the DR-006-derived phase period, which is itself downstream of this row, and proposes no sample rate.

- Deck note: No committed deck of its own: the runner states a single-side, single-free-bit reduction of design/cdac/cdac_array.sch in-line (see its module docstring's METHOD section for why no existing regenerated fragment isolates that topology), at the schematic's own W/L/MF values. Each corner's assembled deck is committed as raw evidence under sim/cdac-bit-trial-settling/corners/.
- Runner: `sim/cdac-bit-trial-settling/run_bit_trial_settling.py`
- Cold start: `python3 sim/cdac-bit-trial-settling/run_bit_trial_settling.py --corners --record`
- Documented in: `sim/cdac-bit-trial-settling/run_bit_trial_settling.py`
- Evidence: `sim/cdac-bit-trial-settling/records/20260907-013225-5f176a6.md`

**`sim/sequencer-logic-delay`** — Mechanism (c) of Section 7 Item 2: the SAR sequencer's own CLK-to-phase-output logic delay across all 11 ring-sequencer phase transitions, over the full ratified corner set. Informational against this DRAFT row, on the same DR-006-downstream yardstick; proposes no sample rate.

- Deck note: No committed deck of its own: the runner xschem-netlists design/sar_sequencer.sch fresh on each invocation (the DUT netlist sha256 in every record is that netlist's hash) and wraps it in the stimulus stated in-line, reusing sim/sar-sequencer-behavioral/testbench/sar_sequencer_tb_fragment.spice's own probe-time convention. Each corner's assembled deck is committed under sim/sequencer-logic-delay/corners/.
- Runner: `sim/sequencer-logic-delay/run_sequencer_logic_delay.py`
- Cold start: `python3 sim/sequencer-logic-delay/run_sequencer_logic_delay.py --corners --record`
- Documented in: `sim/sequencer-logic-delay/run_sequencer_logic_delay.py`
- Evidence: `sim/sequencer-logic-delay/records/20260906-230516-0904419.md`

**`sim/sampling-acquisition-settling`** — Mechanism (d) of Section 7 Item 2: how close the bootstrapped sampling switch gets to a new worst-case (rail-to-rail differential) input by the end of the DR-006 worst-case acquisition window, over the full ratified corner set. This is the mechanism that did NOT clear that budget before issue #236 and does after; the record reports that informationally against a provisional-LSB reference scale, not as pass/fail against this DRAFT row.

- Testbench: `sim/sampling-frontend/testbench/sampling_frontend_dut.spice`
- Deck note: Reuses the sampling front end's own committed DUT fragment unmodified, read in place rather than duplicated (the same convention sim/sampling-frontend/run_hold_kick.py set); only the stimulus and the .meas set are stated by the runner.
- Runner: `sim/sampling-acquisition-settling/run_acquisition_settling.py`
- Cold start: `python3 sim/sampling-acquisition-settling/run_acquisition_settling.py --corners --record`
- Documented in: `sim/sampling-acquisition-settling/run_acquisition_settling.py`
- Evidence: `sim/sampling-acquisition-settling/records/20260908-051436-6ccd72d.md`

**`sim/vcm-drive-budget`** — The interface precondition on mechanism (d): how much external VCM drive resistance (and how much on-die decoupling) the front end tolerates while still acquiring within the DR-006 windows this DRAFT row derives, over the full ratified corner set. Indexed here -- rather than under a row of its own -- because it measures the SAME quantity as the bench above (differential sampled-value error at the end of the acquisition window) with the VCM drive made non-ideal, and its yardstick windows come from this row; Section 7 Item 6 is explicit that it quantifies rather than closes its gap, and it proposes no sample rate and edits no spec row. The cited record is the post-issue-#236 bare-R_source full-grid leg; the other three legs (legacy window, and C_decouple at both windows) are separate records in the same directory, cited in Section 7 Item 6.

- Testbench: `sim/sampling-frontend/testbench/sampling_frontend_dut.spice`
- Deck note: Same unmodified sampling front-end DUT fragment as the bench above, read in place; the runner replaces only that deck's ideal Vvcm source with an ideal source in series with the swept R_source (plus optional C_decouple).
- Runner: `sim/vcm-drive-budget/run_vcm_drive_budget.py`
- Cold start: `python3 sim/vcm-drive-budget/run_vcm_drive_budget.py --corners --record`
- Documented in: `sim/vcm-drive-budget/run_vcm_drive_budget.py`
- Evidence: `sim/vcm-drive-budget/records/20260908-100413-f3e2914.md`

**`sim/full-conversion-transient`** — The only campaign that drives the whole transistor-level design/sar_adc_top.spice through complete conversions, at the DR-006 worst-case f_clk = 12 MHz, over the full ratified corner set -- the end-to-end data Section 7 Item 2 says a future decision record needs before this row can be re-derived. The cited record's own verdict is FAIL against its own informational criterion (0/9 corners resolve all 5 inputs to their ideal code within +-1 LSB, though the 12-period phase structure is correct at 5/5 conversions everywhere); that is recorded as-is, and is not a pass/fail verdict against this DRAFT row, which the record explicitly declines to substantiate.

- Testbench: `design/sar_adc_top.spice`, `sim/full-conversion-transient/testbench/full_conversion_tb_fragment.spice`
- Runner: `sim/full-conversion-transient/run_conversion.py`
- Cold start: `python3 sim/full-conversion-transient/run_conversion.py --corners --record`
- Documented in: `sim/full-conversion-transient/README.md`
- Evidence: `sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md`

### ENOB

- **Status**: DRAFT
- **Claim class**: `draft-informational`
- **Note**: DRAFT target value (> 9.0 bit baseline / > 9.5 stretch). Issue #29's behavioral-accelerated estimate composes already-run evidence (comparator noise from #28's corner campaign, CDAC mismatch from the DNL/INL campaign below, plus analytic quantization and kT/C terms); it is reported INFORMATIONALLY against the DRAFT target and explicitly is NOT a dynamic-test (FFT) measurement -- see the record's own LIMITATIONS field.

**`sim/enob-estimate`** — Composed ENOB estimate against the DRAFT ENOB row (issue #29).

- Deck note: Composite/derived experiment: no new ngspice deck is executed. Its inputs are the two SPICE-backed records named in its Composite-inputs manifest (comparator-decision, cdac-array-transfer), each of which ships its own committed deck under this index.
- Runner: `sim/enob-estimate/run_enob.py`
- Cold start: `python3 sim/enob-estimate/run_enob.py --cdac-mc-record 20260828-005006-0c70212 --record`
- Documented in: `sim/enob-estimate/run_enob.py`
- Evidence: `sim/enob-estimate/records/20260828-005033-0c70212.md`

### INL / DNL

- **Status**: DRAFT
- **Claim class**: `draft-informational`
- **Note**: DRAFT target value (<= +-1 LSB). Issue #29's mismatch Monte Carlo campaign over the CDAC array's own transfer characteristic, reported in ratified-LSB units with a zero-stdev negative control, INFORMATIONALLY against the DRAFT target. Scope is the array in isolation, stated in the record itself.

**`sim/cdac-array-transfer`** — max|DNL| / max|INL| distributions at tt_mm with a plain-tt negative control (issue #29).

- Testbench: `sim/cdac-array-transfer/testbench/tb_cdac_array_transfer.spice`
- Deck note: The Monte Carlo code set is generated by sim/cdac-array-transfer/gen_fragment.py, verified byte-for-byte against this committed hand-authored deck for its own 5 codes by sim/tests/test_cdac_fragment_gen.py.
- Runner: `sim/cdac-array-transfer/run_mc.py`
- Cold start: `python3 sim/cdac-array-transfer/run_mc.py --n 40 --seed 1 --record`
- Documented in: `sim/cdac-array-transfer/README.md`
- Evidence: `sim/cdac-array-transfer/records/20260828-005006-0c70212.md`

### `V_REF`

- **Status**: RATIFIED
- **Claim class**: `ratified-measured`
- **Note**: V_REF = V_DD = 1.8 V, RATIFIED (DR-003 via #27). A fixed design constant wired into the testbench as VREFP={vdd_val} rather than a free-running simulated quantity; the campaign below grades the consequences (structural sizing, monotonicity, polarity) across the full ratified corner set.

**`sim/cdac-array-transfer`** — Ratified V_REF / LSB / CDAC sizing campaign across the full ratified corner set (issue #28).

- Testbench: `sim/cdac-array-transfer/testbench/tb_cdac_array_transfer.spice`
- Runner: `sim/cdac-array-transfer/run_transfer.py`
- Cold start: `python3 sim/cdac-array-transfer/run_transfer.py --ratified-record`
- Documented in: `sim/cdac-array-transfer/README.md`
- Evidence: `sim/cdac-array-transfer/records/20260827-213107-e13bc1e.md`

### LSB (differential)

- **Status**: RATIFIED
- **Claim class**: `ratified-measured`
- **Note**: LSB = 2*V_REF/2^N = 3.5156 mV, RATIFIED (DR-003 via #27). Derived from V_REF and N, so it is graded by the same campaign record as V_REF -- one run, three ratified rows, each named explicitly in that record rather than left implicit.

**`sim/cdac-array-transfer`** — Ratified V_REF / LSB / CDAC sizing campaign across the full ratified corner set (issue #28).

- Testbench: `sim/cdac-array-transfer/testbench/tb_cdac_array_transfer.spice`
- Runner: `sim/cdac-array-transfer/run_transfer.py`
- Cold start: `python3 sim/cdac-array-transfer/run_transfer.py --ratified-record`
- Documented in: `sim/cdac-array-transfer/README.md`
- Evidence: `sim/cdac-array-transfer/records/20260827-213107-e13bc1e.md`

### Sampling cap (CDAC unit × array)

- **Status**: RATIFIED
- **Claim class**: `ratified-measured`
- **Note**: C_u ~= 8.65 fF, 2^9 = 512 positions/side, RATIFIED (DR-003 via #27). Graded structurally (the deck's own device sizing and array population) plus functionally (monotonicity and polarity) at every point of the ratified corner set.

**`sim/cdac-array-transfer`** — Ratified V_REF / LSB / CDAC sizing campaign across the full ratified corner set (issue #28).

- Testbench: `sim/cdac-array-transfer/testbench/tb_cdac_array_transfer.spice`
- Runner: `sim/cdac-array-transfer/run_transfer.py`
- Cold start: `python3 sim/cdac-array-transfer/run_transfer.py --ratified-record`
- Documented in: `sim/cdac-array-transfer/README.md`
- Evidence: `sim/cdac-array-transfer/records/20260827-213107-e13bc1e.md`

### Comparator input-referred noise

- **Status**: RATIFIED
- **Claim class**: `ratified-measured`
- **Note**: <= 1.0148 mV rms baseline / <= 0.5859 mV rms stretch, RATIFIED (DR-003 via #27). Graded against the ratified baseline threshold across the full ratified corner set, with the binding (worst-case) corner named explicitly in the record even though the row passes.

**`sim/comparator-decision`** — AC .noise input-referred noise across the full ratified corner set (issue #28).

- Testbench: `sim/comparator-decision/testbench/comparator_core.spice`
- Runner: `sim/comparator-decision/run.py`
- Cold start: `python3 sim/comparator-decision/run.py noise-corners --record`
- Documented in: `sim/comparator-decision/run.py`
- Evidence: `sim/comparator-decision/records/20260827-212404-e13bc1e.md`

### Kickback

- **Status**: DRAFT
- **Claim class**: `draft-informational`
- **Note**: DRAFT row (<= 5 mV peak pin disturbance into a 1 kOhm series source impedance, single decision edge; stretch <= 2 mV), added by DR-011 via issue #361. The bound is adopted verbatim from the sibling 2AMLogic/sky130-comparator canary's own DR-002-ratified row as a stated interim choice -- NOT derived from this block's system-level budget -- so nothing here is graded pass/fail against it. Issue #346's single-corner (tt/27 C) probe is still the only corner covered: the record below reports 73.3673 mV worst-case peak pin disturbance INFORMATIONALLY and says so in its own Claim field, which cites spec/target-spec.md explicitly. That is ~14.7x the proposed target; the gap is recorded, not relaxed (CLAUDE.md). Issue #390 (DR-014's first gate) has since split that disturbance into its common-mode and differential components at the same corner: the differential part -- the part a differential top-plate CDAC does not reject, i.e. the part that lands on a decision -- is 10.9153 mV at Vindiff=+50 mV (~2.2x the proposed target) and 4.1918 mV at the half-LSB overdrive a marginal SAR decision actually presents (~0.84x the target, ~2.1x the stretch). So the row is missed on the quantity it bounds, and the decision-relevant component is a much smaller multiple of it than 14.7x -- but is not negligible either, which is what DR-014 Consequences §4 said would decide whether its 'no mitigation adopted' disposition weakens. Ratifying this row would oblige a full-corner campaign -- the bound is stated at the ratified corner set and the evidence covers one point of it (DR-011 Consequences §5).
- **Tracking**: DR-014 (#349: static preamp not adopted, DR-004 Decision 1 stands, no mitigation adopted yet); #390 (common-mode/differential split of the kickback measurement, DR-014's first gate -- DELIVERED by the record below, which supersedes #346's baseline; confirms a differential component above the bound at the large-overdrive point, DR-014 Consequences §4's condition); #434 (follow-on: measuring the headroom-neutral mitigation classes DR-014 Consequences §4 / Open items names, filed once #390's result met that condition); DR-011's Open items (a budget-derived successor bound, a residual-at-next-decision measurable, and the full-corner kickback campaign ratification would require)

**`sim/comparator-decision`** — Peak pin disturbance on VINP/VINN across a single CLK reset->evaluate edge, into a 1 kOhm series source impedance, at tt/27 C (issue #346), plus -- since issue #390, DR-014's first gate -- the common-mode/differential decomposition of the same disturbance and later recovery pick-offs of both, over a Vindiff grid that now includes the half-LSB (1.7578 mV) point. The per-pin peak the row's bound is stated in is unchanged and reproduces exactly (73.3673 mV at Vindiff=+50 mV; -70.3419 mV at the Vindiff=0 control). The decomposition is what says how much of that lands on a decision: at Vindiff=0 the deck is symmetric so the disturbance is common-mode by construction, and the measured common-mode part barely moves with overdrive (-70.3419 -> -70.4415 mV), while the differential part is -10.9153 mV at Vindiff=+50 mV and +4.1918 mV at the half-LSB point. A subtraction between two per-pin rows is NOT that split and is no longer described as one.

- Testbench: `sim/comparator-decision/testbench/comparator_core.spice`
- Runner: `sim/comparator-decision/run.py`
- Cold start: `python3 sim/comparator-decision/run.py kickback --record`
- Documented in: `sim/comparator-decision/run.py`
- Evidence: `sim/comparator-decision/records/20260925-050027-0259924.md`

### Power

- **Status**: DRAFT
- **Claim class**: `draft-informational`
- **Note**: DRAFT row, target text 'provisional, minimise at rate' with the note 'report, don't pre-commit'. There is still no threshold to grade against, so nothing here is a pass/fail claim -- but 'report' is exactly what the bench below now does: issue #254's end-to-end campaign carries the first supply- and reference-current measurement of any kind on this block (per-rail `.meas tran avg i(...)` over a whole steady-state conversion, at every point of the ratified corner set). It is indexed here, informationally, rather than left orphaned. This row was claim_class 'unbenched' until issue #274; the stated reason (no bench exists, and a number with no ratified line to grade it against would be one CLAUDE.md forbids inventing) is why the class is 'draft-informational' rather than 'ratified-measured', and why no power target is proposed anywhere in this index or in the record. If a future decision record ratifies a power row, this index's ratified-row rule then requires a bench graded against it.
- **Tracking**: future power decision record (none open); docs/chipalooza/challenge-4-proposal.md Section 4's Power row carries the current reported figures

**`sim/full-conversion-transient`** — Average per-rail current and power (VDD, VPWR, VREFP, VCM, VREFN) over one whole steady-state conversion at f_clk = 12 MHz, across the full ratified corner set -- the same run that feeds the Sample rate row above. Reported, not pre-committed: the record names this DRAFT row explicitly and states that it substantiates neither it nor a proposed target.

- Testbench: `design/sar_adc_top.spice`, `sim/full-conversion-transient/testbench/full_conversion_tb_fragment.spice`
- Runner: `sim/full-conversion-transient/run_conversion.py`
- Cold start: `python3 sim/full-conversion-transient/run_conversion.py --corners --record`
- Documented in: `sim/full-conversion-transient/README.md`
- Evidence: `sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md`

**`sim/supply-impedance-sensitivity`** — Same per-rail average current/power as the bench above, but with DR-015's package-style R+L (or a lumped substrate stand-in) driving the four supply terminals instead of ideal sources at the die -- DR-012's own open item, issue #378, 'the impedance argument is unmeasured'. Baseline corner only (see the record's own Subset-corner justification); reported informationally, same as the row above, and no power target is proposed here either.

- Testbench: `design/sar_adc_top.spice`, `sim/full-conversion-transient/testbench/full_conversion_tb_fragment.spice`
- Runner: `sim/supply-impedance-sensitivity/run_supply_impedance.py`
- Cold start: `python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --arms ideal,package-r-only,package,substrate --record`
- Documented in: `sim/supply-impedance-sensitivity/README.md`
- Evidence: `sim/supply-impedance-sensitivity/records/20260925-073912-0e385e5.md`

### Corners

- **Status**: RATIFIED
- **Claim class**: `methodology`
- **Note**: -40/27/125 C, +-10 % supply, sky130 process corners, RATIFIED (DR-003 via #27). This row constrains how every other campaign runs rather than naming a DUT quantity, so its evidence is that the ratified-row campaigns below each state a Corner matrix run covering every sky130 process corner in sim/pdk.json and three points on each of the temperature and supply axes. sim/check_spec_coverage.py checks that SHAPE, not the numbers themselves -- the numbers live in the spec and in each record, and sim/harness/corners.py deliberately keeps spec values out of harness code.

**`sim/sar-sequencer-behavioral`** — Ratified corner set executed end to end (issue #28).

- Testbench: `sim/sar-sequencer-behavioral/testbench/sar_sequencer_tb_fragment.spice`
- Runner: `sim/sar-sequencer-behavioral/run_testbench.py`
- Cold start: `python3 sim/sar-sequencer-behavioral/run_testbench.py --corners --record`
- Documented in: `sim/sar-sequencer-behavioral/run_testbench.py`
- Evidence: `sim/sar-sequencer-behavioral/records/20260827-211956-e13bc1e.md`

**`sim/cdac-array-transfer`** — Ratified corner set executed end to end (issue #28).

- Testbench: `sim/cdac-array-transfer/testbench/tb_cdac_array_transfer.spice`
- Runner: `sim/cdac-array-transfer/run_transfer.py`
- Cold start: `python3 sim/cdac-array-transfer/run_transfer.py --ratified-record`
- Documented in: `sim/cdac-array-transfer/README.md`
- Evidence: `sim/cdac-array-transfer/records/20260827-213107-e13bc1e.md`

**`sim/comparator-decision`** — Ratified corner set executed end to end (issue #28).

- Testbench: `sim/comparator-decision/testbench/comparator_core.spice`
- Runner: `sim/comparator-decision/run.py`
- Cold start: `python3 sim/comparator-decision/run.py noise-corners --record`
- Documented in: `sim/comparator-decision/run.py`
- Evidence: `sim/comparator-decision/records/20260827-212404-e13bc1e.md`

## Harness proofs (never counted toward a spec row)

`sim/README.md` states these two experiments "will never substantiate a spec row". The check enforces it: each one's `tb.json` claim must start with `None`, and listing either as a bench for any row is a failure.

- **`sim/harness-corner-smoke`** — Harness self-test, never a spec claim (sim/README.md 'Harness self-test experiments'): an ideal divider plus a diode-connected nfet_01v8, proving the corner runner actually switches the .lib process section, .temp and vdd_val independently. Counted toward T1 item 9 by nothing.
- **`sim/mc-smoke`** — Harness self-test, never a spec claim: one diode-connected nfet_01v8 drawn N times at tt_mm with a deterministic plain-tt negative control, proving the Monte Carlo plumbing reaches the simulator. Counted toward T1 item 9 by nothing.

## Pinning

Every record indexed here states, in its own Environment section, the PDK variant + resolved open_pdks commit and the ngspice version it was produced with; sim/check_spec_coverage.py verifies those against sim/pdk.json / sim/toolchain.json rather than trusting the prose. xschem is pinned by sim/toolchain.json's xschem_tag and is a WARNING rather than a fatal drift (sim/selftest.sh stage 2's rule: xschem only netlists, and every record pins the exact netlist it ran by SHA-256) -- so the per-record xschem-side provenance this check enforces is the presence of that DUT netlist sha256 line, not a version string.

- PDK pin: `sim/pdk.json`
- Toolchain pin: `sim/toolchain.json`
- Cold-start bootstrap: `docs/environment-setup.md`

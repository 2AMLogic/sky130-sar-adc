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
| Sample rate | DRAFT | NOT benched -- deliberately, see reason | — | — |
| ENOB | DRAFT | benched (DRAFT row, evidence informational) | `sim/enob-estimate` | `20260828-005033-0c70212.md` |
| INL / DNL | DRAFT | benched (DRAFT row, evidence informational) | `sim/cdac-array-transfer` | `20260828-005006-0c70212.md` |
| `V_REF` | RATIFIED | benched (ratified, graded pass/fail) | `sim/cdac-array-transfer` | `20260827-213107-e13bc1e.md` |
| LSB (differential) | RATIFIED | benched (ratified, graded pass/fail) | `sim/cdac-array-transfer` | `20260827-213107-e13bc1e.md` |
| Sampling cap (CDAC unit × array) | RATIFIED | benched (ratified, graded pass/fail) | `sim/cdac-array-transfer` | `20260827-213107-e13bc1e.md` |
| Comparator input-referred noise | RATIFIED | benched (ratified, graded pass/fail) | `sim/comparator-decision` | `20260827-212404-e13bc1e.md` |
| Power | DRAFT | NOT benched -- deliberately, see reason | — | — |
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
- **Claim class**: `unbenched`
- **Why no bench**: Deliberately unbenched, not overlooked: spec/target-spec.md's own 'Not ratified by this record' list names the provisional 100 kS/s-1 MS/s row as not re-derived, and no record under sim/ claims it. Benching it needs a switch-R_on/settling campaign against the integrated signal path, which would produce a number no ratified line exists to grade -- and CLAUDE.md forbids inventing one. A future decision record ratifies the row first; this index then requires its bench, because a RATIFIED row may never carry claim_class 'unbenched'.
- **Tracking**: #24 (CDAC/switch netlist) and the future sample-rate decision record

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

### Power

- **Status**: DRAFT
- **Claim class**: `unbenched`
- **Why no bench**: Deliberately unbenched, not overlooked: the row's own target text is 'provisional, minimise at rate' with the note 'report, don't pre-commit'. There is no threshold to grade against, so a power bench would produce a number with no ratified line to pass or fail -- and inventing one is exactly what CLAUDE.md's spec-is-a-gate rule forbids. If a future decision record ratifies a power row, this index's ratified-row rule then forces a bench for it.
- **Tracking**: future power decision record (none open)

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

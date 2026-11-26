# sim/cdac-array-transfer — CDAC array DAC transfer characteristic (issue #53)

Standalone experiment: exercises `design/cdac/cdac_array.sch`'s own
code-vs-output linearity, in isolation from the sampling front end,
comparator, and SAR logic (none of which exist yet — see issue #53's
"Dependencies: none").

## Why this experiment does NOT have a `testbench/tb.json`

Every other experiment under `sim/` (`harness-corner-smoke/`, `mc-smoke/`)
follows the generic manifest convention `sim/README.md` documents:
`testbench/tb.json` + a fragment, run through `sim/run_corners.py` /
`sim/monte_carlo.py`, both of which unconditionally emit `.control op ...` —
a bare DC operating-point analysis (`sim/harness/testbench.py`'s
`_render_body()`).

That is correct for a DUT with a real DC operating point. **This DUT does
not have one worth measuring**: the CDAC array's `TOP_P`/`TOP_N` nodes are
purely capacitive (no resistive path except the RC-time-constant-only leak
resistor the testbench fragment adds for numerical solvability). At true DC
steady state an ideal capacitor is an open circuit, so `.op` alone reports
whatever the leak-resistor network implies — **not** the code-dependent
charge-redistribution voltage the array actually produces. Deliberately
running this experiment through `run_corners.py` would not error; it would
silently report a wrong, code-independent number (every code would read
back as `Vcm`, the leak resistor's bias point). That failure mode is exactly
why this experiment ships its own runner instead of a `tb.json` — a `tb.json`
present here would be an invitation to exactly that misuse.

**Use `run_transfer.py` instead**:

```sh
source sim/env.sh
python3 sim/cdac-array-transfer/run_transfer.py --check-env
python3 sim/cdac-array-transfer/run_transfer.py --record
```

**Ratified-spec-row campaign (issue #28)** — the same DUT swept across the
full ratified corner set and graded against the ratified `V_REF` / LSB /
CDAC unit-cap-and-array-size rows, written as its own record (`--record`
above still writes only the pre-ratification informational record; the two
are independent flags, not a superseding pair):

```sh
python3 sim/cdac-array-transfer/run_transfer.py --ratified-record
```

That is the cold-start invocation `sim/spec-coverage.json` indexes for those
three spec rows; `sim/check_spec_coverage.py` checks this file still
documents it verbatim.

It reuses `sim/harness/pdk.py`, `sim/harness/toolchain.py`,
`sim/harness/measure.py`, and `sim/harness/evidence.py` unmodified (same PDK
resolution, ngspice invocation/timeout/`.spiceinit` handling, `name = value`
log parsing, and append-only evidence-record format as every other
experiment) — only the analysis type (`tran`, not `op`) and the
netlist-assembly/measurement logic are experiment-specific, so it lives next
to its own fragment rather than inside the shared harness modules.

## Method

See `testbench/tb_cdac_array_transfer.spice`'s own header for the full
derivation: five representative 9-bit sub-array codes (0, 128, 256, 384,
511) are each given their own copy of the array (both differential sides),
reset to `Vcm` via an ideal testbench-only switch, then released to their
target code through the design's real `nfet_01v8`/`pfet_01v8` bottom-plate
switches; the settled top-plate voltage is compared against the ideal
charge-redistribution value computed independently in `run_transfer.py`.

## Directory layout

Follows `sim/README.md`'s convention (`testbench/`, `netlist-snapshots/`,
`corners/`, `records/`) except for the `tb.json` omission explained above.

## Monte Carlo DNL/INL campaign (issue #29)

`run_mc.py` (a third, separate driver, alongside `run_transfer.py` above)
extends this same DUT with a mismatch (`tt_mm`) Monte Carlo campaign over a
larger, programmatically generated code set (`gen_fragment.py` — verified
byte-for-byte against `testbench/tb_cdac_array_transfer.spice`'s own 5-code
hand-authored fragment by `sim/tests/test_cdac_fragment_gen.py`, then reused
to generate the additional major-carry-transition codes a real DNL/INL
Monte Carlo needs, which the original quartile-spaced 5-code set cannot
express — see `run_mc.py`'s own module docstring for the full derivation):

```sh
source sim/env.sh
python3 sim/cdac-array-transfer/run_mc.py --check-env
python3 sim/cdac-array-transfer/run_mc.py --n 40 --seed 1 --record
```

Writes into this same directory's `mc-draws/`, `netlist-snapshots/`,
`records/`, and (new) `yield-reports/` — a `klt yield` JSON report per
record, see `sim/README.md`'s "Statistical-row Monte Carlo campaigns"
section for the machine-checkable-evidence convention this follows.

### Re-scoring an existing campaign against a candidate target (issue #129)

`run_mc.py` also supports **re-analyzing a PRIOR record's already-committed
`mc-draws/<record-id>/` logs against a different candidate INL/DNL bound**,
with NO new ngspice invocation — used by
`spec/decision-records/DR-007-revised-enob-inl-dnl-targets.md` to evidence a
candidate revised target from the SAME draws issue #29 already collected,
rather than re-running a ~35-minute N=40 campaign for numbers that would come
out identical:

```sh
source sim/env.sh
python3 sim/cdac-array-transfer/run_mc.py \
  --reanalyze 20260828-005006-0c70212 \
  --target-limit-lsb 2.0 --target-yield 0.99 \
  --record
```

This mints a new (append-only) record whose `## DNL/INL distributions` table
reproduces the source record's statistics exactly (same draws, re-scored),
with its `Claim`/`klt yield` sections framed against the candidate target
instead of `spec/target-spec.md`'s row — see
`sim/tests/test_cdac_mc_reanalyze.py` for the byte-for-byte reproduction
check. `--target-limit-lsb`/`--target-yield` also apply to a **fresh** `--n`
run (default `1.0`/`0.99`, matching the DRAFT spec row), for evaluating a
brand-new campaign against a non-default candidate directly.

### Mismatch gain error (issue #756)

`run_mc.py --reanalyze <record-id> --gain-error --record` mints a record of the
mismatch half of the CDAC gain error from an existing campaign's committed
logs (no new ngspice run; the code-0 and code-511 levels are already in every
log). Per draw, gain error = (`tt_mm` code-0→511 span − plain-`tt` span of the
same seed) / 3.5156 mV, so the systematic `C_par` term cancels and is reported
separately. The record compares mean/stdev/3σ (with N and the stdev's standard
error) to DR-003 Item 3's analytic figure and adds no spec row. Spans are
quantized at the 6-significant-digit `.meas` print resolution (~0.0028 LSB).

## `klt sim` pilot (issue #564)

A first `klt sim` request for the ratified-corner transfer campaign (the same
9-point one-at-a-time star as `--ratified-record`) lives in
`testbench/klt/request.json` (+ `tb_body.spice`, which `.include`s the fragment
above). It is a pilot beside, not a replacement for, `run_transfer.py`.

```sh
uvx --from "klayout-tools==0.8.0" klt sim sim/cdac-array-transfer/testbench/klt/request.json --dry-run --format json   # expect unit_count: 9
uvx --from "klayout-tools==0.8.0" klt sim sim/cdac-array-transfer/testbench/klt/request.json -o OUTDIR --report-out OUTDIR/report.json.gz --format json
python3 sim/cdac-array-transfer/compare_klt_envelope.py OUTDIR/report.json.gz   # 90 pairs, |delta| <= 2e-5 V vs record 20261001-120402-d24f700
```

Result so far: record `records/20261106-180843-15ea2ea.md` (NOT RUN -- the
fleet refused the job on a client/runner version mismatch; no comparison was
possible). Raw report: `klt-sim/20261106-180843-15ea2ea/`.

## Graded spec-row envelope (issue #1021)

`testbench/klt/request-graded.json` (driven by `run_klt_graded.py`) is the
graded sibling of the pilot request above: same DUT (`tb_body.spice` ->
`tb_cdac_array_transfer.spice`), same 9-point ratified OAT corner grid, same
ten raw top-plate FINDs, plus the ratified-row observables. What is graded
and what is deliberately not:

| Row | Observable in the envelope | Pass condition | Status |
|---|---|---|---|
| `V_REF` | `vref_ratio = (v(vrefp)-v(vrefn))/v(vdd)` and `v_vrefn`, both `spec_row: v_ref`-tagged, limits-bearing | Ratified relation `V_REF = V_DD` per corner (DR-003): ratio within `1 ± 1e-5` relative, VREFN within `±1e-5 V` of 0. The slack is solver/print precision ONLY -- `1e-5` rel is twice the six-significant-digit `.meas` print half-step just above unity (print step `1.00001 − 1.00000 = 1e-5`, half-step `5e-6`) and ≥ 16x ngspice's default `vntol` = 1e-6 V at the 1.62 V rail corner -- not a design tolerance | **Graded** (record `records/20261126-040720-de9c8405.md`, PASS 9/9 corners) |
| LSB (differential) | vdiff values + four untagged `mono_step_*` limits-bearing checks; per-corner derived LSB computed in the record | **No ratified tolerance exists** for the step's deviation from `2*V_REF/2^N = 3.5156 mV` -- none is invented here (CLAUDE.md). The monotonicity/polarity checks carry limits but NO `spec_row` tag, so they can never be read as the row's coverage | **Gap** -- tolerance decision owned by `spec/decision-records/DR-026-cdac-row-tolerance-decisions.md` (proposed); `sim/spec-coverage.json` keeps the row in the `ratified-gap` class naming it |
| Sampling cap | Structural census (`run_transfer.check_structural_sizing()`, exact values) + untagged `q_vrefp` reference-charge integral -> per-corner `cu_elec` in the record | Structural: plate side exactly `1.9000 um`, per-side weights `1,2,4,...,256` + termination = `512`/side (ratified, DR-003/DR-019; corner-invariant). Electrical `cu_elec` (8.59-9.54 fF over the 9 corners vs the ratified "≈ 8.66 fF" estimate): **no ratified tolerance** -> informational only, no tag, no limits | **Structural graded; electrical gap** -- same DR-026 decision; row stays `ratified-gap` |

The `q_vrefp` -> `cu_elec` derivation (full arithmetic in
`run_klt_graded.py`'s `SWITCHED_UNITS_EQ`): for one array side with `sw`
switched unit positions, the floating top plate's redistribution means the
charge drawn from VREFP is `C_u*vdd*sw*(1 - sw/512)` per side, so the
five-code set's exact equivalent is `328699/512 = 641.990234375` unit
positions -- not `5*511`. The envelope's tran step is `0.05n` (the pilot's
`0.5n` aliases the ~0.2 n switching event the integral needs).

Cold start (indexed verbatim by `sim/spec-coverage.json`):

```sh
source sim/env.sh
python3 sim/cdac-array-transfer/run_klt_graded.py --record
```

A `--dry-run` first (no simulation, schema/corner-grid validation):

```sh
uvx --from "klayout-tools==0.9.0" klt sim sim/cdac-array-transfer/testbench/klt/request-graded.json --dry-run --format json   # expect unit_count: 9
```

The submit goes through `klt sim` (batch fleet via `$KLT_SIM_BACKEND`, with
`--wait-for-capacity 600` per the shared harness's fleet-capacity policy);
the runner refuses to mint a record whose worker PDK/ngspice stamps drift
from `sim/pdk.json` / `sim/toolchain.json`. A full-grid record requires the
committed graded request and one result for each ratified process, temperature
and supply combination in the OAT grid. Run a subset request directly with
`klt sim` for debugging. The corrected record is
`records/20261126-040720-de9c8405.md` (PASS; raw report under
`klt-sim/20261122-103440-000e61e7/`). The #811 baseline-agreement probe
(`compare_klt_envelope.py`) is reported inside that record informationally:
it FAILs the pilot's `|delta| <= 2e-5 V` rule across uncontrolled
differences (PDK pin, host, ngspice build, tran step) -- that gate belongs
to #811 and is neither passed, widened nor reinterpreted here.

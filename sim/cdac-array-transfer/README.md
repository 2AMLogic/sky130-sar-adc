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

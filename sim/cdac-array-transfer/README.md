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

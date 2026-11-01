# Digital-partition functional verification (T1 item 5, digital)

Bit-exact gate-level regression of the digital partition's two macros, run with
`klt functional-verification` (cocotb + Icarus Verilog) on the **pre-route**
netlists that `klt place-and-route` consumed:

| Macro | Netlist | Bench |
|---|---|---|
| `sar_sequencer` (walking-one ring + 10-bit SAR register) | `layout/sar-sequencer/netlist/sar_sequencer.v` | `tb/test_sar_sequencer.py` |
| `top_glue` (DR-008 drive + recode, DR-009 enable pair / dummy load, `CLKN`) | `layout/top-glue/netlist/top_glue.v` | `tb/test_top_glue.py` |

Both are checked against `tb/sar_ref.py`, a reference model written from the
DR-006 / DR-008 / DR-009 text rather than from the netlists. Every test compares
**every output port** to the model after every clock edge / input change.
`python3 -I sim/digital-functional/tb/sar_ref.py` runs the model's own self-check
(walking-one shape, textbook closed-loop SAR over all 1024 codes, reset, glue
invariants); it is in `npm run check:ci` as `check:digital-ref`.

## What the tests cover

`sar_sequencer`: reset state; walking-one phase order and period (12 clocks);
**all-ones** and **all-zeros** codes (the latter also proves no stale-bit
retention); the four codes the SPICE campaign drove (811, 212, 682, 341); all
1024 codes in closed loop back to back; a **mid-conversion asynchronous reset at
each of the 12 sequencer states**, then a fresh correct conversion; 4000 edges of
seeded random `COMP_OUT` with random asynchronous resets.

`top_glue`: the full 2^10 `DOUT` x 8 (`PH_B9`, `BUSY`, `OUTN_NC`) input space
(which contains all-ones and all-zeros, each also a named test); both `CLK`
polarities; the sign-branch codes; the DR-009 enable pair.

## Cell models

`models/sky130_fd_sc_hd_subset.v` is the PDK's own functional Verilog for exactly
the nine cell types the two netlists instantiate (plus the two UDPs the flop
needs), unedited, extracted by `bin/extract-cell-models.py` (source file hashes
and PDK revision are in its header). It is committed because a request names its
sources by path and the PDK lives outside the repo.

## Negative control

`mutations/*.json` are `klt functional-verification --mutations` proposals: 5
single-line netlist faults for the sequencer (mux inputs swapped, ring link
skipped, reset disabled on one flop, a BUSY term dropped, wrong capture select)
and 6 for the glue (wrong operand, DR-008 polarity, recode cell swapped, clock
inverter stuck, dummy-load operand, DR-009 enable polarity). The suite kills all
11 (`runs/<id>/<macro>.mutations.json`). A mutation score is evidence the bench
can fail; it is not a coverage claim beyond those faults.

## Limits (read before citing)

- **Zero-delay.** No SDF, no timing. Post-route SDF re-simulation is `bin/run-sdf-record.py` (issue #679, `records/*-sdf.md`);
  timing is `sim/digital-sta/`.
- **The routed `sar_sequencer` is the issue-#102 netlist, 36 instances.**
  `design/sar_sequencer.sch` has 57: it gained the `COMP_EFF` xnor (DR-008's
  sign-branch comparator correction) and per-conversion clear gating in issue
  #263, and `sim/digital-partition/`'s SPICE snapshot carries them. The
  layout netlist was never updated (issue #680), so this suite — and the STA in
  `sim/digital-sta/` — covers the netlist that was routed, not today's schematic.
  The sequencer's closed-loop tests use the textbook binary search against the
  routed register (raw `COMP_OUT`), which is what that netlist implements.
- The DR-008 recode and the DR-009 pair are verified in `top_glue` in isolation,
  not as a chain with the sequencer.
- Provisional: `spec/target-spec.md` is DRAFT (issue #1).

## Reproducing

```bash
python3 -m venv .venv-signoff
.venv-signoff/bin/pip install -r signoff/requirements.txt cocotb   # klt 0.6.0
KLT=.venv-signoff/bin/klt python3 -I sim/digital-functional/bin/run-record.py
```

`run-record.py` mints `runs/<id>/` and `records/<id>.md` (never overwrites).
`klt` leaves scratch files in `requests/.klt/`; delete them before committing.
Needs `iverilog` on `PATH`. `klt` 0.6.0 has no `-o`, so that directory is where
it writes.

## SDF-annotated re-run (issue #679)

`bin/run-sdf-record.py <sim/digital-sta run id>` re-runs the bench on the routed
`*_post_route.v` netlists with each corner's SDF back-annotated
(`options.sdf`), using `tb/test_*_sdf.py` (timing from `SAR_TB_HALF_NS` /
`SAR_TB_SETTLE_NS`; the zero-delay benches are untouched because the zero-delay
record hashes them) and `models/sky130_fd_sc_hd_subset_timing.v` (the PDK's
`specify`-bearing models, `bin/extract-cell-models.py --timing`). It refuses to
write a record unless a short-settle control fails and a no-SDF control passes.
Results: `records/*-sdf.md`. Icarus drops SDF TIMINGCHECK, so setup/hold are not
checked here.

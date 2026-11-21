# layout/sampling-frontend/pex/ -- real `klt pex` parasitic verification (issue #1017)

First `klt pex` record for the sampling front end sub-block: a real `klt
extract --parasitics --pdk sky130A` run against the layout `reports/LATEST`
names, re-simulated at the schematic and extracted levels and diffed, at the
ratified 9-point one-at-a-time PVT grid. The measured quantity is the
acquisition-window settling experiment of
`sim/sampling-acquisition-settling/run_acquisition_settling.py` (issues
#121/#236): the DR-006 worst-case (12 MHz) per-phase budget residual after a
worst-case full-scale differential input step, its confirmatory long-window
read, and the campaign's 50%/90% crossing delays -- on TOP_P/TOP_N and on
the bootstrap rails BOOST_P/BOOST_N. See
`layout/sampling-frontend/reports/<record-id>/record.md` (one new record per
`run_pex.py --record` invocation) for the actual numbers.

## Files here (reusable source, versioned)

- `testbench.spice` -- the one testbench `klt pex` runs on both legs: the
  acquisition campaign's two-SAMPLE-pulse stimulus with its constants
  unchanged (precharge 10 ns, SAMPLE#1 100 ns wide, input step during hold
  at 130 ns, SAMPLE#2 at 160 ns, budget read 83.3333 ns after the 160.1 ns
  trigger, confirm read at 305 ns), `.meas` rows supplied by the request
  `run_pex.py` builds (the crossing thresholds are constants because the
  campaign holds its stimulus amplitudes fixed across the PVT grid -- its
  own ratified-grid convention). Only `vdd` is keyed by `corners.supply_v`
  (a literal DC source, the alter gotcha,
  `layout/comparator/pex/README.md`); Vcm and the VIN amplitudes stay at
  the campaign's fixed 0.9/0.2/1.6 V values at every corner. The Xdut line
  is POSITIONAL on the extracted netlist's own pin order (alphabetical, 12
  pins); `run_pex.py` asserts every run's extraction still declares exactly
  that list. BPREF_x sit on dead-end nets -- the `*_NC` wiring
  `design/sar_adc_top.spice` gives them, per
  `sim/sampling-cdac-handoff`'s documented interface contract.
- `run_pex.py` -- this record's generator; also materializes the schematic
  DUT wrap per run (the committed regenerated fragment
  `sim/sampling-frontend/testbench/sampling_frontend_dut.spice`, verbatim
  minus its `.GLOBAL GND` line, wrapped in the CURRENT extraction's own
  `.SUBCKT` name and pin order). Run it to reproduce:

  ```sh
  layout/bin/setup-venv.sh          # once, or after bumping requirements.txt
  source sim/env.sh                 # exports PDK_ROOT/PDK
  python3 layout/sampling-frontend/pex/run_pex.py --check-env
  python3 layout/sampling-frontend/pex/run_pex.py --pilot    # tt/27C/1.8V, local
  python3 layout/sampling-frontend/pex/run_pex.py --record   # 9 OAT corners, batch
  ```

  Each `--record` run mints a new timestamped, append-only record under
  `layout/sampling-frontend/reports/<record-id>/` -- it never edits a prior
  record and never touches `reports/LATEST` (that pointer belongs to the
  drawing flow, the same convention `layout/comparator/pex/README.md`
  documents).

## Scope: this block alone, not the combined load

`sim/sampling-cdac-handoff`'s combined front-end + CDAC-array question is
deliberately NOT measured here: that testbench instantiates two separate
layout tops, and `klt pex` extracts exactly one `--top` per run and swaps a
single DUT `.include` -- the multi-top gap
[2AMLogic/klayout-tools#5494](https://github.com/2AMLogic/klayout-tools/issues/5494)
tracks; the composed-block run additionally waits on issue #103's top-level
LVS. Each record says so in its own scope statement.

## Shared machinery

The pinned-`klt` invocation (layout/requirements.txt's 0.6.0, never the
ambient fleet build on `$PATH`), the batch-fleet capacity retry, the
ratified OAT corner carve (`corners` + `exclude`), extracted-`.SUBCKT`
parsing and the per-net R/C table reader live in `layout/bin/pex_flow.py`,
shared with `layout/cdac-array/pex/` and `layout/comparator/pex/`
(issue #1017). `$PEX_KLT_BIN` overrides the pinned binary for a
throwaway-venv run without touching the pin (issue #1017 step 4).

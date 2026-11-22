# layout/cdac-array/pex/ -- real `klt pex` parasitic verification (issue #1017)

First `klt pex` record for the CDAC array sub-block: a real `klt extract
--parasitics --pdk sky130A` run against the layout `reports/LATEST` names,
re-simulated at the schematic and extracted levels and diffed, at the
ratified 9-point one-at-a-time PVT grid (the same OAT star the `sim/`
campaigns sweep). The measured quantity is the DAC transfer characteristic
of `sim/cdac-array-transfer`'s own methodology (five representative codes,
both differential sides, settled top-plate pair at t=500 ns), plus the
extracted top-plate parasitic R/C table read against the schematic-level
`C_par` figure `sim/top-plate-cpar/` measured (issue #754) and against what
DR-022 / DR-025 assume for systematic gain error. See
`layout/cdac-array/reports/<record-id>/record.md` (one new record per
`run_pex.py --record` invocation) for the actual numbers.

## Files here (reusable source, versioned)

- `testbench.spice` -- the one testbench `klt pex` runs on both legs: five
  array instances (codes 0/128/256/384/511, P side driven directly, N side
  with the 9-bit mirrored complement -- the transfer campaign's own
  differential-CDAC convention), reset-to-Vcm by an ideal testbench-only
  switch, per-bit SEL PWL sources for the code event. The X lines are
  POSITIONAL on the extracted netlist's own pin order (alphabetical);
  `run_pex.py` asserts every run's extraction still declares exactly that
  list, so a re-draw that reorders pins fails loudly instead of silently
  permuting nets. `vdd` and `vcm` are literal DC sources keyed by
  `corners.supply_v` (the alter gotcha, `layout/comparator/pex/README.md`);
  VCM tracks the rail (VCM = VDD/2) as a PAIRED supply point, never swept
  independently; VREFP is wired straight to the vdd rail node per DR-003's
  V_REF = V_DD. Both PEX legs use 1.8 V for the pulsed SEL and reset highs
  and 0.9 V for the reset switch threshold. The transfer campaign scales
  these to VDD and VDD/2. The levels differ at the two off-nominal rails.
- `run_pex.py` -- this record's generator; also materializes the schematic
  DUT wrap per run (below). Run it to reproduce:

  ```sh
  layout/bin/setup-venv.sh          # once, or after bumping requirements.txt
  source sim/env.sh                 # exports PDK_ROOT/PDK
  python3 layout/cdac-array/pex/run_pex.py --check-env
  python3 layout/cdac-array/pex/run_pex.py --pilot    # tt/27C/1.8V, local
  python3 layout/cdac-array/pex/run_pex.py --record   # 9 OAT corners, batch
  ```

  Each `--record` run mints a new timestamped, append-only record under
  `layout/cdac-array/reports/<record-id>/` -- it never edits a prior record
  and never touches `reports/LATEST` (that pointer belongs to the drawing
  flow, the same convention `layout/comparator/pex/README.md` documents).

- The schematic DUT (`cdac_array_pex_reference.spice`) is GENERATED per run
  into the record directory (not committed here): the per-bit device
  pattern of `sim/cdac-array-transfer/testbench/tb_cdac_array_transfer.spice`
  (one weighted `cap_mim_m3_1` plus the real `nfet_01v8`/`pfet_01v8`
  bottom-plate switch pair per bit position, both sides, plus the
  VREFN-tied termination cap), wrapped in the CURRENT extraction's own
  `.SUBCKT` name and pin order. The comparator flow commits a hand-copied
  wrap; this flow derives it from the extraction each time so the wrap
  cannot drift from a re-drawn layout's pin order.

## Shared machinery

The pinned-`klt` invocation (layout/requirements.txt's 0.6.0, never the
ambient fleet build on `$PATH`), the batch-fleet capacity retry, the
ratified OAT corner carve (`corners` + `exclude`, the shape
`sim/top-plate-cpar/run_top_plate_cpar.py` established), extracted-`.SUBCKT`
parsing and the per-net R/C table reader live in `layout/bin/pex_flow.py`,
shared with `layout/sampling-frontend/pex/` and `layout/comparator/pex/`
(issue #1017). `$PEX_KLT_BIN` overrides the pinned binary for a
throwaway-venv run without touching the pin (issue #1017 step 4).

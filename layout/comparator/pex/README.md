# layout/comparator/pex/ -- real `klt pex` parasitic verification (issue #112)

Supersedes the wire-*area* symmetry proxy
`layout/comparator/reports/20260825-135219-59f8e86/record.md` documented as
"not a parasitic extraction" with a real `klt extract --parasitics --pdk
sky130A` run against the same composed layout, re-simulated at the
schematic and extracted levels and diffed. See
`layout/comparator/README.md`'s "Floorplan and routing" section for how the
two results relate, and `layout/comparator/reports/<record-id>/record.md`
(one new record per `run_pex.py` invocation) for the actual numbers.

## Files here (reusable source, versioned)

- `comparator_pex_reference.spice` -- schematic-equivalent DUT: the same
  device list `sim/comparator-decision/testbench/comparator_core.spice`
  carries (issue #54), wrapped in a `.SUBCKT gen_compose_0 <pins...>`
  header/footer so `klt pex`'s DUT-`.include`-swap convention (docs/cli/
  pex.md) has something to swap. `comparator_core.spice` itself is FLAT (no
  `.SUBCKT` wrapper -- by design, since `sim/comparator-decision/run.py`'s
  own pick-off methodology drives its nets directly), so pointing a
  testbench's `.include` at it directly would trip `klt pex`'s
  `flat_dut_mismatch` check instead of working; see that file's own header
  comment for the full reasoning.
- `testbench.spice` -- schematic-side `klt sim`/`klt pex` testbench body:
  reset(CLK=0)->evaluate(CLK=VDD) transient stimulus, reusing
  `run.py`'s own pick-off methodology/timing constants (`RESET_NS`,
  `RESET_TR_NS`, `PICKOFF_NS`). Two corner points via `corners.supply_v` on
  literal `Vinp`/`Vinn` DC sources (see "the alter gotcha" below):
  Vindiff=0 (isolates the routing/parasitic-driven imbalance, since neither
  leg's devices are stochastically mismatched at this corner) and
  Vindiff=+10mV (a `run.py` `VINDIFF_GAIN_CAL_MV` gain-calibration point).
- `extracted_testbench.spice` -- byte-identical stimulus to
  `testbench.spice`; the only difference is its `.include` target, pointed
  at a per-record extracted netlist (see "Why not just `klt pex`" below for
  why this is a separate, hand-maintained file rather than something `klt
  pex` generates for us).
- `pex_request.json` -- canonical `klt sim`/`klt pex`-format request
  (corners, analysis, measurements). `run_pex.py` derives both legs'
  concrete request copies from this one file at run time.
- `normalize_extracted_units.py` -- workaround for
  2AMLogic/klayout-tools#1396 (see below); mechanical, value-preserving.
- `run_pex.py` -- this record's generator. Run it to reproduce:

  ```sh
  layout/bin/setup-venv.sh          # once, or after bumping requirements.txt
  source sim/env.sh                 # exports PDK_ROOT/PDK
  python3 layout/comparator/pex/run_pex.py --check-env
  python3 layout/comparator/pex/run_pex.py --record
  cat layout/comparator/reports/$(ls -t layout/comparator/reports | grep -v LATEST | head -1)/record.md
  ```

  Each run mints a new timestamped, append-only record under
  `layout/comparator/reports/<record-id>/` (same convention
  `layout/comparator/README.md` documents for the drawing flow) -- it never
  edits a prior record, and it never touches `reports/LATEST` (that pointer
  is the *drawing* flow's, i.e. which `comparator.gds` to extract from --
  this flow only reads it).

## Why not just `klt pex`

The issue's own acceptance criteria say "`klt pex` (or the documented
equivalent)" for exactly this reason: `klt pex` end-to-end hit **two
independent tool bugs** on this sub-block, both filed generically per
`CLAUDE.md`'s friction protocol (no design-specific detail in either):

1. **[2AMLogic/klayout-tools#1395](https://github.com/2AMLogic/klayout-tools/issues/1395)**
   -- `klt pex`'s generated extracted-side request copy re-resolves a
   relative `models.lib` path against the *original request file's own
   directory* instead of the PDK-variant directory `models.pdk` resolves it
   against: `model library not found`, even though the identical request
   runs fine standalone via `klt sim` and on `klt pex`'s own schematic-side
   leg (an unmodified re-run of the same request).
2. **[2AMLogic/klayout-tools#1396](https://github.com/2AMLogic/klayout-tools/issues/1396)**
   -- `klt extract --pdk sky130A --parasitics`'s sky130 MOS binding writes
   device geometry (`L`/`W`/`AS`/`AD`/`PS`/`PD`) with explicit SPICE unit
   suffixes (`L=0.5U`); sky130's vendor model deck sets `.option
   scale=1.0u`, and `sky130_fd_pr__nfet_01v8`/`pfet_01v8`'s own internal
   NRD/NRS default-value formula assumes bare, suffix-free micron literals.
   Feeding it unit-suffixed values makes the computed default NRD/NRS come
   out ~1e6x too large and ngspice refuses the device ("could not find a
   valid modelname") -- verified on a single-device minimal repro, isolated
   from this sub-block's own topology.

Bug 1 blocks `klt pex` from completing at all on a request whose `models`
field uses the `{"pdk": ..., "lib": "<relative path>"}` form (the
form `docs/cli/sim.md` documents as the normal case). Bug 2 would still
break the extracted-side simulation even with bug 1 worked around (`klt
pex`'s own internal extraction step hits it, not just a caller's manual
`klt extract` call).

`run_pex.py` instead runs the same three logical steps `klt pex`'s own
documentation describes (extract, re-simulate each leg, diff) as separate
commands:

1. `klt extract --parasitics --pdk sky130A` -- **unaffected by either bug**;
   this is the actual parasitic-annotated netlist, produced exactly as `klt
   pex` would produce it internally. This step alone already satisfies AC1
   ("a real `klt pex` parasitic extraction... producing a
   parasitic-annotated netlist") and AC2 (`extract.json`'s
   `parasitics.nets[]` has every net's ground + coupled capacitance, in
   farads, directly -- no simulation needed for that part).
2. `normalize_extracted_units.py`'s workaround, applied to the extracted
   netlist (bug 2's fix, done locally rather than waiting on the upstream
   patch).
3. `klt sim` on each leg separately (bug 1's fix -- both legs' requests are
   generated from `pex_request.json` by `run_pex.py` itself, with each
   leg's own already-correct `netlist` field, rather than relying on `klt
   pex`'s own buggy request-copy machinery).
4. The schematic-vs-extracted delta, computed and written into `record.md`
   by `run_pex.py` directly (the same computation `klt pex`'s own `delta[]`
   would produce, done in Python here instead).

Once both upstream issues are fixed, this workaround can be deleted and
`run_pex.py` replaced with a single `klt pex layout.gds pex_request.json
--deck sky130 --pdk sky130A --pdk-root $PDK_ROOT` call -- `pex_request.json`
is deliberately kept in the exact shape that call already expects.

## The `alter` gotcha (why `testbench.spice`'s sources are literal, not `.param`)

`corners.supply_v`'s doc (docs/cli/sim.md) says it is "keyed by source/
`.param` name" -- but empirically, `klt sim`'s generated `alter <key>=<value>`
command only resolves a *named voltage/current source* (ngspice's `alter`
target), not a `.param` referenced indirectly via `{param}` substitution
inside a source's `DC` value. Keying `corners.supply_v` off a `.param` name
silently no-ops (ngspice logs `Error: no such device or model name <param>`,
but `klt sim`'s failure classification does not treat an unresolved `alter`
target as its own diagnostic code, so the corner still "passes" with the
un-altered default value). `testbench.spice`/`extracted_testbench.spice`
therefore declare `Vinp`/`Vinn` as literal DC sources and key
`corners.supply_v` off their source names (`vinp`/`vinn`) directly.

## What AC2's capacitance numbers do and do not establish

`extract.json`'s `parasitics.nets[]` gives each net's own ground capacitance
plus every *coupled* (net-to-net) capacitance term -- this is Phase 1's
vertical-overlap-only coupling model (issue #760): same-layer/lateral
coupling is not included unless a net is named via `--critical-net`
(2AMLogic/klayout-tools issue #976), which this run does not use. The
OUTP/OUTN and VINN/VINP capacitance numbers in `record.md` are therefore a
first-order, vertical-coupling-only figure -- consistent with, not a
superset of, everything a full parasitic extraction could in principle
model (see `extract.json`'s own `extraction.model` block for the exact
scope note `klt extract` reports).

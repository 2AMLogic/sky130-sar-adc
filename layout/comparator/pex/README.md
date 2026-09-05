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
- `testbench.spice` -- the one testbench `klt pex` runs on both legs:
  reset(CLK=0)->evaluate(CLK=VDD) transient stimulus, reusing
  `run.py`'s own pick-off methodology/timing constants (`RESET_NS`,
  `RESET_TR_NS`, `PICKOFF_NS`). Two corner points via `corners.supply_v` on
  literal `Vinp`/`Vinn` DC sources (see "the alter gotcha" below):
  Vindiff=0 (isolates the routing/parasitic-driven imbalance, since neither
  leg's devices are stochastically mismatched at this corner) and
  Vindiff=+10mV (a `run.py` `VINDIFF_GAIN_CAL_MV` gain-calibration point).
  Run unmodified for the schematic-side leg; `klt pex` itself generates the
  extracted-side leg by swapping this file's one `.include` line for its
  own freshly-extracted netlist (docs/cli/pex.md's "The DUT `.include`
  swap") -- no hand-maintained extracted-side copy needed.
- `pex_request.json` -- canonical `klt sim`/`klt pex`-format request
  (corners, analysis, measurements), passed to `klt pex` as-is.
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

## Why not just `klt pex` (historical -- resolved by issue #146)

Until klayout-tools==0.4.0 (this repo's currently pinned version), `run_pex.py`
could not call `klt pex` end-to-end: it hit **two independent tool bugs** on
this sub-block, both filed generically per `CLAUDE.md`'s friction protocol
(no design-specific detail in either), and worked around locally instead of
waiting on the upstream fix. Both are now fixed upstream and confirmed
present in the pinned 0.4.0 (issue #146), so `run_pex.py` now makes the
single `klt pex` call this section used to say it couldn't:

1. **[2AMLogic/klayout-tools#1395](https://github.com/2AMLogic/klayout-tools/issues/1395)**
   -- `klt pex`'s generated extracted-side request copy re-resolves a
   relative `models.lib` path against the *original request file's own
   directory* instead of the PDK-variant directory `models.pdk` resolves it
   against: `model library not found`, even though the identical request
   runs fine standalone via `klt sim` and on `klt pex`'s own schematic-side
   leg (an unmodified re-run of the same request). Fixed by merged PR
   [#1403](https://github.com/2AMLogic/klayout-tools/pull/1403).
2. **[2AMLogic/klayout-tools#1396](https://github.com/2AMLogic/klayout-tools/issues/1396)**
   -- `klt extract --pdk sky130A --parasitics`'s sky130 MOS binding used to
   write device geometry (`L`/`W`/`AS`/`AD`/`PS`/`PD`) with explicit SPICE
   unit suffixes (`L=0.5U`); sky130's vendor model deck sets `.option
   scale=1.0u`, and `sky130_fd_pr__nfet_01v8`/`pfet_01v8`'s own internal
   NRD/NRS default-value formula assumes bare, suffix-free micron literals.
   Feeding it unit-suffixed values made the computed default NRD/NRS come
   out ~1e6x too large and ngspice refused the device ("could not find a
   valid modelname"). Fixed by merged PR
   [#1404](https://github.com/2AMLogic/klayout-tools/pull/1404), which added
   a per-PDK-family `GEOMETRY_STYLE_BARE_UM` so sky130 extraction now emits
   bare-micron geometry directly.

`run_pex.py` used to run the same three logical steps `klt pex`'s own
documentation describes (extract, re-simulate each leg, diff) as three
separate commands, with a local `normalize_extracted_units.py` script
rewriting the extracted netlist's unit-suffixed geometry fields to bare
micron numbers (bug 2's workaround) in between the extract and re-simulate
steps, and a hand-maintained `extracted_testbench.spice` standing in for
what `klt pex`'s own `.include`-swap machinery would otherwise generate
(bug 1's workaround, since that machinery was what hit bug 1).

Both files are deleted as of issue #146 -- re-running the old workaround
against the pinned 0.4.0 before deleting it confirmed why: `klt extract`'s
sky130 output is *already* bare-micron now (bug 2's fix), so
`normalize_extracted_units.py`'s re-normalization of already-bare values
made the geometry ~1e6x wrong in the *opposite* direction and the
extracted-side `klt sim` leg errored out -- the workaround had gone from
necessary to actively harmful the moment the pin moved to 0.4.0, not merely
redundant. `run_pex.py` now calls `klt pex <layout>.gds pex_request.json
--deck sky130 --pdk sky130A --pdk-root $PDK_ROOT` directly for the
re-simulate-both-legs-and-diff step, alongside a standalone `klt extract
--parasitics` call kept only because `klt pex`'s own JSON response echoes
just an aggregate extraction-model scope note, not the full per-net R/C
table AC1/AC2 need (see `run_pex.py`'s module docstring for the exact
before/after code path).

## The `alter` gotcha (why `testbench.spice`'s sources are literal, not `.param`)

`corners.supply_v`'s doc (docs/cli/sim.md) says it is "keyed by source/
`.param` name" -- but empirically, `klt sim`'s generated `alter <key>=<value>`
command only resolves a *named voltage/current source* (ngspice's `alter`
target), not a `.param` referenced indirectly via `{param}` substitution
inside a source's `DC` value. Keying `corners.supply_v` off a `.param` name
silently no-ops (ngspice logs `Error: no such device or model name <param>`,
but `klt sim`'s failure classification does not treat an unresolved `alter`
target as its own diagnostic code, so the corner still "passes" with the
un-altered default value). `testbench.spice` therefore declares `Vinp`/
`Vinn` as literal DC sources and keys `corners.supply_v` off their source
names (`vinp`/`vinn`) directly -- `klt pex`'s extracted-side leg reuses
these same source declarations unmodified (it only ever swaps the
`.include` line), so this applies identically to both legs.

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

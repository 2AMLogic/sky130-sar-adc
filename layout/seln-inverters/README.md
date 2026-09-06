# layout/seln-inverters/ — SELn<i> = NOT(DOUT<i>) inverter bank (issue #103)

Physical layout for the nine `sky130_fd_sc_hd__inv_1` instances
`design/sar_adc_top.sch` (issue #56) adds directly at the top-level
integration, not inside any sub-block: `DOUT<i>` (the SAR sequencer's own
per-bit register output, #102) drives `SELn<i>` = `NOT(DOUT<i>)`, the CDAC
array's (#100) N-side per-bit switch control. A differential DAC needs the
two sides' `SEL` complementary (not equal) because
`design/cdac/cdac_unit_cell.sch`'s single-control-line switch uses the
identical truth table on both array sides — see `design/sar_adc_top.sch`'s
own header for the full wiring rationale.

**This is new top-level glue logic, not a sub-block re-layout.** None of
#99 (sampling front end), #100 (CDAC array), #101 (comparator) or #102 (SAR
sequencer)'s own schematics instantiate these nine cells; they exist only in
the integration schematic issue #103 itself owns. That is why this directory
lives next to `layout/sar-sequencer/` etc. rather than inside any of them.

## Status: DRC-clean, LVS-clean

`reports/LATEST`'s record:

| Verdict | Result |
| --- | --- |
| `klt place-and-route` | reaches `route`, 0 setup/hold violations |
| `klt drc --deck sky130` | **CLEAN**, 0 violations |
| `klt lvs` | **match**, 18/18 devices, 20/20 nets, 20/20 pins (9 informational "ambiguous pairing resolved structurally" warnings, one per symmetric `SELn<i>` net — expected for nine electrically-identical, independently-driven inverters, not a real defect) |

## Which `klt` flow, and why

`klt place-and-route` (OpenROAD), the same choice `layout/sar-sequencer/`
makes and for the same reason: `netlist/seln_inverters.v` is a **hand-verified
1:1 structural transliteration** of `design/sar_adc_top.sch`'s own
`xinv_seln0..xinv_seln8` instances (nine independent `sky130_fd_sc_hd__inv_1`
cells, `DOUT<i>` -> `A`, `SELn<i>` -> `Y`), not RTL — there is nothing for
`klt synthesize` to usefully do.

**No clock, no state — but the request schema still requires
`constraints.clock_port`/`clock_period_ns`.** This design has zero sequential
elements, so `requests/place-and-route.json` declares a placeholder clock net
name (`CTS_NO_SUCH_CLOCK`) that does not appear anywhere in the netlist,
purely to satisfy that required field. Naming a *real* net (e.g. an actual
input pin) as the placeholder instead reproducibly **segfaults** `klt
place-and-route`'s `cts` stage (OpenROAD exit code 139) once that net has zero
fanout to any sequential cell — filed generically as
`2AMLogic/klayout-tools#1506`; the nonexistent-net workaround above avoids it
by taking `clock_tree_synthesis`'s no-op path instead.

**Floorplan is generously oversized for the cell count** (9 single-height
`inv_1` instances, ~2% final utilization) because `klt place-and-route`'s PDN
generator (`add_pdn_stripe`) needs enough die width for at least one full-width
met4/met5 strap (sky130's `met4`/`met5` minimum width is 1.6 µm) with real
margin on both sides — the same real PDN (`tapcell` ties,
`add_global_connection`/`pdngen` merging every `VPWR`/`VPB` pin into one net
and every `VGND`/`VNB` pin into another, plus met1/met4/met5 straps) issue
#102 needed for a *connected* `VPWR`/`VGND` rather than the row-rail-only
obstruction `klt place-and-route` draws by default when `power` is omitted —
see `layout/sar-sequencer/README.md`'s own "Power delivery" note for why an
unconnected PDN makes LVS unreachable independent of any `klt` gap. A future
pass could shrink this by tuning strap width/pitch for such a small block;
area was not a goal here (this macro's isolated LVS/DRC closure was).

## LVS reference provenance

Same mechanism as `layout/sar-sequencer/bin/generate-lvs-reference.py` (issue
#102): `klt extract --deck sky130` is a flat, transistor-level extractor, so
the LVS reference has to be flat and transistor-level too, with every drawn
NMOS/PMOS generalized to `klt`'s own `nfet`/`pfet` device classes.
`bin/generate-lvs-reference.py` flattens the **post-route** structural
Verilog netlist (`klt place-and-route`'s own `write_verilog` dump) against
the sky130 PDK's own official per-cell CDL model
(`sky130_fd_sc_hd.cdl`, Apache-2.0, SkyWater's own release — not
reverse-engineered).

## Running the flow

```sh
layout/bin/setup-venv.sh              # once, or after bumping requirements.txt
source sim/env.sh                      # exports PDK_ROOT/PDK
layout/seln-inverters/bin/run-flow.sh   # ~1 minute; place-and-route -> DRC -> LVS
```

Requires an `openroad` binary on `$PATH` (see `docs/environment-setup.md`).
Each run mints a new timestamped, append-only record under `reports/<record-id>/`
(same convention as `layout/trivial-cell/reports/`), and `reports/LATEST`
points at the newest one.

## Files

```
layout/seln-inverters/
  README.md                        # this file
  netlist/
    seln_inverters.v               # hand-verified structural netlist (not RTL)
  requests/
    place-and-route.json           # klt place-and-route request
  bin/
    run-flow.sh                    # place-and-route -> DRC -> post-route netlist dump -> LVS reference -> extract --def-pins -> LVS -> record
    generate-lvs-reference.py      # flattens the post-route netlist against the PDK's own CDL models
    render-record.py               # renders record.md from the JSON envelopes run-flow.sh produced
  reference/                       # generate-lvs-reference.py's own output -- regenerated per run, git-ignored
  reports/
    LATEST                         # record-id of the most recent run
    <record-id>/                   # append-only: netlist, request, routed GDS/DEF, post-route netlist,
                                    # generated LVS reference, every klt JSON envelope, record.md
```

## Where this fits into #103's top-level assembly

This macro is one of the five blocks the top-level assembly places and
routes (the other four being #99/#100/#101/#102's own already-closed
layouts). Its own ports (`DOUT8..DOUT0`, `SELn8..SELn0`, `VPWR`, `VGND`) are
documented, with exact DEF-derived coordinates, in
`layout/sar-adc-top/README.md`'s floorplan notes, alongside the other four
blocks' pin geometry — see that directory for the composition/routing status.

## Provenance

Structure follows `layout/sar-sequencer/`'s own conventions (append-only
timestamped records, `reports/LATEST` pointer, `record.md` provenance
stamping, CDL-based flat LVS reference generation), narrowed to this block's
single cell type and its own top-level port list. Clean room: the topology
placed and routed is this repo's own `design/sar_adc_top.sch` (issue #56);
the only external inputs are the sky130 PDK's own official, freely-licensed
standard-cell library and OpenROAD's own placement/routing/CTS algorithms.

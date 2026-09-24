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

## Known limitation: 33 metal minimum-area violations, waived 2026-09-19 (issue #333)

**The "DRC: CLEAN" verdict above is real but narrow, and this section states
exactly how narrow.** `klt drc --deck sky130` at the pinned
`klayout-tools==0.5.0` authors 47 rules across five kinds (`width`, `space`,
`enclosing`, `separation`, `isolated`) and **no `area`-kind rule at all**, so
sky130A's own metal minimum-area rules have never looked at this record.
Measured independently — `docs/chipalooza/measure_metal_min_area.py`, which
reads the layer numbers and thresholds out of the pinned PDK's own
`sky130A_mr.drc` and applies the deck's own `Region#with_area` primitive to the
merged top-cell flatten — this flow's `reports/LATEST` record carries:

| Rule | Threshold | Shapes below | Shape | Area | Drawn by |
| --- | --- | --- | --- | --- | --- |
| `m1.6` | 0.083 um² | 18 | 0.290 × 0.230 um (16), plus 2 router stubs | 0.0667 um² | `VIA_L1M1_PR_MR` |
| `m5.4` | 4.0 um² | 15 | 1.420 × 1.600 um | 2.2720 um² | `VIA_via5_6_1600_1600_1_1_1600_1600` |

33 shapes in total, re-measured 2026-09-19 against
`reports/20260917-180644-527ec73/seln_inverters.gds` on the pinned toolchain
(`klt 0.5.0`, `klayout 0.30.12`, open_pdks
`c6d73a35f524070e85faff4a6a9eef49553ebc2b`). **No `sky130_fd_sc_hd__*` library
cell contributes a single one** — every violating shape is in a generated via
cell or a router-drawn stub. `met2`, `met3` and `met4` are clear at this
block's size; `layout/sar-sequencer/` (the other `klt place-and-route` flow,
denser and with more routing layers in play) additionally trips `m2.6` and
`m3.6`, so the same waiver appears in its README with its own 112-shape table.

**Why this is not fixable from this repository.** Nothing in `layout/` draws
any of this geometry. The flow's only in-repo inputs are
`netlist/seln_inverters.v` and `requests/place-and-route.json`; everything
above comes out of `klt place-and-route`'s OpenROAD run and the DEF→GDS merge:

- The `m1.6` shapes are **the PDK's own tech-LEF via enclosure**, instantiated
  verbatim. `sky130_fd_sc_hd__nom.tlef` defines `VIA L1M1_PR_MR`'s met1 rect as
  `-0.145 -0.115 0.145 0.115` — 0.29 × 0.23 = 0.0667 um², below the *same*
  PDK's own 0.083 um² `m1.6` threshold standing alone. That is legal in the
  LEF, which expects the enclosure to merge with the wire it terminates; it
  becomes a violation only where the router leaves too little attached metal.
  Fixing it means a post-route minimum-area repair pass inside the router, not
  a constant this repo owns.
- The `m5.4` shapes are OpenROAD's PDN via5 patches. This one class is
  *influenced* by a repo-owned parameter (`power.straps`' met5 width), since
  sky130's 4.0 um² met5 floor needs ≥ 2.5 um of length on a 1.6 um strap — but
  re-tuning the power grid to dodge a DRC rule is a power-delivery design
  change, not a DRC fix (and this block's PDN is deliberately identical to
  `layout/sar-sequencer/`'s, so the two would have to move together).

A post-route GDS patch step owned by this repo was considered and rejected:
growing metal around a via inside already-routed, spacing-tight standard-cell
metal risks shorts and spacing violations, and would desynchronise the
committed GDS from the routed DEF that `klt extract --def-pins` and the LVS
reference are both derived from. Trading a silent minimum-area gap for a
possible connectivity defect is not an improvement.

**Upstream filings (generic, per CLAUDE.md's friction protocol).**

- `2AMLogic/klayout-tools#2139` — the live filing for this gap, with a
  reproducing input (a generic 48-stage inverter chain, 99 shapes below
  `m1.6`/`m5.4`, with `klt drc --deck sky130` reporting `status: "clean"` on
  it), the per-class root cause, and the tech-LEF evidence above.
- `2AMLogic/klayout-tools#2072` / `#2075` — the earlier filing. `#2075` fixed
  the same class of defect in `klt gen-compose`'s landing pads but explicitly
  did **not** reproduce the place-and-route half on its own corpus fixtures;
  `#2139` supplies the reproducer that half was missing.
- `2AMLogic/klayout-tools#1989` (merged, unreleased; `klt 0.5.0` is still the
  newest PyPI release as of 2026-09-19) adds the `met*.area.1` rules that would
  let `klt drc` see this itself — the same unreleased-fix gate issue #103 is
  already tracking for its own upstream blockers.

**What retires this waiver.** A `klayout-tools` release carrying a routed
output free of sub-minimum-area metal (`#2139`), re-run through
`bin/run-flow.sh` to mint a new record, with
`docs/chipalooza/measure_metal_min_area.py` reporting zero shapes for this flow
and `klt drc --deck sky130` — by then carrying `#1989`'s `met*.area.1` rules —
still reporting clean. Until then this is a **stated** limitation, not an
unmeasured one.

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

## `klt 0.4.0` → `0.5.0` re-run (issue #323): no change

This flow's sign-off record rested on `klt 0.4.0` (`reports/20260906-002022-a36e06f/`)
while `layout/requirements.txt` had already moved to `klt 0.5.0` for the other
sub-blocks and the top-level composition — a version-parity gap, not a known
defect (see the parent issue for why that gap mattered). Re-run under the
pinned `klt 0.5.0` (`reports/20260917-180644-527ec73/`, now `reports/LATEST`):
`drc.json` and `lvs.json` are field-identical to the superseded record —

| Field (source) | `klt 0.4.0` | `klt 0.5.0` | Delta |
| --- | --- | --- | --- |
| `drc.json` `status` / `violation_count` | clean / 0 | clean / 0 | none |
| `lvs.json` `status` | match | match | none |
| `lvs.json` `mismatch_count` / `error_count` | 9 / 0 | 9 / 0 | none |
| `lvs.json` `counts.devices` (layout/reference/matched) | 18/18/18 | 18/18/18 | none |
| `lvs.json` `counts.nets` (layout/reference/matched) | 20/20/20 | 20/20/20 | none |
| `lvs.json` `counts.pins` (layout/reference/matched) | 20/20/20 | 20/20/20 | none |
| `lvs.json` `category_counts` | `topology: 9` | `topology: 9` | none |

The nine `topology` entries are the same expected "ambiguous pairing resolved
structurally" warnings the Status section above describes (one per
symmetric, electrically-identical `SELn<i>` inverter), unchanged in count or
kind under `klt 0.5.0`. No regression, so no upstream `klayout-tools` issue
was filed for this re-run.

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

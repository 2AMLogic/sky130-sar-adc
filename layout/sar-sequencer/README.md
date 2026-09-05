# layout/sar-sequencer/ — SAR logic/sequencer physical layout (issue #102)

Physical layout for the SAR logic/sequencer sub-block: an (N+1)-stage
walking-one ring sequencer plus a 10-bit SAR register, captured in
`design/sar_sequencer.sch`/`.sym` (issue #55) on `sky130_fd_sc_hd` standard
cells. This directory places and routes that netlist and runs it through the
`klt` DRC/LVS flow, following `layout/README.md`'s (and `layout/trivial-cell/`'s)
conventions.

## Which `klt` flow, and why

**`klt place-and-route` (OpenROAD), not the full-custom `klt draw` flow.**
This sub-block is pure digital standard-cell logic with no analog matching/
symmetry judgement call (unlike the sampling front end, CDAC array, or
comparator sub-blocks) — placement and routing is exactly the kind of
decision a placer/router should make, not a hand-drawn one.

**`klt place-and-route` directly, *not* `klt synthesize` first.** `klt
synthesize` runs Yosys/ABC technology mapping from **RTL** — but this
sub-block has no RTL. `design/sar_sequencer.sch` already specifies exact
`sky130_fd_sc_hd` cell instances (dfrtp_1/mux2_1/or4_1/or3_1/inv_1) and
connectivity, already behaviorally verified against that exact netlist by
`sim/sar-sequencer-behavioral/`'s own testbench. Re-synthesizing from scratch
RTL through Yosys/ABC would let the tool pick *different* cells/drive
strengths than the ones already captured and simulated — laying out an
un-simulated netlist instead of the reviewed one. `layout/sar-sequencer/netlist/sar_sequencer.v`
is therefore a **hand-verified 1:1 structural transliteration** of the
schematic's own SPICE X-card connectivity (cross-checked line-for-line
against a real netlist snapshot in
`sim/sar-sequencer-behavioral/netlist-snapshots/*.spice`) into Verilog module-
instantiation syntax — not RTL synthesis output — and is fed straight to `klt
place-and-route`.

**Clock constraint**: `requests/place-and-route.json`'s `clock_period_ns:
83.33` (12 MHz) is `spec/decision-records/DR-006-sar-sequencer-bit-count-and-timing-budget.md`'s
own derived `f_clk,max` (the faster, more timing-demanding end of its
provisional `1.2 MHz – 12 MHz` range) — not an arbitrary number.

**Power delivery (`requests/place-and-route.json`'s `power` block)**: a real
PDN (`tapcell` well/substrate ties, `VPWR`/`VGND` global-connect, and
met1/met4/met5 straps — parameters taken from
`OpenROAD-flow-scripts`'s own published `platforms/sky130hd/pdn.tcl`
reference config, Apache/BSD-licensed EDA tooling config, not anyone's
silicon), not the row-rail-only obstruction `klt place-and-route` draws by
default when `power` is omitted. This is required for a *connected* `VPWR`/
`VGND`, not just an obstruction-shaped one — see "LVS reference provenance"
below for why an unconnected PDN made this sub-block's own LVS
un-passable, independent of any `klt` tool gap.

## Running the flow

```sh
layout/bin/setup-venv.sh              # once, or after bumping requirements.txt
source sim/env.sh                      # exports PDK_ROOT/PDK
layout/sar-sequencer/bin/run-flow.sh   # ~1-2 minutes; place-and-route -> DRC -> LVS
```

Requires an `openroad` binary on `$PATH` in addition to `layout/README.md`'s
own prerequisites (`klt place-and-route` invokes it as a subprocess) — see
`docs/environment-setup.md`.

Each run mints a new timestamped, append-only record under
`reports/<record-id>/` (same convention as `layout/trivial-cell/reports/`,
see `layout/README.md`): the input netlist, the resolved P&R request, the
routed GDS/DEF, the post-route netlist, the generated LVS reference, every
`klt` JSON envelope, and a human-readable `record.md`. `reports/LATEST`
points at the newest record id.

## Current status (as of the record referenced by `reports/LATEST`)

- **Place-and-route: succeeds.** Floorplan → global/detailed placement →
  clock-tree synthesis → global/detailed routing all complete at the 12 MHz
  clock constraint above with **zero setup/hold timing violations**.
- **DRC: clean.** `klt drc --deck sky130` reports 0 violations against the
  routed GDS.
- **LVS: clean.** `klt lvs` reports `status: "match"`, 760/760 devices and
  395/395 nets matched, 0 mismatches — see "LVS reference provenance" below
  for the three-part fix that got here from the `mismatch` verdict PR #105
  originally recorded.

## LVS reference provenance

`klt extract --deck sky130` is a **flat, transistor-level** extractor (its
own docstring: "extraction is flat"), so a `klt lvs` reference has to be flat
and transistor-level too — a hierarchical reference with `X`-instances of
`sky130_fd_sc_hd__*` standard cells cannot be compared circuit-for-circuit
against a flat layout netlist. `klt extract`'s sky130 deck also generalizes
every drawn NMOS/PMOS into two device classes, `nfet`/`pfet` (not
`nfet_01v8`/`special_nfet_01v8`/`pfet_01v8_hvt`), so the reference has to use
those same two generic model names.

`bin/generate-lvs-reference.py` builds that reference mechanically: it
parses `klt place-and-route`'s own **post-route** `write_verilog` dump (the
gate-level netlist *as actually routed* — `clock_tree_synthesis`/
`repair_design`/`repair_timing` legitimately insert clock buffers and repair
cells beyond the pre-P&R input netlist; verified by direct diff that these
are the *only* additions — no combinational-logic instance, port, or gate-
level connection differs from `netlist/sar_sequencer.v`'s own schematic-
derived topology) and flattens every instance against the sky130 PDK's own
official per-cell transistor-level CDL models
(`$PDK_ROOT/sky130A/libs.ref/sky130_fd_sc_hd/cdl/sky130_fd_sc_hd.cdl`,
Apache-2.0 licensed, SkyWater's own release — not reverse-engineered from
anyone's silicon or netlist).

### History: from `mismatch` (PR #105) to `match` (issue #102's own re-investigation)

PR #105 reached place-and-route + DRC-clean but recorded `klt lvs` as
`mismatch` with `matched: 0` nets/devices on both sides, despite the
reference's device count matching the layout-extracted netlist's own
**exactly** (760 = 760). It root-caused that to a `klt extract`
pin-name-promotion gap on a DEF→GDS-merged layout and filed
`2AMLogic/klayout-tools#1385` (fixed upstream by klt#1391/#1397, released in
klayout-tools 0.4.0). Bumping `layout/requirements.txt`'s pin to 0.4.0 and
switching this flow's LVS step from inline extraction
(`layout.top_cell_pins: true`) to a pre-extraction pass using the new `klt
extract --def-pins <def_path>` (deriving the declared pin set directly from
the routed DEF's own `PINS` section, instead of guessing from GDS label
nesting) did produce clean, canonical top-level pin names — but `klt lvs`
**still** reported a full `mismatch` (0/760, 0/415 nets/devices), even with
an explicit `hints.same_nets` assertion pairing `CLK` to `CLK` outright
rejected. Since `klt lvs` self-compare (the extracted netlist against an
unmodified copy of itself) matched 100% at this same scale, and neither pin
order nor a wholesale net-identity merge broke that self-compare, the
remaining full mismatch was not a `klt` engine limitation — it was a real
topological difference between the routed layout and this reference. Direct
inspection of the extracted netlist found two:

1. **The layout's `VPWR`/`VGND` were not single, unified nets.** `klt
   place-and-route` without a `request.power` block only draws a row-rail
   *obstruction* (`add_pdn_stripe -followpins` + `pdngen -dont_add_pins`,
   with no vertical straps) — enough to keep the router from routing through
   the rail, but not enough to tie every row's local power/ground segment
   into one global net. The routed GDS carried **7 disconnected `VGND`
   islands and 7 disconnected `VPWR` islands** (`VGND`, `VGND$1`..`VGND$6`,
   and the `VPWR` equivalents) — while the reference, like every real
   integration of this sub-block, assumes one global `VPWR` and one global
   `VGND`. Since nearly every device's body/supply terminal touches one of
   these nets, a 7-way split versus a 1-node reference poisoned enough of
   the graph to prevent `NetlistComparer` from establishing *any*
   correspondence, even with an exact device-count match and an explicit
   `same_nets` hint. Fixed by adding a real PDN
   (`requests/place-and-route.json`'s `power` block: `tapcell`
   well/substrate ties, `add_global_connection`/`pdngen` merging every
   `VPWR`/`VPB`/`VDDPE`/`VDDCE`-pattern pin into one `VPWR` net and every
   `VGND`/`VNB`/`VSSE`-pattern pin into one `VGND` net, plus met1/met4/met5
   straps) — parameters taken directly from `OpenROAD-flow-scripts`'s own
   published `platforms/sky130hd/pdn.tcl` reference config (Apache/BSD EDA
   tooling config, not anyone's silicon). This is a place-and-route
   *request* fix in this repo's own files, not a `klt` defect or gap: `klt
   place-and-route` already supports a full PDN via `request.power` — this
   sub-block's own request just hadn't asked for one. With the PDN in
   place, `VPWR`/`VGND` also become genuine promoted top-level pins (a real
   block-level P/G interface `pdngen`'s own `-pins` promotes), so
   `top_ports` in `generate-lvs-reference.py` now declares them too.
2. **`generate-lvs-reference.py` ignored the CDL's `m=` (finger-count)
   parameter.** `sky130_fd_sc_hd__buf_4`'s own CDL declares its output-stage
   transistors as `m=4` (four parallel fingers, not one finger at 4x the
   width) — `klt extract`'s `combine_devices` correctly folds the four
   physically-drawn layout fingers into one schematic-equivalent device at
   4x the per-finger width (confirmed: this sub-block's raw pre-fold
   `device_count` of 778 folds to exactly 760, matching 3 `buf_4` instances
   x 2 multi-finger output transistors x 3 folded-away redundant fingers),
   but the reference generator was reading only the CDL's bare per-finger
   `w=` and ignoring `m=` — understating that folded device's true width 4x
   for every `buf_4` instance's output stage. Fixed by scaling
   `w = CDL's w= * CDL's m=` when building each device's SPICE card (using
   `decimal.Decimal`, not `float`, so e.g. `0.65 * 4` prints as the exact
   `2.6` a human would write). With this fixed, the residual mismatch (24
   entries, all on the three `buf_4` clock-buffer instances'
   `device.unmatched`/`net.merged`/`net.split`) also cleared.

Once both were fixed, a fresh run reached `status: "match"`, 760/760
devices and 395/395 nets, 0 mismatches — with `--def-pins` alone (no
`--def-net-names` needed): `klt lvs` compares topology, not net *names*, so
the merged/joined pin-label names `--def-pins` still leaves in place (e.g.
`A0|DOUT0|Q`) never blocked the match once the underlying connectivity graph
was actually correct. `bin/run-flow.sh` always records whichever verdict
`klt lvs` actually reports, so a regression would show up as `mismatch` in
`record.md` with no script change required to detect it.

## Files

```
layout/sar-sequencer/
  README.md                        # this file
  netlist/
    sar_sequencer.v                # hand-verified structural netlist (not RTL) -- see "Which klt flow" above
  requests/
    place-and-route.json           # klt place-and-route request (clock/floorplan/io/power per above)
  bin/
    run-flow.sh                    # place-and-route -> DRC -> post-route netlist dump -> LVS reference -> extract --def-pins -> LVS -> record
    generate-lvs-reference.py      # flattens a structural Verilog netlist against the PDK's own CDL models
    render-record.py               # renders record.md from the JSON envelopes run-flow.sh produced
  reference/                       # generate-lvs-reference.py's own output -- regenerated per run, git-ignored
  reports/
    LATEST                         # record-id of the most recent run
    <record-id>/                   # append-only: netlist, request, routed GDS/DEF, post-route netlist,
                                    # generated LVS reference, klt JSON envelopes, record.md
```

## Provenance

Structure follows `layout/trivial-cell/`'s own conventions (append-only
timestamped records, `reports/LATEST` pointer, `record.md` provenance
stamping) per `CLAUDE.md`'s "Harness bootstrap" instruction, adapted for the
digital place-and-route flow this sub-block uses instead of `klt gen`/`klt
draw`. Clean room: the topology placed and routed is this repo's own
`design/sar_sequencer.sch` (issue #55); the only external inputs are the
sky130 PDK's own official, freely-licensed standard-cell library (LEF/
liberty/GDS/CDL) and OpenROAD's own placement/routing/CTS algorithms — never
another party's implementation.

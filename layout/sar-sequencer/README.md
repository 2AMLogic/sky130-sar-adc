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
- **LVS: blocked by a `klt`/klayout-tools tool gap, not a design defect** —
  see "LVS reference provenance" below for the full investigation. A generic
  writeup has been filed at `2AMLogic/klayout-tools#1385` (tool-gap only, per
  `CLAUDE.md`'s friction protocol).

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
anyone's silicon or netlist). This reproducibly produces a reference whose
device count matches the layout-extracted netlist's own **exactly** (760 =
760, after `klt lvs`'s `options.combine_devices` reconciles multi-finger
layout splits against the CDL's single-device abstraction).

Despite that exact device-count parity, `klt lvs` still reports `mismatch`
with `matched: 0` nets/devices on both sides. Root cause, isolated by direct
inspection of the merged GDS's own layer/label content
(`klt layers`/`klt extract --top-cell-pins`):

- The sky130 extraction deck only scans two layers for pin-name text
  (`decks/sky130.py`'s `metal_labels = ((67, 5), (68, 5))` — li1.pin/
  met1.pin). The very first attempt used `met2`/`met3` for
  `place-and-route.json`'s `io.layer_h`/`io.layer_v` (a typical OpenROAD I/O-
  pin layer choice) and produced **zero** usable top-level pin names; the
  request now uses `li1`/`met1` instead, which the deck does scan.
- Even so, `klt extract --top-cell-pins` (intended to promote only labels
  drawn directly in the top cell) still produces collided, `|`-joined pin
  names (e.g. `A0|DOUT2|Q`) and dozens of near-duplicate `CLK$1`..`CLK$18`
  entries for what should be ~4 real clock-tree segments. This traces to how
  a DEF→GDS merge fundamentally differs from a hand-drawn hierarchical
  layout: DEF's own `NETS` section records every net's physical pin
  connections as `(component, local-pin-name)` pairs, and every one of those
  connection points is geometrically *in the top cell* once the design is
  flattened by routing — unlike a hand-drawn `klt draw` layout, where a
  sub-cell's own internal pin labels are genuinely nested inside that
  instance's own view. `--top-cell-pins`'s "only labels drawn directly in
  the top cell" heuristic is exactly right for the latter and cannot
  distinguish the two for the former, so it ends up promoting per-instance
  local-pin-name labels (`A0`, `Q`, `S`, …) and clock-tree-segment labels
  right alongside genuine top-level design ports.
- Without a reliable set of top-level pin names, `klt lvs`'s
  `NetlistComparer` has no anchor to seed net/device correspondence on a
  ~760-device graph, and reports a full mismatch even though the two sides'
  device populations are demonstrably identical in count.

This is a `klt place-and-route` (Epic #391) / `klt extract`+`klt lvs` (Epic
#153) integration gap, not a defect in this sub-block's design or in the
reference-generation approach above — filed generically at
`2AMLogic/klayout-tools#1385` per `CLAUDE.md`'s friction protocol
(design-specific detail intentionally omitted from that filing). `bin/run-flow.sh` always
records whichever verdict `klt lvs` actually reports, so a rerun against a
future `klt` release that closes this gap will simply show `match` in
`record.md` with no script change required.

## Files

```
layout/sar-sequencer/
  README.md                        # this file
  netlist/
    sar_sequencer.v                # hand-verified structural netlist (not RTL) -- see "Which klt flow" above
  requests/
    place-and-route.json           # klt place-and-route request (clock/floorplan/io per above)
  bin/
    run-flow.sh                    # place-and-route -> DRC -> post-route netlist dump -> LVS reference -> LVS -> record
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

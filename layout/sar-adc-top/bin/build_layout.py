#!/usr/bin/env python3
"""Floorplan + route the top-level SAR ADC assembly (issue #103).

Composes the four already-closed sub-block layouts (`layout/sampling-frontend/`
#99, `layout/cdac-array/` #100, `layout/comparator/` #101, `layout/sar-sequencer/`
#102) plus this issue's own glue macro (`layout/seln-inverters/`, PR #166) into
one GDS matching `design/sar_adc_top.sch`'s hierarchy, per #103's scope:
**placement and interconnect/supply routing only -- no sub-block's own internal
layout is touched.** See `layout/sar-adc-top/README.md` for the full
floorplan/routing-plan writeup this module implements, including the
direct-GDS-inspection findings (cdac_array's own internal metal occupancy,
per-block pin geometry, the clear-layer corridors this router relies on) that
make the plan below safe.

Two verbs, same split `layout/comparator/bin/build_layout.py` established and
this flow reuses verbatim for the same reason (`klt gen-compose`'s own bundle
router is unproven for analog-quality nets, and here also has to reach ports on
four different native metal layers across five heterogeneous blocks -- routing
by hand against a router this repo controls is what makes a DRC/LVS-clean
verdict reachable at all):

* `compose.request.json` -- a `klt gen-compose` **explicit**-placement request
  naming each of the five sub-blocks as a `blocks[].cell` entry (#1189 -- an
  *existing* GDS cell this command did not itself generate) plus this script's
  own new `route` cell, with **no** `routing` block.
* `draw.request.json` -- every wire, via and top-level pin label this
  assembly's own interconnect needs, in the *composed* (global) coordinate
  system, fed to `klt draw`.

Floorplan
---------
Five blocks, explicitly placed, chosen so that **no two bounding boxes
overlap** (verified by `_check_no_overlap` below) and so that every net this
module has to route either (a) never needs to cross through another block's
own bounding box at all, or (b) crosses only through a region this module
verified by direct GDS inspection to be free of that block's own drawn
geometry on the layer used to cross it (`layout/sar-adc-top/README.md`
"Per-block internal-layer occupancy, verified by direct inspection"):

* `cdac_array` at the origin -- the floorplan's anchor; every other block's
  offset is chosen relative to it.
* `sampling_frontend` centred above `cdac_array` so that its own `TOP_P`/
  `TOP_N` pins sit near `cdac_array`'s `TOP_P`/`TOP_N` *midpoint* -- equalising
  the two nets' route lengths, since `cdac_array`'s own two `TOP_P`/`TOP_N`
  pins are fixed (by its already-closed #100 layout) ~219 um apart on opposite
  edges.
* `comparator` stacked further above `sampling_frontend`, at (very nearly) the
  same x -- both analog blocks' own `TOP_P`/`TOP_N`-net pins end up in one
  shared vertical corridor, so `TOP_P`/`TOP_N` each route as a simple chain
  (`cdac_array` -> `sampling_frontend` -> `comparator`) rather than a
  three-way star.
* `sar_sequencer` and `seln_inverters` placed well below `cdac_array` (a
  digital region entirely disjoint in y from the analog region above), side by
  side with `sar_sequencer`'s own right-edge I/O column facing
  `seln_inverters`' own left-edge I/O column across a shared channel.

Routing
-------
Every net is one of:

* **Same-block-edge extension** (`TOP_P`, `TOP_N`, `VREFP`, `VREFN`): the
  sub-block's own pin is already on the *escape* layer (`cdac_array`'s
  `TOP_P`/`TOP_N` are already met4, already routed almost to its own bbox
  edge) -- this module only extends the existing shape, on the same layer, no
  new via.
* **Analog-region crossing** (`TOP_P`, `TOP_N`, `VDD`, `SAMPLE_INT`, `CLK`,
  `COMP_OUT`): a per-net-exclusive `analog_leg()` Z-shape -- met4 vertical
  (at each endpoint's own x) up to a per-net `JOG_Y`, met3 horizontal at
  that `JOG_Y`, met4 vertical back down to the other endpoint. The met3/met4
  *layer* split (not just per-net y/x exclusivity) is load-bearing:
  `sampling_frontend` and `comparator` sit at overlapping x ranges, so two
  different nets' own met4 verticals routinely cross a third net's met4
  horizontal jog if drawn on one layer -- seeing this cross empirically via
  `klt extract` (not `klt drc`, which cannot see a same-layer short two
  different nets agree to share) is what drove the met3/met4 split; see
  `analog_leg()`'s own docstring.
* **Digital-channel fan-out** (`DOUT<i>`, `SELn<i>`): the same layer-split
  idea, met1 horizontals / met2 verticals, applied to the dense
  `sar_sequencer`<->`seln_inverters` I/O channel (19 nets sharing both
  macros' own single-column edges) -- see the `DOUT<i>`/`SELn<i>` loop's own
  comments for the two additional, non-obvious collisions found empirically
  there (a wide via-stack pad landing on a neighbour's trunk; two unrelated
  arithmetic sequences, `DROP_X` and `cdac_array`'s own per-pin `cx`,
  coincidentally landing within one pad-width of each other).
* **Basement crossing** (`sar_cross_to_analog`, used by `CLK`/`COMP_OUT`/
  `SAMPLE_INT`'s own `sar_sequencer`-side leg): escape east off
  `sar_sequencer`'s own bbox, onto met2 immediately (never met1, to stay
  invisible to the digital channel's own met1 pin-to-`DROP_X` stubs, whose
  union covers the *entire* channel width), down to a shared "basement" y
  below every block's own bbox, then into its own `analog_leg`. See that
  function's own docstring for the two collisions this shape works around.
* **Simple same-layer stub** (`VINP`, `VINN`, `VCM`, `RST_B`, `BUSY`,
  `DOUT9`, the switch-row `SELp<i>`/`SELn<i>` cdac-side risers): a riser
  (`Canvas.riser()`) at the pin's own position plus a short lead to an
  external pin label, or vice versa -- no long-haul highway needed.

Clean room: every number in this module was measured directly from this
repo's own already-committed sub-block GDS/DEF artefacts (`klt cells`, a
direct `klayout.db` shape dump, or the routed DEF's own `PINS` section) --
never from any third-party layout, floorplan, or netlist.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

DBU = 1000  # nm per um


def nm(v: float) -> int:
    return int(round(v * DBU))


# --------------------------------------------------------------------------- #
# sky130 layer table (same numbering every other layout/ flow in this repo
# uses -- klayout_tools.decks.sky130, klt==0.4.0).
# --------------------------------------------------------------------------- #
POLY_PIN = (66, 5)
LI1 = (67, 20)
MCON = (67, 44)
MET1 = (68, 20)
MET1_PIN = (68, 5)
VIA1 = (68, 44)
MET2 = (69, 20)
MET2_PIN = (69, 5)
VIA2 = (69, 44)
MET3 = (70, 20)
VIA3 = (70, 44)
MET4 = (71, 20)
MET4_PIN = (71, 5)

# Adjacency chain used by `riser()` to walk from one layer to another --
# MET1 <-> MET2 <-> MET3 <-> MET4 (a poly/li1 pad walks one extra step,
# LI1 <-> MET1, via `mcon`).
_METAL_CHAIN = [LI1, MET1, MET2, MET3, MET4]
_VIA_BETWEEN = {
    (LI1, MET1): MCON,
    (MET1, MET2): VIA1,
    (MET2, MET3): VIA2,
    (MET3, MET4): VIA3,
}

PAD_UM = 0.36  # generic via/wire landing pad side. Bigger than
#                layout/cdac-array/bin/cdac_layout.py's own PAD_HALF*2 (0.32)
#                deliberately: that convention relies on the *caller*
#                drawing a separately-sized met3 shape (e.g. a capacitor
#                plate) to satisfy met3.enclosing.via2 (0.065 um); this
#                module draws freestanding via stacks with no such plate, so
#                every pad here has to satisfy the tightest enclosure on its
#                own -- 0.36 gives via2/via3 (0.20 um, below) a 0.08 um
#                margin, comfortably over the 0.065 threshold.
VIA1_UM = 0.15  # via1 (met1<->met2) square side -- matches this repo's own
#                 layout/comparator/bin/build_layout.py VIA1_S convention.
VIA_UM = 0.20  # via2/via3 (met2<->met3, met3<->met4) square side --
#                matches layout/cdac-array/bin/cdac_layout.py's VIA_S.
MCON_UM = 0.17  # li1<->met1 -- matches this repo's own MCON_S convention.
WIRE_W = 0.40  # highway wire width -- generous; these runs are long and
#                unconstrained, not density-critical
ESCAPE_W = 0.14  # sar_sequencer/seln_inverters own routed-DEF pin box height
#                  (0.14 um -- `met1.width`'s own minimum) -- an escape lead
#                  at THIS block's own already-legal track width, used to
#                  clear its bbox edge before this module's own,
#                  much-larger via risers land (see `dig_escape()`): a
#                  PAD_UM-wide via built directly at the reported pin
#                  position is wider than the routed track around it and
#                  violates met1.space.1 against the macro's own adjacent,
#                  unrelated nets (found empirically -- see the PR
#                  description).


def _layer_index(layer: tuple[int, int]) -> int:
    return _METAL_CHAIN.index(layer)


class Canvas:
    """Shape/label accumulator -- the same minimal drawing surface every
    other `bin/build_layout.py` in this repo uses, re-derived here (rather
    than imported) because this flow's "pin" is `(x, y, layer)` triples
    across *five* blocks' own native layers, not one block's own
    `klt gen` report table."""

    def __init__(self) -> None:
        self.shapes: list[tuple[tuple[int, int], tuple[float, float, float, float]]] = []
        self.labels: list[tuple[tuple[int, int], str, float, float]] = []

    def rect(self, layer: tuple[int, int], x0: float, y0: float, x1: float, y1: float) -> None:
        self.shapes.append((layer, (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))))

    def square(self, layer: tuple[int, int], cx: float, cy: float, side: float) -> None:
        h = side / 2.0
        self.rect(layer, cx - h, cy - h, cx + h, cy + h)

    def wire(self, layer: tuple[int, int], x0: float, y0: float, x1: float, y1: float, w: float = WIRE_W) -> None:
        h = w / 2.0
        if abs(x0 - x1) < 1e-9 and abs(y0 - y1) < 1e-9:
            return
        if abs(x0 - x1) < 1e-9:
            self.rect(layer, x0 - h, min(y0, y1) - h, x0 + h, max(y0, y1) + h)
        elif abs(y0 - y1) < 1e-9:
            self.rect(layer, min(x0, x1) - h, y0 - h, max(x0, x1) + h, y0 + h)
        else:
            raise ValueError(f"wire must be axis-aligned: ({x0},{y0})-({x1},{y1})")

    def via(self, at_layer_lo: tuple[int, int], at_layer_hi: tuple[int, int], x: float, y: float) -> None:
        """One via/mcon cut, with a landing pad on both adjoining metals."""
        cut = _VIA_BETWEEN[(at_layer_lo, at_layer_hi)]
        cut_side = {MCON: MCON_UM, VIA1: VIA1_UM}.get(cut, VIA_UM)
        self.square(at_layer_lo, x, y, PAD_UM)
        self.square(at_layer_hi, x, y, PAD_UM)
        self.square(cut, x, y, cut_side)

    def riser(self, x: float, y: float, from_layer: tuple[int, int], to_layer: tuple[int, int]) -> None:
        """Stack via cuts directly above/below (x, y) to walk from
        `from_layer` to `to_layer` (either direction) through every
        intermediate metal in `_METAL_CHAIN`. Never moves laterally -- every
        cut lands at the exact same (x, y) the caller's own pin already
        reported, so this only ever adds new *vertical* (in the process
        sense) conductor, never anything that could spill onto a
        neighbour's shape."""
        lo, hi = sorted((_layer_index(from_layer), _layer_index(to_layer)))
        for i in range(lo, hi):
            self.via(_METAL_CHAIN[i], _METAL_CHAIN[i + 1], x, y)

    def label(self, layer: tuple[int, int], x: float, y: float, text: str) -> None:
        self.labels.append((layer, text, x, y))

    def path(self, layer: tuple[int, int], points: list[tuple[float, float]], w: float = WIRE_W) -> None:
        """A Manhattan polyline: `points` must alternate strictly in x xor y
        between consecutive entries (no diagonal legs)."""
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            self.wire(layer, x0, y0, x1, y1, w=w)


def _pin_layer_for(layer: tuple[int, int]) -> tuple[int, int]:
    return {LI1: MET1_PIN, MET1: MET1_PIN, MET2: MET2_PIN, MET3: None, MET4: MET4_PIN}[layer]


# --------------------------------------------------------------------------- #
# Per-block placement offsets (um). Chosen so no two bboxes overlap (checked
# below) and so the analog TOP_P/TOP_N route lengths are (very nearly) equal
# -- see the module docstring's "Floorplan" section.
# --------------------------------------------------------------------------- #
OFFSETS = {
    "cdac_array": (0.0, 0.0),
    "sampling_frontend": (63.825, 88.25),
    "comparator": (100.2, 173.8),
    "sar_sequencer": (21.1175, -150.0),
    "seln_inverters": (87.6875, -150.0),
}

# Each sub-block's own bbox, in ITS OWN local frame -- verified directly
# against the committed GDS (`klt cells` / a direct klayout.db bbox read),
# not transcribed from any README prose.
BBOX = {
    "cdac_array": (-4.5, -35.0, 218.7, 55.85),
    "sampling_frontend": (0.0, -2.4, 195.56, 58.05),
    "comparator": (0.0, 2.5, 24.0, 38.65),
    "sar_sequencer": (0.0, 0.0, 42.57, 42.57),
    "seln_inverters": (0.0, 0.0, 86.195, 86.195),
}

# Each sub-block's own top GDS cell name (needed for the `blocks[].cell`
# request entries) and the GDS file this flow reads it from -- paths are
# resolved relative to this script's own reports/<record-id>/ working
# directory by run-flow.sh, which copies each source GDS in first.
CELL_NAME = {
    "cdac_array": "cdac_array",
    "sampling_frontend": "gen_compose_0",
    "comparator": "gen_compose_0",
    "sar_sequencer": "sar_sequencer",
    "seln_inverters": "seln_inverters",
}

# Every pin this assembly's own interconnect touches: (block, name) ->
# (x_um, y_um, layer) in that block's OWN LOCAL frame. Verified directly:
# cdac_array by direct klayout.db shape/label inspection against
# layout/cdac-array/reports/LATEST/cdac_array.gds (post-#165 -- the VDD
# entry is the real met1 landing pad the #165 fix drew, NOT the nwell pin
# label position, which sits on bare, uncontactable nwell -- see the
# README's "cdac_array.VDD: label position vs. real landing point" note);
# sampling_frontend/comparator by the same direct inspection against their
# own committed GDS; sar_sequencer/seln_inverters from their own routed
# DEF's `PINS` section (the authoritative top-level port declaration these
# two macros' own LVS flow already relies on -- GDS labels there also carry
# every internal std-cell pin name, not just top-level ports).
PIN = {
    ("cdac_array", "TOP_P"): (-2.4, 27.55, MET4),
    ("cdac_array", "TOP_N"): (216.8, 27.55, MET4),
    ("cdac_array", "VDD"): (1.00, -26.37, MET1),
    ("cdac_array", "VREFP"): (-2.0, -34.8, MET1),
    ("cdac_array", "VREFN"): (-2.0, -33.4, MET2),
    ("sampling_frontend", "VDD"): (1.76, 50.90, MET2),
    ("sampling_frontend", "SAMPLE"): (2.67, 50.40, MET2),
    ("sampling_frontend", "VINP"): (10.10, 53.40, MET2),
    ("sampling_frontend", "VINN"): (22.90, 53.90, MET2),
    ("sampling_frontend", "VCM"): (13.30, 51.90, MET2),
    ("sampling_frontend", "TOP_P"): (42.23, 57.40, MET2),
    ("sampling_frontend", "TOP_N"): (44.52, 57.90, MET2),
    ("comparator", "GND"): (1.3, 20.0, MET1),
    ("comparator", "VINN"): (4.9, 20.0, MET1),
    ("comparator", "VINP"): (9.1, 20.0, MET1),
    ("comparator", "OUTP"): (10.1, 18.5, MET1),
    ("comparator", "OUTN"): (10.6, 18.0, MET1),
    ("comparator", "VDD"): (17.9, 15.0, MET1),
    ("comparator", "CLK"): (1.9, 24.5, MET1),
    ("sar_sequencer", "PH_SAMPLE"): (42.272, 17.85, MET1),
    ("sar_sequencer", "CLK"): (42.272, 21.25, MET1),
    ("sar_sequencer", "RST_B"): (42.272, 22.61, MET1),
    ("sar_sequencer", "COMP_OUT"): (42.272, 26.01, MET1),
    ("sar_sequencer", "BUSY"): (42.272, 30.09, MET1),
    **{
        ("sar_sequencer", f"DOUT{i}"): (42.272, y, MET1)
        for i, y in enumerate(
            [21.93, 19.89, 19.21, 29.41, 26.69, 18.53, 17.17, 16.49, 23.29, 28.73]
        )
    },
    **{
        ("seln_inverters", f"DOUT{i}"): (0.297, y, MET1)
        for i, y in enumerate([49.13, 43.01, 43.69, 44.37, 39.61, 38.25, 45.73, 42.33, 46.41])
    },
    **{
        ("seln_inverters", f"SELn{i}"): (0.297, y, MET1)
        for i, y in enumerate([41.65, 47.77, 45.05, 38.93, 40.97, 48.45, 37.57, 47.09, 40.29])
    },
    **{("cdac_array", f"SELp{i}"): (3.945 + 11 * i, -28.08, LI1) for i in range(9)},
    **{("cdac_array", f"SELn{i}"): (102.945 + 11 * i, -28.08, LI1) for i in range(9)},
}


def global_pin(block: str, name: str) -> tuple[float, float, tuple[int, int]]:
    x, y, layer = PIN[(block, name)]
    dx, dy = OFFSETS[block]
    return x + dx, y + dy, layer


def global_bbox(block: str) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = BBOX[block]
    dx, dy = OFFSETS[block]
    return x0 + dx, y0 + dy, x1 + dx, y1 + dy


def _check_no_overlap() -> None:
    names = list(BBOX)
    for i, a in enumerate(names):
        ax0, ay0, ax1, ay1 = global_bbox(a)
        for b in names[i + 1 :]:
            bx0, by0, bx1, by1 = global_bbox(b)
            overlap = ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1
            if overlap:
                raise SystemExit(f"build_layout.py: floorplan overlap: {a} and {b}")


# --------------------------------------------------------------------------- #
# Highway tracks. Every number here was chosen against the module docstring's
# floorplan (verified clear of every block's own bbox in `_check_no_overlap`'s
# sense -- a highway track is drawn only in y (or x) ranges no placed block's
# bbox occupies, except where it deliberately climbs into cdac_array's own
# confirmed-clear switch-row band; see README.md for that verification).
# --------------------------------------------------------------------------- #
WEST_CORRIDOR_X = {  # one exclusive met4 x-track per net that has to cross
    #                  from the digital region (y < -35) to the analog one
    #                  (y > 55.85), fully west of every block's own bbox
    "VDD": -8.0,
    "CLK": -10.0,
    "COMP_OUT": -12.0,
}
CDAC_CROSS_Y = -28.08  # met3 y this module crosses cdac_array's own bbox at
#                        -- inside the confirmed-clear switch-row band
#                        (README.md: met3/met4 have zero shapes for
#                        y in [-35, -25] across the full array width)


#: Escape direction for each digital macro's own I/O column -- `sar_sequencer`
#: exposes its column on its own right edge (bbox x1), `seln_inverters` on its
#: own left edge (bbox x0) -- see the module docstring's "Floorplan". The
#: distance (1.7 um) only has to clear each macro's own ~0.3 um pin inset
#: from its bbox edge; every net using this escape then travels further
#: still open channel/corridor space, so the exact landing x is not otherwise
#: load-bearing.
DIG_ESCAPE_DX = {"sar_sequencer": 1.7, "seln_inverters": -1.7}


def dig_escape(c: Canvas, block: str, pin: str) -> tuple[float, float]:
    """Extend `(block, pin)` (a `sar_sequencer`/`seln_inverters` met1 signal
    pin) straight out past that macro's own bbox edge on a THIN
    (`ESCAPE_W`-wide) met1 lead, at the macro's own already-legal track
    width, before this module's own wider via risers touch anything -- see
    `ESCAPE_W`'s own docstring for why a wide via built directly on the
    reported pin position is unsafe here. Returns the staging point, now
    safely outside the macro's own bbox. Every net using this helper is at
    its own distinct native (block, pin) y (the routed DEF never repeats a
    y across two different pins), so two different nets' escape leads never
    collide even though they share the exact same escape direction/x."""
    x, y, native = global_pin(block, pin)
    assert native == MET1
    dx = DIG_ESCAPE_DX[block]
    ex = x + dx
    c.wire(MET1, x, y, ex, y, w=ESCAPE_W)
    return ex, y


#: Per-net basement y (safely below every placed block's own bbox -- the
#: lowest is sar_sequencer/seln_inverters at -150.0), one for each net that
#: crosses via `sar_cross_to_analog`. Distinct per net (0.7 um pitch,
#: comfortably clearing met4.space): see that function's own docstring for
#: why sharing one y across multiple callers is a real short, not a
#: harmless coincidence.
BASEMENT_Y = {"CLK": -160.0, "COMP_OUT": -160.7, "PH_SAMPLE": -161.4}


#: A y safely below every DOUT<i>/SELn<i> met2 trunk's own bottom (the
#: deepest is row_y for k=17, -42.0 - 0.7*17 = -53.9 -- see the DOUT<i>/
#: SELn<i> loop below) -- used by `sar_cross_to_analog` so its own met1->
#: met4 riser (a `PAD_UM`-wide pad on every intermediate metal, not just
#: met1/met4) lands well clear of that channel instead of inside it.
BELOW_CHANNEL_Y = -56.0


def sar_cross_to_analog(
    c: Canvas, pin: str, escape_x: float, corridor_x: float, basement_y: float
) -> tuple[float, float]:
    """Route a `sar_sequencer` met1 signal pin east (thin lead, clearing its
    own bbox), then *immediately* onto met2 for the whole southward drop to
    `BELOW_CHANNEL_Y`, up to met4 *there*, further south into the shared
    basement (below every block's own bbox), then west to `corridor_x` --
    never re-crossing `sar_sequencer`'s own bbox on met2/met3/met4, all
    three of which it uses internally for its own routing (its own DEF/GDS
    report `VIA_M2M3_PR`/`VIA_via3_4_*`/`VIA_via4_5_*` instances) -- unlike a
    straight shot west at the pin's own height, which would cut directly
    across its own interior.

    Two collisions found empirically (`klt extract`, not `klt drc`, which is
    blind to same-layer shapes uniting on purpose vs. by accident -- see the
    PR description for both) drive this shape:

    1. This net's own escape column runs right through the
       `sar_sequencer`<->`seln_inverters` channel the DOUT<i>/SELn<i> loop
       below packs with its own met1 pin-to-`DROP_X` stubs. Those stubs all
       originate from the *same two shared points* (`sar_sequencer`'s own
       single I/O-column x, `seln_inverters`' own single I/O-column x) and
       fan out to eighteen different `DROP_X` columns, so their union
       covers *the entire channel width* on met1 -- there is no met1 x in
       this channel a crossing net's own vertical can occupy without
       perpendicularly crossing at least one of them (a real short: two
       different nets' shapes touching at a point merges them, regardless
       of either one's width). This module's own vertical drop is on met2
       instead -- a plain parallel-line clearance problem against
       DOUT<i>/SELn<i>'s own met2 `DROP_X` trunks (a fixed, short list to
       stay `>= 0.3 um` from), not the met1 stub-shadow's effectively
       whole-channel reach.
    2. `Canvas.riser()` draws a `PAD_UM`-wide (0.36 um) pad on every
       intermediate metal it walks through. Landing the met1->met4 riser
       (which walks met2 and met3) at the pin's own height, inside the
       channel, put a stray met2 pad on top of a DOUT<i>/SELn<i> met2
       trunk. Doing the whole met2 drop down to `BELOW_CHANNEL_Y` (below
       every DOUT<i>/SELn<i> trunk's own bottom) before building the
       met2->met4 riser keeps that riser's own pads in the clear
       regardless of where `escape_x` falls.

    `escape_x` is the caller's own choice of a per-net x for the eastward
    escape + southward drop (distinct from every `DROP_X` entry by more
    than met2.space, and distinct across every net that calls this);
    `basement_y` is the caller's own choice of a per-net y for the final
    westward leg -- also distinct across every caller (an earlier version
    of this module shared one `basement_y`, whose westward legs then
    overlapped in x at the same y and merged into one net). Returns the
    corridor landing point, ready for the caller to continue north."""
    x, y, native = global_pin("sar_sequencer", pin)
    assert native == MET1
    c.wire(MET1, x, y, escape_x, y, w=ESCAPE_W)
    c.via(MET1, MET2, escape_x, y)
    c.wire(MET2, escape_x, y, escape_x, BELOW_CHANNEL_Y, w=ESCAPE_W)
    c.riser(escape_x, BELOW_CHANNEL_Y, MET2, MET4)
    c.path(MET4, [(escape_x, BELOW_CHANNEL_Y), (escape_x, basement_y), (corridor_x, basement_y)])
    return corridor_x, basement_y


def _riser_and_highway(
    c: Canvas,
    block: str,
    pin: str,
    highway_layer: tuple[int, int],
    label: str | None = None,
) -> tuple[float, float]:
    """Build a via riser from `(block, pin)`'s own native layer up/down to
    `highway_layer`, exactly at its own reported position (never moving
    laterally -- see `Canvas.riser`'s own docstring for why that is safe).
    Returns the riser's own (x, y) on the highway layer, ready for the
    caller to route out of. Optionally drops a `label` there (used only for
    the sub-block-facing end of an otherwise-unconnected top-level port)."""
    x, y, native = global_pin(block, pin)
    c.riser(x, y, native, highway_layer)
    if label:
        pin_layer = _pin_layer_for(highway_layer)
        if pin_layer:
            c.label(pin_layer, x, y, label)
    return x, y


#: Per-net jog row for the analog-region crossing pattern (`analog_leg`
#: below), one exclusive y each, all safely above `comparator`'s own bbox
#: top edge (212.45) -- see `analog_leg`'s own docstring for why every net
#: needs its own y here (an earlier version of this module shared trunk
#: heights between nets, whose own vertical taps down to `sampling_frontend`/
#: `comparator` then crossed a *different* net's shared horizontal trunk;
#: found empirically via `klt extract`, not `klt drc` -- see the PR
#: description).
JOG_Y = {"TOP_P": 220.0, "TOP_N": 220.7, "VDD": 221.4, "SAMPLE_INT": 222.1}


def analog_leg(c: Canvas, x0: float, y0: float, x1: float, y1: float, jog_y: float) -> None:
    """One Z-shaped leg of an analog-region net: met4 vertical at `x0` from
    `y0` up to `jog_y`, met3 horizontal at `jog_y` from `x0` to `x1`, met4
    vertical at `x1` from `jog_y` down to `y1`.

    Every analog-region net (`TOP_P`/`TOP_N`/`VDD`/`SAMPLE_INT`, each with
    its own exclusive `jog_y`) is built from one or more of these legs
    sharing the same `jog_y` and `x0` -- multiple legs off the same `x0`
    merge into one net exactly like `Router.route_spine` does in
    `layout/comparator/bin/build_layout.py`. The met3/met4 layer split is
    load-bearing, not stylistic: `sampling_frontend`/`comparator` sit at
    overlapping x ranges (`comparator` almost directly above
    `sampling_frontend`), so two different nets' own met4 *verticals*
    (dropping down to their own pins) routinely cross a third net's met4
    *horizontal* jog if both were drawn on the same layer -- moving every
    horizontal jog to met3 removes that risk regardless of x/y overlap,
    the same fix `layout/sar-adc-top/README.md`'s "Routing" section applies
    to the digital region's own dense channel (met1 horizontals, met2
    verticals)."""
    c.wire(MET4, x0, y0, x0, jog_y, w=WIRE_W)
    c.riser(x0, jog_y, MET4, MET3)
    c.wire(MET3, x0, jog_y, x1, jog_y, w=WIRE_W)
    c.riser(x1, jog_y, MET3, MET4)
    c.wire(MET4, x1, jog_y, x1, y1, w=WIRE_W)


def build() -> tuple[dict, dict]:
    _check_no_overlap()
    c = Canvas()

    # ------------------------------------------------------------------ #
    # 1. TOP_P / TOP_N -- cdac_array's own pin is already met4, already
    #    routed almost to its own bbox edge; extended a little further past
    #    that edge (still met4, same already-established net -- TOP_N's own
    #    edge (216.8) falls *inside* sampling_frontend's own bbox x-range,
    #    so it is walked further east, past sampling_frontend's own right
    #    edge (259.385), before turning north -- never straight up through
    #    sampling_frontend's own interior) before each net's own
    #    `analog_leg` pair reaches sampling_frontend/comparator.
    # ------------------------------------------------------------------ #
    cx, cy, _ = global_pin("cdac_array", "TOP_P")
    fx, fy = _riser_and_highway(c, "sampling_frontend", "TOP_P", MET4)
    px, py = _riser_and_highway(c, "comparator", "VINP", MET4)
    analog_leg(c, cx, cy, px, py, JOG_Y["TOP_P"])
    analog_leg(c, fx, fy, fx, fy, JOG_Y["TOP_P"])  # tees into the leg above

    cx, cy, _ = global_pin("cdac_array", "TOP_N")
    ex = 260.0  # east of sampling_frontend's own right edge (259.385)
    c.wire(MET4, cx, cy, ex, cy, w=WIRE_W)
    fx, fy = _riser_and_highway(c, "sampling_frontend", "TOP_N", MET4)
    px, py = _riser_and_highway(c, "comparator", "VINN", MET4)
    analog_leg(c, ex, cy, px, py, JOG_Y["TOP_N"])
    analog_leg(c, fx, fy, fx, fy, JOG_Y["TOP_N"])

    # ------------------------------------------------------------------ #
    # 2. VDD (analog): cdac_array + sampling_frontend + comparator + one
    #    external pin. cdac_array's own VDD pin sits deep inside its own
    #    bbox (switch row, y ~ -26) with the whole rest of the array's own
    #    interior between it and the analog region above -- riser to met3
    #    inside the confirmed-clear switch-row band, exit west (the only
    #    direction with no block bbox anywhere along the whole vertical
    #    span), then climb the west corridor into its own `analog_leg`.
    # ------------------------------------------------------------------ #
    vx, vy, _ = global_pin("cdac_array", "VDD")
    c.riser(vx, vy, MET1, MET3)
    wx = WEST_CORRIDOR_X["VDD"]
    c.wire(MET3, vx, vy, wx, vy, w=WIRE_W)
    c.riser(wx, vy, MET3, MET4)
    fx, fy = _riser_and_highway(c, "sampling_frontend", "VDD", MET4)
    px, py = _riser_and_highway(c, "comparator", "VDD", MET4)
    analog_leg(c, wx, vy, px, py, JOG_Y["VDD"])
    analog_leg(c, fx, fy, fx, fy, JOG_Y["VDD"])
    # External VDD pin: a further stub off the met3 jog row itself, west of
    # the corridor (still clear of every block's own bbox), stepped back up
    # to met4 to land the label (this module has no met3 pin layer -- every
    # other external pin in this flow is met1/met2/met4). -20.0 clears every
    # other west-corridor/basement-crossing x this module uses (-8/-10/-12/
    # -14) -- an earlier version landed here at -14.0, exactly on top of
    # SAMPLE_INT's own dedicated crossing column, and merged the two nets
    # (found empirically via `klt extract`; see the PR description).
    ext_x = -20.0
    c.wire(MET3, wx, JOG_Y["VDD"], ext_x, JOG_Y["VDD"], w=WIRE_W)
    c.riser(ext_x, JOG_Y["VDD"], MET3, MET4)
    c.label(MET4_PIN, ext_x, JOG_Y["VDD"], "VDD")

    # ------------------------------------------------------------------ #
    # 3. VREFP / VREFN: cdac_array + one external pin each. Already on
    #    their own native layer right at cdac_array's own left edge --
    #    just extend a short stub further west (still same layer, no via).
    # ------------------------------------------------------------------ #
    for net, layer in (("VREFP", MET1), ("VREFN", MET2)):
        x, y, _ = global_pin("cdac_array", net)
        ext_x = -15.0
        c.path(layer, [(x, y), (ext_x, y)])
        c.label(MET1_PIN if layer == MET1 else MET2_PIN, ext_x, y, net)

    # ------------------------------------------------------------------ #
    # 4. CLK / COMP_OUT: comparator (analog) <-> sar_sequencer (digital).
    #    Each crosses via `sar_cross_to_analog` (its own escape x, so the
    #    two nets' met4 drops never collide) into its own exclusive west
    #    corridor track, then up to the analog highway. CLK additionally
    #    reaches an external pin, labelled directly on its own escape lead.
    # ------------------------------------------------------------------ #
    for net, comp_pin, seq_pin, escape_x, jog_y in (
        ("CLK", "CLK", "CLK", 65.6, 223.0),
        ("COMP_OUT", "OUTP", "COMP_OUT", 66.5, 223.7),
    ):
        wx = WEST_CORRIDOR_X[net]
        px, py = _riser_and_highway(c, "comparator", comp_pin, MET4)
        cx0, cy0 = sar_cross_to_analog(c, seq_pin, escape_x, wx, BASEMENT_Y[net])
        analog_leg(c, wx, cy0, px, py, jog_y)
    sx, sy, _ = global_pin("sar_sequencer", "CLK")
    c.label(MET1_PIN, sx + 0.8, sy, "CLK")

    # ------------------------------------------------------------------ #
    # 5. Digital region: SAMPLE_INT, RST_B, BUSY, DOUT<i>, SELn<i>.
    # ------------------------------------------------------------------ #
    # SAMPLE_INT: sar_sequencer.PH_SAMPLE -> sampling_frontend.SAMPLE, same
    # west-corridor crossing pattern as CLK/COMP_OUT (its own escape x).
    wx = -14.0
    cx0, cy0 = sar_cross_to_analog(c, "PH_SAMPLE", 67.4, wx, BASEMENT_Y["PH_SAMPLE"])
    fx, fy = _riser_and_highway(c, "sampling_frontend", "SAMPLE", MET4)
    analog_leg(c, wx, cy0, fx, fy, JOG_Y["SAMPLE_INT"])

    # RST_B, BUSY: sar_sequencer <-> one external pin each (thin escape +
    # a short, still-thin extension -- no other net shares this exact
    # (x, y), so width is not otherwise load-bearing here).
    for net, pin in (("RST_B", "RST_B"), ("BUSY", "BUSY")):
        ex, ey = dig_escape(c, "sar_sequencer", pin)
        c.wire(MET1, ex, ey, ex + 3.0, ey, w=ESCAPE_W)
        c.label(MET1_PIN, ex + 3.0, ey, net)

    # DOUT<i> (i=0..9) / SELn<i> (i=0..8): the channel between sar_sequencer
    # and seln_inverters is dense (19 nets share the same two macros' own
    # single-column I/O edges), so every one of these gets its own
    # exclusive (drop_x, row_y) pair -- see the module docstring's
    # "Routing" section and `DROP_X`/`ROW_Y`'s own comment for why
    # horizontals stay on met1 and verticals on met2 throughout: two
    # different *layers* never collide regardless of geometric overlap,
    # which is what makes 19 independent nets tractable through one shared
    # open channel without a general channel-routing search.
    # 1.0 um pitch (not the 0.7 um met1/met2 minimum-legal pitch used
    # elsewhere in this module): `sar_cross_to_analog`'s own met2->met4
    # riser lands a `PAD_UM`-wide (0.36 um) pad at its own escape x, roughly
    # midway between two `DROP_X` entries -- clearing a thin (met2.width,
    # 0.14 um) `DROP_X` trunk by met2.space (0.14 um) from a 0.36 um-wide
    # pad needs 0.18 + 0.07 + 0.14 = 0.39 um from centre to centre, which a
    # 0.7 um pitch's own midpoint (0.35 um either way) does not clear
    # (found empirically via `klt drc`, not by hand-checking every
    # clearance in advance; see the PR description). 1.0 um pitch gives a
    # 0.5 um-clear midpoint instead.
    # The 68.45 phase (not 68.0) is also load-bearing, not just the 1.0 um
    # pitch: cdac_array's own SELp<i>/SELn<i> `cx` values (3.945 + 11*i,
    # 102.945 + 11*i) are a *different* arithmetic sequence than `DROP_X`,
    # and a 68.0 phase put SELp6's own cx (69.945) 0.055 um from DOUT2's own
    # drop_x (70.0) -- close enough that SELp6's own met1->met3 riser (built
    # while routing DOUT6, a completely unrelated net) landed its
    # intermediate met2 pad on top of DOUT2's own met2 trunk (found
    # empirically via `klt extract`, the same class of bug as
    # `sar_cross_to_analog`'s own -- see the PR description). 68.45 clears
    # every `cx` this loop uses by >= 0.495 um.
    order: list[tuple[str, int]] = [("DOUT", i) for i in range(9)] + [("SELn", i) for i in range(9)]
    DROP_X = {key: 68.45 + 1.0 * k for k, key in enumerate(order)}
    ROW_Y = {key: -42.0 - 1.0 * k for k, key in enumerate(order)}

    # DOUT9: sar_sequencer + external pin only (no seln_inverters/cdac_array
    # member) -- a plain escape + label, no channel/drop_x needed.
    ex, ey = dig_escape(c, "sar_sequencer", "DOUT9")
    c.wire(MET1, ex, ey, ex + 3.0, ey, w=ESCAPE_W)
    c.label(MET1_PIN, ex + 3.0, ey, "DOUT9")

    for i in range(9):
        key = ("DOUT", i)
        drop_x, row_y = DROP_X[key], ROW_Y[key]

        sx, sy, _ = global_pin("sar_sequencer", f"DOUT{i}")
        c.wire(MET1, sx, sy, drop_x, sy, w=ESCAPE_W)
        c.via(MET1, MET2, drop_x, sy)

        ix, iy, _ = global_pin("seln_inverters", f"DOUT{i}")
        c.wire(MET1, ix, iy, drop_x, iy, w=ESCAPE_W)
        c.via(MET1, MET2, drop_x, iy)

        c.wire(MET2, drop_x, sy, drop_x, row_y, w=ESCAPE_W)
        c.via(MET1, MET2, drop_x, row_y)
        c.label(MET2_PIN, drop_x, row_y, f"DOUT{i}")

        cx, cy, _ = global_pin("cdac_array", f"SELp{i}")
        c.wire(MET1, drop_x, row_y, cx, row_y, w=ESCAPE_W)
        c.riser(cx, row_y, MET1, MET3)
        c.wire(MET3, cx, row_y, cx, CDAC_CROSS_Y, w=WIRE_W)
        c.riser(cx, CDAC_CROSS_Y, MET3, LI1)

    for i in range(9):
        key = ("SELn", i)
        drop_x, row_y = DROP_X[key], ROW_Y[key]

        ix, iy, _ = global_pin("seln_inverters", f"SELn{i}")
        c.wire(MET1, ix, iy, drop_x, iy, w=ESCAPE_W)
        c.via(MET1, MET2, drop_x, iy)

        c.wire(MET2, drop_x, iy, drop_x, row_y, w=ESCAPE_W)
        c.via(MET1, MET2, drop_x, row_y)

        cx, cy, _ = global_pin("cdac_array", f"SELn{i}")
        c.wire(MET1, drop_x, row_y, cx, row_y, w=ESCAPE_W)
        c.riser(cx, row_y, MET1, MET3)
        c.wire(MET3, cx, row_y, cx, CDAC_CROSS_Y, w=WIRE_W)
        c.riser(cx, CDAC_CROSS_Y, MET3, LI1)

    # ------------------------------------------------------------------ #
    # 6. Remaining top-level external pins with no other-block member:
    #    VINP, VINN, VCM (sampling_frontend).
    # ------------------------------------------------------------------ #
    for net in ("VINP", "VINN", "VCM"):
        x, y, _ = global_pin("sampling_frontend", net)
        ext_x = x - 10.0
        c.path(MET2, [(x, y), (ext_x, y)])
        c.label(MET2_PIN, ext_x, y, net)

    draw_params = {
        "shapes": [
            {"layer": list(layer), "rect_um": [x0, y0, x1, y1]}
            for layer, (x0, y0, x1, y1) in c.shapes
        ],
        "labels": [
            {"layer": list(layer), "text": text, "at_um": [x, y]}
            for layer, text, x, y in c.labels
        ],
    }

    blocks = []
    for block in OFFSETS:
        x0, y0, _x1, _y1 = BBOX[block]
        dx, dy = OFFSETS[block]
        blocks.append(
            {
                "id": block,
                "cell": {
                    "gds_path": f"{block}.gds",
                    "cell_name": CELL_NAME[block],
                },
            }
        )
    blocks.append({"id": "route", "generator_report": "draw.json"})

    origins = {block: {"x": OFFSETS[block][0], "y": OFFSETS[block][1]} for block in OFFSETS}
    origins["route"] = {"x": 0.0, "y": 0.0}

    compose_request = {
        "schema": "klt.gen_compose.request/1",
        "pdk": {"variant": "sky130A"},
        "blocks": blocks,
        "placement": {
            "strategy": "explicit",
            "order": list(OFFSETS) + ["route"],
            "origins_um": origins,
        },
        "connectivity": [],
    }

    return draw_params, compose_request


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_dir", type=Path)
    args = parser.parse_args()

    draw_params, compose_request = build()
    (args.out_dir / "draw.request.json").write_text(json.dumps(draw_params, indent=2) + "\n")
    (args.out_dir / "compose.request.json").write_text(
        json.dumps(compose_request, indent=2) + "\n"
    )
    print(
        f"build_layout.py: {len(draw_params['shapes'])} shapes, "
        f"{len(draw_params['labels'])} labels, {len(compose_request['blocks'])} blocks"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

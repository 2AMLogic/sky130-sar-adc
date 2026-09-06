#!/usr/bin/env python3
"""Floorplan, well-partition and route the full sampling front end (issue
#99): the nine-PFET three-domain n-well recipe issue #122 proved
(`layout/sampling-frontend-wells/`), plus the block's eleven NFETs and four
MiM capacitors, plus every wire between them.

Emits the two documents `layout/sampling-frontend/bin/run-flow.sh` feeds to
`klt`, exactly the split `layout/comparator/bin/build_layout.py` and
`layout/sampling-frontend-wells/bin/build_layout.py` both use and both
document the reasoning for (`klt gen-compose`'s own routing is advisory, not a
DRC-clean guarantee -- `klt draw` is this repo's routing authority):

* ``draw.request.json`` -- every shape this module owns: the three n-well
  islands and their taps (unchanged from issue #122), one p-substrate tap for
  the NFETs, and every wire (met1 columns, met2 tracks, mcon/via1/via2/via3
  cuts), in the composed coordinate system.
* ``compose.request.json`` -- a `klt gen-compose` placement request for every
  device block plus this routing cell, at explicit origins, with **no**
  ``routing`` block (`klt gen-compose` used purely as a placer).

Floorplan: three rows, side by side, no vertical stacking
----------------------------------------------------------
Three device rows sit left to right along the SAME y=0 baseline, in mutually
exclusive x ranges separated by wide channels:

  ROW 1 (PFETs)  |  channel  |  ROW 2 (NFETs)  |  channel  |  ROW 3 (caps)

This is deliberate, not incidental: every net's single met2 track (see
"Routing style" below) sits in one shared band **above every row** (at
``TRACK_Y0``, chosen above the tallest block -- the 46.9um `Csamp` capacitor
row dominates). Because no two rows share an x range, a pin's vertical riser
from its own row up to that shared band never has to cross through another
row's own devices or wells -- the collision hazard a two-dimensional
(stacked-row) floorplan would create. The cost is wasted area (long risers
from the tiny transistor rows up past the huge capacitor row's own height);
this floorplan, like its two siblings, is not an area or parasitic
optimisation (see "Layout choices that are not claims" in
`../sampling-frontend-wells/README.md`, which applies here too).

Row 1 (PFETs) is `layout/sampling-frontend-wells/`'s own three-n-well-island
recipe, unchanged: `boost_p` = {Sa_p, Se_p}, `vdd` = {Scp_p, Cmswp_p, Invp,
Cmswp_n, Scp_n}, `boost_n` = {Se_n, Sa_n} -- see that module's docstring
("THE RECIPE") for why all four parts of it are required. This module adds a
fourth tap: a p-substrate tie in Row 2's own margin, routed to GND.

What that substrate tap does -- and does NOT do -- stated precisely, because
it is easy to overclaim: `klt extract --deck sky130` synthesizes **one
global** NMOS body net (`vsubs`) via `connect_global`, regardless of drawn
geometry, so the tap does not turn any NFET's body terminal into a
schematic-named net. `klt lvs` still reports `device.body_unverified` for
all eleven NFETs, and that warning is an expected property of this deck, not
a defect this flow could route its way out of. What the tap *does* do is
merge this layout's drawn `GND` conductor into that same `vsubs` net, so
every NFET source the schematic ties to GND lands on the one net its own
body already sits on. Without it, `GND` would extract as an ordinary signal
net distinct from `vsubs` and LVS would not match at all. Same idiom, and
the same limit, as `layout/comparator/bin/build_layout.py`'s own NFET
substrate tie.

Routing style: one met2 track per net, met1 the rest of the way
-----------------------------------------------------------------
Every net gets exactly one met2 track, in one shared band above all three
rows (``TRACK_Y0 + k * TRACK_PITCH_UM``) -- the same "one track, no channel
contention" scheme `layout/sampling-frontend-wells/bin/build_layout.py` uses,
extended from one row to three.

Every pin, **regardless of which layer `klt gen` reports its port on**, is
walked down to met1 before it is routed, and only returns to met2 at the one
via1 cut that lands it on its own net's track:

* a `mos_array`/`diff_pair` S/G/D port is already on li1 -- one `mcon` reaches
  met1 directly (unchanged from the wells recipe).
* a `cap_array` bottom-plate port (`*_BOT`) is on met3 -- one `via2` steps it
  down to met2, then one `via1` steps that down again to met1.
* a `cap_array` top-plate port (`*_TOP`) is on met4 -- `via3` to met3, `via2`
  to met2, `via1` to met1: three vias stacked at the port's own (x, y),
  landing on top of (and electrically merging with, once flattened) whatever
  local met3/via3 structure `cap_array` already drew under its own top-plate
  pad, exactly the same way two independently-drawn same-layer shapes at the
  same coordinates merge anywhere else in this flow.

**Why met1 the whole way, not met2 the whole way for cap pins**: a net's met2
track is one long horizontal rectangle spanning every column x that net
touches, drawn at that net's own track y. If a *different* net's riser also
rode on met2 below its own track (which every cap-originated pin would, absent
this rule, since it starts on met2 already), it would have to physically
cross every lower-numbered net's met2 track at whatever x it shares with
them -- an unconditional short between two unrelated nets, on the very layer
that carries the whole track scheme. Met1 has no such hazard: it carries
nothing but per-pin columns, so any column may freely underpass any net's
met2 track (different layer, only diverging at each pin's own via1). Stepping
every pin down to met1 immediately, before any jogging or rising, makes this
true unconditionally rather than by track-ordering luck.

Layer plane split (as in both sibling modules): every `klt gen` block draws
only nwell/diff/poly/licon1/li1 plus, for the two capacitor blocks,
capm/met3/via3/met4 confined to each unit cap's own small footprint -- met1
and met2 are unused by every block, so this module owns both outright.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "bin"))

from _geometry_common import Rect as _Rect  # noqa: E402
from gen_blocks import (  # noqa: E402
    CAP_DEVICES,
    DOMAIN_TAP_NET,
    NFET_DEVICES,
    PFET_DEVICES,
)

# --- layer table (sky130A GDS numbers, as klt's own curated deck names them) --
L_NWELL = (64, 20)
L_TAP = (65, 44)
L_LICON = (66, 44)
L_LI1 = (67, 20)
L_MCON = (67, 44)
L_MET1 = (68, 20)
L_VIA1 = (68, 44)
L_MET2 = (69, 20)
L_MET2_PIN = (69, 5)
L_VIA2 = (69, 44)
L_MET3 = (70, 20)
L_VIA3 = (70, 44)
L_MET4 = (71, 20)

# --- rule-derived geometry (sky130 deck thresholds + margin) -----------------
WIRE_UM = 0.30  # met1/met2 wire + landing-pad width (m1.1/m2.1 minimum 0.14)
MET_SPACE_UM = 0.14  # m1.2 / m2.2
MCON_UM = 0.17
VIA1_UM = 0.15  # via1 square side (via1.width min 0.15) -- matches the wells
# recipe's own sizing, proven DRC-clean against met1/met2.enclosing.via.1's
# 0.055um threshold with a 0.30um landing pad.
VIA23_UM = 0.20  # via2/via3 square side (via2/via3.width min 0.20 -- a
# DIFFERENT, larger minimum than via1's 0.15; found directly building this
# layout, via2.width.1 violations at 0.15).
STACK_PAD_UM = 0.42  # landing pad for a stacked via cut (matches the
# gate_contact pad size `klt gen` itself uses elsewhere in this repo, so a
# 0.20um via2/via3 lands with >= 0.11um enclosure on every side -- comfortably
# above met2/met3/met4's 0.04-0.065um enclosure-of-via thresholds).
MET3_VIA_INSET_UM = 0.20  # a `cap_array` *_BOT port's reported x sits right at
# the bottom plate's own edge (direction 180, x = the plate's left edge) --
# landing a via2 exactly there would poke past met3's own boundary and fail
# met3.enclosing.via2. Step the via2 landing this far INTO the plate instead
# (>= met3.enclosing.via2's ~0.065um threshold, with margin); the pin's
# effective (x, y) for jogging purposes moves with it.
LICON_UM = 0.17
LICON_PITCH_UM = 0.60

#: Drawn n-well island separation -- unchanged from issue #122's own recipe.
#: sky130's own `nwell.2a` ("min. nwell spacing (merged if less)") is 1.27um.
WELL_GAP_UM = 1.60
WELL_MARGIN_UM = 0.30
WELL_TAP_MARGIN_UM = 2.00
WELL_BELOW_UM = 2.40
WELL_ABOVE_UM = 0.40

#: n-well tap strip geometry (Row 1), in each domain's left margin.
TAP_X0_UM = 0.40
TAP_X1_UM = 1.00
TAP_Y0_UM = -1.80
TAP_Y1_UM = -0.60

#: Row 1 (PFET) device pitch -- unchanged from the wells recipe.
BLOCK_PITCH_UM = 3.20
CHANNEL_LEFT_UM = 0.45
CHANNEL_RIGHT_UM = 0.45

#: Row-to-row channel width.
ROW_GAP_UM = 6.00

#: Row 2 (NFET) layout: left-to-right, one block-width + margin per device,
#: reserving the leftmost slot for the p-substrate tap.
ROW2_TAP_WIDTH_UM = 2.00
ROW2_BLOCK_MARGIN_UM = 1.20

#: Row 3 (capacitor) layout: left-to-right, one block-width + margin.
ROW3_BLOCK_MARGIN_UM = 3.00

#: How far above a `cap_array` unit's own bbox top its *_TOP port's met4
#: riser must clear before stepping down to met3/met2/met1 -- see
#: `_step_down_to_met1`'s `L_MET4` case for why landing that step INSIDE the
#: cell's own footprint shorts the two plates together. Must clear
#: met3.space (0.30um) from the bottom plate's own top edge to the new met3
#: landing pad's near edge (STACK_PAD_UM/2 further out); 0.50 measured
#: exactly 0.29um clear on the first build (a met3.space.1 violation) --
#: 0.80 gives comfortable margin instead of chasing the threshold exactly.
CAP_MET4_ESCAPE_MARGIN_UM = 0.80

#: Shared met2 track band, one track per net, above every row (the tallest
#: block is the 46.9um `Csamp` capacitor pair -- see `floorplan()`, which
#: computes `TRACK_Y0` from the actual composed geometry rather than a
#: hand-picked constant, so a future device-size change cannot silently put a
#: capacitor above a stale track band).
TRACK_PITCH_UM = 0.50
TRACK_MARGIN_ABOVE_TALLEST_UM = 2.00

#: All seventeen nets this sub-block carries, in the order their tracks are
#: assigned (bottom-up). Supplies/clocks first (closest to the devices, since
#: they fan out the widest), then per-side signals.
TRACK_ORDER = (
    "SAMPLEB",
    "SAMPLE",
    "VDD",
    "GND",
    "VCM",
    "BOOST_P",
    "BOOST_N",
    "VINP",
    "VINN",
    "BSBOT_P",
    "BSBOT_N",
    "G_P",
    "G_N",
    "BPREF_P",
    "BPREF_N",
    "TOP_P",
    "TOP_N",
)

#: Nets promoted to top-level pins (labelled on met2.pin) -- exactly
#: `design/sampling_frontend.sym`'s drawn pin list. GND is deliberately absent
#: (`devices/gnd.sym` is `global=true` in the schematic, so it needs no pin at
#: this level of hierarchy either) even though it gets a track here like every
#: other net: `layout/sampling-frontend-wells/` labels GND-equivalent nets the
#: same way its own PIN_NETS omits nothing GND-like because that cell has no
#: NFETs; this cell's GND *does* need a track (the p-substrate tap and every
#: NFET source route through it) but not a promoted pin, since nothing at a
#: higher level of hierarchy will ever connect to it by name.
PIN_NETS = (
    "VDD",
    "SAMPLE",
    "VCM",
    "VINP",
    "VINN",
    "TOP_P",
    "TOP_N",
    "BPREF_P",
    "BPREF_N",
)

#: Internal nets that ALSO get a met2.pin label, even though they are not
#: `design/sampling_frontend.sym` ports (`klt lvs`'s `top_cell_pins` stays at
#: its default `false` -- see run-flow.sh -- so labelling an internal net does
#: not turn it into an LVS port requirement). `BOOST_P`/`BOOST_N` are the two
#: PFET body-tie domain nets from DR-007: `klt extract`'s
#: `unbiased_pmos_body_nets` check flags *any* PMOS body sitting on an
#: unlabelled (KLayout-anonymous) net, independent of whether that net is
#: correctly, structurally tied by real geometry -- found directly building
#: this layout (all four of `Sa_p`/`Se_p`/`Sa_n`/`Se_n` flagged unbiased on
#: their first extraction, despite each one's body correctly sharing a net
#: with its own drain/source per DR-007's recipe) once `BOOST_P`/`BOOST_N`
#: stopped being top-level ports the way they were in
#: `layout/sampling-frontend-wells/`'s narrower, PFET-only cell. Labelling
#: them here (this module only, not the schematic's own port list) is what
#: makes the verdict measure the same thing it measured there.
INTERNAL_BODY_TIE_LABELS = ("BOOST_P", "BOOST_N")


class Rect(_Rect):
    """An axis-aligned rectangle in integer nanometres.

    ``__slots__``, ``__init__``, ``um()``, ``centred()`` and ``as_um()`` are
    the shared shell inherited from `layout/bin/_geometry_common.py`;
    ``hwire()``/``vwire()`` below are this sub-block's own wiring extension
    (verbatim from `layout/sampling-frontend-wells/bin/build_layout.py`,
    whose own recipe this module builds on top of -- see this module's
    docstring).
    """

    __slots__ = ()

    @classmethod
    def hwire(cls, xa: float, xb: float, y: float, width: float = WIRE_UM) -> "Rect":
        lo, hi = (xa, xb) if xa <= xb else (xb, xa)
        return cls.um(lo - width / 2, y - width / 2, hi + width / 2, y + width / 2)

    @classmethod
    def vwire(cls, x: float, ya: float, yb: float, width: float = WIRE_UM) -> "Rect":
        lo, hi = (ya, yb) if ya <= yb else (yb, ya)
        return cls.um(x - width / 2, lo - width / 2, x + width / 2, hi + width / 2)


class BuildError(RuntimeError):
    """The floorplan violated one of this module's own build-time invariants."""


def load_block(report_path: Path) -> dict:
    """Read a `klt gen` report -> ``{"ports": {name: (x, y, width, dir, layer)},
    "bbox"}``."""
    report = json.loads(report_path.read_text())
    ports = {}
    for port in report["ports"]:
        layer = (port["layer"]["layer"], port["layer"]["datatype"])
        ports[port["name"]] = (
            port["x_um"],
            port["y_um"],
            port["width_um"],
            port["direction_deg"],
            layer,
        )
    return {"ports": ports, "bbox": report["bbox_um"]}


# --------------------------------------------------------------------------- #
# Row 1: PFETs, unchanged from layout/sampling-frontend-wells/
# --------------------------------------------------------------------------- #
def floorplan_row1(blocks: dict[str, dict]) -> tuple[dict, list[dict]]:
    origins: dict[str, dict[str, float]] = {}
    domains: list[dict] = []

    cursor = 0.0
    ordered_domains: list[str] = []
    for _bid, _name, domain, *_rest in PFET_DEVICES:
        if domain not in ordered_domains:
            ordered_domains.append(domain)

    for domain in ordered_domains:
        members = [row[0] for row in PFET_DEVICES if row[2] == domain]
        well_x0 = cursor
        x = well_x0 + WELL_TAP_MARGIN_UM
        for block_id in members:
            origins[block_id] = {"x": x, "y": 0.0}
            x += BLOCK_PITCH_UM
        last = members[-1]
        well_x1 = origins[last]["x"] + blocks[last]["bbox"]["x1"] + WELL_MARGIN_UM
        top = max(blocks[b]["bbox"]["y1"] for b in members)
        domains.append(
            {
                "id": domain,
                "net": DOMAIN_TAP_NET[domain],
                "members": members,
                "well": {
                    "x0": well_x0,
                    "y0": -WELL_BELOW_UM,
                    "x1": well_x1,
                    "y1": top + WELL_ABOVE_UM,
                },
                "tap": {
                    "x0": well_x0 + TAP_X0_UM,
                    "x1": well_x0 + TAP_X1_UM,
                    "y0": TAP_Y0_UM,
                    "y1": TAP_Y1_UM,
                },
            }
        )
        cursor = well_x1 + WELL_GAP_UM

    return origins, domains


def _assert_well_isolation(domains: list[dict]) -> None:
    for a, b in zip(domains, domains[1:]):
        gap = b["well"]["x0"] - a["well"]["x1"]
        if gap < WELL_GAP_UM - 1e-9:
            raise BuildError(
                f"n-well islands {a['id']!r} and {b['id']!r} are {gap:.3f} um "
                f"apart, below the drawn separation {WELL_GAP_UM} um"
            )


def tap_shapes(spec: dict) -> tuple[list[tuple[tuple[int, int], Rect]], float, float]:
    """One well/substrate tap structure: tap+li1 strip, licon1 column."""
    x0, x1, y0, y1 = spec["x0"], spec["x1"], spec["y0"], spec["y1"]
    shapes: list[tuple[tuple[int, int], Rect]] = [
        (L_TAP, Rect.um(x0, y0, x1, y1)),
        (L_LI1, Rect.um(x0, y0, x1, y1)),
    ]
    cx = (x0 + x1) / 2
    y = y0 + LICON_PITCH_UM / 2
    while y + LICON_PITCH_UM / 2 <= y1 + 1e-9:
        shapes.append((L_LICON, Rect.centred(cx, y, LICON_UM, LICON_UM)))
        y += LICON_PITCH_UM
    return shapes, cx, (y0 + y1) / 2


# --------------------------------------------------------------------------- #
# Row 2: NFETs (unmatched singles + the Msw diff_pair) + one substrate tap
# --------------------------------------------------------------------------- #
def floorplan_row2(x_start: float, blocks: dict[str, dict]) -> tuple[dict, dict, float]:
    """Returns (origins, substrate_tap_spec, row2_x1)."""
    origins: dict[str, dict[str, float]] = {}
    x = x_start + ROW2_TAP_WIDTH_UM + ROW2_BLOCK_MARGIN_UM

    tap_spec = {
        "x0": x_start + 0.40,
        "x1": x_start + 1.00,
        "y0": -1.80,
        "y1": -0.60,
    }

    block_ids = [row[0] for row in NFET_DEVICES]
    for block_id in block_ids:
        origins[block_id] = {"x": x, "y": 0.0}
        width = blocks[block_id]["bbox"]["x1"] - blocks[block_id]["bbox"]["x0"]
        x += width + ROW2_BLOCK_MARGIN_UM

    return origins, tap_spec, x


# --------------------------------------------------------------------------- #
# Row 3: the two capacitor pairs
# --------------------------------------------------------------------------- #
def floorplan_row3(x_start: float, blocks: dict[str, dict]) -> dict:
    origins: dict[str, dict[str, float]] = {}
    x = x_start
    for block_id, _plate_um, _legs in CAP_DEVICES:
        origins[block_id] = {"x": x, "y": 0.0}
        width = blocks[block_id]["bbox"]["x1"] - blocks[block_id]["bbox"]["x0"]
        x += width + ROW3_BLOCK_MARGIN_UM
    return origins


# --------------------------------------------------------------------------- #
# Generic per-pin "walk down to met1" + column/track routing
# --------------------------------------------------------------------------- #
def _step_down_to_met1(
    shapes: list[tuple[tuple[int, int], Rect]],
    x: float,
    y: float,
    layer: tuple[int, int],
    direction: float,
    met4_escape_y: float | None = None,
) -> tuple[float, float]:
    """Emit whatever via stack is needed to reach met1 from ``layer``, and
    return the **effective** (x, y) the caller should treat as this pin's
    location from here on (usually the input point unchanged; see the
    ``L_MET3`` and ``L_MET4`` cases). See this module's docstring, "Routing
    style", for why every pin -- not just li1 ports -- ends up on met1."""
    if layer == L_LI1:
        shapes.append((L_MCON, Rect.centred(x, y, MCON_UM, MCON_UM)))
        return x, y
    if layer == L_MET3:
        # A `cap_array` *_BOT port reports its position AT the bottom plate's
        # own edge (direction 180 => the plate's left edge is x=0 in the
        # block's local frame) -- landing a via2 exactly there would poke past
        # met3's own boundary. Shift the via into the plate (direction 180
        # faces -x, so "into the plate" is +x) by MET3_VIA_INSET_UM; the
        # thin met3 strip between the reported edge and the via is already
        # part of the same bottom-plate conductor, so no extra wire is needed
        # to bridge it.
        if direction == 180.0:
            x = x + MET3_VIA_INSET_UM
        shapes.append((L_MET2, Rect.centred(x, y, STACK_PAD_UM, STACK_PAD_UM)))
        shapes.append((L_VIA2, Rect.centred(x, y, VIA23_UM, VIA23_UM)))
        # The FINAL met1 pad, unlike the via2/via3 landing pads above, only
        # has to enclose via1 (0.15um) -- WIRE_UM (0.30) already clears that
        # with margin, and matching it to the jog wire's own width below
        # avoids a corner notch a wider STACK_PAD_UM pad would leave between
        # itself and the (narrower) hwire/riser, which read back as a
        # met1.space.1 violation when first built this way.
        shapes.append((L_MET1, Rect.centred(x, y, WIRE_UM, WIRE_UM)))
        shapes.append((L_VIA1, Rect.centred(x, y, VIA1_UM, VIA1_UM)))
        return x, y
    if layer == L_MET4:
        # A `cap_array` *_TOP port's own via3 + local met3 landing sit
        # DIRECTLY ABOVE the bottom plate's own met3 sheet, which -- being a
        # PLATE -- covers this unit's ENTIRE footprint (its reported *_BOT
        # port width_um spans the whole cell height). Found directly building
        # this layout: adding a second via3/met3 pad at the port's own (x, y)
        # -- reasoning that it would merely "duplicate" the generator's own
        # already-isolated stub -- instead lands squarely inside the bottom
        # plate's own sheet and SHORTS the two plates together (`klt extract`
        # reported the top- and bottom-plate nets merged into one, with the
        # real, now-orphaned top-plate net anonymous). There is no offset
        # inside the cell's footprint where a new met3 shape is safe, because
        # the bottom plate occupies the whole footprint.
        #
        # Fix: ride MET4 (which the bottom plate never touches) straight up
        # and OUT of the cell's footprint first -- `met4_escape_y`, past the
        # unit's own bbox top, supplied by the caller -- and only step down
        # to met3/met2/met1 once clear of it.
        if met4_escape_y is None:
            raise BuildError("L_MET4 port requires met4_escape_y")
        shapes.append((L_MET4, Rect.vwire(x, y, met4_escape_y)))
        # An explicit landing pad at the escape point: the vertical wire
        # alone only encloses via3 in x, not y (it ends exactly AT
        # met4_escape_y, so via3's own half-width above that point would
        # otherwise poke past the wire's own end -- a met4.enclosing.via3.1
        # violation found directly building this layout).
        shapes.append((L_MET4, Rect.centred(x, met4_escape_y, STACK_PAD_UM, STACK_PAD_UM)))
        y = met4_escape_y
        shapes.append((L_MET3, Rect.centred(x, y, STACK_PAD_UM, STACK_PAD_UM)))
        shapes.append((L_VIA3, Rect.centred(x, y, VIA23_UM, VIA23_UM)))
        shapes.append((L_MET2, Rect.centred(x, y, STACK_PAD_UM, STACK_PAD_UM)))
        shapes.append((L_VIA2, Rect.centred(x, y, VIA23_UM, VIA23_UM)))
        shapes.append((L_MET1, Rect.centred(x, y, WIRE_UM, WIRE_UM)))
        shapes.append((L_VIA1, Rect.centred(x, y, VIA1_UM, VIA1_UM)))
        return x, y
    raise BuildError(f"no met1 step-down rule for layer {layer!r}")


def _assert_column_pitch(columns: dict[float, str]) -> None:
    minimum = WIRE_UM + MET_SPACE_UM
    xs = sorted(columns)
    for xa, xb in zip(xs, xs[1:]):
        if xb - xa < minimum - 1e-9:
            raise BuildError(
                f"met1 columns for nets {columns[xa]!r} (x={xa:.3f}) and "
                f"{columns[xb]!r} (x={xb:.3f}) are {xb - xa:.3f} um apart, "
                f"below the {minimum:.2f} um wire+space pitch"
            )


def build(reports_dir: Path) -> tuple[dict, dict, dict]:
    """Return the (draw params, gen-compose request, layout summary) triple."""
    all_block_ids = (
        [row[0] for row in PFET_DEVICES]
        + [row[0] for row in NFET_DEVICES]
        + [row[0] for row in CAP_DEVICES]
    )
    blocks = {bid: load_block(reports_dir / f"{bid}.json") for bid in all_block_ids}

    origins1, domains = floorplan_row1(blocks)
    _assert_well_isolation(domains)
    row1_x1 = domains[-1]["well"]["x1"]

    row2_x0 = row1_x1 + ROW_GAP_UM
    origins2, substrate_tap_spec, row2_x1 = floorplan_row2(row2_x0, blocks)

    row3_x0 = row2_x1 + ROW_GAP_UM
    origins3 = floorplan_row3(row3_x0, blocks)

    origins = {**origins1, **origins2, **origins3}

    shapes: list[tuple[tuple[int, int], Rect]] = []
    labels: list[tuple[tuple[int, int], str, float, float]] = []
    columns: dict[float, str] = {}
    net_columns: dict[str, list[tuple[float, float]]] = {}

    def add_column(net: str, x: float, y_from: float) -> None:
        if x in columns and columns[x] != net:
            raise BuildError(f"column x={x:.3f} claimed by both {columns[x]!r} and {net!r}")
        columns[x] = net
        net_columns.setdefault(net, []).append((x, y_from))

    # --- Row 1: the three n-well islands and their taps ---------------------
    for domain in domains:
        well = domain["well"]
        shapes.append((L_NWELL, Rect.um(well["x0"], well["y0"], well["x1"], well["y1"])))
        tap_geometry, tap_x, tap_y = tap_shapes(domain["tap"])
        shapes.extend(tap_geometry)
        shapes.append((L_MCON, Rect.centred(tap_x, tap_y, MCON_UM, MCON_UM)))
        shapes.append((L_MET1, Rect.centred(tap_x, tap_y, WIRE_UM, WIRE_UM)))
        add_column(domain["net"], tap_x, tap_y)

    # --- Row 2: the p-substrate tap, tied to GND -----------------------------
    tap_geometry, tap_x, tap_y = tap_shapes(substrate_tap_spec)
    shapes.extend(tap_geometry)
    shapes.append((L_MCON, Rect.centred(tap_x, tap_y, MCON_UM, MCON_UM)))
    shapes.append((L_MET1, Rect.centred(tap_x, tap_y, WIRE_UM, WIRE_UM)))
    add_column("GND", tap_x, tap_y)

    # --- Per-pin columns: PFETs (Row 1), unchanged from the wells recipe ----
    for block_id, _name, _domain, _w, _l, d_net, g_net, s_net in PFET_DEVICES:
        _route_mos_pins(shapes, add_column, blocks[block_id], origins[block_id], "U0", d_net, g_net, s_net)

    # --- Per-pin columns: NFETs (Row 2) --------------------------------------
    for block_id, _name, _w, _l, d_net, g_net, s_net in NFET_DEVICES:
        _route_mos_pins(shapes, add_column, blocks[block_id], origins[block_id], "U0", d_net, g_net, s_net)

    # --- Per-pin columns: capacitors (Row 3) ---------------------------------
    for block_id, _plate_um, legs in CAP_DEVICES:
        for unit_index, _name, top_net, bot_net in legs:
            _route_cap_pins(shapes, add_column, blocks[block_id], origins[block_id], unit_index, top_net, bot_net)

    _assert_column_pitch(columns)

    missing = set(net_columns) - set(TRACK_ORDER)
    if missing:
        raise BuildError(f"nets with no assigned met2 track: {sorted(missing)}")
    unused = set(TRACK_ORDER) - set(net_columns)
    if unused:
        raise BuildError(f"tracks assigned to nets with no columns: {sorted(unused)}")

    # --- Shared met2 track band, above every row -----------------------------
    tallest_top = max(blocks[b]["bbox"]["y1"] for b in all_block_ids)
    track_y0 = tallest_top + TRACK_MARGIN_ABOVE_TALLEST_UM

    summary_nets: dict[str, dict] = {}
    for index, net in enumerate(TRACK_ORDER):
        track_y = track_y0 + index * TRACK_PITCH_UM
        cols = sorted(net_columns[net])
        for x, y_from in cols:
            shapes.append((L_MET1, Rect.vwire(x, y_from, track_y)))
            shapes.append((L_MET1, Rect.centred(x, track_y, WIRE_UM, WIRE_UM)))
            shapes.append((L_VIA1, Rect.centred(x, track_y, VIA1_UM, VIA1_UM)))
        xs = [x for x, _ in cols]
        shapes.append((L_MET2, Rect.hwire(min(xs), max(xs), track_y)))
        if net in PIN_NETS or net in INTERNAL_BODY_TIE_LABELS:
            labels.append((L_MET2_PIN, net, xs[0], track_y))
        summary_nets[net] = {
            "track_y_um": round(track_y, 3),
            "columns_um": [round(x, 3) for x in xs],
            "pin_count": len(xs),
        }

    draw_params = {
        "shapes": [{"layer": list(layer), "rect_um": rect.as_um()} for layer, rect in shapes],
        "labels": [
            {"layer": list(layer), "text": text, "at_um": [x, y]} for layer, text, x, y in labels
        ],
    }

    order = list(origins) + ["route"]
    compose_request = {
        "schema": "klt.gen_compose.request/1",
        "pdk": {"variant": "sky130A"},
        "blocks": [{"id": bid, "generator_report": f"{bid}.json"} for bid in origins]
        + [{"id": "route", "generator_report": "draw.json"}],
        "placement": {
            "strategy": "explicit",
            "order": order,
            "origins_um": {**origins, "route": {"x": 0.0, "y": 0.0}},
        },
        "connectivity": [],
    }

    layout_summary = {
        "row1_x_range_um": [0.0, row1_x1],
        "row2_x_range_um": [row2_x0, row2_x1],
        "row3_x_range_um": [row3_x0, max(o["x"] for o in origins3.values())],
        "track_y0_um": track_y0,
        "well_gap_drawn_um": WELL_GAP_UM,
        "nwell_2a_rule_um": 1.27,
        "domains": [
            {
                "id": domain["id"],
                "tap_net": domain["net"],
                "members": domain["members"],
                "schematic_devices": [
                    row[1] for row in PFET_DEVICES if row[2] == domain["id"]
                ],
                "well_um": {k: round(v, 3) for k, v in domain["well"].items()},
                "tap_um": {k: round(v, 3) for k, v in domain["tap"].items()},
            }
            for domain in domains
        ],
        "island_gaps_um": [
            round(b["well"]["x0"] - a["well"]["x1"], 3) for a, b in zip(domains, domains[1:])
        ],
        "substrate_tap_um": {k: round(v, 3) for k, v in substrate_tap_spec.items()},
        "block_origins_um": origins,
        "nets": summary_nets,
    }
    return draw_params, compose_request, layout_summary


def _route_mos_pins(shapes, add_column, block, origin, prefix, d_net, g_net, s_net) -> None:
    """Route one device's D/G/S pins: mcon to met1, jog by direction, add a
    column for the shared per-net met2 track pass to pick up later."""
    ox, oy = origin["x"], origin["y"]
    for suffix, net in ((f"{prefix}_D", d_net), (f"{prefix}_G", g_net), (f"{prefix}_S", s_net)):
        x, y, _width, direction, layer = block["ports"][suffix]
        px, py = ox + x, oy + y
        px, py = _step_down_to_met1(shapes, px, py, layer, direction)
        if direction == 180.0:  # faces -x: jog left
            col_x = px - CHANNEL_LEFT_UM
        elif direction == 0.0:  # faces +x: jog right
            col_x = px + CHANNEL_RIGHT_UM
        else:  # faces +y: straight up, no jog
            col_x = px
        if abs(col_x - px) > 1e-9:
            shapes.append((L_MET1, Rect.hwire(px, col_x, py)))
        add_column(net, col_x, py)


def _route_cap_pins(shapes, add_column, block, origin, unit_index, top_net, bot_net) -> None:
    ox, oy = origin["x"], origin["y"]
    # Above the whole cell's own bbox top (the bottom plate's own met3 sheet
    # spans that full height) -- see _step_down_to_met1's L_MET4 case.
    escape_y = oy + block["bbox"]["y1"] + CAP_MET4_ESCAPE_MARGIN_UM
    for suffix, net in ((f"C{unit_index}_TOP", top_net), (f"C{unit_index}_BOT", bot_net)):
        x, y, _width, direction, layer = block["ports"][suffix]
        px, py = ox + x, oy + y
        px, py = _step_down_to_met1(shapes, px, py, layer, direction, met4_escape_y=escape_y)
        if direction == 180.0:
            col_x = px - CHANNEL_LEFT_UM
        elif direction == 0.0:
            col_x = px + CHANNEL_RIGHT_UM
        else:
            col_x = px
        if abs(col_x - px) > 1e-9:
            shapes.append((L_MET1, Rect.hwire(px, col_x, py)))
        add_column(net, col_x, py)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports_dir", type=Path, help="directory holding every <block>.json report")
    args = parser.parse_args()

    draw_params, compose_request, layout_summary = build(args.reports_dir)
    (args.reports_dir / "draw.request.json").write_text(json.dumps(draw_params, indent=2) + "\n")
    (args.reports_dir / "compose.request.json").write_text(json.dumps(compose_request, indent=2) + "\n")
    (args.reports_dir / "layout.summary.json").write_text(json.dumps(layout_summary, indent=2) + "\n")
    print(
        f"build_layout.py: {len(draw_params['shapes'])} shapes, "
        f"{len(draw_params['labels'])} labels, {len(compose_request['blocks'])} blocks"
    )
    for domain in layout_summary["domains"]:
        well = domain["well_um"]
        print(
            f"build_layout.py: n-well island {domain['id']} -> tap net "
            f"{domain['tap_net']}: x {well['x0']}..{well['x1']} um"
        )
    print(f"build_layout.py: track band starts at y={layout_summary['track_y0_um']} um")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

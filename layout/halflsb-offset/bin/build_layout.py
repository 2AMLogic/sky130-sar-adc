#!/usr/bin/env python3
"""Floorplan, well-partition and route DR-009's half-LSB quantizer-offset
network (issue #495): the two `Choff_{n,p}` MiM caps, the six
`Moff_{n,p}_{cmn,refp,cmp}` switches, their body ties, and every wire between
them.

Emits the two documents `layout/halflsb-offset/bin/run-flow.sh` feeds to `klt`,
the same split every full-custom sibling in this repo uses and documents (`klt
gen-compose`'s own routing is advisory, not a DRC-clean guarantee -- `klt draw`
is this repo's routing authority):

* ``draw.request.json`` -- every shape this module owns: two n-well islands and
  their VDD taps, two p-substrate taps tied to GND, and every wire (met1
  columns, met2 tracks, mcon/via1/via2/via3 cuts), in the composed coordinate
  system.
* ``compose.request.json`` -- a `klt gen-compose` placement request for the
  seven generated blocks plus this routing cell, at explicit origins, with
  **no** ``routing`` block (`klt gen-compose` used purely as a placer).

Floorplan: two congruent side groups, one shared track band above them
----------------------------------------------------------------------
The block is laid out as ONE group, repeated:

    [ side n group ]   [ side p group = side n group + (SIDE_PITCH_UM, 0) ]

and within a group, left to right::

    cap unit | GND tap | cmn (nfet) | ---- n-well island: VDD tap, refp, cmp ----

The `cap unit` slot is not a block of its own: both offset caps come from a
single `klt gen cap_array num=2` call (see `gen_blocks.py`), whose own unit
pitch is set to `SIDE_PITCH_UM`, so unit 0 lands in side n's slot and unit 1 in
side p's. That is what makes **one** translation vector relate the whole `_p`
half of the network to the `_n` half.

Why that congruence is the point, and how it is enforced
-------------------------------------------------------
DR-009's `_p` half is a *matching dummy*: `Choff_p` and its three tied-off
switches inject nothing and exist only so both comparator inputs see the same
capacitance and the same switch junction parasitics. A dummy that is not
actually matched is worse than no dummy, because it adds an unbalanced load
while the schematic claims it removes one -- and neither `klt drc` nor `klt
lvs` can see the difference (LVS compares topology and device parameters, and
both sides' devices are identical in both; a floorplan that scattered the `_p`
devices arbitrarily would match perfectly).

So the matching is not asserted in prose here: `_assert_side_congruence()`
takes the two sides' shape lists, translates every `_n`-side shape by exactly
`(SIDE_PITCH_UM, 0)`, and raises unless the result is the `_p` side's shape
list as a multiset. Every drawn rectangle -- well, tap, licon column, mcon,
via stack, landing pad and jog -- is covered. Two things are deliberately
**outside** that assertion, both by necessity rather than by convenience:

1. **The two caps' own internal geometry**, which this module does not draw.
   It is the generator's, emitted twice from one `num=2` call, which is a
   stronger statement than a congruence check on shapes this module wrote.
2. **Everything at or above `TRACK_Y0`** -- the per-net met1 risers and the
   met2 tracks they land on. Each net owns exactly one track, and the two
   sides' corresponding nets are different nets (`HALF_LSB_EN` vs `VGND`,
   `BOT_OFF_N` vs `BOT_OFF_P`), so their tracks cannot be at the same y and
   their risers cannot be congruent. `TRACK_ORDER` therefore assigns the four
   matched net pairs to *adjacent* tracks, which bounds the residual asymmetry
   at one track pitch of 0.30 um-wide met1 per matched net rather than at an
   arbitrary amount; `layout.summary.json` records the resulting per-side met1
   area so the residual is a measured number in the record instead of a claim.

Routing style: one met2 track per net, met1 the rest of the way
--------------------------------------------------------------
Identical to `layout/sampling-frontend/bin/build_layout.py`'s scheme, and it
has to be, because this block composes the same two generator families (MiM
`cap_array` units with met3 bottom-plate / met4 top-plate ports, `mos_array`
singles with li1 S/G/D ports). Every pin is walked down to met1 before it is
routed and only returns to met2 at the one via1 cut that lands it on its own
net's track -- `layout/bin/_geometry_common.py`'s `step_down_to_met1()`, which
is that module's shared copy of the emitter, including the three
empirically-found DRC fixes in it (the met3 via inset, the met4 escape above
the bottom plate's own sheet, and the 0.50 um met3 island pad that clears
`m3.6`). See its docstring; nothing about the via stack is re-derived here.

Layer plane split (as in every sibling): the generated blocks draw only
nwell/diff/poly/licon1/li1 plus, for the capacitor pair, capm/met3/via3/met4
confined to each unit's own small footprint -- met1 and met2 are unused by
every block, so this module owns both outright.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "bin"))

from _geometry_common import (  # noqa: E402
    L_MET1,
    L_MET2,
    L_VIA1,
    STACK_PAD_UM,
    VIA1_UM,
    BuildError,
    MCON_UM,
    L_MCON,
    Rect,
    nm,
)
from _geometry_common import _assert_column_pitch as _assert_column_pitch_shared  # noqa: E402
from _geometry_common import _assert_well_isolation as _assert_well_isolation_shared  # noqa: E402
from _geometry_common import step_down_to_met1  # noqa: E402
from _geometry_common import tap_shapes as _tap_shapes_core  # noqa: E402
from gen_blocks import (  # noqa: E402
    CAP_BLOCK_ID,
    CAP_LEGS,
    SIDE_PITCH_UM,
    SIDES,
    SWITCH_DEVICES,
    SWITCH_ROLES,
    block_ids,
)

# --- layer table: only what this module draws that `_geometry_common` does not
# already name for the shared via-stack emitter.
L_NWELL = (64, 20)
L_MET2_PIN = (69, 5)

# --- rule-derived geometry (sky130 deck thresholds + margin) -----------------
WIRE_UM = 0.30  # met1/met2 wire + landing-pad width (m1.1/m2.1 minimum 0.14)
MET_SPACE_UM = 0.14  # m1.2 / m2.2
LICON_UM = 0.17

#: sky130's manufacturing grid, the one `klt precheck --grid-um` grades against
#: (`layout/sampling-frontend/bin/run-flow.sh` passes 0.005). Every coordinate
#: this module *chooses* is snapped to it. The one coordinate it does NOT
#: choose -- the MiM plate side, which DR-009 ties to the CDAC unit cap -- used
#: to be off-grid (1898 nm) and dragged 48 shapes off with it; DR-019/#498
#: resized it to a grid-legal 1.9000 um, so the composed layout is now entirely
#: on this grid. See `../README.md`, "The 5 nm manufacturing grid", and
#: `run-flow.sh`'s two precheck stages, both of which must now pass outright.
GRID_UM = 0.005

#: A met2 track for a net with exactly ONE column would otherwise be a
#: `WIRE_UM` square: 0.09 um^2, only 1.3x sky130A's `m2.6` minimum met2 area
#: (0.0676 um^2, now a live `met2.area.1` rule in the curated deck since
#: `klayout-tools==0.6.0`). Four of this block's twelve nets are single-column
#: (`TOP_N`, `TOP_P`, `HALF_LSB_ENN`, `VPWR`), so the case is not hypothetical;
#: a `STACK_PAD_UM` square is 0.1764 um^2, 2.6x the threshold, for no cost.
SINGLE_COLUMN_PAD_UM = STACK_PAD_UM

#: Drawn n-well island separation. sky130's own `nwell.2a` ("min. nwell
#: spacing (merged if less)") is 1.27 um; this is the value
#: `_assert_well_isolation` holds the two islands to, and `klt drc`'s own
#: `nwell.space.1` re-checks on the finished GDS.
WELL_GAP_UM = 1.60
WELL_MARGIN_UM = 0.30
WELL_TAP_MARGIN_UM = 2.00
WELL_BELOW_UM = 2.40
WELL_ABOVE_UM = 0.40

#: Tap strip geometry (both the n-well taps and the p-substrate taps), as an
#: offset from the strip's own left edge.
TAP_WIDTH_UM = 0.60
TAP_Y0_UM = -1.80
TAP_Y1_UM = -0.60

#: Within-group floorplan, all local to the group's own origin x.
GROUP_CAP_X_UM = 0.00  #: cap unit's own left (met3 bottom-plate) edge
GROUP_SUB_TAP_X_UM = 3.40  #: p-substrate tap strip left edge, GND
GROUP_NFET_X_UM = 5.20  #: the `cmn` NFET block origin
NFET_TO_WELL_UM = 1.60  #: NFET diffusion right edge -> n-well island left edge
PFET_PITCH_UM = 3.20  #: refp -> cmp block origin pitch inside the island

#: Clearance from one group's n-well island right edge to the NEXT group's
#: p-substrate tap. Not a transcribed rule (sky130 scopes tap/implant rules by
#: the nsdm/psdm markers no `klt gen` generator draws, so `klt drc`'s curated
#: deck does not check it -- see `../sampling-frontend/README.md`, "What this
#: flow does not check"); a deliberately generous channel instead, since the
#: whole span is empty anyway.
GROUP_CHANNEL_UM = 2.00

#: Per-pin jog, by the direction `klt gen` reports the port facing.
CHANNEL_LEFT_UM = 0.45
CHANNEL_RIGHT_UM = 0.45

#: y origin of the capacitor row, above the switch row's own tallest geometry
#: (the n-well island top at ~3.4 um). The caps are 3.818 um tall and carry the
#: only met3/met4 in the layout, so putting them in their own row keeps the
#: switch groups' li1/nwell plane and the caps' capm/met3/met4 plane from
#: sharing any x range at all.
CAP_ROW_Y_UM = 5.00

#: How far above the cap block's own bbox top a `*_TOP` met4 riser must climb
#: before stepping down -- `step_down_to_met1`'s `L_MET4` case, whose docstring
#: explains why landing that step inside the unit's footprint shorts the two
#: plates together. 0.80 um is the value `layout/sampling-frontend/` measured
#: DRC-clean (0.50 left exactly 0.29 um of met3 clearance, one met3.space.1
#: violation short).
CAP_MET4_ESCAPE_MARGIN_UM = 0.80

#: Shared met2 track band. `TRACK_Y0` is computed from the actual composed
#: geometry (see `build()`), not hand-picked, so a device- or row-height change
#: cannot silently put a capacitor or a met4 escape pad inside the band.
TRACK_PITCH_UM = 0.50
TRACK_MARGIN_ABOVE_UM = 1.50

#: All twelve nets this sub-block carries, in track-assignment order
#: (bottom-up, closest to the devices first).
#:
#: The order is load-bearing, not cosmetic. The four nets shared by both sides
#: (`VDD`, `GND`, `VREFP`, `VCM`) come first, since they fan out widest. Then
#: the four side-specific pairs are assigned to ADJACENT tracks --
#: (`HALF_LSB_EN`, `VGND`), (`HALF_LSB_ENN`, `VPWR`), (`BOT_OFF_N`,
#: `BOT_OFF_P`), (`TOP_N`, `TOP_P`) -- each pair being one net on the working
#: side and its dummy-side counterpart. That is the only lever this routing
#: scheme has on the one asymmetry `_assert_side_congruence` cannot remove
#: (see this module's docstring, item 2): with the pair adjacent, the matched
#: nets' met1 risers differ by exactly one `TRACK_PITCH_UM`, and
#: `layout.summary.json` records the resulting per-side met1 area.
TRACK_ORDER = (
    "VDD",
    "GND",
    "VREFP",
    "VCM",
    "HALF_LSB_EN",
    "VGND",
    "HALF_LSB_ENN",
    "VPWR",
    "BOT_OFF_N",
    "BOT_OFF_P",
    "TOP_N",
    "TOP_P",
)

#: The matched net pairs `TRACK_ORDER` above must keep adjacent, as
#: `(working-side net, dummy-side net)`. Asserted, not just commented: a future
#: edit that reorders `TRACK_ORDER` and separates a pair has doubled that
#: pair's residual met1 asymmetry, and should have to say so.
MATCHED_NET_PAIRS = (
    ("HALF_LSB_EN", "VGND"),
    ("HALF_LSB_ENN", "VPWR"),
    ("BOT_OFF_N", "BOT_OFF_P"),
    ("TOP_N", "TOP_P"),
)

#: Nets promoted to a drawn `met2.pin` label. All twelve, including the two
#: internal bottom plates.
#:
#: Ten of them are real ports of this network at the top level (`design/
#: sar_adc_top.spice`'s own net names). `BOT_OFF_N`/`BOT_OFF_P` are internal --
#: no higher level of hierarchy connects to them -- and are labelled anyway,
#: the same choice and for the same reason `layout/sampling-frontend/bin/
#: build_layout.py` labels `BOOST_P`/`BOOST_N`: an unlabelled net extracts as
#: KLayout's anonymous `\$n`, which turns the record's net-correspondence table
#: into a lookup exercise and leaves `layout/sar-adc-top/`'s eventual
#: composition (#401) with no named conductor to probe. `klt lvs`'s
#: `top_cell_pins` stays at its default `false` (see `run-flow.sh`), so
#: labelling a net does not turn it into an LVS port requirement.
PIN_NETS = TRACK_ORDER


def snap_up(value_um: float, grid_um: float = GRID_UM) -> float:
    """``value_um`` rounded UP to the next ``grid_um`` multiple, in integer
    nanometres (so the result is exactly representable in the database unit).

    Up rather than to-nearest: every caller below is a clearance (a met4 escape
    height, the track band's own floor), where rounding down would eat the
    margin the constant was chosen to provide.
    """
    grid_nm = nm(grid_um)
    return -(-nm(value_um) // grid_nm) * grid_nm / 1000.0


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


def tap_shapes(spec: dict) -> tuple[list[tuple[tuple[int, int], Rect]], float, float]:
    """One well/substrate tap structure: tap+li1 strip, licon1 column, plus the
    strip centre the caller lands its mcon/met1 pad on."""
    shapes = _tap_shapes_core(spec, LICON_UM)
    cx = (spec["x0"] + spec["x1"]) / 2
    return shapes, cx, (spec["y0"] + spec["y1"]) / 2


def floorplan(blocks: dict[str, dict]) -> dict:
    """Derive every origin, well and tap rectangle from the generated blocks'
    own bounding boxes.

    Returns a dict with, per side: the three switch block origins, the n-well
    island rectangle, the island's VDD tap, and the p-substrate GND tap -- plus
    the cap block's own origin and the group extent every side shares.
    """
    # One slot x per ROLE, shared by both sides -- which is the first half of
    # the congruence property: two sides cannot disagree about a slot they read
    # out of the same table. `SWITCH_ROLES`' own order is the slot order, and
    # the NFET-first / PFETs-adjacent grouping it fixes is what lets one n-well
    # island per side hold both PFET bodies without enclosing the NFET.
    reference_side = SIDES[0]
    block_of_role = {
        role: next(
            row[0]
            for row in SWITCH_DEVICES
            if row[2] == reference_side and row[1].endswith(f"_{role}")
        )
        for role, _flavor, _w, _l in SWITCH_ROLES
    }
    nfet_roles = [role for role, flavor, _w, _l in SWITCH_ROLES if flavor == "nfet"]
    pfet_roles = [role for role, flavor, _w, _l in SWITCH_ROLES if flavor == "pfet"]
    if len(nfet_roles) != 1 or [role for role, _f, _w, _l in SWITCH_ROLES] != (
        nfet_roles + pfet_roles
    ):
        raise BuildError(
            "this floorplan draws one NFET slot followed by a contiguous run of "
            f"PFET slots inside one n-well island; SWITCH_ROLES declares "
            f"{[(role, flavor) for role, flavor, _w, _l in SWITCH_ROLES]}"
        )

    slot_local_x = {nfet_roles[0]: GROUP_NFET_X_UM}
    well_x0 = (
        GROUP_NFET_X_UM + blocks[block_of_role[nfet_roles[0]]]["bbox"]["x1"]
        + NFET_TO_WELL_UM
    )
    for index, role in enumerate(pfet_roles):
        slot_local_x[role] = well_x0 + WELL_TAP_MARGIN_UM + index * PFET_PITCH_UM
    pfet_top = max(blocks[block_of_role[role]]["bbox"]["y1"] for role in pfet_roles)
    well_x1 = (
        slot_local_x[pfet_roles[-1]]
        + blocks[block_of_role[pfet_roles[-1]]]["bbox"]["x1"]
        + WELL_MARGIN_UM
    )

    # Two independent fit checks, both re-derived from the generated geometry
    # rather than asserted once by choosing SIDE_PITCH_UM carefully:
    #  - the two n-well islands must clear `nwell.2a` with margin
    #    (`_assert_well_isolation` below does this from the same numbers), and
    #  - one group must fit inside SIDE_PITCH_UM with GROUP_CHANNEL_UM to spare
    #    before the next group's own p-substrate tap begins.
    if well_x1 + GROUP_CHANNEL_UM > SIDE_PITCH_UM + GROUP_SUB_TAP_X_UM + 1e-9:
        raise BuildError(
            f"one side group spans 0..{well_x1:.3f} um but SIDE_PITCH_UM is "
            f"{SIDE_PITCH_UM} um: the next group's p-substrate tap starts at "
            f"{SIDE_PITCH_UM + GROUP_SUB_TAP_X_UM:.3f} um, leaving "
            f"{SIDE_PITCH_UM + GROUP_SUB_TAP_X_UM - well_x1:.3f} um of channel, "
            f"below the required {GROUP_CHANNEL_UM} um -- widen SIDE_PITCH_UM"
        )

    plan: dict = {
        "group_extent_um": [GROUP_CAP_X_UM, well_x1],
        "cap_origin_um": {"x": GROUP_CAP_X_UM, "y": CAP_ROW_Y_UM},
        "sides": {},
    }
    for side_index, side in enumerate(SIDES):
        gx = side_index * SIDE_PITCH_UM
        origins = {}
        for role, _flavor, _w, _l in SWITCH_ROLES:
            block_id = next(
                row[0]
                for row in SWITCH_DEVICES
                if row[2] == side and row[1].endswith(f"_{role}")
            )
            origins[block_id] = {"x": gx + slot_local_x[role], "y": 0.0}
        plan["sides"][side] = {
            "group_origin_um": gx,
            "block_origins_um": origins,
            "well": {
                "x0": gx + well_x0,
                "y0": -WELL_BELOW_UM,
                "x1": gx + well_x1,
                "y1": pfet_top + WELL_ABOVE_UM,
            },
            "well_tap": {
                "x0": gx + well_x0 + WELL_TAP_MARGIN_UM / 2 - TAP_WIDTH_UM / 2,
                "x1": gx + well_x0 + WELL_TAP_MARGIN_UM / 2 + TAP_WIDTH_UM / 2,
                "y0": TAP_Y0_UM,
                "y1": TAP_Y1_UM,
            },
            "substrate_tap": {
                "x0": gx + GROUP_SUB_TAP_X_UM,
                "x1": gx + GROUP_SUB_TAP_X_UM + TAP_WIDTH_UM,
                "y0": TAP_Y0_UM,
                "y1": TAP_Y1_UM,
            },
        }
    return plan


def _side_geometry(
    side: str, plan: dict, blocks: dict[str, dict], cap_escape_y: float
) -> tuple[list[tuple[tuple[int, int], Rect]], list[tuple[str, float, float]]]:
    """Every shape and every met1 column ONE side owns, below `TRACK_Y0`.

    Returns `(shapes, columns)` where each column is `(net, x, y_from)`: the x
    a met1 riser will climb at, and the y it starts from. Deliberately
    net-agnostic about geometry -- which net a column carries differs between
    the two sides, the geometry does not, which is exactly what
    `_assert_side_congruence` checks.
    """
    shapes: list[tuple[tuple[int, int], Rect]] = []
    columns: list[tuple[str, float, float]] = []
    side_plan = plan["sides"][side]

    # --- n-well island + its VDD tap ----------------------------------------
    well = side_plan["well"]
    shapes.append((L_NWELL, Rect.um(well["x0"], well["y0"], well["x1"], well["y1"])))
    for spec, net in ((side_plan["well_tap"], "VDD"), (side_plan["substrate_tap"], "GND")):
        tap_geometry, tap_x, tap_y = tap_shapes(spec)
        shapes.extend(tap_geometry)
        shapes.append((L_MCON, Rect.centred(tap_x, tap_y, MCON_UM, MCON_UM)))
        shapes.append((L_MET1, Rect.centred(tap_x, tap_y, WIRE_UM, WIRE_UM)))
        columns.append((net, tap_x, tap_y))

    # --- the three switches' D/G/S pins -------------------------------------
    for block_id, _name, row_side, _flavor, _w, _l, d_net, g_net, s_net, _b in SWITCH_DEVICES:
        if row_side != side:
            continue
        origin = side_plan["block_origins_um"][block_id]
        for suffix, net in (("U0_D", d_net), ("U0_G", g_net), ("U0_S", s_net)):
            x, y, _width, direction, layer = blocks[block_id]["ports"][suffix]
            _add_pin(shapes, columns, net, origin["x"] + x, origin["y"] + y, layer, direction)

    # --- this side's capacitor unit: top and bottom plate escapes -----------
    cap_origin = plan["cap_origin_um"]
    for unit_index, _name, leg_side, top_net, bot_net in CAP_LEGS:
        if leg_side != side:
            continue
        for suffix, net in ((f"C{unit_index}_TOP", top_net), (f"C{unit_index}_BOT", bot_net)):
            x, y, _width, direction, layer = blocks[CAP_BLOCK_ID]["ports"][suffix]
            _add_pin(
                shapes,
                columns,
                net,
                cap_origin["x"] + x,
                cap_origin["y"] + y,
                layer,
                direction,
                met4_escape_y=cap_escape_y,
            )
    return shapes, columns


def _add_pin(
    shapes: list[tuple[tuple[int, int], Rect]],
    columns: list[tuple[str, float, float]],
    net: str,
    px: float,
    py: float,
    layer: tuple[int, int],
    direction: float,
    met4_escape_y: float | None = None,
) -> None:
    """Walk one port down to met1, jog it out of the device's own footprint by
    the direction it faces, and record the column a later pass runs up to this
    net's own met2 track."""
    px, py = step_down_to_met1(shapes, px, py, layer, direction, met4_escape_y=met4_escape_y)
    if direction == 180.0:  # faces -x: jog left
        col_x = px - CHANNEL_LEFT_UM
    elif direction == 0.0:  # faces +x: jog right
        col_x = px + CHANNEL_RIGHT_UM
    else:  # faces +y: straight up, no jog
        col_x = px
    if abs(col_x - px) > 1e-9:
        shapes.append((L_MET1, Rect.hwire(px, col_x, py)))
    columns.append((net, col_x, py))


def _assert_side_congruence(
    per_side: dict[str, list[tuple[tuple[int, int], Rect]]],
    per_side_columns: dict[str, list[tuple[str, float, float]]],
) -> dict:
    """The `_p` half of this network must be the `_n` half translated by
    exactly `(SIDE_PITCH_UM, 0)` -- every shape, and every met1 column.

    This is DR-009's matching-dummy requirement stated as a construction
    property. It is checked in integer nanometres (the database unit), so it is
    exact rather than tolerant: `SIDE_PITCH_UM` is on the 1 nm grid, so a
    congruent layout translates with no rounding at all, and anything that does
    not translate exactly is a real difference between the two sides rather
    than floating-point noise.

    Raises `BuildError` naming the offending shapes. Returns a small summary
    for `layout.summary.json`, so the record states how much was checked rather
    than only that a check ran.
    """
    working, dummy = SIDES
    dx = nm(SIDE_PITCH_UM)

    def key(shapes):
        return sorted(
            (layer, rect.x0, rect.y0, rect.x1, rect.y1) for layer, rect in shapes
        )

    shifted = [
        (layer, r.x0 + dx, r.y0, r.x1 + dx, r.y1) for layer, r in per_side[working]
    ]
    shifted.sort()
    got = key(per_side[dummy])
    if shifted != got:
        only_expected = [entry for entry in shifted if entry not in got]
        only_found = [entry for entry in got if entry not in shifted]
        raise BuildError(
            f"side {dummy!r} is not side {working!r} translated by "
            f"{SIDE_PITCH_UM} um: {len(only_expected)} translated shape(s) "
            f"absent from side {dummy!r} (first: {only_expected[:2]}), "
            f"{len(only_found)} shape(s) on side {dummy!r} with no translated "
            f"counterpart (first: {only_found[:2]})"
        )

    cols_working = sorted(nm(x) for _net, x, _y in per_side_columns[working])
    cols_dummy = sorted(nm(x) for _net, x, _y in per_side_columns[dummy])
    if [x + dx for x in cols_working] != cols_dummy:
        raise BuildError(
            f"side {dummy!r}'s met1 columns are not side {working!r}'s "
            f"translated by {SIDE_PITCH_UM} um: {cols_working} vs {cols_dummy}"
        )

    return {
        "translation_um": SIDE_PITCH_UM,
        "shapes_per_side": len(per_side[working]),
        "columns_per_side": len(cols_working),
        "checked_in_dbu": True,
    }


def _assert_matched_pairs_adjacent() -> None:
    """Each `MATCHED_NET_PAIRS` entry must occupy adjacent `TRACK_ORDER` slots.

    The one asymmetry the congruence assertion cannot remove is the met1 riser
    length difference between a working-side net and its dummy-side
    counterpart, which is `TRACK_PITCH_UM` per track of separation. Adjacency
    pins it at one pitch; nothing else in this module would notice if a
    reordering of `TRACK_ORDER` quietly made it six.
    """
    index = {net: position for position, net in enumerate(TRACK_ORDER)}
    for a, b in MATCHED_NET_PAIRS:
        if abs(index[a] - index[b]) != 1:
            raise BuildError(
                f"matched nets {a!r} (track {index[a]}) and {b!r} (track "
                f"{index[b]}) are not on adjacent tracks: their met1 risers "
                f"would differ by {abs(index[a] - index[b]) * TRACK_PITCH_UM} um "
                f"instead of {TRACK_PITCH_UM} um"
            )


def build(reports_dir: Path) -> tuple[dict, dict, dict]:
    """Return the (draw params, gen-compose request, layout summary) triple."""
    blocks = {bid: load_block(reports_dir / f"{bid}.json") for bid in block_ids()}

    _assert_matched_pairs_adjacent()

    # The `cap_array` unit pitch MUST be the side translation -- see
    # gen_blocks.CAP_SPACING_UM for why it is derived rather than chosen, and
    # why the achieved value is re-read here from the generator's own report.
    cap_ports = blocks[CAP_BLOCK_ID]["ports"]
    cap_pitch = cap_ports["C1_TOP"][0] - cap_ports["C0_TOP"][0]
    if nm(cap_pitch) != nm(SIDE_PITCH_UM):
        raise BuildError(
            f"`klt gen cap_array` placed its two units {cap_pitch:.3f} um apart, "
            f"but the side translation is {SIDE_PITCH_UM} um -- the offset caps "
            f"would not sit in their own sides' groups. Re-derive "
            f"gen_blocks.CAP_MET3_ENCLOSURE_UM from this klt build's own "
            f"cap_array geometry."
        )

    plan = floorplan(blocks)
    _assert_well_isolation_shared(
        [
            {"id": side, "well": plan["sides"][side]["well"]}
            for side in SIDES
        ],
        WELL_GAP_UM,
    )

    cap_escape_y = snap_up(
        plan["cap_origin_um"]["y"]
        + blocks[CAP_BLOCK_ID]["bbox"]["y1"]
        + CAP_MET4_ESCAPE_MARGIN_UM
    )

    per_side: dict[str, list] = {}
    per_side_columns: dict[str, list] = {}
    for side in SIDES:
        per_side[side], per_side_columns[side] = _side_geometry(
            side, plan, blocks, cap_escape_y
        )
    congruence = _assert_side_congruence(per_side, per_side_columns)

    shapes: list[tuple[tuple[int, int], Rect]] = []
    for side in SIDES:
        shapes.extend(per_side[side])

    columns: dict[float, str] = {}
    net_columns: dict[str, list[tuple[float, float]]] = {}
    for side in SIDES:
        for net, x, y_from in per_side_columns[side]:
            if x in columns and columns[x] != net:
                raise BuildError(
                    f"column x={x:.3f} claimed by both {columns[x]!r} and {net!r}"
                )
            columns[x] = net
            net_columns.setdefault(net, []).append((x, y_from))

    _assert_column_pitch_shared(columns, WIRE_UM + MET_SPACE_UM)

    missing = set(net_columns) - set(TRACK_ORDER)
    if missing:
        raise BuildError(f"nets with no assigned met2 track: {sorted(missing)}")
    unused = set(TRACK_ORDER) - set(net_columns)
    if unused:
        raise BuildError(f"tracks assigned to nets with no columns: {sorted(unused)}")

    # --- shared met2 track band, above every row and every met4 escape pad ---
    # Derived from the escape point rather than from the block bboxes alone:
    # a cap `*_TOP` step-down leaves a met2 landing pad at `cap_escape_y`, which
    # is ABOVE the tallest block, and a track band below it would short every
    # net whose track crossed that pad's x.
    geometry_top = max(
        max(
            origin["y"] + blocks[bid]["bbox"]["y1"]
            for bid, origin in plan["sides"][side]["block_origins_um"].items()
        )
        for side in SIDES
    )
    geometry_top = max(
        geometry_top,
        cap_escape_y + STACK_PAD_UM / 2,
        plan["cap_origin_um"]["y"] + blocks[CAP_BLOCK_ID]["bbox"]["y1"],
    )
    track_y0 = snap_up(geometry_top + TRACK_MARGIN_ABOVE_UM)

    labels: list[tuple[tuple[int, int], str, float, float]] = []
    summary_nets: dict[str, dict] = {}
    met1_riser_um = {side: 0.0 for side in SIDES}
    side_of_column = {
        nm(x): side for side in SIDES for _net, x, _y in per_side_columns[side]
    }
    for index, net in enumerate(TRACK_ORDER):
        track_y = track_y0 + index * TRACK_PITCH_UM
        cols = sorted(net_columns[net])
        for x, y_from in cols:
            shapes.append((L_MET1, Rect.vwire(x, y_from, track_y)))
            shapes.append((L_MET1, Rect.centred(x, track_y, WIRE_UM, WIRE_UM)))
            shapes.append((L_VIA1, Rect.centred(x, track_y, VIA1_UM, VIA1_UM)))
            met1_riser_um[side_of_column[nm(x)]] += track_y - y_from
        xs = [x for x, _ in cols]
        if len(xs) == 1:
            shapes.append(
                (L_MET2, Rect.centred(xs[0], track_y, SINGLE_COLUMN_PAD_UM, SINGLE_COLUMN_PAD_UM))
            )
        else:
            shapes.append((L_MET2, Rect.hwire(min(xs), max(xs), track_y)))
        if net in PIN_NETS:
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

    origins = {
        bid: origin
        for side in SIDES
        for bid, origin in plan["sides"][side]["block_origins_um"].items()
    }
    origins[CAP_BLOCK_ID] = plan["cap_origin_um"]
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

    riser_delta = abs(met1_riser_um[SIDES[0]] - met1_riser_um[SIDES[1]])
    layout_summary = {
        "side_translation_um": SIDE_PITCH_UM,
        "side_congruence": congruence,
        "group_extent_um": [round(v, 3) for v in plan["group_extent_um"]],
        "cap_origin_um": plan["cap_origin_um"],
        "cap_unit_pitch_um": round(cap_pitch, 3),
        "cap_met4_escape_y_um": round(cap_escape_y, 3),
        "track_y0_um": round(track_y0, 3),
        "nwell_2a_rule_um": 1.27,
        "well_gap_drawn_um": round(
            plan["sides"][SIDES[1]]["well"]["x0"] - plan["sides"][SIDES[0]]["well"]["x1"], 3
        ),
        "sides": {
            side: {
                "group_origin_um": plan["sides"][side]["group_origin_um"],
                "block_origins_um": plan["sides"][side]["block_origins_um"],
                "well_um": {k: round(v, 3) for k, v in plan["sides"][side]["well"].items()},
                "well_tap_um": {
                    k: round(v, 3) for k, v in plan["sides"][side]["well_tap"].items()
                },
                "substrate_tap_um": {
                    k: round(v, 3) for k, v in plan["sides"][side]["substrate_tap"].items()
                },
                "met1_riser_total_um": round(met1_riser_um[side], 3),
            }
            for side in SIDES
        },
        "met1_riser_asymmetry_um": round(riser_delta, 3),
        "met1_riser_asymmetry_area_um2": round(riser_delta * WIRE_UM, 4),
        "matched_net_pairs": [list(pair) for pair in MATCHED_NET_PAIRS],
        "nets": summary_nets,
    }
    return draw_params, compose_request, layout_summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "reports_dir", type=Path, help="directory holding every <block>.json report"
    )
    args = parser.parse_args()

    draw_params, compose_request, layout_summary = build(args.reports_dir)
    (args.reports_dir / "draw.request.json").write_text(
        json.dumps(draw_params, indent=2) + "\n"
    )
    (args.reports_dir / "compose.request.json").write_text(
        json.dumps(compose_request, indent=2) + "\n"
    )
    (args.reports_dir / "layout.summary.json").write_text(
        json.dumps(layout_summary, indent=2) + "\n"
    )
    print(
        f"build_layout.py: {len(draw_params['shapes'])} shapes, "
        f"{len(draw_params['labels'])} labels, {len(compose_request['blocks'])} blocks"
    )
    congruence = layout_summary["side_congruence"]
    print(
        f"build_layout.py: sides congruent under a "
        f"{congruence['translation_um']} um translation -- "
        f"{congruence['shapes_per_side']} shapes and "
        f"{congruence['columns_per_side']} met1 columns per side, checked in DBU"
    )
    print(
        f"build_layout.py: residual met1 riser asymmetry "
        f"{layout_summary['met1_riser_asymmetry_um']} um "
        f"({layout_summary['met1_riser_asymmetry_area_um2']} um^2 of met1)"
    )
    print(f"build_layout.py: track band starts at y={layout_summary['track_y0_um']} um")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Floorplan, well-partition and route the sampling front end's PFET set
(issue #122) -- the composed **n-well isolation island** recipe.

Emits the two documents `layout/sampling-frontend-wells/bin/run-flow.sh`
feeds to `klt`:

* ``draw.request.json`` -- a ``klt draw`` request holding every shape this
  module owns: the three n-well island rectangles, their three tap
  structures, every wire (met1 branches/stubs, met2 per-net tracks, mcon/via
  cuts) and the fourteen top-level pin labels, in the *composed* coordinate
  system.
* ``compose.request.json`` -- a ``klt gen-compose`` request placing
  `gen_blocks.py`'s nine device blocks plus the routing/well cell at explicit
  origins, with **no** ``routing`` block (`klt gen-compose` is used purely as
  a placer, the same choice `layout/comparator/bin/build_layout.py` documents
  and for the same reasons).

======================================================================
THE RECIPE: a named-net n-well island, isolated from its neighbours
======================================================================

This is the artefact issue #122 exists to establish, written down here so a
later full sampling-frontend layout (#99) does not have to re-derive it. It
has four parts, and **all four are required** -- dropping any one of them
yields a layout that can still pass DRC while being electrically wrong.

1. **Partition the PFETs by body net, and make the partition the floorplan.**
   `gen_blocks.py`'s ``DEVICES`` table carries a ``domain`` per device, and
   the blocks are placed in domain order, all of one domain's devices
   adjacent. A domain is a *contiguous x range*; that is what lets one
   rectangle per domain do the whole job. Here: ``boost_p`` = {Sa_p, Se_p},
   ``vdd`` = {Scp_p, Cmswp_p, Invp, Cmswp_n, Scp_n}, ``boost_n`` = {Se_n,
   Sa_n}.

2. **One n-well rectangle per domain, drawn by this module, merging that
   domain's blocks' own wells -- and nothing else's.** `klt gen mos_array
   --params '{"flavor": "pfet"}'` draws a small local n-well around its own
   unit device. Overlapping rectangles merge into one KLayout region, so a
   single drawn rectangle spanning one domain merges exactly that domain's
   device wells and extends far enough to hold a tap. Two domains' rectangles
   must not touch: ``WELL_GAP_UM`` below is the drawn separation, and it is
   the parameter the whole isolation claim rests on.

3. **A tap inside each island, routed to that domain's net.** A `tap`
   (65/44) shape inside the island, contacted up through licon1 to li1 and
   then through mcon/met1/via/met2 onto the domain's own signal net -- the
   *same* net the devices' source/drain terminals are wired to, not a
   separate "well supply". `klt extract`'s sky130 deck splits `tap` by
   `nwell` containment and wires each tap to the well region that contains
   it, so the well net -- and therefore every PMOS body terminal drawn inside
   that well -- takes the name of whatever the tap is routed to. Nothing else
   names it: this module deliberately draws **no** ``nwell.pin`` (64/5) well
   label, because a drawn label would name the well even if the tap routing
   were broken, and would turn the extraction verdict into a tautology.

4. **Verify the split with a deck that actually carries n-well rules.** `klt
   drc --deck sky130`'s curated rule table did not, at klt 0.3.0 -- no width,
   no spacing, no enclosure -- so a *deliberately* split well passed it
   vacuously on exactly the rules that govern the split. klt 0.4.0 closed
   that gap (2AMLogic/klayout-tools#1420): the curated deck now carries
   ``nwell.width.1``/``nwell.space.1`` directly, checkable with
   `run-flow.sh`'s existing `klt drc --deck sky130` call and a
   negative-control fixture (`drc/nwell_violation_fixture.json`) proving it
   fires. See `../README.md` for the full writeup and issue #149, which
   retired the hand-written `--engine klayout` deck this recipe used to
   need.

Why not `klt gen guard_ring`
----------------------------
`guard_ring` with ``add_well: true`` draws a tap ring inside its own well and
is the closest existing primitive -- but its well tie ties to whatever the
caller routes the ring to, so it does not by itself *isolate* a named-net
island from a caller-specified set of other wells, and a closed ring around a
device blocks routing to every port inside it (the finding
`layout/comparator/bin/gen_blocks.py`'s own docstring records). No `klt gen`
generator produces a named-net-isolated well island directly, so this module
composes one through `klt draw` -- the documented escape hatch for exactly
this ("write a primitive GDSII/OASIS stream from a JSON shape description").

Routing style
-------------
Deliberately simpler than `layout/comparator/`'s greedy channel router,
because this floorplan is a single row and every net's pin set is small:

* every net owns one **met2** horizontal track at its own y, above the device
  row (``TRACK_Y0`` + k * ``TRACK_PITCH_UM``);
* every pin reaches its track on a **met1** column: a source/drain pin first
  jogs horizontally at its own pad y into the free channel beside its block
  (left for S, right for D), then rises; a gate pin -- whose landing pad
  `klt gen`'s ``gate_contact`` already raises clear of the S/D metal -- rises
  straight up from the pad;
* a well tap rises on its own column in the left margin of its domain.

The jog is what makes the columns legal: within a minimum-length device the
S/G/D landing pads are only 0.335 um apart, closer than a 0.30 um met1 wire
plus ``met1.space.1`` (0.14) allows, so routing all three straight up would
be a spacing violation. Jogging S and D into the channels leaves the three
columns >= 0.66 um apart. :func:`_assert_column_pitch` re-checks that
invariant at build time against the actual generated geometry rather than
trusting these numbers to stay true if a device size changes.

Layer plane split (what makes this tractable, same as the comparator's):
every `klt gen` block draws only nwell/diff/poly/licon1/li1, so met1 and met2
are owned outright by this module and cannot short into a block by running
over it -- only a deliberately-placed mcon cut connects a route to a block's
li1 pad.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "bin"))

from _geometry_common import Rect as _Rect  # noqa: E402
from gen_blocks import DEVICES, DOMAIN_TAP_NET, PIN_NETS  # noqa: E402

# --- layer table (sky130A GDS numbers, as klt's own curated deck names them) --
L_NWELL = (64, 20)
L_TAP = (65, 44)
L_LICON = (66, 44)
L_LI1 = (67, 20)
L_MCON = (67, 44)
L_MET1 = (68, 20)
L_VIA = (68, 44)
L_MET2 = (69, 20)
L_MET2_PIN = (69, 5)

# --- rule-derived geometry (sky130 deck thresholds + margin) -----------------
# Every value here is >= the corresponding klt sky130 deck threshold; the deck
# is the authority, these are the drawn sizes chosen to clear it.
WIRE_UM = 0.30  # met1/met2 wire + landing-pad width (m1.1/m2.1 minimum 0.14)
MET_SPACE_UM = 0.14  # m1.2 / m2.2
MCON_UM = 0.17
VIA_UM = 0.15
LICON_UM = 0.17
LICON_PITCH_UM = 0.60

#: Drawn n-well island separation. sky130's own ``nwell.2a`` ("min. nwell
#: spacing (merged if less)") is 1.27 um -- transcribed from
#: ``$PDK_ROOT/$PDK/libs.tech/klayout/drc/sky130A.lydrc`` line 213,
#: ``nwell.isolated(1.27, euclidian)``. 1.60 um is that rule plus margin, and
#: is the single number the whole body-tie isolation claim rests on: below
#: 1.27 um the two islands are not legally separate wells at all.
WELL_GAP_UM = 1.60

#: n-well margin around a domain's device blocks and its tap.
WELL_MARGIN_UM = 0.30
#: Left margin of each domain's n-well, reserved for the tap column.
WELL_TAP_MARGIN_UM = 2.00
#: n-well extent below / above the device row.
WELL_BELOW_UM = 2.40
WELL_ABOVE_UM = 0.40

#: Tap strip geometry, in each domain's left margin (x relative to the
#: domain's n-well x0), below the device row.
TAP_X0_UM = 0.40
TAP_X1_UM = 1.00
TAP_Y0_UM = -1.80
TAP_Y1_UM = -0.60

#: Device block pitch along the row.
BLOCK_PITCH_UM = 3.20
#: Channel columns: a source pin jogs this far left of its block's left edge,
#: a drain pin this far right of its right edge.
CHANNEL_LEFT_UM = 0.45
CHANNEL_RIGHT_UM = 0.45

#: met2 per-net track band, above the tallest device block.
TRACK_Y0_UM = 4.20
TRACK_PITCH_UM = 0.50

#: Order the met2 tracks are assigned in (bottom-up). Supplies and the two
#: clock phases first (the widest-fanout nets, so their tracks sit closest to
#: the devices and their met1 columns stay short), then the per-side signals.
TRACK_ORDER = (
    "SAMPLEB",
    "SAMPLE",
    "VDD",
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
)


class Rect(_Rect):
    """An axis-aligned rectangle in integer nanometres.

    ``__slots__``, ``__init__``, ``um()``, ``centred()`` and ``as_um()`` are
    the shared shell inherited from `layout/bin/_geometry_common.py`;
    ``hwire()``/``vwire()`` below are this sub-block's own well-tie-wiring
    extension.
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
    """Read a `klt gen` report -> ``{"ports": {name: (x, y, extent)}, "bbox"}``."""
    report = json.loads(report_path.read_text())
    ports = {}
    for port in report["ports"]:
        # A `klt gen` port reports its pad centre plus the pad's extent
        # *perpendicular to the direction it faces*: an S/D port (facing
        # +/-x) reports its pad height, a gate port (facing +y) its width.
        ports[port["name"]] = (port["x_um"], port["y_um"], port["width_um"])
    return {"ports": ports, "bbox": report["bbox_um"]}


def floorplan(blocks: dict[str, dict]) -> tuple[dict, list[dict]]:
    """Place every device block and size the three n-well islands.

    Returns ``(origins, domains)`` where ``origins`` maps block id ->
    ``{"x": .., "y": ..}`` (the `klt gen-compose` placement) and ``domains``
    is one entry per n-well island, in left-to-right order.
    """
    origins: dict[str, dict[str, float]] = {}
    domains: list[dict] = []

    cursor = 0.0
    ordered_domains: list[str] = []
    for _bid, _name, domain, *_rest in DEVICES:
        if domain not in ordered_domains:
            ordered_domains.append(domain)

    for domain in ordered_domains:
        members = [row[0] for row in DEVICES if row[2] == domain]
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
    """Every pair of adjacent islands must clear ``nwell.2a`` with margin.

    Checked here as well as by `klt drc --deck sky130` (nwell.space.1, as of
    klt 0.4.0) on the finished GDS: a build-time failure names the offending
    pair, a DRC failure only names a coordinate.
    """
    for a, b in zip(domains, domains[1:]):
        gap = b["well"]["x0"] - a["well"]["x1"]
        if gap < WELL_GAP_UM - 1e-9:
            raise BuildError(
                f"n-well islands {a['id']!r} and {b['id']!r} are {gap:.3f} um "
                f"apart, below the drawn separation {WELL_GAP_UM} um"
            )


def _assert_column_pitch(columns: dict[float, str]) -> None:
    """No two met1 columns may come closer than a wire width + met1 spacing.

    The floorplan constants above make this true, but a device-size change
    (a wider W, a longer L) moves the landing pads and could silently break
    it -- so it is re-derived from the *actual* generated port geometry on
    every build rather than asserted once in a comment.
    """
    minimum = WIRE_UM + MET_SPACE_UM
    xs = sorted(columns)
    for xa, xb in zip(xs, xs[1:]):
        if xb - xa < minimum - 1e-9:
            raise BuildError(
                f"met1 columns for nets {columns[xa]!r} (x={xa:.3f}) and "
                f"{columns[xb]!r} (x={xb:.3f}) are {xb - xa:.3f} um apart, "
                f"below the {minimum:.2f} um wire+space pitch"
            )


def tap_shapes(spec: dict) -> tuple[list[tuple[tuple[int, int], Rect]], float, float]:
    """Draw one well-tap structure; returns its shapes and its mcon landing point."""
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


def build(reports_dir: Path) -> tuple[dict, dict, dict]:
    """Return the (draw params, gen-compose request, well summary) triple."""
    blocks = {row[0]: load_block(reports_dir / f"{row[0]}.json") for row in DEVICES}
    origins, domains = floorplan(blocks)
    _assert_well_isolation(domains)

    shapes: list[tuple[tuple[int, int], Rect]] = []
    labels: list[tuple[tuple[int, int], str, float, float]] = []

    # --- the three n-well islands and their taps ---------------------------
    # Drawn first, before any routing: the well partition is the deliverable,
    # the wires only carry its tap net.
    net_columns: dict[str, list[tuple[float, float]]] = {}
    columns: dict[float, str] = {}

    def add_column(net: str, x: float, y_from: float) -> None:
        if x in columns and columns[x] != net:
            raise BuildError(f"column x={x:.3f} claimed by both {columns[x]!r} and {net!r}")
        columns[x] = net
        net_columns.setdefault(net, []).append((x, y_from))

    for domain in domains:
        well = domain["well"]
        shapes.append((L_NWELL, Rect.um(well["x0"], well["y0"], well["x1"], well["y1"])))
        tap_geometry, tap_x, tap_y = tap_shapes(domain["tap"])
        shapes.extend(tap_geometry)
        shapes.append((L_MCON, Rect.centred(tap_x, tap_y, MCON_UM, MCON_UM)))
        shapes.append((L_MET1, Rect.centred(tap_x, tap_y, WIRE_UM, WIRE_UM)))
        add_column(domain["net"], tap_x, tap_y)

    # --- per-device pin columns --------------------------------------------
    for block_id, _name, _domain, _w, _l, d_net, g_net, s_net in DEVICES:
        block = blocks[block_id]
        ox = origins[block_id]["x"]
        bbox = block["bbox"]
        sx, sy, _ = block["ports"]["U0_S"]
        dx, dy, _ = block["ports"]["U0_D"]
        gx, gy, _ = block["ports"]["U0_G"]

        left_col = ox + bbox["x0"] - CHANNEL_LEFT_UM
        right_col = ox + bbox["x1"] + CHANNEL_RIGHT_UM

        # Source: mcon on the pad, met1 jog left into the channel, then up.
        shapes.append((L_MCON, Rect.centred(ox + sx, sy, MCON_UM, MCON_UM)))
        shapes.append((L_MET1, Rect.hwire(left_col, ox + sx, sy)))
        add_column(s_net, left_col, sy)

        # Drain: mcon on the pad, met1 jog right into the channel, then up.
        shapes.append((L_MCON, Rect.centred(ox + dx, dy, MCON_UM, MCON_UM)))
        shapes.append((L_MET1, Rect.hwire(ox + dx, right_col, dy)))
        add_column(d_net, right_col, dy)

        # Gate: `gate_contact` already raised this pad clear of the S/D
        # metal, so it rises straight up from where it sits.
        shapes.append((L_MCON, Rect.centred(ox + gx, gy, MCON_UM, MCON_UM)))
        shapes.append((L_MET1, Rect.centred(ox + gx, gy, WIRE_UM, WIRE_UM)))
        add_column(g_net, ox + gx, gy)

    _assert_column_pitch(columns)

    missing = set(net_columns) - set(TRACK_ORDER)
    if missing:
        raise BuildError(f"nets with no assigned met2 track: {sorted(missing)}")

    # --- met2 per-net tracks + the met1 columns that reach them -------------
    summary_nets: dict[str, dict] = {}
    for index, net in enumerate(TRACK_ORDER):
        track_y = TRACK_Y0_UM + index * TRACK_PITCH_UM
        cols = sorted(net_columns[net])
        for x, y_from in cols:
            shapes.append((L_MET1, Rect.vwire(x, y_from, track_y)))
            shapes.append((L_MET1, Rect.centred(x, track_y, WIRE_UM, WIRE_UM)))
            shapes.append((L_VIA, Rect.centred(x, track_y, VIA_UM, VIA_UM)))
        xs = [x for x, _ in cols]
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
            {"layer": list(layer), "text": text, "at_um": [x, y]}
            for layer, text, x, y in labels
        ],
    }

    order = [row[0] for row in DEVICES] + ["route"]
    compose_request = {
        "schema": "klt.gen_compose.request/1",
        "pdk": {"variant": "sky130A"},
        "blocks": [{"id": row[0], "generator_report": f"{row[0]}.json"} for row in DEVICES]
        + [{"id": "route", "generator_report": "draw.json"}],
        "placement": {
            "strategy": "explicit",
            "order": order,
            "origins_um": {**origins, "route": {"x": 0.0, "y": 0.0}},
        },
        # Deliberately no `routing` block: `klt gen-compose` is a placer here.
        "connectivity": [],
    }

    well_summary = {
        "well_gap_drawn_um": WELL_GAP_UM,
        "nwell_2a_rule_um": 1.27,
        "domains": [
            {
                "id": domain["id"],
                "tap_net": domain["net"],
                "members": domain["members"],
                "schematic_devices": [
                    row[1] for row in DEVICES if row[2] == domain["id"]
                ],
                "well_um": {k: round(v, 3) for k, v in domain["well"].items()},
                "tap_um": {k: round(v, 3) for k, v in domain["tap"].items()},
            }
            for domain in domains
        ],
        "island_gaps_um": [
            round(b["well"]["x0"] - a["well"]["x1"], 3)
            for a, b in zip(domains, domains[1:])
        ],
        "block_origins_um": origins,
        "nets": summary_nets,
    }
    return draw_params, compose_request, well_summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "reports_dir", type=Path, help="directory holding the nine <block>.json reports"
    )
    args = parser.parse_args()

    draw_params, compose_request, well_summary = build(args.reports_dir)
    (args.reports_dir / "draw.request.json").write_text(json.dumps(draw_params, indent=2) + "\n")
    (args.reports_dir / "compose.request.json").write_text(
        json.dumps(compose_request, indent=2) + "\n"
    )
    (args.reports_dir / "wells.summary.json").write_text(
        json.dumps(well_summary, indent=2) + "\n"
    )
    print(
        f"build_layout.py: {len(draw_params['shapes'])} shapes, "
        f"{len(draw_params['labels'])} labels, {len(compose_request['blocks'])} blocks"
    )
    for domain in well_summary["domains"]:
        well = domain["well_um"]
        print(
            f"build_layout.py: n-well island {domain['id']} -> tap net "
            f"{domain['tap_net']}: x {well['x0']}..{well['x1']} um, "
            f"devices {', '.join(domain['schematic_devices'])}"
        )
    print(f"build_layout.py: island gaps {well_summary['island_gaps_um']} um")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

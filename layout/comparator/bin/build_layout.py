#!/usr/bin/env python3
"""Floorplan + route the dynamic comparator sub-block (issue #101).

Emits the two documents `layout/comparator/bin/run-flow.sh` feeds to `klt`:

* ``draw.request.json`` -- a ``klt draw`` request holding **every** wire in this
  sub-block (met1 branches, met2 trunks, mcon/via cuts, the two body-tie tap
  structures, the merged n-well, and the seven top-level pin labels), drawn in
  the *composed* coordinate system.
* ``compose.request.json`` -- a ``klt gen-compose`` request that places the five
  matched device blocks `gen_blocks.py` generated, plus the routing cell above,
  at explicit origins, with **no** ``routing`` block.

Why this split rather than letting `klt gen-compose` route (the shape the first
increment of #101 used, superseded here):

    `klt gen-compose`'s own contract says the geometry it draws is *advisory* --
    "`klt drc` remains the rule-compliance authority on the composed output, so
    a routed net (`routed: true`) is not a DRC-clean guarantee" (its module
    docstring).  Measured against this block it is not merely advisory but
    unusable as a signoff path: legs it reports `routed: true` land
    `li1.space.1`/`met1.space.1` violations, and a block carrying more than one
    same-block self-net (which a `splits`-interleaved matched pair inherently
    does -- each device's own legs have to tie together) can only ever get one
    of them routed.  Both are filed generically, with no design content, at
    2AMLogic/klayout-tools#1386 per CLAUDE.md's friction protocol.

    `klt draw` is the documented escape hatch for exactly this: "write a
    primitive GDSII/OASIS stream from a JSON shape description", the
    deliberately-dumb write-side verb.  Routing this block by hand against a
    router *we* control is what makes a DRC-clean, LVS-clean verdict reachable
    at all; the device geometry itself is still 100% `klt gen`'s (see
    `gen_blocks.py`), so the matching strategy is unchanged and nothing about
    the devices is hand-drawn.

Layer plane split (what makes this tractable): every `klt gen` block draws only
nwell/diff/poly/licon1/li1 -- **met1 and met2 are completely unused by the
device blocks**, so this module owns both planes outright and cannot short into
a block by routing over it.  Only a deliberately-placed `mcon` cut connects a
route to a block's li1 pad.

Routing style
-------------
* **met1** carries every horizontal branch and the short vertical stub that
  lifts a branch off its pad's own y.
* **met2** carries per-net vertical trunks (one or two per net, at hand-assigned
  x tracks in the inter-block channels), plus nothing else.
* A net with two trunks joins them with one met1 "spine" -- one long wire per
  net instead of one per far-side pin.

Track assignment is a small greedy channel router (:func:`route_net`): candidate
y-tracks on a 0.5 um pitch, tried nearest-first, rejected when the resulting
met1 rectangles come within `MET1_SPACE_UM` of another net's met1.  It is
deterministic (no randomness, no dict-ordering dependence) so a re-run from a
clean checkout reproduces the identical GDS.

Floorplan
---------
Blocks sit in one left-to-right row.  Their y origins are chosen so that every
`diff_pair` block's Q1/Q2 boundary lands on the same horizontal axis
``Y_AXIS``: Q1 (the OUTP-side device of each pair) below it, Q2 (the OUTN-side
device) above it, and the tail switch and the cross-quad input pair centred on
it.  That makes the differential half-circuits mirror images about ``Y_AXIS``,
which is the point: the two sides of a comparator want to see the same
environment.

Body ties
---------
`gen_blocks.py` draws no guard rings (see its own docstring for why), so this
module draws the two body-tie structures the block needs to extract with real
supply-referenced bodies rather than KLayout's synthesized `vsubs` proxy:

* a p-substrate tie -- `tap` outside every n-well, contacted up to the GND net,
  which `klt extract`'s sky130 deck merges with every NMOS body terminal via its
  `connect_global(tap_substrate_outside, substrate_net)` wiring;
* an n-well tie -- `tap` inside the well, contacted up to VDD, naming the well
  net (and therefore every PMOS body terminal) VDD.

The `latp`/`rst` blocks each draw their own local n-well; this module draws one
enclosing n-well rectangle that merges them into a single well and extends it
far enough right to hold the well tie.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# --- layer table (sky130A GDS numbers, as klt's own curated deck names them) --
L_NWELL = (64, 20)
L_DIFF = (65, 20)
L_TAP = (65, 44)
L_LICON = (66, 44)
L_LI1 = (67, 20)
L_MCON = (67, 44)
L_MET1 = (68, 20)
L_MET1_PIN = (68, 5)
L_VIA = (68, 44)
L_MET2 = (69, 20)

# --- rule-derived geometry (sky130 deck thresholds + margin) -----------------
# Every value here is >= the corresponding klt sky130 deck threshold; the deck
# is the authority, these are the drawn sizes chosen to clear it.
MCON_UM = 0.17  # ct.2 spacing 0.19 respected by the track pitch below
VIA_UM = 0.15  # via.1a_a min size 0.15
PAD_UM = 0.30  # met1/met2 landing pad: 0.065 over mcon, 0.075 over via
WIRE_UM = 0.30  # met1/met2 wire width (m1.1/m2.1 minimum is 0.14)
MET1_SPACE_UM = 0.14  # m1.2
MCON_SPACE_UM = 0.19  # ct.2
TRACK_PITCH_UM = 0.50  # y pitch for met1 branches: 0.30 wire + 0.20 gap
PAD_MARGIN_UM = 0.12  # keep an mcon this far inside its li1 pad's own edges
LICON_UM = 0.17
LICON_PITCH_UM = 0.60

DBU = 1000  # nm per um


def nm(value_um: float) -> int:
    """Micrometres -> integer nanometres (the layout database unit)."""
    return int(round(value_um * DBU))


# --- schematic connectivity --------------------------------------------------
# Net -> [(block id, port name)], transcribed device-by-device from
# design/comparator.sch (sim/comparator-decision/testbench/comparator_core.spice
# is the xschem-derived device list this was checked against, pin for pin):
#
#   XM_TAIL   TAIL CLK  GND  -> tail.U0        (D G S)
#   XM_INN    OUTP VINN TAIL -> inpair.Q1_{1,2}
#   XM_INP    OUTN VINP TAIL -> inpair.Q2_{1,2}
#   XM_LATN_P OUTP OUTN GND  -> latn.Q1_1
#   XM_LATN_N OUTN OUTP GND  -> latn.Q2_1
#   XM_LATP_P OUTP OUTN VDD  -> latp.Q1_1
#   XM_LATP_N OUTN OUTP VDD  -> latp.Q2_1
#   XM_RST_P  OUTP CLK  VDD  -> rst.Q1_1
#   XM_RST_N  OUTN CLK  VDD  -> rst.Q2_1
NET_PINS: dict[str, list[tuple[str, str]]] = {
    "GND": [("tail", "U0_S"), ("latn", "Q1_1_S"), ("latn", "Q2_1_S")],
    "CLK": [("tail", "U0_G"), ("rst", "Q1_1_G"), ("rst", "Q2_1_G")],
    "TAIL": [
        ("tail", "U0_D"),
        ("inpair", "Q1_1_S"),
        ("inpair", "Q2_1_S"),
        ("inpair", "Q2_2_S"),
        ("inpair", "Q1_2_S"),
    ],
    "VDD": [
        ("latp", "Q1_1_S"),
        ("latp", "Q2_1_S"),
        ("rst", "Q1_1_S"),
        ("rst", "Q2_1_S"),
    ],
    "VINN": [("inpair", "Q1_1_G"), ("inpair", "Q1_2_G")],
    "VINP": [("inpair", "Q2_1_G"), ("inpair", "Q2_2_G")],
    "OUTP": [
        ("inpair", "Q1_1_D"),
        ("inpair", "Q1_2_D"),
        ("latn", "Q1_1_D"),
        ("latn", "Q2_1_G"),
        ("latp", "Q1_1_D"),
        ("latp", "Q2_1_G"),
        ("rst", "Q1_1_D"),
    ],
    "OUTN": [
        ("inpair", "Q2_1_D"),
        ("inpair", "Q2_2_D"),
        ("latn", "Q2_1_D"),
        ("latn", "Q1_1_G"),
        ("latp", "Q2_1_D"),
        ("latp", "Q1_1_G"),
        ("rst", "Q2_1_D"),
    ],
}

#: Nets promoted to top-level pins (labelled on met1.pin).  TAIL is deliberately
#: absent: it is an internal node of design/comparator.sch, and the LVS
#: reference declares exactly these seven ports.
PIN_NETS = ("VDD", "GND", "CLK", "VINP", "VINN", "OUTP", "OUTN")

#: Order the nets are routed in.  Two rules, both load-bearing:
#:   * a gate-fed net goes first -- a gate pad is only 0.42 um tall, so its mcon
#:     y is essentially pinned and it has the least freedom to be routed around;
#:   * the *positive* half of each differential pair goes before its negative
#:     half, because the negative half mirrors it (see MIRROR_PIN).
ROUTE_ORDER = ("VINN", "VINP", "CLK", "OUTP", "OUTN", "TAIL", "GND", "VDD")

#: Mirror pairing for the differential signal nets: ``negative-half pin ->
#: positive-half pin it is the Y_AXIS mirror image of``.
#:
#: This is the routing half of this block's matching story, and it is *not*
#: implied by the device matching `gen_blocks.py` already establishes.  Two
#: perfectly matched input devices still see different input-referred offset if
#: OUTP and OUTN carry different wire capacitance, because a dynamic
#: comparator's decision is a race between the two output nodes' charging
#: rates -- unequal loading biases that race exactly the way a device Vth
#: mismatch does.  So each negative-half branch is routed on the mirror image
#: of its positive-half counterpart's own y-track (``2*Y_AXIS - y``) wherever
#: that track is free, rather than on whatever the greedy search happens to
#: reach first.
#:
#: The pairing is *not* pin-list order.  For the two-device blocks it is simply
#: Q1 (below the axis) <-> Q2 (above it).  For the cross-quad input pair it
#: follows the common-centroid interleave: the mirror of the bottom-left leg is
#: the top-LEFT leg, which belongs to the *other* device -- which is precisely
#: what makes the arrangement common-centroid in the first place.
#:
#: **Source/drain pins only, deliberately.**  A `klt gen` unit device puts its
#: gate landing pad *above* its own diffusion, on both halves of a pair alike,
#: so two mirror-role devices' gate pads are related by translation, not by
#: reflection: forcing a gate branch onto ``2*Y_AXIS - y`` would drag it a
#: device-height away from the pad it has to land on and make the imbalance
#: worse, not better.  Gate branches therefore take the default
#: shortest-branch preference, and the residual gate-side asymmetry is reported
#: in ``route.summary.json`` rather than papered over.  Source/drain pads *are*
#: true mirror images (they span their device's full height, and the floorplan
#: aligns the Q1/Q2 boundary to ``Y_AXIS``), which is where the mirror
#: preference buys something real.
MIRROR_PIN: dict[tuple[str, str], tuple[str, str]] = {
    ("inpair", "Q2_1_D"): ("inpair", "Q1_2_D"),  # (right, above) <-> (right, below)
    ("inpair", "Q2_2_D"): ("inpair", "Q1_1_D"),  # (left,  above) <-> (left,  below)
    ("latn", "Q2_1_D"): ("latn", "Q1_1_D"),
    ("latp", "Q2_1_D"): ("latp", "Q1_1_D"),
    ("rst", "Q2_1_D"): ("rst", "Q1_1_D"),
}

#: The gate-side counterpart of MIRROR_PIN: ``pin -> pin whose y-track it should
#: reuse verbatim`` (no reflection).  This is the correct relationship for the
#: cross-quad's own gate pads, which -- per MIRROR_PIN's note -- sit above their
#: devices on both halves alike, so the two input nets' pads pair up *by row*:
#: VINN's upper-row gate and VINP's upper-row gate are at the same y in adjacent
#: columns.  Routing both on one track equalises the two input nets' trunk
#: lengths, which is the dominant term in their wire-area imbalance.
#:
#: It is a preference, and on the upper row it does not bind: VINN's upper gate
#: sits in the right column while its trunk is on the left, and VINP's is the
#: other way round, so the two wires must cross -- one goes above the pads, the
#: other below, and they cannot share a track.  ``route.summary.json`` reports
#: the residual imbalance that leaves rather than hiding it.
SAME_TRACK_PIN: dict[tuple[str, str], tuple[str, str]] = {
    ("inpair", "Q2_1_G"): ("inpair", "Q1_1_G"),  # both lower-row gate pads
    ("inpair", "Q2_2_G"): ("inpair", "Q1_2_G"),  # both upper-row gate pads
}

# --- floorplan ---------------------------------------------------------------
#: Horizontal axis every diff_pair block's Q1/Q2 boundary is aligned to.
Y_AXIS = 20.0

#: Block x origins (left to right).  Channel widths are ~2 um -- enough for the
#: two met2 trunks each channel carries plus clearance.
BLOCK_X = {
    "tail": 2.00,
    "inpair": 5.50,
    "latn": 10.70,
    "latp": 14.20,
    "rst": 18.00,
}

#: Per-block y offset applied to Y_AXIS.  For a two-device diff_pair block this
#: is the block-local y of the Q1/Q2 boundary (so the boundary lands on
#: Y_AXIS); for the single-device blocks it is the device's own centre.
BLOCK_Y_ANCHOR = {
    "tail": 4.00,  # centre of the single W=8 tail device
    "inpair": 2.61,  # centre of the 2x2 cross-quad
    "latn": 4.61,  # Q1 top (4.00) .. Q2 bottom (5.22) midpoint
    "latp": 8.61,
    "rst": 16.61,
}

#: Per-net met2 trunk x positions.  Sorted across all nets these are >= 0.5 um
#: apart, which clears m2.2 (0.14) with a 0.30 um wire by a wide margin.  A net
#: with two entries gets one met1 spine joining them.
TRUNK_X = {
    "GND": (1.30, 9.60),
    "CLK": (1.90, 16.40),
    "TAIL": (4.30,),
    "VINN": (4.90,),
    "VINP": (9.10,),
    "OUTP": (10.10, 16.90),
    "OUTN": (10.60, 17.40),
    "VDD": (17.90, 20.30),
}

#: Preferred y for each net's spine (the one long wire per two-trunk net).
#: Chosen in the sparsely-used bands above and below the nfet cluster.
SPINE_HINT_Y = {
    "GND": 13.50,
    "CLK": 38.30,
    "OUTP": 12.50,
    "OUTN": 11.50,
    "VDD": 22.50,
}

#: Body-tie structures.  ``inside_well`` picks which body the tie serves.
TAPS = {
    "GND": {"x0": 0.00, "x1": 0.60, "y0": 17.00, "y1": 23.00, "inside_well": False},
    "VDD": {"x0": 21.00, "x1": 21.60, "y0": 17.00, "y1": 23.00, "inside_well": True},
}

#: One n-well rectangle enclosing both pfet blocks' own local wells (merging
#: them into a single well) and extending right far enough to hold the well tie.
#: Kept clear of every nfet block: the rightmost nfet geometry ends at x ~ 12.0.
NWELL_BOX = {"x0": 13.90, "y0": 2.50, "x1": 24.00, "y1": 38.50}

#: y-track grid for met1 branches.
TRACK_Y0 = 1.50
TRACK_Y1 = 40.00


class RouteError(RuntimeError):
    """The greedy track router could not place a branch."""


class Rect:
    """An axis-aligned rectangle in integer nanometres."""

    __slots__ = ("x0", "y0", "x1", "y1")

    def __init__(self, x0: int, y0: int, x1: int, y1: int) -> None:
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1

    @classmethod
    def um(cls, x0: float, y0: float, x1: float, y1: float) -> "Rect":
        return cls(nm(x0), nm(y0), nm(x1), nm(y1))

    @classmethod
    def centred(cls, cx: float, cy: float, w: float, h: float) -> "Rect":
        return cls(nm(cx - w / 2), nm(cy - h / 2), nm(cx + w / 2), nm(cy + h / 2))

    def within(self, other: "Rect", clearance: int) -> bool:
        """True when ``self`` comes closer than ``clearance`` to ``other``."""
        return (
            self.x0 - clearance < other.x1
            and other.x0 < self.x1 + clearance
            and self.y0 - clearance < other.y1
            and other.y0 < self.y1 + clearance
        )

    def as_um(self) -> list[float]:
        return [self.x0 / DBU, self.y0 / DBU, self.x1 / DBU, self.y1 / DBU]


class Pin:
    """A block port this router has to reach, in composed coordinates."""

    def __init__(self, block: str, port: str, x: float, ylo: float, yhi: float) -> None:
        self.block = block
        self.port = port
        self.x = x
        self.ylo = ylo
        self.yhi = yhi

    @property
    def ymid(self) -> float:
        return (self.ylo + self.yhi) / 2

    def clamp(self, y: float) -> float:
        return min(max(y, self.ylo), self.yhi)

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"{self.block}.{self.port}@({self.x:.3f},{self.ylo:.3f}..{self.yhi:.3f})"


def load_ports(report_path: Path) -> tuple[dict[str, tuple[float, float, float]], dict]:
    """Read a `klt gen` report -> ``{port: (x, y, width)}`` plus its bbox."""
    report = json.loads(report_path.read_text())
    ports = {
        port["name"]: (port["x_um"], port["y_um"], port["width_um"], port["direction_deg"])
        for port in report["ports"]
    }
    return ports, report["bbox_um"]


def pin_from_port(
    block: str, port: str, port_info: tuple[float, float, float, float], dx: float, dy: float
) -> Pin:
    """Translate a block-local port into a composed-coordinate :class:`Pin`.

    A `klt gen` port reports its pad centre plus the pad's extent *perpendicular
    to the direction it faces*: a source/drain port (facing +/-x) reports its
    pad height, a gate port (facing +y) reports its pad width.  A gate pad is
    square (0.42 x 0.42 on every block this flow generates), so its usable y
    span is the same 0.42.
    """
    x_um, y_um, width_um, direction = port_info
    extent = width_um if direction in (0, 180) else 0.42
    half = extent / 2 - PAD_MARGIN_UM
    if half <= 0:
        raise RouteError(f"{block}.{port}: pad too small to land an mcon in")
    return Pin(block, port, x_um + dx, y_um + dy - half, y_um + dy + half)


def track_candidates(preferred: float) -> list[float]:
    """Every y-track, ordered by distance from ``preferred`` (ties: lower first)."""
    count = int(round((TRACK_Y1 - TRACK_Y0) / TRACK_PITCH_UM)) + 1
    tracks = [TRACK_Y0 + i * TRACK_PITCH_UM for i in range(count)]
    return sorted(tracks, key=lambda y: (abs(y - preferred), y))


class Router:
    """Greedy met1 track router over a fixed set of met2 trunks."""

    def __init__(self) -> None:
        self.met1: list[tuple[str, Rect]] = []
        self.mcons: list[Rect] = []
        self.shapes: list[tuple[tuple[int, int], Rect]] = []
        self.trunk_span: dict[tuple[str, float], tuple[float, float]] = {}
        self.labels: list[tuple[tuple[int, int], str, float, float]] = []
        # Per-net wiring, kept so the record can *measure* the differential
        # symmetry claim instead of merely asserting it.
        self.net_met1: dict[str, list[Rect]] = {}
        self.net_met2: dict[str, list[Rect]] = {}
        self.via_count: dict[str, int] = {}
        self.mcon_count: dict[str, int] = {}

    # -- conflict model -----------------------------------------------------
    def met1_free(self, net: str, rects: list[Rect]) -> bool:
        clearance = nm(MET1_SPACE_UM)
        for owner, placed in self.met1:
            if owner == net:
                continue
            for rect in rects:
                if rect.within(placed, clearance):
                    return False
        return True

    def mcon_free(self, rect: Rect) -> bool:
        clearance = nm(MCON_SPACE_UM)
        return not any(rect.within(placed, clearance) for placed in self.mcons)

    # -- emission -----------------------------------------------------------
    def add_met1(self, net: str, rects: list[Rect]) -> None:
        for rect in rects:
            self.met1.append((net, rect))
            self.shapes.append((L_MET1, rect))
            self.net_met1.setdefault(net, []).append(rect)

    def add_via(self, net: str, trunk_x: float, y: float) -> None:
        self.shapes.append((L_VIA, Rect.centred(trunk_x, y, VIA_UM, VIA_UM)))
        self.via_count[net] = self.via_count.get(net, 0) + 1
        key = (net, trunk_x)
        lo, hi = self.trunk_span.get(key, (y, y))
        self.trunk_span[key] = (min(lo, y), max(hi, y))

    def add_mcon(self, net: str, x: float, y: float) -> None:
        rect = Rect.centred(x, y, MCON_UM, MCON_UM)
        self.mcons.append(rect)
        self.shapes.append((L_MCON, rect))
        self.mcon_count[net] = self.mcon_count.get(net, 0) + 1

    # -- the router ---------------------------------------------------------
    def _branch_rects(self, pin_x: float, pin_y: float, trunk_x: float, track_y: float) -> list[Rect]:
        """met1 geometry for one branch: pad + vertical stub + horizontal run."""
        rects = [Rect.centred(pin_x, pin_y, PAD_UM, PAD_UM)]
        if abs(track_y - pin_y) > 1e-9:
            lo, hi = sorted((pin_y, track_y))
            rects.append(
                Rect.um(pin_x - WIRE_UM / 2, lo - WIRE_UM / 2, pin_x + WIRE_UM / 2, hi + WIRE_UM / 2)
            )
        lo, hi = sorted((pin_x, trunk_x))
        rects.append(
            Rect.um(lo - WIRE_UM / 2, track_y - WIRE_UM / 2, hi + WIRE_UM / 2, track_y + WIRE_UM / 2)
        )
        return rects

    def reserve_pad(self, net: str, pin: Pin) -> None:
        """Keep other nets' met1 out of a pin's own landing-pad footprint.

        Only worth doing (and only affordable) for a *gate* pin: its li1 pad is
        0.42 x 0.42, so its mcon -- and therefore the met1 pad that mcon must
        land in -- is pinned to a ~0.2 um y window it cannot escape.  Without
        this reservation the router happily runs an earlier net's horizontal
        branch straight through a later gate pin's only legal pad position and
        then has nowhere to put it (the cross-quad input pair puts two
        *different* gate nets at the same y in adjacent columns, so this is not
        a corner case here -- it is the normal situation).  A source/drain pin
        spans its device's full height and needs no such reservation.
        """
        half = PAD_UM / 2
        self.met1.append(
            (net, Rect.um(pin.x - half, pin.ylo - half, pin.x + half, pin.yhi + half))
        )

    def route_branch(
        self, net: str, pin: Pin, trunk_x: float, preferred_y: float | None = None
    ) -> float:
        """Route one pin to ``trunk_x``; returns the y-track used.

        ``preferred_y`` seeds the candidate ordering.  It defaults to the pin's
        own pad centre (shortest branch), and is overridden by the caller with a
        mirrored counterpart's track for the differential nets (see
        :data:`MIRROR_PIN`).  It is a *preference*, never a constraint: if the
        mirror track is occupied the search still walks outward from it, so a
        congested corner degrades the symmetry rather than failing the route.
        """
        for track_y in track_candidates(pin.ymid if preferred_y is None else preferred_y):
            pin_y = pin.clamp(track_y)
            mcon = Rect.centred(pin.x, pin_y, MCON_UM, MCON_UM)
            if not self.mcon_free(mcon):
                continue
            rects = self._branch_rects(pin.x, pin_y, trunk_x, track_y)
            if not self.met1_free(net, rects):
                continue
            self.add_mcon(net, pin.x, pin_y)
            self.add_met1(net, rects)
            self.add_via(net, trunk_x, track_y)
            return track_y
        raise RouteError(f"no free y-track for {net} pin {pin} -> trunk x={trunk_x}")

    def route_spine(self, net: str, xa: float, xb: float, preferred: float) -> float:
        """Join two of ``net``'s trunks with one horizontal met1 run."""
        lo, hi = sorted((xa, xb))
        for track_y in track_candidates(preferred):
            rect = Rect.um(
                lo - WIRE_UM / 2, track_y - WIRE_UM / 2, hi + WIRE_UM / 2, track_y + WIRE_UM / 2
            )
            if not self.met1_free(net, [rect]):
                continue
            self.add_met1(net, [rect])
            self.add_via(net, xa, track_y)
            self.add_via(net, xb, track_y)
            return track_y
        raise RouteError(f"no free y-track for {net} spine {xa} <-> {xb}")

    def finish_trunks(self) -> None:
        """Emit each net's met2 trunk, spanning every via it carries."""
        for (net, trunk_x), (lo, hi) in sorted(self.trunk_span.items()):
            rect = Rect.um(
                trunk_x - WIRE_UM / 2, lo - WIRE_UM / 2, trunk_x + WIRE_UM / 2, hi + WIRE_UM / 2
            )
            self.shapes.append((L_MET2, rect))
            self.net_met2.setdefault(net, []).append(rect)

    def summary(self) -> dict[str, dict[str, float | int]]:
        """Per-net wiring metrics -- what makes the symmetry claim falsifiable."""
        out: dict[str, dict[str, float | int]] = {}
        for net in sorted(set(self.net_met1) | set(self.net_met2)):
            met1 = union_area_um2(self.net_met1.get(net, []))
            met2 = union_area_um2(self.net_met2.get(net, []))
            out[net] = {
                "met1_area_um2": round(met1, 4),
                "met2_area_um2": round(met2, 4),
                "wire_area_um2": round(met1 + met2, 4),
                "via_count": self.via_count.get(net, 0),
                "mcon_count": self.mcon_count.get(net, 0),
            }
        return out


def union_area_um2(rects: list[Rect]) -> float:
    """Exact area of a union of axis-aligned rectangles, via coordinate
    compression.  Overlap is common here (a branch's pad, stub and horizontal
    run all share corners), and double-counting it would make the differential
    symmetry numbers meaningless."""
    if not rects:
        return 0.0
    xs = sorted({v for r in rects for v in (r.x0, r.x1)})
    ys = sorted({v for r in rects for v in (r.y0, r.y1)})
    total = 0
    for i in range(len(xs) - 1):
        x0, x1 = xs[i], xs[i + 1]
        for j in range(len(ys) - 1):
            y0, y1 = ys[j], ys[j + 1]
            if any(r.x0 <= x0 and x1 <= r.x1 and r.y0 <= y0 and y1 <= r.y1 for r in rects):
                total += (x1 - x0) * (y1 - y0)
    return total / (DBU * DBU)


def build_pins(reports_dir: Path) -> tuple[dict[tuple[str, str], Pin], dict[str, dict[str, float]]]:
    """Resolve every schematic pin to composed coordinates + the block origins."""
    origins: dict[str, dict[str, float]] = {}
    pins: dict[tuple[str, str], Pin] = {}
    for block, x_origin in BLOCK_X.items():
        ports, _bbox = load_ports(reports_dir / f"{block}.json")
        y_origin = Y_AXIS - BLOCK_Y_ANCHOR[block]
        origins[block] = {"x": x_origin, "y": y_origin}
        for port_name, info in ports.items():
            pins[(block, port_name)] = pin_from_port(
                block, port_name, info, x_origin, y_origin
            )
    return pins, origins


def tap_shapes(net: str, spec: dict) -> tuple[list[tuple[tuple[int, int], Rect]], Pin]:
    """Draw one body-tie structure; returns its shapes and its li1 landing pin."""
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
    pin = Pin(f"tap_{net}", "TIE", cx, y0 + PAD_MARGIN_UM, y1 - PAD_MARGIN_UM)
    return shapes, pin


def build(reports_dir: Path) -> tuple[dict, dict, dict]:
    """Return the (draw params, gen-compose request, route summary) triple."""
    pins, origins = build_pins(reports_dir)
    router = Router()

    # Body-tie structures + the merged n-well, drawn before routing so their
    # li1 pads exist as ordinary pins for the GND/VDD nets.
    static_shapes: list[tuple[tuple[int, int], Rect]] = [
        (L_NWELL, Rect.um(NWELL_BOX["x0"], NWELL_BOX["y0"], NWELL_BOX["x1"], NWELL_BOX["y1"]))
    ]
    tap_pins: dict[str, Pin] = {}
    for net in sorted(TAPS):
        shapes, pin = tap_shapes(net, TAPS[net])
        static_shapes.extend(shapes)
        tap_pins[net] = pin
    router.shapes.extend(static_shapes)

    for net in ROUTE_ORDER:
        for block, port in NET_PINS[net]:
            if port.endswith("_G"):
                router.reserve_pad(net, pins[(block, port)])

    tracks: dict[tuple[str, str], float] = {}
    for net in ROUTE_ORDER:
        trunks = TRUNK_X[net]
        keyed_pins: list[tuple[tuple[str, str] | None, Pin]] = [
            (key, pins[key]) for key in NET_PINS[net]
        ]
        if net in tap_pins:
            keyed_pins.append((None, tap_pins[net]))
        first_via: tuple[float, float] | None = None
        for key, pin in keyed_pins:
            trunk_x = min(trunks, key=lambda tx: (abs(tx - pin.x), tx))
            mirror = MIRROR_PIN.get(key) if key is not None else None
            sibling = SAME_TRACK_PIN.get(key) if key is not None else None
            preferred: float | None = None
            if mirror in tracks:
                preferred = 2 * Y_AXIS - tracks[mirror]
            elif sibling in tracks:
                preferred = tracks[sibling]
            track_y = router.route_branch(net, pin, trunk_x, preferred)
            if key is not None:
                tracks[key] = track_y
            if first_via is None:
                first_via = (trunk_x, track_y)
        if len(trunks) > 1:
            for xa, xb in zip(trunks, trunks[1:]):
                router.route_spine(net, xa, xb, SPINE_HINT_Y[net])
        if net in PIN_NETS:
            assert first_via is not None
            router.labels.append((L_MET1_PIN, net, first_via[0], first_via[1]))

    router.finish_trunks()

    draw_params = {
        "shapes": [
            {"layer": list(layer), "rect_um": rect.as_um()} for layer, rect in router.shapes
        ],
        "labels": [
            {"layer": list(layer), "text": text, "at_um": [x, y]}
            for layer, text, x, y in router.labels
        ],
    }

    order = list(BLOCK_X) + ["route"]
    compose_request = {
        "schema": "klt.gen_compose.request/1",
        "pdk": {"variant": "sky130A"},
        "blocks": [{"id": bid, "generator_report": f"{bid}.json"} for bid in BLOCK_X]
        + [{"id": "route", "generator_report": "draw.json"}],
        "placement": {
            "strategy": "explicit",
            "order": order,
            "origins_um": {**origins, "route": {"x": 0.0, "y": 0.0}},
        },
        # Deliberately no `routing` block: `klt gen-compose` is used here purely
        # as a placer.  Every wire is in the `route` block above.
        "connectivity": [],
    }

    per_net = router.summary()
    route_summary = {
        "y_axis_um": Y_AXIS,
        "block_origins_um": origins,
        "trunk_x_um": {net: list(xs) for net, xs in TRUNK_X.items()},
        "nets": per_net,
        "differential_symmetry": [
            _symmetry(per_net, "OUTP", "OUTN"),
            _symmetry(per_net, "VINN", "VINP"),
        ],
    }
    return draw_params, compose_request, route_summary


def _symmetry(per_net: dict, positive: str, negative: str) -> dict:
    """Wire-area imbalance between the two halves of a differential net pair.

    Reported, not asserted: the router treats the mirror track as a preference
    (see :meth:`Router.route_branch`), so a residual imbalance is a real, honest
    number rather than something to hide -- and it is the number a later
    parasitic-extraction pass on this sub-block has to improve on.
    """
    a = float(per_net.get(positive, {}).get("wire_area_um2", 0.0))
    b = float(per_net.get(negative, {}).get("wire_area_um2", 0.0))
    denominator = (a + b) / 2 or 1.0
    return {
        "pair": [positive, negative],
        "wire_area_um2": [a, b],
        "delta_um2": round(abs(a - b), 4),
        "delta_percent": round(100 * abs(a - b) / denominator, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "reports_dir", type=Path, help="directory holding the five <block>.json reports"
    )
    args = parser.parse_args()

    draw_params, compose_request, route_summary = build(args.reports_dir)
    (args.reports_dir / "draw.request.json").write_text(json.dumps(draw_params, indent=2) + "\n")
    (args.reports_dir / "compose.request.json").write_text(
        json.dumps(compose_request, indent=2) + "\n"
    )
    (args.reports_dir / "route.summary.json").write_text(
        json.dumps(route_summary, indent=2) + "\n"
    )
    print(
        f"build_layout.py: {len(draw_params['shapes'])} shapes, "
        f"{len(draw_params['labels'])} labels, {len(compose_request['blocks'])} blocks"
    )
    for entry in route_summary["differential_symmetry"]:
        print(
            f"build_layout.py: {entry['pair'][0]}/{entry['pair'][1]} wire area "
            f"{entry['wire_area_um2'][0]} / {entry['wire_area_um2'][1]} um^2 "
            f"({entry['delta_percent']}% imbalance)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generator for the differential CDAC array sub-block's physical layout
(issue #100), drawn against `design/cdac/cdac_unit_cell.sch` /
`design/cdac/cdac_array.sch` and device physics only (CLAUDE.md's clean-room
rule -- no other party's implementation is consulted or reconstructed).

Runs headlessly via `klayout.db` (`kdb`), the same engine `klt` itself uses,
plus subprocess calls to the pinned `klt gen mos_array` generator for the
two switch-device flavours (`layout/requirements.txt` pins the exact
version). Not a `klt` verb itself -- a repo-local script, matching this
issue's "committed generator script" acceptance criterion.

Emits two cells:

- `cdac_unit_cell` -- one bit position's storage element: one MiM unit
  capacitor + the single-control-line CMOS bottom-plate switch, matching
  `design/cdac/cdac_unit_cell.sch` device-for-device.
- `cdac_array` -- the full differential array: 1024 *physically identical*
  unit capacitors (512 per side) in a 32x32 common-centroid grid, the 18
  bottom-plate switches, and a VREFN-tied bottom-plate guard frame,
  matching `design/cdac/cdac_array.sch`.

`design/cdac/cdac_array.sch` expresses bit `i`'s weight as `MF=2**i` on a
single `cap_mim_m3_1` symbol; `design/cdac/README.md` is explicit that this
is *netlist-level shorthand for `2**i` parallel unit cells, not a claim
about physical placement*. This generator realizes that shorthand the way
the schematic's own README says it must be: every weight is that many
drawn, identical unit capacitors -- never one scaled plate. A single plate
of `w` times the unit area is not electrically equivalent either (the
sky130 MiM model, and `klt extract`'s deck, carry a perimeter term as well
as an area term, so one big plate is *not* `w` unit caps), and it is
matching-poor besides.

See `layout/cdac-array/README.md` for the floorplan/matching-strategy
writeup this module implements -- including what it deliberately does not
achieve -- and `layout/cdac-array/bin/run-flow.sh` for the DRC/extract/LVS
flow that verifies its output.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import klayout.db as kdb

# --------------------------------------------------------------------------- #
# sky130 layer table (klayout_tools.decks.sky130, klt==0.3.0 -- see
# layout/requirements.txt). (layer, datatype) pairs, verified against that
# module's own EXTRACTION_DECK/DECK contents.
# --------------------------------------------------------------------------- #
NWELL = (64, 20)
NWELL_PIN = (64, 5)
POLY = (66, 20)
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
CAPM = (89, 44)

DBU_UM = 0.001

# --------------------------------------------------------------------------- #
# Rule-derived sizing. Every number below clears the corresponding threshold
# in `klayout_tools.decks.sky130.DECK` (klt 0.3.0); the margins are
# deliberately generous, because this block's job is a verifiably clean
# result, not a minimum-area one. Relevant thresholds, for the record:
#   li1.width 0.17   li1.space 0.17
#   met1.width 0.14  met1.space 0.14   met1.enclosing.mcon 0.03
#   met1/met2.enclosing.via1 0.055     via1.width 0.15  via1.space 0.17
#   met2.width 0.14  met2.space 0.14   met2.enclosing.via2 0.04
#   met3.width 0.30  met3.space 0.30   met3.enclosing.via2 0.065
#   met3.enclosing.via3 0.06           met4.enclosing.via3 0.065
#   met4.width 0.30  met4.space 0.30   via2/via3.width 0.20  via2/via3.space 0.20
#   capm.width 1.00  capm.space 0.84   met3.enclosing.capm 0.14
#   capm.enclosing.via3 0.14           capm.separation.via3 0.14
#   mcon.space 0.19
# --------------------------------------------------------------------------- #
VIA_S = 0.20  # via2/via3 square side
VIA1_S = 0.15  # via1 square side
MCON_S = 0.17  # mcon square side
PAD_HALF = 0.16  # met1/met2 landing-pad half-side
WIRE_W = 0.30  # generic li1/met1/met2 wire width
MET4_W = 0.40  # met4 rail/bus width

# --------------------------------------------------------------------------- #
# The unit capacitor. `design/cdac/cdac_unit_cell.sch` sizes it
# W=L=1.8988 um (bare-number sky130_fd_pr convention) -> C_u ~= 8.654 fF per
# DR-003 Item 3. 1.8988 um is not on the 1 nm database grid, so the drawn
# top plate is the nearest grid-legal square, 1.898 um. `CAP_UNIT_F` is the
# capacitance that drawn plate has under the same area+perimeter formula
# `klt extract`'s sky130 deck applies (area_cap_f_um2=2.0e-15,
# perim_cap_f_um=1.9e-16, both transcribed by that deck from the PDK's own
# tt-corner camimc/cpmimc) -- derived here from the drawn geometry and the
# deck's published coefficients, never read back out of an extraction
# result, so the LVS reference generated from cdac_array.sch stays an
# independent statement about the schematic.
# --------------------------------------------------------------------------- #
CAPM_SIDE = 1.898
CAP_AREA_F_UM2 = 2.0e-15
CAP_PERIM_F_UM = 1.9e-16
CAP_UNIT_F = CAPM_SIDE**2 * CAP_AREA_F_UM2 + 4.0 * CAPM_SIDE * CAP_PERIM_F_UM

# Unit-cell footprint. The met3 bottom plate is taller than the capm top
# plate so the bottom-plate via2 lands on bare met3, clear of the MiM
# dielectric stack: capm sits in the plate's upper region, via2 in the lower
# strip. Every one of the 1024 array units is this exact shape -- identical
# plate, identical via positions, identical stub geometry -- which is the
# whole point of a unit-element array.
PLATE_W = 2.20  # met3 bottom plate width  (encloses capm by 0.151 >= 0.14)
PLATE_H = 2.90  # met3 bottom plate height
CAPM_DY = 0.35  # capm centre offset above the unit centre
VIA2_DY = -1.00  # bottom-plate via2 offset below the unit centre
STUB_DY = VIA2_DY  # the met1 stub runs at the via2 row

UNIT_PITCH_X = 3.40  # capm-to-capm 1.502 >= 0.84; met3-to-met3 1.20 >= 0.30
UNIT_PITCH_Y = 3.40  # capm-to-capm 1.502 >= 0.84; met3-to-met3 0.50 >= 0.30

#: 64 columns x 16 rows = 1024 units = 512 per side. The aspect ratio is a
#: *routing* choice, not an aesthetic one: with 16 rows a column holds 8
#: units per side, so the binary split lands on 32/16/8/4/2/1 columns for
#: bits 8..3 and one final column for the whole bit2+bit1+bit0+termination
#: remainder -- seven bottom-plate nets through the centre column. A squarer
#: 32x32 grid halves the column count but doubles the units per column, so
#: the remainder column has to carry *nine* nets on one column pitch, which
#: does not fit met2's 0.14 um spacing rule at any legal track pitch (caught
#: as 78 met2.space.1 violations, all inside that one column, on the first
#: DRC run of this generator -- see the PR description).
N_COL = 64
N_ROW = 16

# Switch-device sizing, per design/cdac/cdac_unit_cell.sch's own header:
# M1 (nfet, BOT->VREFN @ SEL=1): W=1, L=0.15. M2 (pfet, BOT->VREFP @ SEL=0):
# W=2, L=0.15 (both flavours share L, which the gate-tie strap relies on).
NFET_W_UM = 1.0
PFET_W_UM = 2.0
GATE_L_UM = 0.15


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #
def um(v: float) -> int:
    return int(round(v / DBU_UM))


class Canvas:
    """A `kdb.Cell` plus the layer-index cache and the handful of drawing
    primitives this generator needs."""

    def __init__(self, layout: kdb.Layout, cell: kdb.Cell) -> None:
        self.layout = layout
        self.cell = cell
        self._li: dict[tuple[int, int], int] = {}

    def _idx(self, layer: tuple[int, int]) -> int:
        if layer not in self._li:
            self._li[layer] = self.layout.layer(*layer)
        return self._li[layer]

    def rect(self, layer, x0: float, y0: float, x1: float, y1: float) -> None:
        self.cell.shapes(self._idx(layer)).insert(
            kdb.Box(um(x0), um(y0), um(x1), um(y1))
        )

    def square(self, layer, cx: float, cy: float, side: float) -> None:
        h = side / 2.0
        self.rect(layer, cx - h, cy - h, cx + h, cy + h)

    def label(self, layer, cx: float, cy: float, text: str) -> None:
        self.cell.shapes(self._idx(layer)).insert(kdb.Text(text, um(cx), um(cy)))

    def wire(self, layer, x0: float, y0: float, x1: float, y1: float, w: float = WIRE_W) -> None:
        """An axis-aligned wire of width `w` between two points (the ends are
        squared off half a width past each endpoint, so a wire meeting
        another at a corner overlaps it rather than mitring)."""
        h = w / 2.0
        if abs(x0 - x1) < 1e-9:
            self.rect(layer, x0 - h, min(y0, y1) - h, x0 + h, max(y0, y1) + h)
        elif abs(y0 - y1) < 1e-9:
            self.rect(layer, min(x0, x1) - h, y0 - h, max(x0, x1) + h, y0 + h)
        else:
            raise ValueError(f"wire must be axis-aligned: ({x0},{y0})-({x1},{y1})")

    # -- via stacks ------------------------------------------------------- #
    def via1(self, cx: float, cy: float) -> None:
        """met1 <-> met2, with a landing pad on both."""
        self.square(MET1, cx, cy, 2 * PAD_HALF)
        self.square(MET2, cx, cy, 2 * PAD_HALF)
        self.square(VIA1, cx, cy, VIA1_S)

    def via2(self, cx: float, cy: float) -> None:
        """met2 <-> met3, with a met2 landing pad (met3 is the caller's own
        plate or wire)."""
        self.square(MET2, cx, cy, 2 * PAD_HALF)
        self.square(VIA2, cx, cy, VIA_S)

    def mcon(self, cx: float, cy: float) -> None:
        """li1 <-> met1, with a landing pad on both."""
        self.square(LI1, cx, cy, 2 * PAD_HALF + 0.06)
        self.square(MET1, cx, cy, 2 * PAD_HALF)
        self.square(MCON, cx, cy, MCON_S)


# --------------------------------------------------------------------------- #
# The unit capacitor
# --------------------------------------------------------------------------- #
def draw_unit_cap(c: Canvas, cx: float, cy: float, *, capm: bool = True) -> None:
    """One unit capacitor at (cx, cy).

    `capm=False` draws the *guard* variant: the identical met3 bottom plate
    and via2 landing, with the MiM top plate omitted. That omission is what
    makes a guard plate a guard plate rather than a 1025th capacitor -- see
    README.md "Why the guard frame carries no capm".
    """
    c.rect(
        MET3,
        cx - PLATE_W / 2.0,
        cy - PLATE_H / 2.0,
        cx + PLATE_W / 2.0,
        cy + PLATE_H / 2.0,
    )
    if capm:
        c.square(CAPM, cx, cy + CAPM_DY, CAPM_SIDE)
        c.square(VIA3, cx, cy + CAPM_DY, VIA_S)
    c.via2(cx, cy + VIA2_DY)


def connect_bottom(c: Canvas, cx: float, cy: float, strap_x: float) -> None:
    """Wire one unit's bottom plate out to its net's vertical met2 strap.

    Uniform for every unit in the array: met3 plate -> via2 -> met2 pad ->
    via1 -> a *met1* horizontal stub -> via1 -> the met2 strap. The stub is
    on met1 rather than met2 precisely so it may cross any number of other
    nets' met2 straps on its way out of the column without shorting to
    them -- which is what lets the centre column carry nine independent
    bottom-plate nets on a single column pitch.
    """
    y = cy + STUB_DY
    c.via1(cx, y)
    if abs(strap_x - cx) > 1e-9:
        c.wire(MET1, cx, y, strap_x, y)
        c.via1(strap_x, y)


# --------------------------------------------------------------------------- #
# Switch-pair generation, via `klt gen mos_array` (pinned klt).
# --------------------------------------------------------------------------- #
def _klt_bin() -> Path:
    return Path(__file__).resolve().parents[2] / ".venv" / "bin" / "klt"


def _gen_mos_unit(flavor: str, w_um: float, l_um: float, tmpdir: Path):
    out_gds = tmpdir / f"{flavor}_unit.gds"
    params = json.dumps(
        {"rows": 1, "cols": 1, "dummy": 0, "flavor": flavor, "w_um": w_um, "l_um": l_um}
    )
    result = subprocess.run(
        [
            str(_klt_bin()), "gen", "mos_array",
            "--pdk", "sky130A",
            "--params", params,
            "--cell-name", f"{flavor}_unit",
            "-o", str(out_gds),
            "--format", "json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    resp = json.loads(result.stdout)
    ly = kdb.Layout()
    ly.read(str(out_gds))
    return ly, resp


class SwitchTemplate:
    """A cached nfet unit + pfet unit (device physics per
    `design/cdac/cdac_unit_cell.sch`: M1 nfet W=1 L=0.15, M2 pfet W=2
    L=0.15), generated once via `klt gen mos_array` and stamped repeatedly.
    """

    GAP_UM = 1.0  # vertical clearance between the nfet block and the pfet block

    def __init__(self, tmpdir: Path) -> None:
        self.nfet_ly, self.nfet_resp = _gen_mos_unit("nfet", NFET_W_UM, GATE_L_UM, tmpdir)
        self.pfet_ly, self.pfet_resp = _gen_mos_unit("pfet", PFET_W_UM, GATE_L_UM, tmpdir)
        self.nports = self._ports(self.nfet_resp)
        self.pports = self._ports(self.pfet_resp)
        nb = self.nfet_resp["bbox_um"]
        self.nfet_h = nb["y1"] - nb["y0"]

    @staticmethod
    def _ports(resp: dict) -> dict:
        return {p["name"].split("_")[-1]: p for p in resp["ports"]}

    def stamp(self, c: Canvas, origin_x: float, origin_y: float) -> dict:
        """Stamp one nfet (at `origin`) plus one pfet directly above it, tie
        their gates together with a poly strap, and return the absolute
        coordinates of every terminal a caller needs."""
        pfet_origin_y = origin_y + self.nfet_h + self.GAP_UM

        def _copy(src_ly: kdb.Layout, ox: float, oy: float) -> None:
            src_top = src_ly.top_cell()
            trans = kdb.Trans(um(ox), um(oy))
            for src_li in src_ly.layer_indexes():
                info = src_ly.get_info(src_li)
                dst_li = c.layout.layer(info)
                region = kdb.Region(src_top.begin_shapes_rec(src_li))
                region.transform(trans)
                c.cell.shapes(dst_li).insert(region)

        _copy(self.nfet_ly, origin_x, origin_y)
        _copy(self.pfet_ly, origin_x, pfet_origin_y)

        def _abs(port: dict, ox: float, oy: float) -> tuple[float, float]:
            return (port["x_um"] + ox, port["y_um"] + oy)

        nfet_s = _abs(self.nports["S"], origin_x, origin_y)
        nfet_d = _abs(self.nports["D"], origin_x, origin_y)
        nfet_g = _abs(self.nports["G"], origin_x, origin_y)
        pfet_s = _abs(self.pports["S"], origin_x, pfet_origin_y)
        pfet_d = _abs(self.pports["D"], origin_x, pfet_origin_y)
        pfet_g = _abs(self.pports["G"], origin_x, pfet_origin_y)

        # Tie the two gates (SEL): one poly strap bridging the two gate
        # landing pads (both bare poly -- `klt gen mos_array`'s own default
        # `gate_contact=False`). `l_um` is identical for both flavours, so
        # nfet_g[0] == pfet_g[0] exactly and the strap is purely vertical.
        # Its width is pinned to *exactly* the channel poly width, never
        # wider: the strap's straight-line path from one gate pad to the
        # other necessarily re-crosses each device's own channel poly, and a
        # wider strap would locally widen the merged poly there -- which
        # `klt extract`'s DeviceExtractorMOS4Transistor reads as the
        # device's own L, silently growing the extracted gate length past
        # what was requested. (Found empirically; see the PR description.)
        gate_x = (nfet_g[0] + pfet_g[0]) / 2.0
        half = GATE_L_UM / 2.0
        c.rect(POLY, gate_x - half, nfet_g[1], gate_x + half, pfet_g[1])

        return {
            "nfet_s": nfet_s,
            "nfet_d": nfet_d,
            "pfet_s": pfet_s,
            "pfet_d": pfet_d,
            "gate_x": gate_x,
            "gate_y": (nfet_g[1] + pfet_g[1]) / 2.0,
            # The *pfet's* own absolute Y range only -- never the whole
            # switch's nfet+pfet bbox. A shared VDD nwell scoped to the full
            # bbox would also cover the nfet's diffusion only `GAP_UM` away,
            # silently reclassifying every nfet as a pfet during extraction
            # (an nfet is *active outside nwell*), which shows up as
            # "0 nfet, 2x the expected pfet count" in `klt extract`'s
            # device_counts. Found empirically; see the PR description.
            "pfet_well_y0": pfet_origin_y + self.pfet_resp["bbox_um"]["y0"],
            "pfet_well_y1": pfet_origin_y + self.pfet_resp["bbox_um"]["y1"],
        }


# --------------------------------------------------------------------------- #
# The array floorplan. See layout/cdac-array/README.md for the matching
# strategy this section implements and its honest accounting.
# --------------------------------------------------------------------------- #

#: The two centre columns. `col 31` carries all of bit3 (8 units/side);
#: `col 32` carries the whole LSB remainder (bit2+bit1+bit0+termination =
#: 4+2+1+1 = 8 units/side), split by *row* instead of by column.
COL_BIT3 = 31
COL_LSB = 32


def half_sequence() -> list[int]:
    """Per-half column assignment, ordered by distance rank from the array's
    vertical centre line (`h=0` is the column nearest the centre, `h=30` the
    outermost). Entry `h` names the bit that owns that column *in both*
    halves, so every bit listed occupies a mirror-symmetric pair of columns
    about the centre and its X-centroid lands exactly on the centre.

    The assignment is the dyadic "ruler" interleave: the largest bit takes
    every other slot, the next takes every other *remaining* slot, and so
    on -- bit8 x16, bit7 x8, bit6 x4, bit5 x2, bit4 x1 per half (31 slots).
    Spreading each bit uniformly across the half, rather than clumping it,
    is what makes the arrangement robust to a *quadratic* (bowl-shaped)
    gradient as well as the linear one the mirror pair already cancels.
    """
    seq = [0] * 31
    remaining = list(range(31))
    for bit in (8, 7, 6, 5, 4):
        taken = remaining[0::2]
        for h in taken:
            seq[h] = bit
        remaining = remaining[1::2]
    assert not remaining and all(seq), seq
    return seq


#: LSB-column row-pair assignment, ordered by distance rank from the array's
#: horizontal centre line: pair `p` is the per-side row-slot pair
#: `(3 - p, 4 + p)`. The same dyadic interleave as the columns, one
#: dimension down. `("bit0", "term")` is the one unpaired entry -- bit0 and
#: the termination unit are both singletons, so they share a pair.
LSB_PAIR_SEQUENCE: list = [2, 1, 2, ("bit0", "term")]

STRAP_DX_PAIR = (-0.60, 0.60)  # P/N bottom-plate strap offsets, ordinary column
#: The centre column's seven strap offsets: three bottom-plate nets per side
#: plus one shared VREFN strap for the two termination units. Track pitch is
#: 0.55 um (met2 is 0.30 wide with a 0.16 half-width landing pad at each
#: unit's stub, so 0.55 leaves 0.24 clear -- comfortably over met2.space's
#: 0.14); every track clears the unit's own centre pad by >= 0.39 and the
#: neighbouring column's strap at -/+2.80 by >= 0.15.
STRAP_DX_LSB = (-2.30, -1.75, -1.20, -0.65, 0.65, 1.20, 1.75)
_LSB_STRAP_ORDER = [
    "VREFN",
    "BOT_p2", "BOT_p1", "BOT_p0",
    "BOT_n0", "BOT_n1", "BOT_n2",
]

GUARD_COLS = (-1, N_COL)
GUARD_ROWS = (-1, N_ROW)

BUS_Y0 = -8.0  # topmost horizontal met1 bus (VREFN)
BUS_PITCH = 0.5
BUS_X0 = -3.90  # buses span the guard frame's own width
BUS_X1 = N_COL * UNIT_PITCH_X + 0.60

TOP_BUS_P_X = -2.40  # met4 TOP_P collector bus (left margin)
TOP_BUS_N_X = N_COL * UNIT_PITCH_X - 0.80  # met4 TOP_N collector bus (right margin)
VREFN_RISER_X = -2.00  # met2 riser tying the VREFN met1 bus to the switch-row rail

SW_Y0 = -30.0  # nfet origin Y of the switch row
SW_PITCH = 11.0  # 18 switches spread across the array's own width
SW_X0 = 4.0
VREFN_RAIL_Y = -33.4  # met2, below the switch row
VREFP_RAIL_Y = -34.8  # met1, below that -- a different layer from VREFN's rail,
#                       so the two rails and the per-switch source risers may
#                       cross each other freely
NWELL_MARGIN = 0.28  # nwell overhang past the pfet block -- deliberately small,
#                      see `pfet_well_y0`'s note in SwitchTemplate.stamp


def unit_x(col: int) -> float:
    return col * UNIT_PITCH_X


def unit_y(row: int) -> float:
    return row * UNIT_PITCH_Y


def side_of_row(row: int) -> str:
    """Which sub-array (P or N) owns `row`.

    Rows alternate P/N so a Y gradient sees both sides equally; the parity
    *flips* at the array's horizontal midline so that P and N end up with
    exactly equal Y-centroids instead of being offset by one row pitch. See
    README.md "Differential interleave".
    """
    if row < N_ROW // 2:
        return "P" if row % 2 == 0 else "N"
    return "P" if row % 2 == 1 else "N"


def column_bits() -> dict[int, int]:
    """{column index: bit} for the 63 columns owned by one bit each. The
    centre LSB column (COL_LSB) is handled separately."""
    cols: dict[int, int] = {}
    left = list(range(COL_BIT3 - 1, -1, -1))  # 30, 29, ... 0  (h = 0..30)
    right = list(range(COL_LSB + 1, N_COL))  # 33, 34, ... 63 (h = 0..30)
    for h, bit in enumerate(half_sequence()):
        cols[left[h]] = bit
        cols[right[h]] = bit
    cols[COL_BIT3] = 3
    return cols


def lsb_slot_owners() -> dict[int, str]:
    """{per-side row slot 0..15: owning net key} for the centre LSB column.

    Slot `s` is the s-th row of this column belonging to a given side,
    counted bottom-up. Pairs are assigned outward from the array's
    horizontal centre line, so every LSB-group member is itself
    centre-symmetric in Y.
    """
    owners: dict[int, str] = {}
    half = N_ROW // 4  # per-side row slots in this column, halved
    for p, entry in enumerate(LSB_PAIR_SEQUENCE):
        lo, hi = half - 1 - p, half + p
        if isinstance(entry, tuple):
            owners[lo], owners[hi] = entry
        else:
            owners[lo] = owners[hi] = f"bit{entry}"
    return owners


def net_of_unit(col: int, row: int, col_bits: dict[int, int], lsb: dict[int, str]) -> str:
    """The bottom-plate net name of the unit at (col, row)."""
    side = side_of_row(row).lower()
    if col != COL_LSB:
        return f"BOT_{side}{col_bits[col]}"
    slot = sum(1 for r in range(row) if side_of_row(r) == side.upper())
    owner = lsb[slot]
    if owner == "term":
        return "VREFN"
    if owner == "bit0":
        return f"BOT_{side}0"
    return f"BOT_{side}{owner[3:]}"


def strap_x_of(col: int, net: str) -> float:
    """X of the vertical met2 strap carrying `net` through column `col`."""
    base = unit_x(col)
    if col != COL_LSB:
        return base + (STRAP_DX_PAIR[0] if net.startswith("BOT_p") else STRAP_DX_PAIR[1])
    return base + STRAP_DX_LSB[_LSB_STRAP_ORDER.index(net)]


def bus_order() -> list[str]:
    """Vertical order of the horizontal met1 buses under the array."""
    return ["VREFN"] + [f"BOT_p{i}" for i in range(9)] + [f"BOT_n{i}" for i in range(9)]


_BUS_ORDER = bus_order()


def bus_y_of(net: str) -> float:
    return BUS_Y0 - BUS_PITCH * _BUS_ORDER.index(net)


def build_array(layout: kdb.Layout, cell: kdb.Cell, tmpdir: Path) -> dict:
    c = Canvas(layout, cell)
    col_bits = column_bits()
    lsb = lsb_slot_owners()

    # --- 1. The 1024 unit capacitors + their bottom-plate straps ---------- #
    strap_top: dict[tuple[int, str], float] = {}
    unit_counts: dict[str, int] = {}
    for col in range(N_COL):
        for row in range(N_ROW):
            cx, cy = unit_x(col), unit_y(row)
            draw_unit_cap(c, cx, cy)
            net = net_of_unit(col, row, col_bits, lsb)
            unit_counts[net] = unit_counts.get(net, 0) + 1
            sx = strap_x_of(col, net)
            connect_bottom(c, cx, cy, sx)
            key = (col, net)
            strap_top[key] = max(strap_top.get(key, -1e9), cy + STUB_DY)

    for (col, net), y_hi in strap_top.items():
        sx = strap_x_of(col, net)
        c.wire(MET2, sx, bus_y_of(net), sx, y_hi)
        # Tie the strap into its own horizontal met1 bus. The bus is met1 and
        # the strap met2, so every *other* net's bus passes underneath this
        # strap without touching it.
        c.via1(sx, bus_y_of(net))

    # --- 2. Horizontal met1 buses ----------------------------------------- #
    for net in _BUS_ORDER:
        c.wire(MET1, BUS_X0, bus_y_of(net), BUS_X1, bus_y_of(net))

    # --- 3. Top-plate met4 rails (one per row) + the two collector buses -- #
    x_lo = unit_x(0) - 0.5
    x_hi = unit_x(N_COL - 1) + 0.5
    for row in range(N_ROW):
        y = unit_y(row) + CAPM_DY
        if side_of_row(row) == "P":
            c.wire(MET4, TOP_BUS_P_X, y, x_hi, y, w=MET4_W)
        else:
            c.wire(MET4, x_lo, y, TOP_BUS_N_X, y, w=MET4_W)
    y_first, y_last = unit_y(0) + CAPM_DY, unit_y(N_ROW - 1) + CAPM_DY
    c.wire(MET4, TOP_BUS_P_X, y_first, TOP_BUS_P_X, y_last, w=MET4_W)
    c.wire(MET4, TOP_BUS_N_X, y_first, TOP_BUS_N_X, y_last, w=MET4_W)
    c.label(MET4_PIN, TOP_BUS_P_X, unit_y(N_ROW // 2) + CAPM_DY, "TOP_P")
    c.label(MET4_PIN, TOP_BUS_N_X, unit_y(N_ROW // 2) + CAPM_DY, "TOP_N")

    # --- 4. The VREFN-tied guard frame ------------------------------------ #
    # One ring of guard plates: identical met3 bottom-plate geometry and via2
    # landing, no capm (see draw_unit_cap). Left/right/top edges are
    # collected on met2; the bottom edge on met1 -- it is the one edge whose
    # collector would otherwise have to cross all 64 column straps on their
    # own layer.
    for col in GUARD_COLS:
        for row in range(-1, N_ROW + 1):
            draw_unit_cap(c, unit_x(col), unit_y(row), capm=False)
    for row in GUARD_ROWS:
        for col in range(N_COL):
            draw_unit_cap(c, unit_x(col), unit_y(row), capm=False)

    guard_left_x = unit_x(GUARD_COLS[0])
    guard_right_x = unit_x(GUARD_COLS[1])
    guard_top_y = unit_y(N_ROW) + VIA2_DY
    guard_bot_y = unit_y(-1) + VIA2_DY
    for gx in (guard_left_x, guard_right_x):
        c.wire(MET2, gx, bus_y_of("VREFN"), gx, guard_top_y)
        c.via1(gx, bus_y_of("VREFN"))
    c.wire(MET2, guard_left_x, guard_top_y, guard_right_x, guard_top_y)
    c.wire(MET1, guard_left_x, guard_bot_y, guard_right_x, guard_bot_y)
    for col in list(range(N_COL)) + list(GUARD_COLS):
        c.via1(unit_x(col), guard_bot_y)

    # --- 5. The 18 bottom-plate switches ---------------------------------- #
    tmpl = SwitchTemplate(tmpdir)
    switch_nets = [f"BOT_p{i}" for i in range(9)] + [f"BOT_n{i}" for i in range(9)]
    well_y0 = well_y1 = None
    for index, net in enumerate(switch_nets):
        ox = SW_X0 + index * SW_PITCH
        sw = tmpl.stamp(c, ox, SW_Y0)
        sel = ("SELp" if net.startswith("BOT_p") else "SELn") + net[-1]
        c.label(POLY_PIN, sw["gate_x"], sw["gate_y"], sel)

        # BOT: nfet drain <-> pfet drain <-> this bit's met1 bus, all on one
        # li1 riser. li1 crosses every met1 bus it passes on the way up
        # without touching it; only the mcon at this net's own bus lands.
        dx = sw["nfet_d"][0]
        c.wire(LI1, dx, sw["nfet_d"][1], dx, bus_y_of(net))
        c.mcon(dx, bus_y_of(net))

        # VREFN: nfet source -> met1 jog -> met2 riser -> the met2 rail.
        nsx, nsy = sw["nfet_s"]
        c.mcon(nsx, nsy)
        c.wire(MET1, nsx, nsy, ox - 0.40, nsy)
        c.via1(ox - 0.40, nsy)
        c.wire(MET2, ox - 0.40, nsy, ox - 0.40, VREFN_RAIL_Y)

        # VREFP: pfet source -> met1 jog -> met1 riser -> the met1 rail.
        # Deliberately a *different layer* from the VREFN riser above, so the
        # two rails can sit at two different Y without either riser having to
        # cross the other rail on its own layer.
        psx, psy = sw["pfet_s"]
        c.mcon(psx, psy)
        c.wire(MET1, psx, psy, ox - 0.90, psy)
        c.wire(MET1, ox - 0.90, psy, ox - 0.90, VREFP_RAIL_Y)

        well_y0 = sw["pfet_well_y0"] if well_y0 is None else min(well_y0, sw["pfet_well_y0"])
        well_y1 = sw["pfet_well_y1"] if well_y1 is None else max(well_y1, sw["pfet_well_y1"])

    # The VREFN met2 rail must start far enough left to *merge* with the
    # VREFN riser rather than stop just short of it (a 0.05 um gap there is
    # a met2.space.1 violation, not a connection).
    sw_x_lo = VREFN_RISER_X - 0.5
    sw_x_hi = SW_X0 + (len(switch_nets) - 1) * SW_PITCH + 1.8
    c.wire(MET2, sw_x_lo, VREFN_RAIL_Y, sw_x_hi, VREFN_RAIL_Y, w=0.40)
    c.wire(MET1, sw_x_lo, VREFP_RAIL_Y, sw_x_hi, VREFP_RAIL_Y, w=0.40)
    c.label(MET2_PIN, sw_x_lo + 0.5, VREFN_RAIL_Y, "VREFN")
    c.label(MET1_PIN, sw_x_lo + 0.5, VREFP_RAIL_Y, "VREFP")

    # VREFN riser: the met1 bus in the bus band (which the termination units
    # and the guard frame tie to) down to the met2 rail at the switch row.
    c.wire(MET2, VREFN_RISER_X, bus_y_of("VREFN"), VREFN_RISER_X, VREFN_RAIL_Y)
    c.via1(VREFN_RISER_X, bus_y_of("VREFN"))

    # VDD: one nwell rectangle over the pfet row only.
    c.rect(NWELL, sw_x_lo - 0.6, well_y0 - NWELL_MARGIN, sw_x_hi + 0.6, well_y1 + NWELL_MARGIN)
    c.label(NWELL_PIN, sw_x_lo, (well_y0 + well_y1) / 2.0, "VDD")

    return {
        "unit_counts": unit_counts,
        "n_units": sum(unit_counts.values()),
        "cap_unit_f": CAP_UNIT_F,
        "centroids": centroids(),
    }


def centroids() -> dict:
    """Per-net unit-capacitor centroids, in um, relative to the array's own
    geometric centre.

    This is the *measurable* content of the common-centroid claim, computed
    from the same placement functions the geometry is drawn from, and
    asserted by `render-record.py` so a future edit that quietly breaks the
    symmetry fails the flow instead of passing DRC/LVS unnoticed. See
    README.md for what each residual means.
    """
    col_bits = column_bits()
    lsb = lsb_slot_owners()
    cx0 = (unit_x(0) + unit_x(N_COL - 1)) / 2.0
    cy0 = (unit_y(0) + unit_y(N_ROW - 1)) / 2.0
    acc: dict[str, list[float]] = {}
    for col in range(N_COL):
        for row in range(N_ROW):
            net = net_of_unit(col, row, col_bits, lsb)
            if net == "VREFN":
                # The two termination units belong to one net but to
                # different sides; report them separately.
                net = "term_p" if side_of_row(row) == "P" else "term_n"
            entry = acc.setdefault(net, [0.0, 0.0, 0.0])
            entry[0] += unit_x(col)
            entry[1] += unit_y(row)
            entry[2] += 1
    return {
        net: {
            "n": int(n),
            "dx_um": round(sx / n - cx0, 6),
            "dy_um": round(sy / n - cy0, 6),
        }
        for net, (sx, sy, n) in acc.items()
    }


def build_unit_cell(layout: kdb.Layout, cell: kdb.Cell, tmpdir: Path) -> dict:
    """One bit position's storage element, matching
    `design/cdac/cdac_unit_cell.sch` device-for-device: one weight-1 MiM unit
    cap plus the single-control-line CMOS bottom-plate switch."""
    c = Canvas(layout, cell)
    tmpl = SwitchTemplate(tmpdir)

    cap_x, cap_y = 0.0, 0.0
    draw_unit_cap(c, cap_x, cap_y)
    c.wire(MET4, cap_x, cap_y + CAPM_DY, cap_x + 3.0, cap_y + CAPM_DY, w=MET4_W)
    c.label(MET4_PIN, cap_x + 3.0, cap_y + CAPM_DY, "TOP")

    ox, oy = 5.0, -10.0
    sw = tmpl.stamp(c, ox, oy)
    c.label(POLY_PIN, sw["gate_x"], sw["gate_y"], "SEL")

    # BOT: cap bottom plate -> met2 strap -> met1 stub -> li1 drain riser.
    bot_y = cap_y + VIA2_DY
    strap_x = cap_x
    join_y = oy - 3.0
    c.wire(MET2, strap_x, bot_y, strap_x, join_y)
    c.via1(strap_x, join_y)
    dx = sw["nfet_d"][0]
    c.wire(MET1, strap_x, join_y, dx, join_y)
    c.mcon(dx, join_y)
    # One li1 riser ties BOT to *both* drains: the nfet and the pfet share an
    # X (the pfet is the same generated cell shifted in Y), so a single
    # vertical li1 strap spanning from the join row up past the pfet's drain
    # pad touches both. The join row is *below* the nfet, so the strap must
    # reach all the way up to the pfet -- stopping at the nfet leaves the
    # pfet floating (caught as one `device.unmatched` pfet plus one dangling
    # layout net on this cell's first LVS run).
    c.wire(LI1, dx, join_y, dx, sw["pfet_d"][1])
    c.label(MET1_PIN, (strap_x + dx) / 2.0, join_y, "BOT")

    # VREFN / VREFP: a labelled met1 stub off each source pad.
    nsx, nsy = sw["nfet_s"]
    c.mcon(nsx, nsy)
    c.wire(MET1, nsx, nsy, ox - 1.4, nsy)
    c.label(MET1_PIN, ox - 1.4, nsy, "VREFN")
    psx, psy = sw["pfet_s"]
    c.mcon(psx, psy)
    c.wire(MET1, psx, psy, ox - 2.4, psy)
    c.label(MET1_PIN, ox - 2.4, psy, "VREFP")

    c.rect(
        NWELL,
        ox - 1.0,
        sw["pfet_well_y0"] - NWELL_MARGIN,
        ox + 2.2,
        sw["pfet_well_y1"] + NWELL_MARGIN,
    )
    c.label(NWELL_PIN, ox + 1.6, (sw["pfet_well_y0"] + sw["pfet_well_y1"]) / 2.0, "VDD")
    return {"cap_unit_f": CAP_UNIT_F}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-cell-out", type=Path, help="write cdac_unit_cell GDS here")
    parser.add_argument("--array-out", type=Path, help="write cdac_array GDS here")
    parser.add_argument("--summary-out", type=Path, help="write a JSON build summary here")
    args = parser.parse_args()

    if not args.unit_cell_out and not args.array_out:
        parser.error("pass at least one of --unit-cell-out / --array-out")

    summary: dict = {"cap_unit_f": CAP_UNIT_F}
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        if args.unit_cell_out:
            ly = kdb.Layout()
            ly.dbu = DBU_UM
            cell = ly.create_cell("cdac_unit_cell")
            summary["unit_cell"] = build_unit_cell(ly, cell, tmpdir)
            ly.write(str(args.unit_cell_out))
            print(f"wrote {args.unit_cell_out}")
        if args.array_out:
            ly = kdb.Layout()
            ly.dbu = DBU_UM
            cell = ly.create_cell("cdac_array")
            summary["array"] = build_array(ly, cell, tmpdir)
            ly.write(str(args.array_out))
            print(f"wrote {args.array_out}")
    if args.summary_out:
        args.summary_out.write_text(json.dumps(summary, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

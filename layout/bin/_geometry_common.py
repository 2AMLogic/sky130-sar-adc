"""Shared low-level geometry primitive for the layout sub-block
`build_layout.py` scripts.

Used by `layout/comparator/bin/build_layout.py`,
`layout/sampling-frontend-wells/bin/build_layout.py`, and
`layout/sampling-frontend/bin/build_layout.py`, which import this module via
a `sys.path` insert (see either script's own header) rather than a package
install, matching this directory's existing `_record_common.py` /
`_flow_common.sh` shared-module convention.

Houses the byte-identical shell all sub-blocks hand-rolled: the nanometre
database unit, the micrometres -> nanometres converter, and the `Rect` base
class's shared members (`__slots__`, `__init__`, `um()`, `centred()`,
`as_um()`, `hwire()`, `vwire()`) -- the wiring helpers `hwire()`/`vwire()`
are shared by `sampling-frontend-wells` and `sampling-frontend`, which both
build met1/met2 wires and landing pads the same way (this module's own
`WIRE_UM` only supplies their default width; each consumer keeps its own
module-level `WIRE_UM`, byte-identical to this one, for its other uses).
`within()` for the comparator's greedy track router remains a genuine,
sub-block-specific extension and stays defined on that sub-block's own
`Rect` subclass, not here.

Also houses the tap/well-tie structure all three consumers draw the same
way: `tap_shapes()` (the shared shape-construction core -- tap+li1 rects
plus a licon1 column, at the `L_TAP`/`L_LICON`/`L_LI1`/`LICON_PITCH_UM`
layers/pitch defined here), and the `sampling-frontend`/
`sampling-frontend-wells` pair's own `_assert_well_isolation()` and
`_assert_column_pitch()` build-time invariant checks (byte-identical between
those two consumers; `comparator` does not use either check). Each consumer
still owns its own `tap_shapes()` *wrapper*: `comparator`'s returns a `Pin`,
the other two return `(shapes, cx, cy)` -- see `tap_shapes()`'s own
docstring below for why the shared core stays shape-only.

Since issue #495 it also houses the metal-stack layer table and
`step_down_to_met1()` -- the "walk any generator port down to met1 before
routing it" via-stack emitter `layout/sampling-frontend/bin/build_layout.py`
worked out empirically (three layer cases, each with a DRC finding behind
it) and `layout/halflsb-offset/bin/build_layout.py` needs verbatim, because
both compose `klt gen cap_array` MiM units (met3 bottom-plate / met4
top-plate ports) alongside `klt gen mos_array` devices (li1 S/G/D ports).
The two copies are deliberately NOT yet folded into one: that function's
output is the *drawn geometry* behind `layout/sampling-frontend/`'s
committed DRC-clean / LVS-match record, and this repo's records are
append-only, so re-pointing that flow at this copy is work that belongs with
that flow's next re-run rather than with a sibling block's first one (the
same staging `_pfet_devices.py`'s own header documents for issues
#245--#248). What keeps the duplication honest meanwhile is mechanical, not
a comment: `sim/tests/test_geometry_common_shared_helpers.py` drives both
copies over every layer case and asserts the emitted shape lists are
identical, so a divergence is a test failure and the eventual fold-in is a
provable no-op.
"""
from __future__ import annotations

DBU = 1000  # nm per um

# Default `hwire()`/`vwire()` width -- met1/met2 wire + landing-pad width
# (m1.1/m2.1 minimum 0.14). Each consumer (`sampling-frontend-wells`,
# `sampling-frontend`) also keeps its own module-level `WIRE_UM` constant,
# byte-identical to this one, for its other uses elsewhere in that module
# (`Rect.centred()` calls, spacing minimums); this copy only fixes the
# `hwire()`/`vwire()` default so those two stay in lockstep.
WIRE_UM = 0.30


def nm(value_um: float) -> int:
    """Micrometres -> integer nanometres (the layout database unit)."""
    return int(round(value_um * DBU))


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

    def as_um(self) -> list[float]:
        return [self.x0 / DBU, self.y0 / DBU, self.x1 / DBU, self.y1 / DBU]

    @classmethod
    def hwire(cls, xa: float, xb: float, y: float, width: float = WIRE_UM) -> "Rect":
        lo, hi = (xa, xb) if xa <= xb else (xb, xa)
        return cls.um(lo - width / 2, y - width / 2, hi + width / 2, y + width / 2)

    @classmethod
    def vwire(cls, x: float, ya: float, yb: float, width: float = WIRE_UM) -> "Rect":
        lo, hi = (ya, yb) if ya <= yb else (yb, ya)
        return cls.um(x - width / 2, lo - width / 2, x + width / 2, hi + width / 2)


# --- tap/well-tie structure: layers + pitch, shared by all three consumers ---
L_TAP = (65, 44)
L_LICON = (66, 44)
L_LI1 = (67, 20)
LICON_PITCH_UM = 0.60

# --- metal stack: layers + cut/pad sizing, for `step_down_to_met1()` ---------
# sky130A GDS numbers, as klt's own curated deck names them. Each consumer that
# also uses these layers for its OWN wiring keeps its own module-level copy of
# the names it needs (`layout/sampling-frontend/bin/build_layout.py` does),
# byte-identical to these, exactly the way `WIRE_UM` above is already carried
# twice -- this copy only fixes what the shared step-down emitter draws.
L_MCON = (67, 44)
L_MET1 = (68, 20)
L_VIA1 = (68, 44)
L_MET2 = (69, 20)
L_VIA2 = (69, 44)
L_MET3 = (70, 20)
L_VIA3 = (70, 44)
L_MET4 = (71, 20)

MCON_UM = 0.17
VIA1_UM = 0.15  # via1 square side (via1.width min 0.15), proven DRC-clean
# against met1/met2.enclosing.via.1's 0.055um threshold with a 0.30um pad.
VIA23_UM = 0.20  # via2/via3 square side (via2/via3.width min 0.20 -- a
# DIFFERENT, larger minimum than via1's 0.15; found directly building
# `layout/sampling-frontend/`, as via2.width.1 violations at 0.15).
STACK_PAD_UM = 0.42  # landing pad for a stacked via cut (the same pad size
# `klt gen`'s own gate_contact uses), so a 0.20um via2/via3 lands with
# >= 0.11um enclosure on every side.
MET3_ISLAND_PAD_UM = 0.50  # a met3 pad that is the ONLY met3 shape at its own
# (x, y) has to satisfy sky130A's met3 MINIMUM-AREA rule (`m3.6`, 0.240um^2)
# on its own; a STACK_PAD_UM square is 0.1764um^2, below it and invisible to
# `klt drc`'s curated deck (issue #326). 0.50^2 = 0.25um^2 clears it.
MET3_VIA_INSET_UM = 0.20  # a `cap_array` *_BOT port's reported x sits right AT
# the bottom plate's own edge, so landing a via2 there pokes past met3's
# boundary and fails met3.enclosing.via2. Step the landing this far INTO the
# plate instead.


def tap_shapes(spec: dict, licon_um: float) -> list[tuple[tuple[int, int], "Rect"]]:
    """Shared core of one tap/well-tie structure: tap+li1 strip, licon1 column.

    ``spec`` gives the drawn rectangle's ``x0``/``x1``/``y0``/``y1`` (um);
    ``licon_um`` is the licon1 square side each consumer already sizes
    locally (their own module-level ``LICON_UM``, unchanged by this
    extraction -- it is not one of the layer/pitch constants above, since a
    future consumer could reasonably size its own licon1 cuts differently).

    Returns the shape list only -- deliberately not a `(shapes, cx, cy)` or
    `(shapes, Pin)` tuple, because the three consumers disagree on what else
    to return: `layout/comparator/bin/build_layout.py`'s own `tap_shapes()`
    wrapper builds a `Pin` from these shapes plus `spec`, while
    `layout/sampling-frontend/bin/build_layout.py` and
    `layout/sampling-frontend-wells/bin/build_layout.py`'s wrappers each
    return `(shapes, cx, cy)` floats instead. Each wrapper computes its own
    return contract from `spec` (which already carries `x0`/`x1`/`y0`/`y1`)
    rather than this shared core guessing which flavour to produce.
    """
    x0, x1, y0, y1 = spec["x0"], spec["x1"], spec["y0"], spec["y1"]
    shapes: list[tuple[tuple[int, int], "Rect"]] = [
        (L_TAP, Rect.um(x0, y0, x1, y1)),
        (L_LI1, Rect.um(x0, y0, x1, y1)),
    ]
    cx = (x0 + x1) / 2
    y = y0 + LICON_PITCH_UM / 2
    while y + LICON_PITCH_UM / 2 <= y1 + 1e-9:
        shapes.append((L_LICON, Rect.centred(cx, y, licon_um, licon_um)))
        y += LICON_PITCH_UM
    return shapes


class BuildError(RuntimeError):
    """A `build_layout.py` script's own build-time invariant was violated.

    Shared by `layout/sampling-frontend/bin/build_layout.py`,
    `layout/sampling-frontend-wells/bin/build_layout.py` (both raised this
    same, byte-identical exception class locally before this extraction) and
    `layout/halflsb-offset/bin/build_layout.py`;
    `layout/comparator/bin/build_layout.py` does not use it. Defined above
    `step_down_to_met1()`, which raises it.
    """


def step_down_to_met1(
    shapes: list[tuple[tuple[int, int], "Rect"]],
    x: float,
    y: float,
    layer: tuple[int, int],
    direction: float,
    met4_escape_y: float | None = None,
) -> tuple[float, float]:
    """Emit whatever via stack reaches met1 from ``layer``, and return the
    **effective** (x, y) the caller should treat as the pin's location from
    here on (usually the input point unchanged; see the ``L_MET3`` and
    ``L_MET4`` cases).

    Why every pin -- not just an li1 one -- ends up on met1: a net's met2
    track is one long horizontal rectangle spanning every column x that net
    touches. If a *different* net's riser also rode on met2 below its own
    track (which every cap-originated pin would, absent this rule, since it
    starts on met2 already), it would physically cross every lower-numbered
    net's met2 track at whatever x it shares with them -- an unconditional
    short between two unrelated nets, on the very layer that carries the whole
    track scheme. Met1 has no such hazard: it carries nothing but per-pin
    columns, so any column may freely underpass any net's met2 track.

    Extracted verbatim (issue #495) from
    `layout/sampling-frontend/bin/build_layout.py`'s own
    `_step_down_to_met1`, which is still the live copy that flow's committed
    record was drawn with -- see this module's header for why both exist and
    for the test that holds them identical.
    """
    if layer == L_LI1:
        shapes.append((L_MCON, Rect.centred(x, y, MCON_UM, MCON_UM)))
        return x, y
    if layer == L_MET3:
        # A `cap_array` *_BOT port reports its position AT the bottom plate's
        # own edge (direction 180 => the plate's left edge is x=0 in the
        # block's local frame) -- landing a via2 exactly there would poke past
        # met3's own boundary. Shift the via into the plate (direction 180
        # faces -x, so "into the plate" is +x) by MET3_VIA_INSET_UM; the thin
        # met3 strip between the reported edge and the via is already part of
        # the same bottom-plate conductor, so no extra wire bridges it.
        if direction == 180.0:
            x = x + MET3_VIA_INSET_UM
        shapes.append((L_MET2, Rect.centred(x, y, STACK_PAD_UM, STACK_PAD_UM)))
        shapes.append((L_VIA2, Rect.centred(x, y, VIA23_UM, VIA23_UM)))
        # The FINAL met1 pad, unlike the via2/via3 landing pads above, only has
        # to enclose via1 (0.15um) -- WIRE_UM (0.30) already clears that with
        # margin, and matching it to the jog wire's own width avoids a corner
        # notch a wider STACK_PAD_UM pad would leave between itself and the
        # (narrower) hwire/riser, which read back as met1.space.1 when first
        # built that way.
        shapes.append((L_MET1, Rect.centred(x, y, WIRE_UM, WIRE_UM)))
        shapes.append((L_VIA1, Rect.centred(x, y, VIA1_UM, VIA1_UM)))
        return x, y
    if layer == L_MET4:
        # A `cap_array` *_TOP port's own via3 + local met3 landing sit DIRECTLY
        # ABOVE the bottom plate's own met3 sheet, which -- being a PLATE --
        # covers the unit's ENTIRE footprint. Adding a second via3/met3 pad at
        # the port's own (x, y) lands squarely inside that sheet and SHORTS the
        # two plates together (measured while building
        # `layout/sampling-frontend/`: `klt extract` reported the top- and
        # bottom-plate nets merged into one). There is no offset inside the
        # cell's footprint where a new met3 shape is safe.
        #
        # Fix: ride MET4 (which the bottom plate never touches) straight up and
        # OUT of the cell's footprint first -- `met4_escape_y`, past the unit's
        # own bbox top, supplied by the caller -- and only step down to
        # met3/met2/met1 once clear of it.
        if met4_escape_y is None:
            raise BuildError("L_MET4 port requires met4_escape_y")
        shapes.append((L_MET4, Rect.vwire(x, y, met4_escape_y)))
        # An explicit landing pad at the escape point: the vertical wire alone
        # only encloses via3 in x, not y (it ends exactly AT met4_escape_y, so
        # via3's own half-width above that point would poke past the wire's own
        # end -- a met4.enclosing.via3.1 violation found directly).
        shapes.append((L_MET4, Rect.centred(x, met4_escape_y, STACK_PAD_UM, STACK_PAD_UM)))
        y = met4_escape_y
        # This met3 pad is the whole met3 shape at this point -- via3 lands on
        # it from above, via2 leaves it from below, no met3 wire touches it --
        # so it satisfies m3.6 on its own: MET3_ISLAND_PAD_UM, not
        # STACK_PAD_UM (issue #326).
        shapes.append((L_MET3, Rect.centred(x, y, MET3_ISLAND_PAD_UM, MET3_ISLAND_PAD_UM)))
        shapes.append((L_VIA3, Rect.centred(x, y, VIA23_UM, VIA23_UM)))
        shapes.append((L_MET2, Rect.centred(x, y, STACK_PAD_UM, STACK_PAD_UM)))
        shapes.append((L_VIA2, Rect.centred(x, y, VIA23_UM, VIA23_UM)))
        shapes.append((L_MET1, Rect.centred(x, y, WIRE_UM, WIRE_UM)))
        shapes.append((L_VIA1, Rect.centred(x, y, VIA1_UM, VIA1_UM)))
        return x, y
    raise BuildError(f"no met1 step-down rule for layer {layer!r}")


def _assert_well_isolation(domains: list[dict], well_gap_um: float) -> None:
    """Every pair of adjacent n-well islands must clear ``nwell.2a`` with margin.

    Checked here as well as by `klt drc --deck sky130` (nwell.space.1, as of
    klt 0.4.0) on the finished GDS: a build-time failure names the offending
    pair, a DRC failure only names a coordinate.
    """
    for a, b in zip(domains, domains[1:]):
        gap = b["well"]["x0"] - a["well"]["x1"]
        if gap < well_gap_um - 1e-9:
            raise BuildError(
                f"n-well islands {a['id']!r} and {b['id']!r} are {gap:.3f} um "
                f"apart, below the drawn separation {well_gap_um} um"
            )


def _assert_column_pitch(columns: dict[float, str], minimum: float) -> None:
    """No two met1 columns may come closer than a wire width + met1 spacing.

    The floorplan constants make this true, but a device-size change (a wider
    W, a longer L) moves the landing pads and could silently break it -- so
    it is re-derived from the *actual* generated port geometry on every
    build rather than asserted once in a comment.
    """
    xs = sorted(columns)
    for xa, xb in zip(xs, xs[1:]):
        if xb - xa < minimum - 1e-9:
            raise BuildError(
                f"met1 columns for nets {columns[xa]!r} (x={xa:.3f}) and "
                f"{columns[xb]!r} (x={xb:.3f}) are {xb - xa:.3f} um apart, "
                f"below the {minimum:.2f} um wire+space pitch"
            )

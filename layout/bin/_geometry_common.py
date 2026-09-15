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

    Shared by `layout/sampling-frontend/bin/build_layout.py` and
    `layout/sampling-frontend-wells/bin/build_layout.py` (both raised this
    same, byte-identical exception class locally before this extraction);
    `layout/comparator/bin/build_layout.py` does not use it.
    """


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

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

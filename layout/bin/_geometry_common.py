"""Shared low-level geometry primitive for the layout sub-block
`build_layout.py` scripts.

Used by `layout/comparator/bin/build_layout.py` and
`layout/sampling-frontend-wells/bin/build_layout.py`, which import this
module via a `sys.path` insert (see either script's own header) rather than a
package install, matching this directory's existing `_record_common.py` /
`_flow_common.sh` shared-module convention.

Houses only the byte-identical shell both sub-blocks hand-rolled: the
nanometre database unit, the micrometres -> nanometres converter, and the
`Rect` base class's shared members (`__slots__`, `__init__`, `um()`,
`centred()`, `as_um()`). Each sub-block's own extra `Rect` method --
`within()` for the comparator's greedy track router, `hwire()`/`vwire()` for
the sampling-frontend-wells' well-tie wiring -- is a genuine, sub-block-
specific extension and stays defined on that sub-block's own `Rect` subclass,
not here.
"""
from __future__ import annotations

DBU = 1000  # nm per um


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

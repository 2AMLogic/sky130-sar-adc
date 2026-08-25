#!/usr/bin/env python3
"""Workaround for a `klt extract --pdk` sky130 unit-convention bug
(issue #112) -- rewrite `L`/`W`/`AS`/`AD`/`PS`/`PD` device-geometry fields
in a `klt extract --parasitics --pdk sky130A`-written netlist from explicit
SPICE unit-suffixed literals (e.g. ``L=0.5U``, ``AS=0.84P``) to bare micron
numbers (``L=0.5``, ``AS=0.84``).

Why this is needed (verified empirically, single-device minimal repro):
sky130's vendor model deck (``.lib ... tt`` -> ``corners/all.spice``) sets
``.option scale=1.0u`` and documents its own convention explicitly: *"The
scale option forces all netlists to provide distance units in microns (e.g.,
1 micron width is W=1, not W=1u)"*. `sky130_fd_pr__nfet_01v8`/`pfet_01v8`'s
own internal NRD/NRS *default*-value formula (used whenever a caller does
not supply `nrd`/`nrs` explicitly, which `klt extract`'s PDK-bound X-cards
never do) assumes its `pd`/`ps`/`ad`/`as` inputs are bare micron numbers
under that convention. `klt extract --pdk`'s SPICE writer instead emits
explicit-unit-suffixed values (`AS=0.84P`, `PS=4.84U`, ...) -- syntactically
valid, unit-correct SPICE on their own, but NOT the bare-micron convention
this specific PDK subcircuit's internal default formula expects. Feeding it
the unit-suffixed form makes the computed default NRD/NRS come out ~1e6x too
large (observed: `nrd=7.00000e+04` for a device whose intended NRD is
~0.07), and ngspice refuses the whole device with a generic "could not find
a valid modelname" -- the same symptom class docs/cli/sim.md's
`model_bin_range` diagnostic describes for a different root cause on a
different PDK, so it is easy to misdiagnose as a device-sizing problem
instead of a units convention mismatch.

sim/comparator-decision/testbench/comparator_core.spice's own hand/xschem
device cards already use the bare-micron convention (`ad=2.32 as=2.32
pd=16.58 ps=16.58`, no unit suffixes) -- this script makes a `klt
extract`-written netlist match that same convention, mechanically and
value-preservingly (every value is parsed and re-emitted as the identical
physical quantity, just without the now-redundant explicit suffix).

Filed generically per CLAUDE.md's friction protocol at
2AMLogic/klayout-tools (no design-specific detail) -- see
layout/comparator/pex/README.md for the issue link. This script is a local
workaround, not a permanent fixture: once the upstream binding is fixed to
either (a) write bare-micron literals for sky130, or (b) supply
`nrd`/`nrs`/`nf`/`mult`/`m` explicitly (sidestepping the model's own
default-value formula entirely, the way `klt`'s own generic `nfet`/`pfet`
M-card writer already does for `nrd`-bearing decks), this script becomes
unnecessary and this whole workaround can be deleted.

Usage:
    python3 normalize_extracted_units.py <in.spice> <out.spice>
"""

from __future__ import annotations

import re
import sys

# SPICE unit-suffix multipliers (case-insensitive on the input; "MEG" is the
# one multi-letter suffix and must be checked before the single-letter "M").
_UNIT_MULT = {
    "T": 1e12,
    "G": 1e9,
    "MEG": 1e6,
    "K": 1e3,
    "M": 1e-3,
    "U": 1e-6,
    "N": 1e-9,
    "P": 1e-12,
    "F": 1e-15,
}

# Fields sky130's `.option scale=1.0u` convention treats as bare-micron
# geometry: L/W are lengths (um), PS/PD are perimeters (um), AS/AD are areas
# (um^2) -- klt extract's own convention for these six field names,
# verified against layout/comparator/reports/*/comparator.extract.spice's
# non-parasitic sibling output.
_LENGTH_FIELDS = {"L", "W", "PS", "PD"}
_AREA_FIELDS = {"AS", "AD"}
_GEOM_FIELDS = _LENGTH_FIELDS | _AREA_FIELDS

_FIELD_RE = re.compile(
    r"\b(" + "|".join(_GEOM_FIELDS) + r")=([0-9.eE+\-]+)([A-Za-z]*)"
)


def _to_si(number: str, unit: str) -> float:
    val = float(number)
    if not unit:
        return val
    mult = _UNIT_MULT.get(unit.upper())
    if mult is None:
        raise ValueError(f"unrecognized SPICE unit suffix {unit!r} in {number}{unit}")
    return val * mult


def normalize_line(line: str) -> str:
    def repl(m: re.Match[str]) -> str:
        field, number, unit = m.group(1), m.group(2), m.group(3)
        si_value = _to_si(number, unit)
        if field in _LENGTH_FIELDS:
            bare_um = si_value * 1e6
        else:  # area field: m^2 -> um^2
            bare_um = si_value * 1e12
        return f"{field}={bare_um:.6g}"

    return _FIELD_RE.sub(repl, line)


def normalize_text(text: str) -> str:
    return "\n".join(normalize_line(line) for line in text.splitlines()) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} <in.spice> <out.spice>", file=sys.stderr)
        return 2
    src, dst = argv[1], argv[2]
    with open(src, encoding="utf-8") as f:
        text = f.read()
    with open(dst, "w", encoding="utf-8") as f:
        f.write(normalize_text(text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

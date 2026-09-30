#!/usr/bin/env python3
"""Assert that `layout/halflsb-offset/bin/gen_blocks.py`'s device table -- the
thing this block's geometry is actually built from -- is device-for-device,
terminal-for-terminal, net-for-net identical to `design/sar_adc_top.spice`'s own
top-level `XChoff_*` / `XMoff_*` cards.

**Why a generated LVS reference does not make this redundant.** This block's
`bin/generate-lvs-reference.py` derives the reference from the schematic, so the
reference side is anchored. The *layout* side is not: `bin/gen_blocks.py`'s
`SWITCH_NETS` / `CAP_LEGS` are hand-transcribed, and a transcription error there
produces a layout that disagrees with the reference in a way `klt lvs` usually
does catch -- but "usually" is doing real work in that sentence, and this block
has a measured counter-example:

    `klt lvs` reports a clean **match** against a reference whose
    `HALF_LSB_EN` / `HALF_LSB_ENN` gate connections are swapped.

`NetlistComparer` matches nets structurally, not by name, and both enables enter
this network only as ports -- so swapping them is an isomorphism, and DR-009's
load-bearing enable polarity ("gating on `BUSY` alone would ... inject a
corner-dependent fraction of `0.5 LSB` instead of `0.5 LSB`") is invisible to
the LVS verdict. It is visible in that run's own net-correspondence table, which
`bin/render-record.py` grades, and it is visible here. Both of those are
deliberate: this is issue #387's lesson ("a generated-reference LVS flow agrees
with itself") reproduced, measured, on a new block.

The independent anchor is the schematic netlist. `bin/_schematic_cards.py` reads
it -- and decides ownership from the SCHEMATIC side, so an eleventh top-level
primitive appearing in `design/sar_adc_top.spice` fails this check rather than
quietly belonging to no layout at all (see that module's docstring).

What is checked
---------------
1. Every owned card has exactly one counterpart in the layout table, and vice
   versa (census drift, both directions).
2. Per device: drawn flavour, `W`, `L`, and every terminal net -- `D`/`G`/`S`/`B`
   for a MOSFET, bottom/top plate for a MiM cap (against `CAP_LEGS`' declared
   plate assignment, since a `cap_mim_m3_1` card is terminal-symmetric).
3. `m` / `MF` is 1 on every card: this block draws exactly one device per card,
   so a schematic that multiplies one is not implemented by this geometry.
4. The block's declared net list (`gen_blocks.PORT_NETS`) is exactly the set of
   nets the cards name.
5. The drawn MiM plate side (`gen_blocks.CAP_DRAWN_UM`) agrees with
   `layout/cdac-array/bin/cdac_layout.py`'s own `CAPM_SIDE`, read out of that
   file's text -- DR-009 sizes this cap "identical to the CDAC unit cell's
   `C_u`", and the thing that must be identical is the drawn plate. Read as text
   rather than imported because that module imports `klayout.db`, which is not
   available in CI's headless job.
6. The drawn plate side is within one database unit of the schematic's own
   `W`/`L`, so "we draw the grid-legal neighbour of the requested plate" cannot
   quietly become "we draw a different capacitor".

Usage:
    layout/halflsb-offset/bin/check-schematic-parity.py
    layout/halflsb-offset/bin/check-schematic-parity.py --spice <path>

Exit status: 0 if the two agree exactly, 1 on any difference (with every
difference printed, not just the first).

**Runs headless** -- pure text reads, no PDK, no `klt`, no `layout/.venv`. Wired
into `npm run check:ci` as `check:halflsb-parity` for the same reason
`layout/top-glue/`'s equivalent is: the drift this catches is invisible to every
verdict this repo records, and two weeks of clean runs is what that invisibility
already cost once.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BLOCK_DIR = Path(__file__).resolve().parent.parent
LAYOUT_DIR = BLOCK_DIR.parent
REPO_ROOT = LAYOUT_DIR.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(LAYOUT_DIR / "bin"))

from _schematic_cards import FOREIGN_INSTANCES, owned_cards  # noqa: E402
from gen_blocks import (  # noqa: E402
    CAP_DRAWN_UM,
    CAP_LEGS,
    CAP_SCHEMATIC_UM,
    PORT_NETS,
    SWITCH_DEVICES,
)

PROG = "check-schematic-parity.py"
DEFAULT_SPICE = REPO_ROOT / "design" / "sar_adc_top.spice"

#: The sibling whose unit-cap plate side this block's must equal, and the
#: constant to read out of it.
CDAC_LAYOUT = LAYOUT_DIR / "cdac-array" / "bin" / "cdac_layout.py"
CDAC_PLATE_CONST = "CAPM_SIDE"

#: The database unit, in um. Check 6's tolerance: the drawn plate must be the
#: schematic plate rounded to this grid, nothing looser.
DBU_UM = 0.001


def layout_devices() -> dict[str, dict]:
    """`{schematic name: {...}}` for everything `bin/gen_blocks.py` draws.

    One normalized shape for both flavours: `flavour`, `w_um`, `l_um` and a
    `terminals` dict. A MiM cap has no W/L on the layout side in the schematic's
    units -- what it has is a drawn plate side -- so its `w_um`/`l_um` are
    `CAP_SCHEMATIC_UM`, the value this block asserts (check 6) its drawn plate
    is the grid-legal neighbour of.
    """
    devices: dict[str, dict] = {}
    for _bid, name, _side, flavour, w_um, l_um, d, g, s, b in SWITCH_DEVICES:
        devices[name] = {
            "flavour": flavour,
            "w_um": w_um,
            "l_um": l_um,
            "terminals": {"d": d, "g": g, "s": s, "b": b},
        }
    for _unit, name, _side, top_net, bot_net in CAP_LEGS:
        devices[name] = {
            "flavour": "cap_mim",
            "w_um": CAP_SCHEMATIC_UM,
            "l_um": CAP_SCHEMATIC_UM,
            "terminals": {"p1": bot_net, "p2": top_net},
        }
    return devices


def _schematic_name(card_name: str) -> str:
    """`XMoff_n_cmn` -> `Moff_n_cmn`.

    xschem prefixes every subcircuit-model instance card with `X`; the drawn
    name this repo uses everywhere else (`gen_blocks.SWITCH_DEVICES`,
    `CAP_LEGS`, DR-009's own prose) is the card name without it.
    """
    return card_name[1:] if card_name[:1].upper() == "X" else card_name


def _read_cdac_plate_side() -> float | None:
    """`layout/cdac-array/bin/cdac_layout.py`'s `CAPM_SIDE`, or None if the
    assignment is no longer in the shape this parse recognises (reported as a
    problem by the caller rather than silently skipped)."""
    if not CDAC_LAYOUT.is_file():
        return None
    for raw in CDAC_LAYOUT.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith(f"{CDAC_PLATE_CONST} ") and "=" in line:
            try:
                return float(line.split("=", 1)[1].split("#", 1)[0].strip())
            except ValueError:
                return None
    return None


def compare(spice_path: Path) -> tuple[list[str], dict]:
    """`(problems, census)` -- every difference found, and what was compared."""
    cards, foreign = owned_cards(spice_path, PROG)
    want = {_schematic_name(card.name): card for card in cards}
    got = layout_devices()
    problems: list[str] = []

    for name in sorted(set(want) - set(got)):
        problems.append(
            f"MISSING from the layout table: {name} ({want[name].model}) is in "
            f"the schematic but nothing under layout/halflsb-offset/ draws it"
        )
    for name in sorted(set(got) - set(want)):
        problems.append(
            f"EXTRA in the layout table (not in the schematic): {name} "
            f"({got[name]['flavour']})"
        )

    for name in sorted(set(want) & set(got)):
        card, drawn = want[name], got[name]
        if card.flavour != drawn["flavour"]:
            problems.append(
                f"{name}: drawn flavour {drawn['flavour']!r} != schematic "
                f"{card.flavour!r} ({card.model})"
            )
            continue
        for key, drawn_value in (("W", drawn["w_um"]), ("L", drawn["l_um"])):
            schematic_value = card.number(key)
            if abs(schematic_value - drawn_value) > 1e-9:
                problems.append(
                    f"{name}: drawn {key}={drawn_value} != schematic "
                    f"{key}={schematic_value}"
                )
        for multiplier in ("m", "MF"):
            if multiplier in card.params and abs(card.number(multiplier) - 1.0) > 1e-9:
                problems.append(
                    f"{name}: schematic card declares {multiplier}="
                    f"{card.params[multiplier]}, but this block draws exactly one "
                    f"device per card -- a multiplied device needs that many drawn "
                    f"units (see layout/cdac-array/ for the MF>1 pattern)"
                )
        for terminal, drawn_net in drawn["terminals"].items():
            schematic_net = card.terminal(terminal)
            if schematic_net != drawn_net:
                problems.append(
                    f"{name}.{terminal}: drawn net {drawn_net!r} != schematic net "
                    f"{schematic_net!r}"
                )

    schematic_nets = {net for card in cards for net in card.nets}
    for net in sorted(schematic_nets - set(PORT_NETS)):
        problems.append(
            f"net {net!r} is named by the schematic's own cards but is absent "
            f"from gen_blocks.PORT_NETS -- nothing draws a conductor for it"
        )
    for net in sorted(set(PORT_NETS) - schematic_nets):
        problems.append(
            f"net {net!r} is in gen_blocks.PORT_NETS but no schematic card names "
            f"it -- the layout draws a conductor the schematic does not have"
        )

    cdac_side = _read_cdac_plate_side()
    if cdac_side is None:
        problems.append(
            f"could not read {CDAC_PLATE_CONST} out of "
            f"{CDAC_LAYOUT.relative_to(REPO_ROOT)} -- DR-009 sizes this block's "
            f"offset cap identical to the CDAC unit cap, and that equality has to "
            f"stay machine-checked; fix this parse rather than dropping the check"
        )
    elif abs(cdac_side - CAP_DRAWN_UM) > 1e-9:
        problems.append(
            f"drawn MiM plate side {CAP_DRAWN_UM} um != "
            f"{CDAC_LAYOUT.relative_to(REPO_ROOT)}'s {CDAC_PLATE_CONST} "
            f"{cdac_side} um -- DR-009 requires this cap to be identical to the "
            f"CDAC unit cap, and the half-LSB step is a RATIO against one array "
            f"bit, so a plate-side difference is a ratio error"
        )

    if abs(CAP_DRAWN_UM - CAP_SCHEMATIC_UM) > DBU_UM + 1e-12:
        problems.append(
            f"drawn MiM plate side {CAP_DRAWN_UM} um is more than one database "
            f"unit ({DBU_UM} um) from the schematic's {CAP_SCHEMATIC_UM} um -- "
            f"the drawn plate is meant to be the grid-legal neighbour of the "
            f"requested one, not a different capacitor"
        )

    census: dict = {
        "devices": len(want),
        "flavours": sorted({card.flavour for card in cards}),
        "per_flavour": {
            flavour: sum(1 for card in cards if card.flavour == flavour)
            for flavour in sorted({card.flavour for card in cards})
        },
        "nets": len(PORT_NETS),
        "foreign": {card.name: FOREIGN_INSTANCES[card.name] for card in foreign},
        "cdac_plate_side_um": cdac_side,
    }
    return problems, census


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spice", type=Path, default=DEFAULT_SPICE)
    args = parser.parse_args()

    problems, census = compare(args.spice)
    rel_spice = os.path.relpath(args.spice, REPO_ROOT)

    if problems:
        print(
            f"{PROG}: FAIL -- layout/halflsb-offset/bin/gen_blocks.py does not "
            f"match {rel_spice}'s own top-level XChoff_*/XMoff_* cards:",
            file=sys.stderr,
        )
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print(
        f"{PROG}: OK -- {census['devices']} instances, "
        f"{len(census['flavours'])} device types, {census['nets']} nets, every "
        f"terminal net identical to {rel_spice}"
    )
    for flavour in census["flavours"]:
        print(f"  {flavour}: {census['per_flavour'][flavour]}")
    print(
        f"  drawn MiM plate side {CAP_DRAWN_UM} um == "
        f"{CDAC_LAYOUT.relative_to(REPO_ROOT)}'s {CDAC_PLATE_CONST}"
    )
    for name, owner in sorted(census["foreign"].items()):
        print(f"  not this block's: {name} -> {owner}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

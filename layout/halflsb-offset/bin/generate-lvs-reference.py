#!/usr/bin/env python3
"""Generate the flat, transistor-level LVS reference for DR-009's half-LSB
offset network (issue #495), derived from `design/sar_adc_top.spice`'s own
`XChoff_*` / `XMoff_*` cards.

Nothing here is authored. The topology, the device flavours and the W/L come
from the schematic netlist via `bin/_schematic_cards.py`; the device classes
are generalized to `klt extract --deck sky130`'s own flat vocabulary
(`nfet`/`pfet`/`sky130_fd_pr__model__cap_mim`), the same rewrite
`layout/cdac-array/bin/generate-lvs-reference.py` and
`layout/sampling-frontend/reference.spice` both make and for the same reason:
the layout side can only ever report the generic class.

The ONE place the reference legitimately departs from the card
-------------------------------------------------------------
A `cap_mim_m3_1` card carries `W=1.8988 L=1.8988`; the drawn plate is 1.898 um
(1898 nm -- 1898.8 is not on the 1 nm database grid, and 1.898 is the value
`layout/cdac-array/` already draws for the very unit cap DR-009 says this cap
is identical to). An LVS reference has to state the capacitance of the plate
that is *drawn*, so this script emits `gen_blocks.CAP_UNIT_F` --
`camimc*W*L + cpmimc*2*(W+L)` on the DRAWN side, using the extraction deck's
own published tt-corner coefficients. It is derived from geometry and
coefficients, never read back out of an extraction result, so the reference
stays an independent statement.

That departure is exactly why `bin/check-schematic-parity.py` exists and is a
separate gate: it holds the drawn plate side to the schematic's own value AND
to `layout/cdac-array/bin/cdac_layout.py`'s `CAPM_SIDE`, so "the reference
states the drawn plate's capacitance" cannot drift into "the reference states
whatever the layout happens to draw".

Negative controls
-----------------
`--variant` emits a deliberately-corrupted reference `klt lvs` must report as a
MISMATCH -- the falsifiability discipline `layout/trivial-cell/` established
for this repo (issue #2), specialised to the failure modes THIS network can
actually suffer:

* `broken-device` -- one PFET's W halved. A comparison that ignored device
  parameters would still match.
* `broken-topology` -- `Choff_n`'s top plate moved from `TOP_N` to `TOP_P`, the
  MiM top-plate-net corruption class `layout/sampling-frontend/` met for real
  when a cap top plate extracted as an isolated net.
* `swapped-enable` -- `HALF_LSB_EN` and `HALF_LSB_ENN` swapped on the working
  side's gates, i.e. DR-009's load-bearing enable polarity inverted. **`klt
  lvs` reports this one as a `match`, and that is the finding, not a bug in the
  control.** Both enables enter this network only as ports and
  `NetlistComparer` matches nets structurally rather than by name, so swapping
  them is a legitimate isomorphism: the comparer simply reports
  `HALF_LSB_EN <-> HALF_LSB_ENN` in its own net-correspondence table and calls
  it a match. The corruption IS visible in the same JSON envelope -- in that
  table, not in `status` -- which is why `bin/render-record.py` asserts
  name-identical net correspondence as a verdict of its own, and why the
  schematic-parity gate is load-bearing here rather than belt-and-braces. See
  `../README.md`, "What `klt lvs` cannot see on this block".

Usage:
    layout/halflsb-offset/bin/generate-lvs-reference.py OUT.spice
    layout/halflsb-offset/bin/generate-lvs-reference.py OUT.spice --variant broken-device

Requires no PDK and no `klt`: pure text in, pure text out.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BLOCK_DIR = Path(__file__).resolve().parent.parent
LAYOUT_DIR = BLOCK_DIR.parent
REPO_ROOT = LAYOUT_DIR.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(LAYOUT_DIR / "bin"))

from _schematic_cards import owned_cards  # noqa: E402
from gen_blocks import (  # noqa: E402
    BLOCK_NAME,
    CAP_AREA_F_UM2,
    CAP_DRAWN_UM,
    CAP_PERIM_F_UM,
    CAP_SCHEMATIC_UM,
    CAP_UNIT_F,
    PORT_NETS,
)

PROG = "generate-lvs-reference.py"
DEFAULT_SPICE = REPO_ROOT / "design" / "sar_adc_top.spice"

#: The reference subcircuit's name and its port order -- `gen_blocks`' own,
#: so the layout, the reference and the parity gate cannot disagree about
#: either. Twelve ports: the ten nets a higher level of hierarchy connects to,
#: then the two internal bottom plates, which `bin/build_layout.py` also labels
#: (see its `PIN_NETS` note for why an internal net gets a drawn label).
SUBCKT_NAME = BLOCK_NAME
TOP_PORTS = PORT_NETS

VARIANTS = ("good", "broken-device", "broken-topology", "swapped-enable")


def _device_name(card_name: str) -> str:
    """`XMoff_n_cmn` -> `M_MOFF_N_CMN`, `XChoff_n` -> `C_CHOFF_N`.

    The `M_`/`C_` prefix + upper-case spelling is this repo's own reference
    convention (`layout/sampling-frontend/reference.spice`); `klt lvs` compares
    topology rather than names, so the names exist for the record's own
    net-correspondence table to be readable.
    """
    bare = card_name[1:] if card_name[:1].upper() == "X" else card_name
    prefix = "C_" if bare[:1].upper() == "C" else "M_"
    return prefix + bare.upper()


def _rows(spice_path: Path, variant: str) -> list[tuple[str, str, str]]:
    """`(device name, card text, side)` for every device, with ``variant``'s
    corruption applied. ``side`` is `"n"` or `"p"`, read structurally from
    which of `BOT_OFF_N`/`BOT_OFF_P` the card touches -- never from the
    instance name, so a renamed device still lands in the right group.

    Corruptions are applied HERE, to the schematic-derived rows, rather than by
    editing a committed file: a negative control that is generated the same way
    the positive one is differs from it in exactly one stated respect, which is
    what makes it a control instead of a second opinion.
    """
    cards, _foreign = owned_cards(spice_path, PROG)
    mos = [card for card in cards if card.flavour in ("nfet", "pfet")]
    caps = [card for card in cards if card.flavour == "cap_mim"]

    rows: list[tuple[str, str, str]] = []
    for index, card in enumerate(mos):
        d, g, s, b = (card.terminal(t) for t in ("d", "g", "s", "b"))
        w_um, l_um = card.number("W"), card.number("L")
        if variant == "broken-device" and index == 0:
            w_um = w_um / 2
        if variant == "swapped-enable":
            g = {"HALF_LSB_EN": "HALF_LSB_ENN", "HALF_LSB_ENN": "HALF_LSB_EN"}.get(g, g)
        name = _device_name(card.name)
        rows.append(
            (
                name,
                f"{name:<14s} {d:<11s} {g:<13s} {s:<6s} {b:<6s} "
                f"{card.flavour} L={l_um}U W={w_um}U",
                _side_of(card),
            )
        )
    for card in caps:
        bottom, top = card.terminal("p1"), card.terminal("p2")
        side = _side_of(card)
        if variant == "broken-topology" and side == "n":
            top = "TOP_P"
        name = _device_name(card.name)
        rows.append(
            (
                name,
                f"{name:<14s} {bottom:<11s} {top:<13s} "
                f"{CAP_UNIT_F:.9e} sky130_fd_pr__model__cap_mim",
                side,
            )
        )
    return rows


def _side_of(card) -> str:
    """`"n"` or `"p"`, from the bottom-plate node the card touches."""
    return "n" if "BOT_OFF_N" in card.nets else "p"


def _header(spice_path: Path, variant: str) -> list[str]:
    try:
        rel: Path | str = spice_path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        # A netlist outside the repo -- only the tests do that, deliberately
        # (an injected-defect copy in a temp dir). Name it in full.
        rel = spice_path
    lines = [
        f"* {SUBCKT_NAME}.lvs-reference.spice -- GENERATED, do not edit by hand.",
        "*",
        "* Regenerate with:",
        f"*   layout/halflsb-offset/bin/generate-lvs-reference.py OUT.spice"
        + (f" --variant {variant}" if variant != "good" else ""),
        "*",
        f"* Source of truth: {rel}'s own top-level XChoff_*/XMoff_* cards --",
        "* DR-009 item 2's half-LSB quantizer offset (the _n side) plus its",
        "* matching dummy (the _p side, every gate tied off). Device flavours,",
        "* W and L are transcribed from those cards; device classes are",
        "* generalized to klt extract --deck sky130's own flat vocabulary",
        "* (nfet/pfet/sky130_fd_pr__model__cap_mim), which is the only",
        "* vocabulary the layout side can report.",
        "*",
        "* THE CAPACITANCE IS THE DRAWN PLATE'S, NOT THE CARD'S W/L.",
        f"* The cards ask for W = L = {CAP_SCHEMATIC_UM} um; that is "
        f"{CAP_SCHEMATIC_UM * 1000:.1f} nm,",
        "* off the 1 nm database grid. The drawn plate is "
        f"{CAP_DRAWN_UM} um -- the same",
        "* value layout/cdac-array/bin/cdac_layout.py draws for the unit cap",
        "* DR-009 says this one is identical to. The value below is that drawn",
        f"* plate under the extraction deck's own published tt coefficients",
        f"* (area {CAP_AREA_F_UM2:.1e} F/um^2, perimeter {CAP_PERIM_F_UM:.1e} F/um):",
        f"*   C = {CAP_AREA_F_UM2:.1e}*{CAP_DRAWN_UM}^2 + "
        f"4*{CAP_DRAWN_UM}*{CAP_PERIM_F_UM:.1e} = {CAP_UNIT_F:.9e} F",
        "* Derived from geometry and coefficients, never read back out of an",
        "* extraction result. bin/check-schematic-parity.py is what holds the",
        "* drawn plate side to both the schematic value and the cdac-array",
        "* sibling, so this departure cannot widen on its own.",
        "*",
        "* Bottom plate first (P1), top plate second (P2) -- the order",
        "* klt extract reports a MiM cap's terminals in (a = met3 bottom,",
        "* b = capm top) and the order bin/gen_blocks.py's CAP_LEGS declares.",
        "*",
        "* Clean room: every device and every net below is this repo's own",
        "* schematic, and the extraction coefficients are the pinned sky130A",
        "* PDK's own -- nothing is transcribed from any third-party layout.",
    ]
    if variant != "good":
        lines += [
            "*",
            f"* *** NEGATIVE CONTROL: {variant} ***",
            "* Deliberately WRONG. klt lvs must report this as a MISMATCH; a",
            "* match means the comparison is not looking at what this variant",
            "* corrupts. See this script's docstring for the defect class.",
        ]
    return lines


def _fold_ports(ports: tuple[str, ...]) -> list[str]:
    """`.SUBCKT` line(s), continued with `+` before column 80."""
    lines: list[str] = []
    current = f".SUBCKT {SUBCKT_NAME}"
    for port in ports:
        if len(current) + 1 + len(port) > 78:
            lines.append(current)
            current = "+"
        current += f" {port}"
    lines.append(current)
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_path", type=Path, help="reference netlist to write")
    parser.add_argument("--spice", type=Path, default=DEFAULT_SPICE)
    parser.add_argument("--variant", choices=VARIANTS, default="good")
    args = parser.parse_args()

    rows = _rows(args.spice, args.variant)
    lines = _header(args.spice, args.variant)
    lines += _fold_ports(TOP_PORTS)
    lines.append(
        "* --- the working side (_n): one unit cap switched VREFP -> VCM ------------"
    )
    for _name, text, side in rows:
        if side == "n":
            lines.append(text)
    lines.append(
        "* --- the matching dummy (_p): identical devices, every gate tied off ------"
    )
    for _name, text, side in rows:
        if side == "p":
            lines.append(text)
    lines.append(f".ENDS {SUBCKT_NAME}")

    args.out_path.parent.mkdir(parents=True, exist_ok=True)
    args.out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"{PROG}: wrote {args.out_path} -- variant {args.variant}, "
        f"{len(rows)} devices, {len(TOP_PORTS)} ports"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

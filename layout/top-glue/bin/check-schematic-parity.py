#!/usr/bin/env python3
"""Assert that `layout/top-glue/netlist/top_glue.v` is instance-for-instance,
pin-for-pin, net-for-net identical to `design/sar_adc_top.spice`'s own
top-level `sky130_fd_sc_hd` instance lines.

**This is the check issue #387 exists because nobody had.** The failure mode
it closes is specific and not detectable by `klt lvs`: a layout composed from
a superseded netlist, compared against an LVS reference *generated from that
same superseded netlist*, agrees with itself perfectly. The two sides of the
compare are not independent, so a clean match establishes only that the
generator and the layout came from the same place -- never that the place they
came from is the schematic this repo now builds. Issue #56's
`SELp<i> = DOUT<i>` / `SELn<i> = NOT(DOUT<i>)` glue stayed in
`layout/seln-inverters/` for two weeks after
`spec/decision-records/DR-008-cdac-top-level-switching-polarity.md`
superseded it, through repeated DRC/LVS-clean runs, for exactly this reason.

The independent anchor is the schematic netlist itself. This script re-derives
the expected instance list from `design/sar_adc_top.spice` on every run
(positional pin lists translated against the PDK's own `.SUBCKT` pin order)
and diffs it against the hand-written Verilog the layout is actually built
from. A polarity swap -- the one defect class `klt lvs` structurally cannot
see here, because both sides would carry it -- fails this check.

`design/sar_adc_top.spice` is itself gated against the schematic sources by
`design/regen_netlist.sh --check` in CI, so the chain is
schematic -> netlist -> this check -> Verilog -> layout, with no self-reference.

Since issue #850 the instance-compare and report core lives in
`layout/bin/_lvs_reference_common.py`, shared with
`layout/sar-sequencer/bin/check-schematic-parity.py` (the sequencer
counterpart, issue #676) rather than copied into it. What stays here is the
per-block half: which lines of the spice file are this block's, the default
paths, the pin-order-cache comment, and this gate's own FAIL/OK scope suffix.

Usage:
    layout/top-glue/bin/check-schematic-parity.py              # both files as committed
    layout/top-glue/bin/check-schematic-parity.py --netlist <v>
    layout/top-glue/bin/check-schematic-parity.py --refresh-pin-order-cache

Exit status: 0 if the two agree exactly, 1 on any difference (with every
difference printed, not just the first).

**Runs headless.** The one PDK-derived input is each cell's `.SUBCKT` pin
order (needed to translate the SPICE card's positional net list into named
pins), which is cached in `netlist/sky130_fd_sc_hd-pin-order.json`. With a
resolvable sky130A PDK install the orders are re-derived from
`sky130_fd_sc_hd.cdl` and the cache is *verified* against it (a stale cache
fails, and `--refresh-pin-order-cache` rewrites it); without one the cache is
used as-is. That is what lets this gate run in CI's always-on headless
`checks` job rather than only in the PDK-gated `pdk-smoke` job -- the drift
this check exists to catch went unnoticed for two weeks, so a nightly-only
gate is not enough.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BLOCK_DIR = Path(__file__).resolve().parent.parent
LAYOUT_DIR = BLOCK_DIR.parent
REPO_ROOT = LAYOUT_DIR.parent

sys.path.insert(0, str(LAYOUT_DIR / "bin"))

import _lvs_reference_common
from _lvs_reference_common import (  # noqa: E402
    cdl_text_if_available,
    instance_map_problems,
    report_instance_parity,
    spice_instances_from_cards,
    top_level_subckt_body,
    verilog_instances_with_supply_defaults,
)

DEFAULT_SPICE = REPO_ROOT / "design" / "sar_adc_top.spice"
DEFAULT_NETLIST = BLOCK_DIR / "netlist" / "top_glue.v"
PIN_ORDER_CACHE = BLOCK_DIR / "netlist" / "sky130_fd_sc_hd-pin-order.json"


def _top_level_body(spice_text: str) -> str:
    """The `sar_adc_top` subcircuit body only.

    Delegates to `layout/bin/_lvs_reference_common.py`'s
    `top_level_subckt_body()` since issue #495, which needed the same slice
    for the half-LSB offset network's own parity gate. The regexes and the
    two `SystemExit` messages moved there verbatim; this wrapper stays so the
    rest of this module reads unchanged.
    """
    return top_level_subckt_body(spice_text)


def std_cell_cards(spice_path: Path) -> list[str]:
    """The top-level subcircuit's own `sky130_fd_sc_hd__*` instance cards.

    The per-block half of this gate: *which* lines of
    `design/sar_adc_top.spice` are this block's, i.e. the instances the top
    level adds itself (no sub-block), filtered to the standard-cell library.
    Translating those cards into named pins, diffing them against the Verilog
    and reporting is shared with the sequencer's gate -- see
    `layout/bin/_lvs_reference_common.py`.
    """
    body = _top_level_body(spice_path.read_text(encoding="utf-8"))
    cards: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("*") or line.startswith("."):
            continue
        if line.split()[-1].startswith("sky130_fd_sc_hd__"):
            cards.append(line)
    return cards


def top_level_cell_types(cards: list[str]) -> list[str]:
    """Every `sky130_fd_sc_hd` cell type the top-level subcircuit instantiates.

    Derived from the SCHEMATIC side, never from the layout side's own
    configuration: a cell type present in the schematic but absent from a
    hardcoded layout-side list would otherwise be invisible to this check,
    which is the exact shape of the drift being guarded against.
    """
    return sorted({card.split()[-1] for card in cards})


PIN_ORDER_COMMENT = (
    "Pin order of each sky130_fd_sc_hd cell type "
    "design/sar_adc_top.spice instantiates at the top level, "
    "transcribed from the PDK's own "
    "libs.ref/sky130_fd_sc_hd/cdl/sky130_fd_sc_hd.cdl by "
    "layout/top-glue/bin/check-schematic-parity.py "
    "--refresh-pin-order-cache. Committed so that check can "
    "run in CI's headless, PDK-less job; verified against the "
    "real CDL on every run that HAS a PDK, so it cannot drift "
    "silently. Regenerate, never hand-edit."
)


def resolve_pin_orders(
    cell_types: list[str], cdl_text: str | None, refresh: bool
) -> dict[str, list[str]]:
    """Top-glue's pin orders; the cache rules live in
    `layout/bin/_lvs_reference_common.py`'s `resolve_pin_orders`."""
    return _lvs_reference_common.resolve_pin_orders(
        cell_types,
        cdl_text,
        refresh,
        cache_path=PIN_ORDER_CACHE,
        comment=PIN_ORDER_COMMENT,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spice", type=Path, default=DEFAULT_SPICE)
    parser.add_argument("--netlist", type=Path, default=DEFAULT_NETLIST)
    parser.add_argument(
        "--refresh-pin-order-cache",
        action="store_true",
        help="rewrite netlist/sky130_fd_sc_hd-pin-order.json from the PDK's own CDL",
    )
    args = parser.parse_args()

    cards = std_cell_cards(args.spice)
    cell_types = top_level_cell_types(cards)
    pin_orders = resolve_pin_orders(
        cell_types, cdl_text_if_available(), args.refresh_pin_order_cache
    )

    want = spice_instances_from_cards(cards, pin_orders)
    got = verilog_instances_with_supply_defaults(args.netlist, tuple(cell_types))

    return report_instance_parity(
        want,
        instance_map_problems(want, got),
        spice_path=args.spice,
        netlist_path=args.netlist,
        fail_scope="'s own top-level sky130_fd_sc_hd instances",
        ok_scope="",
    )


if __name__ == "__main__":
    raise SystemExit(main())

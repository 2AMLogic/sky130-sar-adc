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
import json
import os
import re
import sys
from pathlib import Path

BLOCK_DIR = Path(__file__).resolve().parent.parent
LAYOUT_DIR = BLOCK_DIR.parent
REPO_ROOT = LAYOUT_DIR.parent

sys.path.insert(0, str(LAYOUT_DIR / "bin"))

from _lvs_reference_common import (  # noqa: E402
    _extract_cdl_subckt,
    _resolve_pdk_root,
    parse_verilog_netlist,
)

DEFAULT_SPICE = REPO_ROOT / "design" / "sar_adc_top.spice"
DEFAULT_NETLIST = BLOCK_DIR / "netlist" / "top_glue.v"
PIN_ORDER_CACHE = BLOCK_DIR / "netlist" / "sky130_fd_sc_hd-pin-order.json"

#: `emit_std_cell_lvs_reference`'s own implicit supply defaults, repeated here
#: so this check validates them too: the schematic's own instance lines name
#: all four supply pins explicitly, and a Verilog netlist that omits them is
#: only equivalent if these are the nets they resolve to.
SUPPLY_DEFAULTS = {"VGND": "VGND", "VNB": "VGND", "VPB": "VPWR", "VPWR": "VPWR"}

_TOP_SUBCKT_RE = re.compile(r"^\*\*\.subckt\s+sar_adc_top\b", re.M)
_ENDS_RE = re.compile(r"^\*\*\.ends\b", re.M)


def _top_level_body(spice_text: str) -> str:
    """The `sar_adc_top` subcircuit body only.

    `design/regen_netlist.sh` writes xschem's own full-hierarchy dump: the
    top-level subcircuit comes first, delimited by the commented-out
    `**.subckt sar_adc_top ...` / `**.ends` pair xschem emits for the top
    cell, followed by every sub-block's own real `.subckt`. Slicing to that
    first region is what makes "the instances the top level adds, inside no
    sub-block" a mechanical question rather than a judgement.
    """
    start = _TOP_SUBCKT_RE.search(spice_text)
    if start is None:
        raise SystemExit(
            "check-schematic-parity.py: no '**.subckt sar_adc_top' line found"
        )
    end = _ENDS_RE.search(spice_text, start.end())
    if end is None:
        raise SystemExit("check-schematic-parity.py: no '**.ends' line after sar_adc_top")
    return spice_text[start.end() : end.start()]


def top_level_cell_types(spice_path: Path) -> list[str]:
    """Every `sky130_fd_sc_hd` cell type the top-level subcircuit instantiates.

    Derived from the SCHEMATIC side, never from the layout side's own
    configuration: a cell type present in the schematic but absent from a
    hardcoded layout-side list would otherwise be invisible to this check,
    which is the exact shape of the drift being guarded against.
    """
    body = _top_level_body(spice_path.read_text(encoding="utf-8"))
    types: set[str] = set()
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("*") or line.startswith("."):
            continue
        cell_type = line.split()[-1]
        if cell_type.startswith("sky130_fd_sc_hd__"):
            types.add(cell_type)
    return sorted(types)


def _cdl_text_if_available() -> str | None:
    """The PDK's own `sky130_fd_sc_hd.cdl`, or None when no PDK is resolvable
    (a bare CI checkout). Never an error: the cache below covers that case."""
    cdl_path = Path(_resolve_pdk_root()) / (
        "libs.ref/sky130_fd_sc_hd/cdl/sky130_fd_sc_hd.cdl"
    )
    return cdl_path.read_text(encoding="utf-8") if cdl_path.is_file() else None


def resolve_pin_orders(
    cell_types: list[str], cdl_text: str | None, refresh: bool
) -> dict[str, list[str]]:
    """`{cell_type: [pin, ...]}` in the PDK's own `.SUBCKT` declaration order.

    With the PDK present the orders come from the CDL and the committed cache
    is asserted to agree with it; with the PDK absent the cache is the source.
    Either way the orders are the PDK's, never this script's -- the cache is a
    transcription with a verification path, not a second opinion.
    """
    cached: dict[str, list[str]] = {}
    if PIN_ORDER_CACHE.is_file():
        cached = json.loads(PIN_ORDER_CACHE.read_text(encoding="utf-8"))["pin_order"]

    if cdl_text is None:
        missing = sorted(set(cell_types) - set(cached))
        if missing:
            raise SystemExit(
                "check-schematic-parity.py: no sky130A PDK resolvable and "
                f"{PIN_ORDER_CACHE.name} has no pin order for {missing} -- "
                "re-run with the PDK available and "
                "--refresh-pin-order-cache"
            )
        print(
            "check-schematic-parity.py: no PDK resolvable -- using the committed "
            f"pin-order cache ({PIN_ORDER_CACHE.name})"
        )
        return {cell: cached[cell] for cell in cell_types}

    derived = {cell: _extract_cdl_subckt(cdl_text, cell)[0] for cell in cell_types}
    if refresh:
        PIN_ORDER_CACHE.write_text(
            json.dumps(
                {
                    "_comment": (
                        "Pin order of each sky130_fd_sc_hd cell type "
                        "design/sar_adc_top.spice instantiates at the top level, "
                        "transcribed from the PDK's own "
                        "libs.ref/sky130_fd_sc_hd/cdl/sky130_fd_sc_hd.cdl by "
                        "layout/top-glue/bin/check-schematic-parity.py "
                        "--refresh-pin-order-cache. Committed so that check can "
                        "run in CI's headless, PDK-less job; verified against the "
                        "real CDL on every run that HAS a PDK, so it cannot drift "
                        "silently. Regenerate, never hand-edit."
                    ),
                    "open_pdks_commit": json.loads(
                        (REPO_ROOT / "sim" / "pdk.json").read_text(encoding="utf-8")
                    )["open_pdks_commit"],
                    "pin_order": {cell: derived[cell] for cell in sorted(derived)},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"check-schematic-parity.py: refreshed {PIN_ORDER_CACHE}")
        return derived

    drifted = [
        cell for cell in cell_types if cell in cached and cached[cell] != derived[cell]
    ]
    absent = sorted(set(cell_types) - set(cached))
    if drifted or absent:
        raise SystemExit(
            f"check-schematic-parity.py: {PIN_ORDER_CACHE.name} is stale "
            f"(drifted: {drifted}, missing: {absent}) -- re-run with "
            "--refresh-pin-order-cache"
        )
    return derived


def spice_std_cell_instances(
    spice_path: Path, pin_orders: dict[str, list[str]]
) -> dict[str, tuple[str, dict[str, str]]]:
    """`{instance_name: (cell_type, {pin: net})}` for every
    `sky130_fd_sc_hd__*` instance the top-level subcircuit adds.

    The SPICE card is positional (`xname net... subckt`); the PDK's own
    `.SUBCKT` pin order supplies the names to zip it against, so the
    translation is the PDK's, not this script's.
    """
    body = _top_level_body(spice_path.read_text(encoding="utf-8"))
    out: dict[str, tuple[str, dict[str, str]]] = {}
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("*") or line.startswith("."):
            continue
        toks = line.split()
        cell_type = toks[-1]
        if not cell_type.startswith("sky130_fd_sc_hd__"):
            continue
        inst_name = toks[0]
        nets = toks[1:-1]
        pins = pin_orders[cell_type]
        if len(pins) != len(nets):
            raise SystemExit(
                f"check-schematic-parity.py: {inst_name}: {cell_type} has "
                f"{len(pins)} CDL pins but the instance card names {len(nets)} nets"
            )
        out[inst_name] = (cell_type, dict(zip(pins, nets)))
    return out


def verilog_instances(
    netlist_path: Path, cell_types: tuple[str, ...]
) -> dict[str, tuple[str, dict[str, str]]]:
    """The same shape, read out of the structural Verilog, with the implicit
    supply connections resolved exactly as the LVS-reference generator
    resolves them."""
    _, instances = parse_verilog_netlist(str(netlist_path), cell_types)
    out: dict[str, tuple[str, dict[str, str]]] = {}
    for inst_name, cell_type, pin_map in instances:
        full = dict(SUPPLY_DEFAULTS)
        full.update(pin_map)
        if inst_name in out:
            raise SystemExit(
                f"check-schematic-parity.py: duplicate instance name {inst_name}"
            )
        out[inst_name] = (cell_type, full)
    return out


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

    cell_types = top_level_cell_types(args.spice)
    pin_orders = resolve_pin_orders(
        cell_types, _cdl_text_if_available(), args.refresh_pin_order_cache
    )

    want = spice_std_cell_instances(args.spice, pin_orders)
    got = verilog_instances(args.netlist, tuple(cell_types))

    problems: list[str] = []
    for name in sorted(set(want) - set(got)):
        problems.append(f"MISSING from Verilog: {name} ({want[name][0]})")
    for name in sorted(set(got) - set(want)):
        problems.append(f"EXTRA in Verilog (not in schematic): {name} ({got[name][0]})")
    for name in sorted(set(want) & set(got)):
        want_cell, want_pins = want[name]
        got_cell, got_pins = got[name]
        if want_cell != got_cell:
            problems.append(f"{name}: cell type {got_cell!r} != schematic {want_cell!r}")
            continue
        for pin in sorted(set(want_pins) | set(got_pins)):
            w = want_pins.get(pin)
            g = got_pins.get(pin)
            if w != g:
                problems.append(
                    f"{name}.{pin}: Verilog net {g!r} != schematic net {w!r}"
                )

    rel_spice = os.path.relpath(args.spice, REPO_ROOT)
    rel_netlist = os.path.relpath(args.netlist, REPO_ROOT)
    if problems:
        print(
            f"check-schematic-parity.py: FAIL -- {rel_netlist} does not match "
            f"{rel_spice}'s own top-level sky130_fd_sc_hd instances:",
            file=sys.stderr,
        )
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    census: dict[str, int] = {}
    for cell, _ in want.values():
        census[cell] = census.get(cell, 0) + 1
    print(
        f"check-schematic-parity.py: OK -- {len(want)} instances, "
        f"{len(census)} cell types, every pin net-identical to {rel_spice}"
    )
    for cell in sorted(census):
        print(f"  {cell}: {census[cell]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

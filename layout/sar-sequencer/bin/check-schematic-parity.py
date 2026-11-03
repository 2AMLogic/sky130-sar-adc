#!/usr/bin/env python3
"""Assert that `layout/sar-sequencer/netlist/sar_sequencer.v` is
instance-for-instance, pin-for-pin, net-for-net identical to the
`sar_sequencer` subcircuit of `design/sar_adc_top.spice`, which xschem
netlists from `design/sar_sequencer.sch`.

**Why this check exists.** `sar_sequencer.v` is a structural gate-level netlist
*transliterated by hand* from `design/sar_sequencer.sch` -- it is not
synthesized from RTL (see its header and `layout/sar-sequencer/README.md`). A
hand transliteration has no freshness mechanism of its own: the schematic can
move and the Verilog the layout is built from will not notice. `klt lvs` cannot
see that either, because the LVS reference is generated from the same Verilog,
so a layout and a reference that both descend from a stale netlist agree
perfectly. This is the sequencer counterpart of
`layout/top-glue/bin/check-schematic-parity.py` (issue #387), which closed the
same gap for the glue bank.

**What binds the Verilog to the schematic.** Two links, both mechanical:

  design/sar_sequencer.sch --(design/regen_netlist.sh --check, CI)-->
  design/sar_adc_top.spice --(this script)--> layout/sar-sequencer/netlist/sar_sequencer.v

This script re-derives the expected instance list from the spice file's own
`.subckt sar_sequencer` block on every run (positional pin lists translated
against the PDK's own `.SUBCKT` pin order) and diffs it against the Verilog,
also comparing the module port list against the subcircuit's port list.

What it does NOT assert: that the schematic is functionally right (that is
`sim/sar-sequencer-behavioral/`'s job), or that the layout matches the Verilog
(that is `klt lvs`).

Usage:
    layout/sar-sequencer/bin/check-schematic-parity.py
    layout/sar-sequencer/bin/check-schematic-parity.py --netlist <v>
    layout/sar-sequencer/bin/check-schematic-parity.py --refresh-pin-order-cache

Exit status: 0 if the two agree exactly, 1 on any difference (every difference
is printed, not just the first).

**Runs headless.** Each cell's `.SUBCKT` pin order is cached in
`netlist/sky130_fd_sc_hd-pin-order.json`; with a resolvable sky130A PDK the
cache is verified against the PDK's CDL (a stale cache fails), without one the
cache is used as-is, so the gate can run in CI's always-on `checks` job.
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
DEFAULT_NETLIST = BLOCK_DIR / "netlist" / "sar_sequencer.v"
PIN_ORDER_CACHE = BLOCK_DIR / "netlist" / "sky130_fd_sc_hd-pin-order.json"
SUBCKT = "sar_sequencer"

#: The supply pins the Verilog omits; the LVS-reference generator fills them in
#: with these nets (same defaults `top-glue`'s check validates).
SUPPLY_DEFAULTS = {"VGND": "VGND", "VNB": "VGND", "VPB": "VPWR", "VPWR": "VPWR"}

_SUBCKT_RE = re.compile(rf"^\.subckt\s+{SUBCKT}\s+(.*)$", re.M)
_ENDS_RE = re.compile(r"^\.ends\b", re.M)


def sequencer_subckt(spice_text: str) -> tuple[list[str], list[str]]:
    """`(port_list, instance_lines)` of the `sar_sequencer` subcircuit."""
    start = _SUBCKT_RE.search(spice_text)
    if start is None:
        raise SystemExit(f"check-schematic-parity.py: no '.subckt {SUBCKT}' found")
    end = _ENDS_RE.search(spice_text, start.end())
    if end is None:
        raise SystemExit(f"check-schematic-parity.py: no '.ends' after {SUBCKT}")
    lines = []
    for raw in spice_text[start.end() : end.start()].splitlines():
        line = raw.strip()
        if line and not line.startswith(("*", ".")):
            lines.append(line)
    return start.group(1).split(), lines


def _cdl_text_if_available() -> str | None:
    cdl_path = Path(_resolve_pdk_root()) / "libs.ref/sky130_fd_sc_hd/cdl/sky130_fd_sc_hd.cdl"
    return cdl_path.read_text(encoding="utf-8") if cdl_path.is_file() else None


def resolve_pin_orders(
    cell_types: list[str], cdl_text: str | None, refresh: bool
) -> dict[str, list[str]]:
    """`{cell_type: [pin, ...]}` in the PDK's own `.SUBCKT` declaration order
    (see `layout/top-glue/bin/check-schematic-parity.py` for the cache rules)."""
    cached: dict[str, list[str]] = {}
    if PIN_ORDER_CACHE.is_file():
        cached = json.loads(PIN_ORDER_CACHE.read_text(encoding="utf-8"))["pin_order"]

    if cdl_text is None:
        missing = sorted(set(cell_types) - set(cached))
        if missing:
            raise SystemExit(
                "check-schematic-parity.py: no sky130A PDK resolvable and "
                f"{PIN_ORDER_CACHE.name} has no pin order for {missing} -- re-run "
                "with the PDK available and --refresh-pin-order-cache"
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
                        "Pin order of each sky130_fd_sc_hd cell type the "
                        "sar_sequencer subcircuit of design/sar_adc_top.spice "
                        "instantiates, transcribed from the PDK's own "
                        "libs.ref/sky130_fd_sc_hd/cdl/sky130_fd_sc_hd.cdl by "
                        "layout/sar-sequencer/bin/check-schematic-parity.py "
                        "--refresh-pin-order-cache. Committed so that check can "
                        "run in CI's headless, PDK-less job; verified against the "
                        "real CDL on every run that HAS a PDK. Regenerate, never "
                        "hand-edit."
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

    drifted = [c for c in cell_types if c in cached and cached[c] != derived[c]]
    absent = sorted(set(cell_types) - set(cached))
    if drifted or absent:
        raise SystemExit(
            f"check-schematic-parity.py: {PIN_ORDER_CACHE.name} is stale "
            f"(drifted: {drifted}, missing: {absent}) -- re-run with "
            "--refresh-pin-order-cache"
        )
    return derived


def verilog_ports(netlist_path: Path) -> list[str]:
    text = netlist_path.read_text(encoding="utf-8")
    match = re.search(r"\bmodule\s+\w+\s*\((.*?)\)\s*;", text, re.S)
    if match is None:
        raise SystemExit(f"check-schematic-parity.py: no module header in {netlist_path}")
    return [p.strip() for p in match.group(1).split(",") if p.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--spice", type=Path, default=DEFAULT_SPICE)
    parser.add_argument("--netlist", type=Path, default=DEFAULT_NETLIST)
    parser.add_argument(
        "--refresh-pin-order-cache",
        action="store_true",
        help="rewrite netlist/sky130_fd_sc_hd-pin-order.json from the PDK's own CDL",
    )
    args = parser.parse_args()

    ports, lines = sequencer_subckt(args.spice.read_text(encoding="utf-8"))
    cell_types = sorted({ln.split()[-1] for ln in lines})
    pin_orders = resolve_pin_orders(
        cell_types, _cdl_text_if_available(), args.refresh_pin_order_cache
    )

    want: dict[str, tuple[str, dict[str, str]]] = {}
    for line in lines:
        toks = line.split()
        name, cell, nets = toks[0], toks[-1], toks[1:-1]
        if cell not in pin_orders:
            raise SystemExit(f"check-schematic-parity.py: {name}: non-standard-cell line {line!r}")
        if len(pin_orders[cell]) != len(nets):
            raise SystemExit(
                f"check-schematic-parity.py: {name}: {cell} has {len(pin_orders[cell])} "
                f"CDL pins but the instance card names {len(nets)} nets"
            )
        want[name] = (cell, dict(zip(pin_orders[cell], nets)))

    _, instances = parse_verilog_netlist(str(args.netlist), tuple(cell_types))
    got: dict[str, tuple[str, dict[str, str]]] = {}
    for name, cell, pin_map in instances:
        if name in got:
            raise SystemExit(f"check-schematic-parity.py: duplicate instance name {name}")
        full = dict(SUPPLY_DEFAULTS)
        full.update(pin_map)
        got[name] = (cell, full)

    problems: list[str] = []
    v_ports = verilog_ports(args.netlist)
    if sorted(v_ports) != sorted(ports):
        problems.append(
            f"module ports differ: only in Verilog {sorted(set(v_ports) - set(ports))}, "
            f"only in schematic {sorted(set(ports) - set(v_ports))}"
        )
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
            if want_pins.get(pin) != got_pins.get(pin):
                problems.append(
                    f"{name}.{pin}: Verilog net {got_pins.get(pin)!r} != "
                    f"schematic net {want_pins.get(pin)!r}"
                )

    rel_spice = os.path.relpath(args.spice, REPO_ROOT)
    rel_netlist = os.path.relpath(args.netlist, REPO_ROOT)
    if problems:
        print(
            f"check-schematic-parity.py: FAIL -- {rel_netlist} does not match "
            f"{rel_spice}'s .subckt {SUBCKT}:",
            file=sys.stderr,
        )
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    census: dict[str, int] = {}
    for cell, _ in want.values():
        census[cell] = census.get(cell, 0) + 1
    print(
        f"check-schematic-parity.py: OK -- {len(want)} instances, {len(census)} cell "
        f"types, every pin net-identical to {rel_spice} .subckt {SUBCKT}"
    )
    for cell in sorted(census):
        print(f"  {cell}: {census[cell]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

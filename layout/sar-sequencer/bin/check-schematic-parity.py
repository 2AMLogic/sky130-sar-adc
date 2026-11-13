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
same gap for the glue bank. Since issue #850 the two gates run ONE shared
compare core out of `layout/bin/_lvs_reference_common.py` rather than two
copies of it, so a fix to the comparison cannot land in only one of them;
what stays here is the `.subckt sar_sequencer` slice, the module-port check,
and this gate's own FAIL/OK scope suffix.

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
import re
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
    verilog_instances_with_supply_defaults,
)

DEFAULT_SPICE = REPO_ROOT / "design" / "sar_adc_top.spice"
DEFAULT_NETLIST = BLOCK_DIR / "netlist" / "sar_sequencer.v"
PIN_ORDER_CACHE = BLOCK_DIR / "netlist" / "sky130_fd_sc_hd-pin-order.json"
SUBCKT = "sar_sequencer"

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


PIN_ORDER_COMMENT = (
    "Pin order of each sky130_fd_sc_hd cell type the "
    "sar_sequencer subcircuit of design/sar_adc_top.spice "
    "instantiates, transcribed from the PDK's own "
    "libs.ref/sky130_fd_sc_hd/cdl/sky130_fd_sc_hd.cdl by "
    "layout/sar-sequencer/bin/check-schematic-parity.py "
    "--refresh-pin-order-cache. Committed so that check can "
    "run in CI's headless, PDK-less job; verified against the "
    "real CDL on every run that HAS a PDK. Regenerate, never "
    "hand-edit."
)


def resolve_pin_orders(
    cell_types: list[str], cdl_text: str | None, refresh: bool
) -> dict[str, list[str]]:
    """Sequencer's pin orders; the cache rules live in
    `layout/bin/_lvs_reference_common.py`'s `resolve_pin_orders`."""
    return _lvs_reference_common.resolve_pin_orders(
        cell_types,
        cdl_text,
        refresh,
        cache_path=PIN_ORDER_CACHE,
        comment=PIN_ORDER_COMMENT,
    )


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
        cell_types, cdl_text_if_available(), args.refresh_pin_order_cache
    )

    # Per-block: the subcircuit body is sliced whole, so a line that is not a
    # standard-cell instantiation at all is this gate's own error to raise --
    # top-glue filters its cards down to `sky130_fd_sc_hd__*` instead.
    for line in lines:
        toks = line.split()
        if toks[-1] not in pin_orders:
            raise SystemExit(
                f"check-schematic-parity.py: {toks[0]}: non-standard-cell line {line!r}"
            )

    want = spice_instances_from_cards(lines, pin_orders)
    got = verilog_instances_with_supply_defaults(args.netlist, tuple(cell_types))

    problems: list[str] = []
    v_ports = verilog_ports(args.netlist)
    if sorted(v_ports) != sorted(ports):
        problems.append(
            f"module ports differ: only in Verilog {sorted(set(v_ports) - set(ports))}, "
            f"only in schematic {sorted(set(ports) - set(v_ports))}"
        )
    problems += instance_map_problems(want, got)

    return report_instance_parity(
        want,
        problems,
        spice_path=args.spice,
        netlist_path=args.netlist,
        fail_scope=f"'s .subckt {SUBCKT}",
        ok_scope=f" .subckt {SUBCKT}",
    )


if __name__ == "__main__":
    raise SystemExit(main())

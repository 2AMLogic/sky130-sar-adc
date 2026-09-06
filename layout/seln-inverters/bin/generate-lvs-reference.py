#!/usr/bin/env python3
"""Generate
layout/seln-inverters/reference/seln_inverters.lvs-reference.spice -- the
flat, transistor-level LVS reference for the SELn<i> inverter bank (issue
#103's own top-level glue logic).

Adapted from layout/sar-sequencer/bin/generate-lvs-reference.py (issue #102)
-- same mechanism (flatten a structural Verilog netlist against the sky130
PDK's own official per-cell CDL models), narrowed to this block's single
cell type (`sky130_fd_sc_hd__inv_1`) and its own (much shorter) top-level
port list. See that script's docstring for the full "why" (flat extraction,
generic nfet/pfet device classes, post-route-not-pre-route topology, `m=`
finger-count scaling).

Clean room: the topology being flattened is this repo's own captured
schematic (design/sar_adc_top.sch's xinv_seln0..8), elaborated by this
repo's own P&R run; the device models substituted in are the PDK's own
official, freely-licensed standard-cell library.

Usage:
    layout/seln-inverters/bin/generate-lvs-reference.py [netlist.v]

Requires: a resolvable sky130A PDK install (same pin as sim/pdk.json).
Writes: layout/seln-inverters/reference/seln_inverters.lvs-reference.spice
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

LAYOUT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLOCK_DIR = os.path.join(LAYOUT_DIR, "seln-inverters")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "bin"))

from _lvs_reference_common import (  # noqa: E402
    _extract_cdl_subckt,
    _generalize_model,
    _resolve_pdk_root,
    parse_verilog_netlist,
)

DEFAULT_NETLIST = os.path.join(
    BLOCK_DIR, "requests", ".klt", "place-and-route", "seln_inverters_post_route.v"
)
OUT_PATH = os.path.join(
    BLOCK_DIR, "reference", "seln_inverters.lvs-reference.spice"
)

CELL_TYPES = ("sky130_fd_sc_hd__inv_1",)


def main() -> int:
    netlist_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_NETLIST
    if not os.path.isfile(netlist_path):
        print(
            f"generate-lvs-reference.py: netlist not found: {netlist_path}\n"
            "  (run layout/seln-inverters/bin/run-flow.sh first, or pass an "
            "explicit path)",
            file=sys.stderr,
        )
        return 1

    pdk_dir = _resolve_pdk_root()
    cdl_path = os.path.join(
        pdk_dir, "libs.ref", "sky130_fd_sc_hd", "cdl", "sky130_fd_sc_hd.cdl"
    )
    if not os.path.isfile(cdl_path):
        print(f"generate-lvs-reference.py: CDL not found: {cdl_path}", file=sys.stderr)
        return 1
    with open(cdl_path, encoding="utf-8") as handle:
        cdl_text = handle.read()

    cell_defs: dict[str, tuple[list[str], list[tuple]]] = {}
    for cell_type in CELL_TYPES:
        cell_defs[cell_type] = _extract_cdl_subckt(cdl_text, cell_type)

    top_name, instances = parse_verilog_netlist(netlist_path, CELL_TYPES)
    if not instances:
        print(
            f"generate-lvs-reference.py: no standard-cell instances found in "
            f"{netlist_path}",
            file=sys.stderr,
        )
        return 1

    # This design's own fixed port order (matches
    # layout/seln-inverters/netlist/seln_inverters.v's own port list), not
    # whatever order OpenROAD's `write_verilog` happens to re-declare.
    top_ports = (
        [f"DOUT{n}" for n in range(8, -1, -1)]
        + [f"SELn{n}" for n in range(8, -1, -1)]
        + ["VPWR", "VGND"]
    )

    out_lines = [
        "* LVS reference for the SELn<i> inverter bank (issue #103).",
        "*",
        "* Mechanically generated -- DO NOT HAND-EDIT. Regenerate with:",
        "*   layout/seln-inverters/bin/generate-lvs-reference.py [netlist.v]",
        "*",
        f"* Topology source: {os.path.relpath(netlist_path, LAYOUT_DIR)}",
        "* (klt place-and-route's own post-route `write_verilog` dump).",
        "*",
        "* Flat, transistor-level (klt extract --deck sky130 is a flat",
        "* extractor), device classes generalized to nfet/pfet. Device",
        "* models: the sky130 PDK's own official CDL",
        "* (libs.ref/sky130_fd_sc_hd/cdl/sky130_fd_sc_hd.cdl), Apache-2.0",
        "* licensed, SkyWater's own release -- not reverse-engineered.",
        f".SUBCKT {top_name} {' '.join(top_ports)}",
    ]

    for inst_name, cell_type, pin_map in instances:
        signal_pins, devices = cell_defs[cell_type]
        full_pin_map = dict(pin_map)
        full_pin_map.setdefault("VGND", "VGND")
        full_pin_map.setdefault("VNB", "VGND")
        full_pin_map.setdefault("VPB", "VPWR")
        full_pin_map.setdefault("VPWR", "VPWR")

        for dev_inst, drain, gate, source, body, model, w, l in devices:
            def resolve(node: str, _map=full_pin_map, _inst=inst_name) -> str:
                if node in _map:
                    return _map[node]
                return f"{_inst}_{node}"

            out_lines.append(
                f"M{inst_name}_{dev_inst} {resolve(drain)} {resolve(gate)} "
                f"{resolve(source)} {resolve(body)} {_generalize_model(model)} "
                f"L={l}U W={w}U"
            )

    out_lines.append(f".ENDS {top_name}")
    out_lines.append("")

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out_lines))

    device_total = sum(len(cell_defs[cell_type][1]) for _, cell_type, _ in instances)
    print(
        f"generate-lvs-reference.py: wrote {OUT_PATH} "
        f"({len(instances)} instances, {device_total} devices)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

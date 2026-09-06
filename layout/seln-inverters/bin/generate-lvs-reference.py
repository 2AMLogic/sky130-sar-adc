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
import re
import sys
from decimal import Decimal

LAYOUT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLOCK_DIR = os.path.join(LAYOUT_DIR, "seln-inverters")
DEFAULT_NETLIST = os.path.join(
    BLOCK_DIR, "requests", ".klt", "place-and-route", "seln_inverters_post_route.v"
)
OUT_PATH = os.path.join(
    BLOCK_DIR, "reference", "seln_inverters.lvs-reference.spice"
)

CELL_TYPES = ("sky130_fd_sc_hd__inv_1",)

_MODULE_RE = re.compile(r"^module\s+(\w+)\s*\(", re.M)
_INSTANCE_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in CELL_TYPES) + r")\s+(\w+)\s*\((.*?)\)\s*;",
    re.S,
)
_PORT_CONN_RE = re.compile(r"\.\s*(\w+)\s*\(\s*([^()]*?)\s*\)")


def parse_verilog_netlist(path: str) -> tuple[str, list[tuple[str, str, dict[str, str]]]]:
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    module_match = _MODULE_RE.search(text)
    if module_match is None:
        raise SystemExit(f"generate-lvs-reference.py: no 'module' found in {path}")
    top_name = module_match.group(1)

    instances: list[tuple[str, str, dict[str, str]]] = []
    for cell_type, inst_name, port_list_text in _INSTANCE_RE.findall(text):
        pin_map: dict[str, str] = {}
        for port_name, connection in _PORT_CONN_RE.findall(port_list_text):
            connection = connection.strip()
            if connection:
                pin_map[port_name] = connection
        instances.append((inst_name, cell_type, pin_map))

    return top_name, instances


def _extract_cdl_subckt(cdl_text: str, name: str) -> tuple[list[str], list[tuple]]:
    pat = re.compile(rf"^\.SUBCKT {re.escape(name)} (.*?)\n(.*?)^\.ENDS", re.S | re.M)
    match = pat.search(cdl_text)
    if match is None:
        raise SystemExit(f"generate-lvs-reference.py: '{name}' not found in CDL")
    pins = match.group(1).split()
    lines = []
    current = ""
    for line in match.group(2).split("\n"):
        if line.startswith("*"):
            continue
        if line.startswith("+"):
            current += " " + line[1:].strip()
        else:
            if current:
                lines.append(current)
            current = line.strip()
    if current:
        lines.append(current)

    devices = []
    for line in lines:
        if not line.startswith("M"):
            continue
        toks = line.split()
        inst, drain, gate, source, body, model = toks[0], *toks[1:6]
        params = dict(t.split("=", 1) for t in toks[6:] if "=" in t)
        w = Decimal(params["w"]) * int(Decimal(params.get("m", "1")))
        devices.append((inst, drain, gate, source, body, model, w, params.get("l")))
    return pins, devices


def _generalize_model(model: str) -> str:
    if "nfet" in model:
        return "nfet"
    if "pfet" in model:
        return "pfet"
    raise SystemExit(f"generate-lvs-reference.py: unrecognized model '{model}'")


def _resolve_pdk_root() -> str:
    root = os.environ.get("PDK_ROOT") or os.path.expanduser("~/.volare")
    variant = os.environ.get("PDK", "sky130A")
    return os.path.join(root, variant)


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

    top_name, instances = parse_verilog_netlist(netlist_path)
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

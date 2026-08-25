#!/usr/bin/env python3
"""Generate layout/sar-sequencer/reference/sar_sequencer.lvs-reference.spice
-- the flat, transistor-level LVS reference for the SAR sequencer sub-block.

Why this exists (see layout/sar-sequencer/README.md "LVS reference
provenance" for the full writeup):

1. `klt extract --deck sky130` is a flat, transistor-level extractor (its own
   docstring: "extraction is flat"), so a `klt lvs` reference netlist has to
   be flat and transistor-level too -- a hierarchical reference with
   `X`-instances of `sky130_fd_sc_hd__*` standard cells cannot be compared
   circuit-for-circuit against a flat, transistor-level layout netlist. `klt
   extract`'s sky130 deck also generalizes every drawn NMOS/PMOS into two
   device classes, `nfet`/`pfet` (regardless of the real device flavor --
   `nfet_01v8` vs. `special_nfet_01v8`, or `pfet_01v8_hvt`), so the reference
   has to use those same two generic model names for `klt lvs`'s
   `NetlistComparer` to pair devices by class.

2. The reference has to be the netlist OpenROAD actually placed and routed
   -- not the pre-place-and-route structural netlist
   (layout/sar-sequencer/netlist/sar_sequencer.v). `klt place-and-route`'s
   own `cts`/`route` stages legitimately modify the gate-level netlist
   (`clock_tree_synthesis`/`repair_design`/`repair_timing` insert clock
   buffers and repair cells) -- this is standard, expected P&R behavior, not
   a design defect, and the correct LVS target is always "does the drawn
   geometry match what was actually placed and routed", not "does the
   pre-P&R input netlist appear byte-for-byte in the layout" (a *separate*
   concern, formal logical-equivalence checking against the original
   netlist, which is out of scope for this flow -- see the README's own
   "LVS reference provenance" section for the verification this repo does
   instead: a structural diff confirming the only insertions are clock-tree/
   repair cells, no combinational-logic change).

This script mechanically expands (flattens) a structural Verilog netlist
(by default, `klt place-and-route`'s own post-route `write_verilog` output)
against the sky130 PDK's own official per-cell transistor-level CDL models
(`$PDK_ROOT/sky130A/libs.ref/sky130_fd_sc_hd/cdl/sky130_fd_sc_hd.cdl`,
Apache-2.0 licensed, SkyWater's own release). Every internal (non-pin) node
of each per-cell definition is uniquified with an `<instance>_` prefix so
instances don't collide on shared local names (e.g. every dfrtp_1 instance
has its own `net82`/`clkpos`/... internal nodes); an unconnected Verilog port
(e.g. a CTS clock-load cell's floating output) is left as its own unique,
otherwise-unreferenced internal node, matching what "unconnected" means for
a real device terminal.

Clean room: the *topology* being flattened is this repo's own captured
schematic, elaborated by this repo's own P&R run; the *device models* being
substituted in are the PDK's own official, freely-licensed standard-cell
library -- not reverse-engineered from anyone's silicon or netlist.

Usage:
    layout/sar-sequencer/bin/generate-lvs-reference.py [netlist.v]

    netlist.v defaults to
    layout/sar-sequencer/requests/.klt/place-and-route/sar_sequencer_post_route.v
    (produced by layout/sar-sequencer/bin/run-flow.sh's own post-route
    `write_verilog` dump -- see that script).

Requires: a resolvable sky130A PDK install (same pin as sim/pdk.json).
Writes: layout/sar-sequencer/reference/sar_sequencer.lvs-reference.spice
"""
from __future__ import annotations

import os
import re
import sys

LAYOUT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAR_SEQ_DIR = os.path.join(LAYOUT_DIR, "sar-sequencer")
DEFAULT_NETLIST = os.path.join(
    SAR_SEQ_DIR,
    "requests",
    ".klt",
    "place-and-route",
    "sar_sequencer_post_route.v",
)
OUT_PATH = os.path.join(
    SAR_SEQ_DIR, "reference", "sar_sequencer.lvs-reference.spice"
)

#: Standard-cell signal-pin order for each cell type this sub-block's
#: post-route netlist may contain, matching the CDL's own `.SUBCKT` pin
#: list minus the four power pins (VGND VNB VPB VPWR), which every instance
#: ties to this design's two global power nets instead (see
#: `full_pin_map.setdefault` below).
CELL_TYPES = (
    "sky130_fd_sc_hd__dfrtp_1",
    "sky130_fd_sc_hd__mux2_1",
    "sky130_fd_sc_hd__or4_1",
    "sky130_fd_sc_hd__or3_1",
    "sky130_fd_sc_hd__inv_1",
    "sky130_fd_sc_hd__buf_4",
)

_MODULE_RE = re.compile(r"^module\s+(\w+)\s*\(", re.M)
_INSTANCE_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in CELL_TYPES) + r")\s+(\w+)\s*\((.*?)\)\s*;",
    re.S,
)
_PORT_CONN_RE = re.compile(r"\.\s*(\w+)\s*\(\s*([^()]*?)\s*\)")


def parse_verilog_netlist(path: str) -> tuple[str, list[str], list[tuple[str, str, dict[str, str]]]]:
    """Parse a flat structural Verilog netlist into
    ``(top_module_name, ports, instances)``, where ``instances`` is a list of
    ``(instance_name, cell_type, {signal_pin: net_or_None})`` -- ``None`` for
    an explicitly unconnected port (e.g. ``.Y()``), never an empty string.

    Deliberately narrow: only recognizes the standard-cell types in
    :data:`CELL_TYPES`, in the named-port-connection form every real
    synthesis/P&R tool (OpenROAD's own `write_verilog` included) emits.
    """
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

    return top_name, [], instances


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
        devices.append((inst, drain, gate, source, body, model, params.get("w"), params.get("l")))
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
            "  (run layout/sar-sequencer/bin/run-flow.sh first, or pass an "
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

    top_name, _unused_ports, instances = parse_verilog_netlist(netlist_path)
    if not instances:
        print(
            f"generate-lvs-reference.py: no standard-cell instances found in "
            f"{netlist_path}",
            file=sys.stderr,
        )
        return 1

    # Top-level port order: this design's own fixed port list (not read back
    # from the Verilog `module (...)` header, whose declaration order is
    # OpenROAD's/Yosys's internal choice, not necessarily this design's own
    # canonical order) -- matches
    # layout/sar-sequencer/netlist/sar_sequencer.v's own port list exactly.
    top_ports = (
        ["CLK", "RST_B", "COMP_OUT"]
        + [f"PH_B{n}" for n in range(9, -1, -1)]
        + ["PH_EOC", "PH_SAMPLE", "BUSY"]
        + [f"DOUT{n}" for n in range(9, -1, -1)]
    )

    out_lines = [
        "* LVS reference for the SAR logic/sequencer sub-block (issue #102).",
        "*",
        "* Mechanically generated -- DO NOT HAND-EDIT. Regenerate with:",
        "*   layout/sar-sequencer/bin/generate-lvs-reference.py [netlist.v]",
        "*",
        f"* Topology source: {os.path.relpath(netlist_path, LAYOUT_DIR)}",
        "* (klt place-and-route's own post-route `write_verilog` dump -- see",
        "* layout/sar-sequencer/README.md, 'LVS reference provenance', for",
        "* why the LVS reference has to be the *post-route* netlist, not the",
        "* pre-P&R structural netlist).",
        "*",
        "* Flat, transistor-level (klt extract --deck sky130 is a flat",
        "* extractor), device classes generalized to nfet/pfet (matching that",
        "* deck's own generalization of every drawn NMOS/PMOS regardless of",
        "* flavor). Device models: the sky130 PDK's own official CDL",
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
            def resolve(node: str) -> str:
                if node in full_pin_map:
                    return full_pin_map[node]
                return f"{inst_name}_{node}"

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

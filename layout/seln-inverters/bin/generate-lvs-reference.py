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

from _lvs_reference_common import emit_std_cell_lvs_reference  # noqa: E402

DEFAULT_NETLIST = os.path.join(
    BLOCK_DIR, "requests", ".klt", "place-and-route", "seln_inverters_post_route.v"
)
OUT_PATH = os.path.join(
    BLOCK_DIR, "reference", "seln_inverters.lvs-reference.spice"
)

CELL_TYPES = ("sky130_fd_sc_hd__inv_1",)


def main() -> int:
    netlist_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_NETLIST

    # This design's own fixed port order (matches
    # layout/seln-inverters/netlist/seln_inverters.v's own port list), not
    # whatever order OpenROAD's `write_verilog` happens to re-declare.
    top_ports = (
        [f"DOUT{n}" for n in range(8, -1, -1)]
        + [f"SELn{n}" for n in range(8, -1, -1)]
        + ["VPWR", "VGND"]
    )

    header_lines = [
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
    ]

    return emit_std_cell_lvs_reference(
        netlist_path,
        OUT_PATH,
        CELL_TYPES,
        top_ports,
        header_lines,
        run_flow_hint="layout/seln-inverters/bin/run-flow.sh",
    )


if __name__ == "__main__":
    raise SystemExit(main())

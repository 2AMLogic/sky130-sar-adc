#!/usr/bin/env python3
"""Generate layout/top-glue/reference/top_glue.lvs-reference.spice -- the
flat, transistor-level LVS reference for the SAR ADC's top-level
standard-cell glue bank (issue #387).

Same mechanism as `layout/sar-sequencer/bin/generate-lvs-reference.py` (issue
#102) and the superseded `layout/seln-inverters/` (PR #166): flatten `klt
place-and-route`'s own post-route structural Verilog dump against the sky130
PDK's own official per-cell CDL models, generalizing every NMOS/PMOS to
`klt`'s own `nfet`/`pfet` device classes because `klt extract --deck sky130`
is a flat, transistor-level extractor. See that script's docstring for the
full "why" (flat extraction, post-route-not-pre-route topology, `m=`
finger-count scaling).

Widened from that sibling's single `inv_1` to this bank's **six** cell types
(`CELL_TYPES` below), which is the whole point of this block: the glue
`design/sar_adc_top.spice` adds at the top level is no longer nine
inverters. `_lvs_reference_common.emit_std_cell_lvs_reference()` already
parameterizes on the cell-type tuple, so no new flattening code is needed
here -- only this block's own configuration.

Clean room: the topology being flattened is this repo's own
`netlist/top_glue.v`, itself hand-derived from this repo's own captured
`design/sar_adc_top.spice`, elaborated by this repo's own P&R run; the device
models substituted in are the PDK's own official, freely-licensed
standard-cell library (Apache-2.0, SkyWater's own release).

Usage:
    layout/top-glue/bin/generate-lvs-reference.py [netlist.v]

Requires: a resolvable sky130A PDK install (same pin as sim/pdk.json).
Writes: layout/top-glue/reference/top_glue.lvs-reference.spice
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

LAYOUT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLOCK_DIR = os.path.join(LAYOUT_DIR, "top-glue")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "bin"))

from _lvs_reference_common import emit_std_cell_lvs_reference  # noqa: E402

DEFAULT_NETLIST = os.path.join(
    BLOCK_DIR, "requests", ".klt", "place-and-route", "top_glue_post_route.v"
)
OUT_PATH = os.path.join(BLOCK_DIR, "reference", "top_glue.lvs-reference.spice")

#: Every `sky130_fd_sc_hd` cell type `design/sar_adc_top.spice` instantiates
#: at the top level, and therefore every type `netlist/top_glue.v` may
#: contain. Kept in the same order as that netlist's own groups. A type
#: missing from this tuple is silently *dropped* by
#: `parse_verilog_netlist`'s instance regex rather than erroring, so the
#: census assertion in `main()` below is what actually gates it.
CELL_TYPES = (
    "sky130_fd_sc_hd__inv_1",
    "sky130_fd_sc_hd__and2_1",
    "sky130_fd_sc_hd__and2b_1",
    "sky130_fd_sc_hd__mux2_1",
    "sky130_fd_sc_hd__xnor2_1",
    "sky130_fd_sc_hd__xor2_1",
)

#: The instance census `design/sar_adc_top.spice` itself specifies, per cell
#: type -- the same 33/6 census `docs/chipalooza/check_proposal_citations.py
#: --stats` reports for the top level outside every sub-block. Asserted
#: against the post-route netlist on every run, so a silently-dropped or
#: silently-duplicated instance fails the flow instead of quietly minting a
#: reference that agrees with a layout neither matches the schematic. This is
#: the check that would have caught issue #387: the superseded glue's
#: reference and layout were both built from the same #56 instance list, so
#: they agreed with each other while agreeing with nothing else.
EXPECTED_CENSUS = {
    "sky130_fd_sc_hd__inv_1": 3,
    "sky130_fd_sc_hd__and2_1": 18,
    "sky130_fd_sc_hd__and2b_1": 1,
    "sky130_fd_sc_hd__mux2_1": 1,
    "sky130_fd_sc_hd__xnor2_1": 1,
    "sky130_fd_sc_hd__xor2_1": 9,
}

#: This block's own fixed port order -- the same order
#: `netlist/top_glue.v`'s own module header declares, not whatever order
#: OpenROAD's `write_verilog` happens to re-declare. `VPWR`/`VGND` are
#: appended here but are NOT Verilog module ports (the P&R request's own
#: `power` block owns them); the flattened reference needs them as real
#: `.SUBCKT` pins because every cell's own CDL model connects to them.
TOP_PORTS = (
    ["CLK"]
    + [f"DOUT{n}" for n in range(9, -1, -1)]
    + ["PH_B9", "BUSY", "OUTN_NC", "CLKN"]
    + [f"SELp{n}" for n in range(8, -1, -1)]
    + [f"SELn{n}" for n in range(8, -1, -1)]
    + [f"ADCOUT{n}" for n in range(8, -1, -1)]
    + ["HALF_LSB_EN", "HALF_LSB_ENN", "DUMLOAD_MUX_NC", "DUMLOAD_XNOR_NC"]
    + ["VPWR", "VGND"]
)


def check_census(netlist_path: str) -> int:
    """Fail loudly if the post-route netlist's own per-cell-type instance
    census is not exactly `EXPECTED_CENSUS`.

    Runs before the reference is emitted, so a drifted netlist never gets a
    matching reference generated for it.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "bin"))
    from _lvs_reference_common import parse_verilog_netlist  # noqa: PLC0415

    _, instances = parse_verilog_netlist(netlist_path, CELL_TYPES)
    census: dict[str, int] = {}
    for _, cell_type, _ in instances:
        census[cell_type] = census.get(cell_type, 0) + 1
    if census != EXPECTED_CENSUS:
        print(
            "generate-lvs-reference.py: instance census does not match "
            "design/sar_adc_top.spice's own top-level glue\n"
            f"  expected: {EXPECTED_CENSUS}\n"
            f"  found:    {census}\n"
            f"  netlist:  {netlist_path}",
            file=sys.stderr,
        )
        return 1
    return 0


def main() -> int:
    netlist_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_NETLIST
    if not os.path.isfile(netlist_path):
        print(
            f"generate-lvs-reference.py: netlist not found: {netlist_path}\n"
            "  (run layout/top-glue/bin/run-flow.sh first, or pass an explicit path)",
            file=sys.stderr,
        )
        return 1

    census_status = check_census(netlist_path)
    if census_status != 0:
        return census_status

    header_lines = [
        "* LVS reference for the SAR ADC top-level standard-cell glue bank",
        "* (issue #387).",
        "*",
        "* Mechanically generated -- DO NOT HAND-EDIT. Regenerate with:",
        "*   layout/top-glue/bin/generate-lvs-reference.py [netlist.v]",
        "*",
        f"* Topology source: {os.path.relpath(netlist_path, LAYOUT_DIR)}",
        "* (klt place-and-route's own post-route `write_verilog` dump, itself",
        "* elaborated from layout/top-glue/netlist/top_glue.v -- hand-derived",
        "* 1:1 from design/sar_adc_top.spice's own top-level instance lines as",
        "* they stand under DR-008/DR-009, NOT from issue #56's superseded",
        "* xinv_seln0..8 inverter bank).",
        "*",
        "* Instance census asserted against design/sar_adc_top.spice on every",
        "* run: inv_1 x3, and2_1 x18, and2b_1 x1, mux2_1 x1, xnor2_1 x1,",
        "* xor2_1 x9 (33 instances, 6 cell types).",
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
        TOP_PORTS,
        header_lines,
        run_flow_hint="layout/top-glue/bin/run-flow.sh",
    )


if __name__ == "__main__":
    raise SystemExit(main())

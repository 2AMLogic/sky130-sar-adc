#!/usr/bin/env python3
"""Generate the top-level LVS reference for the SAR ADC assembly (issue
#103): each of the five sub-blocks' own already-generated, already-verified
flat reference subckt, concatenated, plus one new `.SUBCKT sar_adc_top`
wrapper instantiating all five per `design/sar_adc_top.sch`'s own
interconnect (mirrored 1:1 from `design/sar_adc_top.spice`'s own
`xfe`/`xcdac`/`xcmp`/`xseq`/`xinv_seln<i>` instantiation lines -- see that
file's header for its own schematic provenance).

Does NOT re-derive any device-level topology: every device card comes
unmodified from the four sub-blocks' own committed reference (`klt lvs`
already verifies these against each sub-block's own schematic in each
sub-block's own flow) -- this script only adds the *composition* the
schematic itself specifies, one level up.

Usage:
    layout/sar-adc-top/bin/generate-lvs-reference.py \\
        --sar-sequencer-report <dir> --seln-inverters-report <dir> \\
        -o <out.spice>

`--sar-sequencer-report`/`--seln-inverters-report` name a
`reports/<record-id>/` directory holding that sub-block's own
`<name>.lvs-reference.spice` (sar_sequencer/seln_inverters do not commit a
stable top-level reference path the way cdac_array/comparator/
sampling_frontend do -- each place-and-route run mints its own, per that
sub-block's own README).

Clean room: assembles this repo's own already-verified sub-block references
per this repo's own captured schematic; introduces no new device-level
content and consults no third-party netlist.
"""
from __future__ import annotations

import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LAYOUT_DIR = REPO_ROOT / "layout"

TOP_SUBCKT = """\
.SUBCKT sar_adc_top VINP VINN VDD VREFP VREFN VCM CLK RST_B \
DOUT9 DOUT8 DOUT7 DOUT6 DOUT5 DOUT4 DOUT3 DOUT2 DOUT1 DOUT0 BUSY
* sampling_frontend (layout/sampling-frontend/reference.spice ports:
* VDD GND SAMPLE VCM VINP VINN TOP_P TOP_N BPREF_P BPREF_N BOOST_P BOOST_N)
Xfe VDD GND SAMPLE_INT VCM VINP VINN TOP_P TOP_N \
BPREF_P_NC BPREF_N_NC BOOST_P_NC BOOST_N_NC sampling_frontend
* cdac_array (layout/cdac-array/reference/cdac_array.lvs-reference.spice
* ports: VREFP VREFN VDD vsubs SELn0 SELp0 .. SELn8 SELp8, TOP_N/TOP_P
* mid-list -- mirrored verbatim from design/sar_adc_top.spice's own xcdac)
Xcdac VREFP VREFN VDD GND SELn0 DOUT0 SELn1 DOUT1 SELn2 DOUT2 SELn3 DOUT3 \
SELn4 DOUT4 TOP_N TOP_P DOUT5 SELn5 DOUT6 SELn6 SELn7 DOUT7 SELn8 DOUT8 \
cdac_array
* comparator (layout/comparator/reference.spice ports:
* VDD GND CLK VINP VINN OUTP OUTN)
Xcmp VDD GND CLK TOP_P TOP_N COMP_OUT OUTN_NC comparator
* sar_sequencer (this sub-block's own LATEST reports/<id>/
* sar_sequencer.lvs-reference.spice ports: CLK RST_B COMP_OUT PH_B9..PH_B0
* PH_EOC PH_SAMPLE BUSY DOUT9..DOUT0 VPWR VGND -- PH_B<i>/PH_EOC left
* dead-ended per design/sar_adc_top.sch's own documented integration gap;
* VPWR/VGND left as this instance's own self-contained rail, per that same
* gap note extended to a second digital instance -- see
* layout/sar-adc-top/README.md "GND / VPWR / VGND")
Xseq CLK RST_B COMP_OUT PH_B9_NC PH_B8_NC PH_B7_NC PH_B6_NC PH_B5_NC \
PH_B4_NC PH_B3_NC PH_B2_NC PH_B1_NC PH_B0_NC PH_EOC_NC SAMPLE_INT BUSY \
DOUT9 DOUT8 DOUT7 DOUT6 DOUT5 DOUT4 DOUT3 DOUT2 DOUT1 DOUT0 \
VPWR_SEQ VGND_SEQ sar_sequencer
* seln_inverters (this issue's own glue macro -- LATEST reports/<id>/
* seln_inverters.lvs-reference.spice ports: DOUT8..DOUT0 SELn8..SELn0
* VPWR VGND; VPWR/VGND left as ITS OWN separate self-contained rail, not
* tied to sar_sequencer's -- see the same README note above)
Xinv DOUT8 DOUT7 DOUT6 DOUT5 DOUT4 DOUT3 DOUT2 DOUT1 DOUT0 \
SELn8 SELn7 SELn6 SELn5 SELn4 SELn3 SELn2 SELn1 SELn0 \
VPWR_SELN VGND_SELN seln_inverters
.ENDS
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sar-sequencer-report", required=True, type=Path)
    parser.add_argument("--seln-inverters-report", required=True, type=Path)
    parser.add_argument("-o", "--out", required=True, type=Path)
    args = parser.parse_args()

    parts = [
        "* sar_adc_top.lvs-reference.spice -- GENERATED, do not edit by hand.\n"
        "* Regenerate with: layout/sar-adc-top/bin/generate-lvs-reference.py\n"
        "* Assembles the five already-verified sub-block reference subckts\n"
        "* below (unmodified) into one hierarchical top-level netlist per\n"
        "* design/sar_adc_top.sch -- see this script's own module docstring.\n\n"
    ]
    sources = [
        LAYOUT_DIR / "sampling-frontend" / "reference.spice",
        LAYOUT_DIR / "cdac-array" / "reference" / "cdac_array.lvs-reference.spice",
        LAYOUT_DIR / "comparator" / "reference.spice",
        args.sar_sequencer_report / "sar_sequencer.lvs-reference.spice",
        args.seln_inverters_report / "seln_inverters.lvs-reference.spice",
    ]
    for src in sources:
        parts.append(f"* --- from {src.relative_to(REPO_ROOT)} " + "-" * 20 + "\n")
        parts.append(src.read_text())
        parts.append("\n")
    parts.append("* --- top-level composition (design/sar_adc_top.sch) " + "-" * 10 + "\n")
    parts.append(TOP_SUBCKT)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(parts))
    print(f"generate-lvs-reference.py: wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

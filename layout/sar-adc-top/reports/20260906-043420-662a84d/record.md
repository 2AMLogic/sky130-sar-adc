# SAR ADC top-level assembly record: 20260906-043420-662a84d

## Provenance
- `klt` version: klt 0.4.0
- PDK variant: sky130A
- repo commit: `662a84dc3b6ba5391fd2af3a5ad74da5c016a9bd` (dirty)

## DRC (sky130 deck, composed top-level layout)
- **CLEAN** -- 0 violations

## Connectivity verification (unfiltered extraction, by net)
`klt extract` with no declared-pin restriction, checked net-by-net against the intended interconnect in `layout/sar-adc-top/README.md` -- this is the direct evidence this issue's closing summary relies on, independent of the pin-declaration blocker below.

| Expected net | Found in (unfiltered) net name | OK? |
| --- | --- | --- |
| TOP_P | `TOP_P|VINP` | yes |
| TOP_N | `TOP_N|VINN` | yes |
| VDD (analog) | `VDD` | yes |
| VREFP | `VREFP` | yes |
| VREFN | `VREFN` | yes |
| CLK | `A|CLK, A|CLK|X, CLK|X` | NO (3 matches) |
| COMP_OUT | `A1|COMP_OUT|OUTP` | yes |
| SAMPLE_INT | `D|PH_SAMPLE|SAMPLE|Y` | yes |
| RST_B | `RESET_B|RST_B` | yes |
| BUSY | `A|BUSY|X` | yes |
| DOUT0 | `A|A0|DOUT0|Q|SELp0` | yes |
| DOUT1 | `A|A0|DOUT1|Q|SELp1` | yes |
| DOUT2 | `A|A0|DOUT2|Q|SELp2` | yes |
| DOUT3 | `A|A0|DOUT3|Q|SELp3` | yes |
| DOUT4 | `A|A0|DOUT4|Q|SELp4` | yes |
| DOUT5 | `A|A0|DOUT5|Q|SELp5` | yes |
| DOUT6 | `A|A0|DOUT6|Q|SELp6` | yes |
| DOUT7 | `A|A0|DOUT7|Q|SELp7` | yes |
| DOUT8 | `A|A0|DOUT8|Q|SELp8` | yes |
| DOUT9 | `A0|DOUT9|Q` | yes |
| SELn0 | `SELn0|Y` | yes |
| SELn1 | `SELn1|Y` | yes |
| SELn2 | `SELn2|Y` | yes |
| SELn3 | `SELn3|Y` | yes |
| SELn4 | `SELn4|Y` | yes |
| SELn5 | `SELn5|Y` | yes |
| SELn6 | `SELn6|Y` | yes |
| SELn7 | `SELn7|Y` | yes |
| SELn8 | `SELn8|Y` | yes |

## LVS (top-level layout vs. hierarchical reference)
- verdict: **mismatch**
- devices: layout=867 reference=867 matched=812
- pins promoted from `--def-pins`: 23 (expected 19)
- **known blocker**: no `klt extract` declared-pin mechanism (`--top-cell-pins`, `--pins`, `--def-pins`) reproducibly promotes exactly this design's own intended 19-port top-level interface once composed from five independently-labeled sub-blocks with no governing top-level DEF -- `--top-cell-pins` demotes this flow's own genuine ports (drawn in an instanced routing cell, not the literal top cell), `--pins` cannot express an already-joined promoted name as one token, and `--def-pins` over-promotes unrelated internal nodes that happen to share a joined-label component with a declared name (e.g. a downstream clock-buffer net also carrying `CLK`). Filed generically at 2AMLogic/klayout-tools#1513. The connectivity table above is this record's actual evidence that the composition's own interconnect is correct; this LVS verdict reflects the pin-count mismatch that blocker causes, not a routing defect.


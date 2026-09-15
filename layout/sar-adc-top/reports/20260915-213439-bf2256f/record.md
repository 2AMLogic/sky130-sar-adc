# SAR ADC top-level assembly record: 20260915-213439-bf2256f

## Provenance
- `klt` version: klt 0.5.0
- PDK variant: sky130A
- repo commit: `bf2256f6dc157523c35f5eff6866cf0b4d230841` (dirty)

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
- pins promoted from `--pin-source-cells`: layout=19 reference=19 matched=19 (expected 19/19/19) -- klayout-tools#1513 is resolved: this is the first record where every top-level pin promotes correctly.
- devices: layout=869 reference=869 matched=794
- nets: layout=444 reference=446 matched=393
- mismatch categories:
  - `device.unmatched`: 99
  - `net.merged`: 12
  - `net.split`: 10
  - `topology`: 2
  - `topology.flattened`: 1
- **known blockers (distinct from klayout-tools#1513, which is now resolved)**: two, layered. (1) `klt lvs`'s `options.combine_devices` is a single flag applied to the whole (flattened) compared netlist, with no per-subcircuit scoping. Three of the five already-independently-verified sub-blocks (comparator, sar_sequencer, seln_inverters) need it `true` to re-lump their own genuinely split/interleaved layout legs against their own lumped reference devices; the other two (cdac_array, sampling_frontend) need it `false` (cdac_array to avoid klayout-tools#1497's parallel-capacitor combine nondeterminism). klayout-tools#1552 (this repo's own report of exactly this gap) is closed upstream via #1556's new `options.combine_devices_per_circuit`, but that option does not actually help here: it can only scope a side that already has separate per-macro subcircuits, and `klt extract`'s layout-side output for a composed GDS is always one flat circuit (extraction still has no hierarchical mode, #1085) -- confirmed by direct measurement, filed generically as klayout-tools#1878. (2) klayout-tools#1558's v0.5.0 fix to stop writing an unsimulatable trailing class-name token on `C` cards has the side effect of losing that class name on the SPICE round-trip this flow's pre-extracted `layout.netlist` LVS shape depends on, so capacitor devices no longer resolve to their reference-side counterpart by class name -- filed generically as klayout-tools#1876. Neither blocker is a routing defect: the pin declaration and (per the connectivity table above) the physical routing are both independently confirmed correct.


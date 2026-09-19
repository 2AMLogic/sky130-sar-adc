# SAR ADC top-level assembly record: 20260919-050355-fb11617

## Provenance
- `klt` version: klt 0.5.0
- PDK variant: sky130A
- repo commit: `fb116171e2275fce32d058db4e9371020a3da4b3` (dirty)

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
| CLK | `A|CLK` | yes (see note) |
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

- **CLK**: `A|CLK` is the single net promoted to this assembly's own top-level pin by `klt extract --pin-source-cells`. 3 unfiltered net names contain the label(s) `CLK` -- the other 2 (`A|CLK|X`, `CLK|X`) are internal nets of a sub-block that label their own copy of this signal (a label-name collision the flattened extraction exposes, not a split of the routed net).

## LVS (top-level layout vs. hierarchical reference)
- verdict: **mismatch**
- pins promoted from `--pin-source-cells`: layout=19 reference=19 matched=19 (expected 19/19/19) -- klayout-tools#1513 is resolved: this is the first record where every top-level pin promotes correctly.
- devices: layout=869 reference=869 matched=794
- nets: layout=444 reference=446 matched=412
- mismatch categories:
  - `device.unmatched`: 75
  - `net.merged`: 12
  - `net.split`: 10
  - `topology.flattened`: 1
- capacitor device-class token (klayout-tools#1876): restored on 1028/1028 `C` cards (sky130_fd_pr__model__cap_mim) from `klt extract`'s own per-instance comment lines, into `sar_adc_top.extract.lvs.spice` -- the extractor's own `sar_adc_top.extract.spice` is kept unmodified alongside it. Without this, the SPICE round-trip this LVS shape depends on loses the capacitor class name and the same layout reports 26 extra mismatches (124 vs 98) and 19 fewer matched nets (393 vs 412).
- **known blocker: one, klayout-tools#1878** (klayout-tools#1513's pin-declaration blocker is resolved by `--pin-source-cells`; #1876's capacitor device-class regression is worked around locally, see the line above). `klt lvs`'s `options.combine_devices` is a single flag applied to the whole (flattened) compared netlist, with no per-subcircuit scoping. Three of the five already-independently-verified sub-blocks (comparator, sar_sequencer, seln_inverters) need it `true` to re-lump their own genuinely split/interleaved layout legs against their own lumped reference devices; the other two (cdac_array, sampling_frontend) need it `false` (cdac_array to avoid klayout-tools#1497's parallel-capacitor combine nondeterminism). klayout-tools#1552 (this repo's own report of exactly this gap) is closed upstream via #1556's new `options.combine_devices_per_circuit`, but that option does not actually help here: it can only scope a side that already has separate per-macro subcircuits, and `klt extract`'s layout-side output for a composed GDS is always one flat circuit (extraction still has no hierarchical mode, #1085) -- confirmed by direct measurement, filed generically as klayout-tools#1878. Neither the class-scoped `combine_devices: ["NFET","PFET"]` form (klayout-tools#1370) nor `klt lvs`'s inline-extraction shape substitutes for it (126 and 2199 mismatches respectively -- see run-flow.sh's own measured trace). This blocker is not a routing defect: the pin declaration and (per the connectivity table above) the physical routing are both independently confirmed correct.

## `--abstract-cells` ablation probe (2026-09-19)

`bin/probe-abstract-cells.py` was run against this record's own `sar_adc_top.gds`
(`layout/.venv/bin/python layout/sar-adc-top/bin/probe-abstract-cells.py
layout/sar-adc-top/reports/20260919-050355-fb11617`), producing
`abstract-probe.klt-0.5.0.summary.json` alongside this file. It re-measures the
README's "A fourth shape measured" `--abstract-cells` black-boxing result
against five ablations and corrects that section's original diagnosis: the
6-mismatch composite-net collapse is a same-instance pin-to-net binding fault
(three of `cdac_array__cdac_array`'s own declared pins resolving onto one
synthesized net, which also absorbs the unrelated `VINN`/`VINP` net),
unaffected by either supplying the macro's previously-missing 4th pin or
stripping its nwell/tap geometry -- i.e. **not** the klayout-tools#1911/#1934
mechanism this section originally blamed it on. See the README section for
the full writeup; corrected diagnosis filed generically as
[klayout-tools#2142](https://github.com/2AMLogic/klayout-tools/issues/2142).


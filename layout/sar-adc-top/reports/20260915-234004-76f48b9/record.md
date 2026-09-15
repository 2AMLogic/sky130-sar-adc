# SAR ADC top-level assembly record: 20260915-234004-76f48b9

## Provenance
- `klt` version: klt 0.5.0
- PDK variant: sky130A
- repo commit: `76f48b919a59481399023d2f57214b4bf0dd47f7` (dirty)

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

## Addendum: `--abstract-cells` black-boxing experiment (same GDS, this record)

Measured against this same `sar_adc_top.gds`, not adopted for signoff -- see
`layout/sar-adc-top/README.md`'s "LVS device/topology blocker" section
("A fourth shape measured") for the full writeup and rationale. Extra
artifacts in this record directory, all reproducible from files committed
here (no `/tmp` paths):

- `abstract-cells-experiment.extract.spice` / `.extract.lvs.spice` /
  `.extract.json` -- `klt extract --abstract-cells 'cdac_array__cdac_array'
  --abstract-cells 'sar_sequencer__sar_sequencer' --abstract-cells
  'seln_inverters__seln_inverters'` (plus `--pin-source-cells`, same as the
  signoff attempt above) on the same `sar_adc_top.gds`, then
  `bin/restore-cap-device-class.py` (same #1876 workaround as the signoff
  attempt).
- `abstract-cells-experiment.reference-full-device.spice` +
  `.lvs-full-device.request.json` / `.lvs-full-device.json` -- first trial:
  the three abstracted sub-blocks' reference subckts renamed to their
  `<block-id>__<cell-name>` qualifiers but left at full device detail
  (comparator/sampling_frontend inlined into the top). **1476 mismatches**
  -- comparing a real, hundreds-of-devices reference subckt against a
  layout-side black box that has zero devices fails outright; kept as
  evidence for why hollowing (next) is necessary, not as a candidate shape.
- `abstract-cells-experiment.reference-hollow.spice` +
  `.lvs-hollow.request.json` / `.lvs-hollow.json` -- second trial: the same
  three subckts hollowed (header + `.ENDS` only, no devices), matching the
  layout side's own opaque boundary. **6 mismatches** (`device.unmatched:
  3`, `net.merged: 2`, `topology: 1`; nets 59/61/128, devices 35/35/32, pins
  19/19/92) -- traced to klayout-tools#1911 (a `--abstract-cells`-side net-
  name corruption caused by `cdac_array`'s own label-less 4th port), not
  independently verifiable as benign yet, hence not adopted.


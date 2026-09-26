# SAR ADC top-level assembly record: 20260926-081248-203cca3

## Provenance
- `klt` version: klt 0.6.0
- PDK: sky130A (open_pdks f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7)
- repo commit: `203cca3f5ec87ed03d16ca523283202edefea8da` (dirty)

## DRC (sky130 deck, composed top-level layout)
- **CLEAN** -- 0 violations

## On-die supply decoupling (DR-017, placed by issue #440)
`klt gen cap_array` unit cell: 46.9 x 46.9 um `capm` plate, 1 device, bbox 47.9 x 48.82 um. Placed 4 times -- 2 per supply domain, which is how DR-017's `MF = 2` is drawn -- at `decap_a0` (128.0, 150.0), `decap_a1` (180.0, 150.0), `decap_d0` (196.0, -150.0), `decap_d1` (196.0, -98.0).

| quantity | value | share of the composed die |
| --- | --- | --- |
| composed bounding box | 280.450 x 385.500 um = 108113.475 um^2 | 100 % |
| `capm` plate area, both domains | 8798.44 um^2 | 8.14 % |
| placed cell footprint, both domains | 9353.91 um^2 | 8.65 % |

- Capacitance per domain: **8.870 pF** (2 x 4.435 pF), from the PDK's own `camimc`/`cpmimc` coefficients -- the same value `klt extract` reports for each placed unit, and the same one the LVS reference declares.
- MiM devices in the filtered extraction: **1032** (the composition's pre-existing 1028 CDAC/front-end unit caps, plus these 4).
- Decoupling capacitors as the compared netlist actually carries them (every `C` card both of whose terminals are supply nets):
  - `GND|VGND|VSS` <-> `VDD`: 2 x 4.434864e-12 F
  - `GND|VGND|VSS` <-> `VPB|VPWR`: 2 x 4.434864e-12 F
  `GND`, `VGND` and `cdac_array`'s own `VSS` extract as ONE net -- the shared p-substrate bulk sky130 offers no way to split, per `spec/decision-records/DR-012-analog-ground-pad.md` -- so both domains' return terminals land on that one name here. That is the same merge the LVS section's `net.merged` entries already track, not a new finding, and it is why the analog pair is the one that cannot correspond to a reference device (see that section).
- LVS mismatch entries naming a decoupling capacitor: 1.
  - `device.unmatched` (reference side): reference `DECAP_A0` / layout `\$1892`, class `SKY130_FD_PR__MODEL__CAP_MIM`.
  Each is the DR-012 substrate merge above reaching a device, not a new mismatch class: `GND` is on the reference side of an already-tracked `net.merged` entry, so no reference device with a `GND` terminal can correspond, and the analog pair has one. The digital pair, whose return port is `VGND` -- the name the comparer paired that merged layout net with -- does correspond.
- Series resistance of the ties, from `decap-ties.json` (lumped DC over drawn conductor only, at the PDK's own `rm2`/`rm3`/`rm4`/`rcvia2`/`rcvia3`/`rcvia4`; excludes each plate's own distributed resistance and all inductance):
  - `VDD (analog supply -> both top plates)`: **2.98 ohm** (shared 0.795, branches 3.842 / 5.064)
  - `GND (analog return -> both bottom plates)`: **10.857 ohm** (shared 8.601, branches 3.41 / 6.66)
  - `VPWR (digital supply -> both top plates)`: **3.605 ohm** (shared 1.641, branches 3.41 / 4.632)
  - `VGND (digital return -> both bottom plates)`: **9.843 ohm** (shared 7.7, branches 3.41 / 5.765)
  - **analog (VDD/GND) domain ESR: 13.837 ohm** at 8.870 pF -- Q = 1.062 at the 1221.5 MHz resonance that capacitance forms with DR-015's own 1.914 nH per-terminal package inductance, and the ESR equals the pair's own reactance at 1.297 GHz.
  - **digital (VPWR/VGND) domain ESR: 13.448 ohm** at 8.870 pF -- Q = 1.092 at the 1221.5 MHz resonance that capacitance forms with DR-015's own 1.914 nH per-terminal package inductance, and the ESR equals the pair's own reactance at 1.334 GHz.
  **The dominant term is not the metal -- it is the SINGLE-CUT vias**, at `rcvia2`/`rcvia3` = 3.41 ohm per cut. Each return path has three (the met4->met2 riser's two, plus the via2 into each plate) against each supply path's one, which is why the return ties are 3.6x and 2.7x their own domain's supply tie despite running on 2.0 um conductor. Of the analog return's 8.601 ohm shared leg, 6.82 ohm is those two riser cuts and only 1.781 ohm is 28.5 um of met2. Widening the straps further therefore buys almost nothing; a via ARRAY at each riser and each plate entry would cut the ESR ~3x, and that is a separate change with its own re-measurement -- it moves no device and changes no declared value, so it needs no superseding decision record. See README.md's "On-die decoupling (DR-017)" for what it would and would not buy.
- **DR-017's Decision §3 area budget is confirmed placeable, and costs no die area at all.** Its `capm` figure above is the 8798.44 um^2 / 8.14 % that record computed at schematic level; both sites fall inside the *pre-existing* composed bounding box, which this record reports unchanged, so the allocation displaced no routing and grew no die. See `layout/sar-adc-top/README.md`, "On-die decoupling (DR-017)", for the met3/met4 occupancy measurement the two placements were chosen from.

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
- pins promoted from `--pin-source-cells`: layout=21 reference=22 matched=22 -- klayout-tools#1513 is resolved: every top-level pin label this flow draws promotes correctly. The layout count is BELOW the reference count by design, not by defect: since issue #362 the reference carries `GND` and `VGND` as two ports of what the layout extracts as ONE net (`GND|VGND|VSS` -- the shared p-substrate, which bulk sky130 offers no way to split), so a single promoted layout pin answers both reference ports and `matched` counts both. See `spec/decision-records/DR-012-analog-ground-pad.md`.
- devices: layout=871 reference=871 matched=804
- nets: layout=443 reference=444 matched=411
- mismatch categories:
  - `device.unmatched`: 67
  - `net.merged`: 11
  - `net.split`: 10
  - `topology.flattened`: 1
- capacitor device-class token (klayout-tools#1876): restored on 1032/1032 `C` cards (sky130_fd_pr__model__cap_mim) from `klt extract`'s own per-instance comment lines, into `sar_adc_top.extract.lvs.spice` -- the extractor's own `sar_adc_top.extract.spice` is kept unmodified alongside it. Without this, the SPICE round-trip this LVS shape depends on loses the capacitor class name and the same layout reports far more mismatches and far fewer matched nets -- measured on the pre-issue-#440 composition as 26 extra mismatches (124 vs 98) and 19 fewer matched nets (393 vs 412). Those two numbers are that one measurement, not a re-measurement of the layout in hand: this record's own verdict above is what describes THIS layout, and the point they make (the step is load-bearing, not a no-op) is unchanged by a composition that adds four more `C` cards.
- **known blocker: one, klayout-tools#1878** (klayout-tools#1513's pin-declaration blocker is resolved by `--pin-source-cells`; #1876's capacitor device-class regression is worked around locally, see the line above). `klt lvs`'s `options.combine_devices` is a single flag applied to the whole (flattened) compared netlist, with no per-subcircuit scoping. Three of the five already-independently-verified sub-blocks (comparator, sar_sequencer, seln_inverters) need it `true` to re-lump their own genuinely split/interleaved layout legs against their own lumped reference devices; the other two (cdac_array, sampling_frontend) need it `false` (cdac_array to avoid klayout-tools#1497's parallel-capacitor combine nondeterminism). klayout-tools#1552 (this repo's own report of exactly this gap) is closed upstream via #1556's new `options.combine_devices_per_circuit`, but that option does not actually help here: it can only scope a side that already has separate per-macro subcircuits, and `klt extract`'s layout-side output for a composed GDS is always one flat circuit (extraction still has no hierarchical mode, #1085) -- confirmed by direct measurement, filed generically as klayout-tools#1878. Neither the class-scoped `combine_devices: ["NFET","PFET"]` form (klayout-tools#1370) nor `klt lvs`'s inline-extraction shape substitutes for it (126 and 2199 mismatches respectively -- see run-flow.sh's own measured trace). This blocker is not a routing defect: the pin declaration and (per the connectivity table above) the physical routing are both independently confirmed correct.


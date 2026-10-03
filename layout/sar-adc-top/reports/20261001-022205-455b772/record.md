# SAR ADC top-level assembly record: 20261001-022205-455b772

## Provenance
- `klt` version: klt 0.6.0
- PDK: sky130A (open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b)
- repo commit: `455b77219e476df7b65bbb350856e6fc94feb730` (dirty)

## DRC (sky130 deck, composed top-level layout)
- **CLEAN** -- 0 violations

## Composition parity and matched pairs (issue #401)
- `bin/check-composition-parity.py`: **OK** -- every placed block, every net on every one of their pins, this assembly's own top-level port set and the composition `bin/generate-lvs-reference.py` emits are all derived from `design/sar_adc_top.spice`'s own top-level cards and asserted against it. Full output: `composition-parity.txt`.
- negative control (`--self-test`, a moved `SELp0` binding -- issue #387's own drift shape): **caught**.
  - blocks: cdac_array, comparator, halflsb_offset, sampling_frontend, sar_sequencer, top_glue
  - generated LVS reference wrapper: 4 positional sub-blocks, 33 std cells via top_glue, 8 primitives via halflsb_offset, 4 decoupling unit cards -- every net re-derived from design/sar_adc_top.spice
- DR-009 offset-cap top-plate legs: `TOP_N` 165.430 um, `TOP_P` 165.430 um (delta 0.0000 um, tolerance 0.01 um). The `_p` side injects nothing -- its only job is that both comparator top plates see the same capacitance and the same switch junction parasitics -- so `HALFLSB_OFFSET`'s own dx is solved for this equality rather than chosen.
- DR-009 dummy comparator load, as drawn top-level conductor: `COMP_OUT` 258.271 um^2, `OUTN_NC` 241.379 um^2 -- **imbalance 6.5%**, bound 10%. The GATE half of DR-009's match is identical by construction (the same two cell types on the same two input pins, asserted above); this is the WIRE half, which is this composition's own doing. `OUTN_NC` carries a solved matching extension of its own corridor column south to y = -155.0 um (its declared limit is -155.0 um, inside the existing extent) -- deliberate matching metal on the dummy, not on the live net. The residual cannot reach zero here: the two nets have different destinations, so their paths are mirror-shaped, not congruent. **DR-009's own Consequences section asks for a post-extraction re-run of `sim/full-conversion-transient/` as the electrical check, and that is not this flow's to run** -- this figure bounds the geometry, it does not stand in for that simulation.

## On-die supply decoupling (DR-017, placed by issue #440)
`klt gen cap_array` unit cell: 46.9 x 46.9 um `capm` plate, 1 device, bbox 47.9 x 48.82 um. Placed 4 times -- 2 per supply domain, which is how DR-017's `MF = 2` is drawn -- at `decap_a0` (128.0, 150.0), `decap_a1` (180.0, 150.0), `decap_d0` (196.0, -150.0), `decap_d1` (196.0, -98.0).

| quantity | value | share of the composed die |
| --- | --- | --- |
| composed bounding box | 290.500 x 386.200 um = 112191.100 um^2 | 100 % |
| `capm` plate area, both domains | 8798.44 um^2 | 7.84 % |
| placed cell footprint, both domains | 9353.91 um^2 | 8.34 % |

- Capacitance per domain: **8.870 pF** (2 x 4.435 pF), from the PDK's own `camimc`/`cpmimc` coefficients -- the same value `klt extract` reports for each placed unit, and the same one the LVS reference declares.
- MiM devices in the filtered extraction: **1034** (the composition's pre-existing 1028 CDAC/front-end unit caps, plus these 4).
- Decoupling capacitors as the compared netlist actually carries them (every `C` card both of whose terminals are supply nets):
  - `GND|VGND|VSS` <-> `VDD`: 2 x 4.434864e-12 F
  - `GND|VGND|VSS` <-> `VPB|VPWR`: 2 x 4.434864e-12 F
  `GND`, `VGND` and `cdac_array`'s own `VSS` extract as ONE net -- the shared p-substrate bulk sky130 offers no way to split, per `spec/decision-records/DR-012-analog-ground-pad.md` -- so both domains' return terminals land on that one name here. That is the same merge the LVS section's `net.merged` entries already track, not a new finding, and it is why the analog pair is the one that cannot correspond to a reference device (see that section).
- LVS mismatch entries naming a decoupling capacitor: 1.
  - `device.unmatched` (reference side): reference `DECAP_A0` / layout `\$2120`, class `SKY130_FD_PR__MODEL__CAP_MIM`.
  Each is the DR-012 substrate merge above reaching a device, not a new mismatch class: `GND` is on the reference side of an already-tracked `net.merged` entry, so no reference device with a `GND` terminal can correspond, and the analog pair has one. The digital pair, whose return port is `VGND` -- the name the comparer paired that merged layout net with -- does correspond.
- Series resistance of the ties, from `decap-ties.json` (lumped DC over drawn conductor only, at the PDK's own `rm2`/`rm3`/`rm4`/`rcvia2`/`rcvia3`/`rcvia4`; excludes each plate's own distributed resistance and all inductance):
  - `VDD (analog supply -> both top plates)`: **2.98 ohm** (shared 0.795, branches 3.842 / 5.064)
  - `GND (analog return -> both bottom plates)`: **4.192 ohm** (shared 3.486, branches 0.853 / 4.103)
  - `VPWR (digital supply -> both top plates)`: **3.605 ohm** (shared 1.641, branches 3.41 / 4.632)
  - `VGND (digital return -> both bottom plates)`: **3.258 ohm** (shared 2.585, branches 0.853 / 3.208)
  - **analog (VDD/GND) domain ESR: 7.172 ohm** at 8.870 pF -- Q = 2.048 at the 1221.5 MHz resonance that capacitance forms with DR-015's own 1.914 nH per-terminal package inductance, and the ESR equals the pair's own reactance at 2.502 GHz.
  - **digital (VPWR/VGND) domain ESR: 6.863 ohm** at 8.870 pF -- Q = 2.14 at the 1221.5 MHz resonance that capacitance forms with DR-015's own 1.914 nH per-terminal package inductance, and the ESR equals the pair's own reactance at 2.615 GHz.
  **What these ties' resistance is made of is vias, not metal**, at `rcvia2`/`rcvia3` = 3.41 ohm per cut against `rm2`/`rm4` = 0.125/0.047 ohm/sq on 2.0 um conductor. Each return path crosses three of those levels (the met4->met2 riser's two, plus the via2 into each plate) against each supply path's one. **Every via2/via3 the ties draw is a 2x2 array of 4 cuts** (issue #465), so each of those 8 sites (6 via2 + 2 via3 -- the two met4->met2 risers' two levels each, plus the four via2 plate entries) contributes 3.41/4 = 0.853 ohm instead of 3.41. That is drawn on measurement in both directions: issue #440 measured the single-cut ties at 13.837 / 13.448 ohm per domain with ~80 % of it in those cuts, and `sim/supply-impedance-sensitivity/records/20260926-183200-e8fa47c.md` then measured that the resistance COSTS die-side bounce (worst rail 12.135 -> 16.180 mV peak-to-peak, 1.333x, at `tt_27c_1.80v`) rather than usefully damping the package resonance.

  Three cuts in these paths are deliberately still single, which is why the reduction is ~1.95x rather than the ~3x issue #440 projected: each domain's two via4 landings off the met5 rails (`rcvia4` = 0.38 ohm/cut, and the 1.6 um rail cannot enclose a second cut across it) and -- the binding one -- **each `klt gen cap_array` unit cell's own centre via3 into `capm`**, 3.41 ohm, which this composer does not draw and cannot widen. That single cut is now the largest term in both supply ties, and moving it is a generator change. See README.md's "On-die decoupling (DR-017)".
- **DR-017's Decision §3 area budget is confirmed placeable, and costs no die area at all.** Its own schematic-level figure was 8798.44 um^2 of `capm` -- the same absolute area the table above reports, at 7.84 % of THIS composition's die rather than the 8.14 % it was of the pre-issue-#401 one (that denominator grew with the glue #401 composed, not with this allocation). Both sites fall inside the composed bounding box that assembly already had, so the allocation displaced no routing and grew no die. See `layout/sar-adc-top/README.md`, "On-die decoupling (DR-017)", for the met3/met4 occupancy measurement the two placements were chosen from.

## Connectivity verification (unfiltered extraction, by net)
`klt extract` with no declared-pin restriction, checked net-by-net against the intended interconnect in `layout/sar-adc-top/README.md` -- this is the direct evidence this issue's closing summary relies on, independent of the pin-declaration blocker below.

| Expected net | Found in (unfiltered) net name | OK? |
| --- | --- | --- |
| TOP_P | `TOP_P|VINP` | yes |
| TOP_N | `TOP_N|VINN` | yes |
| VDD (analog) | `VDD` | yes |
| VREFP | `VREFP` | yes |
| VREFN | `VREFN` | yes |
| VCM | `VCM` | yes |
| CLK | `A|CLK` | yes (see note) |
| CLKN | `CLK|CLKN|Y` | yes |
| COMP_OUT | `A1|COMP_OUT|OUTP` | yes |
| OUTN_NC | `A|A1|OUTN|OUTN_NC` | yes |
| SAMPLE_INT | `D|PH_SAMPLE|SAMPLE|Y` | yes |
| RST_B | `RESET_B|RST_B` | yes |
| BUSY | `A|B|BUSY|X` | yes |
| PH_B9 | `A|A_N|D|PH_B9|Q|S` | yes |
| DOUT0 | `A|A0|B|DOUT0|Q` | yes |
| DOUT1 | `A|A0|B|DOUT1|Q` | yes |
| DOUT2 | `A|A0|B|DOUT2|Q` | yes |
| DOUT3 | `A|A0|B|DOUT3|Q` | yes |
| DOUT4 | `A|A0|B|DOUT4|Q` | yes |
| DOUT5 | `A|A0|B|DOUT5|Q` | yes |
| DOUT6 | `A|A0|B|DOUT6|Q` | yes |
| DOUT7 | `A|A0|B|DOUT7|Q` | yes |
| DOUT8 | `A|A0|B|DOUT8|Q` | yes |
| DOUT9 | `A|A0|B|DOUT9|Q` | yes |
| SELp0 | `SELp0|X` | yes |
| SELp1 | `SELp1|X` | yes |
| SELp2 | `SELp2|X` | yes |
| SELp3 | `SELp3|X` | yes |
| SELp4 | `SELp4|X` | yes |
| SELp5 | `SELp5|X` | yes |
| SELp6 | `SELp6|X` | yes |
| SELp7 | `SELp7|X` | yes |
| SELp8 | `SELp8|X` | yes |
| SELn0 | `SELn0|X` | yes |
| SELn1 | `SELn1|X` | yes |
| SELn2 | `SELn2|X` | yes |
| SELn3 | `SELn3|X` | yes |
| SELn4 | `SELn4|X` | yes |
| SELn5 | `SELn5|X` | yes |
| SELn6 | `SELn6|X` | yes |
| SELn7 | `SELn7|X` | yes |
| SELn8 | `SELn8|X` | yes |
| HALF_LSB_EN | `A|HALF_LSB_EN|X` | yes |
| HALF_LSB_ENN | `HALF_LSB_ENN|Y` | yes |
| BOT_OFF_N | `BOT_OFF_N` | yes |
| BOT_OFF_P | `BOT_OFF_P` | yes |

- **CLK**: `A|CLK` is the single net promoted to this assembly's own top-level pin by `klt extract --pin-source-cells`. 4 unfiltered net names contain the label(s) `CLK` -- the other 3 (`A|CLK|X`, `CLK|CLKN|Y`, `CLK|X`) are internal nets of a sub-block that label their own copy of this signal (a label-name collision the flattened extraction exposes, not a split of the routed net).

**Nets that must be distinct** (issue #387's own failure mode: the pre-DR-008 composition satisfied every row above while `DOUT<i>` and `SELp<i>` were literally one net):

- all 30 pairs distinct: every `DOUT<i>`/`SELp<i>`, `DOUT<i>`/`SELn<i>` and `SELp<i>`/`SELn<i>` pair, plus `CLK`/`CLKN`, `COMP_OUT`/`OUTN_NC` and `HALF_LSB_EN`/`HALF_LSB_ENN`, resolves to a different extracted net. That is the direct, per-net evidence that this composition implements DR-008's derived switching polarity rather than issue #56's unconditional one.


## LVS (top-level layout vs. hierarchical reference)
- verdict: **mismatch**
- pins promoted from `--pin-source-cells`: layout=21 reference=22 matched=22 -- klayout-tools#1513 is resolved: every top-level pin label this flow draws promotes correctly. The layout count is BELOW the reference count by design, not by defect: since issue #362 the reference carries `GND` and `VGND` as two ports of what the layout extracts as ONE net (`GND|VGND|VSS` -- the shared p-substrate, which bulk sky130 offers no way to split), so a single promoted layout pin answers both reference ports and `matched` counts both. See `spec/decision-records/DR-012-analog-ground-pad.md`.
- devices: layout=1095 reference=1095 matched=1046
- nets: layout=554 reference=555 matched=519
- mismatch categories:
  - `device.unmatched`: 49
  - `net.merged`: 9
  - `net.split`: 8
  - `topology.flattened`: 1
- capacitor device-class token (klayout-tools#1876): restored on 1034/1034 `C` cards (sky130_fd_pr__model__cap_mim) from `klt extract`'s own per-instance comment lines, into `sar_adc_top.extract.lvs.spice` -- the extractor's own `sar_adc_top.extract.spice` is kept unmodified alongside it. Without this, the SPICE round-trip this LVS shape depends on loses the capacitor class name and the same layout reports far more mismatches and far fewer matched nets -- measured on the pre-issue-#440 composition as 26 extra mismatches (124 vs 98) and 19 fewer matched nets (393 vs 412). Those two numbers are that one measurement, not a re-measurement of the layout in hand: this record's own verdict above is what describes THIS layout, and the point they make (the step is load-bearing, not a no-op) is unchanged by a composition that adds four more `C` cards.
- **known blocker: one, klayout-tools#1878** (klayout-tools#1513's pin-declaration blocker is resolved by `--pin-source-cells`; #1876's capacitor device-class regression is worked around locally, see the line above). `klt lvs`'s `options.combine_devices` is a single flag applied to the whole (flattened) compared netlist, with no per-subcircuit scoping. Three of the six already-independently-verified sub-blocks (comparator, sar_sequencer, top_glue) need it `true` to re-lump their own genuinely split/interleaved layout legs against their own lumped reference devices; two of the others (cdac_array, sampling_frontend) need it `false` (cdac_array to avoid klayout-tools#1497's parallel-capacitor combine nondeterminism), and the sixth (halflsb_offset, whose eight cards are all `m = MF = 1`) has nothing to fold either way. klayout-tools#1552 (this repo's own report of exactly this gap) is closed upstream via #1556's new `options.combine_devices_per_circuit`, but that option does not actually help here: it can only scope a side that already has separate per-macro subcircuits, and `klt extract`'s layout-side output for a composed GDS is always one flat circuit (extraction still has no hierarchical mode, #1085) -- confirmed by direct measurement, filed generically as klayout-tools#1878. Neither the class-scoped `combine_devices: ["NFET","PFET"]` form (klayout-tools#1370) nor `klt lvs`'s inline-extraction shape substitutes for it (126 and 2199 mismatches respectively -- see run-flow.sh's own measured trace). This blocker is not a routing defect: the pin declaration and (per the connectivity table above) the physical routing are both independently confirmed correct.


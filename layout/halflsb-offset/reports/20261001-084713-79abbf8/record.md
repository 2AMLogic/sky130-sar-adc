# Half-LSB offset network layout record: 20261001-084713-79abbf8

Physical layout for DR-009 item 2's half-LSB quantizer-offset network (issue #495): the eight `sky130_fd_pr` primitives `design/sar_adc_top.spice` instantiates at its own top level, inside no sub-block, which had no drawn geometry anywhere under `layout/` before this block. Two `cap_mim_m3_1` offset caps (`Choff_n` and its matching dummy `Choff_p`) drawn as one `klt gen cap_array` matched pair, plus six `klt gen mos_array` switches (`Moff_{n,p}_{cmn,refp,cmp}`); the n-well islands, the substrate ties, the floorplan and all routing come from `layout/halflsb-offset/bin/build_layout.py`. `layout/top-glue/` covers the 33 `sky130_fd_sc_hd` instances of the same region; composing both into `layout/sar-adc-top/` is issue #401 and is NOT claimed here.

## Overall verdict: PASS

- [x] `bin/check-schematic-parity.py` agrees with `design/sar_adc_top.spice`'s own eight top-level primitive cards
- [x] every `klt gen` block is DRC-clean in isolation
- [x] `klt drc --deck sky130` on the composed layout is clean
- [x] DRC negative control: the deliberately-illegal n-well fixture reports violations naming `nwell.space.1` on that same deck
- [x] `klt precheck` passes outright on the layout's own 1 nm database grid
- [x] `klt precheck` passes outright on sky130's 5 nm MANUFACTURING grid too -- no off-grid shape on any layer, MiM stack included
- [x] extraction reports the schematic's exact device population ({'nfet': 2, 'pfet': 4, 'sky130_fd_pr__model__cap_mim': 2})
- [x] extraction reports no single-terminal net (every drawn terminal reaches the net the schematic puts it on)
- [x] extraction reports no unbiased PMOS body net, and every PFET body on `VDD`
- [x] LVS matches the schematic-derived reference
- [x] every matched net's layout name equals its reference name (the port-permutation guard -- see verdict 13)
- [x] LVS negative controls (device-parameter corruption; capacitor top-plate net corruption) both report mismatch
- [x] swapped-enable control reproduces its documented blind spot: `klt lvs` reports `match`, while that run's own net correspondence is NOT name-identical
- [x] `build_layout.py`'s `_n`/`_p` translation congruence held (16.0 um, checked in DBU)

## Provenance

- `klt` version: klt 0.6.0
- KLayout engine: 0.30.12
- PDK: sky130A (open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b)
- PDK root: resolved via `PDK_ROOT environment variable`
- repo commit: `79abbf82c5507b8724795198078c326771772984` on `feature/issue-498` (dirty working tree)
- DRC deck: `sky130` (sha256:a1d90e066e822d0a8f36e2d4f4969b83df4360692f689b5815be9c3f151f7c8e)
- deliverable: `halflsb_offset.gds`

## Schematic parity (the independent anchor)

This block's LVS reference is *generated from* `design/sar_adc_top.spice`, so the reference side is anchored to the schematic by construction. The layout side is not: `bin/gen_blocks.py`'s device table is hand-transcribed. `bin/check-schematic-parity.py` is what closes that, device by device and terminal by terminal, before this record directory is created -- and again here, as the verdict above. Its own output, verbatim:

```
check-schematic-parity.py: OK -- 8 instances, 3 device types, 12 nets, every terminal net identical to design/sar_adc_top.spice
  cap_mim: 2
  nfet: 2
  pfet: 4
  drawn MiM plate side 1.9 um == layout/cdac-array/bin/cdac_layout.py's CAPM_SIDE
  not this block's: XCdecap_a -> layout/sar-adc-top/ -- DR-017's analog-domain on-die decoupling cap (GND/VDD), drawn by that block's own build_layout.py
  not this block's: XCdecap_d -> layout/sar-adc-top/ -- DR-017's digital-domain on-die decoupling cap (VGND/VPWR), ditto
```

## What `klt lvs` cannot see on this block

`klt lvs` reaches a clean `match` against the `swapped-enable` negative control -- a reference identical to the good one except that `HALF_LSB_EN` and `HALF_LSB_ENN` are exchanged on the working side's three gates, i.e. DR-009's load-bearing enable polarity inverted. `NetlistComparer` matches nets structurally rather than by name, and both enables enter this network only as ports, so the exchange is a legitimate isomorphism.

That is measured here, not argued: this run's own `lvs.swapped-enable.json` reports `status: match` with mismatch_count=1. What it also reports, in the same envelope, is a net correspondence that is no longer name-identical: ['HALF_LSB_ENN <-> HALF_LSB_EN', 'HALF_LSB_EN <-> HALF_LSB_ENN']. Verdict 11 above grades exactly that field on the GOOD run, which is what turns this defect class back into a failure.

## `_n` / `_p` matching, as a construction property

DR-009's `_p` half is a matching dummy: it injects nothing and exists only so both comparator inputs carry the same capacitance and the same switch junction parasitics. Neither DRC nor LVS can see whether it actually matches -- a layout that scattered the `_p` devices would be clean and would match. So `build_layout.py` asserts it instead: every shape the `_p` side owns below the track band is the corresponding `_n`-side shape translated by exactly 16.0 um, checked in integer nanometres.

- shapes per side covered by the assertion: 41
- met1 columns per side: 13
- the two caps are one `klt gen cap_array num=2` call, unit pitch 16.0 um (asserted equal to the side translation), so their own geometry is identical by the generator's construction rather than by this assertion
- residual asymmetry, which the assertion deliberately excludes: the per-net met1 risers above y = 11.33 um, where each net owns one track. 4.0 um of length difference in total (1.2 um^2 of 0.30 um met1) across the 4 matched net pairs, which `TRACK_ORDER` holds to adjacent tracks for exactly this reason

| Side | group origin (um) | n-well island (um) | VDD tap (um) | GND tap (um) | met1 riser total (um) |
| --- | --- | --- | --- | --- | --- |
| `_n` | 0.0 | 7.89..14.63 x -2.4..3.37 | 8.59..9.19 | 3.4..4.0 | 154.29 |
| `_p` | 16.0 | 23.89..30.63 x -2.4..3.37 | 24.59..25.19 | 19.4..20.0 | 158.29 |

n-well island separation drawn: 9.26 um against sky130's `nwell.2a` minimum of 1.27 um. Both islands tap `VDD`: every `XMoff_*` PFET card declares `VDD` as its body, so unlike `layout/sampling-frontend/`'s DR-007 partition there is no multi-domain body-tie question here -- the two islands exist because the NFET between them may not sit in an n-well, not because they are different nets.

## The offset capacitor

DR-009 sizes `Choff_{n,p}` identical to `design/cdac/cdac_unit_cell.sch`'s own `C_u`. The cards ask for W = L = 1.9 um, which is off the 1 nm database grid; the drawn plate is 1.9 um -- the value `layout/cdac-array/bin/cdac_layout.py` already draws for every one of its 1024 array units, which `bin/check-schematic-parity.py` reads out of that file and asserts. The half-LSB step is a *ratio* against one array bit, so matching the sibling's drawn plate matters more than rounding 1900.0 nm to the nearer grid point.

Reference capacitance: 8.664000000e-15 F per unit, from the drawn plate under the extraction deck's own published tt coefficients -- derived from geometry, never read back out of an extraction result.

## Blocks (`klt gen`)

| Block | Cell | Devices | bbox (um) | own DRC |
| --- | --- | --- | --- | --- |
| `moff_n_cmn` | `MOFF_N_CMN` | 1 | 0.0,0.0 .. 1.09,1.82 | clean |
| `moff_n_refp` | `MOFF_N_REFP` | 1 | -0.15,-0.15 .. 1.24,2.97 | clean |
| `moff_n_cmp` | `MOFF_N_CMP` | 1 | -0.15,-0.15 .. 1.24,2.97 | clean |
| `moff_p_cmn` | `MOFF_P_CMN` | 1 | 0.0,0.0 .. 1.09,1.82 | clean |
| `moff_p_refp` | `MOFF_P_REFP` | 1 | -0.15,-0.15 .. 1.24,2.97 | clean |
| `moff_p_cmp` | `MOFF_P_CMP` | 1 | -0.15,-0.15 .. 1.24,2.97 | clean |
| `choff` | `CHOFF` | 2 | 0.0,0.0 .. 18.900000000000002,3.8200000000000003 | clean |

## Composition

- `klt draw` (cell `ROUTE`): 172 shapes, 12 pin labels (two n-well islands, four taps, every wire)
- `klt gen-compose` (cell `gen_compose_0`): 8 blocks placed at explicit origins, bbox {'x0': -0.4, 'y0': -2.4, 'x1': 30.63, 'y1': 17.04}
- `klt gen-compose` is used as a **placer only** (no `routing` block in the request), the same choice every full-custom sibling documents.
- `klt gen-compose` emitted 13 placement warnings, in two expected classes (7 citing `choff`'s hint, 6 citing a `moff_*` block's, 0 neither):
  - **7** cite the cap pair: `klt gen cap_array` reports the requested inter-unit `spacing_um` as its own `drc_hints.min_spacing_um`, so a matched pair deliberately spaced 16.0 um apart makes every block placed inside that span look like a spacing violation.
  - **6** cite a `moff_*` switch: the `route` cell carries the licon/met1 that CONTACTS each device's own ports, so it is placed at 0.00 um from every one of them by construction -- a `min_spacing_um` hint cannot distinguish an abutting contact cell from an unrelated neighbour.
  - Neither is a rule minimum and `klt drc` on the composed layout is clean. Both are the same tool gap -- one `min_spacing_um` field for two unrelated meanings -- filed generically upstream as klayout-tools#2638 (see `../README.md`, "Upstream filings").
- track band starts at y = 11.33 um, above the cap pair's own met4 escape at y = 9.62 um

## Results

| Stage | Status | Detail |
| --- | --- | --- |
| DRC, curated deck (composed layout) | clean | violation_count=0, rule_counts={} |
| DRC, curated deck (illegal n-well fixture) | violations | violation_count=2, rule_counts={'nwell.space.1': 1, 'nwell.width.1': 1} |
| precheck, 1 nm database grid | pass | 5 checks, 0 failed |
| precheck, 5 nm manufacturing grid | pass | failing checks [], 0 off-grid shapes |
| Extract | extracted | device_count=8 {'nfet': 2, 'pfet': 4, 'sky130_fd_pr__model__cap_mim': 2}, net_count=12, pin_count=12, unbiased_pmos_body_nets=0, single_terminal_nets=0 |
| LVS (schematic-derived reference) | match | devices 8/8 matched, nets 12/12 matched, pins 12/12 matched |
| LVS (device-parameter negative control) | mismatch | mismatch_count=6, categories={'device.property': 5, 'topology': 1} |
| LVS (capacitor top-plate negative control) | mismatch | mismatch_count=4, categories={'device.unmatched': 1, 'topology': 3} |
| LVS (swapped-enable, EXPECTED to match negative control) | match | mismatch_count=1, categories={'topology': 1} |

## Off-grid census (5 nm manufacturing grid)

Recorded rather than hidden, and **empty since issue #498**. Every coordinate this flow *chooses* was always snapped to the 5 nm grid (`build_layout.GRID_UM`); what it could not choose was the MiM plate side, which DR-009 requires to be identical to `design/cdac/cdac_unit_cell.sch`'s `C_u`. That plate was 1898 nm on a side -- not a multiple of 5 -- so neither its own edges nor the port coordinates nor the vias and landing pads derived from them could sit on the manufacturing grid, and the census stood at 48 shapes (`reports/20260930-231954-70fdc06/`). DR-019 (#496) resized `C_u` to a 5 nm-grid-legal 1.9000 um and #498 carried that through both this block and `layout/cdac-array/`; the census went to 0. Verdict 6 was inverted to require an outright pass rather than a confined residual.

| Cell | Layer | Off-grid shapes |
| --- | --- | --- |
| (none) | | 0 |

## DRC coverage (what the deck did and did not check)

Recorded straight from `klt drc`'s own `coverage` block rather than asserted in prose, so a later deck release changing it shows up as a diff in the next record.

- rule families in scope: ['cap2m', 'capm', 'ct', 'difftap', 'li', 'licon', 'm1', 'm2', 'm3', 'm4', 'm5', 'nwell', 'poly', 'via', 'via2', 'via3', 'via4']
- layers checked: ['64/20', '65/20', '66/20', '66/44', '67/20', '67/44', '68/20', '68/44', '69/20', '69/44', '70/20', '70/44', '71/20', '89/44']
- layers present in the stream with **no** rule: ['65/44', '69/5']
- rules skipped (layer absent from the stream): ['capm2.enclosing.via4.1', 'capm2.separation.via4.1', 'capm2.space.1', 'capm2.width.1', 'met4.enclosing.capm2.1', 'met4.enclosing.via4.1', 'met5.area.1', 'met5.enclosing.via4.1', 'met5.holes_area.1', 'met5.space.1', 'met5.width.1', 'via4.space.1', 'via4.width.1']

## Net correspondence (layout <-> reference)

- `BOT_OFF_N` <-> `BOT_OFF_N` (pin)
- `BOT_OFF_P` <-> `BOT_OFF_P` (pin)
- `GND` <-> `GND` (pin)
- `HALF_LSB_EN` <-> `HALF_LSB_EN` (pin)
- `HALF_LSB_ENN` <-> `HALF_LSB_ENN` (pin)
- `TOP_N` <-> `TOP_N` (pin)
- `TOP_P` <-> `TOP_P` (pin)
- `VCM` <-> `VCM` (pin)
- `VDD` <-> `VDD` (pin)
- `VGND` <-> `VGND` (pin)
- `VPWR` <-> `VPWR` (pin)
- `VREFP` <-> `VREFP` (pin)

## Reported LVS findings (good reference)

- [warning] topology: device class has no counterpart on the other side, but no devices of this class were extracted either -- not a real topology mismatch

Every finding above is reported at `severity: warning` with `error_count = 0`; `klt lvs`'s own overall verdict for this run is `match`.


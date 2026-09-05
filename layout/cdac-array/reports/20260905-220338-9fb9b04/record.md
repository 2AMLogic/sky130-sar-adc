# CDAC array layout record: 20260905-220338-9fb9b04

## Provenance
- `klt` version: klt 0.4.0
- xschem version: XSCHEM V3.4.7
- PDK variant: sky130A
- repo commit: `9fb9b04d381d544b0676cc1091cb8d36c587db60` (dirty)

## Drawn geometry
- unit capacitance (derived from the drawn plate): 8.647287999999999e-15 F
- unit capacitors drawn: 1024
- units per bottom-plate net: `BOT_n0`=1, `BOT_n1`=2, `BOT_n2`=4, `BOT_n3`=8, `BOT_n4`=16, `BOT_n5`=32, `BOT_n6`=64, `BOT_n7`=128, `BOT_n8`=256, `BOT_p0`=1, `BOT_p1`=2, `BOT_p2`=4, `BOT_p3`=8, `BOT_p4`=16, `BOT_p5`=32, `BOT_p6`=64, `BOT_p7`=128, `BOT_p8`=256, `VREFN`=2

## `cdac_unit_cell`
- DRC (sky130 deck): **CLEAN** (0 violations)
- extraction: 3 devices {'nfet': 1, 'pfet': 1, 'sky130_fd_pr__model__cap_mim': 1}, 7 nets, 7 pins
- LVS vs. `design/cdac/cdac_unit_cell.sch`: **MATCH**
  - devices: layout=3 reference=3 matched=3
  - nets: layout=7 reference=7 matched=7

## `cdac_array`
- DRC (sky130 deck): **CLEAN** (0 violations)
- extraction: 1060 devices {'nfet': 18, 'pfet': 18, 'sky130_fd_pr__model__cap_mim': 1024}, 42 nets, 24 pins
- LVS vs. `design/cdac/cdac_array.sch`: **MATCH**
  - devices: layout=1060 reference=1060 matched=1060
  - nets: layout=42 reference=42 matched=42

## Unit-element check
Since issue #148, `klt lvs`'s own comparison (verdict 4, above) is already literal and uncombined -- it compares this array's 1024 drawn unit capacitors against 1024 reference unit cards 1:1, with no `combine_devices` folding on either side, so an LVS match alone already implies the array is built from exactly 1024 unit elements. This is therefore a redundant, but cheap and independent, confirmation of the same fact from the extraction side alone:
- expected: `{'sky130_fd_pr__model__cap_mim': 1024, 'nfet': 18, 'pfet': 18}`
- extracted: `{'nfet': 18, 'pfet': 18, 'sky130_fd_pr__model__cap_mim': 1024}` -- **OK**

## Common-centroid check
Per-net unit-capacitor centroid, in um, relative to the array's own geometric centre. A linear process gradient across the array is cancelled exactly when a bit's centroid sits on that centre; a differential gradient between the two sides is cancelled when a bit's P and N centroids coincide.

| net | units | dx (um) | dy (um) |
| --- | ---: | ---: | ---: |
| `term_n` | 1 | +1.700 | +22.100 |
| `BOT_n0` | 1 | +1.700 | -22.100 |
| `BOT_n1` | 2 | +1.700 | +0.000 |
| `BOT_n2` | 4 | +1.700 | +0.000 |
| `BOT_n3` | 8 | -1.700 | +0.000 |
| `BOT_n4` | 16 | +0.000 | +0.000 |
| `BOT_n5` | 32 | +0.000 | -0.000 |
| `BOT_n6` | 64 | +0.000 | -0.000 |
| `BOT_n7` | 128 | +0.000 | +0.000 |
| `BOT_n8` | 256 | +0.000 | +0.000 |
| `term_p` | 1 | +1.700 | +25.500 |
| `BOT_p0` | 1 | +1.700 | -25.500 |
| `BOT_p1` | 2 | +1.700 | +0.000 |
| `BOT_p2` | 4 | +1.700 | +0.000 |
| `BOT_p3` | 8 | -1.700 | -0.000 |
| `BOT_p4` | 16 | +0.000 | -0.000 |
| `BOT_p5` | 32 | +0.000 | +0.000 |
| `BOT_p6` | 64 | +0.000 | +0.000 |
| `BOT_p7` | 128 | +0.000 | +0.000 |
| `BOT_p8` | 256 | +0.000 | +0.000 |

Residuals, all of them deliberate and documented in `layout/cdac-array/README.md`: bit3 and the bit2/bit1/bit0/termination group each own a single, unsplittable column, so their X centroids sit half a column pitch either side of the centre (equal and opposite, so the *side total* is still centred); and bit0 and the termination unit are single units per side, so their P/N pair is one row pitch apart in Y rather than coincident.

## Verdicts
- [x] cdac_unit_cell: DRC clean (0)
- [x] cdac_unit_cell: LVS match (match)
- [x] cdac_array: DRC clean (0)
- [x] cdac_array: LVS match (match)
- [x] cdac_array: 1024 unit caps + 18 nfet + 18 pfet extracted ({'nfet': 18, 'pfet': 18, 'sky130_fd_pr__model__cap_mim': 1024})
- [x] bits 8..1: Y centroid on the array centre (|dy| < 1e-6 um)
- [x] bits 8..4: X centroid on the array centre (|dx| < 1e-6 um)
- [x] bits 8..0: P and N X centroids coincide (|dx_p - dx_n| < 1e-6 um)

Matching quality is **not** among the verdicts above and cannot be: DRC and LVS are silent about it. See `layout/cdac-array/README.md` for the common-centroid/dummy strategy this layout implements, what it cancels, and what it does not.

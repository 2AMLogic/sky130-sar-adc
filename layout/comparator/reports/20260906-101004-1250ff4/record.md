# Comparator layout record: 20260906-101004-1250ff4

Physical layout for the dynamic (StrongARM-class) comparator sub-block of this SAR ADC (issue #101), drawn against `design/comparator.sch`. Devices come from `klt gen`'s matched `diff_pair`/`mos_array` generators (see `layout/comparator/bin/gen_blocks.py` for the matching strategy); placement and every wire come from `layout/comparator/bin/build_layout.py`, verified here against the sky130 DRC deck and the schematic-derived LVS reference.

## Overall verdict: PASS

- [x] every `klt gen` matched device/pair block is DRC-clean in isolation
- [x] DRC on the composed comparator layout is clean
- [x] LVS matches the known-good reference
- [x] LVS negative control (device-parameter corruption) reports mismatch
- [x] LVS negative control (topology corruption) reports mismatch
- [x] extraction reports no unbiased PMOS body net (the drawn n-well tie really biases every PMOS body)

## Provenance

- `klt` version: klt 0.4.0
- KLayout engine: 0.30.12
- PDK: sky130A (open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b)
- PDK root: resolved via `PDK_ROOT environment variable`
- repo commit: `1250ff4e57bd982bcfdf248f09bb51b7edb784b6` on `feature/issue-180` (dirty working tree)
- DRC deck: `sky130` (sha256:5afac7ab8561545859f5e2e74f4621c6ffc052756dc8fe344ea263398e96b240)

## Blocks (`klt gen`)

| Block | Cell | Devices | bbox (um) | own DRC |
| --- | --- | --- | --- | --- |
| `tail` | `TAIL` | 1 | 0.0,0.0 .. 1.34,8.82 | clean |
| `inpair` | `INPAIR` | 4 | 0.0,0.0 .. 3.08,6.04 | clean |
| `latn` | `LATN` | 2 | 0.0,0.0 .. 1.34,10.040000000000001 | clean |
| `latp` | `LATP` | 2 | -0.15,-0.15 .. 1.49,18.19 | clean |
| `rst` | `RST` | 2 | -0.15,-0.15 .. 1.49,34.19 | clean |

## Routing + composition

- `klt draw` (cell `ROUTE`): 239 shapes, 7 pin labels
- `klt gen-compose` (cell `gen_compose_0`): 7 blocks placed at explicit origins, bbox {'x0': 0.0, 'y0': 2.5, 'x1': 26.6, 'y1': 38.65}
- `klt gen-compose` is used as a **placer only** here (no `routing` block in the request) -- see `build_layout.py`'s module docstring, and 2AMLogic/klayout-tools#1386 for the generically-filed tool gap that motivates it.

## Results

| Stage | Status | Detail |
| --- | --- | --- |
| DRC (composed layout) | clean | violation_count=0, rule_counts={} |
| Extract | extracted | device_count=13, net_count=10, pin_count=7, unbiased_pmos_body_nets=0 |
| LVS (good reference) | match | devices 11/11 matched, nets 10/10 matched, pins 7/7 matched |
| LVS (device-parameter negative control) | mismatch | mismatch_count=8, categories={'device.property': 5, 'topology': 3} |
| LVS (topology negative control) | mismatch | mismatch_count=3, categories={'device.unmatched': 1, 'topology': 2} |

## Differential routing symmetry

Device matching alone does not fix a dynamic comparator's offset: its decision is a race between OUTP and OUTN, so unequal wire capacitance on the two output nodes biases that race the same way a device mismatch would. `build_layout.py` routes each negative-half branch on the mirror image of its positive-half counterpart's own y-track where that track is free (see its `MIRROR_PIN`), and the numbers below are what that actually achieved -- measured from the drawn geometry, not asserted. They are *not* a parasitic extraction; wire area is a proxy for wire capacitance, and a real `klt pex` pass on this sub-block would supersede them.

| Pair | wire area (um^2) | delta | imbalance |
| --- | --- | --- | --- |
| OUTP / OUTN | 14.487 / 14.082 | 0.405 um^2 | 2.84% |
| VINN / VINP | 2.493 / 2.913 | 0.42 um^2 | 15.54% |
| DIP / DIN | 10.824 / 11.574 | 0.75 um^2 | 6.7% |

Per-net wiring:

| Net | met1 (um^2) | met2 (um^2) | vias | mcons |
| --- | --- | --- | --- | --- |
| CLK | 8.865 | 15.57 | 9 | 5 |
| DIN | 6.744 | 4.83 | 6 | 4 |
| DIP | 7.044 | 3.78 | 6 | 4 |
| GND | 0.663 | 0.09 | 2 | 2 |
| OUTN | 5.202 | 8.88 | 7 | 5 |
| OUTP | 5.307 | 9.18 | 7 | 5 |
| TAIL | 3.537 | 1.29 | 5 | 5 |
| VDD | 6.174 | 7.62 | 11 | 7 |
| VINN | 1.653 | 0.84 | 2 | 2 |
| VINP | 1.623 | 1.29 | 2 | 2 |

## Net correspondence (layout <-> reference)

- `CLK` <-> `CLK` (pin)
- `\$3` <-> `DIN` (internal)
- `\$2` <-> `DIP` (internal)
- `GND` <-> `GND` (pin)
- `OUTN` <-> `OUTN` (pin)
- `OUTP` <-> `OUTP` (pin)
- `\$7` <-> `TAIL` (internal)
- `VDD` <-> `VDD` (pin)
- `VINN` <-> `VINN` (pin)
- `VINP` <-> `VINP` (pin)

## Reported LVS findings

- [warning] topology: device class has no counterpart on the other side, but no devices of this class were extracted either -- not a real topology mismatch

Every finding above is reported at `severity: warning` with `error_count = 0`; `klt lvs`'s own overall verdict for this run is `match`.


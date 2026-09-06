# Sampling front end n-well isolation record: 20260906-230044-0904419

Physical composition of the sampling front end's PFET set into **three electrically distinct n-well islands** (issue #122), drawn against `design/sampling_frontend.sch` and its DR-004 body-tie requirement: `Sa_p`/`Se_p` tie their body to `BOOST_P`, `Sa_n`/`Se_n` to `BOOST_N`, and the remaining five PFETs to `VDD`. Devices come from `klt gen mos_array`; the well partition, the taps and every wire come from `layout/sampling-frontend-wells/bin/build_layout.py`.

## Overall verdict: PASS

- [x] every `klt gen` PFET block is DRC-clean in isolation
- [x] `klt drc --deck sky130` on the composed layout is clean (as of klt 0.4.0, this includes the n-well isolation verdict: nwell.width.1 / nwell.space.1 are part of the curated deck)
- [x] DRC negative control: the same curated deck reports violations naming `nwell.space.1` on a deliberately-illegal well split
- [x] `klt precheck` passes (geometry hygiene; every pin label lands on drawn metal)
- [x] extraction reports no unbiased PMOS body net
- [x] extraction reports every PFET body on its own n-well island's tap net (Sa/Se -> BOOST_P/BOOST_N, the rest -> VDD)
- [x] LVS matches the known-good reference
- [x] LVS negative control (body-tie corruption: Sa/Se bodies moved to VDD) reports mismatch
- [x] LVS negative control (device-parameter corruption) reports mismatch

## Provenance

- `klt` version: klt 0.4.0
- KLayout engine: 0.30.12
- PDK: sky130A (open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b)
- PDK root: resolved via `PDK_ROOT environment variable`
- repo commit: `09044191cdd163518f2651e6f640d98bb130103a` on `feature/issue-208` (dirty working tree)
- curated DRC deck: `sky130` (sha256:5afac7ab8561545859f5e2e74f4621c6ffc052756dc8fe344ea263398e96b240) -- as of klt 0.4.0 this deck alone carries the n-well isolation rules (nwell.width.1 / nwell.space.1); see #149

## The n-well partition (the deliverable)

One drawn `nwell` rectangle per body-tie domain, each merging only its own devices' generator-drawn local wells and each holding one `tap` routed to that domain's net. `nwell.2a` (sky130's minimum n-well spacing) is 1.27 um; the drawn separation is 1.6 um.

| Island | tap net | schematic devices | n-well x range (um) | tap (um) |
| --- | --- | --- | --- | --- |
| `boost_p` | **BOOST_P** | Sa_p, Se_p | 0.0 .. 6.74 | 0.4..1.0 x -1.8..-0.6 |
| `vdd` | **VDD** | Scp_p, Cmswp_p, Invp, Cmswp_n, Scp_n | 8.34 .. 24.68 | 8.74..9.34 x -1.8..-0.6 |
| `boost_n` | **BOOST_N** | Se_n, Sa_n | 26.28 .. 33.27 | 26.68..27.28 x -1.8..-0.6 |

Island-to-island gaps: [1.6, 1.6] um.

## Extracted body terminals

`klt extract --deck sky130` derives a PMOS body from the `nwell` island the device actually sits in, named by whatever the tap inside that island is routed to. No `nwell.pin` (64/5) well label is drawn anywhere in this layout, deliberately: a drawn label would name the well even if the tap routing were broken, which would make this table a tautology instead of a measurement.

| Schematic device | island | expected body | extracted body | |
| --- | --- | --- | --- | --- |
| `Sa_p` | `boost_p` | BOOST_P | BOOST_P | OK |
| `Se_p` | `boost_p` | BOOST_P | BOOST_P | OK |
| `Scp_p` | `vdd` | VDD | VDD | OK |
| `Cmswp_p` | `vdd` | VDD | VDD | OK |
| `Invp` | `vdd` | VDD | VDD | OK |
| `Cmswp_n` | `vdd` | VDD | VDD | OK |
| `Scp_n` | `vdd` | VDD | VDD | OK |
| `Se_n` | `boost_n` | BOOST_N | BOOST_N | OK |
| `Sa_n` | `boost_n` | BOOST_N | BOOST_N | OK |

`unbiased_pmos_body_nets`: 0 entries.

## Blocks (`klt gen mos_array`)

| Block | Cell | Devices | bbox (um) | own DRC |
| --- | --- | --- | --- | --- |
| `sa_p` | `SA_P` | 1 | -0.15,-0.15 .. 1.49,1.97 | clean |
| `se_p` | `SE_P` | 1 | -0.15,-0.15 .. 1.24,1.97 | clean |
| `scp_p` | `SCP_P` | 1 | -0.15,-0.15 .. 1.24,1.97 | clean |
| `cmswp_p` | `CMSWP_P` | 1 | -0.15,-0.15 .. 1.24,1.97 | clean |
| `invp` | `INVP` | 1 | -0.15,-0.15 .. 1.24,2.97 | clean |
| `cmswp_n` | `CMSWP_N` | 1 | -0.15,-0.15 .. 1.24,1.97 | clean |
| `scp_n` | `SCP_N` | 1 | -0.15,-0.15 .. 1.24,1.97 | clean |
| `se_n` | `SE_N` | 1 | -0.15,-0.15 .. 1.24,1.97 | clean |
| `sa_n` | `SA_N` | 1 | -0.15,-0.15 .. 1.49,1.97 | clean |

## Composition

- `klt draw` (cell `ROUTE`): 179 shapes, 14 pin labels (the three n-well islands, their taps, every wire)
- `klt gen-compose` (cell `gen_compose_0`): 10 blocks placed at explicit origins, bbox {'x0': 0.0, 'y0': -2.4, 'x1': 33.57, 'y1': 10.85}
- `klt gen-compose` is used as a **placer only** (no `routing` block in the request), the same choice `layout/comparator/` documents.

## Results

| Stage | Status | Detail |
| --- | --- | --- |
| DRC, curated deck (composed layout) | clean | violation_count=0, rule_counts={} -- includes the n-well isolation rules as of klt 0.4.0 |
| DRC, curated deck (illegal well-split fixture) | violations | violation_count=2, rule_counts={'nwell.space.1': 1, 'nwell.width.1': 1} -- negative control for the row above |
| precheck | pass | 5 checks, 0 failed |
| Extract | extracted | device_count=9, net_count=14, pin_count=14, unbiased_pmos_body_nets=0 |
| LVS (good reference) | match | devices 9/9 matched, nets 14/14 matched, pins 14/14 matched |
| LVS (body-tie negative control) | mismatch | mismatch_count=14, categories={'device.unmatched': 4, 'net.unmatched': 8, 'topology': 2} |
| LVS (device-parameter negative control) | mismatch | mismatch_count=7, categories={'device.property': 5, 'topology': 2} |

## Net correspondence (layout <-> reference)

- `BOOST_N` <-> `BOOST_N` (pin)
- `BOOST_P` <-> `BOOST_P` (pin)
- `BPREF_N` <-> `BPREF_N` (pin)
- `BPREF_P` <-> `BPREF_P` (pin)
- `BSBOT_N` <-> `BSBOT_N` (pin)
- `BSBOT_P` <-> `BSBOT_P` (pin)
- `G_N` <-> `G_N` (pin)
- `G_P` <-> `G_P` (pin)
- `SAMPLE` <-> `SAMPLE` (pin)
- `SAMPLEB` <-> `SAMPLEB` (pin)
- `VCM` <-> `VCM` (pin)
- `VDD` <-> `VDD` (pin)
- `VINN` <-> `VINN` (pin)
- `VINP` <-> `VINP` (pin)

## Reported LVS findings (good reference)

- [warning] topology: device class has no counterpart on the other side, but no devices of this class were extracted either -- not a real topology mismatch
- [warning] topology: device class has no counterpart on the other side, but no devices of this class were extracted either -- not a real topology mismatch

Every finding above is reported at `severity: warning` with `error_count = 0`; `klt lvs`'s own overall verdict for this run is `match`.


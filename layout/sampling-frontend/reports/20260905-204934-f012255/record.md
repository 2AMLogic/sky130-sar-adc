# Sampling front end layout record: 20260905-204934-f012255

Physical layout for the sampling front end sub-block of this SAR ADC (issue #99), drawn against `design/sampling_frontend.sch`: eleven NFETs (including the `Msw_p`/`Msw_n` input switch pair), nine PFETs partitioned into the three isolated n-well body-tie domains DR-004 / DR-007 require, and four MiM capacitors, plus every wire between them. Devices come from `klt gen mos_array`/`klt gen cap_array`; the well partition, the substrate tap, the floorplan and all routing come from `layout/sampling-frontend/bin/build_layout.py`.

## Overall verdict: PASS

- [x] every `klt gen` block is DRC-clean in isolation
- [x] `klt drc --deck sky130` on the composed layout is clean
- [x] DRC negative control: the deliberately-illegal n-well fixture reports violations naming `nwell.space.1` on that same deck
- [x] `klt precheck` passes (geometry hygiene; every pin label lands on drawn metal)
- [x] extraction reports the schematic's exact device population ({'nfet': 11, 'pfet': 9, 'sky130_fd_pr__model__cap_mim': 4})
- [x] extraction reports no single-terminal net (every drawn terminal reaches the net the schematic puts it on)
- [x] extraction reports no unbiased PMOS body net
- [x] extraction reports every PFET body on its own n-well island's tap net (Sa/Se -> BOOST_P/BOOST_N, the rest -> VDD)
- [x] LVS matches the known-good reference
- [x] LVS negative control (body-tie corruption: the four boosted bodies moved to VDD) reports mismatch
- [x] LVS negative controls (device-parameter corruption; capacitor top-plate net corruption) both report mismatch

## Provenance

- `klt` version: klt 0.4.0
- KLayout engine: 0.30.12
- PDK: sky130A (open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b)
- PDK root: resolved via `PDK_ROOT environment variable`
- repo commit: `f012255a2f22964c3e7aece39b1a0404ef15c60e` on `feature/issue-99` (dirty working tree)
- DRC deck: `sky130` (sha256:5afac7ab8561545859f5e2e74f4621c6ffc052756dc8fe344ea263398e96b240)
- deliverable: `sampling_frontend.gds`

## The n-well partition (DR-004 / DR-007)

One drawn `nwell` rectangle per body-tie domain, each merging only its own devices' generator-drawn local wells and each holding one `tap` routed to that domain's net -- the recipe issue #122 proved in `layout/sampling-frontend-wells/`, reused here unchanged. `nwell.space.1` (sky130's minimum n-well spacing) is 1.27 um; the drawn separation is 1.6 um.

| Island | tap net | schematic devices | n-well x range (um) | tap (um) |
| --- | --- | --- | --- | --- |
| `boost_p` | **BOOST_P** | Sa_p, Se_p | 0.0 .. 6.74 | 0.4..1.0 x -1.8..-0.6 |
| `vdd` | **VDD** | Scp_p, Cmswp_p, Invp, Cmswp_n, Scp_n | 8.34 .. 24.68 | 8.74..9.34 x -1.8..-0.6 |
| `boost_n` | **BOOST_N** | Se_n, Sa_n | 26.28 .. 33.27 | 26.68..27.28 x -1.8..-0.6 |

Island-to-island gaps: [1.6, 1.6] um.
p-substrate tap (routed to GND): {'x0': 39.67, 'x1': 40.27, 'y0': -1.8, 'y1': -0.6} um.

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

`unbiased_pmos_body_nets`: 0 entries. `single_terminal_nets`: 0.

The eleven NFET bodies are **not** in this table on purpose: the curated deck synthesizes one global substrate net (`vsubs`) for them regardless of drawn geometry, so `klt lvs` reports `device.body_unverified` for all eleven and no drawn tap can change that. What the drawn p-substrate tap does do is merge this layout's `GND` conductor into `vsubs`, without which `GND` would extract as a separate net and LVS would not match at all.

## Blocks (`klt gen`)

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
| `msw_p` | `MSW_P` | 1 | 0.0,0.0 .. 1.09,2.82 | clean |
| `msw_n` | `MSW_N` | 1 | 0.0,0.0 .. 1.09,2.82 | clean |
| `sb_p` | `SB_P` | 1 | 0.0,0.0 .. 1.09,1.82 | clean |
| `scn_p` | `SCN_P` | 1 | 0.0,0.0 .. 1.09,1.82 | clean |
| `sd_p` | `SD_P` | 1 | 0.0,0.0 .. 1.34,1.82 | clean |
| `cmswn_p` | `CMSWN_P` | 1 | 0.0,0.0 .. 1.09,1.82 | clean |
| `cmswn_n` | `CMSWN_N` | 1 | 0.0,0.0 .. 1.09,1.82 | clean |
| `sd_n` | `SD_N` | 1 | 0.0,0.0 .. 1.34,1.82 | clean |
| `scn_n` | `SCN_N` | 1 | 0.0,0.0 .. 1.09,1.82 | clean |
| `sb_n` | `SB_N` | 1 | 0.0,0.0 .. 1.09,1.82 | clean |
| `invn` | `INVN` | 1 | 0.0,0.0 .. 1.09,1.82 | clean |
| `cboot` | `CBOOT` | 2 | 0.0,0.0 .. 22.1,10.8 | clean |
| `csamp` | `CSAMP` | 2 | 0.0,0.0 .. 96.3,47.9 | clean |

## Composition

- `klt draw` (cell `ROUTE`): 412 shapes, 11 pin labels (the three n-well islands, the substrate tap, every wire)
- `klt gen-compose` (cell `gen_compose_0`): 23 blocks placed at explicit origins, bbox {'x0': 0.0, 'y0': -2.4, 'x1': 195.56, 'y1': 58.050000000000004}
- `klt gen-compose` is used as a **placer only** (no `routing` block in the request), the same choice `layout/comparator/` and `layout/sampling-frontend-wells/` both document.
- row x ranges (um): PFETs [0.0, 33.269999999999996], NFETs [39.269999999999996, 68.16], caps [74.16, 99.25999999999999]; shared met2 track band starts at y = 49.9 um

## Results

| Stage | Status | Detail |
| --- | --- | --- |
| DRC, curated deck (composed layout) | clean | violation_count=0, rule_counts={} |
| DRC, curated deck (illegal n-well fixture) | violations | violation_count=2, rule_counts={'nwell.space.1': 1, 'nwell.width.1': 1} |
| precheck | pass | 5 checks, 0 failed |
| Extract | extracted | device_count=24 {'nfet': 11, 'pfet': 9, 'sky130_fd_pr__model__cap_mim': 4}, net_count=17, pin_count=12, unbiased_pmos_body_nets=0, single_terminal_nets=0 |
| LVS (good reference) | match | devices 24/24 matched, nets 17/17 matched, pins 12/12 matched |
| LVS (body-tie negative control) | mismatch | mismatch_count=9, categories={'device.body_unverified': 1, 'device.unmatched': 4, 'topology': 4} |
| LVS (device-parameter negative control) | mismatch | mismatch_count=9, categories={'device.body_unverified': 1, 'device.property': 5, 'topology': 3} |
| LVS (capacitor top-plate negative control) | mismatch | mismatch_count=9, categories={'device.body_unverified': 1, 'device.unmatched': 5, 'topology': 3} |

## DRC coverage (what the deck did and did not check)

Recorded straight from `klt drc`'s own `coverage` block rather than asserted in prose, so a later deck release changing it shows up as a diff in the next record.

- rule families in scope: ['cap2m', 'capm', 'ct', 'difftap', 'li', 'licon', 'm1', 'm2', 'm3', 'm4', 'm5', 'nwell', 'poly', 'via', 'via2', 'via3', 'via4']
- layers checked: ['64/20', '65/20', '66/20', '66/44', '67/20', '67/44', '68/20', '68/44', '69/20', '69/44', '70/20', '70/44', '71/20', '89/44']
- layers present in the stream with **no** rule: ['65/44', '69/5']
- rules skipped (layer absent from the stream): ['capm2.enclosing.via4.1', 'capm2.separation.via4.1', 'capm2.space.1', 'capm2.width.1', 'met4.enclosing.capm2.1', 'met4.enclosing.via4.1', 'met5.enclosing.via4.1', 'met5.space.1', 'met5.width.1', 'via4.space.1', 'via4.width.1']

## Net correspondence (layout <-> reference)

- `BOOST_N` <-> `BOOST_N` (pin)
- `BOOST_P` <-> `BOOST_P` (pin)
- `BPREF_N` <-> `BPREF_N` (pin)
- `BPREF_P` <-> `BPREF_P` (pin)
- `\$13` <-> `BSBOT_N` (internal)
- `\$8` <-> `BSBOT_P` (internal)
- `vsubs` <-> `GND` (pin)
- `\$14` <-> `G_N` (internal)
- `\$6` <-> `G_P` (internal)
- `SAMPLE` <-> `SAMPLE` (pin)
- `\$15` <-> `SAMPLEB` (internal)
- `TOP_N` <-> `TOP_N` (pin)
- `TOP_P` <-> `TOP_P` (pin)
- `VCM` <-> `VCM` (pin)
- `VDD` <-> `VDD` (pin)
- `VINN` <-> `VINN` (pin)
- `VINP` <-> `VINP` (pin)

## Reported LVS findings (good reference)

- [warning] device.body_unverified: 11 NMOS device body terminal(s) were compared against the 'vsubs' deck-synthesized substrate net, not a real schematic net -- no drawn substrate-tap geometry resolved these device(s)' body terminal to a real net (see docs/cli/extract.md, "Coverage")
- [warning] topology: device class has no counterpart on the other side, but no devices of this class were extracted either -- not a real topology mismatch

Every finding above is reported at `severity: warning` with `error_count = 0`; `klt lvs`'s own overall verdict for this run is `match`.


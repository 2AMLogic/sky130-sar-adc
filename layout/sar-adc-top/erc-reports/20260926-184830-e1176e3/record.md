# `klt erc` supply record `20260926-184830-e1176e3` — T1 item 11 (Power delivery, structural)

**Verdict: unchanged from the record it supersedes, on a layout whose supply
geometry really did move** — six via stacks in the decoupling ties went from one
cut to four (issue #465). Both halves of item 11, stated up front so neither
hides behind the other:

- **Passing:** all four of this block's drawn supplies (`VDD`, `GND`, `VPWR`,
  `VGND`) resolve to **exactly one** electrical island each, with no
  `erc.unconnected_net` and no `erc.supply_short` anywhere —
  `erc_status: "clean"`, `erc_finding_count: 0`.
- **Still unmet:** item 11 also requires zero `erc.missing_tie` *from a tie the
  run actually checked*, and this spec declares no `ties[]` (disclosed,
  unchanged, see the spec's `ties_disclosure`). `klt signoff` renders that state
  `unmet` / `supply_spec_disclosed_tool_limitation`. A second, independent
  reason is that item 11's grading path consults item 4's LVS report first,
  which reports `mismatch` (klayout-tools#1878).

## Why this record exists: the decoupling ties' via stacks were widened

It supersedes `erc-reports/20260926-081822-203cca3/` (issue #440, which first
placed DR-017's two per-domain decoupling pairs). This record's layout is that
same composition with one class of change, made on measurement:

`sim/supply-impedance-sensitivity/records/20260926-183200-e8fa47c.md` (issue
#465) measured what the ties' own series resistance costs — adding #440's
measured 13.837 Ω / 13.448 Ω per domain to the committed netlist raises every
die-side rail's peak-to-peak excursion, worst rail `VPWR_DIE` from 12.135 mV to
16.180 mV (1.333×) at `tt_27c_1.80v`. So `build_layout.py` now draws **every
via2/via3 in those four ties as a 2×2 array of four cuts** (`DECAP_VIA_ARRAY`),
and `reports/20260926-184816-e1176e3/decap-ties.json` reports the ESR down to
**7.172 Ω** (analog) and **6.863 Ω** (digital), ~1.95× lower.

**That is precisely the kind of change that has to be re-graded here rather than
reasoned about, because it edits the conductor of a declared supply.** Each of
those six sites is a *series* element in a supply island's own path: three of
them (the two risers' met2↔met3 levels and the met3↔met4 levels) are the only
connection between a rail and the met2 run beyond them, and four are the only
connection between a met2 run and a capacitor's met3 bottom plate. Widening one
means deleting its single cut and drawing four new ones on a 0.40 µm pitch with
both landing pads grown by 0.20 µm — an edit that, done wrong, breaks the chain
outright (an `erc.unconnected_net` naming that supply) or grows a pad into a
neighbour (`erc.supply_short`).

| domain terminal | the via stacks on its path, and their cut count now | what a wrong array here would have looked like |
|---|---|---|
| `Cdecap_a` return (`GND`) | riser met4→met3 **4 cuts**, met3→met2 **4 cuts**; via2 into each of two met3 bottom plates **4 cuts** each | `GND` at 2+ islands (chain broken), or a met2/met3 pad short onto `comparator`'s own geometry |
| `Cdecap_a` supply (`VDD`) | none drawn here — met4 throughout, then each unit cell's own centre via3 | unchanged by this issue |
| `Cdecap_d` return (`VGND`) | via4 off met5 **1 cut** (unchanged), riser met4→met3 **4**, met3→met2 **4**; via2 into each bottom plate **4** each | `VGND` at 2+ islands, or a short onto the `VPWR` rail 13.6 µm away |
| `Cdecap_d` supply (`VPWR`) | via4 off met5 **1 cut** (unchanged) | unchanged by this issue |

Neither failure appears: **0 findings, 4/4 supplies at one island**, 210 gate
nets checked — every count field-identical to the superseded record. That is the
independent structural confirmation the DRC verdict cannot give (`klt drc` grades
shapes, not connectivity) and that this flow's LVS verdict cannot give either,
because it is a pre-existing `mismatch`.

Produced by `layout/sar-adc-top/bin/run-erc.sh`. This is a verdict *about* an
existing layout record; it regenerates no geometry.

| | |
|---|---|
| Graded layout | `layout/sar-adc-top/reports/20260926-184816-e1176e3/sar_adc_top.gds` — **a new GDS**, the first carrying multi-cut via arrays anywhere in this flow |
| Layout content hash | `sha256:fe38e3b58f6d4867e5239911c9a7fbf3b2107d7265b732f48c978e4b6387aa9e`, moved from `sha256:72a5fb7f0f5b2fb2cde9aa0f7470522b1ea48f198cd190d94c81ffffa12afadb` (the superseded record's pin) |
| Spec | `layout/sar-adc-top/erc-supply-spec.json` — `sha256:6638db431ac6d04ef60055f5fa5c24f1ef415aae91c9119ee050c024421fbde9`, **unchanged** from the superseded record |
| Tool | `klt` 0.6.0 / KLayout 0.30.12 (`layout/erc-requirements.txt`) |
| PDK | sky130A (open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b) |
| Invocation | `klt erc <gds> <spec> --pdk sky130 --deck sky130 --format json`, from the repo root with **repo-relative** paths |
| `status` / `erc_status` | `clean_partial` / `clean` (exit 0) |
| `erc_finding_count` | 0 |
| Gate nets checked | 210 (unchanged) |

## The non-tuning argument

The spec's own hash did not move at all this time — `sha256:6638db43…`, the same
file byte for byte as the superseded record graded, and the same graded-content
digest `run-erc.sh` computes over `stackup`, `vias`, `nets[]` and
`ties_disclosure.kind`:

```
run-erc.sh: graded-spec subset sha256=7f48fd89387b64b24c379baff04e6ef38361610240eac2c2d0adb8470584d982
```

Identical to the superseded record's digest and to its two predecessors'. **No
`_comment` was edited either**, which is why the whole-file hash is unchanged as
well: the spec's `stackup` already declares met2/via2/met3/via3/met4/via4/met5,
and a via array changes how many cuts are drawn on those layers, not which
layers a supply path uses. So this record is the same gate applied to different
geometry, with nothing about the gate restated.

## Mesh ablation cross-check, re-run on the new geometry

`ground-mesh-ablation.json` in this record is a fresh run of
`bin/probe-ground-mesh.py` against the graded GDS (exit 0):

```
as_predicted: true          full_reproduces_record_gds: true
full_is_one_island: true    ablated_splits: true
controls_unmoved: true      controls_moved: []
third_leg_as_predicted: true
```

It is re-run rather than inherited because the analog decoupling pair's return
tie is one of the four ties this issue widened, and that tie taps
`comparator.GND`'s own met4 stub — the single piece of analog-ground conductor
`--ablate-ground-mesh` still draws. Two of those lines are what check the
widened array specifically:

- `full_reproduces_record_gds: true` — the un-ablated variant the probe composes
  reproduces the graded GDS byte for byte (`sha256:fe38e3b5…` on both sides), so
  the arrays are in the record *and* in the probe's control arm.
- `ablated_splits: true` at **2** islands, with both islands' own descriptions
  **unchanged from the superseded record**: `sampling_frontend`'s own met1 ground
  (13 shapes, bbox 103.495–130.115 × 86.450–140.720 µm) and `comparator`'s own
  met4 stub grown east to carry the decoupling pair (10 shapes, bbox
  100.200–227.900 × 150.000–197.900 µm). A widened via that had failed to land
  would have shown as a *third* island here, or as the pair dropping off the
  second one.

`controls_unmoved: true` (`controls_moved: []`) likewise repeats: ablating the
analog mesh moves `VDD`, `VPWR` and `VGND`'s island counts not at all, so the
four wider via stacks did not smuggle a new path between the two domains.

## What this record does NOT say

- **Not that the substrate half of `GND` is graded.** `klt erc` sees drawn
  conductor only. The four decoupling returns all land on the one extracted net
  `GND|VGND|VSS` — bulk sky130 offers no way to split it, per
  `spec/decision-records/DR-012-analog-ground-pad.md` — and a one-island verdict
  on `GND` still means "the drawn `GND` conductor is one island", not "every
  NMOS body reaches it".
- **Not that the ESR is now low enough**, and not that it is measured *here*.
  `klt erc` is a connectivity model with no resistance in it: four cuts and one
  cut are the same verdict to it. The 13.837/13.448 Ω → **7.172/6.863 Ω**
  reduction this record's layout was built for is measured by
  `bin/probe-decap-sites.py` and lives in
  `reports/20260926-184816-e1176e3/decap-ties.json`, beside the DRC/LVS verdict.
  What the remaining resistance costs the rails is a simulation question, in
  `sim/supply-impedance-sensitivity/`.
- **Not that the decoupling meets DR-017's bounce target.** It does not, and
  DR-017's Decision §4 says so. This issue lowered the ties' contribution to the
  excursion; it did not move the target, and no arm of it was re-simulated on the
  reduced value (see DR-017's routing-parasitics open item for what is still
  owed).

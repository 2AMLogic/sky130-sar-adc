# `klt erc` supply record `20260926-081822-203cca3` — T1 item 11 (Power delivery, structural)

**Verdict: unchanged from the record it supersedes — this time on a layout that
really did move.** Both halves of item 11, stated up front so neither hides
behind the other:

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

**Why this record exists: the layout gained four capacitors, and each one is a
new conductor on an already-declared supply** (issue #440, placing
`spec/decision-records/DR-017-on-die-decoupling-budget.md`'s per-domain
decoupling). It supersedes `erc-reports/20260925-044420-f039594/`, whose two
predecessors were both prose-drift re-runs on one unchanged GDS; this one is
the first ERC record in that chain graded on **different geometry**.

That is exactly why it had to be re-run rather than reasoned about. Every one of
the four `sky130_fd_pr__cap_mim_m3_1` units adds drawn metal to a supply island
this spec declares, and each reaches its domain through a path this spec's
stackup either covers or does not:

| domain terminal | path from the supply to the plate | stackup entries it depends on |
|---|---|---|
| `Cdecap_a` return (`GND`) | `comparator.GND`'s own met4 stub → via3 → met3 island → via2 → met2 run → via2 into each met3 bottom plate | met4, via3, met3, via2, met2 |
| `Cdecap_a` supply (`VDD`) | `comparator.VDD`'s own met4 column → met4 strap → each unit's met4 top-plate lead → via3 → `capm` | met4 (only) |
| `Cdecap_d` return (`VGND`) | met5 rail → via4 → met4 → via3 → met3 island → via2 → met2 L → via2 into each bottom plate | met5, via4, met4, via3, met3, via2, met2 |
| `Cdecap_d` supply (`VPWR`) | met5 rail → via4 → met4 strap → each unit's met4 top-plate lead → via3 → `capm` | met5, via4, met4 |

A single missing via anywhere in those four chains would have shown up here as
an `erc.unconnected_net` naming the supply, or (a plate reached from the wrong
rail) as an `erc.supply_short`. Neither appears: **0 findings, 4/4 supplies at
one island**. That is the independent structural confirmation the DRC verdict
cannot give — `klt drc` grades shapes, not connectivity — and that this flow's
LVS verdict cannot give either, because it is a pre-existing `mismatch`.

Produced by `layout/sar-adc-top/bin/run-erc.sh`. This is a verdict *about* an
existing layout record; it regenerates no geometry.

| | |
|---|---|
| Graded layout | `layout/sar-adc-top/reports/20260926-081248-203cca3/sar_adc_top.gds` — **a new GDS**, the first carrying DR-017's decoupling pair placed |
| Layout content hash | `sha256:72a5fb7f0f5b2fb2cde9aa0f7470522b1ea48f198cd190d94c81ffffa12afadb`, moved from `sha256:bbb9b5373d80e8bb6ca3a8f698700678686ca15f6df27fe8ef2b2a55a67ec223` (the superseded record's pin) |
| Spec | `layout/sar-adc-top/erc-supply-spec.json` — `sha256:6638db431ac6d04ef60055f5fa5c24f1ef415aae91c9119ee050c024421fbde9`, moved from `sha256:429841c89ecc08652f12c0d7dacc18e6d21e0d2113b776aa11e5e97d6ed0943c` |
| Tool | `klt` 0.6.0 / KLayout 0.30.12 (`layout/erc-requirements.txt`) |
| PDK | sky130A (open_pdks f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7) |
| Invocation | `klt erc <gds> <spec> --pdk sky130 --deck sky130 --format json`, from the repo root with **repo-relative** paths |
| `status` / `erc_status` | `clean_partial` / `clean` (exit 0) |
| `erc_finding_count` | 0 |
| Gate nets checked | 210 (unchanged) |

## The non-tuning argument

The spec's hash moved, so the obvious question is whether the gate was widened
to let a new layout through. It was not, and that is mechanically checkable
rather than a matter of trust: `run-erc.sh` computes a graded-content digest
over exactly `stackup`, `vias`, `nets[]` and `ties_disclosure.kind`, with every
`_comment` (and any other underscore-prefixed) key dropped at both levels.

```
run-erc.sh: graded-spec subset sha256=7f48fd89387b64b24c379baff04e6ef38361610240eac2c2d0adb8470584d982
```

**Identical** to the superseded record's digest, and to its predecessor's. The
spec edits behind the whole-file hash move are three `_comment` passages:

1. **SCOPE** repointed from `reports/20260924-234053-66dca3c/` to
   `reports/20260926-081248-203cca3/`, with the geometry delta named and
   re-derived — met3 (70/20) **1428 → 1440** shapes, `capm` (89/44)
   **1028 → 1032**, both read off `klt layers --flattened --format json`'s own
   hierarchical `shapes` field on each GDS, and via4/met5 now reaching
   190.4/192.0 µm instead of 171.808/172.208 — and the fact that **no net is
   added, removed or renamed** stated explicitly: the four supplies declared
   here are the four this spec has always declared.
2. **the `met3` stackup comment's** drawn-geometry count, 1428 → **1440**
   shapes, plus why met2/via2 are load-bearing rather than merely present for
   the `GND`/`VGND` verdicts: sky130's extraction deck removes met3 that touches
   a `capm` plate from via3 connectivity, so a MiM bottom plate is reachable
   only from met2 through via2.
3. **the `met5` stackup comment**, noting that each digital rail is now also the
   met5 side of one via4 down to its own decoupling capacitor, so met5+via4 are
   the only path between the digital supplies and those two devices.

`ties_disclosure.reason`'s own two GDS-specific counts were re-checked and are
**unchanged on the new GDS**: still 12 `tap.drawing` 65/44 shapes, and
`sky130_fd_sc_hd__tapvpwrvgnd_1` instances are still present by name. Nothing in
that passage was edited, so the string echoed verbatim into `erc.json` is
byte-identical to the superseded record's.

## Mesh ablation cross-check, re-run on the new geometry

`ground-mesh-ablation.json` in this record is a fresh run of
`bin/probe-ground-mesh.py` against the graded GDS. It is re-run here rather than
inherited because issue #440 touched both the composition and the probe's own
input list (the probe now copies `decap.json` — the compose request names the
decoupling unit as a `blocks[].generator_report`, since `run-flow.sh` generates
that cell during the run — and the `decap_unit.gds` that report points at,
alongside the five sub-block GDS files, so both of its variants are composed
from the record's own bytes).

```
as_predicted: true          full_reproduces_record_gds: true
full_is_one_island: true    ablated_splits: true
controls_unmoved: true      controls_moved: []
third_leg_as_predicted: true
```

Three of those lines are load-bearing for *this* issue specifically, not just
for the mesh:

- `full_reproduces_record_gds: true` — the un-ablated variant the probe builds
  reproduces the graded GDS byte for byte, so the decoupling pair is in both the
  record and the probe's control arm.
- `controls_unmoved: true` (`controls_moved: []`) — ablating the mesh moves
  `VDD`, `VPWR` and `VGND`'s island counts not at all. The decoupling pair
  therefore does not smuggle a second path between the domains: if either
  digital tie had accidentally reached analog ground, removing the analog mesh
  would have moved a digital control.
- `ablated_splits: true` at **2** islands, the same count as before this issue —
  and the ablated arm's own island *descriptions* say which one the decoupling
  pair joined, which is the sharpest single check on the analog tie in this
  record. Pre-#440 the two ablated `GND` islands were `sampling_frontend`'s own
  met1 ground (13 shapes) and `comparator`'s own met4 stub (6 shapes, bbox
  100.2–102.62 × 169.8–197.8 µm). Post-#440 the first is byte-identical and the
  second has **grown to carry the pair** — 10 shapes, bbox 100.2–227.9 ×
  150.0–197.9 µm, i.e. it now reaches east to `decap_a1`. A third island, or the
  pair appearing on `sampling_frontend`'s, would both have been wrong.

The analog pair's own return taps `comparator.GND`'s own met4 stub, which is the
one piece of analog-ground conductor `--ablate-ground-mesh` still draws — which
is exactly what that island growth confirms. That is deliberate and asserted in
`build_layout.py` (`_check_decoupling_caps`): a tap on the mesh trunk instead
would have left the pair floating in the ablated arm, and the two arms would
then have differed by the mesh *and* the decoupling — measuring something other
than the mesh.

## What this record does NOT say

- **Not that the substrate half of `GND` is graded.** `klt erc` sees drawn
  conductor only. The four decoupling returns all land on the one extracted net
  `GND|VGND|VSS` — bulk sky130 offers no way to split it, per
  `spec/decision-records/DR-012-analog-ground-pad.md` — and a one-island verdict
  on `GND` still means "the drawn `GND` conductor is one island", not "every
  NMOS body reaches it".
- **Not that the decoupling meets DR-017's bounce target.** That is a simulation
  question, measured in `sim/supply-impedance-sensitivity/` and explicitly not
  met (DR-017's Decision §4). This record grades whether the two capacitors are
  *connected*, which is a precondition for that measurement meaning anything
  about this layout, not a substitute for it.
- **Not that the route to each capacitor is low-impedance enough.** `klt erc` is
  a connectivity model with no resistance in it. The ties' own series resistance
  **is** now measured, but by a different tool and recorded beside the DRC/LVS
  verdict rather than here: `reports/20260926-081248-203cca3/decap-ties.json`
  reports **13.837 Ω** per analog domain and **13.448 Ω** per digital domain,
  ~80 % of it single-cut vias. What that does and does not mean for DR-017's
  ideal-cap measurement is in `layout/sar-adc-top/README.md`'s "On-die
  decoupling (DR-017)" section, and the residual is DR-017's own standing open
  item.

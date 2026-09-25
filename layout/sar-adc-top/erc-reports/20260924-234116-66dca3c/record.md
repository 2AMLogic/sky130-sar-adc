# `klt erc` supply record `20260924-234116-66dca3c` — T1 item 11 (Power delivery, structural)

**Verdict: the supply-continuity half of item 11 still PASSES, on a layout whose
analog ground is now a drawn mesh joining all three analog blocks; item 11 as a
whole is still UNMET.** Both halves, stated up front so neither hides behind the
other:

- **Passing:** all four of this block's drawn supplies (`VDD`, `GND`, `VPWR`,
  `VGND`) resolve to **exactly one** electrical island each, with no
  `erc.unconnected_net` and no `erc.supply_short` anywhere —
  `erc_status: "clean"`, `erc_finding_count: 0`.
- **Still unmet:** item 11 also requires zero `erc.missing_tie` *from a tie the
  run actually checked*, and this spec declares no `ties[]` (disclosed, see
  below). `klt signoff` renders that state `unmet` /
  `supply_spec_disclosed_tool_limitation`. A second, independent reason is that
  item 11's grading path consults item 4's LVS report first, which reports
  `mismatch` (klayout-tools#1878).

**Read the first bullet with care, because this record is the second in a row
where the number did not move and the layout did.** `GND` read "1 island"
before issue #362 drew a pad on it, "1 island" after, and "1 island" again now
that issue #377 has meshed three sub-block ground terminals into it. A
connectivity model that reports the same integer across all three states is not
evidence about any of them. The evidence for the mesh is the **ablation** in
"Cross-checks" below — remove the mesh and nothing else, and this same model
splits `GND` into two islands.

This **supersedes** `erc-reports/20260924-214731-b323061/` (issue #362), which
graded an older GDS. That record is not wrong and is not edited: it graded the
layout that existed, by content hash. Issue **#377** changed the layout.

Produced by `layout/sar-adc-top/bin/run-erc.sh`. This is a verdict *about* an
existing layout record; it regenerates no geometry.

| | |
|---|---|
| Graded layout | `layout/sar-adc-top/reports/20260924-234053-66dca3c/sar_adc_top.gds` |
| Layout content hash | `sha256:bbb9b5373d80e8bb6ca3a8f698700678686ca15f6df27fe8ef2b2a55a67ec223` |
| Spec | `layout/sar-adc-top/erc-supply-spec.json` (unchanged — `sha256:fd4f5a93…`, byte-identical to every run this supersedes) |
| Tool | `klt` 0.6.0 / KLayout 0.30.12 (`layout/erc-requirements.txt`) |
| Invocation | `klt erc <gds> <spec> --pdk sky130 --deck sky130 --format json`, from the repo root with **repo-relative** paths |
| `status` / `erc_status` | `clean_partial` / `clean` (exit 0) |
| `erc_finding_count` | 0 |
| Gate nets checked | 210 (unchanged) |

**The spec was not touched.** Its content hash is the same
`sha256:fd4f5a93160072689b6fbc52dcce01b7eab8b68c48e6dc2fb6632500aa929946` every
earlier run pinned — the same four `nets[]`, the same stackup, the same vias.
The layout moved; the gate did not. (Its prose `_comment` passages still
describe the #344-era run — disclosed, tracked as **#364**, untouched here for
exactly the reason this paragraph relies on.)

## Per-supply verdict

`status` is **not** the item-11 verdict (an antenna or floating-gate finding in
the same report is a real defect but is not this item's subject —
klayout-tools#1994). The item's own pass conditions are per-supply:

| Supply | Islands | `erc.unconnected_net` | `erc.supply_short` | Continuity verdict |
|---|---:|---|---|---|
| `VDD` | 1 | none | none | **pass** |
| `GND` | 1 | none | none | **pass** — and now one island made of *three sub-blocks' own drawn terminals*, not one; see below |
| `VPWR` | 1 | none | none | **pass** |
| `VGND` | 1 | none | none | **pass** |
| `erc.missing_tie` | — | — | — | **not computed** — see below, and it is why item 11 is not met |

`erc_coverage.checked` carries all four as
`erc.net_connectivity:["VDD"|"GND"|"VPWR"|"VGND"]`, so each is checked and
passing, not silently skipped.

## What changed, and what it rests on

Issue **#377**, implementing
[`DR-013`](../../../spec/decision-records/DR-013-analog-ground-mesh.md), which
closes the largest open item of
[`DR-012`](../../../spec/decision-records/DR-012-analog-ground-pad.md):

1. **`layout/sampling-frontend/` promotes `GND` to a drawn met2 pin**
   (record `20260924-232823-66dca3c`; one `PIN_NETS` entry, no geometry moved,
   DRC clean, LVS match).
2. **`layout/cdac-array/` draws a real p-substrate tap and labels it `VSS`**
   (record `20260924-233346-66dca3c`; new `tap`/li1/licon1/mcon/met1 geometry
   below the n-well tap, DRC clean, LVS match).
3. **`build_layout.py`'s `analog_ground_mesh()` joins all three terminals** —
   one met3 trunk at y = 165.0 in the open channel between
   `sampling_frontend`'s top edge (147.22) and `comparator`'s bottom edge
   (176.3), with met4 droppers at x = 101.5 (`comparator.GND`), x = 103.795
   (`sampling_frontend.GND`) and x = −16.0 (an exclusive west-corridor track
   carrying `cdac_array.VSS`'s leg out of the array's confirmed-clear
   switch-row band). The DR-012 pad label stays at (101.5, 170.0).

Before this, two of the three analog blocks reached the analog ground only
through the p-substrate net `klt extract`'s sky130 deck synthesises — real
resistance, but not conductor any tool in this flow grades. That is the caveat
the superseded record carried under "Why `GND`'s pass must be read narrowly",
second bullet, and it is retired here.

## Cross-checks

Each of these was run against **this** GDS; none is assumed.

**1. The mesh — not the substrate — is what joins the three blocks' drawn
grounds.** `layout/sar-adc-top/bin/probe-ground-mesh.py` rebuilds this assembly
twice from this record's own committed sub-block GDS: once as shipped, once
with `build_layout.py --ablate-ground-mesh`, which draws DR-012's pad exactly as
#362 shipped it and omits *only* #377's mesh. Both are graded against the
byte-identical spec, same `klt` build:

| Variant | `erc_status` | findings | `GND` |
|---|---|---:|---|
| full (as shipped) | `clean` | 0 | one island |
| mesh ablated | `violations` | 1 | `erc.unconnected_net` — *"declared net 'GND' resolves to 2 disconnected electrical islands (expected exactly one)"* |

The two islands the ablated run names are `sampling_frontend`'s own ground
(met1, bbox 103.495 … 130.115 × 86.45 … 140.72, 13 shapes) and the comparator's
plus its pad (met4, 100.2 … 102.62 × 169.8 … 197.8, 6 shapes) — exactly the two
the mesh joins. `VDD`, `VPWR` and `VGND` are unmoved between the variants, as
controls, and the full variant's recomposed GDS is **byte-identical (sha256)**
to the one this record grades, so the two runs differ by the mesh and nothing
else. Summary committed beside this file as `ground-mesh-ablation.json`; the
script exits 3 rather than 0 if the prediction ever fails.

**2. The stackup ablations from #362 still behave, and now say more.** Same
method as the superseded record's (drop one entry from the spec's own `vias[]`
/ `stackup[]` and re-run), against both GDS files:

| Ablation | `GND` islands, pre-#377 GDS | `GND` islands, this GDS |
|---|---:|---:|
| `via3` removed (met3↔met4) | 2 | **3** |
| `via2` removed (met2↔met3) | 2 | **3** |
| `met4` removed from the stackup | 1 (no finding) | **2** |

Every row moves in the direction the geometry predicts, which is the point of
running them: cutting the riser stack now severs three pieces rather than two
(`comparator`'s own ground, `sampling_frontend`'s own ground, and the mesh's own
met4), and removing met4 entirely — which deletes the droppers but leaves the
met3 trunk — leaves the two sub-block grounds unjoined where the pre-#377 layout
had nothing to disconnect. `VDD` (3 → 3, 2 → 2), `VPWR` and `VGND` (23 → 23) are
unchanged across every row and both GDS files, so the movement is attributable
to this change.

**3. `klt drc` on the same bytes is clean.**
`reports/20260924-234053-66dca3c/drc.json` reports `status: "clean"`, 0
violations across 52 rules, so the mesh is graded against sky130A's own met1–met5
width/space/enclosure rules rather than argued to be legal. Minimum area is part
of that verdict: the pinned 0.6.0 deck authors `met1.area.1` … `met5.area.1`
among those 52. The independent cross-check agrees —
`docs/chipalooza/measure_metal_min_area.py` reports **0** shapes below every one
of `m1.6`/`m2.6`/`m3.6`/`m4.4a`/`m5.4` on this GDS, the same 0 as on the pre-#377
GDS. The mesh appears there only as polygon counts: met1 1503 → 1504, met2
1518 → 1519, met3 1342 → 1345, met4 29 → 31.

**4. The LVS compare on the same record does not regress.**
`reports/20260924-234053-66dca3c/lvs.json`: **88 mismatches, the same 88** as the
superseded record, in the same four categories (`device.unmatched` 66,
`net.merged` 11, `net.split` 10, `topology.flattened` 1), the same 803/869
devices matched, the same 411/443 nets matched, the same 21/22/22 pins. The one
visible difference is a net *name*: `GND|VGND` is now `GND|VGND|VSS`, because
`cdac_array`'s newly drawn `VSS` label joined a merge that already existed. The
device count on that net is unchanged at **692**.

**5. The two re-opened sub-block flows were re-verified, and their own klt pin
bump held separate.** Both were still standing on `klayout-tools==0.5.0`-era
records while `layout/requirements.txt` had moved to 0.6.0, so each was first
re-run **unchanged** on the new pin and reproduced its superseded verdicts
exactly, before the pin/tap change was applied. Post-change:
`sampling-frontend` DRC clean / LVS match, 24/24 devices, 17/17 nets, 12/12
pins; `cdac-array` DRC clean / LVS match on both its cells, 1060/1060 devices,
42/42 nets, 24/24 pins.

## Why `GND`'s pass must be read narrowly — the part that is still true

One bullet of the superseded record's warning is retired by this change; the
rest stands, and matters more now that a pass could be mistaken for a complete
ground plan:

- **`klt erc` has no device recognition.** It is a purely geometric wire/via
  connectivity model. This block's analog ground return is still partly the
  **p-substrate**, which `klt extract`'s sky130 deck synthesises as one shared
  net regardless of drawn geometry and which no geometric model can see. So
  `GND: 1 island` means *the drawn `GND` conductor is one island*, not *every
  NMOS body reaches it through metal*.
- ~~*Two of the four analog blocks still draw no ground conductor at all.*~~
  **Retired by this record**: all three analog sub-blocks now draw a ground
  terminal of their own and the mesh joins them. What replaces it is narrower
  and still true: **one tap per sub-block is a floor, not a substrate-noise
  plan.** `cdac_array` is 219 µm wide and switches 1024 unit capacitors with a
  single substrate tap at its west edge. DR-013 records that as an open item.
- **`GND` and `VGND` are one extracted net** (`GND|VGND|VSS`, 692 devices)
  while this ERC model reports them as two independent single islands. Both
  readings are correct about different things: they share no *drawn conductor*
  (what `klt erc` sees) and they share the *p-substrate* (what `klt extract`'s
  deck synthesises). Bulk sky130 offers no way to make them two nodes; DR-010's
  partition is of metal return paths and pads, and DR-012 says so explicitly
  rather than letting the clean ERC table imply isolation.
- **Nothing here is an impedance measurement.** DR-013's central argument —
  that a drawn path is better than 200 µm of p-substrate under the comparator's
  own decision reference — is a design-time argument, not a simulated result.
  `klt erc` reports topology, not ohms. #378 is the open item.
- The substrate half is what `erc.missing_tie` would have graded — and that
  check was not run.

## `erc.missing_tie`: not computed (absence of evidence, not evidence of absence)

Unchanged from every superseded record. No `ties[]` is declared, so
`erc.missing_tie` is **not computed** — it is not reported as a misleading zero.
The report says so in machine-readable form rather than only in prose:

```json
"ties_disclosure": { "kind": "tool_limitation", "reason": "..." }
"erc_coverage": { "inapplicable": [ { "id": "erc.missing_tie:[]",
                                      "reason": "ties_disclosed_tool_limitation" } ] }
```

`"kind": "tool_limitation"` (not `"unexpressible"`) is the accurate one here:
sky130 taps *are* nameable on this layout — more of them than before, since
this change drew one more (`cdac_array`'s `VSS` p-substrate tap, `tap.drawing`
65/44 on bare substrate, wired to li1 through licon1 66/44). The obstacle is
**klayout-tools#2169** — a `ties[]` declaration on a real routed standard-cell
design collapses into one electrical island and reports a **false**
`erc.supply_short`. Declaring `ties[]` would replace a stated gap with a
misleading finding, so it is left undeclared and disclosed.

**Well-tie evidence standing in for the ungraded check** (named so a reader can
go look, not asserted):

1. **Tap cells are instantiated.** `sky130_fd_sc_hd__tapvpwrvgnd_1` text on
   `text.drawing` 83/44 in the standard-cell macros.
2. **Body/tub nets are labelled.** `VPB` on `nwell.label` 64/5 and `VNB` on
   `pwell.label` 64/59.
3. **Two of the analog sub-blocks now draw and label their own substrate tap**
   (`sampling_frontend`'s, tied to `GND`; `cdac_array`'s, tied to `VSS`),
   joining `comparator`'s. This is the stand-in that got stronger with this
   change — and it is still a stand-in: none of it is `erc.missing_tie`.
4. **LVS net correspondence**
   (`reports/20260924-234053-66dca3c/lvs.json`) carries the supply nets, with
   `GND` a declared reference port answered by the `GND|VGND|VSS` layout net.
   It is **still not a clean LVS**: that run's `status` is `mismatch` (88).
   Item 4 does not pass; this stand-in inherits that weakness.

## Antenna half (reported, not this item's subject)

210 gate nets, gate area computed as `poly ∩ diff` via
`stackup[0].active_layer` (klayout-tools#1979). Every gate reports
`antenna_verdict: "pass_partial"` and **zero** levels violate. `pass_partial`
rather than `pass` is expected, not a defect: sky130's published antenna table
covers li1/met1/met2 only, so the met3/met4/met5 levels this block declares are
`"unchecked"` — a coverage gap in the PDK's own rule table, recorded rather than
papered over. This is why the envelope's overall `status` is `clean_partial`
while `erc_status` is `clean`.

Worth one sentence because this change adds met3/met4 to a ground net and a new
tap to a sub-block: the mesh carries no gate, so it changes no gate's antenna
ratio, and the met3/met4 levels were already `"unchecked"` for every one of the
210 gates before it existed. The gate count is unchanged at 210.

## Upstream friction

No new `klayout-tools` gap was filed from this increment. The three the
superseded records carry are all unchanged by this run, and one of them is
directly relevant to how this record's own evidence is structured:

- **klayout-tools#2169** (`ties[]` on a routed standard-cell design produces a
  false `erc.supply_short`) is why `erc.missing_tie` stays ungraded, and is the
  one item-11 sub-check this block still does not compute.
- **klayout-tools#2401** (a mis-transcribed `stackup[].label_layer` is silent —
  every declared net matches zero islands and reports as `erc.unconnected_net`,
  indistinguishable from a real supply defect) is untouched and still open.
  This is a *clean* record, the case where #2401 would be least visible; the
  two ablation tables above are what rule it out here, since a spec whose label
  layers were wrong could not produce islands that *split* under ablation.
- **klayout-tools#2457** (`klt erc` has no rule for *"does this declared supply
  reach a top-level terminal"*), filed from #362, is unchanged. This record is
  a second illustration of the same shape one level down: the tool also has no
  rule for *"is this supply's island made of conductor this design drew, or of
  one macro's own"*, which is why the mesh needed a hand-built ablation to be
  evidenced at all.

## Follow-ups

- **`erc.missing_tie` stays ungraded** until klayout-tools#2169 is fixed. That
  is the one item-11 sub-check this block still does not compute, and the reason
  a clean continuity table is not a met item.
- **One substrate tap per analog sub-block is a floor, not a plan.** DR-013's
  own open item; nothing in this record grades substrate noise.
- **The ground return is still unmeasured.** No `sim/` campaign models package
  parasitics, substrate resistance or bond-wire inductance — DR-012's second
  open item, tracked as **#378**, untouched by this change.
- **Staleness rule.** This record grades one specific GDS by content hash. A new
  `reports/<id>/` record from `run-flow.sh` makes this one stale, not wrong —
  re-run `run-erc.sh` to mint a fresh ERC record beside it.

# layout/sar-adc-top/ — top-level SAR ADC layout assembly (issue #103)

Top-level routing/assembly of the four sub-block layouts (`layout/sampling-frontend/`
#99, `layout/cdac-array/` #100, `layout/comparator/` #101, `layout/sar-sequencer/`
#102) plus this issue's own new glue logic (`layout/seln-inverters/`, the nine
`SELn<i> = NOT(DOUT<i>)` inverters `design/sar_adc_top.sch` adds directly at
the integration level — see that directory's own README) into one GDS
matching `design/sar_adc_top.sch`'s hierarchy, per #103's scope: **placement
and interconnect/supply routing only — no sub-block's internal layout is
touched.**

## Status (as of this record)

**Placement + interconnect routing complete and DRC-clean at the top level.
The LVS *pin-declaration* blocker (klayout-tools#1513) is resolved.
`layout/requirements.txt` now pins the officially-released
`klayout-tools==0.5.0` (published 2026-09-15) instead of the unofficial
`SAR_ADC_TOP_KLT` env-var override this flow used to need — that override is
retired. LVS itself still does not reach a clean match, but is now blocked on
exactly **one** open tool gap (klayout-tools#1878): the second gap the 0.5.0
bump exposed (klayout-tools#1876, capacitor device-class identity lost on the
SPICE round-trip) is **worked around locally** by this flow's own
`bin/restore-cap-device-class.py`, which recovers the pre-regression
verdict — 98 mismatches / 412 matched nets, against 124 / 393 without it. A
newly-tried `--abstract-cells` black-boxing shape narrows this further to
**6** mismatches, but rests on a not-yet-understood tool behaviour — a
same-instance pin-to-net binding fault, **not** the klayout-tools#1911/#1934
gap originally suspected (that fix is merged upstream but, per a 2026-09-19
ablation matrix, does not touch this collapse; corrected diagnosis filed as
klayout-tools#2142) — and is recorded as a measurement, not adopted for
signoff — see "LVS device/topology blocker" below for the full, current
trace of both.**

**Update (2026-09-26, issue #440): DR-017's two per-domain decoupling
capacitors are placed, and the layout is no longer stale against the
schematic.** Record `20260926-081248-203cca3` is the current `reports/LATEST`
and `erc-reports/20260926-081822-203cca3/` the current ERC record. `MF = 2` per
domain is drawn as **four** `klt gen cap_array` unit cells (two across
`VDD`/`GND`, two across `VPWR`/`VGND`), generated inside this flow and placed as
four more `blocks[]` entries in the same `klt gen-compose` request. DRC stays
**clean (0 violations / 52 rules)**; `klt erc` stays **`clean`, 0 findings**,
with all four supplies at one island each on the new geometry; LVS reaches
**871 layout devices against an 871-device reference** (`bin/generate-lvs-reference.py`
now emits top-level primitives for the first time) in the **same four mismatch
categories**, the one moved count being `device.unmatched` 66 → 67, which is the
already-tracked DR-012 substrate merge reaching a device. **DR-017's Decision §3
area budget is confirmed placeable and cost no die area at all** — both sites
fall inside the unchanged 280.450 × 385.500 µm bounding box, measured against
the pre-placement die's own back-end occupancy (met3 was 88 % free, met4 97 %).
The residual DR-017 asked to be told about is now quantified rather than
flagged: the ties add **13.8 Ω / 13.4 Ω of ESR per domain, ~80 % of it
single-cut vias**. See "On-die decoupling (DR-017)" below for the measurement,
the corridors, and what the ESR does and does not mean.

**Update (2026-09-23): `layout/requirements.txt` now pins
`klayout-tools==0.6.0`, and #103 is still not LVS-clean.** v0.6.0 is the
first release carrying klayout-tools#2147 (commit `3cc085c`, the fix for
#2142), which was this issue's tracked blocker. Record
`20260923-131726-fa1e0af` shows DRC still clean, connectivity still verified,
and the whole-request `klt lvs` verdict field-identical to 0.5.0 (98
mismatches). The `--abstract-cells` collapse is **also unchanged** under
0.6.0. #2147 fixed a real but different bug. The actual mechanism is now
located and filed as klayout-tools#2396: abstraction erases the MiM top
plate but keeps its via, so every capacitor in the black box shorts top to
bottom plate. Two further gaps sit behind it: klayout-tools#2398 (the well
tap is erased, so cdac_array's `VDD` pin is cut off) and
klayout-tools#2397 (0.6.0's reader-side #1876 fix never fires on this
netlist, so `bin/restore-cap-device-class.py` stays load-bearing). See "Update
(2026-09-23): re-measured on `klayout-tools==0.6.0`" below.

**Update (2026-09-24, issue #377): the analog ground pad now has a mesh under
it, and all three analog blocks draw a ground terminal.** Record
`20260924-234053-66dca3c` is the current `reports/LATEST`, and
`erc-reports/20260924-234116-66dca3c/` the current ERC record.
`layout/sampling-frontend/` promotes its existing `GND` track to a pin and
`layout/cdac-array/` draws a new p-substrate tap labelled `VSS` (each with its
own re-verified record); `bin/build_layout.py`'s `analog_ground_mesh()` — a
met3 trunk at `y = 165.0` with three met4 droppers — ties all three to the
DR-012 pad, whose own coordinate is unchanged. DRC stays clean (0 violations,
52 rules) and **LVS is unchanged in every field**: 88 mismatches in the same
four categories, 803/869 devices, 411/443 nets, pins 21/22/22. `klt erc` stays
`clean`, 0 findings, against the same byte-identical spec.

**None of those verdicts is evidence for the mesh**, and this is the second
time in three days that sentence has had to be written here. The substrate
already joined these nets, so the extraction reported one `GND` net before the
mesh existed and reports one after. The evidence that the *drawn* conductor is
what joins them is an ablation:
`bin/probe-ground-mesh.py` rebuilds the assembly with the mesh omitted and
nothing else changed, and `klt erc` then reports `GND` resolving to **2**
disconnected islands. Summary committed at
`erc-reports/20260924-234116-66dca3c/ground-mesh-ablation.json`. The topology
is [`DR-013`](../../spec/decision-records/DR-013-analog-ground-mesh.md), which
closes DR-012's largest open item.

**Update (2026-09-24, issue #362): the analog ground has a drawn pad.** Record
`20260924-214710-b323061` was the `reports/LATEST` of that increment
(superseded by #377's above), and `erc-reports/20260924-214731-b323061/` its
ERC record.
`bin/build_layout.py`'s new `analog_ground_pad()` carries `comparator`'s own
drawn `GND` pin — the only analog-ground conductor any sub-block here exposes —
up to met4 and south, out of that macro's footprint, to a top-level `GND` pin
label; `design/sar_adc_top.sch`/`.sym` gain the matching port (21 → **22**).
The decision this implements, including what the pad is *not* (a second node
beside the p-substrate), is
[`DR-012`](../../spec/decision-records/DR-012-analog-ground-pad.md). DRC stays
clean and the LVS mismatch count is **unchanged at 88**, in the same four
categories, with the same 803/869 devices matched; the pin counts go 21/21/21 →
**21/22/22** — reference 22 because `GND` is now a port, layout still 21 because
`GND` and `VGND` are one extracted net (`GND|VGND`, the shared p-substrate),
`matched` 22 because that one layout pin answers both reference ports. `klt erc`
stays `clean`, 0 findings, on a byte-identical spec: `GND` read "1 island"
before this change too, which is precisely why the "one island ≠ reaches a pad"
caveat had to be retired by moving the layout rather than by re-reading the
report.

**Update (2026-09-24, issue #355): the digital supply rails are routed, and
T1 item 11's continuity half now passes.** Record `20260924-190817-f3622fc` was
the `reports/LATEST` of that increment (superseded by #362's above).
`bin/build_layout.py` ties `sar_sequencer`'s and
`seln_inverters`' own met5 PDN straps together and out to two new top-level
supply pins (`VPWR`/`VGND`, per
[`DR-010`](../../spec/decision-records/DR-010-digital-supply-domain-partition.md)),
which is what `klt erc` had graded FAIL as two disconnected islands per rail.
DRC stays clean; the LVS verdict **improves** for the first time in this
flow's history — **21/21/21** pins (was 19/19/19), **88** mismatches (was 98),
**803/869** devices matched (was 794), nets 443/444/411 — because each digital
rail is now one net on both sides instead of a `VPWR_SEQ`/`VPWR_SELN` pair.
The remaining 88 are the *same* klayout-tools#1878 `combine_devices`-scoping
blocker as before; nothing below about that blocker changed. Numbers quoted
further down this document that predate this record (98 mismatches, 19/19/19
pins, 444/446/412 nets) are the state of the record they name and are left
as written.

**Re-run for issue #245** (`layout/sampling-frontend/`'s own re-verification
after issue #236's `Sa`/`Cmsw` sizing change), record
`20260908-072857-80df05e`: DRC is still clean, and the LVS mismatch verdict
is numerically **identical** to the pre-#245 baseline
(`reports/20260907-110058-a546200/`) — devices 869/869/794, nets 444/446/412,
mismatch categories `device.unmatched`=75/`net.merged`=12/`net.split`=10/
`topology.flattened`=1, all unchanged. That identity is itself evidence, not
a coincidence: it confirms `layout/sampling-frontend/`'s re-drawn geometry
(post-#236) recomposes into the assembly exactly as before, once this
sub-block's own new `SAMPLE` pin position — which DID move, from
`x_um=2.67` to `x_um=17.285` in that sub-block's own local frame, because
`Sa_p`/`Sa_n` no longer contribute a `SAMPLE`-net column once their gate net
became `G_P`/`G_N` — is threaded through to this assembly's own hardcoded
per-pin routing table (`bin/build_layout.py`'s `PIN` dict, updated this same
issue). Before that table was updated, a same-day trial run showed exactly
what an un-updated pin coordinate produces: `SAMPLE_INT` disconnected
entirely from the connectivity table (0 matches, where every other net still
matched) and the LVS device-match count dropped by 4 (794 → 790) — a real,
if easily overlooked, consequence of a sub-block's own internal net-label
placement moving that this composition's own hand-transcribed pin table does
not track automatically. **This LVS mismatch remains the SAME pre-existing,
unrelated `combine_devices`-scoping gap** tracked in
`docs/chipalooza/challenge-4-proposal.md` §3/§7 Item 1 and klayout-tools#1552
— issue #245 re-ran this composition as an additional confirming data point
against that already-open finding, not a new or different blocker.

**Re-run for issue #103's own `klayout-tools==0.5.0` pin bump** (retiring the
`SAR_ADC_TOP_KLT` override), record `20260915-213439-bf2256f`: DRC is still
clean (0 violations, unaffected by the bump), the unfiltered connectivity
check still passes net-by-net, and pins still promote 19/19/19. The LVS
mismatch verdict, however, is **not** identical to the pre-bump baseline —
devices 869/869/794 unchanged, but nets 444/446/**393** (down from 412) and
mismatch categories `device.unmatched`=**99** (up from 75)/`net.merged`=12/
`net.split`=10/**`topology`=2** (new)/`topology.flattened`=1 — 124 total
mismatches, up from 98. This is a **genuine, newly-introduced regression**,
not noise: isolated by diffing the extracted netlist's own `C` (capacitor)
device cards byte-for-byte between the pre-bump build and 0.5.0 against the
*same* composed GDS — the pre-bump build wrote `C$866 \$423 TOP_P|VINP
8.647288e-15 sky130_fd_pr__model__cap_mim`; 0.5.0 writes the bare
`C$866 \$423 TOP_P|VINP 8.647288e-15`, with no trailing class-name token at
all. That is klayout-tools#1558/#1564's own (correct, and separately
motivated) fix to stop emitting a `C` card ngspice cannot actually simulate
— but its side effect is that `NetlistSpiceReader` reading that bare card
back in (exactly what this flow's pre-extracted `layout.netlist` LVS shape
does) can no longer recover the capacitor's real device-class name, so it no
longer resolves as the same class as the reference netlist's own explicitly-named
capacitor devices. Filed generically as klayout-tools#1876. Separately,
klayout-tools#1552 (this repo's own prior report of the `combine_devices`
scoping gap) is closed upstream via #1556's new
`options.combine_devices_per_circuit` — tried directly against this
composition and found not to help: `klt extract`'s layout-side output for a
`klt gen-compose`d GDS is always one flat circuit (no hierarchical
extraction mode exists, #1085), so the option has no per-macro subcircuit
boundary to scope against on that side, and a direct trial reached a
*worse* result (1154 mismatches) than the existing whole-request
`combine_devices: true` compromise this flow keeps using. Filed generically
as klayout-tools#1878. See "LVS device/topology blocker" below for the full,
current writeup of both gaps.

**Re-run for issue #326's minimum-area fix**, record
`20260918-191315-935ce76`: DRC stays clean and the LVS verdict is
field-identical to `20260915-234004-76f48b9` (98 mismatches, 869/869/794
devices, 444/446/412 nets, 19/19/19 pins, same four categories). What changed
is geometry `klt drc` structurally could not see at the `klt 0.5.0` pin of the
day — see "Minimum-area rules: in the deck since `klt 0.6.0`, and clean"
below, which also corrects that section's counts. The composition's own
top-level `bbox_um` moves for the first time since PR #174, by 0.05 um in `x0`
only (-20.200 -> -20.250), because the external `VDD` pin's label-only met4
landing pad widened from 0.36 to 0.50 um; that pad is the composition's
leftmost shape. This re-run also picked up `layout/cdac-array/`'s,
`layout/sar-sequencer/`'s and `layout/seln-inverters/`'s own PR #327 records
and `layout/sampling-frontend/`'s new `20260918-191227-935ce76`, so all five
composition inputs are again each flow's current `reports/LATEST`.

### Minimum-area rules: in the deck since `klt 0.6.0`, and clean

**Premise update (issue #363).** This section used to open "the deck has
none", and that was true of `klayout-tools==0.5.0`: 47 rules across five kinds
(`width`, `space`, `enclosing`, `separation`, `isolated`) and **no `area`-kind
rule at all**, so sky130A's own metal minimum-area rules — `m1.6` 0.083,
`m2.6` 0.0676, `m3.6` 0.240, `m4.4a` 0.240, `m5.4` 4.0 um^2, all five in the
pinned PDK's own `libs.tech/klayout/drc/sky130A_mr.drc` — had never looked at
this layout, and a `status: "clean"` verdict said nothing about them.

That gap closed when `layout/requirements.txt` moved to
`klayout-tools==0.6.0` (issue #103, 2026-09-23), which contains
klayout-tools#1989 (commit `50cc29c3`). **The pinned deck now authors 52 rules
including `met1.area.1` … `met5.area.1` and `met1.holes_area.1` …
`met5.holes_area.1`** — read them out of this record's own
`reports/20260924-214710-b323061/drc.json` `coverage.rules_checked` (52 rules,
the ten `met*.area.1`/`met*.holes_area.1` among them, field-identical to the
superseded `20260924-190817-f3622fc`'s), which reports **0 violations**. Minimum area is a first-class part of this flow's
`klt drc` verdict again, not an out-of-band footnote.

`docs/chipalooza/measure_metal_min_area.py` is kept as an **independent
cross-check** rather than retired. It reads the thresholds and layer numbers
out of the pinned PDK's own deck (never transcribed) and applies KLayout's own
`Region#with_area` — the same primitive the deck's rule text calls — to each
flow's current record:

```
layout/bin/setup-venv.sh                                    # once
layout/.venv/bin/python docs/chipalooza/measure_metal_min_area.py
```

Issue #326 found **17 shapes below `m3.6`/`m4.4a`** in the composed GDS that
this repo's own generators drew: 12 met3 + 1 met4 from this flow's via risers,
4 met3 from `layout/sampling-frontend/`'s stacked-via pads. All were **pads on
a layer a via riser merely passes through** (or, for the one met4 island, a
landing that carries only a pin label) — exactly the pads nothing else merges
with, which is why a `PAD_UM`-sized 0.1296 um^2 square was fine everywhere
else and a violation there. `bin/build_layout.py` now sizes such a pad from
`MIN_METAL_AREA_UM2` (`_pad_side()`/`Canvas.riser()`'s `isolated_ends`), so it
clears its own layer's rule unaided; every pad that merges into one of this
module's own wires keeps `PAD_UM` and none of the empirically-tuned clearances
documented below moves. The composed GDS now measures **0** shapes below
`m3.6`/`m4.4a`.

**Nothing remains below threshold. The "145 residual shapes" this section
used to report never existed** — they were an artifact of the measuring
script, corrected under issue #363.

That figure claimed 145 shapes on met1/met2/met3/met5 emitted by `klt`'s own
place-and-route inside `sar_sequencer`/`seln_inverters` (generated via cells
`VIA_L1M1_PR_MR` met1 0.290×0.230 um, `VIA_M2M3_PR` met3 0.330×0.330 um,
`VIA_via5_6_*` met5 1.420×1.600 um, plus router-drawn stubs), split 112 +
33 across the two producing flows. Every one of them is **fully merged into a
wire or a PDN strap on its own layer** in the drawn GDS, which is exactly what
the PDK's tech-LEF expects of a via enclosure — so none of them is below
anything. The script under-merged: it built its region with
`kdb.Region(); region.insert(iter); region.merge()`, and
`Region#insert(RecursiveShapeIterator)` carries each shape's GDS user
properties across, where KLayout's merge is property-aware and refuses to
merge polygons whose properties differ. This repo's routed GDS attaches a
net-name property (`[[1, "VPWR"]]`, `[[1, "VGND"]]`) to each PDN strap and
none to the via cells inside it, so covered pads stayed separate polygons and
were counted as standalone violations. On this record's met5 the two
constructions read 24 polygons / 1058.75 um^2 (buggy) against 5 polygons /
896.09 um^2 (correct) — and a merged region's area *is* its union area, so the
larger number is a double count.

**Two independent measurements now agree at zero**, which is how the defect
was caught in the first place:

| Measurement | `m1.6` | `m2.6` | `m3.6` | `m4.4a` | `m5.4` |
| --- | --- | --- | --- | --- | --- |
| `drc.json`'s own `met*.area.1` (record `20260924-214710-b323061`) | 0 | 0 | 0 | 0 | 0 |
| `measure_metal_min_area.py`, corrected (same record, re-run under #362) | 0 | 0 | 0 | 0 | 0 |
| `measure_metal_min_area.py`, pre-#363 (**wrong**) | 114 | 6 | 8 | 0 | 15 |

The same correction applies to the two producing flows measured on their own
GDS: `layout/sar-sequencer/` 112 → **0**, `layout/seln-inverters/` 33 → **0**.
Issue #333's waiver over those residuals is therefore **withdrawn, not
reaffirmed** — there was nothing to waive. The upstream filings that rested on
the same count (klayout-tools#2072/#2075, klayout-tools#2139) are noted as
superseded in each flow's README.

The regression is pinned by `sim/tests/test_measure_metal_min_area.py`, which
reproduces the two constructions on a synthetic fixture where they disagree
(a property-bearing strap covering a sub-threshold via pad) and asserts the
corrected one; CI's headless `checks` job runs it against the pinned KLayout
engine.

`reports/20260918-191315-935ce76/minimum-area.json` — that script's `--json`
output against the superseded 2026-09-18 record — is **pre-#363 output and its
`below_min_area` counts are wrong**. It is kept, not rewritten:
`layout/` evidence is append-only, and a record says what was measured at the
time. Read it only through this section.

`layout/sar-adc-top/bin/build_layout.py` places all five sub-blocks — plus,
since issue #440, the four `DECAP_UNIT` cells DR-017's per-domain decoupling is
drawn as — with `klt gen-compose` (explicit placement, each named as a
`blocks[].cell` entry per #1189), and hand-routes every net
`design/sar_adc_top.sch` calls for (`klt draw`), following the floorplan/routing plan this document works out below.
`klt drc` on the composed layout is **clean (0 violations)**. A
full-hierarchy, unfiltered `klt extract` was checked net-by-net by hand
against the intended interconnect (see the latest
`reports/<record-id>/record.md`'s own "Connectivity verification" table) —
every one of the ~30 top-level nets this assembly routes extracts as its own
distinct, correctly-scoped net, with exactly the intended cross-sub-block
membership and no unintended shorts. That table is the direct evidence
backing this issue's own DRC/interconnect-correctness claims.

`klt extract --pin-source-cells` (klayout-tools#1515, merged 2026-09-06)
now promotes exactly this design's own intended 19 top-level pins — 19/19/19
promoted/reference/matched, where none of `--top-cell-pins`/`--pins`/
`--def-pins` could reach better than a 23-vs-19 over-promotion (see "LVS pin
declaration: resolved" below for the fix and why it works). `klt lvs`
itself still reports a **mismatch**, but for an unrelated reason discovered
only once the pin blocker cleared: `options.combine_devices` has no
per-subcircuit scoping, and this design's five already-independently-verified
sub-blocks need *opposing* settings (see "LVS device/topology blocker"
below). Neither blocker reflects a routing defect — the connectivity table
above and the resolved pin counts are independent, positive evidence the
composition and its interconnect are correct.

<details>
<summary>Historical trace: why `--top-cell-pins`/`--pins`/`--def-pins` each failed (kept for the record; resolved by `--pin-source-cells`, see below)</summary>

`klt lvs` itself still reports a mismatch, but not because the routing is
wrong: no available `klt extract` declared-pin mechanism
(`--top-cell-pins`/`--pins`/`--def-pins`) reproducibly promotes *exactly*
this design's own intended 19-port top-level interface once composed from
five independently-labeled sub-blocks with no governing top-level DEF (two
of the five are placed-and-routed standard-cell macros carrying their own
internal, generic net labels — `A`, `X`, `Q`, `Y`, `D`, `S` — that collide
with this design's own port names once everything is flattened for
extraction). Filed generically at klayout-tools#1513 (see "LVS pin
declaration blocker" below for the full trace of why each of the three
mechanisms fails differently). This mirrors, one level up, the exact class
of gap `layout/sar-sequencer/`'s own `--def-pins` fix (klayout-tools#1390)
already resolved for a *single* placed-and-routed macro — this is the same
root cause recurring at the *composition* scale, where there is no single
governing DEF to anchor it on.

</details>

An earlier increment of this issue (previous revision of this document)
found and fixed a real sub-block-layout completeness gap while working out
this same floorplan: two of `cdac_array`'s pins (#100) had **no drawn
conductor a top-level assembly could physically contact**. That gap was
filed and closed as **#165** (`cdac_array: VDD (nwell) and SELp/SELn (poly
gate) pins have no externally-contactable landing geometry`) before this
increment's own routing pass began; the section immediately below is kept
for the record of what that investigation found. See "GND / VPWR / VGND"
and "Recommended composition mechanism" further down for the routing detail
that followed once #165 landed; the short version of the original finding:

- `cdac_array.VDD` is a bare `nwell` rectangle with a text label and **zero**
  drawn `tap`/`licon1`/`li1`/metal anywhere on it (`cdac_layout.py`'s own
  `stamp()`/pfet-well code draws no tap at all). Unlike the p-substrate
  (`GND`), which has a real chip-wide auto-merge fallback in `klt extract`'s
  sky130 deck (every untapped NMOS body resolves to one shared `vsubs` net
  regardless of drawn geometry — the mechanism the "GND / VPWR / VGND"
  section below already described), an n-well is a genuinely isolated tub
  with **no such global fallback**: `cdac_array.VDD` LVS-matches at the
  sub-block level (the reference subckt's `VDD` port only has to resolve to
  *some* named node) while being physically unreachable from outside the
  block.
- `cdac_array`'s `SELp<i>`/`SELn<i>` (i=0..8) are bare-poly gate straps held
  at **exactly** the transistor channel width end to end, by the generator's
  own deliberate design (`cdac_layout.py`'s own comment: a wider strap would
  silently grow the extracted device L). Direct geometry inspection around
  one such pin (`SELp0`) found real diffusion within ~0.5 um of the pin's own
  declared position — i.e. the labelled point sits near the channel-diffusion
  overlap, not in a safe field-poly extension. Landing a contact there risks
  silently corrupting the extracted L (an electrical defect that would not
  necessarily fail DRC, and might not fail LVS either if parameter tolerance
  is loose) — precisely the "passes DRC/LVS clean while degrading whole-chip
  spec" failure mode #103's own Curator complexity note warns about, so this
  issue does not attempt it blind.

Every *other* top-level pin was independently verified to have real,
externally-reachable drawn conductor during this same investigation:
`sampling_frontend`/`comparator`'s `VDD` (both are real device source/drain
nets with real diffusion contacts, unlike `cdac_array`'s body-only `VDD`),
`cdac_array`'s own `TOP_P`/`TOP_N`/`VREFP`/`VREFN` (real met4/met1/met2
conductor confirmed at each pin's exact declared position), and every
`sar_sequencer`/`seln_inverters` digital I/O pin (ordinary `klt
place-and-route` output, always real metal by construction). So the
composition/routing plan below is otherwise ready to execute once #165
lands — this issue is blocked on that dependency for the `VDD` and
`SELp`/`SELn` nets specifically, not on any remaining floorplan/routing
uncertainty.

This is deliberately not attempted blind: getting a first heterogeneous
5-block (4 full-custom analog + 1 std-cell digital) composition to a correct,
DRC-legal, LVS-matching result on the first attempt is realistic to expect to
take several iterations, mirroring every sub-block's own report history
(`layout/comparator/reports/`, `layout/sampling-frontend/reports/`, etc. each
carry multiple records from get-it-working passes) — this document exists so
that iteration starts from real, already-verified data instead of
re-deriving it.

## Per-block pin geometry (source of truth for the routing pass)

Extracted directly from each block's own committed GDS (`klt cells`/a
`klayout.db` label dump; DEF `PINS` sections for the two std-cell macros,
which is what `--def-pins` already treats as authoritative — see
`layout/sar-sequencer/README.md`). All coordinates are in that block's own
**local** cell coordinate system (origin at the block's own `(0,0)` corner as
committed), in micrometers, and must be translated by whatever placement
offset the composition finally chooses.

### `sampling_frontend` (top cell in `layout/sampling-frontend/reports/20260915-120718-1e90b14/sampling_frontend.gds`, re-verified post-issue-#236/#245 and post-`klayout-tools==0.5.0`)

bbox: `(0.0, -2.4)` to `(195.56, 58.97)`. All pins on layer `69/5` (met2.pin).
`GND` had **no drawn pin** here until issue #377 added one (record
`20260924-232823-66dca3c`); the table below carries it, and the sentence this
line used to end on — "see GND/substrate below" — now points at a closed gap
rather than an open one.

**Every `y_um` below is +0.92 µm vs. the klt-0.4.0 era, as of issue #103's
`klayout-tools` 0.4.0 → 0.5.0 bump.** klt 0.5.0 builds this sub-block's own
`cboot`/`csamp` MIM cap arrays 0.92 µm taller than 0.4.0 did. `csamp` is
this sub-block's own tallest block, and its own `build_layout.py` stacks the
shared met2 routing channel directly on top of the tallest block, so
`track_y0_um` rides up with it — `49.9 → 50.82` in the record's own
`layout.summary.json` — and so does the block's own top edge
(`58.05 → 58.97`). `x_um` is unchanged for every pin (the cap arrays grew
only in `y`; this generator draws `W` vertically).

This is exactly the kind of sub-block-internal move this composition's own
hand-transcribed pin table does not track automatically — the same failure
mode issue #245 hit (see the `SAMPLE` note below). Leaving the pre-bump `y`
values in `bin/build_layout.py` put this assembly's top-level landing pads
0.92 µm below the pins they were meant to contact, which showed up as
4 × `met2.space.1` against the neighbouring track (0.07–0.09 µm gaps) and
LVS 128; re-reading the table off the current GDS restores DRC-clean and the
124-mismatch verdict documented above.

**SAMPLE's own `x_um` moved from `2.67` to `17.285` as of issue #245** (a
separate, earlier move, unrelated to the klt bump): this sub-block's own
`build_layout.py` always labels a net's met2.pin at that net's *leftmost*
contributing column (`xs[0]`), and issue #236 moved `Sa_p`/`Sa_n`'s gate
from `SAMPLE` to `G_P`/`G_N` — the two devices that used to supply
`SAMPLE`'s own leftmost column (2.67, in `Sa_p`'s own PFET-row position).
That issue's own `Cmswn`/`Cmswp` widening did *not* move the track band
(those two grew in `y` but never overtook `Csamp`); klt 0.5.0's taller
`csamp` is what finally did.

Read directly off layer `69/5` text in the record's own
`sampling_frontend.gds`, cross-checked against its `layout.summary.json`
`nets.<net>.track_y_um` / `columns_um[0]`:

| Pin | x_um | y_um |
| --- | --- | --- |
| VDD | 1.76 | 51.82 |
| GND | 39.97 | 52.32 |
| SAMPLE | 17.285 | 51.32 |
| BOOST_P | 0.70 | 53.32 |
| VINP | 10.10 | 54.32 |
| VCM | 13.30 | 52.82 |
| BPREF_P | 14.87 | 57.32 |
| VINN | 22.90 | 54.82 |
| BPREF_N | 21.27 | 57.82 |
| BOOST_N | 26.98 | 53.82 |
| TOP_P | 42.23 | 58.32 |
| TOP_N | 44.52 | 58.82 |

`GND`'s own x is that net's leftmost contributing column — the p-substrate
tap's own column, 39.97 — which is why it sits well to the right of the other
supply pins; its y is track 3 of the shared band (50.82 + 3 × 0.50).

Used by this assembly: `VDD`, `GND` (-> the analog ground mesh, #377),
`SAMPLE` (<- sequencer's `PH_SAMPLE`, net
`SAMPLE_INT`), `VINP`/`VINN` (<- top-level external pins), `VCM` (<-
top-level external pin), `TOP_P`/`TOP_N` (<-> cdac_array/comparator).
`BOOST_P`/`BOOST_N`/`BPREF_P`/`BPREF_N` are internal to this sub-block (per
DR-004/DR-007 and `design/sar_adc_top.sch`'s own "known integration gap"
note — `BPREF_P`/`BPREF_N` are deliberately left dead-ended, not routed to
anything else).

### `cdac_array` (top cell in `layout/cdac-array/reports/20260905-220338-9fb9b04/cdac_array.gds`, `reports/LATEST` as of this record — geometry/pin positions re-verified identical to the earlier `20260825-132454-51cbdd4` record this table was originally transcribed from)

bbox: `(-4.5, -35.0)` to `(218.7, 55.85)`.

| Pin | x_um | y_um | layer/datatype |
| --- | --- | --- | --- |
| VDD | -2.50 | -26.37 | 64/5 (nwell.pin) |
| VREFP | -2.00 | -34.80 | 68/5 (met1.pin) |
| VREFN | -2.00 | -33.40 | 69/5 (met2.pin) |
| TOP_P | -2.40 | 27.55 | 71/5 (met4.pin) |
| TOP_N | 216.80 | 27.55 | 71/5 (met4.pin) |
| SELp0..SELp8 | 4.545, 15.545, 26.545, 37.545, 48.545, 59.545, 70.545, 81.545, 92.545 | -27.08 | 66/5 (poly.pin) |
| SELn0..SELn8 | 103.545, 114.545, 125.545, 136.545, 147.545, 158.545, 169.545, 180.545, 191.545 | -27.08 | 66/5 (poly.pin) |
| VSS | 1.00 | -31.60 | 68/5 (met1.pin) — **added by issue #377** |

The `VSS` row is new. This block used to have **no `GND`/`VSS` pin at all**:
its 4th port was a literal `vsubs` connection with no drawn label, so the
reference netlist renamed the schematic's `VSS` to the deck's synthesized
global. Issue #377 drew a real p-substrate tap (below the `VDD` n-well tap,
sharing its x) up to a met1 landing pad and labelled it `VSS`, and the
reference now says `VSS` too — see `layout/cdac-array/README.md`'s "`VSS`
landing geometry". `TOP_P`/`TOP_N` sit on
**opposite edges** (left/right) at the same `y`, ~221 µm apart — the CDAC
array is far wider than either of its two abutting neighbors (sampling
front end, comparator), which is the central floorplan constraint this
composition has to resolve (see "Open floorplan questions" below).
`VDD`'s pin sits on the **well** layer (64/5), not a metal, and — verified by
direct GDS inspection, not just inferred from the pin's layer — **there is no
tap or metal anywhere on that well at all** (`cdac_layout.py` draws no tap
for this net). This is not a "which metal is it via-stacked to" question;
routing this net requires a new landing pad that does not yet exist. See
"Status" above and #165. `SELp0..SELp8`/`SELn0..SELn8` have the same
"pin sits on bare drawn geometry" shape (poly, not metal) but a
*different* underlying issue — see #165's device-L-safety concern, also
summarized in "Status" above and in "Recommended composition mechanism"
below.

### `comparator` (top cell `gen_compose_0` in `layout/comparator/reports/20260915-120705-1e90b14/comparator.gds`)

bbox: `(0.0, 2.5)` to `(26.6, 38.65)` -- widened from `(24.0, 38.65)` by
issue #180's re-draw (the sixth `klt gen` block, `rstd`, and the `DIP`/`DIN`
precharge devices it added, per DR-004 Amendment A). All pins on layer `68/5`
(met1.pin).

| Pin | x_um | y_um |
| --- | --- | --- |
| GND | 1.30 | 20.00 |
| VINN | 4.90 | 20.00 |
| VINP | 9.10 | 20.00 |
| OUTP | 10.10 | 17.50 |
| OUTN | 10.60 | 22.50 |
| VDD | 17.90 | 15.00 |
| CLK | 1.90 | 24.50 |

OUTP/OUTN moved (18.50->17.50, 18.00->22.50 in y) as a direct consequence of
#180's re-route: those nets' `NET_PINS` no longer start with the input
pair's own drain pins (moved to the new internal `DIP`/`DIN` nodes), which
changes which pin the greedy router processes -- and therefore which y-track
it lands on -- first. `DIP`/`DIN` themselves are not top-level pins (internal
nodes, like `TAIL`), so they do not appear in this table.

Unlike the other three full-custom blocks, `comparator` has a **real drawn
`GND` pin** (7-port reference, `.SUBCKT comparator VDD GND CLK VINP VINN OUTP
OUTN`) rather than relying only on the deck's substrate auto-merge — see
below. Since issue **#362** that pin is also what the block's own top-level
analog ground pad is built on: it is the only analog-ground conductor any
sub-block in this composition draws, so `bin/build_layout.py`'s
`analog_ground_pad()` risers off it (see "The analog ground pad" below).
Direct inspection of this macro's own GDS around that pin, for the record:
met1 `(0.15, 19.85)–(2.36, 20.15)` carrying the label, a via1 up to a
`(1.15, 19.85)–(1.45, 20.15)` met2 landing, and a `tap.drawing` (65/44)
rectangle `(0.0, 17.0)–(0.6, 23.0)` underneath — and **no met3 or met4
anywhere in this macro at all**, which is what makes a met4 stub over its own
footprint safe.

### `sar_sequencer` (top cell `sar_sequencer` in `layout/sar-sequencer/reports/20260905-191258-4c6c655/sar_sequencer.gds`)

bbox: `(0.0, 0.0)` to `(42.57, 42.57)`. Signal pins from the routed DEF's own
`PINS` section (`sar_sequencer.def`), all on `met1`, all at `x = 42.272`
(the block's right-edge I/O column):

| Pin | y_um | direction |
| --- | --- | --- |
| PH_SAMPLE | 17.85 | output (net `SAMPLE_INT` at this integration level) |
| CLK | 21.25 | input |
| RST_B | 22.61 | input |
| COMP_OUT | 26.01 | input |
| DOUT0..DOUT9 | 21.93, 19.89, 19.21, 29.41, 26.69, 18.53, 17.17, 16.49, 23.29, 28.73 | output |
| BUSY | 30.09 | output |

(`PH_B9..PH_B0`/`PH_EOC` are also real DEF pins at this same `x`, but are
intentionally left unconnected at this integration level per
`design/sar_adc_top.sch`'s own header — not needed by this assembly.)

`VPWR`/`VGND` are **buried met5 straps**, not edge pins:

| Net | x range (um) | y (um) |
| --- | --- | --- |
| VPWR | 2.30 .. 40.48 | 29.92 |
| VGND | 2.30 .. 40.48 | 16.32 |

Landing a connection on these means overlapping a drawn met5 rectangle
somewhere inside that x range at that exact y — not a simple edge abutment.

### `seln_inverters` (top cell `seln_inverters` in `layout/seln-inverters/reports/20260906-002022-a36e06f/seln_inverters.gds`)

bbox: `(0.0, 0.0)` to `(86.195, 86.195)`. Signal pins on `met1`, all at
`x = 0.297` (left-edge I/O column):

| Pin | y_um |
| --- | --- |
| DOUT0..DOUT8 | 49.13, 43.01, 43.69, 44.37, 39.61, 38.25, 45.73, 42.33, 46.41 |
| SELn0..SELn8 | 41.65, 47.77, 45.05, 38.93, 40.97, 48.45, 37.57, 47.09, 40.29 |

`VPWR`/`VGND` are buried met5 straps (3 VGND stripes, 2 VPWR stripes,
spanning roughly `x = 2.3 .. 84.3`) for the same PDN reason as
`sar_sequencer` above.

### `DECAP_UNIT` (generated by this flow, not a committed sub-block — issue #440)

The one cell in this table that has no `layout/<block>/` directory behind it:
`run-flow.sh` step 2b generates it with `klt gen cap_array` from
`build_layout.py`'s own `DECAP_GEN_PARAMS`, and step 4 places it **four** times.
Its numbers therefore come from the generator's own report
(`reports/<record>/decap.json`) rather than from a committed GDS, and
`build_layout.py --verify-decap` re-asserts every one of them against that
report on every run — a `klt` bump that moves the cell fails the flow instead of
silently mis-tieing four capacitors.

bbox: `(0.0, 0.0)` to `(47.9, 48.82)` — `x1 = 47.9` is the met3 bottom plate
(0.5 µm wider than the 46.9 µm `capm` plate on each side, per `capm.3`);
`y1 = 48.82` is the met4 top-plate lead escaping the cell's top edge. Contents:
one 46.9 µm `capm` plate (89/44), one 47.9 µm met3 plate (70/20), **one** via3
cut at the plate centre (70/44), and three met4 shapes (71/20) forming the
0.42 µm lead.

| Port | x_um | y_um | Layer | Note |
| --- | --- | --- | --- | --- |
| `C0_BOT` | 0.0 | 23.95 | met3 (70/20) | the plate's own **left edge**, not a landing point — the 47.9 µm plate *is* the terminal. Every via2 into it is stepped `DECAP_VIA2_INSET_UM` = 2.0 µm inside the footprint instead, or `met3.enclosing.via2.1` fails |
| `C0_TOP` | 23.95 | 48.61 | met4 (71/20) | the 0.42 µm met4 lead the generator runs from the centre via3 out through the cell's top edge, so a top-plate tie arrives from the north on met4 and needs **no via at all**. The reported y is half the lead's width inside the bbox top (48.82) |

## Net list this assembly must route

Beyond each block's own already-closed internal wiring, per
`design/sar_adc_top.sch` / `design/sar_adc_top.spice`:

| Net | Members |
| --- | --- |
| `VINP` | external pin -> `sampling_frontend.VINP` |
| `VINN` | external pin -> `sampling_frontend.VINN` |
| `VDD` (analog) | external pin, `sampling_frontend.VDD`, `cdac_array.VDD`, `comparator.VDD` |
| `VREFP` | external pin -> `cdac_array.VREFP` |
| `VREFN` | external pin -> `cdac_array.VREFN` |
| `VCM` | external pin -> `sampling_frontend.VCM` |
| `CLK` | external pin -> `comparator.CLK`, `sar_sequencer.CLK` |
| `RST_B` | external pin -> `sar_sequencer.RST_B` |
| `TOP_P` | `sampling_frontend.TOP_P`, `cdac_array.TOP_P`, `comparator.VINP` |
| `TOP_N` | `sampling_frontend.TOP_N`, `cdac_array.TOP_N`, `comparator.VINN` |
| `COMP_OUT` | `comparator.OUTP` -> `sar_sequencer.COMP_OUT` |
| `SAMPLE_INT` | `sar_sequencer.PH_SAMPLE` -> `sampling_frontend.SAMPLE` |
| `DOUT<i>` (i=0..8) | `sar_sequencer.DOUT<i>` -> `cdac_array.SELp<i>`, `seln_inverters.DOUT<i>`, **and** external output pin `DOUT<i>` (3-way fanout) |
| `SELn<i>` (i=0..8) | `seln_inverters.SELn<i>` -> `cdac_array.SELn<i>` |
| `DOUT9` | `sar_sequencer.DOUT9` -> external output pin only (no CDAC/SELn use) |
| `BUSY` | `sar_sequencer.BUSY` -> external output pin |
| `comparator.OUTN` | left dead-ended (`OUTN_NC`) — not needed by the sequencer |
| `VPWR` (digital) | external pin, `sar_sequencer`'s met5 PDN strap, `seln_inverters`' met5 PDN strap (issue #355 — one net, **not** tied to analog `VDD`; see DR-010) |
| `VGND` (digital) | external pin, `sar_sequencer`'s met5 PDN strap, `seln_inverters`' met5 PDN strap (issue #355 — one net, **not** tied to analog `GND` *in metal*; see DR-010 and, for what the substrate does regardless, DR-012) |
| `GND` (analog) | external pin, `comparator.GND`, `sampling_frontend.GND`, `cdac_array.VSS` (issue #362 drew the pad on the first of those, then the only drawn analog-ground conductor here; issue #377 added the other two inside their own sub-block layouts and the met3/met4 mesh that joins all three. The substrate joins them regardless — that is DR-012's point, not this route's; what the mesh adds is a drawn path `klt drc` grades. See DR-012 and DR-013) |
| `Cdecap_a` (`VDD`/`GND`) | **two** placed `cap_mim_m3_1` unit cells across the analog pair — `MF = 2`, 8.870 pF, DR-017, placed by issue #440. The only devices this assembly's own top level instantiates; every other row here routes between sub-blocks. Bottom plates tap `comparator.GND`'s own met4 stub on met2; top plates tap `comparator.VDD`'s own met4 column on met4. See "On-die decoupling (DR-017)" |
| `Cdecap_d` (`VPWR`/`VGND`) | **two** placed `cap_mim_m3_1` unit cells across the digital pair — same size and value, same record. Each reaches its own met5 rail through one via4. See "On-die decoupling (DR-017)" |

**22** top-level external chip pins in total: `VINP, VINN, VDD, VREFP, VREFN,
VCM, CLK, RST_B, DOUT9..DOUT0, BUSY, VPWR, VGND, GND` (matching
`design/sar_adc_top.sym`'s own pin list exactly, in order). `VPWR`/`VGND` were
added by issue #355 and `GND` by issue #362; before #355 this list read
"Twenty … pins in total" and then named nineteen, which the LVS pin counts
(19/19/19) had always reported correctly.

The layout side still promotes **21** of those 22, and that is not a missing
pin: `GND` and `VGND` are one extracted net (`GND|VGND|VSS` since issue #377
joined `cdac_array`'s own `VSS` label to it — the shared p-substrate), so one
promoted layout pin answers both reference ports, which the LVS `matched=22`
count records. See DR-012 and DR-013.

## GND / VPWR / VGND: not a routing job (mostly)

Worked out from `klt extract --deck sky130`'s own documented substrate
synthesis (`layout/sampling-frontend-wells/README.md`, `layout/sampling-frontend/reference.spice`'s
header) plus `design/sar_adc_top.spice`'s own `.GLOBAL GND`/`.GLOBAL VDD`
declarations and its item-2 "known integration gap" note:

- **Analog `GND` needs no wire between the three blocks to reach a matching
  LVS verdict — and is wired between them anyway, on purpose (issues #362 and
  #377, [`DR-012`](../../spec/decision-records/DR-012-analog-ground-pad.md) and
  [`DR-013`](../../spec/decision-records/DR-013-analog-ground-mesh.md)).**
  `klt extract`'s sky130 deck synthesizes every NMOS/PMOS-body's p-substrate
  connection as one globally-shared substrate net *regardless of drawn
  geometry* — so before #377, `sampling_frontend`'s GND (no drawn pin at all)
  and `cdac_array`'s VSS (also no drawn pin) reported as the same net the deck
  assigns `comparator`'s real, drawn `GND` pin to, with **no wire required
  between the three blocks for this assembly to reach a matching verdict** on
  that specific net.

  That is a statement about the *verdict*, and it was allowed to stand in for
  a statement about the *design* for too long. The return path the deck was
  papering over is p-substrate resistance under the one device whose decision
  is referenced to it. Since #377 all three blocks draw a real ground terminal
  (`sampling_frontend.GND`, `cdac_array.VSS` — both added in those sub-block
  layouts) and this module ties them into one drawn conductor; the LVS verdict
  is unchanged by that, which is exactly why the mesh carries its own
  ablation evidence rather than pointing at a clean report. See "The analog
  ground pad and mesh" below.

  **Confirmed on the composed extraction, not just inferred from the per-block
  READMEs** (the caveat this paragraph used to carry):
  `reports/20260924-234053-66dca3c/extract.json` reports one net named
  `GND|VGND|VSS` carrying **692 devices** — the analog ground, the standard
  cells' substrate ties and the p-substrate, all one node, with
  `merged_net_labels` naming all three labels on it (it read `GND|VGND` at 692
  devices in the pre-#377 record; the third label is `cdac_array`'s own new
  `VSS` pin joining the merge, not a new node). That is the mechanism working
  as documented, one level up, and it is also the reason DR-010's domain
  partition can only ever be about *metal return paths and pads*, never about
  galvanic isolation.

  What the auto-merge never supplied is a **terminal**. Until #362 this block
  had `.GLOBAL GND` and no top-level `GND` pin anywhere, so the one net every
  analog device returns through had nothing a package could bond to, while
  `VDD` did. `klt erc` cannot see that distinction (one island is one island,
  pin or no pin), which is why it passed throughout. See "The analog ground
  pad" below for the geometry and DR-012 for the decision.
- **`VDD` (analog) is a real net and must be routed** between
  `sampling_frontend`, `cdac_array`, and `comparator` (and the external
  `VDD` pin) — it is not part of the substrate auto-merge.
- **Digital `VPWR`/`VGND` are ONE independent supply domain with their own
  top-level pins — resolved 2026-09-24 by issue #355 and
  [`DR-010`](../../spec/decision-records/DR-010-digital-supply-domain-partition.md).**
  They are **not** tied to the analog `VDD`/`GND` anywhere on-die; they are
  two distinct `.GLOBAL` nets (`design/sar_adc_top.spice` lines 323–324, since
  issue #258), each now also a formal top-level port of `sar_adc_top`, and the
  layout ties `sar_sequencer`'s and `seln_inverters`' own met5 PDN straps
  together and out to a pin of that name. Both domains sit at the same 1.8 V
  supply point (DR-001); the partition is of *domains and pins*, not voltages,
  and the star point between them is off-die. Read DR-010 for the
  substrate/supply-noise reasoning and for what that reasoning does **not**
  claim (nothing in `sim/` measures the coupling).

  <details>
  <summary>Superseded reading (pre-#355), kept because several documents still
  cite it</summary>

  This section used to say: "*Neither `VPWR` nor `VGND` is declared `.GLOBAL`
  in `design/sar_adc_top.spice`, and neither is a formal port of the
  `sar_sequencer` subckt call at the top level — so by ordinary SPICE hierarchy
  scoping, `sar_sequencer`'s own internal `VPWR`/`VGND` is a different net from
  `seln_inverters`'. **Do not tie them together.**"

  Two things were wrong with it by the time #355 read it. The `.GLOBAL` half
  had been **false since issue #258** (which added the `lvpwr1`/`lvgnd1`
  `global=true` label instances precisely so each rail would be one net across
  the hierarchy) — the prose was never updated, and
  `bin/generate-lvs-reference.py` had encoded the stale reading as
  `VPWR_SEQ`/`VPWR_SELN`. The "do not tie them" half was a *scoping* claim
  doing duty as a *physical* one: schematic scoping says nothing about whether
  a laid-out block is powerable, and item 11 graded the physical question FAIL.

  </details>

**Graded: the supply-continuity half now passes; item 11 as a whole is still
unmet (2026-09-24).** T1 checklist item 11 (Power delivery — structural,
klayout-tools#2025) grades the *physical* question — is the supply connected to
what it powers. Its first run (issue #344,
`erc-reports/20260923-143401-1ee4ba8/`) came back FAIL: `VPWR` and `VGND` each
resolved to **two** disconnected electrical islands, neither reaching a
top-level supply. Issue #355 fixed the layout, not the gate (the spec's graded
fields hash identically on every run — see the table below), and
`erc-reports/20260924-190825-f3622fc/` reported `erc_status: clean`, 0
findings — all four declared supplies at exactly one island each, no
`erc.supply_short`. The current record,
`erc-reports/20260924-230820-3e79547/` (issue #364), reports the same on the
layout that now also carries a drawn analog `GND` pad. **The item still does not
render `met`**:
`klt signoff` renders it `unmet` / `check_failed`, because its grading path
(`_grade_power_delivery`) checks the cited LVS part *first* and item 4's LVS is
still `mismatch` (klayout-tools#1878) — so the continuity half being clean is
not what the reason is about. Behind that sits a second, latent reason the run
never gets to: the item also requires zero `erc.missing_tie` from a tie the run
actually checked, and this spec declares no `ties[]` (klayout-tools#2169 would
turn a correct one into a false `erc.supply_short`), the state
`supply_spec_disclosed_tool_limitation` names. See "Structural supply check
(`klt erc`, T1 item 11)" below.

### The digital-rail route itself (issue #355)

`bin/build_layout.py`'s `digital_supply_rail()` — **one met5 rectangle per
rail, no via anywhere.** This is what open question 2 below had left untried.
The two macros are placed at the same `dy` (`OFFSETS`), so `sar_sequencer`'s
met5 strap for a rail and exactly one of `seln_inverters`' straps for the same
rail occupy the *same* global y band:

| Rail | Global y band (µm) | `sar_sequencer` strap x | `seln_inverters` strap x | Rail rectangle x |
|---|---|---|---|---|
| `VPWR` | −120.88 … −119.28 | 23.4175 … 61.5975 | 89.9875 … 172.2075 | 15.0 … 91.9875 |
| `VGND` | −134.48 … −132.88 | 23.4175 … 61.5975 | 89.9875 … 171.8675 | 15.0 … 91.9875 |

A rectangle spanning that band is therefore *colinear* with both straps — same
layer, same 1.6 µm width (`m5.1`'s own minimum, which is what both macros'
`klt place-and-route` drew) — so it merges into one polygon rather than
landing on anything. Three consequences, none cosmetic:

- **No via4 riser is needed**, so nothing has to satisfy `m5.3` (0.31 µm met5
  enclosure of via4) or `m5.4` (4.0 µm² minimum area — sixteen times the area
  of this module's own `ISLAND_PAD_UM` pad) on a freestanding pad. This module
  draws no met5 pad at all, and `MET5` is deliberately left out of
  `build_layout.py`'s `_METAL_CHAIN` so a future `riser(..., MET5)` fails loudly
  instead of minting an illegal pad.
- **No new spacing relation appears inside either macro.** Over each macro's
  own footprint the rectangle is geometrically identical to the strap it merges
  with, so the merged polygon's edges are the strap's own — already legal
  against that macro's own neighbouring straps, which sit 12.0 µm away in y
  (7.5× `m5.2`).
- **It crosses no other net.** The rectangle is horizontal and every strap is
  horizontal; `_check_digital_rail_clearance()` asserts every *other* strap's y
  band clears this one by at least `m5.2`, and that neither rail's west stub
  enters any other placed block's bbox. It passes *over* both macros' met4 PDN
  columns, which is not a connection without a via4.

The top-level `VPWR`/`VGND` pin labels land at `x = 18.0`, on the stretch of
each rectangle that lies west of both macros' footprints — so the promoted pin
is unambiguously on conductor this module drew (`--pin-source-cells` would not
promote a macro-internal label anyway). Top-level pins go 19 → **21**.

`klt drc` grades this geometry rather than the README arguing it: the pinned
0.6.0 deck authors `met5.width.1` / `met5.space.1` / `met5.area.1` (see
`reports/20260924-190817-f3622fc/drc.json`'s `coverage.rules_checked`) and the
record is clean, 0 violations. The `klt erc` cross-checks that show the met5
rectangle is what actually joins the two islands — including an ablation
against the pre-#355 GDS — are in `erc-reports/20260924-190825-f3622fc/`'s own
"Cross-checks".

### The analog ground pad (issue #362) and mesh (issue #377)

`bin/build_layout.py`'s `analog_ground_mesh()` — **one met3 trunk, three met4
droppers, one pad label.** Issue #362 drew the pad alone (a via riser on
`comparator`'s own `GND` met1 pin, global `(101.5, 193.8)`, plus a met4 stub
running **south** to `y = 170.0` where the top-level `GND` pin label sits);
issue #377 added the mesh below it, joining the other two analog blocks' own
drawn ground terminals to the same conductor. The pad's own coordinate did not
move.

| | |
|---|---|
| Members | `comparator.GND` met1 local `(1.3, 20.0)` → global `(101.5, 193.8)`; `sampling_frontend.GND` met2 local `(39.97, 52.32)` → global `(103.795, 140.57)`; `cdac_array.VSS` met1 local `(1.00, −31.60)` → global, same (that block is the floorplan's origin) |
| Trunk | met3 at `y = 165.0`, `x` −16.2 … 104.0 — in the open channel between `sampling_frontend`'s top edge (147.22) and `comparator`'s bottom edge (176.3) |
| Droppers | met4 at `x` 101.5 (comparator, `y` 164.8 … 194.0), `x` 103.795 (sampling_frontend, `y` 140.37 … 165.2), `x` −16.0 (the cdac corridor, `y` −31.8 … 165.2) |
| cdac escape | met3 at `y = −31.6`, `x` −16.2 … 1.2 — inside the array's confirmed-clear switch-row band |
| Pin label | met4.pin (`71/5`) at `(101.5, 170.0)`, unchanged from #362 |

Five things about that shape are load-bearing:

- **The trunk is met3 and every dropper is met4.** Four of
  `sampling_frontend`'s own pins (`TOP_P`, `TOP_N`, `VDD`, `SAMPLE`) cross this
  channel northbound on met4 at `x` 65.585 … 108.345; a met4 trunk would short
  every one of them. This is `analog_leg()`'s own layer-split rule, and the
  mesh is literally built from two `analog_leg()` calls sharing `GND_MESH_Y`
  as their jog row — the same primitive every other analog-region net here
  uses, including the degenerate `(x, y) → (x, y)` form that tees the
  comparator dropper in.
- **The cdac leg goes the long way round, for the same reason `VDD`'s does.**
  That block's `VSS` tap sits ~200 µm south, deep inside the array's own
  footprint, so the leg risers to met3 *inside* the switch-row band (verified
  free of that macro's own met3/met4 across its full width, re-confirmed
  against the post-#377 GDS), exits west past the array's edge, and climbs an
  exclusive met4 corridor track at `x = −16.0` — 2.0 µm west of
  `SAMPLE_INT`'s own crossing column, 4.0 µm east of the external `VDD` pin's
  met4 landing.

- **South, not north.** Every other analog net leaves its pin northward into a
  per-net `analog_leg` jog row. `GND` cannot: `comparator`'s own `CLK` column
  rises to met4 at `x = 102.1` and runs north from `y = 198.3`, **0.6 µm** from
  this pin's own x — two 0.4 µm met4 wires sharing that gap leave 0.2 µm, and
  `m4.2` needs 0.30 µm. Running south instead puts the two columns' `y` spans
  4.1 µm apart, so they never face each other at all. Issue #362 asserted that
  as a pin-y-ordering argument; since #377 `_check_analog_ground_mesh()`
  asserts the thing itself, **geometrically**: every met3/met4 shape the mesh
  draws is checked against every met3/met4 shape the rest of this module draws
  and must clear it by `m3.2`/`m4.2` — with *touching* an explicit failure,
  because a mesh shape that touches another net's shape has merged `GND` with
  it. That covers the `CLK` case exactly (their real separation is 4.2 µm)
  instead of re-deriving it, and it covers the other 700-odd shapes too. A
  future re-route fails in `build_layout.py` rather than in `klt drc` — and
  the check is live, not decorative: moving the mesh corridor onto
  `SAMPLE_INT`'s column raises "they TOUCH, which merges GND with another
  net", and moving it 0.02 µm inside the limit raises the spacing message.
- **It crosses nothing on the way out.** `comparator` draws **no met3 and no
  met4 at all** (direct merged-`Region` dump of its committed GDS: layers
  65/20, 66/20, 66/44, 67/20, 67/44, 68/20, 68/44, 69/20, 64/20, 65/44 only),
  so the stub passes over that macro's own footprint on an empty level, and the
  stretch below it — `y` 147.22 … 176.3, the channel between `sampling_frontend`
  and `comparator` — holds no block bbox. The same assertion checks the label
  lands in that channel rather than inside either macro.
- **The pad still has no horizontal leg of its own.** The mesh trunk is not
  one: it runs 5 µm *below* the label, joining the three blocks, and is not in
  series with the pad. Grouping this pin with the other analog supply pins in
  the west corridor would still cost ~130 µm of met3 on a new exclusive jog
  row, crossing four met4 corridor columns, in series with the one net where
  series metal buys nothing. There is no pad ring in this composition — every
  pin label sits where its own net's conductor already is — so the grouping has
  no consumer yet. DR-012 records the trade and marks the position provisional.

`klt drc` grades this geometry rather than the README arguing it:
`reports/20260924-234053-66dca3c/drc.json` is clean, 0 violations — and since
the pinned 0.6.0 deck authors `met1.area.1` … `met5.area.1` (see "Minimum-area
rules" above), that verdict now covers minimum area too. The independent
cross-check agrees, re-run on this record's own GDS after issue #363 corrected
the script's property-aware-merge bug: **0** shapes below every one of
`m1.6`/`m2.6`/`m3.6`/`m4.4a`/`m5.4`, the same **0** the pre-#377 GDS
(`reports/20260924-214710-b323061/`) measures under the same corrected script.
The mesh shows up in that readout only as polygon counts — met1 1503 → 1504,
met2 1518 → 1519, met3 1342 → 1345, met4 29 → 31 — all above threshold, because
every riser pad that stands alone on its own layer is `ISLAND_PAD_UM`-sized for
exactly this reason.

### Why the mesh needs an ablation, and what it showed

A clean DRC/LVS/ERC pass is **not** evidence that this mesh exists, let alone
that it works, and saying so is the whole point of recording it this way.
`klt extract`'s sky130 deck ties every NMOS body to one synthesized global
substrate net regardless of drawn geometry, so the composed layout reported a
single 692-device `GND|VGND` net *before* the mesh was drawn
(`reports/20260924-214710-b323061/extract.json`) and reports the same
692-device net after it — now named `GND|VGND|VSS`, the only visible
difference being that `cdac_array`'s newly drawn `VSS` label joined the
merge. `klt erc`'s "one island" verdict
on `GND` likewise read `1` before and reads `1` after. Reading either as proof
that the three blocks' grounds are joined *in metal* is exactly the reading
error DR-012 exists to retire, one level down.

`bin/probe-ground-mesh.py` is the measurement that separates the two claims.
It rebuilds this assembly twice from the record's own committed sub-block GDS
— once as shipped, once with `build_layout.py --ablate-ground-mesh`, which
draws DR-012's pad exactly as #362 shipped it and omits *only* #377's mesh —
and grades both against the byte-identical ERC supply spec:

| Variant | `erc_status` | `GND` |
|---|---|---|
| full (as shipped) | `clean`, 0 findings | one island |
| mesh ablated | `violations`, 1 finding | `erc.unconnected_net`: *"declared net 'GND' resolves to 2 disconnected electrical islands (expected exactly one)"* |

The two islands the ablated run names are `sampling_frontend`'s own ground
(met1, bbox 103.495 … 130.115 × 86.45 … 140.72) and the comparator's plus its
pad (met4, 100.2 … 102.62 × 169.8 … 197.8). `VDD`, `VPWR` and `VGND` are
unmoved between the variants, as controls, and the full variant's recomposed
GDS is **byte-identical** (sha256) to the record's own — so the two runs
differ by the mesh and nothing else.

**That island count covers two of the mesh's three legs, not three**, and the
gap is a naming one rather than a wiring one: `comparator` and
`sampling_frontend` both label their terminal `GND`, while `cdac_array`'s is
labelled `VSS` (its own schematic port name), which the graded ERC spec does
not declare — so that leg's orphaned island in the ablated run has no declared
name for `klt erc` to report. Reading the 2-island finding as covering all
three would be a smaller copy of exactly the over-read this whole section
exists to retire, so the probe asks a second question. It re-grades the same
two GDS against a **scratch** spec — the graded one plus a `VSS` supply entry,
written to the work directory and never committed:

| Variant | graded spec | scratch spec (`+VSS`, diagnostic) |
|---|---|---|
| full (as shipped) | `clean` | `erc.supply_short`: *"declared nets 'GND' and 'VSS' are electrically the same net (shorted together)"* |
| mesh ablated | `GND` splits into 2 islands | no `GND`/`VSS` short — `GND` splits instead |

A short between two declared supplies is normally a defect; here it is the
measurement. `klt erc` sees drawn conductor and nothing else, so "these two
labels are one electrical net" is a statement about *metal* — which is
precisely what the `cdac_array` leg claims, and it is present only when the
mesh is. The graded spec deliberately does **not** declare `VSS`: doing so
would turn this block's own T1 item 11 record red over a short that is the
design.

The summary of both passes is committed at
`erc-reports/20260924-234116-66dca3c/ground-mesh-ablation.json`; the script
exits 3 if **either** prediction fails, so a mesh that stopped mattering —
in whole or in that one leg — would turn the check red rather than quietly
passing.

The earlier, narrower ablation from #362 — cut `via3` and the pad separates
from `comparator`'s ground — is in the previous ERC record's own
"Cross-checks".

### On-die decoupling (DR-017)

[`DR-017`](../../spec/decision-records/DR-017-on-die-decoupling-budget.md)
(issue #431, PR #449) sizes **one `sky130_fd_pr__cap_mim_m3_1` per supply
domain at `W = L = 46.9 µm`, `MF = 2` → 8.870 pF each**: `Cdecap_a` across the
analog `VDD`/`GND` pair, `Cdecap_d` across the digital `VPWR`/`VGND` pair, both
in `design/sar_adc_top.sch`/`.spice`. That record deliberately left the layout
to a separate pass — issue #440, whose record is
`reports/20260926-081248-203cca3/` and whose ERC record is
`erc-reports/20260926-081822-203cca3/`.

**`MF = 2` is drawn as what it is: two matched 46.9 µm unit cells per domain,
four placements in all.** The unit is `klt gen cap_array` at `num = 1`, the same
generator at the same plate size that `layout/sampling-frontend/` already ships
DRC-clean for its own `Csamp_{p,n}`. The two shapes issue #440 named were (a)
teach `bin/build_layout.py` to draw the met3/`capm`/via3/met4 stack by hand, or
(b) build the decap as its own sub-block with its own generator and DRC record.
**Neither was chosen; a third was.** The cell is generated *inside this flow*
(`run-flow.sh` step 2b, from `build_layout.py`'s own `DECAP_GEN_PARAMS` via
`decap.request.json`) and placed as four more `blocks[]` entries in the same
`klt gen-compose` request the five sub-blocks use. That buys (a)'s single flow
and single record without (a)'s hand-drawn MiM stack, and it buys (b)'s
already-proven generator without a fifth directory whose only content would be
one 47.9 µm cell. `--verify-decap` then asserts the generator's own reported
bbox and both port positions against the placement tables on every run, so a
`klt` bump that moves the cell fails the flow instead of silently mis-tieing
four capacitors.

#### The met3/met4 real-estate question, answered by measurement

DR-017's Decision §3 allocates 8798.44 µm² of `capm` — 8.14 % of the composed
die — on the argument that a MiM cap is a **back-end** device and can therefore
sit *over* sub-blocks that route below met3. Its own "Open items" says that
argument was never checked against the composed die's actual back-end
occupancy. `bin/probe-decap-sites.py` checks it:

```
layout/sar-adc-top/bin/probe-decap-sites.py \
  --record   layout/sar-adc-top/reports/20260926-081248-203cca3 \
  --baseline layout/sar-adc-top/reports/20260924-234053-66dca3c
```

committed as `reports/20260926-081248-203cca3/decap-ties.json`. Back-end
occupancy of the **last pre-placement** composed die (`...-66dca3c`), against
its own 280.450 × 385.500 µm = 108113.475 µm² bounding box:

| layer | shapes | merged area | share of die |
|---|---|---|---|
| met3 | 1639 | 12996.221 µm² | 12.02 % |
| via3 | 1487 | 59.354 µm² | 0.06 % |
| met4 | 235 | 3526.432 µm² | 3.26 % |
| via4 | 17 | 10.880 µm² | 0.01 % |
| met5 | 33 | 896.090 µm² | 0.83 % |
| `capm` | 1028 | 8280.162 µm² | 7.66 % |

**So the budget is confirmed placeable, and it is not close.** met3 — the
tightest of the six, because it is both a routing plane *and* the MiM bottom
plate — was 88 % free; met4 was 97 % free. Two free rectangles hold all four
units with a 1.0 µm keep-out and **zero** clash against any of those layers:

| corridor | rectangle | size | units that fit | clash |
|---|---|---|---|---|
| analog — east of `comparator`, north of `sampling_frontend` | (120.0, 139.5)–(258.5, 219.5) | 138.5 × 80.0 µm | 2 × 1 | 0 µm² |
| digital — east of `seln_inverters`, south of `cdac_array` | (193.0, −165.0)–(260.2, −6.0) | 67.2 × 159.0 µm | 1 × 3 | 0 µm² |

The digital pair is stacked in *y* rather than side by side because that
corridor is 67.2 µm wide: one 47.9 µm unit fits across it, two do not. The four
placed footprints (`decap_a0` (128.0, 150.0), `decap_a1` (180.0, 150.0),
`decap_d0` (196.0, −150.0), `decap_d1` (196.0, −98.0)) each report **CLEAR**
against the pre-placement geometry grown by the keep-out.

**Two consequences worth stating plainly.** First, **the allocation cost no die
area at all**: both sites are inside the *pre-existing* bounding box, which the
new record reports unchanged at 280.450 × 385.500 µm, so nothing was displaced
and nothing grew. DR-017's "8.14 % of the die" is therefore an overstatement of
the cost in the only currency that matters here — it is 8.14 % of the die's
*`capm` layer*, not 8.14 % of its area budget. Second, **finding more free
met3/met4 than DR-017 assumed is not licence to raise `MF`.** DR-017 Amendment A
(issue #431) measures the response as *saturating*: `MF = 2` already captures
98.2 % of what `MF = 32` achieves, so the extra capacitance the free field could
hold buys 0.495 mV. The measurement above closes the area question; it does not
reopen the sizing one.

#### How each capacitor reaches its domain

The two terminals are reached on **different layers, for a deck reason rather
than a floorplan one**. sky130's extraction deck removes every met3 shape that
interacts with a `capm` plate from generic met3↔met4 (via3) connectivity — that
exclusion is what stops the cap's own DRM-required centre via3 from reading as a
plate-to-plate short. So a **bottom plate is reachable only from below**
(via2 from met2) and a **top plate only from above** (met4, merging with the
unit's own met4 lead); a new met3 shape anywhere inside a unit's footprint would
short the two plates outright.

| tie | path | conductor |
|---|---|---|
| `Cdecap_a` return (`GND`) | met4→met2 riser on `comparator.GND`'s own met4 stub at y = 172.0, met2 east under both units, via2 up 2.0 µm inside each bottom plate's west edge | met2, 2.0 µm |
| `Cdecap_a` supply (`VDD`) | met4 strap at y = 216.0 east from `comparator.VDD`'s own met4 column, one met4 column down onto each unit's own top-plate lead — **no via on this net** | met4, 2.0 µm |
| `Cdecap_d` supply (`VPWR`) | one via4 off the met5 rail at x = 185.0, met4 strap east, one met4 column north through both leads | met4, 2.0 µm |
| `Cdecap_d` return (`VGND`) | one via4 off the met5 rail at x = 190.0, met4→met2 riser, an L of met2 (east, then north), via2 up into each bottom plate | met2, 2.0 µm |

Every conductor here is **2.0 µm wide — 5× this module's own `WIRE_W`** — and
both digital ties leave their rail at the rail's own centre-line y, so neither
adds a bend the rail does not already have. `DIG_RAIL_EAST_X` extends each met5
rail east past `seln_inverters`' own strap to give the via4 a landing in open
field; that is the same same-layer merge the rails' west stretch already is, so
it creates no new met5 spacing relation and needs no via of its own.

The analog return deliberately taps **`comparator.GND`'s own met4 stub**, not
the mesh trunk. Two reasons, both asserted in `_check_decoupling_caps()` rather
than left to this prose: it is the shortest path to the comparator, whose
decision reference is the node DR-012 and DR-017 both care about; and it is the
one piece of analog-ground conductor `--ablate-ground-mesh` still draws, so the
decoupling pair is **identical in both build variants** and
`bin/probe-ground-mesh.py`'s two arms still differ by the mesh and nothing else.
That is confirmed in the new ERC record, not just argued: `controls_unmoved:
true` / `controls_moved: []` — ablating the mesh moves `VDD`, `VPWR` and
`VGND`'s island counts not at all, which it would not if either digital tie had
accidentally reached analog ground.

#### What the placement costs in series resistance — DR-017's own open residual

DR-017's measured benefit was obtained with an **ideal** capacitor, and its
closing open item names the series resistance of the route as the one thing that
can erode it. Nothing this flow grades can see it: `klt drc` grades shapes,
`klt erc` is a connectivity model with no resistance in it, and LVS here is a
pre-existing mismatch. `probe-decap-sites.py` therefore builds a lumped DC
ladder for each tie from the **same `build_layout.py` constants
`decoupling_caps()` draws from**, evaluates it with the PDK's own
`libs.tech/ngspice/r+c/res_typical__cap_typical.spice` values
(`rm2 = 0.125`, `rm3 = rm4 = 0.047 Ω/sq`; `rcvia2 = rcvia3 = 3.41 Ω/cut`,
`rcvia4 = 0.38 Ω/cut`), and — the part that makes it worth reading — **verifies
every wire segment against the rectangles the record's own `draw.request.json`
actually carries**, failing the flow if the model has drifted from the layout.
(That check earns its keep: it rejected a first draft of the probe that used one
rail y for both digital returns.)

| tie | shared leg | near / far branch | tie total |
|---|---|---|---|
| `VDD` (analog supply) | 0.795 Ω | 3.842 / 5.064 Ω | **2.980 Ω** |
| `GND` (analog return) | 8.601 Ω | 3.410 / 6.660 Ω | **10.857 Ω** |
| `VPWR` (digital supply) | 1.641 Ω | 3.410 / 4.632 Ω | **3.605 Ω** |
| `VGND` (digital return) | 7.700 Ω | 3.410 / 5.765 Ω | **9.843 Ω** |

| domain | C | ESR | Q at the 1221.5 MHz DR-015 resonance | ESR = X_C at |
|---|---|---|---|---|
| analog (`VDD`/`GND`) | 8.870 pF | **13.837 Ω** | 1.06 | 1.297 GHz |
| digital (`VPWR`/`VGND`) | 8.870 pF | **13.448 Ω** | 1.09 | 1.334 GHz |

**The dominant term is not the metal — it is single-cut vias.** Each return path
has three 3.41 Ω cuts (the met4→met2 riser's two, plus the via2 into each plate)
against each supply path's one, which is why the return ties are 3.6× and 2.7×
their own domain's supply tie *despite* the 2.0 µm conductor. Of the analog
return's 8.601 Ω shared leg, 6.82 Ω is those two riser cuts and only 1.781 Ω is
28.5 µm of met2.

**What that does and does not mean for DR-017.** The pair still behaves as a
capacitor over the whole band the bounce lives in — ESR does not reach the pair's
own reactance until ~1.3 GHz. But at the 1221.5 MHz resonance that 8.870 pF
forms with DR-015's 1.914 nH per-terminal package inductance, Q ≈ 1.06: the ties
are **comparable to** the reactance there, so the ideal-cap measurement DR-017
reports is optimistic at the top of the band, by an amount this pass has not
simulated. Two honest halves of that: a Q near 1 also *damps* the resonance,
which works in the bounce's favour, and the sign of the net effect is a
simulation question, not a layout one.

**The fix, if it is wanted, is a via array, not a wider strap.** Widening 2.0 µm
conductor buys almost nothing when ~80 % of a return tie is via cuts; replacing
each single-cut riser and plate entry with a 2 × 2 array would cut the ESR ≈ 3×.
That change **moves no device and alters no declared value**, so it needs no
superseding decision record — but it does need a re-measurement to say what it
buys, which is a `sim/supply-impedance-sensitivity/` run and therefore out of
this pass's scope. Tracked as its own follow-up.

## Structural supply check (`klt erc`, T1 item 11)

| | |
|---|---|
| Spec | `layout/sar-adc-top/erc-supply-spec.json` |
| Runner | `layout/sar-adc-top/bin/run-erc.sh` (after `layout/bin/setup-erc-venv.sh`) |
| Records | `layout/sar-adc-top/erc-reports/<record-id>/` (`erc.json` + `record.md`), `erc-reports/LATEST` |
| Tool pin | `layout/erc-requirements.txt` → `klayout-tools==0.6.0` / `klayout==0.30.12` |
| Current record | `erc-reports/20260926-081822-203cca3/` — `erc_status: clean`, 0 findings, grading `reports/20260926-081248-203cca3/sar_adc_top.gds` (the first ERC record in this chain graded on **different geometry** rather than re-minted prose) |

| Record | Graded GDS | Supply continuity | Item 11 as graded |
|---|---|---|---|
| `20260923-143401-1ee4ba8` (issue #344, first run) | `reports/20260919-050355-fb11617/` | **FAIL** — `VPWR`/`VGND` 2 islands each | `unmet` |
| `20260924-190825-f3622fc` (issue #355) | `reports/20260924-190817-f3622fc/` | **PASS** — all four supplies 1 island each, 0 findings | `unmet` — `erc.missing_tie` is not computed (below) |
| `20260924-214731-b323061` (issue #362) | `reports/20260924-214710-b323061/` | **PASS** — unchanged, all four supplies 1 island each, 0 findings | `unmet` — same two reasons |
| `20260924-234116-66dca3c` (issue #377, ground mesh) | `reports/20260924-234053-66dca3c/` | **PASS** — unchanged, all four supplies 1 island each, 0 findings (evidence for the mesh is the ablation above, not this row) | `unmet` — same two reasons |
| `20260925-011943-f981dc9` (issue #364, prose re-mint) | `reports/20260924-234053-66dca3c/` | **PASS** — same bytes, same report | `unmet` — same two reasons |
| `20260925-044420-f039594` (issue #364, second prose re-mint) | `reports/20260924-234053-66dca3c/` | **PASS** — same bytes, same report | `unmet` — same two reasons |
| `20260926-081822-203cca3` (issue #440, DR-017 decoupling placed) | `reports/20260926-081248-203cca3/` | **PASS** — all four supplies 1 island each, 0 findings, on a GDS that gained four capacitors and four new conductors onto already-declared supplies | `unmet` — same two reasons |

**The gate has not moved across any of those seven runs, and that is checkable.**
`klt erc` grades `stackup`, `vias`, `nets[]` and `ties_disclosure.kind`; it
ignores `_comment` keys and treats `ties_disclosure.reason` as a string to echo.
Canonicalising exactly that graded subset and hashing it gives
`7f48fd89387b64b24c379baff04e6ef38361610240eac2c2d0adb8470584d982` on **every**
revision of the spec from #344 to today — `run-erc.sh` prints it
(`graded-spec subset sha256=…`) on each run, so it is re-derived rather than
transcribed. The whole-file `provenance.spec.content_hash` carried that argument
for the first four rows (`sha256:fd4f5a93…`, byte-identical); issue **#364**
refreshed the spec's stale prose comments three times — once before the mesh
landed, once after (row 5), and once more (row 6) to correct two GDS-specific
shape counts a Judge round found the row-5 re-mint had left describing the
superseded `…-b323061` run instead of the graded `…-66dca3c` one — since none
of the three changed the graded *layout*, only the spec. The whole-file hash
moved to `sha256:9224444c…` for row 5 and `sha256:429841c8…` for row 6 while
leaving the graded digest fixed both times. The verdict moved exactly twice:
once because the layout moved (row 4, issue #377), and never because the gate
did.

The third through sixth rows are the ones worth reading carefully, for
different reasons. In the third, the number did **not** move and issue #362
nevertheless changed something real: `GND` resolved to one island before it had
any top-level pin and resolves to one island now that it has one, because "one
island" and "reaches a pad" are different claims and a geometric connectivity
model makes only the first. In the fourth, the number *again* did not move, and
issue #377 nevertheless changed something real in the same way: `GND` read one
island before three sub-blocks' grounds were meshed in drawn metal and reads
one island after — the evidence for the mesh is the ablation in that record's
own "Cross-checks", not this row. Both cases are why a passing supply row here
must be read with the cited ERC record's own "Why `GND`'s pass must be read
narrowly" section beside it. In the fifth and sixth, *nothing* about the layout
or the graded spec moved: a recursive field diff of any two adjacent records'
`erc.json` files among rows 4-6 differs in exactly the leaves
`provenance.spec.content_hash` and (for row 6 vs. row 5) `ties_disclosure.reason`
— the record's own "The non-tuning argument" section carries the command.

This is a verdict **about** one `reports/<record-id>/` GDS, pinned to it by
content hash; it regenerates no geometry, which is why it lives in its own
`erc-reports/` tree rather than inside a `reports/` record (those are
append-only). It runs from its own venv (`layout/.venv-erc`,
`layout/erc-requirements.txt`) rather than the DRC/LVS flow's `layout/.venv`
— the two pins are free to move independently, and the reason that separation
was introduced was that `klayout-tools==0.5.0`'s `klt erc` emitted no
`provenance` block and so could not pin a report to its input at all. Both
files now pin 0.6.0; see `layout/erc-requirements.txt`'s own header.

`erc.missing_tie` is deliberately **not computed** (no `ties[]` declared),
disclosed in-report as `ties_disclosed_tool_limitation`: klayout-tools#2169
turns a correct `ties[]` declaration on a routed standard-cell design into a
false `erc.supply_short`. The well-tie evidence standing in for it — tap-cell
instances, body/tub labels, and the LVS `net_correspondence` — is named in the
record, along with where that stand-in is weaker than it looks.

## Composition mechanism actually used: `klt gen-compose` as a pure placer

The section below is kept as the *investigation record* that led to this
decision; what `layout/sar-adc-top/bin/build_layout.py` actually implements
resolved open question 4 the other way from what this section originally
proposed: `klt gen-compose` is used **purely as a placer**
(`connectivity: []`, every block a `blocks[].cell` entry per #1189), and
**every** net — digital and analog alike, not just `TOP_P`/`TOP_N`/`VDD` —
is hand-routed via `klt draw`, matching every other full-custom flow in this
repo (`comparator/`, `sampling-frontend/`, `sampling-frontend-wells/`) for
the same reason: `klt gen-compose`'s own bundle router's geometry is
advisory (`klt drc` remains the authority), and this composition's own
mixed digital/analog, multi-metal-layer interconnect needs the same
explicit layer-alternation control (met1/met2 in the digital channel,
met3/met4 in the analog crossings — see `build_layout.py`'s own docstring)
that made getting a first attempt to a clean `klt drc` verdict tractable at
all. Once #165 landed, the two originally-blocked nets (`VDD`,
`SELp<i>`/`SELn<i>`) routed the same way as everything else — no separate
mechanism was needed for them specifically.

Open questions this investigation worked through before that implementation
(kept for the record):

1. ~~`cdac_array.VDD`'s pin sits on the well layer...~~ **Resolved (by
   investigation, not by a fix): not a "which layer does `gen-compose`
   expect" question at all.** Direct GDS inspection found `cdac_array.VDD`
   has no drawn conductor whatsoever, on any layer — see the "Status"
   section above and #165. Routing this net is not possible until #165 adds
   a real tap-to-metal landing pad; there is no alternative landing point on
   the *same physically-connected net* to fall back to, because no metal
   touches that net anywhere in the block.
2. `sar_sequencer.VPWR`/`VGND` and `seln_inverters.VPWR`/`VGND` are buried
   met5 straps well inside each macro's own footprint, not edge-abutting
   pins — reaching them means a routed wire's own met5 geometry has to
   extend into (and overlap) that macro's own bounding box at the exact
   strap coordinates above, which is legal (same-layer overlap merges,
   rather than violating spacing) but has not been tried here. **Update
   (2026-09-19, superseded):** it read "neither `VPWR` nor `VGND` is a formal
   port of either macro's subckt call at the top level — so this issue does not
   need to reach these straps at all; they stay self-contained per-macro
   rails." **Resolved the other way, 2026-09-24 (issue #355, DR-010): the
   straps ARE reached, and the original prediction above was the right one.**
   Same-layer overlap does merge; it needs no via and no pad, and DRC is clean.
   What the superseded update got wrong was treating a schematic-scoping
   argument as settling a physical question — `klt erc` then graded the
   physical question FAIL (two disconnected islands per rail, neither reaching
   a top-level supply). See "The digital-rail route itself (issue #355)" above
   for the geometry, and DR-010 for why the rails are one independent domain
   rather than being tied to analog `VDD`/`GND`.
3. `cdac_array` (223 µm wide) is far wider than `sampling_frontend` (196 µm)
   or `comparator` (24 µm), and its `TOP_P`/`TOP_N` sit on opposite edges
   ~221 µm apart while `sampling_frontend`/`comparator`'s own `TOP_P`/`TOP_N`
   sit within a ~45 µm span. **Resolved floorplan strategy:** since
   `cdac_array`'s own two pins are fixed by its already-closed #100 layout
   (not something #103 may touch), the only lever left is *where* the other
   two blocks' matching `TOP_P`/`TOP_N` pin pair sits along that same span.
   Centring `sampling_frontend`'s (and `comparator`'s) own `TOP_P`/`TOP_N`
   pair on `cdac_array`'s own `TOP_P`/`TOP_N` **midpoint**
   (`x = (-2.4 + 216.8) / 2 = 107.2` µm in `cdac_array`'s local frame) makes
   the routed `TOP_P` leg and the routed `TOP_N` leg equal length (~109 µm
   each) by construction — the best available mitigation for the Curator's
   "IR-drop/coupling into matching-critical sub-blocks" concern, given
   `cdac_array`'s own pin placement cannot be revisited here. A single
   left-to-right row placement (`gen-compose`'s `"row"` strategy) cannot
   express this — it needs `"explicit"` placement with a hand-computed
   per-block origin, which is what every existing full-custom flow in this
   repo already uses gen-compose for (see below).
4. Whether `klt gen-compose`'s bundle router can be trusted for the analog
   `TOP_P`/`TOP_N`/`VDD` nets without introducing IR-drop/coupling risk the
   Curator flagged (#103's own complexity note) — likely needs a manually
   reviewed placement/routing plan for those specific nets even if the
   purely-digital nets (`DOUT<i>`/`SELn<i>`/`COMP_OUT`/`SAMPLE_INT`/`CLK`/
   `RST_B`) route automatically. Given #165's `VDD` finding, `VDD` will need
   hand-drawn routing (`klt draw`, the same escape hatch
   `layout/comparator/bin/build_layout.py` already documents and uses) once
   a real landing pad exists — `gen-compose`'s own bundle router only routes
   between *already-real* metal ports, never manufactures a landing point on
   a bare well/poly shape.

## LVS pin declaration: resolved (klayout-tools#1513 → #1515)

**Resolved.** `klt extract --pin-source-cells route__SAR_ADC_TOP_ROUTE`
(klayout-tools#1515, merged 2026-09-06) now promotes exactly this design's
own intended 19 top-level pins — 19/19/19 promoted/reference/matched, per
every record from `reports/20260907-110058-a546200/` onward. Two changes
were needed together, both in `layout/sar-adc-top/bin/run-flow.sh`:

1. **`--pin-source-cells <cell>`** resolves a named cell's own drawn pin
   labels to their real net *by position*, not by name — sidestepping every
   failure mode the three name-matching mechanisms hit (below). This
   flow's own 19 external-pin labels are all drawn directly in the routing
   cell `build_layout.py`'s own interconnect populates (step 3 of
   `run-flow.sh`), so naming that one cell as the pin source is exactly the
   filter this composition needs.
2. **The routing cell needed a globally-unique name first.** Every other
   `bin/build_layout.py` flow in this repo (`comparator/`,
   `sampling-frontend/`) also names its own internal routing cell `ROUTE`
   by convention — so once all five sub-block GDS files are merged into one
   composed layout, there are *three* distinct cells that could answer to
   that name (this flow's own top-level one, plus one buried inside each of
   `comparator`'s and `sampling_frontend`'s own internal composition).
   `--pin-source-cells ROUTE` matched **none** of them (0 pins promoted) —
   `klt gen-compose`'s own deterministic `"<block-id>__<cell-name>"` naming
   (docs/cli/gen-compose.md, #1189) means none of the three is literally
   named `ROUTE` after composition; each is `<block>__ROUTE` (or
   `<block>__ROUTE$N` where a same-named cell from a different source GDS
   also collided during the underlying GDS merge). Renaming this flow's own
   cell to `SAR_ADC_TOP_ROUTE` (via `klt draw --cell-name`) makes it
   globally unique, so `--pin-source-cells route__SAR_ADC_TOP_ROUTE`
   (the block id `route` this flow's own compose request already uses,
   `__`, the new cell name) resolves unambiguously — confirmed empirically:
   the ambiguous `ROUTE` name promotes 0 pins; the disambiguated
   `route__SAR_ADC_TOP_ROUTE` promotes exactly 19.

Requires a `klt` build with klayout-tools#1515. Originally reached only via
the (now-retired) `SAR_ADC_TOP_KLT` env-var override, since the fix postdated
`layout/requirements.txt`'s then-pinned `klayout-tools==0.4.0`; the officially
released `klayout-tools==0.5.0` (published 2026-09-15, now the pinned
version) carries it, so this flow runs entirely on the pinned
`layout/.venv/bin/klt` — see "Provenance" below.

<details>
<summary>Historical trace: why <code>--top-cell-pins</code>/<code>--pins</code>/<code>--def-pins</code> each failed (kept for the record)</summary>

`layout/sar-adc-top/bin/run-flow.sh` used to try each of `klt extract`'s
three *name-matching* declared-top-level-pin mechanisms in sequence, and
none reproduced exactly this design's intended 19-port interface once the
five sub-blocks were composed and flattened:

- **`--top-cell-pins`**: demotes this flow's *own* genuine top-level pin
  labels too, since `build_layout.py`'s own `route` block — where every one
  of them lives — is an *instanced* sub-cell of the composed top cell, not
  the literal top cell itself (the same shape `layout/comparator/bin/
  build_layout.py`'s own comment already documents choosing *not* to use
  `--top-cell-pins` for, for the identical reason — but that flow's own five
  sub-blocks are freshly-generated `klt gen` device primitives with no
  competing internal pin labels of their own, so it never hits the
  *over*-promotion problem below either).
- **`--pins`** (issue #514): does an exact string match against each
  promoted net's own name — but once a genuine top-level port merges with an
  internal macro's own generic pin label (e.g. `sar_sequencer`'s own first
  clock-buffer gate, literally named `A` in its post-route netlist, sharing
  a net with this design's own `CLK`), `klt extract`'s own net-naming joins
  every label found on that net into one string (`A,CLK` internally) — and
  there is no way to express an already-comma-joined name as a single
  `--pins` token, since `--pins`'s own argument syntax uses that same comma
  as its *item* separator. Confirmed empirically: `--pins CLK` reports "0
  declared pin names matched," full stop.
- **`--def-pins`** (issue #1390): the automatic, DEF-derived counterpart —
  works around `--pins`'s limitation by matching *any* comma-joined
  component instead of the whole string, so declaring `CLK` alone does
  reach the `A,CLK` net above. But two of this design's five sub-blocks are
  independently-synthesized standard-cell macros, each free to reuse the
  same generic labels (`A`/`X`/`Q`/`Y`) for *unrelated* internal nodes — a
  downstream, already-buffered copy of the clock net, entirely internal to
  `sar_sequencer`, also happens to carry `CLK` as one of *its own* joined
  labels (an artifact of the same generic reuse, not an actual electrical
  connection to this design's own top-level `CLK` port — see this
  investigation's own connectivity-verification table, which shows the true
  `CLK` net's device count separately and correctly). `--def-pins CLK`
  cannot distinguish "the net whose only relevant label is `CLK`" from "any
  net with `CLK` among several labels," so it over-promotes: the composed
  layout ends up with 23 promoted pins against this design's own 19,
  guaranteeing an `LVS` pin-count mismatch regardless of how correct the
  underlying routing is.

Filed generically (no design-specific detail) at
[klayout-tools#1513](https://github.com/2AMLogic/klayout-tools/issues/1513)
per `CLAUDE.md`'s friction protocol — the same protocol, and the same class
of gap, that produced klayout-tools#1385/#1390 for a single placed-and-routed
macro (`layout/sar-sequencer/`'s own LVS reference provenance section); this
is that same gap recurring one composition level up, where there is no
single top-level DEF left to anchor `--def-pins` on. Closed by
[klayout-tools#1515](https://github.com/2AMLogic/klayout-tools/issues/1515),
merged 2026-09-06 — see above.

</details>

## LVS device/topology blocker (klayout-tools#1552, now #1878 + #1876)

**Historical measurement below is against `klayout-tools==0.4.0`
(via the since-retired `SAR_ADC_TOP_KLT` override) — see "Update: re-run
against the officially pinned `klayout-tools==0.5.0`" further down for the
current numbers and the two upstream issues that replaced this section's
original #1552.**

Reaching 19/19/19 pins was necessary but not sufficient for a
`klt lvs` **match**. With `--pin-source-cells` wired in and
`options.combine_devices: true` (the same top-level LVS request
`run-flow.sh` already used), `klt lvs` reports:

| | layout | reference | matched |
| --- | --- | --- | --- |
| pins | 19 | 19 | 19 |
| devices | 869 | 869 | 794 |
| nets | 444 | 446 | 412 |

— `status: mismatch`, `device.unmatched: 75`, `net.merged: 12`,
`net.split: 10`, `topology.flattened: 1` (see the latest
`reports/<record-id>/lvs.json` for the full per-mismatch detail).

**Root cause: `options.combine_devices` has no per-subcircuit scoping, and
this design's five sub-blocks need opposing settings.** Each sub-block's own
already-closed, already-independently-verified LVS record was reached with
its own deliberately-chosen `combine_devices` setting:

| Sub-block | `combine_devices` | Why |
| --- | --- | --- |
| `cdac_array` | `false` | Its own reference emits one uncombined unit `C` card per physically-drawn MiM cap (issue #148) specifically to avoid `Netlist.combine_devices()`'s documented nondeterminism on large parallel-capacitor groups (klayout-tools#1497) — `true` risks silently corrupting an already-verified array. |
| `sampling_frontend` | `false` | No parallel devices to fold (each of its 24 devices is schematically distinct) — a deliberate no-op choice, not a requirement, per that flow's own `run-flow.sh` comment. |
| `comparator` | `true` | Its own layout genuinely draws split/interleaved unit-width legs (e.g. the input pair's four common-centroid `W=2u` legs) that must be re-lumped to match the reference's lumped `W=4u` devices. |
| `sar_sequencer` | `true` | Folded/multi-finger standard cells need re-lumping the same way. |
| `seln_inverters` | `true` | Same as `sar_sequencer`. |

`klt lvs`'s `options.combine_devices` is a single flag applied once to the
*whole* (flattened) compared netlist — there is no way to apply `false` to
the `cdac_array`/`sampling_frontend` region and `true` to the
`comparator`/`sar_sequencer`/`seln_inverters` region of the same compare.
Both global settings were measured directly against this composition:

- `combine_devices: true` (the setting `run-flow.sh` uses, since it is the
  *less-wrong* of the two): 98 mismatches, the table above. The 75
  `device.unmatched` entries concentrate almost entirely in `cdac_array` (38
  devices — reintroducing klayout-tools#1497's own already-tracked
  nondeterminism) and `sampling_frontend` (23 devices, which have nothing of
  their own to fold — `combine_devices()` appears to consider parallel-device
  groups across the *whole* flattened netlist, not scoped to within a
  sub-block's own original hierarchy boundary, so a shared top-level rail
  connecting unrelated sub-blocks is enough to perturb a sub-block that was
  independently verified device-for-device correct in isolation), plus 5 in
  `comparator` and 9 in `seln_inverters`.
- `combine_devices: false`: 2197 mismatches (2168 `device.unmatched`) — as
  expected, since `comparator`/`sar_sequencer`/`seln_inverters` genuinely
  need the folding this setting disables.

Neither setting is correct for this composition, and no third option exists
in `klt lvs`'s current request schema. This does not indicate a routing
defect: the pin declaration above and the unfiltered, net-by-net
connectivity check both independently confirm the composition's own new
interconnect is correct: what remains unverified by a `klt lvs` **match**
specifically is each sub-block's *own* internal device-level correctness at
the composed scale — already independently verified at each sub-block's own
scope (#99–#102's own closed, clean LVS records), which this blocker
prevents from being *re-confirmed* in the composed context, not from being
verified at all for the first time.

Filed generically (no design-specific detail) at
[klayout-tools#1552](https://github.com/2AMLogic/klayout-tools/issues/1552)
per `CLAUDE.md`'s friction protocol, proposing (in increasing order of
effort): per-subcircuit `combine_devices` scoping in the `klt lvs` request;
hierarchy-preserving extraction/comparison (the "real fix" klayout-tools#1085
named but did not implement, choosing `options.flatten_reference` instead);
or a documented `--abstract-cells` + matching hand-authored reference recipe
that would let this design's own five already-verified sub-blocks be
compared as opaque, pinned black boxes at the top level — reducing the
top-level compare to pure interconnect/topology, where `combine_devices` has
nothing left to disagree about.

### Update: re-run against the officially pinned `klayout-tools==0.5.0`

`klayout-tools` v0.5.0 (published 2026-09-15) is the first PyPI release
carrying `#1556`'s new `options.combine_devices_per_circuit` — i.e. the
"per-subcircuit `combine_devices` scoping" fix this section's original
klayout-tools#1552 report proposed as its first, lowest-effort suggested
fix. `layout/requirements.txt` bumped to it and `run-flow.sh`'s
`SAR_ADC_TOP_KLT` override was retired, so this flow now runs entirely on
the officially pinned `klt` — but re-running the full flow against it did
**not** reach a clean match, for two separate reasons, both filed
generically upstream:

1. **`options.combine_devices_per_circuit` does not actually help this
   composition.** It is only useful when both sides of the compare already
   have separate per-macro subcircuit boundaries to scope patterns against.
   The reference side does (`generate-lvs-reference.py` emits one `.subckt`
   per sub-block); the layout side never does, because `klt extract`'s
   output for a `klt gen-compose`d GDS is always exactly one flat circuit —
   hierarchical extraction still doesn't exist (klayout-tools#1085 remains
   open, unchanged since the original #1552 report named it as a blocker).
   Tried directly with a real per-macro mapping (`false` for `cdac_array`/
   `sampling_frontend`, `true` for `comparator`/`sar_sequencer`/
   `seln_inverters`, on the reference side; the layout side necessarily
   collapsed to one blanket setting since only one circuit exists there):
   **1154 mismatches** (reference device count nearly doubled, to 1873) —
   substantially worse than the existing whole-request `combine_devices:
   true` compromise below, not better. Filed generically as
   [klayout-tools#1878](https://github.com/2AMLogic/klayout-tools/issues/1878).
2. **A separate, newly-introduced regression in the same release.**
   klayout-tools#1558/#1564 ("write bare `C` cards for unbound
   capacitors") — an unrelated, independently-motivated fix to stop `klt
   extract` writing a `C` card ngspice cannot actually simulate — has the
   side effect of dropping the capacitor device class's own name from the
   written SPICE text entirely. `NetlistSpiceReader` reading that bare card
   back in (exactly what this flow's pre-extracted `layout.netlist` LVS
   shape does) can no longer recover that class name, so it registers under
   KLayout's own anonymous capacitor class instead of the reference
   netlist's own explicitly-named one — breaking device-class
   correspondence for capacitors specifically. Confirmed directly: the same
   composed GDS, extracted once with a pre-#1558 `klt` build and once with
   0.5.0, produces byte-identical `C` cards except for that one trailing
   token (`... 8.647288e-15 sky130_fd_pr__model__cap_mim` vs. `...
   8.647288e-15`). Filed generically as
   [klayout-tools#1876](https://github.com/2AMLogic/klayout-tools/issues/1876).

Re-running with the existing whole-request `options.combine_devices: true`
(unchanged from before the bump — the `combine_devices_per_circuit` trial
above was strictly worse, so `run-flow.sh` keeps the old setting) against
0.5.0:

| | layout | reference | matched |
| --- | --- | --- | --- |
| pins | 19 | 19 | 19 |
| devices | 869 | 869 | 794 |
| nets | 444 | 446 | 393 |

— `status: mismatch`, `device.unmatched: 99` (up from 75), `net.merged: 12`,
`net.split: 10`, `topology: 2` (new — "device class could not be mapped to a
counterpart", the #1876 capacitor regression above), `topology.flattened: 1`
— 124 total mismatches, up from 98 pre-bump. The extra 24 `device.unmatched`
entries and the 2 new `topology` entries are exactly the #1876 capacitor
regression; the original 75/12/10/1 breakdown (the #1878-tracked
`combine_devices` scoping gap) is otherwise unchanged. See the latest
`reports/<record-id>/lvs.json` for the full per-mismatch detail.

None of this indicates a routing defect: the pin declaration and the
unfiltered, net-by-net connectivity check both still independently confirm
the composition's own new interconnect is correct — what remains unverified
by a `klt lvs` **match** is still each sub-block's *own* internal
device-level correctness at the composed scale (already independently
verified at each sub-block's own scope, #99–#102's own closed, clean LVS
records), now blocked on two upstream tool gaps instead of one.

### Update: klayout-tools#1876 worked around locally; one blocker left

Gap 2 above (the capacitor device-class token) turned out to be **locally
recoverable without touching `klt`**, so this flow no longer carries it.
`klt extract` still *states* every extracted instance's device class — in
that instance's own provenance comment, written immediately above the card
it describes:

```
* device instance $866 r0 *1 0,0.35 sky130_fd_pr__model__cap_mim
C$866 \$423 TOP_P|VINP 8.647288e-15
```

`bin/restore-cap-device-class.py` (added this increment, run by `run-flow.sh`
between step 7's `klt extract` and its `klt lvs`) copies that class name —
the extractor's own statement of the class, not an assumption made here —
back onto the `C` card, reproducing byte-for-byte the shape `klt extract`
itself wrote before #1558. Three properties make this a workaround rather
than a fudge:

- **It only ever appends a class token to a `C` card** whose last field is a
  bare numeric value, taken from the `* device instance` comment for *that
  same instance name*; a mismatch or a missing comment is a hard error
  (exit 1), never a guess. Every other line is copied verbatim.
- **It writes a separate artifact.** The record keeps `klt extract`'s own
  unmodified `sar_adc_top.extract.spice` *and* the annotated
  `sar_adc_top.extract.lvs.spice` the LVS request consumes, so the whole
  transformation is a one-token-per-`C`-card diff a reviewer can audit.
- **It retires itself.** A card that already carries its class is left
  alone, so the step becomes a no-op the moment klayout-tools#1876 is fixed
  upstream — `capclass.json`'s `"restored": 0` / `"noop": true` is the
  signal that the flow can drop it, with no behavioural change in between.

With it in place, against the same officially pinned 0.5.0 build
(`reports/20260915-222624-10afb15/`):

| | layout | reference | matched |
| --- | --- | --- | --- |
| pins | 19 | 19 | 19 |
| devices | 869 | 869 | 794 |
| nets | 444 | 446 | **412** |

— `status: mismatch`, `device.unmatched: 75`, `net.merged: 12`,
`net.split: 10`, `topology.flattened: 1`; **98 total mismatches**, and the
`topology: 2` ("device class could not be mapped to a counterpart") category
is gone entirely. That is *exactly* the pre-0.5.0 breakdown — i.e. the #1876
regression is fully accounted for and neutralised locally, and what remains
is the single, long-standing `combine_devices`-scoping gap
(klayout-tools#1878). The remaining 75 unmatched devices are **all
reference-side**, and break down exactly along that gap's own
opposing-settings fault line: 43 NFETs (9 in `seln_inverters`, 18
`cdac_array` bit-cell devices, 11 in `sampling_frontend`, 5 in
`comparator`), 24 MiM capacitors (20 of `cdac_array`'s weighted/terminating
caps plus `sampling_frontend`'s 4 boot/sample caps), and 8
`sampling_frontend` PFETs — i.e. the blocks that need folding and the blocks
that must *not* be folded, both mis-served by one whole-request flag.

Two further shapes were measured this increment and are recorded here so a
later pass does not re-try them blind:

- **Class-scoped `combine_devices: ["NFET","PFET"]`** (klayout-tools#1370's
  device-class restriction — the closest thing `klt lvs` has to scoping that
  is *not* per-circuit): **126 mismatches**, with device matching identical
  (794/869). Device class cannot separate the FET legs that need folding
  from the ones that must not be folded, because both families are FETs.
- **`klt lvs`'s inline-extraction shape** (`layout.file` + `deck` +
  `pin_source_cells`, which would sidestep #1876's SPICE round-trip
  altogether, and which `layout/sampling-frontend/` uses at its own scope):
  **2199 mismatches**, `status: inconclusive`, with a
  `device.combine_incomplete` warning. It compares the *raw* extracted
  netlist (1893 devices) on which KLayout's own `Netlist.combine_devices()`
  exhausts its retry budget, where the pre-extracted shape starts from `klt
  extract`'s own already-folded 869 devices. So the inline shape is not a
  substitute here even though it avoids #1876 — which is why the workaround
  above, not a shape change, is the right fix for that gap in this flow.

### A fourth shape measured: `--abstract-cells` black-boxing (klayout-tools#620) — promising, but blocked on a newly-found gap

klayout-tools#1878's own "what would actually close it" section names a
third option beyond the two already tried above: `--abstract-cells` +
a matching hand-authored reference, letting this design's own
already-independently-verified sub-blocks be compared as opaque, pinned
black boxes at the top level instead of flattened devices — "reducing the
top-level compare to pure interconnect/topology, where `combine_devices`
has nothing left to disagree about." `--abstract-cells` (issue #620) was
never tried against this composition before this pass; it already ships in
the pinned `klayout-tools==0.5.0` (no version bump needed).

**Mechanism.** `klt extract --abstract-cells '<qualified-cell-name>'`
(repeatable) treats every instance of a matched cell **type** as an opaque
subcircuit boundary instead of flattening its devices into the top circuit,
resolving that boundary's pins from the cell's own drawn labels. The
composed GDS's direct children carry `klt gen-compose`'s own deterministic
`<block-id>__<cell-name>` qualified names (`klt cells sar_adc_top.gds`):
`cdac_array__cdac_array`, `sar_sequencer__sar_sequencer`,
`seln_inverters__seln_inverters` each draw their own pin labels directly on
their own top cell and abstract cleanly; `comparator__gen_compose_0` and
`sampling_frontend__gen_compose_0` do not (their pin labels live one level
deeper, in their own internal `ROUTE` sub-cell — `--abstract-cells`
resolves pins only from labels drawn *directly* in the matched cell's own
definition) and were left flat.

To compare a partially-abstracted layout netlist against a reference with
the matching shape, the reference's own already-verified, already-committed
sub-block subckts for exactly those three macros are **renamed** to the same
`<block-id>__<cell-name>` qualifiers (so `NetlistComparer`'s own circuit
correspondence pairs them by name — verified necessary: leaving the
reference-side names as-is, or feeding the full (non-abstracted) sub-block
device lists under the renamed headers, both fail outright, see below) and
**hollowed** (header + `.ENDS` only, no devices — matching the layout side's
own now-opaque boundary; comparing a real device-level reference subckt
against a genuinely-empty black box is not "pure interconnect", it is
comparing zero devices against hundreds, and fails completely). Comparator
and sampling_frontend's own reference subckts are inlined (their device
cards copied in with each port substituted for its top-level net,
`M`/`C` device designators kept as the first character so
`NetlistSpiceReader` still classifies them correctly, everything else
prefixed with the instance name for uniqueness) directly into the top
`.SUBCKT sar_adc_top`, matching the layout side's own flat top-circuit
device set. `options.flatten_reference: false` (not the flow's existing
`true`) is required so the reference keeps these three circuit boundaries
instead of erasing them before comparing.

**Result.** Against the same composed GDS as the 98-mismatch baseline
above: **6 mismatches** (`device.unmatched: 3`, `net.merged: 2`,
`topology: 1`; nets 59/61/128 pins 19/19/92, devices 35/35/32 — the small
absolute counts are `gen_compose_0`'s own flat portion only, once
cdac_array/sar_sequencer/seln_inverters are opaque). A **75 -> 3** and
**98 -> 6** mismatch reduction, by removing exactly the sub-blocks whose own
`combine_devices` need conflicted with the rest (cdac_array,
sar_sequencer, seln_inverters no longer contribute any devices to fold at
all).

**Why this is not adopted for signoff, and is not the flow's default.** All
6 remaining mismatches trace to one thing: three of `cdac_array__cdac_array`'s
own separately-declared pins (`TOP_N`, `TOP_P`, `VREFN`) get resolved onto
**one** synthesized net, which additionally absorbs the (already
legitimately dual-labelled, see the connectivity table's `TOP_N`/`TOP_P`
rows) `VINN`/`VINP` net — `TOP_N|TOP_P|VINN|VINP|VREFN`, one composite label
where five should exist. `klt extract`'s own `warnings[]` output names this
directly: *"1 --abstract-cells instance(s) resolved two or more of their
separately declared pins onto the same net: ... pins TOP_N, TOP_P, VREFN ->
net '...' ... this ... is also the signature of a pin-to-net binding
fault"*.

**Update (2026-09-19): the original diagnosis above was wrong.** The
original recording of this section attributed the collapse to
`cdac_array__cdac_array`'s 4th schematic port (a body/bulk tie with no
drawn label, resolved only through the sky130 deck's global-net fallback)
being silently dropped (23 resolved pins, not the reference's 24), and
filed that as klayout-tools#1911. #1911 got an upstream fix (merged as
commit `ad3f836`/PR #1934, not yet released as of this update) that indeed
closes a real bug — but a **different** one: #1934's own PR description
traces it to a black-boxed cell's *erased nwell/tap geometry* silently
reclassifying a substrate tie *elsewhere in the design*, through the deck's
whole-layout body-identity classification pass. That is a cross-instance,
classification-side effect, and it is not what this section's 6 mismatches
trace to.

An ablation matrix (`layout/sar-adc-top/bin/probe-abstract-cells.py`,
committed alongside this update; results in each record's own
`abstract-probe.<klt-version>.summary.json`) re-measured the collapse
directly against the fix's own targets and found neither one changes it:

- Supplying `cdac_array`'s missing 4th port with a drawn tie (so the macro
  now resolves all 24 of its schematic pins, not 23 — the exact condition
  #1911's original diagnosis says should matter) leaves the composite net
  **byte-for-byte unchanged**.
- Stripping `cdac_array`'s own nwell/tap geometry (the exact geometry
  #1934's classification-pass fix reasons about) also leaves the composite
  net **unchanged**.
- Turning `--pin-source-cells` off changes nothing either (this mechanism
  was never about declared-pin sourcing).
- Abstracting a *different* macro (`sar_sequencer`/`seln_inverters`
  together, `cdac_array` left flat) reproduces only the design's own
  legitimate `TOP_N|VINN`/`TOP_P|VINP` dual-label pair — the same pair a
  fully flat (no `--abstract-cells` at all) extraction already reports —
  and nothing more.

So the currently-cited blocker rationale ("wait for a klayout-tools release
containing #1934") does not actually apply here: once released, #1934 will
not change this section's 6 mismatches, because the mechanism it fixes is
not the one producing them. Filed the corrected diagnosis generically as
[klayout-tools#2142](https://github.com/2AMLogic/klayout-tools/issues/2142)
(closes-relationship to #1911/#1934 noted there as "related, different
mechanism" rather than superseding — #1911/#1934 is a real, separate fix
that this repo has no reason to distrust on its own terms).

Until #2142 is understood/fixed, this repo has no way to independently
confirm the 6 remaining mismatches are the cosmetic label artefact they
appear to be, rather than a real connectivity defect the corrupted names
happen to mask — so, per CLAUDE.md's "Verification is the product" (no
claim without a testbench this repo can actually audit), this shape is
**recorded here as a measurement, not adopted**: `run-flow.sh` keeps using
the already-audited 98-mismatch `combine_devices: true` /
`flatten_reference: true` whole-request compare above as its signoff
attempt. Once #2142 is resolved upstream, re-run
`bin/probe-abstract-cells.py` first — if the composite net resolves to
exactly the 3 pins it should split back into, this is still the shortest
path to a full LVS match this issue has found so far.

**Update (2026-09-23): re-measured on `klayout-tools==0.6.0`. #2147 does
not resolve the collapse, and the actual mechanism is now located.**
klayout-tools v0.6.0 (PyPI, 2026-09-22) is the first release containing
#2147 (commit `3cc085c`; `gh api .../compare/v0.6.0...3cc085c` reports
ahead_by 0). #2147 fixed two real probe-layer defects: a pin's probe layer
was tracked per pin rather than per access point, and nwell/tap could act
as a fallback answer. Its reproduced signature, though, is a macro's pins
collapsing onto a **parent power strap**. The probe re-run on
record `20260923-131726-fa1e0af`
(`abstract-probe.klt-0.6.0.summary.json`) reproduces this repo's collapse
**byte for byte** on 0.6.0, in all four `cdac_array`-abstracted variants.
Only the warning text changed.

The collapse is a merge of the parent's own nets, not a pin-binding
fault. In the extracted top circuit, `TOP_N|VINN`, `TOP_P|VINP` and `VREFN`,
three separate nets in the flat extraction, become one net, and the black
box's pins then correctly bind to it. The flat netlist shows how that can
happen: exactly one unit cap connects `VREFN` to `TOP_N|VINN`, and exactly
one connects `VREFN` to `TOP_P|VINP`. Shorting every cap's top plate to its
bottom plate merges precisely those three nets and leaves `VREFP` alone,
which is exactly the observed shape. Reading klt 0.6.0's
`extract_abstract.py`/`extract.py` explains it:
`_abstract_cell_mask_layers()` erases every connectivity layer that is not
contact/metal/via/label, which includes the MiM top plate (`capm`). But the
deck's top-plate-via exclusion (#364/#1388) is scoped to
`bottom_plate.interacting(top_plate)`, so it becomes empty once `capm` is
gone. Every one of the 1024 via3 top-plate vias then reads as an ordinary
met3→met4 via. The probe's new `cdac-no-capm-via` ablation confirms it: on
a variant GDS with **only** those 1024 interior via3-on-capm shapes deleted,
the composite net splits back into exactly the legitimate `TOP_N|VINN` /
`TOP_P|VINP` pair, net count goes 425 → 427, and the tied-pin warning
disappears. Filed generically as
[klayout-tools#2396](https://github.com/2AMLogic/klayout-tools/issues/2396).

**What would remain once #2396 is fixed (diagnostic, not signoff).** Re-running
the 2026-09-15 hollow-reference compare
(`reports/20260915-234004-76f48b9/abstract-cells-experiment.reference-hollow.spice`,
`options.flatten_reference: false`) against a three-cell abstraction of
that via3-stripped variant, after `restore-cap-device-class.py`, gives **2
mismatches** (down from 6). Devices are 35/35/35 and pins 19/19. Both
remaining entries are the `cdac_array` instance: a `topology` entry plus
one unmatched layout net. The instance line shows why. The black box's
`VDD` pin binds to a single-terminal net `$283` that appears nowhere else,
and not to the routed `VDD`. `cdac_array.VDD` is a well-labelled pin
whose only drawn route to the parent is #165's tap→licon→li1→mcon→met1
landing (one `tap` shape in the well). Abstraction erases `tap`
(klayout-tools#2082 restores the well itself, not the tap), so that route
is severed. Filed generically as
[klayout-tools#2398](https://github.com/2AMLogic/klayout-tools/issues/2398).
Stacking the probe's `cdac-tied` substrate-tie variant on top as well gives
3 mismatches (the tie's own `vsubs` pin becomes a second isolated net for
the same reason), so that is not a route to a match either. `vsubs`
still needs `--abstract-cell-lef` or a reference-side decision. None of these
modified-GDS numbers is signoff evidence: this repo does not edit
already-verified sub-block geometry to pass a compare.
The unmodified-GDS `--abstract-cells` shape stays **not adopted**, for the
same reason as before. `run-flow.sh`'s signoff attempt stays the whole-request
compare.

## Remaining work (tracked against #103)

- [x] Place all five blocks via `klt gen-compose` `placement.strategy:
      "explicit"`, each sourced as a `blocks[].cell` entry (#1189).
- [x] **Place DR-017's on-die decoupling (issue #440).** `Cdecap_a`/`Cdecap_d`
      are drawn as four `klt gen cap_array` unit cells (two per domain,
      `MF = 2`) and tied across their own domains' supply/return conductors;
      DRC re-run clean (0 / 52 rules), `klt erc` re-run clean (0 findings, all
      four supplies at one island on the new geometry), LVS re-run against a
      regenerated **871**-device reference in the same four mismatch
      categories. DR-017's Decision §3 area budget is **confirmed placeable at
      `MF = 2`** against a direct back-end occupancy measurement, and cost no
      die area — so no superseding record was needed. See "On-die decoupling
      (DR-017)" above, including the ESR the ties cost (DR-017's own open
      residual, now quantified: 13.8 Ω / 13.4 Ω per domain, ~80 % of it
      single-cut vias).
- [x] Hand-route (`klt draw`) every net in the interconnect table above.
      `layout/sar-adc-top/bin/build_layout.py` documents the concrete
      floorplan/layer-alternation scheme that made this tractable (met1
      horizontals / met2 verticals in the dense digital channel, met3
      horizontals / met4 verticals in the analog-region crossings — see that
      module's own docstring and its `analog_leg()`/`DROP_X` comments for
      the specific same-layer collisions found and fixed along the way).
- [x] Produce and commit the composed top-level GDS under this directory,
      following the `layout/trivial-cell/` record convention
      (`reports/<timestamp>-<sha>/` with `draw.json`/`compose.json`,
      `drc.json`, `extract.json`/`extract.unfiltered.json`, `lvs.json`,
      `record.md`).
- [x] `klt drc` clean at the top level (0 violations).
- [x] Build the top-level LVS reference (`layout/sar-adc-top/bin/
      generate-lvs-reference.py`): a hierarchical SPICE netlist calling each
      sub-block's own already-generated flat reference subckt plus the
      top-level interconnect, run through `klt lvs` with
      `options.flatten_reference: true` (issue #1085).
- [x] `klt extract --pin-source-cells` reaches 19/19/19 promoted/reference/
      matched top-level pins (klayout-tools#1513/#1515, resolved).
- [x] `layout/requirements.txt` bumped to the officially released
      `klayout-tools==0.5.0`; the `SAR_ADC_TOP_KLT` override is retired —
      this flow runs entirely on the pinned `klt` now.
- [ ] **Blocked on klayout-tools#1878 and klayout-tools#1876** (see "Update:
      re-run against the officially pinned `klayout-tools==0.5.0`" above) for
      an actual `klt lvs` **match** verdict — the connectivity itself is
      verified correct by the unfiltered-extraction, net-by-net check in each
      record's own `record.md`, and the pin declaration is exact; what
      remains is (1) a `combine_devices` scoping gap the 0.5.0-era
      `combine_devices_per_circuit` feature does not actually close for this
      composition's flat layout-side extraction (klayout-tools#1878,
      superseding the now-closed klayout-tools#1552), and (2) a newly
      surfaced capacitor device-class round-trip regression
      (klayout-tools#1876) — neither is fixable by this repo alone.
- [x] `layout/requirements.txt` bumped to `klayout-tools==0.6.0` (2026-09-23,
      the first release carrying #2147/`3cc085c`). Re-measured: whole-request
      compare unchanged (98), `--abstract-cells` collapse unchanged, mechanism
      located (see "Update (2026-09-23)" above).
- [ ] **Blocked on klayout-tools#2396** (MiM top-plate short inside an
      `--abstract-cells` black box) **and klayout-tools#2398** (well-tap
      erasure cutting off `cdac_array.VDD`) for the `--abstract-cells` path.
      Once both ship in a release, re-run `bin/probe-abstract-cells.py`
      and the hollow-reference compare on the unmodified GDS. If that
      reaches `match`, promote it into `run-flow.sh` as the signoff shape.
      Separately, klayout-tools#2397 decides when
      `bin/restore-cap-device-class.py` can retire. `capclass.json`'s
      `noop: true` can no longer be the trigger, because #1876 was fixed on
      the reader side.
- [ ] Once an actual `match` verdict is reached, revisit whether `klt pex` (now
      implemented, unlike the tooling gap #103's own body anticipated) is
      usable for T1 item 7's post-layout verification — not attempted this
      increment, since `klt pex` presumes a device/net correspondence to
      attach parasitics onto, which does not yet exist here.

### T1 items 3/4/7: what this issue makes checkable at the top level

Per #103's own acceptance criteria, this is the accounting of which items
this issue's work makes checkable (run, with a real verdict) versus which
remain tool-blocked, as of this record:

- **Item 3 (DRC clean)**: **checkable and clean.** `klt drc` reports 0
  violations on the fully composed 5-block layout (unchanged since PR #174).
- **Item 4 (LVS clean)**: **checkable, not yet clean.** The pin-declaration
  blocker (klayout-tools#1513) was resolved (via the now-retired
  `SAR_ADC_TOP_KLT` override, and since this issue's own `klayout-tools==0.5.0`
  pin bump, via the officially pinned `klt`) — `klt lvs` runs with an exact
  19/19/19 pin correspondence instead of refusing to seed a comparison at
  all. It still reports `mismatch`, now blocked on exactly one gap: the
  original `combine_devices` scoping gap (klayout-tools#1552) is closed
  upstream but its fix (`combine_devices_per_circuit`) does not actually
  apply to this composition's flat layout-side extraction
  (klayout-tools#1878). The capacitor device-class round-trip regression
  0.5.0 additionally introduced (klayout-tools#1876) no longer contributes:
  `bin/restore-cap-device-class.py` neutralises it locally and
  self-retires once it is fixed upstream (98 mismatches / 412 matched nets,
  back to the pre-regression breakdown). **Re-checked 2026-09-23 on
  `klayout-tools==0.6.0`: still checkable, still not clean.** The
  whole-request compare is unchanged at 98. The `--abstract-cells` path,
  the only shape that has come close, is now blocked on klayout-tools#2396
  and #2398, not #2142. #2142 is fixed in 0.6.0 but was not this collapse's
  cause.
- **Item 7 (post-layout verification via `klt pex`)**: **not attempted,
  blocked on item 4.** `klt pex` is implemented upstream (unlike the tooling
  gap #103's own body anticipated when filed), but extracting parasitics
  presumes the device/net correspondence a clean LVS match would establish;
  running it against a netlist `klt lvs` itself cannot yet confirm
  corresponds to the schematic would not produce meaningful top-level
  evidence. Left for the follow-up that resolves klayout-tools#1878.

## Provenance

Clean room: this document only records geometry already drawn by this
repo's own sub-block flows (#99–#102) and this issue's own new
`layout/seln-inverters/` macro — no third-party layout, floorplan, or netlist
was consulted.

### `klt` build required: resolved — pinned `klayout-tools` (0.5.0, now 0.6.0), no override needed

`reports/20260907-110058-a546200/` through `reports/20260908-072857-80df05e/`
were generated with a `klt` build from klayout-tools commit
[`2313dd0301b2dd90e4cad9a2cf1c62ff36d3a9b5`](https://github.com/2AMLogic/klayout-tools/commit/2313dd0301b2dd90e4cad9a2cf1c62ff36d3a9b5)
(#1515, "feat(extract): add `--pin-source-cells` for gen-compose'd
multi-macro pin declaration", merged 2026-09-06), via the `SAR_ADC_TOP_KLT`
env-var override — `layout/requirements.txt` pinned `klayout-tools==0.4.0`
at the time, and PyPI had not yet published a release newer than that.

`klayout-tools` v0.5.0 published to PyPI 2026-09-15T02:19:49Z, confirmed
(via `gh api .../compare`) to contain both `2313dd0301b2dd90e4cad9a2cf1c62ff36d3a9b5`
(#1515) and commit `5598e540` (#1556, `options.combine_devices_per_circuit`)
as ancestors. `layout/requirements.txt` now pins `klayout-tools==0.5.0`, and
`layout/sar-adc-top/bin/run-flow.sh`'s `SAR_ADC_TOP_KLT` override is
retired — `reports/20260915-120341-1e90b14/` onward (current:
`reports/20260915-222624-10afb15/`) is generated entirely
from the officially pinned `layout/.venv/bin/klt`, reproducible by any third
party via the ordinary `layout/bin/setup-venv.sh` + `layout/sar-adc-top/bin/
run-flow.sh` invocation, with no extra build step. See "Update: re-run
against the officially pinned `klayout-tools==0.5.0`" above for what that
re-run found: DRC and the unfiltered connectivity check are unaffected, but
the `klt lvs` verdict is not — bumping past 0.4.0 also picked up
klayout-tools#1558's capacitor SPICE-writer change, which regresses this
flow's specific pre-extracted-netlist LVS shape (klayout-tools#1876), and
`combine_devices_per_circuit` itself does not close the original
`combine_devices` scoping gap for this composition's flat layout-side
extraction (klayout-tools#1878). Both are real, currently-open upstream
gaps, not resolved by this pin bump alone — but only #1878 still costs this
flow anything: #1876 is neutralised locally by
`bin/restore-cap-device-class.py` (see "Update: klayout-tools#1876 worked
around locally" above), which needs no `klt` build change and retires itself
when the upstream fix lands.

`klayout-tools` v0.6.0 published to PyPI 2026-09-22T18:52:45Z and contains
`3cc085c` (#2147) and #1921 (#1876's reader-side fix).
`layout/requirements.txt` has pinned `klayout-tools==0.6.0` since
2026-09-23; `reports/20260923-131726-fa1e0af/` onward is generated from that
pin. That record, and the trivial-cell regression record
`layout/trivial-cell/reports/20260923-131710-fa1e0af/`, were produced inside
a Linux container (`python:3.14-bookworm`, the same pinned `klt`/`klayout`
wheels, the same pinned sky130A PDK mounted read-only, and the worktree
bind-mounted so `run-flow.sh` ran unmodified). The macOS host this
session ran on was failing library validation for every native Python
extension (`library load mig callout failed`), a host fault rather than a
flow change. The DRC/extract/LVS verdicts match the macOS-generated 0.5.0
records field for field wherever the tool behavior did not change.

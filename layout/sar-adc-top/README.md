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
**6** mismatches, but rests on a not-yet-understood tool behaviour
(klayout-tools#1911) and is recorded as a measurement, not adopted for
signoff — see "LVS device/topology blocker" below for the full, current
trace of both.**

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
is geometry `klt drc` structurally could not see — see "Minimum-area rules:
measured separately, because the deck has none" below. The composition's own
top-level `bbox_um` moves for the first time since PR #174, by 0.05 um in `x0`
only (-20.200 -> -20.250), because the external `VDD` pin's label-only met4
landing pad widened from 0.36 to 0.50 um; that pad is the composition's
leftmost shape. This re-run also picked up `layout/cdac-array/`'s,
`layout/sar-sequencer/`'s and `layout/seln-inverters/`'s own PR #327 records
and `layout/sampling-frontend/`'s new `20260918-191227-935ce76`, so all five
composition inputs are again each flow's current `reports/LATEST`.

### Minimum-area rules: measured separately, because the deck has none

`klt drc --deck sky130` at the pinned `klayout-tools==0.5.0` authors **47
rules across five kinds** (`width`, `space`, `enclosing`, `separation`,
`isolated`) and **no `area`-kind rule at all**. sky130A's own metal
minimum-area rules — `m1.6` 0.083, `m2.6` 0.0676, `m3.6` 0.240, `m4.4a`
0.240, `m5.4` 4.0 um^2, all five in the pinned PDK's own
`libs.tech/klayout/drc/sky130A_mr.drc` — had therefore never looked at this
layout, and a `status: "clean"` verdict said nothing about them. The deck gap
is fixed upstream (klayout-tools#1989, commit `50cc29c3`) but **not
released**; this repo grades against what is released.

Until that release lands, minimum area is measured by
`docs/chipalooza/measure_metal_min_area.py`, which reads the thresholds and
layer numbers out of the pinned PDK's own deck (never transcribed) and applies
KLayout's own `Region#with_area` — the same primitive the deck's rule text
calls — to each flow's current record:

```
layout/bin/setup-venv.sh                                    # once
layout/.venv/bin/python docs/chipalooza/measure_metal_min_area.py
```

**That measurement is a CI gate, not a manual habit** (issue #338). It runs in
`.github/workflows/ci.yml`'s PDK-gated `pdk-smoke` job — nightly, on
`workflow_dispatch`, and on any PR labelled `run-pdk-smoke` — against the
already-committed GDS in each flow's current `reports/LATEST` record, so it
re-runs no layout flow and costs seconds. Two invocations, in this order:

```
layout/.venv/bin/python docs/chipalooza/measure_metal_min_area.py \
    --self-test --baseline docs/chipalooza/metal_min_area_baseline.json
layout/.venv/bin/python docs/chipalooza/measure_metal_min_area.py \
    --baseline docs/chipalooza/metal_min_area_baseline.json
```

`--self-test` is the negative control this repo applies to every other layout
verdict (see verdict 3 in the trivial-cell proof): it measures a
deliberately-illegal fixture — one isolated square sized from the deck's own
`m3.6` threshold, attributed to `cdac-array` — and exits non-zero unless the
gate catches it, so a clean verdict from the second invocation cannot be
vacuous.

`--baseline docs/chipalooza/metal_min_area_baseline.json` is what keeps the
145 tool-emitted shapes below from red-lining CI permanently. Each entry is a
per-(flow, rule) **ceiling** carrying the issue that tracks it — all ten name
#333 and nothing else — so:

- one shape more than recorded, anywhere, **fails**: a new isolated pad from
  this flow's own via risers is caught even though this flow is waived for
  #333's shapes (a waiver is a ceiling, never a blanket exemption);
- a flow with no entry — `cdac-array`, `comparator`, `sampling-frontend`, the
  three whose metal this repo hand-authors end to end — is gated at **zero**;
- fewer shapes than recorded **passes**, with a loud `STALE ALLOWANCE`
  warning, so the day #333 is fixed the gate does not turn red on a closed
  defect — it asks to be tightened.

When #333 closes: delete `docs/chipalooza/metal_min_area_baseline.json` and
drop the `--baseline` argument from that CI step. Nothing else references it.
The baseline's own bookkeeping (what it waives, what it must never waive) is
unit-tested headlessly on every push in
`sim/tests/test_metal_min_area_baseline.py`.

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

What remains below threshold in the composed GDS is **145 shapes on
met1/met2/met3/met5 that `klt`'s own place-and-route emitted** inside
`sar_sequencer`/`seln_inverters` — generated via cells (`VIA_L1M1_PR_MR` met1
0.290x0.230 um, `VIA_M2M3_PR` met3 0.330x0.330 um, `VIA_via5_6_*` met5
1.420x1.600 um) and router-drawn stubs. No `sky130_fd_sc_hd__*` library cell
violates anything. That is not geometry this repo authors: investigated under
issue #333, which found no fix reachable from this repo and closed with an
explicit dated waiver in each producing flow's README
(`layout/sar-sequencer/README.md`'s 112 shapes and
`layout/seln-inverters/README.md`'s 33 — 112 + 33 = the 145 above exactly, the
composition itself adding none). Filed generically upstream as
klayout-tools#2072 (closed; its fix landed for `klt gen-compose` only, the
place-and-route half explicitly not reproduced) and re-filed with a reproducing
input as klayout-tools#2139.

The measurement itself is committed alongside the record it grades:
`reports/20260918-191315-935ce76/minimum-area.json` is that script's own
`--json` output against this record's `sar_adc_top.gds` — 0 shapes below
`m3.6`/`m4.4a`, and every one of the 145 residual met1/met2/met3/met5 shapes
listed with its own bounding box, so #333 starts from measured geometry rather
than a re-derivation.

`layout/sar-adc-top/bin/build_layout.py` places all five sub-blocks (`klt
gen-compose`, explicit placement, each named as a `blocks[].cell` entry per
#1189) and hand-routes every net `design/sar_adc_top.sch` calls for (`klt
draw`), following the floorplan/routing plan this document works out below.
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

bbox: `(0.0, -2.4)` to `(195.56, 58.97)`. All pins on layer `69/5` (met2.pin)
except `GND`, which has **no drawn pin** — see "GND/substrate" below.

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

Used by this assembly: `VDD`, `SAMPLE` (<- sequencer's `PH_SAMPLE`, net
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

No `GND`/`VSS` pin — see "GND/substrate" below (this block's port list is
`VREFP VREFN VDD vsubs SELn0 SELp0 ... TOP_N TOP_P`, i.e. its 4th port is a
literal `vsubs` connection, not a drawn label). `TOP_P`/`TOP_N` sit on
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
below.

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

Twenty top-level external chip pins in total: `VINP, VINN, VDD, VREFP, VREFN,
VCM, CLK, RST_B, DOUT9..DOUT0, BUSY` (matching `design/sar_adc_top.sym`'s own
pin list exactly).

## GND / VPWR / VGND: not a routing job (mostly)

Worked out from `klt extract --deck sky130`'s own documented substrate
synthesis (`layout/sampling-frontend-wells/README.md`, `layout/sampling-frontend/reference.spice`'s
header) plus `design/sar_adc_top.spice`'s own `.GLOBAL GND`/`.GLOBAL VDD`
declarations and its item-2 "known integration gap" note:

- **Analog `GND` is free.** `klt extract`'s sky130 deck synthesizes every
  NMOS/PMOS-body's p-substrate connection as one globally-shared `vsubs` net
  *regardless of drawn geometry* — so `sampling_frontend`'s GND (no drawn
  pin at all) and `cdac_array`'s VSS (also no drawn pin) already report as
  the same net the deck would assign `comparator`'s real, drawn `GND` pin to
  as well, with **no wire required between the three blocks for this
  assembly to reach a matching verdict** on that specific net. This still
  needs confirming empirically against the *composed* (not per-block) flat
  extraction before relying on it — the per-block READMEs establish the
  mechanism, not this specific 3-block composition.
- **`VDD` (analog) is a real net and must be routed** between
  `sampling_frontend`, `cdac_array`, and `comparator` (and the external
  `VDD` pin) — it is not part of the substrate auto-merge.
- **Digital `VPWR`/`VGND` are two separate, self-contained domains, and
  `design/sar_adc_top.sch`'s own netlist keeps them that way.** Neither
  `VPWR` nor `VGND` is declared `.GLOBAL` in `design/sar_adc_top.spice`, and
  neither is a formal port of the `sar_sequencer` subckt call at the top
  level — so by ordinary SPICE hierarchy scoping, `sar_sequencer`'s own
  internal `VPWR`/`VGND` (already a closed, self-contained rail per #102) is
  a *different* net from `seln_inverters`' own internal `VPWR`/`VGND`
  (this issue's own closed macro), even though both literally use the
  string `"VPWR"`. **Do not tie them together** when building the top-level
  LVS reference or the physical routing — per the schematic's own
  documented item-2 gap note, both digital rails are meant to stay
  unconnected to anything else at this structural level; a future
  full-ADC testbench (#28/#29/#31) supplies their bias independently, the
  same way `sim/sar-sequencer-behavioral/`'s own testbench already does.
  (This is the existing, accepted VDD/GND-vs-VPWR/VGND divergence the
  schematic's own header already documents, extended to cover two separate
  digital instances rather than just analog-vs-digital.)

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
   rather than violating spacing) but has not been tried here. **Update:**
   per `design/sar_adc_top.spice`'s own hierarchy scoping (re-confirmed
   directly against the generated netlist during this investigation),
   neither `VPWR` nor `VGND` is a formal port of either macro's subckt call
   at the top level — so this issue does not need to reach these straps at
   all; they stay self-contained per-macro rails, exactly as the "GND / VPWR
   / VGND" section below already concluded. Listed here only so a future
   reader does not re-open the question.
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
6 remaining mismatches trace to one thing: `cdac_array__cdac_array`'s own
schematic 4th port (a body/bulk tie resolved, in the *unabstracted* layout,
through the sky130 deck's global-net fallback rather than a drawn label —
the same mechanism the "GND / VPWR / VGND" section above already documents
for other blocks) has **no drawn label anywhere in cdac_array's own
definition**, so `--abstract-cells` silently drops it (23 resolved pins,
not the reference's 24) — and, surprisingly, that drop does not just cost
the black box its own 4th terminal: it also **corrupts the synthesized net
name for several unrelated top-level nets** (`VINN`/`VINP`/`TOP_N`/`TOP_P`/
`VREFN` collapse into one bogus composite label, cascading into the 6
mismatches above), even though those nets never touch `cdac_array`'s own
footprint. Isolated directly: abstracting `sar_sequencer`/`seln_inverters`
alone (neither has a label-less port) leaves every net name clean;
abstracting `cdac_array` alone, on its own, reproduces the corruption every
time, independent of which other flags are combined with it. This is a new
finding, distinct from klayout-tools#1876/#1878/#1085 (a different root
cause — a black-boxed cell's *dropped, label-less* port perturbing
*unrelated* net-name synthesis, not a combine_devices scoping question or a
missing hierarchical-extraction mode), so it is not covered by an existing
report — filed generically as
[klayout-tools#1911](https://github.com/2AMLogic/klayout-tools/issues/1911).

Until #1911 is understood/fixed, this repo has no way to independently
confirm the 6 remaining mismatches are the cosmetic label artefact they
appear to be, rather than a real connectivity defect the corrupted names
happen to mask — so, per CLAUDE.md's "Verification is the product" (no
claim without a testbench this repo can actually audit), this shape is
**recorded here as a measurement, not adopted**: `run-flow.sh` keeps using
the already-audited 98-mismatch `combine_devices: true` /
`flatten_reference: true` whole-request compare above as its signoff
attempt. Once #1911 is resolved upstream, re-measure this shape first —
if the 6 mismatches resolve to genuinely benign net-naming artefacts (or
disappear once the underlying pin-drop is fixed), this is the shortest
path to a full LVS match this issue has found so far.

## Remaining work (tracked against #103)

- [x] Place all five blocks via `klt gen-compose` `placement.strategy:
      "explicit"`, each sourced as a `blocks[].cell` entry (#1189).
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
- [ ] Once klayout-tools#1878/#1876 (or an equivalent workaround) resolve:
      confirm an actual `match` verdict, and revisit whether `klt pex` (now
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
  back to the pre-regression breakdown).
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

### `klt` build required: resolved — `klayout-tools==0.5.0`, no override needed

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

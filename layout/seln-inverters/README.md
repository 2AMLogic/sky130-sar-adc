# layout/seln-inverters/ — SUPERSEDED (issue #387): the glue this block draws is not in the schematic any more

> **SUPERSEDED 2026-09-25 by `layout/top-glue/` (issue #387). Do not cite this
> block's DRC/LVS verdicts as evidence about the top level.**
>
> This directory lays out nine `sky130_fd_sc_hd__inv_1` cells implementing
> `SELn<i> = NOT(DOUT<i>)` — issue #56's unconditional complementary CDAC
> bottom-plate drive. `spec/decision-records/DR-008-cdac-top-level-switching-polarity.md`
> **superseded that wiring on 2026-09-11** (issue #263, PR #266): the drive is
> now decision-directed, `SELp<i> = DOUT9 AND DOUT<i>` and
> `SELn<i> = DOUT9N AND DOUT<i>`, built from eighteen `and2_1` gates plus an
> `xinv_dout9n` complement. **`design/sar_adc_top.spice` contains no
> `xinv_seln<i>` instance at all**, so the nine cells drawn here correspond to
> nothing in the current schematic.
>
> The replacement is `layout/top-glue/`, whose netlist is gated against
> `design/sar_adc_top.spice` on every run and in CI
> (`layout/top-glue/bin/check-schematic-parity.py`) precisely so this cannot
> happen again — a generated-reference LVS flow compares a layout against a
> reference derived from the same netlist, so it agrees with itself whatever
> the schematic says, which is why this block stayed clean and wrong for two
> weeks.
>
> **Why it is still in the tree:** `layout/sar-adc-top/`'s composition still
> reads this block's GDS (`bin/build_layout.py` places `seln_inverters`;
> `bin/generate-lvs-reference.py`'s `TOP_SUBCKT` still wires each `SELp<i>`
> straight to `DOUT<i>`). Deleting it would break that flow without fixing it.
> It is retired — records kept, as append-only history — by the top-level
> recomposition tracked as issue #401. Everything below this banner is
> preserved as the record of what was built and verified, and remains accurate
> *about those nine inverters*; it is no longer accurate about the SAR ADC's
> top-level glue.

Physical layout for the nine `sky130_fd_sc_hd__inv_1` instances
`design/sar_adc_top.sch` (issue #56) added directly at the top-level
integration, not inside any sub-block: `DOUT<i>` (the SAR sequencer's own
per-bit register output, #102) drove `SELn<i>` = `NOT(DOUT<i>)`, the CDAC
array's (#100) N-side per-bit switch control. That scheme's own rationale was
that a differential DAC needs the two sides' `SEL` complementary (not equal)
because `design/cdac/cdac_unit_cell.sch`'s single-control-line switch uses the
identical truth table on both array sides. DR-008's closed-loop verification
found the conclusion wrong (driving both sides unconditionally moves both
bottom plates by a full reference swing on every bit trial); see that record,
not `design/sar_adc_top.sch`'s superseded header, for the wiring that stands.

**This was new top-level glue logic, not a sub-block re-layout.** None of
#99 (sampling front end), #100 (CDAC array), #101 (comparator) or #102 (SAR
sequencer)'s own schematics instantiate these nine cells; they existed only in
the integration schematic issue #103 itself owns. That is why this directory
lives next to `layout/sar-sequencer/` etc. rather than inside any of them —
and `layout/top-glue/` sits there now for the same reason.

## Status: DRC-clean, LVS-clean

`reports/LATEST`'s record:

| Verdict | Result |
| --- | --- |
| `klt place-and-route` | reaches `route`, 0 setup/hold violations |
| `klt drc --deck sky130` | **CLEAN**, 0 violations |
| `klt lvs` | **match**, 18/18 devices, 20/20 nets, 20/20 pins (9 informational "ambiguous pairing resolved structurally" warnings, one per symmetric `SELn<i>` net — expected for nine electrically-identical, independently-driven inverters, not a real defect) |

## WITHDRAWN 2026-09-24 (issue #363): the "33 metal minimum-area violations" were a measurement artifact

**This section used to be a dated waiver over 33 sub-minimum-area shapes,
issued under issue #333 on 2026-09-19. It is withdrawn, not reaffirmed: there
were never 33 violations, and there are none now.** The count came from
`docs/chipalooza/measure_metal_min_area.py`, which issue #363 found
**under-merges** the region it measures.

The script built its region as `kdb.Region(); region.insert(iter);
region.merge()`. `Region#insert(RecursiveShapeIterator)` carries each shape's
GDS user properties across, and KLayout's merge is **property-aware**: two
overlapping polygons whose property sets differ are never merged into one. The
DEF→GDS merge attaches a net-name property (`[[1, "VPWR"]]`, `[[1, "VGND"]]`)
to every PDN strap and none to the via cells sitting inside it, so a covered
via pad stayed its own polygon and was counted as a standalone violation. The
15 `m5.4` "violations" were the clearest case of all: each is a 1.42 × 1.60 um
via5 patch lying wholly **inside** a 1.6 um-wide met5 PDN strap that is itself
far above the 4.0 um² floor.

Re-measured 2026-09-24 against the same
`reports/20260917-180644-527ec73/seln_inverters.gds`, same pinned toolchain
(`klayout 0.30.12`, open_pdks `c6d73a35f524070e85faff4a6a9eef49553ebc2b`),
with the corrected construction:

| Rule | Threshold | Merged polygons (pre-#363 → corrected) | Shapes below (pre-#363 → corrected) |
| --- | --- | --- | --- |
| `m1.6` | 0.083 um² | 130 → 60 | 18 → **0** |
| `m2.6` | 0.0676 um² | 216 → 102 | 0 → **0** |
| `m3.6` | 0.240 um² | 180 → 90 | 0 → **0** |
| `m4.4a` | 0.240 um² | 111 → 6 | 0 → **0** |
| `m5.4` | 4.0 um² | 20 → 5 | 15 → **0** |

**33 → 0.** `layout/sar-sequencer/`, the other `klt place-and-route` flow,
carried the companion waiver over 112 shapes on the same premise; it corrects
to 0 the same way, and 112 + 33 was exactly the composed top level's
now-retracted 145.

**Independent corroboration.** This flow's own record predates the
`klayout-tools==0.6.0` bump, so its `drc.json` carries no `area`-kind rule. But
this block's GDS is composed verbatim into `layout/sar-adc-top/`, whose current
record `20260924-190817-f3622fc` was minted on the 0.6.0 pin and whose
`drc.json` `coverage.rules_checked` **does** include `met1.area.1` …
`met5.area.1` (52 rules, status `clean`, **0 violations**) over geometry that
contains this block's. Two independent measurements of the same five foundry
rules now agree at zero; before #363 they disagreed, and the hand-rolled one
was wrong.

The regression is pinned by `sim/tests/test_measure_metal_min_area.py` and run
in CI's headless `checks` job, so this count cannot silently drift again.

**Upstream filings, now superseded.** `2AMLogic/klayout-tools#2139` was filed
(generically, per CLAUDE.md's friction protocol) as the live tool gap for this
"defect", with a generic 48-stage inverter-chain reproducer whose 99 sub-
`m1.6`/`m5.4` shapes were counted with the same under-merging measurement; its
premise does not survive #363, and it should be read as withdrawn on this
repo's side. That withdrawal is now on the public record: under issue #373 the
reproducer was re-run from its own quoted inputs and measured both ways on the
identical output GDS — 76 shapes below threshold under the pre-#363
construction, **0** under the corrected one — and a correction comment was
posted on `#2139`, which had already been closed upstream (`COMPLETED`,
2026-09-19) by merged PR `2AMLogic/klayout-tools#2144`. See
`layout/sar-sequencer/README.md`'s copy of this block for the per-rule numbers
and for why no revert of `#2144` was asked for. The earlier `#2072`/`#2075`
pair is split: `#2075`'s `klt
gen-compose` landing-pad fix addressed a real, separate defect (issue #326's 17
shapes were genuinely isolated pads) and stands, while the place-and-route half
does not. `#1989` — merged and, as of the 0.6.0 pin, **released** — is what
gives `klt drc` its own `met*.area.1` rules and therefore the corroboration
above.

## Which `klt` flow, and why

`klt place-and-route` (OpenROAD), the same choice `layout/sar-sequencer/`
makes and for the same reason: `netlist/seln_inverters.v` was a **hand-verified
1:1 structural transliteration** of `design/sar_adc_top.sch`'s own
`xinv_seln0..xinv_seln8` instances **as that schematic stood under issue #56**
(nine independent `sky130_fd_sc_hd__inv_1` cells, `DOUT<i>` -> `A`,
`SELn<i>` -> `Y`), not RTL — there is nothing for `klt synthesize` to usefully
do. Those nine instances no longer exist: DR-008 removed them on 2026-09-11,
and nothing re-derived this netlist afterwards (issue #387). "1:1 with the
schematic" was true when written and is not true now — see the banner at the
top of this file.

**No clock, no state — but the request schema still requires
`constraints.clock_port`/`clock_period_ns`.** This design has zero sequential
elements, so `requests/place-and-route.json` declares a placeholder clock net
name (`CTS_NO_SUCH_CLOCK`) that does not appear anywhere in the netlist,
purely to satisfy that required field. Naming a *real* net (e.g. an actual
input pin) as the placeholder instead reproducibly **segfaults** `klt
place-and-route`'s `cts` stage (OpenROAD exit code 139) once that net has zero
fanout to any sequential cell — filed generically as
`2AMLogic/klayout-tools#1506`; the nonexistent-net workaround above avoids it
by taking `clock_tree_synthesis`'s no-op path instead.

**Floorplan is generously oversized for the cell count** (9 single-height
`inv_1` instances, ~2% final utilization) because `klt place-and-route`'s PDN
generator (`add_pdn_stripe`) needs enough die width for at least one full-width
met4/met5 strap (sky130's `met4`/`met5` minimum width is 1.6 µm) with real
margin on both sides — the same real PDN (`tapcell` ties,
`add_global_connection`/`pdngen` merging every `VPWR`/`VPB` pin into one net
and every `VGND`/`VNB` pin into another, plus met1/met4/met5 straps) issue
#102 needed for a *connected* `VPWR`/`VGND` rather than the row-rail-only
obstruction `klt place-and-route` draws by default when `power` is omitted —
see `layout/sar-sequencer/README.md`'s own "Power delivery" note for why an
unconnected PDN makes LVS unreachable independent of any `klt` gap. A future
pass could shrink this by tuning strap width/pitch for such a small block;
area was not a goal here (this macro's isolated LVS/DRC closure was).

## LVS reference provenance

Same mechanism as `layout/sar-sequencer/bin/generate-lvs-reference.py` (issue
#102): `klt extract --deck sky130` is a flat, transistor-level extractor, so
the LVS reference has to be flat and transistor-level too, with every drawn
NMOS/PMOS generalized to `klt`'s own `nfet`/`pfet` device classes.
`bin/generate-lvs-reference.py` flattens the **post-route** structural
Verilog netlist (`klt place-and-route`'s own `write_verilog` dump) against
the sky130 PDK's own official per-cell CDL model
(`sky130_fd_sc_hd.cdl`, Apache-2.0, SkyWater's own release — not
reverse-engineered).

## Running the flow

```sh
layout/bin/setup-venv.sh              # once, or after bumping requirements.txt
source sim/env.sh                      # exports PDK_ROOT/PDK
layout/seln-inverters/bin/run-flow.sh   # ~1 minute; place-and-route -> DRC -> LVS
```

Requires an `openroad` binary on `$PATH` (see `docs/environment-setup.md`).
Each run mints a new timestamped, append-only record under `reports/<record-id>/`
(same convention as `layout/trivial-cell/reports/`), and `reports/LATEST`
points at the newest one.

## Files

```
layout/seln-inverters/
  README.md                        # this file
  netlist/
    seln_inverters.v               # hand-verified structural netlist (not RTL)
  requests/
    place-and-route.json           # klt place-and-route request
  bin/
    run-flow.sh                    # place-and-route -> DRC -> post-route netlist dump -> LVS reference -> extract --def-pins -> LVS -> record
    generate-lvs-reference.py      # flattens the post-route netlist against the PDK's own CDL models
    render-record.py               # renders record.md from the JSON envelopes run-flow.sh produced
  reference/                       # generate-lvs-reference.py's own output -- regenerated per run, git-ignored
  reports/
    LATEST                         # record-id of the most recent run
    <record-id>/                   # append-only: netlist, request, routed GDS/DEF, post-route netlist,
                                    # generated LVS reference, every klt JSON envelope, record.md
```

## `klt 0.4.0` → `0.5.0` re-run (issue #323): no change

This flow's sign-off record rested on `klt 0.4.0` (`reports/20260906-002022-a36e06f/`)
while `layout/requirements.txt` had already moved to `klt 0.5.0` for the other
sub-blocks and the top-level composition — a version-parity gap, not a known
defect (see the parent issue for why that gap mattered). Re-run under the
pinned `klt 0.5.0` (`reports/20260917-180644-527ec73/`, now `reports/LATEST`):
`drc.json` and `lvs.json` are field-identical to the superseded record —

| Field (source) | `klt 0.4.0` | `klt 0.5.0` | Delta |
| --- | --- | --- | --- |
| `drc.json` `status` / `violation_count` | clean / 0 | clean / 0 | none |
| `lvs.json` `status` | match | match | none |
| `lvs.json` `mismatch_count` / `error_count` | 9 / 0 | 9 / 0 | none |
| `lvs.json` `counts.devices` (layout/reference/matched) | 18/18/18 | 18/18/18 | none |
| `lvs.json` `counts.nets` (layout/reference/matched) | 20/20/20 | 20/20/20 | none |
| `lvs.json` `counts.pins` (layout/reference/matched) | 20/20/20 | 20/20/20 | none |
| `lvs.json` `category_counts` | `topology: 9` | `topology: 9` | none |

The nine `topology` entries are the same expected "ambiguous pairing resolved
structurally" warnings the Status section above describes (one per
symmetric, electrically-identical `SELn<i>` inverter), unchanged in count or
kind under `klt 0.5.0`. No regression, so no upstream `klayout-tools` issue
was filed for this re-run.

## Where this fits into #103's top-level assembly

This macro is, **for now and wrongly**, one of the five blocks the top-level
assembly places and routes (the other four being #99/#100/#101/#102's own
already-closed layouts). Its own ports (`DOUT8..DOUT0`, `SELn8..SELn0`,
`VPWR`, `VGND`) are documented, with exact DEF-derived coordinates, in
`layout/sar-adc-top/README.md`'s floorplan notes, alongside the other four
blocks' pin geometry — see that directory for the composition/routing status.

That composition is the reason this directory has not been deleted, and it is
itself the remaining half of issue #387: the assembly (issue #401) must place
`layout/top-glue/` and DR-009's half-LSB offset network (issue #400) instead of
this block, and `layout/sar-adc-top/bin/generate-lvs-reference.py`'s `TOP_SUBCKT`
wrapper must be re-derived from `design/sar_adc_top.spice` as it stands. Until
then the composed `sar_adc_top.gds` implements issue #56's superseded glue, and
no LVS verdict on it — clean or otherwise — says anything about whether it
implements this repo's schematic.

## Provenance

Structure follows `layout/sar-sequencer/`'s own conventions (append-only
timestamped records, `reports/LATEST` pointer, `record.md` provenance
stamping, CDL-based flat LVS reference generation), narrowed to this block's
single cell type and its own top-level port list. Clean room: the topology
placed and routed is this repo's own `design/sar_adc_top.sch` (issue #56);
the only external inputs are the sky130 PDK's own official, freely-licensed
standard-cell library and OpenROAD's own placement/routing/CTS algorithms.

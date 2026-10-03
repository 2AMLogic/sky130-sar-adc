# layout/halflsb-offset/ — DR-009's half-LSB quantizer-offset network (issue #495)

Physical layout for the **8 `sky130_fd_pr` primitives `design/sar_adc_top.spice`
adds directly at the integration level**, inside no sub-block, and which had no
drawn geometry anywhere under `layout/` before this directory existed:
`spec/decision-records/DR-009-comparator-output-load-balance-and-half-lsb-offset.md`
item 2's half-LSB quantizer offset, plus its matching dummy.

`layout/top-glue/` (issue #387) covers the 33 `sky130_fd_sc_hd` instances of the
same region. These eight are the non-standard-cell remainder: `klt
place-and-route` places `sky130_fd_sc_hd` cells on a `unithd` site grid and has
no notion of a MiM capacitor or a hand-sized analog switch, and `BOT_OFF_N` /
`BOT_OFF_P` hang directly off the comparator's own `TOP_N` / `TOP_P` input
nodes, so placing them is an analog-floorplan question rather than a row-placement
one. Together the two directories close the top level's primitive census;
composing both into `layout/sar-adc-top/` is issue #401 and is **not** claimed
here.

## What is here

Census, re-derived from `design/sar_adc_top.spice` on every run by
`bin/check-schematic-parity.py` (and independently reported by `python3
docs/chipalooza/check_proposal_citations.py --stats`):

| Instance | Device | Size | Role |
| --- | --- | --- | --- |
| `Choff_n` | `cap_mim_m3_1` | `W = L = 1.9000` (drawn 1.900) | offset cap, `TOP_N` ↔ `BOT_OFF_N` |
| `Moff_n_refp` | `pfet_01v8` | `L=0.15 W=2` | `BOT_OFF_N` → `VREFP`, gate `HALF_LSB_EN` |
| `Moff_n_cmn` | `nfet_01v8` | `L=0.15 W=1` | `BOT_OFF_N` → `VCM`, gate `HALF_LSB_EN` |
| `Moff_n_cmp` | `pfet_01v8` | `L=0.15 W=2` | `BOT_OFF_N` → `VCM`, gate `HALF_LSB_ENN` |
| `Choff_p` | `cap_mim_m3_1` | `W = L = 1.9000` (drawn 1.900) | matching dummy cap, `TOP_P` ↔ `BOT_OFF_P` |
| `Moff_p_refp` | `pfet_01v8` | `L=0.15 W=2` | tied off (gate `VGND`) |
| `Moff_p_cmn` | `nfet_01v8` | `L=0.15 W=1` | tied off (gate `VGND`) |
| `Moff_p_cmp` | `pfet_01v8` | `L=0.15 W=2` | tied off (gate `VPWR`) |

**8 instances, 3 device types, 12 nets.** What the network does — one CDAC
unit cap driven over *half* the reference swing, so the `+0.5 LSB` offset is set
by a reference ratio rather than by a sub-unit capacitor; the `_p` side existing
only so both comparator top plates carry the same capacitance and the same switch
junction parasitics; and why the `HALF_LSB_EN = BUSY AND NOT(PH_B9)` timing is
load-bearing — is DR-009's, not this directory's. Read that record; this flow
implements it and does not re-derive it.

## Status: DRC-clean, LVS-clean

`reports/LATEST`'s record, whose full fourteen-verdict list is in that
`record.md`:

| Verdict | Result |
| --- | --- |
| `bin/check-schematic-parity.py` | **OK** — 8 instances, 3 device types, 12 nets, every terminal net identical to `design/sar_adc_top.spice` |
| `klt drc --deck sky130` (7 blocks, then composed) | **CLEAN**, 0 violations |
| `klt drc` on the illegal n-well fixture, same deck | **VIOLATIONS** naming `nwell.space.1` |
| `klt precheck` (1 nm database grid) | **pass** |
| `klt precheck` (5 nm manufacturing grid) | **pass** since #498 — 0 off-grid shapes, down from 48 (see "The 5 nm manufacturing grid") |
| `klt extract --deck sky130` | 8 devices (4 pfet / 2 nfet / 2 MiM), 12 nets, 12 pins, no single-terminal net, no unbiased PMOS body |
| `klt lvs` vs the schematic-derived reference | **match**, 8/8 devices, 12/12 nets, 12/12 pins |
| `klt lvs` vs device-parameter / cap-top-plate controls | **mismatch** (both) |
| `_n`/`_p` translation congruence | asserted at build time, 41 shapes + 13 columns per side, in DBU |

## What `klt lvs` cannot see on this block

**`klt lvs` reports a clean `match` against a reference whose `HALF_LSB_EN` and
`HALF_LSB_ENN` are exchanged on the working side's three gates** — i.e. against
DR-009's load-bearing enable polarity inverted. That is measured on every run
(`reports/<id>/lvs.swapped-enable.json`), not argued.

The mechanism: `NetlistComparer` matches nets structurally rather than by name,
and both enables enter this network only as ports, so exchanging them is a
legitimate isomorphism of the graph. The comparer simply reports
`HALF_LSB_EN <-> HALF_LSB_ENN` in its own net-correspondence table and calls it a
match.

Two things follow, and both are wired in rather than noted:

1. **`bin/render-record.py` grades name-identical net correspondence as a
   verdict of its own.** The corruption *is* in the same JSON envelope — in
   `net_correspondence`, not in `status` — so requiring every matched net's
   layout name to equal its reference name turns this class back into a failure.
2. **`bin/check-schematic-parity.py` is load-bearing here, not
   belt-and-braces.** It re-derives the expected device table from
   `design/sar_adc_top.spice` and diffs it against the table the geometry is
   built from, so the swap fails before a record can be minted.
   `sim/tests/test_halflsb_offset_schematic_parity.py` pins that with the swap
   itself as its most important negative case.

This is issue #387's lesson — "a generated-reference LVS flow agrees with
itself" — reproduced and measured on a different block, with a different
mechanism. If a future `klt` reports the swapped-enable control as a `mismatch`,
verdict 13 fails: **invert the verdict and say so in the next record, do not
delete it.** Same discipline as issue #149's inversion of
`layout/sampling-frontend-wells/`'s verdict 5 once klt 0.4.0 closed the n-well
DRC gap that verdict measured.

## Matching is a construction property, not a claim

DR-009's `_p` half injects nothing. Its only job is that both comparator inputs
see the same capacitance and the same switch junction parasitics — so a dummy
that is *not* matched is worse than no dummy, because it adds an unbalanced load
while the schematic claims it removes one. Neither DRC nor LVS can see the
difference: a layout that scattered the `_p` devices arbitrarily would be clean
and would match.

So `bin/build_layout.py` asserts it. `_assert_side_congruence()` takes the two
sides' shape lists, translates every `_n`-side shape by exactly
`SIDE_PITCH_UM = 16.00 um`, and raises unless the result is the `_p` side's list
as a multiset — every well, tap, licon column, mcon, via stack, landing pad and
jog, compared in integer nanometres so it is exact rather than tolerant. The met1
column positions are checked the same way. `layout.summary.json` records how much
was covered (41 shapes and 13 columns per side on the current record) and
`record.md` states it.

**The assertion's own ability to fail is tested**, because every committed run is
of a layout that *is* congruent, so a silently-vacuous assertion would look
identical in the record. `sim/tests/test_halflsb_offset_side_congruence.py`
(headless, in `npm run check:ci`) drives `_assert_side_congruence()` over a
congruent positive control and then over six one-database-unit breaks — x drift,
y drift, a wrong layer, a missing shape, an extra shape, a column-table drift —
and requires each to raise; it also reads `reports/LATEST`'s own
`layout.summary.json` and fails if that run's congruence verdict covered zero
shapes. `_assert_matched_pairs_adjacent()` gets the same treatment.

Two things sit outside that assertion, both by necessity:

- **The two caps' own internal geometry**, which this module does not draw. Both
  offset caps are the two units of a *single* `klt gen cap_array num=2` call, so
  their equality is the generator's property — a stronger statement than a
  congruence check on shapes this flow wrote. `build_layout.py` additionally
  asserts that the pitch the generator actually achieved is `SIDE_PITCH_UM`
  exactly, so a future `klt` with a different met3 enclosure fails the build
  rather than silently shifting one side of the network.
- **Everything at or above the met2 track band.** Each net owns exactly one
  track, and the two sides' corresponding nets are *different nets*
  (`HALF_LSB_EN` vs `VGND`, `BOT_OFF_N` vs `BOT_OFF_P`), so their tracks cannot
  share a y and their met1 risers cannot be congruent. `TRACK_ORDER` therefore
  keeps each matched pair on **adjacent** tracks — asserted by
  `_assert_matched_pairs_adjacent()`, because nothing else in the module would
  notice a reordering that made the separation six tracks instead of one — which
  bounds the residual at one track pitch per matched net. The current record
  measures it: **4.0 µm of met1 length difference in total, 1.2 µm² of 0.30 µm
  met1**, across the four matched net pairs.

**What this is not.** No matching *measurement* backs any of the above. There is
no Monte Carlo mismatch run on this network, and the congruence assertion is a
statement about drawn geometry, not about silicon: it says the two sides are the
same shape in the same orientation at a fixed offset, which is the strongest
thing a flow with no mismatch simulation is entitled to say. Same standing as
"Layout choices that are not claims" in `../sampling-frontend-wells/README.md`.

### One translation vector, and what it costs

The whole `_p` half is *one* translation of the `_n` half, which required setting
the `cap_array` pair's own unit pitch equal to the switch groups' translation
(`gen_blocks.CAP_SPACING_UM` is derived from `SIDE_PITCH_UM`, not chosen). The
benefit is that `BOT_OFF_N`'s and `BOT_OFF_P`'s routing — the nets whose
parasitics DR-009 wants matched — is congruent, not merely similar.

The cost is stated plainly: the two offset caps sit **16 µm apart** rather than
abutting at the generator's minimum spacing, so any linear process gradient
across that span is uncorrected, where an abutting pair would largely cancel it.
That is a real tradeoff and it was taken deliberately, on the grounds that the
routing asymmetry an incongruent floorplan produces is the larger and the more
*systematic* of the two errors, while neither is measured here. Area was not a
consideration either way (the composed cell is ≈ 31 × 19 µm, mostly empty
channel).

## The 5 nm manufacturing grid

The flow runs `klt precheck` twice and **both runs are gating**:

- `--grid-um 0.001` (the layout's own database unit) — must pass outright.
- `--grid-um 0.005` (sky130's manufacturing grid) — must pass outright too,
  since issue #498. `record.md` still prints a per-cell/per-layer census of
  every off-grid shape; it is now empty.

### It did not always pass, and why the fix was not this flow's to make

This block was the first place in the repo to measure the 5 nm grid, and the
first measurement failed: **48 off-grid shapes**
(`reports/20260930-231954-70fdc06/`), spread over `capm`/met3/via3/met4 and the
met1/via1/met2/via2 that lands on them.

Every coordinate this flow *chooses* was already snapped to the 5 nm grid
(`build_layout.GRID_UM`, applied to the met4 escape height and the track band's
floor). The coordinate it does not choose is the MiM plate side: DR-009 sizes
the offset cap identically to `design/cdac/cdac_unit_cell.sch`'s `C_u`, and that
plate was **1898 nm** on a side. 1898 is not a multiple of 5, so neither the
plate's own edges nor the port coordinates derived from it (a plate centre at
1449 nm, a bottom-plate port at the plate edge) could land on a 5 nm grid, and
neither could any via or landing pad centred on those ports. Rounding the plate
to a 5 nm-legal value *here alone*, without moving `C_u` identically, would have
been a ratio error rather than a fix — the half-LSB step is a ratio against one
array bit.

So the question went where it belonged, to the unit cap. Issue #496 decided it:
[DR-019](../../spec/decision-records/DR-019-cdac-unit-cap-grid-legal-plate-resize.md)
reads the PDK's own shipped signoff DRC deck directly, finds the 5 nm grid check
is real (not a klt-only convention) and on by default for the metal/via layers
that land on the plate, and resizes `C_u`'s plate to the smallest
5 nm-grid-legal side at or above DR-003 Item 3's matching floor — `1.9000 µm`,
up from `1.8988 µm`, `C_u` `8.654 fF` → `8.664 fF`.

### The measurement DR-019 deliberately did not make

DR-019 declined to predict where the census would land, calling it "expected to
shrink sharply (though not necessarily to zero)" and leaving the measurement to
issue #498, which carried the resize through `design/`, `layout/cdac-array/` and
this block. Measured, on the identical flow with only the plate side changed:

| | before (1.898 µm plate) | after (1.900 µm plate) |
| --- | ---: | ---: |
| `halflsb_offset` off-grid shapes at 5 nm | 48 | **0** |
| `cdac_unit_cell` off-grid shapes at 5 nm | 1 | **0** |
| `cdac_array` off-grid shapes at 5 nm | 1024 | **0** |

It reaches zero. Nothing else in either block was off-grid for any other
reason — every one of the 48 shapes traced back to the plate side, directly or
through a via centred on a port derived from it.

Verdict 6 was therefore **inverted**, not deleted: it used to assert that
`offgrid` was the only failing check and that every off-grid shape sat on a
MiM-stack layer (i.e. that no transistor-level geometry was off-grid); it now
requires an outright pass. The same discipline issue #149 applied when klt 0.4.0
closed the n-well DRC gap `layout/sampling-frontend-wells/`'s verdict 5
measured — a verdict that still tolerated a residual would now be permission to
regress. `layout/cdac-array/` gained its own pair of precheck verdicts in the
same pass, per DR-019's standing policy that this check is a gate for any block
in this repo drawing a MiM cap, not an advisory metric.

## Which `klt` flow, and why

Device generators + a hand-written floorplan/router emitted through `klt draw` +
`klt gen-compose` as a **placer only**, i.e. `layout/sampling-frontend/`'s shape.
That block draws the closest thing already in this repo — MiM caps plus
hand-sized `nfet_01v8`/`pfet_01v8` switches, DRC-clean and LVS-clean — and this
one composes the same two generator families, so it reuses that flow's own
routing scheme rather than inventing a second one:

- **One met2 track per net, met1 the rest of the way.** Every pin is walked down
  to met1 before it is routed and only returns to met2 at the one via1 cut that
  lands it on its own net's track. `layout/bin/_geometry_common.py`'s
  `step_down_to_met1()` is the shared emitter, including the three
  empirically-found DRC fixes in it (the met3 via inset off the plate edge, the
  met4 escape *above* the bottom plate's own sheet — landing it inside the
  footprint shorts the two plates — and the 0.50 µm met3 island pad that clears
  `m3.6`'s minimum-area rule).
- **Two n-well islands, one per side, both tapped to `VDD`.** Every `XMoff_*`
  PFET card declares `VDD` as its body, so unlike `layout/sampling-frontend/`'s
  DR-007 three-domain partition there is no multi-domain body-tie question here.
  The islands are split because the `cmn` NFET sitting between them may not be
  inside an n-well — not because they are different nets.
- **Two p-substrate taps, one per side, tied to `GND`.** Read narrowly, exactly
  as `layout/sampling-frontend/bin/build_layout.py` documents: `klt extract
  --deck sky130` synthesizes **one global** NMOS body net via `connect_global`
  regardless of drawn geometry, so no drawn tap makes the two NFET bodies two
  separately-checkable terminals. What the taps do is merge this layout's drawn
  `GND` conductor into that global net, without which `GND` would extract as an
  ordinary signal net and LVS would not match at all.

`layout/bin/_geometry_common.py`'s `step_down_to_met1()` and
`layout/bin/_pfet_devices.py`'s `mos_array_params()` are both shared copies whose
originals still live in `layout/sampling-frontend/bin/`. They were not folded
into one in this pass because that flow's output is the drawn geometry behind a
committed, append-only record; `sim/tests/test_geometry_common_shared_helpers.py`
drives both copies over every input and asserts identical output, so the
duplication is graded rather than merely noted and the eventual fold-in is a
provable no-op.

## LVS reference provenance

`bin/generate-lvs-reference.py` derives the reference from
`design/sar_adc_top.spice`'s own eight cards (via `bin/_schematic_cards.py`),
generalizing device classes to `klt extract --deck sky130`'s own flat vocabulary
— the only vocabulary the layout side can report. It is regenerated on every run
into the record directory; nothing is hand-written and nothing is committed
outside a record.

The reference states a *capacitance* where the card states a `W`/`L`, because
that is the only vocabulary the layout side reports:
`camimc·W·L + cpmimc·2(W+L)` on the drawn plate, with the extraction deck's own
published tt coefficients (area 2.0 fF/µm², perimeter 0.19 fF/µm). Derived from
geometry and coefficients, never read back out of an extraction result.

Since DR-019 (#496/#498) the drawn plate and the card agree exactly — both
`1.9000 µm`, giving `8.664000e-15 F`. Before it, the card asked for `1.8988`
(1898.8 nm, undrawable on the 1 nm database grid) and this block drew
`layout/cdac-array/`'s own `1.898` instead, for `8.647288000e-15 F`; that
departure is retired. `bin/check-schematic-parity.py` is what kept it from
widening and still does: it asserts the drawn plate side equals
`layout/cdac-array/bin/cdac_layout.py`'s own `CAPM_SIDE` (read out of that file's
text) and is within one database unit of the schematic's own value.

Clean room: every device, net and coefficient above is this repo's own schematic
or the pinned sky130A PDK's own published extraction data. Nothing is transcribed
from any third-party layout.

## Running the flow

```sh
layout/bin/setup-venv.sh               # once, or after bumping requirements.txt
source sim/env.sh                      # exports PDK_ROOT/PDK
layout/halflsb-offset/bin/run-flow.sh  # ~1 minute
```

Requires `layout/.venv` and a resolvable sky130A PDK install (the `sim/pdk.json`
pin). No `klayout` binary and no `openroad`. Each run mints a new timestamped,
append-only record under `reports/<record-id>/` and `reports/LATEST` points at
the newest one.

The schematic-parity gate runs **before** the record directory is created and is
the one stage that aborts the flow rather than being graded afterwards: a layout
table that has drifted from `design/sar_adc_top.spice` must not be able to mint a
record at all. It is also always-on in CI via `npm run check:halflsb-parity`
inside `check:ci` — headless, no PDK — for the reason `layout/top-glue/`'s
equivalent is: the drift it catches is invisible to every verdict this repo
records.

## Files

```
layout/halflsb-offset/
  README.md                       # this file
  bin/
    run-flow.sh                   # parity gate -> gen -> per-block DRC -> build -> draw ->
                                  # compose -> DRC (+ n-well fixture) -> precheck x2 ->
                                  # extract -> 4 references -> LVS x4 -> record
    gen_blocks.py                 # the device table (roles + per-side nets) and the
                                  # `klt gen` invocations
    build_layout.py               # floorplan, n-well islands, taps, routing; asserts the
                                  # _n/_p translation congruence
    _schematic_cards.py           # the schematic side: reads design/sar_adc_top.spice's own
                                  # cards and decides block ownership from them
    check-schematic-parity.py     # the independent anchor -- see the sections above
    generate-lvs-reference.py     # the schematic-derived reference + three negative controls
    render-record.py              # renders record.md, asserts the fourteen verdicts
  reports/
    LATEST                        # record-id of the most recent run
    <record-id>/                  # append-only: per-block GDS/JSON, draw/compose requests,
                                  # layout.summary.json, the composed GDS, every klt JSON
                                  # envelope, schematic-parity.txt, the four references,
                                  # the extracted netlist, report.md, record.md
```

The headless tests that hold the two build-time gates non-vacuous live with the
rest of this repo's stdlib-only tests rather than here, so `npm run check:ci`
picks them up without a PDK:

```
sim/tests/
  test_halflsb_offset_schematic_parity.py   # nine injected schematic defects, each of which
                                            # check-schematic-parity.py must reject, plus the
                                            # committed netlist as the positive control
  test_halflsb_offset_side_congruence.py    # the _n/_p congruence assertion's positive control
                                            # and six 1 nm breaks it must raise on
  test_geometry_common_shared_helpers.py    # pins the two helpers this block shares with
                                            # layout/sampling-frontend/ to its own copies
```

## Upstream filings (`klayout-tools`, per CLAUDE.md's friction protocol)

- [klayout-tools#2638](https://github.com/2AMLogic/klayout-tools/issues/2638) —
  `klt gen-compose`'s `explicit`-strategy spacing warning (the check
  klayout-tools#692 added) has one field, `drc_hints.min_spacing_um`, for two
  unrelated meanings, and this flow trips both. **13 warnings on every run, with
  `klt drc` on the composed layout clean**, split as `reports/<id>/record.md`
  itself partitions them:
  - **7** cite `choff`: `klt gen cap_array` reports the **requested** inter-unit
    `spacing_um` as its own `min_spacing_um`, so a matched pair deliberately
    spaced 16.0 um apart — a pitch chosen precisely so the switches sit between
    the units — makes every block inside that span look like a spacing
    violation. The value is an intra-array pitch, not a clearance.
  - **6** cite a `moff_*` switch: the `route` cell carries the licon/met1 that
    *contacts* each device's own ports, so it is placed at 0.00 um from every
    one of them by construction. There is no way to declare an intentional
    abutment, so the count scales with the number of devices the routing cell
    touches.
- [klayout-tools#2639](https://github.com/2AMLogic/klayout-tools/issues/2639) —
  `klt gen-compose`'s `placement.origins_um` accepts a translation only: there is
  no way to place a generated block mirrored or rotated, which is the natural
  expression of an analog matched pair. This block works around it with pure
  translation congruence (see "Matching is a construction property"), which is a
  defensible choice here — the `_p` side is a *dummy* that injects nothing, so
  gradient cancellation across the pair is not what its matching is for — but
  would not be for a common-centroid pair.

Both are filed generically (tool gap only, no spec values, no block topology),
per `CLAUDE.md`'s friction protocol.

## Provenance

Flow shape, record conventions and routing scheme follow
`layout/sampling-frontend/` (device generators, `klt draw` for every wire,
`klt gen-compose` as a placer, append-only timestamped records, `reports/LATEST`,
`record.md` provenance stamping, positive + negative LVS controls); the
schematic-parity gate follows `layout/top-glue/bin/check-schematic-parity.py`
(issue #387), widened from `sky130_fd_sc_hd` instance lines to `sky130_fd_pr`
cards — device flavour, `W`, `L`, `m`/`MF` and every terminal net — and given a
schematic-side ownership rule so a new top-level primitive cannot land in no
block at all.

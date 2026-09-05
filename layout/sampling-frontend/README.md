# layout/sampling-frontend/ — the sampling front end sub-block layout (issue #99)

Physical layout for the whole sampling front end of this SAR ADC, drawn against
`design/sampling_frontend.sch`: the differential input switches `Msw_p`/`Msw_n`,
the bootstrap/precharge switch set that defines the sampled common mode, the
`Invp`/`Invn` clock inverter, and the four MiM capacitors — **24 devices, 17
nets**, verified end to end with `klt`'s draw → DRC → extract → LVS flow.

```sh
layout/bin/setup-venv.sh                    # once, or after bumping requirements.txt
source sim/env.sh                           # exports PDK_ROOT/PDK
layout/sampling-frontend/bin/run-flow.sh    # ~3.5 min; exit 0 iff all eleven verdicts hold
cat layout/sampling-frontend/reports/$(cat layout/sampling-frontend/reports/LATEST)/record.md
```

No `klayout` binary is needed — every stage runs through klt's own built-in
decks via the `klayout` Python module. (`layout/sampling-frontend-wells/`'s
flow does need one; see "Why there is no hand-written DRC deck here" below.)

**Status: DRC-clean, LVS-clean, 24/24 devices, 17/17 nets, 12/12 pins**, with
every PFET body extracting on the n-well island DR-004 requires. The record
referenced by `reports/LATEST` carries all eleven verdicts, seven positive and
four negative:

| # | Verdict | Why it is here |
| --- | --- | --- |
| 1 | every `klt gen` block is DRC-clean *in isolation* | a composed-DRC failure is attributable to the wells/routing, not to a device |
| 2 | `klt drc --deck sky130` on the composed layout is **clean** | the deliverable is legal against the rules that deck carries |
| 3 | that **same** deck reports **violations**, naming `nwell.space.1`, on a deliberately-illegal n-well fixture | verdict 2 means nothing until "violations" is shown reachable on the same deck in the same run — and on the well layer specifically, which the previous klt pin did not check at all |
| 4 | `klt precheck` passes | geometry hygiene; every pin label lands on drawn metal |
| 5 | extraction reports **exactly** 11 nfet + 9 pfet + 4 MiM caps | the population the schematic instantiates, no more and no less |
| 6 | extraction reports **no** single-terminal net | the cheap, legible guard against the defect this layout actually hit (see "The MiM top-plate trap") |
| 7 | extraction reports **no** unbiased PMOS body net | no PMOS body fell back to KLayout's anonymous, DC-floating proxy net |
| 8 | extraction reports **each** PFET's body on its own island's tap net — `Sa`/`Se` on `BOOST_P`/`BOOST_N`, the other five on `VDD` | DR-004's requirement, measured; verdict 7 alone would be satisfied by one VDD well over everything |
| 9 | `klt lvs` reports **match** against `reference.spice` | the drawn geometry is the schematic, body column included |
| 10 | `klt lvs` reports **mismatch** against `reference.broken-body-tie.spice` | LVS notices a *body-terminal-only* corruption (the four boosted bodies moved to VDD, nothing else changed) |
| 11 | `klt lvs` reports **mismatch** against `reference.broken-device.spice` **and** `reference.broken-topology.spice` | LVS notices a *device-parameter-only* corruption (one W changed) and a *capacitor-top-plate-net-only* corruption |

Verdicts 3, 6, 10 and 11 are the falsifiability discipline
`layout/trivial-cell/` established for this repo (issue #2), each specialised
to a failure mode this sub-block can actually suffer.

---

# The matching / dummy strategy

The issue this directory closes calls this out explicitly, and it deserves to
be: **common-mode definition is sensitive to switch mismatch**, so a layout
that is DRC- and LVS-clean can still be wrong in a way neither checker has an
opinion about. What follows is the deliberate strategy, stated so it can be
argued with — and, where it is measurable, measured.

## 1. What is matching-critical here, and what is not

Three device groups in this schematic, with genuinely different sensitivity:

| Group | Devices | Mismatch shows up as | Treatment |
| --- | --- | --- | --- |
| **Input switches** | `Msw_p`, `Msw_n` | differential sampled-charge error, i.e. an input-referred offset and a common-mode-to-differential conversion term | identical drawn geometry, symmetric routing (§2) |
| **Sampling capacitors** | `Csamp_p`, `Csamp_n` | direct differential gain error; a ΔC/C plate mismatch is a first-order INL/offset term | one `cap_array num=2` call — see §3 |
| **Bootstrap / precharge switches** | `Sa`, `Sb`, `Scn`, `Scp`, `Sd`, `Se`, `Cmswn`, `Cmswp`, `Cboot` | second-order: these settle to a rail during a phase, and their mismatch perturbs a *settled* node rather than the sampled charge | plain `mos_array` 1×1 singles, no matching structure (§4) |

## 2. `Msw_p` / `Msw_n`: identical geometry, no common-centroid interleave — and why

Both input switches are drawn from the **same generator call with the same
parameters** (`mos_array`, nfet, W=2 µm, L=0.15 µm, 1 finger, `dummy: 0`,
`gate_contact: true`), placed at the same y on the same row, adjacent to each
other in x. They are geometrically identical cells, so every *systematic*
per-device effect that depends on drawn geometry — gate length, diffusion
width, contact count, LOD/stress from the device's own diffusion edges — is
identical between them by construction rather than by inspection.

What this layout deliberately does **not** do is interleave them in a
common-centroid cross-quad (`klt gen diff_pair`, which is exactly that
generator, and which the prior Builder investigation on issue #99 recommended
for this pair). That is a real, deliberate deferral, not an oversight, and the
reason is a floorplan fact rather than a disagreement about matching:

* `diff_pair` draws its two legs (`Q1`/`Q2`) **vertically stacked at the same
  local x** — one leg's D/G/S ports sit directly above the other's.
* This block's routing scheme (see `bin/build_layout.py`'s docstring) gives
  every net exactly **one** met2 track and reaches it with one met1 column per
  pin. Two different nets whose pins share an x column cannot both have a
  column there; `build_layout.py` raises `BuildError` on exactly that
  collision. Working around it needs per-pin x offsets, which cascade into
  collisions with *other* devices' columns.

So the honest statement of what this layout claims and does not claim:

* **Claimed, and checked at build time:** the two input switches have
  identical drawn geometry, sit on the same row at the same y, and their D/G/S
  columns differ only by the block pitch. `bin/build_layout.py`'s
  `_assert_column_pitch` guarantees no column is shared or crowded.
* **Not claimed:** cancellation of a *linear process gradient* across the
  input pair. That is what a common-centroid interleave buys and this
  placement does not. The pair sits ~2.3 µm apart, so the residual is a
  gradient term over that distance, not a random-mismatch term (random
  mismatch is set by WL, which is identical either way).
* **Follow-up, not silently dropped:** a common-centroid treatment for
  `Msw_p`/`Msw_n` needs either a floorplan with a per-pin routing channel
  instead of one shared track per net, or a `diff_pair` variant whose legs are
  side by side. The second is a generator gap and is filed generically
  upstream (see "Friction-protocol filings" below); the first is a re-floorplan
  of this whole sub-block, which is the right time to also revisit area, since
  this floorplan optimises for verifiability rather than area (§5).

## 3. `Csamp_p` / `Csamp_n` and `Cboot_p` / `Cboot_n`: one generator call per pair

Each differential capacitor pair is drawn from a **single `klt gen cap_array`
call with `num=2`**, not from two independent calls. `cap_array` emits `num`
units of identical drawn geometry at a fixed pitch, so the two sides of each
pair are matched by construction. This costs nothing — `cap_array` already
supports `num > 1` — and it is worth more here than for the switches, because
a sampling-capacitor mismatch is a *first-order* differential error.

Same limitation as §2, stated the same way: two units at a fixed pitch are
matched in geometry but not common-centroid, so a linear gradient across the
pair is not cancelled. `layout/cdac-array/` is this repo's worked example of
what real common-centroid capacitor matching costs and how it is measured; the
sampling caps here are a two-element pair, not a weighted array, so the
centroid machinery that array needs would be disproportionate.

## 4. No dummies anywhere, deliberately

`dummy: 0` on every `mos_array` call, and no dummy capacitor units.

Dummies buy edge-environment uniformity: the outermost real device in an array
otherwise sees a different diffusion/poly neighbourhood than the interior ones.
That argument applies to an **array of nominally identical devices**, which is
what `layout/cdac-array/` is. It does not apply here: this sub-block is
eighteen functionally distinct switches spanning six different W/L
combinations, plus a two-device clock inverter, laid out as singles. There is
no "interior" for an edge device to differ from. Adding dummies would consume area and invite a matching
claim this flow has no evidence for.

The one place the argument would apply — the `Msw_p`/`Msw_n` pair — is covered
by §2: both are single-finger devices with the same neighbours on the row, and
the open follow-up there is common-centroid placement, which is a stronger
remedy than edge dummies.

## 5. What this floorplan is *not*

Inherited verbatim from `layout/sampling-frontend-wells/README.md`'s own
"Layout choices that are not claims", because they hold here too:

* **No area claim.** Three rows side by side on one baseline with generous
  channels and one shared met2 track band above everything, chosen so the
  routing is trivially verifiable rather than compact. The composed cell is
  ~196 × 60 µm, most of it air.
* **No parasitic claim.** `BOOST_P`/`BOOST_N` are high-impedance boosted nodes
  whose parasitic loading matters to `sim/sampling-frontend/`'s own settling
  result, and the well-junction capacitance the three n-well islands add sits
  directly on them. Quantifying that is a `klt pex` question on this layout,
  the way `layout/comparator/pex/` settled the comparator's analogue, and is
  logged as an open item in
  `spec/decision-records/DR-007-sampling-frontend-nwell-domains.md`. It is not
  answered here.

---

# The n-well body-tie domains (DR-004 / DR-007)

The nine PFETs do **not** share one VDD-tied n-well. `Sa_p`/`Se_p` tie their
body to `BOOST_P` and `Sa_n`/`Se_n` to `BOOST_N` — nodes that rise *above* VDD
during sampling — while the other five tie to VDD normally. A VDD-tied body on
`Sa`/`Se` forward-biases their drain/body junction once BOOST exceeds VDD by a
diode drop.

This flow reuses issue #122's proven recipe unchanged: `bin/gen_blocks.py`'s
`PFET_DEVICES` table carries a `domain` per device and is the single source of
truth; `bin/build_layout.py` reads it for both the well partition and the tap
net; `bin/render-record.py` re-derives the *expected* body net from it when
asserting the extracted result. The four-part recipe and the reasoning behind
each part live in `layout/sampling-frontend-wells/bin/build_layout.py`'s "THE
RECIPE" docstring and that directory's `README.md`; they are not restated here,
so the two cannot drift.

What this sub-block adds beyond that PFET-only study: a fourth tap — a
p-substrate tie in the NFET row's own margin, routed to GND. Read
`bin/build_layout.py`'s docstring for what it does and does not do; the short
version is that it merges the drawn `GND` conductor into the deck's
globally-synthesized `vsubs` net (without which LVS cannot match at all), and
that it does **not** make any NFET body a schematic-named net (no drawn
geometry can, on this deck — `klt lvs` reports `device.body_unverified` for all
eleven NFETs, expected).

---

# The MiM top-plate trap (and why this needs klt 0.4.0)

Worth recording, because it is invisible in a DRC report and it is exactly the
kind of thing this canary exists to find.

`klt extract`'s sky130 deck connects a MiM cap's top plate (`capm`) up through
`via3` onto `met4`. It also *excludes* the top-plate via from the deck's
generic met3↔met4 connectivity, so the DRM-required overlap between that via
and the bottom plate underneath it is not read as a short between the two
plates. On the **klt 0.3.0** pin that exclusion was scoped to the capacitor's
`bottom_plate` **layer in full** — every met3 shape drawn anywhere in the
layout. Because a legal `via3` is enclosed by met3 by construction, the
consequence was that *every* via3 in a layout containing any `capm` was
dropped from generic connectivity: a MiM top plate could not be routed down to
met2/met1 at all.

The symptom was not an error. DRC was clean, all 24 devices extracted, every
transistor terminal landed on the right net — and all four capacitor top plates
came back as isolated, anonymous, single-terminal nets. The only thing in the
0.3.0 envelope that pointed at it was `single_terminal_nets[]`, which is why
verdict 6 above exists as a first-class verdict rather than a footnote, and why
`reference.broken-topology.spice` corrupts precisely a capacitor top-plate net.

klt 0.4.0 narrows the exclusion to met3 that actually touches a `capm` plate,
which fixes it; `layout/requirements.txt` records the bump and the measurement
(same GDS: 0.3.0 → 21 nets with four single-terminal plates, 0.4.0 → 17 nets
with none). No upstream issue was filed for this one: it was already fixed
upstream before this sub-block hit it.

## Why there is no hand-written DRC deck here

`layout/sampling-frontend-wells/drc/nwell_isolation.drc` exists because klt
0.3.0's curated sky130 deck carried **no rules on the n-well layer at all**, so
a deliberately-split well passed DRC vacuously on the rules governing the
split. That directory's own README said what to do when the gap closed
upstream: *"retire `drc/nwell_isolation.drc` rather than maintaining a
transcription in parallel."* klt 0.4.0 closed it (`nwell.width.1`,
`nwell.space.1` — klayout-tools#1420), so this flow does not carry a copy. Two
concrete reasons beyond "the gap closed":

1. **That deck's stated approximation is invalid for this cell.** Its header
   documents dropping `difftap.10`'s `and(nsdm)` implant scope on the grounds
   that *"every `tap` shape in this layout is an n+ well tie inside an n-well by
   construction"*. True of a PFET-only cell; false here — this sub-block draws a
   p-substrate tap **outside** every n-well, which that widened rule would flag
   as a violation it is not.
2. **It cannot be run in this environment anyway.** It requires
   `klt drc --engine klayout`, which shells out to a `klayout` binary; the one
   installed here never returns (even `klayout -v` hangs indefinitely at 0% CPU).
   That is an environment problem, not a klt one, but it means a flow depending
   on it is not reproducible here.

## What this flow does not check

Stated plainly, and recorded *from `klt drc`'s own `coverage` block* in every
record rather than asserted only in prose:

* **`difftap.8` / `difftap.10`** — an n-well's minimum enclosure of the p+ diff
  and the n+ tap inside it. klt 0.4.0 deliberately does not transcribe these:
  sky130 scopes them by the `psdm`/`nsdm` implant markers, which no `klt gen`
  generator draws, so any plain-layer stand-in would either pass vacuously or
  produce false positives. `65/44` (tap) accordingly shows up in each record's
  `layers_in_stream_without_rules`. The identical Row-1 well/tap/device
  geometry *was* checked against both rules in issue #122's own record, on the
  hand-written deck, before that deck became unusable here.
* **Implant, density and antenna rules** — no generator in this flow draws
  implant layers, and neither deck models density or antenna effects.
* **Anything electrical.** DRC and LVS say the drawn geometry is legal and is
  the schematic. They say nothing about settling, charge injection, or the
  parasitic loading on the boosted nodes (§5).

---

# Friction-protocol filings

Per `CLAUDE.md`, every place `klt` was awkward, missing, or wrong for this
layout is filed **generically** at `2AMLogic/klayout-tools` — tool gap only, no
spec values, no topology, since that tracker is public and this repo is not.

Filed by this sub-block:

- [klayout-tools#1494](https://github.com/2AMLogic/klayout-tools/issues/1494) —
  `klt gen cap_array`'s per-unit top-plate port sits at the unit's centre, on
  top-plate metal, directly over the bottom plate that spans the unit's whole
  footprint — so a caller cannot land a via stack anywhere inside the cell
  without shorting the plates, and must first ride the top-plate metal out past
  the cell's own bbox. A generator-side escape/landing structure outside the
  plate footprint would remove that hand-composition step (see
  `bin/build_layout.py`'s `_step_down_to_met1` `L_MET4` branch for the
  work-around this flow carries).
- [klayout-tools#1495](https://github.com/2AMLogic/klayout-tools/issues/1495) —
  `klt gen diff_pair` places its two legs vertically stacked at one local x,
  which makes it unusable for a floorplan whose routing gives each net a single
  horizontal track (§2). A side-by-side leg arrangement, or a documented port
  x-offset, would make the matched-pair generator usable in that very common
  floorplan.

Already filed and already fixed upstream, inherited rather than re-filed:
klayout-tools#1420 (the curated deck's missing well rules — closed by the
rules klt 0.4.0 now carries) and the MiM top-plate-via exclusion scoping
described above.

---

# Files

```
layout/sampling-frontend/
  README.md                           # this file, incl. the matching strategy
  reference.spice                     # LVS reference (schematic-correct target)
  reference.broken-body-tie.spice     # negative control: the four boosted bodies -> VDD
  reference.broken-device.spice       # negative control: one W changed
  reference.broken-topology.spice     # negative control: cap top plates moved off TOP_x
  drc/
    nwell_rules_fixture.json          # deliberately-illegal n-well fixture (curated-deck control)
  bin/
    gen_blocks.py                     # the 22 klt gen calls + the device/domain tables (source of truth)
    build_layout.py                   # floorplan, well partition, taps, routing
    run-flow.sh                       # gen -> per-block drc -> draw -> compose -> drc x2 -> precheck -> extract -> lvs x4 -> record
    render-record.py                  # renders record.md, asserts the eleven verdicts
  reports/
    LATEST                            # record-id of the most recent run
    <record-id>/                      # append-only, one directory per run:
                                      #   <block>.gds/.json           the 22 klt gen blocks
                                      #   drc.blocks.json             per-block DRC
                                      #   draw.request.json           wells, taps and every wire, as klt draw input
                                      #   layout.summary.json         the floorplan + well partition, measured
                                      #   draw.json, route.gds        the drawn well/routing cell
                                      #   compose.request.json, compose.json
                                      #   sampling_frontend.gds       THE DELIVERABLE
                                      #   drc.json                    curated deck, composed layout
                                      #   nwell_rules_fixture.gds, drc.fixture.json
                                      #   precheck.json
                                      #   extract.json, sampling_frontend.extract.spice
                                      #   lvs.json + the three negative-control envelopes
                                      #   report.md, record.md
```

# Records are append-only

Same rule as `sim/`, `layout/trivial-cell/`, `layout/comparator/` and
`layout/sampling-frontend-wells/`: a re-run mints a new `<record-id>`
(`<YYYYMMDD>-<HHMMSS>-<short-git-sha>`, UTC) and never edits an existing report
directory. `record.md` stamps the `klt` version, the KLayout engine version,
the resolved PDK variant + open_pdks commit, the DRC deck's content hash, and
the repo commit with its dirty flag.

Like every other layout record in this repo, a record is minted from a **dirty**
working tree by construction — the flow writes its own report files into the
repo before `record.md` is rendered. The record says so rather than hiding it.

# Provenance

Pattern (per-block `klt gen`, `klt draw` for everything the generators do not
draw, `klt gen-compose` as a placer only, timestamped append-only reports,
positive + negative verdicts asserted from JSON envelopes rather than exit
codes) follows `layout/README.md`'s, `layout/comparator/`'s and
`layout/sampling-frontend-wells/`'s own conventions. Device sizing, topology
and the body-tie domains are re-derived from `design/sampling_frontend.sch` /
`sim/sampling-frontend/testbench/sampling_frontend_dut.spice` and from DR-004's
stated requirement — not copied from a sibling sub-block or any external
implementation. Clean-room, per `CLAUDE.md`.

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

**Not yet closed, and now known to be blocked on a real, verified dependency
rather than an open question.** This PR ships the fifth block this assembly
needs (`layout/seln-inverters/`, DRC-clean and LVS-clean on its own) and the
floorplan/routing investigation below. The investigation went past "what
should the composition request look like" into actually probing every
sub-block's own committed GDS geometry (direct KLayout API inspection, not
just the pin-position tables each block's own README already published), and
found that two of `cdac_array`'s pins (#100) have **no drawn conductor a
top-level assembly can physically contact** — not a floorplan/routing
question this issue can resolve, but a sub-block-layout completeness gap
filed as **#165** (`cdac_array: VDD (nwell) and SELp/SELn (poly gate) pins
have no externally-contactable landing geometry`). See "GND / VPWR / VGND"
and "Recommended composition mechanism" below for the verified detail; the
short version:

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

### `sampling_frontend` (top cell in `layout/sampling-frontend/reports/20260905-204934-f012255/sampling_frontend.gds`)

bbox: `(0.0, -2.4)` to `(195.56, 58.05)`. All pins on layer `69/5` (met2.pin)
except `GND`, which has **no drawn pin** — see "GND/substrate" below.

| Pin | x_um | y_um |
| --- | --- | --- |
| VDD | 1.76 | 50.90 |
| SAMPLE | 2.67 | 50.40 |
| BOOST_P | 0.70 | 52.40 |
| VINP | 10.10 | 53.40 |
| VCM | 13.30 | 51.90 |
| BPREF_P | 14.87 | 56.40 |
| VINN | 22.90 | 53.90 |
| BPREF_N | 21.27 | 56.90 |
| BOOST_N | 26.98 | 52.90 |
| TOP_P | 42.23 | 57.40 |
| TOP_N | 44.52 | 57.90 |

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

### `comparator` (top cell `gen_compose_0` in `layout/comparator/reports/20260825-135219-59f8e86/comparator.gds`)

bbox: `(0.0, 2.5)` to `(24.0, 38.65)`. All pins on layer `68/5` (met1.pin).

| Pin | x_um | y_um |
| --- | --- | --- |
| GND | 1.30 | 20.00 |
| VINN | 4.90 | 20.00 |
| VINP | 9.10 | 20.00 |
| OUTP | 10.10 | 18.50 |
| OUTN | 10.60 | 18.00 |
| VDD | 17.90 | 15.00 |
| CLK | 1.90 | 24.50 |

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

## Recommended composition mechanism: `klt gen-compose`, not hand-drawn routing

Every existing full-custom sub-block flow in this repo (`comparator/`,
`sampling-frontend/`, `sampling-frontend-wells/`) uses `klt gen-compose`
**purely as a placer** (`connectivity: []`) and hand-authors every wire via
`klt draw`, because those flows route matching-critical, transistor-level
nets where geometry control matters. Top-level block-to-block interconnect
is a different problem — five pre-verified, opaque blocks, not
matching-critical transistor placement — and `klt gen-compose`'s own
`routing`/`connectivity[]` mechanism (issue #1073's N-pin `route_bundle`:
a routed minimum spanning tree over a net's pins, each leg through
`route_two_pin`'s own via-drop/obstacle/collision handling) is designed for
exactly this case. Each block would be declared as a `blocks[].cell` entry
(an *existing* GDS cell, not a fresh `klt gen` report) with hand-declared
`ports[]` taken directly from the tables above.

**Not yet attempted end-to-end** (and now blocked on #165 for two of the
nets below). Open questions before that attempt:

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

## Remaining work (tracked against #103, not yet done)

- [ ] **Blocked on #165** (`cdac_array.VDD`/`SELp`/`SELn` have no
      externally-contactable landing geometry — see "Status" above). This is
      a real dependency, not an open design question: the composition/
      routing plan below is otherwise ready to execute, but `VDD` and the 18
      `SELp<i>`/`SELn<i>` nets cannot be physically routed until #165 lands.
- [ ] Once #165 lands: place all five blocks via `klt gen-compose`
      `placement.strategy: "explicit"` (per the resolved floorplan strategy
      in open question 3 above), each sourced as a `blocks[].cell` entry (an
      existing GDS cell `gen-compose` did not itself generate, #1189) rather
      than a `generator_report` — none of these five blocks came from `klt
      gen`/`klt draw` in this issue's own flow.
- [ ] Hand-route (`klt draw`, not `gen-compose`'s own bundle router — see
      open question 4) the interconnect table above, using #165's new
      landing pads for `VDD`/`SELp`/`SELn` once they exist. Reuse
      `layout/comparator/bin/build_layout.py`'s `Router`/`Pin`/track-based
      channel-routing pattern (already proven DRC-clean in this repo) rather
      than re-deriving one from scratch.
- [ ] Produce and commit the composed top-level GDS under this directory,
      following the `layout/trivial-cell/` record convention
      (`reports/<timestamp>-<sha>/` with `draw.json`/`compose.json`,
      `drc.json`, `extract.json`, `lvs.json`, `record.md`).
- [ ] Build the top-level LVS reference: a hierarchical SPICE netlist calling
      each sub-block's own already-generated flat reference subckt
      (`layout/cdac-array/reference/cdac_array.lvs-reference.spice`,
      `layout/comparator/reference.spice`,
      `layout/sar-sequencer/reports/<LATEST>/sar_sequencer.lvs-reference.spice`,
      `layout/sampling-frontend/reference.spice`,
      `layout/seln-inverters/reference/seln_inverters.lvs-reference.spice`)
      plus the top-level interconnect, run through `klt lvs` with
      `options.flatten_reference: true` (`klt lvs`'s own structural
      flatten, issue #1085) so hierarchy-local net scoping — the exact
      VPWR/VGND-domain-separation behavior described above — is preserved
      automatically rather than hand-derived.
- [ ] `klt drc`/`klt lvs` clean at the top level; record which of #103's own
      acceptance-criteria items (T1 items 3/4/7) that unblocks, and confirm
      whether `klt pex` (now implemented, unlike the tooling gap #103's own
      body anticipated) is usable for item 7's post-layout verification.

## Provenance

Clean room: this document only records geometry already drawn by this
repo's own sub-block flows (#99–#102) and this issue's own new
`layout/seln-inverters/` macro — no third-party layout, floorplan, or netlist
was consulted.

# layout/comparator/ -- dynamic comparator physical layout (issue #101)

Physical layout for the dynamic (StrongARM-class) comparator sub-block,
drawn against `design/comparator.sch`/`.sym` (issue #54) -- see that file's
header for the topology and `sim/comparator-decision/testbench/
comparator_core.spice` for the xschem-derived device list this layout's
connectivity is checked against. Follows `layout/README.md`'s (and
`layout/trivial-cell/`'s / `layout/sar-sequencer/`'s) record convention.

**Status: partial.** DRC is not yet clean and LVS is not yet clean -- see
"Composition status" below for the honest, specific writeup. What *is*
complete: a deliberate, documented matching strategy for the input
differential pair (the acceptance-criteria-critical sub-circuit for
input-referred offset, tracked by #29), and five independently DRC-clean
matched-device blocks with correct, schematic-derived connectivity intent
that a fixed/future `klt gen-compose` build should be able to route and
verify without any change to this design's own files.

## Which `klt` flow, and why

`klt gen` (the headless PCell generator harness) for each matched device/
pair, composed via `klt gen-compose` -- **not** `klt draw` (raw shapes, no
device recognition) and **not** `klt place-and-route` (digital standard-cell
flow; this is full-custom analog with a real matching judgement call, the
opposite of `layout/sar-sequencer/`'s "no analog matching/symmetry judgement
call" case). `klt gen`'s `diff_pair`/`mos_array` generators are exactly the
family-1/family-4 "matched analog primitive" generators built for this kind
of block (`klt gen --list`'s own descriptions).

## Matching strategy (the judgement call this issue's acceptance criteria calls out)

`design/comparator.sch` has four matched device pairs plus one unmatched
single device (the tail switch). Effort is *not* spread evenly across them
-- it is concentrated on the one pair the issue's acceptance criteria and
#29 actually track:

- **Input pair, M_INN/M_INP (`inpair` block) -- the matching-critical net.**
  `klt gen diff_pair --params '{"w_um": 2, "l_um": 0.5, "splits": 2,
  "flavor": "nfet", ...}'`: a true common-centroid cross-quad ("A B / B A")
  interleave of two W=2um legs per device, combining to the schematic's
  W=4um per device (`M_INN`/`M_INP`'s own `sim/comparator-decision/
  testbench/comparator_core.spice` sizing). This directly targets
  *gradient-induced* threshold/current mismatch -- a linear process
  gradient across the pair cancels to first order under common-centroid
  interleaving, which a plain side-by-side placement does not achieve. This
  is the one deliberate layout decision this record substantiates
  regardless of the composition's own current routing status (see below):
  the two legs' correct W/L and interleaved placement are drawn and
  DRC-clean today, independent of whether the rest of the design is fully
  wired up yet.
- **Cross-coupled latch pairs (M_LATN_P/N, M_LATP_P/N) and the reset pair
  (M_RST_P/N).** Symmetric by schematic role (each pair is interchangeable
  under the OUTP<->OUTN swap) but not the static input-offset net #29
  tracks -- these affect regeneration symmetry/speed, a second-order offset
  contributor, not the primary one. `klt gen diff_pair --params '{...,
  "splits": 1, ...}'`: plain A/B placement, adjacent, identical orientation,
  single-instance per device at its full schematic width. Proportionate
  effort: real, deliberate symmetry without spending the interleaved-leg
  complexity budget where the issue's own acceptance criteria doesn't ask
  for it.
- **Tail switch, M_TAIL (`tail` block).** A single device, no matching
  partner -- `klt gen mos_array` 1x1, reusing the same validated
  unit-device primitive (contact/landing-pad geometry) every other block
  already uses, rather than a bespoke single-device draw.

`layout/comparator/bin/gen_blocks.py`'s own module docstring carries this
same writeup next to the actual generator params, so the rationale and the
code it explains never drift apart.

**No guard ring on any block** (`add_guard_ring: false`): composing a closed
guard/collector ring per block turned out to block `klt gen-compose` from
reaching almost any of that block's *other* ports -- every port not on the
ring itself sits inside a closed metal loop that a route cannot legally
cross without shorting to the ring's own tap net (`klt gen-compose` reports
this explicitly: `"block '...' has a closed guard/collector ring ... route
to the ring's own tap port instead, regenerate ... with a routing opening,
or ... add_guard_ring: false"`). Dropping the ring means every device's body
terminal extracts to the deck-synthesized `vsubs`/per-block-well proxy net
documented in `layout/trivial-cell/README.md`'s "device.body_unverified"
paragraph -- the same accepted, documented limitation the trivial-cell
proof already carries for `mos_array` with no ring, not a new one introduced
here. `reference.spice`'s own header explains why the reference still
declares the *intended* GND/VDD body ties rather than hand-matching this.

## Composition status

`klt gen-compose` (pinned `klayout-tools==0.3.0` -- bumped from 0.2.0 for
this issue; see `layout/requirements.txt`'s own header for why: 0.2.0 has no
bundle/>2-pin net routing at all, which every rail in this design needs)
places all five blocks and **partially** routes the connectivity: some nets
route fully (`CLK`, `VINN`), most route only some of their legs
(`GND`/`TAIL`/`VDD`/`OUTP`), and two do not route at all (`VINP`/`OUTN`).
Concretely, on the record referenced by `reports/LATEST`:

- **DRC: not clean** -- 10 violations (`li1.space.1`/`met1.space.1`), all
  traced to metal `klt gen-compose` itself drew for a leg it reported
  `routed: true`, not to any of the five input blocks (each is independently
  DRC-clean in isolation -- verified by running `klt drc` directly on each
  block's own `<id>.gds` before composition).
- **LVS: mismatch** -- expected, not a surprise, given the above: an
  unrouted net is a real open circuit in the drawn geometry, so `klt lvs`
  correctly reports mismatches rather than a false "clean" verdict.

This is a genuine, current `klt gen-compose` capability gap, not a design
error in this sub-block's own connectivity list (`build_compose_request.py`
encodes the schematic's real device-by-device net list, cross-checked
pin-for-pin against `comparator_core.spice`): routing a net shared by more
than two same-facing (all-drain, or all-drain+gate) block ports in a single
row, and routing more than one same-block self-net per block, are both
outside what the pinned build's router can currently do. Filed generically
(no design content) at
[2AMLogic/klayout-tools#1386](https://github.com/2AMLogic/klayout-tools/issues/1386)
per `CLAUDE.md`'s friction protocol.

Follow-up to close this sub-block out to full DRC/LVS-clean is tracked by
issue #107 (filed alongside this record) -- either once #1386 lands, or via
a floorplan/explicit-waypoint workaround that doesn't require it.

## Running the flow

```sh
layout/bin/setup-venv.sh --force        # klayout-tools bumped to 0.3.0, see requirements.txt
source sim/env.sh                        # exports PDK_ROOT/PDK
layout/comparator/bin/run-flow.sh        # ~1 minute
cat layout/comparator/reports/$(cat layout/comparator/reports/LATEST)/record.md
```

Each run mints a new timestamped, append-only record under
`reports/<record-id>/` (same convention as `layout/trivial-cell/reports/`
and `layout/sar-sequencer/reports/`): the five generated blocks (gds+json),
the composition request/response, the composed GDS, `klt drc`/`extract`/
`lvs` JSON envelopes, the reference netlist used, and a human-readable
`record.md`. `reports/LATEST` points at the newest record id.

## Files

```
layout/comparator/
  reference.spice                   # hand-authored LVS reference (schematic-correct target)
  bin/
    gen_blocks.py                   # the five klt gen invocations + matching-strategy rationale
    build_compose_request.py        # gen-compose request: placement + full net-by-net connectivity
    run-flow.sh                     # orchestrates gen -> compose -> drc -> extract -> lvs -> record
    render-record.py                # renders record.md from the run's own JSON envelopes
  reports/
    LATEST
    <record-id>/                    # append-only: block gds/json, compose/drc/extract/lvs json,
                                     # the composed GDS, reference.spice, record.md
```

## Provenance

Pattern (per-block `klt gen` + `klt gen-compose`, timestamped append-only
reports, honest partial-status record) follows `layout/README.md`'s and
`layout/sar-sequencer/README.md`'s own conventions; device sizing and
topology are re-derived from `design/comparator.sch`/
`comparator_core.spice`, not copied from either sibling or any external
implementation -- clean-room, per `CLAUDE.md`.

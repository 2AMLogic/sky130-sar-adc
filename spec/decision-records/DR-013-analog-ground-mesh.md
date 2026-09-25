# DR-013: Every analog sub-block draws its own ground terminal, and the top level joins them in metal — a trunk-and-dropper mesh, not a star and not the substrate

- **Status**: proposed — like DR-008, DR-009, DR-010 and DR-012 this record
  settles an integration-level wiring question (`layout/sar-adc-top/`'s
  top-level routing, and two sub-block layouts' pin lists), not a numeric row
  of `spec/target-spec.md`. It inherits the same provisional status as every
  record still resting on DR-003's DRAFT numeric inputs.
- **Date**: 2026-09-24
- **Decided by**: Builder agent, issue #377
- **Supersedes**: none
- **Superseded by**: (none while this record stands)
- **Related**: #377 (this decision and its implementation), #362 / DR-012 (the
  pad this mesh feeds, and the record whose "Open items" named this one),
  #355 / DR-010 (the same structural gap in the digital domain), #378 (the
  sibling open item: nothing here is measured),
  `layout/sampling-frontend/reports/20260924-232823-66dca3c/`,
  `layout/cdac-array/reports/20260924-233346-66dca3c/`,
  `layout/sar-adc-top/reports/20260924-234053-66dca3c/`,
  `layout/sar-adc-top/erc-reports/20260924-234116-66dca3c/` (including its
  `ground-mesh-ablation.json`).

## Context

DR-012 gave this block a drawn top-level analog `GND` pad and stated, in its
own "Open items", what it had not done:

> **Two of the four analog blocks still draw no ground conductor.**
> `sampling_frontend` and `cdac_array` reach this pad only through the
> substrate. […] It is the largest remaining gap in this block's ground plan
> and is **not** closed by this record.

This record closes it. The facts it rests on, each against a named artefact:

- **Two sub-blocks drew no ground conductor at all.**
  `layout/sampling-frontend/` drew a p-substrate tap and a `GND` met2 track
  but deliberately did not *label* them (its `PIN_NETS` comment gave the
  reason: "nothing at a higher level of hierarchy will ever connect to it by
  name" — a statement #362 falsified). `layout/cdac-array/` drew no ground
  geometry whatsoever: its fourth schematic port `VSS` resolved to the sky130
  deck's synthesized global substrate net, and both `klt extract` and
  `klt lvs` were satisfied by that.
- **The tools cannot see the difference, and said so.** The composed
  extraction reported one `GND|VGND` net of 692 devices with the mesh absent
  (`layout/sar-adc-top/reports/20260924-214710-b323061/extract.json`) and
  reports the same 692-device net, now `GND|VGND|VSS`, with it present
  (`…/20260924-234053-66dca3c/extract.json`). `klt erc` read `GND` as one
  island both times. `klt drc` grades spacing, not connectivity. **No
  ordinary verdict in this repo moves when this mesh is added or removed** —
  which is why one had to be constructed that does.
- **An ablation was constructed, and it moves.**
  `layout/sar-adc-top/bin/probe-ground-mesh.py` rebuilds the assembly twice
  from the record's own committed sub-block GDS — as shipped, and with
  `build_layout.py --ablate-ground-mesh`, which draws DR-012's pad exactly as
  #362 shipped it and omits only this record's mesh — and grades both against
  the byte-identical ERC supply spec. Full: `erc_status: clean`, `GND` one
  island. Ablated: `erc.unconnected_net` — *"declared net 'GND' resolves to 2
  disconnected electrical islands"*, naming `sampling_frontend`'s ground and
  the comparator-plus-pad island. `VDD`/`VPWR`/`VGND` are unmoved as controls,
  and the full variant's recomposed GDS is byte-identical (sha256) to the
  record's own, so the two runs differ by the mesh and nothing else.

Not verified, and explicitly not claimed below: **no simulation in this repo
measures ground-return impedance, substrate coupling, or the difference this
mesh makes to either.** Everything in "Decision" is a design-time argument
from this design's own topology and from device physics; CLAUDE.md's "no claim
without a testbench" rule applies to it, and DR-012's second open item (#378)
is still open.

## Decision

**Every analog sub-block in this composition draws its own ground terminal,
and the top level joins those terminals in drawn metal.** Concretely, and in
force for `layout/` from this record forward:

1. **`layout/sampling-frontend/` promotes `GND` to a drawn pin.** One entry in
   `PIN_NETS`; the met2 track, its columns and the p-substrate tap under them
   are unchanged. The label lands at that net's own leftmost contributing
   column, local `(39.97, 52.32)`, by that generator's existing convention.
2. **`layout/cdac-array/` draws a real p-substrate tap and labels it `VSS`** —
   its own schematic port name — at local `(1.00, −31.60)`, on bare substrate
   directly below the `VDD` n-well tap #165 added, using the same tap
   geometry. Its LVS reference stops renaming `VSS` to `vsubs`, because the
   condition that rename was justified by ("a block with no substrate tap of
   its own") no longer holds for that top.
3. **The mesh is a trunk with droppers, not a star and not a ring.** One met3
   trunk at `y = 165.0` — in the open channel between `sampling_frontend`'s
   top edge and `comparator`'s bottom edge — with one met4 dropper onto each
   of the three terminals. The trunk is met3 and the droppers met4 because
   four of `sampling_frontend`'s own pins cross that channel northbound on
   met4; a met4 trunk would short every one of them.
4. **The pad DR-012 placed does not move.** The mesh is added 5 µm below the
   pad label, so `GND`'s top-level terminal is at the same coordinate DR-012
   recorded, and the label still sits on a plain met4 stretch. The mesh is
   not in series with the pad.
5. **This is a return-path decision, not an isolation one.** The mesh does
   not — and cannot, in bulk sky130 — separate the analog ground from the
   p-substrate or from `VGND`. DR-012 already decided what the node *is*;
   this record decides only that the current between these three blocks has
   a drawn metal path, graded by `klt drc`, in parallel with the substrate
   it always had.
6. **The mesh carries a standing geometric assertion, and an ablation.**
   `_check_analog_ground_mesh()` checks every met3/met4 shape the mesh draws
   against every met3/met4 shape the rest of that module draws — *touching is
   an explicit failure*, because a mesh shape that touches another net's shape
   has merged `GND` with it — plus the channel and block-footprint
   constraints. `bin/probe-ground-mesh.py` is re-runnable and exits non-zero
   if the ablation ever stops splitting.
7. **This record sets no numbers** and changes no row of
   `spec/target-spec.md`.

### Why metal, when the substrate already connects them

The substrate tie is real, so the mesh is not what makes these three blocks
one node. What it changes is the path, and the argument is DR-012's own, one
level down:

- **A return path with no stated impedance is not a design.** Nothing in this
  repo describes the p-substrate's sheet resistance, and the distance between
  `cdac_array`'s switch row and `comparator`'s tap is ~200 µm of it. A drawn
  met3/met4 path replaces the uncontrolled part of that path with conductor
  this repo draws, `klt drc` grades and a future extraction can be asked about.
- **The comparator is what pays for the difference.** `design/comparator.sch`
  is a StrongARM-class latch: during regeneration its own ground *is* the
  reference its differential pair's imbalance is resolved against. Every
  bottom-plate switch in `cdac_array` dumps its charge into the substrate at
  the same instant. Whatever fraction of that current returns through
  substrate under the comparator appears at the decision instant as offset.
- **It is the asymmetry that is indefensible, again.** `VDD` is routed between
  all three analog blocks in metal. A design that routes its analog supply in
  metal and its analog return through the wafer has not made a ground plan.

## Alternatives considered

- **Leave it: the substrate already connects them (the null option).**
  Rejected, per the three points above. The cost of *choosing* the mesh is
  ~390 µm of drawn met3/met4 (of which ~24 µm was already there as DR-012's
  pad stub) plus one new tap in each of two sub-blocks; the cost of *not*
  choosing it is a return path with no stated impedance under the one device
  whose decision is referenced to it — and a block that can say nothing about
  its own ground plan that any tool in this flow checks.
- **A star: route each sub-block's ground separately to the `GND` pad.**
  Rejected as a distinction without a difference *on this floorplan*, and said
  plainly rather than dressed up as a cost: the star's meeting point would
  have to sit in the same inter-block channel the trunk occupies, and the two
  shapes then differ by a few microns of met3, not by a topology. What decides
  it is readability — a trunk is one named horizontal every leg tees into, the
  shape `digital_supply_rail()` already established one domain over — and the
  fact that DR-010 puts the real star point off-die, so an on-die star would
  claim a significance it does not have.
- **Route the mesh north with the other analog nets, on its own `analog_leg`
  jog row above `comparator`.** Rejected, and this is the closest call. It
  would group the ground mesh with every other analog-region net at
  `JOG_Y ≈ 224`, which is tidier and reuses the existing corridor discipline
  exactly. Two costs. It adds ~59 µm of met4 to *each* of the `cdac_array` and
  `sampling_frontend` legs (~120 µm in all), in series on the one net where
  series metal buys nothing, to reach a row with no other consumer for ground.
  And it does not actually reach the third member: DR-012 established that
  `comparator`'s `GND` column cannot run north at all (its own `CLK` column is
  0.6 µm away in x and `m4.2` needs 0.30 µm), so a northern trunk would still
  have to send a dropper back down past `GND_MESH_Y` to meet it — paying the
  extra length and keeping the southward run. The cost of not choosing it: the
  ground mesh is the one analog net whose horizontal does not live in the
  jog-row band, which a future reader has to notice. `GND_MESH_Y`'s own
  comment says why.
- **Tie the mesh to `VGND`'s met5 rail while we are here (one drawn ground).**
  Rejected, for exactly DR-012's reason, restated because a mesh makes the
  temptation stronger rather than weaker: the metal bridge is the part DR-010
  deliberately withheld, and it would carry the standard-cell bank's switching
  return current straight through the analog ground on its way back to the
  source. The cost of not choosing it is that the two domains must be tied at
  one point off-die, which DR-010 already requires of the board.
- **Give `cdac_array` several distributed substrate taps instead of one.**
  Deferred, not rejected on merit. One tap is what makes the port a drawn,
  reachable terminal — the gap this record closes; how many taps a 219 µm-wide
  switching array *should* have, and where, is a substrate-noise question this
  repo has no measurement for. Naming it here so it is a known deferral rather
  than an implied claim of sufficiency. See "Open items".
- **Deep-nwell isolation for the analog ground.** Rejected, as in DR-012 and
  for the same reasons; unchanged by this record.

## Spec lines affected

**No row of `spec/target-spec.md` changes**, and none is added. What this
record fixes is sub-block *interfaces* and top-level *routing*, which that
table does not enumerate:

- `layout/sampling-frontend/bin/build_layout.py`: `GND` joins `PIN_NETS`
  (9 → 10 promoted nets; the LVS pin count is unchanged at 12/12/12, because
  the deck's global already produced a pin there — what changed is that the
  pin is now a drawn label on this cell's own conductor).
- `layout/cdac-array/bin/cdac_layout.py`: a new `VSS` p-substrate tap and pin;
  `bin/generate-lvs-reference.py`: the `VSS` → `vsubs` rename is retired for
  `cdac_array` and kept for `cdac_unit_cell`.
- `layout/sar-adc-top/bin/build_layout.py`: two new `PIN` entries, one new
  `WEST_CORRIDOR_X` track, `analog_ground_mesh()` +
  `_check_analog_ground_mesh()` replacing `analog_ground_pad()` +
  `_check_analog_ground_pad()`, and the `--ablate-ground-mesh` measurement
  variant.
- **No schematic changes.** `design/sar_adc_top.sch` already ties
  `cdac_array`'s `VSS` port to `GND`, and `sampling_frontend`'s ground is
  `.GLOBAL`. The top-level interface stays at DR-012's 22 ports.
- DR-012 is **not** superseded or amended: this record closes one of its open
  items and inherits its framing of what the node is.

## Consequences

- **DRC stays clean and the LVS mismatch count does not move.**
  `layout/sar-adc-top/reports/20260924-234053-66dca3c/`: `klt drc` clean, 0
  violations across 52 rules; `klt lvs` **88 mismatches, the same 88**, in the
  same four categories (`device.unmatched` 66, `net.merged` 11, `net.split`
  10, `topology.flattened` 1), the same 803/869 devices and 411/443 nets, the
  same 21/22/22 pins. The independent minimum-area cross-check still reports
  **0** shapes below every threshold; the mesh appears there only as polygon
  counts (met1 1503 → 1504, met2 1518 → 1519, met3 1342 → 1345, met4 29 → 31).
- **The ERC verdict does not move either, and that is again the point.**
  `erc-reports/20260924-234116-66dca3c/`: `erc_status: clean`, 0 findings,
  against a byte-identical spec (`sha256:fd4f5a93…`). The verdict that *does*
  move is the ablation's, and it is committed beside it.
- **Two sub-block LVS runs got one finding better, narrowly.** Both
  `sampling_frontend` and `cdac_array` stop reporting
  `device.body_unverified`, because their substrate net now carries a drawn
  label and extracts under a real name instead of the deck's `vsubs`. **This
  does not mean the body ties are verified.** The deck still joins every NMOS
  body by `connect_global`, by construction, and a per-device body-tie check
  remains outside what it can grade. Each sub-block README says so at the
  point a reader would otherwise over-read the number.
- **Two already-closed sub-block layouts were re-opened, and their records
  re-minted on a newer tool pin.** Both flows were still standing on
  `klayout-tools==0.5.0`-era records while `layout/requirements.txt` had moved
  to 0.6.0; each was first re-run unchanged on the new pin (reproducing its
  superseded verdicts exactly) so the pin bump and this change could be told
  apart.
- **More metal in the analog region, and one more thing to route around.**
  The mesh occupies an exclusive met4 corridor track at `x = −16.0` and a met3
  row at `y = 165.0` that no other net may now cross on those layers. A future
  net that needs either fails in `_check_analog_ground_mesh()` rather than in
  `klt drc` — which is the intended trade, but it is a constraint the
  floorplan did not carry before.
- **Nothing in `sim/` is invalidated, and nothing in `sim/` supports this.**
  No netlist changed. The impedance argument in "Decision" remains unmeasured.

## Open items

- **The mesh's impedance is unmeasured**, exactly as DR-012's pad's is. The
  testbench that would settle both is the one #378 names: drive the assembled
  `sar_adc_top` through package-like R+L on each supply terminal, with a
  substrate-resistance model between the analog blocks, and compare code
  errors against the ideal-ground case. Until that exists, no number in this
  record may be quoted as measured — including the claim that the metal path
  carries a useful fraction of the return current.
- **One substrate tap per sub-block is a floor, not a design.**
  `cdac_array` is 219 µm wide and switches 1024 unit capacitors; one tap at
  its west edge is what makes its ground port a reachable terminal, not a
  substrate-noise plan. Distributed taps (and a guard ring around the switch
  row) are the obvious next question, and this record deliberately does not
  answer it.
- **The mesh's position is provisional, for the same reason the pad's is.**
  There is no pad ring in this composition; when one exists, both the pad's
  placement and whether the mesh should run in a supply corridor instead of
  the inter-block channel are real questions this record does not answer.
- **`erc.missing_tie` is still not computed** for this layout
  (klayout-tools#2169, disclosed in the ERC spec's own
  `ties_disclosure`), so the tie half of T1 item 11 remains ungraded — the
  mesh does not change that, and no reader should take a clean supply
  verdict as covering it.

# DR-012: The block presents a drawn analog `GND` pad — the p-substrate node's own front-side terminal, not a second node beside it

- **Status**: proposed — like DR-008, DR-009 and DR-010 this record settles an
  integration-level wiring question (`design/sar_adc_top.sch`'s top-level
  interface, and `layout/sar-adc-top/`'s top-level routing), not a numeric row
  of `spec/target-spec.md`. It inherits the same provisional status as every
  record still resting on DR-003's DRAFT numeric inputs.
- **Date**: 2026-09-24
- **Decided by**: Builder agent, issue #362
- **Supersedes**: none
- **Superseded by**: (none while this record stands)
- **Related**: #378 / [DR-015](DR-015-package-parasitic-assumption.md) and
  [`sim/supply-impedance-sensitivity/`](../../sim/supply-impedance-sensitivity/README.md)
  (the impedance-argument measurement this record's second open item asked
  for, and the package-parasitic assumption it rests on, since closed),
  #377 / [DR-013](DR-013-analog-ground-mesh.md) (the analog
  ground mesh this record's largest open item asked for, since closed),
  #362 (this decision and its implementation), #355 / DR-010 (the
  same structural gap one domain over, and the record whose "Open items" named
  this one), #344 (the `klt erc` supply-spec tooling), DR-001 (the ratified
  1.8 V core-flavour scope), `layout/sar-adc-top/README.md` ("GND / VPWR /
  VGND"), `layout/sar-adc-top/reports/20260924-214710-b323061/` (the DRC/LVS
  record), `layout/sar-adc-top/erc-reports/20260924-214731-b323061/` (the ERC
  record).

## Context

`VDD` has been a top-level port of `sar_adc_top` since the block was written.
Its return never was. `design/sar_adc_top.spice` declared `.GLOBAL GND` and
three of the four analog sub-blocks referenced that net, but nothing in the
block's own interface exposed a terminal a package could bond it to — and
`layout/sar-adc-top/bin/build_layout.py` drew no `GND` geometry at all. This is
the same structural gap issue #355 closed for the digital `VPWR`/`VGND` rails,
in the analog half, and DR-010's "Open items" named it rather than absorbing it.

**`klt erc` does not catch this shape, and its passing verdict must not be read
as though it did.** T1 checklist item 11 grades "does this declared supply
resolve to exactly one electrical island". `GND` always did — the comparator's
own drawn ground is one connected conductor — so it passed on
`erc-reports/20260924-190825-f3622fc/` while having no pin at all. "One island"
and "reaches a pad" are different claims, and a geometric connectivity model
makes only the first. That record said so in its own words; this record is what
removes the need for the caveat.

**Verified, not assumed** (each against a named artefact in this tree):

- **Only one sub-block draws an analog-ground conductor.** `comparator` has a
  real `GND` met1 pin at its own local (1.3, 20.0) — confirmed by a direct
  `klayout.db` shape dump of `layout/comparator/reports/LATEST/comparator.gds`,
  which finds met1 at that position, a via1 up to a met2 landing, and a
  `tap.drawing` (65/44) shape spanning local y 17.0–23.0 underneath it.
  `sampling_frontend` draws no ground pin; `cdac_array`'s fourth port is
  `VSS` in the schematic and appears as `vsubs` in its layout-side LVS
  reference, with no drawn pin either. Both reach the node only through the
  substrate synthesis in `klt extract`'s sky130 deck
  (`layout/sampling-frontend-wells/README.md`).
- **`GND` and `VGND` are already ONE extracted net.**
  `reports/20260924-214710-b323061/extract.json` reports a single net named
  `GND|VGND` carrying 692 devices, with `merged_net_labels` naming both labels
  on it. This is not a layout defect and not new: in bulk sky130 the analog
  ground, the standard cells' substrate ties and the p-substrate are one node,
  and DR-010 said as much ("separate grounds can only ever mean separate metal
  return paths, never galvanic isolation"). What is new is that this repo now
  has the measurement, not just the argument.
- **`klt erc` and `klt extract` disagree about that, correctly.** The same GDS
  reports `GND` and `VGND` as two independent single islands to `klt erc` and as
  one net to `klt extract`. Both are right about different things: the two share
  no *drawn conductor* (what a geometric model sees) and do share the
  *p-substrate* (what the extraction deck synthesises). Neither reading is the
  one to quote alone.
- **There is no third option available in this PDK.** Isolating the analog
  ground from the substrate would need a deep-nwell/triple-well structure.
  sky130 offers `dnwell`, but no sub-block in this repo draws one, every
  existing DRC/LVS/ERC record grades a bulk composition, and introducing one
  would re-open four already-closed sub-block layouts. That is a different
  decision with a different risk profile; it is named in "Alternatives
  considered" and not taken here.

Not verified, and explicitly not claimed below: **no simulation in this repo
measures ground-return impedance, substrate coupling, or bond-wire inductance.**
The reasoning in "Decision" is a design-time argument from this design's own
topology and from device physics; CLAUDE.md's "no claim without a testbench"
rule applies to it. See "Open items".

## Decision

**The block presents a drawn top-level `GND` pad.** Concretely, and in force for
`design/` and `layout/sar-adc-top/` alike:

1. `GND` becomes a **top-level port** of `sar_adc_top`, appended to the block's
   interface after `VGND`. The interface goes from 21 ports to **22**: `VINP
   VINN VDD VREFP VREFN VCM CLK RST_B DOUT9..DOUT0 BUSY VPWR VGND GND`.
2. **The pad is the substrate node's own front-side terminal, not a second
   node.** This record does *not* claim `GND` is electrically distinct from the
   p-substrate or from `VGND`; the extraction says plainly that it is not. What
   the pad buys is a **drawn, low-impedance, bondable** terminal on that node,
   where before the only path off-die would have been whatever a die-attach
   paddle happened to provide through the back of the wafer.
3. **Two ground pads on one node is the intended shape, not an inconsistency
   with DR-010.** DR-010 partitions *pads and metal return paths*, which is what
   a die-level decision can control, and explicitly disclaimed galvanic
   isolation. `GND` and `VGND` remain two distinct `.GLOBAL` nets in the
   schematic and two distinct drawn conductors in metal, bonded separately, so
   the digital return current travels off-die and back to the source through the
   package rather than through the die's own substrate resistance on its way
   past the comparator.
4. **The pad is built on `comparator`'s own drawn `GND` pin**, because it is the
   only analog-ground terminal any sub-block in this composition draws. This is
   a consequence of the sub-blocks as they exist, not a claim that one pin is
   the right ground plan; see "Open items". (That consequence has since been
   removed rather than argued away: [DR-013](DR-013-analog-ground-mesh.md)
   gave the other two analog sub-blocks their own drawn ground terminals and
   meshed all three. The pad still anchors on `comparator`'s pin, at the same
   coordinate.)
5. **The star point stays off-die**, as DR-010 already required. The block now
   presents four supply terminals as real drawn pads (`VDD`, `GND`, `VPWR`,
   `VGND`) instead of three, and an enclosing testbench or harness ties them at
   one point — exactly as `sim/full-conversion-transient/` already does with
   independent sources.
6. **This record sets no numbers** and changes no row of `spec/target-spec.md`.

### Why a pad, stated as reasoning and not as a measurement

The alternative — bonding ground through the substrate only — is not a
conservative default here, it is a specific and worse choice:

- **A bulk die's back side is not a specified conductor in this flow.** Nothing
  in `sim/pdk.json`'s pinned open_pdks install, in any `layout/` record, or in
  this repo's spec describes backside metal, wafer thinning, or a conductive
  die-attach. A "substrate-only" ground would be a return path whose impedance
  no artefact in this repo states, on the one node whose impedance the
  comparator's decision is referenced to.
- **Substrate is a resistor, and the comparator is what pays for it.**
  `design/comparator.sch` is a StrongARM-class latch: during regeneration its
  own ground *is* the reference its differential pair's imbalance is resolved
  against. Return current through 10s of ohms of p-substrate between the
  comparator's taps and a paddle contact appears at the decision instant as
  offset. A drawn metal pad replaces the uncontrolled part of that path with
  conductor this repo draws and `klt drc` grades.
- **It is the asymmetry that is indefensible.** `VDD` is a drawn pad; `VPWR` and
  `VGND` became drawn pads in #355. A design that bonds three of its four supply
  terminals in metal and the fourth through the wafer has not made a ground
  plan, it has left one out.

## Alternatives considered

- **Bond ground through the substrate only; draw no pad (the null option).**
  Rejected, per the three points above. The cost of *not* choosing it is one pad
  and ~24 µm of met4; the cost of choosing it is a return path with no stated
  impedance under the one device whose decision is referenced to it.
- **Draw the pad, but tie it to `VGND` in metal at the top level (one drawn
  ground).** Rejected, and it is the cheaper layout — the substrate already
  makes them one node, so the metal tie looks free. It is not: it adds the
  low-impedance metal bridge DR-010 deliberately withheld, which is the part
  that would carry the standard-cell bank's switching return current straight
  through the analog ground on its way back to the source. Merging them would
  also make DR-010 unmeasurable on silicon: the two domains could never be
  separated at the board, because the tie would be in metal. The cost of not
  choosing it is one extra pad.
- **Route the pad west, into the analog supply corridor beside `VDD`/`VREFP`/
  `VREFN`.** Rejected for now, and this is the weakest rejection in this record:
  it is a defensible layout and would group the analog pins together. It costs
  ~130 µm of met3 on a new exclusive jog row, crossing four met4 corridor
  columns, added in series with the one net where series metal buys nothing.
  Since this composition has **no pad ring at all** — every pin label in it sits
  wherever its own net's conductor already is — the grouping has no consumer
  yet. Revisit when a pad ring exists; the position is provisional in exactly
  the sense every other pin position here is.
- **Isolate the analog ground with a deep n-well, making `GND` a genuinely
  separate node from `VGND`.** Rejected as out of scope and not obviously
  correct. It would re-open four already-closed sub-block layouts, invalidate
  every committed DRC/LVS/ERC record, and buy isolation that is itself only
  partial (a dnwell tub is capacitively coupled to the substrate it floats in).
  The cost of not choosing it: the two grounds remain one DC node, which this
  record states rather than hides.
- **Declare `GND` out of the ERC supply spec, or relabel the gap as
  tool-limited.** Rejected on principle: tuning the spec until the layout passes
  is forbidden here (CLAUDE.md, "the spec is a gate"), and in any case the gap
  was never one `klt erc` claimed to grade. The tool reported honestly; the
  layout was what had to move.

## Spec lines affected

**No row of `spec/target-spec.md` changes**, and none is added. What this record
fixes is the block's **top-level interface**, which that table does not
enumerate:

- `design/sar_adc_top.sym` / `design/sar_adc_top.sch`: one new `dir=in` port,
  `GND`, appended after `VGND`; `design/sar_adc_top.spice` regenerated (its
  device cards are byte-identical — verified with `design/regen_netlist.sh
  --check` — since `sar_adc_top` netlists flat and the regeneration moves only
  the port-declaration comments).
- `layout/sar-adc-top/bin/generate-lvs-reference.py`: `GND` becomes the 22nd
  port of the generated `.SUBCKT sar_adc_top`, where it was previously an
  internal node of that wrapper.
- DR-001's ratified 1.8 V core-flavour scope is untouched. DR-010 is **not**
  superseded or amended: this record is the analog counterpart it named.

## Consequences

- **DRC stays clean, and the LVS mismatch count does not move.**
  `reports/20260924-214710-b323061/`: `klt drc` clean, 0 violations; `klt lvs`
  **88 mismatches, the same 88** as the pre-#362 record, in the same four
  categories (`device.unmatched` 66, `net.merged` 11, `net.split` 10,
  `topology.flattened` 1), with the same 803/869 devices and 411/443 nets
  matched. Minimum area is inside that clean verdict rather than beside it: the
  pinned 0.6.0 deck authors `met1.area.1` … `met5.area.1` (52 rules in this
  record's own `coverage.rules_checked`), and the independent cross-check
  (`docs/chipalooza/measure_metal_min_area.py`, re-run after issue #363
  corrected its property-aware-merge bug) agrees at **0** shapes below every one
  of `m1.6`/`m2.6`/`m3.6`/`m4.4a`/`m5.4` — the same **0** the pre-#362 GDS
  measures under the same corrected script. The pad this record adds appears
  there only as polygon counts (met3 1341 → 1342, met4 28 → 29), both above
  threshold, because the riser's isolated pads are sized from
  `MIN_METAL_AREA_UM2` for exactly that reason.
- **The LVS pin counts become asymmetric, on purpose: 21/22/22** (was 21/21/21).
  The reference side gains `GND` as a 22nd port; the layout side still promotes
  21 pins, because `GND` and `VGND` are one extracted net and one promoted pin
  answers both reference ports — which `matched=22` records. A reader who sees
  `layout < reference` here should not read it as a missing pin: it is this
  record's central physical fact showing up in the pin table.
  `bin/render-record.py` now renders that explanation whenever the two counts
  differ, rather than leaving a bare number.
- **The ERC verdict does not move, and that is the point.**
  `erc-reports/20260924-214731-b323061/`: `erc_status: clean`, 0 findings, all
  four supplies one island each, graded against a **byte-identical** spec
  (`sha256:fd4f5a93…`). `GND` read "1 island" before this change and reads
  "1 island" after it; what changed is that the island now reaches a drawn
  top-level pin. That the number could not move is the whole reason the caveat
  had to be retired by changing the layout.
- **One more pad.** `docs/chipalooza/challenge-4-proposal.md`'s §2.2 pad table
  carries it as a supply line (the same treatment `VDD`/`VPWR`/`VGND` already
  had). Anything downstream that assumed a 21-port interface now sees 22.
- **A board/package requirement is sharpened, not created.** DR-010 already
  required exactly one off-die star point between the domains. This record makes
  the analog side of that tie a real, bondable terminal instead of an implied
  one; getting it wrong (two ties, or none) remains a *system* failure mode this
  design depends on someone else avoiding.
- **Nothing in `sim/` is invalidated.** The regenerated netlist's device cards
  are byte-identical, and every existing testbench already drives `GND` as a
  global node.
- **`klt erc`'s "one island" wording should be read narrowly everywhere else it
  appears in this repo.** This issue existed for as long as it did because a
  passing supply row was taken to mean more than it says. The ERC record for
  this change states the distinction in its own "Why `GND`'s pass must be read
  narrowly" section, and the tool-side capability gap behind it is filed
  generically as **klayout-tools#2457** (`klt erc` has no rule for *"does this
  declared supply reach a top-level terminal"*) — so the next block does not
  have to rediscover it by hand.

## Open items

- ~~**Two of the four analog blocks still draw no ground conductor.**
  `sampling_frontend` and `cdac_array` reach this pad only through the
  substrate. Closing that means drawing a real ground pin on each and a
  top-level analog ground mesh between them — a change inside two already-closed
  sub-block layouts, with its own DRC/LVS re-verification. It is the largest
  remaining gap in this block's ground plan and is **not** closed by this
  record. Tracked as **#377**.~~ **CLOSED** by
  [DR-013](DR-013-analog-ground-mesh.md) (issue #377, 2026-09-24): both
  sub-blocks now draw a real ground terminal of their own
  (`sampling_frontend.GND` met2 pin, `cdac_array.VSS` met1 pin over a new
  p-substrate tap, each re-verified DRC-clean and LVS-no-worse in its own new
  record), and `layout/sar-adc-top/bin/build_layout.py`'s
  `analog_ground_mesh()` joins all three to this pad in drawn met3/met4. The
  pad's own coordinate is unchanged. Note what that record had to do to
  *prove* it, because this record's own central caution applies one level
  down: no ordinary verdict moves when the mesh is added, since the substrate
  joined those nets already — the evidence is an ERC ablation
  (`layout/sar-adc-top/bin/probe-ground-mesh.py`, summary in
  `erc-reports/20260924-234116-66dca3c/ground-mesh-ablation.json`) in which
  removing the mesh and nothing else splits `GND` into two islands.
- ~~**The impedance argument is unmeasured.** No `sim/` campaign in this repo
  models the ground return at all — no package parasitics, no substrate
  resistance, no bond-wire inductance. A testbench that would settle it: drive
  the assembled `sar_adc_top` through package-like R+L on each of the four
  supply terminals, run `sim/full-conversion-transient/`'s own stimulus, and
  compare code errors against the ideal-ground case. Until that exists, no
  number from this record may be quoted as measured. Tracked as **#378**.~~
  **CLOSED**, at the scope stated below, by
  [`sim/supply-impedance-sensitivity/`](../../sim/supply-impedance-sensitivity/README.md)
  (issue #378) and its first record,
  `sim/supply-impedance-sensitivity/records/20260925-073912-0e385e5.md`. That
  campaign runs `sim/full-conversion-transient/`'s own committed stimulus,
  unmodified, against the same committed `design/sar_adc_top.spice`, driving
  the four supply terminals through
  [DR-015](DR-015-package-parasitic-assumption.md)'s package-style R+L (a
  *stated assumption* derived from wire geometry, not a package selection or
  anyone else's data) instead of ideal sources. At the ratified baseline
  corner (`tt_27c_1.80v`), the as-built shape (`package`: all four terminals
  bonded through R = 102.2 mΩ + L = 1.914 nH) moves the captured code by
  **0 LSB** against the ideal-ground control at every mid-scale input, while
  the die-side analog-ground excursion is **37.333 mV** peak-to-peak — against
  **0.059 mV** for the package resistance alone with the inductance zeroed
  (`package-r-only`, a strict one-element ablation isolating the bond
  inductance's own contribution), and **10.779 mV** for a lumped,
  on-die-only substrate return of this record's own stated order
  (`substrate`, `R_SUB` = 30 Ω — a stand-in, not an extracted network). So the
  reasoning in "Decision" above is now a measurement at this one corner, not
  only prose: the ground return's impedance is real and its **inductance**,
  not its resistance, dominates the excursion it produces, but neither moves
  a captured code at this magnitude. **What this does not close**, and what
  no reader may take from it: a worst-corner claim (this record ran the
  ratified baseline corner only; the nine-point grid is open at 2 of 9 points
  for the `ideal`/`package` pair as of issue #409 item 1 — see that campaign's
  "Why the corner grid arrives in pieces", whose first-stated reason, a
  shared-host policy against local multi-corner runs, was re-checked and
  **retired**, leaving a measured cost against a session that must end and a
  batch route that cannot mint this repo's record format), and a
  priced measurement of this record's own *rejected* `no-gnd-pad` null option
  (implemented but not run, on cost — its own record estimates roughly an
  order of magnitude more wall clock than the control arm). Both were tracked
  as **#409** and restated in
  [DR-015](DR-015-package-parasitic-assumption.md)'s "Open items"; **the
  second is now measured** (next bullet), the first is still open.
- **The rejected null option now has a price, at one corner and one assumed
  substrate magnitude** (issue #409 item 2, 2026-09-25,
  `sim/supply-impedance-sensitivity/records/20260925-204633-7339971.md`).
  Deleting this record's pad and letting `GND` reach the board only through
  the lumped substrate link — the `no-gnd-pad` arm, a strict one-element
  ablation against the `package` arm it is run beside — costs **+27.6 mV** of
  die-side `GND_DIE` excursion (**65.237 mV** against **37.590 mV**, 1.74×)
  and **0 LSB** of captured code at `tt_27c_1.80v`. Read that as the shape of
  the argument in "Decision" above rather than as a vindication of it: the
  option this record rejected is measurably worse *on the comparator's own
  reference* and indistinguishable *on the output* at this point, which is
  exactly why the choice could not have been made on captured codes and was
  not. Three limits travel with the number and none may be dropped when it is
  quoted: it is **one corner**; it is at DR-015's **lumped** `R_SUB`/`R_SUBX`
  = 30 Ω, a stand-in taken from this record's own "10s of ohms" prose rather
  than an extraction, and the arm is above all a function of that value; and
  the excursion figures are **undecoupled** upper bounds, since no decoupling
  is designed anywhere in this block (see the last open item). The earlier
  estimate that this arm would cost roughly an order of magnitude more wall
  clock than the control was also wrong — it ran in 487 s, 1.67× the control
  and less than the `package` arm — so "too expensive to run" is retired as a
  reason, not merely postponed.
- **The pad's position is provisional.** There is no pad ring; when one exists,
  the analog ground terminal's placement relative to the other supply pads (and
  whether it wants more than one bond point of its own) is a real question this
  record does not answer.
- ~~**On-die decoupling** for any domain is still not designed, budgeted, or
  measured (carried over from DR-010).~~ **ADDRESSED, at the scope that record
  states**, by [DR-017](DR-017-on-die-decoupling-budget.md) (issue #431): one
  `cap_mim_m3_1` per supply domain, `MF = 2` → 8.870 pF each, sized from a
  met3/met4 area budget rather than from a bounce target — because DR-017's own
  measurements show this die's `package`-arm excursion falls only as ~1/√C, so
  **no affordable on-die capacitance reaches 1 LSB** and the residual belongs
  to the bond inductance (a packaging decision, not a die decision). Two parts
  of the item stay open there rather than here: the capacitors exist in
  `design/` only and are not yet placed or DRC/LVS-verified in
  `layout/sar-adc-top/`, and the reference network (`VREFP`/`VREFN`/`VCM`,
  ideal at the die in every campaign here) is still undecoupled and unmeasured.

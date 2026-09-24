# DR-010: The digital `VPWR`/`VGND` domain stays independent of the analog `VDD`/`GND` domain, and gets its own top-level pins

- **Status**: proposed — like DR-008 and DR-009 this record settles an
  integration-level wiring question (`design/sar_adc_top.sch`'s top-level
  interface, and `layout/sar-adc-top/`'s top-level routing), not a numeric row
  of `spec/target-spec.md`. It inherits the same provisional status as every
  record still resting on DR-003's DRAFT numeric inputs.
- **Date**: 2026-09-24
- **Decided by**: Builder agent, issue #355
- **Supersedes**: none
- **Superseded by**: (none while this record stands)
- **Related**: #355 (this decision and its implementation), #344 (the `klt erc`
  supply-spec tooling and the finding that forced the question), #258 (which
  made `VPWR`/`VGND` one `.GLOBAL` net each instead of one private copy per
  subcircuit instance — this record builds directly on that), DR-001 (the
  ratified 1.8 V core-flavour scope both domains sit at),
  `layout/sar-adc-top/README.md` ("GND / VPWR / VGND", open question 2),
  `layout/sar-adc-top/erc-reports/20260923-143401-1ee4ba8/` (the failing run),
  `layout/sar-adc-top/erc-reports/20260924-190825-f3622fc/` (the passing one).

## Context

`klt erc`'s first structural supply run on the composed top level (issue #344,
T1 checklist item 11 *Power delivery — structural*) came back with two
findings, both real:

```
erc.unconnected_net  VPWR  declared net 'VPWR' resolves to 2 disconnected electrical islands (expected exactly one)
erc.unconnected_net  VGND  declared net 'VGND' resolves to 2 disconnected electrical islands (expected exactly one)
```

The two islands per rail are the two standard-cell macros' own self-contained
rails (`sar_sequencer`'s and `seln_inverters`'), corroborated independently by
that layout record's own `lvs.json` `net_correspondence`. The analog supplies
(`VDD`, `GND`) each resolved to exactly one island in the same run, with no
`erc.supply_short` anywhere — this was specifically the digital half.

**Verified, not assumed** (each against a named artifact in this tree):

- `design/sar_adc_top.spice` already declares `.GLOBAL VPWR` and `.GLOBAL VGND`
  (lines 323–324), so at the *netlist* level each digital rail has been **one**
  net across the whole hierarchy since issue #258 — distinct from `VDD`/`GND`,
  which have their own `.GLOBAL` cards. The *schematic* half of the question
  was therefore already answered; what was missing was (a) a top-level port for
  either rail and (b) any drawn conductor tying the two macros together.
- The layout half had never been attempted: per `layout/sar-adc-top/README.md`
  open question 2, both macros expose their rails only as **buried met5 PDN
  straps** well inside their own footprints, not as edge-abutting DEF pins, so
  reaching them means a top-level wire overlapping each macro's own bounding
  box at exact strap coordinates.
- `layout/sar-adc-top/bin/generate-lvs-reference.py` encoded the *opposite* of
  the netlist's own `.GLOBAL` scoping, wiring `Xseq` to `VPWR_SEQ`/`VGND_SEQ`
  and `Xinv` to `VPWR_SELN`/`VGND_SELN` — two private rail pairs. That was
  consistent with the README prose it cited and inconsistent with the
  schematic it claims to mirror.
- The digital and analog **grounds already share the p-substrate**, whatever
  the metal does: the two macros are tapped by `klt place-and-route`'s own
  `sky130_fd_sc_hd__tapvpwrvgnd_1` cells (present by name in the graded GDS),
  and `klt extract`'s sky130 deck synthesises every untapped analog NMOS body
  onto one shared `vsubs` net regardless of drawn geometry
  (`layout/sampling-frontend-wells/README.md`). So "separate grounds" can only
  ever mean *separate metal return paths*, never galvanic isolation. This
  record does not pretend otherwise.

Not verified, and explicitly not claimed below: **no simulation in this repo
measures digital-to-analog supply coupling.** The reasoning in "Decision" is a
design-time argument from this design's own topology and from device physics;
it is not a measured result, and CLAUDE.md's "no claim without a testbench"
rule applies to it. See "Open items".

## Decision

**The digital supply domain stays independent of the analog one, and is given
its own top-level pins.** Concretely, and in force for `design/` and
`layout/sar-adc-top/` alike:

1. `VPWR` and `VGND` are **not** tied to `VDD`/`GND` anywhere on-die — not in
   the schematic, not in the top-level LVS reference, and not in metal. They
   remain the two distinct `.GLOBAL` nets #258 made them.
2. `VPWR` and `VGND` each become a **top-level chip pin** of `sar_adc_top`,
   appended to the block's interface after `BUSY`. The top-level interface goes
   from 19 ports to **21**: `VINP VINN VDD VREFP VREFN VCM CLK RST_B
   DOUT9..DOUT0 BUSY VPWR VGND`.
3. The two standard-cell macros share **one** `VPWR` net and **one** `VGND`
   net — they are one logic domain, not two — so the layout ties
   `sar_sequencer`'s and `seln_inverters`' own met5 PDN straps together and
   carries each rail out to its own top-level pin.
4. Both domains sit at the **same voltage** (1.8 V, DR-001's ratified core
   flavour). This record partitions *domains and pins*, not supply voltages;
   it introduces no second voltage and no level shifter, and every `sim/` row
   stays a single-supply-point measurement.
5. The star point between the two domains is **off-die** — a board/package
   decision, not a die decision. This record deliberately does not specify it
   beyond naming that it must exist: the block presents four supply terminals
   (`VDD`, `GND` via the substrate, `VPWR`, `VGND`) and an enclosing testbench
   or harness ties them at one point, exactly as
   `sim/full-conversion-transient/` and `sim/sar-sequencer-behavioral/` already
   do with independent sources.

### Why independent, stated as the reasoning and not as a measurement

The sequencer clocks on the same edge the comparator decides. That makes any
digital-supply disturbance **coincident with the decision instant by
construction**, not by coincidence — the worst possible phase relationship, and
the one a random-noise argument would understate. Three mechanisms follow from
this design's own topology:

- **Comparator.** `design/comparator.sch` is a StrongARM-class latch: during
  regeneration its own supply *is* the reference the differential pair's
  imbalance is resolved against, so a supply step inside the decision window
  appears at the input as offset. Tying `VPWR` to `VDD` would put the whole
  standard-cell bank's switching current — 19 `DOUT`/`SELn` drivers plus the
  sequencer's own register, all switching at once — onto exactly that node.
- **CDAC.** `design/cdac/cdac_array.sch`'s bottom-plate PFET switches take
  `VDD` as their n-well/body bias, and the array's own settling is what each
  bit trial measures. A supply disturbance on `VDD` during a bit trial is a
  DAC-settling error, not merely a noise term.
- **Reference.** `VREFP` is driven onto the same bottom plates; the analog rail
  and the reference are not independent of one another at the switch level.

Keeping the digital rail on its own pins does not remove the substrate path
(above), but it removes the **low-impedance metal bridge** that would otherwise
carry digital return current straight through the analog ground on its way back
to the source — which is the part a die-level decision can actually control.

## Alternatives considered

- **Tie `VPWR`/`VGND` to `VDD`/`GND` at the top level (one domain, two fewer
  pins).** Rejected. It is the cheaper layout (the digital region already
  abuts the west supply corridor) and it would close item 11 with no new pins.
  The cost of *not* choosing it is exactly two pads and one board-level star
  point; the cost of choosing it is a die that can never be measured with the
  two domains separated, because the tie is in metal — an irreversible
  commitment made to save a pad, against the three mechanisms above.
- **Leave the two macros' rails independent, with four supply pins
  (`VPWR_SEQ`/`VGND_SEQ`/`VPWR_SELN`/`VGND_SELN`).** Rejected, and this is the
  shape the top-level LVS reference had encoded. The two macros drive each
  other's inputs directly (`sar_sequencer.DOUT<i>` → `seln_inverters.DOUT<i>`),
  so a rail-to-rail offset between two separately-fed supplies lands straight
  on a logic input threshold at that crossing — a real functional hazard for no
  isolation benefit, since both macros sit in the same standard-cell region
  over the same substrate. It also doubles the pad cost of the decision. The
  cost of not choosing it: nothing this design can name — the two macros have
  no reason to be independently biased.
- **Hybrid: separate `VPWR`, but merge `VGND` into `GND` in metal** (a common
  "one ground" practice). Rejected. It concedes the whole return-current
  objection while keeping the supply split that is cheap to keep — the
  substrate already provides the DC ground commonality, so the metal merge buys
  only impedance on the path that carries the switching current.
- **Declare the rails out of the ERC supply spec instead.** Rejected on
  principle, and already rejected once by #344: tuning the spec until the
  layout passes is forbidden here (CLAUDE.md, "the spec is a gate"). The rails
  are drawn, labelled supplies; a spec that omitted them would grade nothing.

## Spec lines affected

**No row of `spec/target-spec.md` changes**, and none is added — this record
sets no numbers. What it fixes is the block's **top-level interface**, which
that table does not enumerate:

- `design/sar_adc_top.sym` / `design/sar_adc_top.sch`: two new `dir=in` ports,
  `VPWR` and `VGND`, appended after `BUSY`; `design/sar_adc_top.spice`
  regenerated (its device netlist is unchanged — the regeneration moves only
  the port-declaration comments, since `sar_adc_top` netlists flat).
- DR-001's ratified 1.8 V core-flavour scope is untouched and is the supply
  point both domains sit at.

## Consequences

- **T1 item 11's supply-continuity half passes for the first time — and the
  item still does not render `met`.**
  `layout/sar-adc-top/erc-reports/20260924-190825-f3622fc/` reports
  `erc_status: clean`, 0 findings: all four declared supplies (`VDD`, `GND`,
  `VPWR`, `VGND`) each resolve to exactly one electrical island, with no
  `erc.supply_short`. **`signoff/t1-report.json`'s two item-11 rows nevertheless
  render `unmet`, with reason `check_failed` and `citation: null`** — verified
  by running the pinned grader, not predicted. Read the reason precisely,
  because it is not the one this record's continuity work bears on:
  `klt signoff`'s `_grade_power_delivery` tests the cited *LVS* part before it
  looks at the supply spec at all, and item 4's LVS is still `mismatch`
  (klayout-tools#1878), so grading short-circuits at `check_failed` and never
  reaches the tie question. The tie gap is a **second, latent** reason — no
  `ties[]` is declared (klayout-tools#2169 would turn a correct declaration
  into a false `erc.supply_short`), which is the state the grader has a
  dedicated `supply_spec_disclosed_tool_limitation` reason for — and it is what
  would surface next, once the LVS half matches. Neither is touched by this
  record: what moved is that both rows went from `no_evidence` to
  `check_failed`, i.e. from "nothing was cited" to "the evidence was cited, ran,
  and does not yet clear the item". `citation: null` is the grader's ordinary
  rendering for any unmet item; the compound citation itself lives in
  `signoff/block-manifest.json`, not in the report's null field.
- **The top-level LVS compare improves**, which was not the goal and is worth
  stating as an effect rather than a justification: 21/21/21 pins (was
  19/19/19) and 88 mismatches (was 98), 803 devices matched (was 794), on
  `layout/sar-adc-top/reports/20260924-190817-f3622fc/`. DRC stays clean.
  The remaining 88 are the same klayout-tools#1878 `combine_devices`-scoping
  blocker as before; this record does not touch it.
- **Two more pads.** `docs/chipalooza/challenge-4-proposal.md`'s §2.2 pad table
  carries them as supply lines (not slot-budget line items, the same treatment
  `VDD` already had). Anything downstream that assumed a 19-port interface —
  a future pad ring, a harness adapter — now sees 21.
- **A board/package requirement is created.** The two domains must be tied at
  exactly one point off-die. Getting that wrong (two ties, or none) is now a
  *system* failure mode this design depends on someone else avoiding; it is
  named here so it is not discovered at bring-up.
- **No on-die decoupling exists** on either domain, and this record does not
  add any. Separate rails with no decap is better than shared rails with no
  decap on the coupling axis, and worse than either on the IR/di-dt axis — the
  structural item (11) is explicitly not the analysis item (`klt power`,
  IR-drop/EM), and nothing here should be read as an IR-drop claim.
- **Nothing in `sim/` is invalidated.** The regenerated netlist's device cards
  are byte-identical, and every existing testbench already sources `VPWR`/
  `VGND` independently of `VDD`/`GND` — which is, in hindsight, the same
  partition this record now makes explicit on the die.
- **klayout-tools#2400 does not bite this design.** That upstream gap (a
  `nets[]` entry matches supplies by label *string*, so genuinely independent
  domains that reuse a macro library's PG pin names cannot be declared) was
  flagged in the failing ERC record as a reason item 11 might stay
  unsatisfiable *if* the resolution kept the two macros' rails independent of
  each other. Decision 3 above does not: there is exactly one `VPWR` net and
  one `VGND` net in this block, so one label string names one net and the
  declaration is exact.

## Open items

- **The coupling argument is unmeasured.** No `sim/` campaign in this repo
  drives the digital rail with a realistic switching load and measures the
  comparator's own decision under it. This record's reasoning stands on
  topology and device physics, which is enough to *choose a partition* and not
  enough to *quantify* what the partition buys. A testbench that would settle
  it: drive `VPWR` through a package-like R+L into the assembled
  `sar_adc_top`, run `sim/full-conversion-transient/`'s own stimulus, and
  compare code errors against the same run with `VPWR` tied to `VDD`. Until
  that exists, no number from this record may be quoted as measured.
- **The analog `GND` still has no top-level pin.** `GND` is `.GLOBAL`, its
  return is partly the substrate, and `cdac_array`'s own fourth port is a
  literal `vsubs` connection — so unlike `VDD`, there is no drawn top-level
  `GND` pad for a package to bond to. `klt erc` does not catch this (one island
  is one island, pin or no pin), and this record does not fix it: it is the
  same class of gap for the *analog* half, tracked separately as **#362**.
- **On-die decoupling** for either domain is not designed, budgeted, or
  measured.

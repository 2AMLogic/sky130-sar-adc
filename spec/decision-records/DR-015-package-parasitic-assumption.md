# DR-015: The package-parasitic values `sim/` uses are a stated assumption, derived from wire geometry — not a package selection

- **Status**: proposed — like DR-008, DR-010 and DR-012 this record settles how
  a *simulation* is set up and what may be claimed from it, not a numeric row
  of `spec/target-spec.md`. It sets no row, adds no row, and it is not a
  packaging decision.
- **Date**: 2026-09-25
- **Decided by**: Builder agent, issue #378
- **Supersedes**: none
- **Superseded by**: (none while this record stands)
- **Related**: #378 (the campaign that forced it),
  [DR-012](DR-012-analog-ground-pad.md) (whose "Open items" asked for a
  package-like R+L testbench and whose "10s of ohms of p-substrate" wording is
  the substrate stand-in's magnitude), [DR-010](DR-010-digital-supply-domain-partition.md)
  (the off-die star point these values sit between, and the still-open
  on-die-decoupling item), `sim/supply-impedance-sensitivity/` (the first and
  currently only consumer), #409 (the residual work this record defers: the
  ratified PVT grid, the `no-gnd-pad` arm, the `R`/`L` sweep and an extracted
  substrate network — of which the sweep and the `no-gnd-pad` arm have since
  been closed at stated scopes, see "Open items"), `CLAUDE.md`'s clean-room
  rule.

## Context

DR-012's open item names a testbench — "drive the assembled `sar_adc_top`
through package-like R+L on each of the four supply terminals" — and a
testbench needs numbers. This block has no package: no assembly decision, no
pad ring (DR-012 says so in its own "Alternatives considered"), no bond
diagram, no substrate extraction. So the numbers cannot be *measured* from
anything in this tree, and two failure modes are available if that is not
handled explicitly:

- **Folklore.** A plausible `2 nH` typed into a deck, quoted by the next
  record, and treated as settled three records later, with nobody able to say
  where it came from.
- **Reverse engineering.** Lifting a parasitic table out of some vendor's
  package datasheet or a competitor's assembly. `CLAUDE.md` forbids it
  outright, and it would also be a *package selection* smuggled in as a
  simulation parameter.

**Verified, not assumed:**

- **The formulas are textbook and are evaluated in code, not transcribed.**
  `sim/supply-impedance-sensitivity/run_supply_impedance.py` computes the
  bond-wire inductance from the standard straight round-wire expression
  `L = (µ₀·l/2π)·(ln(2l/r) − 3/4)` and its resistance from `ρ·l/A`, from the
  wire length/diameter/material constants declared at the top of that file. A
  reader can change the geometry and see the values move; nothing is a magic
  constant.
- **The table below cannot drift from the code.**
  `sim/tests/test_supply_impedance.py` parses every value out of this record's
  Markdown and compares it against the module constants, and separately
  recomputes both formulas from the geometry. That check exists because this
  record's own *draft* shipped with exactly the Folklore bug described above —
  its bond-wire row quoted the package total (`1.914 nH`) instead of the wire's
  own `1.414 nH` — and nothing but a reader's arithmetic would have caught it.
- **The substrate magnitude is this repo's own prior wording.** DR-012's
  "Decision" section already argues from "return current through 10s of ohms of
  p-substrate between the comparator's taps and a paddle contact". The lumped
  stand-in below takes its order of magnitude from that sentence, so the
  campaign testing DR-012 uses DR-012's own premise rather than a new
  invention.

**Not verified, and explicitly not claimed below:** that any real package has
these parasitics; that this die's substrate presents this resistance; that the
lumped substrate elements resemble the distributed network an extraction would
produce. Those are assumptions, and every record consuming them must say so.

## Decision

**`sim/` campaigns that need a supply-return network use the following stated
assumption, and say in their own record that it is an assumption.**

1. **Per bonded supply terminal**, a series `R + L` between the board's star
   point and the die pad:

   | element | value | provenance |
   | --- | --- | --- |
   | bond wire, `l = 1.5 mm`, `d = 25.4 µm` (1 mil) gold | `L = 1.414 nH`, `R = 72.2 mΩ` | computed from `L = (µ₀·l/2π)(ln(2l/r) − 3/4)` and `R = ρ·l/A`, `ρ_Au = 2.44e-8 Ω·m` |
   | lead frame + board trace to the star point | `+0.5 nH`, `+30 mΩ` | a **stated allowance**, not a derivation |
   | **total, per terminal** | **`L = 1.914 nH`, `R = 102.2 mΩ`** | the value a bonded arm uses |

   Every row above is **evaluated in `run_supply_impedance.py`, not transcribed
   here**: this table is a rendering of that file's own constants, and each
   record the campaign writes re-renders it from the same code. If the two ever
   disagree, the code is the value that ran and this table is the typo.

2. **Lumped substrate stand-ins**, for the on-die return that no extraction
   exists for: `R_SUB = 30 Ω` in a ground return, and `R_SUBX = 30 Ω` between
   the analog and digital ground die nodes (the path DR-012's extraction
   evidence says makes `GND` and `VGND` one net). Magnitude from DR-012's own
   "10s of ohms"; **a single lumped resistor is not a substrate network**, and
   no record may present it as one.

3. **This is not a package selection.** No package family, pin count, die
   attach, or assembly flow is chosen, implied, or recommended here. A future
   packaging decision is a different record, and it supersedes this one.

4. **Scope of what may be claimed.** A result resting on these values is
   evidence about *a* supply return of this order of magnitude — a sensitivity,
   a ranking between two grounding schemes, an upper bound. It is not a
   prediction for any assembled part, and it may not be quoted as one.

5. **A campaign that attributes an effect to one element must ablate that
   element and nothing else.** The values above are used at two settings that
   differ in exactly one term — the full `R + L`, and the same `R` with `L = 0`
   — so "this is the bond inductance's contribution" is a measured difference
   rather than an inference. A difference taken between two networks that differ
   in more than one element (for instance the package `R` against the substrate
   `R_SUB`, which is ~300× larger) is a comparison of *schemes*, not an
   attribution to a mechanism, and must be reported as the former.

6. **No decoupling is modelled, deliberately.** This design has no on-die
   decoupling (an open item of both DR-010 and DR-012) and no board decoupling
   is added in simulation either. Every result under this assumption is
   therefore an *undecoupled* case: pessimistic by construction, and stated as
   such rather than presented as the expected system behaviour.

7. **This record sets no numbers in `spec/target-spec.md`** and changes no row.

## Alternatives considered

- **Take a real package's parasitics from a vendor datasheet or an existing
  assembly.** Rejected on principle: `CLAUDE.md`'s clean-room rule forbids
  building on anyone else's implementation data, and a datasheet's table would
  also import a packaging *choice* nobody in this project has made. The cost of
  not choosing it: no number here is tied to a purchasable part, so nothing
  under this assumption is a prediction for one — which is why item 4 above
  exists.
- **Sweep `R`/`L` over a range instead of fixing one point.** Not rejected on
  merit — this is the better experiment, and it is named in "Open items". It is
  not taken *now* because each point is a whole-ADC transient of the same cost
  as `sim/full-conversion-transient/`'s, so a 2-D sweep is a campaign in its own
  right. The cost of not choosing it: a single assumption point can only show
  whether the mechanism matters at that magnitude, not where its threshold is.
- **Keep running every campaign with ideal sources (the status quo).** Rejected:
  that is exactly the unmeasured state DR-012 flagged against itself. The cost
  of choosing the status quo is that DR-012's central argument stays prose
  forever.
- **Add a decoupling capacitor so the bonded arms ring less and simulate
  faster.** Rejected. It would model a system this design does not have, and it
  would understate the very excursion the campaign exists to measure. The cost
  of not choosing it is real and is paid in runtime: an undecoupled bond-wire
  inductance against the die's own capacitance rings in the GHz, which forces
  the solver's timestep down and makes a bonded arm slower than an ideal one.
- **Put the values in the runner only, with no record.** Rejected: a number
  that changes what a `sim/` record claims is exactly the kind of decision
  `spec/README.md` says gets a record ("any scope decision, including a
  decision to defer"), and folklore is the failure mode described in Context.

## Spec lines affected

**None.** No row of `spec/target-spec.md` is added, changed, or removed. This
record constrains how a testbench is built and what its results may claim, in
the same way DR-012 constrains an interface without setting a number.

## Consequences

- **`sim/` records become comparable to each other on this axis.** Two
  campaigns using this assumption can be compared; one that invents its own
  values cannot. Any record that departs from these values must say so and say
  why.
- **Every number produced under this assumption inherits its status.** If a
  packaging decision later replaces these values, the records resting on them
  are not wrong — they measured what they said they measured — but they stop
  bounding the real part, and the superseding record must name which campaigns
  need re-running.
- **Simulation gets slower, not faster.** See the fourth alternative: an
  undecoupled `L` against die capacitance rings, and the transient solver pays
  for it. That cost is the price of not modelling a decoupling network that
  does not exist.
- **The substrate stand-in is the weakest element here, and it is load-bearing
  for one arm.** The `no-gnd-pad` arm of `sim/supply-impedance-sensitivity/`
  (DR-012's rejected null option) is *entirely* a function of `R_SUB`: with a
  small `R_SUB` it looks harmless, with a large one it looks fatal. That arm
  must always be read as "at this assumed magnitude", and closing it properly
  needs an extracted substrate network, which is its own open item.
- **A reader can no longer find an unexplained impedance in a deck.** The
  values are computed from named geometry in one file and restated in every
  record, so the provenance question is answered in the artefact rather than in
  someone's memory.
- **Item 5 costs one extra simulation per campaign, and buys the only
  attributable number.** Requiring an `L = 0` companion to every `R + L`
  setting means a campaign runs an arm it would otherwise skip. That arm is
  cheap — with no inductance there is nothing to ring, so it costs about what
  the ideal control costs — and without it a campaign can only say "these two
  grounding schemes differ", never "the bond inductance is what did it".

## Open items

These are tracked together as **#409** rather than left as prose, so that
"deferred" is a queue entry and not a memory. Two are now closed at stated
scopes — the `R`/`L` sweep and the `no-gnd-pad` arm that prices DR-012's
rejected option; the rest remain open.

- ~~**No `R`/`L` sweep.** One assumption point shows whether the mechanism
  matters at that magnitude; it does not find the magnitude at which it starts
  to matter. A bounded 2-D sweep (bond inductance × substrate resistance) at
  one corner is the natural follow-up.~~ **CLOSED, at the scope stated here**,
  by `sim/supply-impedance-sensitivity/records/20260925-164447-722fcb0.md`
  (issue #409 item 3) — the as-built `package` topology re-run at bond
  inductance `0×`/`1×`/`10×` of the `1.914 nH` above, crossed with the lumped
  substrate link `R_SUBX` at `3`/`30`/`300 Ω`, plus the `ideal` control, at
  `tt_27c_1.80v`. Its `1× / 30 Ω` point is card-for-card the `package` arm of
  the record before it, so the box is a walk away from *this* record's
  assumption point rather than an unrelated grid. **What it changes for this
  record:** item 4's "a result resting on these values is evidence about *a*
  supply return of this order of magnitude" now has a measured width — no
  mid-scale captured code moves anywhere in that box (worst `|Δ code|` = 0 LSB
  at all nine points), while the die-side analog-ground excursion climbs from
  `0.059 mV` to `99.749 mV` along the `R_SUBX = 30 Ω` column. **What it does
  not change:** the null is *bounded*, so nothing here licenses a claim outside
  `L ≤ 10×`, `R_SUBX ∈ [3, 300] Ω`, or at any other corner; the excursion
  figures are undecoupled upper bounds (item 6); and the two axes interact
  non-monotonically, so neither may be quoted as a trend on its own. The
  substrate-only *return* `R_SUB` is **not** swept — it is absent from the
  as-built topology, and sweeping it is the `no-gnd-pad` arm's own campaign,
  still open below.
- **No extracted substrate network.** `R_SUB`/`R_SUBX` stay lumped stand-ins
  until something in `layout/` can produce a real substrate network for this
  composition. Until then no result here is a statement about this die's
  substrate.
- ~~**The one arm that would price DR-012's *rejected* option has not been
  run.** `sim/supply-impedance-sensitivity/`'s `no-gnd-pad` arm is implemented
  but absent from the first committed record, on cost: a high-impedance,
  lightly-damped ground drives the transient solver's timestep down by roughly
  an order of magnitude. So the evidence so far prices the *bonded* return;
  what the substrate-only return would have cost at this assumed `R_SUB` is
  still owed, and no record under this assumption may imply
  otherwise.~~ **CLOSED, at the scope stated here**, by
  `sim/supply-impedance-sensitivity/records/20260925-204633-7339971.md` (issue
  #409 item 2) — `ideal` / `package` / `no-gnd-pad` at `tt_27c_1.80v`, the last
  two being a strict one-element ablation (same three bonded terminals at this
  record's R+L, same `R_SUBX`, the only difference is whether `GND` has a bond
  of its own). **What it changes for this record:** the Consequences item above
  ("the substrate stand-in is the weakest element here, and it is load-bearing
  for one arm") now has a number attached at the assumed magnitude — deleting
  the pad costs **+27.6 mV** of die-side ground excursion (65.237 mV against
  37.590 mV, 1.74×) and **0 LSB** of captured code. So the rejected option is
  measurably worse on the rail and indistinguishable on the output at this
  point, which is why DR-012's choice could not have rested on captured codes.
  **What it does not change:** the arm is still *entirely* a function of the
  lumped `R_SUB`/`R_SUBX` stand-ins at `30 Ω` — the next item below is
  unaffected, and the figure is evidence about *a* substrate-only return of
  that order, not about this die's substrate — and there is still no sweep of
  `R_SUB` itself (the 2-D box above swept `R_SUBX` on the as-built topology,
  which `no-gnd-pad` is not). **The cost claim that deferred it was wrong**,
  and is corrected rather than quietly dropped: the full-stimulus run took
  **487 s, 1.67× the `ideal` control** — *cheaper* than the `package` arm in
  the same record — against a truncated-slice calibration that had projected
  ~17× and several hours. A slice starting at `t = 0` prices the start-up
  transient, not the steady-state conversions the stimulus spends its span on.
- **The corner axis of that gap is untouched by it.** Every record under this
  assumption is **one** corner (`tt_27c_1.80v`), so the findings that a bonded
  return, a swept box, and now the null option each cost < 1 LSB are statements
  about that point and not about the ratified grid.
- **No decoupling is designed, budgeted, or modelled** — carried over from
  DR-010 and DR-012 rather than settled here. When a decoupling plan exists,
  this assumption gains a second, decoupled variant and the pessimism above
  becomes quantifiable rather than merely declared.
- **A packaging decision supersedes this record**, whenever one is made. Until
  then, nothing in this repo has chosen a package, and this record must not be
  read as though it had.

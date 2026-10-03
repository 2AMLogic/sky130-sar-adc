# DR-011: A DRAFT Kickback row for the target spec, at an interim adopted bound

- **Status**: proposed — this record does not self-ratify. Per the canary
  spec/DR ratification-via-PR standing policy (2AMLogic/2am#357: "a builder
  drafts the ratification/DR as a PR on the evidence, and the operator's PR
  approval is the ratification act" — the same policy DR-003 was ratified
  under via #27/PR #46, and the same posture DR-007 holds today), the row
  this record proposes lands in `spec/target-spec.md` as **DRAFT**. It is not
  binding, it may not be quoted as settled, and no `sim/` bench may encode it
  as a pass/fail threshold (`spec/README.md`).
- **Date**: 2026-09-24
- **Decided by**: Builder agent, issue #361
- **Supersedes**: none — `spec/target-spec.md` has never carried a Kickback
  row in any status, so there is no prior decision on this question to
  replace. This record adds a row; it does not revise one.
- **Superseded by**: (none while this record stands)
- **Related**: #361 (this record), #346 / PR #358 (the `kickback` testbench
  mode and the baseline measurement this record reads),
  `sim/comparator-decision/records/20260924-041815-afcb1b5.md` (that
  baseline), #349 (blocked on this row existing — the cross-repo
  static-preamp mitigation finding that has nothing to be graded against
  until a bound exists),
  [DR-003](DR-003-numeric-spec-derivation.md) (the ratified LSB and corner
  set this record's plausibility check and corner scope are stated against),
  [DR-004](DR-004-comparator-topology-and-noise-budget.md) (the comparator
  topology whose kickback is measured; its Decision §3 "exercised, not
  budgeted" treatment of regen/offset is the precedent the baseline record
  cites for its own informational status),
  [DR-007](DR-007-revised-enob-inl-dnl-targets.md) (the citation pattern this
  record's `target-spec.md` row follows: a `proposed`, not-yet-ratified
  candidate value cited from the table).

## Context

Issue #346 (PR #358, merged 2026-09-24) gave this repo's embedded comparator
its first measured kickback figure. From
`sim/comparator-decision/records/20260924-041815-afcb1b5.md`, verbatim:

> **Overall**: measured (informational, see Claim above) -- worst-case peak
> pin disturbance across the 2 Vindiff point(s) run: 73.3673 mV (at
> Vindiff=+50.0000mV)

**What that number is, stated precisely** (all of it read from that record,
none of it re-derived here):

- **73.3673 mV** peak pin disturbance on `VINP`, at `t = 5.108 ns`, at
  `Vindiff = +50 mV`.
- **Stimulus**: 1 kΩ series source impedance on each of `VINP`/`VINN` (ideal
  DC source → resistor → DUT pin), a single reset(5.0 ns, `CLK=0`) →
  evaluate(`CLK=1.8 V`) edge per run over a 40 ns evaluate window, `Vcm =
  0.9 V`.
- **Corner scope**: `process=['tt'], temperature_c=[27.0], supply_v=[1.8]` —
  **one PVT point**. This is a first-pass, nominal-corner-only
  characterization, explicitly *not* a PVT sweep; the record says so in its
  own subset-corner justification.
- **Decomposition**: the `Vindiff = 0 mV` control row reads −70.3419 mV. At
  zero differential input there is no decision to make, so that figure is
  attributable to CLK-gated reset/precharge/tail switching alone. The
  decision transient itself therefore contributes only
  `73.3673 − 70.3419 = 3.0254 mV`, i.e. **≈ 4.1 % of the total** — the other
  ≈ 95.9 % is clock-edge-coupled, not decision-coupled.

The record files this **INFORMATIONAL**, and says why in its own `Claim`
field: `spec/target-spec.md` has no Kickback row, DRAFT or ratified, to grade
it against. Per `spec/README.md` ("When a record is required" → "Any change
to the ratified spec — a new parameter …"), adding that row is a decision
record's job, not a silent table edit. This record is that decision record.

**What is verified vs. what is assumed.** Verified: every number above, read
directly from the committed record (which itself pins sky130A @
`c6d73a35…`, ngspice-46, and the DUT netlist SHA-256). Verified: the
cross-repo prior art named under "Alternatives considered" — fetched from
`2AMLogic/sky130-comparator`'s own default branch on 2026-09-24, not quoted
from memory or from the issue text. **Assumed, and flagged as such**: that
the peak pin disturbance into a 1 kΩ source is the right *quantity* to bound
for a comparator embedded in a SAR loop. It is the quantity this repo's
bench measures today and the quantity the same-PDK sibling bounds, but the
accuracy-binding quantity for *this* block is arguably a different one — see
"Open items".

## Decision

**Add one new row to `spec/target-spec.md`'s Target table, as DRAFT:**

| Parameter | Target | Stretch | Corner scope |
|---|---|---|---|
| Kickback | ≤ 5 mV peak pin disturbance into a 1 kΩ series source impedance, single decision edge | ≤ 2 mV, same conditions | the ratified corner set (DR-003: `−40/27/125 °C`, ±10 % supply, sky130 process corners) |

Three things this decision is, stated so a reader does not have to infer
them:

1. **The numeric bound is adopted verbatim from a sibling repo, as an
   explicit interim choice — not derived from this block's own system-level
   budget.** `2AMLogic/sky130-comparator`'s own Kickback row (≤ 5 mV target /
   ≤ 2 mV stretch, into a 1 kΩ source, single decision edge) was ratified
   there by **DR-002** (2026-09-16, their issue #28), and their proposed
   DR-004 static-preamp record is graded against it. This record adopts those
   two numbers as this repo's DRAFT candidate. That adoption is the *choice*
   this record is making, and the whole of "Alternatives considered" is the
   argument for it; it is not an unstated assumption inherited by proximity.
   (Note on attribution: issue #361 attributes the ≤ 5 / ≤ 2 mV bound to that
   repo's DR-004. Checked against their tree on 2026-09-24 — DR-004 is the
   *topology* record and is itself `proposed`; the bound it is measured
   against was ratified by their DR-002. Both are cited below at their
   correct provenance.)
2. **The corner scope is the ratified corner set, and today's evidence does
   not cover it.** The bound is stated to hold at every point of DR-003's
   ratified corner set. The only measurement that exists is one point
   (`tt`/27 °C/1.8 V). The row is DRAFT partly for that reason: it is
   under-evidenced on the corner axis, and that gap is named, not papered
   over.
3. **The design does not meet the proposed bound, by a wide margin, and this
   record does not adjust the bound to make it pass.** 73.3673 mV is
   **≈ 14.7×** the proposed 5 mV target and **≈ 36.7×** the proposed 2 mV
   stretch. Per `CLAUDE.md` ("agents do not relax a spec line to make a
   result pass") the correct output here is a bound the design misses, plus a
   named mitigation path — not a bound reverse-engineered from the
   measurement. Grading that gap and choosing a mitigation is #349's job,
   which this row unblocks; it is not this record's.

**Plausibility check against this repo's own ratified numbers** (a sanity
test on the adopted numbers, explicitly *not* a derivation of them): against
the ratified LSB of `3.5156 mV` (DR-003 via #27), the adopted target is
`1.42 LSB` and the adopted stretch is `0.57 LSB`; the measured baseline is
`20.87 LSB`. A peak input-pin disturbance of order one LSB, at a node that
is driven by a real source impedance and given the rest of a bit-trial phase
to recover, is not an obviously mis-scaled bound for a 10-bit converter.
That check is why adopting the sibling's numbers is defensible rather than
arbitrary — it is not a substitute for the budget derivation named in "Open
items".

## Alternatives considered

- **Derive the bound from this repo's own system-level budget instead of
  adopting the sibling's** — the alternative the acceptance criteria of #361
  ask be weighed explicitly, and the one that would be *better* if it could
  be done today. Not chosen, for a reason that is a gap in this repo's
  evidence rather than a judgement about the method: the derivation needs two
  inputs this repo does not have. (a) **A source-impedance assumption for the
  ADC's own analog inputs.** This repo has no input-drive spec row at all;
  the nearest thing, `sim/vcm-drive-budget/`, quantifies tolerable *VCM*
  drive resistance and explicitly "quantifies rather than closes" its gap
  (`docs/chipalooza/challenge-4-proposal.md` Section 7 Item 6). Without a
  stated source impedance, a kickback bound in millivolts is a bound on an
  unspecified quantity. (b) **A residual-at-next-decision settling analysis.**
  The accuracy-binding quantity inside a SAR loop is not the peak excursion
  during one edge but what is left of it when the *next* bit trial's decision
  is taken; deriving that needs the bit-trial timing budget
  (`sim/cdac-bit-trial-settling/`, `sim/sequencer-logic-delay/`) composed
  with a kickback recovery time constant nothing has measured. **The cost of
  not choosing this option** is real and is named here rather than hidden: an
  adopted bound carries no argument of its own about *this* converter, so a
  future budget derivation could move it in either direction, and any
  mitigation sized against it today may turn out over- or under-specified.
  The cost of *choosing* it, though, is that #361 would produce no row at all
  and #349 would stay permanently blocked — which is the concrete failure
  this issue exists to end. Adopt now, derive later, and say so.
- **Adopt the sibling's bound silently, as though it were obviously this
  repo's bound too.** Rejected explicitly, because it is the specific failure
  mode #361 names. `2AMLogic/sky130-comparator`'s
  [DR-004](https://github.com/2AMLogic/sky130-comparator/blob/main/spec/decision-records/DR-004-comparator-preamp-supersession.md)
  (their issue #34, PR #40, merged 2026-09-22 — `proposed`, a recommendation
  for two-key ratification, not itself ratified) is the record that *meets*
  the ≤ 5 / ≤ 2 mV bound, at 1.89 mV (tt/27 °C), 1.86 mV (ss/−40 °C) and
  1.77 mV (ff/125 °C), via a static resistive-load NMOS preamplifier ahead of
  the StrongARM latch. The bound itself was ratified by their **DR-002**
  (2026-09-16), whose own Basis for it is stated as first-principles
  engineering judgement "about what a comparator feeding a real driving stage
  should limit its own kickback to" — for a **standalone** comparator canary.
  That is informative prior art for this repo and nothing more, for three
  stated reasons: (i) their block drives an external stage, ours drives the
  CDAC top plate inside a closed SAR loop, so the mechanism that costs
  accuracy differs; (ii) their mitigation's cost (~95 µW static bias at
  1.8 V, per their DR-004) is weighed against *their* DRAFT 50 µW supply row,
  while this repo's Power row is "provisional, minimise at rate" with no
  threshold at all — the same microwatts buy a different verdict in the two
  budgets; (iii) their decision-time row is stated at 50 mV overdrive with
  its own corner caveats, and this repo has its own separate DR-006 bit-trial
  timing budget the same mitigation would have to fit. Naming the numbers as
  **adopted prior art** rather than **derived requirement** is what keeps
  that difference visible to whoever ratifies this row.
- **Bound the residual disturbance at the next bit-trial decision instant
  instead of the peak during the edge.** This is the technically better row,
  and it is rejected only as *premature*. No bench measures it: the
  `kickback` mode reports peak excursion over the transition, not a residual
  at a later pick-off point, and adding that measurement is a testbench
  change (a new pick-off convention, and a recovery-time-constant
  measurement) out of #361's scope. Proposing a row nothing can measure would
  produce a spec line with no possible evidence — worse than a measurable
  interim one. Named as the successor row in "Open items".
- **Bound kickback at a fraction of an LSB derived from the LSB alone** (e.g.
  ≤ ½ LSB = 1.7578 mV target). Rejected: it looks derived but is not. A
  half-LSB *peak transient* criterion silently conflates peak excursion with
  residual error — a disturbance that settles well before the next decision
  costs nothing regardless of its peak, and a much smaller one that does not
  settle costs a full code. Picking ½ LSB would be choosing a number for the
  appearance of rigour, which is the same error in the opposite direction
  from adopting one openly. Worth noting for whoever does the real
  derivation: at 1.7578 mV, even the sibling's best measured same-PDK
  topology (1.77–1.89 mV) would fail — so this is not a target anyone
  currently knows how to hit in sky130, and proposing it would be inventing a
  settled number rather than deriving one.
- **File no row, and instead widen #346's record to grade itself.**
  Rejected — `sim/` records are append-only and may never encode an
  unratified spec value as a threshold (`spec/README.md`); and #349 needs a
  *spec* bound, not a bench-local constant, to evaluate a mitigation against.

**Clean-room note.** Citing the sibling canary's ratified *spec bound* and
its published measured figures is the cross-pollination `CLAUDE.md` and the
baseline record's own Methodology field already sanction between 2AMLogic
canaries on the same PDK. Nothing about `2AMLogic/sky130-comparator`'s
netlist, device sizing, or layout is imported here, and no third party's
implementation is cited, reconstructed, or relied upon — this record adopts
a *target number*, not a design.

## Spec lines affected

`spec/target-spec.md`:

- **Target table — one new row, `Kickback`**: `≤ 5 mV peak pin disturbance
  into a 1 kΩ series source impedance, single decision edge (target); stretch
  ≤ 2 mV`, Status `DRAFT (new row, DR-011 candidate)`, note citing this
  record and #346's baseline.
- **Header status block and the "Not binding" bullet**: extended to name the
  new DRAFT Kickback row alongside the sample-rate and ENOB/INL-DNL rows, so
  the file's own summary of what is and is not binding stays complete.
- **"What T1 (bronze) will require of this block"**: the list of DRAFT rows
  nothing is claimable against gains Kickback.

**No existing row is edited, relaxed, or tightened.** `V_REF`, LSB,
resolution `N`, the CDAC unit-cap/array size, the comparator input-referred
noise budget, and the corner set stay exactly as DR-003 ratified them via
#27; the Architecture, Sample rate, ENOB, INL/DNL and Power rows stay exactly
as they read today. This record's whole footprint on the table is one added
row.

`sim/spec-coverage.json` (and its generated rendering `sim/spec-coverage.md`)
gains the matching index entry, because T1 item 9's completeness check
(`sim/check_spec_coverage.py`) mechanically fails a spec row that no bench
indexes. The entry is `claim_class: draft-informational` — a DRAFT row whose
committed evidence is recorded informationally, never as pass/fail against an
unratified number — pointing at the existing `comparator-decision` bench and
#346's record. That is bookkeeping this decision forces, not a second
decision.

## Consequences

1. **#349 becomes gradeable.** It has been `loom:blocked` on precisely this:
   a bound, any bound, for its cross-repo static-preamp finding to be
   evaluated against. With this row in place the comparison is arithmetic
   (73.3673 mV vs. 5 mV / 2 mV) rather than undefined.
2. **This repo now carries a spec row its design misses by ~14.7×, in
   writing.** That is the intended consequence, not an accident — it is the
   honest state of the block — but it is a real cost: the Target table now
   advertises a gap, T1 item 9's index carries a DRAFT row with a failing
   informational measurement, and any reader of `spec/target-spec.md` sees a
   row nothing currently satisfies. The alternative (no row) hid the same gap
   behind an absence.
3. **A mitigation campaign is now scopeable, and the baseline tells it where
   to look.** The ≈ 95.9 % / ≈ 4.1 % split between clock-coupled and
   decision-coupled kickback (Context) is a strong hint that clock-edge and
   reset/tail-switch shaping, or a stage that removes the channel-formation
   mechanism, matters far more here than anything that changes the decision
   transient. That is a *direction*, read from this repo's own two data
   points — not an endorsement of any particular topology, which is #349's
   call to make on its own evidence.
4. **The bound may move once it is derived properly.** Adopting a number
   means a later budget-derived row can supersede it in either direction
   (looser, if the residual-at-next-decision criterion turns out generous;
   tighter, if the SAR loop's floating-top-plate behaviour is less forgiving
   than a driven 1 kΩ source). Any mitigation sized against today's number
   inherits that risk, and work done against it is not wasted but is not
   final either.
5. **Ratifying this row obliges a full-corner kickback campaign.**
   `sim/check_spec_coverage.py` permits `claim_class: unbenched` only on a
   DRAFT row, so ratification mechanically forces a bench — and the corner
   scope decided above means that bench must cover the ratified corner set,
   not the single `tt`/27 °C point that exists today. That is real deferred
   work created by this record, named here rather than discovered at
   ratification time.
6. **No existing campaign is invalidated and nothing must be re-run.** This
   record adds a row and indexes an already-committed record against it; it
   changes no threshold any existing bench grades against, because no bench
   graded against a Kickback row (there was none).

## Open items

- **A budget-derived Kickback bound for *this* block**, replacing the adopted
  interim one. Owner: a future decision record, once (a) an input-drive /
  source-impedance assumption exists for the ADC's analog inputs and (b) a
  residual-at-next-decision settling criterion can be composed from the
  bit-trial timing budget (DR-006, `sim/cdac-bit-trial-settling/`,
  `sim/sequencer-logic-delay/`) and a measured kickback recovery time
  constant. That record would supersede this one on the same question.
- **A residual-at-next-decision measurable**, if (a) above lands: a pick-off
  convention and a recovery-time measurement added to
  `sim/comparator-decision/run.py`'s `kickback` mode. Owner: whoever takes
  the successor row; out of #361's scope.
- **Full-corner kickback characterization** (`−40/27/125 °C`, ±10 % supply,
  all five sky130 process corners). Owner: a `kickback-corners` campaign,
  required before ratification per Consequences §5; the single `tt`/27 °C
  point that exists today is a first-pass baseline, not corner evidence.
- **Mitigation selection and its cost accounting** — whether this block
  adopts a preamp-class stage, clock-edge shaping, or something else, and how
  its static-current cost is weighed against this repo's own (thresholdless)
  Power row. Owner: #349, unblocked by this row; explicitly not decided here.
- **Operator ratification of this record** — mirrors #26 → #27's two-step
  pattern. Until approved, the row above is DRAFT: not binding, not quotable
  as settled, and not encodable as a `sim/` pass/fail threshold.

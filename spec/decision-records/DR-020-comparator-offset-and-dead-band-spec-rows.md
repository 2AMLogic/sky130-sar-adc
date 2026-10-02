# DR-020: No comparator offset or dead-band spec row yet — the systematic term and the non-decision band are both measured below `0.06 mV`, and the term that *would* need a row (random/mismatch offset) has no derived allocation

- **Status**: proposed — ratification via the operator's approval of the PR
  resolving #515, per the canary spec/DR ratification-via-PR standing policy
  (2AMLogic/2am#357: "a builder drafts the ratification/DR as a PR on the
  evidence, and the operator's PR approval is the ratification act"), the same
  mechanism DR-003 / DR-011 / DR-019 used.
- **Date**: 2026-10-02
- **Decided by**: Builder agent, issue #515
- **Supersedes**: none (closes one named Open item of
  `spec/decision-records/DR-004-comparator-topology-and-noise-budget.md` and
  narrows a second; DR-004 itself stands unedited — see "Consequences")
- **Superseded by**: (none while this record stands)
- **Related**: #515 (this decision — a cross-pollination report from the
  sibling canary `2AMLogic/sky130-comparator`, filed into this repo),
  [`DR-004`](DR-004-comparator-topology-and-noise-budget.md) ("Open items":
  the undecided offset/regeneration-time spec rows, and the
  precise-offset-extraction methodology gap this record's measurement
  addresses), [`DR-003`](DR-003-numeric-spec-derivation.md) Item 3 (the
  ratified differential LSB this record's boundaries are scaled against) and
  Item 4 (the error-budget split a future offset row would have to be
  allocated from), [`DR-006`](DR-006-sar-sequencer-bit-count-and-timing-budget.md)
  (the `83.333 ns` worst-case bit-trial phase the measured decision delays sit
  inside), [`DR-011`](DR-011-comparator-kickback-target-row.md) (the precedent
  for *adopting* a sibling canary's row verbatim as an interim choice — the
  path this record deliberately does **not** take, see "Alternatives
  considered"),
  `sim/comparator-decision/records/20261002-203719-c898d06.md` (**this
  record's evidence**: the new `offset-bisect` boundary-bisection campaign at
  `tt`/27 °C and `ss`/−40 °C),
  `sim/comparator-decision/records/20260821-071918-433a294.md` (the prior
  mismatch pick-off record, which this record does **not** supersede and whose
  σ stays the random-term characterization),
  `sim/comparator-decision/run.py` (`offset-bisect`, the subcommand added for
  this measurement; `sim/tests/test_offset_bisect.py`, its algorithm tests),
  [`sky130-comparator#66`](https://github.com/2AMLogic/sky130-comparator/issues/66)
  and [`sky130-comparator#119`](https://github.com/2AMLogic/sky130-comparator/pull/119)
  (the methodology source — cited, never inspected; see "Context").

## Context

**What forced the question.** DR-004's "Open items" names the gap twice, in its
own words: *"Offset and regeneration-time spec rows — `spec/target-spec.md` has
neither today … a future record should decide whether either belongs in the
table, using this record's `sim/comparator-decision/` evidence as a starting
data set if so"*, and *"A precise (not order-of-magnitude) offset extraction
methodology"*. Issue #515 supplied the trigger: a cross-pollination report from
the sibling canary `2AMLogic/sky130-comparator` (its issue #66 / PR #119),
which found on a **post-layout extracted** DUT both a nonzero systematic
decision offset at its nominal corner and a wide non-decision band at
slow/cold — two quantities a σ-only offset characterization cannot express at
all — and proposed a companion spec row for exactly that gap.

**What was verified for this record, and against what.**

1. **A methodology gap in this repo's own driver, confirmed by reading it.**
   `sim/comparator-decision/run.py`'s `offset` subcommand reduces each Monte
   Carlo draw to one linearized pick-off statistic, with no boundary search and
   no dead-band concept. Its sign-corrected decision test (`sign * (outp -
   outn) > threshold`) cannot distinguish a **wrong-polarity decision** from a
   **non-decision** — both fail it identically. `RegenCornerPoint.classify()`
   had already fixed that conflation for the *timing* sweep; nothing had fixed
   it for the *voltage* axis.

2. **A new, decision-referred measurement, run for this record.** The
   `offset-bisect` subcommand added in #515 classifies each probe by its
   **absolute** resolved polarity (never relative to the applied input) and
   bisects the two edges of the Vindiff axis independently — the
   largest-still-negative and smallest-still-positive boundaries — yielding a
   systematic offset (their midpoint) and a non-decision band width (their
   separation) as **two separate numbers**. A boundary in Vindiff is
   decision-referred: unlike the pick-off statistic, it has no fitted gain in
   it and therefore no linear-regime validity range to fall outside of. That
   is the escalation DR-004's Open item asked for, reached by changing the
   question rather than by either path DR-004 named (narrowing `PICKOFF_NS`,
   or fitting the calibration curve nonlinearly).

3. **The measured result** (`sim/comparator-decision/records/20261002-203719-c898d06.md`;
   schematic-derived `comparator_core.spice`, mismatch **disabled**, 29
   transient probes, `20 ns` evaluate window, `0.1 mV` bisection floor):

   | PVT point | systematic offset (mV) | non-decision band (mV) |
   |---|---|---|
   | `tt_27c_1.80v` | `−0.0275 ± 0.0275` — **not resolved** | `0.0000 ± 0.0549` — **not resolved** |
   | `ss_-40c_1.80v` | `+0.0000 ± 0.0275` — **not resolved** | `0.0549 ± 0.0549` — **not resolved** |

   Both quantities come out at or below the uncertainty their own converged
   brackets leave, at both corners. The honest statement is therefore a
   **bound, not a width**: `|systematic offset| < 0.028 mV` and
   `band < 0.055 mV`, i.e. both are at least `32×` smaller than the
   `1.7578 mV` half-LSB (DR-003 Item 3) a correct bit trial must resolve.

4. **The measurement's own negative control passed.** `tt`/27 °C on a
   mismatch-free symmetric DUT must return ~0 by construction, and does. The
   coarse scan is a *symmetric signed* grid specifically so a sign or
   direction error would show up as a one-sided ladder; instead the decision
   delays match across every probed `±|Vindiff|` pair to the last recorded
   digit at both corners (`1.1125 ns` at `±50 mV`, `2.0275 ns` at
   `±1.7578 mV` at `tt`; `1.0925`/`2.6275 ns` respectively at `ss`/−40 °C).
   The only probe in the campaign that failed to resolve inside the window is
   `Vindiff = 0` at `ss`/−40 °C — the metastability control, which has no
   correct answer to get right. The bisection never consumes it as a bracket
   and does not count it as band corroboration.

5. **Consistency with the prior pick-off record, checked arithmetically rather
   than asserted.** `20260821-071918-433a294` reports mean `35.2441 mV`, stdev
   `97.0825 mV` over `N = 16` `tt_mm` draws. For `N = 16` the standard error
   of that mean is `97.0825 / √16 = 24.2706 mV`, so that record's *own*
   estimate of the systematic (mean) term is `35.2441 ± 24.2706 mV` —
   `1.45` standard errors from zero, which is not a detection of a systematic
   offset. A near-zero systematic boundary is therefore **consistent** with
   it, not in tension; the comparison is a statement about sample size.

6. **Scope, verified and stated rather than glossed.** This is a
   **schematic-level** measurement. The comparator's committed layout
   extraction is DRC/LVS-clean but **device-level only** —
   `layout/comparator/reports/LATEST`'s own record states it is not a
   parasitic extraction — so the sibling's specific *post-layout* finding
   cannot be replicated in this repo today, and #515 scoped that out
   explicitly. Nothing in this record tests what a parasitic extraction would
   add.

**Clean-room note.** Only the *algorithm shape* crossed from the sibling repo
(classify both polarities; bisect two boundaries over the input axis; treat
near-boundary solver crawl as a budget floor, not a circuit outcome). The
implementation is re-derived against this repo's own primitives, that repo's
source was never inspected (#515 records it was described secondhand), and no
netlist, sizing, corner choice, or measured value from it is introduced —
per `CLAUDE.md`'s clean-room rule. Its numbers are referred to in this record
only by *shape* ("a nonzero systematic offset", "a wide band"), never by value.

## Decision

**No new `spec/target-spec.md` row — neither an offset row nor a
dead-band/non-decision row — is added by this record.** This is a scoping
call, not a numeric one, and the reasoning is specific to which term was
measured:

1. **A *systematic* offset row is not warranted.** The quantity is bounded
   below `0.028 mV` at both measured corners — `≈ 1/63` of a half-LSB. A row
   bounding it would be met by `>30×` on the day it was written, would gate no
   design decision, and would add a verification obligation (a full PVT
   campaign per `spec/target-spec.md`'s corner contract) for a term that is
   not the one at risk.

2. **A dead-band / non-decision row is not warranted either.** The band is
   likewise below the measurement floor (`< 0.055 mV`) at both corners,
   including the slow/cold corner where a finite evaluate window is most
   likely to produce one. The comparator resolves at every nonzero overdrive
   probed, down to `0.0549 mV` — `1/32` of a half-LSB — and does so in
   `5.0475 ns` at `ss`/−40 °C, inside DR-006's `83.333 ns` worst-case
   bit-trial phase by `≈ 16×` (`2.6275 ns`, `≈ 32×`, at the half-LSB
   overdrive the SAR actually has to resolve).

3. **The term that *would* need a row is the random/mismatch offset, and this
   record declines to set a number for it.** That term is large — stdev
   `97.0825 mV`, range `[−136.4332, +224.9353] mV` at the current `W = 4 µm`
   input pair, i.e. `≈ 55×` the half-LSB at 1σ — and it is the one that would
   actually cost conversions. It is not given a row here because **two
   prerequisites are missing, and inventing the row without them would be
   exactly the "invent settled numbers to replace the drafts" failure
   `CLAUDE.md` forbids**:
   - **No derived allocation.** DR-003 Item 4 split the non-quantization error
     budget three ways for *noise*; no comparator-offset allocation has been
     derived from the ADC's own ENOB/INL budget. A bound with no budget behind
     it is a guess with a `≤` in front of it.
   - **No adequate measurement.** The only σ this repo has comes from the
     method DR-004 itself labels *"an upper-bound / order-of-magnitude
     statistic … not a precise linear extraction"*, at `N = 16`, at one
     mismatch corner. That is a first-look sample, not a basis for a ratified
     bound.

4. **The methodology question IS settled, and the escalation path is now
   mechanised.** `offset-bisect` is committed, tested, and corner-parameterised
   (`--points`). Running it **per Monte Carlo draw** — a distribution of
   decision *boundaries* rather than of pick-off *values* — is the measurement
   that would produce a defensible σ with no calibration-range caveat. This
   record names that as the gate on a future offset row; it does not run it
   (see "Open items" for why).

5. **Do not port the sibling's row.** DR-011 set the precedent for adopting a
   sibling canary's ratified row verbatim as an interim choice, and that
   precedent is deliberately **not** followed here. DR-011's subject (kickback)
   had *no* bound at all and a measured baseline missing one by `≈ 14.7×` — an
   interim row there bought a real gate. Here the schematic-level block already
   measures `>30×` inside any plausible bound, so a ported row would gate
   nothing while implying this repo had evidence for a number it did not
   derive. The sibling's finding is *post-layout*; the correct response to it
   is a post-layout measurement, not a borrowed row.

## Alternatives considered

- **Add a DRAFT systematic-offset row now, bounded at (say) a half-LSB,
  mirroring the sibling's companion row.** Rejected. The cost of *not* adding
  it is that `spec/target-spec.md` continues to carry no offset row, so no
  campaign is mechanically obliged to measure one — a real completeness gap,
  and the same one DR-003 left open for gain error. The cost of adding it is
  worse: it would be a row this block passes by `>30×` at schematic level
  while the term that actually threatens conversions (random offset, `≈ 55×`
  the half-LSB at 1σ) stays unbounded, and a reader would reasonably conclude
  the offset question was handled. A row that looks like a gate but gates
  nothing is worse than a named gap, which is why this record names the gap
  instead (and writes it into `spec/target-spec.md`'s own open-items list so it
  cannot be lost).

- **Adopt the sibling's proposed companion row verbatim, as DR-011 did for
  kickback.** Rejected — see Decision §5. The cost of not doing it is the loss
  of DR-011's genuine benefit: an interim row creates an obligation where none
  existed. That benefit does not apply when the measured value is already
  `>30×` inside the bound; and unlike kickback, the finding being ported rests
  on a *netlist class this repo cannot build yet*, so the row would be
  unfalsifiable here.

- **Set a random-offset (σ) row from the existing `N = 16` pick-off
  distribution.** Rejected. The cost of not doing it is that the largest known
  comparator non-ideality stays un-bounded by the spec. But DR-004 already
  disclaims that distribution's magnitudes as order-of-magnitude for the
  larger draws, and ratifying a bound from it would convert a stated caveat
  into a spec line — the precise move `CLAUDE.md`'s "the spec is a gate" rule
  exists to prevent. The honest alternative is to name what makes it
  ratifiable, which Decision §3 does.

- **Narrow `PICKOFF_NS` or fit a nonlinear calibration curve** (the two
  escalations DR-004 itself named). Not taken. Both keep the pick-off framing
  and so keep its central weakness: an inferred input-referred voltage, whose
  validity depends on a calibration whose range must then be defended. The cost
  of not taking them is that DR-004's named paths remain unexplored and the
  existing `offset` subcommand is unimproved — it is kept, unchanged, as the
  random-term baseline. Bisecting the boundary avoids the calibration entirely,
  which is why it was taken instead.

- **Run the full nine-point ratified PVT grid before deciding.** Rejected on
  cost against what it would change. Each probe is a full `20 ns` transient at
  a `0.005 ns` step and the campaign is ~15 probes per corner point, run
  serially on a shared dispatch worker where no process may outlive its session
  (`.loom/docs/long-running-compute.md`). Two points — the nominal *negative
  control* and the slow/cold *stress* point — are what the decision in front of
  this record actually turns on: a systematic term `>30×` below the half-LSB at
  the worst of the two is not going to become row-worthy at `ff`/125 °C. The
  cost of not sweeping is real and is stated: this record's bound is a
  two-point bound and must not be quoted as a PVT-complete one.

- **Wait for comparator PEX and decide the row post-layout.** Rejected as a
  *blocker*, kept as *future work*. The schematic-level question DR-004 asked
  is answerable now and has been open since DR-004; deferring it indefinitely
  on evidence that does not exist yet is how an open item becomes permanent.
  The cost of deciding now is that a post-layout measurement could reverse the
  conclusion — which is precisely why "Open items" below names it as the
  trigger to supersede this record rather than pretending it cannot happen.

## Spec lines affected

**No row of `spec/target-spec.md`'s Target table changes.** No row is added,
removed, or re-valued, and no ratified number moves. Specifically:

- **No offset row** is created (the table still has none — unchanged by this
  record, by decision rather than by omission).
- **No dead-band / non-decision row** is created.
- **The ratified comparator input-referred-noise row is untouched.** Noise
  (`≤ 1.0148 mV rms` baseline, DR-003 Item 4) and decision offset are
  different quantities; nothing here relaxes, reinterprets, or re-derives it.
- **One documentation addition**: a bullet is added to
  `spec/target-spec.md`'s "Numeric rows — Not ratified by this record — still
  open, named explicitly, not guessed" list, recording that the offset /
  dead-band row question was *asked and answered* by this record and naming
  the two prerequisites for revisiting it. This mirrors the existing
  gain-error bullet's pattern (a flagged spec-completeness gap with no
  invented row), so the question cannot be silently re-opened or forgotten.
  Because the Target table itself is unchanged, `sim/spec-coverage.json` needs
  no new entry.

## Consequences

1. **DR-004's spec-row Open item is closed** — "*a future record should decide
   whether either belongs in the table*" now has an answer for offset: **no,
   not yet, and here is what would change that.** DR-004 is **not** edited;
   per the template's rule its findings stand as written, and this record is
   cross-referenced from its Open items list.

2. **DR-004's precise-extraction Open item is narrowed, not closed.** A precise
   decision-referred extraction now exists and is committed — but for the
   **systematic** term only. The random term still has no precise extraction;
   the per-draw bisection in "Open items" is what would close it. A reader must
   not take this record as having closed that item.

3. **The regeneration-time half of DR-004's Open item is untouched.** This
   record decides nothing about a regeneration-time / decision-delay spec row.
   The new evidence is relevant to it (decision delay at the half-LSB
   overdrive: `2.0275 ns` at `tt`/27 °C, `2.6275 ns` at `ss`/−40 °C, both
   `>30×` inside DR-006's bit-trial phase) but that row is a separate decision
   and stays open.

4. **A new verification obligation is created — a small one.**
   `sim/comparator-decision/run.py` gains a committed subcommand
   (`offset-bisect`) with unit tests (`sim/tests/test_offset_bisect.py`,
   PDK-free, in `npm run test:unit`). The tests are the mechanism that keeps
   the measurement honest: the bisection's boundary direction, polarity
   classification, dead-band detection, and failure-reporting are each driven
   by a synthetic DUT whose true answer is known by construction, because on
   real analog data a wrong answer and a right one are both just a float.

5. **The bad consequence, stated plainly: this record's bound is two points
   wide and schematic-only.** It does not bound a manufactured part (mismatch
   is disabled by design in the measurement), does not generalise past `tt`/27 °C
   and `ss`/−40 °C, does not generalise past the `20 ns` evaluate window, and
   says nothing about a parasitic-extracted DUT. Anyone quoting
   "`offset < 0.028 mV`" as a property of this comparator will be wrong.
   `offset-bisect --points` runs any other PVT point by accumulation, which is
   the intended way to widen it.

6. **A reversal path is left open on purpose.** Because no row was added,
   adding one later costs nothing beyond a new decision record — whereas
   retracting a ratified row would require superseding it. If comparator PEX
   or a per-draw campaign produces a systematic term or a band at half-LSB
   scale, this record is superseded, not patched.

## Open items

- **A per-Monte-Carlo-draw boundary bisection** (a distribution of decision
  boundaries, rather than of pick-off values) — the measurement that would
  make a random-offset σ ratifiable without DR-004's calibration-range caveat.
  Mechanically possible today (`offset-bisect` plus the `offset`
  subcommand's existing `rndseed` plumbing), deliberately not run here: at
  ~15 serial transient probes per *draw*, an `N = 16` campaign is two orders of
  magnitude more ngspice time than this record's two points and does not fit a
  single session on a shared dispatch worker. Owner: a follow-up issue filed
  from #515, or #29's offset campaign scale-up.
- **A derived comparator-offset allocation from the ADC error budget** —
  DR-003 Item 4's three-way split covers noise only. Without an allocation
  there is no defensible number for an offset row even once σ is measured
  precisely. Owner: a future decision record, alongside or inside the σ
  campaign above.
- **Post-layout (PEX) replication** — the sibling's finding is post-layout and
  this repo's comparator extraction carries no parasitics
  (`layout/comparator/reports/LATEST`). A `klt pex` pass on that sub-block, and
  an extracted netlist wired into `sim/comparator-decision/`, would let
  `offset-bisect` run the actual comparison. **This is the named trigger to
  supersede this record**: a systematic offset or band at half-LSB scale
  post-layout would change the answer in Decision §1–2. Owner: a follow-up
  issue once comparator PEX exists; explicitly out of scope of #515.
- **A regeneration-time / decision-delay spec row** — the other half of
  DR-004's Open item, untouched here (Consequences §3).
- **The `ss`/−40 °C comparator *headroom* margin** (DR-003 Item 1 / DR-004's
  Alternatives) — still open. This record's slow/cold probes are adjacent
  evidence (the latch does resolve at `ss`/−40 °C down to `0.0549 mV`
  overdrive) but headroom is a Vth/overdrive question, not a decision-boundary
  one, and this record does not claim to have answered it.
- **Ratification** — like DR-003/DR-011/DR-019, nothing here is binding until
  the operator approves the PR resolving #515. Until then this is a proposed
  record and `spec/target-spec.md`'s table remains exactly as it was.

# DR-014: Kickback mitigation: a static preamp is not adopted, and DR-004 Decision §1 stands

- **Status**: proposed. Like DR-004 and DR-011, this record ratifies nothing.
  It is an input to a future operator ratification act, following the
  ratification-via-PR policy DR-011's header cites.
- **Date**: 2026-09-25
- **Decided by**: Builder agent, issue #349
- **Supersedes**: none. This record re-examines
  [DR-004](DR-004-comparator-topology-and-noise-budget.md) Decision §1 ("No
  static preamp") against new evidence and **keeps** it. It replaces no
  decision. DR-004 gains a header back-reference to this record and nothing
  else.
- **Superseded by**: (none while this record stands)
- **Re-examined**: 2026-09-25, by
  [DR-016](DR-016-kickback-headroom-neutral-mitigation-measurement.md) (issue
  #434). It answered this record's Consequences §4 condition for the
  cross-coupled-neutralization class: measured, and it does not close the
  gap. **This record's Decision stands.** DR-016 supersedes nothing here, and
  this line is the only edit.
- **Related**: #349 (this record), #390 (follow-on: common-mode / differential
  split of the kickback measurement, the first gate named below), #434
  (follow-on: measuring the headroom-neutral mitigation classes named in
  Consequences §4 / Open items below, filed once #390 confirmed a
  differential component above the bound; answered for cross-coupled
  neutralization by [DR-016](DR-016-kickback-headroom-neutral-mitigation-measurement.md)),
  [DR-011](DR-011-comparator-kickback-target-row.md) (the DRAFT Kickback row
  and its "Mitigation selection" open item, which this record closes),
  [DR-004](DR-004-comparator-topology-and-noise-budget.md) Decision §1,
  [DR-003](DR-003-numeric-spec-derivation.md) Item 1 (the headroom stack),
  `sim/comparator-decision/records/20260924-041815-afcb1b5.md` (kickback
  baseline), `sim/comparator-decision/records/20260906-074451-7724af3.md`
  (decision delay over the ratified corners),
  `sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md` (the
  block's only power measurement)

## Context

DR-011 added a DRAFT Kickback row: `≤ 5 mV` target and `≤ 2 mV` stretch, as
peak pin disturbance into a `1 kΩ` series source over a single decision edge.
The bound was adopted verbatim from sibling `2AMLogic/sky130-comparator` as an
interim choice. This repo's comparator measures **73.3673 mV** at
`Vindiff = +50 mV`, `tt`/27 °C, 1.8 V (baseline record, "Overall" line). That
is `≈ 14.7×` the target and `≈ 36.7×` the stretch (DR-011 Decision §3). Issue
#349 reports same-PDK prior art. Their proposed DR-004 put a static
resistive-load NMOS preamp ahead of their StrongARM latch and reached
`1.89 / 1.86 / 1.77 mV` at `tt`/27 °C, `ss`/−40 °C, and `ff`/125 °C. Their
earlier clock-edge shaping (their DR-003) went from `144.60 → 85.71 mV`. All
sibling figures here are quoted from #349's body, which the Curator
cross-checked against their merged record. None were re-measured here. No
sibling netlist, sizing, or layout was consulted (clean room, `CLAUDE.md`).

Adopting that finding here is not a drop-in change. It would overturn this
repo's own DR-004 Decision §1 (lines 86–119). That decision rests on
DR-003 Item 1's stack
`V_cm,min = Vth,n + V_ov,in + V_dsat,tail = 626.9 + 125 + 125 = 876.9 mV`
against `V_cm = 900 mV`, a **23.1 mV** margin at `tt`/27 °C (DR-003 lines
128–136). #349 asks this record to weigh (a) the gap, (b) that headroom
rationale against a static preamp at 1.8 V, and (c) whether a cheaper
mitigation class closes the gap.

## Decision

**A static preamp is not adopted. DR-004 Decision §1 stands, and no other
mitigation is adopted by this record either.** The Kickback row stays DRAFT,
unchanged and unmet. The next step is a measurement (#390), not a
topology change. The reasons follow, in order (a), (b), (c).

**(a) The gap is real, but most of it is common-mode, and whether the row's
quantity matters inside the loop is not established.** The baseline's own
`Vindiff = 0 mV` control reads `−70.3419 mV` at `t = 5.108 ns`. That is
`95.9 %` of the `73.3673 mV` worst case, and it arrives about 8 ps after the
CLK ramp ends. With zero input the testbench is symmetric, so that
disturbance is **common-mode by construction**: VINP and VINN move together.
A differential top-plate CDAC rejects common-mode disturbance to first order.
The component that lands on a decision is the differential one, and **no
committed record measures it**. An exploratory re-run of the committed deck
was made while drafting this record. It was not written as a record, so it
is disclosed here and not relied on as evidence. It read a differential peak
of `≈ 10.9 mV` at `Vindiff = +50 mV`, with both components back to zero by
`t = 10 ns`. If a committed run confirms this, the differential part alone
also misses 5 mV. The row cannot simply be waved away. It does mean the
gap is not yet characterised well enough to size a mitigation against, and
#390 measures it. DR-011's own open items add a second caveat: its bound is
adopted, not derived, and the accuracy-binding in-loop quantity is the
residual at the next decision on a floating top plate. The `1 kΩ` bench
does not model that condition.

**(b) The headroom argument binds a static preamp harder than DR-004 §1
said.** Evaluated against a static preamp, DR-004 §1's reasoning is wrong in
one direction and too weak in the other:

- **It was over-conservative for the latch it was written about.** The
  876.9 mV stack assumes a saturated tail. The dynamic latch's tail is a
  clocked switch. At the ratified `−10 %` supply, where `V_cm` tracks to
  `0.81 V`, the stack gives `810 − 876.9 = −66.9 mV`, yet the latch resolves
  `0.5 mV` in `4.3575 ns` (`tt_27c_1.62v`, the binding corner in
  `20260906-074451-7724af3`). All 27/27 input-driven points decided at all
  nine one-at-a-time ratified corner points.
- **It is accurate for a static preamp.** A continuously biased
  differential stage needs a saturated tail to set its bias, and that is
  exactly the stack DR-003 wrote down. At 1.62 V it is already `−66.9 mV`
  short at `tt`/27 °C with DR-003's planning overdrives. DR-003 expects
  `ss`/−40 °C to be worse, and that point is still unevaluated (DR-004 Open
  items). Flipping to a PMOS-input preamp makes this worse, not better. With
  the same planning values, `V_DD − V_cm = 900 mV` against
  `|Vth,p| + V_ov + V_dsat = 979.9 + 250 = 1229.9 mV` is `−329.9 mV`
  (DR-003 line 115).
- **The sibling's own record shows the kind of failure that risk
  predicts.** #349 reports that their preamp design no longer resolves a
  `0.5 mV` input at `ss`/−40 °C within 400 ns, against `2.5575 ns` before the
  preamp. This record does not claim a cause. But a SAR comparator must
  resolve sub-LSB inputs (half an LSB is `1.7578 mV`) inside DR-006's
  provisional `83.333 ns` bit-trial phase. Decision delay is currently the
  one comparator property this repo has PVT-complete, at `19.1×` margin. A
  preamp would put that at risk in exchange for a bench figure that is
  mostly common-mode.
- **The static current is large relative to this block.** The sibling
  preamp draws `~95 µW` static at 1.8 V. This whole ADC core measures
  `27.971 µW` at `tt_27c_1.80v`, 12 MHz (`20260912-002315-9aaf1ca`, Power
  table). A comparable bias would multiply the block's measured power by
  about 4.4 (`(27.971 + 95) / 27.971`). The Power row has no threshold
  ("provisional, minimise at rate"), so this is a cost, not a
  disqualification. Power-gating the preamp between conversions could reduce
  it, and that has not been evaluated.

**(c) The cheaper classes do not close the gap on today's evidence.**
Clock-edge shaping achieved a `144.60/85.71 = 1.69×` reduction in the
sibling. Applied here at the same ratio, 73.3673 mV becomes `≈ 43.5 mV`,
still `≈ 8.7×` the target, and it costs decision time. It is therefore not
adopted as a gap-closer. The sibling's double-tail result (`7.5 mV`) and
input-isolation switches both showed a roughly 1:1 kickback/speed trade
there. The double-tail latch is still worth noting: its first stage is also
clocked, so it avoids the static-bias headroom and power cost in (b). It
remains an unevaluated alternative, as DR-004's Alternatives already say.
Two generic techniques are unmeasured anywhere in this program:
cross-coupled neutralization, which targets the differential component, and
complementary-clock charge compensation, which targets the common-mode
component. Neither is headroom-costly. Choosing among them needs #390's split.

## Alternatives considered

- **Adopt a static preamp and supersede DR-004 §1.** This is the only
  class with same-PDK evidence of meeting the bound. It is rejected for now
  because of (b): known headroom risk at ratified corners, a demonstrated
  small-input regeneration hazard, and about 4.4× block power. All of that
  would be paid against a gap whose decision-relevant component is
  unmeasured. **Cost of not choosing it:** the row stays unmet, perhaps for
  some time, and the one proven route is deferred.
- **Adopt clock-edge shaping now as a partial fix.** Rejected. At the
  sibling's ratio it leaves `≈ 8.7×` the gap, and it spends decision-time
  margin on a mostly common-mode peak.
- **Supersede or relax DR-011's bound.** Rejected. `CLAUDE.md` forbids
  relaxing a row to make a result pass. Re-deriving the bound is DR-011's
  own open item, for a record with a budget behind it.
- **Amend DR-004 in place instead of writing a new record.** Rejected
  because nothing in DR-004 changes. A standalone record plus a header
  pointer keeps DR-004's body as written.

## Spec lines affected

`spec/target-spec.md` **Kickback** row: the value, stretch, corner scope,
and **DRAFT** status are unchanged. Only its note gains a pointer to this
record's disposition. No other row changes. `sim/spec-coverage.json`'s
Kickback `tracking` field is repointed from #349 to this record and #390,
and `sim/spec-coverage.md` is regenerated from it.

## Consequences

1. DR-011's "Mitigation selection" open item is answered for now: no
   preamp, and no adopted mitigation. The spec table keeps advertising a
   `≈ 14.7×` gap. That is intended and honest, but it is still a gap.
2. DR-004 Decision §1 now rests on a sharper argument than before. The
   latch has more headroom than §1 claimed. A static preamp has less.
3. Any later preamp proposal carries a specific burden. It must show the
   stage biases at `tt_27c_1.62v` and at `ss`/−40 °C (the stack is
   negative at the former with planning values), and it must re-run
   `regen-corners` down to `0.5 mV`.
4. If #390 confirms a differential component above the bound, this record's
   "not adopted" becomes weaker, and the headroom-neutral classes in (c)
   must then be measured before a preamp is reconsidered.

## Open items

- **#390**: common-mode / differential split, including a sub-LSB `Vindiff`
  point. This is the first gate.
- **Headroom-neutral candidates**: a double-tail latch, cross-coupled
  neutralization, and complementary-clock compensation, tracked as **#434**,
  filed once #390's result confirmed a differential component above the
  bound at the large-overdrive point (the condition Consequences §4 above
  names). Cross-coupled neutralization is now measured
  ([DR-016](DR-016-kickback-headroom-neutral-mitigation-measurement.md)) and
  does not close the gap; the double-tail latch and complementary-clock
  compensation remain unmeasured.
- **A preamp headroom probe**, if the question reopens. It would cover
  `1.62 V` and `ss`/−40 °C, and include `nfet_01v8_lvt`, which is listed in
  DR-001's core device table but has never been probed in this repo. A
  lower-Vth input pair is the most plausible way to make the stack fit.
- **The in-loop residual measurable and full-corner kickback campaign**:
  unchanged from DR-011's open items.
- **Ratification**: nothing here is binding until an operator act rules on
  it.

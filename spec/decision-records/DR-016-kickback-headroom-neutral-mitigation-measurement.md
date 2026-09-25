# DR-016: Cross-coupled neutralization measured — it does not close DR-014's gap, and DR-014's "not adopted" call stands

- **Status**: proposed. Like DR-014, this record ratifies nothing. It is an
  input to a future operator ratification act, following the
  ratification-via-PR policy DR-011's header cites.
- **Date**: 2026-09-25
- **Decided by**: Builder agent, issue #434
- **Supersedes**: none. This record re-examines
  [DR-014](DR-014-comparator-kickback-mitigation-no-static-preamp.md)'s
  Consequences §4 condition against new evidence and **keeps** DR-014's
  Decision. DR-014 gains a header back-reference to this record and nothing
  else, the same convention DR-004 carries for DR-014 itself.
- **Superseded by**: (none while this record stands)
- **Related**: #434 (this record's own issue), [DR-014](DR-014-comparator-kickback-mitigation-no-static-preamp.md)
  (whose Consequences §4 this record answers), #390 (the split measurement
  that triggered Consequences §4's condition), [DR-004](DR-004-comparator-topology-and-noise-budget.md)
  Decision §1 (the "no static preamp" call this record does not disturb),
  `sim/comparator-decision/records/20260925-182138-23ad4d8.md` (the
  cross-coupled-neutralization measurement this record weighs),
  `sim/comparator-decision/records/20260925-050027-0259924.md` (#390's
  baseline split the measurement above compares against),
  `sim/comparator-decision/testbench/comparator_core_neutralized.spice` (the
  EXPERIMENTAL DUT variant measured)

## Context

DR-014 Consequences §4 stated a condition: "If #390 confirms a differential
component above the bound, this record's 'not adopted' becomes weaker, and
the headroom-neutral classes in (c) must then be measured before a preamp is
reconsidered." #390 closed with a differential component of **10.9153 mV** at
`Vindiff = +50 mV` (`≈ 2.2×` the DRAFT `≤ 5 mV` target) — above the bound at
the large-overdrive point, satisfying that condition. DR-014 (c) and its Open
items name three headroom-neutral classes, none measured anywhere in this
program at the time: a double-tail latch, cross-coupled neutralization
(targets the differential component), and complementary-clock charge
compensation (targets the common-mode component). Issue #434 was filed to
measure them; per its own acceptance criteria, landing any ONE closes real
ground without requiring the other two, and none is required to reach a
specific number — `CLAUDE.md`'s "no claim without a testbench" rule applies,
not a target result.

**What was measured.** Cross-coupled neutralization, added to the same
11-device StrongARM-class latch `design/comparator.sch` netlists to
`sim/comparator-decision/testbench/comparator_core.spice`, via a sibling
fragment (`sim/comparator-decision/testbench/comparator_core_neutralized.spice`,
an EXPERIMENTAL, hand-authored, non-adopted variant — no `design/*.sch` file
is touched). Two capacitors, `CNEUT_A`/`CNEUT_B` = 1.0 fF, couple each input
transistor's drain to the OPPOSITE input transistor's gate, sized as a
first-order physics estimate of the input pair's own BSIM4 `CGDO` overlap
term (`sky130_fd_pr__nfet_01v8`'s `CGDO = 2.54e-10 F/m × overlap_mult`; at
`tt`, `overlap_mult = 0.9642` per that corner's own `.param` line, giving
`2.449068e-10 F/m`, verified directly against the installed PDK model file at
`sim/pdk.json`'s pinned commit — matching the DUT fragment's own header
figure exactly), not a fitted or hand-tuned value, and not reverse-engineered
from any other party's design (`CLAUDE.md`). The measurement
(`sim/comparator-decision/records/20260925-182138-23ad4d8.md`) reuses #390's
exact stimulus, decomposition, and Vindiff grid (0 mV symmetry control,
half-LSB `+1.7578 mV`, `+50 mV` large-overdrive) at the same single corner
(`tt`/27 °C/1.8 V) #390 itself used, so the two records are directly
comparable without normalization.

**Result.** At `Vindiff = +50 mV`, the worst-case peak per-pin disturbance
moves from **73.3673 mV** (baseline) to **69.9461 mV** (`−4.7 %`), and the
worst-case peak DIFFERENTIAL deviation — the component a differential
top-plate CDAC does not reject, and the one this technique specifically
targets — moves from **−10.9153 mV** to **−10.8355 mV** (`−0.7 %`). The
worst-case peak common-mode deviation is effectively unchanged (`−70.4415 →
−67.0662 mV` at `+50 mV`; this technique does not target the common-mode
component and the small movement is incidental capacitive loading, not a
mitigation effect). Both figures round-trip: this record's author re-ran
`python3 sim/comparator-decision/run.py kickback-neutralized` independently
of the WIP that produced the committed record and reproduced every measured
value to the last stated digit.

**Why the effect is this small.** The input pair (`XM_INN`/`XM_INP`, `W = 4
µm`) is not the dominant source of switching charge on this latch: the tail
switch (`XM_TAIL`, `W = 8 µm`) and the four reset PMOS devices (`XM_RST_*`,
`W = 4–16 µm`) are larger and gate directly off `CLK`, the signal doing the
actual switching in this testbench's single reset→evaluate edge. Cross-coupled
neutralization cancels only the differential charge coupled through the input
pair's own `Cgd` — a real but small fraction of the total charge landing on
`VINP`/`VINN` through every coupling path at once. A larger neutralization
capacitor was not swept as a committed record (the DUT fragment's own header
discloses an *informational*, uncommitted 0/0.5/1/2/4/8 fF exploratory sweep
that found the 1 fF point stays inside the range that helps rather than
hurts, but does not report a value that would close the gap) — this record
does not claim that a differently-sized capacitor would perform much better
or worse; that is unmeasured.

## Decision

**Cross-coupled neutralization, at this sizing and this one PVT point, does
not close enough of DR-014's gap to reconsider adopting a mitigation.
DR-014's Decision stands: no static preamp, no mitigation adopted. The
Kickback row stays DRAFT, unchanged and unmet.**

A `0.7 %` reduction in the worst-case peak differential deviation is not a
result any mitigation-adoption decision could rest on — it is well inside the
kind of run-to-run variation a single-corner, single-sizing measurement
carries, and it leaves the differential component at `10.8355 mV`, still
`≈ 2.2×` the DRAFT `≤ 5 mV` target at the large-overdrive point. DR-014
Consequences §4's own wording is conditional ("must then be measured before a
preamp is reconsidered") — measuring is the obligation the condition created,
not adopting. That obligation is now partly discharged: cross-coupled
neutralization is measured, and on this evidence it is not a gap-closer. The
other two headroom-neutral classes DR-014 (c) names — a double-tail latch and
complementary-clock charge compensation — remain unmeasured; per issue #434's
own acceptance criteria, measuring any one of the three was sufficient to
close real ground, and this record does that for one of them without
overreaching into the other two.

## Alternatives considered

- **Treat the `−0.7 %` differential improvement as sufficient grounds to
  reconsider a preamp.** Rejected. DR-014 (b) already established that a
  preamp's headroom and power cost are the binding objections, not the
  absence of a cheaper alternative; a measurement this small does not weigh
  against those costs, and DR-014's own condition asks whether a
  headroom-neutral class closes the gap, not whether it moves it at all.
- **Sweep the neutralization capacitor value as part of this record, to see
  if a larger value performs meaningfully better.** Rejected as out of scope
  for issue #434, whose acceptance criteria are satisfied by measuring one
  class at minimum at the baseline corner. The DUT fragment's own
  informational (uncommitted) exploratory sweep found the chosen 1 fF value
  stays inside the range that helps rather than hurts; a committed sweep,
  should headroom-neutral mitigation be revisited later, is future work, not
  answered here.
- **Also measure the double-tail latch and complementary-clock compensation
  classes in this same pass.** Rejected as unnecessary scope for this record:
  issue #434 states any one measured class closes real ground, and this
  record's own negative result does not change that — a negative result on
  one class is still an answer, not a reason to chase the other two
  immediately. They remain open (see Open items).
- **Supersede or relax DR-011's bound to make this measurement read as a
  pass.** Rejected. `CLAUDE.md` forbids relaxing a row to make a result pass;
  the DRAFT Kickback row and its numbers are untouched by this record.

## Spec lines affected

None. `spec/target-spec.md`'s Kickback row — value, stretch, corner scope,
and DRAFT status — is unchanged. `sim/spec-coverage.json`'s Kickback
`tracking` field gains a pointer to this record alongside DR-014/#390/#434,
and `docs/chipalooza/challenge-4-proposal.md`'s Kickback row is updated to
cite it in place of the prose noting #434 as untracked open work — that gap
is what this record and issue #434 close. `sim/spec-coverage.md` is
regenerated from the JSON index.

## Consequences

1. DR-014 Consequences §4's condition is now answered for cross-coupled
   neutralization specifically: measured, and it does not close the gap.
   DR-014's Decision is unweakened by this record — if anything it is
   reinforced, since the one headroom-neutral class this record checked
   turned out not to be a cheap fix either.
2. Issue #434's mandatory 4th acceptance item (this record, plus the doc/
   index citation updates) is satisfied without measuring the remaining two
   headroom-neutral classes, per that issue's own "any ONE closes real
   ground" scoping. #434 can close on this record.
3. The double-tail latch and complementary-clock charge compensation classes
   DR-014 (c) names remain unevaluated. Nothing in this record forecloses
   measuring them later; nothing in it obliges it either. If a future
   preamp reconsideration is proposed, DR-014 Consequences §3's own burden
   (headroom at `tt_27c_1.62v` and `ss`/−40 °C, a re-run of `regen-corners`
   down to `0.5 mV`) still applies, unchanged by this record.
4. A larger or differently-implemented neutralization capacitor might perform
   better than this record's physics-derived 1 fF sizing — that is
   unmeasured and this record does not claim otherwise (see "Why the effect
   is this small" above and "Alternatives considered").

## Open items

- **The double-tail latch and complementary-clock charge compensation
  classes**: still unmeasured anywhere in this program. Tracked under
  DR-014's own Open items; no new issue is filed for them by this record,
  per issue #434's explicit scope guidance not to over-reach.
- **A neutralization-capacitor value sweep**, committed as a record rather
  than the DUT fragment header's informational, uncommitted exploration —
  only worth doing if this mitigation class is revisited.
- **A preamp headroom probe**, if the question reopens: unchanged from
  DR-014's own Open items (covers `1.62 V` and `ss`/−40 °C, and
  `nfet_01v8_lvt`).
- **The in-loop residual measurable and full-corner kickback campaign**:
  unchanged from DR-011's and DR-014's open items.
- **Ratification**: nothing here is binding until an operator act rules on
  it.

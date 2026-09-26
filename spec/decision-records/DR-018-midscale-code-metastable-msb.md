# DR-018: The mid-scale (`+0.00·V_REF`) captured code is a coin flip on a metastable MSB decision — supply-impedance code deltas may not be read on it

- **Status**: proposed. This record ratifies no spec row and changes no number
  in `spec/target-spec.md`. It scopes how a class of already-committed evidence
  must be read, following the ratification-via-PR policy DR-011's header cites.
- **Date**: 2026-09-26
- **Decided by**: Builder agent, issue #455
- **Supersedes**: none. It adds a reading rule to
  [DR-012](DR-012-analog-ground-pad.md),
  [DR-015](DR-015-package-parasitic-assumption.md) and
  [DR-017](DR-017-on-die-decoupling-budget.md); each gains a back-reference to
  this record beside its own mid-scale citation and nothing else, the same
  convention DR-014 carries for DR-016.
- **Superseded by**: (none while this record stands)
- **Related**: #455 (this record's own issue), #409 (the corner campaign that
  surfaced the anomaly), `sim/supply-impedance-sensitivity/records/20260926-162049-476a8ab.md`
  (the mid-scale boundary probe this record rests on),
  `sim/supply-impedance-sensitivity/records/20260926-050045-8e62675.md` (the
  ratified-grid record whose `package-r-only@fs_27c_1.80v` point the probe
  re-runs), `sim/full-conversion-transient/records/20260912-011519-9aaf1ca.md`
  (the committed per-trial decision-margin trace this probe's instants are
  identical to), [DR-004](DR-004-comparator-topology-and-noise-budget.md)
  Decision §2 (the input-referred noise budget this record measures the margin
  against; DR-004 is itself `proposed`, so the band is a stated budget, not a
  ratified line), [DR-009](DR-009-comparator-output-load-balance-and-half-lsb-offset.md)
  (the half-LSB offset work that established the per-trial margin probe),
  [DR-003](DR-003-numeric-spec-derivation.md) (`LSB = 2·V_REF/2^N`, `V_REF = V_DD`)

## Context

`sim/supply-impedance-sensitivity/` compares five supply-return networks by
re-running one stimulus and reading (a) the die-side rail excursion and (b) the
captured code, on three mid-scale inputs. Its ratified-grid record
(`20260926-050045-8e62675`) reports one code movement that its own stated
mechanism cannot produce: at `fs_27c_1.80v` the `package-r-only` arm — the
control plus a ~0.1 Ω series resistor per supply terminal, **0.057 mV** of
die-side ground movement — reads **505** on the `+0.00·V_REF` input against the
control's **511**, while the `package` and `no-gnd-pad` arms at the same corner,
with **11.4 mV** and **13.7 mV** of ground movement (~200×), read the control's
511 exactly. A supply-return mechanism monotone in the excursion cannot order
those three that way, so something else moves that code. Issue #455 was filed to
name it rather than average it away.

**What was measured** (`sim/supply-impedance-sensitivity/records/20260926-162049-476a8ab.md`,
`run_supply_impedance.py --midscale-probe`, at `fs_27c_1.80v` only):

1. **Reproduction.** Both points' own committed decks were re-run on a second
   host at the pinned open_pdks commit and the same ngspice major version. The
   `ideal@fs_27c_1.80v` control reproduces the committed log **to every printed
   digit** — all five captured codes and every per-rail average current to six
   significant figures. The `package-r-only@fs_27c_1.80v` point **does not
   reproduce**: the fresh run reads the control's mid-scale code, and its
   per-rail currents move onto the control's values, which is what 0.1 Ω of
   series resistance should do to a ~7 µA rail. The recorded 505 is therefore not
   a reproducible property of that deck; the two runs also differ 3–4× in the
   number of timepoints the solver visited, and the control demonstrates that the
   *control's* answers are invariant under exactly that difference.
2. **Per-trial margin.** With the committed `--decision-margin-trace` probes
   (imported, same instants) on every variant, the mid-scale conversion has
   exactly **one** decision anywhere near its threshold: the **sign bit (bit 9)**,
   at **≈1 µV** (`≈0.0003 LSB`) of comparator differential input. Every one of
   the nine magnitude trials that follows is presented with **≥1.49 LSB**
   (≥5.2 mV) and decided correctly. `1 LSB = 3.5156 mV` at 1.8 V and DR-004's
   own input-referred noise budget (Decision §2) is `1.0148 mV` (`0.29 LSB`) — so the
   marginal decision sits roughly **three orders of magnitude inside** the band
   the design promises nothing about, and the low-order trials are *not* near
   their thresholds at all.
3. **What it would take to reach 505 through the magnitude search — and why no
   arm here can.** The recorded 505 is magnitude `6` in the below-mid-scale
   branch (`ADCOUT<i> = DOUT<i> XOR DOUT9N` with `DOUT9 = 0` makes
   `code = 511 − magnitude`; `505 → 6 → DOUT2 = DOUT1 = 1`), so the bit-2 trial
   has to decide the other way. The probe measures what that trial is actually
   presented with: **+15.694 mV (+4.46 LSB)**. Moving a decision by 15.7 mV is
   **275×** the `package-r-only` arm's whole die-side ground excursion at this
   corner (0.057 mV) and larger than *any* arm's there (`no-gnd-pad`, the worst,
   13.7 mV). The magnitude search is therefore not reachable by this campaign's
   perturbations at all — which leaves the ~1 µV sign trial as the only decision
   of that conversion any of them could touch.
4. **Why a disturbance there is not a 1-LSB event.** `DOUT9` is the sign bit of a
   sign-plus-true-magnitude search: it gates all nine `SELn`/`SELp` pairs through
   `DOUT9N` and the nine-bit offset-binary recode (`ADCOUT<i> = DOUT<i> XOR
   DOUT9N`) — verified directly in `design/sar_adc_top.spice`, not inferred. A
   sign decision that resolves differently, or late, re-runs the whole magnitude
   search against the other side of mid-scale; it does not nudge one bit. A
   multi-LSB mid-scale code is the *expected* signature of a disturbed sign
   trial, and the 1-LSB moves this campaign reports elsewhere on that input are
   the lucky case, not the bound.

**Verified vs assumed.** (1)–(4) are measured, arithmetic on measured values, or
read off the committed netlist.
What is **not** established: the trajectory inside the recorded 505 run. That run
does not reproduce on the probing host, so its own per-trial margins cannot be
recovered after the fact, and this record does not claim to know which trial
diverged in it.

## Decision

1. **The `+0.00·V_REF` captured code is not a sensitivity metric.** No record,
   decision record or proposal may state a supply-return (or decoupling, or
   package-parasitic) *code* sensitivity read on that input as a measurement of
   that mechanism. The mid-scale conversion's outcome is set by a decision with
   ~1 µV of margin, while the die-side rail movement every non-ideal arm of this
   campaign introduces spans **0.041 mV to 17.055 mV** across the ratified grid
   (0.057–13.7 mV at this corner) — **50× to ~17,000× that margin**. Its outcome
   is therefore a coin flip with respect to all of them, and a coin flip is
   **not monotone in the perturbation**. That is exactly what the recorded
   ordering shows.
2. **What the campaign's supply-return claims rest on instead**: the die-side
   rail excursions (`GND_DIE`/`VGND`/`VDD`/`VPWR` peak-to-peak), which are
   monotone, reproducible and already the basis of DR-012/DR-015/DR-017's
   quantitative arguments, plus the captured codes at the **off-boundary**
   mid-scale inputs (`±0.25·V_REF`), which do not move in any arm at any
   ratified corner in any committed record of this campaign.
3. **A mid-scale code delta may still be reported — as an observation, with this
   record cited.** It is real data about a real conversion, and hiding it would
   be worse. It must be stated as a code read on the 511/512 boundary whose
   movement is not attributable to the arm, never as an `N LSB` sensitivity of
   the mechanism under test.
4. **Reproducibility rule for a code difference.** A captured-code difference
   between two decks is evidence of a circuit difference only if both decks are
   re-run on one host and one toolchain and the difference survives. Comparing a
   fresh run against a log minted elsewhere is not sufficient for this input.
5. **No design change is adopted on this evidence.** Nothing here shows the ADC
   failing a criterion it was given: the input sits on the MSB threshold, three
   orders of magnitude inside DR-004's stated noise budget, and a SAR without
   redundancy is not promised to resolve it. Adding redundancy, MSB hysteresis or
   a longer first trial would be a design change argued from an unreproduced
   6-LSB observation — which this record declines to do.
6. **Future campaigns must not place a graded test point on the MSB threshold.**
   Any ENOB/INL/DNL or code-accuracy campaign that grades a captured code must
   either avoid the exact MSB threshold or declare that point indeterminate by
   ±0.5 LSB up front. The existing `+0.00·V_REF` point in
   `sim/full-conversion-transient/testbench/full_conversion_tb_fragment.spice`
   is **left as it is** (see Alternatives): it is cited by many committed
   records, and its 511/512 split is itself the evidence for this record.

## Alternatives considered

- **Treat the 6 LSB as a real supply-return sensitivity and widen DR-012/DR-015's
  claims accordingly** — rejected: the ordering across arms falsifies it
  (0.057 mV → 6 LSB while 13.7 mV → 0 LSB), and the point does not reproduce.
  The cost of *not* choosing it is that this campaign keeps a code metric that
  is blind on one of its three inputs; Decision §2 pays that cost by naming what
  the claims actually rest on.
- **Call it a comparator design defect and mitigate it (redundancy, MSB
  hysteresis, a longer MSB trial)** — rejected for now: the measured margins say
  the *only* marginal decision is one the design was never asked to resolve, and
  the mitigation would be argued from a run nobody can reproduce. The cost of not
  choosing it is real: if a future campaign finds multi-LSB mid-scale codes that
  *do* reproduce, this call must be revisited, and Open items names that trigger.
- **Move the mid-scale test input off the boundary (e.g. `+0.05·V_REF`)** —
  rejected here: the committed fragment's input schedule is shared by every
  campaign that uses it, its code table is cited by several records, and a
  changed stimulus would make none of them comparable. It is also the wrong
  trade: the boundary point is the most informative input in the set precisely
  because it exposes this behaviour. Future campaigns get Decision §6 instead.
- **Re-run the whole 45-run grid on one host to settle the ordering** — rejected
  on cost and value: 8+ hours of whole-ADC transients to re-measure a quantity
  this record has just established is a coin flip. The probe is one corner and
  six runs, and it answers the question that was actually open.
- **Delete or amend record `20260926-050045-8e62675`'s 505 row** — refused by
  `CLAUDE.md`'s append-only rule. The record stays exactly as minted; the probe
  record and this decision record are what a reader meets beside it.

## Spec lines affected

**None.** No row of `spec/target-spec.md` changes, and no number in it is
proposed, relaxed or graded here. The rows this touches indirectly are the DRAFT
**Power** row (the row the supply-impedance campaign is indexed under in
`sim/spec-coverage.json`) and the DRAFT **ENOB**/**INL**/**DNL** rows, which
Decision §6 constrains the *method* of a future bench for without changing a
value.

## Consequences

- **Three decision records gain a caveat pointer.** DR-012 (§"What the campaign
  found"), DR-015 (§Consequences' grid paragraph) and DR-017 (Amendment A's
  mid-scale `|Δcode|` column) each cite a mid-scale code delta from this
  campaign; each now names this record beside that citation. None of their
  *decisions* changes: every one of them is argued from the rail excursion, and
  the mid-scale code entered as corroboration.
- **The campaign keeps its code comparison, and it keeps being useful** — on the
  `±0.25·V_REF` inputs, where the committed evidence is a clean, reproducible
  null at every corner in every arm. What it loses is the ability to read an
  `N LSB` supply-return number off the boundary input.
- **The probe is committed and re-runnable** (`--midscale-probe`), including on a
  host where the mid-scale code *does* move — which is the one experiment that
  would recover the diverging trial directly.
- **Bad consequence, stated plainly**: this record closes the question with a
  *negative* result. It does not explain what happened inside the 505 run, and
  anyone who wants that answer needs the host that produced it. A reader who
  wanted "the mechanism, named" gets "the mechanism class, named, and the metric
  retired" instead.
- **Second bad consequence**: the `+0.00·V_REF` row of every future record of
  this campaign is now a row that must be read with a caveat rather than a
  number, which is more friction at every reading, forever, than a one-line
  sensitivity figure would have been.

## Open items

- **The recorded 505's own trajectory.** Unreproducible on the probing host.
  Settled by running `--midscale-probe` on a host where that point's mid-scale
  code moves (the per-trial table then names the diverging trial), or not at all.
- **Whether any mid-scale multi-LSB move reproduces anywhere.** If one does —
  same deck, same host, twice — Decision §5 is void and the comparator/SAR owns
  it. Tracked on #455's closing discussion rather than a new issue, because the
  trigger is a future observation, not a task somebody can start today.
- **The `+0.88 mV`-per-trial residual bias visible in the per-trial table** (the
  magnitude search converges toward ~1.5 LSB of positive comparator input rather
  than toward zero) is reported by this probe and by the committed
  decision-margin record, and is explained by neither. It is a settling /
  charge-injection question for the CDAC and comparator work, not a
  supply-impedance one, and it is why the mid-scale code reads 511 rather than
  512 at most corners.
- **Decision §6's guidance is not enforced by any check.** A future
  code-accuracy bench could still grade the boundary point. Making that
  mechanical (a runner-side refusal, or a `sim/spec-coverage.json` rule) is left
  to whoever builds that bench.

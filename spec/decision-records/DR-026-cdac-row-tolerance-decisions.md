# DR-026: tolerances for the ratified CDAC measurement rows (LSB step, electrical C_u)

- **Status**: proposed
- **Date**: 2026-11-22
- **Decided by**: proposed via issue #1021; no option chosen yet; ratification pending a separate operator decision recorded in this file's `## Decision` section (merging the PR that proposes this record does not ratify it; DR-003 standing policy)
- **Supersedes**: none
- **Superseded by**: (none while this record stands)
- **Related**: issue #1021; DR-003 (ratified the rows and their values); DR-019 (resized the unit-cap plate); `sim/cdac-array-transfer/records/20261126-040720-de9c8405.md` (the graded `klt sim` envelope whose informational columns are this record's evidence); `sim/cdac-array-transfer/records/20261001-120402-d24f700.md` (the structural + functional baseline); `sim/spec-coverage.json` rows `LSB (differential)` and `Sampling cap (CDAC unit × array)` (declared gaps naming this record until it is ratified)

## Context

Issue #1021 found that three RATIFIED `spec/target-spec.md` rows (`V_REF`,
LSB, Sampling cap) were evidenced only by a structural + functional/
monotonicity record whose own Claim states that no numeric error-tolerance
exists — a verdict that does not grade the named quantities. The `V_REF` row
needed no new number: its entire content is the exact relation
`V_REF = V_DD`, now machine-graded per corner by the envelope's
`spec_row`-tagged `vref_ratio`/`v_vrefn` measurements
(`sim/cdac-array-transfer/records/20261126-040720-de9c8405.md`, PASS 9/9).

The other two rows cannot be graded without a tolerance that does not exist
anywhere in the ratified spec, and CLAUDE.md forbids an agent from choosing
one. This record proposes those tolerances for ratification; until it (or a
successor) is ratified, both rows stay declared gaps in
`sim/spec-coverage.json` naming this record, and the envelope reports their
observables informationally with no `spec_row` tag.

**Verified facts this record rests on** (all from committed evidence, full
9-point ratified corner set unless stated):

- At the five sampled codes the largest absolute voltage-level error
  (measured minus ideal differential voltage) is 1.1656 mV in the baseline
  and 1.1556 mV in the graded run, both about 0.33 nominal LSB. For each
  corner the corrected record compares the measured voltage change over
  each of the four intervals with its ideal change at that supply. The
  first three intervals span 128 codes each and the last spans 127 codes
  (384 to 511). The largest relative interval error per corner ranges from
  0.012% to 0.191%. The model uses no mismatch draws.
- An electrical unit-cap observable exists: the reference charge integral
  `q_vrefp` divided by the exact switched-unit equivalent of the five-code
  set (641.990234375 positions; derivation in
  `sim/cdac-array-transfer/run_klt_graded.py`) gives `cu_elec` =
  8.59–8.75 fF at eight of nine corners and 9.54 fF at `tt_125c_1.80v`,
  against the ratified "C_u ≈ 8.66 fF" (itself an "≈" figure). The 125 °C
  outlier direction (more charge than colder corners) is consistent with
  junction leakage adding to the integral, but that attribution is NOT
  established by the committed runs — the corner dependence is reported,
  not explained.

## Decision

Nothing is decided by this record yet — it is the proposal the two gap
declarations name. For each row, the ranked options are:

**LSB row — tolerance for the five-code spot check, in units of
`2·V_REF/2^N`:**

1. *Recommended:* **±0.5 LSB on the 5-code spot check, graded per corner**
   (the envelope gains a `spec_row: lsb`-tagged deviation measurement once
   this is ratified). A band on sampled voltage-level error gives
   ~1.5× headroom over the observed 0.33 nominal LSB. The INL/DNL rows
   also express deviations in LSB.
2. **Defer to the DNL/INL statistical rows**: declare the LSB row graded by
   its exact relation only (as `V_REF` now is) and let accuracy live in the
   DRAFT INL/DNL rows. Cost: the ratified LSB row then never has its own
   magnitude grade, and a future INL relaxation cannot be caught at this
   bench.
3. **No tolerance ever**: same as (2) but stated as permanent. Cost: the
   signoff grader can never mark the row `met` from this flow.

**Sampling-cap row — tolerance on the electrical `cu_elec` observable:**

1. *Recommended:* **structural-only grade**: the row is graded by the exact
   structural values (plate side 1.9000 µm, 512 positions/side — already
   machine-checked by `run_transfer.check_structural_sizing()` inside the
   graded record) and the electrical `cu_elec` stays informational. The
   ratified row's "≈ 8.66 fF" is a design estimate, not a measurement
   target; no band is invented around an "≈".
2. **±15 % electrical band on `cu_elec` per corner** (covers the committed
   8.59–9.54 fF range with margin). Cost: a band wide enough to swallow the
   125 °C leakage contribution grades almost nothing about the cap itself.
3. **±2 % electrical band at 27 °C corners only**, leakage-dominated corners
   exempt. Cost: a corner-conditional tolerance is a new spec form this
   table has never used, and the exemption boundary is arbitrary until the
   leakage attribution is measured.

## Alternatives considered

- **Widen the existing top-plate `limits` of the #564 pilot envelope to
  "cover" the rows** — rejected in issue #1021's curation: those limits
  grade neither named quantity.
- **Choose a tolerance in code** (a runner constant presented as fact) —
  rejected: CLAUDE.md's "agents do not relax a spec line / invent settled
  numbers" rule; this is exactly the decision this record exists to route
  to the operator.

## Spec lines affected

`spec/target-spec.md` target-table rows **LSB (differential)** and
**Sampling cap (CDAC unit × array)**: each would gain a tolerance clause (or
an explicitly structural-only grade clause) in the note column, in the same
DR-via-#27 form the values themselves were ratified in. No row *value*
changes. The `V_REF` row is unaffected (already gradeable as an exact
relation; graded by the envelope cited above).

## Consequences

- Until ratification (or supersession), `sim/spec-coverage.json` keeps both
  rows in the `ratified-gap` claim class naming this record, and the
  signoff manifest's `5.analog` entry (issue #1014, in flight) keeps them as
  declared gaps — no envelope, however green, reads as their coverage.
- On ratification of option LSB-1: the graded request gains one
  `spec_row: lsb`-tagged measurement and a re-run mints a new record; the
  gap declaration then moves to `ratified-measured` citing it.
- On ratification of sampling-cap-1: the electrical column stays
  informational forever; the row's graded evidence is structural + the
  layout citation that already exists.
- Bad consequence of the recommended pair: the LSB spot-check tolerance
  (option 1) is derived from the *systematic* deviation of the current
  design — it is a coverage-enabling band, not an architecture-neutral
  requirement, and a redesign that improves the switches would silently sit
  far inside it. The DNL/INL rows remain the real accuracy gate.

## Open items

- The 125 °C `cu_elec` outlier's leakage attribution (measured, not
  inferred) — a follow-up probe if option sampling-cap-2 is ever chosen.
- Whether the `mono_step_*` monotonicity checks should eventually carry
  `spec_row` tags of their own row rather than grading nothing — a spec-taxonomy
  question (there is no "monotonicity" row), settled only if the operator
  wants one.

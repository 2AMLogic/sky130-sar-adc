# DR-000: <short title>

<!--
Copy this file to spec/decision-records/DR-NNN-<slug>.md and fill it in.
Use the next unused NNN. One decision per record; keep it to about one page.
A decision record is required for every spec change (see CLAUDE.md: "the spec
is a gate").

A decision record is a *decision*, not a derivation. Long quantitative work
(CDAC sizing, comparator budgets, timing budgets, Monte-Carlo methodology)
belongs in a `spec/*-memo.md` design memo that a decision record cites; the
record states what was decided and why, and points at the memo for the
arithmetic.

Do not delete or rewrite a ratified record — supersede it with a new one, and
fill in the "Superseded by" field on the old record.
-->

- **Status**: proposed | ratified | superseded by DR-NNN
- **Date**: YYYY-MM-DD
- **Decided by**: <name / role / issue>
- **Supersedes**: <DR-NNN, or "none">
- **Superseded by**: <DR-NNN, or "(none while this record stands)">
- **Related**: <issues, `spec/` files, `sim/` evidence this record consumes>

## Context

What forced this decision? One short paragraph: the constraint, the
measurement, or the conflict that made the current spec inadequate. Link to
the issue, the simulation evidence in `sim/`, or the prior record it revises.
State plainly which facts are *verified* (and against what — a PDK file, a
committed sim run) and which are still assumptions.

## Decision

The decision, stated as a change to the spec — the parameter and its new
value, or the approach now ratified. Be specific enough that design work can
lock to it without further interpretation. If the record scopes rather than
sets numbers, say so explicitly so a reader does not mistake a scoping call
for a ratified value.

## Alternatives considered

- **<alternative>** — why it was not chosen. Name the cost of *not* choosing
  it, not just the cost of choosing it.
- **<alternative>** — why it was not chosen.

## Spec lines affected

Which row(s) of the table in `spec/target-spec.md`, or which `spec/`
file/line, does this decision change. Name them explicitly so a reader can
tell what is settled without re-deriving it from the prose above. For a port
of a gf180-sar-adc row, state whether the number carries, must be re-derived,
or is deferred.

## Consequences

What follows from this: what becomes possible, what becomes harder, which
testbenches or corner sets change, what work is invalidated or must be
re-run. **Include the bad consequences, not just the good ones** — a record
that lists only benefits has not finished arguing.

## Open items

What this record deliberately leaves unsettled, and who or what settles it
(a later DR, a design memo, a characterization campaign, the operator).

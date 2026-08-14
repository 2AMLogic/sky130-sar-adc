# spec/ — the spec and its decision records

This directory is the block's **gate**. `CLAUDE.md` states the rule this
directory exists to make enforceable:

> **The spec is a gate**: spec changes go through `spec/` with a decision
> record; agents do not relax a spec line to make a result pass. A row that
> proves unmeetable is superseded by a new decision record, never silently
> loosened.

## Contents

```
spec/
  README.md                        # this file
  target-spec.md                   # the target table — DRAFT in full until #1
  decision-records/
    TEMPLATE.md                    # start here for a new record
    DR-NNN-<slug>.md               # one decision per record
  <topic>-memo.md                  # (as needed) long quantitative derivations
```

- **`target-spec.md`** is **DRAFT and unratified in its entirety** until issue
  #1 ratifies it. No row in it is binding, no number in it may be quoted as
  settled, and — critically for the harness — **no value from it may be
  encoded as a pass/fail threshold** anywhere in `sim/`. Where a testbench
  needs a supply or a limit today, it states its own in its `tb.json`
  manifest and says in its `claim` field that it is not a spec claim (see
  `sim/README.md`).
- **`decision-records/`** holds the records. A decision record fixes one spec
  change or one architecture choice, with the reasoning that produced it, so
  downstream work can lock to it without re-litigating it.
- **`<topic>-memo.md`** is where long quantitative work belongs (CDAC sizing,
  comparator noise budget, timing budget, Monte Carlo methodology). A decision
  record is a *decision*, not a derivation: it states what was decided and why
  and cites the memo for the arithmetic. The sibling `2AMLogic/gf180-sar-adc`
  carries several such memos; this repo adds its own as they are needed.

## Two append-only trails, one house style

`spec/` records **why we decided**; `sim/` records **what we measured**
(`sim/README.md`). Both are append-only and both use the same `Supersedes`
semantics on purpose, so they read as one continuous, non-rewritable trail:

| | `spec/decision-records/` | `sim/records/` |
| --- | --- | --- |
| Identifier | `DR-NNN` | `<YYYYMMDD>-<HHMMSS>-<short-sha>` |
| Rewritten after the fact? | never, except the `Status` / `Superseded by` back-pointer | never at all |
| Reversal mechanism | a new record with `Supersedes: DR-NNN` | a new record with `Supersedes: <record-id>` |

The narrow carve-out on the spec side exists because a decision record states
what is *currently in force*: a reader landing on an obsolete record must be
able to see, in that record, that it no longer governs. A `sim/` record needs
no such carve-out — a timestamped measurement stays true regardless of what
supersedes it, so `sim/` records are never touched at all.

## When a record is required

Write a record for:

- **Any change to the ratified spec** — a new parameter, a changed value, a
  relaxed or tightened limit, a removed row. A failing result is grounds for a
  decision record *proposing* a change, never for a silent edit.
- **Any architecture choice that constrains downstream design** — CDAC
  switching scheme, comparator topology, synchronous vs asynchronous SAR
  logic, sampling/bootstrapping approach, mixed-signal simulation strategy. If
  another issue would have to re-derive the choice to proceed, record it.
- **Any scope decision**, including a decision to defer — device/supply
  flavor, interface scope, clocking source.
- **Any divergence from the port-parity sibling** `2AMLogic/gf180-sar-adc`.
  `CLAUDE.md` requires that where sky130 forces a departure, the divergence is
  recorded here rather than happening silently.

A record is **not** required for:

- Implementation detail already fully determined by a ratified record.
- Simulation results — those are `sim/` evidence records. A decision record
  may *cite* a `sim/` `<record-id>` as the evidence that forced it.

## File naming and numbering

```
spec/decision-records/DR-NNN-<slug>.md
```

- **`DR-` prefix, always.** The same `DR-NNN` token appears in the filename,
  in the document's `# DR-NNN: <title>` heading, and in every cross-reference
  (`Status: superseded by DR-007`, `Supersedes: DR-003`), so one token
  identifies a record everywhere.
- **`NNN` is three digits, zero-padded** — `DR-001`, `DR-042`, `DR-117`.
  (This repo uses three digits, matching `TEMPLATE.md` and `DR-001`;
  gf180-sar-adc uses four. Do not mix the two within this repo.)
- **`<slug>`** is short, kebab-case, and describes the *decision*, not the
  issue: `DR-001-supply-flavor-scope.md`.
- **`NNN` is the next unused number**: strictly greater than every number
  already present on `main`, and not already claimed by an open PR. Superseded
  records still count — numbers are never reused or reclaimed.

  ```sh
  git fetch origin main
  git ls-tree -r --name-only origin/main spec/decision-records/ \
    | grep -oE 'DR-[0-9]{3}' | sort -u | tail -1     # highest number on main
  gh pr list --state open --search 'DR- in:title'    # claimed in flight
  ```

  If two branches pick the same number concurrently, the later-merged one is
  **renumbered before merge** — filename, heading, and every cross-reference.

## One decision per record, one page

- **One decision per record.** If a record has the word "and" between two
  independent choices, it is two records. Splitting keeps supersession
  precise: superseding one choice must not drag an unrelated, still-valid
  choice along with it.
- **One page.** Context, Decision, Alternatives considered, Consequences, Spec
  lines affected, Open items — readable at once. Supporting analysis goes in a
  `spec/<topic>-memo.md` or in `sim/`, cited from **Related**.

## Statuses

- **`proposed`** — written and under discussion. A proposed record may be
  edited or withdrawn in its own PR; supersession applies from ratification
  onward. A proposed record is **not** an answer: `DR-001` is `proposed` and
  is the record issue #1 ratifies *against*, not a settled decision.
- **`ratified`** — in force. Downstream design may lock to it.
- **`superseded by DR-NNN`** — no longer in force; the named record replaces
  it on the same question.

## Superseding a ratified record

1. **Write a new record** with the next unused `DR-NNN`, with its own Context
   / Decision / Alternatives / Consequences / Spec lines affected, and
   `Supersedes: DR-NNN` naming the old one.
2. **Add the back-pointer to the old record**: set its `Status` to
   `superseded by DR-NNN` and fill its `Superseded by` field. That is the
   *only* edit ever made to a ratified record — its Context, Decision,
   Alternatives, and Consequences stay exactly as ratified, wrong conclusions
   and all.
3. **Both directions must resolve.** A one-way link is a broken record.

`Supersedes` means "replaces this record's decision on the same question". A
record deciding a *different* question about the same block is independent and
leaves `Supersedes` empty, however closely related the two are.

## Provenance

Adapted from `2AMLogic/gf180-sar-adc`'s `spec/decision-records/README.md`
(commit `f613571aee5b80eff1eea37bdce9dfc88c5cf396`) per `CLAUDE.md`'s port-
parity and harness-bootstrap rules. Deliberate divergences: this file sits at
`spec/README.md` and covers the whole directory (the spec table, the memo
convention, and the records) rather than the records alone; numbering is three
digits here, matching this repo's existing `TEMPLATE.md` and `DR-001`; and the
`sim/` cross-reference table above is added so the two append-only trails are
introduced together.

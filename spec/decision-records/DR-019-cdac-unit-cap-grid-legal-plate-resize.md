# DR-019: CDAC unit-cap plate resized to a 5 nm-grid-legal side; `klt precheck --grid-um 0.005` is a gate, not an advisory

- **Status**: proposed — ratification via the operator's approval of the PR
  resolving #496, per the canary spec/DR ratification-via-PR standing policy
  (2AMLogic/2am#357: "a builder drafts the ratification/DR as a PR on the
  evidence, and the operator's PR approval is the ratification act"), the
  same mechanism DR-003 used to ratify the row this record amends.
- **Date**: 2026-09-30
- **Decided by**: Builder agent, issue #496
- **Supersedes**: none (amends one number inside
  `spec/decision-records/DR-003-numeric-spec-derivation.md` Item 3; DR-003
  itself stands, see "Consequences")
- **Superseded by**: (none while this record stands)
- **Related**: #496 (this decision), #495 (`layout/halflsb-offset/`, whose
  committed `klt precheck --grid-um 0.005` census is the measurement that
  surfaced this question),
  `spec/decision-records/DR-003-numeric-spec-derivation.md` Item 3 (the
  matching-floor derivation this record's new plate size still satisfies),
  `spec/decision-records/DR-005-cdac-array-design.md` (the unit-cap sizing
  decision this record amends), `spec/decision-records/DR-009-comparator-output-load-balance-and-half-lsb-offset.md`
  (the half-LSB offset cap sized identically to `C_u`, which inherits this
  resize), `layout/halflsb-offset/reports/LATEST/precheck.grid5.json` (the
  48-shape off-grid census this record resolves), `layout/cdac-array/bin/cdac_layout.py`
  (`CAPM_SIDE`, the 1024-instance consumer of the old value),
  `design/cdac/cdac_unit_cell.sch`, `design/sar_adc_top.sch` (`Choff_n`/`Choff_p`
  and their matching dummies), the shipped PDK deck
  `$PDK_ROOT/sky130A/libs.tech/klayout/drc/sky130A.lydrc` (read directly for
  this record — see "Context" — at `open_pdks` commit
  `c6d73a35f524070e85faff4a6a9eef49553ebc2b`, the same commit
  `sim/pdk.json` pins), **#498** (follow-up issue: carries the resize
  through `design/cdac/`, `design/sar_adc_top.sch`, `layout/cdac-array/`,
  `layout/halflsb-offset/`, and the dependent `sim/` campaigns — not done by
  this record), **`2AMLogic/klayout-tools#2642`** (friction issue: `klt
  drc`'s curated sky130 deck is missing the manufacturing-grid/angle rule
  category the real signoff deck carries — generic, no design detail).

## Context

**The question, restated.** `design/cdac/cdac_unit_cell.sch`'s unit capacitor
`C_u` is a `sky130_fd_pr__cap_mim_m3_1` with `W = L = 1.8988` (µm) — a plate
1898.8 nm on a side. 1898.8 is not a multiple of 5, so no layout that draws
that exact plate, or any via/landing-pad centred on its edge, can land every
vertex on sky130's 5 nm manufacturing grid. `layout/halflsb-offset/` (#495) is
the first block in this repo to measure the consequence with `klt precheck
--grid-um 0.005`: 48 off-grid shapes, confined to the MiM stack and the metal
that lands on it, with `klt drc` (the klt-bundled `sky130` rule deck) reporting
**clean** on the same geometry. Issue #496 asked whether that is acceptable,
and if not, what replaces it — a DR-005/DR-003 question about `C_u` itself,
not a layout-flow question.

**What was verified, not assumed, before deciding.** The issue's own
complexity marker warns that asserting the PDK "snaps or accepts" off-grid
MiM geometry without checking would be a silent-failure-mode wrong call. This
record does not take `klt drc`'s "clean" verdict as evidence that sky130
tolerates the off-grid geometry — it reads the PDK's own shipped signoff DRC
deck directly:

1. **The real foundry deck has a manufacturing-grid rule category, on by
   default, for nearly every layer in the stack.**
   `$PDK_ROOT/sky130A/libs.tech/klayout/drc/sky130A.lydrc` declares
   `OFFGRID = true # manufacturing grid/angle checks` (line 48) and, inside
   its `if OFFGRID` block (the "OFFGRID-ANGLES section"), emits a
   `<layer>.ongrid(0.005)` check — rule class `x.1b`, "OFFGRID vertex on
   `<layer>`" — for `nwell`, `diff`, `tap`, `poly`, `licon`, `li`, `mcon`,
   `m1`, `via`, `m2`, `via2`, `m3`, `via3`, `m4`, `via4`, `m5`, `pad`, and
   roughly twenty other layers. This is read directly off the installed PDK
   at the commit this repo pins (`sim/pdk.json`), not inferred.
2. **The capm layer itself is the one documented exception.** Grepping the
   same file for `capm` finds exactly one rule,
   `capm.with_angle(0..90).output("capm.7", ...)` (a rectangle-shape check) —
   there is no `capm.ongrid(...)` line. `capm2` has none either. So the MiM
   plate's own four corners are not directly rule-checked for grid alignment
   by the real deck.
3. **Mapping #495's own 48-shape census against those two facts is decisive.**
   `layout/halflsb-offset/reports/LATEST/precheck.grid5.json`'s violations
   are tagged by raw GDS layer/datatype; cross-referencing the same deck's
   own layer aliases (`capm = polygons(89, 44)`; `m1_wildcard = "68/0-4,6-43,45-*"`,
   `via_wildcard = "68/44"`, and the equivalent `m2`/`via2` = `69/*`,
   `m3`/`via3` = `70/*`, `m4`/`via4` = `71/*`) shows **46 of the 48 off-grid
   shapes sit on met1/via1/met2/via2/met3/via3/met4 — layers the real deck
   DOES grid-check** — and only 2 sit on bare `capm` (89/44), the one layer
   it does not. The off-grid plate's own edges might individually survive the
   real deck's rule set; the via/pad geometry a router must centre on those
   edges, which is nearly all of the census, would not.
4. **`klt drc`'s "clean" verdict on this geometry is therefore not evidence
   of real foundry-grid compliance.** `layout/halflsb-offset/reports/LATEST/drc.json`'s
   own `rules_checked`/`rules_skipped` lists (41 + 13 rule names) contain
   **no `*.ongrid` or `OFFGRID` entry at all** — the `sky130` deck `klt drc`
   runs in this repo's flows does not implement the real deck's
   manufacturing-grid/angle rule category (`x.1b`/`x.2`/`x.3a`), on any
   layer. It is a reduced deck (width/space/enclosure/area only), not the
   signoff deck. A "DRC clean" record in this repo currently says nothing
   about grid legality one way or the other.

**Conclusion from the evidence, not a guess.** Item 1's interpretation ("if
the foundry flow snaps or accepts it, the answer is a DR line plus a standing
waiver") does not hold: the real, shipped sky130A signoff deck does not
silently accept this geometry — it has a specific, named rule class for
exactly this defect, active by default, and it would flag the overwhelming
majority of #495's census. Item 3's interpretation ("the 5 nm grid is not a
gate for this project's sign-off target") is also not supported: this repo's
own `spec/target-spec.md` "What T1 (bronze) will require" section names DRC
clean against the signoff deck as a T1 requirement, and the deck this repo
would need to clear for that claim carries the `x.1b` rule this geometry
would trip.

**The matching floor does not block a fix.** DR-003 Item 3 derived
`A_unit = (A_C/sigma_u)^2 = 3.6056 µm²` as a **minimum** matching-limited
area (`sigma_u` must be *at most* `1.4746 %`, which requires area *at least*
`3.6056 µm²`) — any grid-legal side at or above `1.8988 µm` satisfies it, so
rounding up, not down, stays compliant.

## Decision

**Option 2 of #496: re-size `C_u` to the smallest 5 nm-grid-legal plate at or
above the matching floor — `W = L = 1.9000 µm` (1900 nm), up from `1.8988 µm`
(1898.8 nm).** Not Option 1 (waive) — the evidence above shows the grid check
is not waivable on the deck this repo would need for a real signoff claim.
Not Option 3 (irrelevant) — same reason, plus this repo's own T1 bar already
names DRC-clean-against-signoff as a requirement.

**New unit-cap figures**, using DR-003's own PDK-read coefficients
(`camimc = 2.0000 fF/µm²`, `cpmimc = 0.1900 fF/µm`, `A_C = 2.8 %·µm`),
reproducible the same way DR-003's were:

```
s = 1.9000 um (was 1.8988 um)
area = s^2 = 3.6100 um^2 (was 3.60544 um^2; +0.126%)
C_u = camimc*area + cpmimc*(4*s) = 7.2200 + 1.4440 = 8.6640 fF
      (was 8.6540 fF; +0.116%)
sigma_u = A_C / sqrt(area) = 2.8 / 1.9000 = 1.4737 %
      (was 1.4746 %; matching improves fractionally, by construction --
       area only went up)
sigma(DNL)_3sigma = 22.605 * sigma_u = 0.3333 LSB (was 0.3335 LSB)
sigma(gain error)_3sigma = 32 * sigma_u = 47.16% ... as a fraction of C_u;
      in DR-003's own units this is 1.4191 LSB (was 1.42 LSB)
```

Every downstream number DR-003 Item 3 reported moves by a fraction of a
percent, in the favorable direction (more area, not less) — this is a plate
resize, not a re-derivation of the matching methodology, and no DR-003
conclusion (the ~415× kT/C margin, the matching-vs-kT/C dominance ordering,
the flagged-not-fixed gain-error finding) changes in kind.

**`klt precheck --grid-um 0.005` is a GATE for this repo's layout work going
forward, not an advisory metric.** It is currently the *only* check in this
repo's toolchain that catches a real `x.1b`-class defect (see Context item 4)
— `klt drc`'s bundled deck does not. Every future `layout/` flow that draws a
MiM cap, or any geometry whose coordinates derive from one, should run it and
treat `offgrid` as a required-pass check, not a recorded-and-ignored one,
unless a specific shape is affirmatively shown to sit only on a layer the real
signoff deck does not grid-check (`capm`/`capm2` themselves — a narrow
carve-out, not a blanket waiver, and one that does not help here because the
surrounding via/pad geometry is on checked layers regardless).

**What this record does not do.** It does not re-draw
`design/cdac/cdac_unit_cell.sch`, `design/sar_adc_top.sch`,
`layout/cdac-array/`, or `layout/halflsb-offset/` — per #496's own scope
("Out of scope: Redrawing any existing block... this issue is the decision,
not its consequences") and the task's explicit instruction not to do the
re-layout/re-derivation inline. The follow-up issue filed alongside this
record (see "Consequences") is that work.

## Alternatives considered

- **Option 1 — accept the 1898.8 nm plate and record a standing waiver.**
  This was the leading candidate until the PDK's own signoff deck was read
  directly (Context items 1–3): the premise it needs — "the foundry flow
  snaps or accepts it" — is false for 46 of the 48 measured violations. A
  waiver written on the strength of `klt drc`'s clean verdict alone would
  have been exactly the silent wrong call #496's complexity marker warned
  against; rejected once checked, not on priors.
- **Option 3 — declare the 5 nm grid irrelevant to this project's sign-off
  target.** Rejected for the same evidentiary reason, plus a direct
  self-contradiction: `spec/target-spec.md`'s own "What T1 (bronze) will
  require" section names DRC-clean-against-the-signoff-deck as a T1
  requirement, and that deck carries the rule this geometry trips.
- **Rounding down to `1895 nm`** (also 5 nm-grid-legal, and closer to the
  original value). Rejected: it is below DR-003's `1.8988 µm` matching
  floor (`sigma_u` would exceed `1.4746 %`), which would quietly loosen the
  `≤ ±1 LSB` 3σ DNL/INL criterion DR-003 sized against. Rounding up costs
  nothing DR-003 did not already budget for (Item 3's ~415× kT/C margin
  absorbs a 0.13% area increase without comment) and keeps the same
  direction of safety margin DR-003 itself used throughout.
- **A larger jump (e.g. the `~9.9×` resize `spec/target-spec.md`'s DR-007
  update note names as a possible future redesign path for the array
  gain-error finding, #269).** Out of scope for this record: that resize (if
  ever adopted) answers a different question (absolute gain error from
  top-plate parasitic loading) with a different, much larger cost
  (re-deriving the array size itself). Conflating the two would have made a
  12 nm grid-legality fix into an excuse to relitigate #269's open redesign
  question, which #496 did not ask this record to do.
- **Filing a klayout-tools issue and deferring the spec decision until `klt
  drc`'s bundled deck implements the `x.1b` rule category.** Rejected as the
  primary path: that gap is real and worth reporting (see "Consequences"),
  but this repo's spec decision does not need to wait on it — the real PDK
  deck already answers the geometric question directly, and `klt precheck
  --grid-um 0.005` already catches the defect in this repo's own flows today.
  The tool gap is filed as its own, generic friction issue, not as a blocker
  on this record.

## Spec lines affected

`spec/target-spec.md`'s "Numeric rows — RATIFIED 2026-08-19" section and
Target table row "Sampling cap (CDAC unit × array)":

| Field | Old | New |
|---|---|---|
| Unit-cap plate side | `1.8988 µm` (not grid-legal) | `1.9000 µm` (5 nm-grid-legal) |
| `C_u` | `≈ 8.65 fF` (`8.6540 fF`) | `≈ 8.66 fF` (`8.6640 fF`) |
| Array size | `2^9 = 512` positions/side | unchanged |
| Status | RATIFIED (DR-003 via #27) | RATIFIED (DR-003 via #27; plate resized to a grid-legal side by DR-019 via #496) |

`spec/decision-records/DR-003-numeric-spec-derivation.md` is **not** rewritten
(ratified records are not edited in place) but gets an appended "UPDATE"
note, the same convention DR-005 already carries for DR-008's later touch, so
a reader of DR-003 alone is not misled about which plate size is current.
`spec/decision-records/DR-005-cdac-array-design.md` and
`spec/decision-records/DR-009-comparator-output-load-balance-and-half-lsb-offset.md`
each get a one-line Related/cross-link note pointing here, since both cite
the old `1.8988` literal in their own Decision text.

## Consequences

1. **A follow-up issue is required, and is filed alongside this record
   (not assumed), to actually carry the resize through the design and
   layout tree**: **#498** —
   `design/cdac/cdac_unit_cell.sch`'s `W`/`L` (and its
   symbol/any cached value), `design/sar_adc_top.sch`'s `Choff_n`/`Choff_p`
   and their matching-dummy devices (DR-009 requires them identical to
   `C_u`), `layout/cdac-array/bin/cdac_layout.py`'s `CAPM_SIDE`, and a
   re-run of every flow and sim campaign that currently encodes `1.8988`:
   `layout/cdac-array/`'s full flow (1024 instances), `layout/halflsb-offset/`'s
   full flow (whose `precheck.grid5.json` census this record directly
   answers — expected to shrink sharply, though not necessarily to zero,
   once `C_u` and its offset-cap sibling both move to a grid-legal side;
   that is a measurement for #498, not asserted here), and
   `sim/cdac-array-transfer/`, `sim/full-conversion-transient/`,
   `sim/enob-estimate/` (every campaign whose record cites the old `C_u` or
   array capacitance). None of that is done by this record.
2. **The "real deck vs. klt-bundled deck" gap (Context item 4) is a genuine
   klayout-tools capability gap, not a design question**, filed separately
   as a generic friction issue per `CLAUDE.md`'s friction protocol (no
   spec/design detail in that filing): **`2AMLogic/klayout-tools#2642`** —
   `klt drc`'s curated `sky130` rule deck does not implement the shipped
   PDK's own manufacturing-grid/angle rule category, so a "DRC clean"
   record in *any* sky130 `klt` flow, anywhere, currently asserts less than
   it appears to. That gap would have produced the same silent miscall this
   record avoided only because it was checked against the PDK's own deck
   directly; a future block without that checking step would not get the
   same warning from `klt drc` alone.
3. **DR-003 Item 3's qualitative conclusions are unchanged** (matching
   dominates kT/C by ~415×, the flagged-but-not-fixed gain-error finding) —
   every number moves by a fraction of a percent, in the direction DR-003's
   own margins already absorb. This record does not reopen DR-003's
   methodology.
4. **A real cost, not a free fix**: the resize is a ratified-spec-row change
   (`spec/target-spec.md`'s C_u row was RATIFIED, not DRAFT), so per
   `CLAUDE.md`'s "the spec is a gate", every record and artifact that cites
   the old value is now stale until the follow-up issue's re-derivation
   lands — named explicitly here rather than silently inherited. Until that
   issue closes, `design/`, `layout/cdac-array/`, and `layout/halflsb-offset/`
   draw a plate size that is one grid step below the newly ratified row; this
   is a known, tracked inconsistency, not a defect introduced by this record.
5. **The grid-legality question itself does not need to be reopened by any
   future block that draws a MiM cap in this repo.** Any future unit cap
   sized to a 5 nm-grid-legal side inherits a clean answer; any one that is
   not (e.g. a deliberately different value for a different sub-block) must
   re-run `klt precheck --grid-um 0.005` and treat a nonzero `offgrid` count
   as a defect to fix at the source (resize), not a residual to document and
   carry — the standing policy this record sets, so `layout/halflsb-offset/`'s
   README (which could not resolve this itself per #496/#495's own scoping)
   and any future block cite this record instead of re-deriving the policy.

## Open items

- **#498's own re-derivation and re-verification list** — filed; owner: a
  future Builder.
- **`2AMLogic/klayout-tools#2642`** (Consequence 2) — filed separately,
  generic, no design detail; owner: klayout-tools' own maintainers/roles.
- **Whether `layout/halflsb-offset/`'s `precheck.grid5.json` census reaches
  zero once both caps resize**, or whether a smaller residual remains for
  some other reason (e.g. a via/pad placement choice unrelated to the plate
  size) — not measured here; #498's own re-run is the check, not an
  assumption made by this record.
- **#269's much larger possible resize** (the array gain-error redesign
  path) remains exactly as open as `spec/target-spec.md`'s DR-007 update
  note already left it. This record's 0.126%-area nudge is not a step
  toward or away from that question.

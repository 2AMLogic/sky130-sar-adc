# DR-017: One MiM decoupling capacitor per supply domain, sized from a met3/met4 area budget — because the die-side bounce is measured to fall only as ~1/√C and no affordable on-die capacitance reaches 1 LSB

- **Status**: proposed — like DR-010, DR-012 and DR-015 this record settles a
  design/testbench question, not a numeric row of `spec/target-spec.md`. It
  inherits the same provisional status as every record still resting on
  DR-003's DRAFT numeric inputs.
- **Date**: 2026-09-25
- **Amended**: 2026-09-26 — **Amendment A (issue #431)**, at the end of this
  record: the shipped value's own `package`-arm excursion has since been
  measured, and it **refutes the `1/√C` model** this record's Decision §3
  reasons from and whose name is in the title above. **Read Amendment A before
  quoting any capacitance-scaling claim from the body below** — in particular
  the fitted `C_die ≈ 9.21 pF`, the `26.64 mV` prediction, and the
  "`≈ 1.03 nF` per domain / 4.7× the composed die" arithmetic, all three of
  which the amendment retracts. **Decision §1, §2 and §6 stand unchanged**
  (the device, its `MF = 2` value, and the deferral of placement); §3's
  *criterion* and §5's *deferral* are restated; §4's target verdict is
  unchanged in outcome and strengthened in reason. Nothing in the body is
  deleted or rewritten — a decision record's history is the point of having
  one.
- **Decided by**: Builder agent, issue #431 (body and Amendment A)
- **Supersedes**: none
- **Superseded by**: (none while this record stands; Amendment A amends it in
  place rather than superseding it — the decision itself, one
  `sky130_fd_pr__cap_mim_m3_1` per supply domain at `MF = 2`, survives the
  refutation of the model that was used to argue for it, and is better
  supported afterwards than before)
- **Related**: #431 (this decision and its implementation), DR-010
  (`DR-010-digital-supply-domain-partition.md`, whose "On-die decoupling for
  either domain is not designed, budgeted, or measured" open item this record
  answers), DR-012 (`DR-012-analog-ground-pad.md`, which carries the same item
  forward and whose analog `GND` pad is the terminal this record's analog cap
  sits against), DR-015 (`DR-015-package-parasitic-assumption.md` — the
  package-style R+L the `package` arm drives through, and its own Decision
  clause 6, "No decoupling is modelled, deliberately", whose premise this
  record is the first to change), #378 / #410 (the campaign and the ratified
  no-decoupling baseline this record measures against), #409 (the still-open
  full-PVT-grid and R/L-sweep re-run of `sim/supply-impedance-sensitivity/` —
  not absorbed as a blocking dependency, for the reason #431's own filing
  comment states), `sim/supply-impedance-sensitivity/records/20260925-073912-0e385e5.md`
  (the no-decoupling baseline), `2AMLogic/gf180-sar-adc`'s
  `spec/decision-records/DR-0036-vdd-decoupling-budget.md` (the port-parity
  sibling record for the same question — read, and deliberately **not** copied;
  see "Alternatives considered")

## Context

DR-010 and DR-012 both carry "on-die decoupling … is not designed, budgeted,
or measured" as a standing open item, with no tracking issue of their own
until #431. DR-015's Decision clause 6 states plainly that
`sim/supply-impedance-sensitivity/` models **no** decoupling anywhere,
"deliberately," so every result under that assumption is "pessimistic by
construction." That campaign's own first committed record
(`records/20260925-073912-0e385e5.md`, issue #378, cited by DR-012's "Open
items") is what makes the gap measurable rather than merely asserted:

- At the ratified baseline corner (`tt_27c_1.80v`), the as-built `package` arm
  (all four supply terminals bonded through DR-015's package-style
  `R = 102.2 mΩ, L = 1.914 nH`) moves **0 LSB** of captured code against the
  ideal-source control, but leaves the die-side analog ground (`GND_DIE`, the
  comparator's own decision reference) at **37.333 mV** peak-to-peak and the
  digital rail (`VPWR_DIE`) at **61.755 mV** peak-to-peak.
- A strict one-element ablation in the same record (`package` vs
  `package-r-only`, identical resistance, `L` zeroed) attributes essentially
  all of that excursion to the bond **inductance**: `package-r-only` measures
  **0.059 mV** on the same node. Bond resistance alone is negligible; bond
  inductance is not.

**Issue #431's own headline numbers (129–259 mV worst-case bounce, 3–7 of 45
codes moving) are deliberately not used here.** They come from an unmerged
branch (`feature/issue-378-ground-return-pvt`, record
`sim/ground-return-impedance/records/20260925-134451-5b3f175.md`) under a
*different* package-parasitic assumption (a `2.01 nH / 0.099 Ω` isolated-wire
model) than the one ratified on `main`
(`DR-015-package-parasitic-assumption.md`'s `1.914 nH` **package total** — bond
wire plus a stated lead-frame/board allowance). Issue #409 — open, independently
in flight as of this record's date, and not a blocker for this one per its own
filing comment — is what would reconcile the two models and extend `main`'s
campaign to the full ratified PVT grid. **Everything below is measured on
`main`, under `main`'s own model, at one corner**; no worst-case-PVT claim is
made, in the same sense DR-015's own record states of itself.

**Why act on one corner rather than wait for #409.** #431's filing comment names
the reason: its own acceptance criteria already require re-running
`sim/supply-impedance-sensitivity/` with decoupling in the netlist, "which is a
natural point to pick up main's own package model rather than the branch's."
The inductance-dominated mechanism is itself a topology fact that does not
change with corner or with which of the two package models binds — only its
magnitude does — so the *class* of mitigation is decidable now even though the
worst-case magnitude is not.

### Die area, and what a MiM capacitor actually costs

The composed top-level layout
(`layout/sar-adc-top/reports/20260924-234053-66dca3c/compose.json`, the current
`reports/LATEST`) has a bounding box of
**280.450 µm × 385.500 µm = 108,113.475 µm²**. There is **no pad ring** in this
composition, so no area has ever been reserved beyond the four sub-blocks'
footprints and the routing between them.

`sky130_fd_pr__cap_mim_m3_1` is a **back-end** device: its plates are met3 and
met4 with the `capm` dielectric between them, so what it consumes is
**met3/met4 real estate**, not silicon. In principle it can be drawn *over*
sub-blocks that route below met3. That is the whole reason a decoupling
allocation of this size is arguable at all here — and it is also **an
unverified planning assumption in this record**, because no `layout/` pass has
yet checked how much of the composed die's met3/met4 is already spoken for (the
`TOP_P`/`TOP_N` met4 pins, `analog_ground_mesh()`'s met3 trunk and met4
droppers, and the met5 digital supply straps all live up there). See "Open
items"; the area figures below are a schematic-level budget check, not a
verified layout fact.

**MiM density**, read from the PDK's own model file rather than assumed:
`camimc = 2.0000 fF/µm²` (area) and `cpmimc = 0.1900 fF/µm` (perimeter) at
nominal `mim = 0` (`libs.tech/ngspice/parameters/montecarlo.spice`; the
`r+c/*_lin.spice` corner files bracket the area term at 1.778–2.231 fF/µm²,
so every capacitance below carries roughly ±11 % of process spread). The unit
cell reused here is `W = L = 46.9 µm` — the same footprint as
`design/sampling_frontend.sch`'s `Csamp_{p,n}`, already proven DRC-clean in
`layout/sampling-frontend/reports/LATEST/` — giving

> `C_u = 2.0000 fF/µm² × 2199.61 µm² + 0.1900 fF/µm × 187.60 µm = 4434.86 fF`
> ≈ **4.435 pF** in **2199.61 µm²** (2.034 % of the composed die).

## What was measured

Sizing here is **direct simulation**, not a closed form (see "Alternatives
considered" for why the closed form is unavailable in this repo). Every number
below comes from the same `sim/supply-impedance-sensitivity/` runner, the same
committed stimulus, the same baseline corner and the same deck assembly — only
the two `Cdecap_*` cards' `MF` differs.

### The sizing axis: how much does capacitance buy, on the arm that has inductance?

| `MF` per domain | `C` per domain | MiM area, both domains | `GND_DIE` p-p | `VPWR_DIE` p-p | worst mid-scale \|Δcode\| | wall clock |
|---|---|---|---|---|---|---|
| 0 (no decoupling) | — | — | **37.333 mV** | **61.755 mV** | 0 LSB | 1261 s |
| 32 (an affordability probe, **not** a proposal) | 141.916 pF | 140,775.04 µm² (130.2 % of die) | **9.214 mV** | **12.153 mV** | 0 LSB | 3323 s |
| 2 (**this record's decision**) | 8.870 pF | 8798.44 µm² (8.14 % of die) | ~~*not measured — see "Open items"*~~ **9.709 mV** † | ~~*not measured*~~ **12.799 mV** † | ~~*not measured*~~ 0 LSB † | > 3800 s |

- † The `MF = 2` cells were blank when this record was written; they have since
  been measured by
  `sim/supply-impedance-sensitivity/records/20260926-050045-8e62675.md` (issue
  #409 item 1, `package` arm at `tt_27c_1.80v`, one point of its nine-point
  grid). Grading them against this record's two-point prediction is left to
  #448. The wall-clock cell is this record's own dispatch-host observation and
  is unchanged.
- The `MF = 0` row is the committed baseline record
  `sim/supply-impedance-sensitivity/records/20260925-073912-0e385e5.md`
  (`package` arm, `tt_27c_1.80v`).
- The `MF = 32` row is **a probe, not a record**: it is a complete run of the
  same runner's own `run_point()` on the same `package` arm, corner and deck
  assembly, against a netlist that is not the committed design — so it mints no
  append-only evidence and moves no `records/LATEST`. It is reproducible in one
  step: set `MF=2` → `MF=32` on both `XCdecap_*` cards of
  `design/sar_adc_top.spice` and re-run the campaign's documented invocation. It
  exists to answer one question the decision needs: *how much is even
  purchasable on this axis?*
- **The `MF = 2` `package`-arm row is honestly blank.** Five attempts at the
  campaign's own indexed four-arm invocation were each terminated by this
  host's ~63-minute per-process budget with that one arm still running,
  including one attempt on an otherwise idle host. It is a **compute-resource
  gap, not a result**: no number for it is asserted, estimated-as-measured, or
  quoted anywhere in this record. Tracked as **#448**; the two arms of the same
  invocation that *did* complete against the as-committed netlist are below.

**The finding that drives this record: the excursion falls far more slowly than
the capacitance rises.** Thirty-two unit cells per domain — a MiM area 1.3× the
whole composed die — buys a factor of **4.05** on `GND_DIE` (37.333 → 9.214 mV)
and **5.08** on `VPWR_DIE`. That is what a bond-inductance tank whose impedance
goes as `√(L/C)` predicts, and fitting `ΔV(C_d) = ΔV₀ / √(1 + C_d/C_die)`
through those two points puts the design's own supply-pair capacitance at
`C_die ≈ 9.21 pF`. Under that fit `MF = 2` would read **26.64 mV** — **a
prediction from two points, not a measurement**, and the thing #448 exists to
confirm or refute.

> **REFUTED — read Amendment A.** The `MF = 2` point has since been measured at
> **9.709 mV**, 2.74× *below* this prediction. The response is not `1/√C`; it
> **saturates**, and 98.2 % of the reduction that 16× more capacitance achieves
> is already delivered at `MF = 2`. The fitted `C_die ≈ 9.21 pF` and every
> number derived from it (including the `1.03 nF` / 4.7-die-area figure below)
> are retracted by Amendment A. The *direction* of this paragraph's finding —
> that capacitance buys far less than proportionally — survives; its *law*,
> and therefore its claim that there is no knee to size to, does not.

### The as-committed netlist: two arms that did complete

Both ran `design/sar_adc_top.spice` at DUT netlist
`sha256:c93a2926b779922289539214d6f3471db7b2ffb95ba3b4dc97dee6279385fdb1`,
against the baseline record's
`sha256:96b3696ee9ecc84417c44f4bda51584e6a2cdd8d94c3ce9c4393993aef6c481f`,
under the same invocation, at `tt_27c_1.80v`. **The committed netlist's hash is
now `6a0be472…` instead**, and the difference is exactly one line: this record
was renumbered DR-016 → DR-017 after those runs (the number had been taken on
`main` meanwhile), which edits a schematic *comment* and therefore moves
`design/sar_adc_top.sch`'s own sha256 in the netlist's provenance header. The
device cards are byte-identical — `diff` of the two netlists is that single
header line — so the runs below are runs of this design, but a re-run will
re-simulate rather than hit `--log-cache` (the cache keys on the whole deck, as
it should).

| arm | `GND_DIE` p-p | `VGND_DIE` p-p | `VDD_DIE` p-p | `VPWR_DIE` p-p | captured codes | wall clock |
|---|---|---|---|---|---|---|
| `ideal` (with decoupling) | 0.000 mV | 0.000 mV | 0.000 mV | 0.000 mV | 214 / 383 / 511 / 641 / 1023 | 2073 s |
| `ideal` (baseline record, no decoupling) | 0.000 mV | 0.000 mV | 0.000 mV | 0.000 mV | 214 / 383 / 511 / 641 / 1023 | 554 s |
| `package-r-only` (with decoupling) | 0.059 mV | 0.086 mV | 0.059 mV | 0.086 mV | 214 / 383 / 511 / 641 / 1023 | 1534 s |
| `package-r-only` (baseline record) | 0.059 mV | 0.088 mV | 0.059 mV | 0.089 mV | 214 / 383 / 511 / 641 / 1023 | 312 s |

Two things these do establish, and they are not small:

1. **The two added devices are inert where they should be.** Under ideal
   supplies the captured codes are code-for-code identical to the baseline
   record's `ideal` row, and so is every average rail current to four
   significant figures — `I(VDD)` 2.097 µA, `I(VPWR)` 6.966 µA, `I(GND)`
   2.177 µA, `I(VREFP)` 6.470 µA, `I(VCM)` 0.014 µA, against the baseline
   record's 2.097 / 6.966 / 2.177 / 6.470 / 0.014. A capacitor across an ideal
   source cannot move that source's node voltage, and measurement agrees. This
   is the no-code-regression check the decision needs before adding any device.
2. **The mechanism claim is confirmed on its own negative control.** With the
   bond resistance present and the inductance zeroed, 8.870 pF per domain
   changes `GND_DIE` not at all (0.059 mV, both cases). A capacitor across the
   die's own supply/return pair does nothing to a purely resistive return —
   exactly what "Alternatives considered" says below, now measured rather than
   argued.

**A cost finding worth carrying forward.** DR-015 rejected adding decoupling
partly on the expectation that it would make the bonded arms "ring less and
simulate faster". The opposite is observed on every arm: 2073 s vs 554 s on
`ideal`, 1534 s vs 312 s on `package-r-only`, and > 3800 s vs 1261 s on
`package`. **Host load varied over the runs and is not controlled for**, so
these are not a clean 3–5× attribution — but the `ideal` arm is electrically
*unchanged* by the two devices and still took 3.7× longer, which no load
explanation alone covers. The plausible mechanism is the PDK MiM subcircuit's
own internal series resistance (`r1 = rm3·l/w`, a fraction of an ohm for a
square plate) against its capacitance: a sub-picosecond pole the transient
solver must resolve. Anyone budgeting a `--corners` or `--sweep` run on the
decoupled design should price it from these numbers, not from the undecoupled
record's.

**Consequence, stated before the decision so the decision is read against it:
1 LSB is not reachable on this axis.** `1 LSB_diff = 2·V_REF/2^N = 3.5156 mV`
(DR-003 Item 2). ~~Under the fitted law, reaching it from 37.333 mV needs
`C_d ≈ 112 × C_die ≈ 1.03 nF` per domain — about **510,000 µm²** of MiM,
**4.7× the composed die**.~~ **That arithmetic is retracted by Amendment A**:
it is a consequence of the refuted `1/√C` law, and the measured response
implies something stronger, not milder — the target is unreachable at *any*
on-die supply-pair capacitance, because the excursion bottoms out near
9.2 mV (2.6 LSB) and 16× the shipped allocation moves it 1.8 %. On-die
decoupling therefore *improves* this number;
it does not *solve* it. The lever that does is the bond inductance itself (a
packaging decision this repo has not made — DR-015's own closing consequence),
and that is where the residual is booked.

## Decision

1. **Add one `sky130_fd_pr__cap_mim_m3_1` decoupling capacitor per supply
   domain** at the top level of `design/sar_adc_top.sch` /
   `design/sar_adc_top.spice`, tied directly across that domain's own
   supply/return pair: `Cdecap_a` across `VDD`/`GND` (analog, the comparator's
   own decision reference) and `Cdecap_d` across `VPWR`/`VGND` (digital, the
   standard-cell bank). Both use the `W = L = 46.9 µm` unit cell above.
2. **Size both at `MF = 2` → 8.870 pF per domain**, 8798.44 µm² of MiM across
   both domains = **8.14 %** of the composed die's met3/met4 footprint.
3. **The sizing criterion is an area budget, not a bounce target**, because the
   measurement above shows a bounce target cannot be the criterion: the
   response is ~1/√C, so there is no knee to size to, and the value that would
   meet 1 LSB is ~4.7 die-areas of MiM. **[Amendment A restates this clause:
   there *is* a knee, `MF = 2` is at or past it, and the criterion is now that
   measured knee rather than the 10 % area budget — which the shipped value
   satisfies incidentally, and which must no longer be read as licence to
   *raise* `MF` if more met3/met4 turns out to be free.]** The budget is stated plainly and is a
   choice, not a derivation: **≤ 10 % of the composed die's footprint across
   both domains**, on the argument that a back-end-of-line device drawn over
   existing sub-blocks costs routing real estate rather than silicon, and that
   a tenth of the die's met3/met4 is a defensible first allocation to make and
   then check. `MF = 2` is the largest equal per-domain allocation that fits
   inside it (`MF = 3` would be 12.2 %).
4. **The bounce target this record states, and does not meet, is
   `≤ 1 LSB_diff = 3.5156 mV` peak-to-peak** on each domain's own die-side node
   under the `package` arm. It is stated rather than dropped because a number a
   reader can check is worth more than silence, and because the *gap* to it is
   what the residual open item is measured in. **This record does not relax
   it, and does not claim it** — it records that the target is unreachable on
   the axis this record controls, and names the axis that could reach it (the
   package).
5. **Both domains get the same value.** The digital rail bounces harder
   (61.755 vs 37.333 mV) but the analog one is the rail whose excursion is the
   comparator's own reference, and the two are tied together anyway through
   DR-015's lumped `R_SUBX = 30 Ω` substrate link — so an asymmetric split
   would be tuning one number of a two-node coupled network against a
   single-corner measurement. Equal allocation is the conservative choice here;
   an asymmetric one is re-openable once #409's grid says which domain actually
   binds.
6. **Placement is not decided by this record.** `Cdecap_a`/`Cdecap_d` exist in
   `design/` only. Where they land in `layout/sar-adc-top/`'s composed top
   level — and whether the composed die's met3/met4 can in fact carry 8798 µm²
   of `capm` without displacing routing — is explicit follow-on work; see "Open
   items". If that pass finds the real-estate claim in §3 does not hold, the
   fallback is to reduce `MF`, not to abandon the mechanism: the response is
   monotone, so a smaller cap is a smaller benefit and never a wrong one.

## Alternatives considered

- **No on-die decoupling at all — record why none is needed (#431's explicit
  second option).** Rejected, but it is the closest call in this record and the
  argument against it is not "the bounce is fatal" (it is not: 0 LSB moved at
  this corner) but *asymmetry of the alternatives*. Adding the caps is monotone
  beneficial (the response is monotone in `C`), costs no silicon and no pin,
  needs no new device flavour, and is the only lever this repo controls;
  declining forgoes a reduction the `MF = 32` point measures as real — a factor
  of 4.05 at 16× this allocation — in exchange for met3/met4 the layout has not
  yet been shown to need. What tips it is that the *sign* of the effect is
  measured even though the magnitude at `MF = 2` is not (#448): a capacitor
  across a bonded supply pair can only lower that pair's tank impedance. The
  honest framing is that this is a **cheap, partial** mitigation adopted with
  its limits stated, not a fix.
- **Adopt gf180-sar-adc's DR-0036 method verbatim (0.5 LSB target, the
  `C_local ≥ L·I_pk²/(2·ΔV_inst²)` closed form).** Rejected on both counts.
  The **method** cannot be evaluated here: DR-0036 itself states it needs a
  package loop-inductance model and a **peak** (not average) switching-current
  measurement, and while this repo has the first (DR-015), it has no
  equivalent of gf180-sar-adc's `sim/adc-rail-current/` for the second — `sim/`
  here reports only the *average* current over a whole conversion. Assuming a
  pulse width to back out a peak is the exact move DR-0036's own "Alternatives
  considered" rejects. The **0.5 LSB target** is calibrated to that system's own
  static droop budget (its DR-0034), which this repo has no equivalent of;
  importing the bare number detached from the budget it was derived against is
  the folklore failure mode DR-015's Context names.
- **Size from that closed form anyway with an illustrative `L` or `ΔV_inst`.**
  Rejected. DR-0036's own step-9 table is presented *as a demonstration that
  the answer is unconstrained across four orders of magnitude* without the
  missing inputs — it is a reason not to pick a number, not a method for
  picking one.
- **Sweep `MF` finely and pick the knee.** Rejected: there is no knee. A 1/√C
  response has none, and the two `package`-arm points that do exist bracket the
  whole affordable range — `C_d = 0` and `C_d = 141.9 pF`, a factor of 4.05 in
  excursion across everything a die this size could hold. Each further point is
  an hour or more of whole-ADC transient (see the probe's 3323 s, and #448 for
  the arm that does not finish at all on this host), and would refine a curve
  whose *shape* is the finding. The one point that would earn its cost is the
  shipped value's own, which is why it is an open item rather than a sweep.
- **Wait for #409's PVT grid and R/L sweep before sizing anything.** Rejected,
  per #431's filing comment and the Context above. The worst-corner number is
  still owed before the target in Decision §4 can be called anything other than
  unmet — but a schematic-level decision on a monotone, area-bounded mitigation
  does not need the worst corner to be right in direction.
- **Decouple the references (`VREFP`/`VREFN`/`VCM`) as well.** Not rejected —
  **out of scope and deliberately not decided here.** Those three terminals are
  driven by *ideal sources at the die* in `sim/supply-impedance-sensitivity/`
  by construction (that campaign is about DR-012's four *supply* terminals), so
  this repo currently has no measurement of what a reference-network impedance
  costs, and a capacitor sized against an unmeasured impedance would be a
  guess. It is named in "Open items" because the CDAC's bottom-plate switching
  is plausibly the largest single transient on this die and its return path is
  not a supply rail.
- **Size decoupling against the `substrate` arm instead of `package`.**
  Rejected: `substrate` is not an ablation of `package` (its resistance is
  ~300× larger, per the baseline record's own reading instructions), and a
  capacitor across the die's own supply/return pair does nothing to a purely
  resistive return — there is no inductance there to decouple. `package` is the
  arm whose mechanism this class of mitigation addresses.

## Spec lines affected

**No row of `spec/target-spec.md` changes**, and none is added — this record
sets a design decision and an area budget, not a spec-table value, in the same
sense DR-010/DR-012/DR-015 do.

- `design/sar_adc_top.sch`: two new `sky130_fd_pr/cap_mim_m3_1` instances,
  `Cdecap_a` (`VDD`↔`GND`) and `Cdecap_d` (`VPWR`↔`VGND`), at the top level.
  No existing net, port, or device is touched.
- `design/sar_adc_top.spice`: regenerated by `design/regen_netlist.sh`
  (mechanical, and CI-checked by `--check`). The two new `X` cards and the
  schematic sha256 in the provenance header are the whole diff.
- `spec/decision-records/DR-010-digital-supply-domain-partition.md` and
  `spec/decision-records/DR-012-analog-ground-pad.md`: their "on-die
  decoupling" open items now point here. Neither record's Decision or
  Consequences is edited — only the open-item pointer moves, per the
  append-only convention for standing records.
- `docs/chipalooza/challenge-4-proposal.md`: §3's top-level primitive census
  moves from 8 to 10 `sky130_fd_pr` instances (`cap_mim_m3_1` ×2 → ×4), which
  check 20 of `docs/chipalooza/check_proposal_citations.py` grades in both
  directions, so it is not optional. §4's Power row and §7 Item 1's DR-012
  retirement paragraph both still cite the *undecoupled* record
  `20260925-073912-0e385e5` and stay correct while that record remains
  `records/LATEST`; they move when #448 mints the decoupled one.

## Consequences

- **The target in Decision §4 is not met, and is not claimed.** The as-shipped
  `MF = 2` excursion ~~is unmeasured (#448)~~ has since been measured at
  9.709 mV `GND_DIE` pp (`records/20260926-050045-8e62675.md`; ~~grading it
  against this record is #448's~~ **graded in Amendment A**); ~~the value the
  two-point fit predicts for it, 26.64 mV, is 7.6× the 3.5156 mV target~~ **the
  measured 9.709 mV is 2.76× the 3.5156 mV target**, and the *best affordable*
  point measured on this axis — a MiM area 1.3× the whole die — is still 2.6×
  it. No reading of this record supports a claim that the die-side bounce meets
  1 LSB. **Amendment A adds the worst corner of the ratified grid: 13.964 mV
  (3.972 LSB) at `ff_27c_1.80v`, on the as-shipped netlist.**
- **Captured code is unchanged wherever it has been checked.** Both completed
  arms on the as-committed netlist reproduce the baseline record's captured
  codes exactly (214 / 383 / 511 / 641 / 1023), as does the `MF = 32` probe on
  the `package` arm. This record adds no code-correctness regression to
  anything already on record — and, under ideal supplies, adds nothing at all:
  the two devices are inert there to four significant figures of every rail
  current.
- **DR-015's Decision clause 6 ("no decoupling is modelled, deliberately") is
  now false of `design/`, and DR-015's own Consequences anticipated it** ("When
  a decoupling plan exists, this assumption gains a second, decoupled
  variant"). Two places that asserted the old premise are corrected in the same
  change as this record: `sim/supply-impedance-sensitivity/README.md` and that
  runner's own sweep-record writer. Both now say that on-die decoupling is
  whatever `design/sar_adc_top.spice` commits, that no *board* decoupling is
  modelled in any case, and that a record's own DUT netlist sha256 is how to
  tell which case it is. The baseline record `20260925-073912-0e385e5` stands
  unedited and is **not** superseded: it remains the only committed measurement
  of the undecoupled design.
- **Every `sim/` campaign that drives this netlist is now materially more
  expensive.** See the wall-clock finding under "What was measured": the
  electrically-inert `ideal` arm still took 3.7× longer with the two devices in.
  A `--corners` or `--sweep` run on the decoupled design must be budgeted from
  the decoupled numbers, and one arm of the campaign now exceeds this dispatch
  host's per-process budget outright (#448).
- **`design/sar_adc_top.spice`'s device count moves 869 → 871**, so every
  DRC/LVS record under `layout/sar-adc-top/reports/` is now stale against the
  schematic by two devices. **That staleness will not clear by re-running the
  reference generator.** `layout/sar-adc-top/bin/generate-lvs-reference.py`
  emits no top-level primitive devices at all: its `.SUBCKT sar_adc_top`
  wrapper is a hardcoded template (that file's `TOP_SUBCKT`, lines 40–79) that
  instantiates exactly the five sub-blocks — `Xfe` / `Xcdac` / `Xcmp` / `Xseq`
  / `Xinv` — and nothing else. So its `869` was never a count of
  `design/sar_adc_top.spice`'s devices; it is the count of the five composed
  sub-blocks, and it already omits DR-009's eight top-level analog devices
  (`Choff_n`/`Choff_p` and their six `Moff_*` drive FETs) and the 33
  top-level `sky130_fd_sc_hd` glue cells. Re-running that generator on this
  tree reproduces the committed
  `layout/sar-adc-top/reports/20260924-234053-66dca3c/sar_adc_top.lvs-reference.spice`
  byte-for-byte, with zero `Cdecap` cards. This is a pre-existing limitation of
  that script, not something this record changes — emitting an 871-device
  reference therefore requires a code change to it, and is part of the layout
  work tracked as **#440** (alongside the `capm`-drawing generator the Open
  items below already name). Named here so that a future LVS device-count delta
  is traceable to this record rather than rediscovered, and so that #440's
  builder does not expect `871` from an unmodified re-run.
  **Update (issue #440, 2026-09-26): that code change is made.** The generator
  now emits four `cap_mim_m3_1` cards — the first top-level primitives it has
  ever carried, two per domain, matching how the layout draws `MF = 2` — and the
  reference reaches **871** devices. It still emits neither DR-009's eight
  top-level analog devices nor the 33 glue cells, because the layout does not
  place those either; the rule that file now follows is "one card per device the
  composed layout actually draws", so the remaining gap against
  `design/sar_adc_top.spice` stays a *layout* gap, tracked where the layout is.
- ~~**An area cost no `layout/` record yet reflects.**~~ **Reflected — and it
  turned out not to be an area cost (issue #440).** 8798.44 µm² (8.14 % of the
  composed die) was a schematic-level planning figure; record
  `layout/sar-adc-top/reports/20260926-081248-203cca3/` places both devices and
  reports the composed bounding box **unchanged** at 280.450 × 385.500 µm. Both
  sites are in back-end field that a direct occupancy measurement found free
  (met3 88 % free, met4 97 % free, zero clash at a 1.0 µm keep-out), so the
  allocation displaced no routing and grew no die: 8.14 % is the share of the
  die's *`capm` layer*, not of its area budget. What the placement *did* cost is
  series resistance — see the routing-parasitics item under "Open items".

## Open items

- ~~**The shipped value's own `package`-arm number is not measured, and no
  estimate stands in for it.**~~ **Since measured**:
  `sim/supply-impedance-sensitivity/records/20260926-050045-8e62675.md` (issue
  #409 item 1) records `GND_DIE` 9.709 mV / `VPWR_DIE` 12.799 mV pp at
  `tt_27c_1.80v` on the as-committed `MF = 2` netlist; grading that against
  Decision §3/§4's 1/√C model remains #448's. The text below is kept as
  written. The `MF = 2` row of the sizing table above is
  blank on purpose: five attempts at the campaign's own indexed four-arm
  invocation were each terminated by this dispatch host's ~63-minute
  per-process budget with that one arm still running, one of them on an
  otherwise idle host. The other three arms complete and are
  `--log-cache`-restartable; `package` alone is not. The batch route this host's
  rules would otherwise prefer is closed for this campaign for two reasons
  already recorded in its own README: `klt sim` owns a different
  request/response contract and cannot mint a record in this repo's format, and
  the fleet's runner image ships ngspice-42, below `sim/toolchain.json`'s
  `ngspice_min_major = 46` floor. So this is a **compute-resource gap** — a host
  that can hold one process for longer than an hour — and it is tracked as
  **#448**, which also states what must happen if the measurement refutes the
  1/√C model Decision §3 and §4 both rest on (a superseding record, not a
  wording fix).
- ~~**Layout placement, and DRC/LVS/ERC re-verification, are not done by this
  record.**~~ **Done — issue #440, and Decision §3's area budget is CONFIRMED
  placeable at `MF = 2`.** Record
  `layout/sar-adc-top/reports/20260926-081248-203cca3/` places both capacitors
  as four `klt gen cap_array` unit cells (two per domain, which is how `MF = 2`
  is drawn), tied across their own domains' supply/return conductors: DRC clean
  (0 violations / 52 rules), `klt erc` clean (0 findings, all four supplies at
  one island each on the new geometry, `erc-reports/20260926-081822-203cca3/`),
  and `klt lvs` against a regenerated **871**-device reference in the same four
  mismatch categories as before, the one moved count being `device.unmatched`
  66 → 67 (the already-tracked DR-012 substrate merge reaching a device, not a
  new category). **No superseding record reducing `MF` is needed**: the
  composed die's own back-end occupancy was measured directly before the
  placement (`bin/probe-decap-sites.py`, committed as that record's
  `decap-ties.json`) and met3 — the tightest of the six layers involved,
  because it is both a routing plane and the MiM bottom plate — was **88 %
  free**, met4 **97 % free**. Both sites fall inside the *pre-existing*
  280.450 × 385.500 µm bounding box, so **the allocation cost no die area at
  all** and displaced no routing. The two enabling gaps this item named are
  closed the way it anticipated: the composer now generates the MiM unit cell
  in-flow with `klt gen cap_array` rather than drawing `capm` by hand, and
  `bin/generate-lvs-reference.py` emits top-level primitives for the first
  time. Full measurement, corridors and interconnect:
  `layout/sar-adc-top/README.md`, "On-die decoupling (DR-017)".
- **No peak switching-current measurement exists in this repo.** A
  `sim/adc-rail-current/`-equivalent campaign (fine-timestep current
  integration bracketing the CDAC/comparator switching instants) would let a
  future record replace this one's empirical sizing with the closed form
  gf180-sar-adc's DR-0036 derives. Not built here.
- **The reference network is undecoupled and unmeasured.** `VREFP`/`VREFN`/
  `VCM` are ideal at the die in every `sim/` campaign in this repo, so the
  CDAC's bottom-plate switching current — plausibly the largest transient on
  this die — has never been driven through a realistic impedance. Until it is,
  neither this record nor DR-015 can say what fraction of the residual
  `GND_DIE` excursion is even *addressable* by supply-pair decoupling.
- ~~**The worst-case PVT grid is still owed**, unchanged from DR-012's and
  DR-015's standing items and #409's scope: this record's numbers are one
  corner (`tt_27c_1.80v`). When #409 lands a full-grid re-run on `main`, it
  should be run **with** this record's decoupling in the netlist too, so the
  worst-corner bounce is known for the as-decided design and not only for the
  undecoupled baseline.~~ **Done, exactly as asked**:
  `records/20260926-050045-8e62675.md` is that full-grid re-run and it ran on
  the as-shipped decoupled netlist; Amendment A reads the worst corner off it
  (13.964 mV `GND_DIE` pp at `ff_27c_1.80v`). **What stays open**: the
  undecoupled baseline is still one corner, so there is no worst-corner-to-
  worst-corner decoupled/undecoupled comparison — only the `tt_27c_1.80v` pair.
  And note that the MiM area coefficient itself moves
  ±11 % across the PDK's own cap corners, which **neither** that grid nor this
  record's own nominal-corner sizing exercises: the grid walks
  process/temperature/voltage, not the PDK's `mim` cap corner.
- **The residual belongs to the package, and no packaging decision exists.**
  The gap between the measured excursion and Decision §4's 3.5156 mV target is
  set by bond inductance, which this repo has not chosen. DR-015's own closing
  consequence already says a packaging decision supersedes it; this record adds
  that such a decision is also the only route to the target stated here.
- **A real substrate/package extraction** would let this record's numbers
  graduate from "meets a stated area budget under a stated assumption" to a
  measured margin. Carried over from DR-012/DR-015 rather than settled here —
  the lumped `R_SUB`/`R_SUBX` stand-ins and DR-015's bond geometry are both
  still assumptions, and this record's sizing inherits whatever slack or
  overreach they carry.
- **Routing parasitics between each cap and its domain's switching devices are
  not modelled — but the resistance half is now MEASURED on the drawn layout,
  and it is three orders of magnitude larger than anything any simulation here
  has contained.** This record adds an ideal `cap_mim_m3_1`, and issue #440's
  placement quantifies what the drawn ties cost: **13.837 Ω of ESR on the
  analog domain and 13.448 Ω on the digital**, at the PDK's own
  `rm2`/`rm3`/`rm4` sheet and `rcvia2`/`rcvia3`/`rcvia4` per-cut resistances.
  **~80 % of it is single-cut vias**, not metal — three 3.41 Ω cuts in each
  return path against one in each supply path — so widening the 2.0 µm straps
  would buy almost nothing while via arrays would cut it ≈3×.

  **Amendment A below does not already cover this, and must not be read as
  doing so.** Its "Eliminating one obvious explanation for the floor" section
  eliminates the *device's own* plate resistance, the MiM subcircuit's
  `r1 = rm3·l/w` — one square for a 46.9 µm plate, so `0.047 Ω` per unit and
  `0.0235 Ω` for the shipped pair. That is the largest ESR present in *any*
  measured point of its ladder, and the interconnect carries **~590×** it. The
  `MF = 32` step Amendment A reasons from moved ESR between `0.0015 Ω` and
  `0.024 Ω`; the layout's is `13.8 Ω`. Amendment A's conclusion (the residual
  floor is not ESR-limited) stands on its own evidence and is not contradicted
  here — it simply was never a measurement at this magnitude, because no
  netlist in this repo has ever contained the interconnect at all.

  What the measured ESR does and does not license, read against the pair's own
  reactance: ESR does not reach `X_C` until ~1.3 GHz, so the pair still behaves
  as a capacitor across the band the bounce lives in. But at the **1221.5 MHz**
  resonance 8.870 pF forms with DR-015's 1.914 nH per-terminal package
  inductance, **Q ≈ 1.06** — the ties are *comparable to* the reactance there,
  so the ideal-cap excursion this record reports is optimistic at the top of the
  band by an amount no simulation here has bounded, while a Q near 1 also damps
  that resonance in the bounce's favour. **The sign of the net effect is
  unmeasured**, and closing it needs a `sim/supply-impedance-sensitivity/` run
  with the ESR in the netlist — which would also be the first run in this
  campaign to distinguish device ESR from interconnect ESR. The inductance half
  remains unmodelled entirely, needing extraction. Numbers and derivation:
  `layout/sar-adc-top/README.md`, "On-die decoupling (DR-017)", and
  `bin/probe-decap-sites.py`, which fails the layout flow if its model drifts
  from the drawn geometry.

## Amendment A (issue #431, 2026-09-26): the `1/√C` model is refuted by the shipped value's own measurement

**Read this section before quoting any capacitance-scaling number from the body
above.** The body sized `MF = 2` without ever measuring `MF = 2` on the arm the
sizing argument is about, and said so plainly — the row was left blank and
tracked as #448. That measurement now exists, on `main`, on the as-committed
netlist, and it **refutes the `1/√C` law the body fitted through its other two
points**. The refutation runs in the design's favour: the shipped capacitor is
**2.7× more effective than the body predicted**, and the reason the 1 LSB
target is unreachable is stronger and simpler than the body's arithmetic said.

**Decision §1, §2 and §6 stand unchanged.** One
`sky130_fd_pr__cap_mim_m3_1` per supply domain, `MF = 2` → 8.870 pF each,
placement still deferred to #440. **Nothing in `design/` changes.** What changes
is the *reason* `MF = 2` is right (§3), the *arithmetic* behind the target
verdict (§4, same verdict), and the *disposition* of §5's deferred question.

### Where the measurement came from

`sim/supply-impedance-sensitivity/records/20260926-050045-8e62675.md` — issue
#409 item 1, the full ratified nine-point PVT grid × five arms, minted
2026-09-26. It was **not** run for this record, and it does not mention
decoupling; it identifies its DUT by hash, which is exactly the mechanism this
record's own Consequences named as "how to tell which case it is":

> `- DUT netlist sha256: 6a0be472ef845710dbdce0aa68c4e6ede8c4894c1e0368fe19281a87bc926b7f`

That is the hash of `design/sar_adc_top.spice` as this record committed it,
`MF = 2` cards included. So the grid is a measurement of **this** decision's
netlist, and the `package` arm at `tt_27c_1.80v` is the row the blank cell
wanted. The comparison is arm-for-arm legitimate: same runner, same committed
stimulus fragment (`d819f870…`), same DR-015 package assumption, same
`R_SUBX = 30 Ω`, same corner. The grid's fifth arm (`no-gnd-pad`) changes no
other arm's deck.

One independent check that the two runs are comparable at all: the average rail
currents on the `package` arm are the same to three or four significant figures
across the netlist change — `I(VDD)` 2.121 → 2.113 µA, `I(VPWR)` 6.502 →
6.546 µA, `I(GND)` 2.204 → 2.198 µA, `I(VREFP)` 6.503 → 6.503 µA. A decoupling
capacitor is not supposed to change how much charge the conversion consumes,
only where it comes from on the short timescale, and it does not.

### Grading the prediction

`package` arm, `tt_27c_1.80v`, peak-to-peak die-side excursion:

| `MF` | `C` per domain | `GND_DIE` measured | body's `1/√C` prediction | `VPWR_DIE` measured | that law's `VPWR_DIE` prediction |
|---|---|---|---|---|---|
| 0 | — | 37.333 mV | *(fit anchor)* | 61.755 mV | *(fit anchor)* |
| **2** | **8.870 pF** | **9.709 mV** | 26.64 mV | **12.799 mV** | 38.67 mV |
| 32 | 141.916 pF | 9.214 mV † | *(fit anchor)* | 12.153 mV † | *(fit anchor)* |

† The `MF = 32` row is the body's own probe, **not committed evidence** — see
the body's "What was measured". Which half of this amendment depends on it
matters, so it is stated once and not blurred: the **refutation** below does
not need it (it is the body's own published prediction against a committed
measurement), while the **saturation shape** does.

**Verdict: refuted, on both domains, in the same direction.** The body's fit
over-predicts the shipped value's excursion by **2.74×** on `GND_DIE`
(26.64 vs 9.709 mV) and **3.02×** on `VPWR_DIE` (38.67 vs 12.799 mV). Two
nodes in two different supply domains, refuted by the same factor to within
10 % — this is not a corner artefact or a single bad `.meas`.

The other two die-side nodes the same two records both report agree, and they
were never part of any fit: `VGND_DIE` 40.817 → 10.790 mV (3.78×) and
`VDD_DIE` 25.108 → 8.968 mV (2.80×). All four die-side supply nodes improve by
2.8–4.8× from 8.870 pF per domain.

### What the three points say instead: the response saturates

The body's `1/√C` reading came from having only the endpoints, where a
saturating curve and a slow power law are indistinguishable. With the middle
point in, they are not:

- **Between `MF = 2` and `MF = 32` — a 16.0× increase in capacitance — the
  excursion falls 9.709 → 9.214 mV.** That is **1.054×**, where the fitted law
  requires 2.89×.
- **`MF = 2` already captures 98.2 % of the total reduction** that 16× more
  capacitance achieves (27.624 mV of 28.119 mV). On `VPWR_DIE`, 98.7 %
  (48.956 of 49.602 mV).
- **Marginal value collapses by ~840×.** The first 8.870 pF per domain buys
  3.11 mV/pF. The next 133.046 pF buys 0.0037 mV/pF — 0.495 mV total, in
  exchange for a further 131,976 µm² of MiM, **122 % of the whole composed
  die**.
- **There is an empirical floor near 9.2 mV** (2.62 LSB_diff) at this corner,
  and `MF = 2` sits within **5.4 %** of it. Equivalently: **at least 24.7 % of
  the undecoupled 37.333 mV is not removable by supply-pair capacitance** at
  any allocation this die could hold.

So the body's Decision §3 was right that a bounce target cannot be *met*, and
wrong about why: not "no knee, so size by area" but **"a knee, and `MF = 2` is
at or just past it, and past it there is a floor decoupling cannot reach."**

**What this amendment does not claim.** It does not claim a functional form.
Three points fit a three-parameter saturating curve exactly, which proves
nothing about shape; every statement above is a ratio between measured points,
not a law. It does not locate the knee — the interval between 0 and 8.870 pF is
unmeasured, so "`MF = 2` is at or past the knee" is an upper bound on the
knee's position, not a measurement of it. And the floor is an *empirical* one:
no measured point lies below 9.214 mV, which is not the same as a proof that
none could.

### Eliminating one obvious explanation for the floor, and naming the likely one

**It is not the capacitor's own series resistance.** The PDK's MiM subcircuit
carries a plate resistance `r1 = rm3·l/w`; `MF` unit cells in parallel divide
it by `MF`, so the `MF = 32` point has **1/16** the ESR of the shipped one. An
ESR-limited response would have improved substantially over that step. It
improved 1.8 %. ESR is not what the excursion is resting on.

**The likely mechanism is current whose loop does not contain the decoupled
pair — and this is a hypothesis, not a measurement.** `VREFP`/`VREFN`/`VCM` are
driven by *ideal sources at the die* in this campaign by construction (it is a
campaign about DR-012's four *supply* terminals). Charge the CDAC draws from
`VREFP` returns to the board through `GND`'s own bond inductance, and a
capacitor tied across `VDD`/`GND` is not in that loop — it can only circulate
current between those two nodes. The magnitudes are consistent with that being
material rather than marginal: on this arm and corner the reference terminal
carries **3.1× the analog supply's own average current** (`I(VREFP)` 6.503 µA
vs `I(VDD)` 2.113 µA). The second candidate is the lumped `R_SUBX = 30 Ω`
link, which injects the digital ground's own excursion into `GND_DIE`
regardless of what either supply pair is decoupled with.

Both remain hypotheses: these are **average** currents over a whole conversion,
not the peak transients that set a bounce, and this repo has no peak-current
campaign (already an open item above). The measurement that would settle it is
also already an open item above — *"The reference network is undecoupled and
unmeasured"* — and this amendment raises its priority rather than adding a new
one: it is now the item standing between this design and any further reduction
of `GND_DIE`, because the axis this record controls is spent.

### The worst corner, now that the grid exists

The same record supplies what the body could not: the as-shipped design across
the full ratified nine-point grid, `package` arm, `GND_DIE` peak-to-peak —

| corner | mV | | corner | mV |
|---|---|---|---|---|
| `ff_27c_1.80v` | **13.964** (worst) | | `tt_125c_1.80v` | 9.617 |
| `tt_27c_1.98v` | 13.535 | | `tt_27c_1.80v` | 9.709 |
| `fs_27c_1.80v` | 11.415 | | `ss_27c_1.80v` | 8.952 |
| `tt_-40c_1.80v` | 11.318 | | `tt_27c_1.62v` | 7.710 (best) |
| `sf_27c_1.80v` | 9.917 | | | |

- **Worst `GND_DIE` = 13.964 mV = 3.972 LSB_diff**, at `ff_27c_1.80v`. The
  baseline corner this record sized at is **70 %** of the worst; the grid
  spreads 1.81× end to end.
- **Worst `VPWR_DIE` = 15.531 mV = 4.418 LSB_diff**, at `tt_27c_1.98v` — a
  *different* corner from the analog node's worst.
- **Worst mid-scale |Δcode| on the `package` arm across all nine points = 1 LSB**
  (that record's own Findings). The decoupled design moves at most one code
  anywhere on the ratified grid.

**This is not a worst-case comparison against the undecoupled design**, and must
not be quoted as one: the undecoupled baseline was only ever run at
`tt_27c_1.80v`, so the only like-for-like pair in this repo remains
37.333 → 9.709 mV at that one corner. 13.964 mV (decoupled, `ff`) against
37.333 mV (undecoupled, `tt`) compares two different corners and is worth
nothing.

### What this changes in the Decision above

1. **§3's criterion is restated: the measured knee, not the area budget.**
   `MF = 2` is retained because 16× more capacitance buys 1.8 %, not because it
   is the largest allocation fitting inside 10 % of the composed die. The area
   budget is now **satisfied incidentally and is no longer the binding
   constraint** — which cuts the way that matters for #440: if a layout pass
   finds *more* met3/met4 free than the body assumed, that is **not** a reason
   to raise `MF`. Raising it is now positively rejected, on measurement.
2. **§4's verdict is unchanged and its reason is stronger.** The target
   (`≤ 1 LSB_diff = 3.5156 mV`) is still stated and still not met: 9.709 mV
   (2.76 LSB) at the baseline corner, 13.964 mV (3.97 LSB) at the worst. The
   body's route to it — `≈ 1.03 nF` per domain, 4.7 die-areas — is **retracted**
   as a consequence of the refuted law. The correct statement is that **no
   on-die supply-pair capacitance reaches the target**, because the response
   bottoms out near 2.6 LSB. The residual still books to bond inductance, which
   is still a packaging decision this repo has not made.
3. **§5's deferred question is closed, not answered.** The body deferred an
   asymmetric per-domain split until "#409's grid says which domain actually
   binds". The grid has landed, and the honest reading is that the question is
   now **moot**: both domains are already within ~5 % of their own floors at
   `MF = 2`, so there is nothing to win by moving allocation between them, and
   a reallocation could only push whichever domain it shrinks back toward its
   knee. Equal allocation stands. (For the record, the grid does not hand over
   a single binding domain either: `GND_DIE` is worst at `ff_27c_1.80v` and
   `VPWR_DIE` at `tt_27c_1.98v`, and the analog node — smaller in mV — is the
   one that is the comparator's own reference.)
4. **§6's fallback gains a caveat #440 needs.** The body told #440 that if the
   met3/met4 real estate does not hold, reducing `MF` is safe because "the
   response is monotone, so a smaller cap is a smaller benefit and never a wrong
   one". Monotonicity is not in question, but the *cost* of a reduction is no
   longer small and no longer known: `MF = 2` sits near a knee whose position
   below 8.870 pF **has not been measured**, so a reduction to `MF = 1` could
   cost anywhere between nothing and most of the 3.84× this record buys. **A
   reduction below `MF = 2` must be measured, not assumed** — it needs the
   `package`-arm point at the reduced value, in a superseding record, exactly as
   the body already instructed for the area question.

### Why this is an amendment and not a superseding record

#448 stated, reasonably, that a refutation of the `1/√C` model would be "a
superseding-record question, not a wording fix", because Decision §3 and §4
both rest on that model. The distinction this amendment draws is between a
record's **decision** and its **rationale**. Nothing here changes what the
design does: the same two devices, at the same value, in the same places, with
the same target stated and unmet. What changed is that the argument offered for
that value was wrong, and the corrected argument supports the same value more
firmly than the original did. A superseding record would retire a decision that
the evidence has just confirmed, and would fork the citation trail of a record
four documents already point at. This repo's own precedent for that shape is
DR-004's Amendment A, which changed a *topology* in place; changing a rationale
while keeping the decision is a strictly smaller move.

**What would have forced a superseding record**, and did not happen: a measured
`MF = 2` point that made `MF = 2` the *wrong* value — either far worse than the
body assumed (in which case the area budget would have to be re-argued against
a real bounce target) or so good that the target became reachable (in which case
§4's verdict would flip). The measurement did neither. The two clauses that are
*substantively* rewritten here (§3's criterion, §5's disposition) are both
recorded above in full rather than edited in the body, and the body's refuted
numbers are struck in place with pointers here.

### What Amendment A leaves open

- **The knee is bounded, not located.** No point exists between 0 and 8.870 pF
  per domain. One `package`-arm run at `MF = 1` would locate it and directly
  de-risk §6's fallback for #440. It was **attempted for this amendment and
  abandoned**: the host was carrying a load average of ~24 from a concurrent
  campaign in another repository and the control arm timed out on its first
  attempt, so the run was killed rather than added to the contention. It is a
  ~26-minute two-arm run on an uncontended host (344 s + 1190 s at this corner,
  from the grid record's own wall clock), and it mints no record — it is a probe
  on a non-committed netlist, exactly like the body's `MF = 32` point.
- **The `MF = 32` point is still not committed evidence.** The saturation claim
  above leans on it. Promoting it to a record means running the campaign's
  indexed invocation against an `MF = 32` netlist that this design does not
  ship, which is not obviously worth an hour of transient; the alternative, and
  the cheaper one, is the `MF = 1` probe above, which tests the same shape from
  the side the decision actually lives on.
- **The cap-corner axis is untouched.** The MiM area coefficient moves ±11 %
  across the PDK's own `mim` corners (body, "Die area"), and neither the
  nine-point grid nor any measurement here walks it — the grid varies
  process/temperature/voltage only. So every capacitance in this record is a
  nominal-corner capacitance.
- **The floor's mechanism is unattributed.** ESR is eliminated above; the
  reference-return and `R_SUBX` candidates are not distinguished from each
  other, and both are argued from average rather than peak currents. Until the
  reference network is driven through a real impedance, this record cannot say
  what fraction of the 9.2 mV floor is even *addressable* by any on-die device.
- **`records/LATEST` still names the undecoupled record** and this amendment
  does not move it. That pointer is load-bearing for DR-012's retirement
  paragraph and the chipalooza proposal's Power row, both of which are about the
  *undecoupled* upper bound on purpose. Re-pointing it is #448's call, not this
  amendment's.

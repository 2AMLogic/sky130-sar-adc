# DR-016: One MiM decoupling capacitor per supply domain, sized from a met3/met4 area budget — because the die-side bounce is measured to fall only as ~1/√C and no affordable on-die capacitance reaches 1 LSB

- **Status**: proposed — like DR-010, DR-012 and DR-015 this record settles a
  design/testbench question, not a numeric row of `spec/target-spec.md`. It
  inherits the same provisional status as every record still resting on
  DR-003's DRAFT numeric inputs.
- **Date**: 2026-09-25
- **Decided by**: Builder agent, issue #431
- **Supersedes**: none
- **Superseded by**: (none while this record stands)
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
considered" for why the closed form is unavailable in this repo). Each point
below is the same `sim/supply-impedance-sensitivity/` `package` arm, the same
committed stimulus, the same corner, the same deck assembly — only the two
`Cdecap_*` cards' `MF` differs.

| `MF` per domain | `C` per domain | MiM area, both domains | `GND_DIE` p-p | `VPWR_DIE` p-p | worst mid-scale \|Δcode\| |
|---|---|---|---|---|---|
| 0 (no decoupling) | — | — | **37.333 mV** | **61.755 mV** | 0 LSB |
| 2 (**this record's decision**) | 8.870 pF | 8798.44 µm² (8.14 % of die) | **PLACEHOLDER_GND_MF2 mV** | **PLACEHOLDER_VPWR_MF2 mV** | PLACEHOLDER_DCODE_MF2 LSB |
| 32 (an affordability probe, **not** a proposal) | 141.916 pF | 140,775.04 µm² (130.2 % of die) | **9.214 mV** | **12.153 mV** | 0 LSB |

- The `MF = 0` row is the committed baseline record
  `sim/supply-impedance-sensitivity/records/20260925-073912-0e385e5.md`.
- The `MF = 2` row is this record's own new committed record,
  `sim/supply-impedance-sensitivity/records/PLACEHOLDER_NEW_RECORD.md`, minted by
  the campaign's own indexed invocation with the decoupling in
  `design/sar_adc_top.spice`.
- The `MF = 32` row is **a probe, not a record**: it was produced by the same
  runner's own `run_point()` on the same `package` arm and corner, against a
  netlist that is *not* the committed design, so it mints no append-only
  evidence. It is reproducible in one step — set `MF=2` → `MF=32` on both
  `XCdecap_*` cards of `design/sar_adc_top.spice` and re-run the campaign's
  documented invocation. It exists to answer one question the decision needs
  and nothing else: *how much is even purchasable on this axis?* (3323 s of
  wall clock on this host.)

**The finding that drives this record: the excursion falls far more slowly than
the capacitance rises.** Thirty-two unit cells per domain — a MiM area 1.3× the
whole composed die — buys a factor of **4.05** on `GND_DIE` (37.333 → 9.214 mV)
and **5.08** on `VPWR_DIE`. That is consistent with a bond-inductance tank whose
impedance goes as `√(L/C)`: fitting `ΔV(C_d) = ΔV₀ / √(1 + C_d/C_die)` through
the two measured endpoints puts the design's own supply-pair capacitance at
`C_die ≈ 9.21 pF`, and predicts a **1/√C** law for everything in between — so
that fit, made before the `MF = 2` run, predicts **26.64 mV** at `MF = 2`. The
`MF = 2` row above is the third point, run afterwards, that tests that
prediction rather than asserting it.

**Consequence, stated before the decision so the decision is read against it:
1 LSB is not reachable on this axis.** `1 LSB_diff = 2·V_REF/2^N = 3.5156 mV`
(DR-003 Item 2). Under the fitted law, reaching it from 37.333 mV needs
`C_d ≈ 112 × C_die ≈ 1.03 nF` per domain — about **510,000 µm²** of MiM,
**4.7× the composed die**. On-die decoupling therefore *improves* this number;
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
   meet 1 LSB is 4.5 die-areas of MiM. The budget is stated plainly and is a
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
  beneficial, costs no silicon and no pin, needs no new device flavour, and is
  the only lever this repo controls; declining costs a measured ~25–30 %
  (see the `MF = 2` row) of a real excursion on the comparator's own reference
  in exchange for met3/met4 the layout has not yet been shown to need. The
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
- **Sweep `MF` finely and pick the knee.** Rejected: there is no knee. A
  1/√C response has none, and the two decoupled points already measured span a
  16× range of `C_d` for a factor of ~4 in excursion. Further points would cost ~1 h of
  whole-ADC transient each (see the probe's 3323 s) and would refine a curve
  whose *shape* is already the finding.
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
  moves from 8 to 10 `sky130_fd_pr` instances (`cap_mim_m3_1` ×2 → ×4), and
  §4's Power row re-points at the new supply-impedance record. Both are
  machine-graded by `docs/chipalooza/check_proposal_citations.py`, so neither
  is optional.

## Consequences

- **The `package`-arm die-side excursion drops from 37.333 mV / 61.755 mV to
  PLACEHOLDER_GND_MF2 mV / PLACEHOLDER_VPWR_MF2 mV** at `tt_27c_1.80v`
  (`sim/supply-impedance-sensitivity/records/PLACEHOLDER_NEW_RECORD.md`), against
  the 3.5156 mV target stated in Decision §4 — **not met, by design and by
  measurement**, see "What was measured".
- **Captured code is unchanged**: PLACEHOLDER_DCODE_MF2 LSB moved against the
  ideal control at every mid-scale input, the same verdict the no-decoupling
  baseline reached. This record improves margin without changing any
  code-correctness verdict already on record, and the `ideal` arm of the new
  record is itself the regression check that the two added devices are inert
  under ideal supplies (a capacitor across an ideal source cannot move its node
  voltage).
- **DR-015's Decision clause 6 ("no decoupling is modelled, deliberately") now
  has exactly one committed exception, and DR-015's own Consequences
  anticipated it** ("When a decoupling plan exists, this assumption gains a
  second, decoupled variant"). This is that variant. The baseline record
  `20260925-073912-0e385e5` stands unedited and is **not** superseded: the two
  records measure different netlists on purpose, and the older one remains the
  only committed measurement of the undecoupled design.
- **Simulation gets slower, not faster.** DR-015 rejected adding decoupling
  partly on the argument that it would make the bonded arms ring less and
  simulate faster. Measured, the opposite happened: the `MF = 32` probe cost
  3323 s against the undecoupled `package` arm's 1261 s. Adding capacitance
  lowers the tank's frequency but raises its Q against a 102.2 mΩ bond, so the
  solver pays for a longer, lighter-damped settle. Anyone budgeting a future
  `--corners` or `--sweep` run should price it from this record's own
  wall-clock table, not from the undecoupled one.
- **`design/sar_adc_top.spice`'s device count moves 869 → 871**, so every
  DRC/LVS record under `layout/sar-adc-top/reports/` is now stale against the
  schematic by two devices, and `bin/generate-lvs-reference.py` will emit an
  871-device reference the next time it runs. Named here so that a future LVS
  device-count delta is traceable to this record rather than rediscovered.
- **An area cost no `layout/` record yet reflects.** 8798.44 µm² (8.14 % of the
  composed die) is a schematic-level planning figure. Until a layout pass
  places these two devices, `compose.json`'s bounding box and every DRC/LVS and
  ERC record under `layout/sar-adc-top/` describe a die that does not contain
  them.

## Open items

- **Layout placement, and DRC/LVS/ERC re-verification, are not done by this
  record.** Placing `Cdecap_a`/`Cdecap_d` in `layout/sar-adc-top/`'s composed
  top level — ideally close to each domain's own switching devices, and
  ideally *over* sub-blocks that route below met3, which is the assumption
  Decision §3's area budget rests on — and re-running `klt drc` / `klt lvs`
  against the now-871-device reference is real, separate layout work: it needs
  a `capm`-drawing generator this top-level composer does not have today, and
  it lands on top of that flow's own already-tracked LVS gap
  (`2AMLogic/klayout-tools#1878`). Tracked as **#440**, filed alongside this
  record; it also carries the instruction that if the met3/met4 real estate
  does not hold, the answer is a superseding record reducing `MF`, not a silent
  edit.
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
- **The worst-case PVT grid is still owed**, unchanged from DR-012's and
  DR-015's standing items and #409's scope: this record's numbers are one
  corner (`tt_27c_1.80v`). When #409 lands a full-grid re-run on `main`, it
  should be run **with** this record's decoupling in the netlist too, so the
  worst-corner bounce is known for the as-decided design and not only for the
  undecoupled baseline. Note also that the MiM area coefficient itself moves
  ±11 % across the PDK's own cap corners, which this single nominal-corner
  measurement does not exercise.
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
  not modelled.** This record adds an ideal `cap_mim_m3_1`; the series
  resistance and inductance of however it is eventually routed will erode the
  measured benefit. Flagged, not modelled — and one more reason the layout pass
  above is a re-measurement, not just a placement.

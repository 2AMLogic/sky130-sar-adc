# DR-001: Supply-flavor scope — 1.8 V core flavor, higher-voltage arrangements deferred

- **Status**: **accepted** — ratified by the operator in #1 on 2026-08-13.
- **Date**: 2026-08-13 (drafted); 2026-08-13 (ratified)
- **Decided by**: Builder agent, issue #3
- **Ratified in**: #1 (Ratify the target spec — T1-gate entry). The operator
  ruled **for this record's recommendation without modification**: the 1.8 V
  core flavour for the analog signal path, comparator and SAR logic, with
  `sky130_fd_sc_hd` as the digital library; all three higher-voltage
  arrangements deferred as written.
- **Supersedes**: none — first record in this repo
- **Superseded by**: (none while this record stands)

> **Ratification note — deferral (3) remains live.** The mixed arrangement is
> deferred *conditionally*, and ratifying this record did **not** close it. It
> was safe to ratify only because `V_REF` is TBD-downstream of the flavour
> rather than an input to it. If a ratified input full-scale ever exceeds the
> core rail, this record does not cover that case and **DR-002 must settle the
> pass-device flavour before any switch is drawn**. This ratification must not
> be read as pre-approving a wider input range.
>
> This record sets **no numbers**: `V_REF`, the LSB, the CDAC unit-cap floor
> (kT/C) and the comparator input-referred-noise budget all remain TBD and
> re-derive on sky130. gf180-sar-adc's 3.3 V figures do not port.
- **Corrections** (this record has never been ratified; corrections are logged
  here rather than superseding it):
  - 2026-08-13, during review of PR #4 — the `sky130_fd_sc_hvl` voltage range
    was wrong in three places (Context "Digital libraries", Consequence §5,
    Alternatives "gf180-like 3.3 V"). The record read "characterized at
    4.40–5.50 V", which is the span of `hvl`'s **`ff` corner only**; the
    library's HV rail is characterized 1.32–5.50 V and its nominal point is
    `tt_025C_3v30`. The Alternatives text consequently claimed "3.3 V falls in
    the gap for both" libraries, which is false — 3.3 V is `hvl`'s own `tt`
    nominal. That sub-argument is now grounded on `hvl`'s cell inventory (the
    disqualification the Context bullet already establishes) instead of on a
    characterization gap that does not exist. **The Decision and the rejection
    of the 3.3 V arrangement are unchanged**; their load-bearing legs
    (no complementary 3.3 V enhancement pair, thick-oxide Vt/geometry/area,
    method-not-numeric parity) were not affected.
- **Related**: #1 (spec ratification, `loom:operator-only`), #2 (sim harness),
  `spec/target-spec.md` ("The one that gates the rest: supply flavor (open)"),
  port-parity sibling `2AMLogic/gf180-sar-adc` (DR-0002 reference source,
  DR-0004 device flavor, `spec/cdac-sizing-memo.md`), mechanism precedent
  `2AMLogic/sky130-bandgap` `spec/decision-records/DR-001-supply-flavor-scope.md`

## Context

`spec/target-spec.md` is DRAFT in full, and it names one row as the gate on
all the others: the supply flavor. Every quantitative row below it — `V_REF`,
the LSB, the CDAC unit-cap floor, the comparator input-referred-noise budget,
power — is a function of that choice, and the draft table carries most of
them as gf180-sar-adc placeholders precisely because the choice is open. Issue
#1 cannot ratify a single number until it is settled, and #2 cannot fix the
supply/corner axes of the PVT harness either. This record is the input #1
ratifies against; it argues scope, and deliberately sets no values.

**What the PDK actually offers (verified, not assumed).** Enumerated from the
installed sky130A models (`~/.volare/sky130A/libs.ref/sky130_fd_pr/spice/`,
open_pdks `c6d73a35f524070e85faff4a6a9eef49553ebc2b`) rather than from
recollection, following the sibling repo's precedent of grepping the shipped
model files:

| Class | Devices present |
|---|---|
| Core (1.8 V) | `nfet_01v8`, `nfet_01v8_lvt`, `pfet_01v8`, `pfet_01v8_lvt`, `pfet_01v8_hvt`, `pfet_01v8_mvt` |
| Medium/high voltage | `nfet_g5v0d10v5`, `pfet_g5v0d10v5` (5.0 V gate / 10.5 V drain), `nfet_g5v0d16v0`, `pfet_g5v0d16v0` |
| Native / specialty | `nfet_03v3_nvt`, `nfet_05v0_nvt` (native NMOS, **no PMOS counterpart**), the 20 V LDMOS family, ESD and RF variants |

This confirms the repo's standing assumption in checkable form: **there is no
complementary 3.3 V enhancement pair in sky130.** The only 3.3 V-named device
is `nfet_03v3_nvt`, a near-zero-threshold native NMOS with no PMOS partner —
useful as a cascode or a startup element, not a logic or signal-path flavor.
A "3.3 V sky130 design" therefore does not mean "sky130's 3.3 V devices"; it
means *the 5 V thick-oxide devices operated at 3.3 V*, which is a different
proposition with different Vt, geometry, and area consequences.

Two further facts, verified the same way, bear directly on the choice:

- **Digital libraries.** `sky130_fd_sc_hd` ships 446 layout (`mag`) files —
  169 distinct cell types — characterized at 1.28–1.95 V; `sky130_fd_sc_hvl`
  ships 71 (70 `fd` cells plus one `sky130_ef_sc_hvl__fill_8`), whose
  high-voltage rail is characterized **1.32–5.50 V**, but corner by corner
  rather than uniformly: `ss` at 1.32/1.49/1.65/1.95/2.40/2.70/3.00/5.50 V,
  `tt` at 2.64/2.97/3.30 V, `ff` at 4.40/4.95/5.50 V. Its nominal point is
  `tt_025C_3v30` — `hvl`'s own `default_operating_conditions`, with
  `voltage_map("VPWR", 3.3)` — so `hvl` is a 3.3 V-nominal library that also
  characterizes up to 5.50 V, not a 5 V-only one. Only 8 of those 71 are level shifters
  (`lsbuflv2hv_*`, `lsbufhv2lv_*`); the rest is a real, if minimal,
  gate/flop/latch/scan set — 2- and 3-input `and`/`or`/`nand`/`nor`,
  `xor2`/`xnor2`, `mux2`/`mux4`, a shallow `a21o`/`a22o`/`o21a`/`o22a` family,
  `dfrtp`/`dfstp`/`dfxbp` and their `sdf*` scan variants, and latches. What
  decides the choice is therefore not the level-shifter share but the
  71-versus-446 gap and which classes sit in it: `hvl` carries none of `hd`'s
  complex-gate depth — no deep AOI/OAI (`a2111o`, `a311o`, `o221a`, …), no
  4-input gates (`nand4`, `nor4`, `and4`, `or4`), no arithmetic (`fa`, `ha`,
  `maj3`), and no clock-tree or delay cells (`clkbuf`, `clkinv`, `dlygate4sd*`).
  `hvl` is a minimal glue and boundary library, not a general-purpose synthesis
  target for SAR logic.
- **Mismatch models.** Both flavors ship `__mismatch` corner models; the
  `01v8` pair additionally ships `__subvt_mismatch`, and
  `pfet_g5v0d10v5__subvt_mismatch` exists while its NMOS counterpart does not
  appear in the installed set. Since ENOB, INL/DNL, and offset are
  Monte-Carlo-gated rows in this repo, statistical model coverage is a
  first-class selection criterion here, not a footnote.

## Decision

**Recommend the 1.8 V core flavor (`nfet_01v8`/`pfet_01v8` and their Vt
variants) for the analog signal path, the comparator, and the SAR logic, with
`sky130_fd_sc_hd` as the digital library.** All higher-voltage arrangements
are **deferred**, explicitly and by name:

1. **A 5.0 V arrangement** on `nfet_g5v0d10v5`/`pfet_g5v0d10v5` throughout —
   deferred as a separate, separately-scoped block, not partially designed
   and not architected-for here.
2. **A "gf180-like" 3.3 V arrangement** — the same thick-oxide devices
   operated at 3.3 V to reproduce gf180-sar-adc's `V_REF` numerically —
   deferred; see Alternatives.
3. **A mixed arrangement** (thick-oxide pass devices and input front end,
   1.8 V core comparator and logic, level shifters at the boundary) —
   deferred **conditionally**. This one is not closed by this record: it
   becomes live if and only if #1 ratifies an input full-scale that exceeds
   the core rail. Per `CLAUDE.md`, the pass-device flavor for an input range
   above 1.8 V is a ratification question, not an assumption; if #1 ratifies
   such a range, this record does **not** cover it and a follow-on DR-002
   must settle the pass-device flavor before any switch is drawn.

**This record sets no numbers.** It does not fix `V_REF`, the LSB, the unit
cap, or any budget — it scopes which device menu those values will be derived
against, so that #1 has one flavor to ratify rather than three to arbitrate.
`V_REF` remains open even under this recommendation: the core flavor admits a
`V_REF` at the rail or below it (a lower `V_REF` buys comparator headroom at
the cost of a smaller LSB), and that trade is a downstream derivation, not a
scoping call.

## Alternatives considered

- **5.0 V arrangement throughout (`*_g5v0d10v5`).** Not recommended. It is
  the only option that *loosens* the noise budgets (a larger `V_REF` means a
  larger LSB), but it pays for that in four places at once: switching energy
  scales as `V²` in the matching-limited regime this design is expected to sit
  in (Consequences, §2), so a 5.0 V array costs ≈7.7× the switching energy of
  a 1.8 V one at equal capacitance; the SAR logic has only the 71-cell `hvl`
  library to build from; the thick-oxide devices are coarser and slower, which
  the draft 100 kS/s–1 MS/s row does not need; and it requires the system to
  supply a 5 V rail that nothing in the draft spec asks for. The cost of *not*
  choosing it is a tighter kT/C and comparator-noise budget — real, quantified
  below, and judged affordable because gf180-sar-adc's sizing found kT/C ~230×
  away from binding, a margin a 3.4× tightening does not consume.
- **"gf180-like" 3.3 V on thick-oxide devices.** Not recommended, and worth
  rejecting explicitly because it is the tempting one: it would make
  gf180-sar-adc's numbers port arithmetically. But it is a false economy —
  the devices would be 5 V-rated parts run at 3.3 V, so their thresholds and
  geometries are the thick-oxide ones regardless, meaning the comparator
  headroom, area, and speed all pay the thick-oxide price while only the
  supply looks familiar. It also still needs a 3.3 V rail, and it puts the SAR
  logic on the wrong digital library: `hd` stops at 1.95 V, so the only
  characterized library at 3.3 V is `hvl` — 3.3 V is in fact `hvl`'s own `tt`
  nominal, not a characterization gap — and `hvl` is precisely the library the
  Context bullet above already disqualifies as a synthesis target (71 files, no
  complex-gate depth, no 4-input gates, no arithmetic, no clock-tree or delay
  cells). At 3.3 V the SAR logic is not choosing between two libraries; it is
  `hvl` or nothing. One narrower corner cost does attach: `hvl`'s fast corner
  starts at 4.40 V, so a 3.3 V ±10 % band (2.97–3.63 V) contains `tt` and `ss`
  points but no fast-corner `hvl` library at all. Numeric port-parity with the sibling is not a design goal; method
  parity is (`README.md`: "a port of its *block class and method*").
- **Mixed HV front end + 1.8 V core.** Not rejected — deferred conditionally
  (Decision §3). It is the right answer *if* an above-rail input range is
  ratified, and the wrong answer otherwise, because it buys a second supply
  domain, level shifters in the signal path's control, and a two-flavor
  characterization campaign for nothing. Deciding it now, in either direction,
  would be deciding it before #1 supplies the fact it depends on.
- **Deferring the flavor call entirely to #1.** Rejected as a process matter.
  #1 is `loom:operator-only` and ratifies; it should ratify against an argued
  record, not perform the derivation. This mirrors the mechanism
  `sky130-bandgap` used, where the flavor-scope record was the input its
  ratification cited rather than a question re-litigated in the issue.

## Why gf180-sar-adc's 3.3 V numbers do not port

gf180-sar-adc sets `V_REF = 3.3 V` and, for the differential mode this block
also targets, `LSB_diff = 2·V_REF/2^10 = 6.4453 mV`. Under the recommended
flavor, `V_REF` is at most the 1.8 V rail; taking `V_REF = 1.8 V` purely as an
**illustrative** upper bound (not a ratified value), `LSB_diff = 3.6/1024 =
3.5156 mV` — a factor `1.8/3.3 = 0.545`. Three scalings follow, and they are
algebra, not assumption:

| Quantity | Scaling with `V_REF` | Illustrative 3.3 V → 1.8 V |
|---|---|---|
| LSB (either mode) | `∝ V_REF` | ×0.545 |
| kT/C-limited `C_sample` floor (`C_min = 2kT/σ²`, `σ ∝ LSB`) | `∝ 1/V_REF²` | **×3.36** |
| Comparator input-referred noise budget (volts rms) | `∝ V_REF` | ×0.545 (power ×0.298) |
| Comparator offset expressed **in LSB** | `∝ 1/V_REF` (offset in volts is device-set) | ×1.83 |
| Capacitor-matching-limited unit cap | **independent of `V_REF`** — ratiometric error | ×1 |

So the rows below `V_REF` in `spec/target-spec.md` are invalidated as ported
numbers, specifically:

| Draft row | Ported status |
|---|---|
| `V_REF` | **Does not port.** 3.3 V is not a sky130 device flavor at all (Context). Value re-derived under the ratified flavor. |
| LSB (differential and single-ended) | **Does not port.** Derived from `V_REF`; both modes re-stated once `V_REF` is set. |
| Sampling cap / CDAC unit cap | **Does not port.** *Both* floors move: the kT/C floor by the ×3.36 above, and the matching floor because sky130's capacitor devices are different devices entirely (`cap_mim_m3_1`/`cap_mim_m3_2` and the `cap_vpp_*` family), with their own density and matching coefficients. gf180's cap-sizing *memo is the method*; none of its capacitance values carry. |
| Comparator input-referred noise | **Does not port.** Budget shrinks with the LSB; the topology that meets it at 1.8 V may also differ (Consequences §3). |
| Comparator offset | **Does not port**, and gets *harder* in LSB terms even though it is unchanged in volts. |
| Power | **Does not port.** Re-measured, not scaled. |
| Corners (±10 % supply) | **Re-anchored**, not invalidated — but one end of the band is uncharacterized. The ±10 % band attaches to the ratified rail; anchored at 1.8 V it is 1.62–1.98 V. `sky130_fd_sc_hd` is characterized 1.28–1.95 V, so it covers the low end with room to spare and falls 0.03 V **short** of the high end: there is no characterized `hd` library at 1.98 V. See Consequence §6. |

What **does** carry from the sibling is the block class and the method, per
#1's item 2: differential top-plate charge-redistribution architecture,
`N = 10`, the ENOB and INL/DNL *targets*, the temperature corner set, the
policy that ENOB/INL/DNL/offset are statistical rows gated on Monte-Carlo
evidence, and the shape of the sizing/budget memos. Those are unaffected by
this record.

## Spec lines affected

This record changes no value in `spec/target-spec.md`. It resolves the
"supply flavor (open)" section that precedes the table, and it is the record
#1 should cite for that section rather than re-deriving the argument. Every
row of the DRAFT table remains DRAFT and unratified until #1 closes.

## Consequences

1. **CDAC unit-cap floor — the naive expectation is probably wrong, in the
   design's favor.** A smaller LSB does tighten kT/C by ×3.36, but that only
   pushes unit-cap area up *if kT/C is the binding floor*. It is not expected
   to be: gf180-sar-adc's `spec/cdac-sizing-memo.md` found its kT/C floor
   roughly two and a half orders of magnitude (~230×) below its matching
   floor, and capacitor matching is a **ratiometric** error — the unit cap it
   demands is independent of `V_REF` entirely. A 3.36× tightening does not
   close a 230× gap, so the expected outcome is that the sky130 unit cap is
   set by matching and is **flavor-independent**. This must be re-derived
   against sky130's own capacitor devices before it is claimed; it is stated
   here as the expectation this record is betting on, not as a result.
2. **Power — the advantage is real only in the matching-limited regime.** In
   the kT/C-limited regime the switching energy `C·V_REF²` is *invariant*
   under the flavor choice, because `C_min ∝ 1/V_REF²` exactly cancels the
   `V_REF²`. The 1.8 V flavor's ×0.298 energy advantage over 3.3 V (and
   ×0.130 over 5.0 V) therefore materializes only under §1's expectation. If
   §1's re-derivation surprises us and kT/C binds, the power case for this
   flavor evaporates and this record should be revisited.
3. **Comparator — this is where the flavor hurts.** Two costs compound. The
   input-referred noise budget shrinks by ×0.545 in volts (×0.298 in power),
   and for a dynamic comparator whose input-referred noise goes as
   `√(kT/C_load)`-scaled terms, holding a 0.545× σ costs roughly 3.4× the
   load capacitance and a corresponding increase in decision energy and
   regeneration time. Simultaneously, 1.8 V leaves a thin stack budget: tail
   device, input pair, and cross-coupled latch must all fit, and the input
   common mode (≈`V_REF/2` for a differential top-plate array) has to sit
   above the NMOS threshold plus tail saturation at the slow/cold corner.
   Practical consequence: a static-preamp topology is likely foreclosed and a
   dynamic (StrongARM- or double-tail-class) comparator is close to
   mandatory. Port parity with gf180-sar-adc's comparator-topology record is
   therefore **not** assured — that is a downstream DR, and it should not
   assume the sibling's answer carries.
4. **Reference settling gets slightly worse, not better.** Settling to a fixed
   fraction of an LSB needs the same number of time constants at any `V_REF`
   (step and tolerance scale together), so the flavor does not relax the
   settling *accuracy* requirement at all. What it does change is `τ = R_on·C`:
   at 1.8 V the sampling and CDAC switches have far less gate overdrive, so
   `R_on` is both higher and more signal-dependent. Bootstrapped or
   clock-boosted sampling switches move from "a good idea" to "probably
   required," and switch sizing becomes a live budget item rather than an
   afterthought. Against the draft 100 kS/s–1 MS/s row (≈83 ns per bit trial
   at 1 MS/s, 10 bits plus sampling) there is expected to be room — but that is
   an expectation for #2's harness to test, not a claim.
5. **SAR logic gets the good library.** 446 characterized `hd` cells at
   1.28–1.95 V versus `hvl`'s 71 is not a close comparison for synthesizable
   control logic — and what decides it is the missing cell classes, not the
   supply span: `hvl`'s HV rail is characterized 1.32–5.50 V with a 3.30 V `tt`
   nominal, so no plausible rail rules `hvl` in or out on voltage alone
   (Context). Choosing `hd` also keeps this block on the same digital flow the
   rest of the open sky130 ecosystem uses.
6. **Two characterization gaps to carry, not to hide.** Both sit in
   `sky130_fd_sc_hd`'s timing libraries, and both land on corners #1 is being
   asked to ratify. They are the same defect class on two different axes:
   - *Temperature.* The `hd` libraries top out at 100 °C (`n40C`, `025C`,
     `100C`), while the draft corner row asks for 125 °C; `sky130_fd_sc_hvl`
     is characterized to 150 °C.
   - *Fast-high supply.* The `hd` libraries top out at 1.95 V, and only on the
     fast corner (`sky130_fd_sc_hd__ff_n40C_1v95`, `__ff_100C_1v95`; no `tt` or
     `ss` library exists above 1.80 V and 1.76 V respectively), while
     1.8 V +10 % is 1.98 V — the library falls 0.03 V short of the top of a
     ±10 % band anchored at 1.8 V. The low end is not at issue: 1.28 V
     characterized against 1.62 V required.

   Transistor-level models cover the full range on both axes, so SPICE-level
   PVT is unaffected — but any STA-style signoff of the SAR logic at 125 °C,
   or at the fast-high supply corner, has no characterized library under this
   flavor. For each axis #1 should decide whether the draft row stands
   (accepting extrapolated or transistor-level-only digital timing evidence) or
   is re-anchored to what `hd` actually characterizes: 100 °C, and a supply
   band whose top is 1.95 V. These are genuine costs of the recommended flavor
   and belong in the ratification, not in a footnote after it.
7. **Monte-Carlo coverage is better on the core flavor**, which matters
   disproportionately here because ENOB, INL/DNL, and offset are all
   MC-gated: the `01v8` pair ships both `__mismatch` and `__subvt_mismatch`
   models, while the installed thick-oxide set is missing an NMOS
   `__subvt_mismatch` counterpart. #2's Monte-Carlo runner should confirm
   which mismatch models it actually invokes rather than inferring from file
   names.
8. **Unblocks, but does not pre-empt, #1.** With this record #1 has one flavor
   to ratify plus the explicit deferrals, instead of a three-way arbitration
   folded into a table review. Ratification remains the operator's act; this
   record is `proposed` until #1 closes and must not be cited as settled
   before then.
9. **Port-parity divergence, recorded.** gf180-sar-adc is 3.3 V throughout on
   a PDK whose *lowest* flavor is 3.3 V; sky130's core flavor is 1.8 V. This
   is a forced divergence, recorded here per `CLAUDE.md` rather than left
   silent — the block class ports, the supply does not.

## Open items

- `V_REF` itself, given the ratified flavor (at the rail, or below it for
  comparator headroom) — a downstream derivation feeding #1's table, not a
  scoping call.
- The pass-device flavor for any input range above the core rail — a
  conditional DR-002, live only if #1 ratifies such a range (Decision §3).
- Whether the unit cap is matching-limited or kT/C-limited on sky130's
  capacitor devices — a CDAC sizing memo, and the assumption Consequence §1
  is betting on.
- The comparator topology at 1.8 V, and whether the sibling's choice carries
  — a downstream DR informed by Consequence §3.
- The 125 °C vs 100 °C digital-library question raised in Consequence §6 — for
  #1 to rule on.
- The fast-high supply corner raised in Consequence §6: whether the top of the
  ratified ±10 % band (1.98 V at a 1.8 V rail) stands with no characterized
  `hd` library above 1.95 V, or the band is re-anchored to 1.95 V — for #1 to
  rule on, on the same footing as the temperature row.

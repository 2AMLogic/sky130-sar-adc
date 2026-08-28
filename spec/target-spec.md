# sky130-sar-adc — target spec

**Status: supply flavour RATIFIED (2026-08-13, DR-001 via #1). `V_REF`,
LSB, resolution `N`, the CDAC unit-cap/array size, and the comparator
input-referred-noise budget RATIFIED (2026-08-19, DR-003 via #27). Sample
rate and the statistical rows (ENOB, INL/DNL — target values only) remain
DRAFT.**

- **Binding:** the supply flavour — 1.8 V core (`nfet_01v8`/`pfet_01v8`), digital
  on `sky130_fd_sc_hd`. Design, sim and layout may lock to it. See
  [the supply-flavour section](#the-one-that-gates-the-rest-supply-flavor--ratified-2026-08-13),
  including the **DR-002 tripwire** on input full-scale. Also binding:
  `V_REF`, LSB, resolution `N`, the CDAC unit-cap/array size, and the
  comparator input-referred-noise budget — ratified against
  [DR-003](decision-records/DR-003-numeric-spec-derivation.md). See
  [the numeric-rows section](#numeric-rows--ratified-2026-08-19) below.
- **Not binding:** sample rate, and the ENOB/INL-DNL *target values* pending
  their Monte-Carlo evidence campaign (#29). Each remains a starting point,
  to be confirmed, amended, or replaced by a decision record under
  `spec/decision-records/`.

An agent must not treat the sample-rate row as settled, must not close a
`TBD` by porting gf180-sar-adc's 3.3 V figure, and must not relax a ratified
row to make a result pass.

## The one that gates the rest: supply flavor — RATIFIED 2026-08-13

**Settled.** The analog signal path, comparator, and SAR logic are built on the
**1.8 V core** (`nfet_01v8`/`pfet_01v8` and their Vt variants), with
`sky130_fd_sc_hd` as the digital library. Ratified by the operator in #1 on
2026-08-13 against
[`decision-records/DR-001-supply-flavor-scope.md`](decision-records/DR-001-supply-flavor-scope.md),
which moves `proposed → accepted`. Design, sim, and layout may lock to this.

gf180-sar-adc is a 3.3 V design (`V_REF = 3.3 V`); sky130's device menu is
different, and **gf180's 3.3 V does not carry over.** `V_REF`, the LSB, the
sampling-cap floor (kT/C), and the comparator input-referred-noise budget all
follow *from* the ratified rail and are still **TBD** — see the table below.
Ratifying the flavor does not ratify any of them.

Higher-voltage arrangements are **deferred by name**, per DR-001:

1. **5.0 V throughout** (`nfet_g5v0d10v5`/`pfet_g5v0d10v5`) — deferred as a
   separately-scoped block; not partially designed for here.
2. **"gf180-like" 3.3 V** (thick-oxide at 3.3 V, to reproduce gf180's `V_REF`
   numerically) — deferred.
3. **Mixed** (thick-oxide front end, 1.8 V core comparator and logic, level
   shifters at the boundary) — **deferred conditionally, and this one is a live
   tripwire.**

> ### ⚠ The DR-002 tripwire
>
> Deferral (3) is **not closed**. It becomes live **if and only if a ratified
> input full-scale exceeds the core rail.** This ratification is safe today only
> because `V_REF` is TBD-downstream of the flavor, not an input to it.
>
> If any later campaign or ratification proposes an input range above 1.8 V,
> **DR-001 does not cover it** — a follow-on **DR-002 must settle the
> pass-device flavor before any switch is drawn.** Per `CLAUDE.md` the
> pass-device flavor for an input range above the core rail is a ratification
> question, never an assumption. Do not treat this ratification as having
> pre-approved a wider input range.

## Numeric rows — RATIFIED 2026-08-19

**Settled.** `V_REF`, LSB, resolution `N`, the CDAC unit-cap/array size, and
the comparator input-referred-noise budget are ratified against
[`decision-records/DR-003-numeric-spec-derivation.md`](decision-records/DR-003-numeric-spec-derivation.md),
which moves `proposed → accepted`, per the operator's approval of the PR
resolving #27 (canary spec/DR ratification-via-PR standing policy,
2AMLogic/2am#357: "a builder drafts the ratification/DR as a PR on the
evidence, and the operator's PR approval is the ratification act"). The
ruling is DR-003's recommendation without modification:

- **`V_REF = V_DD = 1.8 V`** — at the rail, not above it. Does not trigger
  the DR-002 tripwire above (the full-scale stays at the ratified core rail).
- **LSB (differential) = `2·V_REF/2^N` = `3.5156 mV`**.
- **Resolution `N = 10`** — confirmed as drafted, not changed.
- **CDAC unit cap `C_u ≈ 8.65 fF`, `2^9 = 512` positions/side** —
  matching-limited (sky130's own MIM local-mismatch model,
  `A_C = 2.8 %·µm`); the kT/C floor is `≈ 415×` looser and does not bind.
- **Comparator input-referred noise `≤ 1.0148 mV rms` (baseline, ENOB > 9.0)
  / `≤ 0.5859 mV rms` (stretch, ENOB > 9.5)** — one-third of the total
  non-quantization budget (equal three-way split with kT/C sampling noise
  and reference/distortion).
- **Corners: hold `−40/27/125 °C` as drafted (Option A of DR-003 Item 5)**,
  with the scope note DR-003 records: this repo's only committed
  verification methodology is transistor-level ngspice SPICE (no
  OpenSTA/Liberty-based digital signoff step exists or is scheduled), so the
  125 °C ceiling is unaffected today; any *future* Liberty/STA-based signoff
  of the SAR logic inherits a 100 °C ceiling automatically
  (`sky130_fd_sc_hd`'s characterized range) without needing to be
  re-litigated when that step is added.

**Not ratified by this record — still open, named explicitly, not
guessed:**

- **Sample rate** — the draft `100 kS/s–1 MS/s` row is not re-derived; no
  switch-`R_on`/settling data exists yet (needs a CDAC/switch netlist, #24,
  and a corner campaign, #28).
- **Item 1's worst-corner (`ss`, `−40 °C`) comparator headroom margin** —
  the nominal (`tt`, 27 °C) margin is `23.1 mV`, quantified against real
  sky130 device data (`spec/dr-003-support/vth_probe.spice`); the
  slow/cold-corner sweep did not converge while drafting DR-003 and is
  named as open work for the future comparator-topology DR, not asserted
  here.
- **A gain-error spec row** — DR-003 Item 3 found the ratified `C_u`'s
  total-array gain error (`1.42 LSB` at 3σ) would exceed 1 LSB *if* this
  spec carried a gain-error target, but it does not today; this record
  flags the spec-completeness gap without inventing a row to close it.
- **ENOB / INL-DNL target values** — unchanged by this ratification; they
  remain statistical rows gated on Monte-Carlo evidence (#29), per DR-003
  Item 6. **Evidence now exists** (issue #29: `sim/cdac-array-transfer/`
  Monte Carlo DNL/INL campaign, `sim/comparator-decision/` offset Monte
  Carlo campaign, `sim/enob-estimate/` behavioral-accelerated ENOB
  estimate) — see each record's own `klt yield` report against these DRAFT
  targets. **The evidence reports the DRAFT targets are not currently
  met** at the nominal (`tt`/27 °C/1.8 V) mismatch corner sampled: the CDAC
  mismatch Monte Carlo campaign's `klt yield` verdict is `0.825`/`0.925`
  empirical yield (N=40) against the `≤ ±1 LSB` target's `0.99` target
  yield, and the composite behavioral ENOB estimate is `8.491`
  bit (mean-case) / `7.749` bit (worst-case) against the `> 9.0` bit
  baseline target — both informational (the target values are DRAFT, not
  ratified), neither relaxed nor reinterpreted to force a pass, per
  `CLAUDE.md`'s "do not relax a spec line to make a result pass" rule.
  That evidence existing (or its shortfall) does not itself ratify or
  reject these target values; ratification (or a superseding decision
  record, if the targets prove unmeetable as currently designed) is a
  future decision record's job, not this one's.

Full derivation, reproducible arithmetic (`spec/dr-003-support/calc.py`),
and the device-level evidence each number is read from:
[DR-003](decision-records/DR-003-numeric-spec-derivation.md).

## Target table

| Parameter | Target | Status | Carried from / note |
|---|---|---|---|
| Architecture | charge-redistribution SAR, differential, top-plate sampling | DRAFT | gf180-sar-adc |
| Resolution `N` | 10 bit | **RATIFIED** (DR-003 via #27) | confirmed vs area/ENOB tradeoff on sky130 (DR-003 Item 2) |
| Sample rate | provisional 100 kS/s–1 MS/s | DRAFT | not re-derived by DR-003; needs settling data (#24/#28) |
| ENOB | > 9.0 bit (target), stretch > 9.5 | DRAFT (target value) | statistical row — MC evidence campaign complete (#29, `sim/enob-estimate/`), ratification still open |
| INL / DNL | ≤ ±1 LSB (target) | DRAFT (target value) | statistical — MC evidence campaign complete (#29, `sim/cdac-array-transfer/`), combined with #28's process corners; ratification still open |
| `V_REF` | `1.8 V` (= `V_DD`, at the rail) | **RATIFIED** (DR-003 via #27) | derived from the ratified 1.8 V core rail (DR-001) |
| LSB (differential) | `2·V_REF/2^N = 3.5156 mV` | **RATIFIED** (DR-003 via #27) | derived |
| Sampling cap (CDAC unit × array) | `C_u ≈ 8.65 fF`, `2^9 = 512` positions/side | **RATIFIED** (DR-003 via #27) | matching-limited; kT/C floor is `≈ 415×` looser |
| Comparator input-referred noise | `≤ 1.0148 mV rms` (baseline) / `≤ 0.5859 mV rms` (stretch) | **RATIFIED** (DR-003 via #27) | `28.86 %` / `16.67 %` of LSB; one-third of the total non-quant budget |
| Power | provisional, minimise at rate | DRAFT | report, don't pre-commit |
| Corners | −40/27/125 °C, ±10 % supply, sky130 process corners | **RATIFIED** (DR-003 via #27) | held as drafted; see the Liberty/STA scope note above |

## What T1 (bronze) will require of this block

Per `klayout-tools/docs/design-evidence-tiers.md`: schematic + regenerated
netlist; DRC clean; LVS match; full PVT corner sim vs **this table's ratified
rows**; **Monte-Carlo** on the statistical rows (ENOB, INL/DNL, offset) with
seed + sample count + negative control; post-layout (extracted) re-sim; a
characterization report; testbenches shipped; repo hygiene. `V_REF`, LSB,
`N`, the CDAC unit-cap/array size, the comparator noise budget, and the
corner set are ratified (DR-003 via #27) and evidence may be recorded
against them now; sample rate and the ENOB/INL-DNL *target values* remain
DRAFT and nothing against those specific rows is claimable until a future
record ratifies them.

## Non-goals (draft)

Not taped out, no tier claimed. Not a port of gf180's *numbers* — a port of its
*block class and method*; the sky130 numbers are re-derived here.

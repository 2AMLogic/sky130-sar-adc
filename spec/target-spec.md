# sky130-sar-adc — target spec

**Status: supply flavour RATIFIED (2026-08-13, DR-001 via #1). Every numeric row
remains DRAFT — UNRATIFIED.**

- **Binding:** the supply flavour — 1.8 V core (`nfet_01v8`/`pfet_01v8`), digital
  on `sky130_fd_sc_hd`. Design, sim and layout may lock to it. See
  [the supply-flavour section](#the-one-that-gates-the-rest-supply-flavor--ratified-2026-08-13),
  including the **DR-002 tripwire** on input full-scale.
- **Not binding:** every number in the table below. Each is a starting point
  carried from the sibling
  [gf180-sar-adc](https://github.com/2AMLogic/gf180-sar-adc) or a published sky130
  reference, to be confirmed, amended, or replaced by a decision record under
  `spec/decision-records/`. Ratifying the flavour settles what the numbers are
  *derived on*, not what they are.

An agent must not treat any numeric row below as settled, must not close a
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

## DRAFT target table (all provisional)

| Parameter | DRAFT target | Carried from / note |
|---|---|---|
| Architecture | charge-redistribution SAR, differential, top-plate sampling | gf180-sar-adc |
| Resolution `N` | 10 bit | gf180-sar-adc; confirm vs area/ENOB tradeoff on sky130 |
| Sample rate | provisional 100 kS/s–1 MS/s | set by application + comparator/DAC settling on sky130 |
| ENOB | > 9.0 bit (target), stretch > 9.5 | statistical row — MC evidence required |
| INL / DNL | ≤ ±1 LSB (target) | statistical — MC + process corners |
| `V_REF` | **TBD** — follows supply flavor (DR-001) | gf180 was 3.3 V; sky130 likely lower |
| LSB (differential) | `2·V_REF / 2^N` — **TBD** with `V_REF` | derived |
| Sampling cap (CDAC unit × array) | floor set by kT/C at target ENOB | gf180 CDAC-sizing memo is the method, not the number |
| Comparator input-referred noise | fraction of LSB, budgeted (not the whole budget) | gf180 comparator-budget memo |
| Power | provisional, minimise at rate | report, don't pre-commit |
| Corners | −40/27/125 °C, ±10 % supply, sky130 process corners | canary standard |

## What T1 (bronze) will require of this block

Per `klayout-tools/docs/design-evidence-tiers.md`: schematic + regenerated
netlist; DRC clean; LVS match; full PVT corner sim vs **this table once ratified**;
**Monte-Carlo** on the statistical rows (ENOB, INL/DNL, offset) with seed +
sample count + negative control; post-layout (extracted) re-sim; a
characterization report; testbenches shipped; repo hygiene. Nothing in this file
is claimable until it is ratified and the evidence exists.

## Non-goals (draft)

Not taped out, no tier claimed. Not a port of gf180's *numbers* — a port of its
*block class and method*; the sky130 numbers are re-derived here.

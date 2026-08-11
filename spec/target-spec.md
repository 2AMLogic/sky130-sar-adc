# sky130-sar-adc — target spec

**Status: DRAFT — UNRATIFIED.** No value here is binding. Every number is a
starting point carried from the sibling
[gf180-sar-adc](https://github.com/2AMLogic/gf180-sar-adc) or a published sky130
reference, to be confirmed, amended, or replaced by ratification (issue #1) and
the decision records under `spec/decision-records/`. An agent must not treat any
row below as settled, and must not relax a ratified row to make a result pass.

## The one that gates the rest: supply flavor (open)

gf180-sar-adc is a 3.3 V design (`V_REF = 3.3 V`). **sky130's device menu is
different**, and the whole converter scales off this choice:

- **1.8 V core** (`nfet_01v8`/`pfet_01v8`) — smaller LSB, tighter kT/C and
  comparator-noise budgets, lower power. The likely default.
- a **medium/high-voltage** arrangement if dynamic range argues for it.

`V_REF`, the LSB, the sampling-cap floor (kT/C), and the comparator input-referred
noise budget all follow from this. It is the first decision record (DR-001) and
an input to ratification — **do not assume gf180's 3.3 V carries over.**

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

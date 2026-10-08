# sky130-sar-adc

A charge-redistribution **SAR ADC** for the
[SkyWater sky130](https://github.com/google/skywater-pdk) open PDK, designed in
the open-source analog flow: **xschem** for schematic capture, **ngspice** for
simulation, and [klayout-tools](https://github.com/2AMLogic/klayout-tools)
(`klt`) for layout. It is a sky130 **port** of the sibling canary
[gf180-sar-adc](https://github.com/2AMLogic/gf180-sar-adc) — same block class, a
second PDK — so that "one SAR ADC, two open PDKs" becomes the portability proof.

This block is built by AI agents. Not "AI-assisted" — agents do the schematic
capture, size the CDAC and comparator, write the testbenches, run the PVT and
Monte-Carlo campaigns, argue the design decisions out in written decision
records, and open the pull requests. The verification evidence in `sim/` is the
point of the repository: every claim is meant to be backed by a testbench and a
recorded corner sweep you can check yourself.

## What this is — a reverse-engineering-free DESIGN canary

Nothing here is recovered from an existing part, a competitor's netlist, or a
decapped die. The ADC is designed forward from a ratified target specification,
and the whole record — spec, decision records, evidence, dead ends — is original
work. The repo is **dogfood for [klayout-tools](https://github.com/2AMLogic/klayout-tools)**
(a real mixed-signal block against the sky130 decks is the forcing function on
the tool; every friction is filed generically upstream) and **catalog inventory**
(one block, one PDK, in the 2AM Logic canary catalog).

## Status: pre-silicon; layout composed, conversion and signoff unresolved

This is a pre-silicon design with no tier grant. Schematic sources, a composed
layout and a closed-loop conversion campaign all exist, but the block does not
yet convert correctly across its full input range and its layout does not yet
pass LVS. Nothing here is T1 (bronze). The sections below say what the
committed evidence supports; each links to it, and the linked records, not this
summary, are authoritative.

- **Harness** — the xschem + ngspice sim harness and the `klt` DRC/LVS layout
  flow (issue #2), seeded from gf180-sar-adc and
  [sky130-bandgap](https://github.com/2AMLogic/sky130-bandgap):
  `sim/run_corners.py` (PVT), `sim/monte_carlo.py` (recorded seed, N, and a
  deterministic negative control), the append-only evidence-record convention
  in [`sim/README.md`](sim/README.md), and
  [`layout/README.md`](layout/README.md)'s trivial-cell proof, which also checks
  that injected DRC and LVS faults come back *flagged*.
  [`docs/environment-setup.md`](docs/environment-setup.md) is the reproducible
  bootstrap.
- **Design sources** — the four sub-blocks (sampling front end, CDAC array,
  comparator, SAR logic/sequencer) and a top-level integration schematic,
  [`design/sar_adc_top.sch`](design/sar_adc_top.sch), with a mechanically
  regenerated, CI-checked full-hierarchy netlist,
  [`design/sar_adc_top.spice`](design/sar_adc_top.spice). The supply flavor is
  ratified on the 1.8 V core by
  [DR-001](spec/decision-records/DR-001-supply-flavor-scope.md); that reopens
  (a follow-on DR-002 would settle the pass-device flavor) if a ratified input
  full-scale ever exceeds the core rail.
- **Spec: partly ratified** — [`spec/target-spec.md`](spec/target-spec.md) is
  the authority. Resolution, `V_REF`, the LSB, the CDAC unit-cap/array size,
  the comparator noise budget and the corner set are **RATIFIED**
  ([DR-003](spec/decision-records/DR-003-numeric-spec-derivation.md)). Other
  rows (sample rate, the ENOB and INL/DNL target values, kickback, power,
  architecture) are still **DRAFT**, and no harness threshold may treat a draft
  value as settled.
- **Layout: exists, LVS failing** — each sub-block under [`layout/`](layout/)
  has a reproducible flow and committed reports, and a composed top level is in
  [`layout/sar-adc-top/`](layout/sar-adc-top/README.md). DRC on the composed
  stream is clean within the transcribed deck scope, with disclosed coverage
  gaps. **LVS does not match**, and there is no post-layout (extracted)
  verification of the full block. Details and numbers are in
  [`signoff/README.md`](signoff/README.md).
- **Conversion: partial, overall FAIL** — the full-conversion transient
  campaign ([`sim/full-conversion-transient/`](sim/full-conversion-transient/README.md);
  newest record named in `records/LATEST`) resolves the three mid-scale inputs
  to within ±1 LSB at all nine ratified corners. It is still recorded as an
  overall **FAIL**: the two near-full-scale inputs do not converge
  ([#265](https://github.com/2AMLogic/sky130-sar-adc/issues/265)), and a
  smaller array gain-error contributor is also open. That verdict is against
  the experiment's own informational criterion, not a ratified spec row. The
  statistical (Monte-Carlo) rows are not signed off either; see item 6 in the
  signoff report. This is not a demonstration of full ADC conversion.
- **Measurements** — `measurements/` stays empty until there is silicon.
- **The gap, graded** — [`signoff/t1-report.json`](signoff/t1-report.json) is
  the verdict of record: the eleven-item T1 (bronze) evidence checklist rendered
  mechanically by `klt signoff --manifest`, per partition, with a `reason` on
  every unmet row. CI re-grades it on every push, so it cannot go stale
  unnoticed. [`signoff/README.md`](signoff/README.md) is the claim written
  around it, and [`docs/t1-gap.md`](docs/t1-gap.md) is the short in-repo map
  pointing at both. Current state: **3 of 22 rows met**, tier `null`.

## Private for now

This repository is **private**. Whether and when it goes public is an
**operator** decision, not an agent one. Write every commit, issue, and document
as if a stranger will read it.

## How verification will work here

1. **No claim without a testbench**, run across the PVT corner matrix, raw
   per-corner logs committed with the summary. A SAR ADC's accuracy, offset, and
   linearity rows are **statistical** — they carry Monte-Carlo evidence
   (recorded seed, sample count, deterministic negative control), not just
   corners.
2. **`sim/` is append-only evidence.** A record is never edited or deleted; a
   re-run mints a new record naming the one it supersedes.

## License

Apache License 2.0 — see [LICENSE](LICENSE). Copyright 2026 2AM Logic.

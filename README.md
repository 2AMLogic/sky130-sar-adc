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

## Status: harness up, schematic sources exist. Pre-spec (ratification), pre-layout, pre-silicon.

The toolchain is standing, and schematic sources now exist: the four
sub-blocks (sampling front end #52, CDAC array #53, comparator #54, SAR
logic/sequencer #55) plus a top-level integration schematic wiring them
together (#56, `design/sar_adc_top.sch`, with an instantiable symbol and a
mechanically regenerated, CI-checked full-hierarchy netlist,
`design/sar_adc_top.spice`). This is schematic capture and per-sub-block
standalone verification, not a closed-loop ADC conversion result — the
top-level integration's own polarity/wiring decisions (documented in
`design/sar_adc_top.sch`'s header) are explicitly unverified pending the
future per-row/Monte-Carlo testbenches (#28/#29/#31). Layout has not started.

- **Done** — the xschem + ngspice sim harness and the `klt` DRC/LVS layout flow
  (issue #2), seeded from gf180-sar-adc and
  [sky130-bandgap](https://github.com/2AMLogic/sky130-bandgap):
  `sim/run_corners.py` (PVT), `sim/monte_carlo.py` (distributions with a
  recorded seed, N, and a deterministic negative control), the append-only
  evidence-record convention in [`sim/README.md`](sim/README.md), and
  [`layout/README.md`](layout/README.md)'s trivial-cell proof — which asserts
  not just that DRC comes back clean and LVS matches, but that an injected DRC
  violation and two corrupted LVS references all come back *flagged*.
  `docs/environment-setup.md` is the reproducible bootstrap.
- **Partly settled** — the **supply flavor** is **RATIFIED** (2026-08-13, via
  [DR-001](spec/decision-records/DR-001-supply-flavor-scope.md) and issue #1):
  the analog signal path, comparator, and SAR logic are built on the 1.8 V
  core (`pfet_01v8`/`nfet_01v8`), with the higher-voltage arrangements
  deferred by name. That deferral reopens — and a follow-on DR-002 must settle
  the pass-device flavor before any switch is drawn — **if a ratified input
  full-scale ever exceeds the core rail**; DR-001 pre-approves nothing wider.
- **Not done** — every numeric row of the target spec is still **DRAFT and
  unratified** (see `spec/target-spec.md` and issue #1). `V_REF`, the LSB, the
  kT/C noise budget, and the ENOB/INL/DNL targets are all starting points
  carried from gf180-sar-adc or a published sky130 reference, not settled
  sky130 results — ratifying the flavor settles what they are *derived on*,
  not what they are. No harness threshold encodes a draft spec value.
- **Not started** — closed-loop ADC conversion verification (a real per-row
  PVT/Monte-Carlo campaign against the full `design/sar_adc_top.sch`
  hierarchy, #28/#29/#31) and layout. `measurements/` stays empty until there
  is silicon.
- **The gap, itemized** — [`docs/t1-gap.md`](docs/t1-gap.md) maps the ten-item
  T1 (bronze) evidence checklist to this block's current verdict and to the
  issue tracking each failing item, as of the 2026-08-15 re-read.

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

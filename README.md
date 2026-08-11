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

## Status: scaffold. Pre-spec, pre-schematic, pre-layout, pre-silicon.

This repository has just been created. It holds the map — a DRAFT target spec,
the canary rules, and the bootstrap issues. There is no schematic, no evidence,
no layout yet.

- **Not done** — the target spec is **DRAFT and unratified** (see
  `spec/target-spec.md` and issue #1). Every value is a starting point carried
  from gf180-sar-adc or a published sky130 reference, not a settled sky130
  result. In particular the **supply flavor** (1.8 V core vs a medium-voltage
  arrangement) and therefore `V_REF`, the LSB, and the kT/C noise budget are
  open questions the spec must settle first — sky130's device menu is not
  gf180's 3.3 V flavor.
- **Not done** — the xschem + ngspice sim harness (with the Monte-Carlo and PVT
  runners a data converter needs) and the `klt` layout/DRC/LVS flow are not yet
  stood up; they seed from gf180-sar-adc and
  [sky130-bandgap](https://github.com/2AMLogic/sky130-bandgap). See issue #2.
- **Not started** — schematic entry, the CDAC/comparator design, verification,
  and layout. `measurements/` stays empty until there is silicon.

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

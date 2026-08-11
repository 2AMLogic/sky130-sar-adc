# sky130-sar-adc — agent instructions

Private canary block (for now): a SAR ADC on the sky130 open PDK,
designed and verified by AI agents. A clean-room DESIGN canary — designed forward
from a written spec, never reverse-engineered from anyone's silicon or netlist.
Its two jobs are to dogfood `klayout-tools` and to grow the catalog's inventory
of verified open-PDK analog blocks.

- **PDK**: sky130 (open PDK). Open-source flow: xschem + ngspice for design/sim,
  klayout-tools (`klt`) for layout work. sky130 has no native 3.3 V flavor — the
  1.8 V core devices are `pfet_01v8`/`nfet_01v8` and the high-voltage devices are
  `pfet_g5v0d10v5`/`nfet_g5v0d10v5`; the pass-device flavor for a 3.3 V input is a
  ratification question, not an assumption (see `spec/target-spec.md`).
- **Clean room (no reverse engineering)**: this block is designed from its spec
  and device physics. Do not introduce, cite, or reconstruct any other party's
  implementation — measured, delayered, netlisted, or otherwise. If a task seems
  to need a competitor's internal detail, stop; the canary's value is that it
  owes nothing to anyone else's work.
- **Friction protocol (the canary's job)**: every time klayout-tools is awkward,
  missing a capability, or wrong for what you need, file an issue at
  `2AMLogic/klayout-tools` describing the tool gap **generically** — that tracker
  is public and scoped to the tool, so keep design-specific detail (spec values,
  this repo's content, block topology) out of it and describe the gap, not the
  design. This holds even though this repo is private: the tracker you file into
  is not.
- **Verification is the product**: no claim without a testbench. PVT corners on
  every recorded result. `sim/` results are append-only evidence — a later run
  mints a new record rather than overwriting an earlier one.
- **The spec is a gate**: spec changes go through `spec/` with a decision record;
  agents do not relax a spec line to make a result pass. A row that proves
  unmeetable is superseded by a new decision record, never silently loosened.
  Until issue #1 ratifies it, the whole table in `spec/target-spec.md` is DRAFT —
  do not treat any value as final, and do not invent settled numbers to replace
  the drafts.
- **Private, for now**: this repo is private while the spec is drafted and the
  harness stood up. Going public is an operator decision that inherits the
  workspace firewall/disclosure rules — not an agent decision. Write commits,
  issues, and documents as private working material meanwhile.
- **Port parity**: the spec and structure mirror the ratified
  `2AMLogic/gf180-sar-adc` — same block, two PDKs. Prefer aligning with it; where
  sky130 forces a departure, record the divergence in `spec/` rather than
  diverging silently.
- **Harness bootstrap**: copy the sim-harness and `klt` layout-flow patterns from
  `2AMLogic/sky130-bandgap` (sky130 flow) and `2AMLogic/gf180-sar-adc` (SAR ADC
  testbenches) rather than reinventing them.

<!-- BEGIN LOOM ORCHESTRATION -->
This repository uses [Loom](https://github.com/rjwalters/loom) for AI-powered development orchestration — see the Loom repository for the full guide (roles, labels, worktrees, configuration). When installed, Loom also writes a locally-substituted copy of that guide to `.loom/CLAUDE.md`.
<!-- END LOOM ORCHESTRATION -->
<!-- BEGIN REPO-SKILLS -->
This repository has [Repo Skills](https://github.com/rjwalters/repo) installed —
general repository hygiene and environment commands invoked as `/repo:<command>`. Run
`/repo:help` for the command list, or see `.claude/skills/repo/SKILL.md` for the full
guide. Hygiene commands apply safe, reversible fixes by default and report each
change; run with `--ask` to review first, and `--prune` to allow irreversible
removals. Managed by `install.sh` — edit outside the markers only.
<!-- END REPO-SKILLS -->

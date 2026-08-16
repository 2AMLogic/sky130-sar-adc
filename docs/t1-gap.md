# Gap to T1 (bronze) — what stands between this block and a bronze candidate

**Snapshot: 2026-08-16, from the checklist re-read of `main`@`d3fda4c`.**
The live status lives on GitHub — issue **#23** is the tracker and is authoritative.
This file is a dated map of the gap so a reader with only the repo in front of them can
see the shape of it; it is not an evidence record and it does not grade anything.

## Where the verdict comes from

Issue #16 re-read the full ten-item T1 checklist
(`klayout-tools/docs/design-evidence-tiers.md` → "T1 checklist") against this block's
evidence at `main`@`d3fda4c` and posted an item-by-item table with a citation per verdict:

> **1/10 pass (item 10)** — 3 items N/A pending upstream artifacts (3, 4, 7), 6 fail
> (1, 2, 5, 6, 8, 9). Blocking items: 1–9.

Block kind for this repo is **analog** (whole-custom, transistor-level; xschem schematic
capture, no RTL/synthesis flow in-repo), so only the *Analog* column of checklist items
1, 2, 5, 6 and 7 applies.

## Item → issue map

| # | T1 item | Verdict (2026-08-15) | Tracked by |
|---|---------|----------------------|------------|
| 1 | Design sources | FAIL | #24 |
| 2 | Layout | FAIL | #25 |
| 3 | DRC clean | N/A — no ADC layout to check | becomes live when #25 lands |
| 4 | LVS clean | N/A — no ADC netlist/layout to compare | becomes live when #24 + #25 land |
| 5 | Full corner verification vs a ratified spec | FAIL | #28, gated by #26 → #27 |
| 6 | Statistical claims carry Monte Carlo evidence | FAIL | #29, gated by #26 → #27 |
| 7 | Post-layout verification | N/A — no extracted netlist; `klt pex` not implemented upstream (klayout-tools Epic #709) | becomes live when #25 lands *and* `klt pex` exists |
| 8 | Characterization report | FAIL | #30 |
| 9 | Testbenches shipped | FAIL | #31 |
| 10 | Repo hygiene | PASS | — |

Rows 5 and 6 share one root cause on their spec-gated half — the numeric rows of
`spec/target-spec.md` are DRAFT/unratified — so that cause is tracked once, as #26
(agent-side derivation of the sky130 numbers) feeding #27 (the operator ratification).
Row 9 is tracked separately from rows 5/6 because the cross-cutting contract it grades —
a bench for *every* claimed row, a documented cold-start invocation, a pinned PDK
revision — can regress silently while each individual campaign still looks green.

## What is *not* the gap

The harness is not the gap. The sim harness and the `klt` layout flow are both
demonstrated working, negative controls included: the trivial-cell record under
`layout/trivial-cell/reports/` shows an injected DRC violation and two corrupted LVS
references all coming back flagged, and the two `sim/` self-test experiments show a
9-corner PVT sweep and a Monte-Carlo run with a recorded seed, sample count and a
deterministic negative control. Those records are **harness proofs, not design claims**
(`sim/README.md`), and none of them may be cited toward a T1 item.

The gap is that no SAR ADC schematic, netlist or layout exists yet, and the target
spec's numeric rows are still DRAFT — so items 1, 2 and everything downstream of them
cannot pass regardless of harness quality.

## Rules that hold over every item above

- **No grant is recorded in this repo.** `2AMLogic/product/everyblock/grants.md` is the
  authoritative ledger and grants are recorded by the operator.
- **No spec row is relaxed to make a result pass.** A row that proves unmeetable is
  superseded by a new decision record and an operator ruling, never silently loosened.
- **Ratification is an operator act, never fleet work** — hence #27 rather than a build
  issue.
- **Staleness is failure.** A report generated against an older netlist or layout
  revision than current `main` is stale, not passing; evidence going stale drops the
  block below the tier until it is re-established.

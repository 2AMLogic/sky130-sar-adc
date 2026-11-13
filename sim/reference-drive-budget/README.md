# `sim/reference-drive-budget/` — VREFP/VREFN drive-impedance budget

How much **series source resistance** the `VREFP` / `VREFN` pads tolerate
before the converter's captured output codes move, at every ratified PVT
corner (issue #841).

## Why this campaign exists

No `sim/` campaign put an impedance on the reference before this one.
`sim/vcm-drive-budget/` budgets `VCM` only;
`sim/supply-impedance-sensitivity/` says in its own words that
`VREFP`/`VREFN`/`VCM` "stay ideal at the die" and bonds the four *supply*
terminals instead; every committed deck under `sim/` drives the reference
from ideal DC sources with nothing in series. The CDAC draws transient
charge from the reference at every bit trial, so this is the interface a
"low resistance to the pad" requirement actually lands on — and no figure
could be stated for it without inventing one.

It produces **evidence only**. It changes no `spec/target-spec.md` row
(DRAFT until #1), and it chooses no route of
`docs/chipalooza/challenge-4-proposal.md` §7 item 11.

## Cold start

One-time machine bootstrap is `docs/environment-setup.md` sections 1–3.
Then:

```
source sim/env.sh
python3 sim/reference-drive-budget/run_reference_drive_budget.py --check-env
python3 sim/reference-drive-budget/run_reference_drive_budget.py --record
```

The documented corner-campaign invocation is:

    python3 sim/reference-drive-budget/run_reference_drive_budget.py --record

Other modes:

| Mode | What it does |
|---|---|
| `--check-env` | resolve the PDK and exit |
| `--dry-run --workdir DIR` | write the deck + `klt sim` request and stop; no simulation |
| `--probe` | ONE unit (`tt`/27 °C/1.80 V, `R_ref = 0`) through `klt sim --backend local` |
| `--record` | submit the whole grid and mint an evidence record |

`--r-ohm`, `--timeout-s`, `--hosts`, `--wait-for-capacity` and `--backend`
override the sweep and the submission; `--supersedes` names the prior record
of this experiment a new one replaces.

## What it measures

- **DUT**: `design/sar_adc_top.spice`, as committed — the whole converter.
  A single-bit reduction (as in `sim/cdac-bit-trial-settling/`) holds every
  other bit's bottom plate on an ideal DC source, so the charge the rest of
  the array draws through the shared reference rail is absent from it.
- **Stimulus**: `sim/full-conversion-transient/testbench/full_conversion_tb_fragment.spice`,
  read in place and used **verbatim** except for the two reference source
  cards. The clock (DR-006 worst case `f_clk = 12 MHz`), the reset, the five
  DC differential inputs, the `.tran` card and all 175 `.meas` cards are that
  campaign's own. Solver settings are DR-023's reference policy
  (`.options reltol=1e-4 method=gear`).
- **The only edit**: `VVREFP` / `VVREFN` are re-pointed from the die node to
  a drive node, with `R_ref` in series to the die:

  ```
  VVREFP VREFP_DRV 0 DC {vdd_val}        RREFP VREFP_DRV VREFP {r_ref}
  VVREFN VREFN_DRV 0 DC 0                RREFN VREFN_DRV VREFN {r_ref}
  ```

  The source *instance* names do not move, so the fragment's own
  `.meas tran i_vrefp avg i(vvrefp)` cards still measure the current
  delivered from the drive side. `VCM`, `VDD`, `VPWR` and `VGND` stay ideal
  at the die, so the reference is the only non-ideal drive in the deck.
- **Observable**: the captured output code of each of the five inputs, read
  mid-`PH_EOC`, decoded by `sim/full-conversion-transient/run_conversion.py`'s
  own decoder.

### The control is per corner, not the ideal code

Every corner carries its own `R_ref = 0` row, and every error is the code
difference from **that** row. This is not a stylistic choice: the current
full-conversion corner record resolves the three mid-scale inputs within
1 LSB but is 100+ LSB off at `±0.78·V_REF` at every corner — the
near-full-scale common-mode droop DR-021 proposes to fix. Referencing to the
ideal code would attribute that pre-existing, already-recorded defect to the
reference drive. The record reports whether each control row matches the
ideal codes as *context*, never as a validity criterion.

### An input already at a code rail is blind, and is excluded rather than counted

That same DR-021 droop has, on the **positive** side, already pushed the
captured code hard against full scale: `+0.78·V_REF` reads `1023` in every
control row of the committed grid. A clipped code reports the same `0` delta
whatever the reference drive does to push it further out of range, so a `+0`
there is an artefact of the clipping — not the observation "the reference
drive left this input alone".

`pinned_inputs()` detects a control code sitting on either rail (`0` or full
scale) and the record then:

- prints **`pin`**, not `+0`, in that input's delta cells;
- **excludes** those (corner, input) pairs from every movement count it
  states, and says how many it excluded and which input they belong to;
- states in its limits section that it **bounds nothing** on a pinned input.

A pinned input that moves *inward*, off the rail, still prints its signed
delta and still counts toward `max abs delta` — the marker hides nothing that
actually moved. What the budgets in the committed grid turn on is the
*other* near-full-scale input, `−0.78·V_REF`, which the record reads off the
sweep rather than asserting.

`R_ref = 0` is simulated as ngspice's own zero-resistor floor — it rewrites a
0 Ω resistor to 1 × 10⁻¹² Ω with a warning — so the control row's topology is
identical to every swept row's rather than being a different deck.

### Budget tiers

Adapted from `sim/vcm-drive-budget/`'s `find_budget()` to an integer-code
observable:

- **0 LSB tier** — the largest swept `R_ref` whose captured codes are
  *unchanged* from the control at every input.
- **1 LSB tier** — the largest whose codes move by at most 1 LSB.

Both tiers are decided by the inputs that can register movement; an input
pinned at a code rail (above) contributes nothing to either, so a budget is
a statement about the countable inputs only.

A budget equal to the largest swept value is reported **right-censored**, the
same way that campaign reports one. The selection rule is also the same: the
last passing rung in ascending order, not the last rung before the first
failure — and when a rung above the chosen budget also passes, the record
says the sweep was **non-monotone** rather than hiding it.

## Execution: one `klt sim` request

The grid is expressed as a request, never as a loop over `ngspice`:

- the ratified 9-point one-at-a-time PVT star as `corners.process` ×
  `corners.temperature_c`, with `exclude` dropping the full-factorial points
  the star does not contain;
- the **supply as a `corners.params` axis** (`vdd_val`), not
  `corners.supply_v`. Every source in the committed fragment is written as an
  expression in `{vdd_val}`, and `alter` addresses element *instances*, never
  a `.param` — klt refuses a `supply_v` key that names a `.param`, and
  refuses one naming a `PWL`/`PULSE` source as well;
- `R_ref` zipped against the supply in the same `corners.params` rows, so the
  rows are the full supply × `R_ref` product.

`options.save_vectors` keeps only the signals the `.meas` cards read, so a
6.3 µs transient over ~2000 devices does not ship a `save all` rawfile per
unit.

### Sharding, and why `remote.hosts` is explicit

One unit is a whole-ADC 6.3 µs transient: **485 s measured** for
`tt`/27 °C/1.80 V on an 8-vCPU host. The fleet kills a whole **job** at its
`max_job_seconds` ceiling (3600 s by default) and *every* unit in a killed
job is lost, including the ones that had already finished.

`batch.job_ceiling_check: "split"` would size shards from
`options.timeout_s` — the per-unit *kill*, deliberately set to 2.5× the
measured runtime — and would therefore shard this grid into two-unit jobs.
So `shard_count()` sizes `remote.hosts` from the **measured** runtime
instead, conservatively: it assumes a shard's units run one after another
even though the job actually runs them through `--backend local-parallel`.
An explicit `remote.hosts` is honoured as given and its shards are not
re-assessed (`docs/cli/sim.md`, "Three budgets, and the fleet's whole-job
ceiling").

Submission passes `--wait-for-capacity 600` (and sets
`batch.capacity_wait_s`), so a burst that meets `batch_no_capacity` waits
with backoff instead of failing the step. A failed submit is reported, never
replaced by a local grid.

## What this testbench does **not** model

Read this before quoting any number from it.

- **Series resistance only.** Two resistors, one per reference pad, same
  value. No bond or trace inductance, no pad or bus capacitance, no
  decoupling network, no on-chip reference buffer.
- **Nothing else on the net.** No other load, no other project's switching
  activity, no high-frequency behaviour of a shared bus. A statement that
  some shared bus's switches are "less than 5 Ω" is *not* answered by this
  campaign beyond the series-resistance term of it.
- **`VCM` and all four supply terminals stay ideal at the die.**
- **DC inputs** — five levels, one conversion each, plus a discarded start-up
  conversion. Not a dynamic input and not a Monte Carlo draw.
- **One conversion rate** — `f_clk = 12 MHz`, `f_s = 1 MS/s`. A slower clock
  gives the reference longer to settle and would move these budgets up.
- **Nothing on an input pinned at a code rail** — see "An input already at a
  code rail is blind" above. In the committed grid that is `+0.78·V_REF` at
  every corner, so the budgets are a statement about the other four inputs.
- **Neither cross-check against `sim/full-conversion-transient/` is
  controlled for toolchain.** That campaign's record and this one were
  produced under different `open_pdks` commits, and this campaign submits
  from one host while the units execute on batch workers. The record names
  both PDK commits wherever it states a comparison, and names the
  disagreements as well as the agreements — including the corners where the
  two campaigns' ideal-drive codes do *not* match, which bound how much
  weight a 1 LSB movement in this record can carry.

## Files

| Path | What it is |
|---|---|
| `run_reference_drive_budget.py` | the runner: deck assembly, request builder, report reader, budget tiers, record writer |
| `records/` | dated, append-only evidence records; `records/LATEST` names the current one |
| `corners/<record-id>/` | that record's raw `klt sim` report, the request and the submitted deck |
| `netlist-snapshots/<record-id>.spice` | the assembled circuit body that run simulated |
| `sim/tests/test_reference_drive_budget.py` | PDK-free unit tests (deck edits, request shape, report reading, budget arithmetic, pinned-input exclusion, both cross-checks) |

Records are **append-only**: a re-run mints a new record-id and points back
through **Supersedes**, never edits an existing one (`sim/README.md`).

# sim/digital-partition/ — digital Fmax bracket, rail power, routed area (issue #619)

Closes the evidence gap behind T1 item 8's *digital* requirement ("Fmax, area
and power across the corner set, not just functional pass/fail"): the declared
digital partition — `design/sar_sequencer.sch` plus the 33 top-level
`sky130_fd_sc_hd` glue instances `design/sar_adc_top.sch` adds
(`signoff/block-manifest.json`'s `partition_boundary`) — characterized at the
ratified nine-point OAT corner set.

```
source sim/env.sh
python3 sim/digital-partition/run_digital_partition.py --plan
python3 sim/digital-partition/run_digital_partition.py --record
python3 sim/report/generate.py --write       # regenerates docs/characterization-report-digital.md
```

## Files

| File | Role |
|---|---|
| `digital_char.py` | PDK-free logic: frequency grid + bracket search, deck / `klt sim` request builders, grading, power arithmetic, checklist predicate |
| `digital_area.py` | Area from the committed routed DEF/GDS + the composed placement |
| `digital_report.py` | Report rendering, freshness pins, the generic envelope builder (used by `sim/report/generate.py`) |
| `run_digital_partition.py` | Campaign controller + record writer |
| `records/`, `corners/`, `runs/` | Append-only evidence (record, per-probe decks/requests/reports/logs, `campaign.json`) |

Tests: `sim/tests/test_digital_partition.py` (no ngspice, no PDK).

## Method in one paragraph

Every simulation unit is a `klt sim` request (default backend `$KLT_SIM_BACKEND`,
the Spot batch fleet); the controller never runs ngspice. The clock search is
adaptive per corner but quantised to one grid (12 MHz × 2^(i/8), ceiling
1536 MHz), so corners that need the same frequency share one request. Each
probe runs six back-to-back conversions with a deterministic COMP_OUT pattern
and checks, via high-impedance behavioural monitor nodes, the one-hot phase
after every clock edge, the BUSY/HALF_LSB control outputs, reset and
auto-restart, and at end-of-conversion the captured code, ADCOUT recode and
SELn/SELp. A missing or non-finite measurement is *invalid* — never a pass,
never a fail — and an all-invalid request stops the campaign. A too-fast
(6 GHz) clock must be graded FAIL at every corner (negative control). Rail
power is the average of `i(Vdig)` over declared whole-period windows; energy per
conversion is the active power × 12 clock periods.

## What the numbers are not

Schematic-level (no extracted parasitics); loads and COMP_OUT arrival are
experiment assumptions, not spec values; the bracket is a functional limit of
the digital partition alone and is **not** the reciprocal of a propagation
delay and **not** the ADC sample rate. See the record's Assumptions section.

## Runner / fleet notes

* `--allow-runner-skew` sets `batch.runner_version_check: "warn"`; it exists
  because the fleet runner image can lag the client `klt`. The record states the
  option when used. Default is `enforce`.
* `--capacity-wait-s` waits out a fleet capacity refusal (shared fleet).
* `--workdir` caches completed probe reports so an interrupted campaign resumes
  without re-spending fleet jobs.
* `--probe CORNER MHZ` runs one debug unit and may use `--backend local`.

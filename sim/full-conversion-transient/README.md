# `sim/full-conversion-transient/` — end-to-end full-conversion transient

The first experiment in this repo that runs the **whole ADC**. Every other
`sim/` experiment drives one sub-block, or drives the SAR sequencer against an
*ideal* comparator-decision stimulus (`sim/sar-sequencer-behavioral/`). This
one drives the committed, schematic-derived
[`design/sar_adc_top.spice`](../../design/sar_adc_top.spice) — sampling front
end + CDAC array + comparator + SAR sequencer + the nine `SELn` inverters —
through complete conversions at the DR-006 worst-case master clock, and
compares the captured `DOUT9..DOUT0` against the ideal code for each input, at
every point of the ratified PVT corner grid.

## What it measures

| Quantity | How |
| --- | --- |
| Captured code vs ideal code | 5 DC differential inputs spanning the code range (`-0.78`, `-0.25`, `0.00`, `+0.25`, `+0.78` × `V_REF`), read mid-`SAMPLE` of each conversion, decoded against `LSB = 2·V_REF/2^N` (`spec/target-spec.md`, RATIFIED DR-003) |
| Conversion completion | `BUSY` and `PH_SAMPLE` (`SAMPLE_INT`) sampled in the middle of each of the 12 CLK periods of every measured conversion — the "12 CLK periods, no missing or duplicated phase" check |
| Average supply/reference current and power | `.meas tran ... avg i(<source>)` over one whole steady-state conversion, per rail (`VDD`, `VPWR`, `VREFP`, `VCM`, `VREFN`) |

**Which `spec/target-spec.md` rows these numbers feed, and how:** the timing
data feeds the DRAFT **Sample rate** row and the current/power data feeds the
DRAFT **Power** row. **Neither is a pass/fail claim against a ratified row.**
Both rows are DRAFT; this campaign is the whole-ADC data that DR-003 Item 5
("no switch-`R_on`/CDAC settling data exists yet") and DR-006's own open item
("non-uniform, settling-driven phase timing — needs #24's CDAC/switch/
comparator netlist and #28's corner campaign") say a future decision record
needs *before* either row can be re-derived. This experiment records what the
circuit does at 12 MHz; it proposes no sample rate and no power target
("report, don't pre-commit"), and edits no spec row.

## Cold start

```sh
source sim/env.sh                                                    # PDK_ROOT / PDK
python3 sim/full-conversion-transient/run_conversion.py --check-env  # toolchain + PDK pin

# the recorded campaign (9 ratified OAT corner points + the mechanism probe):
SIM_NGSPICE_TIMEOUT_S=3600 python3 sim/full-conversion-transient/run_conversion.py \
    --corners --record --mechanism-probe --jobs 3
```

Reproduces from a clean checkout against the pinned PDK (`sim/pdk.json`) and
toolchain (`sim/toolchain.json`). Other useful invocations:

```sh
python3 sim/full-conversion-transient/run_conversion.py                 # baseline corner only
python3 sim/full-conversion-transient/run_conversion.py --mechanism-probe
python3 sim/full-conversion-transient/run_conversion.py --node-trace      # issue #259 node-level trace
python3 sim/full-conversion-transient/gen_full_conversion_tb.py --check  # fragment freshness
python3 -m unittest discover -s sim/tests -t sim/tests                   # PDK-free unit tests
```

**Runtime.** One corner point is a ~6.3 µs transient over the whole ADC and
takes roughly 3–6 minutes on the reference toolchain (longer on a contended
machine), so the 120 s `sim/harness` default timeout is far too small —
`SIM_NGSPICE_TIMEOUT_S` must be raised, as above. `--jobs N` runs N corner
points concurrently (independent ngspice processes; it changes runtime only,
never results).

## Timing schedule (DR-006)

`spec/decision-records/DR-006-sar-sequencer-bit-count-and-timing-budget.md`
allocates `N + 2 = 12` uniform master-clock periods per conversion. At the
worst-case `f_clk = 12 MHz` end of DR-006's derived `1.2–12 MHz` range a period
is `1000/12 = 83.333… ns`, so one conversion is exactly 1 µs. With CLK rising
edges numbered `k`, conversion `c` occupies:

| period | phase | note |
| --- | --- | --- |
| `12c + 0` | `PH_B9` | MSB trial; `DOUT9` captured at edge `12c + 1` |
| `12c + 1 … 12c + 9` | `PH_B8 … PH_B0` | one bit trial per period |
| `12c + 10` | `PH_EOC` | code complete and stable from edge `12c + 10` |
| `12c + 11` | `PH_SAMPLE` | `BUSY` low; the front end acquires conversion `c+1` |

Six back-to-back conversions are simulated: conversion 0 is a **start-up**
conversion and is discarded (its CDAC bottom plates start from the
`RST_B`-cleared register state and its SAMPLE phase is the power-up interval);
conversions 1–5 carry the five DC inputs. Each input is stepped three CLK
periods before its conversion's first bit trial — mid-bit-trial, with the
sampling switch open, so the step cannot disturb the conversion in flight.

## Directory contents

| Path | What |
| --- | --- |
| `gen_full_conversion_tb.py` | Generates the committed fragment; owns the timing schedule, the input set and the ideal-code mapping. `--check` fails if the committed fragment is stale (also pinned byte-for-byte by `sim/tests/test_full_conversion.py`). |
| `testbench/full_conversion_tb_fragment.spice` | The generated, committed testbench: sources, `.tran`, and every `.meas` card. Rail-referenced via `{vdd_val}` so one fragment serves every supply point. |
| `run_conversion.py` | Deck assembly, corner loop, decoding, record writing. |
| `netlist-snapshots/<record-id>.spice` | The frozen DUT netlist the record was produced from (byte-identical to `design/sar_adc_top.spice` at the recorded commit). |
| `corners/<record-id>/<corner-id>.log` | Raw ngspice output, one per ratified corner point. |
| `diagnostics/<record-id>/*.log` | `--mechanism-probe` raw output (see below). Kept separate from `corners/` because one of the two runs is on a **modified** netlist and must never be read as a corner result. |
| `diagnostics/<record-id>/node-trace-<corner-id>.log` | `--node-trace` raw output (issue #259, see below) — on the **unmodified** DUT, unlike the mechanism probe. |
| `records/<record-id>.md` | The append-only evidence record. `records/LATEST` names the newest **corner-campaign** record; `--node-trace` records are separate, targeted diagnostics and never update `LATEST`. |

## Deck assembly: the two load-bearing details

1. **`.global VPWR VGND`.** `design/sar_adc_top.sch`'s own header records that
   the digital standard cells' `VPWR`/`VGND` are literal instance properties
   with no schematic-graph node anywhere in the hierarchy, and names "adding a
   `.global` equivalence … at THAT testbench's assembly step" as the assembling
   testbench's job. Without it, `VPWR`/`VGND` inside the `sar_sequencer`
   subcircuit are floating locals and the sequencer has no supply at all.
2. **The `sky130_fd_sc_hd` combined-cell `.include`**, exactly as
   `sim/sar-sequencer-behavioral/run_testbench.py` does it.

## The mechanism probe (`--mechanism-probe`)

A **diagnostic**, not evidence for any spec row. It runs the same stimulus
twice at the baseline corner: once on the unmodified DUT, and once on a
**testbench-only modified** copy in which the comparator instance's strobe is
re-pointed from `CLK` to a separate `CLK_CMP` node driven half a CLK period
later. Its only job is to separate "the comparator's decision never reaches the
register" from "the register captures a decision that is itself wrong" when a
code comes out wrong. The modified netlist exists only inside the run's scratch
deck — nothing is ever written back to `design/`, and the modified run never
contributes to a corner result.

## The node-level trace (`--node-trace`, issue #259)

A second, more targeted **diagnostic**, not a corner campaign and not
evidence for any spec row. Unlike `--mechanism-probe`, it runs the
**as-committed, unmodified** DUT — it only appends read-only `.meas tran ...
find v(...)` probes after the committed fragment, never re-points any
instance's strobe. At each of the two corners issue #259's Acceptance
Criteria name (the binding corner and the corner where the
phase-timing/completion check itself also fails), it samples `COMP_OUT`
(`OUTP`) and its differential partner `OUTN_NC` (`OUTN`) against `CLK`, at
every one of the 10 bit-trial capturing edges — both mid-evaluate and 1 ns
before each capturing edge — plus the corresponding bit-capture register's
own output 2 ns after that edge. It always writes its own evidence record
under `records/` (never `records/LATEST`, which stays pointed at the
corner-campaign result).

**Two conversions are probed per run, and the pair is load-bearing.** Extra
`.meas` cards sample a transient that runs anyway, so tracing conversion 2
(`Vd = −0.25·V_REF`, ideal MSB `0`) *and* conversion 4 (`Vd = +0.25·V_REF`,
ideal MSB `1`) costs no extra simulation time. Their ideal MSB decisions
differ on purpose: the MSB trial is the only bit trial whose CDAC state
cannot already be corrupted by an earlier mis-captured bit, so comparing the
two conversions' MSB-trial *evaluate-half* output is the control that
separates "the decision is made correctly and then destroyed before capture"
(a capture-timing defect) from "no usable decision is ever made" (a dead
comparator). Both would otherwise look identical — a stuck code. If that
control ever stops discriminating, the record says so and explicitly refuses
to conclude, rather than reporting the capture-edge finding as sufficient.

## Findings

The first recorded campaign (`records/LATEST`) is a **FAIL** at every ratified
corner: the code is wrong for every input, while the 12-period phase structure
is correct everywhere. Both mechanisms are named, evidenced and filed as a
follow-up issue — see the record itself and
[issue #259](https://github.com/2AMLogic/sky130-sar-adc/issues/259). Nothing
here relaxes a spec line to make a result pass; the failure is recorded as a
finding, per `CLAUDE.md`.

Issue #259's own `--node-trace` record pins the mechanism down at node level.
The comparator and the bit-capture registers share the same `CLK` *net* but
use **opposite edges of it, in the wrong order**: the comparator's decision
exists only during the `CLK`-high evaluate half and is destroyed on the
**falling** edge (`XM_RST_P`/`XM_RST_N` pull both `OUTP` and `OUTN` to
`VDD`), while `xbreg9..xbreg0` sample on the **rising** edge that ends the
following reset half. `COMP_OUT` is therefore already back at `VDD` (digital
`1`) before every single capturing edge, at both traced corners, and every
register dutifully captures a `1` — hence code 1023. The deficit is a fixed
half-period of ordering, not a setup/hold margin, which is why all 9 ratified
corners fail identically.

This confirms — and refines —
[issue #257](https://github.com/2AMLogic/sky130-sar-adc/issues/257)'s
proposed root cause, and rules out
[issue #258](https://github.com/2AMLogic/sky130-sar-adc/issues/258)'s
floating-rail mechanism (already fixed by PR #261, with the saturation
unchanged across that fix). It does not itself implement a design fix — out
of scope for #259.

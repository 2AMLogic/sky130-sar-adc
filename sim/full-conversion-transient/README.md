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
python3 sim/full-conversion-transient/run_conversion.py --cm-trace        # issue #265 common-mode trace
python3 sim/full-conversion-transient/run_conversion.py --decision-margin-trace  # issue #263 / DR-009
python3 sim/full-conversion-transient/run_conversion.py --coherent-sine --record
# ^ issue #603/#605 coherent-sine SNDR/ENOB, baseline corner only (set
#   SIM_NGSPICE_TIMEOUT_S=5400 on a slow host; the 120 s default is too short)
python3 sim/full-conversion-transient/run_conversion.py --corners --record \
    --supersedes <record-id>   # name the prior record this one replaces (e.g. after a design/ fix)
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
| `testbench/coherent_sine_tb_fragment.spice` | `--coherent-sine`'s generated, committed testbench (issue #603): same supplies/clock/code reads as the DC fragment, coherent antiphase sine input. Pinned byte-for-byte by `sim/tests/test_dynamic_enob_fft.py`. |
| `dynamic_enob.py` | Stdlib-only radix-2 FFT and SNDR/ENOB/SFDR analyzer for `--coherent-sine` (no numpy -- `sim/` runs without a venv). |
| `corners/<record-id>/coherent-sine-<corner-id>.log` | `--coherent-sine` raw output, with the exact fragment that ran beside it. |
| `netlist-snapshots/<record-id>.spice` | The frozen DUT netlist the record was produced from (byte-identical to `design/sar_adc_top.spice` at the recorded commit). |
| `corners/<record-id>/<corner-id>.log` | Raw ngspice output, one per ratified corner point. |
| `diagnostics/<record-id>/*.log` | `--mechanism-probe` raw output (see below). Kept separate from `corners/` because one of the two runs is on a **modified** netlist and must never be read as a corner result. |
| `diagnostics/<record-id>/node-trace-<corner-id>.log` | `--node-trace` raw output (issue #259, see below) — on the **unmodified** DUT, unlike the mechanism probe. |
| `diagnostics/<record-id>/cm-trace-<corner-id>.log` | `--cm-trace` raw output (issue #265, see below) — on the **unmodified** DUT. |
| `diagnostics/<record-id>/decision-margin-<variant>-<corner-id>.log` | `--decision-margin-trace` raw output (issue #263 / DR-009, see below). Two variants per corner: `as-committed` (unmodified DUT) and `unbalanced-control` (testbench-only modification — never a corner result). |
| `records/<record-id>.md` | The append-only evidence record. `records/LATEST` names the newest **corner-campaign** record; `--node-trace`/`--cm-trace`/`--decision-margin-trace` records are separate, targeted diagnostics and never update `LATEST`; neither do `--coherent-sine` records. |

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

## The common-mode trace (`--cm-trace`, issue #265)

A third, targeted **diagnostic**, in the same "unmodified DUT, read-only
`.meas` probes" family as `--node-trace`. Issue #263/#266 fixed the three
structural defects `--node-trace` (issue #259) pinned down, and most of this
experiment's own five-input schedule then converged — except the two
near-full-scale inputs (`±0.78·V_REF`), which still fail badly and
corner-invariantly (`+0.78·V_REF` saturates to code 1023 at every ratified
corner). `--cm-trace` tests DR-008's own "Open items" leading hypothesis for
that residual failure: that decision-directed single-side CDAC switching
(the fix issue #263 landed) pushes the comparator's `TOP_P`/`TOP_N` input
pair (its own `VINP`/`VINN`) out of its ~23 mV nominal common-mode headroom
margin (DR-004) for large-magnitude codes. It traces `TOP_P`/`TOP_N` (added
to `node_trace_plan()`'s probe set alongside the existing `COMP_OUT`/`CLK`
probes) at conversions 1 and 5 — the `±0.78·V_REF` inputs themselves — at the
same two corners `--node-trace` uses.

**Finding: CONFIRMED**, and the mechanism is larger than DR-004's ~23 mV
framing suggested. At the MSB trial (the "free" sign bit, decided directly
off the sampled residual with no CDAC switching), `TOP_P`/`TOP_N` are simply
the sampled `VINP`/`VINN` and their average is exactly `VCM` by construction.
Once the magnitude bits begin, decision-directed switching gates one array
side's `SEL*<i>` to 0 for the *whole* conversion, so that side's bottom
plates — and its own top plate, with no other charge path once the sampling
switch has opened — stay frozen at whatever the sampling phase left them at.
The active side must then travel all the way to the frozen side's own
sampled value to converge, and for a near-full-scale input the frozen side
sits near a rail (measured: `TOP_N` pinned at ~0.20 V for the whole
`+0.78·V_REF` conversion) — so the pair's common mode droops from `VCM`
toward that near-rail value along with it. Measured worst-case droop:
**600–755 mV** at both traced corners, roughly 30× DR-004's own ~23 mV
margin figure — an input-magnitude-driven effect, not a PVT-margin one — and
the captured code diverges from the ideal code at exactly the bit trial
where the droop first flips the comparator's decision. See
[issue #265](https://github.com/2AMLogic/sky130-sar-adc/issues/265) and its
own `--cm-trace` evidence record for the full per-phase data and the
recommendation (an architecture-level tradeoff among a common-mode-neutral
CDAC switching scheme, a wider-common-mode comparator, or a documented
reduced dynamic range — filed as
[issue #267](https://github.com/2AMLogic/sky130-sar-adc/issues/267) rather
than attempted here).

## The decision-margin trace (`--decision-margin-trace`, issue #263 / DR-009)

The fourth **diagnostic** mode, and the one that answers a question none of
the others can: *is a wrong code the search's fault or the comparator's?*
The corner campaign only sees codes, and `--node-trace` samples the
comparator's **output** pair. This mode samples its **input** — `v(TOP_P) −
v(TOP_N)`, plus the top-plate common mode — at the last instant before each
bit trial's evaluate half opens (the DAC has had half a CLK period to settle
and the latch has not begun to load it), and pairs it with the decision the
comparator then produced and the bit the register captured. A decision that
disagrees with the *sign of the comparator's own input* is a comparator
defect by construction; one that agrees, while the code still comes out
wrong, is a search or decode defect.

Like `--mechanism-probe` (and unlike `--node-trace`) it runs the DUT twice:
`as-committed`, and an `unbalanced-control` copy with DR-009's two
comparator-output balancing dummy instances deleted at deck-assembly time,
which reproduces the pre-DR-009 asymmetric loading. **The pair is the
measurement**: both variants present the comparator with the same residuals
and decide them differently, which is what makes "the offset is created by
the output loading" evidence rather than inference. The modification is
testbench-only and is never written back to `design/`; if the two dummy
instances are ever renamed, the probe fails loudly instead of silently
tracing the wrong netlist.

Three mid-scale conversions are traced (`−0.25`, `+0.00`, `+0.25·V_REF`) —
the inputs whose late bit trials present residuals of order 1 LSB, where a
few-mV offset changes the answer. The near-full-scale conversions belong to
[issue #265](https://github.com/2AMLogic/sky130-sar-adc/issues/265) and are
deliberately not traced here.

## The coherent-sine dynamic test (`--coherent-sine`, issue #603)

The only **dynamic** (FFT) ENOB bench in the tree. The ENOB row's other
evidence, `sim/enob-estimate/run_enob.py`, composes per-block noise in
quadrature and says itself that a real dynamic ENOB needs a coherent-sampled
full-chip transient. This mode is that transient. It is an informational
**cross-check** of the behavioral estimate. It never grades the DRAFT ENOB row.

- **Stimulus.** The same DUT, supplies, clock, reset, mid-`PH_EOC` code reads
  and per-period BUSY/SAMPLE checks as the DC bench. Only the input changes,
  to an antiphase sine about `VCM`
  (`testbench/coherent_sine_tb_fragment.spice`, generated by
  `gen_full_conversion_tb.sine_fragment_text()`). Default plan: `N = 32`
  conversions after 1 discarded start-up conversion, tone on bin 7
  (`f_in = 7 · 1 MS/s / 32 = 218.75 kHz`), peak `0.25·V_REF` (−12 dBFS).
  The amplitude is the largest magnitude the DC corner campaign resolves
  within 1 LSB. A larger tone would sweep into the near-full-scale saturation
  that DR-021 addresses.
- **Analysis.** `dynamic_enob.py` is a stdlib-only radix-2 FFT, coherent with
  no window and DC excluded. It computes `SNDR`, `ENOB = (SNDR − 1.76)/6.02`
  (the same relationship `run_enob.py` uses), SFDR, and the ENOB normalised
  to a full-scale sine. That last figure is an extrapolation, and the record
  says so. Each record also reports an ideal 10-bit quantizer on the
  *identical* plan, because on a short record the ideal quantizer's own
  estimate deviates from `6.02·N + 1.76`.
- **Validity gate.** An FFT turns any code stream into a number. So the
  runner stamps the record **NOT A VALID MEASUREMENT** and exits 1 if any
  of these is wrong: a measurement is missing, a conversion lacks the
  12-period BUSY/SAMPLE structure, or the largest non-DC bin is not the
  drive bin.
- **Scope.** Baseline corner (`tt/27C/1.8V`) only. A longer record, more
  corners or Monte Carlo is a `klt sim` request (#564), not a local loop.
  Records never update `records/LATEST`.

**Pilot status (issue #605): first record minted.** The earlier ngspice-42
probe (issue #603) is not evidence and is superseded. The default plan
(`tt/27C/1.8V`, N=32, bin 7, 0.25*V_REF) was run on the pinned toolchain
(ngspice-47, PDK `c6d73a35...`) through the opt-in manual-dispatch job
`coherent-sine-evidence` in `.github/workflows/ci.yml` (dispatch CI with
`coherent_sine_evidence=true`; it uploads the new append-only files as an
artifact and never commits or pushes). Record:
`records/20261010-070734-f968286.md` (239 s wall-clock for 33.3 us).

* **VALIDITY is clean:** 0 missing measurements, 32/32 conversions with the
  correct 12-period BUSY/SAMPLE structure, largest non-DC bin = drive bin 7.
  This confirms the #603 probe's all-BUSY / two-code collapse was an artefact
  of the below-floor ngspice-42, not of the sine stimulus.
* **The headline figures are dominated by a single outlier conversion.**
  The record reports SNDR = 2.17 dB (ENOB 0.068 bit at the tone's amplitude;
  2.001 bit full-scale-normalised) and SFDR 13.77 dB, against 50.89 dB /
  8.161 bit for an ideal quantizer on the same plan. The record's own
  captured-code table shows where that comes from: **31 of the 32 codes are
  within +/-2 LSB of ideal**, and one conversion (sample 8, conversion 9,
  sampled Vd = +0.0196 x V_REF, just above the zero crossing) returned code
  **960 against an ideal 522 (+438 LSB)**. That one conversion carries nearly
  all of the error power. A back-of-envelope recompute from the table (not
  recorded evidence) puts SNDR at roughly 47 dB with conversion 9 replaced
  by a typical +1 LSB code. The SFDR is very likely set by the same
  outlier. So 2.17 dB / 0.068 bit should **not** be read as a clean
  measurement of the converter's dynamic performance, and it does not show
  the code is wrong across the inputs. What it shows is one unexplained
  near-mid-scale conversion error that the VALIDITY gate does not check for:
  the gate checks phase structure, missing measurements and the tone bin,
  not per-code error. The minted record is append-only, and its LIMITATIONS
  section does not mention the outlier. This paragraph is the correction.
  Root-causing conversion 9 and adding an outlier check are tracked in
  [issue #621](https://github.com/2AMLogic/sky130-sar-adc/issues/621). The result is informational only (one corner, N=32, no
  noise, below full scale). The DRAFT ENOB row and every target value are
  unchanged.
* Indexed under the ENOB row of `sim/spec-coverage.json`.

**Per-code outlier diagnostic (issue #621).** `--coherent-sine` now reports,
on the console and in every new record, a named *diagnostic* (not a validity
criterion -- a large code error can be a real DUT result): the signed error
`captured - ideal` per sample, the bound, the maximum |error|, and every
outlier (sample, conversion, ideal, captured, signed error). The default bound
is `SINE_OUTLIER_BOUND_LSB = 8` LSB, flagged when |error| is strictly greater:
4x the +-2 LSB spread of the in-family codes in the first record and 8x the
DC campaign's 1 LSB resolution, yet far below a glitch like conversion 9
(+438). Headline SNDR/ENOB/SFDR always come from the complete, unmodified
captured stream. Beside them the record gives a clearly labelled
**DIAGNOSTIC-ONLY, NOT REPLACEMENT EVIDENCE** sensitivity: because an FFT needs
the whole coherent record, the outlier samples are not deleted but have their
error zeroed (ideal code substituted at those samples only) and the metrics
and deltas recomputed. Existing validity failures (missing measurement, phase
structure, wrong tone bin) are unchanged. Covered PDK-free by
`TestOutlierDiagnostic` in `sim/tests/test_dynamic_enob_fft.py`.

**Conversion 9 root cause: still OPEN.** Checked while implementing #621: the
existing `--node-trace` / `--decision-margin-trace` modes probe conversions
using the *DC* campaign's stimulus (`tb.input_fraction`, DC fragment), so they
do **not** cover the coherent-sine conversion-9 input and timing context and
cannot be reused as-is; a sine-fragment trace is needed. The pinned toolchain
(`sim/toolchain.json`: ngspice >= 46) was unavailable on the implementing host
(ngspice-42), where results are not valid evidence, so no trace was run, no
mechanism is claimed, and no new record was minted. The first record and its
corrections above stand.

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

**Where this stands now (issue #263, both passes).** The paragraphs above are
kept as the record of how the investigation went; they describe the
*pre-#257* campaign, not the current one. Since then: #257 fixed the
capture-edge ordering; #263's first pass
(`spec/decision-records/DR-008-...`) added the trial perturbation, the
per-conversion CDAC clear and decision-directed single-side switching with
offset-binary output recoding; #263's second pass
(`spec/decision-records/DR-009-...`) balanced the comparator's differential
output load and added a half-LSB quantizer offset. The newest campaign
record resolves **all three mid-scale inputs to within ±1 LSB at 9/9
ratified corners**. It is still recorded as an overall **FAIL**, for exactly
one remaining reason: the two near-full-scale inputs (`±0.78·V_REF`) do not
converge — [issue #265](https://github.com/2AMLogic/sky130-sar-adc/issues/265)
— and DR-009's own "Open items" names a second, smaller contributor that is
not closed either (the array's ~1% absolute gain error, which is 0 LSB at
mid-scale but ~3 LSB near full scale). Read `records/LATEST`, not this
section, for the current numbers.

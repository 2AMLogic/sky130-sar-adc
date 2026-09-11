"""Structured citation data for the aggregated characterization report
(issue #30, T1 item 8). Kept separate from sim/report/generate.py's
rendering/freshness logic so the *evidence-selection* decision (which
record substantiates which spec/target-spec.md row) is a reviewable data
structure, not buried in string-formatting code.

Each row below names the exact evidence record(s) sim/report/generate.py
resolves and re-extracts fields from at generation time (Record ID,
Overall, Corner matrix run / Statistical convention, Supersedes) --  see
that module's docstring for why this counts as "regenerating from the
records" rather than hand-transcribing their contents, and for the
mechanical freshness check every ``sim_citations`` path is run through.

Do not add a citation here without having read the record it names --
this file is provenance, not a template.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Row:
    id: str
    spec_row: str
    status: str  # verbatim from spec/target-spec.md's own Status column
    spec_anchor: str
    conditions: str
    verdict: str
    notes: str
    sim_citations: tuple[str, ...] = field(default_factory=tuple)
    layout_citations: tuple[str, ...] = field(default_factory=tuple)


ROWS: tuple[Row, ...] = (
    Row(
        id="architecture",
        spec_row="Architecture",
        status="DRAFT",
        spec_anchor="spec/target-spec.md#target-table",
        conditions="N/A -- descriptive/topology row, not a numeric pass/fail claim.",
        verdict="N/A (DRAFT, descriptive row)",
        notes=(
            "Implemented as charge-redistribution SAR, differential, top-plate "
            "sampling (`design/sar_adc_top.sch`, `design/cdac/cdac_array.sch`, "
            "`design/sampling_frontend.sch`, `design/comparator.sch`, "
            "`design/sar_sequencer.sch`) -- matches the DRAFT row's description. "
            "Not ratified, so there is no pass/fail verdict to render; listed here "
            "for coverage honesty (every target-spec.md row appears, including "
            "unratified/unmeasured ones, per this report's own acceptance criteria)."
        ),
    ),
    Row(
        id="resolution-n",
        spec_row="Resolution `N`",
        status="RATIFIED",
        spec_anchor="spec/target-spec.md#numeric-rows--ratified-2026-08-19",
        conditions=(
            "Full ratified corner set: process {ff, fs, sf, ss, tt} x "
            "temperature {-40, 27, 125} C x supply {1.62, 1.8, 1.98} V, "
            "9 one-at-a-time points (sim/README.md 'Corner-grid shape')."
        ),
        verdict="PASS (9/9 corners)",
        notes=(
            "Confirms MSB-first bit-by-bit capture of all 10 output bits, correct "
            "clock/phase sequencing, and the ring sequencer's auto-restart, at "
            "every bound corner. The CDAC array's own 9-bit sub-array realizes "
            "only 512 positions/side; the 10th (sign) bit comes from the "
            "top-level differential structure, per "
            "`sim/cdac-array-transfer/records/20260828-005006-0c70212.md`'s own "
            "'UNITS / scope note' -- not independently re-verified by this row's "
            "own citation."
        ),
        sim_citations=("sim/sar-sequencer-behavioral/records/20260827-211956-e13bc1e.md",),
    ),
    Row(
        id="sample-rate",
        spec_row="Sample rate",
        status="DRAFT",
        spec_anchor="spec/target-spec.md#target-table",
        conditions=(
            "All four constituent mechanisms have now been probed "
            "individually; none of these campaigns is a sample-rate "
            "measurement. (a) CDAC-array bottom-plate-switch settling: "
            "now PVT-complete (the full ratified OAT grid, 9 "
            "one-at-a-time points). (b) Comparator decision "
            "(regeneration) delay: the full ratified OAT grid (process "
            "{ff, fs, sf, ss, tt} x temperature {-40, 27, 125} C x supply "
            "{1.62, 1.8, 1.98} V, 9 one-at-a-time points), now PVT-complete "
            "after issue #175's reset-integrity topology fix (DR-004 "
            "Amendment A). (c) Sequencer CLK-to-phase-output logic delay: "
            "now ALSO PVT-complete (the same full ratified OAT grid, 9 "
            "one-at-a-time points), covering all 11 ring-sequencer phase "
            "transitions at every point (99 phase measurements). (d) "
            "Sampling front end acquisition (a new "
            "worst-case, rail-to-rail differential input value acquired "
            "once SAMPLE re-asserts): now ALSO PVT-complete (the same full "
            "ratified OAT grid, 9 one-at-a-time points), one step direction. "
            "All four mechanisms are now PVT-complete. Issue #236 fixed the "
            "sampling front end's own acquisition mechanism (the fourth) "
            "after it was found to fail the DR-006 phase budget at every "
            "ratified corner; re-measured against the full grid, it now "
            "clears the budget at all 9."
        ),
        verdict=(
            "UNMEASURED as an end-to-end sample-rate figure (four "
            "mechanisms probed individually, not combined); all four "
            "mechanisms are now PVT-complete AND all four now clear the "
            "DR-006 worst-case phase budget at every ratified corner -- "
            "CDAC settling and sequencer logic delay by a wide margin, "
            "comparator decision delay PASSes its own reset-integrity "
            "control (9/9 corners HELD) and also clears the budget at "
            "every corner, and the sampling front end's own acquisition "
            "(the sole mechanism that previously failed at every corner) "
            "now also clears it at all 9, after issue #236's circuit fix. "
            "Separately (issue #254): the first WHOLE-ADC transient (not a "
            "per-mechanism probe) drove the committed `design/sar_adc_top."
            "spice` through complete conversions at the DR-006 worst-case "
            "12 MHz clock across the full ratified 9-corner grid; its "
            "12-CLK-period phase structure (BUSY/PH_SAMPLE timing) PASSED "
            "at 8/9 corners (informational -- this experiment binds no "
            "spec row), but code correctness FAILED at 9/9 corners (every "
            "DC input at every corner captured the saturated code 1023), "
            "so no end-to-end sample rate could be derived from it either "
            "-- see the Findings entry below and issue #259. After issue "
            "#257's capture-timing fix (`comparator.CLK` driven from "
            "`CLKN`) the same campaign re-run reports the phase structure "
            "at 9/9 corners and an input-tracking (no longer saturated) "
            "code, worst error 910 -> 384 LSB -- but still not the correct "
            "code at any corner, so this row stays UNMEASURED; the "
            "remaining defect is the SAR search itself, tracked in #263."
        ),
        notes=(
            "No end-to-end sample-rate campaign exists. All four of its "
            "input terms have now been probed separately, and this row "
            "reports all four honestly rather than adding them up. (a) The "
            "CDAC array's own switch-R_on/top-plate settling is now "
            "PVT-complete: binding (slowest) corner `tt_27c_1.62v`, bit 8 "
            "(rise) at 13.2312 ns, 6.3x inside the DR-006-derived "
            "83.333 ns worst-case phase budget; fastest corner "
            "`tt_27c_1.98v` at 10.3019 ns (8.1x); worst-to-best spread "
            "across the whole grid only 1.28x, and the tt/27C/1.8V point "
            "reproduces the single-corner record's own 11.3861 ns exactly. "
            "All 9/9 corners clear the budget. A secondary, non-gating "
            "finding: the smallest-swing diagnostic row (bit 0, ~0.2% of "
            "VDD swing) failed to produce a 99%-settling crossing at 5/9 "
            "corners -- root-caused (not asserted without evidence, "
            "confirmed window-invariant out to 300 ns) to a small, "
            "genuine, already-converged offset between the real simulated "
            "circuit and the analytic closed-form ideal (order 0.1-0.3 mV, "
            "plausibly charge-injection/subthreshold-leakage) that is "
            "negligible against bit 8's own ~1.8 V swing but exceeds 1% of "
            "bit 0's own ~4 mV swing at some corners; bit 8 (the array's "
            "own true worst case per its tau_i(i) = R_on * C_i * "
            "(1 - C_i/C_total) shape) crossed cleanly at all 9/9 corners, "
            "so this curiosity does not affect the worst-case finding. "
            "(b) The comparator's own decision "
            "delay is now PVT-complete: issue #175 (DR-004 Amendment A) "
            "moved the cross-coupled NMOS latch pair's sources off "
            "hard-wired GND onto the input pair's own precharged drain "
            "nodes, closing the reset-integrity defect the prior pass "
            "surfaced (Vindiff = 0 mV control now HELD at all 9 ratified "
            "corners, 0.00 uA reset-phase static current at every corner). "
            "All 27/27 input-driven decision points resolved within the "
            "15.0 ns evaluate window; binding corner `tt_27c_1.62v` at "
            "Vindiff = +0.5 mV, decision delay 4.3575 ns, 19.1x inside the "
            "DR-006-derived 83.333 ns worst-case phase budget (headroom "
            "against a DRAFT figure, not a pass against a ratified line). "
            "(c) The SAR sequencer's own CLK-to-phase-output logic delay is "
            "now PVT-complete across all 11 of its own ring-sequencer phase "
            "transitions at all 9 ratified corner points (99 phase "
            "measurements, all producing a valid crossing): binding "
            "(slowest) corner `ss_27c_1.80v`, phase b1 at 0.4237 ns, 196.7x "
            "inside the DR-006-derived 83.333 ns worst-case phase budget; "
            "fastest corner `ff_27c_1.80v` at 0.2480 ns (336.1x); "
            "worst-to-best spread across the whole grid only 1.71x, and the "
            "tt/27C/1.8V point reproduces the single-corner record's own "
            "0.3123 ns exactly. Slow process and low supply are the two "
            "slow directions; temperature is nearly inert (0.3211 ns at "
            "-40 C vs. 0.3038 ns at 125 C). All 9/9 corners clear the "
            "budget by more than two orders of magnitude -- by far the "
            "smallest of the four mechanisms measured, and not the "
            "bottleneck at any ratified corner. (d) The sampling front end's "
            "own acquisition of a NEW worst-case (rail-to-rail) differential "
            "input value, once SAMPLE re-asserts, was first bounded at ONE "
            "corner (tt/27C/1.8V): the fast early settling (50%/90% of the "
            "way to the new value) is sub-ns on both nodes, but a slow "
            "secondary settling tail -- traced to the bootstrap precharge "
            "PFET `Sa`'s imperfect off-state once `BOOST_x` is driven above "
            "VDD, letting the boosted gate droop over tens of ns -- left a "
            "residual 23.43 mV (single-ended, worst node) still uncorrected "
            "83.333 ns after the acquiring edge, ~13.3x the provisional "
            "differential LSB's half-step. That single-corner finding has "
            "since been taken to the FULL ratified PVT grid (9 "
            "one-at-a-time points): every one of the 9 corners exceeds the "
            "half-LSB reference scale, confirming the mechanism is not a "
            "corner-specific artifact. Binding corner `tt_27c_1.62v`: "
            "TOP_P residual 67.19 mV, 38.2x the half-LSB, 2.9x worse than "
            "the tt/27C/1.8V baseline point; best corner `tt_27c_1.98v`: "
            "9.00 mV, 5.1x the half-LSB. Issue #236 fixed this: "
            "instrumenting `BOOST_x` directly found two independent "
            "limiters. (1) The bootstrap precharge PFET `Sa`'s gate was "
            "tied to `SAMPLE` (a VDD-level signal) while `Sa`'s own source "
            "is `BOOST_x` (driven to ~VIN+VDD during sampling) -- V_sg = "
            "BOOST_x - VDD ~= VIN, an ON device discharging the boosted "
            "node throughout the sample phase, not the leaky-off device "
            "originally assumed. Re-gating `Sa` from the switch's own gate "
            "node `G_x` instead (already GND during hold, shorted to "
            "`BOOST_x` during sampling) makes `Sa` genuinely off. (2) With "
            "(1) applied, the common-mode reference transmission gate "
            "`Cmswn`/`Cmswp` -- in series with `Csamp` via the floating "
            "`BPREF_x` node -- was the limiter that remained; widened from "
            "W=1um to W=16um. Re-measured against the full ratified PVT "
            "grid with both fixes applied: ALL 9/9 corners now clear the "
            "DR-006 worst-case (12 MHz) phase budget, worst case "
            "`tt_27c_1.62v` at 0.380 mV (~0.2x the half-LSB) vs. that same "
            "corner's pre-fix 67.190 mV (~38.2x). This mechanism is no "
            "longer the standout bottleneck of the four -- all four now "
            "clear the budget at every ratified corner. Three things this "
            "fix touches are explicitly NOT yet re-derived: "
            "`sim/vcm-drive-budget/`'s R_source/C_decouple budget (a wider "
            "`Cmsw` draws more peak current from the shared `VCM` rail), "
            "and `layout/sampling-frontend/`'s LVS match and "
            "`layout/sar-adc-top/`'s composition of it (both now stale "
            "against the new `Sa` gate net and `Cmsw` width) -- tracked as "
            "issue #245. Named as open work by spec/target-spec.md's "
            "own 'Not ratified by this record' list (#24/#28); DR-006's "
            "1.2-12 MHz clock range remains a mechanical consequence of "
            "this DRAFT row, not a derived result. (e) Issue #254's "
            "`sim/full-conversion-transient/` campaign is the first to "
            "drive the whole assembled `sar_adc_top` netlist (all four "
            "sub-blocks together, real comparator, real sequencer) rather "
            "than one mechanism in isolation. Its own phase-timing check "
            "(BUSY high during EOC, low again by the next conversion's "
            "SAMPLE phase -- the same 12-CLK-period structure "
            "`sim/sar-sequencer-behavioral/` proved against an IDEAL "
            "COMP_OUT stimulus) reproduces at 8/9 ratified corners "
            "(`ff_27c_1.80v` is the one exception), corroborating (a)/(c) "
            "above at the whole-ADC level. But the captured DOUT9..DOUT0 "
            "code itself is wrong at all 9/9 corners (every DC input "
            "saturates to code 1023) -- a NEW, whole-ADC-only finding none "
            "of the four isolated mechanisms above could have surfaced, "
            "since each drives its own sub-block with an ideal stimulus "
            "for every OTHER sub-block. A `--mechanism-probe` diagnostic "
            "(delaying the comparator's own capture-clock edge relative to "
            "its strobe, testbench-only, not a committed design change) "
            "produces different, non-saturated codes at the same input "
            "set, pointing at a comparator-decision-capture timing "
            "relationship in `design/sar_adc_top.sch`'s wiring as the "
            "likely mechanism -- filed as issue #259 rather than asserted "
            "here as a root cause. This finding does not change (a)-(d)'s "
            "own per-mechanism PASS verdicts against the DR-006 phase "
            "budget; it shows those four passing budgets are not "
            "sufficient for the assembled ADC to produce a correct code, "
            "which is exactly why this row remains UNMEASURED rather than "
            "closed out. (f) Issue #258 then made "
            "`design/sar_adc_top.spice` self-contained -- it now emits "
            "`.GLOBAL VPWR` / `.GLOBAL VGND` alongside the analog rails' "
            "own cards, so the standard cells nested inside its `xseq` "
            "instance are no longer scoped to a private, unpowered copy "
            "of the digital rails whenever the netlist is simulated as a "
            "whole. The campaign in (e) was re-run against that fixed "
            "netlist and reproduces every finding unchanged (same 1023 "
            "saturation at 9/9 corners, same 8/9 phase structure, same "
            "per-corner power). That is the expected outcome rather than "
            "a null result: (e)'s own testbench already supplied the "
            "missing declaration at its own deck-assembly step, so #258 "
            "moves the declaration into the netlist without changing what "
            "this campaign measures. The re-run therefore does NOT "
            "supersede (e), and #259 stands exactly where it did. "
            "(g) Issue #257 then fixed the capture-timing relationship "
            "#259's node-level trace pinned down: `comparator.CLK` is now "
            "driven from `CLKN = NOT(CLK)` (`design/sar_adc_top.sch`), so "
            "the comparator's evaluate half ends AT the bit-capture "
            "registers' own rising capturing edge instead of a half-period "
            "after its decision was destroyed. The campaign in (e)/(f) was "
            "re-run against that fixed netlist -- the record cited below "
            "supersedes (f)'s -- and the phase-timing check now reproduces "
            "at 9/9 ratified corners (the `ff_27c_1.80v` exception noted "
            "above is gone), strengthening (a)/(c) at the whole-ADC level. "
            "The captured code is no longer stuck at 1023: it now tracks "
            "the applied differential (`0, 0, 768, 896, 1023` for the five "
            "DC inputs) and the worst code error drops 910 -> 384 LSB. It "
            "is still WRONG at 9/9 corners, bit-identical at every corner "
            "(no PVT dependence at all), for a second and independent "
            "reason the fix uncovered and issue #263 now tracks: the SAR "
            "search applies no trial perturbation before each decision, "
            "never clears the CDAC bits between conversions, and drives "
            "both array sides unconditionally. So this row stays "
            "UNMEASURED for the same reason as before -- the four "
            "per-mechanism budgets still are not sufficient for the "
            "assembled ADC to produce a correct code -- but the reason is "
            "now a search-algorithm defect, not a capture-timing one."
        ),
        sim_citations=(
            "sim/cdac-bit-trial-settling/records/20260905-220919-bbf06dd.md",
            "sim/cdac-bit-trial-settling/records/20260907-013225-5f176a6.md",
            "sim/comparator-decision/records/20260906-074451-7724af3.md",
            "sim/sequencer-logic-delay/records/20260906-192230-1b5c996.md",
            "sim/sequencer-logic-delay/records/20260906-230516-0904419.md",
            "sim/sampling-acquisition-settling/records/20260906-202424-cb7e7aa.md",
            "sim/sampling-acquisition-settling/records/20260908-051436-6ccd72d.md",
            "sim/full-conversion-transient/records/20260910-190240-2d1d196.md",
            "sim/full-conversion-transient/records/20260911-132101-add8859.md",
        ),
    ),
    Row(
        id="enob",
        spec_row="ENOB",
        status="DRAFT (target value)",
        spec_anchor="spec/target-spec.md#target-table",
        conditions=(
            "Behavioral-accelerated composite (NOT a dynamic-test/FFT "
            "measurement): comparator noise term taken from the RATIFIED full-"
            "PVT corner campaign's worst-case binding corner (`tt_125c_1.80v`, "
            "not re-simulated); CDAC mismatch nonlinearity from a `tt_mm` "
            "Monte Carlo campaign, N=40, base seed=1 (draws seed..seed+N-1), "
            "PVT point tt/27C/1.8V; kT/C sampling noise analytic at the 125 C "
            "worst case; quantization noise analytic (LSB/sqrt(12))."
        ),
        verdict=(
            "DOES NOT MEET the DRAFT baseline target (>9.0 bit), informationally: "
            "8.506 bit (mean-case CDAC mismatch) / 7.755 bit (worst-case). Target "
            "not ratified -- not a pass/fail against a ratified line."
        ),
        notes=(
            "Excludes dynamic effects (settling, slewing, aperture jitter, "
            "reference droop -- needs a future top-level transient/FFT "
            "campaign), treats CDAC INL as an rms noise-like term rather than "
            "input-correlated distortion, reuses the comparator's REDUCED SUB-"
            "MODEL noise figure, and deliberately excludes comparator offset. "
            "Re-run this pass (issue #175) against the amended comparator noise "
            "figure (0.8643 mV rms, down from 0.9591 mV rms) -- achieved ENOB "
            "moved from 8.491/7.749 to 8.506/7.755 bit; the pass/fail outcome is "
            "unchanged. See the cited record's own LIMITATIONS field for the "
            "full list."
        ),
        sim_citations=("sim/enob-estimate/records/20260906-082749-7724af3.md",),
    ),
    Row(
        id="inl-dnl",
        spec_row="INL / DNL",
        status="DRAFT (target value)",
        spec_anchor="spec/target-spec.md#target-table",
        conditions=(
            "Monte Carlo: `tt_mm` corner, N=40, base seed=1, PVT point "
            "tt/27C/1.8V, 22-code reduced set covering every major-carry "
            "transition of the 9-bit sub-array. Combined with (not replacing) "
            "the deterministic structural/monotonicity PVT campaign for the "
            "same DUT, run across the full ratified 9-point corner set."
        ),
        verdict=(
            "DOES NOT MEET the DRAFT target (<= +-1 LSB, target_yield=0.99), "
            "informationally: empirical yield 0.8250 [0.6722, 0.9266] (DNL) / "
            "0.9250 [0.7961, 0.9843] (INL) at 95% CI, N=40. klt yield's own "
            "sample-size verdict on both is 'insufficient' for a tight yield-"
            "fraction claim. Target not ratified."
        ),
        notes=(
            "The array-only 9-bit sub-array's own code step is 2x the ratified "
            "ADC LSB; DNL/INL are reported in ratified-LSB units per the cited "
            "record's own UNITS/scope note, not the array's native step."
        ),
        sim_citations=(
            "sim/cdac-array-transfer/records/20260828-005006-0c70212.md",
            "sim/cdac-array-transfer/records/20260827-213107-e13bc1e.md",
        ),
    ),
    Row(
        id="vref",
        spec_row="`V_REF`",
        status="RATIFIED",
        spec_anchor="spec/target-spec.md#numeric-rows--ratified-2026-08-19",
        conditions=(
            "Full ratified corner set, 9 OAT points. V_REF is a fixed design "
            "constant per DR-003's own scope table, not itself a simulated "
            "quantity -- the cited record confirms the CDAC array correctly "
            "consumes `VREFP={vdd_val}`/`VREFN=0` at each corner's own supply "
            "point, not that a reference-generator circuit meets a tolerance "
            "(none is ratified)."
        ),
        verdict="PASS (structural + functional/monotonicity check, 9/9 corners)",
        notes="See spec/decision-records/DR-003-numeric-spec-derivation.md for the full derivation.",
        sim_citations=("sim/cdac-array-transfer/records/20260827-213107-e13bc1e.md",),
    ),
    Row(
        id="lsb",
        spec_row="LSB (differential)",
        status="RATIFIED",
        spec_anchor="spec/target-spec.md#numeric-rows--ratified-2026-08-19",
        conditions="Full ratified corner set, 9 OAT points (same record as `V_REF` above).",
        verdict="PASS (structural + functional/monotonicity check, 9/9 corners)",
        notes=(
            "3.5156 mV differential; used as the reporting unit for the INL/DNL "
            "row above and the ENOB row's quantization-noise term."
        ),
        sim_citations=("sim/cdac-array-transfer/records/20260827-213107-e13bc1e.md",),
    ),
    Row(
        id="sampling-cap",
        spec_row="Sampling cap (CDAC unit × array)",
        status="RATIFIED",
        spec_anchor="spec/target-spec.md#numeric-rows--ratified-2026-08-19",
        conditions=(
            "sim: structural check (unit-cap geometry + per-side weight totals) "
            "at every corner of the ratified sim record. layout: drawn/extracted "
            "physical geometry, DRC + LVS against design/cdac/cdac_array.sch, "
            "single-point (no corner sweep -- DRC/LVS are corner-invariant "
            "structural checks, not PVT-dependent measurements)."
        ),
        verdict=(
            "PASS (sim structural check, 9/9 corners) + PASS (layout: DRC clean, "
            "LVS match, unit-cap count 1024 = 512/side x 2, common-centroid "
            "checks all pass). Drawn unit cap 8.6473 fF vs. ratified C_u ~= "
            "8.65 fF."
        ),
        notes=(
            "Layout evidence is independent, physical confirmation of the "
            "sim-only structural check. Supersedes "
            "layout/cdac-array/reports/20260825-132454-51cbdd4/, whose LVS "
            "'match' verdict did not reproduce on its own committed "
            "artefacts -- see layout/cdac-array/README.md and issue #148."
        ),
        sim_citations=("sim/cdac-array-transfer/records/20260827-213107-e13bc1e.md",),
        layout_citations=("layout/cdac-array/reports/20260905-220338-9fb9b04/record.md",),
    ),
    Row(
        id="comparator-noise",
        spec_row="Comparator input-referred noise",
        status="RATIFIED",
        spec_anchor="spec/target-spec.md#numeric-rows--ratified-2026-08-19",
        conditions=(
            "Full ratified corner set, 9 OAT points, `ac-based` noise "
            "methodology, integration bandwidth 1 kHz - 1 GHz. REDUCED SUB-"
            "MODEL (the input pair's own precharged drain-node PMOS pair "
            "diode-connected as loads, cross-coupled latch pairs omitted, "
            "CLK held at VDD) -- named, flagged simplification, re-derived "
            "against the amended device set by issue #175 (DR-004 Amendment "
            "A), see "
            "spec/decision-records/DR-004-comparator-topology-and-noise-budget.md."
        ),
        verdict=(
            "PASS vs. baseline (<=1.0148 mV rms) at every corner, binding "
            "corner `tt_125c_1.80v` = 0.8643 mV rms; does NOT meet the stretch "
            "threshold (<=0.5859 mV rms) at the binding corner."
        ),
        notes="",
        sim_citations=("sim/comparator-decision/records/20260906-065109-eedd532.md",),
    ),
    Row(
        id="power",
        spec_row="Power",
        status="DRAFT",
        spec_anchor="spec/target-spec.md#target-table",
        conditions=(
            "Issue #254's `sim/full-conversion-transient/` campaign, full "
            "ratified OAT grid (9 one-at-a-time points): average supply/"
            "reference current over one steady-state conversion (12 CLK "
            "periods at the DR-006 worst-case 12 MHz clock), per rail "
            "(`VDD`, `VPWR`, `VREFP`, `VCM`, `VREFN`), `P = sum(V_source * "
            "|avg I_source|)`. ADC core only -- no reference buffer, clock "
            "generator, or output driver exists in this design yet, so a "
            "real system's reference/clock power is not included."
        ),
        verdict=(
            "UNMEASURED as a Power-row figure/target (informational first "
            "current/power evidence only, not a pass/fail against any "
            "target -- 'report, don't pre-commit')"
        ),
        notes=(
            "First supply-current measurement of any kind on this block. "
            "Binding (highest-power) corner `tt_27c_1.98v`: 14.743 uW; "
            "lowest `tt_27c_1.62v`: 8.692 uW; tt/27C/1.80V baseline point: "
            "11.101 uW. NOTE: this same campaign's own code-correctness "
            "check FAILS at all 9 ratified corners (see the Sample rate "
            "row above and issue #259), so these current/power numbers are "
            "measured on a conversion that is NOT resolving to the correct "
            "code -- they characterize the circuit's steady-state current "
            "draw under the DR-006 12 MHz clock schedule, not the current "
            "draw of a functionally-correct conversion. Re-measure once the "
            "code-correctness defect is fixed, before treating this figure "
            "as durable. One unrelated, non-gating data point also exists "
            "outside sim/'s evidence trail: `layout/sar-sequencer/reports/"
            "20260825-124031-1a2f7c1/record.md`'s OpenROAD PnR estimate for "
            "the digital SAR-sequencer sub-block ONLY (0.0155 mW) -- a static "
            "EDA-tool estimate, not a simulated/measured full-ADC number, and "
            "not tied to the ratified corner set. Cited for completeness, not "
            "as spec-row evidence. Re-measured unchanged after issue #258's "
            "netlist-scoping fix (`.GLOBAL VPWR`/`.GLOBAL VGND` now declared "
            "by `design/sar_adc_top.spice` itself): every per-corner figure "
            "above reproduced to the digit, so the caveat about these numbers "
            "being measured on a functionally-incorrect conversion was "
            "unchanged too. SUPERSEDED FIGURES (issue #257): the second "
            "record cited below re-measures the same campaign on the "
            "post-#257 DUT (`comparator.CLK` driven from `CLKN`, so the bit "
            "trials now capture live comparator decisions instead of the "
            "comparator's reset level), and the power roughly doubles because "
            "the CDAC and the SAR register are now actually switching every "
            "conversion instead of sitting in a stuck all-ones code: binding "
            "(highest-power) corner `tt_27c_1.98v` 26.760 uW, lowest "
            "`tt_27c_1.62v` 16.750 uW, tt/27C/1.80V baseline 21.874 uW. The "
            "caveat itself still stands and is the reason this row remains "
            "UNMEASURED: the conversion still does not resolve to the correct "
            "code (see the Sample rate row above and issue #263), so this is "
            "the steady-state current draw of a switching-but-not-converging "
            "conversion. Re-measure again once #263 lands."
        ),
        sim_citations=(
            "sim/full-conversion-transient/records/20260910-190240-2d1d196.md",
            "sim/full-conversion-transient/records/20260911-132101-add8859.md",
        ),
    ),
    Row(
        id="corners",
        spec_row="Corners",
        status="RATIFIED",
        spec_anchor="spec/target-spec.md#numeric-rows--ratified-2026-08-19",
        conditions=(
            "The -40/27/125 C x +-10% supply x sky130 process-corner set "
            "itself, as exercised by every deterministic-row campaign below."
        ),
        verdict=(
            "In use, verified: harness self-test PASS (proves the corner "
            "runner switches the .lib process-corner section / .temp card / "
            "vdd_val independently per axis; sim/selftest.sh Stage 4's "
            "sabotage negative control backs this further) plus 3 deterministic-"
            "row corner campaigns (27 corner-points total), all PASS."
        ),
        notes="",
        sim_citations=(
            "sim/harness-corner-smoke/records/20260814-020959-98d9186.md",
            "sim/cdac-array-transfer/records/20260827-213107-e13bc1e.md",
            "sim/comparator-decision/records/20260906-065109-eedd532.md",
            "sim/sar-sequencer-behavioral/records/20260827-211956-e13bc1e.md",
        ),
    ),
)


POST_LAYOUT_NOTE = """\
**post-layout: not yet available, because** full-ADC layout is not complete
(#25, open, `loom:epic`) and `klt pex` is not implemented end-to-end upstream
(a `2AMLogic/klayout-tools` tool gap, filed generically per `CLAUDE.md`'s
friction protocol; see `layout/comparator/pex/README.md` for the two
specific bugs hit and worked around by hand for the one sub-block below).

One sub-block exception exists and is disclosed here rather than folded into
a spec-row verdict: `layout/comparator/reports/20260825-151036-aaf3010/record.md`
is a genuine post-layout parasitic-extraction re-sim (`klt extract
--parasitics` + `klt sim` on both legs, working around two `klt pex` bugs by
hand) for the **comparator sub-block only**, at a **single** PVT point
(tt/27C/1.8V), comparing schematic-vs-extracted pick-off offset. It is
**not** corner-swept, is **not** integrated into `sim/`'s append-only
evidence trail (no `Claim` against a `spec/target-spec.md` row, no
`records/` entry), and does **not** cover the CDAC array, sampling front
end, or SAR sequencer. It answers a narrower question -- is the
comparator's routing-parasitic-driven offset material against its
device-mismatch-driven offset? (no, by more than two orders of magnitude) --
and does not substitute for T1 item 7's full-ADC extracted re-sim against
the ratified corner set. Treated here as informational, not as post-layout
spec-row evidence.
"""

BLIND_SPOTS = (
    (
        "Comparator RESET-integrity defect (FIXED by issue #175 / DR-004 "
        "Amendment A, kept here as history, not a live gap). Through PR #176, "
        "`design/comparator.sch`'s outputs separated to the rails DURING the "
        "CLK=0 reset phase at 3 of 9 ratified corner points with the inputs "
        "shorted to the common mode (Vindiff = 0 mV negative control), because "
        "the cross-coupled NMOS latch pair's sources were tied directly to "
        "GND and therefore conducted throughout reset, in opposition to the "
        "reset PMOS pair -- an unstable equilibrium that amplified corner/"
        "temperature asymmetry to a decision before the clock edge arrived. "
        "Issue #175 moved those sources onto the input pair's own precharged "
        "drain nodes (DIP/DIN), closing the DC path and the amplification "
        "mechanism: the re-run campaign "
        "(`sim/comparator-decision/records/20260906-074451-7724af3.md`) shows "
        "9/9 reset-integrity controls HELD and 0.00 uA reset-phase static "
        "current at every corner. No ADC-level transient has ever exercised "
        "the real comparator inside the full hierarchy (the sequencer "
        "campaign is behavioural; the ENOB estimate composes a noise term "
        "rather than simulating the latch) -- still true post-fix, and still "
        "why a defect of this kind could recur undetected by those two "
        "campaigns alone."
    ),
    (
        "Comparator noise methodology is a REDUCED SUB-MODEL (the input "
        "pair's own precharged drain-node PMOS pair diode-connected as "
        "loads, cross-coupled latch pairs omitted) -- excludes the latch's "
        "own regenerative-phase noise contribution. Carried unchanged (as a "
        "methodology limitation) into the ratified corner campaign and into "
        "the ENOB composite, across the issue #175 topology amendment. See "
        "DR-004."
    ),
    (
        "ENOB is a behavioral-accelerated composite, not a dynamic-test "
        "(FFT) measurement: it excludes settling, slewing, aperture jitter "
        "and reference droop; treats CDAC INL as an rms noise-like term "
        "rather than input-correlated distortion; and deliberately "
        "excludes comparator offset."
    ),
    (
        "Comparator/ADC offset has no numeric spec row (ratified or DRAFT). "
        "`sim/comparator-decision/`'s offset Monte Carlo (N=24, `tt_mm`, "
        "seed=1) is a distribution-only characterization with no `klt "
        "yield` pass/fail step -- a limit-less measurement is a `klt yield` "
        "input error by design, per sim/README.md."
    ),
    (
        "Both statistical-row Monte Carlo campaigns (CDAC N=40, comparator "
        "offset N=24) are sized only for a distribution-SHAPE claim "
        "(~10-15% relative standard error on the estimated stdev), not for "
        "a tight yield-fraction claim at 95% confidence -- `klt yield`'s "
        "own sample-size verdict on the CDAC measurements is 'insufficient' "
        "(5547 samples needed for `dnl_max_lsb`, 2666 for `inl_max_lsb`, at "
        "+-0.01). Neither campaign's `klt yield` report declares a "
        "`negative_control` (the harness-level negative control described "
        "in each record's own 'Negative control' section is separate from, "
        "and does not substitute for, this `klt yield`-level declaration)."
    ),
    (
        "`dnl_max_lsb`'s N=40 sample set fails an Anderson-Darling "
        "normality check (A2*=0.9079 > 0.787) in its `klt yield` report -- "
        "the parametric yield/Cpk figures for that measurement are "
        "indicative only; this report cites the empirical estimate."
    ),
    (
        "SAR sequencer layout LVS does **NOT** match "
        "(`layout/sar-sequencer/reports/20260825-124031-1a2f7c1/record.md`): "
        "device counts match exactly (760/760) but net/device "
        "correspondence resolves 0/0, due to a known `klt extract` pin/net-"
        "name-promotion bug on OpenROAD DEF->GDS-merged layouts (filed "
        "generically upstream). DRC is clean. A real, outstanding LVS gap "
        "for one of five layout sub-blocks -- not a warning-level nit."
    ),
    (
        "Comparator layout LVS is now a MISMATCH against the current "
        "schematic (as of issue #175 / DR-004 Amendment A's topology "
        "change) -- `reports/LATEST` still records a genuine match, but that "
        "was against the pre-amendment 9-device topology. The drawn "
        "geometry has not been updated: it still implements 9 devices "
        "where the schematic now has 11 (the two DIP/DIN precharge PMOS "
        "are not drawn), confirmed via a falsifiability control that "
        "reproduces the old match against the superseded reference and a "
        "genuine mismatch (8 unmatched devices) against the amended one -- "
        "`layout/comparator/reports/20260906-064104-eedd532/`. Re-drawing "
        "the block is tracked as issue #180, not bundled into #175's "
        "topology fix. See `layout/comparator/README.md`'s status section."
    ),
    (
        "Uncombined evidence legs: `sim/sampling-frontend/` and "
        "`sim/sampling-cdac-handoff/` (interface-correctness diagnostics "
        "for the sampling front end <-> CDAC handoff) are not run at the "
        "full ratified corner set -- mostly tt/27C/1.8V only, with a single "
        "`ss`-corner point run as a directional (non-gating) check that "
        "exceeded half an LSB. Neither carries a `spec/target-spec.md#...` "
        "`Claim` of its own, so neither is cited against any row above; "
        "both remain load-bearing supporting evidence for the front-end/"
        "CDAC interface design that has not been folded into a spec-row "
        "corner campaign."
    ),
    (
        "`V_REF` is asserted, not simulated: DR-003's own scope table "
        "treats it as a fixed design constant. No record measures a "
        "reference-generator circuit's own tolerance (none is ratified)."
    ),
    (
        "Layout evidence cited by this report (sampling-cap row, and the "
        "LVS findings above) has no append-only 'Supersedes' convention "
        "the way `sim/` does (sim/README.md). This report's mechanical "
        "freshness check (see sim/report/generate.py) therefore covers "
        "only the `sim/` citations; layout citations are pinned to the "
        "specific report-directory path shown and are not automatically "
        "re-resolved to 'latest'. Documented gap, not silently assumed "
        "current."
    ),
)

NO_GRANT_STATEMENT = """\
This report records **no grant**. `2AMLogic/product/everyblock/grants.md` is
the authoritative ledger for tier grants (T1/T2/...) and is maintained by
the operator; nothing in this file should be read as, or substituted for,
that ledger. This report aggregates evidence records and their verdicts
only.
"""

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
            "Two of the constituent mechanisms have now been probed "
            "individually; neither campaign is a sample-rate measurement. "
            "(a) CDAC-array bottom-plate-switch settling: `tt`/27C/1.8V "
            "single point only. (b) Comparator decision (regeneration) delay: "
            "the full ratified OAT grid (process {ff, fs, sf, ss, tt} x "
            "temperature {-40, 27, 125} C x supply {1.62, 1.8, 1.98} V, 9 "
            "one-at-a-time points), now PVT-complete after issue #175's "
            "reset-integrity topology fix (DR-004 Amendment A)."
        ),
        verdict=(
            "UNMEASURED as an end-to-end sample-rate figure (two mechanisms "
            "probed individually, not combined); comparator decision delay "
            "is now a PVT-complete measurement, PASS on its own reset-"
            "integrity control (9/9 corners HELD)"
        ),
        notes=(
            "No end-to-end sample-rate campaign exists. Two of its input terms "
            "have been probed separately, and this row reports both honestly "
            "rather than adding them up. (a) The CDAC array's own "
            "switch-R_on/top-plate settling is bounded at ONE corner: worst "
            "case 11.3861 ns (bit 8, rise), 7.3x inside the DR-006-derived "
            "83.333 ns worst-case phase budget -- so the array's own settling "
            "is not the bottleneck at that corner. Switch R_on varies "
            "materially with process/temperature and no other corner has been "
            "run. (b) The comparator's own decision delay is now PVT-complete: "
            "issue #175 (DR-004 Amendment A) moved the cross-coupled NMOS "
            "latch pair's sources off hard-wired GND onto the input pair's "
            "own precharged drain nodes, closing the reset-integrity defect "
            "the prior pass surfaced (Vindiff = 0 mV control now HELD at all "
            "9 ratified corners, 0.00 uA reset-phase static current at every "
            "corner). All 27/27 input-driven decision points resolved within "
            "the 15.0 ns evaluate window; binding corner `tt_27c_1.62v` at "
            "Vindiff = +0.5 mV, decision delay 4.3575 ns, 19.1x inside the "
            "DR-006-derived 83.333 ns worst-case phase budget (headroom "
            "against a DRAFT figure, not a pass against a ratified line). "
            "The sequencer's logic delay and the sampling front end's "
            "acquisition remain entirely unmeasured, so this is still not an "
            "end-to-end sample-rate number. Named as open work by "
            "spec/target-spec.md's own 'Not ratified by this record' list "
            "(#24/#28); DR-006's 1.2-12 MHz clock range remains a mechanical "
            "consequence of this DRAFT row, not a derived result."
        ),
        sim_citations=(
            "sim/cdac-bit-trial-settling/records/20260905-220919-bbf06dd.md",
            "sim/comparator-decision/records/20260906-074451-7724af3.md",
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
        conditions="N/A -- no full-block power campaign exists.",
        verdict="UNMEASURED",
        notes=(
            "One unrelated, non-gating data point exists outside sim/'s "
            "evidence trail: `layout/sar-sequencer/reports/"
            "20260825-124031-1a2f7c1/record.md`'s OpenROAD PnR estimate for "
            "the digital SAR-sequencer sub-block ONLY (0.0155 mW) -- a static "
            "EDA-tool estimate, not a simulated/measured full-ADC number, and "
            "not tied to the ratified corner set. Cited for completeness, not "
            "as spec-row evidence."
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

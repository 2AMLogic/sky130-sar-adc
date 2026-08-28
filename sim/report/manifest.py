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
        conditions="N/A -- no campaign has been run.",
        verdict="UNMEASURED",
        notes=(
            "No switch-R_on/settling-time campaign exists under sim/. It needs a "
            "CDAC/switch netlist and a dedicated corner campaign; the completed "
            "corner campaigns (issue #28) covered the RATIFIED deterministic "
            "rows (V_REF/LSB/N/sizing/comparator noise), not sample rate. Named "
            "as open work by spec/target-spec.md's own 'Not ratified by this "
            "record' list (#24/#28)."
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
            "8.491 bit (mean-case CDAC mismatch) / 7.749 bit (worst-case). Target "
            "not ratified -- not a pass/fail against a ratified line."
        ),
        notes=(
            "Excludes dynamic effects (settling, slewing, aperture jitter, "
            "reference droop -- needs a future top-level transient/FFT "
            "campaign), treats CDAC INL as an rms noise-like term rather than "
            "input-correlated distortion, reuses the comparator's REDUCED SUB-"
            "MODEL noise figure, and deliberately excludes comparator offset. "
            "See the cited record's own LIMITATIONS field for the full list."
        ),
        sim_citations=("sim/enob-estimate/records/20260828-005033-0c70212.md",),
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
        notes="Layout evidence is independent, physical confirmation of the sim-only structural check.",
        sim_citations=("sim/cdac-array-transfer/records/20260827-213107-e13bc1e.md",),
        layout_citations=("layout/cdac-array/reports/20260825-132454-51cbdd4/record.md",),
    ),
    Row(
        id="comparator-noise",
        spec_row="Comparator input-referred noise",
        status="RATIFIED",
        spec_anchor="spec/target-spec.md#numeric-rows--ratified-2026-08-19",
        conditions=(
            "Full ratified corner set, 9 OAT points, `ac-based` noise "
            "methodology, integration bandwidth 1 kHz - 1 GHz. REDUCED SUB-"
            "MODEL (cross-coupled latch pair replaced by diode-connected loads, "
            "CLK held at VDD) -- named, flagged simplification, see "
            "spec/decision-records/DR-004-comparator-topology-and-noise-budget.md."
        ),
        verdict=(
            "PASS vs. baseline (<=1.0148 mV rms) at every corner, binding "
            "corner `tt_125c_1.80v` = 0.9591 mV rms; does NOT meet the stretch "
            "threshold (<=0.5859 mV rms) at the binding corner."
        ),
        notes="",
        sim_citations=("sim/comparator-decision/records/20260827-212404-e13bc1e.md",),
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
            "sim/comparator-decision/records/20260827-212404-e13bc1e.md",
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
        "Comparator noise methodology is a REDUCED SUB-MODEL (cross-coupled "
        "latch pair replaced by diode-connected loads) -- excludes the "
        "latch's own regenerative-phase noise contribution. Carried "
        "unchanged into the ratified corner campaign and into the ENOB "
        "composite. See DR-004."
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
        "Comparator layout LVS is a genuine MATCH but carries one warning-"
        "severity finding ('device class has no counterpart on the other "
        "side, but no devices of this class were extracted either -- not a "
        "real topology mismatch', error_count=0) -- noted for completeness, "
        "not gating."
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

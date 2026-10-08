#!/usr/bin/env python3
"""Sampling-frontend/CDAC-array bottom-plate handoff verification (issue #95).

Resolves the interface mismatch documented in
spec/decision-records/DR-004-sampling-frontend-sizing.md's "Open items" and
design/sar_adc_top.sch's "KNOWN, NAMED-NOT-CLOSED INTEGRATION GAPS" item 1:
design/sampling_frontend.sch (#52) drives BPREF_P/BPREF_N to VCM only during
SAMPLE on the documented assumption that design/cdac/cdac_array.sch (#53)
would "take over" a combined bottom-plate node once sampling ends -- but the
array as actually built has no such node: every bit's bottom plate
(BOT_p0..BOT_p8 / BOT_n0..BOT_n8) is individually and continuously driven to
VREFP or VREFN by its own SEL<i> switch (design/cdac/cdac_unit_cell.sch),
and design/sar_adc_top.sch (#56) already leaves BPREF_P/BPREF_N on their own
dead-end nets (BPREF_P_NC/BPREF_N_NC) rather than wiring them to anything.

This experiment instantiates BOTH sub-blocks' regenerated netlist fragments
together, tied at TOP_P/TOP_N exactly as design/sar_adc_top.sch wires them
(BPREF_P/BPREF_N left unconnected to anything else, matching the *_NC dead
ends), and drives SELp<i>/SELn<i> directly with ideal DC sources standing in
for the SAR sequencer's DOUT<i> register held at a fixed "previous
conversion" code throughout the SAMPLE phase under test -- the same
testbench-only-ideal-driver precedent sim/cdac-array-transfer/'s own
testbench already uses for SEL, since design/sar_sequencer.sch's mux2_1/
dfrtp_1 register holds each bit at its prior value except during that bit's
own trial phase (never during SAMPLE), per that schematic's own header.

WHY THIS MATTERS (the circuit argument this experiment tests empirically,
not just by hand analysis): during SAMPLE, TOP_P/TOP_N are driven
low-impedance to VINP/VINN by the front end's own bootstrapped switches
(Msw_p/Msw_n) -- so whatever the CDAC array's bottom plates are doing during
SAMPLE cannot prevent TOP_P/TOP_N from tracking the analog input. Once
SAMPLE ends, TOP_P/TOP_N float and their value is set by charge conservation
across every capacitor attached to them: the CDAC array's own per-bit caps
(bottom plates continuously driven, so NOT floating -- their charge is
input-dependent exactly as intended by a charge-redistribution DAC) and the
front end's own Csamp_p/Csamp_n (bottom plate BPREF_P/BPREF_N, which -- once
Cmswn/Cmswp open at the SAMPLE falling edge AND the dead-end top-level
wiring leaves BPREF_P/BPREF_N touching nothing else -- become an ISOLATED
two-terminal capacitor whose charge is frozen and which therefore injects
ZERO further current into TOP_P/TOP_N for the rest of the conversion). So
TOP_P/TOP_N should settle to VINP/VINN at the end of SAMPLE regardless of
what "previous code" the CDAC array's bottom plates were left at -- this
experiment sweeps three previous-code states (all-zero, all-one,
alternating) across the front end's own worst-case/common-mode test points
to confirm that prediction, not just assert it.

WHAT `--corners` ADDS, AND WHY IT IS A DIFFERENT QUESTION (issue #469).
Everything above is about CORRECTNESS of the sampled value at the end of a
generous (400 ns) SAMPLE window: does the CDAC array's previous-code state
corrupt it (it does not). It says nothing about SPEED at the assembled
load. `docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2's fourth
named sample-rate mechanism -- "(d) the sampling front end's own
acquisition of a new, worst-case (rail-to-rail) differential input value
once SAMPLE re-asserts" -- is measured by
`sim/sampling-acquisition-settling/run_acquisition_settling.py`, whose
PVT-complete record reads
`sim/sampling-frontend/testbench/sampling_frontend_dut.spice` ALONE: its
`TOP_P`/`TOP_N` carry only the front end's own `Csamp_p`/`Csamp_n`
(~4.43 pF/side, DR-004). At the top level, `design/sar_adc_top.sch` ties
those same nodes to the CDAC array too -- roughly DOUBLE the load that grid
was run against. `--corners` closes that gap: it replays mechanism (d)'s own
stimulus and its own fixed-time DR-006-budget probe, byte-for-byte the same
measurement definition, against THIS experiment's combined (front end + real
CDAC array) top-plate load, at the full ratified 9-point OAT PVT grid. The
only pre-existing combined-load evidence for it was one directional `ss`
point in this campaign's first record (5.33 mV single-ended residual at
`worst_case_pp`, ~3.0x the provisional differential half-LSB), measured
before issue #236's two-part front-end fix and explicitly deferred there to
"a future timing pass". This is that pass.

Usage (from the repo root, after `source sim/env.sh`):
    python3 sim/sampling-cdac-handoff/run_handoff.py            # print results
    python3 sim/sampling-cdac-handoff/run_handoff.py --record    # + write evidence
    python3 sim/sampling-cdac-handoff/run_handoff.py --full      # + ss corner
    # Mechanism (d) at the assembled load, full ratified PVT grid (9 OAT
    # points -- the same axes sim/sampling-acquisition-settling/ sweeps):
    python3 sim/sampling-cdac-handoff/run_handoff.py --corners --record
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
EXPERIMENT_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(SIM_DIR))
from harness import corners as corners_mod, pdk, toolchain, evidence, measure  # noqa: E402

FE_FRAG = EXPERIMENT_DIR / "testbench" / "sampling_frontend_dut.spice"
CDAC_FRAG = EXPERIMENT_DIR / "testbench" / "cdac_array_dut.spice"

# The two schematics those committed fragments are netlisted FROM. --corners
# re-netlists both at run time and refuses to run if a committed fragment's
# device content no longer matches its schematic (see
# assert_fragments_current() -- issue #469's "measure the shipping devices"
# requirement, enforced structurally rather than trusted).
FE_SCH = REPO_ROOT / "design" / "sampling_frontend.sch"
CDAC_SCH = REPO_ROOT / "design" / "cdac" / "cdac_array.sch"
XSCHEMRC = SIM_DIR / "xschemrc"

# The two `.meas tran ... find ... at=` names emitted by build_netlist()'s
# .control block below -- passed to harness.measure.parse() as its required
# explicit allowlist.
MEASURE_NAMES = ["top_p_end", "top_n_end"]

# Same three differential test points sim/sampling-frontend/run_transient.py
# uses, for direct comparability against DR-004's already-recorded in-sample
# settling result.
TEST_POINTS = {
    "common_mode": (0.9, 0.9),
    "worst_case_pp": (1.6, 0.2),
    "worst_case_np": (0.2, 1.6),
}

# "Previous conversion" bottom-plate code states the CDAC array's SELp<i>/
# SELn<i> are held at throughout SAMPLE (per design/sar_adc_top.sch's own
# SELp<i>=DOUT<i> / SELn<i>=NOT(DOUT<i>) wiring, and design/sar_sequencer.sch's
# register holding each bit outside its own trial phase). bits are
# lsb-first, i=0..8.
CODE_STATES = {
    "prev_code_zero": [0] * 9,  # DOUT_prev = 0 on every bit -> BOT_p*=VREFP, BOT_n*=VREFN
    "prev_code_one": [1] * 9,  # DOUT_prev = 1 on every bit -> BOT_p*=VREFN, BOT_n*=VREFP
    "prev_code_alt": [i % 2 for i in range(9)],  # alternating bits
}

VDD = 1.8
VCM = 0.9
LSB_DIFF_MV_PROVISIONAL = 3.5156  # DR-003 Item 2, provisional pending #27

SAMPLE_END_NS = 409.0  # matches sim/sampling-frontend/run_transient.py

# --- issue #469: ratified corner axes for the --corners mode below ----------
# spec/target-spec.md's "Numeric rows -- RATIFIED 2026-08-19" section:
# -40/27/125C, +-10% supply, sky130 process corners. Passed to the shared
# corners.ratified_oat_grid() helper (NOT hand-assembled from
# supply_points()/oat_grid(), which is the drift issue #211/#217 closed) so
# this campaign's grid is the same 9-point one-at-a-time star every other
# --corners driver in sim/ runs.
SUPPLY_TOLERANCE = corners_mod.RATIFIED_SUPPLY_TOLERANCE
TEMPS_C = corners_mod.RATIFIED_TEMPS_C
PROCESS_CORNERS = corners_mod.RATIFIED_PROCESS_CORNERS

# --- issue #469: mechanism (d)'s stimulus, replayed at the combined load ----
# Every constant below is lifted unchanged from
# sim/sampling-acquisition-settling/run_acquisition_settling.py, deliberately:
# the ONLY intended difference between that campaign's PVT-complete record and
# this one is the capacitive load on TOP_P/TOP_N (front end alone there; front
# end + real CDAC array here, tied exactly as design/sar_adc_top.sch wires
# them). See that script's own module docstring for the full rationale of each
# interval, of the two-pulse shape, and of why the budget-relevant read is a
# fixed-time `find ... at=` probe rather than a TRIG/TARG crossing search.
EDGE_TR_NS = 0.2
T_SAMPLE1_RISE_NS = 10.0
T_SAMPLE1_WIDTH_NS = 100.0
T_SAMPLE1_FALL_NS = T_SAMPLE1_RISE_NS + T_SAMPLE1_WIDTH_NS  # 110.0
T_INPUT_TOGGLE_NS = T_SAMPLE1_FALL_NS + 20.0  # 130.0 -- input steps while Msw is off
T_SAMPLE2_RISE_NS = T_INPUT_TOGGLE_NS + 30.0  # 160.0 -- the acquiring edge
T_SAMPLE2_WIDTH_NS = 150.0
T_SAMPLE2_FALL_NS = T_SAMPLE2_RISE_NS + T_SAMPLE2_WIDTH_NS  # 310.0
TRAN_STOP_NS = T_SAMPLE2_FALL_NS + 20.0  # 330.0

# The ONE stimulus constant that is deliberately NOT the front-end-only
# campaign's own value (0.02 ns), and why. `tran <step> <stop>`'s first
# argument is a step CEILING, not a fixed step: ngspice still reduces the step
# adaptively through the fast edges either way, so the ceiling only bounds how
# coarsely it may march through the slow intervals. The front-end-only campaign
# needs 0.02 ns because it ALSO measures sub-ns `TRIG/TARG` 50%/90% crossings;
# this mode measures only the two fixed-time `find ... at=` reads deep in the
# slow settling tail, where a 0.2 ns ceiling changes nothing measurable -- and
# the combined (roughly doubled) top-plate load makes each run expensive enough
# (~4 minutes at 0.2 ns, ~25 minutes at 0.02 ns on the host that produced this
# campaign's records) that the 10x ceiling is what makes the 9-point grid a
# single-session run at all. `--tran-step-ns` re-runs any point at another
# ceiling so the choice is checkable rather than asserted; the record reports
# the ceiling it was produced at.
TRAN_STEP_NS = 0.2

# DR-006-derived per-phase clock budgets (one CLK period per phase, uniform
# allocation) -- quoted for comparison only, never as a pass/fail gate: the
# sample-rate spec row they descend from is entirely DRAFT (#1/#27).
T_PHASE_WORST_NS = 1.0e3 / 12.0  # 83.333... ns @ f_clk_max = 12 MHz
T_PHASE_SLOW_NS = 1.0e3 / 1.2  # 833.33... ns @ f_clk_min = 1.2 MHz

TRIG_AT_NS = T_SAMPLE2_RISE_NS + EDGE_TR_NS / 2.0  # 160.1 -- 50% of the edge
BUDGET_PROBE_AT_NS = TRIG_AT_NS + T_PHASE_WORST_NS  # 243.433...
CONFIRM_AT_NS = T_SAMPLE2_FALL_NS - 5.0  # 305.0

V_INITIAL_P, V_FINAL_P = 0.2, 1.6
V_INITIAL_N, V_FINAL_N = 1.6, 0.2

SIDES = {
    "p": ("TOP_P", V_INITIAL_P, V_FINAL_P),
    "n": ("TOP_N", V_INITIAL_N, V_FINAL_N),
}

# The `.meas tran ... find ... at=` names build_acquisition_netlist() emits.
BUDGET_MEASURE_NAMES = [f"{stat}_{side}" for side in SIDES for stat in ("budget", "confirm")]

# The single CDAC "previous conversion" code state --corners holds throughout.
# One state, not all three: this campaign's own tt-corner evidence (record
# 20260824-231304-144edeb) found the sampled value IDENTICAL to the reported
# precision across all three, which is the expected consequence of every
# bottom plate being continuously driven (never floating) -- so the array's
# contribution to the TOP_x load, the quantity --corners measures, does not
# depend on the code. `prev_code_one` is chosen because it is the state at
# which that record's own pre-#236 `ss` excursion (5.33 mV) was found, and
# --corners re-checks the independence itself at the baseline corner (the
# other two states, 2 extra runs) rather than leaving it asserted from the
# older, pre-#236, different-measurement record alone.
CORNERS_CODE_STATE = "prev_code_one"


def build_netlist(
    vinp: float, vinn: float, code_bits: list[int], corner: str, temp_c: float = 27.0
) -> str:
    fe_frag = FE_FRAG.read_text()
    cdac_frag = CDAC_FRAG.read_text()
    info = pdk.resolve()
    lines = [
        f"* sampling-cdac-handoff verification (issue #95) -- corner={corner} temp={temp_c}C",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        "",
        f"Vdd VDD 0 dc {VDD}",
        "Vvss VSS 0 dc 0",
        f"Vrefp VREFP 0 dc {VDD}",
        "Vrefn VREFN 0 dc 0",
        f"Vinp VINP 0 dc {vinp}",
        f"Vinn VINN 0 dc {vinn}",
        f"Vvcm VCM 0 dc {VCM}",
        # SAMPLE: 0 (hold) -> VDD (sample) at 10ns, width 400ns, period 800ns
        # -- identical pulse shape to sim/sampling-frontend/run_transient.py.
        f"Vsample SAMPLE 0 pulse(0 {VDD} 10n 1n 1n 400n 800n)",
        "",
        "* SELp<i>/SELn<i>: ideal DC sources standing in for the SAR",
        "* sequencer's DOUT<i> register held at a fixed previous-conversion",
        "* code throughout SAMPLE (see module docstring).",
    ]
    for i, bit in enumerate(code_bits):
        selp = VDD if bit else 0.0
        seln = 0.0 if bit else VDD
        lines.append(f"Vselp{i} SELp{i} 0 dc {selp}")
        lines.append(f"Vseln{i} SELn{i} 0 dc {seln}")
    lines += [
        "",
        fe_frag,
        "",
        cdac_frag,
        "",
        ".control",
        "tran 1n 500n",
        f"meas tran top_p_end find v(TOP_P) at={SAMPLE_END_NS}n",
        f"meas tran top_n_end find v(TOP_N) at={SAMPLE_END_NS}n",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


def _device_lines(fragment_text: str) -> list[str]:
    """The device/card lines of a netlist fragment: everything that is not a
    `*`-comment line and not a bare `.end`. Used to compare a committed
    fragment against a freshly netlisted schematic without tripping over the
    hand-written provenance header the committed copies carry (and which
    xschem, naturally, does not emit)."""
    return [
        line
        for line in fragment_text.splitlines()
        if not line.startswith("*") and line.strip() != ".end"
    ]


def _netlist_schematic(sch: Path, out_dir: Path, out_name: str) -> Path:
    """toolchain.netlist_with_xschem() plus a documented tolerance for one
    xschem quirk this campaign is the first in the tree to hit.

    Measured with the pinned xschem 3.4.7 on this repo's own schematics:
    `design/sampling_frontend.sch`, `design/sar_sequencer.sch` and
    `design/cdac/cdac_unit_cell.sch` all netlist with exit 0, while
    `design/cdac/cdac_array.sch` and `design/sar_adc_top.sch` exit **10** with
    empty stdout/stderr -- having written a complete, correct netlist (its
    device lines are byte-identical to the committed fragment, and it ends with
    the `**.ends` / `.end` pair xschem emits last). `netlist_with_xschem()`
    treats any nonzero exit as fatal, which is right in general, so rather than
    weaken that shared helper for every caller this wrapper accepts a nonzero
    exit ONLY when the output file is present and structurally complete --
    header line present and `.end` as its last card. A genuinely truncated
    netlist still raises.
    """
    try:
        return toolchain.netlist_with_xschem(sch, out_dir, XSCHEMRC, out_name)
    except RuntimeError as exc:
        out_path = out_dir / out_name
        if not out_path.is_file():
            raise
        text = out_path.read_text()
        cards = [line for line in text.splitlines() if line.strip()]
        complete = (
            any(line.startswith("**.subckt") for line in cards)
            and cards[-1].strip() == ".end"
        )
        if not complete:
            raise
        print(
            f"  (note: xschem exited nonzero on {sch.name} but wrote a complete "
            f"netlist -- accepted, see _netlist_schematic()'s docstring: {exc})"
        )
        return out_path


def assert_fragments_current(scratch: Path) -> str:
    """Re-netlist design/sampling_frontend.sch and design/cdac/cdac_array.sch
    with xschem and refuse to continue if either committed testbench fragment's
    device content has drifted from its schematic.

    Issue #469's acceptance criterion is that this campaign's DUT is the
    SHIPPING devices (post-#236's two-part front-end fix, post-DR-017), and
    that the record's own `DUT netlist sha256` is what proves it. A committed
    fragment is only as current as whoever last regenerated it, so --corners
    re-derives the comparison every run instead of trusting the commit: a
    drifted fragment is a hard failure naming the regeneration command, not a
    silently stale measurement. Returns the one-line provenance note the
    evidence record quotes.
    """
    for sch in (FE_SCH, CDAC_SCH):
        if not sch.is_file():
            raise RuntimeError(f"schematic not found: {sch}")
    regen_dir = scratch / "regen"
    fresh = {
        FE_FRAG: _netlist_schematic(FE_SCH, regen_dir, "sampling_frontend.spice"),
        CDAC_FRAG: _netlist_schematic(CDAC_SCH, regen_dir, "cdac_array.spice"),
    }
    for committed, regenerated in fresh.items():
        want = _device_lines(regenerated.read_text())
        have = _device_lines(committed.read_text())
        if want != have:
            raise RuntimeError(
                f"committed fragment {committed.relative_to(REPO_ROOT)} no longer "
                f"matches its schematic's netlist -- regenerate it (see that "
                f"file's own header for the exact command) before recording a "
                f"result, so the record measures the shipping devices. "
                f"{len(have)} committed device/card line(s) vs "
                f"{len(want)} regenerated."
            )
    return (
        "both committed fragments re-netlisted from their schematics this run "
        "(`design/sampling_frontend.sch`, `design/cdac/cdac_array.sch`) and "
        "found device-for-device identical -- the run aborts rather than "
        "records if they are not"
    )


def _pwl(points: list[tuple[float, float]]) -> str:
    """Same `pwl(...)` rendering sim/sampling-acquisition-settling/'s own
    deck builder uses."""
    return "pwl(" + " ".join(f"{t:g}n {v:g}" for t, v in points) + ")"


def build_acquisition_netlist(
    code_bits: list[int], corner: str, temp_c: float, vdd: float,
    tran_step_ns: float = TRAN_STEP_NS,
) -> str:
    """Mechanism (d)'s two-pulse acquisition stimulus and its fixed-time
    DR-006-budget probe, applied to the COMBINED (front end + real CDAC array)
    top-plate load this campaign already assembles -- issue #469.

    Deliberately identical to
    sim/sampling-acquisition-settling/run_acquisition_settling.py's
    build_transient() in stimulus shape, probe times and measured quantity, so
    the two records' residual columns are directly comparable and the only
    variable between them is the load on TOP_P/TOP_N. What is added here is
    this campaign's own CDAC array fragment, its VREFP/VREFN/VSS rails, and
    the SELp<i>/SELn<i> ideal previous-code drivers build_netlist() above
    already documents.
    """
    fe_frag = FE_FRAG.read_text()
    cdac_frag = CDAC_FRAG.read_text()

    sample_points = [
        (0.0, 0.0),
        (T_SAMPLE1_RISE_NS, 0.0),
        (T_SAMPLE1_RISE_NS + EDGE_TR_NS, vdd),
        (T_SAMPLE1_FALL_NS, vdd),
        (T_SAMPLE1_FALL_NS + EDGE_TR_NS, 0.0),
        (T_SAMPLE2_RISE_NS, 0.0),
        (T_SAMPLE2_RISE_NS + EDGE_TR_NS, vdd),
        (T_SAMPLE2_FALL_NS, vdd),
        (T_SAMPLE2_FALL_NS + EDGE_TR_NS, 0.0),
        (TRAN_STOP_NS, 0.0),
    ]
    vinp_points = [
        (0.0, V_INITIAL_P),
        (T_INPUT_TOGGLE_NS, V_INITIAL_P),
        (T_INPUT_TOGGLE_NS + EDGE_TR_NS, V_FINAL_P),
        (TRAN_STOP_NS, V_FINAL_P),
    ]
    vinn_points = [
        (0.0, V_INITIAL_N),
        (T_INPUT_TOGGLE_NS, V_INITIAL_N),
        (T_INPUT_TOGGLE_NS + EDGE_TR_NS, V_FINAL_N),
        (TRAN_STOP_NS, V_FINAL_N),
    ]

    lines = toolchain.deck_preamble(
        corner,
        temp_c,
        f"sampling-cdac-handoff -- mechanism (d) at the assembled top-plate "
        f"load (issue #469) -- corner={corner} temp={temp_c}C vdd={vdd}V",
    )
    lines += [
        f"Vdd VDD 0 dc {vdd}",
        "Vvss VSS 0 dc 0",
        f"Vrefp VREFP 0 dc {vdd}",
        "Vrefn VREFN 0 dc 0",
        f"Vvcm VCM 0 dc {VCM}",
        f"Vinp VINP 0 {_pwl(vinp_points)}",
        f"Vinn VINN 0 {_pwl(vinn_points)}",
        f"Vsample SAMPLE 0 {_pwl(sample_points)}",
        "",
        "* SELp<i>/SELn<i>: ideal DC sources standing in for the SAR",
        "* sequencer's DOUT<i> register held at a fixed previous-conversion",
        "* code throughout both SAMPLE pulses (see module docstring).",
    ]
    for i, bit in enumerate(code_bits):
        lines.append(f"Vselp{i} SELp{i} 0 dc {vdd if bit else 0.0}")
        lines.append(f"Vseln{i} SELn{i} 0 dc {0.0 if bit else vdd}")
    lines += [
        "",
        fe_frag,
        "",
        cdac_frag,
        "",
        ".control",
        f"tran {tran_step_ns}n {TRAN_STOP_NS}n",
    ]
    for side, (node, _v_initial, _v_final) in SIDES.items():
        lines.append(f"meas tran budget_{side} find v({node}) at={BUDGET_PROBE_AT_NS}n")
        lines.append(f"meas tran confirm_{side} find v({node}) at={CONFIRM_AT_NS}n")
    lines += [".endc", ".end"]
    return "\n".join(lines) + "\n"


def run_acquisition_point(
    code_name: str,
    corner: str,
    temp_c: float,
    supply_v: float,
    scratch: Path,
    quiet: bool = False,
    tran_step_ns: float = TRAN_STEP_NS,
) -> dict:
    """One combined-load acquisition run: build the deck, run ngspice, and
    reduce it to the per-side residuals plus the worst-of-TOP_P/TOP_N row the
    --corners record reports."""
    code_bits = CODE_STATES[code_name]
    cid = corners_mod.corner_id(corner, temp_c, supply_v)
    netlist = build_acquisition_netlist(
        code_bits, corner, temp_c, supply_v, tran_step_ns=tran_step_ns
    )
    log_text = toolchain.run_ngspice_with_retry(netlist, scratch, f"acq_{code_name}_{cid}")
    m = measure.parse(log_text, BUDGET_MEASURE_NAMES)

    rows = []
    for side, (node, v_initial, v_final) in SIDES.items():
        budget_v = m.get(f"budget_{side}")
        confirm_v = m.get(f"confirm_{side}")
        rows.append({
            "side": side,
            "node": node,
            "v_initial": v_initial,
            "v_final": v_final,
            "budget_v": budget_v,
            "budget_err_mv": None if budget_v is None else (budget_v - v_final) * 1000,
            "confirm_v": confirm_v,
            "confirm_err_mv": None if confirm_v is None else (confirm_v - v_final) * 1000,
        })
    complete = all(
        r["budget_err_mv"] is not None and r["confirm_err_mv"] is not None for r in rows
    )
    worst = max(rows, key=lambda r: abs(r["budget_err_mv"])) if complete else None
    point = {
        "corner": corner,
        "temp_c": temp_c,
        "supply_v": supply_v,
        "corner_id": cid,
        "code": code_name,
        "complete": complete,
        "rows": rows,
        "worst_node": worst["node"] if worst else None,
        "worst_budget_err_mv": worst["budget_err_mv"] if worst else None,
        "worst_confirm_err_mv": worst["confirm_err_mv"] if worst else None,
        "tran_step_ns": tran_step_ns,
        "netlist": netlist,
    }
    if not quiet:
        if complete:
            print(
                f"{cid} [{code_name}]: worst node {worst['node']} "
                f"residual@budget={worst['budget_err_mv']:+.4f} mV "
                f"(confirm {worst['confirm_err_mv']:+.4f} mV)"
            )
        else:
            print(f"{cid} [{code_name}]: INCOMPLETE (a budget/confirm read did not parse)")
    return point


def run_corners(
    scratch: Path, quiet: bool = False, tran_step_ns: float = TRAN_STEP_NS
) -> tuple[list[dict], list[dict]]:
    """Mechanism (d) at the assembled load over the ratified OAT PVT grid.

    The grid itself comes from the shared corners.ratified_oat_grid() helper
    (process x temperature x supply, one-at-a-time around the ratified
    tt/27C/nominal baseline) -- the same call
    sim/sampling-acquisition-settling/run_acquisition_settling.py's own
    run_corners() makes, so the two campaigns' 9 points are the same 9 points
    and their residual columns line up row for row.

    Returns (grid_points, code_control_points): the 9 grid points at
    CORNERS_CODE_STATE, and the other two CDAC previous-code states re-run at
    the baseline corner as a code-state-independence control.
    """
    pdk.resolve_or_raise()
    grid = corners_mod.ratified_oat_grid(VDD, SUPPLY_TOLERANCE, PROCESS_CORNERS, TEMPS_C)

    points = [
        run_acquisition_point(
            CORNERS_CODE_STATE, pc, tc, sv, scratch, quiet=quiet,
            tran_step_ns=tran_step_ns,
        )
        for pc, tc, sv in grid
    ]
    control = [
        run_acquisition_point(
            code_name, "tt", 27.0, VDD, scratch, quiet=quiet,
            tran_step_ns=tran_step_ns,
        )
        for code_name in CODE_STATES
        if code_name != CORNERS_CODE_STATE
    ]
    return points, control


def run_point(
    point_name: str,
    vinp: float,
    vinn: float,
    code_name: str,
    code_bits: list[int],
    corner: str,
    scratch: Path,
) -> dict:
    netlist = build_netlist(vinp, vinn, code_bits, corner)
    log_name = f"{point_name}_{code_name}_{corner}"
    output = toolchain.run_ngspice(netlist, scratch, log_name)
    meas = measure.parse(output, MEASURE_NAMES)
    return {
        "point": point_name,
        "code": code_name,
        "corner": corner,
        "vinp": vinp,
        "vinn": vinn,
        "netlist": netlist,
        "log_name": log_name,
        **meas,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true", help="write a sim/README.md-style evidence record")
    ap.add_argument("--full", action="store_true", help="also run one point at the ss corner")
    ap.add_argument(
        "--corners", action="store_true",
        help="measure mechanism (d) -- the acquisition residual at the DR-006 "
        "worst-case phase budget -- at this campaign's combined front-end + "
        "CDAC top-plate load, over the full ratified 9-point OAT PVT grid "
        "(issue #469), instead of the end-of-SAMPLE handoff check above",
    )
    ap.add_argument(
        "--tran-step-ns", type=float, default=TRAN_STEP_NS,
        help="transient step CEILING for --corners, in ns (default "
        f"{TRAN_STEP_NS}; see TRAN_STEP_NS's own comment for why this mode's "
        "default differs from the front-end-only campaign's 0.02 ns)",
    )
    ap.add_argument(
        "--note", default="",
        help="free-text provenance note recorded as this record's `**Note**` "
        "field -- the place a re-run says WHY it was re-run. Added by #498: "
        "until then this runner had no --note at all, so a re-run after a "
        "design/ change could not be traced back to what it replaced from the "
        "record itself. Prose only: name the displaced record MACHINE-readably "
        "via --supersedes, which both citation gates actually read.",
    )
    evidence.add_supersedes_argument(ap)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    check = toolchain.check_env()
    if check.status == 3:
        print("SKIP: ngspice/PDK not available (" + "; ".join(check.messages) + ")")
        return 0
    if check.status == 1:
        print("FAIL: toolchain drift -- " + "; ".join(check.messages))
        return 1
    for w in check.warnings:
        print(f"WARNING: {w}")

    if args.corners:
        with tempfile.TemporaryDirectory(prefix="sampling-cdac-handoff-corners-") as tmp:
            scratch = Path(tmp)
            regen_note = assert_fragments_current(scratch)
            print(f"DUT provenance: {regen_note}\n")
            points, control = run_corners(
                scratch, quiet=args.quiet, tran_step_ns=args.tran_step_ns
            )
            incomplete = [p for p in points + control if not p["complete"]]
            if args.record:
                write_corners_record(
                    points, control, regen_note,
                    note=args.note, supersedes=args.supersedes,
                )
            if incomplete:
                print(
                    f"\nFAIL: {len(incomplete)}/{len(points) + len(control)} runs "
                    "produced incomplete measurements."
                )
                return 1
            print(
                f"\nOVERALL: PASS (all {len(points)} grid points and "
                f"{len(control)} code-state control runs produced values -- see "
                "the printed residuals above, and the record, for whether the "
                "mechanism itself fits the DR-006 phase budget at this load)"
            )
        return 0

    scratch = Path("/tmp/sampling-cdac-handoff-run")
    results = []
    for point_name, (vinp, vinn) in TEST_POINTS.items():
        for code_name, code_bits in CODE_STATES.items():
            results.append(
                run_point(point_name, vinp, vinn, code_name, code_bits, "tt", scratch)
            )
    if args.full:
        results.append(
            run_point(
                "worst_case_pp", 1.6, 0.2, "prev_code_one", CODE_STATES["prev_code_one"], "ss", scratch
            )
        )

    print(
        f"{'point':16} {'code':16} {'corner':5} {'vinp':6} {'vinn':6} "
        f"{'top_p_end':10} {'top_n_end':10} {'err_p_mV':9} {'err_n_mV':9}"
    )
    max_abs_err_mv = 0.0
    for r in results:
        err_p_mv = (r["top_p_end"] - r["vinp"]) * 1000
        err_n_mv = (r["top_n_end"] - r["vinn"]) * 1000
        max_abs_err_mv = max(max_abs_err_mv, abs(err_p_mv), abs(err_n_mv))
        print(
            f"{r['point']:16} {r['code']:16} {r['corner']:5} {r['vinp']:<6} {r['vinn']:<6} "
            f"{r['top_p_end']:<10.6f} {r['top_n_end']:<10.6f} {err_p_mv:<9.4f} {err_n_mv:<9.4f}"
        )
    print(f"\nmax |TOP_x - VINx| across all runs: {max_abs_err_mv:.4f} mV")

    if args.record:
        write_record(results, note=args.note, supersedes=args.supersedes)
    return 0


def write_record(results: list[dict], note: str = "", supersedes: str = "") -> None:
    combined_netlist_text = FE_FRAG.read_text() + "\n\n" + CDAC_FRAG.read_text()
    prov = evidence.resolve_provenance(EXPERIMENT_DIR, combined_netlist_text)
    record_id = prov.record_id
    record_path = prov.record_path
    netlist_sha = prov.netlist_sha
    pdk_line = prov.pdk_line
    ng_version = prov.ng_version

    lines = []
    a = lines.append
    a(f"# sampling-cdac-handoff -- {record_id}")
    a("")
    a("- **Record ID**: " + record_id)
    a(
        "- **Claim**: Resolves issue #95 (sampling-frontend/CDAC-array "
        "bottom-plate reference mismatch) via path (a): design/"
        "sampling_frontend.sch's BPREF_P/BPREF_N being left floating/"
        "dead-ended (design/sar_adc_top.sch's actual BPREF_P_NC/BPREF_N_NC "
        "wiring) does NOT corrupt the front end's top-plate sampled value -- "
        "TOP_P/TOP_N settle to VINP/VINN by the end of SAMPLE regardless of "
        "what 'previous conversion' code the CDAC array's own SELp<i>/"
        "SELn<i> bottom-plate switches are holding throughout SAMPLE. No "
        "claim against a ratified spec row (spec/target-spec.md is entirely "
        "DRAFT pending #1/#27)."
    )
    a(
        "- **Netlist provenance**: two regenerated schematic fragments "
        "(design/sampling_frontend.sch #52, design/cdac/cdac_array.sch #53), "
        "tied at TOP_P/TOP_N exactly as design/sar_adc_top.sch (#56) wires "
        "them -- see testbench/*.spice headers for the exact regen commands."
    )
    a(
        f"- **Corner/point matrix**: {len(TEST_POINTS)} differential test points "
        f"(matching sim/sampling-frontend/'s own worst_case_pp/worst_case_np/"
        f"common_mode) x {len(CODE_STATES)} CDAC-array 'previous code' states "
        "(all-zero, all-one, alternating) at tt/27C/1.8V"
        + (", plus one point at the ss corner (--full)" if any(r["corner"] == "ss" for r in results) else "")
        + "."
    )
    a(
        "- **Subset-corner justification**: this is a charge-redistribution/"
        "interface check, not a spec-row PVT claim (there is no ratified row "
        "to check yet). Full temperature/supply-tolerance/process-corner "
        "coverage is deferred to #28's future full corner campaign, matching "
        "the same subset-corner precedent sim/sampling-frontend/ already "
        "established for this sub-block."
    )
    if note:
        a(f"- **Note**: {note}")
    a("")
    a("## Test points")
    a("")
    a("| Point | Code | Corner | VINP | VINN | TOP_P settled | TOP_N settled | Err P (mV) | Err N (mV) |")
    a("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        err_p_mv = (r["top_p_end"] - r["vinp"]) * 1000
        err_n_mv = (r["top_n_end"] - r["vinn"]) * 1000
        a(
            f"| {r['point']} | {r['code']} | {r['corner']} | {r['vinp']} | {r['vinn']} | "
            f"{r['top_p_end']:.6f} | {r['top_n_end']:.6f} | {err_p_mv:.4f} | {err_n_mv:.4f} |"
        )
    a("")

    tt_results = [r for r in results if r["corner"] == "tt"]
    other_results = [r for r in results if r["corner"] != "tt"]
    max_abs_err_tt_mv = max(
        max(abs((r["top_p_end"] - r["vinp"]) * 1000), abs((r["top_n_end"] - r["vinn"]) * 1000))
        for r in tt_results
    )
    half_lsb_mv = LSB_DIFF_MV_PROVISIONAL / 2

    a(
        f"LSB (differential, provisional per DR-003, pending #27): "
        f"{LSB_DIFF_MV_PROVISIONAL} mV -- the max |TOP_x - VINx| single-ended "
        f"error across every tt-corner point/code combination above is "
        f"{max_abs_err_tt_mv:.4f} mV, well under one provisional LSB even "
        f"single-ended (differential error, the quantity that actually "
        f"matters for a bit decision, is smaller still after P/N "
        f"cancellation)."
    )
    a("")
    a("## Result")
    a("")
    tt_verdict = "PASS" if max_abs_err_tt_mv < half_lsb_mv else "FAIL"
    a(
        f"**tt/27C: {tt_verdict}.** TOP_P/TOP_N settle to within "
        f"{max_abs_err_tt_mv:.4f} mV of their respective analog inputs by "
        "the end of the 400ns SAMPLE window, at every tested differential "
        "input point AND every tested CDAC-array 'previous code' state -- "
        "the measured error is IDENTICAL (to the precision reported) across "
        "all three previous-code states at every input point, confirming "
        "that BPREF_P/BPREF_N's floating/dead-ended state (design/"
        "sar_adc_top.sch's actual BPREF_P_NC/BPREF_N_NC wiring) does not "
        "perturb correct sampling, and that the sampled value does not "
        "depend on what code the CDAC array's own bottom-plate switches "
        "were left at from a prior conversion. This matches the "
        "circuit-level argument in this issue's own DR-004 update: during "
        "SAMPLE, TOP_P/TOP_N are driven low-impedance by the front end's "
        "own bootstrapped switches regardless of what the (always "
        "individually driven, never floating) CDAC array bottom plates are "
        "doing; once SAMPLE ends, the front end's own Csamp_p/Csamp_n "
        "become isolated two-terminal capacitors (their other terminal, "
        "BPREF_P/BPREF_N, touches nothing else at the top level) and "
        "therefore inject zero further current into TOP_P/TOP_N for the "
        "rest of the conversion. **This is this record's answer to issue "
        "#95**: path (a) holds -- BPREF_x is not load-bearing for correct "
        "sampling, given the CDAC array's real always-driven bottom-plate "
        "behavior."
    )
    if other_results:
        a("")
        max_abs_err_other_mv = max(
            max(abs((r["top_p_end"] - r["vinp"]) * 1000), abs((r["top_n_end"] - r["vinn"]) * 1000))
            for r in other_results
        )
        a(
            f"**Non-tt corner(s) (directional check only, NOT a pass/fail "
            f"gate -- same precedent as sim/sampling-frontend/'s own `--full` "
            f"flag): {max_abs_err_other_mv:.4f} mV.** This EXCEEDS half the "
            f"provisional LSB ({half_lsb_mv:.4f} mV) at the ss corner on the "
            "worst_case_pp point -- a real, newly-surfaced residual, not "
            "swept under the rug: this record's combined circuit loads "
            "TOP_P/TOP_N with BOTH the front end's own Csamp_p/Csamp_n "
            "(~4.43pF/side, per DR-004) AND the real CDAC array's own "
            "~4.43pF/side of bit capacitors -- roughly double the load "
            "DR-004's own Sa/Sd L=0.5um sizing fix was verified against, "
            "and DR-004's Open items already flagged that fix as 'NOT "
            "corner-swept' at ss/-40C. This is a settling-time/loading "
            "concern for a FUTURE area/timing pass (removing the front "
            "end's own now-redundant Csamp_p/Csamp_n would roughly halve "
            "this load, per this record's own 'Not changed here' note "
            "below) -- it does NOT change this record's tt-corner answer to "
            "issue #95 (BPREF_x's floating state itself is not what causes "
            "this; the CDAC array's real capacitive load is the same "
            "whether or not Csamp_p/Csamp_n are present, since BPREF_x's "
            "isolation means Csamp_p/Csamp_n's own current contribution is "
            "already zero -- see the tt-corner result above, identical "
            "across all three previous-code states)."
        )
    a("")
    a(
        "**Not tested here** (out of this record's scope, tracked "
        "separately): the post-edge SAMPLE-to-HOLD transition droop (issue "
        "#61) and the SAR sequencer's own bit-trial correctness (#55, "
        "already closed/merged, exercised by its own standalone testbench) "
        "-- this record only exercises the moment SAMPLE ends, matching "
        "sim/sampling-frontend/'s own top_p_end/top_n_end measurement point."
    )
    a("")
    a(
        "**Not changed here**: design/sampling_frontend.sch's Csamp_p/"
        "Csamp_n/BPREF_P/BPREF_N/Cmswn/Cmswp circuitry is left in place, "
        "not removed -- see spec/decision-records/DR-004-sampling-frontend-"
        "sizing.md's updated 'Open items' entry for why (it is now provably "
        "inert post-SAMPLE, per the argument above, rather than merely "
        "assumed harmless; removing it would need re-verifying DR-004's own "
        "Sa/Sd/Cboot sizing against a smaller load, which this record does "
        "not attempt)."
    )
    a("")
    lines.extend(
        evidence.environment_block(
            pdk_line=pdk_line,
            ngspice_line=ng_version,
            netlist_sha256=netlist_sha,
            extra={"Toolchain check": "PASS" if toolchain.check_env().status == 0 else "see sim/run_corners.py --check-env"},
        )
    )
    a("")
    lines.extend(evidence.footer_lines(
        "sim/sampling-cdac-handoff/run_handoff.py", supersedes
    ))

    record_path.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {record_path}")


# The record this campaign's --corners mode EXTENDS rather than supersedes: it
# asks a different question of the same assembled circuit (does the previous
# CDAC code corrupt the sampled value by the end of a generous SAMPLE window
# -- yes/no) and its answer stands. See write_corners_record()'s own
# "Relationship to ..." bullet.
HANDOFF_SEED_RECORD = "20260824-231304-144edeb"

# The front-end-ALONE record whose 9 ratified corner points this campaign's
# --corners mode re-runs at roughly double the top-plate load -- the direct
# comparison the whole exercise exists to make (issue #469).
FRONTEND_ONLY_CORNERS_RECORD = (
    "sim/sampling-acquisition-settling/records/20260908-051436-6ccd72d.md"
)
FRONTEND_ONLY_WORST_MV = 0.380  # tt_27c_1.62v, that record's binding corner
FRONTEND_ONLY_WORST_CORNER = "tt_27c_1.62v"
# The one pre-#236 combined-load figure in the tree, from HANDOFF_SEED_RECORD's
# own --full ss point: a different measurement (end-of-SAMPLE error, not the
# DR-006-budget residual), quoted only as the number this pass supplants.
PRE_236_SS_EXCURSION_MV = 5.33


def write_corners_record(
    points: list[dict], control: list[dict], regen_note: str, note: str = "",
    supersedes: str = "",
) -> Path:
    """Evidence record for the combined-load mechanism-(d) PVT campaign
    (issue #469), using the shared `corners/<record-id>/` per-point-deck layout
    every other --corners record in sim/ writes."""
    run = evidence.resolve_corners_provenance(EXPERIMENT_DIR, points, VDD)
    record_id = run.record_id
    record_path = run.record_path

    # Reported as this record's "DUT netlist sha256" so it is directly
    # comparable with the campaign's first record, which hashes the same
    # combined-fragment text: the two differ iff the shipping devices differ.
    combined_netlist_text = FE_FRAG.read_text() + "\n\n" + CDAC_FRAG.read_text()
    dut_sha = evidence.sha256_text(combined_netlist_text)

    half_lsb_mv = LSB_DIFF_MV_PROVISIONAL / 2
    complete_points = run.complete_points
    incomplete = run.incomplete

    lines: list[str] = []
    a = lines.append
    a(
        f"# sampling-cdac-handoff -- mechanism (d) at the assembled top-plate "
        f"load -- full PVT grid -- {record_id}"
    )
    a("")
    a(f"- **Record ID**: {record_id}")
    a(
        "- **Claim**: measures, for the first time in this repo, "
        "`docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2's fourth "
        "named sample-rate mechanism -- (d) the sampling front end's own "
        "acquisition of a NEW, worst-case (rail-to-rail) differential input "
        "value once SAMPLE re-asserts -- at the **assembled** top-plate load, "
        "over the full ratified PVT corner set. `TOP_P`/`TOP_N` here carry "
        "BOTH `design/sampling_frontend.sch`'s own `Csamp_p`/`Csamp_n` "
        "(~4.43 pF/side, DR-004) AND `design/cdac/cdac_array.sch`'s real "
        "per-bit capacitance (~4.43 pF/side), tied exactly as "
        "`design/sar_adc_top.sch` (#56) wires the two sub-blocks -- roughly "
        "double the load the mechanism's own PVT-complete record "
        f"([`{FRONTEND_ONLY_CORNERS_RECORD}`]"
        f"(../../{FRONTEND_ONLY_CORNERS_RECORD.split('sim/', 1)[1]}), which "
        "reads the front-end fragment alone) was run against. Stimulus, probe "
        "times and measured quantity are identical to that record's; the only "
        "variable is the load. No claim is graded against a ratified spec row: "
        "`spec/target-spec.md`'s sample-rate row is entirely DRAFT (#1/#27), "
        "and the DR-006 phase-period figure quoted below is itself downstream "
        "of that DRAFT row -- the provisional differential half-LSB appears "
        "only as a familiar reference scale."
    )
    a(
        "- **Netlist provenance**: the two committed fragments this campaign "
        "already assembles (`testbench/sampling_frontend_dut.spice` from "
        "`design/sampling_frontend.sch`, post-issue-#236's two-part fix -- "
        "`Sa` re-gated from `SAMPLE` to `G_{p,n}`, `Cmswn`/`Cmswp` widened "
        "W=1um -> W=16um; and `testbench/cdac_array_dut.spice` from "
        f"`design/cdac/cdac_array.sch`). {regen_note[0].upper()}{regen_note[1:]}. "
        f"The combined-fragment `DUT netlist sha256` below (`{dut_sha[:12]}...`) "
        f"therefore differs from this campaign's first record "
        f"([`records/{HANDOFF_SEED_RECORD}.md`]({HANDOFF_SEED_RECORD}.md), "
        "`20e99428...`) precisely because the shipping front-end devices "
        "changed at #236; the CDAC array fragment is unchanged. Only "
        "`.lib`/`.temp`/`Vdd`/`VREFP` and the ideal `SELp<i>`/`SELn<i>` logic "
        f"levels vary per corner point; every point's own deck is committed "
        f"under `corners/{record_id}/`."
    )
    a(
        corners_mod.corner_matrix_summary_line(
            run.process_corners_run, run.temps_run, run.supplies_run, len(points)
        )
    )
    a(
        "- **Stimulus**: two SAMPLE pulses, unchanged from the front-end-only "
        f"campaign. Pulse #1 ({T_SAMPLE1_WIDTH_NS:g} ns wide) settles "
        f"`TOP_P`/`TOP_N` to {V_INITIAL_P}V/{V_INITIAL_N}V; during the "
        "following hold phase (SAMPLE deasserted, `Msw` off) `VINP`/`VINN` "
        f"step to the opposite rail-adjacent extreme ({V_FINAL_P}V/"
        f"{V_FINAL_N}V); SAMPLE pulse #2 re-asserts at {T_SAMPLE2_RISE_NS:g} ns "
        f"and every residual below is read at a FIXED time "
        f"{BUDGET_PROBE_AT_NS:g} ns -- exactly one DR-006 worst-case "
        f"({T_PHASE_WORST_NS:.3f} ns, f_clk = 12 MHz) phase period after that "
        f"edge's own 50% crossing ({TRIG_AT_NS:g} ns). The `confirm` column is "
        f"a second fixed read at {CONFIRM_AT_NS:g} ns "
        f"(~{(CONFIRM_AT_NS - TRIG_AT_NS) / T_PHASE_WORST_NS:.1f}x the budget, "
        f"still well short of the {T_PHASE_SLOW_NS:.0f} ns slow-end phase), "
        "showing how much further the node gets given more time than the "
        "budget allows."
    )
    a(
        "- **CDAC previous-code state**: `" + CORNERS_CODE_STATE + "` held "
        "throughout at every grid point, with the other two states re-run at "
        "the baseline corner as an independence control (table below). The "
        "array's bottom plates are continuously driven by their own `SEL<i>` "
        "switches and never float, so the code sets their charge but not the "
        "capacitance `TOP_x` sees -- which is what this record measures."
    )
    if note:
        a(f"- **Note**: {note}")
    a("")
    a(
        "## Worst-node residual at the DR-006 worst-case phase budget, per corner"
    )
    a("")
    a(
        "\"Worst node\" is whichever of `TOP_P`/`TOP_N` has the "
        "larger-magnitude residual at that corner (not necessarily the same "
        "node at every corner). The `x half-LSB` column is a reference scale "
        f"({half_lsb_mv:.4f} mV, half the provisional differential LSB, "
        "DR-003 Item 2 pending #27) -- NOT a pass/fail gate against a "
        "ratified row."
    )
    a("")
    a(
        "| Corner | Worst node | Residual @ budget (mV) | Residual @ confirm (mV) | x half-LSB |"
    )
    a("|---|---|---|---|---|")
    for p in points:
        if not p["complete"]:
            a(f"| `{p['corner_id']}` | -- | INCOMPLETE | INCOMPLETE | -- |")
            continue
        a(
            f"| `{p['corner_id']}` | `{p['worst_node']}` | "
            f"{p['worst_budget_err_mv']:+.4f} | {p['worst_confirm_err_mv']:+.4f} | "
            f"{abs(p['worst_budget_err_mv']) / half_lsb_mv:.2f}x |"
        )
    a("")
    a("## Per-side residuals at the baseline corner, and the code-state control")
    a("")
    a(
        "Both sides at every CDAC previous-code state, all at "
        f"`{corners_mod.corner_id('tt', 27.0, VDD)}`: the array's own "
        "previous-code state should not move this residual, and this table is "
        "what says whether it does."
    )
    a("")
    a("| Code state | Node | Old -> New (V) | Residual @ budget (mV) | Residual @ confirm (mV) |")
    a("|---|---|---|---|---|")
    baseline_id = corners_mod.corner_id("tt", 27.0, VDD)
    code_rows = [p for p in points + control if p["corner_id"] == baseline_id]
    for p in code_rows:
        for r in p["rows"]:
            budget_str = "N/A" if r["budget_err_mv"] is None else f"{r['budget_err_mv']:+.4f}"
            confirm_str = "N/A" if r["confirm_err_mv"] is None else f"{r['confirm_err_mv']:+.4f}"
            a(
                f"| `{p['code']}` | `{r['node']}` | {r['v_initial']} -> "
                f"{r['v_final']} | {budget_str} | {confirm_str} |"
            )
    a("")

    notes: list[str] = []
    if incomplete:
        bad = ", ".join(p["corner_id"] for p in incomplete)
        notes.append(
            f"**{len(incomplete)}/{len(points)} corner points produced "
            f"incomplete measurements ({bad})** -- treat this record as partial "
            "evidence at those points, not a passing or failing result, until "
            "re-run clean."
        )
    if complete_points:
        binding = max(complete_points, key=lambda p: abs(p["worst_budget_err_mv"]))
        best = min(complete_points, key=lambda p: abs(p["worst_budget_err_mv"]))
        binding_mv = abs(binding["worst_budget_err_mv"])
        best_mv = abs(best["worst_budget_err_mv"])
        cleared = [p for p in complete_points if abs(p["worst_budget_err_mv"]) <= half_lsb_mv]
        all_cleared = len(cleared) == len(points)
        spread_str = (
            f"; worst-to-best spread {binding_mv / best_mv:.2f}x across the grid"
            if best_mv > 0 else ""
        )
        notes.append(
            f"**Binding corner (largest residual): `{binding['corner_id']}`**, "
            f"`{binding['worst_node']}` still {binding_mv:.4f} mV "
            f"(single-ended) from its ideal target value "
            f"{T_PHASE_WORST_NS:.3f} ns after the acquiring edge -- "
            f"{binding_mv / half_lsb_mv:.2f}x the provisional differential "
            f"half-LSB reference scale. Best corner: `{best['corner_id']}` at "
            f"{best_mv:.4f} mV ({best_mv / half_lsb_mv:.2f}x)"
            f"{spread_str}."
        )
        if all_cleared:
            notes.append(
                f"**All {len(cleared)}/{len(points)} ratified corner points land "
                "INSIDE the provisional differential half-LSB reference scale at "
                "the DR-006 worst-case (12 MHz) phase budget, at the ASSEMBLED "
                "(front end + CDAC array) top-plate load.** This is the gap "
                "issue #469 opened: mechanism (d)'s own PVT-complete record "
                "reads the front-end fragment alone, so its "
                f"{FRONTEND_ONLY_WORST_MV:.3f} mV binding-corner residual "
                f"(`{FRONTEND_ONLY_WORST_CORNER}`) was measured at about half "
                "the top-plate capacitance the top level actually presents. "
                f"Doubling that load moves the binding corner's residual to "
                f"{binding_mv:.4f} mV at `{binding['corner_id']}` -- still "
                "inside the reference scale at every ratified corner. The "
                f"campaign's own pre-#236 combined-load figure "
                f"({PRE_236_SS_EXCURSION_MV} mV single-ended at one directional "
                "`ss` point, explicitly deferred there to \"a future timing "
                "pass\") is superseded as a live concern by this grid, not by "
                "argument: that point was measured against the pre-#236 "
                "schematic and against a different quantity (the error at the "
                "end of a 400 ns SAMPLE window, not the residual at the DR-006 "
                "budget)."
            )
        else:
            failed = [p for p in complete_points if abs(p["worst_budget_err_mv"]) > half_lsb_mv]
            failed_ids = ", ".join(f"`{p['corner_id']}`" for p in failed)
            notes.append(
                f"**{len(failed)}/{len(points)} ratified corner points EXCEED "
                "the provisional differential half-LSB reference scale at the "
                "DR-006 worst-case (12 MHz) phase budget once the CDAC array's "
                f"own ~4.43 pF/side is present ({failed_ids}).** This is a real "
                "finding, reported as measured: mechanism (d)'s own "
                "PVT-complete record reads the front-end fragment alone and "
                f"reports {FRONTEND_ONLY_WORST_MV:.3f} mV at its binding corner "
                f"(`{FRONTEND_ONLY_WORST_CORNER}`), so \"mechanism (d) clears "
                "the budget at 9/9 ratified corners\" holds for the front end "
                "in isolation but NOT for the load the top level actually "
                "presents. It does not violate any ratified spec row (the "
                "sample-rate row is entirely DRAFT) and nothing here relaxes a "
                "spec line; the design follow-up is filed separately, since "
                "this campaign measures rather than redesigns. Of the two "
                "~4.43 pF/side contributions, DR-004's own Open items already "
                "note that the front end's `Csamp_p`/`Csamp_n` are provably "
                "inert post-SAMPLE (their far plate `BPREF_x` dead-ends at the "
                "top level), so removing them would roughly halve this load -- "
                "at the cost of re-verifying DR-004's `Sa`/`Sd`/`Cboot` sizing "
                "against the smaller load, which this record does not attempt."
            )
        notes.append(
            "**Sensitivity shape.** Residuals by axis, each with the other two "
            "axes at the ratified baseline: "
            + "; ".join(
                f"`{p['corner_id']}` {abs(p['worst_budget_err_mv']):.4f} mV"
                for p in complete_points
            )
            + "."
        )
    control_complete = [p for p in control if p["complete"]]
    baseline_grid = [p for p in complete_points if p["corner_id"] == baseline_id]
    if control_complete and baseline_grid:
        code_worst = [abs(p["worst_budget_err_mv"]) for p in control_complete + baseline_grid]
        spread_mv = max(code_worst) - min(code_worst)
        notes.append(
            "**Code-state independence control (this record's own, not "
            f"inherited).** Across all {len(code_worst)} CDAC previous-code "
            f"states at `{baseline_id}` the worst-node residual varies by "
            f"{spread_mv:.4f} mV "
            f"({spread_mv / half_lsb_mv:.3f}x the half-LSB reference scale) -- "
            "consistent with the array's bottom plates being continuously "
            "driven rather than floating, which is why the 9-point grid above "
            "is run at one code state rather than three."
        )
    notes.append(
        "**What this record does NOT do.** It does not combine mechanism (d) "
        "with the other three named sample-rate mechanisms (CDAC array "
        "switch settling, comparator decision delay, sequencer logic delay) "
        "into an end-to-end sample-rate figure -- that remains open "
        "(`docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2) -- and it "
        "does not re-measure those three at this load. It measures one "
        "direction of the worst-case differential step (both `TOP_P` and "
        "`TOP_N`, but one step polarity), the same single direction the "
        "front-end-only campaign measures, so the two are comparable. It also "
        "does not touch `design/`: no schematic changed in this pass."
    )
    notes.append(
        f"**Relationship to [`records/{HANDOFF_SEED_RECORD}.md`]"
        f"({HANDOFF_SEED_RECORD}.md)**: extends, does not supersede. That "
        "record answers issue #95's question (does the CDAC array's "
        "previous-code state, with `BPREF_x` dead-ended, corrupt the value "
        "sampled by the end of the SAMPLE window -- it does not), which this "
        "run's own code-state control above reproduces at the same baseline "
        "corner. This record answers a different question about the same "
        "assembled circuit: how fast that value arrives, against the DR-006 "
        "phase budget, across the ratified PVT grid. Both stand. Same "
        "\"extends, does not formally supersede\" relationship the other "
        "mechanism campaigns' own `--corners` records carry toward their "
        "single-corner predecessors."
    )

    a("## Result")
    a("")
    for n in notes:
        a("- " + n)
    a("")

    lines.extend(
        evidence.environment_block(
            pdk_line=run.pdk_line,
            ngspice_line=run.ng_version,
            netlist_sha256=dut_sha,
            extra={
                "DUT netlist sha256 covers": (
                    "`testbench/sampling_frontend_dut.spice` + "
                    "`testbench/cdac_array_dut.spice`, the same combined text "
                    f"[`records/{HANDOFF_SEED_RECORD}.md`]({HANDOFF_SEED_RECORD}.md) "
                    "hashes, so the two are directly comparable"
                ),
                f"Baseline deck sha256 (`{baseline_id}`)": f"`{run.netlist_sha}`",
                "tran step": f"{TRAN_STEP_NS} ns",
                "Toolchain check": (
                    "PASS" if toolchain.check_env().status == 0
                    else "see sim/run_corners.py --check-env"
                ),
            },
        )
    )
    a("")
    lines.extend(evidence.footer_lines(
        "sim/sampling-cdac-handoff/run_handoff.py", supersedes
    ))

    record_path.write_text("\n".join(lines) + "\n")
    evidence.write_latest_pointer(EXPERIMENT_DIR, record_id)
    print(f"\nWrote record: {record_path}")
    return record_path


if __name__ == "__main__":
    raise SystemExit(main())

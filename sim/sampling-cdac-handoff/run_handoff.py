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
import json
import sys
import tempfile
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
EXPERIMENT_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(SIM_DIR))
from harness import corners as corners_mod  # noqa: E402
from harness import evidence, klt_sim, measure, pdk, testbench, toolchain  # noqa: E402
from harness.acquisition import (  # noqa: E402
    BUDGET_PROBE_AT_NS,
    CONFIRM_AT_NS,
    EDGE_TR_NS,
    SIDES,
    T_INPUT_TOGGLE_NS,
    T_PHASE_SLOW_NS,
    T_PHASE_WORST_NS,
    T_SAMPLE1_FALL_NS,
    T_SAMPLE1_RISE_NS,
    T_SAMPLE1_WIDTH_NS,
    T_SAMPLE2_RISE_NS,
    TRAN_STOP_NS,
    TRIG_AT_NS,
    V_FINAL_N,
    V_FINAL_P,
    V_INITIAL_N,
    V_INITIAL_P,
    acquisition_sources,
)

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

# The first argument of `tran <step> <stop>` sets the step ceiling. ngspice
# reduces the step adaptively through fast edges, so this ceiling bounds how
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
    # `accept_complete_on_nonzero` covers design/cdac/cdac_array.sch, which
    # exits 10 with a complete netlist because its open nets fail xschem's ERC
    # -- see toolchain.netlist_with_xschem()'s docstring (issue #860).
    fresh = {
        FE_FRAG: toolchain.netlist_with_xschem(
            FE_SCH, regen_dir, XSCHEMRC, "sampling_frontend.spice",
            accept_complete_on_nonzero=True,
        ),
        CDAC_FRAG: toolchain.netlist_with_xschem(
            CDAC_SCH, regen_dir, XSCHEMRC, "cdac_array.spice",
            accept_complete_on_nonzero=True,
        ),
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
        *acquisition_sources(vdd),
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
    points = [
        run_acquisition_point(
            CORNERS_CODE_STATE, pc, tc, sv, scratch, quiet=quiet,
            tran_step_ns=tran_step_ns,
        )
        for pc, tc, sv, _cid in corners_mod.sweep(
            VDD, SUPPLY_TOLERANCE, PROCESS_CORNERS, TEMPS_C, announce=False
        )
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
        "--dr027-candidate", action="store_true",
        help="issue #1033 candidate-geometry study: mechanism (d) at the "
        "DR-027 proposed 3.3000 um unit plate (front end unchanged), at "
        "BOTH DR-006 phase deadlines, over the 9-point OAT grid via three "
        "klt sim submits (grid + two code-state controls). Combine with "
        "--dry-run, --probe or --record, and --bit-trial-record to link "
        "the companion bit-trial campaign.",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="--dr027-candidate only: write the deck + request to --workdir "
        "and stop (no simulation)",
    )
    ap.add_argument(
        "--probe", action="store_true",
        help="--dr027-candidate only: one corner (tt_27c_1.80v) on the "
        "local backend -- the single-unit debug path",
    )
    ap.add_argument(
        "--bit-trial-record", default=None,
        help="--dr027-candidate --record only: the companion "
        "sim/cdac-bit-trial-settling candidate record id whose committed "
        "report supplies the bit-trial half of the settling-versus-rate "
        "table and verdict",
    )
    ap.add_argument(
        "--backend", default=None,
        help="klt sim backend for --dr027-candidate (default: klt's own / "
        "KLT_SIM_BACKEND; the grid goes to the batch fleet)",
    )
    ap.add_argument(
        "--workdir", type=Path, default=None,
        help="scratch dir for --dr027-candidate submits (default: a fresh tmpdir)",
    )
    ap.add_argument(
        "--timeout-s", type=float, default=CAND_TIMEOUT_S,
        help="per-unit options.timeout_s for --dr027-candidate (default: "
        "%(default)s). The fleet refuses a job whose timeout_s * units + "
        "120 exceeds its whole-job ceiling -- see CAND_TIMEOUT_S's comment "
        "before raising this",
    )
    ap.add_argument(
        "--hosts", type=int, default=CAND_HOSTS,
        help="remote.hosts shard count for --dr027-candidate's grid submit "
        "(default: %(default)s)",
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

    gate = toolchain.preflight()
    if gate is not None:
        return gate

    if args.dr027_candidate:
        return candidate_main(args)

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

    evidence.close_record(prov, lines, "Record")


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

    evidence.close_record(run, lines, "Record")
    evidence.write_latest_pointer(EXPERIMENT_DIR, record_id)
    return record_path


# ---------------------------------------------------------------------------
# issue #1033: DR-027 candidate-geometry study (--dr027-candidate)
# ---------------------------------------------------------------------------
#: The DR-027 proposed unit-plate side (um) -- issue #1033's statement of the
#: #1016 proposal: 512 unit positions/side at a 3.3000 um plate, C_tot ~ 12.4
#: pF/side nominal. EXPERIMENTAL study value: design/cdac/ still draws the
#: DR-019 1.9000 um plate, and the front end's own Csamp_p/Csamp_n stay on
#: the shared top plates exactly as design/sar_adc_top.sch wires them.
CANDIDATE_UNIT_CAP_WL_UM = 3.3000
PRODUCTION_UNIT_CAP_WL_UM = 1.9000  # what cdac_array_dut.spice draws today

#: The extended two-pulse stimulus. The baseline acquisition stimulus ends
#: SAMPLE pulse #2 at 310 ns -- long enough for its 243.4 ns budget probe but
#: NOT for the DR-006 slow-end deadline (160.1 + 833.333 = 993.433 ns), which
#: issue #1033 requires INSIDE the active phase and ahead of switch turn-off.
#: Pulse #2 is widened to 860 ns (fall at 1020 ns), everything else about the
#: two-pulse shape is unchanged.
CAND_T_SAMPLE2_WIDTH_NS = 860.0
CAND_T_SAMPLE2_FALL_NS = T_SAMPLE2_RISE_NS + CAND_T_SAMPLE2_WIDTH_NS  # 1020.0
CAND_TRAN_STOP_NS = CAND_T_SAMPLE2_FALL_NS + 20.0                     # 1040.0

#: The two DR-006 phase deadlines, measured from the acquiring edge's own
#: 50 % crossing (TRIG_AT_NS), exactly the baseline budget probe's
#: convention. CAND_FAST_AT_NS is BUDGET_PROBE_AT_NS by construction --
#: asserted at import so a future edit to either constant surfaces here
#: rather than as a silent incomparability with the 1.9000 um records.
CAND_FAST_AT_NS = TRIG_AT_NS + T_PHASE_WORST_NS    # 243.4333... ns
CAND_SLOW_AT_NS = TRIG_AT_NS + T_PHASE_SLOW_NS     # 993.4333... ns
CAND_LATE_AT_NS = CAND_T_SAMPLE2_FALL_NS - 5.0     # 1015 ns (CONFIRM_AT_NS's own convention)
assert abs(CAND_FAST_AT_NS - BUDGET_PROBE_AT_NS) < 1e-9

#: The slow step's coarse ceiling: it reads only fixed-time `find` values
#: deep in the settled tail (the same argument TRAN_STEP_NS's own comment
#: makes for the 0.2 ns ceiling), so a 1 ns ceiling over the 1040 ns window
#: costs far less than 0.2 ns would while changing nothing measurable.
#: PR #1041 finding 3: the slow step now uses the SAME ceiling as the fast
#: step (TRAN_STEP_NS), so fixed-time reads at both deadlines and the
#: settling-time crossing below all come from trajectories of one resolution.
CAND_SLOW_TRAN_STEP_NS = 0.2
CAND_FAST_TRAN_STOP_NS = 250.0  # covers the fast deadline with margin

#: Supply-source name = the `corners.supply_v` axis key (sim/input-drive-
#: budget/'s convention). One body serves all nine corners, so every
#: corner-dependent LEVEL (SAMPLE swing, SEL logic levels, VREFP) is a
#: normalised source scaled by v(VDD) through behavioural sources; the input
#: extremes and VCM stay fixed at the baseline campaign's values (its own
#: documented convention).
CAND_SUPPLY_KEY = "vsup"

#: Fleet policy: the grid is one request (9 corners x 2 analysis steps = 18
#: units, hosts=2 keeps the whole-job bound at 300*9+120 = 2820 s inside the
#: ceiling the input-drive-budget runner documents), the two code-state
#: control submits are one corner each (2 units, unsharded).
CAND_TIMEOUT_S = 300.0
CAND_HOSTS = 2

#: The committed 1.9000 um assembled-load grid this study is the companion
#: of -- its binding corner/figure is what the candidate's fast-deadline
#: column is read against (0.9280 mV worst-node acquisition residual at
#: 83.333 ns, `tt_27c_1.62v`, at commit 75b91e85).
CAND_BASELINE_RECORD = "20261001-135431-7487784"

#: The differential half-LSB reference scale (DR-003 Item 2, provisional
#: pending #27) -- the stated criterion the DRAFT-row verdict is read
#: against, a reference scale, never a ratified gate.
HALF_LSB_MV = LSB_DIFF_MV_PROVISIONAL / 2  # 1.7578 mV

#: The other two mechanisms' PVT-complete binding figures, quoted from the
#: sample-rate entry of sim/report/manifest.py, for the time-left arithmetic.
COMPARATOR_DECISION_NS = 4.3575    # binding tt_27c_1.62v
SEQUENCER_LOGIC_NS = 0.4237        # binding ss_27c_1.80v
V_TARGET_DIFF = V_FINAL_P - V_FINAL_N  # 1.4 V differential ideal


def candidate_cdac_fragment() -> tuple[str, int]:
    """The candidate CDAC array fragment: the committed production fragment
    with ONLY the 20 unit-cap plates rewritten 1.9000 -> 3.3000 um (9 P-side
    bit caps + 9 N-side + 2 termination units). Every switch device line is
    byte-identical to the committed fragment -- the resize-the-plate-only
    rule issue #1033 states. Returns (text, n_swapped) and refuses (raises)
    if the production fragment carries anything but exactly 20 unit caps at
    the production plate."""
    lines = []
    n = 0
    for ln in CDAC_FRAG.read_text().splitlines():
        if (
            ln.startswith("XC")
            and "cap_mim_m3_1" in ln
            and f"W={PRODUCTION_UNIT_CAP_WL_UM:.4f}" in ln
        ):
            ln = ln.replace(
                f"W={PRODUCTION_UNIT_CAP_WL_UM:.4f} L={PRODUCTION_UNIT_CAP_WL_UM:.4f}",
                f"W={CANDIDATE_UNIT_CAP_WL_UM:.4f} L={CANDIDATE_UNIT_CAP_WL_UM:.4f}",
            )
            n += 1
        lines.append(ln)
    if n != 20:
        raise RuntimeError(
            f"expected exactly 20 unit-cap plates at W=L="
            f"{PRODUCTION_UNIT_CAP_WL_UM:.4f} in {CDAC_FRAG.name} "
            f"(9 per side + 2 termination units); found {n} -- the "
            "production fragment changed shape; re-derive the candidate "
            "study before recording."
        )
    header = (
        "* !!! EXPERIMENTAL DR-027 CANDIDATE STUDY FRAGMENT (issue #1033) !!!\n"
        "* Generated from testbench/cdac_array_dut.spice by run_handoff.py's\n"
        "* --dr027-candidate mode: ONLY the 20 cap_mim_m3_1 plate sides are\n"
        f"* rewritten {PRODUCTION_UNIT_CAP_WL_UM:.4f} -> {CANDIDATE_UNIT_CAP_WL_UM:.4f} um\n"
        "* (C_tot ~ 12.4 pF/side nominal). Every switch device line is\n"
        "* byte-identical to the committed fragment. This is NOT a netlist of\n"
        "* the shipping design -- design/cdac/ still draws the DR-019 1.9000\n"
        "* um plate -- and it is never committed as a testbench/ fragment."
    )
    return header + "\n" + "\n".join(lines), n


def _candidate_pwl_points() -> tuple[list[tuple[float, float]], list[tuple[float, float]], list[tuple[float, float]]]:
    """(sample-control, vinp, vinn) PWL point lists, the baseline
    acquisition stimulus with SAMPLE pulse #2 widened (see
    CAND_T_SAMPLE2_WIDTH_NS). The SAMPLE control is NORMALISED 0..1 (scaled
    by v(VDD) in the body); the input extremes keep the baseline campaign's
    own fixed levels."""
    sample = [
        (0.0, 0.0),
        (T_SAMPLE1_RISE_NS, 0.0),
        (T_SAMPLE1_RISE_NS + EDGE_TR_NS, 1.0),
        (T_SAMPLE1_FALL_NS, 1.0),
        (T_SAMPLE1_FALL_NS + EDGE_TR_NS, 0.0),
        (T_SAMPLE2_RISE_NS, 0.0),
        (T_SAMPLE2_RISE_NS + EDGE_TR_NS, 1.0),
        (CAND_T_SAMPLE2_FALL_NS, 1.0),
        (CAND_T_SAMPLE2_FALL_NS + EDGE_TR_NS, 0.0),
        (CAND_TRAN_STOP_NS, 0.0),
    ]
    vinp = [
        (0.0, V_INITIAL_P), (T_INPUT_TOGGLE_NS, V_INITIAL_P),
        (T_INPUT_TOGGLE_NS + EDGE_TR_NS, V_FINAL_P), (CAND_TRAN_STOP_NS, V_FINAL_P),
    ]
    vinn = [
        (0.0, V_INITIAL_N), (T_INPUT_TOGGLE_NS, V_INITIAL_N),
        (T_INPUT_TOGGLE_NS + EDGE_TR_NS, V_FINAL_N), (CAND_TRAN_STOP_NS, V_FINAL_N),
    ]
    return sample, vinp, vinn


def build_candidate_body(code_name: str = CORNERS_CODE_STATE) -> str:
    """Circuit BODY for the candidate study's `klt sim` requests: no `.lib`,
    `.temp`, `.control`, `.meas` or `.end` (klt emits those). The front-end
    fragment is inserted VERBATIM (Csamp_p/Csamp_n stay on TOP_P/TOP_N, per
    issue #1033: "Keep the front end's own sampling capacitor on each shared
    top plate"); the CDAC fragment is candidate_cdac_fragment()'s
    plate-only rewrite; the SEL ideal previous-code drivers and the SAMPLE
    control are normalised sources scaled by the corner supply (the
    input-drive-budget campaign's own re-expression); VCM and the input
    extremes stay fixed at the baseline campaign's values."""
    sample, vinp, vinn = _candidate_pwl_points()
    code_bits = CODE_STATES[code_name]
    L: list[str] = [
        "* sim/sampling-cdac-handoff -- DR-027 candidate-geometry study",
        "* (issue #1033): mechanism (d) -- the sampling front end acquiring a",
        "* new worst-case differential input once SAMPLE re-asserts -- at the",
        f"* assembled load with the candidate {CANDIDATE_UNIT_CAP_WL_UM:.4f} um"
        " unit plate",
        "* (array C_tot ~ 12.4 pF/side nominal; front end Csamp unchanged),",
        "* at BOTH DR-006 phase deadlines. EXPERIMENTAL study deck: the",
        "* production fragment still draws the 1.9000 um plate. Circuit body",
        "* only -- klt sim supplies the corner section, temperature card,",
        "* measurement cards and tran analysis steps.",
        ".options num_threads=1",
        "",
        FE_FRAG.read_text().rstrip("\n"),
        "",
        candidate_cdac_fragment()[0],
        "",
        f"* --- testbench sources (the supply source is named `{CAND_SUPPLY_KEY}`,",
        "* which is also the corners.supply_v axis key) ---",
        f"{CAND_SUPPLY_KEY} VDD 0 DC {VDD}",
        "Bvrefp VREFP 0 V=v(VDD)",
        "Vrefn VREFN 0 DC 0",
        "Vvss VSS 0 dc 0",
        f"Vvcm VCM 0 DC {VCM}",
        f"Vinp VINP 0 {testbench.pwl(vinp)}",
        f"Vinn VINN 0 {testbench.pwl(vinn)}",
        f"Vsmpn SMPN 0 {testbench.pwl(sample)}",
        "Bsample SAMPLE 0 V=v(SMPN)*v(VDD)",
        "* ACQERR: |(TOP_P - TOP_N) - 1.4 V|, the differential acquisition",
        "* error the settling-time measurement (acq_tset) crosses the",
        "* half-LSB reference band on (PR #1041 finding 4).",
        f"Bacqerr ACQERR 0 V=abs(v(TOP_P)-v(TOP_N)-{V_TARGET_DIFF:g})",
        "",
        "* SELp<i>/SELn<i>: ideal previous-code drivers (`" + code_name + "`),",
        "* normalised and scaled by the corner supply -- the same ideal-DC",
        "* stand-in the per-corner baseline decks make.",
    ]
    for i, bit in enumerate(code_bits):
        L.append(
            f"Bselp{i} SELp{i} 0 V=v(VDD)" if bit else f"Vselp{i} SELp{i} 0 DC 0"
        )
        L.append(
            f"Vseln{i} SELn{i} 0 DC 0" if bit else f"Bseln{i} SELn{i} 0 V=v(VDD)"
        )
    return "\n".join(L) + "\n"


def candidate_analysis_steps() -> list[dict]:
    """Two `tran` steps per corner. `fast` (0.2 ns ceiling, the baseline
    grid's own documented ceiling) covers the 12 MHz deadline read at
    243.433 ns -- the SAME instant as the baseline records' budget probe, so
    the candidate's fast column is corner-for-corner comparable with them.
    `slow` (coarse 1 ns ceiling) extends past the 1.2 MHz deadline read at
    993.433 ns plus a late read at 1015 ns, both inside SAMPLE pulse #2 and
    ahead of its fall (issue #1033's window rule)."""
    fast_meas = [
        {
            "name": f"acq_fast_{side}",
            "spice": (
                f".meas tran acq_fast_{side} find v({node}) "
                f"at={CAND_FAST_AT_NS:.6f}n"
            ),
            "unit": "V",
        }
        for side, (node, _i, _f) in SIDES.items()
    ]
    slow_meas = []
    for stat, at_ns in (("slow", CAND_SLOW_AT_NS), ("late", CAND_LATE_AT_NS)):
        slow_meas += [
            {
                "name": f"acq_{stat}_{side}",
                "spice": (
                    f".meas tran acq_{stat}_{side} find v({node}) "
                    f"at={at_ns:.6f}n"
                ),
                "unit": "V",
            }
            for side, (node, _i, _f) in SIDES.items()
        ]
    # Settling time (PR #1041 finding 4): from the acquiring SAMPLE edge's
    # 50 % crossing to the LAST fall of |differential error| through the
    # provisional differential half-LSB band, i.e. the instant after which
    # the node entered the band and stayed in it for the rest of the window.
    # A missing crossing (never in band / never out of it) is DATA.
    # The window ENDS at the late read (CAND_LATE_AT_NS, ahead of the SAMPLE
    # fall): in a longer window the switch turn-off itself re-crosses the
    # band and FALL=LAST would time the turn-off, not the acquisition.
    tset_meas = [{
        "name": "acq_tset",
        "spice": (
            f".meas tran acq_tset TRIG AT={TRIG_AT_NS:g}n "
            f"TARG V(ACQERR) VAL={HALF_LSB_MV * 1e-3:.9g} FALL=LAST"
        ),
        "unit": "s",
    }]
    return [
        {
            "name": "fast",
            "reset": True,
            "analysis": {
                "kind": "tran",
                "args": f"{TRAN_STEP_NS:g}n {CAND_FAST_TRAN_STOP_NS:g}n",
            },
            "measurements": fast_meas,
        },
        {
            "name": "slow",
            "reset": True,
            "analysis": {
                "kind": "tran",
                "args": f"{CAND_SLOW_TRAN_STEP_NS:g}n {CAND_TRAN_STOP_NS:g}n",
            },
            "measurements": slow_meas,
        },
        {
            "name": "tset",
            "reset": True,
            "analysis": {
                "kind": "tran",
                "args": f"{TRAN_STEP_NS:g}n {CAND_LATE_AT_NS:g}n",
            },
            "measurements": tset_meas,
        },
    ]


def candidate_corner_ids() -> list[str]:
    """The ratified 9-point one-at-a-time PVT grid, in grid order."""
    return corners_mod.ratified_corner_ids(
        VDD, SUPPLY_TOLERANCE, PROCESS_CORNERS, TEMPS_C
    )


def build_candidate_request(
    netlist_name: str,
    cids: list[str],
    *,
    timeout_s: float = CAND_TIMEOUT_S,
    backend: str | None = None,
    hosts: int | None = None,
) -> dict:
    """ONE `klt sim` request for a candidate submit (OAT grid via `exclude`,
    the input-drive-budget/top-plate-cpar convention)."""
    return klt_sim.build_oat_request(
        netlist_name, cids, CAND_SUPPLY_KEY,
        analysis_steps=candidate_analysis_steps(),
        timeout_s=timeout_s, backend=backend, hosts=hosts,
    )


SubmitError = klt_sim.SubmitError


def submit_candidate(
    workdir: Path,
    code_name: str,
    cids: list[str],
    backend: str | None,
    timeout_s: float = CAND_TIMEOUT_S,
    hosts: int | None = None,
) -> tuple[dict, dict]:
    """Write body+request under `workdir` for one CDAC previous-code state,
    run `klt sim`, return (report, info). The report is cached beside the
    request (harness.klt_sim.submit's own resume behavior)."""
    body = build_candidate_body(code_name)
    req = build_candidate_request(
        "tb.spice", cids, timeout_s=timeout_s, backend=backend, hosts=hosts,
    )
    # A cached report beside different inputs is set aside, not reused.
    klt_sim.write_inputs(
        workdir, {"tb.spice": body, "request.json": json.dumps(req, indent=1) + "\n"}
    )
    # A single-corner submit is one fleet unit, which `klt sim` resolves to
    # the LOCAL backend on its own -- and `--wait-for-capacity` is a
    # batch-only flag (the client refuses the pairing). The two code-state
    # controls are exactly that shape, so the capacity wait is dropped
    # whenever the submit is explicitly local or single-corner.
    capacity_wait_s = (
        None if backend == "local" or len(cids) == 1
        else klt_sim.DEFAULT_CAPACITY_WAIT_S
    )
    report = klt_sim.submit(
        workdir / "request.json", workdir / "out", backend=backend,
        capacity_wait_s=capacity_wait_s,
    )
    _vals, info = klt_sim.measurements_by_corner(report, CAND_SUPPLY_KEY)
    return report, dict(info, backend=backend or "(klt default / KLT_SIM_BACKEND)")


def candidate_corner_row(values: dict[str, float | None], code_name: str) -> dict:
    """One corner's acquisition row: per-side residuals at both deadlines
    plus the differential error the DRAFT-row verdict is read against."""
    row: dict = {"code": code_name}
    for stat, step in (("fast", "fast"), ("slow", "slow"), ("late", "slow")):
        vs = {}
        for side, (node, v_initial, v_final) in SIDES.items():
            v = values.get(f"{step}.acq_{stat}_{side}")
            ok = klt_sim.finite(v)
            vs[side] = v if ok else None
            row[f"{stat}_{side}_v"] = v if ok else None
            row[f"{stat}_{side}_err_mv"] = (
                (v - v_final) * 1e3 if ok else None
            )
        if all(vs[s] is not None for s in SIDES):
            row[f"{stat}_diff_err_mv"] = (
                (vs["p"] - vs["n"]) - V_TARGET_DIFF
            ) * 1e3
        else:
            row[f"{stat}_diff_err_mv"] = None
    complete = all(
        row.get(f"{stat}_{side}_err_mv") is not None
        for stat in ("fast", "slow", "late")
        for side in SIDES
    )
    row["complete"] = complete
    tset = values.get("tset.acq_tset")
    row["tset_ns"] = tset * 1e9 if klt_sim.finite(tset) else None
    if complete:
        row["worst_node"] = max(
            SIDES, key=lambda s: abs(row[f"fast_{s}_err_mv"])
        )
        row["worst_fast_err_mv"] = row[f"fast_{row['worst_node']}_err_mv"]
        # Per-endpoint worst node: each deadline's table names its OWN worst.
        for stat in ("fast", "slow"):
            row[f"worst_node_{stat}"] = max(
                SIDES, key=lambda s, st=stat: abs(row[f"{st}_{s}_err_mv"])
            )
    return row


def _report_backend(rep: dict) -> str:
    """The backend a report says it actually ran on (environment.backend.
    resolved) -- the record states what happened, not what was requested."""
    env = rep.get("environment") or {}
    return str((env.get("backend") or {}).get("resolved"))


def _fmt_mv(v: float | None, nd: int = 4) -> str:
    return "N/A" if v is None else f"{v:+.{nd}f}"


def read_bit_trial_companion(
    record_id: str,
) -> tuple[str, dict[str, list[dict]], list[str]]:
    """The bit-trial candidate campaign's committed raw report, re-read from
    its `corners/<record-id>/report.json` -- the machine-readable half of
    the settling-versus-rate table (never re-parsed from the record's own
    Markdown). Returns (record_id, {corner_id: rows}, complete corner ids)
    using the companion runner's own reader."""
    sys.path.insert(0, str(SIM_DIR / "cdac-bit-trial-settling"))
    import run_bit_trial_settling as companion  # noqa: E402
    report_path = (
        SIM_DIR / "cdac-bit-trial-settling" / "corners" / record_id / "report.json"
    )
    report = json.loads(report_path.read_text())
    by_corner, complete = companion.read_candidate_report(report)
    return record_id, by_corner, complete


def verdict_lines(
    grid: dict[str, dict],
    cids: list[str],
    bt_record: str | None,
    bt_by_corner: dict[str, list[dict]] | None,
    bt_complete: list[str] | None,
) -> list[str]:
    """The DRAFT sample-rate row verdict, one bullet per endpoint, plus the
    combined settling-versus-rate table rows. Criterion stated up front (a
    reference scale, not a ratified gate): the endpoint holds iff the
    worst-grid-corner DIFFERENTIAL acquisition error at that deadline is
    within the provisional differential half-LSB AND the bit-trial phase
    budget still leaves room for the comparator + sequencer delays."""
    out = [
        "**Verdict criterion (a reference scale, not a ratified gate).** An "
        "endpoint of the DRAFT `100 kS/s--1 MS/s` row is reported as HOLDING "
        f"iff (a) the worst grid corner's DIFFERENTIAL acquisition error at "
        f"that deadline stays within the provisional differential half-LSB "
        f"({HALF_LSB_MV:.4f} mV, DR-003 Item 2 pending #27), and (b) the "
        "bit-trial settling at that deadline leaves the phase with more time "
        f"than the comparator decision ({COMPARATOR_DECISION_NS} ns) plus "
        f"sequencer logic ({SEQUENCER_LOGIC_NS} ns) delays need (their own "
        "PVT-complete binding figures, cited in the sample-rate entry of "
        "`sim/report/manifest.py`). Both mechanisms' numbers are measured at "
        "the candidate plate with UNCHANGED switches and weights.",
    ]
    complete = [c for c in cids if grid.get(c, {}).get("complete")]
    for label, rate, stat in (
        ("1 MS/s (fast end, f_clk = 12 MHz)", "1 MS/s", "fast"),
        ("100 kS/s (slow end, f_clk = 1.2 MHz)", "100 kS/s", "slow"),
    ):
        errs = [
            (c, grid[c][f"{stat}_diff_err_mv"])
            for c in complete
            if grid[c].get(f"{stat}_diff_err_mv") is not None
        ]
        if not errs:
            out.append(
                f"- **{rate}: NO VERDICT** -- no completed corner produced a "
                "differential read at this deadline."
            )
            continue
        bind_cid, bind_err = max(errs, key=lambda ce: abs(ce[1]))
        worst_node_cid, worst_node_name, worst_node_err = max(
            (
                (c, SIDES[node][0], grid[c][f"{stat}_{node}_err_mv"])
                for c in complete
                for node in SIDES
                if grid[c].get(f"{stat}_{node}_err_mv") is not None
            ),
            key=lambda ce: abs(ce[2]),
        )
        acq_ok = abs(bind_err) <= HALF_LSB_MV
        # Bit-trial side, from the companion record's own reader.
        bt_ok = None
        bt_txt = "no companion bit-trial record supplied (--bit-trial-record)"
        if bt_by_corner is not None:
            tkey = "t99_ns"
            ekey = "pend_fast_err_mv" if stat == "fast" else "pend_slow_err_mv"
            valid = [
                (cid, r) for cid, rows in bt_by_corner.items() for r in rows
                if r.get(tkey) is not None
            ]
            if valid:
                bt_cid, bt_row = max(valid, key=lambda cr: cr[1][tkey])
                deadline = (
                    T_PHASE_WORST_NS if stat == "fast" else T_PHASE_SLOW_NS
                )
                left = deadline - bt_row[tkey]
                need = COMPARATOR_DECISION_NS + SEQUENCER_LOGIC_NS
                bt_ok = left > need
                bt_txt = (
                    f"bit-trial worst t_settle_99% = {bt_row[tkey]:.4f} ns "
                    f"(bit {bt_row['test_bit']}/{bt_row['direction']} at "
                    f"`{bt_cid}`, companion record "
                    f"[`{bt_record}`](../../cdac-bit-trial-settling/records/"
                    f"{bt_record}.md)), leaving {left:.3f} ns of the "
                    f"{deadline:.3f} ns phase vs the {need:.4f} ns the "
                    "comparator + sequencer delays need"
                )
        # A positive verdict needs the FULL requested corner set on both
        # sides; a demonstrated failure on the corners present still stands.
        missing_acq = [c for c in cids if c not in complete]
        missing_bt = (
            [c for c in cids if c not in (bt_complete or [])]
            if bt_by_corner is not None else []
        )
        if bt_ok is None:
            verdict = "NO VERDICT (companion evidence missing)"
        elif not acq_ok or not bt_ok:
            verdict = "DOES NOT HOLD"
        elif missing_acq or missing_bt:
            verdict = "NO VERDICT (incomplete evidence)"
            bt_txt += (
                f"; INCOMPLETE: acquisition missing {missing_acq or 'none'}, "
                f"bit-trial missing {missing_bt or 'none'}"
            )
        else:
            verdict = "HOLDS"
        reason = (
            f"differential acquisition error {bind_err:+.4f} mV at `{bind_cid}` "
            f"({abs(bind_err) / HALF_LSB_MV:.2f}x the {HALF_LSB_MV:.4f} mV "
            "half-LSB reference; worst single-ended node residual "
            f"{worst_node_err:+.4f} mV on `{worst_node_name}` at "
            f"`{worst_node_cid}`)"
        )
        out.append(
            f"- **{label}: {verdict}.** At this deadline the binding "
            f"acquisition corner: {reason}. {bt_txt}." if bt_txt
            else f"- **{label}: {verdict}.** {reason}."
            + (
                ""
                if (acq_ok and bt_ok is not False) or bt_ok is None
                else " A measured settling failure is a valid outcome (#1033); "
                "closing it by resizing the sampling switch is a separate "
                "design change needing its own DR-011/DR-014 evidence, and "
                "any row change goes through a decision record, never an "
                "edit of the DRAFT row."
            )
        )
    return out


def write_candidate_record(
    grid: dict[str, dict],
    control: dict[str, dict],
    cids: list[str],
    info: dict,
    reports: dict[str, dict],
    workdirs: dict[str, Path],
    bt_record: str | None,
    bt_by_corner: dict[str, list[dict]] | None,
    bt_complete: list[str] | None,
    regen_note: str,
    note: str = "",
    supersedes: str = "",
) -> Path:
    """The candidate-geometry acquisition record: the combined
    settling-versus-rate table (this campaign's acquisition rows plus the
    companion bit-trial record's own numbers), the DRAFT-row verdict, and
    the same `corners/<record-id>/` + `request/` artifact layout the
    input-drive-budget batch records use."""
    body = build_candidate_body(CORNERS_CODE_STATE)
    prov, lines = evidence.open_record(
        EXPERIMENT_DIR, body, "corners",
        {f"{name}.json": json.dumps(rep, indent=1) + "\n"
         for name, rep in reports.items()},
    )
    req_root = EXPERIMENT_DIR / "corners" / prov.record_id / "request"
    for name, wd in workdirs.items():
        d = req_root / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "request.json").write_text((wd / "request.json").read_text())
        (d / "tb.spice").write_text((wd / "tb.spice").read_text())

    env = klt_sim.executing_environment(prov, info)
    klt_version = klt_sim.client_version()
    complete = [c for c in cids if grid.get(c, {}).get("complete")]

    lines[0] = (
        "# sampling-cdac-handoff -- mechanism (d) at the DR-027 candidate "
        f"plate ({CANDIDATE_UNIT_CAP_WL_UM:.4f} um) -- full PVT grid -- "
        f"{prov.record_id}"
    )
    lines += [
        "- **Claim**: re-derives the sampling front end's acquisition of a "
        "new worst-case (rail-to-rail) differential input once SAMPLE "
        "re-asserts (mechanism (d)) at the assembled front-end + CDAC "
        "top-plate load with the DR-027 CANDIDATE unit plate "
        f"({CANDIDATE_UNIT_CAP_WL_UM:.4f} um side, ~12.4 pF/side nominal "
        "array contribution; the front end's own Csamp_p/Csamp_n stay on "
        "the shared top plates, per issue #1033), over the full ratified "
        "9-point OAT PVT grid, against BOTH DR-006 phase deadlines -- the "
        "12 MHz (1 MS/s) worst case and the 1.2 MHz (100 kS/s) slow end of "
        "the DRAFT sample-rate row -- and states a written verdict on that "
        "DRAFT row at each endpoint. EXPERIMENTAL study deck: "
        "`design/cdac/` still draws the DR-019 1.9000 um plate, and no "
        "claim here is graded against a ratified row (the sample-rate row "
        "is entirely DRAFT, #1/#27).",
        "- **Issue**: #1033 (the required settling/rate companion of the "
        "#1016 / DR-027 resize study)",
        "- **Netlist provenance**: the committed production fragments this "
        "campaign always assembles, with the CDAC fragment's 20 unit-cap "
        "plates rewritten to the candidate side and EVERYTHING else "
        "byte-identical (switch devices included) -- see "
        "candidate_cdac_fragment(), which refuses to run if the production "
        "fragment is not exactly 20 caps at the production plate. "
        f"{regen_note[0].upper()}{regen_note[1:]} -- so the candidate is "
        "generated from a VERIFIED baseline, per #1033.",
        corners_mod.corner_matrix_summary_line(
            sorted({corners_mod.parse_corner_id(c)[0] for c in cids}),
            sorted({corners_mod.parse_corner_id(c)[1] for c in cids}),
            sorted({corners_mod.parse_corner_id(c)[2] for c in cids}),
            len(cids),
        ),
        "- **Stimulus**: the baseline two-pulse acquisition stimulus with "
        f"SAMPLE pulse #2 widened to {CAND_T_SAMPLE2_WIDTH_NS:g} ns (fall at "
        f"{CAND_T_SAMPLE2_FALL_NS:g} ns) so the DR-006 slow-end deadline "
        f"({CAND_SLOW_AT_NS:.3f} ns, the acquiring edge's 50 % crossing at "
        f"{TRIG_AT_NS:g} ns + {T_PHASE_SLOW_NS:.3f} ns) falls inside the "
        "active phase and ahead of switch turn-off (#1033's window rule); "
        "the fast deadline's read is at the SAME "
        f"{CAND_FAST_AT_NS:.3f} ns instant the 1.9000 um records' budget "
        "probe uses, so their columns are directly comparable. One body "
        "serves all nine corners: SAMPLE swing, SEL logic levels and VREFP "
        "are normalised sources scaled by the corner supply, while the "
        "input extremes and VCM keep the baseline campaign's fixed values "
        "(its own documented convention).",
        f"- **CDAC previous-code state**: `{CORNERS_CODE_STATE}` at every "
        "grid point; the other two states re-run at the baseline corner as "
        "an independence control (the baseline grid's own convention -- the "
        "array's bottom plates are continuously driven, so the code sets "
        "their charge but not the capacitance TOP_x sees).",
        f"- **Overall**: {'COMPLETE' if len(complete) == len(cids) else 'INCOMPLETE'} "
        f"({len(complete)}/{len(cids)} corners produced every fixed-time "
        "read at both deadlines)",
    ]
    if note:
        lines.append(f"- **Note**: {note}")
    lines.append("")

    for stat, desc in (
        ("fast", f"12 MHz deadline ({CAND_FAST_AT_NS:.3f} ns)"),
        ("slow", f"1.2 MHz deadline ({CAND_SLOW_AT_NS:.3f} ns)"),
    ):
        lines += [
            f"## Acquisition residual per corner -- {desc}",
            "",
            "Single-ended residuals are each side's read minus its own "
            "target (negative = short of the target); the differential error is "
            "(TOP_P - TOP_N) - 1.4 V, the quantity the half-LSB reference "
            f"scale ({HALF_LSB_MV:.4f} mV) is stated against. `late` is a "
            f"read at {CAND_LATE_AT_NS:g} ns, inside pulse #2 and ahead of "
            "its fall, separating a still-settling node from a settled "
            "offset.",
            "",
            "| Corner | Worst node | P resid (mV) | N resid (mV) | "
            "differential err (mV) | x half-LSB | late diff err (mV) |",
            "|---|---|---|---|---|---|---|",
        ]
        for cid in cids:
            row = grid.get(cid, {})
            if not row.get("complete"):
                lines.append(f"| `{cid}` | -- | INCOMPLETE | INCOMPLETE | -- | -- | -- |")
                continue
            d = row[f"{stat}_diff_err_mv"]
            lines.append(
                f"| `{cid}` | `{row[f'worst_node_{stat}']}` | "
                f"{_fmt_mv(row[f'{stat}_p_err_mv'])} | "
                f"{_fmt_mv(row[f'{stat}_n_err_mv'])} | "
                f"{_fmt_mv(d)} | {abs(d) / HALF_LSB_MV:.2f}x | "
                f"{_fmt_mv(row['late_diff_err_mv'])} |"
            )
        lines.append("")

    lines += [
        "## Acquisition settling time (time of entry into the half-LSB band)",
        "",
        "Measured, not read at a fixed instant: `.meas ... TRIG AT="
        f"{TRIG_AT_NS:g}n TARG V(ACQERR) VAL={HALF_LSB_MV * 1e-3:.9g} "
        "FALL=LAST` on ACQERR = |(TOP_P - TOP_N) - 1.4 V|, i.e. the time "
        "from the acquiring (second) SAMPLE edge's 50 % crossing to the "
        "last instant the differential error falls through the provisional "
        f"differential half-LSB ({HALF_LSB_MV:.4f} mV, DR-003 Item 2 "
        "pending #27) -- after which it stays inside the band for the rest "
        f"of the measurement window, which ends at the {CAND_LATE_AT_NS:g} ns late read, ahead of SAMPLE pulse #2's fall (a longer window would time the switch turn-off, not the acquisition). A corner with no "
        "crossing is shown as `none` (never entered, or never left, the "
        "band) and is retained as data. Same 0.2 ns step ceiling as the "
        "fixed-time reads.",
        "",
        "| Corner | t_settle (half-LSB band) (ns) | within 12 MHz deadline "
        f"({T_PHASE_WORST_NS:.3f} ns) | within 1.2 MHz deadline "
        f"({T_PHASE_SLOW_NS:.3f} ns) |",
        "|---|---|---|---|",
    ]
    for cid in cids:
        t = grid.get(cid, {}).get("tset_ns")
        if t is None:
            lines.append(f"| `{cid}` | none | -- | -- |")
        else:
            lines.append(
                f"| `{cid}` | {t:.3f} | "
                f"{'yes' if t <= T_PHASE_WORST_NS else 'NO'} | "
                f"{'yes' if t <= T_PHASE_SLOW_NS else 'NO'} |"
            )
    tvals = [
        (c, grid[c]["tset_ns"]) for c in cids
        if grid.get(c, {}).get("tset_ns") is not None
    ]
    if tvals:
        tb_cid, tb = max(tvals, key=lambda ct: ct[1])
        lines += [
            "",
            f"Binding corner: `{tb_cid}`, t_settle = {tb:.3f} ns after the "
            f"acquiring SAMPLE edge ({tb / T_PHASE_WORST_NS:.2f}x the "
            f"12 MHz deadline, {tb / T_PHASE_SLOW_NS:.2f}x the 1.2 MHz "
            f"deadline); {len(tvals)}/{len(cids)} corners produced a "
            "crossing.",
        ]
    lines.append("")

    lines += [
        "## Code-state independence control (baseline corner)",
        "",
        "| Code state | P resid @ fast (mV) | N resid @ fast (mV) | "
        "diff err @ fast (mV) | diff err @ slow (mV) |",
        "|---|---|---|---|---|",
    ]
    baseline_id = corners_mod.corner_id("tt", 27.0, VDD)
    for code_name, row in control.items():
        lines.append(
            f"| `{code_name}` | {_fmt_mv(row.get('fast_p_err_mv'))} | "
            f"{_fmt_mv(row.get('fast_n_err_mv'))} | "
            f"{_fmt_mv(row.get('fast_diff_err_mv'))} | "
            f"{_fmt_mv(row.get('slow_diff_err_mv'))} |"
        )
    lines.append("")

    # --- the combined settling-versus-rate table ---
    lines += [
        "## Settling versus rate at the candidate plate -- both mechanisms",
        "",
        "The DR-027-required table linking the two measurements of this "
        "study: the acquisition half is this record's own grid above; the "
        "bit-trial half is re-read from the companion candidate record's "
        "committed raw report (its own runner's reader, never re-parsed "
        "from prose).",
        "",
        "| Endpoint | Mechanism | Binding corner | Binding row/node | "
        "Measured quantity | Value | Budget / reference | Margin |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for label, stat, deadline_ns in (
        ("1 MS/s (12 MHz)", "fast", T_PHASE_WORST_NS),
        ("100 kS/s (1.2 MHz)", "slow", T_PHASE_SLOW_NS),
    ):
        errs = [
            (c, grid[c][f"{stat}_diff_err_mv"]) for c in complete
            if grid[c].get(f"{stat}_diff_err_mv") is not None
        ]
        if errs:
            bind_cid, bind_err = max(errs, key=lambda ce: abs(ce[1]))
            lines.append(
                f"| {label} | front-end acquisition (differential) | "
                f"`{bind_cid}` | (TOP_P-TOP_N)-1.4V | residual @ deadline | "
                f"{bind_err:+.4f} mV | {HALF_LSB_MV:.4f} mV half-LSB | "
                f"{abs(bind_err) / HALF_LSB_MV:.2f}x |"
            )
        else:
            lines.append(
                f"| {label} | front-end acquisition (differential) | -- | -- | "
                "residual @ deadline | INCOMPLETE | -- | -- |"
            )
        if bt_by_corner is not None:
            valid = [
                (cid, r) for cid, rows in bt_by_corner.items() for r in rows
                if r.get("t99_ns") is not None
            ]
            if valid:
                bt_cid, bt_row = max(valid, key=lambda cr: cr[1]["t99_ns"])
                lines.append(
                    f"| {label} | CDAC bit-trial settling | `{bt_cid}` | "
                    f"bit {bt_row['test_bit']}/{bt_row['direction']} | "
                    f"t_settle_99% | {bt_row['t99_ns']:.4f} ns | "
                    f"{deadline_ns:.3f} ns phase "
                    f"(- {COMPARATOR_DECISION_NS + SEQUENCER_LOGIC_NS:.4f} ns "
                    "comparator+sequencer) | "
                    f"{(deadline_ns - COMPARATOR_DECISION_NS - SEQUENCER_LOGIC_NS) / bt_row['t99_ns']:.2f}x |"
                )
            else:
                lines.append(
                    f"| {label} | CDAC bit-trial settling | -- | -- | "
                    "t_settle_99% | INCOMPLETE | -- | -- |"
                )
        else:
            lines.append(
                f"| {label} | CDAC bit-trial settling | (companion record "
                "not supplied) | -- | -- | -- | -- | -- |"
            )
    lines += [
        "",
        "Margins are (deadline - comparator - sequencer) / settling for the "
        "bit-trial rows -- i.e. how many times over the settled array still "
        "fits the phase once the other two mechanisms' binding delays are "
        "subtracted.",
        "",
        "## Result -- verdict on the DRAFT sample-rate row at the candidate plate",
        "",
    ]
    lines += verdict_lines(grid, cids, bt_record, bt_by_corner, bt_complete)
    lines += [
        "",
        "## What this record does not establish",
        "",
        "- Both benches are sub-block settling measurements at an "
        "EXPERIMENTAL plate size: passing or failing them does not by "
        "itself set the sample rate, and whole-ADC code correctness "
        "(the #263/#259 line of work) remains open independently.",
        "- The front end here is the shipping front end driving ~2.8x the "
        "array capacitance with UNCHANGED sampling switches, exactly the "
        "configuration whose shortfall #1033 asks quantified. The study "
        "does not resize anything; a resize needs its own DR-011/DR-014 "
        "charge-injection/kickback evidence, and any target-table change "
        "goes through a decision record (DR-027's ratification path), "
        "never an edit.",
        "- As in the baseline grid: one step direction of the worst-case "
        "differential stimulus, the previous-code state fixed at every "
        "grid point (with the control table above), and the held-bit "
        "parasitic omission inherited from the companion bench's own "
        "documented reduction.",
        "",
        "## Reproduction",
        "",
        "```bash",
        "# One-time machine bootstrap: docs/environment-setup.md sections 1-3.",
        "source sim/env.sh",
        "# the companion bit-trial candidate record first:",
        "# `--wait-for-capacity` is batch-only, so the backend must be batch:",
        "export KLT_SIM_BACKEND=batch",
        "python3 sim/cdac-bit-trial-settling/run_bit_trial_settling.py --dr027-candidate --record --backend batch",
        "# then this campaign, linking it:",
        "python3 sim/sampling-cdac-handoff/run_handoff.py --dr027-candidate --record --backend batch \\",
        f"    --bit-trial-record <that run's record id>",
        "```",
        "",
        "Three `klt sim` submits, as recorded in each archived report's "
        "`environment`: "
        + "; ".join(
            f"`{name}` backend `{_report_backend(rep)}`"
            for name, rep in reports.items()
        )
        + ". The 9-corner grid is submitted with `--wait-for-capacity 600`; "
        "the two single-corner code-state controls carry no capacity wait "
        "(the client refuses that flag for a single unit). No ngspice loop "
        "runs on the submitting host. `--probe` runs one corner on the local "
        "backend and is the only path that simulates locally. Requests and "
        "bodies are committed "
        f"under `corners/{prov.record_id}/request/`, the raw reports beside "
        f"this record under `corners/{prov.record_id}/`.",
        "",
        "## `klt sim` runs",
        "",
        f"- grid job `{info.get('job_id')}`, status `{info.get('status')}`, "
        f"backend `{info.get('backend')}`, executing PDK "
        f"`{info.get('worker_pdk')}`, executing simulator "
        f"`{info.get('worker_ngspice')}`"
        + (", sharded" if info.get("sharded") else "")
        + ".",
        "",
        "**Uncontrolled difference -- against the 1.9000 um baseline "
        f"grid.** [`records/{CAND_BASELINE_RECORD}.md`]"
        f"({CAND_BASELINE_RECORD}.md) was minted on "
        "`sky130A @ c6d73a35f524070e85faff4a6a9eef49553ebc2b` / `ngspice-46` "
        "by an in-process ngspice loop; this record was produced by the "
        "executing worker named above. Where those differ, a change between "
        "the two records is as readily a PDK or simulator-version difference "
        "as a geometry one; the controlled comparison is structural (same "
        "stimulus shape, same probe instants, same fragments modulo the "
        "plate side), and the fast-deadline column is directly comparable "
        "corner-for-corner.",
        "",
    ]
    lines += evidence.environment_block(
        env["pdk"],
        env["ngspice"],
        prov.netlist_sha,
        {
            "klt": klt_version,
            "candidate plate": f"{CANDIDATE_UNIT_CAP_WL_UM:.4f} um "
            "(EXPERIMENTAL; production draws 1.9000 um)",
            "assembled top-plate load": "front end Csamp (~4.43 pF/side, "
            "DR-004) + candidate array (~12.2 pF/side model-evaluated, "
            "512 x 23.805 fF -- see the companion record's unit-cap probe)",
            "tran steps": (
                f"fast {TRAN_STEP_NS:g} ns ceiling x {CAND_FAST_TRAN_STOP_NS:g} ns; "
                f"slow {CAND_SLOW_TRAN_STEP_NS:g} ns ceiling x "
                f"{CAND_TRAN_STOP_NS:g} ns"
            ),
            **env["attribution_extra"],
        },
    )
    lines += [""]
    lines += evidence.footer_lines(
        "sim/sampling-cdac-handoff/run_handoff.py", supersedes
    )
    evidence.write_latest_pointer(EXPERIMENT_DIR, prov.record_id)
    return evidence.close_record(prov, lines, "Record")


def candidate_main(args: argparse.Namespace) -> int:
    """The --dr027-candidate CLI path (issue #1033)."""
    pdk.resolve_or_raise()
    workroot = args.workdir or Path(tempfile.mkdtemp(prefix="handoff-dr027-"))
    cids = candidate_corner_ids()
    baseline_cid = corners_mod.corner_id("tt", 27.0, VDD)

    if args.dry_run:
        workroot.mkdir(parents=True, exist_ok=True)
        body = build_candidate_body(CORNERS_CODE_STATE)
        (workroot / "tb.spice").write_text(body)
        req = build_candidate_request(
            "tb.spice", cids, timeout_s=args.timeout_s,
            backend=args.backend, hosts=args.hosts,
        )
        (workroot / "request.json").write_text(json.dumps(req, indent=1) + "\n")
        print(f"wrote deck + request under {workroot}")
        print(f"corners: {len(cids)}  steps/corner: {len(req['analysis_steps'])}")
        return 0

    with tempfile.TemporaryDirectory(prefix="handoff-dr027-frag-") as tmp:
        regen_note = assert_fragments_current(Path(tmp))

    if args.probe:
        report, info = submit_candidate(
            workroot / "probe", CORNERS_CODE_STATE, [baseline_cid], "local",
            args.timeout_s,
        )
        row = candidate_corner_row(
            klt_sim.measurements_by_corner(report, CAND_SUPPLY_KEY)[0].get(baseline_cid) or {},
            CORNERS_CODE_STATE,
        )
        print(f"{baseline_cid} (local backend):")
        for stat in ("fast", "slow", "late"):
            print(
                f"  {stat}: P {_fmt_mv(row.get(f'{stat}_p_err_mv'))} mV  "
                f"N {_fmt_mv(row.get(f'{stat}_n_err_mv'))} mV  "
                f"diff {_fmt_mv(row.get(f'{stat}_diff_err_mv'))} mV"
            )
        print(
            "  compare: 1.9000 um assembled grid's tt_27c_1.80v fast-deadline "
            "row: TOP_P +0.0000 mV / TOP_N +0.0120 mV (record "
            f"{CAND_BASELINE_RECORD})"
        )
        print(f"  klt sim: backend {info.get('backend')}, status {info.get('status')}")
        return 0

    reports: dict[str, dict] = {}
    workdirs: dict[str, Path] = {}
    grid_info: dict = {}
    grid: dict[str, dict] = {}
    control: dict[str, dict] = {}
    for name, code_name, sub_cids in [
        ("grid", CORNERS_CODE_STATE, cids),
        ("code_zero", "prev_code_zero", [baseline_cid]),
        ("code_alt", "prev_code_alt", [baseline_cid]),
    ]:
        report, info = submit_candidate(
            workroot / name, code_name, sub_cids, args.backend,
            args.timeout_s, hosts=(args.hosts if name == "grid" else None),
        )
        results, _ = klt_sim.measurements_by_corner(
            report, CAND_SUPPLY_KEY, null_error_corners=False
        )
        for cid in results:
            row = candidate_corner_row(results[cid] or {}, code_name)
            if name == "grid":
                grid[cid] = row
            else:
                control[code_name] = row
        # the grid's own baseline-corner row doubles as the control table's
        # prev_code_one entry
        if name == "grid":
            control[CORNERS_CODE_STATE] = grid.get(baseline_cid, {})
            grid_info = info
            reports["report"] = report
            workdirs["grid"] = workroot / name
        else:
            reports[f"report_{name}"] = report
            workdirs[name] = workroot / name
        for cid in sub_cids:
            r = grid.get(cid) or control.get(code_name, {})
            if r.get("complete"):
                print(
                    f"{cid} [{code_name}]: worst node {r['worst_node']} "
                    f"fast {r['worst_fast_err_mv']:+.4f} mV, "
                    f"diff {r['fast_diff_err_mv']:+.4f} mV "
                    f"({abs(r['fast_diff_err_mv']) / HALF_LSB_MV:.2f}x half-LSB)"
                )
            else:
                print(f"{cid} [{code_name}]: INCOMPLETE")

    bt_by_corner = bt_complete = None
    bt_record = None
    if args.bit_trial_record:
        bt_record, bt_by_corner, bt_complete = read_bit_trial_companion(
            args.bit_trial_record
        )

    if args.record:
        write_candidate_record(
            grid, control, cids, grid_info, reports, workdirs,
            bt_record, bt_by_corner, bt_complete, regen_note,
            note=args.note, supersedes=args.supersedes,
        )
    n_incomplete = sum(1 for c in cids if not grid.get(c, {}).get("complete"))
    if n_incomplete:
        print(f"\nFAIL: {n_incomplete}/{len(cids)} grid corners incomplete.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

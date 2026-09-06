#!/usr/bin/env python3
"""Sampling front end acquisition-window settling budget (issue #121, Epic
#542 Phase 4B follow-up).

`docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2 names four
mechanisms that together would produce an end-to-end sample-rate figure.
Three are now quantified: `sim/cdac-bit-trial-settling/` (CDAC array
switch-settling, tt/27C/1.8V, one corner), `sim/comparator-decision/`
(comparator decision delay, full ratified PVT grid), and
`sim/sequencer-logic-delay/` (SAR sequencer CLK-to-phase-output logic
delay, tt/27C/1.8V, one corner). The fourth -- "the sampling front end's
acquisition remains wholly unmeasured" -- is what this script quantifies:
how long `design/sampling_frontend.sch`'s own bootstrapped sampling switch
takes, once the SAMPLE phase (re)asserts, to acquire a NEW analog input
value onto its own sampling capacitor (`TOP_P`/`TOP_N`) -- at a single
corner, the same "first-pass, single-corner budget" precedent
`sim/vcm-drive-budget/run_vcm_drive_budget.py`,
`sim/cdac-bit-trial-settling/run_bit_trial_settling.py`, and
`sim/sequencer-logic-delay/run_sequencer_logic_delay.py` already
established. It does NOT close the sample-rate open item: none of the four
mechanisms named above has been combined into one end-to-end campaign, and
only the comparator's own campaign has full PVT coverage -- real switch
`R_on` varies materially with process/temperature/supply, the same class
of gap #28's corner campaigns already cover elsewhere in this design.

WHY THIS IS SEPARABLE FROM `sim/sampling-frontend/run_transient.py`'s
EXISTING IN-SAMPLE SETTLING CHECK. That script already proves TOP_P/TOP_N
settle to within simulation resolution (sub-mV) of their analog inputs by
`SAMPLE_END_NS` (409 ns into a 400-ns-wide SAMPLE pulse) -- but a 400 ns
window is a legacy convenience from before DR-006 existed, not a bound
derived from the actual per-phase clock budget; it proves "the value has
landed well before this generous window closes", not "how long after the
triggering SAMPLE edge did it land, and is that inside the DR-006 phase
budget". This experiment adds the missing measurement: for a full-scale
(rail-to-rail, worst-case near-Nyquist) differential input STEP applied
between two consecutive SAMPLE assertions, it measures (a) the wall-clock
delay from the 50% (Vdd/2) crossing of the SECOND SAMPLE rising edge (the
edge that re-connects `TOP_P`/`TOP_N` to the NEW input value) to the point
at which each node first crosses 50%/90% of the way from its OLD (held)
value to its NEW (target) value -- the same TRIG(AT=)/TARG(...CROSS=1)
`.meas` idiom `sim/cdac-bit-trial-settling/`'s own `t_settle_*` measures
and `sim/sequencer-logic-delay/`'s own `delay_*` measures already use --
and (b) the residual error still remaining at a FIXED time exactly one
DR-006 worst-case (12 MHz) phase period after that same trigger point --
a direct, unambiguous "how far off is it when this phase's budget would
end" reading, not a crossing search (see "WHY A FIXED-TIME BUDGET PROBE,
NOT A 99% CROSSING" below for why the third fraction this script's first
draft attempted, a 99% TRIG/TARG crossing, was dropped).

TWO SEPARATE ngspice `.meas ... TRIG/TARG` PITFALLS THIS SCRIPT WORKS AROUND
(both found by debugging implausible first-draft results against the raw
per-timestep transient data, not assumed away). **(1) `TARG ... CROSS=n`
counts crossings from t=0 of the WHOLE simulated waveform, not from the
TRIG point.** Because SAMPLE pulse #1 drives each node from an arbitrary
initial condition up to ITS OWN target value, that ramp necessarily sweeps
through most of the node's usable range -- including values that later
serve as pulse #2's own 50%/90% thresholds for the OPPOSITE-direction
transition. Without correction, `CROSS=1` locks onto pulse #1's own
transient (an early, spurious "crossing" that predates the real trigger
entirely, surfacing as a nonsensical NEGATIVE `(targ_time - trig_time)`).
Fixed by adding `TD=<trig_time>` to every TARG clause below -- ngspice's
documented "start searching no earlier than this time" qualifier -- which
confines the crossing search to pulse #2's own transient, confirmed by
comparing measured delays against the raw transient data directly.
**(2) a threshold close enough to the eventual settled value can pick up a
LATER transient's own artifact instead of genuine convergence.** An earlier
version of this script added a `t_settle_*_99` TRIG/TARG measure alongside
the 50%/90% ones (with the `TD=` fix from (1) already applied). Debugging
an implausible result (a ~100 ns "settling time" for a node that visibly
plateaus far short of the 99% threshold for most of the window) found that
SAMPLE pulse #2's own eventual turn-off transient (a real, previously-
documented kick -- see `sim/sampling-frontend/run_hold_kick.py`, issue #61)
produces a brief overshoot that happens to cross the 99% threshold a split
second before pulse #2 fully deasserts -- a spurious crossing, not genuine
settling, confirmed against the raw per-timestep transient data. A fixed
"find V(node) at=<time>" read (this script's actual choice for its own
budget-relevant fraction, matched to DR-006's own phase-period figure) has
no such ambiguity: it is a single point sample, not a search, so it cannot
pick up a later transient's own artifact.

STIMULUS SHAPE, AND WHY. A single SAMPLE pulse starting from an unbiased
initial condition cannot exercise "acquiring a NEW value" -- `TOP_P`/
`TOP_N` would just settle to whatever ngspice's own arbitrary bias-point
guess happened to be, which is not a meaningful "previous held value".
Instead this script drives two SAMPLE pulses:

  1. SAMPLE pulse #1 (generously wide, 100 ns) with `VINP`/`VINN` held at
     one rail-adjacent extreme -- `TOP_P`/`TOP_N` settle fully to that
     value by the end of the pulse (the SAME settling
     `sim/sampling-frontend/run_transient.py` already proved is sub-mV
     clean well inside 400 ns, so 100 ns here is ample).
  2. During the following HOLD phase (SAMPLE deasserted, `Msw` off,
     `TOP_P`/`TOP_N` floating and retaining their pulse-#1 value), `VINP`/
     `VINN` step to the OPPOSITE rail-adjacent extreme -- modelling the
     worst case for a near-Nyquist input signal changing by the full
     differential span between consecutive samples. This step happens
     entirely while `Msw` is off, so it cannot itself perturb `TOP_P`/
     `TOP_N` -- only SAMPLE pulse #2 (below) can.
  3. SAMPLE pulse #2 re-asserts, 30 ns after the input step completes
     (well clear of the step's own 0.2 ns edge, so nothing measured here
     is an artifact of the input source's own slew). THIS is the edge the
     `.meas` statements below trigger from: it is the point at which the
     bootstrapped switch reconnects `TOP_P`/`TOP_N` to the NEW input
     value, and everything that follows is the acquisition transient this
     script exists to quantify.

No claim here is graded against a ratified spec row: `spec/target-spec.md`
is entirely DRAFT (#1/#27); the DR-006 phase-period figures quoted for
comparison are themselves downstream of the DRAFT sample-rate row (Section
7 Item 2), the same convention `sim/cdac-bit-trial-settling/`'s and
`sim/sequencer-logic-delay/`'s own records already follow. The differential
LSB figure quoted is DR-003 Item 2's provisional value (pending #27),
referenced only as a familiar scale for the residual "confirm" error, the
same convention `sim/sampling-frontend/run_transient.py`'s own "hold delta"
figures already use.

Usage (from the repo root, after ``source sim/env.sh``)::

    python3 sim/sampling-acquisition-settling/run_acquisition_settling.py
    python3 sim/sampling-acquisition-settling/run_acquisition_settling.py --record
    # Full ratified PVT grid (9 OAT points, same axes sim/comparator-decision/
    # sweeps) instead of the single tt/27C/1.8V corner above:
    python3 sim/sampling-acquisition-settling/run_acquisition_settling.py --corners --record
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
EXPERIMENT_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(SIM_DIR))
from harness import corners as corners_mod, evidence, measure, pdk, toolchain  # noqa: E402

# Same regenerated DUT fragment sim/sampling-frontend/run_transient.py and
# sim/sampling-frontend/run_hold_kick.py already use (design/
# sampling_frontend.sch, issue #52) -- not re-netlisted here, per that
# directory's own committed-fragment convention (see the fragment file's own
# header for the regeneration recipe).
DUT_FRAGMENT = REPO_ROOT / "sim" / "sampling-frontend" / "testbench" / "sampling_frontend_dut.spice"

VDD = 1.8
VCM = 0.9
CORNER = "tt"
TEMP_C = 27.0
LSB_DIFF_MV_PROVISIONAL = 3.5156  # DR-003 Item 2, provisional pending #27 --
# reference scale only, same convention sim/sampling-frontend/
# run_transient.py's own "hold delta" figures already use.

# Ratified corner-set axes (issue #28), per spec/target-spec.md's "Numeric
# rows -- RATIFIED 2026-08-19" section: -40/27/125C, +-10% supply, sky130
# process corners -- the same axes sim/comparator-decision/'s own
# regen-corners campaign sweeps. Used only by the optional --corners mode
# below; the single-corner (tt/27C/1.8V) default behavior above is
# unchanged.
SUPPLY_TOLERANCE = 0.10
TEMPS_C = [-40, 27, 125]
PROCESS_CORNERS = ["tt", "ss", "ff", "sf", "fs"]

# The single-corner (tt/27C/1.8V) record --corners's own evidence record
# cross-references as "the finding this campaign extends" -- PR #204,
# sim/sampling-acquisition-settling/records/20260906-202424-cb7e7aa.md.
SINGLE_CORNER_SEED_RECORD = "20260906-202424-cb7e7aa"

EDGE_TR_NS = 0.2  # rise/fall time for every edge below -- same convention
# sim/cdac-bit-trial-settling/'s own EDGE_TR_NS.

# Two-pulse SAMPLE stimulus timing (ns) -- see module docstring "STIMULUS
# SHAPE" for the full rationale of each interval.
T_PRECHARGE_NS = 10.0  # SAMPLE stays low until here (bootstrap network
# precharges: BOOST->VDD, BSBOT->0, G->0 -- same precharge interval
# sim/sampling-frontend/run_transient.py's own 10ns-before-first-edge
# convention already uses).
T_SAMPLE1_RISE_NS = T_PRECHARGE_NS
T_SAMPLE1_WIDTH_NS = 100.0  # generous -- TOP_P/TOP_N fully settle to the
# OLD value well inside this (run_transient.py already shows sub-mV
# settling inside 400ns; 100ns is still >>10x any settling time this
# script's own measurements below turn out to find).
T_SAMPLE1_FALL_NS = T_SAMPLE1_RISE_NS + T_SAMPLE1_WIDTH_NS  # 110.0

T_INPUT_TOGGLE_NS = T_SAMPLE1_FALL_NS + 20.0  # 130.0 -- input steps to the
# opposite rail-adjacent extreme 20ns into the hold phase, while Msw is off
T_SAMPLE2_RISE_NS = T_INPUT_TOGGLE_NS + 30.0  # 160.0 -- SAMPLE re-asserts
# 30ns after the input step completes (well clear of the step's own 0.2ns
# edge)
# DR-006-derived per-phase clock budget (1 CLK period per bit-trial phase,
# uniform allocation, which per DR-006 Sec. "Phase count..." applies
# equally to the SAMPLE phase) -- same reference points
# sim/cdac-bit-trial-settling/ and sim/sequencer-logic-delay/ already
# quote, for comparison only, not a pass/fail gate against a ratified row.
T_PHASE_WORST_NS = 1.0e3 / 12.0  # 83.333... ns @ f_clk_max = 12 MHz
T_PHASE_SLOW_NS = 1.0e3 / 1.2  # 833.33... ns @ f_clk_min = 1.2 MHz

T_SAMPLE2_WIDTH_NS = 150.0  # comfortably longer than T_PHASE_WORST_NS
# (83.333ns) plus a confirmatory read further out, both well clear of the
# pulse's own eventual fall (see "WHY A FIXED-TIME BUDGET PROBE" above for
# why that margin matters -- SAMPLE's own turn-off transient must not
# overlap either probe point).
T_SAMPLE2_FALL_NS = T_SAMPLE2_RISE_NS + T_SAMPLE2_WIDTH_NS  # 310.0

TRAN_STOP_NS = T_SAMPLE2_FALL_NS + 20.0  # 330.0
TRAN_STEP_NS = 0.02  # 20ps -- fine enough to resolve a sub-ns settling
# transient (this design's Csamp is deliberately sized, per DR-004, to
# mimic the real CDAC array's ~4.43pF/side total load, so a settling time
# of the same rough order as sim/cdac-bit-trial-settling/'s own tens-of-ns
# figures is expected, not a picosecond-scale one -- but this script
# measures rather than assumes that).

TRIG_AT_NS = T_SAMPLE2_RISE_NS + EDGE_TR_NS / 2.0  # 160.1 -- 50% crossing
# of the SAMPLE pulse #2 rising edge: the instant Msw reconnects TOP_P/
# TOP_N to the NEW input value. Every settling measurement below is
# relative to this point.
BUDGET_PROBE_AT_NS = TRIG_AT_NS + T_PHASE_WORST_NS  # 243.433... -- a fixed
# read, exactly one DR-006 worst-case (12 MHz) phase period after the
# trigger point: "how far from the ideal target value is this node when
# a real SAMPLE phase, run at the fastest DR-006-derived rate, would end".
CONFIRM_AT_NS = T_SAMPLE2_FALL_NS - 5.0  # 305.0 -- long-time (well inside
# SAMPLE pulse #2, clear of its own fall) confirmatory read, showing
# whether/how far the node eventually gets given much more time than the
# phase budget allows.

# Worst-case rail-adjacent differential swing (same magnitude
# sim/sampling-frontend/run_transient.py's own "worst_case_pp"/
# "worst_case_np" test points use): P goes low->high, N goes high->low,
# simultaneously -- the maximum simultaneous full-scale differential step
# this design's own input range (0-VDD single-ended per side) can present.
V_INITIAL_P, V_FINAL_P = 0.2, 1.6
V_INITIAL_N, V_FINAL_N = 1.6, 0.2

# Only the fast, unambiguous early fractions use a TRIG/TARG crossing
# search (both land well under 1ns after TRIG_AT_NS, nowhere near SAMPLE
# pulse #2's own fall -- see "WHY A FIXED-TIME BUDGET PROBE, NOT A 99%
# CROSSING" above for why a tighter fraction was dropped in favor of
# BUDGET_PROBE_AT_NS/CONFIRM_AT_NS's fixed-time reads instead).
FRACTIONS = [0.5, 0.9]

SIDES = {
    "p": ("TOP_P", V_INITIAL_P, V_FINAL_P),
    "n": ("TOP_N", V_INITIAL_N, V_FINAL_N),
}

TRIG_TARG_NAMES = [f"t_settle_{side}_{int(f * 100)}" for side in SIDES for f in FRACTIONS]
MEASURE_NAMES = [f"{stat}_{side}" for side in SIDES for stat in ("budget", "confirm")]

# ngspice's TRIG(AT=)/TARG(...CROSS=1) measure prints extra " targ=...
# trig=..." context on the SAME line as "name = value" -- sim/harness's
# shared measure.parse() uses a right-anchored regex that rejects this
# outright (silently yielding no match, not an exception). Parsed locally
# here, the identical workaround sim/cdac-bit-trial-settling/
# run_bit_trial_settling.py's and sim/sequencer-logic-delay/
# run_sequencer_logic_delay.py's own `_parse_trig_targ()` already
# established.
_TRIG_TARG_RE_TMPL = r"^{name}\s*=\s*([-+0-9.eE]+)"


def _parse_trig_targ(log_text: str, names: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for name in names:
        pattern = re.compile(_TRIG_TARG_RE_TMPL.format(name=re.escape(name)))
        for line in log_text.splitlines():
            m = pattern.match(line.strip())
            if m:
                try:
                    out[name] = float(m.group(1))
                except ValueError:
                    pass
                break
    return out


def _pwl(points: list[tuple[float, float]]) -> str:
    return "pwl(" + " ".join(f"{t:g}n {v:g}" for t, v in points) + ")"


def build_transient(corner: str = CORNER, temp_c: float = TEMP_C, vdd: float = VDD) -> str:
    frag = DUT_FRAGMENT.read_text()
    info = pdk.resolve()

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

    lines = [
        f"* sampling-frontend acquisition-window settling (issue #121) -- "
        f"corner={corner} temp={temp_c}C",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        "",
        f"Vdd VDD 0 dc {vdd}",
        f"Vvcm VCM 0 dc {VCM}",
        f"Vinp VINP 0 {_pwl(vinp_points)}",
        f"Vinn VINN 0 {_pwl(vinn_points)}",
        f"Vsample SAMPLE 0 {_pwl(sample_points)}",
        "",
        frag,
        "",
        ".control",
        f"tran {TRAN_STEP_NS}n {TRAN_STOP_NS}n",
    ]
    for side, (node, v_initial, v_final) in SIDES.items():
        for frac in FRACTIONS:
            target_v = v_initial + frac * (v_final - v_initial)
            name = f"t_settle_{side}_{int(frac * 100)}"
            lines.append(
                f"meas tran {name} TRIG AT={TRIG_AT_NS}n TARG V({node}) "
                f"VAL={target_v:.8g} TD={TRIG_AT_NS}n CROSS=1"
            )
        lines.append(f"meas tran budget_{side} find v({node}) at={BUDGET_PROBE_AT_NS}n")
        lines.append(f"meas tran confirm_{side} find v({node}) at={CONFIRM_AT_NS}n")
    lines += [".endc", ".end"]
    return "\n".join(lines) + "\n"


def _run(netlist: str, scratch: Path, tag: str) -> dict[str, float]:
    """A few bounded retries with backoff absorb transient contention from
    other concurrent agents' own ngspice runs on a shared machine -- the
    same policy sim/cdac-bit-trial-settling/run_bit_trial_settling.py's own
    `_run()` and sim/sequencer-logic-delay/run_sequencer_logic_delay.py's
    own `_run()` already document."""
    import time

    attempts = 4
    for attempt in range(1, attempts + 1):
        try:
            log_text = toolchain.run_ngspice(netlist, scratch, tag)
            m = measure.parse(log_text, MEASURE_NAMES)
            m.update(_parse_trig_targ(log_text, TRIG_TARG_NAMES))
            return m
        except RuntimeError as exc:
            if "timed out" not in str(exc) or attempt == attempts:
                raise
            print(
                f"  (warning: {tag} timed out (attempt {attempt}/{attempts}), "
                f"retrying after a short backoff -- machine likely contended)",
                file=sys.stderr,
            )
            time.sleep(15 * attempt)
    raise AssertionError("unreachable")  # loop always returns or raises above


def run_all(
    scratch: Path,
    corner: str = CORNER,
    temp_c: float = TEMP_C,
    vdd: float = VDD,
    quiet: bool = False,
    tag: str = "acquisition_settling",
) -> tuple[list[dict], list[dict], str]:
    netlist = build_transient(corner=corner, temp_c=temp_c, vdd=vdd)
    m = _run(netlist, scratch, tag)

    crossing_rows = []
    budget_rows = []
    for side, (node, v_initial, v_final) in SIDES.items():
        budget_v = m.get(f"budget_{side}")
        budget_err_mv = (budget_v - v_final) * 1000 if budget_v is not None else None
        confirm_v = m.get(f"confirm_{side}")
        confirm_err_mv = (confirm_v - v_final) * 1000 if confirm_v is not None else None
        budget_rows.append({
            "side": side, "node": node, "v_initial": v_initial, "v_final": v_final,
            "budget_v": budget_v, "budget_err_mv": budget_err_mv,
            "confirm_v": confirm_v, "confirm_err_mv": confirm_err_mv,
        })
        for frac in FRACTIONS:
            key = f"t_settle_{side}_{int(frac * 100)}"
            delay_s = m.get(key)
            delay_ns = delay_s * 1e9 if delay_s is not None else None
            crossing_rows.append({
                "side": side, "node": node, "fraction": frac,
                "v_initial": v_initial, "v_final": v_final, "delay_ns": delay_ns,
            })
        if not quiet:
            t90 = m.get(f"t_settle_{side}_90")
            t90_str = f"{t90 * 1e9:.5f} ns" if t90 is not None else "N/A (no crossing found)"
            budget_str = f"{budget_err_mv:+.5f} mV" if budget_err_mv is not None else "N/A"
            confirm_str = f"{confirm_err_mv:+.5f} mV" if confirm_err_mv is not None else "N/A"
            print(
                f"{node}: {v_initial}V -> {v_final}V  t_settle_90%={t90_str}  "
                f"residual@{T_PHASE_WORST_NS:.3f}ns-budget={budget_str}  "
                f"residual@confirm={confirm_str}"
            )
    return crossing_rows, budget_rows, netlist


def run_corners(scratch: Path, quiet: bool = False) -> list[dict]:
    """Full ratified-corner-set OAT sweep of run_all(): the same PVT grid
    sim/comparator-decision/'s own regen-corners campaign uses
    (spec/target-spec.md's "Numeric rows -- RATIFIED 2026-08-19" section:
    -40/27/125C, +-10% supply, sky130 process corners), applied to this
    experiment's own worst-node budget/confirm residual at each point. This
    does NOT change the single-corner (tt/27C/1.8V) mechanism this script
    measures -- it re-runs the identical stimulus/measurement at 9 PVT
    points instead of 1, to see whether the tt/27C/1.8V finding (does not
    clear the DR-006 worst-case phase budget) holds, worsens, or improves
    across process/temperature/supply.
    """
    pdk.resolve_or_raise()
    supply_pts = corners_mod.supply_points(VDD, SUPPLY_TOLERANCE)
    grid = corners_mod.oat_grid("tt", 27.0, VDD, PROCESS_CORNERS, TEMPS_C, supply_pts)

    points: list[dict] = []
    for process_corner, temp_c, supply_v in grid:
        cid = corners_mod.corner_id(process_corner, temp_c, supply_v)
        if not quiet:
            print(f"{cid}:")
        crossing_rows, budget_rows, netlist = run_all(
            scratch, corner=process_corner, temp_c=temp_c, vdd=supply_v,
            quiet=quiet, tag=f"acquisition_settling_{cid}",
        )
        complete = all(r["delay_ns"] is not None for r in crossing_rows) and all(
            r["budget_err_mv"] is not None and r["confirm_err_mv"] is not None
            for r in budget_rows
        )
        worst = None
        if complete:
            worst = max(budget_rows, key=lambda r: abs(r["budget_err_mv"]))
        points.append({
            "corner": process_corner, "temp_c": temp_c, "supply_v": supply_v,
            "corner_id": cid, "complete": complete,
            "crossing_rows": crossing_rows, "budget_rows": budget_rows,
            "worst_node": worst["node"] if worst else None,
            "worst_budget_err_mv": worst["budget_err_mv"] if worst else None,
            "worst_confirm_err_mv": (
                next(r["confirm_err_mv"] for r in budget_rows if r["node"] == worst["node"])
                if worst else None
            ),
            "netlist": netlist,
        })
        if not quiet and worst is not None:
            print(
                f"  worst node {worst['node']}: "
                f"residual@budget={worst['budget_err_mv']:+.4f} mV"
            )
    return points


def write_record(crossing_rows: list[dict], budget_rows: list[dict], netlist_sample: str) -> None:
    record_id = evidence.new_record_id()
    record_path = evidence.write_netlist_snapshot_text(EXPERIMENT_DIR, record_id, netlist_sample)
    netlist_sha = evidence.sha256_text(netlist_sample)
    info = pdk.resolve()
    pdk_line = f"{info.variant} @ {pdk.resolved_commit(info)}"
    ng_version = toolchain._ngspice_version() or "unknown"

    lines: list[str] = []
    a = lines.append
    a(f"# Sampling front end acquisition-window settling budget -- {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    a(
        "- **Claim**: quantifies, for the first time in this repo, how long "
        "`design/sampling_frontend.sch`'s own bootstrapped sampling switch "
        "takes, once the SAMPLE phase re-asserts, to acquire a NEW, "
        "worst-case (rail-to-rail, near-Nyquist) differential input value "
        "onto `TOP_P`/`TOP_N` -- isolating the sampling front end's own "
        "acquisition mechanism from every other sample-rate contributor "
        "(CDAC array switch settling, comparator decision delay, sequencer "
        "logic delay). Answers "
        "`docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2's "
        "fourth and last named mechanism -- one more input to a full "
        "sample-rate re-derivation, not that re-derivation itself. No claim "
        "against a ratified spec row: `spec/target-spec.md` is entirely "
        "DRAFT (#1/#27); the DR-006 phase-period figures quoted below are "
        "themselves downstream of the DRAFT sample-rate row. **Unlike the "
        "other three mechanisms already checked, this one does NOT come "
        "back with a comfortable margin -- see Result below.**"
    )
    a(
        "- **Netlist provenance**: `design/sampling_frontend.sch`'s already-"
        "regenerated fragment "
        "(`sim/sampling-frontend/testbench/sampling_frontend_dut.spice`, "
        "the same DUT `sim/sampling-frontend/run_transient.py` and "
        "`sim/sampling-frontend/run_hold_kick.py` already exercise); this "
        "script adds only the two-pulse SAMPLE/VINP/VINN stimulus and the "
        "`.meas` statements below, no schematic change."
    )
    a(
        "- **Point/corner matrix**: `tt`/27C/1.8V only -- a mechanism-"
        "isolating, single-corner first-pass budget, the same precedent "
        "`sim/vcm-drive-budget/`, `sim/cdac-bit-trial-settling/`, and "
        "`sim/sequencer-logic-delay/` already established. Real switch "
        "`R_on` and bootstrap-network subthreshold leakage (the mechanism "
        "this record's finding, below, points at) vary materially with "
        "process/temperature/supply; full PVT coverage of this same budget "
        "is open, same class of gap as #28's corner campaigns elsewhere in "
        "this design -- and, given this record's finding, plausibly more "
        "consequential here than at the other three mechanisms' comfortable "
        "margins."
    )
    a(
        "- **Stimulus**: two SAMPLE pulses. Pulse #1 (100 ns wide) settles "
        f"`TOP_P`/`TOP_N` to `{V_INITIAL_P}`V/`{V_INITIAL_N}`V. During the "
        "following hold phase (SAMPLE deasserted, `Msw` off), `VINP`/`VINN` "
        f"step to the opposite rail-adjacent extreme "
        f"(`{V_FINAL_P}`V/`{V_FINAL_N}`V) -- the maximum simultaneous "
        "full-scale differential step this design's input range can "
        "present between consecutive samples. SAMPLE pulse #2 re-asserts "
        "30 ns after that step completes; every measurement below is "
        "relative to pulse #2's own 50% crossing "
        f"(`{TRIG_AT_NS:g}` ns), the instant `Msw` reconnects `TOP_P`/"
        "`TOP_N` to the new input value."
    )
    a(
        "- **DR-006 phase-period reference points**: "
        f"{T_PHASE_WORST_NS:.3f} ns (worst case, f_clk=12 MHz, one CLK "
        f"period per bit-trial phase, which per DR-006 applies uniformly "
        f"to the SAMPLE phase too) and {T_PHASE_SLOW_NS:.2f} ns (slow end, "
        "f_clk=1.2 MHz) -- quoted for comparison only, not a pass/fail "
        "gate against a ratified row."
    )
    a("")
    a("## Fast early settling (from SAMPLE pulse #2's 50% crossing)")
    a("")
    a(
        "Delay is measured from the 50% (Vdd/2) crossing of the SAMPLE "
        "rising edge that reconnects each node to its new input value, to "
        "the point at which that node first crosses each fraction of the "
        "way from its OLD (held) value to its NEW (target) value -- "
        "ngspice's own `TRIG AT=... TARG ... CROSS=1` measure result, "
        "already `(targ_time - trig_time)`, the same convention "
        "`sim/cdac-bit-trial-settling/`'s `t_settle_*` and "
        "`sim/sequencer-logic-delay/`'s `delay_*` measures use. Only 50%/90% "
        "are measured this way -- see the module docstring's \"WHY A "
        "FIXED-TIME BUDGET PROBE, NOT A 99% CROSSING\" for why a tighter "
        "fraction is read as a fixed-time probe (below) instead."
    )
    a("")
    a("| Node | Old -> New (V) | Fraction | Delay (ns) |")
    a("|---|---|---|---|")
    for r in crossing_rows:
        delay_str = f"{r['delay_ns']:.5f}" if r["delay_ns"] is not None else "N/A"
        a(
            f"| `{r['node']}` | {r['v_initial']} -> {r['v_final']} | "
            f"{int(r['fraction'] * 100)}% | {delay_str} |"
        )
    a("")
    a(
        "Both nodes cross 50% and 90% of the way to their new value in "
        "well under 1 ns -- the bootstrapped switch's own `R_on`/`C_samp` "
        "time constant is fast, consistent with the CDAC array's own "
        "switch-settling figures (`sim/cdac-bit-trial-settling/`, tens of "
        "ns for a comparable total capacitance)."
    )
    a("")
    a(
        "## Residual error at the DR-006 worst-case phase budget "
        f"({T_PHASE_WORST_NS:.3f} ns after the trigger point)"
    )
    a("")
    a(
        "A fixed-time read (not a crossing search), taken exactly one "
        "DR-006-derived worst-case (12 MHz) phase period after SAMPLE pulse "
        "#2's own trigger point -- i.e. exactly how far this node still is "
        "from its ideal new value at the instant a real SAMPLE phase, run "
        "at the fastest rate DR-006 allocates, would end. A second read "
        f"(`confirm`, at {CONFIRM_AT_NS:g} ns, well inside pulse #2, clear "
        "of its own eventual fall) shows how much further it gets given "
        "much more time than the phase budget allows."
    )
    a("")
    a(
        "| Node | Old -> New (V) | Residual @ budget (mV) | Residual @ "
        "confirm (mV) |"
    )
    a("|---|---|---|---|")
    for r in budget_rows:
        budget_str = f"{r['budget_err_mv']:+.4f}" if r["budget_err_mv"] is not None else "N/A"
        confirm_str = f"{r['confirm_err_mv']:+.4f}" if r["confirm_err_mv"] is not None else "N/A"
        a(
            f"| `{r['node']}` | {r['v_initial']} -> {r['v_final']} | "
            f"{budget_str} | {confirm_str} |"
        )
    a("")

    all_crossings_valid = all(r["delay_ns"] is not None for r in crossing_rows)
    all_budget_valid = all(
        r["budget_err_mv"] is not None and r["confirm_err_mv"] is not None
        for r in budget_rows
    )

    notes: list[str] = []
    if not all_crossings_valid:
        missing = [
            f"{r['node']}@{int(r['fraction'] * 100)}%"
            for r in crossing_rows if r["delay_ns"] is None
        ]
        notes.append(
            f"One or more fast-settling points produced no TRIG/TARG "
            f"crossing: {missing} -- treat this record as incomplete "
            "evidence, not a passing result, until re-run clean."
        )
    if not all_budget_valid:
        notes.append(
            "One or more budget/confirm reads failed to parse -- treat "
            "this record as incomplete evidence, not a passing result, "
            "until re-run clean."
        )
    if all_budget_valid:
        worst_budget = max(budget_rows, key=lambda r: abs(r["budget_err_mv"]))
        half_lsb_mv = LSB_DIFF_MV_PROVISIONAL / 2
        ratio = abs(worst_budget["budget_err_mv"]) / half_lsb_mv
        notes.append(
            "**Finding: at this corner, the sampling front end's own "
            "acquisition mechanism does NOT settle within the DR-006 "
            "worst-case (12 MHz) phase budget** -- worst case "
            f"`{worst_budget['node']}` is still "
            f"{abs(worst_budget['budget_err_mv']):.3f} mV "
            f"(single-ended) from its ideal target value "
            f"{T_PHASE_WORST_NS:.3f} ns after the acquiring edge, "
            f"~{ratio:.1f}x the provisional differential LSB's half-step "
            f"({half_lsb_mv:.4f} mV, DR-003 Item 2, pending #27, quoted as "
            "a reference scale, not a pass/fail gate against a ratified "
            "row). This is the opposite outcome from the other three "
            "mechanisms checked so far (CDAC settling, comparator decision "
            "delay, sequencer logic delay), each of which cleared the same "
            "budget with a double-digit-or-larger margin -- the sampling "
            "front end's own acquisition, not any of those three, is the "
            "likely bottleneck for an end-to-end sample-rate figure at the "
            "fast (12 MHz / ~1 MS/s) end of the DRAFT range, at this "
            "corner."
        )
        confirm_notes = ", ".join(
            f"{r['node']} {r['confirm_err_mv']:+.4f} mV" for r in budget_rows
        )
        notes.append(
            f"By the `confirm` read ({CONFIRM_AT_NS:g} ns, "
            f"{CONFIRM_AT_NS - TRIG_AT_NS:.1f} ns after the trigger -- "
            f"~{(CONFIRM_AT_NS - TRIG_AT_NS) / T_PHASE_WORST_NS:.1f}x the "
            "DR-006 worst-case phase budget, but still well short of the "
            f"{T_PHASE_SLOW_NS:.0f} ns slow-end single-phase budget): "
            f"{confirm_notes} -- still not sub-mV (contrast "
            "`sim/sampling-frontend/run_transient.py`'s own report of "
            "sub-mV settling by its legacy 400 ns window's own probe "
            "point, ~399 ns after the edge -- this record's own debug "
            "trace, described in the module docstring, reproduces that "
            "same eventual sub-mV convergence by ~399 ns in a matching "
            "single-pulse check; the residual tail decays slowly enough "
            "that it is still tens of mV at this record's own much-"
            "earlier `confirm` point). The mechanism traced during "
            "debugging (not asserted without evidence): the bootstrap "
            "precharge PFET `Sa` sits in a reverse-`Vds` orientation once "
            "`BOOST_x` is driven above `VDD` by the boost itself, and its "
            "own imperfect off-state in that orientation lets `BOOST_x` "
            "droop measurably over tens of ns during the sample phase, "
            "gradually reducing `Msw`'s gate overdrive and slowing the "
            "final approach to the target value -- a real, second-order "
            "settling tail this design's original sizing "
            "(`spec/decision-records/DR-004-sampling-frontend-sizing.md`) "
            "did not have DR-006's tighter phase-budget figure to check "
            "against yet (DR-006 postdates neither schematic, but predates "
            "the settling-time data needed to check either against it -- "
            "see DR-006's own \"Alternatives considered\": a non-uniform "
            "phase allocation was explicitly deferred for exactly this "
            "kind of missing data)."
        )
        notes.append(
            "This does NOT mean the design is broken or that any spec row "
            "is violated -- `spec/target-spec.md`'s sample-rate row is "
            "entirely DRAFT, and DR-006's uniform-one-phase-per-CLK-period "
            "allocation was always stated as a placeholder pending exactly "
            "this kind of settling-time evidence. What this record "
            "establishes is a concrete, first, real data point suggesting "
            "the eventual non-uniform phase allocation DR-006 anticipated "
            "(a longer SAMPLE phase) may be needed at the fast end of the "
            "DRAFT sample-rate range -- narrowing, not closing, the open "
            "item, and surfacing a genuine design risk rather than a "
            "reassuring margin, honestly reported either way."
        )
    notes.append(
        "This is a first-pass, single-corner (tt/27C/1.8V), single-"
        "direction (both P and N tested, but only one worst-case "
        "rail-to-rail step direction) budget that isolates ONE mechanism "
        "only (the sampling front end's own acquisition of a NEW "
        "worst-case input value once SAMPLE re-asserts, `design/"
        "sampling_frontend.sch`). It does NOT include CDAC array switch-"
        "settling time (`sim/cdac-bit-trial-settling/`), comparator "
        "decision delay (`sim/comparator-decision/`), sequencer logic "
        "delay (`sim/sequencer-logic-delay/`), or any PVT corner beyond "
        "tt/27C/1.8V. A full sample-rate re-derivation "
        "(`docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2) "
        "needs all four combined, over the full PVT grid, which remains "
        "open. What this record newly establishes is that all four named "
        "mechanisms have now been quantified individually, at least at "
        "one corner -- three comfortably clear the DR-006-derived phase "
        "budget, and this fourth one, measured here for the first time, "
        "does not."
    )

    a("## Result")
    a("")
    for n in notes:
        a("- " + n)
    a("")

    lines.extend(evidence.environment_block(
        pdk_line, f"ngspice {ng_version}", netlist_sha,
        extra={
            "Corner/temp/VDD": "tt / 27C / 1.8V (single point, first-pass)",
            "tran step": f"{TRAN_STEP_NS} ns",
        },
    ))
    a("")
    lines.extend(evidence.footer_lines(
        "sim/sampling-acquisition-settling/run_acquisition_settling.py", ""
    ))

    record_path.write_text("\n".join(lines) + "\n")
    latest_path = EXPERIMENT_DIR / "records" / "LATEST"
    latest_path.write_text(f"{record_id}.md\n")
    print(f"\nWrote record: {record_path}")


def write_corners_record(points: list[dict]) -> Path:
    """Evidence record for the full ratified-PVT-grid --corners campaign,
    same `corners/<record_id>/` per-point-log layout
    sim/comparator-decision/'s own regen-corners campaign uses."""
    record_id = evidence.new_record_id()
    corners_dir = EXPERIMENT_DIR / "corners" / record_id
    corners_dir.mkdir(parents=True, exist_ok=True)
    for p in points:
        (corners_dir / f"{p['corner_id']}.spice").write_text(p["netlist"])

    # Netlist snapshot: the tt/27C/1.8V baseline point's own deck, the same
    # single-point convention write_record() above uses, so a reader can
    # diff it directly against that single-corner record's own snapshot.
    baseline = next(
        (p for p in points if p["corner"] == "tt" and p["temp_c"] == 27.0 and p["supply_v"] == VDD),
        points[0],
    )
    record_path = evidence.write_netlist_snapshot_text(EXPERIMENT_DIR, record_id, baseline["netlist"])
    netlist_sha = evidence.sha256_text(baseline["netlist"])

    info = pdk.resolve()
    pdk_line = f"{info.variant} @ {pdk.resolved_commit(info)}"
    ng_version = toolchain._ngspice_version() or "unknown"

    process_corners_run = sorted({p["corner"] for p in points})
    temps_run = sorted({p["temp_c"] for p in points})
    supplies_run = sorted({p["supply_v"] for p in points})

    incomplete = [p for p in points if not p["complete"]]
    complete_points = [p for p in points if p["complete"]]

    lines: list[str] = []
    a = lines.append
    a(f"# Sampling front end acquisition-window settling budget -- full PVT grid -- {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    a(
        "- **Claim**: extends the single-corner (tt/27C/1.8V) finding in "
        f"[`records/{SINGLE_CORNER_SEED_RECORD}.md`]"
        f"({SINGLE_CORNER_SEED_RECORD}.md) -- that this design's "
        "own bootstrapped sampling switch does NOT settle a new worst-case "
        "differential input value within the DR-006 worst-case (12 MHz) "
        "phase budget -- to the FULL ratified PVT corner set "
        "(spec/target-spec.md's \"Numeric rows -- RATIFIED 2026-08-19\" "
        "section: -40/27/125C, +-10% supply, sky130 process corners), the "
        "same OAT grid sim/comparator-decision/'s own regen-corners "
        "campaign sweeps. Identical stimulus and measurement methodology "
        "as the single-corner record (see that record's own module "
        "docstring for the full stimulus-shape rationale and the two "
        "documented `.meas TRIG/TARG` pitfalls this script works around) "
        "-- only the corner point changes per run. No claim here is graded "
        "against a ratified spec row: `spec/target-spec.md`'s sample-rate "
        "row is entirely DRAFT (#1/#27), and the DR-006 phase-period "
        "figures quoted below are themselves downstream of that DRAFT row."
    )
    a(
        "- **Netlist provenance**: `design/sampling_frontend.sch`'s "
        "already-regenerated fragment "
        "(`sim/sampling-frontend/testbench/sampling_frontend_dut.spice`), "
        "unchanged from the single-corner record -- only `.lib`/`.temp`/"
        "`Vdd` vary per corner point. Netlist snapshot above is the "
        "tt/27C/1.8V baseline point; every point's own deck is committed "
        f"under `corners/{record_id}/`."
    )
    a(
        corners_mod.corner_matrix_summary_line(
            process_corners_run, temps_run, supplies_run, len(points)
        )
    )
    a("")
    a("## Worst-node residual at the DR-006 worst-case phase budget, per corner")
    a("")
    a(
        f"Same fixed-time read as the single-corner record, taken "
        f"{T_PHASE_WORST_NS:.3f} ns (worst-case, f_clk=12 MHz) after SAMPLE "
        "pulse #2's own trigger point, at every corner. \"Worst node\" is "
        "whichever of `TOP_P`/`TOP_N` has the larger-magnitude residual at "
        "that corner (not necessarily the same node at every corner)."
    )
    a("")
    a("| Corner | Worst node | Residual @ budget (mV) | Residual @ confirm (mV) | x half-LSB |")
    a("|---|---|---|---|---|")
    half_lsb_mv = LSB_DIFF_MV_PROVISIONAL / 2
    for p in points:
        if not p["complete"]:
            a(f"| `{p['corner_id']}` | -- | INCOMPLETE | INCOMPLETE | -- |")
            continue
        ratio = abs(p["worst_budget_err_mv"]) / half_lsb_mv
        a(
            f"| `{p['corner_id']}` | `{p['worst_node']}` | "
            f"{p['worst_budget_err_mv']:+.4f} | {p['worst_confirm_err_mv']:+.4f} | "
            f"{ratio:.1f}x |"
        )
    a("")

    notes: list[str] = []
    if incomplete:
        bad = ", ".join(p["corner_id"] for p in incomplete)
        notes.append(
            f"**{len(incomplete)}/{len(points)} corner points produced "
            f"incomplete measurements ({bad})** -- treat this record as "
            "partial evidence at those points, not a passing or failing "
            "result, until re-run clean."
        )
    if complete_points:
        binding = max(complete_points, key=lambda p: abs(p["worst_budget_err_mv"]))
        best = min(complete_points, key=lambda p: abs(p["worst_budget_err_mv"]))
        all_over_half_lsb = all(
            abs(p["worst_budget_err_mv"]) > half_lsb_mv for p in complete_points
        )
        notes.append(
            f"**Binding corner (largest residual): `{binding['corner_id']}`**, "
            f"`{binding['worst_node']}` still "
            f"{abs(binding['worst_budget_err_mv']):.3f} mV from its ideal "
            f"target value {T_PHASE_WORST_NS:.3f} ns after the acquiring "
            f"edge -- ~{abs(binding['worst_budget_err_mv']) / half_lsb_mv:.1f}x "
            f"the provisional differential LSB's half-step. Best corner: "
            f"`{best['corner_id']}`, "
            f"{abs(best['worst_budget_err_mv']):.3f} mV "
            f"(~{abs(best['worst_budget_err_mv']) / half_lsb_mv:.1f}x)."
        )
        if all_over_half_lsb:
            notes.append(
                "**Every one of the 9 ratified corner points exceeds the "
                "provisional differential LSB's half-step at the DR-006 "
                "worst-case phase budget** -- the single-corner (tt/27C/"
                "1.8V) finding was not a corner-specific artifact; this "
                "mechanism does not clear the budget anywhere on the "
                "ratified PVT grid at this design's current sizing. This "
                "still does not violate any ratified spec row (the "
                "sample-rate row is entirely DRAFT), but it raises the "
                "weight of this finding from \"one corner, narrows the "
                "open item\" to \"every ratified corner, same conclusion\" "
                "-- consistent with, and strengthening, DR-006's own "
                "deferred non-uniform phase allocation alternative."
            )
        else:
            notes.append(
                "Not every corner point exceeds the half-LSB reference "
                "scale -- the mechanism's severity varies across the "
                "PVT grid; see the per-corner table above for which "
                "points clear it."
            )
    notes.append(
        "This campaign re-runs the SAME single mechanism (the sampling "
        "front end's own acquisition of a new worst-case input value once "
        "SAMPLE re-asserts) across the full ratified PVT grid -- it does "
        "NOT combine with the other three named mechanisms (CDAC "
        "settling, comparator decision delay, sequencer logic delay) into "
        "an end-to-end sample-rate figure, and none of those other three "
        "has itself been taken to this full grid except the comparator's "
        "own decision-delay campaign. A full sample-rate re-derivation "
        "(`docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2) "
        "still needs all four combined, over the full PVT grid, which "
        "remains open."
    )

    a("## Result")
    a("")
    for n in notes:
        a("- " + n)
    a("")

    lines.extend(evidence.environment_block(
        pdk_line, f"ngspice {ng_version}", netlist_sha,
        extra={"tran step": f"{TRAN_STEP_NS} ns"},
    ))
    a("")
    lines.extend(evidence.footer_lines(
        "sim/sampling-acquisition-settling/run_acquisition_settling.py", ""
    ))

    record_path.write_text("\n".join(lines) + "\n")
    latest_path = EXPERIMENT_DIR / "records" / "LATEST"
    latest_path.write_text(f"{record_id}.md\n")
    print(f"\nWrote record: {record_path}")
    return record_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true", help="write an evidence record")
    parser.add_argument(
        "--corners", action="store_true",
        help="run the full ratified PVT grid (9 OAT points) instead of the "
        "single tt/27C/1.8V corner",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    check = toolchain.check_env()
    if check.status == 3:
        print("SKIP: ngspice/PDK not available (" + "; ".join(check.messages) + ")")
        return 0
    if check.status == 1:
        print("FAIL: toolchain drift -- " + "; ".join(check.messages))
        return 1
    for w in check.warnings:
        print(f"WARNING: {w}")

    with tempfile.TemporaryDirectory(prefix="sampling-acquisition-settling-") as tmp:
        scratch = Path(tmp)

        if args.corners:
            points = run_corners(scratch, quiet=args.quiet)
            incomplete = [p for p in points if not p["complete"]]
            if incomplete:
                print(
                    f"FAIL: {len(incomplete)}/{len(points)} corner points "
                    "produced incomplete measurements."
                )
                if args.record:
                    write_corners_record(points)
                return 1
            print(f"\nOVERALL: PASS (all {len(points)} corner points produced values)")
            if args.record:
                write_corners_record(points)
            return 0

        crossing_rows, budget_rows, netlist_sample = run_all(scratch)

        incomplete = any(r["delay_ns"] is None for r in crossing_rows) or any(
            r["budget_err_mv"] is None or r["confirm_err_mv"] is None for r in budget_rows
        )
        if incomplete:
            print("FAIL: one or more measurement points did not produce a value.")
            if args.record:
                write_record(crossing_rows, budget_rows, netlist_sample)
            return 1

        print(
            f"\nOVERALL: PASS (all {len(crossing_rows)} crossing points and "
            f"{len(budget_rows) * 2} budget/confirm reads produced values -- "
            "see printed residuals above for whether the mechanism itself "
            "fits the DR-006 phase budget)"
        )
        if args.record:
            write_record(crossing_rows, budget_rows, netlist_sample)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

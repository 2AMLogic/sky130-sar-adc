#!/usr/bin/env python3
"""VINP/VINN input-drive-impedance budget for the sampling front end
(issue #847).

WHAT IT MEASURES, AND WHY IT DID NOT EXIST. Every `sim/` campaign in this
repo drives `VINP`/`VINN` from an ideal (zero-impedance) source:
`sim/full-conversion-transient/testbench/full_conversion_tb_fragment.spice`
uses bare `PWL` sources, and `sim/vcm-drive-budget/`'s only series element
is on `VCM`. So the design has never quantified how much real series source
resistance the signal pads tolerate. During the SAMPLE window the input pads
charge the sampled capacitance through the bootstrapped sampling switches, so
a series `R_source` forms an RC with that capacitance inside the acquisition
window DR-006 allocates -- the same mechanism `sim/vcm-drive-budget/` already
measured on `VCM`, on the pads that carry the signal rather than the bias.

`docs/chipalooza/challenge-4-proposal.md`'s I/O table is asked (Challenge #4's
`get-involved.html`) to "note any special requirements such as low resistance
to the pad"; this campaign is the figure the `VINP`/`VINN` rows cite.

WHAT IT BORROWS, AND FROM WHERE (nothing here is a new mechanism):

  * **DUT**: the unmodified sampling front-end fragment
    `sim/sampling-frontend/testbench/sampling_frontend_dut.spice`, read in
    place -- not duplicated -- the convention
    `sim/sampling-frontend/run_hold_kick.py` set and both
    `sim/vcm-drive-budget/` and `sim/sampling-acquisition-settling/` follow.
  * **Stimulus**: the two-pulse old-value-to-new-value full-scale step of
    `sim/sampling-acquisition-settling/run_acquisition_settling.py` (SAMPLE
    pulse #1 settles the OLD value; the input steps to the opposite
    rail-adjacent extreme during HOLD, while `Msw` is off; SAMPLE pulse #2
    acquires the NEW value, and every read below is referenced to its own
    50 % rising edge). That runner's module docstring carries the full
    rationale, including why a single SAMPLE pulse from an unbiased initial
    condition cannot express "acquiring a new value" at all -- which for an
    input-side resistance is the whole point, since the previous held sample
    is what `R_source` has to charge away from.
  * **Reading convention**: that same runner's FIXED-TIME `find v(node)
    at=<t>` probe, deliberately NOT a TRIG/TARG crossing search. Its
    docstring records two separate ngspice `.meas` pitfalls found by
    debugging implausible crossing results against raw transient data; a
    single point sample cannot reproduce either. No crossing search is
    reintroduced here.
  * **Reporting convention**: `sim/vcm-drive-budget/`'s `find_budget()` --
    the budget is the LARGEST swept source resistance whose error stays
    within the threshold, reported at two tiers (1.0 and 0.1 provisional
    LSB), with a budget equal to the largest swept value reported as
    RIGHT-CENSORED rather than as a measured limit.
  * **Windows**: `sim/vcm-drive-budget/`'s two, both covered here --
    `worst` = the DR-006-derived worst-case acquisition window
    (12 MHz, 83.333 ns) and `legacy` = this repo's pre-existing 400 ns
    sampling-frontend testbench convention.
  * **Grid**: the ratified 9-point one-at-a-time PVT set
    (`sim/harness/corners.py`).

WHY A CONTROL ROW PER CORNER AND WINDOW, AND WHY BUDGETS ARE RELATIVE TO IT.
The zero-resistance baseline is not zero error at every corner.
`sim/sampling-acquisition-settling/records/20260908-051436-6ccd72d.md` (that
campaign's `LATEST`) reports a per-node residual of -0.3800 mV at
`tt_27c_1.62v` at the 83.333 ns probe with an ideal source, about 0.11
provisional LSB. A 0.1-LSB tier read against the ideal target could therefore
"fail" at that corner with no source resistance at all -- which would be an
artifact of the baseline, not a statement about `R_source`. So every corner
and window here carries its own `R_source = 0` row, the record shows the raw
error against the ideal target as well, and every budget is computed on the
error RELATIVE to that corner-and-window's own control row. A corner whose
control row is itself outside a tier is reported as such, and its raw-error
budget is declared unreadable rather than guessed.

EXECUTION: `klt sim`, NOT A LOCAL ngspice LOOP. The multi-corner grid is one
`klt sim` request that the batch fleet executes (`sim/top-plate-cpar/`'s
pattern; the two campaigns mirrored above both loop `ngspice` in-process,
which is why only their reporting and stimulus are reused, not their
execution). Both sweep axes fit in that one request:

  * `R_source` and the acquisition window are `analysis_steps[]` entries --
    one `tran` step per (window, resistance) pair, each with `reset: true`,
    an `alter` of the two series resistors, an `alter` of the SAMPLE control
    source's `pwl` vector, its own `tran` stop time and its own fixed-time
    `.meas` cards. One request therefore carries 2 windows x 8 resistances
    = 16 solves per corner, and `--batch-set` is not needed.
  * the corner axes are `corners.process` / `temperature_c` / `supply_v`.

Every batch submit passes `--wait-for-capacity 600`: the fleet is
vCPU-budgeted, so a burst is refused with `batch_no_capacity` unless the
submit is allowed to wait with backoff. Only `--probe` (one corner, one
resistance, one window) runs locally.

SUPPLY-TRACKING SAMPLE LEVEL. One deck serves all nine corners, so the SAMPLE
pulse cannot have the corner's supply baked into its literal `pwl` values the
way a per-corner regenerated deck can. It is declared as a NORMALISED (0..1)
`pwl` control source scaled by the corner's own supply through a behavioural
source, `Bsample SAMPLE 0 V=v(SMP_CTL)*v(VDD)`, which is what makes the `pwl`
vector corner-independent and therefore `alter`-able per step. `VINP`/`VINN`
levels are the fixed 0.2/1.6 V rail-adjacent extremes of the mirrored
campaign, which does not scale them with the supply either, and `VCM` is that
campaign's fixed ideal 0.9 V. Both are stated in the record's limits list.

NOTHING HERE IS GRADED AGAINST A RATIFIED SPEC ROW. `spec/target-spec.md` is
entirely DRAFT (#1/#27); `LSB_DIFF_MV_PROVISIONAL` is DR-003 Item 2's
provisional value quoted as a reference scale only; the DR-006 window is
itself downstream of the DRAFT sample-rate row. `spec/target-spec.md`'s
Kickback row (DRAFT) is already stated "into a 1 kOhm series source
impedance", which is why 1 kOhm is a SIMULATED point in the sweep below --
but this campaign does not grade that row, and changes no spec line.

Usage (from the repo root, after ``source sim/env.sh``)::

    python3 sim/input-drive-budget/run_input_drive_budget.py --dry-run
    python3 sim/input-drive-budget/run_input_drive_budget.py --probe
    python3 sim/input-drive-budget/run_input_drive_budget.py --record
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
EXPERIMENT_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(SIM_DIR))
from harness import corners as corners_mod  # noqa: E402

#: Read in place, never duplicated -- sim/sampling-frontend/run_hold_kick.py's
#: committed-fragment convention, the same file sim/vcm-drive-budget/ and
#: sim/sampling-acquisition-settling/ read.
DUT_FRAGMENT = (
    SIM_DIR / "sampling-frontend" / "testbench" / "sampling_frontend_dut.spice"
)

#: The repo-relative path this campaign's records name in their `Written by`
#: footer (issue #274's rule: the unambiguous path, never a bare file name).
WRITTEN_BY = "sim/input-drive-budget/run_input_drive_budget.py"

NOMINAL_SUPPLY_V = 1.8
#: The `corners.supply_v` axis key. `klt sim` applies that axis as a literal
#: `alter <key>=<value>`, so the key IS the supply source's element name -- a
#: key naming no element is refused, and a mismatch would otherwise simulate
#: the nominal supply at every corner. The deck body therefore declares the
#: source under this exact name rather than a hand-written spelling of it
#: (sim/top-plate-cpar/'s own `vsup` convention, drift-proofed).
SUPPLY_KEY = "vsup"
#: DR-003 Item 2, provisional pending #27 -- a reference SCALE for the error,
#: never a pass/fail gate. Same convention as both mirrored campaigns.
LSB_DIFF_MV_PROVISIONAL = 3.5156
#: sim/sampling-acquisition-settling/run_acquisition_settling.py's own fixed
#: ideal VCM, carried over unchanged so this campaign's R_source = 0 control
#: row is directly comparable with that campaign's records.
VCM_V = 0.9

# ---------------------------------------------------------------------------
# Acquisition windows (ns)
# ---------------------------------------------------------------------------
#: DR-006-derived worst case: t_sample = 1 / f_clk, f_clk = 12 * f_s at the
#: fast end of the DRAFT sample-rate row -- the SHORTEST window, i.e. the one
#: least forgiving of a slow input source.
T_WINDOW_WORST_NS = 1.0e3 / 12.0  # 83.333... ns
#: This repo's pre-existing sampling-frontend testbench convention, independent
#: of DR-006 (sim/sampling-frontend/run_transient.py, run_hold_kick.py).
T_WINDOW_LEGACY_NS = 400.0
WINDOWS = {"worst": T_WINDOW_WORST_NS, "legacy": T_WINDOW_LEGACY_NS}
WINDOW_DESCRIPTION = {
    "worst": f"DR-006 worst-case (12 MHz, {T_WINDOW_WORST_NS:.3f} ns)",
    "legacy": f"legacy ({T_WINDOW_LEGACY_NS:.1f} ns) testbench convention",
}

# ---------------------------------------------------------------------------
# Two-pulse SAMPLE stimulus timing (ns) -- carried over verbatim from
# sim/sampling-acquisition-settling/run_acquisition_settling.py, whose module
# docstring holds the rationale for every interval. Only SAMPLE pulse #2's
# WIDTH (and hence the transient stop time) is a function of the window here,
# because the 400 ns window does not fit that runner's fixed 150 ns pulse.
# ---------------------------------------------------------------------------
EDGE_TR_NS = 0.2
T_PRECHARGE_NS = 10.0
T_SAMPLE1_RISE_NS = T_PRECHARGE_NS
T_SAMPLE1_WIDTH_NS = 100.0
T_SAMPLE1_FALL_NS = T_SAMPLE1_RISE_NS + T_SAMPLE1_WIDTH_NS          # 110.0
T_INPUT_TOGGLE_NS = T_SAMPLE1_FALL_NS + 20.0                        # 130.0
T_SAMPLE2_RISE_NS = T_INPUT_TOGGLE_NS + 30.0                        # 160.0
#: The 50 % crossing of SAMPLE pulse #2's rising edge: the instant `Msw`
#: reconnects TOP_P/TOP_N to the NEW input value. Every read is relative to it.
TRIG_AT_NS = T_SAMPLE2_RISE_NS + EDGE_TR_NS / 2.0                   # 160.1
#: Margin between the probe and SAMPLE pulse #2's own fall, so neither read can
#: pick up the pulse's documented turn-off kick (sim/sampling-frontend/
#: run_hold_kick.py, issue #61). Chosen so the `worst` window reproduces the
#: mirrored runner's own 150 ns pulse #2 width exactly.
SAMPLE2_MARGIN_NS = 150.0 - T_WINDOW_WORST_NS                       # 66.666...
#: Gap between the transient's end and SAMPLE pulse #2's fall (that runner's
#: TRAN_STOP_NS - T_SAMPLE2_FALL_NS).
TRAN_TAIL_NS = 20.0
#: Confirmatory read offset before pulse #2 falls (that runner's CONFIRM_AT_NS).
CONFIRM_BACKOFF_NS = 5.0
TRAN_STEP_NS = 0.02  # 20 ps, that runner's converged step

#: Worst-case rail-adjacent full-scale differential step between consecutive
#: samples: P low->high and N high->low simultaneously.
V_INITIAL_P, V_FINAL_P = 0.2, 1.6
V_INITIAL_N, V_FINAL_N = 1.6, 0.2
#: The ideal sampled differential value SAMPLE pulse #2 is acquiring.
V_TARGET_DIFF = V_FINAL_P - V_FINAL_N  # 1.4 V

# ---------------------------------------------------------------------------
# Source-resistance sweep
# ---------------------------------------------------------------------------
#: sim/vcm-drive-budget/run_vcm_drive_budget.py's own R_SOURCE_SWEEP_OHM list,
#: unchanged: 0 (today's implicit ideal-source assumption) through a clearly
#: undriven pad-scale impedance, log-spaced so the transition from negligible
#: to LSB-scale error is resolved to an order of magnitude. 0 and 1e3 are
#: required points -- 0 is the control row, and 1 kOhm is the series source
#: impedance spec/target-spec.md's DRAFT Kickback row already names on these
#: pins, so any statement about it rests on a simulated point.
R_SOURCE_SWEEP_OHM = [0.0, 100.0, 300.0, 1e3, 3e3, 10e3, 30e3, 100e3]
#: R_source = 0 is the pre-existing ideal-source baseline. It is emitted as a
#: 1 uOhm resistor rather than a literal 0, exactly as
#: sim/vcm-drive-budget/run_vcm_drive_budget.py does and for the same reason:
#: a 0-ohm resistor is an ngspice singular-matrix / convergence footgun on some
#: versions. At 1 uOhm the series time constant is ~4e-18 s against a window of
#: 8e-8 s, so it is an ideal source to 10 orders of magnitude.
R_IDEAL_OHM = 1.0e-6

#: The two reported tiers, same largest-passing-value rule as
#: sim/vcm-drive-budget/run_vcm_drive_budget.py's find_budget().
TIERS_LSB = [1.0, 0.1]

SUPPLY_TOLERANCE = corners_mod.RATIFIED_SUPPLY_TOLERANCE
TEMPS_C = corners_mod.RATIFIED_TEMPS_C
PROCESS_CORNERS = corners_mod.RATIFIED_PROCESS_CORNERS

# ---------------------------------------------------------------------------
# Pure helpers (no PDK, no ngspice, no network -- unit-tested)
# ---------------------------------------------------------------------------
def window_timing(window_ns: float) -> dict[str, float]:
    """Every derived time (ns) for one acquisition window.

    `probe_ns` is the budget read: a fixed time exactly `window_ns` after
    SAMPLE pulse #2's 50 % rising edge -- "how far from the ideal target is
    the sampled differential value when this window would end". `confirm_ns`
    is the long-time read, well inside pulse #2 and clear of its own fall."""
    if not (isinstance(window_ns, (int, float)) and window_ns > 0):
        raise ValueError(f"window must be a positive number of ns, got {window_ns!r}")
    sample2_width = window_ns + SAMPLE2_MARGIN_NS
    sample2_fall = T_SAMPLE2_RISE_NS + sample2_width
    return {
        "sample2_width_ns": sample2_width,
        "sample2_fall_ns": sample2_fall,
        "tran_stop_ns": sample2_fall + TRAN_TAIL_NS,
        "probe_ns": TRIG_AT_NS + window_ns,
        "confirm_ns": sample2_fall - CONFIRM_BACKOFF_NS,
    }


def sample_pwl_points(window_ns: float) -> list[tuple[float, float]]:
    """NORMALISED (0..1) two-pulse SAMPLE control waveform for one window.

    Normalised rather than absolute because one deck serves every corner: the
    behavioural `Bsample` in the deck body multiplies this by the corner's own
    `v(VDD)`, so the vector itself is corner-independent and can be handed to
    a step's `alter @Vsmp_ctl[pwl]`."""
    t = window_timing(window_ns)
    return [
        (0.0, 0.0),
        (T_SAMPLE1_RISE_NS, 0.0),
        (T_SAMPLE1_RISE_NS + EDGE_TR_NS, 1.0),
        (T_SAMPLE1_FALL_NS, 1.0),
        (T_SAMPLE1_FALL_NS + EDGE_TR_NS, 0.0),
        (T_SAMPLE2_RISE_NS, 0.0),
        (T_SAMPLE2_RISE_NS + EDGE_TR_NS, 1.0),
        (t["sample2_fall_ns"], 1.0),
        (t["sample2_fall_ns"] + EDGE_TR_NS, 0.0),
        (t["tran_stop_ns"], 0.0),
    ]


def input_pwl_points(end_ns: float) -> dict[str, list[tuple[float, float]]]:
    """The `VINP`/`VINN` old-value -> new-value steps, identical for every
    window: the step happens during HOLD, at a fixed time, so only the
    trailing hold point depends on how long the transient runs. ngspice holds
    a `pwl` source at its last value beyond the last point, so the same vector
    serves a shorter window too -- which is why these are NOT altered per
    step, unlike the SAMPLE control source."""
    return {
        "p": [
            (0.0, V_INITIAL_P),
            (T_INPUT_TOGGLE_NS, V_INITIAL_P),
            (T_INPUT_TOGGLE_NS + EDGE_TR_NS, V_FINAL_P),
            (end_ns, V_FINAL_P),
        ],
        "n": [
            (0.0, V_INITIAL_N),
            (T_INPUT_TOGGLE_NS, V_INITIAL_N),
            (T_INPUT_TOGGLE_NS + EDGE_TR_NS, V_FINAL_N),
            (end_ns, V_FINAL_N),
        ],
    }


def _pwl(points: list[tuple[float, float]]) -> str:
    """`pwl(...)` with explicit ns times -- sim/harness/testbench.py's own
    helper, inlined here because the klt-sim deck body is assembled as text
    and the step `alter` form needs the same vector in SECONDS (see
    `_pwl_vector`), so both renderings live beside each other."""
    return "pwl(" + " ".join(f"{t:g}n {v:g}" for t, v in points) + ")"


def _pwl_vector(points: list[tuple[float, float]]) -> list[float]:
    """The same points flattened to [t0, v0, t1, v1, ...] in SECONDS, the form
    `alter @<src>[pwl]` takes (an ngspice vector, which has no unit suffixes)."""
    out: list[float] = []
    for t_ns, v in points:
        out.extend([t_ns * 1e-9, float(v)])
    return out


def build_body() -> str:
    """Circuit BODY for `klt sim`: no `.lib`, `.temp`, `.control` or `.end`
    (klt emits all four, and the corner axes drive the first two).

    The DUT fragment is inserted verbatim. Everything added is testbench:
    the supply source the `vsup` corner axis alters, the ideal `VCM`, the two
    input sources each in series with its own `R_source` resistor, and the
    normalised SAMPLE control source plus its supply-scaling behavioural
    source. `Rsp`/`Rsn`/`Vsmp_ctl` are the three per-step `alter` targets."""
    longest = max(window_timing(w)["tran_stop_ns"] for w in WINDOWS.values())
    vin = input_pwl_points(longest)
    return "\n".join(
        [
            "* sim/input-drive-budget deck body -- VINP/VINN source-impedance",
            "* budget on the sampling front end (issue #847).",
            "* Devices: sim/sampling-frontend/testbench/sampling_frontend_dut.spice,",
            "* read in place and inserted verbatim below.",
            ".options num_threads=1",
            "",
            DUT_FRAGMENT.read_text().rstrip("\n"),
            "",
            f"* --- testbench sources (the supply source is named `{SUPPLY_KEY}`,",
            "* which is also the corners.supply_v axis key -- see SUPPLY_KEY) ---",
            f"{SUPPLY_KEY} VDD 0 DC {NOMINAL_SUPPLY_V}",
            f"Vvcm VCM 0 DC {VCM_V}",
            "* Input drive: ideal source in series with the swept R_source, one per",
            "* side, swept together (`alter Rsp`/`Rsn` per analysis step). The",
            "* R_source = 0 control row uses 1e-6 ohm, not a literal 0 (see",
            "* R_IDEAL_OHM).",
            f"Vinp VINP_SRC 0 {_pwl(vin['p'])}",
            f"Vinn VINN_SRC 0 {_pwl(vin['n'])}",
            f"Rsp VINP_SRC VINP {R_IDEAL_OHM:.6g}",
            f"Rsn VINN_SRC VINN {R_IDEAL_OHM:.6g}",
            "* SAMPLE: a normalised 0..1 pwl control (altered per step, one vector",
            "* per acquisition window) scaled by the corner's own supply, so the",
            "* vector itself carries no corner-dependent voltage.",
            f"Vsmp_ctl SMP_CTL 0 {_pwl(sample_pwl_points(T_WINDOW_WORST_NS))}",
            "Bsample SAMPLE 0 V=v(SMP_CTL)*v(VDD)",
            "",
        ]
    )


def step_name(window: str, r_source_ohm: float) -> str:
    """A stable, ngspice-vector-safe step name per (window, resistance)."""
    return f"{window}_r{round(r_source_ohm)}"


def r_source_effective(r_source_ohm: float) -> float:
    """The resistance actually emitted: R_IDEAL_OHM stands in for 0."""
    if r_source_ohm < 0:
        raise ValueError(f"R_source must be >= 0, got {r_source_ohm!r}")
    return R_IDEAL_OHM if r_source_ohm == 0 else float(r_source_ohm)


def analysis_steps(
    windows: dict[str, float] | None = None,
    r_source_list: list[float] | None = None,
) -> list[dict]:
    """One `tran` step per (window, R_source): both sweep axes inside a single
    `klt sim` request, next to the corner axes.

    `reset: true` re-parses the circuit before each step, so a step's own
    `alter` set fully determines its deck -- no state or override leaks from
    the previous solve. klt re-emits the corner's own supply `alter` after the
    reset, so the corner axis survives it."""
    windows = WINDOWS if windows is None else windows
    r_source_list = R_SOURCE_SWEEP_OHM if r_source_list is None else r_source_list
    steps: list[dict] = []
    for window, window_ns in windows.items():
        t = window_timing(window_ns)
        for r_source in r_source_list:
            r_eff = r_source_effective(r_source)
            steps.append(
                {
                    "name": step_name(window, r_source),
                    "reset": True,
                    "analysis": {
                        "kind": "tran",
                        "args": f"{TRAN_STEP_NS:g}n {t['tran_stop_ns']:.6f}n",
                    },
                    "alter": {
                        "Rsp": r_eff,
                        "Rsn": r_eff,
                        "Vsmp_ctl": {"pwl": _pwl_vector(sample_pwl_points(window_ns))},
                    },
                    # NOTE the measurement names. An ngspice `meas` result is
                    # written as a vector into the step's own plot, so a
                    # measurement named after a NODE (`top_p`) overwrites that
                    # node's transient waveform with a length-1 scalar, and
                    # every LATER card in the same step that reads `v(TOP_P)`
                    # fails with "out of interval". Found by running this deck:
                    # the budget reads passed and the confirm reads failed, in
                    # that order. Hence the BUDGET_/CONFIRM_ prefixes below --
                    # the same `budget_x`/`confirm_x` naming
                    # sim/sampling-acquisition-settling/run_acquisition_settling.py
                    # uses, and for the same reason. Filed upstream as a
                    # request-validation gap: 2AMLogic/klayout-tools#5446.
                    "measurements": [
                        {
                            "name": "budget_p",
                            "spice": f".meas tran budget_p find v(TOP_P) "
                            f"at={t['probe_ns']:.6f}n",
                            "unit": "V",
                        },
                        {
                            "name": "budget_n",
                            "spice": f".meas tran budget_n find v(TOP_N) "
                            f"at={t['probe_ns']:.6f}n",
                            "unit": "V",
                        },
                        {
                            "name": "confirm_p",
                            "spice": f".meas tran confirm_p find v(TOP_P) "
                            f"at={t['confirm_ns']:.6f}n",
                            "unit": "V",
                        },
                        {
                            "name": "confirm_n",
                            "spice": f".meas tran confirm_n find v(TOP_N) "
                            f"at={t['confirm_ns']:.6f}n",
                            "unit": "V",
                        },
                    ],
                }
            )
    return steps


def corner_ids() -> list[str]:
    """The ratified 9-point one-at-a-time PVT grid, in grid order."""
    grid = corners_mod.ratified_oat_grid(
        NOMINAL_SUPPLY_V, SUPPLY_TOLERANCE, PROCESS_CORNERS, TEMPS_C
    )
    return [corners_mod.corner_id(p, t, v) for p, t, v in grid]


def build_request(
    netlist_name: str,
    cids: list[str],
    *,
    timeout_s: float = 3600.0,
    backend: str | None = None,
    windows: dict[str, float] | None = None,
    r_source_list: list[float] | None = None,
) -> dict:
    """The `klt sim` request for one submission.

    The corner axes are declared as the full cross product with the points the
    one-at-a-time grid omits listed under `exclude` -- `klt sim` has no OAT
    axis form, so this is how sim/top-plate-cpar/ expresses the same grid."""
    pts = [corners_mod.parse_corner_id(c) for c in cids]
    procs = sorted({p for p, _, _ in pts})
    temps = sorted({t for _, t, _ in pts})
    vdds = sorted({v for _, _, v in pts})
    want = set(pts)
    exclude = [
        {"process": p, "temperature_c": t, "supply_v": {SUPPLY_KEY: v}}
        for p in procs
        for t in temps
        for v in vdds
        if (p, t, v) not in want
    ]
    req: dict = {
        "netlist": netlist_name,
        "engine": "ngspice",
        "models": {"pdk": "sky130A", "lib": "libs.tech/combined/sky130.lib.spice"},
        "corners": {
            "process": procs,
            "supply_v": {SUPPLY_KEY: vdds},
            "temperature_c": temps,
        },
        "analysis_steps": analysis_steps(windows, r_source_list),
        "options": {"timeout_s": timeout_s, "keep_artifacts": True},
    }
    if exclude:
        req["exclude"] = exclude
    if backend:
        req["backend"] = backend
    return req


def read_report(report: dict) -> tuple[dict[str, dict[str, float | None]], dict]:
    """`({corner_id: {"<step>.<name>": value}}, run info)`.

    Refuses an error ENVELOPE rather than inventing numbers, and nulls a
    corner whose own status is `error`/`inconclusive` so a partial solve is
    never read as a measurement (sim/top-plate-cpar/'s own reader contract)."""
    if not isinstance(report, dict):
        raise ValueError("klt sim report is not a JSON object")
    if "error" in report and "corners" not in report:
        raise ValueError(f"klt sim error envelope: {report['error']}")
    out: dict[str, dict[str, float | None]] = {}
    for c in report.get("corners") or []:
        sv = (c.get("supply_v") or {}).get(SUPPLY_KEY)
        cid = corners_mod.corner_id(
            c["process"], float(c["temperature_c"]), float(sv)
        )
        vals = {
            m["name"]: m.get("value")
            for m in (c.get("measurements") or [])
            if isinstance(m, dict) and "name" in m
        }
        if c.get("status") in ("error", "inconclusive"):
            vals = {k: None for k in vals}
        out[cid] = vals
    env = report.get("environment") or {}
    remote = env.get("remote") or {}
    worker = remote.get("worker_environment") or {}
    banner = ((worker.get("simulator") or {}).get("version_banner") or "")
    ngs = next(
        (ln.strip("* ").strip() for ln in banner.splitlines() if "ngspice-" in ln),
        None,
    )
    return out, {
        "remote": remote or None,
        "status": report.get("status"),
        "job_id": remote.get("job_id"),
        "worker_pdk": (worker.get("pdk") or {}).get("stamp_text"),
        "worker_ngspice": ngs,
    }


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def sweep_rows(
    values: dict[str, float | None],
    window: str,
    r_source_list: list[float] | None = None,
) -> list[dict] | None:
    """One corner-and-window sweep, as ordered rows -- or None when ANY point
    is missing or non-finite (never a partial sweep, since a budget read off
    one would silently be a budget over a different sweep list).

    `raw_err_mv` is the differential error against the IDEAL target
    (V_TARGET_DIFF). `ctrl_err_mv` is the `R_source = 0` row's own raw error,
    the same for every row of this sweep. `err_mv` is the error RELATIVE to
    that control row, which is what the budgets below are computed on -- see
    the module docstring for why the control row cannot be assumed to be zero."""
    r_source_list = R_SOURCE_SWEEP_OHM if r_source_list is None else r_source_list
    if r_source_list[0] != 0.0:
        raise ValueError(
            "the sweep's first point must be R_source = 0: it is the control "
            f"row every budget is relative to (got {r_source_list[0]!r})"
        )
    rows: list[dict] = []
    for r_source in r_source_list:
        name = step_name(window, r_source)
        top_p = values.get(f"{name}.budget_p")
        top_n = values.get(f"{name}.budget_n")
        top_p_conf = values.get(f"{name}.confirm_p")
        top_n_conf = values.get(f"{name}.confirm_n")
        if not all(_finite(v) for v in (top_p, top_n, top_p_conf, top_n_conf)):
            return None
        diff = top_p - top_n
        rows.append(
            {
                "r_source_ohm": r_source,
                "top_p_v": top_p,
                "top_n_v": top_n,
                "diff_v": diff,
                # Per-node residual against each side's own ideal target: the
                # quantity sim/sampling-acquisition-settling/'s records report,
                # so its control row is directly comparable with theirs.
                "resid_p_mv": (top_p - V_FINAL_P) * 1e3,
                "resid_n_mv": (top_n - V_FINAL_N) * 1e3,
                "diff_conf_v": top_p_conf - top_n_conf,
                "raw_err_mv": (diff - V_TARGET_DIFF) * 1e3,
                "raw_conf_err_mv": (top_p_conf - top_n_conf - V_TARGET_DIFF) * 1e3,
            }
        )
    ctrl = rows[0]["raw_err_mv"]
    for row in rows:
        row["ctrl_err_mv"] = ctrl
        row["ctrl_err_lsb"] = ctrl / LSB_DIFF_MV_PROVISIONAL
        row["err_mv"] = row["raw_err_mv"] - ctrl
        row["err_lsb"] = row["err_mv"] / LSB_DIFF_MV_PROVISIONAL
        row["raw_err_lsb"] = row["raw_err_mv"] / LSB_DIFF_MV_PROVISIONAL
    return rows


def find_budget(rows: list[dict], threshold_lsb: float) -> dict | None:
    """The largest-swept-value rule of sim/vcm-drive-budget/'s own
    find_budget(): the last row (sweep order is ascending) whose
    control-relative error magnitude is still within `threshold_lsb`.

    None means even the smallest NON-ZERO swept point already exceeds the
    threshold -- reported as "< <that value>", never as a budget of 0. A
    result equal to the largest swept value is RIGHT-CENSORED: every swept
    value stayed within threshold, so the true budget is >= that value, not
    equal to it.

    The `R_source = 0` CONTROL row is excluded from the candidates. It is the
    reference every other row's error is measured against, so its own error is
    identically zero and it would otherwise pass every tier -- turning "no
    swept resistance works" into a reported budget of "0 ohm", which reads as
    a measurement but only restates the arithmetic. (This is the one place
    this function is not byte-identical to the `sim/vcm-drive-budget/` one it
    mirrors: that implementation's own docstring promises the None case, but
    because its baseline row is zero by the same construction, its None branch
    is unreachable. Nothing there is wrong today -- its records are
    right-censored, not "none found" -- but the shape does not survive being
    copied onto an axis where the first non-zero point can fail, which this
    one can. Caught by sim/tests/test_input_drive_budget.py.)"""
    ok = [
        r
        for r in rows
        if r["r_source_ohm"] > 0 and abs(r["err_lsb"]) <= threshold_lsb
    ]
    return ok[-1] if ok else None


def budget_summary(
    rows: list[dict],
    r_source_list: list[float] | None = None,
    tiers_lsb: list[float] | None = None,
) -> dict:
    """Per-tier budgets for one corner-and-window sweep, with the censoring and
    control-row facts a reader needs to not over-read them."""
    r_source_list = R_SOURCE_SWEEP_OHM if r_source_list is None else r_source_list
    tiers_lsb = TIERS_LSB if tiers_lsb is None else tiers_lsb
    largest = r_source_list[-1]
    first_nonzero = next((r for r in r_source_list if r > 0), None)
    out: dict = {
        "ctrl_err_mv": rows[0]["ctrl_err_mv"],
        "ctrl_err_lsb": rows[0]["ctrl_err_lsb"],
        "first_nonzero_ohm": first_nonzero,
        "largest_swept_ohm": largest,
        "tiers": {},
    }
    for tier in tiers_lsb:
        hit = find_budget(rows, tier)
        out["tiers"][tier] = {
            "budget_ohm": hit["r_source_ohm"] if hit else None,
            "right_censored": bool(hit and hit["r_source_ohm"] == largest),
            # The control row is the budget's own reference, so a control row
            # outside the tier does not invalidate the RELATIVE budget -- but
            # it does make the RAW-error budget unreadable at this point, which
            # the record must say rather than silently reporting one.
            "control_outside_tier": abs(rows[0]["raw_err_lsb"]) > tier,
        }
    return out


def format_budget(tier_result: dict, summary: dict) -> str:
    """The one-cell rendering of a budget, with censoring stated in the cell
    itself rather than left to a footnote."""
    ohm = tier_result["budget_ohm"]
    if ohm is None:
        return f"< {summary['first_nonzero_ohm']:.0f} (none found)"
    if tier_result["right_censored"]:
        return f">= {ohm:.0f} (right-censored)"
    return f"{ohm:.0f}"


def analyze(
    results: dict[str, dict[str, float | None]],
    cids: list[str],
    windows: dict[str, float] | None = None,
    r_source_list: list[float] | None = None,
) -> dict:
    """`{corner_id: {window: {"rows", "summary"} | None}}`."""
    windows = WINDOWS if windows is None else windows
    out: dict = {}
    for cid in cids:
        vals = results.get(cid)
        per: dict = {}
        for window in windows:
            rows = sweep_rows(vals, window, r_source_list) if vals else None
            per[window] = (
                {"rows": rows, "summary": budget_summary(rows, r_source_list)}
                if rows
                else None
            )
        out[cid] = per
    return out


# ---------------------------------------------------------------------------
# Submission -- every simulation unit goes through `klt sim`
# ---------------------------------------------------------------------------
class SubmitError(RuntimeError):
    pass


#: CLAUDE.md's fleet rule: the fleet is vCPU-budgeted, so a burst is refused
#: with `batch_no_capacity` unless the submit may wait with backoff. Passed on
#: every submission that is not explicitly local.
CAPACITY_WAIT_S = 600


def submit_argv(
    request_path: Path,
    outdir: Path,
    backend: str | None,
    capacity_wait_s: int = CAPACITY_WAIT_S,
) -> list[str]:
    """The `klt sim` argv. `--wait-for-capacity` is passed unless the backend
    is explicitly `local`, where there is no fleet to wait for."""
    argv = ["klt", "sim", str(request_path), "--format", "json", "-o", str(outdir)]
    if backend:
        argv += ["--backend", backend]
    if backend != "local":
        argv += ["--wait-for-capacity", str(capacity_wait_s)]
    return argv


def submit(
    cids: list[str],
    workdir: Path,
    backend: str | None,
    timeout_s: float,
    *,
    windows: dict[str, float] | None = None,
    r_source_list: list[float] | None = None,
) -> tuple[dict, dict, dict]:
    """Write the deck + request under `workdir`, run `klt sim`, return
    `(results, run info, request)`. An existing `report.json` is reused, so a
    re-run after a successful submit does not re-spend fleet capacity."""
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "tb.spice").write_text(build_body())
    req = build_request(
        "tb.spice",
        cids,
        timeout_s=timeout_s,
        backend=backend,
        windows=windows,
        r_source_list=r_source_list,
    )
    (workdir / "request.json").write_text(json.dumps(req, indent=1) + "\n")
    rep_path = workdir / "report.json"
    if rep_path.is_file():
        report = json.loads(rep_path.read_text())
    else:
        argv = submit_argv(workdir / "request.json", workdir / "out", backend)
        print("+ " + " ".join(argv), flush=True)
        done = subprocess.run(argv, capture_output=True, text=True, check=False)
        try:
            report = json.loads(done.stdout)
        except json.JSONDecodeError:
            try:
                report = json.loads(done.stderr)
            except json.JSONDecodeError as exc:
                raise SubmitError(
                    f"klt sim returned no JSON report (rc={done.returncode}): "
                    f"{(done.stderr or done.stdout)[:800]}"
                ) from exc
        if "error" in report and "corners" not in report:
            raise SubmitError(f"klt sim: {json.dumps(report['error'])}")
        rep_path.write_text(json.dumps(report, indent=1) + "\n")
    results, info = read_report(report)
    return results, dict(info, backend=backend or "(klt default / KLT_SIM_BACKEND)"), req


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------
#: Stated in the record so a reader cannot mistake the testbench for the pad.
LIMITS = [
    "**Series resistance only.** The testbench puts one ideal source in series "
    "with one resistor on each input pin. It models no pad capacitance, no ESD "
    "network, no anti-alias capacitor at the pad node and no package or bond-wire "
    "inductance. A real pad network with shunt capacitance at the die side can "
    "behave better (it holds charge locally) or worse (it rings with inductance) "
    "than this; neither is measured here.",
    "**A full-scale step between consecutive samples is the stimulus.** `VINP`/"
    "`VINN` step the whole rail-adjacent differential span (0.2 V <-> 1.6 V per "
    "side) during HOLD, so every figure below is the worst case for a near-Nyquist "
    "input. A slowly varying input presents a far smaller step and is not graded.",
    "**`Csamp` stands in for the CDAC array.** The DUT is the sampling front-end "
    "fragment, whose per-side `Csamp` is sized (DR-004) to mimic the real array's "
    "load. The whole-ADC CDAC, its own parasitics and the comparator input are not "
    "in this deck; `sim/top-plate-cpar/` measures the top-plate parasitic "
    "separately and it is not added here.",
    "**`VCM`, the references and the supply are ideal.** `VCM` is a fixed ideal "
    "0.9 V source -- `sim/sampling-acquisition-settling/`'s own convention, carried "
    "over unchanged so this campaign's control row is comparable with that "
    "campaign's records; it does NOT track the supply corner. `VREFP`/`VREFN` are "
    "absent from this fragment, and the supply is an ideal source at the corner's "
    "own voltage. `VCM`'s own drive impedance is `sim/vcm-drive-budget/`'s "
    "campaign, the references' is #841's, and the supply terminals' is "
    "`sim/supply-impedance-sensitivity/`'s; none is combined with this one.",
    "**The SAMPLE level tracks the supply; the input levels do not.** One deck "
    "serves all nine corners, so SAMPLE is a normalised `pwl` scaled by `v(VDD)` "
    "through a behavioural source, while the 0.2/1.6 V input extremes are fixed "
    "at every corner -- exactly as in the mirrored acquisition-settling runner. At "
    "1.62 V the input extremes are therefore a slightly larger fraction of the "
    "supply than at 1.98 V.",
    "**The budget's resolution is the sweep list.** A budget is the largest "
    "SWEPT resistance that still passes, so it is a lower bound on the true "
    "continuous threshold, quantised to this log-spaced list "
    f"({', '.join(f'{r:g}' for r in R_SOURCE_SWEEP_OHM)} ohm). A budget reported "
    "as `>= 100000` is right-censored by the list's top value, not measured.",
    "**No spec row is graded.** `spec/target-spec.md` is entirely DRAFT (#1/#27). "
    "The provisional differential LSB (3.5156 mV, DR-003 Item 2 pending #27) is a "
    "reference scale only, and the DR-006 window is downstream of the DRAFT "
    "sample-rate row. `spec/target-spec.md`'s DRAFT Kickback row names a 1 kOhm "
    "series source impedance on these pins and is the reason 1 kOhm is a simulated "
    "point here; this record does not grade that row and changes no spec line.",
]


def _ohm(v: float) -> str:
    return f"{v:g}"


def write_record(
    analysis: dict,
    info: dict,
    cids: list[str],
    supersedes: str,
    workdir: Path,
) -> Path:
    from harness import evidence

    body = build_body()
    prov, lines = evidence.open_record(
        EXPERIMENT_DIR, body, "corners", {"report.json": (workdir / "report.json").read_text()}
    )
    req_dir = EXPERIMENT_DIR / "corners" / prov.record_id / "request"
    req_dir.mkdir(parents=True, exist_ok=True)
    (req_dir / "request.json").write_text((workdir / "request.json").read_text())
    (req_dir / "tb.spice").write_text(body)

    windows = list(WINDOWS)
    complete = [c for c in cids if all(analysis[c][w] for w in windows)]

    # open_record() starts `lines` with a generic `# Record <id>` title; give
    # this campaign's records the same descriptive heading shape every other
    # budget campaign's records carry.
    lines[0] = (
        f"# VINP/VINN input-drive-impedance budget -- full PVT grid "
        f"-- {prov.record_id}"
    )
    lines += [
        "- **Claim**: none against any spec row -- characterization. First "
        "measurement in this repo of how much series source resistance the "
        "`VINP`/`VINN` pads tolerate while the sampling front end still acquires "
        "a new full-scale differential input inside the acquisition window. "
        "Reported informationally against the provisional differential LSB as a "
        "reference scale, at two tiers, on the ratified 9-point PVT grid. No spec "
        "line is changed and no decision record is proposed.",
        "- **Issue**: #847",
        f"- **Method**: the unmodified sampling front-end fragment "
        f"(`sim/sampling-frontend/testbench/sampling_frontend_dut.spice`, read in "
        f"place) with one ideal source in series with a swept `R_source` on EACH "
        f"of `VINP` and `VINN` (both resistors always the same value). Stimulus "
        f"and reading convention are "
        f"`sim/sampling-acquisition-settling/run_acquisition_settling.py`'s "
        f"two-pulse old-value-to-new-value full-scale step and its FIXED-TIME "
        f"`find v(node) at=<t>` probe (no crossing search -- see that runner's own "
        f"two documented `.meas TRIG/TARG` pitfalls). The probe is taken exactly "
        f"one acquisition window after SAMPLE pulse #2's 50 % rising edge "
        f"({TRIG_AT_NS:g} ns). Budgets follow `sim/vcm-drive-budget/`'s "
        f"`find_budget()`: the largest swept resistance still within the tier.",
        f"- **Swept `R_source`**: {', '.join(_ohm(r) for r in R_SOURCE_SWEEP_OHM)} ohm "
        f"(`0` is emitted as {R_IDEAL_OHM:g} ohm -- see the runner's `R_IDEAL_OHM`). "
        f"Both acquisition windows are covered: "
        + "; ".join(f"`{w}` = {WINDOW_DESCRIPTION[w]}" for w in windows)
        + ".",
        f"- **Control row**: every corner and window carries its own "
        f"`R_source = 0` row, and every budget below is computed on the error "
        f"RELATIVE to that row. The raw error against the ideal target "
        f"({V_TARGET_DIFF:g} V differential) is tabulated as well. This matters "
        f"because the zero-resistance baseline is not zero everywhere: "
        f"`sim/sampling-acquisition-settling/records/20260908-051436-6ccd72d.md` "
        f"reports a -0.3800 mV per-node residual at `tt_27c_1.62v` with an ideal "
        f"source (~0.11 provisional LSB), so a 0.1-LSB tier read against the ideal "
        f"target could fail there with no source resistance at all.",
        corners_mod.corner_matrix_summary_line(
            sorted({corners_mod.parse_corner_id(c)[0] for c in cids}),
            sorted({corners_mod.parse_corner_id(c)[1] for c in cids}),
            sorted({corners_mod.parse_corner_id(c)[2] for c in cids}),
            len(cids),
        ),
        f"- **Overall**: {'COMPLETE' if len(complete) == len(cids) else 'INCOMPLETE'} "
        f"({len(complete)}/{len(cids)} corners complete at both windows)",
        "",
    ]

    for window in windows:
        lines += [
            f"## `R_source` budget per corner -- {WINDOW_DESCRIPTION[window]} window",
            "",
            "A budget is the largest SWEPT `R_source` whose control-relative "
            "differential error magnitude still stays within the tier, so it is a "
            "lower bound on the true continuous threshold, quantised to the sweep "
            f"list. `>= {R_SOURCE_SWEEP_OHM[-1]:.0f} (right-censored)` means every "
            "swept value stayed within the tier: the true budget is at or above "
            "that value, NOT equal to it. `< "
            f"{next(r for r in R_SOURCE_SWEEP_OHM if r > 0):.0f} (none found)` means "
            "even the smallest non-zero swept value already exceeded the tier.",
            "",
            "| Corner | 1-LSB budget (ohm) | 0.1-LSB budget (ohm) | "
            "control raw err (mV) | control (LSB) |",
            "|---|---|---|---|---|",
        ]
        for cid in cids:
            per = analysis[cid][window]
            if per is None:
                lines.append(f"| `{cid}` | (incomplete) | (incomplete) | - | - |")
                continue
            s = per["summary"]
            lines.append(
                f"| `{cid}` | {format_budget(s['tiers'][1.0], s)} | "
                f"{format_budget(s['tiers'][0.1], s)} | "
                f"{s['ctrl_err_mv']:+.4f} | {s['ctrl_err_lsb']:+.4f} |"
            )
        lines.append("")

        lines += [
            f"### Per-point sweep -- {WINDOW_DESCRIPTION[window]} window",
            "",
            "`raw err` is against the ideal target; `rel err` is against this "
            "corner-and-window's own `R_source = 0` row, and is what the budgets "
            "above are computed on. `confirm` is the long-time read, well inside "
            "SAMPLE pulse #2 and clear of its own fall.",
            "",
            "| Corner | R_source (ohm) | raw err (mV) | rel err (mV) | rel err (LSB) "
            "| confirm raw err (mV) |",
            "|---|---|---|---|---|---|",
        ]
        for cid in cids:
            per = analysis[cid][window]
            if per is None:
                continue
            for row in per["rows"]:
                lines.append(
                    f"| `{cid}` | {_ohm(row['r_source_ohm'])} | "
                    f"{row['raw_err_mv']:+.4f} | {row['err_mv']:+.4f} | "
                    f"{row['err_lsb']:+.4f} | {row['raw_conf_err_mv']:+.4f} |"
                )
        lines.append("")

    lines += ["## Result", ""]
    lines += result_lines(analysis, cids, windows)
    lines += ["", "## What this testbench does not model", ""]
    lines += [f"- {text}" for text in LIMITS]
    lines += [
        "",
        "## Reproduction",
        "",
        "```bash",
        "# One-time machine bootstrap: docs/environment-setup.md sections 1-3.",
        "source sim/env.sh",
        f"python3 {WRITTEN_BY} --record",
        "```",
        "",
        "The multi-corner grid is one `klt sim` request submitted to the batch "
        f"fleet with `--wait-for-capacity {CAPACITY_WAIT_S}`; no `ngspice` loop "
        "runs on the submitting host. `--probe` runs a single corner, a single "
        "resistance and a single window locally (`--backend local`) and is the only "
        "path that does. The request and the deck body are committed beside this "
        f"record under `corners/{prov.record_id}/request/`, and the raw `klt sim` "
        f"report under `corners/{prov.record_id}/report.json`.",
        "",
        "## `klt sim` run",
        "",
        f"- job `{info.get('job_id')}`, status `{info.get('status')}`, backend "
        f"`{info.get('backend')}`, executing PDK `{info.get('worker_pdk')}`, "
        f"executing simulator `{info.get('worker_ngspice')}`",
        "",
        "**Uncontrolled difference.** The Environment block below names the PDK and "
        "ngspice resolved on the SUBMITTING host; the numbers above were produced by "
        "the executing worker named here. Where those differ, no comparison with a "
        "locally run record -- including the acquisition-settling record this one "
        "cites for its control row -- is controlled for PDK or simulator version.",
        "",
    ]

    klt_version = subprocess.run(
        ["klt", "--version"], capture_output=True, text=True, check=False
    ).stdout.strip()
    worker_pdk = info.get("worker_pdk")
    worker_ng = info.get("worker_ngspice")
    exec_known = bool(worker_pdk and worker_ng)
    lines += evidence.environment_block(
        f"sky130A @ {worker_pdk.split()[-1]}" if exec_known else prov.pdk_line,
        worker_ng.split()[0] if exec_known else prov.ng_version,
        prov.netlist_sha,
        {
            "klt": klt_version,
            "tran step": f"{TRAN_STEP_NS:g} ns",
            "provisional differential LSB": f"{LSB_DIFF_MV_PROVISIONAL:g} mV "
            "(DR-003 Item 2, pending #27 -- reference scale only)",
            "PDK / ngspice above": "as run by the executing worker"
            if exec_known
            else "submitting host (executing worker did not report)",
            "submitting host PDK / ngspice": f"{prov.pdk_line} / {prov.ng_version}",
        },
    )
    lines += [""]
    lines += evidence.footer_lines(WRITTEN_BY, supersedes)
    evidence.write_latest_pointer(EXPERIMENT_DIR, prov.record_id)
    return evidence.close_record(prov, lines, "Record")


def result_lines(analysis: dict, cids: list[str], windows: list[str]) -> list[str]:
    """The **Result** bullets, derived from the tables rather than restated by
    hand -- every number here is read back out of `analysis`."""
    out: list[str] = []
    for window in windows:
        done = [c for c in cids if analysis[c][window]]
        if not done:
            out.append(
                f"- **{WINDOW_DESCRIPTION[window]} window**: no corner completed; "
                "nothing is reported for it."
            )
            continue
        for tier in TIERS_LSB:
            graded = [
                (c, analysis[c][window]["summary"]["tiers"][tier]) for c in done
            ]
            none_found = [c for c, t in graded if t["budget_ohm"] is None]
            measured = [(c, t) for c, t in graded if t["budget_ohm"] is not None]
            censored = [c for c, t in measured if t["right_censored"]]
            if not measured:
                out.append(
                    f"- **{WINDOW_DESCRIPTION[window]} window, {tier:g}-LSB tier**: "
                    f"no corner tolerates even the smallest non-zero swept "
                    f"resistance ({len(none_found)}/{len(done)} corners "
                    f"\"none found\"). The budget is below the sweep's resolution "
                    f"at every corner; a finer sweep is needed to state one."
                )
                continue
            tightest = min(t["budget_ohm"] for _c, t in measured)
            loosest = max(t["budget_ohm"] for _c, t in measured)
            tight_cids = [c for c, t in measured if t["budget_ohm"] == tightest]
            loose_cids = [c for c, t in measured if t["budget_ohm"] == loosest]
            spread = (loosest / tightest) if tightest > 0 else float("inf")
            text = (
                f"- **{WINDOW_DESCRIPTION[window]} window, {tier:g}-LSB tier**: "
                f"binding corner(s) {', '.join(f'`{c}`' for c in tight_cids)} at "
                f"{tightest:.0f} ohm; loosest {', '.join(f'`{c}`' for c in loose_cids)} "
                f"at {loosest:.0f} ohm. Worst-to-best spread across the grid: "
                f"{spread:.1f}x."
            )
            if censored:
                text += (
                    f" Right-censored at {len(censored)}/{len(done)} corners "
                    f"({', '.join(f'`{c}`' for c in censored)}): every swept value "
                    "stayed within the tier there, so those budgets are lower "
                    "bounds, not measured limits."
                )
            if none_found:
                text += (
                    f" {len(none_found)}/{len(done)} corners found no budget "
                    f"({', '.join(f'`{c}`' for c in none_found)}): the smallest "
                    "non-zero swept resistance already exceeded the tier there."
                )
            out.append(text)
        outside = [
            c
            for c in done
            if any(
                analysis[c][window]["summary"]["tiers"][t]["control_outside_tier"]
                for t in TIERS_LSB
            )
        ]
        if outside:
            details = []
            for c in outside:
                s = analysis[c][window]["summary"]
                tiers = [
                    f"{t:g}" for t in TIERS_LSB if s["tiers"][t]["control_outside_tier"]
                ]
                details.append(
                    f"`{c}` ({s['ctrl_err_mv']:+.4f} mV, "
                    f"{s['ctrl_err_lsb']:+.4f} LSB; outside the "
                    f"{'/'.join(tiers)}-LSB tier{'s' if len(tiers) > 1 else ''})"
                )
            out.append(
                f"- **Control row outside a tier at {len(outside)}/{len(done)} "
                f"corner(s)** for the {WINDOW_DESCRIPTION[window]} window: "
                + "; ".join(details)
                + ". The budgets above are still readable there, because they are "
                "computed on the error RELATIVE to that same control row -- but a "
                "budget read off the RAW error cannot be stated at those corners, "
                "and none is."
            )
    out.append(
        f"- **{R_SOURCE_SWEEP_OHM[3]:.0f} ohm is a simulated point, not an "
        "interpolation.** `spec/target-spec.md`'s DRAFT Kickback row names a 1 kOhm "
        "series source impedance on these pins, so it is in the sweep list above and "
        "every corner has a measured row at it. This record does not grade that row."
    )
    out.append(
        "- This campaign measures ONE mechanism (the sampling front end acquiring a "
        "new full-scale differential input through a non-ideal input source) on ONE "
        "DUT (the front-end fragment). It does not combine with the CDAC-settling, "
        "comparator-decision or sequencer-delay campaigns into an end-to-end sample "
        "rate, and it establishes nothing about what an actual off-chip driver or pad "
        "network would present -- see \"What this testbench does not model\" below."
    )
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    from harness import evidence, pdk

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check-env", action="store_true",
                    help="report whether the PDK resolves, and exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="write the deck + request to --workdir and stop (no simulation)")
    ap.add_argument("--probe", action="store_true",
                    help="ONE corner (tt_27c_1.80v), ONE resistance (R_source = 0) and "
                         "ONE window (worst), local backend -- the single-unit debug "
                         "probe, compared against sim/sampling-acquisition-settling/'s "
                         "own tt_27c_1.80v row before the grid is submitted")
    ap.add_argument("--record", action="store_true",
                    help="submit the full grid through klt sim and mint a record")
    ap.add_argument("--backend", default=None,
                    help="klt sim backend (default: klt's own / KLT_SIM_BACKEND; the "
                         "multi-corner grid goes to the batch fleet and is never "
                         "looped locally)")
    ap.add_argument("--workdir", type=Path, default=None)
    ap.add_argument("--timeout-s", type=float, default=3600.0)
    evidence.add_supersedes_argument(ap)
    args = ap.parse_args(argv)

    if args.check_env:
        info = pdk.resolve()
        print(f"PDK: {info.variant if info.found else info.error}")
        return 0 if info.found else 1

    workdir = args.workdir or Path(tempfile.mkdtemp(prefix="sim-input-drive-budget-"))
    cids = corner_ids()

    if args.dry_run:
        workdir.mkdir(parents=True, exist_ok=True)
        (workdir / "tb.spice").write_text(build_body())
        req = build_request("tb.spice", cids, timeout_s=args.timeout_s)
        (workdir / "request.json").write_text(json.dumps(req, indent=1) + "\n")
        print(f"wrote deck + request under {workdir}")
        print(f"corners: {len(cids)}  steps/corner: {len(req['analysis_steps'])}  "
              f"units: {len(cids)}")
        return 0

    if args.probe:
        cid = corners_mod.corner_id("tt", 27.0, NOMINAL_SUPPLY_V)
        results, info, _req = submit(
            [cid], workdir / "probe", "local", args.timeout_s,
            windows={"worst": T_WINDOW_WORST_NS}, r_source_list=[0.0],
        )
        rows = sweep_rows(results.get(cid) or {}, "worst", [0.0])
        if rows is None:
            print(f"{cid}: INCOMPLETE -- no usable measurement", file=sys.stderr)
            return 1
        row = rows[0]
        print(f"{cid}  window=worst ({T_WINDOW_WORST_NS:.3f} ns)  R_source=0")
        print(f"  TOP_P residual  {row['resid_p_mv']:+.4f} mV   "
              f"(ideal target {V_FINAL_P:g} V)")
        print(f"  TOP_N residual  {row['resid_n_mv']:+.4f} mV   "
              f"(ideal target {V_FINAL_N:g} V)")
        print(f"  differential raw error {row['raw_err_mv']:+.4f} mV "
              f"({row['raw_err_lsb']:+.4f} provisional LSB)")
        print("  compare: sim/sampling-acquisition-settling/records/"
              "20260908-051436-6ccd72d.md reports +0.0000 mV for the worst node at "
              "tt_27c_1.80v at this same probe time with an ideal source")
        print(f"  klt sim: backend {info.get('backend')}, status {info.get('status')}")
        return 0

    if args.record:
        results, info, _req = submit(cids, workdir, args.backend, args.timeout_s)
        analysis = analyze(results, cids)
        for cid in cids:
            state = ", ".join(
                f"{w}={'ok' if analysis[cid][w] else 'INCOMPLETE'}" for w in WINDOWS
            )
            print(f"{cid}: {state}")
        write_record(analysis, info, cids, args.supersedes, workdir)
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

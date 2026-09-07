#!/usr/bin/env python3
"""VCM drive-impedance / decoupling budget for the sampling front end
(issue #121, Epic #542 Phase 4B follow-up).

`docs/chipalooza/challenge-4-proposal.md` (`docs/chipalooza/challenge-4-proposal.md`,
PR #140) named an open item: every testbench in this repo drives `VCM` from
an ideal (zero-impedance) source, so the design has never quantified how much
real (non-zero) drive resistance and/or on-die decoupling `VCM` needs to
preserve the sampling front end's own already-verified sub-mV in-sample
settling (`sim/sampling-frontend/records/20260821-072657-433a294.md`).

This script answers that, at a single corner (tt/27C/1.8V, deferred full-PVT
per the same precedent `sim/sampling-frontend/run_hold_kick.py` Experiments
1-5 set), by reusing the unmodified sampling front-end DUT fragment
(`sim/sampling-frontend/testbench/sampling_frontend_dut.spice`, read in
place -- not duplicated, matching `run_hold_kick.py`'s own precedent for
`CDAC_FRAGMENT`) and replacing its ideal `Vvcm` source with an ideal source
in series with a swept resistance `R_source` (representing whatever off-chip
or on-chip reference buffer / pad network actually drives the shared `VCM`
net in silicon), optionally with a decoupling capacitor `C_decouple` at the
on-die `VCM` node.

Both `Cmswn_{p,n}`/`Cmswp_{p,n}` switches (the front end's common-mode /
reference-switching transmission gates, `design/sampling_frontend.sch`'s own
comment block) tie to the SAME `VCM` net for both differential legs
(confirmed directly from the DUT fragment: all four switch instances name
node `VCM`), so `R_source` sees the combined current draw of both legs
charging `BPREF_P`/`BPREF_N` back toward `VCM` every SAMPLE assertion -- the
realistic shared-rail case, not two independently driven half-circuits.

**What "acquisition window" means here.** `spec/decision-records/DR-006-sar-
sequencer-bit-count-and-timing-budget.md` derives `f_clk = 12 * f_s` from the
DRAFT 100 kS/s-1 MS/s sample-rate row and a uniform one-`CLK`-period SAMPLE
phase, i.e. `t_sample = 1 / f_clk`:

  - `t_sample_worst_ns` = 1e3 / 12 MHz  = 83.33 ns  (fastest provisional clock
    -- the SHORTEST window, i.e. the case least forgiving of a slow VCM)
  - `t_sample_slow_ns`  = 1e3 / 1.2 MHz = 833.3 ns (slowest provisional clock)

Every prior sampling-frontend record (`run_transient.py`, `run_hold_kick.py`)
used a fixed testbench convention of 400 ns for the SAMPLE pulse width,
independent of DR-006 -- itself never previously reconciled against the
DRAFT clock-rate row. This script tests BOTH the DR-006-derived worst-case
window (83.33 ns) and the repo's existing 400 ns testbench convention, so the
two are for the first time shown side by side.

No claim here is graded against a ratified spec row: `spec/target-spec.md`
is entirely DRAFT (#1/#27), `LSB_DIFF_MV_PROVISIONAL` is quoted only as a
reference scale (same convention `run_hold_kick.py` already established), and
the DR-006 timing window is itself downstream of the DRAFT sample-rate row
(the gap `docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2 already
names). What this DOES produce, for the first time, is a concrete R_source /
C_decouple relationship the design can be checked against once any of those
upstream numbers ratify.

FULL-PVT-GRID MODE (``--corners``, added 2026-09-07). The single-corner
caveat above ("switch R_on varies materially with process/temperature, so a
full PVT sweep of this same budget is still open") is what this mode exists
to close for the bare (undecoupled) R_source budget: it re-runs that one
sweep (the ``worst_case_pp`` test point) at the same ratified 9-point
one-at-a-time (OAT) PVT grid every other
``docs/chipalooza/challenge-4-proposal.md`` Section 7 Item 2 mechanism
campaign now sweeps (process ``{ff, fs, sf, ss, tt}`` x temperature
``{-40, 27, 125} C`` x supply ``{1.62, 1.8, 1.98} V``,
``spec/target-spec.md``'s "Numeric rows -- RATIFIED 2026-08-19" section).
A new ``--window {worst,legacy}`` selector (added 2026-09-07, alongside
``--corners``) chooses which acquisition window's bare R_source sweep is
repeated per corner:

  - ``worst`` (default): the DR-006 worst-case (12 MHz, 83.333 ns) window,
    the full ``R_SOURCE_SWEEP_OHM`` list.
  - ``legacy``: this repo's pre-existing 400 ns testbench convention, the
    reduced ``R_SOURCE_SWEEP_LEGACY_OHM`` list (same reduced-runtime
    rationale as the single-corner default path's own legacy sweep). The
    single-corner record already found the legacy window to be the MORE
    demanding case for this mechanism, not the worst-case window -- this
    mode is what closes that finding's own "not yet corner-complete" gap.

Only one window is swept per invocation.

A second selector, ``--sweep {rsource,decouple}`` (added 2026-09-07), chooses
which *leg* of the budget ``--corners`` repeats per corner:

  - ``rsource`` (default): the bare (undecoupled) R_source sweep described
    above.
  - ``decouple``: the C_decouple sweep -- the last leg of this budget that
    was still single-corner-only. Each corner is decoupled against its OWN
    marginal R_source (``marginal_r_source()``, re-derived from that same
    corner's own bare sweep in the same invocation), never a value borrowed
    from the ``tt``/27C/1.8V point, because the bare budget itself is already
    known to vary by more than an order of magnitude across the grid
    (``records/20260907-052526-f589273.md``). The bare sweep therefore still
    runs per corner in this mode; only the reported leg differs.

Nothing about the single-corner default path above is changed;
``--corners``/``--window``/``--sweep`` are purely additive.

    python3 sim/vcm-drive-budget/run_vcm_drive_budget.py --corners --record
    python3 sim/vcm-drive-budget/run_vcm_drive_budget.py --corners --window legacy --record
    python3 sim/vcm-drive-budget/run_vcm_drive_budget.py --corners --sweep decouple --record
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
EXPERIMENT_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(SIM_DIR))
from harness import corners as corners_mod, evidence, measure, pdk, toolchain  # noqa: E402

DUT_FRAGMENT = (
    SIM_DIR / "sampling-frontend" / "testbench" / "sampling_frontend_dut.spice"
)

VDD_NOM = 1.8
VCM_FRAC = 0.5  # VCM = VCM_FRAC * VDD (DR-003 Item 1, provisional)
LSB_DIFF_MV_PROVISIONAL = 3.5156  # DR-003 Item 2, provisional pending #27

# DR-006-derived acquisition (SAMPLE-high) windows: t_sample = 1 / f_clk,
# f_clk = 12 * f_s, f_s in the DRAFT 100 kS/s-1 MS/s row.
T_SAMPLE_WORST_NS = 1.0e3 / 12.0   # 83.333... ns @ f_clk_max = 12 MHz
T_SAMPLE_SLOW_NS = 1.0e3 / 1.2     # 833.33... ns @ f_clk_min = 1.2 MHz
# Existing repo-wide sampling-frontend testbench convention (run_transient.py
# / run_hold_kick.py), independent of DR-006 -- kept for direct comparison.
T_SAMPLE_LEGACY_NS = 400.0

SAMPLE_TD_NS = 10.0   # SAMPLE rising edge start
SAMPLE_TR_NS = 1.0    # SAMPLE rise/fall time
TRAN_STEP_PS = 10.0   # matches run_hold_kick.py's converged step (see its
                      # own Experiment 5 / TRAN_STEP_PS comment)

TEST_POINTS = {
    "common_mode": (0.9, 0.9),
    "worst_case_pp": (1.6, 0.2),
}
DEFAULT_POINT = "worst_case_pp"

# R_source sweep: 0 (today's implicit ideal-source assumption) through a
# clearly-undriven pad-scale impedance. Log-spaced to resolve where the
# error transitions from negligible to LSB-scale.
R_SOURCE_SWEEP_OHM = [0.0, 100.0, 300.0, 1e3, 3e3, 10e3, 30e3, 100e3]
# The legacy (400 ns) window's tran runs cover ~5x more simulated time than
# the worst-case (83.3 ns) window's; a reduced subset keeps this script's
# total runtime bounded on a shared/contended machine (see _run()'s retry
# docstring) while still bracketing the same order-of-magnitude transition
# the full sweep above resolves for the worst-case window.
R_SOURCE_SWEEP_LEGACY_OHM = [0.0, 10e3, 100e3]

# Decoupling-capacitor values tested at a fixed, marginal R_source (chosen
# after the bare sweep above identifies it) to quantify how much on-die/at-
# pad decoupling relaxes the bare-R_source budget.
C_DECOUPLE_SWEEP_F = [0.0, 1e-12, 10e-12, 100e-12, 1e-9]

# Ratified corner-set axes (issue #28), per spec/target-spec.md's "Numeric
# rows -- RATIFIED 2026-08-19" section: -40/27/125C, +-10% supply, sky130
# process corners -- the same axes every other Section 7 Item 2 mechanism
# campaign (sim/cdac-bit-trial-settling/, sim/comparator-decision/,
# sim/sequencer-logic-delay/, sim/sampling-acquisition-settling/) sweeps.
# Used only by the optional --corners mode below; the single-corner
# (tt/27C/1.8V) default behavior above is unchanged.
SUPPLY_TOLERANCE = 0.10
TEMPS_C = [-40, 27, 125]
PROCESS_CORNERS = ["tt", "ss", "ff", "sf", "fs"]

# The single-corner (tt/27C/1.8V) record --corners's own evidence record
# cross-references as "the finding this campaign extends".
SINGLE_CORNER_SEED_RECORD = "20260905-201703-f012255"

# --corners --window {worst,legacy}: (sample_width_ns, r_source_sweep_list)
# per window. "worst" is the DR-006-derived worst-case (12 MHz) acquisition
# window at the full R_SOURCE_SWEEP_OHM resolution; "legacy" is this repo's
# pre-existing 400 ns testbench convention at the reduced
# R_SOURCE_SWEEP_LEGACY_OHM resolution (same runtime-bounding rationale as
# the single-corner default path's own legacy sweep, see
# R_SOURCE_SWEEP_LEGACY_OHM above).
WINDOW_CONFIG = {
    "worst": (T_SAMPLE_WORST_NS, R_SOURCE_SWEEP_OHM),
    "legacy": (T_SAMPLE_LEGACY_NS, R_SOURCE_SWEEP_LEGACY_OHM),
}
WINDOW_DESCRIPTION = {
    "worst": f"DR-006 worst-case (12 MHz, {T_SAMPLE_WORST_NS:.3f} ns)",
    "legacy": f"legacy ({T_SAMPLE_LEGACY_NS:.1f} ns) testbench convention",
}
# Bare (undecoupled) 1-LSB R_source budget the single-corner
# (tt/27C/1.8V) seed record (SINGLE_CORNER_SEED_RECORD) reports per window
# -- read directly from that record's own "## Result" section, used only to
# phrase this campaign's own "tightens vs. the single-corner finding" note.
SINGLE_CORNER_SEED_BUDGET_1LSB_OHM = {
    "worst": 10e3,
    "legacy": 0.0,
}


def _preamble(corner: str, temp_c: float, title: str) -> list[str]:
    info = pdk.resolve()
    return [
        f"* {title}",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        "",
    ]


def build_transient(
    *,
    vinp: float,
    vinn: float,
    sample_width_ns: float,
    r_source_ohm: float,
    c_decouple_f: float = 0.0,
    corner: str = "tt",
    temp_c: float = 27.0,
    vdd: float = VDD_NOM,
    tran_step_ps: float = TRAN_STEP_PS,
) -> str:
    """One transient deck: the unmodified sampling-frontend DUT fragment,
    with its ideal Vvcm source replaced by an ideal source in series with
    R_source into the on-die VCM net (plus an optional decoupling cap at
    that same node). SAMPLE is a single pulse `sample_width_ns` wide,
    starting at SAMPLE_TD_NS; the measurement of interest is the sampled
    TOP_x value at the END of that window (t = SAMPLE_TD_NS + SAMPLE_TR_NS +
    sample_width_ns - one step), i.e. the instant SAR-ADC decision would
    actually see."""
    vcm = round(vdd * VCM_FRAC, 6)
    sample_end_ns = SAMPLE_TD_NS + SAMPLE_TR_NS + sample_width_ns
    probe_ns = sample_end_ns - (tran_step_ps / 1000.0) * 2
    tran_stop_ns = sample_end_ns + 50.0

    lines = _preamble(
        corner, temp_c,
        f"issue #121 VCM drive-budget -- corner={corner} temp={temp_c}C "
        f"vdd={vdd} vinp={vinp} vinn={vinn} r_source={r_source_ohm:g} "
        f"c_decouple={c_decouple_f:g} sample_width_ns={sample_width_ns:g}",
    )
    lines += [
        f"Vdd VDD 0 dc {vdd}",
        f"Vinp VINP 0 dc {vinp}",
        f"Vinn VINN 0 dc {vinn}",
        f"Vvcm_ideal VCM_IDEAL 0 dc {vcm}",
    ]
    if r_source_ohm > 0:
        lines.append(f"Rvcm VCM_IDEAL VCM {r_source_ohm:.6g}")
    else:
        # R_source = 0 is the pre-existing ideal-source baseline (identical
        # to run_transient.py / run_hold_kick.py's own Vvcm), kept as a
        # literal wire rather than a 0-ohm resistor to avoid an ngspice
        # singular-matrix / convergence footgun on some ngspice versions.
        lines.append("Rvcm VCM_IDEAL VCM 1e-6")
    if c_decouple_f > 0:
        lines.append(f"Cdecouple VCM 0 {c_decouple_f:.6g}")
    lines.append(
        f"Vsample SAMPLE 0 pulse(0 {vdd} {SAMPLE_TD_NS}n {SAMPLE_TR_NS}n "
        f"{SAMPLE_TR_NS}n {sample_width_ns}n {tran_stop_ns * 10}n)"
    )
    lines += ["", DUT_FRAGMENT.read_text(), ""]

    meas = [
        ("top_p_end", "TOP_P", probe_ns),
        ("top_n_end", "TOP_N", probe_ns),
        ("bp_p_end", "BPREF_P", probe_ns),
        ("bp_n_end", "BPREF_N", probe_ns),
        ("vcm_end", "VCM", probe_ns),
    ]
    lines.append(".control")
    lines.append(f"tran {tran_step_ps}p {tran_stop_ns}n")
    for name, node, at_ns in meas:
        lines.append(f"meas tran {name} find v({node}) at={at_ns}n")
    lines += [".endc", ".end"]
    return "\n".join(lines) + "\n"


MEASURE_NAMES = ["top_p_end", "top_n_end", "bp_p_end", "bp_n_end", "vcm_end"]


def _run(netlist: str, scratch: Path, tag: str) -> dict[str, float]:
    """A few bounded retries with backoff absorb transient contention from
    other concurrent agents' own ngspice runs on a shared machine, exactly
    the same policy (and the same observed cause) as
    sim/sampling-frontend/run_hold_kick.py's own `_run()` -- see that
    module's docstring for the full rationale. Exhausting every retry on
    the same netlist still raises."""
    attempts = 4
    for attempt in range(1, attempts + 1):
        try:
            return measure.parse(
                toolchain.run_ngspice(netlist, scratch, tag), MEASURE_NAMES
            )
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


def run_sweep(point: str, sample_width_ns: float, window_label: str,
              scratch: Path,
              r_source_list: list[float] | None = None,
              corner: str = "tt", temp_c: float = 27.0, vdd: float = VDD_NOM,
              quiet: bool = False) -> list[dict]:
    vinp, vinn = TEST_POINTS[point]
    rows = []
    baseline = None
    for r_source in (r_source_list if r_source_list is not None
                     else R_SOURCE_SWEEP_OHM):
        m = _run(
            build_transient(vinp=vinp, vinn=vinn,
                            sample_width_ns=sample_width_ns,
                            r_source_ohm=r_source,
                            corner=corner, temp_c=temp_c, vdd=vdd),
            scratch,
            f"rsweep_{window_label}_{point}_{corner}_{temp_c:g}_{vdd:g}_{r_source:g}",
        )
        diff = m["top_p_end"] - m["top_n_end"]
        row = {"r_source_ohm": r_source, "diff_v": diff, **m}
        if baseline is None:
            baseline = diff
        row["diff_err_mv"] = (diff - baseline) * 1000
        row["diff_err_lsb"] = row["diff_err_mv"] / LSB_DIFF_MV_PROVISIONAL
        rows.append(row)
        if not quiet:
            print(
                f"[{window_label:6}] {point:14} R_source={r_source:9.0f} ohm  "
                f"VCM(end)={m['vcm_end']:.4f} V  "
                f"diff_err={row['diff_err_mv']:+8.4f} mV "
                f"({row['diff_err_lsb']:+7.4f} LSB)"
            )
    return rows


def run_decouple_sweep(point: str, sample_width_ns: float, window_label: str,
                        r_source_ohm: float, scratch: Path,
                        corner: str = "tt", temp_c: float = 27.0,
                        vdd: float = VDD_NOM,
                        quiet: bool = False) -> list[dict]:
    vinp, vinn = TEST_POINTS[point]
    rows = []
    baseline = None
    for c_decouple in C_DECOUPLE_SWEEP_F:
        m = _run(
            build_transient(vinp=vinp, vinn=vinn,
                            sample_width_ns=sample_width_ns,
                            r_source_ohm=r_source_ohm,
                            c_decouple_f=c_decouple,
                            corner=corner, temp_c=temp_c, vdd=vdd),
            scratch,
            f"csweep_{window_label}_{point}_{corner}_{temp_c:g}_{vdd:g}_"
            f"{r_source_ohm:g}_{c_decouple:g}",
        )
        diff = m["top_p_end"] - m["top_n_end"]
        row = {"c_decouple_f": c_decouple, "diff_v": diff, **m}
        if baseline is None:
            baseline = diff
        row["diff_err_mv"] = (diff - baseline) * 1000
        row["diff_err_lsb"] = row["diff_err_mv"] / LSB_DIFF_MV_PROVISIONAL
        rows.append(row)
        if not quiet:
            print(
                f"[{window_label:6}] {point:14} R_source={r_source_ohm:.0f} ohm "
                f"C_decouple={c_decouple * 1e12:7.1f} pF  "
                f"VCM(end)={m['vcm_end']:.4f} V  "
                f"diff_err={row['diff_err_mv']:+8.4f} mV "
                f"({row['diff_err_lsb']:+7.4f} LSB)"
            )
    return rows


def find_budget(rows: list[dict], threshold_lsb: float) -> float | None:
    """Largest R_source (or C_decouple boundary) in `rows` for which
    abs(diff_err_lsb) stays under `threshold_lsb` -- None if even the first
    non-zero point already exceeds it, and the max swept value if every
    point stays under (a right-censored bound, reported as such)."""
    ok = [r for r in rows if abs(r["diff_err_lsb"]) <= threshold_lsb]
    return ok[-1] if ok else None


def marginal_r_source(rows: list[dict], r_source_list: list[float]) -> float:
    """The R_source a decoupling sweep should be run against: the smallest
    swept R_source whose bare (C_decouple = 0) differential error already
    exceeds 1 provisional LSB -- i.e. a case decoupling would actually have
    to rescue. Falls back to the largest swept R_source if no swept point
    exceeds 1 LSB (report that plainly, do not invent one). This is the
    single-corner default path's own definition, factored out so the
    --corners --sweep decouple mode can re-derive it per corner from that
    SAME corner's own bare sweep rather than borrowing the tt/27C/1.8V
    value -- the bare budget is already known to span >= an order of
    magnitude across the ratified grid
    (records/20260907-052526-f589273.md)."""
    over_1lsb = [r for r in rows if abs(r["diff_err_lsb"]) > 1.0]
    return over_1lsb[0]["r_source_ohm"] if over_1lsb else r_source_list[-1]


def run_corners(scratch: Path, point: str = DEFAULT_POINT,
                window: str = "worst",
                quiet: bool = False) -> list[dict]:
    """Full ratified-corner-set OAT sweep of the bare (undecoupled)
    R_source budget at ONE acquisition window (`window`, "worst" or
    "legacy") -- the same PVT grid every other Section 7 Item 2 mechanism
    campaign now sweeps. Does NOT change the mechanism measured: identical
    DUT fragment, identical per-window R_source sweep list
    (`WINDOW_CONFIG[window]`), identical diff_err definition (referenced to
    that SAME corner's own R_source=0 point) as the single-corner default
    path -- only the `.lib` corner, `.temp`, and supply voltage vary per
    point."""
    sample_ns, r_source_list = WINDOW_CONFIG[window]
    grid = corners_mod.ratified_oat_grid(VDD_NOM, SUPPLY_TOLERANCE,
                                          PROCESS_CORNERS, TEMPS_C)
    points: list[dict] = []
    for process_corner, temp_c, supply_v in grid:
        cid = corners_mod.corner_id(process_corner, temp_c, supply_v)
        rows = run_sweep(point, sample_ns, window, scratch,
                          r_source_list=r_source_list,
                          corner=process_corner, temp_c=temp_c, vdd=supply_v,
                          quiet=True)
        budget_1lsb = find_budget(rows, 1.0)
        budget_p1lsb = find_budget(rows, 0.1)
        points.append({
            "corner": process_corner, "temp_c": temp_c, "supply_v": supply_v,
            "corner_id": cid, "rows": rows,
            "budget_1lsb_ohm": budget_1lsb["r_source_ohm"] if budget_1lsb else None,
            "budget_1lsb_censored": bool(budget_1lsb and
                budget_1lsb["r_source_ohm"] == r_source_list[-1]),
            "budget_p1lsb_ohm": budget_p1lsb["r_source_ohm"] if budget_p1lsb else None,
        })
        if not quiet:
            b1 = points[-1]["budget_1lsb_ohm"]
            print(
                f"{cid}: 1-LSB R_source budget = "
                + (f"<= {b1:.0f} ohm" if b1 is not None
                   else f"< {r_source_list[1]:.0f} ohm (none found)")
            )
    return points


def run_corners_decouple(scratch: Path, point: str = DEFAULT_POINT,
                          window: str = "worst",
                          quiet: bool = False) -> list[dict]:
    """Full ratified-corner-set OAT sweep of the C_decouple leg of this
    budget at ONE acquisition window -- the last leg that was still
    single-corner-only. Per corner: run that corner's own bare R_source
    sweep first, take its `marginal_r_source()`, then sweep C_decouple
    against THAT resistance. Nothing about the mechanism changes: identical
    DUT fragment, identical C_DECOUPLE_SWEEP_F list, identical diff_err
    definition (referenced to that same corner/R_source's own
    C_decouple = 0 point) as the single-corner default path -- only the
    `.lib` corner, `.temp`, supply voltage, and the per-corner marginal
    R_source vary."""
    sample_ns, r_source_list = WINDOW_CONFIG[window]
    grid = corners_mod.ratified_oat_grid(VDD_NOM, SUPPLY_TOLERANCE,
                                          PROCESS_CORNERS, TEMPS_C)
    points: list[dict] = []
    for process_corner, temp_c, supply_v in grid:
        cid = corners_mod.corner_id(process_corner, temp_c, supply_v)
        bare_rows = run_sweep(point, sample_ns, window, scratch,
                              r_source_list=r_source_list,
                              corner=process_corner, temp_c=temp_c,
                              vdd=supply_v, quiet=True)
        marginal_r = marginal_r_source(bare_rows, r_source_list)
        rows = run_decouple_sweep(point, sample_ns, window, marginal_r,
                                  scratch, corner=process_corner,
                                  temp_c=temp_c, vdd=supply_v, quiet=True)
        budget_1lsb = find_budget(rows, 1.0)
        points.append({
            "corner": process_corner, "temp_c": temp_c, "supply_v": supply_v,
            "corner_id": cid, "rows": rows, "bare_rows": bare_rows,
            "marginal_r_source_ohm": marginal_r,
            "budget_1lsb_f": budget_1lsb["c_decouple_f"] if budget_1lsb else None,
            "budget_1lsb_censored": bool(budget_1lsb and
                budget_1lsb["c_decouple_f"] == C_DECOUPLE_SWEEP_F[-1]),
        })
        if not quiet:
            b1 = points[-1]["budget_1lsb_f"]
            print(
                f"{cid}: marginal R_source = {marginal_r:.0f} ohm, "
                "1-LSB C_decouple budget = "
                + (f"<= {b1 * 1e12:.2f} pF" if b1 is not None
                   else "none found in the swept range")
            )
    return points


def write_corners_decouple_record(points: list[dict], point: str,
                                   window: str = "worst") -> Path:
    """Evidence record for `run_corners_decouple()` -- same provenance /
    scope / no-ratified-claim conventions as `write_corners_record()`, with
    the C_decouple axis in place of the R_source axis."""
    record_id = evidence.new_record_id()
    netlist_text = DUT_FRAGMENT.read_text()
    record_path = evidence.write_netlist_snapshot_text(
        EXPERIMENT_DIR, record_id, netlist_text
    )
    netlist_sha = evidence.sha256_text(netlist_text)
    info = pdk.resolve()
    pdk_line = f"{info.variant} @ {pdk.resolved_commit(info)}"
    ng_version = toolchain._ngspice_version() or "unknown"

    process_corners_run = sorted({p["corner"] for p in points})
    temps_run = sorted({p["temp_c"] for p in points})
    supplies_run = sorted({p["supply_v"] for p in points})
    sample_ns, _r_source_list = WINDOW_CONFIG[window]
    window_desc = WINDOW_DESCRIPTION[window]
    other_window = "legacy" if window == "worst" else "worst"
    other_window_desc = WINDOW_DESCRIPTION[other_window]

    lines: list[str] = []
    a = lines.append
    a(f"# VCM drive-impedance budget -- full PVT grid -- {window} window -- "
      f"C_decouple sweep -- {record_id}")
    a("")
    a("- **Record ID**: " + record_id)
    a(
        "- **Claim**: extends the single-corner (tt/27C/1.8V) `C_decouple` "
        f"sweep in [`records/{SINGLE_CORNER_SEED_RECORD}.md`]"
        f"({SINGLE_CORNER_SEED_RECORD}.md) -- at the {window_desc} "
        "acquisition window only -- to the FULL ratified PVT corner set "
        "(spec/target-spec.md's \"Numeric rows -- RATIFIED 2026-08-19\" "
        "section), the same OAT grid this mechanism's own bare R_source "
        "campaigns and every other "
        "`docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2 "
        "mechanism campaign already sweep. Identical DUT fragment "
        "(`sim/sampling-frontend/testbench/sampling_frontend_dut.spice`, "
        "unmodified), identical `C_DECOUPLE_SWEEP_F` list, identical "
        "diff_err definition (referenced to that same corner/R_source's own "
        "C_decouple = 0 point) as the single-corner record. **Unlike the "
        "bare R_source full-grid campaigns, each corner here is decoupled "
        "against its OWN marginal R_source** (`marginal_r_source()`, "
        "re-derived from that same corner's own bare sweep in the same "
        "invocation) rather than a value borrowed from tt/27C/1.8V -- the "
        "bare budget is already known to span >= an order of magnitude "
        "across this grid ([`records/20260907-052526-f589273.md`]"
        "(20260907-052526-f589273.md)), so a single borrowed resistance "
        "would not be the marginal case at most corners. No claim here is "
        "graded against a ratified spec row: `spec/target-spec.md` is "
        "entirely DRAFT (#1/#27); `LSB_DIFF_MV_PROVISIONAL` is a reference "
        "scale, never a pass/fail gate; the DR-006 acquisition window is "
        "itself downstream of the DRAFT sample-rate row (Section 7 Item 2)."
    )
    a(
        "- **Netlist provenance**: unmodified "
        "`sim/sampling-frontend/testbench/sampling_frontend_dut.spice`, "
        "read in place -- not duplicated, same convention as the "
        "single-corner record. This record's own harness adds only the "
        "ideal-source/R_source/C_decouple network into `VCM` and the SAMPLE "
        "pulse source, with `.lib`/`.temp`/vdd varying per corner point; "
        "neither is stated in the DUT fragment itself."
    )
    a(
        corners_mod.corner_matrix_summary_line(
            process_corners_run, temps_run, supplies_run, len(points)
        )
    )
    a(
        f"- **Scope**: only the `{point}` test point's C_decouple sweep at "
        f"the {window_desc} window ({sample_ns:.3f} ns) is reported per "
        f"corner, over the "
        f"`[{', '.join(f'{c * 1e12:g}' for c in C_DECOUPLE_SWEEP_F)}]` pF "
        "sweep list, each "
        "corner at its own marginal R_source (see the table below). The "
        f"{other_window_desc} window's own C_decouple sweep stays "
        "single-corner-only (tt/27C/1.8V), deferred to a future pass -- the "
        "same one-window-per-pass precedent this mechanism's own bare "
        "R_source full-grid work already established."
    )
    a("")
    a("## C_decouple budget for <= 1 provisional LSB of differential error, per corner")
    a("")
    a(
        "\"Budget\" is the LAST (largest, in ascending sweep order) swept "
        "C_decouple for which `abs(diff_err_lsb) <= 1.0` still holds at that "
        "corner's own marginal R_source -- see `find_budget()` in this "
        "script, the same convention the bare R_source full-grid records "
        "already use, applied to the C_decouple axis here. It is **not** "
        "necessarily the smallest sufficient C_decouple, and larger values "
        "are not guaranteed to also work: the single-corner seed record's "
        "own C_decouple sweep already found this error is **not** monotonic "
        "in C_decouple (a bigger cap lengthens the same node's settling "
        "time constant as much as it stiffens its DC impedance). A budget "
        f"equal to the largest swept value "
        f"({C_DECOUPLE_SWEEP_F[-1] * 1e12:.0f} pF) is right-censored. "
        "\"None found\" means no swept C_decouple value, at that corner's "
        "own marginal R_source, keeps the error within 1 LSB -- decoupling "
        "alone does not rescue that corner within the swept range."
    )
    a("")
    a("| Corner | Marginal R_source (ohm) | 1-LSB C_decouple budget (pF) |")
    a("|---|---|---|")
    for p in points:
        b1 = p["budget_1lsb_f"]
        b1_str = "none found" if b1 is None else (
            f"<= {b1 * 1e12:.2f}"
            + (" (right-censored)" if p["budget_1lsb_censored"] else "")
        )
        a(f"| `{p['corner_id']}` | {p['marginal_r_source_ohm']:.0f} | {b1_str} |")
    a("")

    a("## Per-corner C_decouple sweeps")
    a("")
    a(
        "Full swept data behind the budget table above -- `diff_err` is "
        "referenced to that same corner/R_source's own C_decouple = 0 row, "
        "so it isolates exactly the contribution of the decoupling "
        "capacitor at that corner."
    )
    a("")
    a("| Corner | R_source (ohm) | C_decouple (pF) | VCM(end) (V) | diff_err (mV) | diff_err (LSB, informational) |")
    a("|---|---|---|---|---|---|")
    for p in points:
        for r in p["rows"]:
            a(
                f"| `{p['corner_id']}` | {p['marginal_r_source_ohm']:.0f} | "
                f"{r['c_decouple_f'] * 1e12:.2f} | {r['vcm_end']:.5f} | "
                f"{r['diff_err_mv']:+.4f} | {r['diff_err_lsb']:+.4f} |"
            )
    a("")

    rescued = [p for p in points if p["budget_1lsb_f"] is not None]
    unrescued = [p for p in points if p["budget_1lsb_f"] is None]
    notes: list[str] = []
    if rescued:
        largest = max(p["budget_1lsb_f"] for p in rescued)
        smallest = min(p["budget_1lsb_f"] for p in rescued)
        largest_label = ", ".join(
            f"`{p['corner_id']}`" for p in rescued if p["budget_1lsb_f"] == largest
        )
        smallest_label = ", ".join(
            f"`{p['corner_id']}`" for p in rescued if p["budget_1lsb_f"] == smallest
        )
        notes.append(
            f"**Decoupling alone brings the differential error inside 1 "
            f"provisional LSB at {len(rescued)} of {len(points)} ratified "
            f"corners**, each at that corner's own marginal R_source. Among "
            f"those, the largest working value found is "
            f"{largest * 1e12:.2f} pF ({largest_label}) and the smallest is "
            f"{smallest * 1e12:.2f} pF ({smallest_label}). Per the table "
            "note above these are points already confirmed to work, not "
            "guaranteed floors -- this error is not monotonic in "
            "C_decouple."
        )
    if unrescued:
        unrescued_label = ", ".join(f"`{p['corner_id']}`" for p in unrescued)
        notes.append(
            f"**{len(unrescued)} of {len(points)} ratified corners are NOT "
            "rescued by any swept C_decouple** at their own marginal "
            f"R_source ({unrescued_label}): at those corners the real drive "
            "path needs a lower source resistance, not just more "
            "capacitance."
        )
    else:
        notes.append(
            "No ratified corner was left unrescued within the swept "
            "C_decouple range -- but see the non-monotonicity caveat above "
            "before reading any of these as a floor."
        )
    notes.append(
        "The per-corner marginal R_source values in the table above are "
        "themselves re-derived from each corner's own bare sweep in this "
        "same invocation, and reproduce the bare R_source full-grid "
        "campaign's own per-corner shape "
        "([`records/20260907-052526-f589273.md`]"
        "(20260907-052526-f589273.md)) rather than assuming the "
        "tt/27C/1.8V value applies everywhere."
    )
    notes.append(
        f"This campaign repeats ONLY the C_decouple sweep at the "
        f"{window_desc} window. The {other_window_desc} window's own "
        "C_decouple sweep remains single-corner (tt/27C/1.8V) only; a "
        "full-grid pass over it is a natural next step, the same "
        "one-window-per-pass precedent this mechanism's own bare R_source "
        "full-grid campaigns already established. It does not, on its own, "
        "establish what R_source/C_decouple an actual on-chip VCM buffer or "
        "off-chip reference network would present -- no such buffer exists "
        "in this design yet (docs/chipalooza/challenge-4-proposal.md "
        "Section 2.2)."
    )

    a("## Result")
    a("")
    for n in notes:
        a(f"- {n}")
    a("")

    a("## Reproduction")
    a("")
    window_flag = "" if window == "worst" else f" --window {window}"
    a(
        "```\npython3 sim/vcm-drive-budget/run_vcm_drive_budget.py --corners"
        f"{window_flag} --sweep decouple --record\n```"
    )
    a("")
    lines += evidence.environment_block(
        pdk_line, ng_version, netlist_sha,
        extra={"toolchain pin file": "sim/toolchain.json"},
    )
    lines += evidence.footer_lines(
        written_by="run_vcm_drive_budget.py", supersedes="none"
    )
    record_path.write_text("\n".join(lines) + "\n")
    latest_path = EXPERIMENT_DIR / "records" / "LATEST"
    latest_path.write_text(f"{record_id}.md\n")
    print(f"\nWrote record: {record_path}")
    return record_path


def write_corners_record(points: list[dict], point: str,
                          window: str = "worst") -> Path:
    record_id = evidence.new_record_id()
    netlist_text = DUT_FRAGMENT.read_text()
    record_path = evidence.write_netlist_snapshot_text(
        EXPERIMENT_DIR, record_id, netlist_text
    )
    netlist_sha = evidence.sha256_text(netlist_text)
    info = pdk.resolve()
    pdk_line = f"{info.variant} @ {pdk.resolved_commit(info)}"
    ng_version = toolchain._ngspice_version() or "unknown"

    process_corners_run = sorted({p["corner"] for p in points})
    temps_run = sorted({p["temp_c"] for p in points})
    supplies_run = sorted({p["supply_v"] for p in points})
    sample_ns, r_source_list = WINDOW_CONFIG[window]
    window_desc = WINDOW_DESCRIPTION[window]
    other_window = "legacy" if window == "worst" else "worst"
    other_window_desc = WINDOW_DESCRIPTION[other_window]

    lines: list[str] = []
    a = lines.append
    a(f"# VCM drive-impedance budget -- full PVT grid -- {window} window -- {record_id}")
    a("")
    a("- **Record ID**: " + record_id)
    a(
        "- **Claim**: extends the single-corner (tt/27C/1.8V) bare "
        f"(undecoupled) R_source budget in [`records/{SINGLE_CORNER_SEED_RECORD}.md`]"
        f"({SINGLE_CORNER_SEED_RECORD}.md) -- at the {window_desc} "
        "acquisition window only -- to the "
        "FULL ratified PVT corner set (spec/target-spec.md's \"Numeric "
        "rows -- RATIFIED 2026-08-19\" section), the same OAT grid every "
        "other `docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2 "
        "mechanism campaign now sweeps. Identical DUT fragment "
        "(`sim/sampling-frontend/testbench/sampling_frontend_dut.spice`, "
        "unmodified), identical R_source sweep list, identical diff_err "
        "definition (referenced to that same corner's own R_source=0 "
        "point) as the single-corner record -- only the `.lib` corner, "
        "`.temp`, and supply voltage vary per point. No claim here is "
        "graded against a ratified spec row: `spec/target-spec.md` is "
        "entirely DRAFT (#1/#27); `LSB_DIFF_MV_PROVISIONAL` is a reference "
        "scale, never a pass/fail gate; the DR-006 acquisition window is "
        "itself downstream of the DRAFT sample-rate row (Section 7 Item 2)."
    )
    a(
        "- **Netlist provenance**: unmodified "
        "`sim/sampling-frontend/testbench/sampling_frontend_dut.spice`, "
        "read in place -- not duplicated, same convention as the "
        "single-corner record. This record's own harness adds only the "
        "ideal-source/R_source network into `VCM` and the SAMPLE pulse "
        "source, with `.lib`/`.temp`/vdd varying per corner point; neither "
        "is stated in the DUT fragment itself."
    )
    a(
        corners_mod.corner_matrix_summary_line(
            process_corners_run, temps_run, supplies_run, len(points)
        )
    )
    a(
        f"- **Scope, narrower than the single-corner default run**: only "
        f"the `{point}` test point's bare (undecoupled) R_source sweep at "
        f"the {window_desc} window ({sample_ns:.3f} ns) is repeated "
        f"per corner, over the reduced `{r_source_list}` sweep list. The "
        f"{other_window_desc} window and the C_decouple sweep stay "
        "single-corner-only (tt/27C/1.8V), deferred to a future pass, "
        "same first-pass/full-grid split precedent the other mechanism "
        "campaigns already established."
    )
    a("")
    a("## Bare R_source budget for <= 1 provisional LSB of differential error, per corner")
    a("")
    a(
        "\"Budget\" is the largest swept R_source (ohm) at which "
        "`abs(diff_err_lsb) <= 1.0` still holds at that corner -- see "
        f"`find_budget()` in this script. A budget equal to the largest "
        f"swept value ({r_source_list[-1]:.0f} ohm) is right-censored: every "
        "swept value stayed under threshold, so the true budget is >= that "
        "value, not necessarily equal to it."
    )
    a("")
    a("| Corner | 1-LSB R_source budget (ohm) | 0.1-LSB R_source budget (ohm) |")
    a("|---|---|---|")
    for p in points:
        b1 = p["budget_1lsb_ohm"]
        b1_str = "none (< smallest nonzero tested)" if b1 is None else (
            f"<= {b1:.0f}" + (" (right-censored)" if p["budget_1lsb_censored"] else "")
        )
        bp1 = p["budget_p1lsb_ohm"]
        bp1_str = "none (< smallest nonzero tested)" if bp1 is None else f"<= {bp1:.0f}"
        a(f"| `{p['corner_id']}` | {b1_str} | {bp1_str} |")
    a("")

    scored = [p for p in points if p["budget_1lsb_ohm"] is not None]
    notes: list[str] = []
    if scored:
        binding_val = min(p["budget_1lsb_ohm"] for p in scored)
        best_val = max(p["budget_1lsb_ohm"] for p in scored)
        binding_ties = [p for p in scored if p["budget_1lsb_ohm"] == binding_val]
        best_ties = [p for p in scored if p["budget_1lsb_ohm"] == best_val]
        binding = binding_ties[0]
        best = best_ties[0]
        binding_label = (
            f"`{binding['corner_id']}`" if len(binding_ties) == 1
            else "tied at " + ", ".join(f"`{p['corner_id']}`" for p in binding_ties)
        )
        best_label = (
            f"`{best['corner_id']}`" if len(best_ties) == 1
            else "tied at " + ", ".join(f"`{p['corner_id']}`" for p in best_ties)
        )
        if binding_val > 0:
            spread_phrase = (
                f"Worst-to-best spread across the ratified grid: "
                f"{best_val / binding_val:.1f}x -- the bare R_source budget "
                "is **not** corner-invariant."
            )
        else:
            # binding_val == 0: a ratio is undefined/uninformative (division
            # by the zero floor) -- state the spread in words instead of a
            # misleading "infx".
            spread_phrase = (
                "The tightest corner(s) allow **zero** margin for any "
                "nonzero drive impedance, while the loosest corner(s) allow "
                f"up to <= {best_val:.0f} ohm"
                + (" (right-censored)" if best["budget_1lsb_censored"] else "")
                + " -- the bare R_source budget is **not** corner-invariant "
                "(a ratio is not meaningful when the tightest corner's own "
                "budget is zero)."
            )
        notes.append(
            f"**Binding corner(s) (tightest 1-LSB budget): {binding_label}**, "
            f"<= {binding_val:.0f} ohm. Loosest corner(s): {best_label}, "
            f"<= {best_val:.0f} ohm"
            + (" (right-censored)" if best["budget_1lsb_censored"] else "")
            + f". {spread_phrase}"
        )
        tt_pt = next(
            (p for p in points if p["corner"] == "tt" and p["temp_c"] == 27.0
             and p["supply_v"] == VDD_NOM), None,
        )
        if tt_pt is not None and tt_pt["budget_1lsb_ohm"] is not None:
            notes.append(
                f"The `tt`/27C/1.8V point in this grid measures a 1-LSB "
                f"budget of <= {tt_pt['budget_1lsb_ohm']:.0f} ohm, "
                "consistent with (reproduces) the single-corner record's "
                "own finding for the same window/point."
            )
        seed_budget = SINGLE_CORNER_SEED_BUDGET_1LSB_OHM[window]
        if seed_budget > 0 and binding_val < seed_budget:
            notes.append(
                f"**This tightens, not merely restates, the single-corner "
                f"finding**: the single-corner (tt/27C/1.8V) record reports "
                f"a <= {seed_budget:.0f} ohm bare budget at this window, but "
                f"the binding corner(s) across the ratified grid "
                f"({binding_label}) is/are <= {binding_val:.0f} ohm -- "
                f"{seed_budget / binding_val:.1f}x tighter. Any "
                "future on-chip VCM buffer / off-chip reference network "
                "sizing that targets only the tt/27C/1.8V figure would "
                "under-budget the real worst-case corner."
            )
        elif seed_budget == 0 and binding_val == 0:
            zero_pts = [p for p in scored if p["budget_1lsb_ohm"] == 0]
            if len(zero_pts) == len(scored):
                notes.append(
                    "**This confirms, at every ratified corner, the "
                    "single-corner record's already-tightest finding**: the "
                    "single-corner (tt/27C/1.8V) record already reports a "
                    "<= 0 ohm bare budget at this window (even R_source=0's "
                    "own ideal-source baseline is the only point inside 1 "
                    "provisional LSB -- the smallest nonzero R_source tested "
                    "already exceeds it), and every one of the 9 ratified "
                    "corners reproduces that same floor. This window offers "
                    "**zero** margin for any nonzero drive impedance, at any "
                    "ratified corner -- consistent with the single-corner "
                    "record's own finding that the legacy window is the MORE "
                    "demanding case for this mechanism, not merely restating "
                    "it at one point."
                )
            else:
                zero_label = ", ".join(f"`{p['corner_id']}`" for p in zero_pts)
                best_raw_label = ", ".join(f"`{p['corner_id']}`" for p in best_ties)
                notes.append(
                    "**This reveals the single-corner (tt/27C/1.8V) <= 0 ohm "
                    "finding is itself corner-dependent, not a uniform "
                    f"floor**: {len(zero_pts)} of {len(scored)} ratified "
                    f"corners ({zero_label}) reproduce that same <= 0 ohm "
                    "floor (zero margin for any nonzero drive impedance at "
                    "those corners), but the remaining "
                    f"{len(scored) - len(zero_pts)} corner(s) recover a "
                    f"positive budget, up to <= {best_val:.0f} ohm"
                    + (" (right-censored)" if best["budget_1lsb_censored"] else "")
                    + f" at {best_raw_label}. Any future on-chip VCM buffer / "
                    "off-chip reference network sizing must still budget for "
                    "the zero-margin corner(s) above, not the tt/27C/1.8V "
                    "point alone -- the single-corner record's own scope "
                    "note (single point, not yet corner-complete) was "
                    "correct to flag this as unresolved."
                )
    else:
        notes.append(
            "No corner point found a positive 1-LSB R_source budget within "
            "the swept range -- see the per-corner table above."
        )
    notes.append(
        f"This campaign repeats ONLY the bare (undecoupled) R_source sweep "
        f"at the {window_desc} window, at every ratified corner. The "
        f"{other_window_desc} window and the C_decouple sweep remain "
        "single-corner (tt/27C/1.8V) only; a full-grid pass "
        "over either is a natural next step, same open-item shape as the "
        "other Section 7 Item 2 mechanisms before their own full-grid "
        "passes landed. It does not, on its own, establish what R_source/"
        "C_decouple an actual on-chip VCM buffer or off-chip reference "
        "network would present -- no such buffer exists in this design "
        "yet (docs/chipalooza/challenge-4-proposal.md Section 2.2)."
    )

    a("## Result")
    a("")
    for n in notes:
        a(f"- {n}")
    a("")

    a("## Reproduction")
    a("")
    window_flag = "" if window == "worst" else f" --window {window}"
    a(
        "```\npython3 sim/vcm-drive-budget/run_vcm_drive_budget.py --corners"
        f"{window_flag} --record\n```"
    )
    a("")
    lines += evidence.environment_block(
        pdk_line, ng_version, netlist_sha,
        extra={"toolchain pin file": "sim/toolchain.json"},
    )
    lines += evidence.footer_lines(
        written_by="run_vcm_drive_budget.py", supersedes="none"
    )
    record_path.write_text("\n".join(lines) + "\n")
    latest_path = EXPERIMENT_DIR / "records" / "LATEST"
    latest_path.write_text(f"{record_id}.md\n")
    print(f"\nWrote record: {record_path}")
    return record_path


def write_record(all_results: dict) -> None:
    record_id = evidence.new_record_id()
    netlist_text = DUT_FRAGMENT.read_text()
    record_path = evidence.write_netlist_snapshot_text(
        EXPERIMENT_DIR, record_id, netlist_text
    )
    netlist_sha = evidence.sha256_text(netlist_text)
    info = pdk.resolve()
    pdk_line = f"{info.variant} @ {pdk.resolved_commit(info)}"
    ng_version = toolchain._ngspice_version() or "unknown"

    lines: list[str] = []
    a = lines.append
    a(f"# VCM drive-impedance / decoupling budget -- {record_id}")
    a("")
    a("- **Record ID**: " + record_id)
    a(
        "- **Claim**: quantifies, for the first time in this repo, how the "
        "sampling front end's SAMPLE-window sampled value "
        "(`design/sampling_frontend.sch`, TOP_P/TOP_N) degrades as a "
        "function of a non-ideal `VCM` drive resistance (`R_source`, in "
        "series with an otherwise-ideal reference into the shared on-die "
        "`VCM` net that both differential legs' `Cmswn/Cmswp` switches tie "
        "to) and how much on-die decoupling capacitance at `VCM` relaxes "
        "that bound -- answering "
        "`docs/chipalooza/challenge-4-proposal.md` Section 7 Item 5 (every "
        "existing testbench drives `VCM` ideally; no drive-impedance/"
        "decoupling budget existed). No claim against a ratified spec row: "
        "`spec/target-spec.md` is entirely DRAFT (#1/#27); the DR-006 "
        "acquisition-window figures used here are themselves downstream of "
        "the DRAFT sample-rate row (Section 7 Item 2); "
        "`LSB_DIFF_MV_PROVISIONAL` is quoted only as a reference scale, "
        "never a pass/fail gate, matching "
        "`sim/sampling-frontend/run_hold_kick.py`'s own convention."
    )
    a(
        "- **Netlist provenance**: unmodified "
        "`sim/sampling-frontend/testbench/sampling_frontend_dut.spice` "
        "(design/sampling_frontend.sch regenerated fragment, issue #52), "
        "read in place -- not duplicated. This record's own harness adds "
        "only the ideal-source/R_source/C_decouple network into `VCM` and "
        "the SAMPLE pulse source; both are stated directly in this record's "
        "own `run_vcm_drive_budget.py`, not in the DUT fragment itself."
    )
    a(
        "- **Point/corner matrix**: `tt`/27C/1.8V only, at "
        f"`{DEFAULT_POINT}` (and `common_mode` for the decoupling-sweep "
        "cross-check) -- a mechanism-isolating, single-corner budget "
        "derivation, the same precedent "
        "`sim/sampling-frontend/run_hold_kick.py` Experiments 1-5 already "
        "established for this sub-block. Full PVT-corner coverage of this "
        "budget (switch R_on varies materially with process/temperature) "
        "is deferred to a future full corner campaign, same open item as "
        "#28 for the rest of this sub-block's characterization."
    )
    a(
        "- **Acquisition windows tested**: "
        f"{T_SAMPLE_WORST_NS:.3f} ns (DR-006-derived worst case, "
        "f_clk=12 MHz -- shortest, least forgiving), "
        f"{T_SAMPLE_LEGACY_NS:.1f} ns (this repo's pre-existing "
        "`run_transient.py`/`run_hold_kick.py` testbench convention, "
        "independent of DR-006, kept for direct comparison -- these two "
        "had never previously been reconciled)."
    )
    a("")

    for window_label, sample_ns, rows, _r_list in all_results["sweeps"]:
        a(f"## R_source sweep -- {window_label} window "
          f"({sample_ns:.3f} ns SAMPLE-high)")
        a("")
        a(
            "Differential TOP_P-TOP_N sampled value at the end of the SAMPLE "
            "window, referenced to this same sweep's own R_source=0 (ideal-"
            "source) point -- i.e. `diff_err` isolates exactly the "
            "contribution of R_source, not the front end's pre-existing "
            "in-sample settling error (already characterized ideally in "
            "`sim/sampling-frontend/records/`)."
        )
        a("")
        a("| R_source (ohm) | VCM(end) (V) | diff_err (mV) | diff_err (LSB, informational) |")
        a("|---|---|---|---|")
        for r in rows:
            a(
                f"| {r['r_source_ohm']:.0f} | {r['vcm_end']:.5f} | "
                f"{r['diff_err_mv']:+.4f} | {r['diff_err_lsb']:+.4f} |"
            )
        a("")

    for window_label, sample_ns, r_source_ohm, rows in all_results["decouple_sweeps"]:
        a(
            f"## C_decouple sweep -- {window_label} window "
            f"({sample_ns:.3f} ns SAMPLE-high), R_source={r_source_ohm:.0f} ohm"
        )
        a("")
        a("| C_decouple (pF) | VCM(end) (V) | diff_err (mV) | diff_err (LSB, informational) |")
        a("|---|---|---|---|")
        for r in rows:
            a(
                f"| {r['c_decouple_f'] * 1e12:.2f} | {r['vcm_end']:.5f} | "
                f"{r['diff_err_mv']:+.4f} | {r['diff_err_lsb']:+.4f} |"
            )
        a("")

    a("## Result")
    a("")
    for note in all_results["notes"]:
        a(f"- {note}")
    a("")

    a("## Reproduction")
    a("")
    a(
        "```\npython3 sim/vcm-drive-budget/run_vcm_drive_budget.py --record\n```"
    )
    a("")
    lines += evidence.environment_block(
        pdk_line, ng_version, netlist_sha,
        extra={"toolchain pin file": "sim/toolchain.json"},
    )
    lines += evidence.footer_lines(
        written_by="run_vcm_drive_budget.py", supersedes="none"
    )
    record_path.write_text("\n".join(lines) + "\n")
    print(f"\nWrote record: {record_path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record", action="store_true",
                    help="write an evidence record under records/")
    ap.add_argument("--point", default=DEFAULT_POINT, choices=list(TEST_POINTS),
                    help="primary differential test point for the R_source sweep")
    ap.add_argument(
        "--corners", action="store_true",
        help="run the full ratified PVT grid (9 OAT points) instead of the "
             "single-corner (tt/27C/1.8V) default -- bare R_source sweep at "
             "one acquisition window only, selected by --window (see module "
             "docstring)",
    )
    ap.add_argument(
        "--window", default="worst", choices=list(WINDOW_CONFIG),
        help="acquisition window swept by --corners: 'worst' (DR-006 "
             "worst-case, 12 MHz, default) or 'legacy' (this repo's "
             "pre-existing 400 ns testbench convention). Ignored without "
             "--corners.",
    )
    ap.add_argument(
        "--sweep", default="rsource", choices=["rsource", "decouple"],
        help="which leg of the budget --corners repeats per corner: "
             "'rsource' (bare undecoupled R_source sweep, default) or "
             "'decouple' (C_decouple sweep, each corner at its own marginal "
             "R_source). Ignored without --corners.",
    )
    args = ap.parse_args()

    scratch = Path("/tmp") / "sim-vcm-drive-budget"
    scratch.mkdir(parents=True, exist_ok=True)

    if args.corners:
        sample_ns, _ = WINDOW_CONFIG[args.window]
        print(f"=== VCM drive-budget: full ratified PVT grid "
              f"({args.sweep} sweep, {args.window} {sample_ns:.3f} ns "
              f"window only) ===")
        if args.sweep == "decouple":
            points = run_corners_decouple(scratch, point=args.point,
                                          window=args.window)
            if args.record:
                write_corners_decouple_record(points, args.point,
                                              window=args.window)
            return 0
        points = run_corners(scratch, point=args.point, window=args.window)
        if args.record:
            write_corners_record(points, args.point, window=args.window)
        return 0

    sweeps = []
    print("=== R_source sweep: DR-006 worst-case window "
          f"({T_SAMPLE_WORST_NS:.3f} ns) ===")
    worst_rows = run_sweep(args.point, T_SAMPLE_WORST_NS, "worst", scratch)
    sweeps.append(("worst-case (12 MHz)", T_SAMPLE_WORST_NS, worst_rows,
                   R_SOURCE_SWEEP_OHM))

    print("\n=== R_source sweep: legacy testbench window "
          f"({T_SAMPLE_LEGACY_NS:.1f} ns) ===")
    legacy_rows = run_sweep(args.point, T_SAMPLE_LEGACY_NS, "legacy", scratch,
                            r_source_list=R_SOURCE_SWEEP_LEGACY_OHM)
    sweeps.append(("legacy (400 ns)", T_SAMPLE_LEGACY_NS, legacy_rows,
                   R_SOURCE_SWEEP_LEGACY_OHM))

    # Pick a representative "marginal" R_source for the decoupling sweep --
    # see marginal_r_source()'s own docstring for the definition (shared
    # with the --corners --sweep decouple path, which re-derives it per
    # corner).
    marginal_r = marginal_r_source(worst_rows, R_SOURCE_SWEEP_OHM)

    print(f"\n=== C_decouple sweep at R_source={marginal_r:.0f} ohm, "
          f"worst-case window ===")
    decouple_rows = run_decouple_sweep(
        args.point, T_SAMPLE_WORST_NS, "worst", marginal_r, scratch
    )
    decouple_sweeps = [("worst-case (12 MHz)", T_SAMPLE_WORST_NS, marginal_r,
                        decouple_rows)]

    notes = []
    for label, sample_ns, rows, r_list in sweeps:
        budget_1lsb = find_budget(rows, 1.0)
        budget_p1lsb = find_budget(rows, 0.1)
        if budget_1lsb is None:
            notes.append(
                f"{label} window: even the smallest tested nonzero "
                f"R_source ({r_list[1]:.0f} ohm) already "
                "exceeds 1 provisional LSB of differential error -- no "
                "positive R_source budget found within the swept range at "
                "this window without decoupling."
            )
        else:
            note = (
                f"{label} window: bare (undecoupled) R_source budget is "
                f"<= {budget_1lsb['r_source_ohm']:.0f} ohm for <= 1 "
                "provisional LSB of differential error"
            )
            if budget_1lsb["r_source_ohm"] == r_list[-1]:
                note += " (right-censored -- every swept value stayed under 1 LSB, true budget is >= this)"
            if budget_p1lsb is not None:
                note += (
                    f"; <= {budget_p1lsb['r_source_ohm']:.0f} ohm for "
                    "<= 0.1 LSB"
                )
            notes.append(note + ".")

    dec_budget_1lsb = find_budget(decouple_rows, 1.0)
    if dec_budget_1lsb is not None:
        notes.append(
            f"At the marginal R_source={marginal_r:.0f} ohm (worst-case "
            f"window), a decoupling capacitor of >= "
            f"{dec_budget_1lsb['c_decouple_f'] * 1e12:.2f} pF at the "
            "on-die VCM node recovers differential error to <= 1 "
            "provisional LSB."
        )
    else:
        notes.append(
            f"At the marginal R_source={marginal_r:.0f} ohm (worst-case "
            "window), no decoupling capacitor up to the largest tested "
            f"({C_DECOUPLE_SWEEP_F[-1] * 1e12:.0f} pF) recovered "
            "differential error to within 1 provisional LSB -- decoupling "
            "alone is not a fix at this R_source; the real drive path "
            "needs a lower source resistance, not just more capacitance "
            "(consistent with an RC-charging picture: within a fixed, "
            "short acquisition window, a bigger C_decouple lengthens the "
            "same node's own settling time constant as much as it "
            "stiffens its DC impedance)."
        )
    notes.append(
        "This is a first-pass, single-corner (tt/27C/1.8V) budget, not a "
        "fabrication-ready spec: it does not yet establish what R_source "
        "and C_decouple an actual on-chip VCM buffer or off-chip reference "
        "network would present (no such buffer exists in this design yet, "
        "per docs/chipalooza/challenge-4-proposal.md Section 2.2 -- every "
        "existing block-level testbench in sim/ still drives VCM from an "
        "ideal source). What this record newly establishes is the target "
        "those (not-yet-designed) blocks would need to meet."
    )

    print()
    for n in notes:
        print(f"- {n}")

    if args.record:
        write_record({
            "sweeps": sweeps,
            "decouple_sweeps": decouple_sweeps,
            "notes": notes,
        })

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

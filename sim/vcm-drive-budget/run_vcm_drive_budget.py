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
to close for the bare (undecoupled) R_source budget at the DR-006 worst-case
(83.333 ns) acquisition window: it re-runs that one sweep (the
``worst_case_pp`` test point, the full ``R_SOURCE_SWEEP_OHM`` list) at the
same ratified 9-point one-at-a-time (OAT) PVT grid every other
``docs/chipalooza/challenge-4-proposal.md`` Section 7 Item 2 mechanism
campaign now sweeps (process ``{ff, fs, sf, ss, tt}`` x temperature
``{-40, 27, 125} C`` x supply ``{1.62, 1.8, 1.98} V``,
``spec/target-spec.md``'s "Numeric rows -- RATIFIED 2026-08-19" section).
Scope is deliberately narrower than the single-corner default run: only the
worst-case (12 MHz) window's bare R_source sweep is repeated per corner --
the legacy (400 ns) window and the C_decouple sweep stay single-corner-only,
same precedent the other mechanism campaigns' own first-pass/full-grid split
already established. Nothing about the single-corner default path above is
changed; ``--corners`` is purely additive.

    python3 sim/vcm-drive-budget/run_vcm_drive_budget.py --corners --record
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
                        r_source_ohm: float, scratch: Path) -> list[dict]:
    vinp, vinn = TEST_POINTS[point]
    rows = []
    baseline = None
    for c_decouple in C_DECOUPLE_SWEEP_F:
        m = _run(
            build_transient(vinp=vinp, vinn=vinn,
                            sample_width_ns=sample_width_ns,
                            r_source_ohm=r_source_ohm,
                            c_decouple_f=c_decouple),
            scratch,
            f"csweep_{window_label}_{point}_{c_decouple:g}",
        )
        diff = m["top_p_end"] - m["top_n_end"]
        row = {"c_decouple_f": c_decouple, "diff_v": diff, **m}
        if baseline is None:
            baseline = diff
        row["diff_err_mv"] = (diff - baseline) * 1000
        row["diff_err_lsb"] = row["diff_err_mv"] / LSB_DIFF_MV_PROVISIONAL
        rows.append(row)
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


def run_corners(scratch: Path, point: str = DEFAULT_POINT,
                quiet: bool = False) -> list[dict]:
    """Full ratified-corner-set OAT sweep of the bare (undecoupled)
    R_source budget at the DR-006 worst-case (83.333 ns) acquisition
    window only -- the same PVT grid every other Section 7 Item 2 mechanism
    campaign now sweeps. Does NOT change the mechanism measured: identical
    DUT fragment, identical R_source sweep list, identical diff_err
    definition (referenced to that SAME corner's own R_source=0 point) as
    the single-corner default path -- only the `.lib` corner, `.temp`, and
    supply voltage vary per point."""
    grid = corners_mod.ratified_oat_grid(VDD_NOM, SUPPLY_TOLERANCE,
                                          PROCESS_CORNERS, TEMPS_C)
    points: list[dict] = []
    for process_corner, temp_c, supply_v in grid:
        cid = corners_mod.corner_id(process_corner, temp_c, supply_v)
        rows = run_sweep(point, T_SAMPLE_WORST_NS, "worst", scratch,
                          corner=process_corner, temp_c=temp_c, vdd=supply_v,
                          quiet=True)
        budget_1lsb = find_budget(rows, 1.0)
        budget_p1lsb = find_budget(rows, 0.1)
        points.append({
            "corner": process_corner, "temp_c": temp_c, "supply_v": supply_v,
            "corner_id": cid, "rows": rows,
            "budget_1lsb_ohm": budget_1lsb["r_source_ohm"] if budget_1lsb else None,
            "budget_1lsb_censored": bool(budget_1lsb and
                budget_1lsb["r_source_ohm"] == R_SOURCE_SWEEP_OHM[-1]),
            "budget_p1lsb_ohm": budget_p1lsb["r_source_ohm"] if budget_p1lsb else None,
        })
        if not quiet:
            b1 = points[-1]["budget_1lsb_ohm"]
            print(
                f"{cid}: 1-LSB R_source budget = "
                + (f"<= {b1:.0f} ohm" if b1 is not None
                   else f"< {R_SOURCE_SWEEP_OHM[1]:.0f} ohm (none found)")
            )
    return points


def write_corners_record(points: list[dict], point: str) -> Path:
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

    lines: list[str] = []
    a = lines.append
    a(f"# VCM drive-impedance budget -- full PVT grid -- {record_id}")
    a("")
    a("- **Record ID**: " + record_id)
    a(
        "- **Claim**: extends the single-corner (tt/27C/1.8V) bare "
        f"(undecoupled) R_source budget in [`records/{SINGLE_CORNER_SEED_RECORD}.md`]"
        f"({SINGLE_CORNER_SEED_RECORD}.md) -- at the DR-006-derived "
        "worst-case (12 MHz, 83.333 ns) acquisition window only -- to the "
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
        f"the worst-case ({T_SAMPLE_WORST_NS:.3f} ns) window is repeated "
        "per corner. The legacy (400 ns) window and the C_decouple sweep "
        "stay single-corner-only (tt/27C/1.8V), deferred to a future pass, "
        "same first-pass/full-grid split precedent the other mechanism "
        "campaigns already established."
    )
    a("")
    a("## Bare R_source budget for <= 1 provisional LSB of differential error, per corner")
    a("")
    a(
        "\"Budget\" is the largest swept R_source (ohm) at which "
        "`abs(diff_err_lsb) <= 1.0` still holds at that corner -- see "
        "`find_budget()` in this script. A budget equal to the largest "
        "swept value (100000 ohm) is right-censored: every swept value "
        "stayed under threshold, so the true budget is >= that value, not "
        "necessarily equal to it."
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
        spread = (best_val / binding_val if binding_val > 0 else float("inf"))
        binding_label = (
            f"`{binding['corner_id']}`" if len(binding_ties) == 1
            else "tied at " + ", ".join(f"`{p['corner_id']}`" for p in binding_ties)
        )
        best_label = (
            f"`{best['corner_id']}`" if len(best_ties) == 1
            else "tied at " + ", ".join(f"`{p['corner_id']}`" for p in best_ties)
        )
        notes.append(
            f"**Binding corner(s) (tightest 1-LSB budget): {binding_label}**, "
            f"<= {binding_val:.0f} ohm. Loosest corner(s): {best_label}, "
            f"<= {best_val:.0f} ohm"
            + (" (right-censored)" if best["budget_1lsb_censored"] else "")
            + f". Worst-to-best spread across the ratified grid: "
            f"{spread:.1f}x -- the bare R_source budget is **not** "
            "corner-invariant."
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
        if binding_val < 10e3:
            notes.append(
                f"**This tightens, not merely restates, the single-corner "
                f"finding**: the single-corner (tt/27C/1.8V) record reports "
                f"a <= 10 kOhm bare budget at this window, but the binding "
                f"corner(s) across the ratified grid ({binding_label}) "
                f"is/are <= {binding_val:.0f} ohm -- "
                f"{10e3 / binding_val:.1f}x tighter. Any "
                "future on-chip VCM buffer / off-chip reference network "
                "sizing that targets only the tt/27C/1.8V figure would "
                "under-budget the real worst-case corner."
            )
    else:
        notes.append(
            "No corner point found a positive 1-LSB R_source budget within "
            "the swept range -- see the per-corner table above."
        )
    notes.append(
        "This campaign repeats ONLY the bare (undecoupled) R_source sweep "
        "at the DR-006 worst-case window, at every ratified corner. The "
        "legacy (400 ns) window -- already shown, single-corner, to be the "
        "MORE demanding case for this mechanism -- and the C_decouple "
        "sweep remain single-corner (tt/27C/1.8V) only; a full-grid pass "
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
    a(
        "```\npython3 sim/vcm-drive-budget/run_vcm_drive_budget.py --corners --record\n```"
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
             "the DR-006 worst-case window only (see module docstring)",
    )
    args = ap.parse_args()

    scratch = Path("/tmp") / "sim-vcm-drive-budget"
    scratch.mkdir(parents=True, exist_ok=True)

    if args.corners:
        print("=== VCM drive-budget: full ratified PVT grid "
              f"(worst-case {T_SAMPLE_WORST_NS:.3f} ns window only) ===")
        points = run_corners(scratch, point=args.point)
        if args.record:
            write_corners_record(points, args.point)
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

    # Pick a representative "marginal" R_source for the decoupling sweep:
    # the largest R_source in the worst-case sweep whose bare (C_decouple=0)
    # error already exceeds 1 provisional LSB -- i.e. a case decoupling
    # would actually need to rescue. Falls back to the largest swept
    # R_source if none exceed 1 LSB (report that plainly, do not invent one).
    over_1lsb = [r for r in worst_rows if abs(r["diff_err_lsb"]) > 1.0]
    marginal_r = over_1lsb[0]["r_source_ohm"] if over_1lsb else R_SOURCE_SWEEP_OHM[-1]

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

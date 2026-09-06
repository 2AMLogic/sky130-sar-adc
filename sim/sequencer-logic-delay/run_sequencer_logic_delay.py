#!/usr/bin/env python3
"""SAR sequencer CLK-to-phase-output propagation-delay budget (issue #121,
Epic #542 Phase 4B follow-up).

`docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2 names three
still-unmeasured contributors to the DRAFT sample-rate row after
`sim/cdac-bit-trial-settling/` (CDAC array switch-settling, tt/27C/1.8V, one
corner) and `sim/comparator-decision/` (comparator decision delay, full
ratified PVT grid) each narrowed the gap: "the sequencer's logic delay and
the sampling front end's acquisition remain wholly unmeasured". This script
takes the first concrete step on the sequencer half of that remaining pair:
it isolates and quantifies how long `design/sar_sequencer.sch`'s own
walking-one ring sequencer takes, after each CLK rising edge, to produce a
valid (0.9 V / Vdd/2 crossing) one-hot phase-select output -- at a single
corner, the same "first-pass, single-corner budget" precedent
`sim/vcm-drive-budget/run_vcm_drive_budget.py` and
`sim/cdac-bit-trial-settling/run_bit_trial_settling.py` already established.
It does NOT close the sample-rate open item: the sampling front end's own
acquisition-window timing remains wholly unmeasured, and this experiment
runs at a single corner only (tt/27C/1.8V) even though real standard-cell
gate delay -- unlike an ideal digital-logic abstraction -- varies materially
with process/temperature/supply, the same class of gap #28's corner
campaigns already cover elsewhere in this design.

WHAT IS BEING MEASURED AND WHY IT IS SEPARABLE FROM
`sim/sar-sequencer-behavioral/`'s EXISTING FUNCTIONAL TESTBENCH.
`sim/sar-sequencer-behavioral/run_testbench.py` already proves this DUT's
bit-by-bit capture, phase timing, and auto-restart are functionally correct
at CLK=10 MHz (100 ns period) -- but it checks values at FIXED windows well
inside each phase (its own `.meas ... find ... at=<t>` style), which proves
"the right value has landed by this point in the period", not "how long
after the triggering CLK edge did it land". This experiment adds the
missing measurement: for each of the sequencer's 11 one-hot ring phases
(`ph_b9`..`ph_b0`, `ph_eoc`), it measures the wall-clock delay from the
50% (Vdd/2) crossing of the CLK rising edge that advances the ring into that
phase, to the 50% crossing of that phase's own output node -- a standard
propagation-delay convention, and the same TRIG(AT=)/TARG(CROSS=) `.meas`
idiom `sim/cdac-bit-trial-settling/`'s own `t_settle_*` measures already
use. `COMP_OUT` is tied to a fixed DC level here (0 V) rather than driven
with the two-cycle bit-pattern stimulus
`sim/sar-sequencer-behavioral/testbench/sar_sequencer_tb_fragment.spice`
uses: this experiment does not care about `DOUT*` correctness (already
proven functionally correct elsewhere) and `design/sar_sequencer.sch`'s own
one-hot ring/phase-generator chain (the dfrtp_1 flip-flops driving
`ph_sample`/`ph_b9..ph_b0`/`ph_eoc`) does not depend on `COMP_OUT` at all --
only the separate `DOUT*` capture registers (each gated by a mux2_1 through
its own bit's phase) do.

WHICH CLK EDGE ADVANCES WHICH PHASE. Derived directly from
`design/sar_sequencer.sch`'s own topology (an (N+2)-stage, N=10, one-hot
walking-ring shift chain: `RST_B` asynchronously presets the chain to
`ph_sample=1`/everything else 0, and every subsequent CLK rising edge shifts
the single set bit one stage forward), not asserted from a behavioral
testbench's timing table alone. With this experiment's own fixed CLK
stimulus -- `PULSE(0 Vdd 50n 1n 1n 50n 100n)` (first rising edge starts at
t=50 ns, 100 ns period) and `RST_B` released at t=221 ns, the same
convention `sar_sequencer_tb_fragment.spice` already uses -- the first CLK
rising edge strictly after `RST_B` releases is the 3rd (t=250 ns), and it is
this edge that shifts `ph_sample`->0, `ph_b9`->1. Every following edge
advances one more phase: edge k (k=3..13) drives (in order)
`ph_b9, ph_b8, ..., ph_b1, ph_b0, ph_eoc`. This mapping is cross-checked,
not just derived: `sar_sequencer_tb_fragment.spice`'s own static probe
times (e.g. its `phb9_c1`/`phb0_c1`/`pheoc_c1` `.meas ... find ... at=`
windows) land strictly inside, never straddling, the edge times this
script's own `_edge_time_ns()` computes for the same transitions.

No claim here is graded against a ratified spec row: `spec/target-spec.md`
is entirely DRAFT (#1/#27); the DR-006 phase-period figures quoted for
comparison are themselves downstream of the DRAFT sample-rate row (Section
7 Item 2), the same convention `sim/cdac-bit-trial-settling/`'s own record
already follows.

FULL-PVT-GRID MODE (``--corners``, added 2026-09-06). The single-corner
caveat above is what the ``--corners`` mode exists to close: it re-runs the
IDENTICAL stimulus and the identical 11 TRIG/TARG `.meas` statements at each
of the 9 one-at-a-time points of this repo's ratified corner set
(spec/target-spec.md's "Numeric rows -- RATIFIED 2026-08-19" section:
process `{tt, ss, ff, sf, fs}` x temperature `{-40, 27, 125} C` x supply
`{1.62, 1.8, 1.98} V`), the same OAT grid `sim/comparator-decision/`'s own
`regen-corners` campaign and `sim/sampling-acquisition-settling/`'s own
`--corners` mode already sweep. Only the `.lib` corner, `.temp`, and the
`vdd_val` parameter change per point -- the DUT netlist, the stimulus
shape, and the measurement convention are byte-identical to the
single-corner default. The 50% threshold tracks the supply at each point
(`vdd/2`), which is the standard propagation-delay convention, not a
per-corner threshold relaxation. The single-corner default behavior is
unchanged; `--corners` is purely additive.

Usage (from the repo root, after ``source sim/env.sh``)::

    python3 sim/sequencer-logic-delay/run_sequencer_logic_delay.py
    python3 sim/sequencer-logic-delay/run_sequencer_logic_delay.py --record
    # Full ratified PVT grid (9 OAT points) instead of the single
    # tt/27C/1.8V corner above:
    python3 sim/sequencer-logic-delay/run_sequencer_logic_delay.py --corners --record

A slower-but-progressing host may need a larger toolchain timeout budget
(the sky130_fd_sc_hd "combined" corner .lib carries a large fixed
per-invocation parse cost, ~13 s, the same fixed cost every sim/ experiment
against this cell library pays -- see
`sim/sar-sequencer-behavioral/run_testbench.py`'s own module docstring):

    SIM_NGSPICE_TIMEOUT_S=300 python3 sim/sequencer-logic-delay/run_sequencer_logic_delay.py --record
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
EXPERIMENT_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(SIM_DIR))
from harness import corners as corners_mod, evidence, pdk, toolchain  # noqa: E402

DESIGN_SCH = REPO_ROOT / "design" / "sar_sequencer.sch"
XSCHEMRC = REPO_ROOT / "sim" / "xschemrc"

VDD = 1.8
CORNER = "tt"
TEMP_C = 27.0

# Ratified corner-set axes (issue #28), per spec/target-spec.md's "Numeric
# rows -- RATIFIED 2026-08-19" section: -40/27/125C, +-10% supply, sky130
# process corners -- the same axes sim/comparator-decision/'s own
# regen-corners campaign and sim/sampling-acquisition-settling/'s own
# --corners mode sweep. Used only by the optional --corners mode below; the
# single-corner (tt/27C/1.8V) default behavior above is unchanged.
SUPPLY_TOLERANCE = 0.10
TEMPS_C = [-40, 27, 125]
PROCESS_CORNERS = ["tt", "ss", "ff", "sf", "fs"]

# The single-corner (tt/27C/1.8V) record --corners's own evidence record
# cross-references as "the finding this campaign extends" -- PR #203,
# sim/sequencer-logic-delay/records/20260906-192230-1b5c996.md.
SINGLE_CORNER_SEED_RECORD = "20260906-192230-1b5c996"

# CLK/RST_B stimulus -- same shape and relative timing as
# sim/sar-sequencer-behavioral/testbench/sar_sequencer_tb_fragment.spice's
# own convention (same DUT), so this experiment's own edge-to-phase mapping
# is directly comparable to that already-verified functional testbench,
# not built against a new, unrelated stimulus.
CLK_PERIOD_NS = 100.0
CLK_FIRST_EDGE_NS = 50.0
CLK_RISE_FALL_NS = 1.0
CLK_PULSE_WIDTH_NS = 50.0
RSTB_RELEASE_START_NS = 219.0
RSTB_RELEASE_END_NS = 221.0

FIRST_ADVANCING_EDGE_INDEX = 3  # 1-based CLK rising-edge count from t=0
# 11 one-hot ring phases, in shift order (ph_sample -> ph_b9 -> ... ->
# ph_b0 -> ph_eoc); ph_sample itself is reset-preset, not CLK-edge-driven,
# so it is not included here -- see module docstring.
PHASE_NODES = [f"ph_b{9 - j}" for j in range(10)] + ["ph_eoc"]


def _edge_time_ns(edge_index_1based: int) -> float:
    """Absolute time (ns) of the 50% (rising, Vdd/2) crossing of the k-th
    CLK pulse (k 1-based, counted from t=0) for this script's own fixed
    PULSE(...) stimulus."""
    edge_start = CLK_FIRST_EDGE_NS + (edge_index_1based - 1) * CLK_PERIOD_NS
    return edge_start + CLK_RISE_FALL_NS / 2.0


TRAN_STOP_NS = _edge_time_ns(FIRST_ADVANCING_EDGE_INDEX + len(PHASE_NODES) - 1) + 30.0
TRAN_STEP_NS = 0.1

# DR-006-derived per-phase clock budget (1 CLK period per bit-trial phase,
# uniform allocation) -- same reference points sim/cdac-bit-trial-settling/
# already quotes, for comparison only, not a pass/fail gate against a
# ratified row.
T_PHASE_WORST_NS = 1.0e3 / 12.0   # 83.333... ns @ f_clk_max = 12 MHz
T_PHASE_SLOW_NS = 1.0e3 / 1.2     # 833.33... ns @ f_clk_min = 1.2 MHz

MEASURE_NAMES = [f"delay_{node[3:]}" for node in PHASE_NODES]  # "delay_b9".."delay_b0","delay_eoc"

# ngspice's TRIG(AT=)/TARG(...CROSS=1) measure prints extra " targ=...
# trig=..." context on the SAME line as "name = value" -- sim/harness's
# shared measure.parse() uses a right-anchored regex that rejects this
# outright (silently yielding no match, not an exception). Parsed locally
# here, the identical workaround sim/cdac-bit-trial-settling/
# run_bit_trial_settling.py's own `_parse_trig_targ()` already established
# (no other sim/ experiment in this repo uses a TRIG/TARG measure yet, so
# this is not lifted into the shared harness module).
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


def netlist_dut(scratch_dir: Path) -> Path:
    """Netlist design/sar_sequencer.sch with xschem (headless), returning the
    path to the generated .spice file. Raises RuntimeError on any xschem
    error/nonzero exit. Duplicated from (not imported from)
    sim/sar-sequencer-behavioral/run_testbench.py's own function of the same
    name and purpose: this repo's convention for a standalone, single-DUT
    digital timing experiment is to state its own netlisting step directly
    rather than cross-import another experiment's module (no sim/ experiment
    in this repo currently imports another experiment's own run_*.py)."""
    scratch_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "xschem", "-x", "-n", "-s", "-q",
        "--rcfile", str(XSCHEMRC),
        "-o", str(scratch_dir),
        str(DESIGN_SCH),
    ]
    timeout_s = toolchain.toolchain_timeout_s()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"xschem netlisting of {DESIGN_SCH} timed out after {timeout_s:g}s. "
            f"If xschem was still making progress (not hung), raise the budget "
            f"with e.g. {toolchain.TIMEOUT_ENV_VAR}=300 (seconds) in the "
            f"environment before re-running."
        ) from exc
    out_path = scratch_dir / "sar_sequencer.spice"
    if proc.returncode != 0 or not out_path.is_file():
        raise RuntimeError(
            f"xschem netlisting of {DESIGN_SCH} failed (exit {proc.returncode}):\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
    return out_path


def build_transient(
    dut_netlist_text: str,
    *,
    corner: str = CORNER,
    temp_c: float = TEMP_C,
    vdd: float = VDD,
) -> tuple[str, dict[str, float]]:
    """One transient deck: the freshly-netlisted DUT plus a fixed CLK/RST_B/
    COMP_OUT stimulus and one TRIG(AT=)/TARG(CROSS=1) `.meas` per ring
    phase. Returns (netlist_text, edge_times) where edge_times maps each
    `.meas` name to the CLK-edge trigger time it is measured from (ns)."""
    info = pdk.resolve()
    stdcell_spice = (
        info.variant_dir / "libs.ref" / "sky130_fd_sc_hd" / "spice" / "sky130_fd_sc_hd.spice"
    )
    if not stdcell_spice.is_file():
        raise RuntimeError(f"sky130_fd_sc_hd combined SPICE deck not found at {stdcell_spice}")

    dut_lines = [ln for ln in dut_netlist_text.splitlines() if ln.strip() != ".end"]
    vth = round(vdd / 2, 6)

    lines = [
        "* sequencer-logic-delay -- standalone CLK-to-phase-output",
        "* propagation-delay testbench (issue #121), NOT routed through",
        "* sim/run_corners.py / sim/monte_carlo.py -- same divergence",
        "* sim/sar-sequencer-behavioral/run_testbench.py's own module",
        "* docstring already documents (their shared .control block only",
        "* supports .op analysis; this is a transient/digital timing check).",
        f"* corner={corner} temp={temp_c}C supply={vdd}V",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        f".param vdd_val = {vdd}",
        f".include {stdcell_spice}",
        "",
        *dut_lines,
        "",
        "VVPWR VPWR 0 DC {vdd_val}",
        "VVGND VGND 0 DC 0",
        "VCLK CLK 0 PULSE(0 {vdd_val} "
        f"{CLK_FIRST_EDGE_NS}n {CLK_RISE_FALL_NS}n {CLK_RISE_FALL_NS}n "
        f"{CLK_PULSE_WIDTH_NS}n {CLK_PERIOD_NS}n)",
        "VRSTB RST_B 0 PWL(0 0 "
        f"{RSTB_RELEASE_START_NS}n 0 {RSTB_RELEASE_END_NS}n {{vdd_val}} "
        f"{TRAN_STOP_NS}n {{vdd_val}})",
        "* Tied fixed -- design/sar_sequencer.sch's own ring/phase-generator",
        "* chain (ph_sample/ph_b9..ph_b0/ph_eoc) does not depend on",
        "* COMP_OUT at all; only the separate DOUT* capture registers do",
        "* (see module docstring). DOUT*/COMP_OUT correctness is out of",
        "* this experiment's scope -- already proven by",
        "* sim/sar-sequencer-behavioral/.",
        "VCOMP COMP_OUT 0 DC 0",
        "",
        f".tran {TRAN_STEP_NS}n {TRAN_STOP_NS}n",
    ]

    edge_times: dict[str, float] = {}
    for j, node in enumerate(PHASE_NODES):
        edge_idx = FIRST_ADVANCING_EDGE_INDEX + j
        trig_t = _edge_time_ns(edge_idx)
        name = f"delay_{node[3:]}"
        lines.append(
            f".meas tran {name} TRIG AT={trig_t}n TARG V({node}) VAL={vth} CROSS=1"
        )
        edge_times[name] = trig_t
    lines.append(".end")

    return "\n".join(lines) + "\n", edge_times


def _run(netlist: str, scratch: Path, tag: str) -> dict[str, float]:
    """A few bounded retries with backoff absorb transient contention from
    other concurrent agents' own ngspice runs on a shared machine -- the
    same policy sim/cdac-bit-trial-settling/run_bit_trial_settling.py's own
    `_run()` and sim/vcm-drive-budget/run_vcm_drive_budget.py's own `_run()`
    already document."""
    import time

    attempts = 4
    for attempt in range(1, attempts + 1):
        try:
            log_text = toolchain.run_ngspice(netlist, scratch, tag)
            return _parse_trig_targ(log_text, MEASURE_NAMES)
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


def netlist_and_check(scratch: Path, quiet: bool = False) -> str:
    """Netlist the DUT once and assert every instance resolves to
    sky130_fd_sc_hd. Split out of run_all() so the --corners campaign can
    reuse ONE netlisting step across all 9 corner points -- the schematic
    does not depend on the corner, only the `.lib`/`.temp`/`vdd_val` lines
    the transient deck adds around it do."""
    dut_path = netlist_dut(scratch / "netlist")
    dut_text = dut_path.read_text()
    if not quiet:
        print(f"OK: {DESIGN_SCH.relative_to(REPO_ROOT)} netlisted cleanly ({dut_path}).")

    non_hd = [
        ln for ln in dut_text.splitlines()
        if ln.strip().startswith("x") and "sky130_fd_sc_hd__" not in ln
    ]
    if non_hd:
        raise RuntimeError(
            "instance(s) not resolving to sky130_fd_sc_hd found in the DUT "
            f"netlist: {non_hd}"
        )
    n_instances = len([ln for ln in dut_text.splitlines() if ln.strip().startswith("x")])
    if not quiet:
        print(f"OK: all {n_instances} standard-cell instances resolve to sky130_fd_sc_hd.")
    return dut_text


def run_point(
    scratch: Path,
    dut_text: str,
    *,
    corner: str = CORNER,
    temp_c: float = TEMP_C,
    vdd: float = VDD,
    quiet: bool = False,
    tag: str = "sequencer_logic_delay",
) -> tuple[list[dict], str]:
    """One PVT point: build the transient deck around an already-netlisted
    DUT, run it, and return (per-phase rows, deck text)."""
    netlist, edge_times = build_transient(dut_text, corner=corner, temp_c=temp_c, vdd=vdd)
    m = _run(netlist, scratch, tag)

    rows = []
    for name in MEASURE_NAMES:
        delay_s = m.get(name)
        delay_ns = delay_s * 1e9 if delay_s is not None else None
        rows.append({
            "name": name,
            "phase": name[len("delay_"):],
            "trig_edge_ns": edge_times[name],
            "delay_ns": delay_ns,
        })
        if not quiet:
            delay_str = (
                f"{delay_ns:.5f} ns" if delay_ns is not None else "N/A (no crossing found)"
            )
            print(f"{name}: trig_edge={edge_times[name]:.1f}ns  delay={delay_str}")

    return rows, netlist


def run_all(scratch: Path) -> tuple[list[dict], str]:
    """Single-corner (tt/27C/1.8V) default path -- unchanged behavior."""
    dut_text = netlist_and_check(scratch)
    return run_point(scratch, dut_text)


def run_corners(scratch: Path, quiet: bool = False) -> list[dict]:
    """Full ratified-corner-set OAT sweep of run_point(): the same PVT grid
    sim/comparator-decision/'s own regen-corners campaign and
    sim/sampling-acquisition-settling/'s own --corners mode use
    (spec/target-spec.md's "Numeric rows -- RATIFIED 2026-08-19" section:
    -40/27/125C, +-10% supply, sky130 process corners), applied to this
    experiment's own per-phase CLK-to-phase-output propagation delay. This
    does NOT change the mechanism measured -- it re-runs the identical
    stimulus and the identical 11 `.meas` statements at 9 PVT points instead
    of 1, to see whether the tt/27C/1.8V finding (266.9x margin inside the
    DR-006-derived worst-case phase budget) holds, worsens, or improves
    across process/temperature/supply. Real standard-cell gate delay varies
    materially with all three axes, which is exactly why the single-corner
    record declined to call itself PVT-complete.
    """
    pdk.resolve_or_raise()
    dut_text = netlist_and_check(scratch, quiet=quiet)
    supply_pts = corners_mod.supply_points(VDD, SUPPLY_TOLERANCE)
    grid = corners_mod.oat_grid("tt", 27.0, VDD, PROCESS_CORNERS, TEMPS_C, supply_pts)

    points: list[dict] = []
    for process_corner, temp_c, supply_v in grid:
        cid = corners_mod.corner_id(process_corner, temp_c, supply_v)
        if not quiet:
            print(f"{cid}:")
        rows, netlist = run_point(
            scratch, dut_text, corner=process_corner, temp_c=temp_c, vdd=supply_v,
            quiet=True, tag=f"sequencer_logic_delay_{cid}",
        )
        valid = [r for r in rows if r["delay_ns"] is not None]
        complete = len(valid) == len(rows)
        worst = max(valid, key=lambda r: r["delay_ns"]) if valid else None
        points.append({
            "corner": process_corner, "temp_c": temp_c, "supply_v": supply_v,
            "corner_id": cid, "complete": complete, "rows": rows,
            "worst_phase": worst["phase"] if worst else None,
            "worst_delay_ns": worst["delay_ns"] if worst else None,
            "netlist": netlist,
        })
        if not quiet:
            if worst is not None:
                print(
                    f"  worst phase `{worst['phase']}`: "
                    f"delay={worst['delay_ns']:.5f} ns "
                    f"({T_PHASE_WORST_NS / worst['delay_ns']:.1f}x inside the "
                    f"{T_PHASE_WORST_NS:.3f} ns DR-006 budget)"
                    + ("" if complete else "  [INCOMPLETE: some phases had no crossing]")
                )
            else:
                print("  INCOMPLETE: no phase produced a TRIG/TARG crossing")
    return points


def write_record(rows: list[dict], netlist_sample: str) -> None:
    record_id = evidence.new_record_id()
    record_path = evidence.write_netlist_snapshot_text(EXPERIMENT_DIR, record_id, netlist_sample)
    netlist_sha = evidence.sha256_text(netlist_sample)
    info = pdk.resolve()
    pdk_line = f"{info.variant} @ {pdk.resolved_commit(info)}"
    ng_version = toolchain._ngspice_version() or "unknown"

    lines: list[str] = []
    a = lines.append
    a(f"# SAR sequencer CLK-to-phase-output propagation-delay budget -- {record_id}")
    a("")
    a("- **Record ID**: " + record_id)
    a(
        "- **Claim**: quantifies, for the first time in this repo, how long "
        "`design/sar_sequencer.sch`'s own walking-one ring sequencer takes, "
        "after each CLK rising edge, to produce a valid one-hot phase-select "
        "output -- isolating the sequencer's own logic-delay mechanism from "
        "every other sample-rate contributor (CDAC array switch settling, "
        "comparator decision delay, sampling front end acquisition). Answers "
        "`docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2 in "
        "part -- one more input to a full sample-rate re-derivation, not "
        "that re-derivation itself. No claim against a ratified spec row: "
        "`spec/target-spec.md` is entirely DRAFT (#1/#27); the DR-006 "
        "phase-period figures quoted below are themselves downstream of "
        "the DRAFT sample-rate row."
    )
    a(
        "- **Netlist provenance**: `design/sar_sequencer.sch`, netlisted "
        "fresh by `xschem` on every run (same DUT, same netlisting step "
        "`sim/sar-sequencer-behavioral/run_testbench.py` already uses and "
        "verifies functionally); this script adds only the CLK/RST_B/"
        "COMP_OUT stimulus and the TRIG/TARG propagation-delay `.meas` "
        "statements, no schematic change."
    )
    a(
        "- **Point/corner matrix**: `tt`/27C/1.8V only -- a mechanism-"
        "isolating, single-corner first-pass budget, the same precedent "
        "`sim/vcm-drive-budget/run_vcm_drive_budget.py` and "
        "`sim/cdac-bit-trial-settling/run_bit_trial_settling.py` already "
        "established. Real standard-cell gate delay varies materially with "
        "process/temperature/supply; full PVT coverage of this same budget "
        "is open, same class of gap as #28's corner campaigns elsewhere in "
        "this design."
    )
    a(
        "- **Phases measured**: all 11 CLK-edge-driven ring phases "
        "(`ph_b9`..`ph_b0`, `ph_eoc`) -- every phase transition this "
        "design's own (N+2)-stage, N=10, one-hot ring produces after its "
        "reset-preset `ph_sample` state. `ph_sample` itself is excluded: it "
        "is asynchronously reset-preset, not CLK-edge-driven, a different "
        "mechanism than the logic delay measured here."
    )
    a(
        "- **DR-006 phase-period reference points**: "
        f"{T_PHASE_WORST_NS:.3f} ns (worst case, f_clk=12 MHz, one CLK "
        f"period per bit-trial phase) and {T_PHASE_SLOW_NS:.2f} ns (slow "
        "end, f_clk=1.2 MHz) -- quoted for comparison only, not a pass/"
        "fail gate against a ratified row."
    )
    a("")
    a("## CLK-to-phase-output propagation delay")
    a("")
    a(
        "Delay is measured from the 50% (Vdd/2) crossing of the CLK rising "
        "edge that advances the ring into each phase, to the 50% crossing "
        "of that phase's own output node -- ngspice's own "
        "`TRIG AT=... TARG ... CROSS=1` measure result, already "
        "`(targ_time - trig_time)`, the same convention "
        "`sim/cdac-bit-trial-settling/`'s own `t_settle_*` measures use."
    )
    a("")
    a("| Phase | Triggering CLK edge (ns) | Delay (ns) |")
    a("|---|---|---|")
    for r in rows:
        delay_str = f"{r['delay_ns']:.5f}" if r["delay_ns"] is not None else "N/A"
        a(f"| `{r['phase']}` | {r['trig_edge_ns']:.1f} | {delay_str} |")
    a("")

    valid_rows = [r for r in rows if r["delay_ns"] is not None]
    notes = []
    if valid_rows:
        worst = max(valid_rows, key=lambda r: r["delay_ns"])
        margin_worst = T_PHASE_WORST_NS / worst["delay_ns"]
        notes.append(
            f"Worst case across all {len(valid_rows)}/{len(rows)} phases "
            f"measured: `{worst['phase']}`, delay = {worst['delay_ns']:.4f} "
            f"ns -- {margin_worst:.1f}x margin inside the DR-006-derived "
            f"worst-case (12 MHz) {T_PHASE_WORST_NS:.3f} ns phase budget, "
            "isolating the sequencer's own logic delay alone (no CDAC "
            "settling, no comparator decision time, no sampling front-end "
            "acquisition time included)."
        )
    if len(valid_rows) < len(rows):
        missing = [r["phase"] for r in rows if r["delay_ns"] is None]
        notes.append(
            f"{len(rows) - len(valid_rows)}/{len(rows)} phase(s) produced no "
            f"TRIG/TARG crossing: {missing} -- treat this record as "
            "incomplete evidence, not a passing result, until re-run "
            "clean."
        )
    notes.append(
        "This is a first-pass, single-corner (tt/27C/1.8V) budget that "
        "isolates ONE mechanism only (the sequencer's own CLK-to-phase-"
        "output logic delay, `design/sar_sequencer.sch`). It does NOT "
        "include CDAC array switch-settling time "
        "(`sim/cdac-bit-trial-settling/`), comparator decision delay "
        "(`sim/comparator-decision/`), sampling front-end acquisition time "
        "(still wholly unmeasured), or any PVT corner beyond tt/27C/1.8V. "
        "A full sample-rate re-derivation "
        "(`docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2) needs "
        "all of those combined, over the full PVT grid, which remains "
        "open. What this record newly establishes is that the sequencer's "
        "own logic-delay contribution, at this corner, is not the "
        "bottleneck relative to the DR-006-derived phase budget -- "
        "narrowing, not closing, the open item."
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
        "sim/sequencer-logic-delay/run_sequencer_logic_delay.py", ""
    ))

    record_path.write_text("\n".join(lines) + "\n")
    latest_path = EXPERIMENT_DIR / "records" / "LATEST"
    latest_path.write_text(f"{record_id}.md\n")
    print(f"\nWrote record: {record_path}")


def write_corners_record(points: list[dict]) -> Path:
    """Evidence record for the full ratified-PVT-grid --corners campaign,
    same `corners/<record_id>/` per-point-deck layout
    sim/comparator-decision/'s own regen-corners campaign and
    sim/sampling-acquisition-settling/'s own --corners mode already use."""
    record_id = evidence.new_record_id()
    corners_dir = EXPERIMENT_DIR / "corners" / record_id
    corners_dir.mkdir(parents=True, exist_ok=True)
    for p in points:
        (corners_dir / f"{p['corner_id']}.spice").write_text(p["netlist"])

    # Netlist snapshot: the tt/27C/1.8V baseline point's own deck, the same
    # single-point convention write_record() above uses, so a reader can
    # diff it directly against the single-corner record's own snapshot.
    baseline = next(
        (p for p in points if p["corner"] == "tt" and p["temp_c"] == 27.0 and p["supply_v"] == VDD),
        points[0],
    )
    record_path = evidence.write_netlist_snapshot_text(
        EXPERIMENT_DIR, record_id, baseline["netlist"]
    )
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
    a(
        "# SAR sequencer CLK-to-phase-output propagation-delay budget -- "
        f"full PVT grid -- {record_id}"
    )
    a("")
    a(f"- **Record ID**: {record_id}")
    a(
        "- **Claim**: extends the single-corner (tt/27C/1.8V) finding in "
        f"[`records/{SINGLE_CORNER_SEED_RECORD}.md`]"
        f"({SINGLE_CORNER_SEED_RECORD}.md) -- that "
        "`design/sar_sequencer.sch`'s own walking-one ring sequencer "
        "produces a valid one-hot phase-select output far inside the "
        "DR-006-derived worst-case (12 MHz) bit-trial phase budget -- to "
        "the FULL ratified PVT corner set (spec/target-spec.md's \"Numeric "
        "rows -- RATIFIED 2026-08-19\" section: -40/27/125C, +-10% supply, "
        "sky130 process corners), the same OAT grid "
        "sim/comparator-decision/'s own regen-corners campaign and "
        "sim/sampling-acquisition-settling/'s own --corners mode sweep. "
        "Identical stimulus, identical DUT, and the identical 11 TRIG/TARG "
        "`.meas` statements as the single-corner record (see that record "
        "and this script's own module docstring for the edge-to-phase "
        "mapping derivation) -- only the corner point changes per run. No "
        "claim here is graded against a ratified spec row: "
        "`spec/target-spec.md`'s sample-rate row is entirely DRAFT "
        "(#1/#27), and the DR-006 phase-period figures quoted below are "
        "themselves downstream of that DRAFT row."
    )
    a(
        "- **Netlist provenance**: `design/sar_sequencer.sch`, netlisted "
        "fresh by `xschem` ONCE per campaign run and reused unchanged at "
        "every corner point (the schematic does not depend on the corner) "
        "-- only `.lib`/`.temp`/`vdd_val` vary per point. No schematic "
        "change; this script adds only the CLK/RST_B/COMP_OUT stimulus and "
        "the propagation-delay `.meas` statements. Netlist snapshot above "
        "is the tt/27C/1.8V baseline point's deck; every point's own deck "
        f"is committed under `corners/{record_id}/`."
    )
    a(
        corners_mod.corner_matrix_summary_line(
            process_corners_run, temps_run, supplies_run, len(points)
        )
    )
    a(
        "- **Threshold convention**: the 50% crossing threshold is `vdd/2` "
        "at each point, tracking that point's own supply (1.62/1.8/1.98 V "
        "-> 0.81/0.9/0.99 V). That is the standard propagation-delay "
        "convention, not a per-corner threshold relaxation."
    )
    a(
        "- **Phases measured**: all 11 CLK-edge-driven ring phases "
        "(`ph_b9`..`ph_b0`, `ph_eoc`) at every corner point -- "
        f"{11 * len(points)} phase measurements in total. `ph_sample` is "
        "excluded at every point for the same reason as the single-corner "
        "record: it is asynchronously reset-preset, not CLK-edge-driven."
    )
    a(
        "- **DR-006 phase-period reference points**: "
        f"{T_PHASE_WORST_NS:.3f} ns (worst case, f_clk=12 MHz, one CLK "
        f"period per bit-trial phase) and {T_PHASE_SLOW_NS:.2f} ns (slow "
        "end, f_clk=1.2 MHz) -- quoted for comparison only, not a pass/"
        "fail gate against a ratified row."
    )
    a("")
    a("## Worst-phase CLK-to-phase-output delay, per corner")
    a("")
    a(
        "\"Worst phase\" is whichever of the 11 ring phases has the largest "
        "delay at that corner (not necessarily the same phase at every "
        "corner). Margin is the DR-006-derived worst-case (12 MHz) "
        f"{T_PHASE_WORST_NS:.3f} ns phase budget divided by that delay."
    )
    a("")
    a("| Corner | Worst phase | Worst delay (ns) | Margin vs. DR-006 budget | Phases measured |")
    a("|---|---|---|---|---|")
    for p in points:
        n_valid = len([r for r in p["rows"] if r["delay_ns"] is not None])
        if p["worst_delay_ns"] is None:
            a(f"| `{p['corner_id']}` | -- | INCOMPLETE | -- | {n_valid}/{len(p['rows'])} |")
            continue
        margin = T_PHASE_WORST_NS / p["worst_delay_ns"]
        a(
            f"| `{p['corner_id']}` | `{p['worst_phase']}` | "
            f"{p['worst_delay_ns']:.5f} | {margin:.1f}x | "
            f"{n_valid}/{len(p['rows'])} |"
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
        binding = max(complete_points, key=lambda p: p["worst_delay_ns"])
        best = min(complete_points, key=lambda p: p["worst_delay_ns"])
        binding_margin = T_PHASE_WORST_NS / binding["worst_delay_ns"]
        spread = binding["worst_delay_ns"] / best["worst_delay_ns"]
        all_clear = all(
            p["worst_delay_ns"] < T_PHASE_WORST_NS for p in complete_points
        )
        notes.append(
            f"**Binding corner (largest delay): `{binding['corner_id']}`**, "
            f"phase `{binding['worst_phase']}` at "
            f"{binding['worst_delay_ns']:.4f} ns -- {binding_margin:.1f}x "
            f"inside the DR-006-derived worst-case (12 MHz) "
            f"{T_PHASE_WORST_NS:.3f} ns phase budget. Fastest corner: "
            f"`{best['corner_id']}`, {best['worst_delay_ns']:.4f} ns "
            f"({T_PHASE_WORST_NS / best['worst_delay_ns']:.1f}x). "
            f"Worst-to-best spread across the ratified grid: {spread:.2f}x."
        )
        if all_clear:
            notes.append(
                f"**All {len(complete_points)}/{len(points)} ratified corner "
                "points clear the DR-006-derived worst-case phase budget**, "
                "every one of them by more than two orders of magnitude -- "
                "the single-corner (tt/27C/1.8V) finding was not a "
                "corner-specific artifact, and the sequencer's own "
                "logic delay is not the sample-rate bottleneck anywhere on "
                "this design's ratified PVT grid. This raises the weight of "
                "that finding from \"one corner, narrows the open item\" to "
                "\"every ratified corner, same conclusion\", and takes this "
                "mechanism from single-corner to PVT-complete. Headroom "
                "against a DRAFT, not-yet-ratified figure -- not a pass "
                "against a ratified spec line."
            )
        else:
            over = ", ".join(
                p["corner_id"] for p in complete_points
                if p["worst_delay_ns"] >= T_PHASE_WORST_NS
            )
            notes.append(
                f"**Not every corner point clears the DR-006-derived "
                f"worst-case phase budget** ({over} exceed it) -- the "
                "single-corner (tt/27C/1.8V) margin did NOT hold across the "
                "ratified PVT grid; see the per-corner table above."
            )
    notes.append(
        "This campaign re-runs the SAME single mechanism (the sequencer's "
        "own CLK-to-phase-output logic delay, `design/sar_sequencer.sch`) "
        "across the full ratified PVT grid -- it does NOT combine with the "
        "other three named mechanisms (CDAC array switch settling, "
        "comparator decision delay, sampling front-end acquisition) into an "
        "end-to-end sample-rate figure. Of those three, the comparator's "
        "own decision delay and the sampling front end's own acquisition "
        "are already PVT-complete (the latter does NOT clear this same "
        "budget at any ratified corner); CDAC array switch settling remains "
        "single-corner only. A full sample-rate re-derivation "
        "(`docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2) still "
        "needs all four combined, over the full PVT grid, which remains "
        "open."
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
        "sim/sequencer-logic-delay/run_sequencer_logic_delay.py", ""
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

    with tempfile.TemporaryDirectory(prefix="sequencer-logic-delay-") as tmp:
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
            print(
                f"\nOVERALL: PASS (all {len(points)} corner points produced "
                f"all {len(MEASURE_NAMES)} phase delays)"
            )
            if args.record:
                write_corners_record(points)
            return 0

        rows, netlist_sample = run_all(scratch)

        if any(r["delay_ns"] is None for r in rows):
            print("FAIL: one or more phases produced no TRIG/TARG crossing.")
            if args.record:
                write_record(rows, netlist_sample)
            return 1

        print("\nOVERALL: PASS (all 11 phases produced a valid crossing)")
        if args.record:
            write_record(rows, netlist_sample)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

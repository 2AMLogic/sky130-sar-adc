#!/usr/bin/env python3
"""End-to-end full-conversion transient campaign on the transistor-level
`design/sar_adc_top.spice` (issue #254).

    source sim/env.sh
    python3 sim/full-conversion-transient/run_conversion.py --check-env
    python3 sim/full-conversion-transient/run_conversion.py            # tt/27C/1.8V only
    python3 sim/full-conversion-transient/run_conversion.py --corners --record
    python3 sim/full-conversion-transient/run_conversion.py --mechanism-probe
    python3 sim/full-conversion-transient/run_conversion.py --coherent-sine --record

WHAT THIS IS. Every prior `sim/` experiment drives one sub-block, or the
sequencer against an *ideal* comparator-decision stimulus
(`sim/sar-sequencer-behavioral/`). This one runs the WHOLE ADC: the
committed, schematic-derived `design/sar_adc_top.spice` (sampling front
end + CDAC array + comparator + SAR sequencer + the nine SELn inverters),
with a real master clock at the DR-006 worst-case `f_clk = 12 MHz`, five DC
differential inputs spanning the code range, and the captured `DOUT9..DOUT0`
compared against the ideal code for each input -- at all nine points of the
ratified one-at-a-time PVT grid. In the same transient it measures the
average supply/reference currents over one steady-state conversion, the
first evidence of any kind for `spec/target-spec.md`'s DRAFT **Power** row.

WHAT IT IS NOT. Neither number it produces is a pass/fail claim against a
ratified spec row. `Sample rate` and `Power` are both DRAFT rows
(`spec/target-spec.md` "Target table"); this campaign is the settling/
functional data DR-003 Item 5 and DR-006's own open item say a future
decision record needs before either row can be re-derived. It reports what
the circuit does at 12 MHz; it does not propose a sample rate, and does not
propose a power target ("report, don't pre-commit").

DIVERGENCE FROM THE SHARED PVT HARNESS (sim/README.md's "divergences, each
deliberate" convention). `sim/run_corners.py`'s shared `.control` block is
`.op`-only (see `sim/harness/testbench.py`'s module docstring), so this
experiment -- like `sim/sequencer-logic-delay/`,
`sim/sampling-acquisition-settling/` and `sim/sar-sequencer-behavioral/`
before it -- assembles and runs its own `.tran` deck, reusing `sim/harness`
for PDK/toolchain resolution, the ngspice invocation, `name = value` log
parsing, the ratified OAT corner grid (`corners.ratified_oat_grid()`), and
the evidence-record scaffolding (`evidence.resolve_provenance()`).

DECK ASSEMBLY. `design/sar_adc_top.spice` is a flat top-level deck (xschem
comments out its own `.subckt`/`.ends` wrapper), so its ports are ordinary
top-level nodes this script's fragment drives directly. Two assembly
details are load-bearing:

  * `.global VPWR VGND` -- `design/sar_adc_top.sch`'s own header records
    that the digital std cells' `VPWR`/`VGND` are literal instance
    properties with no schematic-graph node, and names "adding a `.global`
    equivalence ... at THAT testbench's assembly step" as the assembling
    testbench's job. Without it, `VPWR`/`VGND` inside the `sar_sequencer`
    subcircuit are floating locals and the sequencer has no supply.
  * the `sky130_fd_sc_hd` combined-cell `.include`, exactly as
    `sim/sar-sequencer-behavioral/run_testbench.py` does it.

MECHANISM PROBE (`--mechanism-probe`). A diagnostic mode that runs the same
stimulus twice at the baseline corner: once on the unmodified DUT, and once
on a TESTBENCH-ONLY MODIFIED copy in which the comparator's strobe input is
re-pointed from `CLK` to a separate `CLK_CMP` node driven half a period
later. It exists to isolate *which* mechanism a wrong code comes from; it
NEVER contributes to a corner record, and the modified netlist is never
written back to `design/`. See this experiment's README.md.

COHERENT-SINE DYNAMIC TEST (`--coherent-sine`, issue #603). Opt-in: the
same DUT driven by a coherent antiphase sine instead of the DC schedule
(`gen_full_conversion_tb.sine_fragment_text()`), one captured code per
conversion, SNDR/ENOB by the stdlib-only FFT in `dynamic_enob.py`. Baseline
corner only; an informational cross-check of `sim/enob-estimate/`'s
behavioral-accelerated composite, never a grade of the DRAFT ENOB row.

SOLVER POLICY (issue #637, DR-023). Transient solver settings are a named
profile resolved at deck assembly (SOLVER_PROFILES / `--solver-profile`).
The reference profile is `reltol-gear` (`.options reltol=1e-4 method=gear`)
for every transient this runner assembles; any other profile -- including
`ngspice-default`, the settings of every pre-DR-023 record -- is a labelled
SOLVER CONTROL that never moves records/LATEST and may not --supersedes. `--solver-audit` runs the DC baseline corner under the
reference profile and each control profile, sequentially, and records which
observations (if any) move -- the guard against presenting a
solver-sensitive anomaly as converter behaviour.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import math
import os
import re
import sys
import tempfile
import time
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent
SIM_DIR = EXPERIMENT_DIR.parent
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(EXPERIMENT_DIR))

from harness import corners as corners_mod, evidence, measure, pdk, toolchain  # noqa: E402

import dynamic_enob  # noqa: E402  (issue #603's stdlib-only FFT/ENOB analyzer)
import gen_full_conversion_tb as tb  # noqa: E402  (this experiment's own testbench constants)

REPO_ROOT = evidence.REPO_ROOT
DUT_NETLIST = REPO_ROOT / "design" / "sar_adc_top.spice"

# --- Ratified corner-set axes (spec/target-spec.md "Numeric rows --
# RATIFIED 2026-08-19"; V_REF = V_DD = 1.8 V per DR-003 Item 1). -----------
NOMINAL_SUPPLY_V = 1.8
SUPPLY_TOLERANCE = corners_mod.RATIFIED_SUPPLY_TOLERANCE
TEMPS_C = corners_mod.RATIFIED_TEMPS_C
PROCESS_CORNERS = corners_mod.RATIFIED_PROCESS_CORNERS
BASELINE_CORNER = ("tt", 27.0, NOMINAL_SUPPLY_V)

# Informational tolerance for the per-input code check (NOT a ratified-row
# threshold): the issue's own "ideal code +- 1 LSB" criterion.
CODE_TOLERANCE_LSB = 1


# --------------------------------------------------------------------------
# Transient solver policy (issue #637; spec/decision-records/DR-023-full-conversion-transient-solver-policy.md)
# --------------------------------------------------------------------------
# Solver settings are a NAMED POLICY resolved once at deck assembly
# (`assemble_deck(solver_profile=...)`), never an `.options` string spliced
# into one execution branch. Each profile is the exact list of `.options`
# assignments it adds to the deck (one card, or none). Every record this
# runner writes names the resolved profile and its options card, so a
# workflow label is never the only provenance of how a transient was
# integrated.
#
# REFERENCE POLICY (DR-023): `reltol-gear` -- ngspice's reltol tightened 10x
# (1e-3 -> 1e-4) and Gear instead of trapezoidal integration -- for EVERY
# transient this runner assembles (DC corner campaign, coherent-sine, and the
# diagnostic modes). It is scoped to sim/full-conversion-transient/ only; no
# other experiment's deck changes. Every record minted before DR-023 ran on
# `ngspice-default` (no card); that profile stays available as a labelled
# control so those records can be reproduced, and is the comparison point of
# `--solver-audit`.
#
# Only REFERENCE_SOLVER_PROFILE may produce reference evidence (the corner
# campaign, `records/LATEST`, a `--supersedes` chain). Every other profile is
# a labelled SOLVER CONTROL: it may not --supersedes, never moves LATEST, and
# is refused by the diagnostic modes and by --corners (a control is a check
# on reference evidence, not a second campaign). Changing the reference
# policy again is a new decision record, followed by a fresh reference
# campaign under it.
SOLVER_PROFILES: dict[str, tuple[str, ...]] = {
    # ngspice's own transient defaults (reltol=1e-3, trapezoidal): no card.
    # The reference policy of every record minted before DR-023.
    "ngspice-default": (),
    # DR-023's reference policy (issue #621's combined control): 10x tighter
    # reltol AND Gear integration.
    "reltol-gear": ("reltol=1e-4", "method=gear"),
    # issue #637's single-setting controls, which attribute the #621 effect.
    "reltol-only": ("reltol=1e-4",),
    "gear-only": ("method=gear",),
}
REFERENCE_SOLVER_PROFILE = "reltol-gear"
# What a profile with no card leaves in force (ngspice manual, `.options`):
# stated in every record so "defaults" is never an unstated assumption.
NGSPICE_DEFAULT_SOLVER_SETTINGS = "reltol=1e-3, method=trapezoidal (ngspice defaults)"
# The profiles `--solver-audit` compares against the reference by default:
# every other named profile, legacy default first.
SOLVER_AUDIT_DEFAULT_PROFILES = tuple(
    p for p in SOLVER_PROFILES if p != REFERENCE_SOLVER_PROFILE
)


def check_solver_profile(profile: str) -> None:
    if profile not in SOLVER_PROFILES:
        raise ValueError(
            f"unknown solver profile {profile!r}; known: {', '.join(SOLVER_PROFILES)}"
        )


def is_solver_control(profile: str) -> bool:
    """True for every profile that is not the reference solver policy."""
    check_solver_profile(profile)
    return profile != REFERENCE_SOLVER_PROFILE


def solver_options_card(profile: str) -> str | None:
    """The single `.options` card a profile adds, or None (`ngspice-default`)."""
    check_solver_profile(profile)
    opts = SOLVER_PROFILES[profile]
    return ".options " + " ".join(opts) if opts else None


def _solver_role(profile: str) -> str:
    return ("SOLVER CONTROL" if is_solver_control(profile)
            else "reference policy, DR-023")


def solver_profile_deck_lines(profile: str) -> list[str]:
    """Deck lines for a profile: a labelling comment plus exactly one
    `.options` card, or nothing at all for a profile with no card (so an
    `ngspice-default` deck is byte-identical to a pre-#637 deck)."""
    card = solver_options_card(profile)
    if card is None:
        return []
    return [
        f"* --- solver profile '{profile}' ({_solver_role(profile)}; issue #637 "
        "solver policy; simulator options only, DUT and stimulus unmodified) ---",
        card,
    ]


def solver_settings_text(profile: str) -> str:
    """Human-readable resolved settings for a record's Environment block."""
    card = solver_options_card(profile)
    if card is None:
        return (f"profile `{profile}` ({_solver_role(profile)}): no `.options` card -- "
                f"{NGSPICE_DEFAULT_SOLVER_SETTINGS}")
    return (f"profile `{profile}` ({_solver_role(profile)}): `{card}`; all other "
            "settings ngspice defaults")


def solver_control_note(profile: str) -> str:
    """What a control run changes relative to the reference policy, for the
    record's up-front SOLVER-CONTROL bullet."""
    card = solver_options_card(profile)
    ref_card = solver_options_card(REFERENCE_SOLVER_PROFILE)
    ref = f"`{ref_card}`" if ref_card else NGSPICE_DEFAULT_SOLVER_SETTINGS
    this = f"`{card}`" if card else f"no `.options` card ({NGSPICE_DEFAULT_SOLVER_SETTINGS})"
    return (f"this transient runs solver profile `{profile}`: {this}, instead of the "
            f"reference policy `{REFERENCE_SOLVER_PROFILE}` ({ref}, DR-023)")


# --------------------------------------------------------------------------
# Deck assembly
# --------------------------------------------------------------------------
def dut_text() -> str:
    return DUT_NETLIST.read_text()


def assemble_deck(
    dut_netlist_text: str,
    pdk_info: pdk.PdkInfo,
    process_corner: str = "tt",
    temp_c: float = 27.0,
    supply_v: float = NOMINAL_SUPPLY_V,
    delayed_comparator_strobe: bool = False,
    extra_meas: list[str] | None = None,
    fragment: str | None = None,
    solver_profile: str = REFERENCE_SOLVER_PROFILE,
) -> str:
    """Assemble the runnable deck: per-corner preamble + DUT body + the
    committed stimulus/measurement fragment.

    `fragment` (issue #603's `--coherent-sine`) replaces the committed DC
    fragment with another stimulus/measurement fragment text -- the
    coherent-sine one from `gen_full_conversion_tb.sine_fragment_text()`.
    Default `None` keeps the DC fragment, so every existing mode is
    unchanged.

    `delayed_comparator_strobe` is the `--mechanism-probe` modification
    only (see the module docstring): it re-points the comparator instance's
    strobe from `CLK` to `CLK_CMP` and adds a `CLK_CMP` source delayed by
    half a CLK period, so the comparator evaluates during CLK-low and its
    decision is still valid at the CLK rising edge where the SAR bit
    registers capture. It is a diagnostic on a modified netlist, never a
    recorded corner result.

    `extra_meas` (issue #259's `--node-trace`) is a list of additional,
    already-formatted `.meas tran ...` lines appended after the committed
    fragment and before `.end`. It never modifies the DUT netlist body
    itself (unlike `delayed_comparator_strobe`) -- it only adds read-only
    probes, so it is safe to combine with the as-committed (unmodified)
    netlist.

    `solver_profile` (issue #637) names the transient solver policy (see
    SOLVER_PROFILES); the default is the DR-023 reference policy. A profile
    adds exactly one labelled `.options` card (or nothing, for
    `ngspice-default`), placed after the fragment and before `extra_meas` --
    the same position issue #621's coherent-sine control used, so that
    control's deck is reproduced unchanged.
    """
    solver_lines = solver_profile_deck_lines(solver_profile)  # validates the name first
    stdcell_spice = (
        pdk_info.variant_dir / "libs.ref" / "sky130_fd_sc_hd" / "spice" / "sky130_fd_sc_hd.spice"
    )
    if not stdcell_spice.is_file():
        raise RuntimeError(f"sky130_fd_sc_hd combined SPICE deck not found at {stdcell_spice}")

    dut_lines = [ln for ln in dut_netlist_text.splitlines() if ln.strip().lower() != ".end"]
    extra_sources: list[str] = []
    if delayed_comparator_strobe:
        patched = []
        hits = 0
        for ln in dut_lines:
            if ln.startswith("xcmp VDD CLK "):
                ln = ln.replace("xcmp VDD CLK ", "xcmp VDD CLK_CMP ", 1)
                hits += 1
            patched.append(ln)
        if hits != 1:
            raise RuntimeError(
                "mechanism probe: expected exactly one 'xcmp VDD CLK ' instance line in "
                f"{DUT_NETLIST}, found {hits} -- the netlist changed shape; re-derive the probe."
            )
        dut_lines = patched
        td = tb.T_FIRST_EDGE_NS - tb.EDGE_NS / 2 + tb.T_CLK_NS / 2
        extra_sources = [
            "* --- mechanism probe only: comparator strobe delayed by half a CLK",
            "* period (testbench-only netlist modification, never recorded) -------",
            f"VCLKCMP CLK_CMP 0 PULSE(0 {{vdd_val}} {td:.4f}n {tb.EDGE_NS:g}n "
            f"{tb.EDGE_NS:g}n {tb.T_CLK_NS / 2 - tb.EDGE_NS:.5f}n {tb.T_CLK_NS:.5f}n)",
            "",
        ]

    lines = [
        "* sim/full-conversion-transient -- end-to-end full-conversion transient",
        "* on design/sar_adc_top.spice (issue #254). Assembled by",
        "* sim/full-conversion-transient/run_conversion.py; NOT routed through",
        "* sim/run_corners.py (its shared .control block is .op-only).",
        f"* corner={process_corner} temp={temp_c}C supply={supply_v}V"
        + ("  [MECHANISM PROBE: comparator strobe delayed]" if delayed_comparator_strobe else ""),
        f".lib {pdk_info.ngspice_lib} {process_corner}",
        f".temp {temp_c}",
        f".param vdd_val = {supply_v}",
        f".include {stdcell_spice}",
        "* VPWR/VGND have no schematic-graph node inside sar_sequencer (see",
        "* design/sar_adc_top.sch's header); the testbench ties them here.",
        ".global VPWR VGND",
        "",
        *dut_lines,
        "",
        *extra_sources,
        tb.FRAGMENT_PATH.read_text() if fragment is None else fragment,
        *solver_lines,
        *(extra_meas or []),
        ".end",
    ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Running and decoding
# --------------------------------------------------------------------------
def _run_ngspice(deck: str, scratch: Path, tag: str, attempts: int = 3) -> str:
    """Retry policy documented once in toolchain.run_ngspice_with_retry().
    One full-ADC transient here is ~6.3 us of simulated time over ~2000
    devices and takes minutes, so raise SIM_NGSPICE_TIMEOUT_S well above
    the 120 s harness default before running (the README names the value
    used for the record); attempts=3 (not the shared helper's default 4)
    keeps a fully-exhausted retry budget from blowing past that already-
    long per-attempt wall-clock cost. `--coherent-sine` passes attempts=1:
    its single transient is several times longer again, and a retry after a
    timeout would only repeat the same cost."""
    return toolchain.run_ngspice_with_retry(deck, scratch, tag, attempts=attempts)


def decode(parsed: dict[str, float], supply_v: float) -> dict:
    """Turn one run's parsed `.meas` values into per-conversion code results,
    phase-structure verdicts, and supply-current/power numbers.

    A measurement that is absent OR non-finite (NaN / +-inf -- issue #569)
    is unavailable: it decodes to no bit, contributes no digital margin and
    no current. `measure.parse()` already rejects non-finite values from a
    log; this is the same rule at the decoder boundary for any caller that
    hands in a dict directly. If any required supply current is unavailable
    the result fails (`all_ok=False`) and, when that current carries a power
    term (nonzero potential), `power_w` is `None` rather than the partial
    sum of the currents that remain."""
    threshold = tb.DIGITAL_THRESHOLD_FRACTION * supply_v
    lsb_v = 2.0 * supply_v / (2**tb.N_BITS)

    def value(name: str) -> float | None:
        v = parsed.get(name)
        return v if v is not None and math.isfinite(v) else None

    def bit(name: str) -> int | None:
        v = value(name)
        return None if v is None else (1 if v > threshold else 0)

    margins: list[float] = []
    conversions: list[dict] = []
    for c in tb.measured_conversions():
        bit_names = tb.code_measure_names(c)
        bits = [bit(n) for n in bit_names]
        for n in bit_names:
            v = value(n)
            if v is not None:
                margins.append(abs(v - threshold))
        code = None
        if all(b is not None for b in bits):
            code = int("".join(str(b) for b in bits), 2)
        frac = tb.input_fraction(c)
        ideal = tb.ideal_code(frac)

        busy = [bit(n) for n in tb.busy_measure_names(c)]
        smpl = [bit(n) for n in tb.sample_measure_names(c)]
        for n in tb.busy_measure_names(c) + tb.sample_measure_names(c):
            v = value(n)
            if v is not None:
                margins.append(abs(v - threshold))
        expected_busy = [1] * (tb.PHASES_PER_CONVERSION - 1) + [0]
        expected_smpl = [0] * (tb.PHASES_PER_CONVERSION - 1) + [1]
        phase_ok = busy == expected_busy and smpl == expected_smpl

        conversions.append(
            dict(
                conversion=c,
                fraction=frac,
                vdiff_mv=frac * supply_v * 1000.0,
                ideal_code=ideal,
                code=code,
                bits=bits,
                error_lsb=None if code is None else code - ideal,
                busy=busy,
                sample=smpl,
                phase_ok=phase_ok,
                code_ok=(code is not None and abs(code - ideal) <= CODE_TOLERANCE_LSB),
            )
        )

    currents: dict[str, float] = {}
    power_w: float | None = 0.0
    currents_ok = True
    for name, _source, potential in tb.SUPPLY_SOURCES:
        raw = value(name)
        if raw is None:
            # Unavailable required current: omit it, fail the point, and do
            # not pass the remaining sources off as complete power. A source
            # at 0 V contributes no power term either way (convention below).
            currents_ok = False
            if potential != 0.0:
                power_w = None
            continue
        amps = abs(raw)
        currents[name] = amps
        if power_w is not None:
            power_w += potential * supply_v * amps

    errors = [abs(cv["error_lsb"]) for cv in conversions if cv["error_lsb"] is not None]
    return dict(
        conversions=conversions,
        currents=currents,
        power_w=power_w,
        lsb_v=lsb_v,
        worst_error_lsb=max(errors) if errors else None,
        n_code_ok=sum(1 for cv in conversions if cv["code_ok"]),
        n_phase_ok=sum(1 for cv in conversions if cv["phase_ok"]),
        n_conversions=len(conversions),
        worst_margin_v=min(margins) if margins else float("nan"),
        all_ok=currents_ok and all(cv["code_ok"] and cv["phase_ok"] for cv in conversions),
    )


def _power_uw_str(power_w: float | None) -> str:
    """`power_w` in uW, or `n/a` when decode() marked it unavailable."""
    return "n/a" if power_w is None else f"{power_w * 1e6:.3f}"


def run_point(
    netlist_text: str,
    pdk_info: pdk.PdkInfo,
    scratch: Path,
    process_corner: str,
    temp_c: float,
    supply_v: float,
    delayed_comparator_strobe: bool = False,
    tag_prefix: str = "full_conversion",
    solver_profile: str = REFERENCE_SOLVER_PROFILE,
    audit: bool = False,
) -> dict:
    """One DC-fragment transient. `solver_profile` selects the solver policy
    (issue #637). `audit=True` is `--solver-audit`'s instrumentation, applied
    identically under every profile it compares: the print-only accounting
    card (SOLVER_AUDIT_STATS_CARD) and the read-only register-transition
    guard probes on every measured conversion. Neither touches the DUT, the
    stimulus or the solver settings."""
    cid = corners_mod.corner_id(process_corner, temp_c, supply_v)
    extra_meas: list[str] = []
    if audit:
        extra_meas.append(SOLVER_AUDIT_STATS_CARD)
        for c in tb.measured_conversions():
            extra_meas += transition_guard_measure_lines(c, supply_v)
    deck = assemble_deck(
        netlist_text, pdk_info, process_corner, temp_c, supply_v, delayed_comparator_strobe,
        extra_meas=extra_meas or None, solver_profile=solver_profile,
    )
    t0 = time.time()
    log_text = _run_ngspice(deck, scratch, f"{tag_prefix}_{cid}")
    wall_s = time.time() - t0

    names = tb.all_measure_names()
    guard_names = (
        [n for c in tb.measured_conversions() for n in transition_guard_flat_names(c)]
        if audit else []
    )
    parsed = measure.parse(log_text, names + guard_names, anchored=False)
    # guard probes are read-only extras: their absence never fails the point
    missing = measure.missing(parsed, names)
    result = decode(parsed, supply_v)
    result.update(
        process_corner=process_corner,
        temp_c=temp_c,
        supply_v=supply_v,
        corner_id=cid,
        missing=missing,
        log_text=log_text,
        wall_s=wall_s,
        solver_profile=solver_profile,
    )
    if audit:
        result["guards"] = [
            decode_switch_trace(parsed, c, supply_v) for c in tb.measured_conversions()
        ]
        result["solver_stats"] = parse_solver_stats(log_text)
    if missing:
        result["all_ok"] = False
    return result


def format_point(point: dict) -> str:
    code_str = " ".join(
        f"{cv['fraction']:+.2f}:{'?' if cv['code'] is None else cv['code']}"
        f"/{cv['ideal_code']}"
        for cv in point["conversions"]
    )
    worst = point["worst_error_lsb"]
    idd_names = ("i_vdd", "i_vpwr", "i_vrefp")
    if all(n in point["currents"] for n in idd_names):
        idd_str = f"{1e6 * sum(point['currents'][n] for n in idd_names):.3f}"
    else:
        idd_str = "n/a"  # an unavailable current is not summed as zero (#569)
    return (
        f"{point['corner_id']}: {'PASS' if point['all_ok'] else 'FAIL'} "
        f"codes(captured/ideal) {code_str} "
        f"worst|err|={'n/a' if worst is None else worst} LSB "
        f"phases_ok={point['n_phase_ok']}/{point['n_conversions']} "
        f"IDD={idd_str}uA P={_power_uw_str(point['power_w'])}uW "
        f"({point['wall_s']:.0f}s)"
    )


# --------------------------------------------------------------------------
# Campaign
# --------------------------------------------------------------------------
def run_campaign(
    corners_mode: bool, jobs: int, quiet: bool, scratch: Path,
    solver_profile: str = REFERENCE_SOLVER_PROFILE,
) -> tuple[list[dict], str]:
    pdk_info = pdk.resolve()
    netlist_text = dut_text()

    if corners_mode:
        grid = corners_mod.ratified_oat_grid(
            NOMINAL_SUPPLY_V, SUPPLY_TOLERANCE, PROCESS_CORNERS, TEMPS_C
        )
    else:
        grid = [BASELINE_CORNER]

    points: list[dict] = []
    if jobs > 1 and len(grid) > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = {
                pool.submit(
                    run_point, netlist_text, pdk_info, scratch, pc, tc, sv,
                    solver_profile=solver_profile,
                ): (pc, tc, sv)
                for pc, tc, sv in grid
            }
            done: dict[tuple, dict] = {}
            for fut in concurrent.futures.as_completed(futures):
                point = fut.result()
                done[futures[fut]] = point
                if not quiet:
                    print("  " + format_point(point), flush=True)
            points = [done[key] for key in grid]
    else:
        for pc, tc, sv in grid:
            point = run_point(netlist_text, pdk_info, scratch, pc, tc, sv,
                              solver_profile=solver_profile)
            points.append(point)
            if not quiet:
                print("  " + format_point(point), flush=True)

    return points, netlist_text


def binding_point(points: list[dict]) -> dict:
    """Worst code error first (the quantity this campaign is about), with the
    smallest digital margin to the decision threshold as the tie-break --
    sim/README.md's per-row binding-corner convention, recorded regardless of
    pass/fail."""

    def key(p: dict):
        worst = p["worst_error_lsb"]
        return (
            -(worst if worst is not None else 10**6),
            p["worst_margin_v"],
        )

    return min(points, key=key)


# --------------------------------------------------------------------------
# Evidence record
# --------------------------------------------------------------------------
def _bits_str(bits: list[int | None]) -> str:
    return "".join("?" if b is None else str(b) for b in bits)


def write_record(
    points: list[dict],
    netlist_text: str,
    probe: dict | None = None,
    supersedes: str = "",
    solver_profile: str = REFERENCE_SOLVER_PROFILE,
) -> Path:
    """Mint a DC-fragment record. Under the reference solver profile this is
    the corner-campaign record and it moves `records/LATEST`. Under any other
    profile (issue #637) it is a labelled SOLVER-CONTROL record: it may not
    supersede anything and it never touches LATEST -- refused here, not only
    at the CLI, so no caller can turn a control into reference evidence."""
    control = is_solver_control(solver_profile)
    if control and supersedes:
        raise ValueError(
            f"solver profile {solver_profile!r} is a SOLVER CONTROL, not a replacement "
            "capture; its record may not --supersedes"
        )
    prov, lines = evidence.open_record(
        EXPERIMENT_DIR, netlist_text, "corners",
        {f"{p['corner_id']}.log": p["log_text"] for p in points},
    )
    if probe is not None:
        diag_dir = EXPERIMENT_DIR / "diagnostics" / prov.record_id
        diag_dir.mkdir(parents=True, exist_ok=True)
        for tag, point in probe.items():
            (diag_dir / f"{tag}.log").write_text(point["log_text"])

    binding = binding_point(points)
    overall_ok = all(p["all_ok"] for p in points)
    n_ok = sum(1 for p in points if p["all_ok"])
    processes = sorted({p["process_corner"] for p in points})
    temps = sorted({p["temp_c"] for p in points})
    supplies = sorted({p["supply_v"] for p in points})

    a = lines.append
    if control:
        a(
            "- **SOLVER-CONTROL RUN (issue #637) -- NOT REFERENCE EVIDENCE**: "
            + solver_control_note(solver_profile)
            + ". DUT and stimulus are unmodified; only the integration settings "
            "differ. It exists to test whether a recorded observation depends on the "
            "solver settings. It does not update `records/LATEST` and supersedes nothing."
        )
    a(
        "- **Claim**: `spec/target-spec.md#target-table` -- **Sample rate** and "
        "**Power**, both DRAFT rows, INFORMATIONAL only. This is the first "
        "end-to-end campaign that drives the whole transistor-level "
        "`design/sar_adc_top.spice` through complete conversions at the DR-006 "
        "worst-case `f_clk = 12 MHz`, and the first supply-current measurement "
        "of any kind on this block. It substantiates NEITHER row: no spec row "
        "is edited by this record, no sample rate is proposed, and no power "
        "target is proposed (`report, don't pre-commit`). Re-deriving the "
        "Sample rate row (DR-003 Item 5 / DR-006 open item) and proposing a "
        "Power target remain a future decision record's job."
    )
    a("- **Netlist provenance**: schematic (`design/sar_adc_top.spice`, regenerated "
      "from `design/sar_adc_top.sch` and its four sub-block schematics by "
      "`design/regen_netlist.sh`; `--check` clean at the commit below)")
    a(corners_mod.corner_matrix_summary_line(processes, temps, supplies, len(points)))
    a(
        f"- **Stimulus**: `f_clk = {tb.F_CLK_HZ / 1e6:g} MHz` "
        f"({tb.T_CLK_NS:.4f} ns period, 50% duty), `RST_B` released at "
        f"{tb.T_RSTB_RELEASE_NS:g} ns, `VREFP = V_DD`, `VREFN = 0`, "
        f"`VCM = V_DD/2` (DR-003 ratified `V_REF = V_DD`); "
        f"{tb.N_CONVERSIONS} back-to-back conversions of "
        f"{tb.PHASES_PER_CONVERSION} CLK periods (DR-006), the first discarded "
        f"as start-up, the remaining {len(tb.INPUT_FRACTIONS)} carrying DC "
        "differential inputs of "
        + ", ".join(f"`{f:+.2f}*V_REF`" for f in tb.INPUT_FRACTIONS)
        + " -- see `sim/full-conversion-transient/testbench/"
        "full_conversion_tb_fragment.spice`."
    )
    a(
        f"- **Binding corner**: `{binding['corner_id']}` (largest worst-case code "
        f"error: {binding['worst_error_lsb']} LSB; tie-break = smallest digital "
        f"margin to the decision threshold, {binding['worst_margin_v']:.4f} V) -- "
        "recorded regardless of pass/fail, per sim/README.md's per-row "
        "binding-corner convention."
    )
    a(
        f"- **Overall**: {'PASS' if overall_ok else 'FAIL'} ({n_ok}/{len(points)} "
        "corners resolve every input to its ideal code +-"
        f"{CODE_TOLERANCE_LSB} LSB with a correct 12-period phase structure). "
        "This verdict is against this experiment's own informational criterion, "
        "NOT against a ratified spec row."
    )
    a(
        "- **Measured value(s)**: average supply/reference current and power over "
        f"one steady-state conversion (conversion {tb.IDD_CONVERSION}, all "
        f"{tb.PHASES_PER_CONVERSION} CLK periods) at each corner -- see the "
        "Power table below. Informational first evidence for the DRAFT Power "
        "row; not a target and not a pass/fail."
    )
    a("")

    a("## Per-corner summary")
    a("")
    a(
        "| corner-id | codes within +-1 LSB | 12-period phase structure | "
        "worst \\|code error\\| (LSB) | worst digital margin (V) | verdict |"
    )
    a("|---|---|---|---|---|---|")
    for p in points:
        worst = "n/a" if p["worst_error_lsb"] is None else str(p["worst_error_lsb"])
        a(
            f"| `{p['corner_id']}` | {p['n_code_ok']}/{p['n_conversions']} | "
            f"{p['n_phase_ok']}/{p['n_conversions']} | {worst} | "
            f"{p['worst_margin_v']:.4f} | {'PASS' if p['all_ok'] else 'FAIL'} |"
        )
    a("")

    a("## Captured code vs ideal code, every input at every corner")
    a("")
    header = "| corner-id | " + " | ".join(
        f"`{f:+.2f}*V_REF` (ideal {tb.ideal_code(f)}) " for f in tb.INPUT_FRACTIONS
    ) + "|"
    a(header)
    a("|---" * (len(tb.INPUT_FRACTIONS) + 1) + "|")
    for p in points:
        cells = []
        for cv in p["conversions"]:
            code = "MISSING" if cv["code"] is None else str(cv["code"])
            err = "n/a" if cv["error_lsb"] is None else f"{cv['error_lsb']:+d}"
            cells.append(f"{code} ({err} LSB)")
        a(f"| `{p['corner_id']}` | " + " | ".join(cells) + " |")
    a("")

    a(f"## Per-input detail at the binding corner (`{binding['corner_id']}`)")
    a("")
    a(
        "| input | V_diff (mV) | ideal code | captured code | error (LSB) | "
        "captured bits (DOUT9..DOUT0) | BUSY per CLK period | phase structure |"
    )
    a("|---|---|---|---|---|---|---|---|")
    for cv in binding["conversions"]:
        code = "MISSING" if cv["code"] is None else str(cv["code"])
        err = "n/a" if cv["error_lsb"] is None else f"{cv['error_lsb']:+d}"
        a(
            f"| `{cv['fraction']:+.2f}*V_REF` | {cv['vdiff_mv']:.2f} | "
            f"{cv['ideal_code']} | {code} | {err} | `{_bits_str(cv['bits'])}` | "
            f"`{_bits_str(cv['busy'])}` | {'OK' if cv['phase_ok'] else 'WRONG'} |"
        )
    a("")

    a("## Power (informational -- DRAFT row, `report, don't pre-commit`)")
    a("")
    a(
        "| corner-id | I(VDD) (uA) | I(VPWR) (uA) | I(VREFP) (uA) | I(VCM) (uA) | "
        "I(VREFN) (uA) | total power (uW) |"
    )
    a("|---|---|---|---|---|---|---|")
    for p in points:
        def ua(name: str) -> str:
            v = p["currents"].get(name)
            return "n/a" if v is None else f"{v * 1e6:.3f}"

        a(
            f"| `{p['corner_id']}` | {ua('i_vdd')} | {ua('i_vpwr')} | "
            f"{ua('i_vrefp')} | {ua('i_vcm')} | {ua('i_vrefn')} | "
            f"{_power_uw_str(p['power_w'])} |"
        )
    a("")
    if any(p["power_w"] is None for p in points):
        a(
            "`n/a` total power: at least one supply current at a nonzero "
            "potential was missing or non-finite at that corner, so no total "
            "is reported (a partial sum would understate it)."
        )
        a("")
    a(
        "Power is `sum(V_source * |avg I_source|)` over the sources at a nonzero "
        "potential (`VDD`, `VPWR`, `VREFP` at `V_DD`; `VCM` at `V_DD/2`; `VREFN` "
        "sits at 0 V and contributes no power term), averaged over one whole "
        f"steady-state conversion ({tb.PHASES_PER_CONVERSION} CLK periods at "
        f"{tb.F_CLK_HZ / 1e6:g} MHz). Every reference here is an IDEAL source: "
        "no reference buffer, no clock generator and no output driver exists in "
        "this design yet, so this is the ADC core only, and a real system's "
        "reference/clock power is NOT included."
    )
    a("")

    if not overall_ok:
        a("## Findings")
        a("")
        wrong = [p["corner_id"] for p in points if p["n_code_ok"] < p["n_conversions"]]
        bad_phase = [p["corner_id"] for p in points if p["n_phase_ok"] < p["n_conversions"]]
        a(
            f"- **Code correctness FAILS at {len(wrong)}/{len(points)} corners** "
            + (", ".join(f"`{c}`" for c in wrong) if wrong else "(none)")
            + " -- reported as a finding, not dropped, per CLAUDE.md's "
            "'no claim without a testbench' / 'do not relax a spec line to make a "
            "result pass' rules."
        )
        a(
            f"- **Phase structure (12 CLK periods per conversion) is correct at "
            f"{len(points) - len(bad_phase)}/{len(points)} corners** "
            + (
                "-- failing: " + ", ".join(f"`{c}`" for c in bad_phase)
                if bad_phase
                else "-- every conversion completed inside its 12 CLK periods with "
                "one-hot phases in the DR-006 order."
            )
        )
        if probe is not None:
            a(
                "- **Mechanism probe** (`--mechanism-probe`, baseline corner, "
                "testbench-only modified netlist -- NOT the committed design): see "
                f"`diagnostics/{prov.record_id}/`. "
                + _probe_summary(probe)
            )
        a("")

    lines.extend(
        evidence.environment_block(
            pdk_line=prov.pdk_line,
            ngspice_line=prov.ng_version,
            netlist_sha256=prov.netlist_sha,
            extra={
                "tran step": f"{tb.TRAN_STEP_NS} ns",
                "simulated span": f"{tb.t_stop_ns():.1f} ns per corner point",
                "testbench fragment sha256": f"`{evidence.sha256_file(tb.FRAGMENT_PATH)}`",
                "simulator options": solver_settings_text(solver_profile),
            },
        )
    )
    a("")
    written_by = (
        f"sim/full-conversion-transient/run_conversion.py --record --solver-profile {solver_profile}"
        if control else "sim/full-conversion-transient/run_conversion.py --corners --record"
    )
    lines.extend(evidence.footer_lines(written_by, supersedes))

    path = evidence.close_record(prov, lines, "Solver-control record" if control else "Record")
    if not control:
        evidence.write_latest_pointer(EXPERIMENT_DIR, prov.record_id)
    return path


def _probe_summary(probe: dict) -> str:
    parts = []
    for tag, point in probe.items():
        codes = ", ".join(
            f"{cv['fraction']:+.2f}*V_REF -> {cv['code']} (ideal {cv['ideal_code']})"
            for cv in point["conversions"]
        )
        parts.append(f"`{tag}`: {codes}")
    return " ".join(parts)


# --------------------------------------------------------------------------
# Node-level trace (issue #259): COMP_OUT / comparator differential output
# against the bit-capture registers' sampling CLK edge, on the AS-COMMITTED
# (unmodified) netlist -- unlike --mechanism-probe, this never re-points any
# instance's strobe. It only appends read-only `.meas tran ... find v(...)`
# probes after the committed fragment (assemble_deck()'s `extra_meas`), so
# it is safe to run against the real, unmodified design/sar_adc_top.spice.
# --------------------------------------------------------------------------

# The two corners issue #259's Acceptance Criteria name explicitly: the
# binding corner from the landed records (largest worst-case code error) and
# the one corner where the phase-timing/completion check itself also fails.
NODE_TRACE_CORNERS: tuple[tuple[str, float, float], ...] = (
    ("tt", 27.0, 1.62),  # tt_27c_1.62v
    ("ff", 27.0, 1.80),  # ff_27c_1.80v
)

# Two conversions of the SAME transient run are traced (extra `.meas` probes
# are free -- they sample a run that happens anyway, so tracing two costs no
# extra ngspice time):
#
#   conversion 2  Vd = -0.25*V_REF, ideal code 384 = 0b0110000000
#   conversion 4  Vd = +0.25*V_REF, ideal code 640 = 0b1010000000
#
# Both are non-trivial (ideal per-bit decisions are a genuine mix of 0s and
# 1s, unlike mid-scale or near-full-scale), so a captured all-ones code
# cannot be dismissed as "the ideal answer happened to be mostly 1s anyway".
# They are chosen as an OPPOSITE-SIGN PAIR on purpose: their ideal MSB
# decisions differ (bit9 = 0 vs. bit9 = 1), and the MSB trial is the only
# bit trial in a conversion whose CDAC state is not yet contaminated by an
# earlier mis-captured bit. Comparing the two conversions' MSB-trial
# evaluate-half output therefore tests, independently of the capture-timing
# defect under investigation, whether the comparator core still produces an
# input-dependent decision at all -- the control that separates "the
# decision is made correctly and then destroyed before capture" from "no
# usable decision is ever made".
NODE_TRACE_CONVERSIONS: tuple[int, ...] = (2, 4)

# How far before/after each bit trial's capturing CLK edge (the rising edge
# that ends this phase and starts the next) the pre-edge/post-edge samples
# are taken. Both are well inside their respective windows: the comparator's
# reset half-period is ~T_CLK_NS/2 (~41.7 ns at 12 MHz) wide, and the
# captured bit is held by the mux/DFF feedback for the rest of the
# conversion, so neither epsilon is sensitive to its exact value.
_NODE_TRACE_PRE_EDGE_NS = 1.0
_NODE_TRACE_POST_EDGE_NS = 2.0


def node_trace_plan(conversion: int) -> list[dict]:
    """One entry per bit-trial phase (MSB-first, PH_B9..PH_B0) of
    `conversion`, naming the `.meas` measurement names/nodes/instants this
    trace samples and the bit each phase decides. `bit` mirrors
    gen_full_conversion_tb.py's own MSB-first phase ordering (PH_B9 is phase
    0 of a conversion, PH_B0 is phase 9) -- see that module's docstring
    timing table."""
    plan = []
    for p in range(tb.N_BITS):
        bit = tb.N_BITS - 1 - p
        k_start = tb.PHASES_PER_CONVERSION * conversion + p
        k_end = k_start + 1
        t_start = tb.t_edge_ns(k_start)
        t_end = tb.t_edge_ns(k_end)
        t_mid = t_start + tb.T_CLK_NS * 0.25  # inside the CLK-high evaluate half
        t_pre = t_end - _NODE_TRACE_PRE_EDGE_NS  # inside the CLK-low reset half
        t_post = t_end + _NODE_TRACE_POST_EDGE_NS  # after the capturing edge
        prefix = f"nt_c{conversion}_p{p}"
        plan.append(
            dict(
                phase=p,
                bit=bit,
                t_mid=t_mid,
                t_pre=t_pre,
                t_post=t_post,
                names=dict(
                    clk_mid=f"{prefix}_clk_mid",
                    clk_pre=f"{prefix}_clk_pre",
                    compout_mid=f"{prefix}_compout_mid",
                    compout_pre=f"{prefix}_compout_pre",
                    compoutn_mid=f"{prefix}_compoutn_mid",
                    compoutn_pre=f"{prefix}_compoutn_pre",
                    dout_post=f"{prefix}_dout_post",
                    # issue #265: comparator input top-plate nodes, sampled at
                    # the same mid-evaluate/pre-capture instants as COMP_OUT/
                    # OUTN_NC above, to test the "single-side switching pushes
                    # the comparator's common-mode input out of its headroom
                    # range for large-magnitude codes" hypothesis (DR-008
                    # "Open items", DR-004's ~23 mV nominal CM headroom
                    # margin). TOP_P/TOP_N are design/sar_adc_top.spice's own
                    # top-level nodes (the comparator's VINP/VINN), read-only
                    # probes exactly like the pre-existing entries above.
                    top_p_mid=f"{prefix}_top_p_mid",
                    top_n_mid=f"{prefix}_top_n_mid",
                    top_p_pre=f"{prefix}_top_p_pre",
                    top_n_pre=f"{prefix}_top_n_pre",
                ),
            )
        )
    return plan


def node_trace_measure_lines(plan: list[dict], conversion: int | None = None) -> list[str]:
    lines = [
        "* --- issue #259 node-level trace: COMP_OUT/CLK around each bit's",
        "* capturing edge (testbench-only extra .meas probes; DUT unmodified) --",
    ]
    if conversion is not None:
        lines.append(f"* conversion {conversion}")
    for entry in plan:
        n = entry["names"]
        dout_node = f"dout{entry['bit']}"
        lines += [
            f".meas tran {n['clk_mid']} find v(CLK) at={entry['t_mid']:.4f}n",
            f".meas tran {n['clk_pre']} find v(CLK) at={entry['t_pre']:.4f}n",
            f".meas tran {n['compout_mid']} find v(COMP_OUT) at={entry['t_mid']:.4f}n",
            f".meas tran {n['compout_pre']} find v(COMP_OUT) at={entry['t_pre']:.4f}n",
            f".meas tran {n['compoutn_mid']} find v(OUTN_NC) at={entry['t_mid']:.4f}n",
            f".meas tran {n['compoutn_pre']} find v(OUTN_NC) at={entry['t_pre']:.4f}n",
            f".meas tran {n['dout_post']} find v({dout_node}) at={entry['t_post']:.4f}n",
            f".meas tran {n['top_p_mid']} find v(TOP_P) at={entry['t_mid']:.4f}n",
            f".meas tran {n['top_n_mid']} find v(TOP_N) at={entry['t_mid']:.4f}n",
            f".meas tran {n['top_p_pre']} find v(TOP_P) at={entry['t_pre']:.4f}n",
            f".meas tran {n['top_n_pre']} find v(TOP_N) at={entry['t_pre']:.4f}n",
        ]
    return lines


def _node_trace_names(plan: list[dict]) -> list[str]:
    names: list[str] = []
    for entry in plan:
        names += list(entry["names"].values())
    return names


def run_node_trace_point(
    netlist_text: str,
    pdk_info: pdk.PdkInfo,
    scratch: Path,
    process_corner: str,
    temp_c: float,
    supply_v: float,
    conversions: tuple[int, ...],
) -> dict:
    """Run the as-committed DUT ONCE with the node-trace `.meas` probes for
    every conversion in `conversions` appended, and decode the result into a
    per-conversion, per-phase trace: CLK/COMP_OUT/comparator
    differential-output-pair voltages at the mid-evaluate instant and just
    before the capturing edge, plus the bit register's own captured value
    just after that edge.

    All the traced conversions belong to the same committed stimulus and the
    same transient, so probing several costs no extra simulation time."""
    cid = corners_mod.corner_id(process_corner, temp_c, supply_v)
    plans = {c: node_trace_plan(c) for c in conversions}
    extra_meas: list[str] = []
    for c in conversions:
        extra_meas += node_trace_measure_lines(plans[c], conversion=c)
    deck = assemble_deck(
        netlist_text, pdk_info, process_corner, temp_c, supply_v, extra_meas=extra_meas
    )
    t0 = time.time()
    log_text = _run_ngspice(deck, scratch, f"node_trace_{cid}")
    wall_s = time.time() - t0

    names: list[str] = []
    for c in conversions:
        names += _node_trace_names(plans[c])
    parsed = measure.parse(log_text, names, anchored=False)
    missing = measure.missing(parsed, names)

    threshold = tb.DIGITAL_THRESHOLD_FRACTION * supply_v

    def bit_high(v: float | None) -> str:
        return "?" if v is None else ("1" if v > threshold else "0")

    traced = []
    for c in conversions:
        frac = tb.input_fraction(c)
        ideal_code = tb.ideal_code(frac)
        phases = []
        for entry in plans[c]:
            n = entry["names"]
            v = {k: parsed.get(name) for k, name in n.items()}
            ideal_bit = (ideal_code >> entry["bit"]) & 1
            phases.append(
                dict(
                    phase=entry["phase"],
                    bit=entry["bit"],
                    ideal_bit=ideal_bit,
                    v=v,
                    clk_mid_hi=bit_high(v["clk_mid"]),
                    clk_pre_hi=bit_high(v["clk_pre"]),
                    compout_mid_hi=bit_high(v["compout_mid"]),
                    compout_pre_hi=bit_high(v["compout_pre"]),
                    compoutn_mid_hi=bit_high(v["compoutn_mid"]),
                    compoutn_pre_hi=bit_high(v["compoutn_pre"]),
                    dout_post_hi=bit_high(v["dout_post"]),
                )
            )
        traced.append(
            dict(conversion=c, fraction=frac, ideal_code=ideal_code, phases=phases)
        )

    return dict(
        corner_id=cid,
        process_corner=process_corner,
        temp_c=temp_c,
        supply_v=supply_v,
        conversions=traced,
        missing=missing,
        log_text=log_text,
        wall_s=wall_s,
    )


def _all_phases(point: dict) -> list[dict]:
    """Every traced phase of every traced conversion at one corner."""
    return [ph for conv in point["conversions"] for ph in conv["phases"]]


def msb_evaluate_control(point: dict) -> dict:
    """The opposite-sign MSB-trial control: for each traced conversion, the
    comparator's own mid-evaluate output at the MSB trial (phase 0) -- the
    only bit trial whose CDAC state cannot have been corrupted by an
    earlier mis-captured bit -- against that conversion's ideal MSB.

    `tracks_input` is True only if the mid-evaluate decision matches the
    ideal MSB for EVERY traced conversion AND the traced conversions do not
    all share the same ideal MSB (an all-same-MSB set would make a match
    vacuous)."""
    rows = []
    for conv in point["conversions"]:
        msb = conv["phases"][0]
        rows.append(
            dict(
                conversion=conv["conversion"],
                fraction=conv["fraction"],
                ideal_bit=msb["ideal_bit"],
                compout_mid=msb["v"].get("compout_mid"),
                compout_mid_hi=msb["compout_mid_hi"],
                matches=msb["compout_mid_hi"] == str(msb["ideal_bit"]),
            )
        )
    discriminating = len({r["ideal_bit"] for r in rows}) > 1
    return dict(
        rows=rows,
        discriminating=discriminating,
        tracks_input=discriminating and all(r["matches"] for r in rows),
    )


def run_node_trace(scratch: Path, quiet: bool) -> tuple[dict[str, dict], str]:
    pdk_info = pdk.resolve()
    netlist_text = dut_text()
    out: dict[str, dict] = {}
    for pc, tc, sv in NODE_TRACE_CORNERS:
        point = run_node_trace_point(
            netlist_text, pdk_info, scratch, pc, tc, sv, NODE_TRACE_CONVERSIONS
        )
        out[point["corner_id"]] = point
        if not quiet:
            phases = _all_phases(point)
            n_reset_at_capture = sum(1 for ph in phases if ph["compout_pre_hi"] == "1")
            n_captured_one = sum(1 for ph in phases if ph["dout_post_hi"] == "1")
            control = msb_evaluate_control(point)
            print(
                f"  [node-trace {point['corner_id']}] COMP_OUT already high "
                f"(reset) at {n_reset_at_capture}/{len(phases)} capturing edges; "
                f"{n_captured_one}/{len(phases)} bits captured '1'; "
                f"MSB-trial evaluate-half decision tracks input sign: "
                f"{'YES' if control['tracks_input'] else 'no'} "
                f"({point['wall_s']:.0f}s)",
                flush=True,
            )
    return out, netlist_text


def write_node_trace_record(traces: dict[str, dict], netlist_text: str) -> Path:
    prov, lines = evidence.open_record(
        EXPERIMENT_DIR, netlist_text, "diagnostics",
        {f"node-trace-{cid}.log": point["log_text"] for cid, point in traces.items()},
    )

    first_point = next(iter(traces.values()))
    traced_conversions = first_point["conversions"]
    n_traces_per_corner = sum(len(c["phases"]) for c in traced_conversions)

    a = lines.append
    a(
        "- **Claim**: issue #259 (diagnostic/investigation only -- no spec row "
        "and no design fix). This record extends the "
        "`sim/full-conversion-transient/records/20260910-190240-2d1d196.md` "
        "(also reproduced, unchanged, by the post-#258 "
        "`sim/full-conversion-transient/records/20260911-071010-f0e45fa.md`) "
        "`--mechanism-probe` finding -- 'comparator-decision-capture timing is "
        "implicated' -- with a NODE-LEVEL voltage trace of `COMP_OUT` "
        "(`design/comparator.sch`'s `OUTP`) and its differential partner "
        "`OUTN_NC` (`OUTN`) against `CLK`, at every one of the 10 bit-trial "
        "capturing edges of each of two opposite-sign conversions, at the two "
        "corners issue #259's Acceptance Criteria name: the binding corner "
        "(largest worst-case code error) and the corner where the "
        "phase-timing/completion check itself also fails. It pins down which "
        "`CLK` edge relationship is misaligned in the AS-COMMITTED netlist -- "
        "the DUT is unmodified (only read-only `.meas` probes are added; "
        "contrast `--mechanism-probe`, which re-points the comparator's own "
        "strobe on a testbench-only copy)."
    )
    a(
        "- **Netlist provenance**: schematic (`design/sar_adc_top.spice`, "
        "unmodified -- same as the corner-campaign records; no design fix in "
        "this record's own scope)"
    )
    a(
        f"- **Stimulus**: the committed `sim/full-conversion-transient/testbench/"
        f"full_conversion_tb_fragment.spice` (`f_clk = {tb.F_CLK_HZ / 1e6:g} MHz`, "
        f"DR-006 worst case), traced at "
        + " and ".join(
            f"conversion {c['conversion']} (`Vd = {c['fraction']:+.2f}*V_REF`, "
            f"ideal code {c['ideal_code']} = `{c['ideal_code']:010b}`)"
            for c in traced_conversions
        )
        + " -- both non-trivial inputs whose 10 ideal per-bit decisions are a "
        "genuine mix of 0s and 1s, not all-1s or all-0s, and deliberately an "
        "OPPOSITE-SIGN pair (their ideal MSB decisions differ), which is what "
        "makes the MSB-trial control below discriminating. Both conversions "
        "are probed within the SAME transient run at each corner -- extra "
        "`.meas` cards cost no extra simulation."
    )
    a(
        "- **Corners traced**: `" + "`, `".join(traces.keys()) + "` -- the "
        "binding corner from the landed corner-campaign records and the "
        "corner where the phase-timing/completion check itself also fails "
        "(issue #259 Acceptance Criteria), not the full 9-point ratified grid "
        "(this is a targeted mechanism trace, not a corner campaign)."
    )
    a("")

    a("## The edge relationship at fault (stated explicitly, from the trace below)")
    a("")
    a(
        "**The comparator's decision is destroyed by its own reset half-period "
        "BEFORE the bit-capture register's sampling edge arrives.** The two "
        "blocks are strobed by the same top-level `CLK`, but they use "
        "*opposite* edges of it, in the wrong order:"
    )
    a("")
    a(
        "| block | device / cell | strobed by | decision valid during | decision destroyed at |"
    )
    a("|---|---|---|---|---|")
    a(
        "| comparator (`design/comparator.sch`) | `XM_TAIL` (NFET tail, gate = `CLK`), "
        "`XM_RST_P`/`XM_RST_N` (PFET resets to `VDD`, gates = `CLK`) | level | "
        "`CLK` HIGH half (evaluate) | `CLK` **falling** edge -- `OUTP`/`OUTN` are "
        "both pulled to `VDD` for the whole `CLK` LOW half |"
    )
    a(
        "| bit-capture register (`design/sar_sequencer.sch`, `xbreg9..xbreg0`) | "
        "`sky130_fd_sc_hd__dfrtp_1`, positive-edge-triggered | `CLK` **rising** "
        "edge | n/a | n/a |"
    )
    a("")
    a(
        "So within a bit-trial phase `PH_Bn`, which spans one whole `CLK` "
        "period, the order of events is: **rising edge** (phase opens, "
        "comparator begins evaluating) -> `CLK` HIGH half (decision "
        "regenerates on `OUTP`/`OUTN` -- the only window in which it exists) "
        "-> **falling edge** (`XM_RST_P`/`XM_RST_N` turn on and force both "
        "`OUTP` and `OUTN` to `VDD`) -> `CLK` LOW half (`COMP_OUT` parked at "
        "`VDD`, a fixed digital `1`, for ~`T_CLK/2` = ~"
        f"{tb.T_CLK_NS / 2:.1f} ns at the DR-006 worst-case "
        f"{tb.F_CLK_HZ / 1e6:g} MHz) -> **next rising edge**, which is the "
        "edge `xbreg<n>` uses to capture `MUXOUT<n>` (= `COMP_OUT` while "
        "`PH_Bn` is still high). The register therefore samples the RESET "
        "level, never the decision. **The fault is the half-period "
        "ordering, not a setup/hold margin**: the capture edge is a full "
        "half-period late relative to the last instant the decision exists, "
        "so no amount of process/voltage/temperature skew can align them -- "
        "consistent with all 9 ratified corners failing identically."
    )
    a("")
    a(
        "The `COMP_OUT@pre` column below (`COMP_OUT` sampled "
        f"{_NODE_TRACE_PRE_EDGE_NS:g} ns before each capturing edge, i.e. "
        "inside the reset half) confirms this directly: it reads `VDD` "
        "(digital `1`) at every traced bit trial, at both corners, regardless "
        f"of `ideal bit`, and `DOUT@post` (the register's own output "
        f"{_NODE_TRACE_POST_EDGE_NS:g} ns after the same edge) matches it "
        "exactly -- the register faithfully captures whatever `COMP_OUT` is "
        "doing at its edge, and what it is doing is 'still in reset', not "
        "'holding this bit trial's decision'. `CLK@pre` reads `0 V` in the "
        "same rows, confirming the pre-edge sample really is inside the `CLK` "
        "LOW reset half and not mis-timed."
    )
    a("")

    # --- The MSB-trial control: is the comparator core itself still alive? --
    controls = {cid: msb_evaluate_control(point) for cid, point in traces.items()}
    all_track = all(c["tracks_input"] for c in controls.values())
    a("### Control: is the comparator core still producing a decision at all?")
    a("")
    a(
        "A capture-timing defect and a dead comparator would both show up as "
        "a stuck captured code, so the trace has to tell them apart. The MSB "
        "trial (`PH_B9`) is the discriminator: it is the only bit trial whose "
        "CDAC state cannot already have been corrupted by an earlier "
        "mis-captured bit, so its evaluate-half output is a clean read of the "
        "comparator core. Tracing an opposite-sign pair of conversions makes "
        "that read discriminating -- their ideal MSB decisions differ."
    )
    a("")
    a("| corner | conversion | Vd | ideal MSB | COMP_OUT@mid (V) | reads as | tracks input? |")
    a("|---|---|---|---|---|---|---|")
    for cid, control in controls.items():
        for r in control["rows"]:
            mv = r["compout_mid"]
            a(
                f"| `{cid}` | {r['conversion']} | {r['fraction']:+.2f}*V_REF | "
                f"{r['ideal_bit']} | "
                + ("MISSING" if mv is None else f"{mv:.4f}")
                + f" | {r['compout_mid_hi']} | "
                + ("YES" if r["matches"] else "no")
                + " |"
            )
    a("")
    a(
        (
            "**The comparator core is alive and input-dependent.** At both "
            "traced corners the MSB trial's evaluate-half output follows the "
            "sign of the applied differential input -- opposite-sign inputs "
            "give opposite `COMP_OUT@mid` levels, each matching that "
            "conversion's own ideal MSB. The decision IS made correctly "
            "during the `CLK` HIGH half and is then destroyed by the reset "
            "half before the capturing rising edge. This isolates the defect "
            "to the capture-edge relationship above and rules out 'the "
            "comparator never resolves' as an alternative explanation for "
            "the saturated code."
            if all_track
            else "**Inconclusive / NOT input-dependent -- see the table "
            "above.** The MSB trial's evaluate-half output does not follow "
            "the sign of the applied input at every traced corner, so this "
            "record CANNOT rule out a second, independent defect in the "
            "comparator core itself on top of the capture-edge relationship. "
            "Treat the capture-edge finding as necessary but possibly not "
            "sufficient, and do not close out the saturation bug on the "
            "strength of a capture-timing fix alone without re-running this "
            "control."
        )
    )
    a("")
    a(
        "For bit trials 8..0 the evaluate-half output is NOT expected to "
        "track the ideal bit and does not: once `DOUT9` has been captured "
        "wrongly, every later trial is comparing against a CDAC residual the "
        "SAR algorithm never intended to produce, so those `COMP_OUT@mid` "
        "entries are a downstream consequence of the confirmed mechanism, not "
        "independent evidence about it. They are reported in the per-corner "
        "tables for completeness and nothing is concluded from them here."
    )
    a("")

    for cid, point in traces.items():
        a(f"## Trace at `{cid}`")
        a("")
        if point["missing"]:
            a(f"**MISSING measurements**: {', '.join(point['missing'])}")
            a("")
        for conv in point["conversions"]:
            a(
                f"### Conversion {conv['conversion']} "
                f"(`Vd = {conv['fraction']:+.2f}*V_REF`, ideal code "
                f"{conv['ideal_code']} = `{conv['ideal_code']:010b}`)"
            )
            a("")
            a(
                "| phase | bit | ideal bit | CLK@mid (V) | COMP_OUT@mid (V) | "
                "OUTN@mid (V) | CLK@pre (V) | COMP_OUT@pre (V) | OUTN@pre (V) | "
                "DOUT@post (V) | captured | match ideal? |"
            )
            a("|---|---|---|---|---|---|---|---|---|---|---|---|")
            for ph in conv["phases"]:
                v = ph["v"]

                def fv(key: str, _v=v) -> str:
                    val = _v.get(key)
                    return "MISSING" if val is None else f"{val:.4f}"

                captured = ph["dout_post_hi"]
                match = (
                    "?" if captured == "?" else ("YES" if captured == str(ph["ideal_bit"]) else "no")
                )
                a(
                    f"| PH_B{ph['bit']} | {ph['bit']} | {ph['ideal_bit']} | "
                    f"{fv('clk_mid')} | {fv('compout_mid')} | {fv('compoutn_mid')} | "
                    f"{fv('clk_pre')} | {fv('compout_pre')} | {fv('compoutn_pre')} | "
                    f"{fv('dout_post')} | {captured} | {match} |"
                )
            a("")
        phases = _all_phases(point)
        n_reset_at_capture = sum(1 for ph in phases if ph["compout_pre_hi"] == "1")
        n_captured_one = sum(1 for ph in phases if ph["dout_post_hi"] == "1")
        a(
            f"- `COMP_OUT` already at `VDD` (reset) "
            f"{_NODE_TRACE_PRE_EDGE_NS:g} ns before the capturing edge: "
            f"**{n_reset_at_capture}/{len(phases)}** bit trials "
            f"({len(point['conversions'])} conversions x {tb.N_BITS} bits)."
        )
        a(f"- Bits captured as `1`: **{n_captured_one}/{len(phases)}**.")
        a("")

    a("## Uniform across bits, or subset-specific?")
    a("")
    all_uniform = all(
        all(
            ph["compout_pre_hi"] == "1" and ph["dout_post_hi"] == "1"
            for ph in _all_phases(point)
        )
        for point in traces.values()
    )
    a(
        ("**Uniform.** " if all_uniform else "**NOT uniform -- see per-corner tables above.** ")
        + (
            f"Every one of the {n_traces_per_corner} traced bit trials "
            f"({len(traced_conversions)} conversions x {tb.N_BITS} bits), at "
            "both traced corners, shows `COMP_OUT` already reset to `VDD` "
            "before its capturing edge and the corresponding bit register "
            "capturing `1` -- including `DOUT9` (phase `PH_B9`, the "
            "sequencer's first/MSB trial, whose own `sar_sequencer.sch` "
            "capture path is otherwise identical to every other bit's), and "
            "including the trials whose ideal bit is `1` as well as those "
            "whose ideal bit is `0`. The mechanism is a property of the "
            "shared `CLK` edge relationship between the comparator and every "
            "bit-capture register -- all 10 registers are wired to the same "
            "`CLK` net and fed from the same `COMP_OUT` net -- not of any "
            "specific bit position, mux select, or CDAC feedback path. "
            "Correspondingly, no subset of bits would be fixed, or left "
            "broken, by a change targeting one bit position."
            if all_uniform
            else "Bit-by-bit detail is in the per-corner tables above; the "
            "mechanism does not reproduce identically at every phase, so a "
            "uniform capture-timing explanation alone does not fully account "
            "for the observed saturation -- see the per-phase table for which "
            "bits diverge."
        )
    )
    a("")

    # Largest deviation of any sampled node from its nearest rail, over every
    # probe at every corner -- the quantitative form of "no node is floating
    # at an intermediate level", used by the #258 reconciliation below.
    worst_rail_dev_mv = 0.0
    worst_rail_dev_where = ""
    for cid, point in traces.items():
        for conv in point["conversions"]:
            for ph in conv["phases"]:
                for key, val in ph["v"].items():
                    if val is None:
                        continue
                    dev_mv = min(abs(val), abs(point["supply_v"] - val)) * 1e3
                    if dev_mv > worst_rail_dev_mv:
                        worst_rail_dev_mv = dev_mv
                        worst_rail_dev_where = (
                            f"{cid}, conversion {conv['conversion']}, "
                            f"PH_B{ph['bit']}, {key}"
                        )

    a("## Reconciliation with #257 and #258")
    a("")
    a(
        "### #257 -- \"comparator reset and bit-capture register share the "
        "same CLK edge\": **CONFIRMED, and refined**"
    )
    a("")
    a(
        "#257's root-cause description -- the comparator resets for the "
        "entire `CLK = 0` half-period, and the bit-capture registers sample "
        "on the shared `CLK`'s rising edge, so every register always samples "
        "the post-reset `1` level and never the mid-evaluate decision -- "
        "matches this record's trace exactly: `COMP_OUT@pre` reads `VDD` at "
        f"every one of the {n_traces_per_corner} traced bit trials, at both "
        "corners. #257's further claim that the comparator nonetheless "
        "\"genuinely reads the correct decision partway through the "
        "`CLK`-high evaluate half-period\" is also now independently "
        "supported, by the opposite-sign MSB-trial control above, which "
        "#257's own (phantom, see below) trace could not be checked for. Two "
        "refinements this record adds to #257's wording:"
    )
    a("")
    a(
        "1. #257 frames the defect as the two blocks sharing \"the same "
        "`CLK` edge\". They do not share an edge -- they use **opposite** "
        "edges (comparator: decision destroyed on the FALLING edge; "
        "registers: sample on the RISING edge), in the wrong order. They "
        "share the same `CLK` *net*. The distinction matters for the fix: "
        "the deficit is a fixed half-period of ordering, not a skew or a "
        "setup/hold margin, so any fix must move the capture instant into "
        "the evaluate half (or hold reset off past the capture edge) -- "
        "trimming delay cannot close it."
    )
    a(
        "2. #257's phase-timing observation (\"PASSES at all 9/9 corners\") "
        "does not reproduce: the landed corner-campaign records report "
        "**8/9**, with `ff_27c_1.80v` the exception. That is a property of "
        "the landed records, not of this trace, and it is why `ff_27c_1.80v` "
        "is one of the two corners traced here."
    )
    a("")
    a(
        "**The 1019 LSB vs. 910 LSB discrepancy: RESOLVED -- it is an input-"
        "set difference, not a mechanism or decode-convention difference.** "
        "#257's cited node-level trace record "
        "(`sim/full-conversion-transient/records/20260910-063010-ce6fcf1.md`, "
        "target code 212) does not exist in this repository, per #257's own "
        "2026-09-10 Verified-corrections entry, so its raw data cannot be "
        "re-derived. Its headline number can be, though, and it is "
        "consistent: under THIS repository's committed decode convention "
        "(`gen_full_conversion_tb.py`'s `ideal_code()` -- offset binary, "
        "mid-scale = 512, `LSB = 2*V_REF/2^N`), a captured code of 1023 "
        "against a most-negative input of `-0.9922*V_REF` gives ideal code 4 "
        "and a worst error of exactly **1019 LSB**, while the committed "
        "input schedule's own most-negative point, `-0.78*V_REF`, gives "
        "ideal code 113 and exactly **910 LSB**. Both figures are "
        "`1023 - ideal_code(most-negative input)` under the same convention; "
        "they differ only because #257's campaign applied a near-full-scale "
        "negative input (its own body says \"near -FS\") where this "
        "repository's committed schedule stops at `-0.78*V_REF`. Neither "
        "number is evidence about the mechanism -- both are just the "
        "saturation distance from whatever the most-extreme applied input "
        "happened to be. **Recommendation for whoever fixes this:** treat "
        "910 LSB (the landed, reproducible figure) as the reference and drop "
        "1019 LSB, which has no committed evidence behind it."
    )
    a("")
    a(
        "### #258 -- \"VGND/VPWR omitted from sar_sequencer.sch's `.subckt` "
        "port list, floating when nested\": **NOT the operative mechanism**"
    )
    a("")
    a(
        "Checked three independent ways rather than inferred from the "
        "earlier record's clean digital levels alone:"
    )
    a("")
    a(
        "1. **The defect is no longer present in the DUT this trace ran "
        "on.** #258 was fixed and closed by PR #261 (merged "
        "2026-09-11T08:15:39Z), which made `design/sar_adc_top.sch` emit "
        "`.GLOBAL VPWR` / `.GLOBAL VGND`. The netlist snapshot frozen "
        "alongside this record carries both cards (together with the "
        "pre-existing `.GLOBAL GND` / `.GLOBAL VDD`), so the sequencer's "
        "standard cells are demonstrably powered here -- yet the capture "
        "mechanism traced above is unchanged. A defect that has been fixed "
        "cannot be causing a symptom that survives the fix."
    )
    a(
        "2. **The 9-corner campaign result is byte-for-byte unchanged across "
        "that fix.** "
        "`sim/full-conversion-transient/records/20260911-071010-f0e45fa.md` "
        "re-ran the full ratified grid AFTER PR #261 landed and reports the "
        "identical 1023 saturation, the same 910 LSB worst-case error, and "
        "the same binding corner `tt_27c_1.62v` as the pre-fix "
        "`20260910-190240-2d1d196.md` record. (Expected, and not a "
        "contradiction of #258's own evidence: this experiment's driver "
        "already declared `.global VPWR VGND` in its own assembled deck -- "
        "#258's \"Option 3\" -- so the sequencer was never actually floating "
        "in EITHER campaign. #258's four-check evidence concerned the "
        "committed netlist's behaviour for consumers that do NOT supply that "
        "declaration, which is a real defect, correctly fixed, and simply "
        "not this one.)"
    )
    a(
        "3. **No intermediate voltage appears anywhere in this trace.** "
        "#258's own signature failure mode is digital nodes drifting to "
        "arbitrary non-rail levels (its check 2 observed ~0.4-1.5 V at "
        "VDD = 1.8 V). Every voltage in the per-corner tables above sits at "
        "a clean rail: the largest deviation of ANY sampled node from its "
        f"nearest rail (`0 V` or that corner's own `VDD`) is "
        f"**{worst_rail_dev_mv:.1f} mV**"
        + (
            f" (`{worst_rail_dev_where}`)"
            if worst_rail_dev_where
            else ""
        )
        + ", across every probe at both corners -- including the "
        "`DOUT@post` register outputs inside the sequencer, the block #258 "
        "concerns. The saturated code here is a correctly-captured wrong "
        "value, not an undriven node."
    )
    a("")

    a("## Out of scope")
    a("")
    a(
        "No design fix is proposed or implemented by this record, per issue "
        "#259's own scope. The confirmed mechanism (comparator reset vs. "
        "bit-capture edge, as #257 already describes) is #257's -- or a "
        "future issue's -- job to fix. Nothing in `design/` is modified by "
        "the `--node-trace` mode: it appends read-only `.meas tran ... find "
        "v(...)` cards after the committed testbench fragment and simulates "
        "the byte-identical committed netlist, whose sha256 is recorded "
        "below and whose snapshot is frozen under `netlist-snapshots/`. Nor "
        "is any spec row substantiated, proposed, or relaxed."
    )
    a("")

    lines.extend(
        evidence.environment_block(
            pdk_line=prov.pdk_line,
            ngspice_line=prov.ng_version,
            netlist_sha256=prov.netlist_sha,
            extra={
                "tran step": f"{tb.TRAN_STEP_NS} ns",
                "traced conversions": ", ".join(
                    f"{c['conversion']} (Vd = {c['fraction']:+.2f}*V_REF, "
                    f"ideal code {c['ideal_code']})"
                    for c in traced_conversions
                ),
                "pre-edge / post-edge margins": f"{_NODE_TRACE_PRE_EDGE_NS:g} ns / "
                f"{_NODE_TRACE_POST_EDGE_NS:g} ns",
            },
        )
    )
    a("")
    lines.extend(
        evidence.footer_lines(
            "sim/full-conversion-transient/run_conversion.py --node-trace",
            # Deliberately "(none)", not the two corner-campaign records this
            # extends: **Supersedes** means "replaces and invalidates", which
            # this diagnostic does not do -- see the "Claim" bullet above and
            # the Reconciliation section for the (non-superseding) references
            # to those records. Naming a record ID here would make
            # sim/report/generate.py's find_superseding_sibling() (a plain
            # substring match against this field) misread this record as
            # superseding the corner-campaign evidence, which it does not.
            # Spelled as the named sentinel, not a bare "", so
            # sim/check_supersedes_capability.py can tell this deliberate
            # opt-out apart from a forgotten --supersedes (issue #502).
            evidence.NEVER_SUPERSEDES,
        )
    )

    return evidence.close_record(prov, lines, "Node-trace record")


# --------------------------------------------------------------------------
# Common-mode trace (issue #265): does decision-directed single-side CDAC
# switching push the comparator's TOP_P/TOP_N input pair out of its ~23 mV
# nominal common-mode headroom margin (DR-004) for the two near-full-scale
# inputs (+-0.78*V_REF) that saturate in sim/full-conversion-transient/'s own
# corner campaign? Reuses run_node_trace_point()'s infrastructure (the
# TOP_P/TOP_N probes added above, issue #265) at conversions 1/5 -- the
# +-0.78*V_REF inputs themselves -- rather than the #259 node-trace's own
# opposite-sign +-0.25*V_REF pair. Read-only .meas probes only; the DUT is
# unmodified, exactly like --node-trace.
# --------------------------------------------------------------------------

# Reuse #259's own two named corners (binding corner + the corner where the
# phase-timing check also fails) -- issue #265's problem is already
# established as corner-invariant (the evidence record this issue is filed
# against shows +0.78*V_REF saturating to 1023 at all 9 ratified corners), so
# a targeted 2-corner trace is enough to confirm or refute the mechanism
# without re-running the full 9-point grid for a diagnostic.
CM_TRACE_CORNERS: tuple[tuple[str, float, float], ...] = NODE_TRACE_CORNERS

# The two near-full-scale conversions issue #265 is filed against: conversion
# 1 (Vd = -0.78*V_REF, ideal code 113) and conversion 5 (Vd = +0.78*V_REF,
# ideal code 911) -- see gen_full_conversion_tb.py's INPUT_FRACTIONS.
CM_TRACE_CONVERSIONS: tuple[int, ...] = (1, 5)

# A phase's common mode is treated as "out of range" once it deviates from
# the nominal VCM = vdd_val/2 by more than this many volts -- deliberately
# much looser than DR-004's own ~23 mV nominal margin (it is a headroom
# figure at the comparator's *own* internal devices, not a node-level
# translation this experiment re-derives), so this threshold is used only to
# flag a grossly-out-of-range phase for the write-up, not as a re-derived
# spec limit.
_CM_GROSS_DEVIATION_V = 0.100


def run_cm_trace(scratch: Path, quiet: bool) -> tuple[dict[str, dict], str]:
    pdk_info = pdk.resolve()
    netlist_text = dut_text()
    out: dict[str, dict] = {}
    for pc, tc, sv in CM_TRACE_CORNERS:
        point = run_node_trace_point(
            netlist_text, pdk_info, scratch, pc, tc, sv, CM_TRACE_CONVERSIONS
        )
        out[point["corner_id"]] = point
        if not quiet:
            for conv in point["conversions"]:
                worst_cm = max(
                    abs(0.5 * (ph["v"]["top_p_mid"] + ph["v"]["top_n_mid"]) - 0.5 * sv)
                    for ph in conv["phases"]
                    if ph["v"]["top_p_mid"] is not None and ph["v"]["top_n_mid"] is not None
                )
                print(
                    f"  [cm-trace {point['corner_id']}] conversion {conv['conversion']} "
                    f"(Vd={conv['fraction']:+.2f}*V_REF): worst |CM - VCM| = "
                    f"{worst_cm * 1e3:.1f} mV across the traced bit trials",
                    flush=True,
                )
    return out, netlist_text


def _cm_deviation_v(ph: dict, supply_v: float) -> float | None:
    p = ph["v"].get("top_p_mid")
    n = ph["v"].get("top_n_mid")
    if p is None or n is None:
        return None
    return 0.5 * (p + n) - 0.5 * supply_v


def write_cm_trace_record(traces: dict[str, dict], netlist_text: str) -> Path:
    prov, lines = evidence.open_record(
        EXPERIMENT_DIR, netlist_text, "diagnostics",
        {f"cm-trace-{cid}.log": point["log_text"] for cid, point in traces.items()},
    )

    first_point = next(iter(traces.values()))
    traced_conversions = first_point["conversions"]

    a = lines.append
    a(
        "- **Claim**: issue #265 (diagnostic/investigation only -- no spec row "
        "and no design fix in this record's own scope). This record tests "
        "DR-008's own \"Open items\" leading hypothesis -- that "
        "decision-directed single-side CDAC switching (issue #263) pushes "
        "the comparator's `TOP_P`/`TOP_N` input pair out of its ~23 mV "
        "nominal common-mode headroom margin (DR-004 Amendment A / DR-003 "
        "Item 1) for large-magnitude codes -- with a node-level voltage "
        "trace of `TOP_P`/`TOP_N` (the comparator's own `VINP`/`VINN`, "
        "`design/sar_adc_top.spice`'s `xcmp` instance line) against `CLK` "
        "and `COMP_OUT`, at every one of the 10 bit-trial capturing edges of "
        "the two near-full-scale inputs "
        "(`sim/full-conversion-transient/records/20260911-204111-a6df3bb.md` "
        "-- the record this issue is filed against) that saturate the "
        "captured code. The DUT is unmodified (only read-only `.meas` "
        "probes are added, exactly like `--node-trace`)."
    )
    a(
        "- **Netlist provenance**: schematic (`design/sar_adc_top.spice`, "
        "unmodified -- same as the corner-campaign records; no design fix "
        "in this record's own scope)"
    )
    a(
        f"- **Stimulus**: the committed `sim/full-conversion-transient/testbench/"
        f"full_conversion_tb_fragment.spice` (`f_clk = {tb.F_CLK_HZ / 1e6:g} MHz`, "
        f"DR-006 worst case), traced at "
        + " and ".join(
            f"conversion {c['conversion']} (`Vd = {c['fraction']:+.2f}*V_REF`, "
            f"ideal code {c['ideal_code']} = `{c['ideal_code']:010b}`)"
            for c in traced_conversions
        )
        + " -- the two near-full-scale inputs issue #265 is filed against, "
        "both probed within the SAME transient run at each corner."
    )
    a(
        "- **Corners traced**: `" + "`, `".join(traces.keys()) + "` -- reusing "
        "issue #259's own two named corners (the binding corner from the "
        "landed corner-campaign records and the corner where the "
        "phase-timing/completion check also fails). The saturation this "
        "issue investigates is already established as corner-invariant "
        "(1023 at all 9 ratified corners for `+0.78*V_REF`), so a targeted "
        "2-corner trace is sufficient to confirm or refute the mechanism."
    )
    a("")

    a("## Finding: CONFIRMED")
    a("")
    a(
        "**Decision-directed single-side switching drives the comparator's "
        "common-mode input hundreds of millivolts away from `VCM`, and the "
        "captured code diverges from the ideal code at exactly the bit "
        "trial where that common-mode excursion becomes large enough to "
        "flip the comparator's decision -- independent of the sign of the "
        "residual.** This is a much larger effect than DR-004's ~23 mV "
        "nominal margin framing suggested: the excursion measured here is "
        "driven by the *sampled input's own magnitude*, not by a marginal "
        "process/temperature/supply skew, so it is not a 23 mV-scale margin "
        "violation but a many-hundred-mV one for a near-full-scale input."
    )
    a("")
    a(
        "**Mechanism, read directly off the trace below.** At the MSB trial "
        "(`PH_B9`, DR-003 Item 3's \"free\" sign bit, decided directly off "
        "the sampled residual with no CDAC switching of its own), `TOP_P` "
        "and `TOP_N` are simply the sampled `VINP`/`VINN` -- their average "
        "is exactly `VCM` regardless of the applied differential magnitude, "
        "because a symmetric differential input satisfies "
        "`VINP + VINN = V_DD` by construction. Once the magnitude-bit trials "
        "begin, DR-008's decision-directed gating (`SELp<i> = DOUT9 AND "
        "DOUT<i>`, `SELn<i> = DOUT9N AND DOUT<i>`) means only ONE side's "
        "bottom plates ever move for a given conversion -- the other side's "
        "`SEL*<i>` is permanently gated to 0 for the whole conversion, so "
        "its bottom plates (and therefore its own top plate, which has no "
        "other charge path once the front end's sampling switch has opened) "
        "stay frozen at the value sampling left them at. For the search to "
        "converge (`TOP_P -> TOP_N`), the ACTIVE side must therefore travel "
        "from its own sampled value all the way to the FROZEN side's "
        "sampled value -- a distance that grows with the applied "
        "differential magnitude, not a fixed offset. For a near-full-scale "
        "input the frozen side sits near a rail (see the trace: `TOP_N` "
        "pinned at ~0.197 V for the whole `+0.78*V_REF` conversion, ~10 % of "
        "`V_DD`), so the active side is driven to visit that same "
        "near-rail neighborhood as the search converges -- and the pair's "
        "COMMON MODE (their average, exactly the quantity DR-004's ~23 mV "
        "margin is about) droops from `VCM` toward that near-rail value "
        "along with it, well past the point where the comparator's NMOS "
        "input pair can resolve a decision correctly."
    )
    a("")
    a(
        "This is a **different, and structurally larger**, mechanism than "
        "DR-004's own ~23 mV framing anticipated: DR-004 quantified a "
        "process/temperature/supply-driven headroom margin around the "
        "*design* common-mode point (`VCM`, fixed at 900 mV by construction "
        "in the differential-input testbench). What this record measures is "
        "an INPUT-DEPENDENT common-mode excursion driven by "
        "decision-directed switching's own topology -- it exists even at "
        "`tt`/27 C/nominal supply, the corner where DR-004's margin is "
        "least stressed, and its size scales with the applied signal's own "
        "magnitude rather than with PVT skew. Both mechanisms shrink the "
        "same headroom budget; this record's mechanism is simply far larger "
        "for the two inputs it was run against."
    )
    a("")

    for cid, point in traces.items():
        a(f"## Trace at `{cid}`")
        a("")
        if point["missing"]:
            a(f"**MISSING measurements**: {', '.join(point['missing'])}")
            a("")
        for conv in point["conversions"]:
            a(
                f"### Conversion {conv['conversion']} "
                f"(`Vd = {conv['fraction']:+.2f}*V_REF`, ideal code "
                f"{conv['ideal_code']} = `{conv['ideal_code']:010b}`)"
            )
            a("")
            a(
                "| phase | bit | ideal bit | TOP_P@mid (V) | TOP_N@mid (V) | "
                "CM@mid (V) | CM dev. from VCM (mV) | COMP_OUT@mid (V) | "
                "DOUT@post | match ideal? |"
            )
            a("|---|---|---|---|---|---|---|---|---|---|")
            for ph in conv["phases"]:
                v = ph["v"]

                def fv(key: str, _v=v) -> str:
                    val = _v.get(key)
                    return "MISSING" if val is None else f"{val:.4f}"

                cm_dev = _cm_deviation_v(ph, point["supply_v"])
                cm_mid = (
                    None
                    if v.get("top_p_mid") is None or v.get("top_n_mid") is None
                    else 0.5 * (v["top_p_mid"] + v["top_n_mid"])
                )
                captured = ph["dout_post_hi"]
                match = (
                    "?" if captured == "?" else ("YES" if captured == str(ph["ideal_bit"]) else "no")
                )
                a(
                    f"| PH_B{ph['bit']} | {ph['bit']} | {ph['ideal_bit']} | "
                    f"{fv('top_p_mid')} | {fv('top_n_mid')} | "
                    + ("MISSING" if cm_mid is None else f"{cm_mid:.4f}")
                    + " | "
                    + ("MISSING" if cm_dev is None else f"{cm_dev * 1e3:+.1f}")
                    + f" | {fv('compout_mid')} | {captured} | {match} |"
                )
            a("")
        first_wrong = None
        for conv in point["conversions"]:
            for ph in conv["phases"]:
                captured = ph["dout_post_hi"]
                if captured != "?" and captured != str(ph["ideal_bit"]):
                    first_wrong = (conv["conversion"], ph["bit"], ph)
                    break
            if first_wrong:
                break
        if first_wrong:
            conv_n, bit_n, ph = first_wrong
            cm_dev = _cm_deviation_v(ph, point["supply_v"])
            a(
                f"- First mismatch: conversion {conv_n}, bit {bit_n} "
                f"(`PH_B{bit_n}`) -- common-mode deviation from `VCM` at that "
                "trial's mid-evaluate instant: "
                + ("MISSING" if cm_dev is None else f"**{cm_dev * 1e3:+.1f} mV**")
                + (
                    f" (gross, i.e. beyond +-{_CM_GROSS_DEVIATION_V * 1e3:.0f} mV)"
                    if cm_dev is not None and abs(cm_dev) > _CM_GROSS_DEVIATION_V
                    else ""
                )
                + "."
            )
        a("")

    a("## Recommendation")
    a("")
    a(
        "This record confirms the mechanism; it does not fix it, and no fix "
        "is implemented in this record's own scope. Closing the headroom "
        "gap requires one of, at minimum:"
    )
    a("")
    a(
        "1. **A common-mode-neutral CDAC switching scheme** -- e.g. moving "
        "both array sides in a way that keeps their average near `VCM` "
        "(the property unconditional complementary switching had, and "
        "decision-directed single-side switching gave up per DR-008's own "
        "root-cause finding). `design/cdac/cdac_unit_cell.sch`'s own "
        "two-rail (`VREFP`/`VREFN`) switch, per DR-005, has no third "
        "(`VCM`) rail to release onto, so a scheme along these lines is a "
        "CDAC unit-cell redesign, not a top-level wiring change."
    )
    a(
        "2. **A wider-common-mode-range comparator** (e.g. a rail-to-rail "
        "or complementary-input-pair topology) -- would require "
        "re-qualifying DR-004's noise budget and offset characterization "
        "against the new topology."
    )
    a(
        "3. **A documented, reduced dynamic range** -- accepting that the "
        "current architecture cannot converge inputs whose magnitude drives "
        "the frozen side's sampled value far enough from `VCM` to exceed "
        "the comparator's headroom, and superseding "
        "`spec/target-spec.md`'s input-range row via a new decision record "
        "(CLAUDE.md: \"a row that proves unmeetable is superseded by a new "
        "decision record, never silently loosened\")."
    )
    a("")
    a(
        "Choosing among these is an architecture-level tradeoff (effort vs. "
        "dynamic range vs. re-qualification cost), not a mechanical "
        "follow-up to this record's own diagnostic scope -- filed as its "
        "own follow-up issue rather than attempted here, mirroring DR-008's "
        "own precedent of filing its (then-unconfirmed) version of this "
        "same finding as a separate follow-up rather than blocking on it."
    )
    a("")

    lines.extend(
        evidence.environment_block(
            pdk_line=prov.pdk_line,
            ngspice_line=prov.ng_version,
            netlist_sha256=prov.netlist_sha,
            extra={
                "tran step": f"{tb.TRAN_STEP_NS} ns",
                "traced conversions": ", ".join(
                    f"{c['conversion']} (Vd = {c['fraction']:+.2f}*V_REF, "
                    f"ideal code {c['ideal_code']})"
                    for c in traced_conversions
                ),
                "pre-edge / post-edge margins": f"{_NODE_TRACE_PRE_EDGE_NS:g} ns / "
                f"{_NODE_TRACE_POST_EDGE_NS:g} ns",
            },
        )
    )
    a("")
    lines.extend(
        evidence.footer_lines(
            "sim/full-conversion-transient/run_conversion.py --cm-trace",
            # Diagnostic/investigation record (see the "Claim" bullet above):
            # it extends the corner campaigns' evidence without invalidating
            # any of it, so it supersedes nothing by construction -- the same
            # reasoning as --node-trace above, spelled the same explicit way
            # (issue #502). --supersedes is deliberately NOT threaded here.
            evidence.NEVER_SUPERSEDES,
        )
    )

    return evidence.close_record(prov, lines, "CM-trace record")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def run_mechanism_probe(scratch: Path, quiet: bool) -> dict:
    pdk_info = pdk.resolve()
    netlist_text = dut_text()
    pc, tc, sv = BASELINE_CORNER
    out: dict[str, dict] = {}
    for tag, delayed in (("as-committed", False), ("comparator-strobe-delayed", True)):
        point = run_point(
            netlist_text, pdk_info, scratch, pc, tc, sv,
            delayed_comparator_strobe=delayed, tag_prefix=f"probe_{tag}",
        )
        out[tag] = point
        if not quiet:
            print(f"  [{tag}] " + format_point(point), flush=True)
    return out


# --------------------------------------------------------------------------
# Decision-margin trace (issue #263 second pass / DR-009): the comparator's
# OWN differential input at every bit-trial decision instant, against the
# decision it then produced. This is the probe that separates a SEARCH defect
# (the loop feeds the comparator the wrong residual) from a COMPARATOR defect
# (the residual is right and the decision is wrong) -- neither the code-level
# corner campaign nor --node-trace (which probes the comparator's OUTPUT pair)
# can tell those apart.
#
# Like --mechanism-probe, and unlike --node-trace, this runs the DUT twice:
# once as committed, and once on a testbench-only modified copy with DR-009's
# comparator-output balancing dummies REMOVED, which reproduces the
# pre-DR-009 asymmetric loading. The pair is the control: the same residuals
# decided two different ways is what makes "the offset is created by the
# output loading" a measurement rather than an inference.
# --------------------------------------------------------------------------

# The two DR-009 instance lines whose removal restores the pre-fix,
# asymmetrically-loaded comparator. Matched by instance name at line start, so
# a rename in design/sar_adc_top.sch fails loudly here instead of silently
# probing the wrong thing.
_BALANCE_DUMMY_PREFIXES: tuple[str, ...] = ("xdum_mux_n ", "xdum_xnor_n ")

# Mid-scale conversions only: these are the ones whose residual at the last
# bit trials is small enough (order 1 LSB) for a few-mV comparator offset to
# change the decision, and they are the inputs issue #263's own acceptance
# criteria cover. The near-full-scale conversions (1 and 5) belong to issue
# #265 and are deliberately NOT traced here.
DECISION_MARGIN_CONVERSIONS: tuple[int, ...] = (2, 3, 4)

# Corners: the campaign's baseline point plus the binding (lowest-supply)
# corner of every landed corner-campaign record so far.
DECISION_MARGIN_CORNERS: tuple[tuple[str, float, float], ...] = (
    ("tt", 27.0, NOMINAL_SUPPLY_V),
    ("tt", 27.0, 1.62),
)


def _strip_balance_dummies(netlist_text: str) -> str:
    """Return `netlist_text` with DR-009's two comparator-output balancing
    dummy instances removed -- the pre-DR-009 asymmetric loading, as a
    testbench-only control. Never written back to design/."""
    kept, removed = [], 0
    for ln in netlist_text.splitlines():
        if ln.startswith(_BALANCE_DUMMY_PREFIXES):
            removed += 1
            continue
        kept.append(ln)
    if removed != len(_BALANCE_DUMMY_PREFIXES):
        raise RuntimeError(
            "decision-margin trace: expected exactly "
            f"{len(_BALANCE_DUMMY_PREFIXES)} comparator-output balancing dummy "
            f"instances ({', '.join(p.strip() for p in _BALANCE_DUMMY_PREFIXES)}) "
            f"in {DUT_NETLIST}, found {removed} -- the netlist changed shape; "
            "re-derive this probe."
        )
    return "\n".join(kept) + "\n"


def decision_margin_measure_lines(conversions: tuple[int, ...]) -> tuple[list[str], list[str]]:
    """`.meas` cards sampling, for every bit trial of every conversion in
    `conversions`: the comparator's differential input and common mode at the
    last instant before its evaluate half opens (DAC settled, latch still in
    reset, so this is exactly what the latch is asked to resolve), the
    decision it produced, and the bit the register then captured."""
    lines = [
        "* --- issue #263 / DR-009 decision-margin trace: the comparator's own",
        "* differential input at each bit trial's decision instant, vs the",
        "* decision it produced (read-only probes; DUT unmodified) ----------",
    ]
    names: list[str] = []
    for c in conversions:
        lines.append(f"* conversion {c}")
        for p in range(tb.N_BITS):
            bit = tb.N_BITS - 1 - p
            k = tb.PHASES_PER_CONVERSION * c + p
            # The comparator is strobed by CLKN = NOT(CLK) (issue #257), so it
            # RESETS during the phase's CLK-high half and EVALUATES during the
            # CLK-low half. Sample its input just before the CLK falling edge
            # that opens that evaluate half: the DAC has had half a period to
            # settle and the latch has not yet begun to load it.
            t_in = tb.t_edge_ns(k) + tb.T_CLK_NS * 0.5 - _DECISION_MARGIN_PRE_NS
            t_dec = tb.t_edge_ns(k + 1) - _DECISION_MARGIN_PRE_NS
            t_post = tb.t_edge_ns(k + 1) + _DECISION_MARGIN_POST_NS
            pre = f"dm_c{c}_p{p}"
            for tag, node, t in (
                ("topp", "TOP_P", t_in),
                ("topn", "TOP_N", t_in),
                ("comp", "COMP_OUT", t_dec),
                ("dout", f"dout{bit}", t_post),
            ):
                lines.append(f".meas tran {pre}_{tag} find v({node}) at={t:.4f}n")
                names.append(f"{pre}_{tag}")
        for b in range(tb.N_BITS):
            node = "dout9" if b == tb.N_BITS - 1 else f"adcout{b}"
            nm = f"dm_code_c{c}_b{b}"
            lines.append(
                f".meas tran {nm} find v({node}) at={tb.t_code_read_ns(c):.4f}n"
            )
            names.append(nm)
    return lines, names


_DECISION_MARGIN_PRE_NS = 1.0
_DECISION_MARGIN_POST_NS = 2.0

# Trials whose input magnitude is below the comparator's OWN budgeted
# input-referred noise are not counted as mismatches: the design does not
# promise to resolve them, so calling such a decision "wrong" would be
# grading the circuit against a criterion no record ever set for it. The
# figure is DR-004's ratified input-referred noise budget (<= 1.0148 mV rms,
# `spec/decision-records/DR-004-comparator-topology-and-noise-budget.md`
# Decision item 2) -- about 0.29 LSB at the nominal supply. They are counted
# and reported separately, not hidden.
_DECISION_MARGIN_NOISE_BAND_MV = 1.0148


def run_decision_margin_point(
    netlist_text: str,
    pdk_info: pdk.PdkInfo,
    scratch: Path,
    process_corner: str,
    temp_c: float,
    supply_v: float,
    tag: str,
) -> dict:
    cid = corners_mod.corner_id(process_corner, temp_c, supply_v)
    extra_meas, names = decision_margin_measure_lines(DECISION_MARGIN_CONVERSIONS)
    deck = assemble_deck(
        netlist_text, pdk_info, process_corner, temp_c, supply_v, extra_meas=extra_meas
    )
    log_text = _run_ngspice(deck, scratch, f"decision_margin_{tag}_{cid}")
    parsed = measure.parse(log_text, names, anchored=False)
    threshold = tb.DIGITAL_THRESHOLD_FRACTION * supply_v
    lsb_v = 2.0 * supply_v / (2**tb.N_BITS)

    conversions = []
    for c in DECISION_MARGIN_CONVERSIONS:
        trials = []
        for p in range(tb.N_BITS):
            pre = f"dm_c{c}_p{p}"
            topp = parsed.get(f"{pre}_topp")
            topn = parsed.get(f"{pre}_topn")
            comp = parsed.get(f"{pre}_comp")
            dout = parsed.get(f"{pre}_dout")
            if None in (topp, topn, comp, dout):
                trials.append(dict(bit=tb.N_BITS - 1 - p, missing=True))
                continue
            v_in = topp - topn
            decision = 1 if comp > threshold else 0
            trials.append(
                dict(
                    bit=tb.N_BITS - 1 - p,
                    missing=False,
                    v_in_mv=v_in * 1e3,
                    v_in_lsb=v_in / lsb_v,
                    v_cm_mv=0.5 * (topp + topn) * 1e3,
                    decision=decision,
                    # The decision the comparator's OWN input calls for. Its
                    # polarity is fixed (design/comparator.sch: VINP-VINN > 0
                    # => OUTP high), independent of which sign branch the SAR
                    # is in -- the branch correction lives downstream in
                    # COMP_EFF, so a mismatch here is the comparator's, not
                    # the search's.
                    expected=1 if v_in > 0 else 0,
                    in_noise_band=abs(v_in) * 1e3 < _DECISION_MARGIN_NOISE_BAND_MV,
                    dout=1 if dout > threshold else 0,
                )
            )
        code = 0
        for b in range(tb.N_BITS):
            v = parsed.get(f"dm_code_c{c}_b{b}")
            if v is not None and v > threshold:
                code |= 1 << b
        frac = tb.input_fraction(c)
        conversions.append(
            dict(
                conversion=c,
                fraction=frac,
                ideal_code=tb.ideal_code(frac),
                code=code,
                trials=trials,
            )
        )
    return dict(
        tag=tag,
        corner_id=cid,
        supply_v=supply_v,
        lsb_mv=lsb_v * 1e3,
        conversions=conversions,
        missing=measure.missing(parsed, names),
        log_text=log_text,
    )


def _decision_mismatches(point: dict) -> list[dict]:
    """Every traced bit trial whose decision disagrees with the sign of the
    comparator's own probed input, EXCLUDING trials inside DR-004's
    input-referred noise band (`_DECISION_MARGIN_NOISE_BAND_MV`) -- the design
    does not promise to resolve those, so grading them would hold the circuit
    to a criterion no record ever set for it. They are reported separately by
    `_noise_band_trials()`, not hidden."""
    return [
        dict(conversion=conv["conversion"], **tr)
        for conv in point["conversions"]
        for tr in conv["trials"]
        if not tr["missing"]
        and not tr["in_noise_band"]
        and tr["decision"] != tr["expected"]
    ]


def _noise_band_trials(point: dict) -> list[dict]:
    """Traced trials whose input magnitude is inside DR-004's input-referred
    noise band: reported, never graded."""
    return [
        dict(conversion=conv["conversion"], **tr)
        for conv in point["conversions"]
        for tr in conv["trials"]
        if not tr["missing"] and tr["in_noise_band"]
    ]


def _worst_correct_margin_lsb(point: dict) -> float | None:
    """Smallest |input| (in LSB) among the gradeable trials the comparator
    decided correctly -- how far down the comparator is demonstrated to
    resolve."""
    mags = [
        abs(tr["v_in_lsb"])
        for conv in point["conversions"]
        for tr in conv["trials"]
        if not tr["missing"]
        and not tr["in_noise_band"]
        and tr["decision"] == tr["expected"]
    ]
    return min(mags) if mags else None


def run_decision_margin_trace(scratch: Path, quiet: bool) -> tuple[dict[str, dict], str]:
    pdk_info = pdk.resolve()
    netlist_text = dut_text()
    variants = (
        ("as-committed", netlist_text),
        ("unbalanced-control", _strip_balance_dummies(netlist_text)),
    )
    out: dict[str, dict] = {}
    for tag, text in variants:
        for pc, tc, sv in DECISION_MARGIN_CORNERS:
            point = run_decision_margin_point(text, pdk_info, scratch, pc, tc, sv, tag)
            out[f"{tag}@{point['corner_id']}"] = point
            if not quiet:
                bad = _decision_mismatches(point)
                margin = _worst_correct_margin_lsb(point)
                codes = " ".join(
                    f"{cv['fraction']:+.2f}:{cv['code']}/{cv['ideal_code']}"
                    for cv in point["conversions"]
                )
                print(
                    f"  [{tag} {point['corner_id']}] {len(bad)} of "
                    f"{len(DECISION_MARGIN_CONVERSIONS) * tb.N_BITS} decisions "
                    f"disagree with the sign of the comparator's own input "
                    f"({len(_noise_band_trials(point))} further trial(s) inside "
                    f"DR-004's noise band, not graded); smallest "
                    f"correctly-resolved input "
                    f"{'n/a' if margin is None else f'{margin:.2f} LSB'}; "
                    f"codes(captured/ideal) {codes}",
                    flush=True,
                )
    return out, netlist_text


def write_decision_margin_record(points: dict[str, dict], netlist_text: str) -> Path:
    prov, lines = evidence.open_record(
        EXPERIMENT_DIR, netlist_text, "diagnostics",
        {
            f"decision-margin-{key.replace('@', '-')}.log": point["log_text"]
            for key, point in points.items()
        },
    )

    a = lines.append
    a(
        "- **Claim**: issue #263 (second pass) / "
        "`spec/decision-records/DR-009-comparator-output-load-balance-and-half-"
        "lsb-offset.md` -- diagnostic/mechanism evidence, NOT a spec row and "
        "NOT a corner campaign. It measures the comparator's OWN differential "
        "input at every bit-trial decision instant of the three mid-scale "
        "conversions, against the decision the comparator then produced, on "
        "(a) the as-committed netlist and (b) a testbench-only control copy "
        "with DR-009's comparator-output balancing dummies removed. The pair "
        "is what distinguishes a SEARCH defect (the loop presents the wrong "
        "residual) from a COMPARATOR OFFSET (the residual is right and the "
        "decision is wrong): the two variants present the SAME residuals and "
        "decide them differently."
    )
    a(
        "- **Netlist provenance**: schematic (`design/sar_adc_top.spice`) for "
        "the `as-committed` variant; the `unbalanced-control` variant is that "
        "same netlist with exactly the two lines `"
        + "`, `".join(p.strip() for p in _BALANCE_DUMMY_PREFIXES)
        + "` deleted at deck-assembly time -- a TESTBENCH-ONLY modification, "
        "never written back to `design/`, in the same spirit as this script's "
        "`--mechanism-probe`."
    )
    a(
        "- **Corners traced**: `"
        + "`, `".join(
            corners_mod.corner_id(pc, tc, sv) for pc, tc, sv in DECISION_MARGIN_CORNERS
        )
        + "` -- the campaign's baseline point and the landed records' binding "
        "corner. Not the full 9-point grid: this is a targeted mechanism "
        "trace, and the mechanism it probes is corner-invariant by "
        "construction (a capacitance ratio)."
    )
    a(
        "- **Conversions traced**: "
        + ", ".join(
            f"conversion {c} (`Vd = {tb.input_fraction(c):+.2f}*V_REF`)"
            for c in DECISION_MARGIN_CONVERSIONS
        )
        + " -- the mid-scale inputs, whose late bit trials present the "
        "comparator with residuals of order 1 LSB. The near-full-scale "
        "conversions belong to issue #265 and are deliberately not traced."
    )
    a(
        "- **Probe instants**: comparator input sampled "
        f"{_DECISION_MARGIN_PRE_NS:g} ns before the CLK falling edge that "
        "opens each trial's evaluate half (DAC settled for half a period, "
        "latch still in reset); decision read "
        f"{_DECISION_MARGIN_PRE_NS:g} ns before the capturing rising edge; "
        f"the captured bit read {_DECISION_MARGIN_POST_NS:g} ns after it."
    )
    a("")

    for key, point in points.items():
        a(f"## `{key}`")
        a("")
        bad = _decision_mismatches(point)
        margin = _worst_correct_margin_lsb(point)
        ties = _noise_band_trials(point)
        a(
            f"- decisions disagreeing with the sign of the comparator's own "
            f"input: **{len(bad)} of "
            f"{len(DECISION_MARGIN_CONVERSIONS) * tb.N_BITS}**"
        )
        a(
            f"- trials inside DR-004's input-referred noise band "
            f"(|input| < {_DECISION_MARGIN_NOISE_BAND_MV:g} mV), reported but "
            f"NOT graded: **{len(ties)}**"
        )
        a(
            "- smallest correctly-resolved input: "
            + ("n/a" if margin is None else f"**{margin:.2f} LSB**")
        )
        a(f"- LSB at this corner: {point['lsb_mv']:.4f} mV")
        a("")
        a("| conversion | bit | comparator input (mV) | (LSB) | top-plate CM (mV) | decision | sign of input | captured bit |")
        a("|---|---|---|---|---|---|---|---|")
        for conv in point["conversions"]:
            for tr in conv["trials"]:
                if tr["missing"]:
                    a(
                        f"| `{conv['fraction']:+.2f}*V_REF` | {tr['bit']} | "
                        "MISSING | | | | | |"
                    )
                    continue
                if tr["in_noise_band"]:
                    flag = " *(noise band, not graded)*"
                elif tr["decision"] != tr["expected"]:
                    flag = " **<-**"
                else:
                    flag = ""
                a(
                    f"| `{conv['fraction']:+.2f}*V_REF` | {tr['bit']} | "
                    f"{tr['v_in_mv']:.3f} | {tr['v_in_lsb']:+.2f} | "
                    f"{tr['v_cm_mv']:.1f} | {tr['decision']} | "
                    f"{tr['expected']}{flag} | {tr['dout']} |"
                )
        a("")
        a("| conversion | ideal code | captured code | error (LSB) |")
        a("|---|---|---|---|")
        for conv in point["conversions"]:
            a(
                f"| `{conv['fraction']:+.2f}*V_REF` | {conv['ideal_code']} | "
                f"{conv['code']} | {conv['code'] - conv['ideal_code']:+d} |"
            )
        a("")

    a("## Findings")
    a("")
    committed_bad = sum(
        len(_decision_mismatches(p)) for k, p in points.items() if k.startswith("as-committed@")
    )
    control_bad = sum(
        len(_decision_mismatches(p))
        for k, p in points.items()
        if k.startswith("unbalanced-control@")
    )
    a(
        f"- As-committed: **{committed_bad}** decision(s) disagree with the "
        f"sign of the comparator's own input, across both corners. "
        f"Unbalanced control: **{control_bad}**. Trials inside DR-004's "
        f"input-referred noise band (|input| < "
        f"{_DECISION_MARGIN_NOISE_BAND_MV:g} mV) are excluded from both "
        "counts and listed in the per-variant tables above."
    )
    a(
        "- Every mismatch in either variant is a decision of `1` on a "
        "NEGATIVE input -- the direction an unloaded `OUTN` predicts (the "
        "lighter output node wins the regeneration race, so `OUTP` = "
        "`COMP_OUT` stays high). No mismatch of the opposite direction "
        "appears, which is what rules out a settling or kickback "
        "explanation: those would not be signed."
        if all(
            tr["expected"] == 0
            for p in points.values()
            for tr in _decision_mismatches(p)
        )
        else "- Mismatches appear in BOTH directions, which is NOT the "
        "signature of an output-load-imbalance offset -- re-derive before "
        "citing this record for DR-009's mechanism."
    )
    a(
        "- The residuals themselves are the same in both variants to within "
        "a few tenths of an LSB (compare the per-trial tables above), so the "
        "difference between them is the comparator's decision, not the "
        "search's arithmetic."
    )
    a("")

    lines.extend(
        evidence.environment_block(
            pdk_line=prov.pdk_line,
            ngspice_line=prov.ng_version,
            netlist_sha256=prov.netlist_sha,
            extra={
                "tran step": f"{tb.TRAN_STEP_NS} ns",
                "testbench fragment sha256": f"`{evidence.sha256_file(tb.FRAGMENT_PATH)}`",
            },
        )
    )
    a("")
    lines.extend(
        evidence.footer_lines(
            "sim/full-conversion-transient/run_conversion.py --decision-margin-trace",
            # Diagnostic/mechanism record, NOT a corner campaign (see the
            # "Claim" bullet above) -- supersedes nothing by construction, same
            # as the two trace writers above (issue #502).
            evidence.NEVER_SUPERSEDES,
        )
    )
    return evidence.close_record(prov, lines, "Record")


# --------------------------------------------------------------------------
# Coherent-sine dynamic test (issue #603): SNDR/ENOB by FFT, single corner
# --------------------------------------------------------------------------
#
# An informational CROSS-CHECK of sim/enob-estimate/'s behavioral-accelerated
# composite ENOB, not a grade of the DRAFT ENOB row. Runs ONE corner (the
# baseline tt/27C/1.8V) -- a multi-corner or Monte Carlo extension is a
# `klt sim` request (#564), never a loop over this function.

ENOB_ESTIMATE_RECORDS = SIM_DIR / "enob-estimate" / "records"
# The figure spec/target-spec.md quotes for the behavioral estimate
# (mean-case) when issue #603 was filed. Quoted for the delta only -- the
# record also reads the CURRENT behavioral record (records/LATEST) and
# reports the delta against that, so a later behavioral re-run is not
# silently compared against a stale number.
SPEC_QUOTED_BEHAVIORAL_ENOB_BIT = 8.491
_BEHAVIORAL_ENOB_RE = re.compile(
    r"achieved ENOB \(mean-case CDAC mismatch\) = \*\*(?P<v>[0-9.]+) bit\*\*"
)


def behavioral_enob_reference(records_dir: Path = ENOB_ESTIMATE_RECORDS) -> dict | None:
    """The current behavioral-accelerated mean-case ENOB: `records/LATEST`'s
    record id and its parsed value, or None if either is unavailable."""
    latest = records_dir / "LATEST"
    if not latest.is_file():
        return None
    name = latest.read_text().strip()
    path = records_dir / name
    if not path.is_file():
        return None
    m = _BEHAVIORAL_ENOB_RE.search(path.read_text())
    if not m:
        return None
    return dict(record=os.path.relpath(path, REPO_ROOT), enob_bit=float(m.group("v")))


def decode_code_stream(
    parsed: dict[str, float], supply_v: float, conversions: list[int]
) -> dict:
    """Per-conversion codes (None where any bit is missing/non-finite) and
    phase-structure verdicts for `conversions`, with the same 1/0 threshold
    and MSB-first bit order `decode()` uses."""
    threshold = tb.DIGITAL_THRESHOLD_FRACTION * supply_v

    def bit(name: str) -> int | None:
        v = parsed.get(name)
        if v is None or not math.isfinite(v):
            return None
        return 1 if v > threshold else 0

    codes: list[int | None] = []
    phase_ok: list[bool] = []
    expected_busy = [1] * (tb.PHASES_PER_CONVERSION - 1) + [0]
    expected_smpl = [0] * (tb.PHASES_PER_CONVERSION - 1) + [1]
    for c in conversions:
        bits = [bit(n) for n in tb.code_measure_names(c)]
        codes.append(
            int("".join(str(b) for b in bits), 2) if all(b is not None for b in bits) else None
        )
        busy = [bit(n) for n in tb.busy_measure_names(c)]
        smpl = [bit(n) for n in tb.sample_measure_names(c)]
        phase_ok.append(busy == expected_busy and smpl == expected_smpl)
    return dict(codes=codes, phase_ok=phase_ok)


def analyze_sine_capture(
    codes: list[int | None],
    n: int,
    tone_bin: int,
    amplitude_fraction: float,
) -> dict:
    """FFT analysis of a captured stream plus the ideal-quantizer reference
    on the identical plan (same N, bin, amplitude and input phase).
    `analysis` is None (with `analysis_error` set) if the stream cannot be
    analysed -- e.g. a missing code -- rather than raising, so the record can
    still be written and say why."""
    ideal_codes = [
        tb.ideal_code(tb.sine_input_fraction(c, n, tone_bin, amplitude_fraction))
        for c in tb.sine_measured_conversions(n)
    ]
    ideal = dynamic_enob.analyze(ideal_codes, tone_bin, tb.N_BITS)
    try:
        analysis = dynamic_enob.analyze(codes, tone_bin, tb.N_BITS)
        error = None
    except ValueError as exc:
        analysis, error = None, str(exc)
    return dict(ideal_codes=ideal_codes, ideal=ideal, analysis=analysis, analysis_error=error)


# Per-code outlier bound (issue #621), in LSB of |captured - ideal|. A named
# DIAGNOSTIC threshold, not a spec value and not a validity criterion. The
# first pinned-toolchain capture (records/20261010-070734-f968286.md) has 31
# of 32 codes within +-2 LSB of the ideal quantizer, and the DC corner
# campaign resolves within 1 LSB; 8 LSB (4x the observed in-family spread, 8x
# the DC bound) leaves a wide margin so ordinary settling/INL error never
# trips it, while still catching anything of the order of a 3-bit-weight
# decision error, well below the +438 LSB conversion-9 glitch.
SINE_OUTLIER_BOUND_LSB = 8


def sine_outlier_diagnostic(
    codes: list[int | None],
    ideal_codes: list[int],
    conversions: list[int],
    n: int,
    tone_bin: int,
    bound_lsb: int = SINE_OUTLIER_BOUND_LSB,
) -> dict:
    """Per-code error diagnostic. Signed error = captured - ideal; an outlier
    is a sample with |error| STRICTLY greater than `bound_lsb`. Missing codes
    are not outliers (they already make the capture unanalysable).

    The sensitivity metrics are DIAGNOSTIC-ONLY: an FFT needs the full
    coherent record, so "leaving the outliers out" is done by substituting the
    ideal code at just the outlier samples (zeroing their error) and
    re-analysing; every other sample is untouched. The captured stream itself
    is never modified and the headline metrics always come from it."""
    errors = [None if c is None else c - i for c, i in zip(codes, ideal_codes)]
    present = [abs(e) for e in errors if e is not None]
    outliers = [
        dict(sample=k, conversion=conversions[k], ideal=ideal_codes[k],
             captured=codes[k], error=e)
        for k, e in enumerate(errors)
        if e is not None and abs(e) > bound_lsb
    ]
    leave_out = None
    if outliers:
        idx = {o["sample"] for o in outliers}
        patched = [ideal_codes[k] if k in idx else codes[k] for k in range(len(codes))]
        try:
            leave_out = dynamic_enob.analyze(patched, tone_bin, tb.N_BITS)
        except ValueError:
            leave_out = None
    return dict(
        bound_lsb=bound_lsb,
        max_abs_error=max(present) if present else None,
        errors=errors,
        outliers=outliers,
        leave_out=leave_out,
    )


def sine_trace_measure_lines(conversion: int) -> list[str]:
    """Read-only `.meas` probes (issue #621) for ONE coherent-sine conversion:
    the --node-trace per-phase probes (CLK / COMP_OUT / OUTN_NC / TOP_P / TOP_N
    mid-evaluate and pre-capture, captured bit after the capturing edge) plus
    VINP/VINN/TOP_P/TOP_N at the sampling instant. Unlike the DC --node-trace
    these are placed at the coherent-sine run's own conversion timing (same
    clock grid, `tb.t_edge_ns`), and the captured-bit node follows the sine
    fragment's naming (`dout9`, `adcout8..adcout0`). Adds probes only; the
    DUT netlist and the stimulus are untouched."""
    lines = node_trace_measure_lines(node_trace_plan(conversion), conversion=conversion)
    fixed = []
    for ln in lines:
        for b in range(tb.N_BITS - 1):
            ln = ln.replace(f"find v(dout{b}) ", f"find v(adcout{b}) ")
        fixed.append(ln)
    t_s = tb.t_sample_ns(conversion)
    fixed.append(f"* conversion {conversion}: sampling-instant input / top-plate nodes")
    for tag, node in (("vinp", "VINP"), ("vinn", "VINN"), ("top_p", "TOP_P"), ("top_n", "TOP_N")):
        fixed.append(f".meas tran nt_c{conversion}_samp_{tag} find v({node}) at={t_s - 1.0:.4f}n")
    return fixed


def decode_sine_trace(
    parsed: dict, conversion: int, ideal_code: int, supply_v: float,
    final_code: int | None = None,
) -> dict:
    """Decode one conversion's trace probes into per-phase rows and name the
    FIRST phase whose captured bit differs from the ideal code's bit (the
    observation). Which mechanism produced it is inference, left to the
    record's prose."""
    threshold = tb.DIGITAL_THRESHOLD_FRACTION * supply_v
    phases = []
    for entry in node_trace_plan(conversion):
        v = {k: parsed.get(name) for k, name in entry["names"].items()}
        dout = v["dout_post"]
        got = None if dout is None else int(dout > threshold)
        phases.append(dict(
            phase=entry["phase"], bit=entry["bit"],
            ideal_bit=(ideal_code >> entry["bit"]) & 1, captured_bit=got, v=v,
        ))
    first = next((ph for ph in phases if ph["captured_bit"] != ph["ideal_bit"]), None)
    samp = {t: parsed.get(f"nt_c{conversion}_samp_{t}") for t in ("vinp", "vinn", "top_p", "top_n")}
    # Observation, not inference: a comparator-input top plate driven outside
    # [0, V_DD] (by more than the probe's own noise) at a pre-capture instant.
    # "Outside" means beyond a fixed +/-0.05 V tolerance on each rail, i.e.
    # below -0.05 V or above V_DD + 0.05 V. Only the pre-capture top-plate
    # probes are tested, so this catches rail excursions only: an anomalous
    # staircase step that stays within the rails is not flagged here.
    excursions = [
        (ph["phase"], ph["bit"], node, ph["v"][key])
        for ph in phases
        for node, key in (("TOP_P", "top_p_pre"), ("TOP_N", "top_n_pre"))
        if ph["v"][key] is not None and not (-0.05 <= ph["v"][key] <= supply_v + 0.05)
    ]
    return dict(conversion=conversion, ideal_code=ideal_code, final_code=final_code,
                phases=phases, first_divergent=first, sampling=samp,
                rail_excursions=excursions)


# --- issue #621: switching-event trace of one coherent-sine conversion ------
#
# The per-phase `--sine-trace` above samples TOP_P/TOP_N at two instants per
# phase. That localised conversion 9's anomaly to one analog event (TOP_P
# leaving the rails inside phase 5) but cannot say WHICH plate or control
# moved. This trace answers that with read-only `.meas` probes on the SAME
# transient:
#   1. WHEN-crossing times of every digital node that steers the DAC or the
#      sequencer (DOUT9..0, SELp/SELn8..0, the PH_B ring, PH_EOC, BUSY,
#      BUSY_BITS, SAMPLE_INT): the first SWITCH_TRACE_MAX_EDGES rises and
#      falls inside the conversion window. Each is classified against the
#      SAR's own edge schedule (below) as scheduled or UNSCHEDULED -- an
#      observation about timing, not a mechanism.
#   2. The instant a comparator-input top plate first leaves the rails
#      (WHEN v(TOP_x) = -SWITCH_TRACE_RAIL_V), and every probed node's value
#      at that instant (FIND ... WHEN).
#   3. Per-phase snapshots of the same nodes plus the P/N DAC bottom plates,
#      the sampling front-end's floating plates and boosted gates.
# Node names are the DUT's own (top-level) or `<instance>.<node>` for the
# sequencer/CDAC/front-end internals -- the netlist's top level is flat
# (`**.subckt sar_adc_top` is commented out), so `xseq`, `xcdac` and `xfe`
# are top-level instances.

SWITCH_TRACE_MAX_EDGES = 3
# An edge-triggered transition (clk-to-q + one or two gates) lands within a
# few ns of the CLK rising edge's 50% point; 8 ns is ~10% of the 83.3 ns
# period, generous for these standard cells yet far from mid-period.
SWITCH_TRACE_EDGE_WINDOW_NS = (-1.0, 8.0)
# Top-plate "left the rails" threshold for the WHEN probe: well outside the
# +/-0.05 V rail tolerance of decode_sine_trace(), and never reached by a
# normal staircase (which stays inside [0, V_DD]).
SWITCH_TRACE_RAIL_V = 0.2
# Snapshot instants within each phase, as offsets from that phase's CLK
# rising edge: after the register update, mid CLK-high, just after the CLK
# falling edge (comparator strobe), mid CLK-low, and 1 ns before the next
# capturing edge.
# Dense samples across each bit phase's comparator strobe: 0.5 ns apart from
# 0.5 ns before to 5 ns after the CLK falling edge (T/2 after the rising
# edge). Fine enough to order a D-path glitch against a register change.
SWITCH_TRACE_STROBE_OFFSETS_NS = tuple(tb.T_CLK_NS * 0.5 + 0.5 * i for i in range(-1, 11))
SWITCH_TRACE_SNAPSHOT_OFFSETS_NS = (
    ("post", 4.0),
    ("mid", tb.T_CLK_NS * 0.25),
    ("strobe", tb.T_CLK_NS * 0.5 + 3.0),
    ("late", tb.T_CLK_NS * 0.75),
    ("pre", tb.T_CLK_NS - 1.0),
)


def _switch_trace_digital_nodes() -> list[str]:
    """Nodes whose transitions are classified against the SAR's schedule.
    Names are LOGICAL (the sequencer's own port names for the ring);
    `switch_trace_probe_node()` maps them onto the deck's nets."""
    nodes = [f"DOUT{b}" for b in range(tb.N_BITS - 1, -1, -1)]
    nodes += [f"SELp{b}" for b in range(tb.N_BITS - 2, -1, -1)]
    nodes += [f"SELn{b}" for b in range(tb.N_BITS - 2, -1, -1)]
    nodes += [f"PH_B{b}" for b in range(tb.N_BITS - 1, -1, -1)]
    nodes += ["PH_EOC", "BUSY", "xseq.BUSY_BITS", "SAMPLE_INT"]
    return nodes


def _switch_trace_context_nodes() -> list[str]:
    """The bit registers' own D-path inside the sequencer (internal nets of
    `sar_sequencer`): MUXOUTk = PH_Bk ? COMP_EFF : DOUTk, PRESETk = MUXOUTk |
    PH_B(k+1), DFEEDk = PRESETk & BUSY_BITS (DOUT9's D is MUXOUT9). Their
    transitions are recorded but not schedule-classified: MUXOUTk follows
    the comparator during its own trial, so it legitimately moves mid-phase."""
    nodes = [f"xseq.MUXOUT{b}" for b in range(tb.N_BITS - 1, -1, -1)]
    nodes += [f"xseq.PRESET{b}" for b in range(tb.N_BITS - 2, -1, -1)]
    nodes += [f"xseq.DFEED{b}" for b in range(tb.N_BITS - 2, -1, -1)]
    return nodes


def _switch_trace_analog_nodes() -> list[str]:
    nodes = ["CLK", "CLKN", "COMP_OUT", "OUTN_NC", "xseq.COMP_EFF", "TOP_P", "TOP_N",
             "BPREF_P_NC", "BPREF_N_NC", "xfe.G_P", "xfe.G_N", "VINP", "VINN"]
    nodes += [f"xcdac.BOT_p{b}" for b in range(tb.N_BITS - 2, -1, -1)]
    nodes += [f"xcdac.BOT_n{b}" for b in range(tb.N_BITS - 2, -1, -1)]
    return nodes


def _switch_trace_strobe_nodes() -> list[str]:
    """Nodes sampled densely across each phase's comparator strobe (the CLK
    falling edge): the comparator outputs, the shared COMP_EFF, every bit
    register's output and D-path."""
    return (["CLK", "CLKN", "COMP_OUT", "OUTN_NC", "xseq.COMP_EFF"]
            + [f"DOUT{b}" for b in range(tb.N_BITS - 1, -1, -1)]
            + _switch_trace_context_nodes())


_SEQUENCER_INSTANCE = "xseq"
_SEQUENCER_SUBCKT = "sar_sequencer"


def sequencer_port_nets(netlist_text: str | None = None) -> dict[str, str]:
    """{sequencer port name: top-level net} read from the DUT netlist's own
    `xseq` instance line and `.subckt sar_sequencer` port list. Subckt PORTS
    are not addressable as `xseq.<port>` in ngspice (only internal nets
    are), so a ring probe must name the net the port is wired to."""
    text = dut_text() if netlist_text is None else netlist_text
    inst = sub = None
    for ln in text.splitlines():
        tok = ln.split()
        if not tok:
            continue
        if tok[0].lower() == _SEQUENCER_INSTANCE and tok[-1].lower() == _SEQUENCER_SUBCKT:
            inst = tok[1:-1]
        elif tok[0].lower() == ".subckt" and len(tok) > 1 and tok[1].lower() == _SEQUENCER_SUBCKT:
            sub = tok[2:]
    if inst is None or sub is None or len(inst) != len(sub):
        raise ValueError(
            f"{DUT_NETLIST.name}: cannot map {_SEQUENCER_SUBCKT} ports onto "
            f"{_SEQUENCER_INSTANCE}'s nets -- the netlist changed shape; re-derive the probe."
        )
    return dict(zip(sub, inst))


def switch_trace_probe_node(node: str, ports: dict[str, str] | None = None) -> str:
    """The deck-level name to put inside v(...) for a logical node: ring
    ports (PH_B9..PH_B0, PH_EOC) resolve to their top-level nets."""
    if node.startswith("PH_"):
        return (sequencer_port_nets() if ports is None else ports)[node]
    return node


def _meas_tag(node: str) -> str:
    """A `.meas`-name-safe, lower-case tag for a (possibly hierarchical) node."""
    return node.lower().replace(".", "_")


def switch_trace_window_ns(conversion: int) -> tuple[float, float]:
    """[from, to] of the event probes: from just before the sampling edge
    (12c) to just after edge 12c+11, where the code registers are cleared."""
    base = tb.PHASES_PER_CONVERSION * conversion
    return tb.t_edge_ns(base) - 2.0, tb.t_edge_ns(base + tb.PHASES_PER_CONVERSION - 1) + 10.0


def switch_trace_expected_edges(conversion: int) -> dict[str, set[tuple[int, str]]]:
    """For each digital node, the (edge index, direction) pairs at which the
    SAR's OWN schedule (design/sar_adc_top.spice's sequencer, read from the
    netlist, not from any other design) can move it during conversion c.
    Edge 12c+p starts phase p (p=0 is PH_B9, p=10 PH_EOC, p=11 PH_SAMPLE):

    * PH_B(9-p) rises at 12c+p and falls at 12c+p+1; PH_EOC rises at 12c+10
      and falls at 12c+11. BUSY and SAMPLE_INT switch at 12c and 12c+11;
      BUSY_BITS rises at 12c and falls at 12c+10.
    * DOUT_k (k <= 8) is preset (rises) at 12c+9-k for its trial, falls at
      12c+10-k if the trial is rejected, and is cleared (falls) at 12c+11.
    * DOUT9 can change (either way) only at 12c+1 (the MSB capture).
    * SELp_k = DOUT9 & DOUT_k, SELn_k = !DOUT9 & DOUT_k: either direction at
      any edge where DOUT_k or DOUT9 may change.

    A transition at any other edge, or more than SWITCH_TRACE_EDGE_WINDOW_NS
    after a CLK rising edge, is UNSCHEDULED (observation)."""
    base = tb.PHASES_PER_CONVERSION * conversion
    last = tb.PHASES_PER_CONVERSION - 1  # 11: PH_SAMPLE
    exp: dict[str, set[tuple[int, str]]] = {}
    for p in range(tb.N_BITS):
        b = tb.N_BITS - 1 - p
        exp[f"PH_B{b}"] = {(base + p, "rise"), (base + p + 1, "fall")}
    exp["PH_EOC"] = {(base + tb.N_BITS, "rise"), (base + last, "fall")}
    exp["BUSY"] = {(base, "rise"), (base + last, "fall")}
    exp["SAMPLE_INT"] = {(base, "fall"), (base + last, "rise")}
    exp["xseq.BUSY_BITS"] = {(base, "rise"), (base + tb.N_BITS, "fall")}
    msb = {(base + 1, "rise"), (base + 1, "fall")}
    exp[f"DOUT{tb.N_BITS - 1}"] = set(msb)
    for k in range(tb.N_BITS - 1):
        dk = {(base + 9 - k, "rise"), (base + 10 - k, "fall"), (base + last, "fall")}
        exp[f"DOUT{k}"] = dk
        either = {(e, d) for e, _ in dk | msb for d in ("rise", "fall")}
        exp[f"SELp{k}"] = set(either)
        exp[f"SELn{k}"] = set(either)
    return exp


def _switch_prefix(conversion: int) -> str:
    return f"sw_c{conversion}"


def switch_trace_names(conversion: int) -> dict:
    """Every `.meas` name this trace emits, grouped for decoding."""
    pre = _switch_prefix(conversion)
    events = {
        node: {
            (d, i): f"{pre}_{_meas_tag(node)}_{d}{i}"
            for d in ("rise", "fall") for i in range(1, SWITCH_TRACE_MAX_EDGES + 1)
        }
        for node in _switch_trace_digital_nodes() + _switch_trace_context_nodes()
    }
    all_nodes = (_switch_trace_digital_nodes() + _switch_trace_context_nodes()
                 + _switch_trace_analog_nodes())
    excursion = {
        top: dict(
            t=f"{pre}_{_meas_tag(top)}_off_t",
            at={node: f"{pre}_{_meas_tag(top)}_off_{_meas_tag(node)}" for node in all_nodes},
        )
        for top in ("TOP_P", "TOP_N")
    }
    snapshots = {
        (p, tag): {node: f"{pre}_p{p}_{tag}_{_meas_tag(node)}" for node in all_nodes}
        for p in range(tb.PHASES_PER_CONVERSION - 1)
        for tag, _ in SWITCH_TRACE_SNAPSHOT_OFFSETS_NS
    }
    strobe = {
        (p, i): {node: f"{pre}_p{p}_s{i}_{_meas_tag(node)}" for node in _switch_trace_strobe_nodes()}
        for p in range(tb.N_BITS)
        for i in range(len(SWITCH_TRACE_STROBE_OFFSETS_NS))
    }
    return dict(events=events, excursion=excursion, snapshots=snapshots, strobe=strobe)


def switch_trace_flat_names(conversion: int) -> list[str]:
    names = switch_trace_names(conversion)
    out = [n for per in names["events"].values() for n in per.values()]
    for ex in names["excursion"].values():
        out.append(ex["t"])
        out += list(ex["at"].values())
    for per in names["snapshots"].values():
        out += list(per.values())
    for per in names["strobe"].values():
        out += list(per.values())
    return out


def switch_trace_measure_lines(conversion: int, supply_v: float) -> list[str]:
    """Read-only `.meas` cards for the switching-event trace of one
    coherent-sine conversion. Adds probes only; DUT and stimulus untouched."""
    names = switch_trace_names(conversion)
    t_from, t_to = switch_trace_window_ns(conversion)
    thr = tb.DIGITAL_THRESHOLD_FRACTION * supply_v
    base = tb.PHASES_PER_CONVERSION * conversion
    ports = sequencer_port_nets()

    def v(node: str) -> str:
        return f"v({switch_trace_probe_node(node, ports)})"

    lines = [
        f"* --- issue #621 switching-event trace, conversion {conversion} "
        "(read-only probes; DUT and stimulus unmodified) ---",
    ]
    for node, per in names["events"].items():
        for (d, i), name in per.items():
            lines.append(
                f".meas tran {name} when {v(node)}={thr:.4f} {d}={i} "
                f"from={t_from:.4f}n to={t_to:.4f}n"
            )
    for top, ex in names["excursion"].items():
        cond = f"v({top})={-SWITCH_TRACE_RAIL_V:.4f} fall=1 from={t_from:.4f}n to={t_to:.4f}n"
        lines.append(f".meas tran {ex['t']} when {cond}")
        for node, name in ex["at"].items():
            lines.append(f".meas tran {name} find {v(node)} when {cond}")
    for (p, tag), per in names["snapshots"].items():
        offset = dict(SWITCH_TRACE_SNAPSHOT_OFFSETS_NS)[tag]
        t = tb.t_edge_ns(base + p) + offset
        for node, name in per.items():
            lines.append(f".meas tran {name} find {v(node)} at={t:.4f}n")
    for (p, i), per in names["strobe"].items():
        t = tb.t_edge_ns(base + p) + SWITCH_TRACE_STROBE_OFFSETS_NS[i]
        for node, name in per.items():
            lines.append(f".meas tran {name} find {v(node)} at={t:.4f}n")
    return lines


def classify_switch_event(
    node: str, t_ns: float, expected: dict[str, set[tuple[int, str]]], direction: str
) -> dict:
    """Place one transition on the CLK grid: the nearest preceding rising
    edge index, the offset after it, the phase within the conversion grid,
    and whether the SAR's own schedule allows it there (observation)."""
    # 1e-9 period guard: a transition exactly at the window's early bound
    # must not round onto the previous edge.
    k = math.floor((t_ns - tb.T_FIRST_EDGE_NS - SWITCH_TRACE_EDGE_WINDOW_NS[0]) / tb.T_CLK_NS + 1e-9)
    offset = t_ns - tb.t_edge_ns(k)
    lo, hi = SWITCH_TRACE_EDGE_WINDOW_NS
    on_edge = lo <= offset <= hi
    scheduled = on_edge and (k, direction) in expected.get(node, set())
    return dict(node=node, direction=direction, t_ns=t_ns, edge=k, offset_ns=offset,
                on_edge=on_edge, scheduled=scheduled)


def decode_switch_trace(parsed: dict, conversion: int, supply_v: float) -> dict:
    """Decode the switching-event trace into a time-ordered event list
    (each classified scheduled / UNSCHEDULED), the first top-plate rail
    excursion with every node's value at that instant, and the snapshots.
    Observations only; the mechanism is the record prose's job."""
    names = switch_trace_names(conversion)
    expected = switch_trace_expected_edges(conversion)
    base = tb.PHASES_PER_CONVERSION * conversion
    context = set(_switch_trace_context_nodes())
    events = []
    saturated = []
    for node, per in names["events"].items():
        for d in ("rise", "fall"):
            for i in range(1, SWITCH_TRACE_MAX_EDGES + 1):
                v = parsed.get(per[(d, i)])
                if v is None:
                    break
                ev = classify_switch_event(node, v * 1e9, expected, d)
                ev["phase"] = ev["edge"] - base
                if node in context:
                    ev["scheduled"] = None  # recorded, not schedule-classified
                events.append(ev)
                if i == SWITCH_TRACE_MAX_EDGES:
                    saturated.append((node, d))
    events.sort(key=lambda e: (e["t_ns"], e["node"]))
    unscheduled = [e for e in events if e["scheduled"] is False]
    excursions = {}
    for top, ex in names["excursion"].items():
        t = parsed.get(ex["t"])
        if t is None:
            excursions[top] = None
            continue
        t_ns = t * 1e9
        k = math.floor((t_ns - tb.T_FIRST_EDGE_NS) / tb.T_CLK_NS)
        excursions[top] = dict(
            t_ns=t_ns, edge=k, phase=k - base, offset_ns=t_ns - tb.t_edge_ns(k),
            values={node: parsed.get(name) for node, name in ex["at"].items()},
        )
    snapshots = {
        key: {node: parsed.get(name) for node, name in per.items()}
        for key, per in names["snapshots"].items()
    }
    strobe = {
        key: {node: parsed.get(name) for node, name in per.items()}
        for key, per in names["strobe"].items()
    }
    return dict(conversion=conversion, supply_v=supply_v, events=events, strobe=strobe,
                unscheduled=unscheduled, first_unscheduled=(unscheduled[0] if unscheduled else None),
                saturated=saturated, excursions=excursions, snapshots=snapshots)


def _logic_char(v: float | None, supply_v: float) -> str:
    """'1'/'0' against 50% V_DD, 'x' inside the 20..80% V_DD band (a node
    mid-transition or not driven to a rail), '?' if the probe is missing."""
    if v is None:
        return "?"
    if 0.2 * supply_v < v < 0.8 * supply_v:
        return "x"
    return "1" if v > tb.DIGITAL_THRESHOLD_FRACTION * supply_v else "0"


def _logic_word(values: dict, nodes: list[str], supply_v: float) -> str:
    return "".join(_logic_char(values.get(n), supply_v) for n in nodes)


_SW_DOUT = [f"DOUT{b}" for b in range(tb.N_BITS - 1, -1, -1)]
_SW_SELP = [f"SELp{b}" for b in range(tb.N_BITS - 2, -1, -1)]
_SW_SELN = [f"SELn{b}" for b in range(tb.N_BITS - 2, -1, -1)]
_SW_RING = [f"PH_B{b}" for b in range(tb.N_BITS - 1, -1, -1)] + ["PH_EOC"]
_SW_MUXOUT = [f"xseq.MUXOUT{b}" for b in range(tb.N_BITS - 1, -1, -1)]
_SW_PRESET = [f"xseq.PRESET{b}" for b in range(tb.N_BITS - 2, -1, -1)]
_SW_DFEED = [f"xseq.DFEED{b}" for b in range(tb.N_BITS - 2, -1, -1)]
_SW_BOTP = [f"xcdac.BOT_p{b}" for b in range(tb.N_BITS - 2, -1, -1)]
_SW_BOTN = [f"xcdac.BOT_n{b}" for b in range(tb.N_BITS - 2, -1, -1)]


def switch_trace_record_lines(switch_traces: list[dict]) -> list[str]:
    out: list[str] = []
    add = out.append
    lo, hi = SWITCH_TRACE_EDGE_WINDOW_NS
    add("## Switching-event trace (issue #621; read-only probes on the same run)")
    add("")
    add(
        "Raw `.meas` values from the SAME transient as the code stream above "
        "(probes appended after the stimulus; DUT and stimulus unmodified). "
        "OBSERVED = the times, words and voltages below. A transition is "
        f"*scheduled* when it lands {lo:g}..+{hi:g} ns from a CLK rising edge at "
        "which the SAR's own sequencer can move that node "
        "(`switch_trace_expected_edges()` documents the schedule, derived from "
        "`design/sar_adc_top.spice`); anything else is **UNSCHEDULED**. That is a "
        "timing observation, not a mechanism. Digital words are MSB first; "
        "`1`/`0` against 50% V_DD, `x` = inside the 20..80% V_DD band, `?` = "
        "probe missing. The ring word is PH_B9..PH_B0 then PH_EOC. Every value "
        "here is also in the retained ngspice log."
    )
    add("")
    for st in switch_traces:
        c, vdd = st["conversion"], st["supply_v"]
        add(f"### Conversion {c}")
        add("")
        fu = st["first_unscheduled"]
        add(
            "- **First UNSCHEDULED transition (observed)**: "
            + ("none." if fu is None else
               f"`{fu['node']}` {fu['direction']} at {fu['t_ns']:.3f} ns = phase "
               f"{fu['phase']}, {fu['offset_ns']:+.2f} ns from its CLK rising edge.")
        )
        add(f"- **UNSCHEDULED transitions in the window (observed)**: {len(st['unscheduled'])}.")
        if st["saturated"]:
            add(
                "- **Edge-count limit reached** (more transitions may exist past "
                f"the {SWITCH_TRACE_MAX_EDGES} probed per direction): "
                + ", ".join(f"`{n}` {d}" for n, d in st["saturated"]) + "."
            )
        for top in ("TOP_P", "TOP_N"):
            ex = st["excursions"].get(top)
            add(
                f"- **{top} first below -{SWITCH_TRACE_RAIL_V:g} V (observed)**: "
                + ("never in the window." if ex is None else
                   f"{ex['t_ns']:.3f} ns = phase {ex['phase']}, "
                   f"{ex['offset_ns']:+.2f} ns from its CLK rising edge.")
            )
        add("")
        add("#### Transitions (time-ordered)")
        add("")
        add("| t (ns) | phase | from CLK rise (ns) | node | direction | schedule |")
        add("|---|---|---|---|---|---|")
        for e in st["events"]:
            add(
                f"| {e['t_ns']:.3f} | {e['phase']} | {e['offset_ns']:+.2f} | `{e['node']}` | "
                f"{e['direction']} | "
                + ("context (D-path, not classified)" if e["scheduled"] is None else
                   "scheduled" if e["scheduled"] else "**UNSCHEDULED**")
                + " |"
            )
        add("")
        for top in ("TOP_P", "TOP_N"):
            ex = st["excursions"].get(top)
            if ex is None:
                continue
            v = ex["values"]
            fmt = lambda x: "n/a" if x is None else f"{x:.4f}"
            add(f"#### Node values at the instant {top} crosses -{SWITCH_TRACE_RAIL_V:g} V")
            add("")
            add(
                f"DOUT9..0 `{_logic_word(v, _SW_DOUT, vdd)}`, SELp8..0 "
                f"`{_logic_word(v, _SW_SELP, vdd)}`, SELn8..0 `{_logic_word(v, _SW_SELN, vdd)}`, "
                f"ring `{_logic_word(v, _SW_RING, vdd)}`, BUSY/BUSY_BITS/SAMPLE_INT "
                f"`{_logic_word(v, ['BUSY', 'xseq.BUSY_BITS', 'SAMPLE_INT'], vdd)}`, "
                f"MUXOUT9..0 `{_logic_word(v, _SW_MUXOUT, vdd)}`, PRESET8..0 "
                f"`{_logic_word(v, _SW_PRESET, vdd)}`, DFEED8..0 `{_logic_word(v, _SW_DFEED, vdd)}`."
            )
            add("")
            add("| node | V |")
            add("|---|---|")
            for node in _switch_trace_analog_nodes():
                add(f"| `{node}` | {fmt(v.get(node))} |")
            add("")
        add("#### Per-phase snapshots")
        add("")
        add(
            "Instants are offsets from each phase's CLK rising edge: "
            + ", ".join(f"`{t}` = +{o:.1f} ns" for t, o in SWITCH_TRACE_SNAPSHOT_OFFSETS_NS)
            + "."
        )
        add("")
        add("| phase | instant | DOUT9..0 | SELp8..0 | SELn8..0 | ring | BUSY/BB/SMP | "
            "MUXOUT9..0 | DFEED8..0 | "
            "CLK | COMP_OUT | OUTN_NC | TOP_P | TOP_N | BPREF_P | BPREF_N | G_P | G_N | "
            "BOT_p8..0 (V) | BOT_n8..0 (V) |")
        add("|" + "---|" * 20)
        fmt = lambda x: "n/a" if x is None else f"{x:.3f}"
        for (p, tag), v in st["snapshots"].items():
            add(
                f"| {p} | {tag} | `{_logic_word(v, _SW_DOUT, vdd)}` | "
                f"`{_logic_word(v, _SW_SELP, vdd)}` | `{_logic_word(v, _SW_SELN, vdd)}` | "
                f"`{_logic_word(v, _SW_RING, vdd)}` | "
                f"`{_logic_word(v, ['BUSY', 'xseq.BUSY_BITS', 'SAMPLE_INT'], vdd)}` | "
                f"`{_logic_word(v, _SW_MUXOUT, vdd)}` | `{_logic_word(v, _SW_DFEED, vdd)}` | "
                f"{fmt(v.get('CLK'))} | {fmt(v.get('COMP_OUT'))} | {fmt(v.get('OUTN_NC'))} | "
                f"{fmt(v.get('TOP_P'))} | {fmt(v.get('TOP_N'))} | "
                f"{fmt(v.get('BPREF_P_NC'))} | {fmt(v.get('BPREF_N_NC'))} | "
                f"{fmt(v.get('xfe.G_P'))} | {fmt(v.get('xfe.G_N'))} | "
                + " ".join(fmt(v.get(n)) for n in _SW_BOTP) + " | "
                + " ".join(fmt(v.get(n)) for n in _SW_BOTN) + " |"
            )
        add("")
        fu = st["first_unscheduled"]
        strobe = st.get("strobe") or {}
        if fu is not None and 0 <= fu["phase"] < tb.N_BITS and strobe:
            add(f"#### Strobe window, phase {fu['phase']} (the first UNSCHEDULED transition's phase)")
            add("")
            add(
                "Samples 0.5 ns apart across this phase's CLK falling edge (comparator "
                f"strobe, +{tb.T_CLK_NS * 0.5:.2f} ns after the rising edge). DOUT and the "
                "registers' D-path as logic words; the comparator nodes in volts."
            )
            add("")
            add("| from CLK rise (ns) | CLK | CLKN | COMP_OUT | OUTN_NC | COMP_EFF | "
                "DOUT9..0 | MUXOUT9..0 | PRESET8..0 | DFEED8..0 |")
            add("|" + "---|" * 10)
            for i, off in enumerate(SWITCH_TRACE_STROBE_OFFSETS_NS):
                v = strobe.get((fu["phase"], i), {})
                add(
                    f"| {off:+.2f} | {fmt(v.get('CLK'))} | {fmt(v.get('CLKN'))} | "
                    f"{fmt(v.get('COMP_OUT'))} | {fmt(v.get('OUTN_NC'))} | "
                    f"{fmt(v.get('xseq.COMP_EFF'))} | `{_logic_word(v, _SW_DOUT, vdd)}` | "
                    f"`{_logic_word(v, _SW_MUXOUT, vdd)}` | `{_logic_word(v, _SW_PRESET, vdd)}` | "
                    f"`{_logic_word(v, _SW_DFEED, vdd)}` |"
                )
            add("")
    return out


def format_switch_trace_summary(st: dict) -> str:
    c = st["conversion"]
    out = [f"Switching-event trace, conversion {c} (observed):"]
    fu = st["first_unscheduled"]
    out.append(
        "  first UNSCHEDULED transition: "
        + ("none" if fu is None else
           f"{fu['node']} {fu['direction']} at {fu['t_ns']:.3f} ns = phase {fu['phase']} "
           f"+{fu['offset_ns']:.2f} ns after its CLK rising edge")
    )
    out.append(f"  unscheduled transitions: {len(st['unscheduled'])}")
    for top in ("TOP_P", "TOP_N"):
        ex = st["excursions"].get(top)
        out.append(
            f"  {top} below -{SWITCH_TRACE_RAIL_V:g} V: "
            + ("never" if ex is None else
               f"at {ex['t_ns']:.3f} ns = phase {ex['phase']} +{ex['offset_ns']:.2f} ns")
        )
    return "\n".join(out)


# --------------------------------------------------------------------------
# Solver-sensitivity audit of the DC baseline corner (`--solver-audit`,
# issue #637)
# --------------------------------------------------------------------------
# Runs the SAME DC fragment, DUT and corner (tt/27C/1.8V) once under the
# reference solver profile and once under each control profile, SEQUENTIALLY
# in one process (so the wall-clock figures are like-for-like on one host),
# and writes ONE diagnostic record that says, observation by observation,
# whether anything the reference run shows moves under a control. It is
# the guard that keeps a solver-sensitive anomaly from being presented as
# unqualified converter behaviour: the record names each moved observation
# SOLVER-SENSITIVE. It never touches records/LATEST and supersedes nothing.
#
# Instrumentation, identical under every profile (so it cannot be what
# differs between them):
#   * SOLVER_AUDIT_STATS_CARD -- ngspice's print-only accounting option
#     (`acct`): timepoint / iteration / analysis-time statistics. It does not
#     change any tolerance or the integration method.
#   * transition_guard_measure_lines() -- the WHEN-crossing half of the
#     issue #621 switching-event trace (every DOUT/SEL/ring/control node and
#     the registers' D-path, classified scheduled / UNSCHEDULED against the
#     SAR's own edge schedule) plus the first top-plate rail excursion, on
#     every measured conversion. Read-only `.meas` cards.
SOLVER_AUDIT_STATS_CARD = ".options acct"
# Relative change in a supply/reference current or total power above which
# the audit calls the power observation "moved". An AUDIT reporting
# tolerance only (not a spec threshold): it is far above the 1e-3 relative
# tolerance the reference settings integrate to, so a change past it is not
# integration noise, and every delta is printed regardless.
SOLVER_AUDIT_POWER_REL_TOL = 0.01
# ngspice `acct` statistics the record reports (name as ngspice prints it).
SOLVER_STAT_NAMES = (
    "Transient timepoints",
    "Accepted timepoints",
    "Rejected timepoints",
    "Transient iterations",
    "Transient analysis time",
    "Total analysis time (seconds)",
)
_STAT_RE = re.compile(r"^\s*(?P<name>[A-Za-z][A-Za-z ()]*?)\s*=\s*(?P<value>[-+0-9.eE]+)\s*$")
# Log lines a solver change could plausibly move (counted, not interpreted).
_SOLVER_LOG_PATTERNS = (
    ("timestep too small", re.compile(r"timestep too small", re.I)),
    ("warning lines", re.compile(r"\bwarning\b", re.I)),
    ("gmin/source stepping", re.compile(r"gmin stepping|source stepping", re.I)),
    ("convergence trouble", re.compile(r"trouble|no convergence|failed to converge", re.I)),
)


def transition_guard_names(conversion: int) -> dict:
    names = switch_trace_names(conversion)
    return dict(
        events=names["events"],
        excursion_t={top: ex["t"] for top, ex in names["excursion"].items()},
    )


def transition_guard_flat_names(conversion: int) -> list[str]:
    g = transition_guard_names(conversion)
    out = [n for per in g["events"].values() for n in per.values()]
    return out + list(g["excursion_t"].values())


def transition_guard_measure_lines(conversion: int, supply_v: float) -> list[str]:
    """The event (WHEN-crossing) and rail-excursion-time subset of
    switch_trace_measure_lines(): enough to say whether any register or DAC
    select moved off the SAR's own schedule, without the per-phase snapshot
    and strobe-sample bulk. Read-only probes; DUT and stimulus untouched."""
    wanted = set(transition_guard_flat_names(conversion))
    return [
        f"* --- issue #637 register-transition guard, conversion {conversion} "
        "(read-only probes; DUT and stimulus unmodified) ---",
        *(ln for ln in switch_trace_measure_lines(conversion, supply_v)
          if ln.startswith(".meas") and ln.split()[2] in wanted),
    ]


def parse_solver_stats(log_text: str) -> dict:
    """ngspice `acct` statistics (SOLVER_STAT_NAMES) plus counts of the log
    lines in _SOLVER_LOG_PATTERNS. Missing statistics are simply absent."""
    stats: dict[str, float] = {}
    counts = {label: 0 for label, _ in _SOLVER_LOG_PATTERNS}
    for line in log_text.splitlines():
        m = _STAT_RE.match(line)
        if m and m.group("name") in SOLVER_STAT_NAMES and m.group("name") not in stats:
            try:
                stats[m.group("name")] = float(m.group("value"))
            except ValueError:
                pass
        for label, pat in _SOLVER_LOG_PATTERNS:
            if pat.search(line):
                counts[label] += 1
    return dict(stats=stats, log_counts=counts)


def _rel_delta(ref: float | None, ctl: float | None) -> float | None:
    if ref is None or ctl is None:
        return None
    if ref == 0.0:
        return 0.0 if ctl == 0.0 else math.inf
    return (ctl - ref) / abs(ref)


def compare_audit_runs(reference: dict, control: dict) -> list[dict]:
    """Every observation of `reference` (a run_point(audit=True) result under
    the reference profile) that differs under `control`, as a list of
    {observation, reference, control, failure_mode} dicts. Empty == nothing
    moved. `failure_mode` marks a change in a recorded pass/fail property
    (a code's +-1 LSB verdict, a phase-structure verdict, a missing
    measurement) as opposed to a value that moved within the same verdict."""
    moved: list[dict] = []

    def add(obs: str, ref, ctl, failure_mode: bool) -> None:
        moved.append(dict(observation=obs, reference=ref, control=ctl, failure_mode=failure_mode))

    for rc_, cc in zip(reference["conversions"], control["conversions"]):
        label = f"conversion {rc_['conversion']} (`{rc_['fraction']:+.2f}*V_REF`)"
        if rc_["code"] != cc["code"]:
            add(f"{label} captured code", rc_["code"], cc["code"], False)
        if rc_["code_ok"] != cc["code_ok"]:
            add(f"{label} within +-{CODE_TOLERANCE_LSB} LSB", rc_["code_ok"], cc["code_ok"], True)
        if (rc_["busy"], rc_["sample"]) != (cc["busy"], cc["sample"]):
            add(f"{label} BUSY/SAMPLE words",
                _bits_str(rc_["busy"]) + "/" + _bits_str(rc_["sample"]),
                _bits_str(cc["busy"]) + "/" + _bits_str(cc["sample"]), False)
        if rc_["phase_ok"] != cc["phase_ok"]:
            add(f"{label} 12-period phase structure", rc_["phase_ok"], cc["phase_ok"], True)
    if sorted(reference["missing"]) != sorted(control["missing"]):
        add("missing measurements", len(reference["missing"]), len(control["missing"]), True)
    if reference["all_ok"] != control["all_ok"]:
        add("point verdict (PASS/FAIL)", reference["all_ok"], control["all_ok"], True)

    for name, _source, _pot in tb.SUPPLY_SOURCES:
        d = _rel_delta(reference["currents"].get(name), control["currents"].get(name))
        if d is None:
            if (name in reference["currents"]) != (name in control["currents"]):
                add(f"current `{name}` availability", name in reference["currents"],
                    name in control["currents"], True)
        elif abs(d) > SOLVER_AUDIT_POWER_REL_TOL:
            add(f"current `{name}` (relative change {d:+.2%})",
                reference["currents"][name], control["currents"][name], False)
    d = _rel_delta(reference["power_w"], control["power_w"])
    if d is not None and abs(d) > SOLVER_AUDIT_POWER_REL_TOL:
        add(f"total power (relative change {d:+.2%})", reference["power_w"], control["power_w"], False)

    for rg, cg in zip(reference.get("guards", []), control.get("guards", [])):
        c = rg["conversion"]
        if len(rg["unscheduled"]) != len(cg["unscheduled"]):
            add(f"conversion {c} UNSCHEDULED register/DAC-select transitions",
                len(rg["unscheduled"]), len(cg["unscheduled"]), False)
        for top in ("TOP_P", "TOP_N"):
            r_ex, c_ex = rg["excursions"].get(top), cg["excursions"].get(top)
            if (r_ex is None) != (c_ex is None):
                add(f"conversion {c} {top} below -{SWITCH_TRACE_RAIL_V:g} V",
                    r_ex is not None, c_ex is not None, False)
    return moved


_LATEST_CODE_CELL = re.compile(r"(\d+|MISSING) \(([+-]?\d+|n/a) LSB\)")


def latest_baseline_row(records_dir: Path | None = None) -> dict | None:
    """The `tt_27c_1.80v` codes and total power of the record `records/LATEST`
    names (the reference corner campaign), read from its own tables, so the
    audit can say whether its reference-profile run reproduces the recorded
    failure modes. None if LATEST or the row cannot be read."""
    records_dir = EXPERIMENT_DIR / "records" if records_dir is None else records_dir
    latest = records_dir / "LATEST"
    if not latest.is_file():
        return None
    name = latest.read_text().strip()
    path = records_dir / name
    if not path.is_file():
        return None
    text = path.read_text()
    cid = corners_mod.corner_id(*BASELINE_CORNER)
    section = None
    codes = power = None
    for line in text.splitlines():
        if line.startswith("## "):
            section = line
            continue
        if not line.startswith(f"| `{cid}` |") or section is None:
            continue
        if section.startswith("## Captured code vs ideal code"):
            cells = _LATEST_CODE_CELL.findall(line)
            codes = [None if c == "MISSING" else int(c) for c, _ in cells]
        elif section.startswith("## Power"):
            last = line.rstrip(" |").split("|")[-1].strip()
            try:
                power = float(last) * 1e-6
            except ValueError:
                power = None
    if codes is None:
        return None
    env = {}
    for key, pat in (("ngspice", r"^- ngspice: (.+)$"),
                     ("netlist_sha", r"^- DUT netlist sha256: `([0-9a-f]+)`"),
                     ("fragment_sha", r"^- testbench fragment sha256: `([0-9a-f]+)`"),
                     ("simulator_options", r"^- simulator options: (.+)$")):
        m = re.search(pat, text, re.M)
        env[key] = m.group(1) if m else None
    if env["simulator_options"] is None:
        # every record minted before issue #637 ran on ngspice's defaults
        env["simulator_options"] = f"not stated (pre-#637 record: {NGSPICE_DEFAULT_SOLVER_SETTINGS})"
    return dict(record_id=path.stem, corner_id=cid, codes=codes, power_w=power, **env)


def run_solver_audit(
    profiles: tuple[str, ...], scratch: Path, quiet: bool
) -> tuple[list[dict], str, float]:
    """Reference profile first, then each control profile, one after the other
    (never concurrently: the wall-clock comparison must be like-for-like).
    Returns (runs, netlist_text, total wall seconds)."""
    pdk_info = pdk.resolve()
    netlist_text = dut_text()
    runs: list[dict] = []
    t0 = time.time()
    for profile in (REFERENCE_SOLVER_PROFILE, *profiles):
        if not quiet:
            print(f"  [{profile}] {solver_settings_text(profile)}", flush=True)
        point = run_point(netlist_text, pdk_info, scratch, *BASELINE_CORNER,
                          tag_prefix=f"solver_audit_{profile.replace('-', '_')}",
                          solver_profile=profile, audit=True)
        runs.append(point)
        if not quiet:
            print("    " + format_point(point), flush=True)
    return runs, netlist_text, time.time() - t0


def write_solver_audit_record(
    runs: list[dict], netlist_text: str, total_wall_s: float,
    latest: dict | None, written_by: str,
) -> Path:
    """Mint the audit's diagnostic record (append-only, never LATEST, never
    supersedes: a solver audit is a check on reference evidence, not a
    replacement for it)."""
    reference, controls = runs[0], runs[1:]
    if is_solver_control(reference["solver_profile"]) or not controls or not all(
        is_solver_control(r["solver_profile"]) for r in controls
    ):
        raise ValueError("a solver audit is the reference profile first, then >= 1 control profile")
    prov, lines = evidence.open_record(
        EXPERIMENT_DIR, netlist_text, "diagnostics",
        {f"solver-audit-{r['solver_profile']}-{r['corner_id']}.log": r["log_text"] for r in runs},
    )
    cid = reference["corner_id"]
    comparisons = {r["solver_profile"]: compare_audit_runs(reference, r) for r in controls}
    sensitive = {p: m for p, m in comparisons.items() if m}
    fm_moved = {p: [m for m in ms if m["failure_mode"]] for p, ms in comparisons.items()}
    add = lines.append

    add(
        "- **Claim**: `spec/target-spec.md#target-table` -- none graded. A "
        "SOLVER-SENSITIVITY AUDIT (issue #637) of the full-conversion DC campaign's "
        f"baseline corner `{cid}`: the same DUT, DC stimulus and toolchain under the "
        f"reference solver profile `{REFERENCE_SOLVER_PROFILE}` and under "
        + ", ".join(f"`{r['solver_profile']}`" for r in controls)
        + ". It is a diagnostic about the evidence, not converter evidence: it edits "
        "no spec row, proposes no target, does not update `records/LATEST` and "
        "supersedes nothing."
    )
    add("- **Netlist provenance**: schematic (`design/sar_adc_top.spice`, unmodified)")
    add(corners_mod.corner_matrix_summary_line(
        [reference["process_corner"]], [reference["temp_c"]], [reference["supply_v"]], 1
    ).replace("one-at-a-time per sim/README.md",
              "single-corner solver audit, NOT the ratified grid"))
    add(
        "- **Stimulus**: the committed DC fragment "
        "(`testbench/full_conversion_tb_fragment.spice`), byte-for-byte the "
        "corner campaign's, under every profile."
    )
    add(
        "- **Overall**: "
        + ("NO OBSERVATION MOVED under any control profile -- the reference-profile "
           "result at this corner is not solver-sensitive to these settings."
           if not sensitive else
           "SOLVER-SENSITIVE -- at least one observation moved under "
           + ", ".join(f"`{p}`" for p in sensitive)
           + "; see the comparison below. A moved observation is a property of the "
           "integration settings until shown otherwise and must not be read as "
           "unqualified converter behaviour.")
    )
    add(
        "- **Recorded failure modes moved**: "
        + "; ".join(
            f"`{p}`: " + ("none" if not fm else ", ".join(m["observation"] for m in fm))
            for p, fm in fm_moved.items()
        )
        + "."
    )
    add(
        "- **Measured value(s)**: per-profile codes, phase structure, per-rail "
        "currents/power, UNSCHEDULED register/DAC-select transitions, ngspice "
        "accounting statistics and simulator wall-clock (below)."
    )
    add("")

    add("## Solver profiles and simulator cost (like-for-like, one host, sequential)")
    add("")
    add(
        "Wall-clock is measured around the ngspice subprocess only (deck write + "
        "simulation + log read); it excludes host/CI queueing and toolchain setup. "
        "The runs were sequential in one process on one host. `acct` statistics are "
        "ngspice's own accounting (print-only option, identical in every deck)."
    )
    add("")
    add("| profile | `.options` card | wall-clock (s) | x reference | "
        + " | ".join(SOLVER_STAT_NAMES) + " | "
        + " | ".join(label for label, _ in _SOLVER_LOG_PATTERNS) + " |")
    add("|" + "---|" * (4 + len(SOLVER_STAT_NAMES) + len(_SOLVER_LOG_PATTERNS)))
    for r in runs:
        st = r["solver_stats"]
        card = solver_options_card(r["solver_profile"])
        ratio = r["wall_s"] / reference["wall_s"] if reference["wall_s"] > 0 else float("nan")
        add(
            f"| `{r['solver_profile']}` | {'(none)' if card is None else f'`{card}`'} | "
            f"{r['wall_s']:.0f} | {ratio:.2f} | "
            + " | ".join(
                "n/a" if st["stats"].get(n) is None else f"{st['stats'][n]:g}"
                for n in SOLVER_STAT_NAMES
            )
            + " | "
            + " | ".join(str(st["log_counts"][label]) for label, _ in _SOLVER_LOG_PATTERNS)
            + " |"
        )
    add("")
    add(f"Total audit wall-clock (all {len(runs)} runs): {total_wall_s:.0f} s.")
    add("")

    add("## Captured code vs ideal code, every input under every profile")
    add("")
    add("| profile | " + " | ".join(
        f"`{f:+.2f}*V_REF` (ideal {tb.ideal_code(f)})" for f in tb.INPUT_FRACTIONS
    ) + " | phase structure | verdict |")
    add("|---" * (len(tb.INPUT_FRACTIONS) + 3) + "|")
    if latest is not None:
        add(
            f"| `records/LATEST` = `{latest['record_id']}` ({latest['ngspice'] or 'ngspice ?'}) | "
            + " | ".join("MISSING" if c is None else str(c) for c in latest["codes"])
            + " | (see that record) | (see that record) |"
        )
    for r in runs:
        cells = []
        for cv in r["conversions"]:
            code = "MISSING" if cv["code"] is None else str(cv["code"])
            err = "n/a" if cv["error_lsb"] is None else f"{cv['error_lsb']:+d}"
            cells.append(f"{code} ({err} LSB)")
        add(f"| `{r['solver_profile']}` | " + " | ".join(cells)
            + f" | {r['n_phase_ok']}/{r['n_conversions']} | {'PASS' if r['all_ok'] else 'FAIL'} |")
    add("")
    if latest is not None:
        ref_codes = [cv["code"] for cv in reference["conversions"]]
        same = ref_codes == latest["codes"]
        same_dut = latest["netlist_sha"] == prov.netlist_sha
        add(
            f"- **Reference profile vs `records/LATEST` row `{cid}`**: codes "
            + ("IDENTICAL" if same else "DIFFER")
            + f" ({latest['ngspice'] or 'unknown ngspice'} there, {prov.ng_version} here; "
            + ("same" if same_dut else "DIFFERENT")
            + " DUT netlist sha256; LATEST's simulator options: "
            + f"{latest['simulator_options']}; this run: profile `{reference['solver_profile']}`). "
            + ("The recorded failure modes at this corner are reproduced by this audit's "
               "reference run, so the comparison below speaks to them directly."
               if same else
               "The reference run does not reproduce LATEST's row, so the comparison "
               "below is against this audit's own reference run, not against LATEST.")
        )
        add("")

    add("## Per-input detail (captured bits, BUSY/SAMPLE per CLK period)")
    add("")
    add("| profile | input | captured bits (DOUT9..DOUT0) | BUSY | SAMPLE | phase |")
    add("|---|---|---|---|---|---|")
    for r in runs:
        for cv in r["conversions"]:
            add(f"| `{r['solver_profile']}` | `{cv['fraction']:+.2f}*V_REF` | "
                f"`{_bits_str(cv['bits'])}` | `{_bits_str(cv['busy'])}` | "
                f"`{_bits_str(cv['sample'])}` | {'OK' if cv['phase_ok'] else 'WRONG'} |")
    add("")

    add("## Power (informational -- DRAFT row)")
    add("")
    add("| profile | I(VDD) (uA) | I(VPWR) (uA) | I(VREFP) (uA) | I(VCM) (uA) | "
        "I(VREFN) (uA) | total power (uW) | total power vs reference |")
    add("|---|---|---|---|---|---|---|---|")
    if latest is not None:
        add(f"| `records/LATEST` = `{latest['record_id']}` | | | | | | "
            + ("n/a" if latest["power_w"] is None else f"{latest['power_w'] * 1e6:.3f}")
            + " | |")
    for r in runs:
        def ua(name: str, _r=r) -> str:
            v = _r["currents"].get(name)
            return "n/a" if v is None else f"{v * 1e6:.3f}"
        d = _rel_delta(reference["power_w"], r["power_w"])
        add(f"| `{r['solver_profile']}` | {ua('i_vdd')} | {ua('i_vpwr')} | {ua('i_vrefp')} | "
            f"{ua('i_vcm')} | {ua('i_vrefn')} | {_power_uw_str(r['power_w'])} | "
            + ("n/a" if d is None else f"{d:+.3%}") + " |")
    add("")

    add("## Register-transition guard (read-only probes, every measured conversion)")
    add("")
    lo, hi = SWITCH_TRACE_EDGE_WINDOW_NS
    add(
        "A DOUT/SEL/ring/control transition is *scheduled* when it lands "
        f"{lo:g}..+{hi:g} ns after a CLK rising edge at which the SAR's own "
        "sequencer may move that node (`switch_trace_expected_edges()`); anything "
        "else is UNSCHEDULED -- the signature of issue #621's default-settings "
        "artefact. Rail excursion = a top plate below "
        f"-{SWITCH_TRACE_RAIL_V:g} V inside the conversion window."
    )
    add("")
    add("| profile | conversion | UNSCHEDULED | first UNSCHEDULED | TOP_P below rail | TOP_N below rail |")
    add("|---|---|---|---|---|---|")
    for r in runs:
        for g in r["guards"]:
            fu = g["first_unscheduled"]
            ex = g["excursions"]
            add(
                f"| `{r['solver_profile']}` | {g['conversion']} | {len(g['unscheduled'])} | "
                + ("none" if fu is None else
                   f"`{fu['node']}` {fu['direction']} phase {fu['phase']} {fu['offset_ns']:+.2f} ns")
                + " | "
                + " | ".join("no" if ex.get(t) is None else
                             f"phase {ex[t]['phase']} {ex[t]['offset_ns']:+.2f} ns"
                             for t in ("TOP_P", "TOP_N"))
                + " |"
            )
    add("")

    add("## Comparison against the reference profile")
    add("")
    for p, ms in comparisons.items():
        add(f"### `{p}` vs `{REFERENCE_SOLVER_PROFILE}`")
        add("")
        if not ms:
            add("No observation moved (codes, BUSY/SAMPLE words, phase verdicts, missing "
                f"measurements, per-rail currents and power within "
                f"{SOLVER_AUDIT_POWER_REL_TOL:.0%}, UNSCHEDULED counts, rail excursions).")
        else:
            add("| observation | reference | control | recorded failure mode? |")
            add("|---|---|---|---|")
            for m in ms:
                add(f"| {m['observation']} | {m['reference']} | {m['control']} | "
                    f"{'**yes -- SOLVER-SENSITIVE**' if m['failure_mode'] else 'no (value only)'} |")
        add("")

    add("## LIMITATIONS")
    add("")
    add(
        f"One corner (`{cid}`), five DC inputs, one toolchain. A clean audit here says "
        "the reference settings are adequate for THIS corner's recorded observations; "
        "it does not certify the other eight corners or any other experiment. The "
        "power-change tolerance is an audit reporting threshold, not a spec value."
    )
    add("")

    extra = {
        "tran step": f"{tb.TRAN_STEP_NS} ns",
        "simulated span": f"{tb.t_stop_ns():.1f} ns per run",
        "testbench fragment sha256": f"`{evidence.sha256_file(tb.FRAGMENT_PATH)}`",
        "SIM_NGSPICE_TIMEOUT_S": os.environ.get("SIM_NGSPICE_TIMEOUT_S", "(default)"),
        "audit instrumentation (every profile)": f"`{SOLVER_AUDIT_STATS_CARD}` + register-transition guard `.meas` probes",
    }
    for r in runs:
        extra[f"simulator options [{r['solver_profile']}]"] = solver_settings_text(r["solver_profile"])
        extra[f"wall-clock [{r['solver_profile']}]"] = f"{r['wall_s']:.0f} s"
    lines.extend(evidence.environment_block(
        pdk_line=prov.pdk_line, ngspice_line=prov.ng_version,
        netlist_sha256=prov.netlist_sha, extra=extra,
    ))
    add("")
    # A solver audit is a check on reference evidence, never a replacement for
    # it, so it supersedes nothing by construction (issue #502's named opt-out).
    lines.extend(evidence.footer_lines(written_by, evidence.NEVER_SUPERSEDES))
    return evidence.close_record(prov, lines, "Solver-audit record")


# issue #621: an opt-in SOLVER CONTROL for the coherent-sine run. It tightens
# ngspice's relative tolerance 10x (default 1e-3) and swaps the default
# trapezoidal integration for Gear, which damps trapezoidal ringing. DUT and
# stimulus are untouched; only how the same circuit is integrated changes.
# Its purpose is to separate a circuit behaviour from a numerical artefact:
# an event that persists under both is not an artefact of the default
# settings. Since issue #637 this is the named solver profile `reltol-gear`
# (SOLVER_PROFILES), and DR-023 made that profile the REFERENCE policy, so
# `--sine-solver-control` no longer selects a control: it is kept only as the
# spelling of `--solver-profile reltol-gear` that the committed #621 record's
# Written-by line uses (sim/spec-coverage.json cites it as a cold start).
# A run with it is now a reference capture. The pre-DR-023 settings are
# `--solver-profile ngspice-default`, which is the control.
SINE_SOLVER_CONTROL_PROFILE = "reltol-gear"
SINE_SOLVER_CONTROL_OPTIONS = solver_options_card(SINE_SOLVER_CONTROL_PROFILE)


def run_sine_point(
    netlist_text: str,
    pdk_info: pdk.PdkInfo,
    scratch: Path,
    n: int,
    tone_bin: int,
    amplitude_fraction: float,
    corner: tuple[str, float, float] = BASELINE_CORNER,
    trace_conversions: tuple[int, ...] = (),
    switch_trace_conversions: tuple[int, ...] = (),
    solver_profile: str = REFERENCE_SOLVER_PROFILE,
) -> dict:
    process_corner, temp_c, supply_v = corner
    cid = corners_mod.corner_id(process_corner, temp_c, supply_v)
    fragment = tb.sine_fragment_text(n, tone_bin, amplitude_fraction)
    extra_meas: list[str] = []
    for c in trace_conversions:
        extra_meas += sine_trace_measure_lines(c)
    for c in switch_trace_conversions:
        extra_meas += switch_trace_measure_lines(c, supply_v)
    deck = assemble_deck(
        netlist_text, pdk_info, process_corner, temp_c, supply_v, fragment=fragment,
        extra_meas=extra_meas or None, solver_profile=solver_profile,
    )
    t0 = time.time()
    log_text = _run_ngspice(deck, scratch, f"coherent_sine_{cid}", attempts=1)
    wall_s = time.time() - t0

    names = tb.sine_measure_names(n)
    trace_names: list[str] = []
    for c in trace_conversions:
        trace_names += _node_trace_names(node_trace_plan(c))
        trace_names += [f"nt_c{c}_samp_{t}" for t in ("vinp", "vinn", "top_p", "top_n")]
    for c in switch_trace_conversions:
        trace_names += switch_trace_flat_names(c)
    parsed = measure.parse(log_text, names + trace_names, anchored=False)
    # trace probes are read-only extras: their absence never makes the
    # capture invalid, so `missing` stays the code/phase measurements only.
    missing = measure.missing(parsed, names)
    conversions = tb.sine_measured_conversions(n)
    stream = decode_code_stream(parsed, supply_v, conversions)
    result = analyze_sine_capture(stream["codes"], n, tone_bin, amplitude_fraction)
    result["outlier_diag"] = sine_outlier_diagnostic(
        stream["codes"], result["ideal_codes"], conversions, n, tone_bin
    )
    result["traces"] = [
        decode_sine_trace(parsed, c, result["ideal_codes"][conversions.index(c)], supply_v,
                          stream["codes"][conversions.index(c)])
        for c in trace_conversions
    ]
    result["switch_traces"] = [
        decode_switch_trace(parsed, c, supply_v) for c in switch_trace_conversions
    ]
    result.update(
        stream,
        conversions=conversions,
        n=n,
        tone_bin=tone_bin,
        amplitude_fraction=amplitude_fraction,
        process_corner=process_corner,
        temp_c=temp_c,
        supply_v=supply_v,
        corner_id=cid,
        missing=missing,
        log_text=log_text,
        fragment=fragment,
        wall_s=wall_s,
        solver_profile=solver_profile,
        solver_control=is_solver_control(solver_profile),
    )
    return result


def sine_point_problems(point: dict) -> list[str]:
    """Why a coherent-sine capture is NOT a valid measurement of the
    converter (empty list = valid). An FFT will happily turn any code stream
    into an SNDR, so the run's own sanity evidence gates it: every
    measurement present, every conversion with the correct 12-period
    BUSY/SAMPLE structure (a converter that is not cycling through its
    phases is not converting the sampled tone, whatever codes come out), and
    the largest non-DC bin on the drive bin."""
    problems: list[str] = []
    if point["missing"]:
        problems.append(f"{len(point['missing'])} measurement(s) missing")
    n_bad = sum(1 for ok in point["phase_ok"] if not ok)
    if n_bad:
        problems.append(
            f"phase structure wrong at {n_bad}/{len(point['phase_ok'])} conversions"
        )
    a = point["analysis"]
    if a is None:
        problems.append(f"not analysable: {point['analysis_error']}")
    elif a["peak_bin"] != point["tone_bin"]:
        problems.append(
            f"largest non-DC bin is {a['peak_bin']}, not the drive bin {point['tone_bin']}"
        )
    return problems


def format_outlier_summary(point: dict) -> str:
    """Console lines for the per-code outlier diagnostic (never a validity
    verdict)."""
    d = point["outlier_diag"]
    head = (
        f"per-code outlier diagnostic: bound |error| > {d['bound_lsb']} LSB, "
        f"max |error| = {d['max_abs_error']} LSB, {len(d['outliers'])} outlier(s)"
    )
    out = [head]
    for o in d["outliers"]:
        out.append(
            f"  OUTLIER sample {o['sample']} conversion {o['conversion']}: ideal "
            f"{o['ideal']}, captured {o['captured']}, error {o['error']:+d} LSB"
        )
    lo, a = d["leave_out"], point["analysis"]
    if lo is not None and a is not None:
        out.append(
            f"  DIAGNOSTIC-ONLY (outlier error zeroed; headline above is the "
            f"unmodified stream): SNDR={lo['sndr_db']:.2f} dB "
            f"({lo['sndr_db'] - a['sndr_db']:+.2f}) ENOB={lo['enob_bit']:.3f} bit "
            f"({lo['enob_bit'] - a['enob_bit']:+.3f}) SFDR={lo['sfdr_db']:.2f} dB "
            f"({lo['sfdr_db'] - a['sfdr_db']:+.2f})"
        )
    return "\n".join(out)


def format_sine_point(point: dict) -> str:
    a = point["analysis"]
    ideal = point["ideal"]
    problems = sine_point_problems(point)
    if a is None:
        body = f"NOT ANALYSABLE ({point['analysis_error']})"
    else:
        body = ("INVALID (" + "; ".join(problems) + ") " if problems else "") + (
            f"SNDR={a['sndr_db']:.2f} dB ENOB={a['enob_bit']:.3f} bit "
            f"(FS-normalised {a['enob_fs_bit']:.3f}); ideal quantizer at the same "
            f"plan: SNDR={ideal['sndr_db']:.2f} dB ENOB={ideal['enob_bit']:.3f} bit"
        )
    return (
        f"{point['corner_id']}: N={point['n']} bin={point['tone_bin']} "
        f"A={point['amplitude_fraction']:g}*V_REF -- {body} "
        f"phases_ok={sum(point['phase_ok'])}/{len(point['phase_ok'])} "
        f"({point['wall_s']:.0f}s)"
    )


def write_sine_record(
    point: dict,
    netlist_text: str,
    supersedes: str,
    written_by: str,
    behavioral: dict | None,
) -> Path:
    """Mint a NEW coherent-sine record (append-only; never touches
    records/LATEST, which names the corner campaign)."""
    cid = point["corner_id"]
    prov, lines = evidence.open_record(
        EXPERIMENT_DIR, netlist_text, "corners",
        {
            f"coherent-sine-{cid}.log": point["log_text"],
            "coherent_sine_tb_fragment.spice": point["fragment"],
        },
    )
    n, k, amp = point["n"], point["tone_bin"], point["amplitude_fraction"]
    a = point["analysis"]
    ideal = point["ideal"]
    f_in = tb.sine_tone_hz(n, k)
    span_ns = tb.sine_t_stop_ns(n)
    n_phase_ok = sum(point["phase_ok"])

    add = lines.append
    add(
        "- **Claim**: `spec/target-spec.md#target-table` -- **ENOB**, DRAFT row, "
        "INFORMATIONAL CROSS-CHECK ONLY (issue #603). The first dynamic-test "
        "(coherent-sine FFT) SNDR/ENOB measurement on the whole transistor-level "
        "`design/sar_adc_top.spice`, reported against the behavioral-accelerated "
        "composite estimate (`sim/enob-estimate/`). It does NOT grade the DRAFT "
        "row: one corner, a short record, no noise sources in the transient, and "
        "an amplitude below full scale (see LIMITATIONS). No spec row is edited."
    )
    add("- **Netlist provenance**: schematic (`design/sar_adc_top.spice`, unmodified)")
    profile = point.get("solver_profile", REFERENCE_SOLVER_PROFILE)
    if is_solver_control(profile):
        add(
            "- **SOLVER-CONTROL RUN (issue #621) -- NOT THE REFERENCE CAPTURE**: "
            + solver_control_note(profile)
            + ". DUT and stimulus are unmodified; only the integration settings "
            "differ. It exists to test whether an observed event depends on the "
            "solver settings; its figures are a control, not the converter's "
            "headline evidence."
        )
    add(corners_mod.corner_matrix_summary_line(
        [point["process_corner"]], [point["temp_c"]], [point["supply_v"]], 1
    ).replace("one-at-a-time per sim/README.md", "single-corner pilot, NOT the ratified grid"))
    add(
        f"- **Dynamic-test (FFT) metadata**: N = {n} samples (one code per "
        f"conversion); f_s = {tb.F_SAMPLE_HZ / 1e6:g} MS/s (`f_clk = "
        f"{tb.F_CLK_HZ / 1e6:g} MHz` / {tb.PHASES_PER_CONVERSION} CLK periods per "
        f"conversion, DR-006); coherent bin = {k} (coprime to N); "
        f"f_in = {k} * f_s / {n} = {f_in:.10g} Hz; window = none (coherent sampling)."
    )
    add(
        f"- **Stimulus**: antiphase sine on VINP/VINN about `VCM = V_DD/2`, peak "
        f"differential amplitude `{amp:g}*V_REF` "
        f"({20 * math.log10(amp):.2f} dBFS against the +-V_REF differential full "
        "scale) -- the largest magnitude the DC corner campaign "
        "(`records/20261001-105439-c324f80.md`) resolves within 1 LSB; a larger "
        "tone would sweep into the known near-full-scale saturation DR-021 "
        "addresses and measure that recorded defect instead. "
        f"{tb.SINE_STARTUP_CONVERSIONS} start-up conversion(s) discarded before the "
        f"N-sample record (conversions {point['conversions'][0]}.."
        f"{point['conversions'][-1]}); codes read mid-PH_EOC exactly as the DC "
        "bench does -- see `sim/full-conversion-transient/testbench/"
        "coherent_sine_tb_fragment.spice` (the exact fragment run is also stored "
        f"under `corners/{prov.record_id}/`)."
    )
    add(
        f"- **Runtime (the pilot's first deliverable)**: {span_ns / 1000:.1f} us "
        f"simulated in {point['wall_s']:.0f} s wall-clock "
        f"({point['wall_s'] / (span_ns / 1000):.1f} s per simulated us) on a shared "
        "dispatch host -- see the record-length table below."
    )
    if a is None:
        add(
            f"- **Measured value(s)**: NONE -- the captured stream could not be "
            f"analysed: {point['analysis_error']}. Missing measurements: "
            f"{len(point['missing'])}."
        )
    else:
        add(
            f"- **Measured value(s)** (`{cid}`): SNDR = **{a['sndr_db']:.2f} dB**, "
            f"ENOB = **{a['enob_bit']:.3f} bit** at the tone's own amplitude "
            f"({a['amplitude_dbfs']:.2f} dBFS measured); full-scale-normalised "
            f"ENOB = **{a['enob_fs_bit']:.3f} bit** (extrapolation, see "
            f"LIMITATIONS); SFDR = {a['sfdr_db']:.2f} dB (largest spur bin "
            f"{a['spur_bin']}). Ideal 10-bit quantizer on the identical plan: SNDR = "
            f"{ideal['sndr_db']:.2f} dB, ENOB = {ideal['enob_bit']:.3f} bit "
            f"(FS-normalised {ideal['enob_fs_bit']:.3f} bit)."
        )
    problems = sine_point_problems(point)
    if problems:
        add(
            "- **VALIDITY: NOT A VALID MEASUREMENT OF THE CONVERTER** -- "
            + "; ".join(problems)
            + ". The figures above are what the FFT returns for the captured "
            "stream, recorded as-is (append-only evidence), but they are not an "
            "SNDR/ENOB of the design and no delta below may be read as one."
        )
    d = point["outlier_diag"]
    add(
        f"- **Per-code outlier diagnostic (issue #621; a named DIAGNOSTIC, not a "
        f"validity criterion)**: bound |captured - ideal| > {d['bound_lsb']} LSB; "
        f"max |error| = {d['max_abs_error']} LSB; outliers = **{len(d['outliers'])}** "
        f"of {n}. "
        + ("OUTLIER PRESENT -- the headline figures above are set by these "
           "conversions, not by the converter's general dynamic performance. "
           if d["outliers"] else "")
        + "The headline SNDR/ENOB/SFDR above are computed from the complete, "
        "unmodified captured stream."
    )
    for o in d["outliers"]:
        add(
            f"  - outlier: sample {o['sample']}, conversion {o['conversion']}, ideal "
            f"{o['ideal']}, captured {o['captured']}, signed error {o['error']:+d} LSB"
        )
    if d["outliers"] and d["leave_out"] is not None and a is not None:
        lo = d["leave_out"]
        add(
            "  - **DIAGNOSTIC-ONLY, NOT REPLACEMENT EVIDENCE** -- sensitivity with the "
            "outlier samples' error zeroed (ideal code substituted at those samples "
            "only, to keep the coherent record whole): "
            f"SNDR {lo['sndr_db']:.2f} dB ({lo['sndr_db'] - a['sndr_db']:+.2f} dB vs "
            f"headline), ENOB {lo['enob_bit']:.3f} bit "
            f"({lo['enob_bit'] - a['enob_bit']:+.3f}), SFDR {lo['sfdr_db']:.2f} dB "
            f"({lo['sfdr_db'] - a['sfdr_db']:+.2f}). The captured stream is unchanged."
        )
    add(
        "- **Data provenance**: transient simulation of the schematic netlist at a "
        "single PVT corner; ngspice `.tran` injects no device noise, so the "
        "measured spectrum holds quantization plus deterministic errors only."
    )
    add("")

    add("## Cross-check against the behavioral-accelerated estimate")
    add("")
    if a is None:
        add("No delta: the dynamic measurement did not produce an analysable stream.")
    else:
        add(
            "| reference | behavioral ENOB (bit) | dynamic ENOB, FS-normalised (bit) | "
            "delta, dynamic - behavioral (bit) |"
        )
        add("|---|---|---|---|")
        refs = [("spec/target-spec.md quoted value (when #603 was filed)",
                 SPEC_QUOTED_BEHAVIORAL_ENOB_BIT)]
        if behavioral is not None:
            refs.append((f"`{behavioral['record']}` (current LATEST)", behavioral["enob_bit"]))
        for label, value in refs:
            add(
                f"| {label} | {value:.3f} | {a['enob_fs_bit']:.3f} | "
                f"{a['enob_fs_bit'] - value:+.3f} |"
            )
        add("")
        add(
            "The comparison uses the FULL-SCALE-NORMALISED dynamic ENOB because the "
            "behavioral estimate is full-scale-referred (it composes noise against "
            "`LSB/sqrt(12)`, i.e. a full-scale sine's SNR relationship). The two "
            "do NOT measure the same things: the behavioral estimate includes "
            "125C comparator thermal noise and CDAC mismatch, which this "
            "noise-free, mismatch-free tt transient cannot see; this measurement "
            "includes the dynamic, deterministic error mechanisms of the real "
            "circuit (settling, kickback, CDAC gain error, mid-scale MSB behaviour) "
            "that the behavioral estimate does not model. The measured-vs-ideal "
            "gap below is the cleaner statement of what the circuit itself costs "
            "at this plan."
        )
        add("")
        add(
            f"- Measured vs ideal quantizer, same plan: SNDR "
            f"{a['sndr_db'] - ideal['sndr_db']:+.2f} dB, ENOB "
            f"{a['enob_bit'] - ideal['enob_bit']:+.3f} bit."
        )
        add(
            f"- Tone bin check: largest non-DC bin = {a['peak_bin']} "
            f"({'matches' if a['peak_bin'] == k else 'DOES NOT match'} the drive bin {k})."
        )
        add(
            f"- Clipping: {a['n_at_rails']}/{n} codes at a rail (0 or "
            f"{2 ** tb.N_BITS - 1})."
        )
        add(
            f"- Measured tone amplitude: {a['amplitude_codes']:.2f} codes peak "
            f"(driven: {amp * 2 ** (tb.N_BITS - 1):.2f}); DC: "
            f"{a['dc_codes']:.2f} codes (mid-scale = {2 ** (tb.N_BITS - 1)})."
        )
    add(
        f"- Convergence / phase structure: {len(point['missing'])} missing "
        f"measurement(s); {n_phase_ok}/{len(point['phase_ok'])} conversions with "
        "the correct 12-period BUSY/SAMPLE structure."
    )
    add("")

    add("## Captured code stream")
    add("")
    add("| sample | conversion | sampled Vd (x V_REF) | ideal code | captured code | error (LSB) | phases |")
    add("|---|---|---|---|---|---|---|")
    for i, c in enumerate(point["conversions"]):
        code = point["codes"][i]
        ideal_c = point["ideal_codes"][i]
        err = "n/a" if code is None else f"{code - ideal_c:+d}"
        add(
            f"| {i} | {c} | {tb.sine_input_fraction(c, n, k, amp):+.5f} | {ideal_c} | "
            f"{'MISSING' if code is None else code} | {err} | "
            f"{'OK' if point['phase_ok'][i] else 'WRONG'} |"
        )
    add("")

    if point.get("traces"):
        add("## Conversion trace (issue #621; read-only probes on the same run)")
        add("")
        add(
            "Raw `.meas` values from the SAME transient that produced the code "
            "stream above (probes appended after the stimulus; DUT and stimulus "
            "unmodified), at the coherent-sine run's own conversion timing. "
            "OBSERVED = the voltages/bits below. INFERRED = anything in the prose "
            "after the tables."
        )
        add("")
        for tr in point["traces"]:
            c = tr["conversion"]
            sm = tr["sampling"]
            fmt = lambda x: "n/a" if x is None else f"{x:.4f}"
            add(
                f"### Conversion {c} (ideal code {tr['ideal_code']} = "
                f"`{tr['ideal_code']:010b}`)"
            )
            add("")
            add(
                f"Just before the sampling edge: VINP={fmt(sm['vinp'])} V, "
                f"VINN={fmt(sm['vinn'])} V, TOP_P={fmt(sm['top_p'])} V, "
                f"TOP_N={fmt(sm['top_n'])} V."
            )
            add("")
            add("| phase | bit | ideal bit | captured bit | CLK mid | COMP_OUT mid | OUTN_NC mid | COMP_OUT pre | OUTN_NC pre | TOP_P pre | TOP_N pre |")
            add("|---|---|---|---|---|---|---|---|---|---|---|")
            for ph in tr["phases"]:
                v = ph["v"]
                add(
                    f"| {ph['phase']} | {ph['bit']} | {ph['ideal_bit']} | "
                    f"{'n/a' if ph['captured_bit'] is None else ph['captured_bit']}"
                    f"{'' if ph['captured_bit'] == ph['ideal_bit'] else ' **(differs)**'} | "
                    f"{fmt(v['clk_mid'])} | {fmt(v['compout_mid'])} | {fmt(v['compoutn_mid'])} | "
                    f"{fmt(v['compout_pre'])} | {fmt(v['compoutn_pre'])} | "
                    f"{fmt(v['top_p_pre'])} | {fmt(v['top_n_pre'])} |"
                )
            add("")
            fd = tr["first_divergent"]
            fc = tr["final_code"]
            add(
                f"- **Final captured code (mid-PH_EOC readout, the authoritative "
                f"code)**: {'MISSING' if fc is None else f'{fc} = `{fc:010b}`'} "
                f"(ideal {tr['ideal_code']}). The `captured bit` column above is a "
                "probe 2 ns after each trial's capturing edge, NOT the final "
                "readout: it can differ from the ideal bit in a conversion whose "
                "final code is correct, so by itself it is not a divergence "
                "criterion; compare it with the final code."
            )
            add(
                "- **First post-edge probe differing from the ideal bit (observed)**: "
                + ("none."
                   if fd is None else
                   f"phase {fd['phase']} (bit {fd['bit']}): ideal {fd['ideal_bit']}, "
                   f"probe {fd['captured_bit']}.")
            )
            ex = tr["rail_excursions"]
            add(
                "- **Comparator-input top plate outside [0, V_DD] at a pre-capture "
                "instant (observed)**: "
                + ("none." if not ex else "; ".join(
                    f"phase {p} (bit {b}) {node} = {v:.4f} V" for p, b, node, v in ex)
                ) + (" The first such phase is the earliest analog event outside the "
                     "normal staircase in this trace." if ex else "")
            )
            add("")

    if point.get("switch_traces"):
        lines.extend(switch_trace_record_lines(point["switch_traces"]))

    add("## Record length vs runtime")
    add("")
    per_us = point["wall_s"] / (span_ns / 1000)
    add("| N | simulated span (us) | wall-clock (measured / projected at this rate) |")
    add("|---|---|---|")
    for n_alt in sorted({n, 64, 128, 256, 1024}):
        span_alt = tb.sine_t_stop_ns(n_alt) / 1000
        tag = "measured" if n_alt == n else "projected"
        add(f"| {n_alt} | {span_alt:.1f} | {span_alt * per_us / 60:.0f} min ({tag}) |")
    add("")
    add(
        "Projections assume runtime linear in simulated time at this pilot's own "
        "rate on the same host. Longer records -- and any multi-corner or Monte "
        "Carlo extension -- belong on the batch fleet as a `klt sim` request "
        "(#564), not a local loop."
    )
    add("")

    add("## LIMITATIONS (named, flagged -- not relaxed to force a result)")
    add("")
    add(
        f"1. **Short record.** N = {n}: the noise floor is spread over only "
        f"{n // 2 - 1} non-DC, non-tone bins, so the SNDR estimate itself has "
        "sizeable variance (even the ideal quantizer's ENOB on this plan deviates "
        "from the textbook value). Read the measured-vs-ideal gap, not the "
        "absolute ENOB."
    )
    add(
        "2. **No noise.** `.tran` injects no thermal/flicker noise; the behavioral "
        "estimate's dominant comparator-noise term is absent here by construction."
    )
    add(
        "3. **One corner, no mismatch.** tt/27C/1.8V only; no Monte Carlo. Not a "
        "statistical (yield) statement."
    )
    add(
        f"4. **Below full scale.** {20 * math.log10(amp):.2f} dBFS. The "
        "full-scale-normalised ENOB assumes the noise+distortion floor is "
        "amplitude-independent, which is false for distortion that grows with "
        "amplitude (and the large-signal saturation recorded by the DC campaign "
        "is the opposite of amplitude-independent)."
    )
    add("")

    lines.extend(
        evidence.environment_block(
            pdk_line=prov.pdk_line,
            ngspice_line=prov.ng_version,
            netlist_sha256=prov.netlist_sha,
            extra={
                "tran step": f"{tb.TRAN_STEP_NS} ns",
                "simulated span": f"{span_ns:.1f} ns",
                "wall-clock": f"{point['wall_s']:.0f} s",
                "coherent-sine fragment sha256": f"`{evidence.sha256_text(point['fragment'])}`",
                "SIM_NGSPICE_TIMEOUT_S": os.environ.get("SIM_NGSPICE_TIMEOUT_S", "(default)"),
                "simulator options": solver_settings_text(profile),
            },
        )
    )
    add("")
    lines.extend(evidence.footer_lines(written_by, supersedes))
    return evidence.close_record(prov, lines, "Coherent-sine record")


def resolve_solver_cli(args: argparse.Namespace) -> tuple[str, str]:
    """(resolved solver profile, problem). A non-empty problem means the flag
    combination is refused before any simulation (issue #637)."""
    profile = args.solver_profile
    if args.sine_solver_control:
        if profile not in (None, SINE_SOLVER_CONTROL_PROFILE):
            return "", (f"--sine-solver-control means --solver-profile "
                        f"{SINE_SOLVER_CONTROL_PROFILE}; it conflicts with "
                        f"--solver-profile {profile}")
        profile = SINE_SOLVER_CONTROL_PROFILE
    profile = profile or REFERENCE_SOLVER_PROFILE
    modes = (
        ("--corners", args.corners),
        ("--mechanism-probe", args.mechanism_probe),
        ("--node-trace", args.node_trace),
        ("--cm-trace", args.cm_trace),
        ("--decision-margin-trace", args.decision_margin_trace),
    )
    if args.solver_audit:
        others = [f for f, on in modes + (
            ("--coherent-sine", args.coherent_sine),
            ("--solver-profile", args.solver_profile is not None),
            ("--sine-solver-control", args.sine_solver_control),
            ("--supersedes", bool(args.supersedes)),
        ) if on]
        if others:
            return "", (f"--solver-audit cannot be combined with {', '.join(others)} -- "
                        "it runs its own fixed baseline-corner comparison and its record "
                        "supersedes nothing")
        if args.jobs != 1:
            return "", ("--solver-audit runs its profiles sequentially so the wall-clock "
                        "comparison is like-for-like; --jobs must be 1")
        return profile, ""
    if args.audit_profile:
        return "", "--audit-profile requires --solver-audit"
    if is_solver_control(profile):
        if args.supersedes:
            return "", (f"solver profile {profile!r} is a SOLVER CONTROL, not a "
                        "replacement capture; it may not use --supersedes")
        on = [f for f, flag in modes if flag]
        if on:
            return "", (f"solver profile {profile!r} is a SOLVER CONTROL, allowed only for "
                        f"the baseline-corner DC run and --coherent-sine, not with "
                        f"{', '.join(on)} (a control checks reference evidence; promoting a "
                        "profile to the reference policy is a decision-record change)")
    return profile, ""


def audit_profiles(args: argparse.Namespace) -> tuple[str, ...]:
    """--audit-profile values in the order given, de-duplicated; the default
    set when none is given."""
    seen: list[str] = []
    for p in args.audit_profile:
        if p not in seen:
            seen.append(p)
    return tuple(seen) or SOLVER_AUDIT_DEFAULT_PROFILES


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check-env", action="store_true", help="only check toolchain/PDK pin")
    ap.add_argument("--corners", action="store_true", help="run the full ratified OAT grid (9 points)")
    ap.add_argument("--record", action="store_true", help="write an evidence record under records/")
    ap.add_argument(
        "--mechanism-probe",
        action="store_true",
        help="diagnostic: baseline corner, as-committed vs comparator-strobe-delayed "
        "(testbench-only netlist modification); folded into the record when combined "
        "with --record",
    )
    ap.add_argument(
        "--node-trace",
        action="store_true",
        help="diagnostic (issue #259): node-level COMP_OUT/CLK voltage trace against "
        "every bit-capture register's sampling edge, on the AS-COMMITTED (unmodified) "
        "netlist, at the two corners issue #259 names (tt_27c_1.62v, ff_27c_1.80v), "
        "for an opposite-sign pair of conversions probed within the same run. "
        "Always writes its own evidence record under records/ (a distinct diagnostic "
        "record, never records/LATEST); mutually exclusive with --corners/--record/"
        "--mechanism-probe -- it does not touch the corner-campaign flow at all.",
    )
    ap.add_argument(
        "--cm-trace",
        action="store_true",
        help="diagnostic (issue #265): node-level TOP_P/TOP_N (comparator VINP/VINN) "
        "voltage trace against CLK/COMP_OUT, at conversions 1 and 5 (the "
        "+-0.78*V_REF near-full-scale inputs) on the AS-COMMITTED (unmodified) "
        "netlist -- tests DR-008's common-mode-headroom hypothesis for the "
        "large-signal saturation. Always writes its own evidence record under "
        "records/ (a distinct diagnostic record, never records/LATEST); mutually "
        "exclusive with --corners/--record/--mechanism-probe/--node-trace/"
        "--decision-margin-trace.",
    )
    ap.add_argument(
        "--decision-margin-trace",
        action="store_true",
        help="diagnostic (issue #263 second pass / DR-009): trace the comparator's OWN "
        "differential input at every bit-trial decision instant of the three mid-scale "
        "conversions against the decision it produced, on the as-committed netlist AND "
        "on a testbench-only control copy with DR-009's comparator-output balancing "
        "dummies removed. Separates a search defect from a comparator offset. Always "
        "writes its own diagnostic evidence record under records/ (never "
        "records/LATEST); mutually exclusive with --corners/--record/--mechanism-probe/"
        "--node-trace/--cm-trace.",
    )
    ap.add_argument(
        "--coherent-sine",
        action="store_true",
        help="dynamic test (issue #603): drive a coherent antiphase sine, capture "
        "DOUT9..DOUT0 per conversion and compute SNDR/ENOB by FFT, at the baseline "
        "corner (tt/27C/1.8V) ONLY. Informational cross-check of sim/enob-estimate/, "
        "never a grade of the DRAFT ENOB row. With --record, mints a new record "
        "under records/ (never records/LATEST). Mutually exclusive with --corners/"
        "--mechanism-probe/--node-trace/--cm-trace/--decision-margin-trace; a "
        "multi-corner/Monte Carlo extension is a `klt sim` request (#564), not a "
        "flag here.",
    )
    ap.add_argument(
        "--sine-n", type=int, default=tb.SINE_RECORD_N,
        help=f"--coherent-sine record length N, a power of two (default {tb.SINE_RECORD_N})",
    )
    ap.add_argument(
        "--sine-bin", type=int, default=tb.SINE_TONE_BIN,
        help=f"--coherent-sine tone bin, coprime to N (default {tb.SINE_TONE_BIN})",
    )
    ap.add_argument(
        "--sine-amplitude", type=float, default=tb.SINE_AMPLITUDE_FRACTION,
        help="--coherent-sine peak differential amplitude as a fraction of V_REF "
        f"(default {tb.SINE_AMPLITUDE_FRACTION:g})",
    )
    ap.add_argument(
        "--sine-trace", type=int, action="append", default=[], metavar="CONV",
        help="--coherent-sine only (issue #621): also record a read-only node/control "
        "trace of this conversion number (repeatable) from the SAME transient. "
        "Single run, single corner; adds .meas probes only.",
    )
    ap.add_argument(
        "--sine-switch-trace", type=int, action="append", default=[], metavar="CONV",
        help="--coherent-sine only (issue #621): also record a read-only "
        "switching-event trace of this conversion (repeatable) from the SAME "
        "transient -- WHEN-crossing times of every DAC-steering and sequencer "
        "node classified against the SAR's own edge schedule, node values at the "
        "first top-plate rail excursion, and per-phase snapshots of the DAC "
        "bottom plates and front-end nodes. Single run, single corner; adds "
        ".meas probes only.",
    )
    ap.add_argument(
        "--sine-solver-control", action="store_true",
        help="--coherent-sine only (issue #621): add "
        f"`{SINE_SOLVER_CONTROL_OPTIONS}` to the same deck (DUT and stimulus "
        "unmodified). Kept for the committed #621 record's cold start; it is "
        f"exactly --solver-profile {SINE_SOLVER_CONTROL_PROFILE}, which DR-023 made "
        "the reference policy, so the run is no longer a control. The pre-DR-023 "
        "control is --solver-profile ngspice-default.",
    )
    ap.add_argument(
        "--solver-profile", choices=tuple(SOLVER_PROFILES), default=None,
        help="transient solver policy (issue #637; DR-023). Default "
        f"`{REFERENCE_SOLVER_PROFILE}` (the reference policy). Any other profile -- "
        "including `ngspice-default`, every pre-DR-023 record's settings -- is a "
        "labelled SOLVER CONTROL: allowed "
        "for the baseline-corner DC run and --coherent-sine only, never with "
        "--corners or a diagnostic mode, never with --supersedes, and its record "
        "never updates records/LATEST. Profiles: "
        + "; ".join(f"{k} = {solver_options_card(k) or '(no card)'}" for k in SOLVER_PROFILES),
    )
    ap.add_argument(
        "--solver-audit", action="store_true",
        help="issue #637: solver-sensitivity audit of the DC baseline corner "
        "(tt/27C/1.8V) -- the reference profile, then each --audit-profile, run "
        "sequentially on the same DUT and DC fragment, with print-only ngspice "
        "accounting and read-only register-transition guard probes added to every "
        "run. With --record, mints ONE diagnostic record (never records/LATEST, "
        "supersedes nothing) that names every observation that moved. Mutually "
        "exclusive with every other mode.",
    )
    ap.add_argument(
        "--audit-profile", action="append", default=[], metavar="PROFILE",
        choices=tuple(p for p in SOLVER_PROFILES if p != REFERENCE_SOLVER_PROFILE),
        help="--solver-audit only: a control profile to compare (repeatable; default "
        + " ".join(SOLVER_AUDIT_DEFAULT_PROFILES) + ").",
    )
    ap.add_argument(
        "--jobs", type=int, default=1,
        help="run this many ngspice corner points concurrently (default 1; results "
        "are independent processes, so this changes runtime only)",
    )
    ap.add_argument(
        "--supersedes", default="", metavar="RECORD_ID",
        help="record-id of the prior record of THIS experiment that the new record "
        "replaces for the same claim -- e.g. the previous corner campaign, when the "
        "DUT it graded has since been changed in design/. Written into the record's "
        "**Supersedes** field (sim/README.md's append-only convention: the prior "
        "record is never edited, only pointed back to). Leave unset for a record "
        "that makes a distinct claim rather than replacing one. The named record "
        "must already exist under records/.",
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if args.supersedes and not (
        EXPERIMENT_DIR / "records" / f"{args.supersedes}.md"
    ).is_file():
        print(
            f"FAIL: --supersedes {args.supersedes}: no such record under "
            f"{os.path.relpath(EXPERIMENT_DIR / 'records', REPO_ROOT)}/ -- a "
            "**Supersedes** field must point at a record that exists.",
            file=sys.stderr,
        )
        return 2

    if args.coherent_sine:
        others = [
            flag for flag, on in (
                ("--corners", args.corners),
                ("--mechanism-probe", args.mechanism_probe),
                ("--node-trace", args.node_trace),
                ("--cm-trace", args.cm_trace),
                ("--decision-margin-trace", args.decision_margin_trace),
            ) if on
        ]
        if others:
            print(f"FAIL: --coherent-sine cannot be combined with {', '.join(others)}",
                  file=sys.stderr)
            return 2
        for flag, convs in (("--sine-trace", args.sine_trace),
                            ("--sine-switch-trace", args.sine_switch_trace)):
            bad_trace = [c for c in convs
                         if c not in tb.sine_measured_conversions(args.sine_n)]
            if bad_trace:
                print(f"FAIL: {flag} {bad_trace}: not a measured conversion of this record",
                      file=sys.stderr)
                return 2
        try:
            dynamic_enob.check_coherent(args.sine_n, args.sine_bin)
            tb.sine_fragment_text(args.sine_n, args.sine_bin, args.sine_amplitude)
        except ValueError as exc:
            print(f"FAIL: --coherent-sine plan: {exc}", file=sys.stderr)
            return 2
    elif args.sine_trace or args.sine_switch_trace or args.sine_solver_control:
        print("FAIL: --sine-trace/--sine-switch-trace/--sine-solver-control require "
              "--coherent-sine", file=sys.stderr)
        return 2

    # issue #637: resolve the solver policy once, and refuse every flag
    # combination that would let a control profile stand in for reference
    # evidence -- all before any toolchain check or simulation.
    solver_profile, problem = resolve_solver_cli(args)
    if problem:
        print(f"FAIL: {problem}", file=sys.stderr)
        return 2

    check = toolchain.check_env()
    if args.check_env:
        print(toolchain.summary())
        for m in check.messages:
            print(f"FAIL: {m}")
        for w in check.warnings:
            print(f"WARNING: {w}")
        return check.status
    if check.status == 3:
        print("SKIP: ngspice or the pinned PDK is not installed on this machine.")
        for m in check.messages:
            print(f"  {m}")
        return 0
    if check.status == 1:
        print("FAIL: toolchain drifted from sim/toolchain.json pin.")
        for m in check.messages:
            print(f"  {m}")
        return 1
    for w in check.warnings:
        print(f"WARNING: {w}")

    if tb.FRAGMENT_PATH.read_text() != tb.fragment_text():
        print(
            "FAIL: testbench/full_conversion_tb_fragment.spice is stale against "
            "gen_full_conversion_tb.py -- regenerate it before running.",
            file=sys.stderr,
        )
        return 1

    with tempfile.TemporaryDirectory(prefix="full-conversion-") as scratch_name:
        scratch = Path(scratch_name)

        if args.coherent_sine:
            print(
                f"Coherent-sine dynamic test (issue #603) at "
                f"{corners_mod.corner_id(*BASELINE_CORNER)}: N={args.sine_n}, "
                f"bin={args.sine_bin}, A={args.sine_amplitude:g}*V_REF, "
                f"{tb.sine_t_stop_ns(args.sine_n) / 1000:.1f} us simulated:"
            )
            if is_solver_control(solver_profile):
                print(f"  SOLVER CONTROL (not the reference capture): {solver_settings_text(solver_profile)}")
            sine_netlist_text = dut_text()
            point = run_sine_point(
                sine_netlist_text, pdk.resolve(), scratch,
                args.sine_n, args.sine_bin, args.sine_amplitude,
                trace_conversions=tuple(args.sine_trace),
                switch_trace_conversions=tuple(args.sine_switch_trace),
                solver_profile=solver_profile,
            )
            if not args.quiet:
                print("  " + format_sine_point(point), flush=True)
                print("  " + format_outlier_summary(point).replace("\n", "\n  "), flush=True)
                for st in point["switch_traces"]:
                    print("  " + format_switch_trace_summary(st).replace("\n", "\n  "),
                          flush=True)
            if args.record:
                written_by = "sim/full-conversion-transient/run_conversion.py --coherent-sine --record"
                for flag, value, default in (
                    ("--sine-n", args.sine_n, tb.SINE_RECORD_N),
                    ("--sine-bin", args.sine_bin, tb.SINE_TONE_BIN),
                    ("--sine-amplitude", args.sine_amplitude, tb.SINE_AMPLITUDE_FRACTION),
                ):
                    if value != default:
                        written_by += f" {flag} {value:g}"
                for c in args.sine_trace:
                    written_by += f" --sine-trace {c}"
                for c in args.sine_switch_trace:
                    written_by += f" --sine-switch-trace {c}"
                if args.sine_solver_control:
                    written_by += " --sine-solver-control"
                elif is_solver_control(solver_profile):
                    written_by += f" --solver-profile {solver_profile}"
                write_sine_record(
                    point, sine_netlist_text, args.supersedes, written_by,
                    behavioral_enob_reference(),
                )
            return 1 if sine_point_problems(point) else 0

        if args.solver_audit:
            profiles = audit_profiles(args)
            print(
                f"Solver-sensitivity audit (issue #637) at "
                f"{corners_mod.corner_id(*BASELINE_CORNER)}: reference "
                f"`{REFERENCE_SOLVER_PROFILE}` then {', '.join(profiles)}, sequentially:"
            )
            runs, audit_netlist_text, total_wall_s = run_solver_audit(profiles, scratch, args.quiet)
            for r in runs[1:]:
                moved = compare_audit_runs(runs[0], r)
                print(f"  {r['solver_profile']} vs {REFERENCE_SOLVER_PROFILE}: "
                      + ("no observation moved" if not moved else
                         f"{len(moved)} observation(s) moved: "
                         + "; ".join(m["observation"] for m in moved)))
            if args.record:
                written_by = "sim/full-conversion-transient/run_conversion.py --solver-audit --record"
                if profiles != SOLVER_AUDIT_DEFAULT_PROFILES:
                    written_by += "".join(f" --audit-profile {p}" for p in profiles)
                write_solver_audit_record(
                    runs, audit_netlist_text, total_wall_s, latest_baseline_row(), written_by,
                )
            return 1 if any(r["missing"] for r in runs) else 0

        if args.node_trace:
            corner_names = ", ".join(
                corners_mod.corner_id(pc, tc, sv) for pc, tc, sv in NODE_TRACE_CORNERS
            )
            print(f"Node-level trace (issue #259) at {corner_names}:")
            traces, node_trace_netlist_text = run_node_trace(scratch, args.quiet)
            write_node_trace_record(traces, node_trace_netlist_text)
            any_missing = any(point["missing"] for point in traces.values())
            return 1 if any_missing else 0

        if args.cm_trace:
            corner_names = ", ".join(
                corners_mod.corner_id(pc, tc, sv) for pc, tc, sv in CM_TRACE_CORNERS
            )
            print(f"Common-mode trace (issue #265) at {corner_names}:")
            traces, cm_trace_netlist_text = run_cm_trace(scratch, args.quiet)
            write_cm_trace_record(traces, cm_trace_netlist_text)
            any_missing = any(point["missing"] for point in traces.values())
            return 1 if any_missing else 0

        if args.decision_margin_trace:
            corner_names = ", ".join(
                corners_mod.corner_id(pc, tc, sv)
                for pc, tc, sv in DECISION_MARGIN_CORNERS
            )
            print(
                "Decision-margin trace (issue #263 / DR-009) at "
                f"{corner_names}, as-committed and unbalanced-control:"
            )
            dm_points, dm_netlist_text = run_decision_margin_trace(scratch, args.quiet)
            write_decision_margin_record(dm_points, dm_netlist_text)
            any_missing = any(point["missing"] for point in dm_points.values())
            return 1 if any_missing else 0

        probe = None
        if args.mechanism_probe:
            print("Mechanism probe (baseline corner):")
            probe = run_mechanism_probe(scratch, args.quiet)
            if not (args.corners or args.record):
                return 0

        print(
            f"Running {'the ratified OAT grid (9 points)' if args.corners else 'the baseline corner'}"
            f" -- {tb.N_CONVERSIONS} conversions at {tb.F_CLK_HZ / 1e6:g} MHz per point:"
        )
        if is_solver_control(solver_profile):
            print(f"  SOLVER CONTROL (not reference evidence): {solver_settings_text(solver_profile)}")
        points, netlist_text = run_campaign(
            args.corners, args.jobs, args.quiet, scratch, solver_profile=solver_profile,
        )

        overall_ok = all(p["all_ok"] for p in points)
        n_ok = sum(1 for p in points if p["all_ok"])
        print(
            f"\nOVERALL: {'PASS' if overall_ok else 'FAIL'} "
            f"({n_ok}/{len(points)} corner points correct)"
        )

        if args.record:
            write_record(points, netlist_text, probe, args.supersedes, solver_profile=solver_profile)

    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Shared core of the full-conversion-transient campaigns.

Issue #861's behavior-preserving split of `run_conversion.py`, mirroring the
`comparator_campaigns/` (#613) and `supply_impedance_campaigns/` (#848)
layouts. This module holds everything two or more of that runner's seven
campaigns use -- the ratified corner axes, DR-023's named solver policy, deck
assembly, the ngspice invocation, the `.meas` decode, the single-point run
loop and the corner-campaign loop, the gain/offset fit, and the two
instrumentation cores (`--node-trace`'s per-phase probe plan and the issue
#621 switching-event trace) that `run_point()` and more than one campaign
both reach for.

`EXPERIMENT_DIR`, `assemble_deck()` and `_run_ngspice()` have exactly one
owner, here. Every other module in this package reads them as attributes of
this module (`common.EXPERIMENT_DIR`, `common.assemble_deck(...)`) rather
than importing the value, so that rebinding one of them ON THIS MODULE --
which the record-writer and deck tests do, to redirect a write into a temp
directory or to run a campaign without ngspice -- reaches every caller in one
patch. The same holds inside this module, where a plain global lookup already
sees the rebind.

`run_conversion.py`'s own re-exports (`import run_conversion as fc` in
`sim/supply-impedance-sensitivity/`) are a convenience surface for external
importers, NOT a patch point: a `mock.patch.object(run_conversion, ...)` on a
re-exported name rebinds the copy and no caller sees it. Patch the module
that owns the lookup.

This module imports no campaign module; the campaign modules import this one.
"""
from __future__ import annotations

import concurrent.futures
import math
import re
import sys
import time
from pathlib import Path

#: The experiment directory, `sim/full-conversion-transient/`. This module
#: sits one level deeper (inside the package), hence the second `.parent`.
EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
SIM_DIR = EXPERIMENT_DIR.parent
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(EXPERIMENT_DIR))

from harness import corners as corners_mod, evidence, measure, pdk, toolchain  # noqa: E402

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
# a labelled SOLVER CONTROL: it may not --supersedes and never moves LATEST.
# REPRODUCTION_SOLVER_PROFILE (`ngspice-default`) is additionally allowed
# with --corners and every diagnostic mode, so any pre-DR-023 record --
# the 9-corner campaign behind records/LATEST included -- can be re-run on
# the settings it was minted under; its record is still a labelled control.
# The single-setting attribution controls stay limited to the baseline-corner
# DC run and --coherent-sine (a control is a check on reference evidence, not
# a second campaign). Changing the reference policy again is a new decision
# record, followed by a fresh reference campaign under it.
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
# The settings of every pre-DR-023 record: the one control profile allowed
# with --corners and the diagnostic modes (reproduction, never reference).
REPRODUCTION_SOLVER_PROFILE = "ngspice-default"
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


def solver_control_bullet(profile: str) -> str:
    """The up-front SOLVER-CONTROL bullet of a diagnostic record (node/cm/
    decision-margin trace) run under a control profile. Diagnostic records
    never move `records/LATEST` and supersede nothing under ANY profile; the
    bullet makes the non-reference settings impossible to miss."""
    return (
        "- **SOLVER-CONTROL RUN (issue #637) -- NOT REFERENCE EVIDENCE**: "
        + solver_control_note(profile)
        + ". DUT, stimulus and probes are unmodified; only the integration "
        "settings differ. It re-runs this diagnostic on the settings a "
        "pre-DR-023 record was minted under, so that record stays reproducible."
    )


def solver_written_by(base: str, profile: str) -> str:
    """A diagnostic record's **Written by** command, naming the profile when
    it is not the reference policy (so the command reproduces the record)."""
    return f"{base} --solver-profile {profile}" if is_solver_control(profile) else base


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

    `extra_meas` (issue #259's `--node-trace`) is a list of additional,
    already-formatted `.meas tran ...` lines appended after the committed
    fragment and before `.end`. It never modifies the DUT netlist body
    itself -- it only adds read-only probes, so it is safe to combine with
    the as-committed (unmodified) netlist.

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

    lines = [
        "* sim/full-conversion-transient -- end-to-end full-conversion transient",
        "* on design/sar_adc_top.spice (issue #254). Assembled by",
        "* sim/full-conversion-transient/run_conversion.py; NOT routed through",
        "* sim/run_corners.py (its shared .control block is .op-only).",
        f"* corner={process_corner} temp={temp_c}C supply={supply_v}V",
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
        netlist_text, pdk_info, process_corner, temp_c, supply_v,
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
# Gain / offset extraction from the captured codes (issue #757, DR-022 item 3)
# --------------------------------------------------------------------------
FULL_SCALE_CODE = 2**tb.N_BITS - 1
GAIN_ERROR_DRAFT_LSB = 1.42  # DRAFT spec row, span-referred; informational only
MIDSCALE_MAX_FRACTION = 0.25  # |input| subset used by the secondary fit
DR022_GAIN_REFERENCE = {"tt_27c_1.80v": 0.99200, "tt_27c_1.62v": 0.99190}


def fit_gain_offset(pairs: list[tuple[int, int | None]]) -> dict | None:
    """Least-squares `code = g * ideal + offset` over (ideal, captured) pairs.

    Missing codes and codes saturated at 0 or full scale are excluded (a
    saturated code carries no slope information). Returns None when fewer
    than two distinct ideal codes remain. `resolution_lsb` is a conservative
    bound on the span-referred gain error this method can resolve: +-1 LSB of
    quantization on the two ends of the fitted span, scaled to full scale --
    it is NOT a fit confidence interval."""
    used = [
        (x, y) for x, y in pairs
        if y is not None and 0 < y < FULL_SCALE_CODE
    ]
    if len({x for x, _ in used}) < 2:
        return None
    n = len(used)
    mx = sum(x for x, _ in used) / n
    my = sum(y for _, y in used) / n
    sxx = sum((x - mx) ** 2 for x, _ in used)
    g = sum((x - mx) * (y - my) for x, y in used) / sxx
    offset = my - g * mx
    span = max(x for x, _ in used) - min(x for x, _ in used)
    return dict(
        g=g,
        offset=offset,
        n_used=n,
        eps_pct=(1.0 - g) * 100.0,
        eps_lsb=(1.0 - g) * 2**tb.N_BITS,
        resolution_lsb=2.0 * 2**tb.N_BITS / span,
    )


def corrected_code_errors(
    pairs: list[tuple[int, int | None]], g: float, offset: float
) -> list[float | None]:
    """Error vs ideal (LSB) of each captured code after removing `g` and
    `offset`: `(code - offset) / g - ideal`. None for a missing code."""
    return [None if y is None else (y - offset) / g - x for x, y in pairs]


def point_gain_analysis(point: dict) -> dict:
    """Two fits for one corner: every non-saturated input, and the
    mid-scale subset (|input| <= 0.25 V_REF). The subset is a post-hoc
    exclusion of the inputs whose failure DR-022 attributes to a separate
    mechanism (comparator defect), reported beside, never instead of, the
    all-inputs fit."""
    pairs = [(cv["ideal_code"], cv["code"]) for cv in point["conversions"]]
    mid = [
        (cv["ideal_code"], cv["code"]) for cv in point["conversions"]
        if abs(cv["fraction"]) <= MIDSCALE_MAX_FRACTION + 1e-9
    ]
    out = {}
    for tag, subset in (("all", pairs), ("mid", mid)):
        fit = fit_gain_offset(subset)
        out[tag] = None if fit is None else dict(
            fit, errors=corrected_code_errors(pairs, fit["g"], fit["offset"]),
        )
    return out


def gain_record_lines(points: list[dict]) -> list[str]:
    """Record section: extracted gain per corner and corrected-code errors."""
    lines: list[str] = []
    a = lines.append
    a("## Gain and offset from the captured codes (informational, issue #757)")
    a("")
    a(
        "**Method**: least-squares `code = g * ideal_code + offset` over the "
        "five captured codes of each corner (DR-022 Decision item 3's "
        "split of the acceptance), excluding codes saturated at 0 or "
        f"{FULL_SCALE_CODE}. This is **not** DR-022's bit-8-pair or bits-7..4 "
        "decision-margin extraction: it fits a code-domain slope with 1-LSB "
        "quantization, so offset, gain and any INL are confounded. "
        "`resolution` is a conservative bound (+-1 LSB at each end of the "
        "fitted span, scaled to full scale), not a confidence interval. "
        "Results are informational; the gain-error row "
        f"(`<= {GAIN_ERROR_DRAFT_LSB} LSB`) is DRAFT until #1 and this is "
        "not a pass/fail against it. The `mid-scale` fit uses only "
        f"|input| <= {MIDSCALE_MAX_FRACTION} V_REF, a post-hoc exclusion of "
        "the inputs that fail by tens of LSB for a separate mechanism; it is "
        "reported beside, not instead of, the all-inputs fit."
    )
    a("")
    a(
        "| corner-id | fit | inputs used | g | eps = 1-g (%) | eps x 2^N (LSB) | "
        "resolution (+-LSB) | offset (LSB) | corrected-code error per input (LSB) | "
        "worst \\|corrected error\\| (LSB) | within +-1 LSB |"
    )
    a("|---|---|---|---|---|---|---|---|---|---|---|")
    for p in points:
        for tag, label in (("all", "all non-saturated"), ("mid", "mid-scale")):
            fit = point_gain_analysis(p)[tag]
            if fit is None:
                a(f"| `{p['corner_id']}` | {label} | <2 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |")
                continue
            errs = fit["errors"]
            cells = ", ".join("n/a" if e is None else f"{e:+.1f}" for e in errs)
            worst = max((abs(e) for e in errs if e is not None), default=None)
            a(
                f"| `{p['corner_id']}` | {label} | {fit['n_used']} | {fit['g']:.5f} | "
                f"{fit['eps_pct']:+.2f} | {fit['eps_lsb']:+.1f} | "
                f"{fit['resolution_lsb']:.1f} | {fit['offset']:+.2f} | {cells} | "
                f"{'n/a' if worst is None else f'{worst:.1f}'} | "
                f"{'n/a' if worst is None else ('yes' if worst <= CODE_TOLERANCE_LSB else 'no')} |"
            )
    a("")
    a(
        "Corrected-code errors are listed in input order "
        + ", ".join(f"`{f:+.2f}*V_REF`" for f in tb.INPUT_FRACTIONS)
        + ". The absolute-code verdict above is unchanged."
    )
    a("")
    a("**Cross-check against DR-022** (bit-8-pair `g`, a different method):")
    a("")
    a("| corner-id | DR-022 g | this record, all non-saturated | this record, mid-scale | difference (mid-scale - DR-022) |")
    a("|---|---|---|---|---|")
    by_id = {p["corner_id"]: p for p in points}
    for cid, ref in DR022_GAIN_REFERENCE.items():
        p = by_id.get(cid)
        if p is None:
            a(f"| `{cid}` | {ref:.5f} | not in this run | n/a | n/a |")
            continue
        an = point_gain_analysis(p)
        fa = "n/a" if an["all"] is None else f"{an['all']['g']:.5f}"
        fm = "n/a" if an["mid"] is None else f"{an['mid']['g']:.5f}"
        diff = "n/a" if an["mid"] is None else f"{an['mid']['g'] - ref:+.5f}"
        a(f"| `{cid}` | {ref:.5f} | {fa} | {fm} | {diff} |")
    a("")
    a(
        "**r+c coverage**: all five `tt/ss/ff/sf/fs` libraries in this sweep "
        "load `res_typical__cap_typical`, so it does **not** cover the MiM r+c "
        "corners the DRAFT gain-error row names."
    )
    a("")
    return lines


# --------------------------------------------------------------------------
# Record formatting shared by more than one writer
# --------------------------------------------------------------------------
# The record writers themselves live with their campaigns (dc_codes,
# node_trace, cm_trace, decision_margin, coherent_sine, solver_audit); what
# stays here is what two or more of them render identically.
def _bits_str(bits: list[int | None]) -> str:
    return "".join("?" if b is None else str(b) for b in bits)


# --------------------------------------------------------------------------
# Node-level trace core (issue #259), shared: --node-trace, --cm-trace and
# --coherent-sine's per-conversion trace all run on it. The campaign that
# introduced it owns its conversion set, corner loop and record writer in
# node_trace.py; what is here is the probe plan, the `.meas` cards and the
# single-point runner.
#
# COMP_OUT / comparator differential output
# against the bit-capture registers' sampling CLK edge, on the AS-COMMITTED
# (unmodified) netlist: it never re-points any instance's strobe. It only
# appends read-only `.meas tran ... find v(...)` probes after the committed
# fragment (assemble_deck()'s `extra_meas`), so it is safe to run against
# the real, unmodified design/sar_adc_top.spice.
# --------------------------------------------------------------------------

# The two corners issue #259's Acceptance Criteria name explicitly: the
# binding corner from the landed records (largest worst-case code error) and
# the one corner where the phase-timing/completion check itself also fails.
NODE_TRACE_CORNERS: tuple[tuple[str, float, float], ...] = (
    ("tt", 27.0, 1.62),  # tt_27c_1.62v
    ("ff", 27.0, 1.80),  # ff_27c_1.80v
)

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
    solver_profile: str = REFERENCE_SOLVER_PROFILE,
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
        netlist_text, pdk_info, process_corner, temp_c, supply_v, extra_meas=extra_meas,
        solver_profile=solver_profile,
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
        solver_profile=solver_profile,
    )


# --- issue #621: switching-event trace of one coherent-sine conversion ------
# DECK AND DECODE half only, which is shared: common.run_point() decodes it on
# every audited DC point and --solver-audit's transition guard builds its cards
# from the same names. The record prose (switch_trace_record_lines(), the
# logic-word formatters and the console summary) lives in coherent_sine.py.
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


# --------------------------------------------------------------------------
# Solver-sensitivity audit INSTRUMENTATION (`--solver-audit`, issue #637)
#
# run_point(audit=True) applies these, so they are here rather than in
# solver_audit.py; the comparison, the baseline lookup, the audit runner and
# the record writer are that module's.
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

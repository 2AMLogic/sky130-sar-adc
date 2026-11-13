"""`--coherent-sine`: SNDR/ENOB by FFT at the baseline corner, with the
optional per-conversion node trace and issue #621 switching-event trace
(issue #603).

Issue #861's split of `run_conversion.py` (see `__init__`). This module holds
the behavioral-ENOB cross-reference, the capture decode and FFT analysis, the
outlier diagnostic, the sine-trace measure cards, the switching-event trace's
RECORD PROSE (`switch_trace_record_lines`, the logic-word formatters and the
console summary), the sine runner and the record writer.

The switching-event trace's DECK AND DECODE core (`switch_trace_names`,
`switch_trace_measure_lines`, `classify_switch_event`, `decode_switch_trace`
and their constants) lives in `common` instead: `common.run_point()` decodes
it on every audited DC point, and `--solver-audit`'s transition guard builds
its own cards from the same names.
"""
from __future__ import annotations

import math
import os
import re
import time
from pathlib import Path

from . import common
from .common import (
    BASELINE_CORNER,
    REFERENCE_SOLVER_PROFILE,
    REPO_ROOT,
    SIM_DIR,
    SWITCH_TRACE_EDGE_WINDOW_NS,
    SWITCH_TRACE_MAX_EDGES,
    SWITCH_TRACE_RAIL_V,
    SWITCH_TRACE_SNAPSHOT_OFFSETS_NS,
    SWITCH_TRACE_STROBE_OFFSETS_NS,
    _node_trace_names,
    _switch_trace_analog_nodes,
    decode_switch_trace,
    is_solver_control,
    node_trace_measure_lines,
    node_trace_plan,
    solver_control_note,
    solver_options_card,
    solver_settings_text,
    switch_trace_measure_lines,
    switch_trace_names,
)
from harness import corners as corners_mod, evidence, measure, pdk
import dynamic_enob
import gen_full_conversion_tb as tb


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


# --------------------------------------------------------------------------
# Switching-event trace (issue #621): the RECORD side
# --------------------------------------------------------------------------
# The deck and decode side of this trace is shared and lives in
# `common` (see its own banner there). What follows renders what that decode
# produced: the flat `.meas` name list the parser is handed, the logic-word
# formatters, the record section and the console summary.
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
    deck = common.assemble_deck(
        netlist_text, pdk_info, process_corner, temp_c, supply_v, fragment=fragment,
        extra_meas=extra_meas or None, solver_profile=solver_profile,
    )
    t0 = time.time()
    log_text = common._run_ngspice(deck, scratch, f"coherent_sine_{cid}", attempts=1)
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
        common.EXPERIMENT_DIR, netlist_text, "corners",
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

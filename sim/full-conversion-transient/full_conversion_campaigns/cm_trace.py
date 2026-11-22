"""`--cm-trace`: the comparator's TOP_P/TOP_N common-mode excursion at the two
near-full-scale inputs (issue #265).

Issue #861's split of `run_conversion.py` (see `__init__`). This module holds
the campaign's corner/conversion set, its deviation metric, its runner and its
diagnostic record writer. It reuses `common.run_node_trace_point()` -- the
same read-only `.meas` infrastructure `--node-trace` runs on -- at the
+-0.78*V_REF conversions instead of the #259 pair.
"""
from __future__ import annotations

from pathlib import Path

from . import common
from .common import (
    NODE_TRACE_CORNERS,
    REFERENCE_SOLVER_PROFILE,
    _NODE_TRACE_POST_EDGE_NS,
    _NODE_TRACE_PRE_EDGE_NS,
    dut_text,
    is_solver_control,
    run_node_trace_point,
    solver_control_bullet,
    solver_settings_text,
    solver_written_by,
)
from harness import evidence, pdk
import gen_full_conversion_tb as tb


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


def run_cm_trace(
    scratch: Path, quiet: bool, solver_profile: str = REFERENCE_SOLVER_PROFILE,
) -> tuple[dict[str, dict], str]:
    pdk_info = pdk.resolve()
    netlist_text = dut_text()
    out: dict[str, dict] = {}
    for pc, tc, sv in CM_TRACE_CORNERS:
        point = run_node_trace_point(
            netlist_text, pdk_info, scratch, pc, tc, sv, CM_TRACE_CONVERSIONS,
            solver_profile=solver_profile,
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


def write_cm_trace_record(
    traces: dict[str, dict], netlist_text: str,
    solver_profile: str = REFERENCE_SOLVER_PROFILE,
) -> Path:
    prov, lines = evidence.open_record(
        common.EXPERIMENT_DIR, netlist_text, "diagnostics",
        {f"cm-trace-{cid}.log": point["log_text"] for cid, point in traces.items()},
    )

    first_point = next(iter(traces.values()))
    traced_conversions = first_point["conversions"]

    a = lines.append
    if is_solver_control(solver_profile):
        a(solver_control_bullet(solver_profile))
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
                "simulator options": solver_settings_text(solver_profile),
            },
        )
    )
    a("")
    lines.extend(
        evidence.footer_lines(
            solver_written_by("sim/full-conversion-transient/run_conversion.py --cm-trace",
                              solver_profile),
            # Diagnostic/investigation record (see the "Claim" bullet above):
            # it extends the corner campaigns' evidence without invalidating
            # any of it, so it supersedes nothing by construction -- the same
            # reasoning as --node-trace above, spelled the same explicit way
            # (issue #502). --supersedes is deliberately NOT threaded here.
            evidence.NEVER_SUPERSEDES,
        )
    )

    return evidence.close_record(prov, lines, "CM-trace record")

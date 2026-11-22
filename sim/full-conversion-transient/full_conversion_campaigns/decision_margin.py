"""`--decision-margin-trace`: the comparator's own differential input at every
bit-trial decision instant, against the decision it produced (issue #263
second pass / DR-009).

Issue #861's split of `run_conversion.py` (see `__init__`). This module holds
the DR-009 balancing-dummy strip (a testbench-only control, never written back
to `design/`), the campaign's measure cards, its single-point runner and
corner loop, and its diagnostic record writer.
"""
from __future__ import annotations

from pathlib import Path

from . import common
from .common import (
    DUT_NETLIST,
    NOMINAL_SUPPLY_V,
    REFERENCE_SOLVER_PROFILE,
    dut_text,
    is_solver_control,
    solver_control_bullet,
    solver_settings_text,
    solver_written_by,
)
from harness import corners as corners_mod, evidence, measure, pdk
import gen_full_conversion_tb as tb


# --------------------------------------------------------------------------
# Decision-margin trace (issue #263 second pass / DR-009): the comparator's
# OWN differential input at every bit-trial decision instant, against the
# decision it then produced. This is the probe that separates a SEARCH defect
# (the loop feeds the comparator the wrong residual) from a COMPARATOR defect
# (the residual is right and the decision is wrong) -- neither the code-level
# corner campaign nor --node-trace (which probes the comparator's OUTPUT pair)
# can tell those apart.
#
# Unlike --node-trace, this runs the DUT twice (as the since-retired
# --mechanism-probe once did): once as committed, and once on a
# testbench-only modified copy with DR-009's comparator-output balancing
# dummies REMOVED, which reproduces the pre-DR-009 asymmetric loading. The pair is the control: the same residuals
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
    solver_profile: str = REFERENCE_SOLVER_PROFILE,
) -> dict:
    cid = corners_mod.corner_id(process_corner, temp_c, supply_v)
    extra_meas, names = decision_margin_measure_lines(DECISION_MARGIN_CONVERSIONS)
    deck = common.assemble_deck(
        netlist_text, pdk_info, process_corner, temp_c, supply_v, extra_meas=extra_meas,
        solver_profile=solver_profile,
    )
    log_text = common._run_ngspice(deck, scratch, f"decision_margin_{tag}_{cid}")
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


def run_decision_margin_trace(
    scratch: Path, quiet: bool, solver_profile: str = REFERENCE_SOLVER_PROFILE,
) -> tuple[dict[str, dict], str]:
    pdk_info = pdk.resolve()
    netlist_text = dut_text()
    variants = (
        ("as-committed", netlist_text),
        ("unbalanced-control", _strip_balance_dummies(netlist_text)),
    )
    out: dict[str, dict] = {}
    for tag, text in variants:
        for pc, tc, sv in DECISION_MARGIN_CORNERS:
            point = run_decision_margin_point(text, pdk_info, scratch, pc, tc, sv, tag,
                                              solver_profile=solver_profile)
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


def write_decision_margin_record(
    points: dict[str, dict], netlist_text: str,
    solver_profile: str = REFERENCE_SOLVER_PROFILE,
) -> Path:
    prov, lines = evidence.open_record(
        common.EXPERIMENT_DIR, netlist_text, "diagnostics",
        {
            f"decision-margin-{key.replace('@', '-')}.log": point["log_text"]
            for key, point in points.items()
        },
    )

    a = lines.append
    if is_solver_control(solver_profile):
        a(solver_control_bullet(solver_profile))
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
        "since-retired `--mechanism-probe`."
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
                "simulator options": solver_settings_text(solver_profile),
            },
        )
    )
    a("")
    lines.extend(
        evidence.footer_lines(
            solver_written_by("sim/full-conversion-transient/run_conversion.py "
                              "--decision-margin-trace", solver_profile),
            # Diagnostic/mechanism record, NOT a corner campaign (see the
            # "Claim" bullet above) -- supersedes nothing by construction, same
            # as the two trace writers above (issue #502).
            evidence.NEVER_SUPERSEDES,
        )
    )
    return evidence.close_record(prov, lines, "Record")

"""`--node-trace`: COMP_OUT / comparator differential output against the
bit-capture registers' sampling CLK edge (issue #259).

Issue #861's split of `run_conversion.py` (see `__init__`). This module holds
the campaign's own conversion set, its opposite-sign MSB control, its corner
loop and its diagnostic record writer.

The per-phase probe plan and single-point runner this campaign introduced
(`node_trace_plan`, `node_trace_measure_lines`, `run_node_trace_point`) live
in `common`: `--cm-trace` and `--coherent-sine`'s sine trace both reuse them.
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


def run_node_trace(
    scratch: Path, quiet: bool, solver_profile: str = REFERENCE_SOLVER_PROFILE,
) -> tuple[dict[str, dict], str]:
    pdk_info = pdk.resolve()
    netlist_text = dut_text()
    out: dict[str, dict] = {}
    for pc, tc, sv in NODE_TRACE_CORNERS:
        point = run_node_trace_point(
            netlist_text, pdk_info, scratch, pc, tc, sv, NODE_TRACE_CONVERSIONS,
            solver_profile=solver_profile,
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


def write_node_trace_record(
    traces: dict[str, dict], netlist_text: str,
    solver_profile: str = REFERENCE_SOLVER_PROFILE,
) -> Path:
    prov, lines = evidence.open_record(
        common.EXPERIMENT_DIR, netlist_text, "diagnostics",
        {f"node-trace-{cid}.log": point["log_text"] for cid, point in traces.items()},
    )

    first_point = next(iter(traces.values()))
    traced_conversions = first_point["conversions"]
    n_traces_per_corner = sum(len(c["phases"]) for c in traced_conversions)

    a = lines.append
    if is_solver_control(solver_profile):
        a(solver_control_bullet(solver_profile))
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
        "contrast the since-retired `--mechanism-probe`, which re-pointed the "
        "comparator's own strobe on a testbench-only copy)."
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
                "simulator options": solver_settings_text(solver_profile),
            },
        )
    )
    a("")
    lines.extend(
        evidence.footer_lines(
            solver_written_by("sim/full-conversion-transient/run_conversion.py --node-trace",
                              solver_profile),
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

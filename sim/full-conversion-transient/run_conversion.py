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
SOLVER CONTROL that never moves records/LATEST and may not --supersedes.
`ngspice-default` alone is also allowed with --corners and the diagnostic
modes, so every pre-DR-023 record stays reproducible (as a control).
`--solver-audit` runs the DC baseline corner under the
reference profile and each control profile, sequentially, and records which
observations (if any) move -- the guard against presenting a
solver-sensitive anomaly as converter behaviour.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

# Only this file's own location, for the sys.path bootstrap. The experiment
# directory every writer resolves against is `common.EXPERIMENT_DIR`, which has
# exactly one owner -- deliberately NOT re-exported here, so a patch aimed at
# the wrong module fails loudly instead of silently missing every caller.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE))

from full_conversion_campaigns import common  # noqa: E402
from full_conversion_campaigns.common import (  # noqa: E402
    BASELINE_CORNER,
    NODE_TRACE_CORNERS,
    REFERENCE_SOLVER_PROFILE,
    REPO_ROOT,
    REPRODUCTION_SOLVER_PROFILE,
    SOLVER_AUDIT_DEFAULT_PROFILES,
    SOLVER_PROFILES,
    dut_text,
    is_solver_control,
    run_campaign,
    solver_options_card,
    solver_settings_text,
)
from full_conversion_campaigns.dc_codes import (  # noqa: E402
    run_mechanism_probe,
    write_record,
)
from full_conversion_campaigns.node_trace import (  # noqa: E402
    run_node_trace,
    write_node_trace_record,
)
from full_conversion_campaigns.cm_trace import (  # noqa: E402
    CM_TRACE_CORNERS,
    run_cm_trace,
    write_cm_trace_record,
)
from full_conversion_campaigns.decision_margin import (  # noqa: E402
    DECISION_MARGIN_CORNERS,
    run_decision_margin_trace,
    write_decision_margin_record,
)
from full_conversion_campaigns.coherent_sine import (  # noqa: E402
    SINE_SOLVER_CONTROL_OPTIONS,
    SINE_SOLVER_CONTROL_PROFILE,
    behavioral_enob_reference,
    format_outlier_summary,
    format_sine_point,
    format_switch_trace_summary,
    run_sine_point,
    sine_point_problems,
    write_sine_record,
)
from full_conversion_campaigns.solver_audit import (  # noqa: E402
    compare_audit_runs,
    latest_baseline_row,
    run_solver_audit,
    write_solver_audit_record,
)
from harness import corners as corners_mod, pdk, toolchain  # noqa: E402
import dynamic_enob  # noqa: E402  (issue #603's stdlib-only FFT/ENOB analyzer)
import gen_full_conversion_tb as tb  # noqa: E402  (this experiment's own testbench constants)

# RE-EXPORTS. Not used by this file -- imported so that `import run_conversion
# as fc` keeps reaching them after issue #861's split, which is how
# sim/supply-impedance-sensitivity/ and sim/reference-drive-budget/ reuse this
# experiment's corner axes, solver policy, deck text and decode. They are a
# convenience surface for those importers, NOT a patch point: a
# mock.patch.object() aimed at one of these names rebinds this module's copy
# and no caller in full_conversion_campaigns/ sees it. Patch the module that
# owns the lookup. `EXPERIMENT_DIR`, `assemble_deck` and `_run_ngspice` are
# deliberately absent for that reason -- read them off `common`.
from full_conversion_campaigns.common import (  # noqa: E402,F401
    FULL_SCALE_CODE,
    NOMINAL_SUPPLY_V,
    PROCESS_CORNERS,
    SUPPLY_TOLERANCE,
    TEMPS_C,
    decode,
    solver_profile_deck_lines,
)
from full_conversion_campaigns.coherent_sine import decode_code_stream  # noqa: E402,F401
from full_conversion_campaigns.decision_margin import (  # noqa: E402,F401
    DECISION_MARGIN_CONVERSIONS,
    decision_margin_measure_lines,
)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
# Everything below is flag resolution and dispatch. Each mode's own
# constants, measure cards, runner and record writer live in that campaign's
# module under full_conversion_campaigns/ (issue #861).
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
        # `ngspice-default` (the settings of every pre-DR-023 record) may run
        # --corners and the diagnostic modes so those records stay
        # reproducible; its records stay labelled controls (write_record and
        # the diagnostic writers never move LATEST under a control profile).
        if on and profile != REPRODUCTION_SOLVER_PROFILE:
            return "", (f"solver profile {profile!r} is a SOLVER CONTROL, allowed only for "
                        f"the baseline-corner DC run and --coherent-sine, not with "
                        f"{', '.join(on)} (only {REPRODUCTION_SOLVER_PROFILE!r}, the "
                        "pre-DR-023 settings, may re-run the grid or a diagnostic, to "
                        "reproduce an old record; promoting a profile to the reference "
                        "policy is a decision-record change)")
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
        "labelled SOLVER CONTROL: never with --supersedes, and its record never "
        "updates records/LATEST. `ngspice-default` may also run --corners and every "
        "diagnostic mode (to reproduce a pre-DR-023 record); the other controls are "
        "allowed for the baseline-corner DC run and --coherent-sine only. Profiles: "
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
        common.EXPERIMENT_DIR / "records" / f"{args.supersedes}.md"
    ).is_file():
        print(
            f"FAIL: --supersedes {args.supersedes}: no such record under "
            f"{os.path.relpath(common.EXPERIMENT_DIR / 'records', REPO_ROOT)}/ -- a "
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
    gate = toolchain.preflight(check)
    if gate is not None:
        return gate

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

        if is_solver_control(solver_profile) and (
            args.node_trace or args.cm_trace or args.decision_margin_trace
        ):
            print(f"SOLVER CONTROL (not reference evidence): {solver_settings_text(solver_profile)}")

        if args.node_trace:
            corner_names = ", ".join(
                corners_mod.corner_id(pc, tc, sv) for pc, tc, sv in NODE_TRACE_CORNERS
            )
            print(f"Node-level trace (issue #259) at {corner_names}:")
            traces, node_trace_netlist_text = run_node_trace(scratch, args.quiet, solver_profile)
            write_node_trace_record(traces, node_trace_netlist_text, solver_profile)
            any_missing = any(point["missing"] for point in traces.values())
            return 1 if any_missing else 0

        if args.cm_trace:
            corner_names = ", ".join(
                corners_mod.corner_id(pc, tc, sv) for pc, tc, sv in CM_TRACE_CORNERS
            )
            print(f"Common-mode trace (issue #265) at {corner_names}:")
            traces, cm_trace_netlist_text = run_cm_trace(scratch, args.quiet, solver_profile)
            write_cm_trace_record(traces, cm_trace_netlist_text, solver_profile)
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
            dm_points, dm_netlist_text = run_decision_margin_trace(
                scratch, args.quiet, solver_profile)
            write_decision_margin_record(dm_points, dm_netlist_text, solver_profile)
            any_missing = any(point["missing"] for point in dm_points.values())
            return 1 if any_missing else 0

        probe = None
        if args.mechanism_probe:
            print("Mechanism probe (baseline corner):")
            probe = run_mechanism_probe(scratch, args.quiet, solver_profile)
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

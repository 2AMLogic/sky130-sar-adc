"""`--solver-audit`: the DC baseline corner run under the reference solver
profile and under each control profile, observation by observation (issue
#637).

Issue #861's split of `run_conversion.py` (see `__init__`). This module holds
the audit's power-delta tolerance, the observation comparison, the
landed-record baseline lookup, the sequential audit runner and the diagnostic
record writer.

The instrumentation the audit asks `common.run_point(audit=True)` to add --
ngspice's `acct` statistics card, their parser, and the transition-guard
`.meas` cards -- lives in `common`, because `run_point()` itself applies them.
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
    CODE_TOLERANCE_LSB,
    NGSPICE_DEFAULT_SOLVER_SETTINGS,
    REFERENCE_SOLVER_PROFILE,
    SOLVER_AUDIT_STATS_CARD,
    SOLVER_STAT_NAMES,
    SWITCH_TRACE_EDGE_WINDOW_NS,
    SWITCH_TRACE_RAIL_V,
    _SOLVER_LOG_PATTERNS,
    _bits_str,
    _power_uw_str,
    dut_text,
    format_point,
    is_solver_control,
    run_point,
    solver_options_card,
    solver_settings_text,
)
from harness import corners as corners_mod, evidence, pdk
import gen_full_conversion_tb as tb


# Relative change in a supply/reference current or total power above which
# the audit calls the power observation "moved". An AUDIT reporting
# tolerance only (not a spec threshold): it is far above the relative
# tolerance any compared profile integrates to (1e-4 for the reference
# policy, 1e-3 for the ngspice-default/gear-only controls), so a change past
# it is not integration noise, and every delta is printed regardless.
SOLVER_AUDIT_POWER_REL_TOL = 0.01


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
    records_dir = common.EXPERIMENT_DIR / "records" if records_dir is None else records_dir
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
        common.EXPERIMENT_DIR, netlist_text, "diagnostics",
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

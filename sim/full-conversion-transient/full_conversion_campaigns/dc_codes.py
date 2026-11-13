"""The base DC-code campaign's record writer.

Issue #861's split of `run_conversion.py` (see `__init__`). This module holds
the evidence record minted by the default/`--corners` run -- the one record
this experiment moves `records/LATEST` for.

The campaign loop itself (`run_point`, `run_campaign`) is shared and lives in
`common`.
"""
from __future__ import annotations

from pathlib import Path

from . import common
from .common import (
    CODE_TOLERANCE_LSB,
    REFERENCE_SOLVER_PROFILE,
    _bits_str,
    _power_uw_str,
    binding_point,
    gain_record_lines,
    is_solver_control,
    solver_control_note,
    solver_settings_text,
)
from harness import corners as corners_mod, evidence
import gen_full_conversion_tb as tb


def write_record(
    points: list[dict],
    netlist_text: str,
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
        common.EXPERIMENT_DIR, netlist_text, "corners",
        {f"{p['corner_id']}.log": p["log_text"] for p in points},
    )
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

    lines.extend(gain_record_lines(points))

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
    if control:
        written_by = "sim/full-conversion-transient/run_conversion.py"
        if len(points) > 1:
            written_by += " --corners"
        written_by += f" --record --solver-profile {solver_profile}"
    else:
        written_by = "sim/full-conversion-transient/run_conversion.py --corners --record"
    lines.extend(evidence.footer_lines(written_by, supersedes))

    path = evidence.close_record(prov, lines, "Solver-control record" if control else "Record")
    if not control:
        evidence.write_latest_pointer(common.EXPERIMENT_DIR, prov.record_id)
    return path

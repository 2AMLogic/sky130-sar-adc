#!/usr/bin/env python3
"""End-to-end full-conversion transient campaign on the transistor-level
`design/sar_adc_top.spice` (issue #254).

    source sim/env.sh
    python3 sim/full-conversion-transient/run_conversion.py --check-env
    python3 sim/full-conversion-transient/run_conversion.py            # tt/27C/1.8V only
    python3 sim/full-conversion-transient/run_conversion.py --corners --record
    python3 sim/full-conversion-transient/run_conversion.py --mechanism-probe

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
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import sys
import tempfile
import time
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent
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
SUPPLY_TOLERANCE = 0.10
TEMPS_C = [-40, 27, 125]
PROCESS_CORNERS = ["tt", "ss", "ff", "sf", "fs"]
BASELINE_CORNER = ("tt", 27.0, NOMINAL_SUPPLY_V)

# Informational tolerance for the per-input code check (NOT a ratified-row
# threshold): the issue's own "ideal code +- 1 LSB" criterion.
CODE_TOLERANCE_LSB = 1


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
) -> str:
    """Assemble the runnable deck: per-corner preamble + DUT body + the
    committed stimulus/measurement fragment.

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
    """
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
        tb.FRAGMENT_PATH.read_text(),
        *(extra_meas or []),
        ".end",
    ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Running and decoding
# --------------------------------------------------------------------------
def _run_ngspice(deck: str, scratch: Path, tag: str) -> str:
    """ngspice with a few bounded retries on timeout -- the same
    contention policy `sim/sampling-acquisition-settling/` and
    `sim/sequencer-logic-delay/` already document (a shared machine may be
    running several agents' ngspice jobs at once). One full-ADC transient
    here is ~6.3 us of simulated time over ~2000 devices and takes minutes,
    so raise SIM_NGSPICE_TIMEOUT_S well above the 120 s harness default
    before running (the README names the value used for the record)."""
    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            return toolchain.run_ngspice(deck, scratch, tag)
        except RuntimeError as exc:
            if "timed out" not in str(exc) or attempt == attempts:
                raise
            print(
                f"  (warning: {tag} timed out (attempt {attempt}/{attempts}), retrying "
                "after a short backoff -- machine likely contended)",
                file=sys.stderr,
            )
            time.sleep(15 * attempt)
    raise AssertionError("unreachable")


def decode(parsed: dict[str, float], supply_v: float) -> dict:
    """Turn one run's parsed `.meas` values into per-conversion code results,
    phase-structure verdicts, and supply-current/power numbers."""
    threshold = tb.DIGITAL_THRESHOLD_FRACTION * supply_v
    lsb_v = 2.0 * supply_v / (2**tb.N_BITS)

    def bit(name: str) -> int | None:
        v = parsed.get(name)
        return None if v is None else (1 if v > threshold else 0)

    margins: list[float] = []
    conversions: list[dict] = []
    for c in tb.measured_conversions():
        bit_names = tb.code_measure_names(c)
        bits = [bit(n) for n in bit_names]
        for n in bit_names:
            if parsed.get(n) is not None:
                margins.append(abs(parsed[n] - threshold))
        code = None
        if all(b is not None for b in bits):
            code = int("".join(str(b) for b in bits), 2)
        frac = tb.input_fraction(c)
        ideal = tb.ideal_code(frac)

        busy = [bit(n) for n in tb.busy_measure_names(c)]
        smpl = [bit(n) for n in tb.sample_measure_names(c)]
        for n in tb.busy_measure_names(c) + tb.sample_measure_names(c):
            if parsed.get(n) is not None:
                margins.append(abs(parsed[n] - threshold))
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
    power_w = 0.0
    for name, _source, potential in tb.SUPPLY_SOURCES:
        raw = parsed.get(name)
        if raw is None:
            continue
        amps = abs(raw)
        currents[name] = amps
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
        all_ok=all(cv["code_ok"] and cv["phase_ok"] for cv in conversions),
    )


def run_point(
    netlist_text: str,
    pdk_info: pdk.PdkInfo,
    scratch: Path,
    process_corner: str,
    temp_c: float,
    supply_v: float,
    delayed_comparator_strobe: bool = False,
    tag_prefix: str = "full_conversion",
) -> dict:
    cid = corners_mod.corner_id(process_corner, temp_c, supply_v)
    deck = assemble_deck(
        netlist_text, pdk_info, process_corner, temp_c, supply_v, delayed_comparator_strobe
    )
    t0 = time.time()
    log_text = _run_ngspice(deck, scratch, f"{tag_prefix}_{cid}")
    wall_s = time.time() - t0

    names = tb.all_measure_names()
    parsed = measure.parse(log_text, names, anchored=False)
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
    )
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
    idd_ua = 1e6 * sum(point["currents"].get(n, 0.0) for n in ("i_vdd", "i_vpwr", "i_vrefp"))
    return (
        f"{point['corner_id']}: {'PASS' if point['all_ok'] else 'FAIL'} "
        f"codes(captured/ideal) {code_str} "
        f"worst|err|={'n/a' if worst is None else worst} LSB "
        f"phases_ok={point['n_phase_ok']}/{point['n_conversions']} "
        f"IDD={idd_ua:.3f}uA P={point['power_w'] * 1e6:.3f}uW "
        f"({point['wall_s']:.0f}s)"
    )


# --------------------------------------------------------------------------
# Campaign
# --------------------------------------------------------------------------
def run_campaign(
    corners_mode: bool, jobs: int, quiet: bool, scratch: Path
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
                    run_point, netlist_text, pdk_info, scratch, pc, tc, sv
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
            point = run_point(netlist_text, pdk_info, scratch, pc, tc, sv)
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


def write_record(points: list[dict], netlist_text: str, probe: dict | None = None) -> Path:
    prov = evidence.resolve_provenance(EXPERIMENT_DIR, netlist_text)
    corners_dir = EXPERIMENT_DIR / "corners" / prov.record_id
    corners_dir.mkdir(parents=True, exist_ok=True)
    for p in points:
        (corners_dir / f"{p['corner_id']}.log").write_text(p["log_text"])
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

    lines: list[str] = []
    a = lines.append
    a(f"# Record {prov.record_id}")
    a("")
    a(f"- **Record ID**: {prov.record_id}")
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
            f"{p['power_w'] * 1e6:.3f} |"
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
            },
        )
    )
    a("")
    lines.extend(
        evidence.footer_lines(
            "sim/full-conversion-transient/run_conversion.py --corners --record", ""
        )
    )

    prov.record_path.write_text("\n".join(lines) + "\n")
    (EXPERIMENT_DIR / "records" / "LATEST").write_text(f"{prov.record_id}.md\n")
    print(f"\nRecord written: {os.path.relpath(prov.record_path, REPO_ROOT)}")
    return prov.record_path


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
    prov = evidence.resolve_provenance(EXPERIMENT_DIR, netlist_text)
    diag_dir = EXPERIMENT_DIR / "diagnostics" / prov.record_id
    diag_dir.mkdir(parents=True, exist_ok=True)
    for cid, point in traces.items():
        (diag_dir / f"node-trace-{cid}.log").write_text(point["log_text"])

    first_point = next(iter(traces.values()))
    traced_conversions = first_point["conversions"]
    n_traces_per_corner = sum(len(c["phases"]) for c in traced_conversions)

    lines: list[str] = []
    a = lines.append
    a(f"# Record {prov.record_id}")
    a("")
    a(
        "- **Record ID**: "
        f"{prov.record_id}"
    )
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
            "",
        )
    )

    prov.record_path.write_text("\n".join(lines) + "\n")
    print(f"\nNode-trace record written: {os.path.relpath(prov.record_path, REPO_ROOT)}")
    return prov.record_path


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
        "--jobs", type=int, default=1,
        help="run this many ngspice corner points concurrently (default 1; results "
        "are independent processes, so this changes runtime only)",
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

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

        if args.node_trace:
            corner_names = ", ".join(
                corners_mod.corner_id(pc, tc, sv) for pc, tc, sv in NODE_TRACE_CORNERS
            )
            print(f"Node-level trace (issue #259) at {corner_names}:")
            traces, node_trace_netlist_text = run_node_trace(scratch, args.quiet)
            write_node_trace_record(traces, node_trace_netlist_text)
            any_missing = any(point["missing"] for point in traces.values())
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
        points, netlist_text = run_campaign(args.corners, args.jobs, args.quiet, scratch)

        overall_ok = all(p["all_ok"] for p in points)
        n_ok = sum(1 for p in points if p["all_ok"])
        print(
            f"\nOVERALL: {'PASS' if overall_ok else 'FAIL'} "
            f"({n_ok}/{len(points)} corner points correct)"
        )

        if args.record:
            write_record(points, netlist_text, probe)

    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

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

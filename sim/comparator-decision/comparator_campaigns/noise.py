"""noise campaign for the comparator-decision driver (issue #613 split of run.py)."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from .common import (
    EXPERIMENT_DIR,
    NOISE_BUDGET_BASELINE_V,
    NOISE_BUDGET_STRETCH_V,
    NOISE_FSTART_HZ,
    NOISE_FSTOP_HZ,
    PROCESS_CORNERS,
    SUPPLY_TOLERANCE,
    TEMPS_C,
    VDD,
    _run,
)
from .regen import (
    _finalize_record,
)
from harness import corners as corners_mod, evidence, measure, pdk

# ---------------------------------------------------------------------------
# noise: input-referred noise via a linearized, loop-broken AC .noise model
# ---------------------------------------------------------------------------
#
# Methodology (documented in full in the decision record): the full latch
# has no stable small-signal operating point once regeneration begins (the
# cross-coupled pair is a positive-feedback loop), so a direct `.noise`
# analysis on the full comparator_core.spice fragment is not meaningful
# (ngspice would either fail to converge on `.op`, or converge to a rail
# where the devices are far outside their useful small-signal region).
# Instead this uses a REDUCED sub-model: the tail + input pair, with the
# devices on the input pair's own drain nodes DIODE-CONNECTED (self-biased)
# so the stage finds its own DC bias point without an external bias-voltage
# guess, and with the positive-feedback cross-coupling removed. This is a
# standard "break the loop for small-signal analysis" technique (generic
# circuit-analysis practice, not specific to any implementation).
#
# ISSUE #175 / DR-004 AMENDMENT A -- WHICH DEVICES THE SUB-MODEL KEEPS, AND
# WHY THAT CHANGED WITH THE TOPOLOGY.
#
# The selection rule, stated once so it can be checked rather than trusted:
# model the phase in which a StrongARM latch's input-referred noise is
# actually generated -- the INTEGRATION phase, from the evaluate edge until
# the latch NMOS pair turns on. During that phase the tail is on and the
# input pair is in saturation, converting Vindiff into the differential
# current that discharges the DIP/DIN nodes; every other device is off (the
# latch NMOS pair sits at Vgs = v(OUT) - v(DI) ~ 0 because both nodes are
# still precharged, the latch PMOS pair likewise, and all four reset PMOS are
# off at CLK = VDD). So the sub-model keeps the tail + input pair and, purely
# to give the DIP/DIN nodes a DC bias that a `.op`-based `.noise` analysis
# needs at all, diode-connects the one VDD-side device already attached to
# each of those nodes -- the DI-node precharge PMOS (XM_RST_DIP/XM_RST_DIN).
#
# Before #175 that same rule selected the cross-coupled latch pair itself,
# because the input pair's drains WERE the OUTP/OUTN nodes and those devices
# were what sat on them. The amendment moved the input-pair drains onto
# DIP/DIN, so the rule now selects the DI-node precharge devices. The
# methodology is unchanged; the device list it picks out changed because the
# netlist did.
#
# TWO ALTERNATIVES WERE MEASURED AND REJECTED (both at tt/27C/1.8V, so the
# rejection is checkable rather than asserted):
#
#  * A LITERAL loop-break of all nine core devices -- keep the latch pairs,
#    diode-connect them in place, leave them in series between OUTP/OUTN and
#    DIP/DIN. This is well-defined but DISQUALIFIED BY ITS OWN OPERATING
#    POINT, not by its answer: the amended stack is four devices tall
#    (VDD -> diode PMOS -> OUT -> diode NMOS -> DI -> input NMOS -> TAIL ->
#    tail NMOS -> GND), which does not fit in 1.8 V, so the whole network
#    settles subthreshold -- v(TAIL) = 4.4 mV, v(DIP) = 21.9 mV, i.e. the
#    input pair is off rather than saturated. Its 8.6921 mV rms single-ended
#    result describes a bias point the comparator never occupies.
#  * The same literal loop-break PLUS diode-connected DI precharge devices to
#    restore the bias (all eleven devices). This DOES bias sensibly
#    (v(TAIL) = 28.7 mV, v(DIP) = 383.1 mV -- the input pair saturated,
#    matching the model actually used) and gives 1.0867 mV rms single-ended.
#    It is rejected on the selection rule above rather than on that number:
#    it forces the latch NMOS pair to CONDUCT, which is exactly what they do
#    not do during integration, so its extra noise term is not "the
#    regenerative contribution measured properly" -- it is a different
#    artifact, and a larger departure from the modelled phase than the
#    omission it purports to fix. The genuine regenerative-noise gap stays
#    open, named in DR-004's Open items exactly as before.
#
# Recording the rejected numbers here is deliberate: the model this file uses
# yields a SMALLER figure than one of the alternatives, so the reason for the
# choice must be inspectable. It is the operating-point/phase argument above,
# and it would have selected the same model had the numbers come out the
# other way round.
#
# The AC stimulus is single-ended (Vinp gets AC=1, Vinn stays pure DC), and
# ngspice's `inoise_total` (referred back through Vinp) is reported as a
# SINGLE-ENDED input-referred rms noise voltage. For a symmetric
# differential pair with uncorrelated per-side noise contributions, the
# standard diff-pair noise-doubling result gives
# differential-input-referred variance = 2x the single-ended value, i.e.
# rms_differential = sqrt(2) * rms_single_ended -- this repo does not derive
# that identity from scratch here; it is applied as a named, flagged
# approximation and stated as such in the record, per DR-003 Item 4's own
# deferral of the noise-verification methodology to "the future comparator-
# topology DR."

VBIAS_NOTE = (
    "reduced sub-model of the INTEGRATION phase (DR-004 Amendment A, issue "
    "#175): tail + input pair, with the DI-node precharge PMOS pair "
    "diode-connected (self-biased) as the loads on the input pair's own drain "
    "nodes DIP/DIN, and the cross-coupled latch pairs omitted because they are "
    "off (Vgs ~ 0) until regeneration begins; CLK held at VDD (steady evaluate "
    "bias, tail on); noise taken at v(DIP,DIN)"
)


def _noise_deck(info: pdk.PdkInfo, corner: str, temp_c: float, supply_v: float = VDD) -> str:
    vcm = supply_v / 2.0
    lines = [
        f"* comparator-decision input-referred noise ({VBIAS_NOTE}) "
        f"corner={corner} temp={temp_c}C supply={supply_v}V (issue #54/#28)",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        f".param vdd_val = {supply_v}",
        "",
        "Vdd VDD 0 dc {vdd_val}",
        "Vclkfix CLK 0 dc {vdd_val}",
        f"Vinp VINP 0 dc {vcm} AC 1",
        f"Vinn VINN 0 dc {vcm}",
        "",
        "XM_TAIL TAIL CLK GND GND sky130_fd_pr__nfet_01v8 L=0.5 W=8 nf=1",
        "XM_INN DIP VINN TAIL GND sky130_fd_pr__nfet_01v8 L=0.5 W=4 nf=1",
        "XM_INP DIN VINP TAIL GND sky130_fd_pr__nfet_01v8 L=0.5 W=4 nf=1",
        "XM_RST_DIP DIP DIP VDD VDD sky130_fd_pr__pfet_01v8 L=0.5 W=4 nf=1",
        "XM_RST_DIN DIN DIN VDD VDD sky130_fd_pr__pfet_01v8 L=0.5 W=4 nf=1",
        "",
        ".control",
        # sim/spiceinit sets 'option klu' repo-wide for corner-sweep speed,
        # but ngspice's KLU solver does not support .noise analysis
        # ("Error: Noise simulation is not (yet) supported with 'option
        # KLU'. Use 'option sparse' instead.", verified empirically). This
        # switches the solver back to SPARSE for THIS invocation only (a
        # runtime .control command, not an edit to the shared spiceinit
        # file) -- op-point/transient results elsewhere in this repo are
        # unaffected.
        "option sparse",
        "op",
        "print v(TAIL) v(DIP) v(DIN)",
        f"noise v(dip,din) Vinp dec 20 {NOISE_FSTART_HZ:g} {NOISE_FSTOP_HZ:g} 20",
        "print inoise_total onoise_total",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


@dataclass
class NoiseResult:
    single_ended_rms_v: float
    differential_rms_v: float
    op_tail_v: float
    # The sub-model's own output nodes. Before DR-004 Amendment A (issue #175)
    # the input pair's drains were OUTP/OUTN; the amendment moved them to the
    # internal nodes DIP/DIN, which are what this deck now biases, probes and
    # takes `noise v(dip,din)` across.
    op_dip_v: float
    op_din_v: float
    log_text: str
    corner: str
    temp_c: float
    supply_v: float = VDD


def run_noise(
    corner: str = "tt", temp_c: float = 27.0, supply_v: float = VDD, quiet: bool = False,
) -> NoiseResult:
    info = pdk.resolve_or_raise()
    with tempfile.TemporaryDirectory(prefix="comparator-decision-noise-") as scratch:
        scratch_dir = Path(scratch)
        log_name = "noise"
        deck = _noise_deck(info, corner, temp_c, supply_v)
        log_text = _run(deck, scratch_dir, log_name)

    parsed = measure.parse(log_text, ["inoise_total", "onoise_total", "v(tail)", "v(dip)", "v(din)"])
    # ngspice's `print` echoes lowercased vector names for v(...) forms;
    # measure.parse's regex requires the LHS to look like an identifier
    # (letters/digits/underscore), which `v(tail)` does not match (parens)
    # -- so parse those three directly here instead of relying on
    # measure.parse for them.
    op_tail = op_dip = op_din = float("nan")
    for line in log_text.splitlines():
        s = line.strip()
        if s.startswith("v(tail)"):
            op_tail = float(s.split("=")[1])
        elif s.startswith("v(dip)"):
            op_dip = float(s.split("=")[1])
        elif s.startswith("v(din)"):
            op_din = float(s.split("=")[1])
    single_ended = parsed.get("inoise_total", float("nan"))
    differential = single_ended * (2 ** 0.5)
    if not quiet:
        print(f"  op: TAIL={op_tail:.4f}V DIP={op_dip:.4f}V DIN={op_din:.4f}V")
        print(f"  inoise_total (single-ended) = {single_ended * 1000:.4f} mV rms")
        print(f"  differential estimate (x sqrt(2)) = {differential * 1000:.4f} mV rms")
    result = NoiseResult(
        single_ended_rms_v=single_ended, differential_rms_v=differential,
        op_tail_v=op_tail, op_dip_v=op_dip, op_din_v=op_din,
        log_text=log_text, corner=corner, temp_c=temp_c, supply_v=supply_v,
    )
    return result


def run_noise_corners(quiet: bool = False) -> list[NoiseResult]:
    """Full ratified-corner-set sweep of run_noise() (issue #28): the OAT PVT
    grid built from the ratified corner set (spec/target-spec.md's "Numeric
    rows -- RATIFIED 2026-08-19" section: -40/27/125C, +-10% supply, sky130
    process corners), substantiating the ratified comparator input-referred
    noise-budget row rather than the single nominal-point record alone."""
    pdk.resolve_or_raise()
    grid = corners_mod.ratified_oat_grid(VDD, SUPPLY_TOLERANCE, PROCESS_CORNERS, TEMPS_C)
    results: list[NoiseResult] = []
    for process_corner, temp_c, supply_v in grid:
        result = run_noise(corner=process_corner, temp_c=temp_c, supply_v=supply_v, quiet=quiet)
        results.append(result)
        if not quiet:
            cid = corners_mod.corner_id(process_corner, temp_c, supply_v)
            print(f"  {cid}: differential noise = {result.differential_rms_v * 1000:.4f} mV rms")
    return results


def write_noise_campaign_evidence(
    results: list[NoiseResult], note: str = "",
    supersedes: str = "",
) -> Path:
    info = pdk.resolve()
    netlist_text = _noise_deck(info, "tt", 27.0, VDD)
    raw_logs: dict[str, str] = {}
    for r in results:
        cid = corners_mod.corner_id(r.corner, r.temp_c, r.supply_v)
        raw_logs[f"{cid}.log"] = r.log_text
    prov, lines = evidence.open_record(EXPERIMENT_DIR, netlist_text, "corners", raw_logs)
    record_path = prov.record_path
    a = lines.append

    binding = max(results, key=lambda r: r.differential_rms_v)
    binding_cid = corners_mod.corner_id(binding.corner, binding.temp_c, binding.supply_v)
    overall_ok = binding.differential_rms_v <= NOISE_BUDGET_BASELINE_V
    meets_stretch = binding.differential_rms_v <= NOISE_BUDGET_STRETCH_V

    process_corners_run = sorted({r.corner for r in results})
    temps_run = sorted({r.temp_c for r in results})
    supplies_run = sorted({r.supply_v for r in results})

    a(
        "- **Claim**: `spec/target-spec.md#numeric-rows--ratified-2026-08-19` -- "
        "Comparator input-referred noise `<=1.0148 mV rms` (baseline, ENOB>9.0) / "
        "`<=0.5859 mV rms` (stretch, ENOB>9.5) (RATIFIED, DR-003 via #27). Measures "
        "design/comparator.sch's (reduced sub-model, see Methodology) differential "
        "input-referred noise across the full ratified corner set and grades it "
        "against the ratified baseline threshold -- a genuine pass/fail against a "
        "ratified spec/target-spec.md line, distinct from the prior single-point "
        "nominal-corner record (informational at the time it was written, DR-003 "
        "then being only `proposed`)."
    )
    a("- **Netlist provenance**: schematic, reduced sub-model (see Methodology)")
    a(
        corners_mod.corner_matrix_summary_line(
            process_corners_run, temps_run, supplies_run, len(results)
        )
    )
    a(
        f"- **Noise methodology**: `ac-based`, integration bandwidth "
        f"{NOISE_FSTART_HZ:g}Hz-{NOISE_FSTOP_HZ:g}Hz (see sim/comparator-decision/run.py "
        "module docstring for the bandwidth choice's derivation from the "
        "regen-time-vs-Vindiff record). REDUCED SUB-MODEL, not the full "
        f"comparator_core.spice fragment: {VBIAS_NOTE}. This is a named, "
        "flagged simplification (excludes the cross-coupled latch pair's "
        "own regenerative-phase noise contribution) -- see "
        "spec/decision-records/DR-004-comparator-topology-and-noise-budget.md "
        "for the full derivation and its limitations. The EXCLUSION is unchanged "
        "from every prior record in this experiment -- it is a standing "
        "methodology limitation, not something this corner campaign relaxes to "
        "force a pass. The DEVICE LIST implementing it did change with DR-004 "
        "Amendment A (issue #175): the sub-model's selection rule picks the "
        "VDD-side devices sitting on the input pair's own drain nodes, which the "
        "amendment moved from OUTP/OUTN to DIP/DIN. See that amendment's section "
        "A2 for the rule, and for the two alternative sub-models measured and "
        "rejected against it."
    )
    if note:
        a(f"- **Note**: {note}")
    a(
        f"- **Binding corner**: `{binding_cid}` (worst-case differential "
        f"input-referred noise = {binding.differential_rms_v * 1000:.4f} mV rms) -- "
        "recorded regardless of pass/fail, per sim/README.md's per-row "
        "binding-corner convention."
    )
    a(
        f"- **Overall**: {'PASS' if overall_ok else 'FAIL'} vs. the ratified baseline "
        f"threshold ({NOISE_BUDGET_BASELINE_V * 1000:.4f} mV rms); "
        f"{'also meets' if meets_stretch else 'does NOT meet'} the stretch threshold "
        f"({NOISE_BUDGET_STRETCH_V * 1000:.4f} mV rms) at the binding corner."
    )
    a("")
    a("## Per-corner differential input-referred noise")
    a("")
    a("| corner-id | single-ended noise (mV rms) | differential noise (mV rms) | vs. baseline (<=1.0148 mV) |")
    a("|---|---|---|---|")
    for r in sorted(results, key=lambda r: -r.differential_rms_v):
        cid = corners_mod.corner_id(r.corner, r.temp_c, r.supply_v)
        ok = r.differential_rms_v <= NOISE_BUDGET_BASELINE_V
        a(
            f"| `{cid}` | {r.single_ended_rms_v * 1000:.4f} | {r.differential_rms_v * 1000:.4f} | "
            f"{'PASS' if ok else 'FAIL'} |"
        )
    a("")
    a(
        "No spec row is relaxed to make this result pass or fail -- the ratified "
        "baseline/stretch thresholds above are quoted verbatim from "
        "spec/target-spec.md, per CLAUDE.md's 'do not relax a spec line to make a "
        "result pass' rule."
    )
    a("")
    a("- **Data provenance**: model-card-monte-carlo (sky130A BSIM4 device noise "
      "models via ngspice's `.noise` analysis; no literature/foundry-doc noise figure used)")
    a("")
    return _finalize_record(
        lines, record_path, prov.pdk_line, prov.ng_version, prov.netlist_sha,
        "noise-corners", supersedes=supersedes,
    )


def write_noise_evidence(
    result: NoiseResult, note: str = "", supersedes: str = "",
) -> Path:
    info = pdk.resolve()
    netlist_text = _noise_deck(info, result.corner, result.temp_c)
    prov, lines = evidence.open_record(
        EXPERIMENT_DIR, netlist_text, "corners", {"noise.log": result.log_text}
    )
    record_path = prov.record_path
    a = lines.append
    a(
        "- **Claim**: pending #1/#27 -- measures design/comparator.sch's "
        "(reduced sub-model, see below) input-referred noise, compared "
        "INFORMATIONALLY against "
        "spec/decision-records/DR-003-numeric-spec-derivation.md Item 4's "
        "provisional budget (<=1.0148 mV rms baseline / <=0.5859 mV rms "
        "stretch) -- DR-003 is itself `proposed`, not ratified, so this is "
        "not a pass/fail against a ratified line."
    )
    a("- **Netlist provenance**: schematic, reduced sub-model (see Methodology)")
    a(f"- **Corner matrix run**: process=['{result.corner}'], temperature_c=[{result.temp_c}], supply_v=[{VDD}] (1 point)")
    a(
        f"- **Noise methodology**: `ac-based`, integration bandwidth "
        f"{NOISE_FSTART_HZ:g}Hz-{NOISE_FSTOP_HZ:g}Hz (see sim/comparator-decision/run.py "
        "module docstring for the bandwidth choice's derivation from the "
        "regen-time-vs-Vindiff record). REDUCED SUB-MODEL, not the full "
        f"comparator_core.spice fragment: {VBIAS_NOTE}. This is a named, "
        "flagged simplification (excludes the cross-coupled latch pair's "
        "own regenerative-phase noise contribution) -- see "
        "spec/decision-records/DR-004-comparator-topology-and-noise-budget.md "
        "for the full derivation and its limitations."
    )
    if note:
        a(f"- **Note**: {note}")
    a("- **Overall**: measured value recorded (informational, not pass/fail -- see Claim)")
    a("")
    a("## Measured value(s)")
    a("")
    a("| Quantity | Value | Corner condition |")
    a("|---|---|---|")
    a(f"| Op point: v(TAIL) | {result.op_tail_v:.4f} V | {result.corner}/{result.temp_c}C/{VDD}V |")
    a(f"| Op point: v(DIP)=v(DIN) | {result.op_dip_v:.4f} V | {result.corner}/{result.temp_c}C/{VDD}V |")
    a(
        f"| Single-ended input-referred noise (`inoise_total`, referred through Vinp) | "
        f"{result.single_ended_rms_v * 1000:.4f} mV rms | {result.corner}/{result.temp_c}C/{VDD}V |"
    )
    a(
        f"| **Differential input-referred noise estimate** (`sqrt(2) x` single-ended, "
        f"diff-pair noise-doubling approximation) | **{result.differential_rms_v * 1000:.4f} mV rms** | "
        f"{result.corner}/{result.temp_c}C/{VDD}V |"
    )
    a("")
    a(
        f"DR-003 Item 4's provisional budget: <=1.0148 mV rms (baseline, ENOB>9.0) / "
        f"<=0.5859 mV rms (stretch, ENOB>9.5). This record's differential estimate "
        f"({result.differential_rms_v * 1000:.4f} mV rms) is reported as-is, without "
        "adjusting the topology or sizing to force a particular pass/fail outcome, "
        "per CLAUDE.md's 'no claim without a testbench' / 'do not relax a spec line "
        "to make a result pass' rules."
    )
    a("")
    a("- **Data provenance**: model-card-monte-carlo (sky130A BSIM4 device noise "
      "models via ngspice's `.noise` analysis; no literature/foundry-doc noise figure used)")
    a("")
    return _finalize_record(
        lines, record_path, prov.pdk_line, prov.ng_version, prov.netlist_sha,
        "noise", supersedes=supersedes,
    )

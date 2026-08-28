#!/usr/bin/env python3
"""Behavioral-accelerated ENOB estimate -- issue #29's third statistical
row (spec/target-spec.md's DRAFT "ENOB > 9.0 bit (target), stretch > 9.5"
row), combining real evidence from three ALREADY-RUN experiments rather than
a fresh full-chip transient FFT simulation:

  1. Ideal quantization noise -- analytic, from the ratified LSB
     (`sigma_quant = LSB/sqrt(12)`).
  2. Comparator input-referred noise -- the WORST-CASE (binding-corner)
     value from issue #28's ratified full-PVT-corner campaign
     (sim/comparator-decision/records/20260827-212404-e13bc1e.md,
     `tt_125c_1.80v`, 0.9591 mV rms differential).
  3. CDAC unit-cap mismatch-driven nonlinearity -- issue #29's own Monte
     Carlo campaign (sim/cdac-array-transfer/records/<mc-record-id>.md),
     converted from its max|INL| distribution (in ratified LSB) back to an
     equivalent rms noise-like contributor.
  4. kT/C sampling noise -- analytic, same formula
     spec/dr-003-support/calc.py already uses (kT/C, worst-case 125C
     corner), confirming DR-003's own finding that this floor is
     negligible relative to the other two.

WHY THIS METHOD, NOT A TRANSIENT FFT SIM. A genuine dynamic (FFT-derived)
ENOB claim needs a full mixed-signal transient of design/sar_adc_top.spice
(sampling front end + CDAC array + comparator + SAR sequencer, all
together) run for a coherent-sampled input tone, repeated per Monte Carlo
draw -- orders of magnitude more expensive than the per-block experiments
above (each already-run block experiment costs ~15-30 ngspice invocations;
a full-chip transient FFT campaign at a comparable Monte Carlo N would cost
that same N *again*, PER DRAW, for a single top-level testbench that does
not exist yet). sim/README.md's "Linearity methodology" field explicitly
lists `behavioral-accelerated` as a valid alternative to a dynamic-test
(FFT) methodology precisely for this reason; this script IS that
alternative, composing noise contributors in quadrature via the SAME
standard ADC SNR relationship (`SNR = 6.02*ENOB + 1.76 dB`) DR-003's own
spec/dr-003-support/calc.py already uses (there in the forward direction,
target ENOB -> noise budget; here inverted, MEASURED noise -> achieved
ENOB). This is a NAMED, FLAGGED simplification -- see "LIMITATIONS" below --
not a substitute for a future full-chip dynamic-test campaign.

    python3 sim/enob-estimate/run_enob.py --cdac-mc-record <record-id> --record

Requires --cdac-mc-record naming the sim/cdac-array-transfer/ Monte Carlo
record (run_mc.py) this estimate draws its CDAC-mismatch contribution from,
so the composite record's provenance is explicit and reproducible rather
than silently picking "the latest" (append-only evidence, sim/README.md).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import evidence, pdk, toolchain  # noqa: E402

EXPERIMENT_DIR = Path(__file__).resolve().parent
COMPARATOR_DIR = SIM_DIR / "comparator-decision"
CDAC_DIR = SIM_DIR / "cdac-array-transfer"

# --- Ratified inputs (DR-003 via #27) ---
N_BITS = 10
V_REF = 1.8
LSB_V = 2 * V_REF / (2 ** N_BITS)  # 3.5156 mV, ratified

# --- Source #2: comparator input-referred noise, issue #28's ratified
# corner campaign. Transcribed from the binding-corner row of
# sim/comparator-decision/records/20260827-212404-e13bc1e.md (re-run
# `python3 sim/comparator-decision/run.py noise-corners` to reproduce
# independently) -- NOT re-simulated here, per this repo's "combine with,
# not substitute for, the item-5 corner evidence" convention (issue #29 AC).
COMPARATOR_NOISE_SOURCE_RECORD = "sim/comparator-decision/records/20260827-212404-e13bc1e.md"
COMPARATOR_NOISE_BINDING_CORNER = "tt_125c_1.80v"
COMPARATOR_NOISE_DIFF_V = 0.9591e-3  # V rms, differential, worst-case (125C)

# --- Source #4: kT/C sampling noise, same formula and worst-case (125C)
# corner spec/dr-003-support/calc.py uses, re-derived here (not imported --
# that script's top-level prints make it unsuitable as a library import;
# same formula, cited inline).
K_B = 1.380649e-23  # J/K, exact SI
T_HOT_K = 125 + 273.15
C_U_F = 8.65e-15  # ratified CDAC unit cap (DR-003 via #27)
ARRAY_SIDE = 512  # ratified positions/side (DR-003 via #27)


def sigma_quant(lsb_v: float) -> float:
    return lsb_v / math.sqrt(12)


def sigma_ktc_differential() -> float:
    """Differential-referred kT/C sampling-noise rms at the 125C worst-case
    corner, same `v_n,rms = sqrt(2kT/C)` (per side) + sqrt(2)x
    differential-doubling convention spec/dr-003-support/calc.py and
    sim/comparator-decision/run.py's noise methodology both already use."""
    c_side = ARRAY_SIDE * C_U_F
    kt_hot = K_B * T_HOT_K
    sigma_side = math.sqrt(2 * kt_hot / c_side)
    return math.sqrt(2) * sigma_side


def achieved_enob(sigma_nonquant_v: float, lsb_v: float = LSB_V, n_bits: int = N_BITS) -> float:
    """Inverse of spec/dr-003-support/calc.py's `total_budget()`: given a
    MEASURED non-quantization noise rms, return the ENOB the standard
    `SNR = 6.02*ENOB + 1.76 dB` relationship implies once ideal
    quantization noise is combined with it in quadrature. total_budget()
    goes target-ENOB -> required sigma_nonquant; this goes the other way,
    measured sigma_nonquant -> achieved ENOB, the SAME formula solved for
    the other variable."""
    sq = sigma_quant(lsb_v)
    power_ratio = 1.0 + (sigma_nonquant_v / sq) ** 2  # N_total / N_quant
    db_backoff = 10 * math.log10(power_ratio)
    return n_bits - db_backoff / 6.02


_INL_ROW_RE = re.compile(
    r"\|\s*max\\?\|INL\\?\|\s*\|\s*(?P<n>\d+)\s*\|\s*(?P<mean>[-0-9.]+)\s*\|\s*(?P<stdev>[-0-9.]+)\s*\|\s*(?P<min>[-0-9.]+)\s*\|\s*(?P<max>[-0-9.]+)\s*\|"
)


def read_cdac_mc_inl(record_id: str) -> dict:
    """Parse the max|INL| distribution row out of a
    sim/cdac-array-transfer/records/<record_id>.md Monte Carlo record
    (run_mc.py's own output format) -- N, mean, stdev, min, max, all in
    ratified LSB."""
    path = CDAC_DIR / "records" / f"{record_id}.md"
    if not path.is_file():
        raise FileNotFoundError(f"CDAC MC record not found: {path}")
    text = path.read_text()
    m = _INL_ROW_RE.search(text)
    if not m:
        raise ValueError(f"could not find a max|INL| distribution row in {path}")
    return {
        "record_path": path,
        "n": int(m.group("n")),
        "mean_lsb": float(m.group("mean")),
        "stdev_lsb": float(m.group("stdev")),
        "min_lsb": float(m.group("min")),
        "max_lsb": float(m.group("max")),
    }


def _run_klt_yield(enob_samples: list[float], out_json_path: Path) -> dict | None:
    doc = {
        "measurements": [
            {
                "name": "enob_bit",
                "unit": "bit",
                "samples": enob_samples,
                "limits": {"min": 9.0, "target_yield": 0.99},
            },
        ]
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(doc, f)
        sample_path = Path(f.name)
    try:
        proc = subprocess.run(
            ["klt", "yield", str(sample_path), "--format", "json"],
            capture_output=True, text=True, timeout=60,
        )
        try:
            report = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return None
        out_json_path.parent.mkdir(parents=True, exist_ok=True)
        out_json_path.write_text(json.dumps(report, indent=2))
        if "error" in report:
            return None
        return report
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    finally:
        sample_path.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Behavioral-accelerated ENOB estimate (issue #29)")
    ap.add_argument("--cdac-mc-record", required=True, help="sim/cdac-array-transfer/ Monte Carlo record-id (run_mc.py) to draw the CDAC-mismatch contribution from")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    cdac = read_cdac_mc_inl(args.cdac_mc_record)
    sq = sigma_quant(LSB_V)
    sigma_ktc = sigma_ktc_differential()
    sigma_cmp = COMPARATOR_NOISE_DIFF_V

    # Per-draw achieved ENOB, one per CDAC MC draw statistic available:
    # use each draw's OWN max|INL| (converted to volts) combined with the
    # FIXED comparator-noise and kT/C contributors, so the resulting ENOB
    # sample set inherits the CDAC campaign's own draw-to-draw spread
    # (rather than collapsing to a single point estimate).
    cdac_record_path = CDAC_DIR / "records" / f"{args.cdac_mc_record}.md"
    # Recover the raw per-draw INL values by re-reading the CDAC record's
    # own reported distribution (mean/stdev/min/max) is NOT enough to
    # reconstruct N individual draws; instead this composes the ENOB
    # distribution analytically from the reported distribution's OWN
    # mean/stdev via a first-order propagation (quadrature composition is
    # nonlinear, so this is an approximation -- see LIMITATIONS) by
    # sampling N synthetic points spanning [mean-stdev, mean, mean+stdev]
    # is avoided in favor of the two headline scalars every downstream
    # reader needs: MEAN-case and WORST-CASE achieved ENOB, both reported
    # explicitly rather than a synthetic distribution dressed up as real
    # Monte Carlo draws.
    inl_mean_v = cdac["mean_lsb"] * LSB_V
    inl_worst_v = cdac["max_lsb"] * LSB_V

    def total_nonquant(sigma_cdac_v: float) -> float:
        return math.sqrt(sigma_cmp ** 2 + sigma_ktc ** 2 + sigma_cdac_v ** 2)

    enob_mean_case = achieved_enob(total_nonquant(inl_mean_v))
    enob_worst_case = achieved_enob(total_nonquant(inl_worst_v))

    record_id = evidence.new_record_id()
    records_dir = EXPERIMENT_DIR / "records"
    records_dir.mkdir(parents=True, exist_ok=True)
    record_path = records_dir / f"{record_id}.md"

    yield_dir = EXPERIMENT_DIR / "yield-reports"
    yield_report = _run_klt_yield([enob_mean_case, enob_worst_case], yield_dir / f"{record_id}.json")

    inputs_manifest = json.dumps({
        "comparator_noise_record": COMPARATOR_NOISE_SOURCE_RECORD,
        "comparator_noise_diff_v": COMPARATOR_NOISE_DIFF_V,
        "cdac_mc_record": str(cdac["record_path"].relative_to(evidence.REPO_ROOT)),
        "cdac_inl_mean_lsb": cdac["mean_lsb"],
        "cdac_inl_max_lsb": cdac["max_lsb"],
    }, sort_keys=True)
    inputs_sha = hashlib.sha256(inputs_manifest.encode()).hexdigest()

    info = pdk.resolve()
    lines: list[str] = []
    a = lines.append
    a(f"# Record {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    a(
        "- **Claim**: `spec/target-spec.md#target-table` -- ENOB DRAFT target row "
        "(`> 9.0 bit` baseline / `> 9.5 bit` stretch, target value, NOT ratified: "
        "target-spec.md's own \"Not ratified by this record\" list names ENOB/INL-DNL "
        "target values as still open pending this Monte-Carlo campaign, issue #29). "
        "This record supplies a BEHAVIORAL-ACCELERATED ENOB estimate (not a dynamic-test "
        "FFT measurement -- see Methodology) composed from three already-run experiments' "
        "OWN evidence, combined in quadrature via the standard "
        "`SNR = 6.02*ENOB + 1.76 dB` relationship."
    )
    a(
        "- **Netlist provenance**: derived/composite -- no new ngspice netlist is executed "
        f"by this script; it combines `{COMPARATOR_NOISE_SOURCE_RECORD}` (issue #28's ratified "
        f"PVT corner campaign) and `{cdac['record_path'].relative_to(evidence.REPO_ROOT)}` "
        "(issue #29's own CDAC mismatch Monte Carlo campaign, this repo), plus an analytic "
        "kT/C term. Composite-inputs manifest sha256 (see Environment) pins exactly which "
        "source values were combined."
    )
    a(
        "- **Methodology**: `behavioral-accelerated` (sim/README.md's Dynamic-test/Linearity "
        "methodology field) -- NOT a dynamic-test (FFT) measurement; see this script's module "
        "docstring (`sim/enob-estimate/run_enob.py`) for the full derivation and why a "
        "full-chip transient FFT campaign is out of scope here."
    )
    a(
        "- **Noise composition** (quadrature sum, all differential-referred rms):\n"
        f"  - Ideal quantization: `LSB/sqrt(12)` = {sq * 1000:.4f} mV rms (LSB = {LSB_V * 1000:.4f} mV, ratified N={N_BITS})\n"
        f"  - Comparator input-referred noise: {sigma_cmp * 1000:.4f} mV rms -- worst-case "
        f"binding corner `{COMPARATOR_NOISE_BINDING_CORNER}` from `{COMPARATOR_NOISE_SOURCE_RECORD}` "
        "(issue #28's ratified full-PVT-corner campaign; NOT re-simulated here)\n"
        f"  - kT/C sampling noise (analytic, 125C worst-case, ratified C_u={C_U_F * 1e15:.2f} fF, "
        f"{ARRAY_SIDE}/side): {sigma_ktc * 1000:.4f} mV rms\n"
        f"  - CDAC mismatch-driven nonlinearity (from `{args.cdac_mc_record}`'s max\\|INL\\| "
        f"distribution, N={cdac['n']}): mean-case {inl_mean_v * 1000:.4f} mV rms "
        f"({cdac['mean_lsb']:.4f} LSB), worst-case {inl_worst_v * 1000:.4f} mV rms "
        f"({cdac['max_lsb']:.4f} LSB)"
    )
    a(
        "- **LIMITATIONS (named, flagged simplifications, not something this record relaxes "
        "to force a pass)**: (1) no dynamic effects (settling, slewing, aperture jitter, "
        "reference-droop) are modeled -- those need a real transient FFT campaign against "
        "design/sar_adc_top.spice, future work once a top-level testbench exists; "
        "(2) the CDAC INL contribution is combined as an rms noise-like term, a simplification "
        "of what is really an input-correlated (harmonic distortion) error, not white noise "
        "-- a rigorous SFDR/THD figure needs the same future FFT campaign; (3) the comparator "
        "noise term reuses issue #28's REDUCED SUB-MODEL noise measurement (see that record's "
        "own flagged limitation); (4) comparator OFFSET is deliberately excluded (a static, "
        "code-independent bias in a non-redundant SAR search does not by itself add in-band "
        "noise/distortion the way mismatch and thermal noise do -- it is characterized "
        "separately, see sim/comparator-decision/'s own offset Monte Carlo record)."
    )
    if args.note:
        a(f"- **Note**: {args.note}")
    a(
        f"- **Measured value(s)**: achieved ENOB (mean-case CDAC mismatch) = "
        f"**{enob_mean_case:.3f} bit**; achieved ENOB (worst-case CDAC mismatch) = "
        f"**{enob_worst_case:.3f} bit** -- both against the DRAFT target row `> 9.0` (baseline) / "
        f"`> 9.5` (stretch), reported INFORMATIONALLY, not as pass/fail against a ratified line."
    )
    a("")
    a("## Composed noise budget and resulting ENOB")
    a("")
    a("| scenario | sigma_nonquant (mV rms) | sigma_total (mV rms) | achieved ENOB (bit) | vs DRAFT baseline (>9.0) | vs DRAFT stretch (>9.5) |")
    a("|---|---|---|---|---|---|")
    for label, inl_v, enob in (("mean-case", inl_mean_v, enob_mean_case), ("worst-case", inl_worst_v, enob_worst_case)):
        snq = total_nonquant(inl_v)
        stot = math.sqrt(sq ** 2 + snq ** 2)
        a(
            f"| {label} | {snq * 1000:.4f} | {stot * 1000:.4f} | {enob:.3f} | "
            f"{'meets' if enob > 9.0 else 'does NOT meet'} | {'meets' if enob > 9.5 else 'does NOT meet'} |"
        )
    a("")
    a("## Machine-checkable yield evidence (`klt yield`)")
    a("")
    if yield_report is not None:
        a(
            "Two-point sample set (mean-case, worst-case achieved ENOB above) against "
            "spec/target-spec.md's DRAFT (not ratified) baseline ENOB target (`> 9.0 bit`), "
            "target_yield=0.99, 95% confidence -- INFORMATIONAL, not a ratified pass/fail. "
            f"Full JSON report: `sim/enob-estimate/yield-reports/{record_id}.json`. With only "
            "two points this is a demonstration of the machine-checkable-evidence PATH (same "
            "invocation issue #29's other two statistical rows use), not a real yield claim -- "
            "see the sample-size verdict below, which says so explicitly."
        )
        a("")
        for m in yield_report.get("measurements", []):
            emp = m.get("yield", {}).get("empirical", {}) or {}
            ss = m.get("sample_size", {}) or {}
            a(
                f"- `{m.get('name')}`: n={m.get('n')}, empirical yield={emp.get('estimate')}, "
                f"sample-size verdict={ss.get('verdict')} (required_n_for_target={ss.get('required_n_for_target')})"
            )
        a("")
        for w in yield_report.get("warnings", []):
            a(f"- klt yield warning: {w}")
    else:
        a(
            "`klt yield` did not produce a report in this environment -- see "
            "sim/cdac-array-transfer/run_mc.py's own note on "
            "2AMLogic/klayout-tools#1061 (already-filed, COMPLETED packaging gap; not a new gap)."
        )
    a("")
    a(
        "No spec row is relaxed to make this result pass or fail -- the DRAFT targets above "
        "are quoted verbatim from spec/target-spec.md and explicitly labeled DRAFT throughout, "
        "per CLAUDE.md's 'do not invent settled numbers to replace the drafts' rule."
    )
    a("")
    lines.extend(evidence.environment_block(
        pdk_line=f"{info.variant} @ {pdk.resolved_commit(info)}" if info.found else "not resolved (post-processing record, no ngspice run)",
        ngspice_line=toolchain._ngspice_version() or "unknown",
        netlist_sha256=inputs_sha,
        extra={"Composite-inputs manifest": f"`{inputs_manifest}`"},
    ))
    a("")
    lines.extend(evidence.footer_lines("sim/enob-estimate/run_enob.py", ""))

    if args.record:
        record_path.write_text("\n".join(lines))
        print(f"wrote {record_path}")
    else:
        print("\n".join(lines))

    print(f"achieved ENOB: mean-case={enob_mean_case:.3f} bit, worst-case={enob_worst_case:.3f} bit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

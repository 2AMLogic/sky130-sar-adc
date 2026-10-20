#!/usr/bin/env python3
"""Behavioral-accelerated ENOB estimate -- issue #29's third statistical
row (spec/target-spec.md's DRAFT "ENOB > 9.0 bit (target), stretch > 9.5"
row), combining real evidence from three ALREADY-RUN experiments rather than
a fresh full-chip transient FFT simulation:

  1. Ideal quantization noise -- analytic, from the ratified LSB
     (`sigma_quant = LSB/sqrt(12)`).
  2. Comparator input-referred noise -- the WORST-CASE (binding-corner)
     value from issue #28's ratified full-PVT-corner campaign, re-run
     against DR-004 Amendment A's amended comparator device set
     (sim/comparator-decision/records/20260906-065109-eedd532.md,
     `tt_125c_1.80v`, 0.8643 mV rms differential). That record supersedes
     20260827-212404-e13bc1e, whose 0.9591 mV rms figure measured the
     9-device topology issue #175 replaced.
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

PER-DRAW SAMPLES (issue #587). The `klt yield` sample set is one conditional
analytical ENOB estimate per REAL CDAC mismatch draw, loaded from the source
record's committed `mc-draws/<record-id>/draw_*.log` raw logs (the parser
run_mc.py's `reanalyze_from_logs()` uses; no new simulation). Draw index and
seed are carried into the record and samples document. A missing, incomplete
or non-finite draw set is an explicit failure, never a fallback to summary
statistics. Mean-case / worst-case headline values are kept for comparison.
This is a conditional estimate across CDAC mismatch draws only (fixed
comparator and kT/C terms), not a transient/FFT ENOB and not a joint MC.

Requires --cdac-mc-record naming the sim/cdac-array-transfer/ Monte Carlo
record (run_mc.py) this estimate draws its CDAC-mismatch contribution from,
so the composite record's provenance is explicit and reproducible rather
than silently picking "the latest" (append-only evidence, sim/README.md).

--target-baseline-bit / --target-stretch-bit / --target-yield (issue #129)
let this SAME already-composed estimate be re-scored against a CANDIDATE
REVISED ENOB target (e.g. spec/decision-records/DR-007-revised-enob-inl-dnl-targets.md's
proposal) without re-deriving the noise budget -- default to the DRAFT spec
row's 9.0/9.5/0.99 so an unqualified `--record` run is unchanged:

    python3 sim/enob-estimate/run_enob.py --cdac-mc-record <record-id> \
        --target-baseline-bit 7.5 --target-stretch-bit 8.0 --record

Cold start (the exact invocation that minted the committed record, indexed
by sim/spec-coverage.json for the ENOB row and checked against this
docstring by sim/check_spec_coverage.py -- run it after the one-time
bootstrap in docs/environment-setup.md and `source sim/env.sh`):

    python3 sim/enob-estimate/run_enob.py --cdac-mc-record 20260828-005006-0c70212 --record
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
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
# corner campaign. Transcribed from the binding-corner row of the record
# named below (re-run `python3 sim/comparator-decision/run.py noise-corners`
# to reproduce independently) -- NOT re-simulated here, per this repo's
# "combine with, not substitute for, the item-5 corner evidence" convention
# (issue #29 AC).
#
# Re-pointed by issue #175: DR-004 Amendment A changed the comparator
# topology (the cross-coupled NMOS latch pair's sources moved off hard-wired
# GND onto the input pair's own drain nodes DIP/DIN, which gained their own
# CLK-gated PMOS precharge devices), so every pre-amendment
# sim/comparator-decision/ record measures a device set that no longer
# exists. Leaving this constant pointing at 20260827-212404-e13bc1e would
# make this estimate a composite of one current and one superseded
# measurement -- silently, since nothing recomputes a transcribed constant.
# The binding corner is unchanged (tt_125c_1.80v); the value moved
# 0.9591 -> 0.8643 mV rms.
COMPARATOR_NOISE_SOURCE_RECORD = "sim/comparator-decision/records/20260906-065109-eedd532.md"
COMPARATOR_NOISE_BINDING_CORNER = "tt_125c_1.80v"
COMPARATOR_NOISE_DIFF_V = 0.8643e-3  # V rms, differential, worst-case (125C)

# --- Source #4: kT/C sampling noise, same formula and worst-case (125C)
# corner spec/dr-003-support/calc.py uses, re-derived here (not imported --
# that script's top-level prints make it unsuitable as a library import;
# same formula, cited inline).
K_B = 1.380649e-23  # J/K, exact SI
T_HOT_K = 125 + 273.15
# The ratified CDAC unit cap, DR-003 via #27 as amended by
# spec/decision-records/DR-019-cdac-unit-cap-grid-legal-plate-resize.md (#496,
# carried through by #498): DR-019 resized the MiM plate to a 5 nm-grid-legal
# 1.9000 um square, which moves `C_u` from 8.65 fF to exactly 8.664 fF under
# `klt extract`'s own sky130 area+perimeter coefficients
# (1.9^2 * 2.0e-15 + 4*1.9 * 1.9e-16). Leaving this literal at 8.65e-15 would
# make the kT/C term below a measurement of a plate the design no longer
# draws -- numerically negligible here (that term is ~2.5% of sigma_total and
# moves by ~0.1%), but silently stale, which is exactly the failure mode
# COMPARATOR_NOISE_SOURCE_RECORD's comment above exists to prevent.
C_U_F = 8.664e-15
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


def _load_run_mc():
    """Import sim/cdac-array-transfer/run_mc.py by path (its directory name has
    a hyphen, so it is not importable as a package) for its pure raw-log
    parser `_parse_draw()` / `_LOG_NAME_RE` -- no ngspice is invoked."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("cdac_run_mc", CDAC_DIR / "run_mc.py")
    mod = importlib.util.module_from_spec(spec)
    # run_mc.py imports its sibling gen_fragment.py by bare name.
    sys.modules["cdac_run_mc"] = mod
    sys.path.insert(0, str(CDAC_DIR))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(CDAC_DIR))
    return mod


def load_cdac_draws(record_id: str, expected_n: int | None = None, draws_root: Path | None = None) -> list[dict]:
    """Load the REAL per-draw max|INL| values (ratified LSB) of a CDAC Monte
    Carlo source record from its committed `mc-draws/<record_id>/draw_*.log`
    raw logs (the same parsing run_mc.py's `reanalyze_from_logs()` uses; the
    negative-control `negctrl_*` logs are not draws and are ignored).

    Returns one dict per draw, ordered by draw index:
    `{"index", "seed", "inl_max_lsb"}`. Raises ValueError/FileNotFoundError
    -- never degrades to summary statistics -- if the directory or logs are
    missing, indices are not the contiguous 0..n-1, the count differs from
    `expected_n` (the source record's own reported N), or any draw's INL is
    missing or non-finite (a code measurement absent from the log)."""
    root = draws_root if draws_root is not None else CDAC_DIR / "mc-draws"
    draws_dir = root / record_id
    if not draws_dir.is_dir():
        raise FileNotFoundError(f"no raw draws for CDAC MC record {record_id}: {draws_dir} (refusing to fall back to summary statistics)")
    mc = _load_run_mc()
    found: dict[int, tuple[int, Path]] = {}
    for log_path in sorted(draws_dir.glob("*.log")):
        m = mc._LOG_NAME_RE.match(log_path.name)
        if not m or m.group("kind") != "draw":
            continue
        found[int(m.group("idx"))] = (int(m.group("seed")), log_path)
    if not found:
        raise FileNotFoundError(f"{draws_dir} contains no draw_*.log files")
    if sorted(found) != list(range(len(found))):
        raise ValueError(f"{draws_dir}: draw indices are not contiguous 0..{len(found) - 1}: {sorted(found)}")
    if expected_n is not None and len(found) != expected_n:
        raise ValueError(f"{draws_dir}: {len(found)} draw logs but the source record reports N={expected_n} (incomplete draw set)")
    out = []
    for idx in sorted(found):
        seed, path = found[idx]
        inl = mc._parse_draw(seed, path.read_text()).inl_max_lsb
        if not math.isfinite(inl):
            raise ValueError(f"{path}: draw {idx} (seed {seed}) has missing or non-finite max|INL| ({inl})")
        out.append({"index": idx, "seed": seed, "inl_max_lsb": inl})
    return out


def per_draw_enob(draws: list[dict], sigma_cmp_v: float, sigma_ktc_v: float, lsb_v: float = LSB_V) -> list[dict]:
    """One conditional analytical ENOB estimate per real CDAC draw: the draw's
    OWN max|INL| (converted to volts, treated as an rms noise-like term as in
    the headline estimate) combined in quadrature with the FIXED comparator
    and kT/C terms. Adds `"sigma_cdac_v"` and `"enob_bit"` to each draw."""
    if not draws:
        raise ValueError("no CDAC draws supplied; refusing to emit an empty sample set")
    out = []
    for d in draws:
        inl = d["inl_max_lsb"]
        if not isinstance(inl, (int, float)) or not math.isfinite(inl):
            raise ValueError(f"draw {d.get('index')}: non-finite max|INL| {inl!r}")
        sigma_cdac = inl * lsb_v
        enob = achieved_enob(math.sqrt(sigma_cmp_v ** 2 + sigma_ktc_v ** 2 + sigma_cdac ** 2), lsb_v)
        if not math.isfinite(enob):
            raise ValueError(f"draw {d.get('index')}: non-finite ENOB")
        out.append({**d, "sigma_cdac_v": sigma_cdac, "enob_bit": enob})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Behavioral-accelerated ENOB estimate (issue #29)")
    ap.add_argument("--cdac-mc-record", required=True, help="sim/cdac-array-transfer/ Monte Carlo record-id (run_mc.py) to draw the CDAC-mismatch contribution from")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--note", default="")
    evidence.add_supersedes_argument(ap)
    ap.add_argument(
        "--target-baseline-bit", type=float, default=9.0,
        help="candidate ENOB baseline target in bits (default: the DRAFT spec row's 9.0; issue #129's DR-007 evaluates a candidate revised value here)",
    )
    ap.add_argument(
        "--target-stretch-bit", type=float, default=9.5,
        help="candidate ENOB stretch target in bits (default: the DRAFT spec row's 9.5)",
    )
    ap.add_argument(
        "--target-yield", type=float, default=0.99,
        help="target_yield passed to klt yield (default: 0.99, matching the DRAFT spec row's convention)",
    )
    args = ap.parse_args()
    is_candidate = args.target_baseline_bit != 9.0 or args.target_stretch_bit != 9.5

    cdac = read_cdac_mc_inl(args.cdac_mc_record)
    sq = sigma_quant(LSB_V)
    sigma_ktc = sigma_ktc_differential()
    sigma_cmp = COMPARATOR_NOISE_DIFF_V

    # One conditional analytical ENOB estimate per REAL CDAC MC draw, loaded
    # from the source record's committed raw draw logs (issue #587); fixed
    # comparator and kT/C terms. No synthetic draws; mean/worst headline
    # values below are kept for comparison.
    draws = per_draw_enob(load_cdac_draws(args.cdac_mc_record, expected_n=cdac["n"]), sigma_cmp, sigma_ktc)
    enob_samples = [d["enob_bit"] for d in draws]
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
    yield_measurements = [
            {
                "name": "enob_bit",
                "unit": "bit",
                "samples": enob_samples,
                "draws": [{"index": d["index"], "seed": d["seed"], "inl_max_lsb": d["inl_max_lsb"]} for d in draws],
                "source_record": args.cdac_mc_record,
                "limits": {"min": args.target_baseline_bit, "target_yield": args.target_yield},
            },
        ]
    yield_report = evidence.run_klt_yield(
        yield_measurements,
        yield_dir / f"{record_id}.json",
    )
    yield_samples_path = yield_dir / f"{record_id}.samples.json"
    if yield_report is None and not yield_samples_path.exists():
        # run_klt_yield() deletes the samples document when `klt yield` is
        # unavailable. The per-draw samples are the committed INPUT evidence
        # either way, so persist the identical document and let the record say
        # the verdict is absent.
        yield_samples_path.write_text(json.dumps({"measurements": yield_measurements}, indent=2))

    inputs_manifest = json.dumps({
        "comparator_noise_record": COMPARATOR_NOISE_SOURCE_RECORD,
        "comparator_noise_diff_v": COMPARATOR_NOISE_DIFF_V,
        "cdac_mc_record": str(cdac["record_path"].relative_to(evidence.REPO_ROOT)),
        "cdac_inl_mean_lsb": cdac["mean_lsb"],
        "cdac_inl_max_lsb": cdac["max_lsb"],
        "cdac_draws": [[d["index"], d["seed"], d["inl_max_lsb"]] for d in draws],
    }, sort_keys=True)
    inputs_sha = hashlib.sha256(inputs_manifest.encode()).hexdigest()

    info = pdk.resolve()
    lines: list[str] = []
    a = lines.append
    a(f"# Record {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    if is_candidate:
        a(
            "- **Claim**: `spec/target-spec.md#target-table` -- ENOB row, re-scored against a "
            f"CANDIDATE REVISED target (`> {args.target_baseline_bit:g} bit` baseline / "
            f"`> {args.target_stretch_bit:g} bit` stretch, target_yield={args.target_yield:g}) that "
            "issue #129's `spec/decision-records/DR-007-*.md` proposes (evidence-derived, per "
            "#29's shortfall against the original DRAFT `> 9.0`/`> 9.5` row -- see that record). "
            "This record supplies a BEHAVIORAL-ACCELERATED ENOB estimate (not a dynamic-test "
            "FFT measurement -- see Methodology) composed from three already-run experiments' "
            "OWN evidence, combined in quadrature via the standard "
            "`SNR = 6.02*ENOB + 1.76 dB` relationship, then compared against DR-007's candidate "
            "revised target rather than the original DRAFT row."
        )
    else:
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
        f"  - kT/C sampling noise (analytic, 125C worst-case, ratified C_u={C_U_F * 1e15:.3f} fF, "
        f"{ARRAY_SIDE}/side): {sigma_ktc * 1000:.4f} mV rms\n"
        f"  - CDAC mismatch-driven nonlinearity (from `{args.cdac_mc_record}`'s max\\|INL\\| "
        f"distribution, N={cdac['n']}): mean-case {inl_mean_v * 1000:.4f} mV rms "
        f"({cdac['mean_lsb']:.4f} LSB), worst-case {inl_worst_v * 1000:.4f} mV rms "
        f"({cdac['max_lsb']:.4f} LSB)"
    )
    a(
        "- **Estimate class**: conditional analytical ENOB estimate across real CDAC mismatch "
        f"draws (N={len(draws)}, one estimate per draw of `{args.cdac_mc_record}`). Comparator "
        "noise and kT/C are FIXED model inputs with their existing provenance; the quadrature "
        "treatment of max INL as a noise contribution is an approximation. This is neither a "
        "transient/FFT ENOB measurement nor a joint comparator/CDAC/noise Monte Carlo population. "
        "Supersedes the earlier two-point (mean/worst) yield sample set."
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
    target_label = "DR-007 candidate" if is_candidate else "DRAFT"
    a(
        f"- **Measured value(s)**: achieved ENOB (mean-case CDAC mismatch) = "
        f"**{enob_mean_case:.3f} bit**; achieved ENOB (worst-case CDAC mismatch) = "
        f"**{enob_worst_case:.3f} bit** -- both against the {target_label} target row "
        f"`> {args.target_baseline_bit:g}` (baseline) / `> {args.target_stretch_bit:g}` (stretch), "
        "reported INFORMATIONALLY, not as pass/fail against a ratified line."
    )
    a("")
    a("## Composed noise budget and resulting ENOB")
    a("")
    a(
        f"| scenario | sigma_nonquant (mV rms) | sigma_total (mV rms) | achieved ENOB (bit) | "
        f"vs {target_label} baseline (>{args.target_baseline_bit:g}) | "
        f"vs {target_label} stretch (>{args.target_stretch_bit:g}) |"
    )
    a("|---|---|---|---|---|---|")
    for label, inl_v, enob in (("mean-case", inl_mean_v, enob_mean_case), ("worst-case", inl_worst_v, enob_worst_case)):
        snq = total_nonquant(inl_v)
        stot = math.sqrt(sq ** 2 + snq ** 2)
        a(
            f"| {label} | {snq * 1000:.4f} | {stot * 1000:.4f} | {enob:.3f} | "
            f"{'meets' if enob > args.target_baseline_bit else 'does NOT meet'} | "
            f"{'meets' if enob > args.target_stretch_bit else 'does NOT meet'} |"
        )
    a("")
    a("## Per-draw conditional analytical ENOB estimates (CDAC mismatch draws)")
    a("")
    a(
        f"Source record `{args.cdac_mc_record}`, N={len(draws)} real draws loaded from its committed "
        "`mc-draws/` raw logs (no draws fabricated; negative-control logs excluded). Each row combines "
        "that draw's own max\\|INL\\| with the fixed comparator and kT/C terms in quadrature. "
        "Conditional analytical estimate -- NOT a transient/FFT ENOB, NOT a joint Monte Carlo."
    )
    a("")
    a("| draw | seed | max\\|INL\\| (LSB) | sigma_cdac (mV rms) | conditional ENOB (bit) |")
    a("|---|---|---|---|---|")
    for d in draws:
        a(f"| {d['index']} | {d['seed']} | {d['inl_max_lsb']:.4f} | {d['sigma_cdac_v'] * 1000:.4f} | {d['enob_bit']:.3f} |")
    a("")
    a(
        f"Per-draw ENOB: min {min(enob_samples):.3f}, mean {sum(enob_samples) / len(enob_samples):.3f}, "
        f"max {max(enob_samples):.3f} bit. The mean-case / worst-case headline values above are retained "
        "for comparison (they use the source record's reported mean and maximum of max\\|INL\\|)."
    )
    a("")
    a("## Machine-checkable yield evidence (`klt yield`)")
    a("")
    if yield_report is not None:
        a(
            f"Sample set: {len(draws)} per-draw CONDITIONAL ANALYTICAL ENOB estimates, one per real "
            f"CDAC mismatch Monte Carlo draw of `{args.cdac_mc_record}` (table above; draw index and seed "
            "preserved), with the comparator and kT/C terms held fixed -- against "
            f"the {target_label} baseline ENOB target (`> {args.target_baseline_bit:g} bit`), "
            f"target_yield={args.target_yield:g}, 95% confidence -- INFORMATIONAL, not a ratified "
            f"pass/fail. Full JSON report: `sim/enob-estimate/yield-reports/{record_id}.json`; samples "
            f"document: `sim/enob-estimate/yield-reports/{record_id}.samples.json`. The yield fraction "
            "describes CDAC-mismatch variability only, under the quadrature model; it is not a "
            "transient/FFT ENOB measurement and not a joint comparator/CDAC/noise Monte Carlo "
            "population, and a larger sample count does not validate the model itself."
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
            "`klt yield` did not produce a report in this environment (the native yield "
            "extension was not installed on the minting host -- see "
            "sim/cdac-array-transfer/run_mc.py's own note on "
            "2AMLogic/klayout-tools#1061, already-filed packaging gap; not a new gap), so NO "
            "yield verdict is recorded here. The per-draw sample set that `klt yield` would "
            f"consume is persisted at `sim/enob-estimate/yield-reports/{record_id}.samples.json` "
            "for a later run of `klt yield` against it; that report, once produced, is a new "
            "derived record, not an edit of this one."
        )
    a("")
    if is_candidate:
        a(
            "No spec row is relaxed to make this result pass or fail -- the target above is "
            "DR-007's CANDIDATE REVISED value (issue #129), explicitly labeled candidate/not-"
            "ratified throughout; it does not itself amend spec/target-spec.md (only the "
            "operator's approval of that decision record's own ratification act does, per "
            "CLAUDE.md's 'do not invent settled numbers to replace the drafts' rule)."
        )
    else:
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
    lines.extend(evidence.footer_lines("sim/enob-estimate/run_enob.py", args.supersedes))

    if args.record:
        record_path.write_text("\n".join(lines))
        evidence.write_latest_pointer(EXPERIMENT_DIR, record_id)
        print(f"wrote {record_path}")
    else:
        print("\n".join(lines))

    print(f"achieved ENOB: mean-case={enob_mean_case:.3f} bit, worst-case={enob_worst_case:.3f} bit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

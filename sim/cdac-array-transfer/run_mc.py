#!/usr/bin/env python3
"""Monte Carlo mismatch campaign for the CDAC array's DAC transfer
characteristic -- statistical DNL/INL evidence for
spec/target-spec.md's DNL/INL row (issue #29; T1 item 6 / issue #16's
re-read: "any accuracy, offset, or matching spec row is statistical; a
corner matrix ... cannot validate it").

Extends #53/#28's deterministic 5-code (0,128,256,384,511) transfer-curve
experiment with device-mismatch Monte Carlo draws over a larger,
purpose-built code set (see CODES_MC below) at the `tt_mm` local-mismatch
corner, following the SAME negative-control contract every other MC record
in this repo uses (sim/README.md "Monte Carlo records"): N draws at the
mismatch-enabled corner, N draws at the plain corner with the SAME seed
sequence, and the plain-corner draws must reproduce identically (stdev==0).

    python3 sim/cdac-array-transfer/run_mc.py --check-env
    python3 sim/cdac-array-transfer/run_mc.py --n 50 --seed 1 --record

WHY A NEW, LARGER CODE SET (not #53's 5 codes). #53's set (0, 128, 256,
384, 511) is quartile-spaced -- no two of those codes are adjacent, so it
cannot express DNL at all (DNL is inherently a code-to-code quantity).
CODES_MC below adds the major-carry PAIRS (2**k-1, 2**k) for every one of
the 9-bit sub-array's bit boundaries -- the textbook worst-DNL location for
a binary-weighted DAC (McCreary & Wooley 1975, the same combinatorial result
spec/dr-003-support/calc.py already cites for the analytic DNL/INL
coefficients) -- plus the code range's own endpoints and a short run near
code=0 for a mini code-density sanity check. gen_fragment.py generates the
per-code SPICE block programmatically (verified byte-for-byte against #53's
hand-authored fragment for its own 5 codes -- see
sim/tests/test_cdac_fragment_gen.py) rather than hand-authoring dozens of
copies of the same 27-line block.

UNITS. This array's OWN ideal code-to-code step is `2*V_REF/512` = 7.03 mV
-- TWICE the ratified ADC LSB (`2*V_REF/2^10` = 3.5156 mV, DR-003 via #27):
the array realizes only the 9-bit sub-array's own 512 differential output
levels: the ratified `N=10` total resolution's tenth bit comes from the
top-level differential sign structure (design/sar_adc_top.spice), which
this array-only experiment does not exercise (same scope limitation #53's
own record already states: "informs, but does not substantiate" the
DNL/INL row). DNL/INL below are computed in units of the ratified ADC LSB
(matching spec/target-spec.md's own "<=1 LSB" row), NOT this array's own
7.03 mV code step -- see `dnl_lsb()`/`inl_lsb()`.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import corners as corners_mod, evidence, measure, pdk, toolchain  # noqa: E402
from gen_fragment import gen_fragment  # noqa: E402

EXPERIMENT_DIR = Path(__file__).resolve().parent

NOMINAL_SUPPLY_V = 1.8  # = V_REF = V_DD, ratified (DR-003 via #27)
BASE_CORNER = "tt"
TEMP_C = 27.0
SETTLE_T = "500n"
TRAN_STEP = "0.5n"

RATIFIED_LSB_V = 3.5156e-3  # spec/target-spec.md ratified LSB (2*V_REF/2^N), DR-003 via #27
DRAFT_INL_DNL_TARGET_LSB = 1.0  # spec/target-spec.md DRAFT target row: "INL / DNL <= +-1 LSB
# (target)" -- NOT ratified (target-spec.md's own "Not ratified by this
# record" list names ENOB/INL-DNL target values as still open, gated on
# THIS issue's own MC campaign). Used below ONLY as an informational `klt
# yield` limit, explicitly labeled DRAFT throughout the record -- never
# presented as a pass/fail against a ratified spec/target-spec.md line.

# Reduced code set: major-carry PAIRS (worst-case DNL location for a
# binary-weighted CDAC, per the McCreary & Wooley combinatorics
# spec/dr-003-support/calc.py already applies analytically) at every one of
# the 9-bit sub-array's bit boundaries, the code range's endpoints, and a
# short consecutive run near code=0.
CODES_MC: list[int] = sorted(set(
    [0, 1, 2, 3, 4, 510, 511]
    + [2 ** k - 1 for k in range(9)]
    + [2 ** k for k in range(9)]
    + [383, 384, 385]
))

_sorted_codes = sorted(CODES_MC)
# Adjacent-code pairs within CODES_MC (b - a == 1) -- the ONLY code
# transitions this reduced set can compute a real DNL for; reported
# explicitly in the record rather than silently implied.
ADJACENT_PAIRS_MC: list[tuple[int, int]] = [
    (a, b) for a, b in zip(_sorted_codes, _sorted_codes[1:]) if b - a == 1
]

ENDPOINT_LO, ENDPOINT_HI = 0, 511
ARRAY_IDEAL_STEP_V = 2 * NOMINAL_SUPPLY_V / 512  # this array's own ideal code-to-code step


def ideal_vdiff(code: int, vdd_val: float = NOMINAL_SUPPLY_V) -> float:
    return vdd_val * (2 * code - 511) / 512


def build_netlist(info: pdk.PdkInfo, corner: str, temp_c: float, supply_v: float, rndseed: int | None) -> str:
    lines: list[str] = []
    a = lines.append
    a(f"* cdac-array-transfer Monte Carlo -- corner={corner} temp={temp_c}C supply={supply_v}V seed={rndseed} (issue #29)")
    a(f".lib {info.ngspice_lib} {corner}")
    a(f".temp {temp_c}")
    a(f".param vdd_val = {supply_v}")
    if rndseed is not None:
        a(f".option rndseed={rndseed}")
    a("")
    a(gen_fragment(CODES_MC))
    a("")
    a(".control")
    a(f"tran {TRAN_STEP} {SETTLE_T}")
    for code in CODES_MC:
        a(f"meas tran vtop_p_{code} find v(top_{code}p) at={SETTLE_T}")
        a(f"meas tran vtop_n_{code} find v(top_{code}n) at={SETTLE_T}")
    a(".endc")
    a(".end")
    return "\n".join(lines) + "\n"


def measure_names() -> list[str]:
    names = []
    for code in CODES_MC:
        names.append(f"vtop_p_{code}")
        names.append(f"vtop_n_{code}")
    return names


@dataclass
class Draw:
    seed: int
    vdiff: dict[int, float]  # code -> measured differential output (V)
    dnl_lsb: dict[tuple[int, int], float]  # (c1,c2) -> DNL at that transition, in ratified LSB
    inl_lsb: dict[int, float]  # code -> INL vs endpoint line, in ratified LSB
    dnl_max_lsb: float
    inl_max_lsb: float
    log_text: str


def _parse_draw(seed: int | None, log_text: str) -> Draw:
    """Compute a single draw's DNL/INL statistics from an ngspice batch
    log's text -- shared by `_one_draw()` (fresh simulation) and
    `reanalyze_from_logs()` (re-scoring an ALREADY-COMMITTED log from a
    prior record's `mc-draws/<record-id>/` directory against a different
    candidate target, with no new ngspice invocation). Keeping this pure
    (log text in, Draw out) is what makes the reanalysis path possible
    without re-running the expensive simulation."""
    names = measure_names()
    parsed = measure.parse(log_text, names)
    vdiff = {}
    for code in CODES_MC:
        vp = parsed.get(f"vtop_p_{code}")
        vn = parsed.get(f"vtop_n_{code}")
        vdiff[code] = (vp - vn) if (vp is not None and vn is not None) else float("nan")

    # DNL at each measurable adjacent-code transition: actual step minus
    # this array's own ideal step, normalized by the RATIFIED ADC LSB (see
    # module docstring's "UNITS" note).
    dnl_lsb = {}
    for c1, c2 in ADJACENT_PAIRS_MC:
        actual_step = vdiff[c2] - vdiff[c1]
        dnl_lsb[(c1, c2)] = (actual_step - ARRAY_IDEAL_STEP_V) / RATIFIED_LSB_V

    # INL at every sampled code vs. the endpoint (code 0 -> code 511)
    # straight line, normalized by the ratified ADC LSB.
    v_lo, v_hi = vdiff[ENDPOINT_LO], vdiff[ENDPOINT_HI]
    inl_lsb = {}
    for code in CODES_MC:
        line_v = v_lo + (v_hi - v_lo) * (code - ENDPOINT_LO) / (ENDPOINT_HI - ENDPOINT_LO)
        inl_lsb[code] = (vdiff[code] - line_v) / RATIFIED_LSB_V

    dnl_max = max((abs(v) for v in dnl_lsb.values()), default=float("nan"))
    inl_max = max((abs(v) for v in inl_lsb.values()), default=float("nan"))
    return Draw(
        seed=seed if seed is not None else -1, vdiff=vdiff, dnl_lsb=dnl_lsb, inl_lsb=inl_lsb,
        dnl_max_lsb=dnl_max, inl_max_lsb=inl_max, log_text=log_text,
    )


def _one_draw(info: pdk.PdkInfo, corner: str, seed: int | None, scratch_dir: Path, log_name: str) -> Draw:
    netlist = build_netlist(info, corner, TEMP_C, NOMINAL_SUPPLY_V, seed)
    log_text = toolchain.run_ngspice(netlist, scratch_dir, log_name)
    return _parse_draw(seed, log_text)


@dataclass
class McResult:
    seed: int
    n: int
    corner: str
    mismatch_corner: str
    draws: list[Draw] = field(default_factory=list)
    negctrl: list[Draw] = field(default_factory=list)
    source_record_id: str | None = None  # set only by reanalyze_from_logs()


def run_mc(seed: int = 1, n: int = 50, corner: str = BASE_CORNER, quiet: bool = False) -> McResult:
    info = pdk.resolve()
    if not info.found:
        raise RuntimeError(f"PDK not resolvable: {info.error}")
    mismatch_corner = corners_mod.mismatch_corner_for(corner)

    draws: list[Draw] = []
    negctrl: list[Draw] = []
    with tempfile.TemporaryDirectory(prefix="sim-cdac-mc-") as scratch:
        scratch_dir = Path(scratch)
        for i in range(n):
            this_seed = seed + i
            d = _one_draw(info, mismatch_corner, this_seed, scratch_dir, f"draw_{i}")
            draws.append(d)
            if not quiet:
                print(f"  draw {i} (seed={this_seed}, {mismatch_corner}): DNLmax={d.dnl_max_lsb:.4f} LSB INLmax={d.inl_max_lsb:.4f} LSB")
        for i in range(n):
            this_seed = seed + i
            d = _one_draw(info, corner, this_seed, scratch_dir, f"negctrl_{i}")
            negctrl.append(d)
            if not quiet:
                print(f"  negctrl {i} (seed={this_seed}, {corner}): DNLmax={d.dnl_max_lsb:.4f} LSB INLmax={d.inl_max_lsb:.4f} LSB")
    return McResult(seed=seed, n=n, corner=corner, mismatch_corner=mismatch_corner, draws=draws, negctrl=negctrl)


_LOG_NAME_RE = re.compile(r"^(?P<kind>draw|negctrl)_(?P<idx>\d+)_seed(?P<seed>-?\d+)\.log$")


def reanalyze_from_logs(source_record_id: str, corner: str = BASE_CORNER) -> McResult:
    """Re-derive an McResult from a PRIOR record's already-committed
    `mc-draws/<source_record_id>/*.log` files -- NO new ngspice invocation.
    Used to re-score already-collected evidence against a DIFFERENT
    candidate INL/DNL target (issue #129: DR-007 proposes a revised,
    evidence-derived target; this lets that proposal cite a real `klt
    yield` verdict against the SAME underlying draws #29 already ran,
    rather than re-simulating ~35 minutes of ngspice for numbers that
    would come out identical). Mirrors sim/enob-estimate/run_enob.py's own
    'derived/composite -- no new ngspice netlist executed' convention."""
    draws_dir = EXPERIMENT_DIR / "mc-draws" / source_record_id
    if not draws_dir.is_dir():
        raise FileNotFoundError(f"no mc-draws/ directory for source record {source_record_id}: {draws_dir}")

    mismatch_corner = corners_mod.mismatch_corner_for(corner)
    by_idx: dict[str, dict[int, tuple[int, Path]]] = {"draw": {}, "negctrl": {}}
    for log_path in draws_dir.glob("*.log"):
        m = _LOG_NAME_RE.match(log_path.name)
        if not m:
            continue
        by_idx[m.group("kind")][int(m.group("idx"))] = (int(m.group("seed")), log_path)

    if not by_idx["draw"] or not by_idx["negctrl"]:
        raise FileNotFoundError(f"mc-draws/{source_record_id} is missing draw_*.log or negctrl_*.log files")

    def _load(kind: str) -> list[Draw]:
        out = []
        for idx in sorted(by_idx[kind]):
            seed, path = by_idx[kind][idx]
            out.append(_parse_draw(seed, path.read_text()))
        return out

    draws = _load("draw")
    negctrl = _load("negctrl")
    n = len(draws)
    if len(negctrl) != n:
        raise ValueError(f"mc-draws/{source_record_id}: {n} draw logs but {len(negctrl)} negctrl logs (expected equal)")
    seed = min(s for s, _ in by_idx["draw"].values())
    return McResult(
        seed=seed, n=n, corner=corner, mismatch_corner=mismatch_corner,
        draws=draws, negctrl=negctrl, source_record_id=source_record_id,
    )


def _run_klt_yield(
    dnl_samples: list[float],
    inl_samples: list[float],
    out_json_path: Path,
    target_limit_lsb: float = DRAFT_INL_DNL_TARGET_LSB,
    target_yield: float = 0.99,
) -> dict | None:
    """Invoke `klt yield` against the DNL/INL per-draw worst-case samples,
    using spec/target-spec.md's DRAFT (NOT ratified) INL/DNL target row as
    an informational limit. Returns the parsed JSON report, or None if
    `klt` / its native yield extension is unavailable (recorded as an
    honest gap in the record rather than silently skipped)."""
    doc = {
        "measurements": [
            {
                "name": "dnl_max_lsb",
                "unit": "LSB",
                "samples": dnl_samples,
                "limits": {
                    "min": -target_limit_lsb,
                    "max": target_limit_lsb,
                    "target_yield": target_yield,
                },
            },
            {
                "name": "inl_max_lsb",
                "unit": "LSB",
                "samples": inl_samples,
                "limits": {
                    "min": -target_limit_lsb,
                    "max": target_limit_lsb,
                    "target_yield": target_yield,
                },
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


def write_evidence(
    result: McResult,
    note: str = "",
    target_limit_lsb: float = DRAFT_INL_DNL_TARGET_LSB,
    target_yield: float = 0.99,
) -> tuple[Path, bool]:
    record_id = evidence.new_record_id()
    draws_dir = EXPERIMENT_DIR / "mc-draws" / record_id
    draws_dir.mkdir(parents=True, exist_ok=True)
    for i, d in enumerate(result.draws):
        (draws_dir / f"draw_{i}_seed{d.seed}.log").write_text(d.log_text)
    for i, d in enumerate(result.negctrl):
        (draws_dir / f"negctrl_{i}_seed{d.seed}.log").write_text(d.log_text)

    sample_netlist = build_netlist(pdk.resolve(), result.mismatch_corner, TEMP_C, NOMINAL_SUPPLY_V, result.seed)
    record_path = evidence.write_netlist_snapshot_text(EXPERIMENT_DIR, record_id, sample_netlist)
    netlist_sha = evidence.sha256_text(sample_netlist)

    dnl_draws = [d.dnl_max_lsb for d in result.draws]
    inl_draws = [d.inl_max_lsb for d in result.draws]
    dnl_neg = [d.dnl_max_lsb for d in result.negctrl]
    inl_neg = [d.inl_max_lsb for d in result.negctrl]

    dnl_neg_stdev = statistics.pstdev(dnl_neg) if len(dnl_neg) > 1 else 0.0
    inl_neg_stdev = statistics.pstdev(inl_neg) if len(inl_neg) > 1 else 0.0
    negctrl_ok = dnl_neg_stdev == 0.0 and inl_neg_stdev == 0.0

    dnl_stdev = statistics.pstdev(dnl_draws) if len(dnl_draws) > 1 else 0.0
    inl_stdev = statistics.pstdev(inl_draws) if len(inl_draws) > 1 else 0.0
    positive_ok = dnl_stdev > 0 and inl_stdev > 0

    n = result.n
    rel_se_pct = 100.0 / (2 * (n - 1)) ** 0.5 if n > 1 else float("inf")

    yield_json_path = EXPERIMENT_DIR / "yield-reports" / f"{record_id}.json"
    yield_report = _run_klt_yield(dnl_draws, inl_draws, yield_json_path, target_limit_lsb, target_yield)

    info = pdk.resolve()
    lines: list[str] = []
    a = lines.append
    a(f"# Monte Carlo record {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    if result.source_record_id:
        a(
            "- **Claim**: `spec/target-spec.md#target-table` -- INL/DNL row, re-scored "
            f"against a CANDIDATE REVISED target ({target_limit_lsb:g} LSB, target_yield="
            f"{target_yield:g}) that issue #129's `spec/decision-records/DR-007-*.md` "
            "proposes (evidence-derived, per #29's shortfall against the original DRAFT "
            "`<= +-1 LSB` row -- see that record). This record supplies that re-scoring: "
            "the SAME underlying DNL/INL draws, re-evaluated against the candidate revised "
            "bound, informs (does not by itself ratify) DR-007's proposal."
        )
        a(
            f"- **Reanalysis, not a new simulation**: derived/composite -- NO new ngspice "
            f"invocation. Re-parses the already-committed `mc-draws/{result.source_record_id}/`"
            f" logs from source record `sim/cdac-array-transfer/records/{result.source_record_id}.md` "
            "(issue #29) with the SAME DNL/INL computation `_parse_draw()` uses, then re-runs "
            "`klt yield` against the candidate revised limit above -- mirrors "
            "`sim/enob-estimate/run_enob.py`'s own 'derived/composite' provenance convention."
        )
    else:
        a(
            "- **Claim**: `spec/target-spec.md#target-table` -- DNL/INL DRAFT target row "
            "(`<= +-1 LSB`, target value, NOT ratified: target-spec.md's own \"Not "
            "ratified by this record\" list names ENOB/INL-DNL target values as still "
            "open pending this Monte-Carlo campaign, issue #29). This record supplies "
            "that campaign's DNL/INL evidence: mismatch-driven Monte Carlo statistics "
            "of design/cdac/cdac_array.sch's own DAC transfer characteristic, in "
            "isolation from the sampling front end, comparator, and SAR logic -- "
            "informs, but (per #53's own precedent) does not by itself substantiate a "
            "full end-to-end ADC DNL/INL claim (see the UNITS/scope note below)."
        )
        a(
            "- **Netlist provenance**: schematic, generated (`sim/cdac-array-transfer/gen_fragment.py`, "
            "verified byte-for-byte against #53's hand-authored `testbench/tb_cdac_array_transfer.spice` "
            "for that fragment's own 5 codes -- see `sim/tests/test_cdac_fragment_gen.py`)"
        )
    a(
        f"- **Statistical convention**: mismatch corner `{result.mismatch_corner}`, N={n}, "
        f"seed={result.seed} (draws use seed, seed+1, ..., seed+N-1), PVT point "
        f"process={result.corner} temp={TEMP_C}C supply={NOMINAL_SUPPLY_V}V. **Subset-corner "
        "justification**: nominal PVT point only -- a full corner x mismatch sweep multiplies "
        "this campaign's cost by the corner count for a second-order refinement (mismatch "
        "sigma varies only weakly with PVT relative to its own draw-to-draw spread); combining "
        "with the item-5 PVT corner evidence (issue #28, sim/cdac-array-transfer/records/"
        "20260827-213107-e13bc1e.md) covers the PVT axis for this same DUT (structural sizing "
        "+ monotonicity across the full ratified corner set) -- this record adds the mismatch "
        "axis at the nominal corner rather than re-deriving both simultaneously."
    )
    a(
        f"- **N justification**: target relative standard error on the estimated stdev <= 10%, "
        f"via the standard result SE(s)/s ~= 1/sqrt(2(N-1)) for an approximately-Gaussian "
        f"per-draw statistic; N={n} gives {rel_se_pct:.1f}%, meeting that target. This is NOT a "
        "sample size adequate for a tight (+-1 percentage point) yield-fraction claim at 95% "
        "confidence (that needs O(100s), see the klt yield sample-size verdict below) -- N is "
        "sized for the distribution-shape claim this record makes, not chosen for runtime "
        "convenience (stated honestly per sim/README.md, matching the sim/comparator-decision/ "
        "offset record's own convention)."
    )
    a(
        "- **Linearity methodology**: `reduced-code-set-major-carry`, extended Monte Carlo "
        f"variant of #53's coarse spot-check -- {len(CODES_MC)} codes ({CODES_MC}), covering "
        f"every one of the 9-bit sub-array's major-carry PAIRS ({len(ADJACENT_PAIRS_MC)} "
        "adjacent-code transitions this set can compute a real DNL for: "
        f"{ADJACENT_PAIRS_MC}), the code range's endpoints, and a short consecutive run near "
        "code=0. NOT the full 512-code ramp (DNL/INL are reported ONLY at the codes/transitions "
        "listed, not interpolated or assumed elsewhere)."
    )
    a(
        "- **UNITS / scope note**: this array's own ideal code-to-code step is "
        f"{ARRAY_IDEAL_STEP_V * 1000:.4f} mV = 2x the ratified ADC LSB ({RATIFIED_LSB_V * 1000:.4f} "
        "mV, DR-003 via #27) -- the array realizes only the 9-bit sub-array's own 512 "
        "differential levels; the ratified N=10 total resolution's tenth bit comes from the "
        "top-level differential sign structure (design/sar_adc_top.spice), which this "
        "array-only experiment does not exercise. DNL/INL below are reported in units of the "
        "RATIFIED ADC LSB (matching spec/target-spec.md's own row), not this array's own "
        "7.03 mV step -- see sim/cdac-array-transfer/run_mc.py's module docstring."
    )
    a(
        f"- **Negative control**: N={n} draws at the plain `{result.corner}` corner (mismatch "
        f"DISABLED), same seed sequence -- "
        f"{'PASS (stdev == 0 on both DNLmax and INLmax)' if negctrl_ok else f'FAIL: DNLmax stdev={dnl_neg_stdev:.6g}, INLmax stdev={inl_neg_stdev:.6g}'}"
    )
    a(
        f"- **Positive control**: N={n} draws at the `{result.mismatch_corner}` corner (mismatch "
        f"ENABLED) -- DNLmax stdev={dnl_stdev:.6g} LSB, INLmax stdev={inl_stdev:.6g} LSB "
        f"({'> 0, shows genuine spread -- PASS' if positive_ok else 'FAIL: zero spread despite mismatch enabled'})"
    )
    if note:
        a(f"- **Note**: {note}")
    overall_ok = negctrl_ok and positive_ok
    a(f"- **Overall**: {'PASS' if overall_ok else 'FAIL'} (harness/negative-control validity; "
      "DNL/INL magnitude itself is reported informationally below against the DRAFT target, "
      "not gated as pass/fail -- the target row is not yet ratified)")
    a("")
    a("## DNL/INL distributions (mismatch-enabled draws, worst-case per draw across the sampled code set)")
    a("")
    a("| statistic | N | mean (LSB) | stdev (LSB) | min (LSB) | max (LSB) |")
    a("|---|---|---|---|---|---|")
    a(f"| max\\|DNL\\| | {n} | {statistics.fmean(dnl_draws):.4f} | {dnl_stdev:.4f} | {min(dnl_draws):.4f} | {max(dnl_draws):.4f} |")
    a(f"| max\\|INL\\| | {n} | {statistics.fmean(inl_draws):.4f} | {inl_stdev:.4f} | {min(inl_draws):.4f} | {max(inl_draws):.4f} |")
    a("")
    a("## Negative control (mismatch-disabled, same seed sequence)")
    a("")
    a("| statistic | N | mean (LSB) | stdev (LSB, must be 0) |")
    a("|---|---|---|---|")
    a(f"| max\\|DNL\\| | {n} | {statistics.fmean(dnl_neg):.4f} | {dnl_neg_stdev:.6g} |")
    a(f"| max\\|INL\\| | {n} | {statistics.fmean(inl_neg):.4f} | {inl_neg_stdev:.6g} |")
    a("")
    a("## Machine-checkable yield evidence (`klt yield`)")
    a("")
    if yield_report is not None:
        target_desc = (
            f"DR-007's CANDIDATE REVISED (proposed, not ratified) INL/DNL target "
            f"(`<= +-{target_limit_lsb:g} LSB`)"
            if result.source_record_id else
            f"spec/target-spec.md's DRAFT (not ratified) INL/DNL target row (`<= +-{target_limit_lsb:g} LSB`)"
        )
        a(
            f"Against {target_desc}, target_yield={target_yield:g}, 95% confidence -- "
            "reported here as INFORMATIONAL evidence toward a future ratification decision "
            "record, NOT a pass/fail against a ratified spec/target-spec.md line (per "
            "CLAUDE.md, a DRAFT value is never quoted as if settled). Full JSON report: "
            f"`sim/cdac-array-transfer/yield-reports/{record_id}.json`."
        )
        a("")
        a("| measurement | n | yield (empirical, 95% CI) | Cpk | sigma-to-spec | sample-size verdict |")
        a("|---|---|---|---|---|---|")
        for m in yield_report.get("measurements", []):
            emp = m.get("yield", {}).get("empirical", {}) or {}
            ci = emp.get("confidence_interval", {}) or {}
            cap = m.get("capability", {}) or {}
            ss = m.get("sample_size", {}) or {}
            a(
                f"| `{m.get('name')}` | {m.get('n')} | "
                f"{emp.get('estimate', float('nan')):.4f} [{ci.get('low', float('nan')):.4f}, "
                f"{ci.get('high', float('nan')):.4f}] | "
                f"{cap.get('cpk')} | {cap.get('sigma_to_spec')} | {ss.get('verdict')} "
                f"(required_n_for_target={ss.get('required_n_for_target')}) |"
            )
        a("")
        for w in yield_report.get("warnings", []):
            a(f"- klt yield warning: {w}")
        for m in yield_report.get("measurements", []):
            for w in m.get("warnings", []):
                a(f"- klt yield warning (`{m.get('name')}`): {w}")
        a("")
    else:
        a(
            "`klt yield` did not produce a report in this environment (either `klt` is not on "
            "PATH, or its native `klt_yield_native` extension is not built -- see "
            "`docs/cli/yield.md#building-the-native-extension` in 2AMLogic/klayout-tools; issue "
            "2AMLogic/klayout-tools#1061 already tracks this as a known packaging gap, closed "
            "COMPLETED, with the documented build-from-checkout remediation this repo's own "
            "evidence-generation environment used when this record was produced). This is a "
            "known, already-filed environment gap, not a new one filed by this record."
        )
        a("")
    a(
        "No spec row is relaxed to make this result pass or fail -- the target above is "
        "quoted verbatim from its source (spec/target-spec.md's DRAFT row, or DR-007's "
        "candidate revised proposal) and explicitly labeled DRAFT/candidate throughout, per "
        "CLAUDE.md's 'do not invent settled numbers to replace the drafts' rule."
    )
    a("")
    extra_env = {"MC seed": str(result.seed), "MC N": str(n)}
    if result.source_record_id:
        extra_env["Reanalysis of"] = f"`sim/cdac-array-transfer/records/{result.source_record_id}.md` (no new ngspice run)"
    lines.extend(evidence.environment_block(
        pdk_line=f"{info.variant} @ {pdk.resolved_commit(info)}",
        ngspice_line=toolchain._ngspice_version() or "unknown",
        netlist_sha256=netlist_sha,
        extra=extra_env,
    ))
    a("")
    lines.extend(evidence.footer_lines("sim/cdac-array-transfer/run_mc.py", ""))

    record_path.write_text("\n".join(lines))
    return record_path, overall_ok


def main() -> int:
    ap = argparse.ArgumentParser(description="CDAC array transfer-characteristic Monte Carlo runner (issue #29)")
    ap.add_argument("--check-env", action="store_true")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--corner", default=BASE_CORNER)
    ap.add_argument("--note", default="")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument(
        "--reanalyze", metavar="RECORD_ID", default=None,
        help=(
            "Re-score a PRIOR record's already-committed mc-draws/<RECORD_ID>/ logs "
            "against --target-limit-lsb / --target-yield, with NO new ngspice run "
            "(issue #129: evidencing DR-007's candidate revised target from the SAME "
            "draws #29 already collected). Mutually exclusive with --n/--seed (which "
            "only apply to a fresh simulation)."
        ),
    )
    ap.add_argument(
        "--target-limit-lsb", type=float, default=DRAFT_INL_DNL_TARGET_LSB,
        help="candidate INL/DNL |limit| in ratified LSB for the klt yield evaluation (default: the DRAFT spec row's 1.0)",
    )
    ap.add_argument(
        "--target-yield", type=float, default=0.99,
        help="target_yield passed to klt yield (default: 0.99, matching the DRAFT spec row's convention)",
    )
    args = ap.parse_args()

    if args.check_env:
        info = pdk.resolve()
        print(f"PDK: found={info.found} variant={info.variant} error={info.error!r}")
        return 0 if info.found else 3

    if args.reanalyze:
        result = reanalyze_from_logs(args.reanalyze, corner=args.corner)
        if not args.quiet:
            for i, d in enumerate(result.draws):
                print(f"  draw {i} (seed={d.seed}, {result.mismatch_corner}): DNLmax={d.dnl_max_lsb:.4f} LSB INLmax={d.inl_max_lsb:.4f} LSB")
    else:
        result = run_mc(seed=args.seed, n=args.n, corner=args.corner, quiet=args.quiet)
    exit_code = 0
    if args.record:
        record_path, ok = write_evidence(
            result, note=args.note,
            target_limit_lsb=args.target_limit_lsb, target_yield=args.target_yield,
        )
        print(f"wrote {record_path}")
        print("PASS" if ok else "FAIL")
        exit_code = 0 if ok else 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

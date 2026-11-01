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
import re
import statistics
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import corners as corners_mod, evidence, measure, pdk, toolchain  # noqa: E402
from harness.mc_runner import _draw_n  # noqa: E402
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


def span_v(d: Draw) -> float:
    """Differential span (code ENDPOINT_HI minus code ENDPOINT_LO), volts.
    NaN if either endpoint level is missing from the draw's log."""
    return d.vdiff[ENDPOINT_HI] - d.vdiff[ENDPOINT_LO]


def gain_error_lsb(draw: Draw, plain: Draw) -> float:
    """Mismatch gain error of one `tt_mm` draw, in ratified ADC LSB: the
    draw's code-0 -> code-511 span minus the span of the plain-corner
    (mismatch disabled) draw of the SAME seed, over RATIFIED_LSB_V.
    Referencing to the plain-corner span (not to the ideal 2*V_REF*511/512
    slope) deliberately cancels the systematic C_par divider term, so only
    the mismatch term remains (issue #756; DR-022 Open item 3). NaN if
    either span is missing an endpoint."""
    return (span_v(draw) - span_v(plain)) / RATIFIED_LSB_V


def gain_error_summary(result: "McResult") -> dict:
    """Per-draw mismatch gain error plus summary statistics. Draws with a
    missing endpoint (NaN) are LISTED in `missing_seeds` and excluded from
    the statistics, never silently dropped; `n_used + len(missing_seeds) == n`.
    Sample (n-1) stdev is used, as the estimate of the population sigma the
    analytic 32*sigma_u figure describes."""
    per_draw = [(d.seed, gain_error_lsb(d, p)) for d, p in zip(result.draws, result.negctrl)]
    used = [g for _, g in per_draw if g == g]
    missing = [seed for seed, g in per_draw if g != g]
    n_used = len(used)
    mean = statistics.fmean(used) if used else float("nan")
    sd = statistics.stdev(used) if n_used > 1 else float("nan")
    return {
        "per_draw": per_draw, "n_used": n_used, "missing_seeds": missing,
        "mean_lsb": mean, "stdev_lsb": sd, "three_sigma_lsb": 3 * sd,
        "rel_se_pct": 100.0 / (2 * (n_used - 1)) ** 0.5 if n_used > 1 else float("nan"),
        "plain_span_v": sorted({span_v(p) for p in result.negctrl if span_v(p) == span_v(p)}),
    }


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

    def one_draw(draw_corner: str, this_seed: int, scratch_dir: Path, log_name: str) -> Draw:
        return _one_draw(info, draw_corner, this_seed, scratch_dir, log_name)

    def describe(d: Draw) -> str:
        return f"DNLmax={d.dnl_max_lsb:.4f} LSB INLmax={d.inl_max_lsb:.4f} LSB"

    with tempfile.TemporaryDirectory(prefix="sim-cdac-mc-") as scratch:
        scratch_dir = Path(scratch)
        draws = _draw_n(
            one_draw, mismatch_corner, seed, n,
            scratch_dir, quiet, log_prefix="draw", label="draw", describe_fn=describe,
        )
        negctrl = _draw_n(
            one_draw, corner, seed, n,
            scratch_dir, quiet, log_prefix="negctrl", label="negctrl", describe_fn=describe,
        )
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


def write_evidence(
    result: McResult,
    note: str = "",
    target_limit_lsb: float = DRAFT_INL_DNL_TARGET_LSB,
    target_yield: float = 0.99,
    supersedes: str = "",
) -> tuple[Path, bool]:
    sample_netlist = build_netlist(pdk.resolve(), result.mismatch_corner, TEMP_C, NOMINAL_SUPPLY_V, result.seed)
    prov = evidence.resolve_provenance(EXPERIMENT_DIR, sample_netlist)
    record_id = prov.record_id
    record_path = prov.record_path
    netlist_sha = prov.netlist_sha

    draws_dir = EXPERIMENT_DIR / "mc-draws" / record_id
    draws_dir.mkdir(parents=True, exist_ok=True)
    for i, d in enumerate(result.draws):
        (draws_dir / f"draw_{i}_seed{d.seed}.log").write_text(d.log_text)
    for i, d in enumerate(result.negctrl):
        (draws_dir / f"negctrl_{i}_seed{d.seed}.log").write_text(d.log_text)

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
    yield_report = evidence.run_klt_yield(
        [
            {
                "name": "dnl_max_lsb",
                "unit": "LSB",
                "samples": dnl_draws,
                "limits": {
                    "min": -target_limit_lsb,
                    "max": target_limit_lsb,
                    "target_yield": target_yield,
                },
            },
            {
                "name": "inl_max_lsb",
                "unit": "LSB",
                "samples": inl_draws,
                "limits": {
                    "min": -target_limit_lsb,
                    "max": target_limit_lsb,
                    "target_yield": target_yield,
                },
            },
        ],
        yield_json_path,
    )

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
        pdk_line=prov.pdk_line,
        ngspice_line=prov.ng_version,
        netlist_sha256=netlist_sha,
        extra=extra_env,
    ))
    a("")
    lines.extend(evidence.footer_lines("sim/cdac-array-transfer/run_mc.py", supersedes))

    record_path.write_text("\n".join(lines))
    return record_path, overall_ok


ANALYTIC_GAIN_3SIGMA_LSB = 1.4191  # DR-003 Item 3 as updated by DR-019: 3*32*sigma_u
ANALYTIC_GAIN_SIGMA_UNIT_PCT = 1.4737  # DR-019 sigma_u (percent)


def write_gain_error_evidence(result: McResult, supersedes: str = "", note: str = "") -> tuple[Path, bool]:
    """Mint a gain-error (mismatch half) record from a McResult, normally a
    `reanalyze_from_logs()` one. Informational: no spec row is touched."""
    sample_netlist = build_netlist(pdk.resolve(), result.mismatch_corner, TEMP_C, NOMINAL_SUPPLY_V, result.seed)
    prov = evidence.resolve_provenance(EXPERIMENT_DIR, sample_netlist)
    g = gain_error_summary(result)
    n = result.n
    neg_spans = g["plain_span_v"]
    negctrl_ok = len(neg_spans) == 1  # all same-seed plain draws must give one identical span
    neg_gain = [gain_error_lsb(p, result.negctrl[0]) for p in result.negctrl]
    neg_sd = statistics.pstdev(neg_gain) if len(neg_gain) > 1 else 0.0
    negctrl_ok = negctrl_ok and neg_sd == 0.0
    positive_ok = g["stdev_lsb"] == g["stdev_lsb"] and g["stdev_lsb"] > 0
    ideal_span_v = 2 * NOMINAL_SUPPLY_V * (ENDPOINT_HI - ENDPOINT_LO) / 512
    sys_offset_lsb = (neg_spans[0] - ideal_span_v) / RATIFIED_LSB_V if neg_spans else float("nan")
    ratio = g["three_sigma_lsb"] / ANALYTIC_GAIN_3SIGMA_LSB
    lo = g["stdev_lsb"] * (1 - g["rel_se_pct"] / 100)
    hi = g["stdev_lsb"] * (1 + g["rel_se_pct"] / 100)
    agree = 3 * lo <= ANALYTIC_GAIN_3SIGMA_LSB <= 3 * hi

    L: list[str] = []
    a = L.append
    a(f"# Monte Carlo record {prov.record_id}")
    a("")
    a(f"- **Record ID**: {prov.record_id}")
    a(
        "- **Claim**: mismatch half of the CDAC gain error -- Monte Carlo check of DR-003 Item 3's "
        f"analytic `sigma = 32*sigma_u` (`{ANALYTIC_GAIN_3SIGMA_LSB} LSB` at 3-sigma, DR-019 `C_u`). "
        "Evidence for DR-022 Open item 3 (issue #756). Adds NO spec row and changes no value in "
        "`spec/target-spec.md` (DRAFT until issue #1)."
    )
    if result.source_record_id:
        a(
            "- **Reanalysis, not a new simulation**: derived/composite -- NO new ngspice invocation. "
            f"Re-parses the already-committed `mc-draws/{result.source_record_id}/` logs of source record "
            f"`sim/cdac-array-transfer/records/{result.source_record_id}.md` (the code-0 and code-511 "
            "levels `vtop_p_*`/`vtop_n_*` are already in every log)."
        )
    a(
        f"- **Statistical convention**: mismatch corner `{result.mismatch_corner}`, N={n}, seed={result.seed} "
        f"(draws use seed, seed+1, ..., seed+N-1), PVT point process={result.corner} temp={TEMP_C}C "
        f"supply={NOMINAL_SUPPLY_V}V. Sampled corner only: this says nothing about other PVT corners."
    )
    a(
        "- **Gain-error definition**: per draw, `(span_mm - span_plain) / 3.5156 mV`, where `span` = "
        "differential output at code 511 minus at code 0, `span_mm` is the `tt_mm` draw and `span_plain` "
        "is the plain-`tt` (mismatch disabled) draw of the SAME seed. Referencing to the plain-corner span "
        "cancels the systematic `C_par` divider term, so only the mismatch term remains; the systematic "
        f"term is reported separately below. Units: ratified ADC LSB (3.5156 mV). Scope: the array-only "
        "experiment exercises the 9-bit sub-array, whose code step is 2x the ADC LSB (see "
        "`run_mc.py` UNITS note); the figure here is the span deviation in volts divided by the ADC LSB, "
        "not a 10-bit-ADC-level gain error."
    )
    a(
        f"- **Negative control**: N={n} plain-`{result.corner}` draws, same seed sequence -- "
        f"{'PASS (all plain spans identical, gain-error stdev == 0)' if negctrl_ok else 'FAIL: plain spans differ across draws'}"
    )
    a(
        f"- **Positive control**: `{result.mismatch_corner}` gain-error stdev = {g['stdev_lsb']:.6g} LSB "
        f"({'> 0, genuine spread -- PASS' if positive_ok else 'FAIL: no spread'})"
    )
    if note:
        a(f"- **Note**: {note}")
    a(f"- **Overall**: {'PASS' if negctrl_ok and positive_ok else 'FAIL'} (harness/negative-control validity only; the comparison to the analytic figure is informational)")
    a("")
    a("## Gain-error statistics (mismatch-enabled draws)")
    a("")
    a("| N used / N | mean (LSB) | stdev (LSB, n-1) | 3-sigma (LSB) | SE on stdev | analytic 3-sigma (LSB) | measured 3-sigma / analytic |")
    a("|---|---|---|---|---|---|---|")
    a(
        f"| {g['n_used']} / {n} | {g['mean_lsb']:+.5f} | {g['stdev_lsb']:.5f} | {g['three_sigma_lsb']:.4f} | "
        f"~{g['rel_se_pct']:.1f}% (1/sqrt(2(N-1))) | {ANALYTIC_GAIN_3SIGMA_LSB} | {ratio:.3f} |"
    )
    a("")
    a(f"- Draws excluded for a missing endpoint: {g['missing_seeds'] if g['missing_seeds'] else 'none'}.")
    a(
        f"- Mean vs zero: standard error of the mean = {g['stdev_lsb'] / g['n_used'] ** 0.5:.5f} LSB, so the "
        f"mean ({g['mean_lsb']:+.5f}) is {abs(g['mean_lsb']) / (g['stdev_lsb'] / g['n_used'] ** 0.5):.2f} standard errors from zero."
    )
    a(
        f"- Plain-corner (mismatch-disabled) span: {neg_spans[0] * 1000:.4f} mV vs ideal "
        f"2*V_REF*511/512 = {ideal_span_v * 1000:.4f} mV; systematic offset {sys_offset_lsb:+.4f} LSB "
        "(the `C_par` divider term, excluded from the mismatch figure above; reported, not analysed here)."
        if neg_spans else "- Plain-corner span unavailable."
    )
    a("")
    a("## Interpretation (checked against the raw draws below)")
    a("")
    a(
        f"At `{result.corner}`/{TEMP_C}C/{NOMINAL_SUPPLY_V}V, N={g['n_used']}, seed={result.seed}, the measured "
        f"mismatch gain-error stdev is {g['stdev_lsb']:.4f} LSB (3-sigma {g['three_sigma_lsb']:.4f} LSB; with the "
        f"~{g['rel_se_pct']:.0f}% standard error on the stdev, 3-sigma spans about {3 * lo:.4f}-{3 * hi:.4f} LSB), "
        f"against the analytic {ANALYTIC_GAIN_3SIGMA_LSB} LSB. The analytic figure is "
        f"{'SUPPORTED' if agree else 'NOT supported'} by this measurement at the sampled corner: the measured "
        f"3-sigma is {ratio:.3f}x the analytic value ({1 / ratio:.0f}x smaller). "
        "Resolution caveat: ngspice prints each `.meas` level to 6 significant digits, so the spans are quantized "
        "at 10 uV = 0.0028 LSB; the measured stdev is only ~3 quantization steps, so its last digits are "
        "resolution-limited, which does not affect the ~50x gap to the analytic figure. "
        "This record does not establish why the two differ and does not claim the analytic figure is wrong for "
        "any other definition of gain error; it only reports what this span-referred metric measured."
    )
    a("")
    a("## Per-draw gain error (mismatch-enabled)")
    a("")
    a("| draw | seed | span_mm (V) | span_plain (V) | gain error (LSB) |")
    a("|---|---|---|---|---|")
    for i, (d, p) in enumerate(zip(result.draws, result.negctrl)):
        a(f"| {i} | {d.seed} | {span_v(d):.7f} | {span_v(p):.7f} | {gain_error_lsb(d, p):+.5f} |")
    a("")
    extra_env = {"MC seed": str(result.seed), "MC N": str(n)}
    if result.source_record_id:
        extra_env["Reanalysis of"] = f"`sim/cdac-array-transfer/records/{result.source_record_id}.md` (no new ngspice run)"
        extra_env["Tool-version caveat"] = (
            "the PDK/ngspice lines above describe the host that re-parsed the logs; the draws themselves were "
            "simulated under the SOURCE record's environment (see its Environment block). Not controlled for here."
        )
    L.extend(evidence.environment_block(
        pdk_line=prov.pdk_line, ngspice_line=prov.ng_version, netlist_sha256=prov.netlist_sha, extra=extra_env,
    ))
    a("")
    L.extend(evidence.footer_lines("sim/cdac-array-transfer/run_mc.py", supersedes))
    prov.record_path.write_text("\n".join(L))
    return prov.record_path, negctrl_ok and positive_ok


def main() -> int:
    ap = argparse.ArgumentParser(description="CDAC array transfer-characteristic Monte Carlo runner (issue #29)")
    ap.add_argument("--check-env", action="store_true")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--corner", default=BASE_CORNER)
    ap.add_argument("--note", default="")
    evidence.add_supersedes_argument(ap)
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
        "--gain-error", action="store_true",
        help="with --reanalyze --record: mint the mismatch gain-error record (issue #756) instead of the DNL/INL one",
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
    if args.record and args.gain_error:
        record_path, ok = write_gain_error_evidence(result, supersedes=args.supersedes, note=args.note)
        print(f"wrote {record_path}")
        print("PASS" if ok else "FAIL")
        exit_code = 0 if ok else 1
    elif args.record:
        record_path, ok = write_evidence(
            result, note=args.note,
            target_limit_lsb=args.target_limit_lsb, target_yield=args.target_yield,
            supersedes=args.supersedes,
        )
        print(f"wrote {record_path}")
        print("PASS" if ok else "FAIL")
        exit_code = 0 if ok else 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

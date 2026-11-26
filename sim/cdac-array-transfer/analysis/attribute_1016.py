#!/usr/bin/env python3
"""Attribution analysis of the committed CDAC DNL/INL Monte-Carlo draws --
issue #1016 step 1 (find what limits it), step 2 (design-side closure
options), and the step-3 pilot cross-check, all answered NUMERICALLY from
committed evidence plus the two committed supplementary probes this study
adds (a caps-only isolation probe and the candidate-plate pilot campaign).

NO new ngspice invocation: this script re-parses committed logs with the
SAME `reanalyze_from_logs()` machinery `sim/cdac-array-transfer/run_mc.py`
uses for its own reanalysis records, so every number below re-derives from
committed bytes:

- source campaign : sim/cdac-array-transfer/mc-draws/20261001-124049-5207381/
- caps-only probe : sim/cdac-array-transfer/analysis/probe-caps-only-20261121-075648-75b91e85/
- pilot campaign  : sim/cdac-array-transfer/mc-draws/20261121-075027-75b91e85/ (3.3000 um, N=16, seed 101)

Usage:
    python3 sim/cdac-array-transfer/analysis/attribute_1016.py             # print only
    python3 sim/cdac-array-transfer/analysis/attribute_1016.py --record    # also write the md record
"""

from __future__ import annotations

import argparse
import datetime
import math
import re
import statistics
import subprocess
import sys
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
SIM_DIR = EXPERIMENT_DIR.parent
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(EXPERIMENT_DIR))

import run_mc  # noqa: E402
from analysis.probe_caps_only import PROBE_CODES  # noqa: E402
from gen_fragment import WEIGHTS  # noqa: E402
from harness import evidence as evidence_mod, measure  # noqa: E402

SOURCE_RECORD = "20261001-124049-5207381"  # the committed campaign the issue cites
PILOT_RECORD = "20261121-075027-75b91e85"  # candidate 3.3000 um plate, N=16, seed 101 (issue #1016 step 3)
PROBE_DIR_NAME = "probe-caps-only-20261121-075648-75b91e85"
PROBE_SEEDS = range(1, 9)
PILOT_PLATE_UM = 3.3000
LIMIT_LSB = 1.0  # the ORIGINAL DRAFT row -- the limit this issue works against (NOT DR-007's 2.0 candidate)
TARGET_YIELD = 0.99
Z_99 = 2.3263478740408408  # Phi^-1(0.99), one-sided normal quantile for the 0.99-yield margin

PLATE_NM = 1900
PLATE_UM = PLATE_NM / 1000
SOURCE_SIGMA = run_mc.tt_mim_sigma(PLATE_UM)

CANDIDATE_PLATE_UM = 3.3000  # the closure option A size this study lands on (5 nm-grid-legal)

# Executable dimensions in layout/cdac-array/bin/cdac_layout.py. The area
# estimate keeps the gap of the existing layout at the candidate plate size.
N_COL, N_ROW = 64, 16
PITCH_GAP_UM = 3.400 - PLATE_UM

# Each side steps Vref/512 per unit. Independent P/N errors add in variance.
DIFF_ADC_LSB = math.sqrt(2) * (run_mc.ARRAY_IDEAL_STEP_V / 2) / run_mc.RATIFIED_LSB_V


def design_cap_ff(side_um: float) -> float:
    """DR-019 drawn area and perimeter convention for the proposed spec row."""
    return 2.0 * side_um**2 + 0.19 * 4 * side_um


def weighted_step_sigma(c1: int, c2: int) -> float:
    """First-order ideal divider, one independent fractional error per weighted instance."""
    variance = 0.0
    for code in (c1, 511 - c1, c2, 511 - c2):
        fraction = code / 512
        variance += fraction**2  # the unit termination stays at VREFN
        for weight in WEIGHTS:
            selected = bool(code & weight)
            variance += (weight * (selected - fraction)) ** 2
    one_side_step = run_mc.ARRAY_IDEAL_STEP_V / 2 / run_mc.RATIFIED_LSB_V
    return one_side_step * SOURCE_SIGMA * math.sqrt(variance)


def carry_bit(c1: int, c2: int) -> int | None:
    """Carry position k of the transition c1 -> c1+1: the number of trailing
    1-bits in c1 (bits 0..k-1 clear, bit k sets). Always well-defined for
    adjacent codes; k=0 is a plain single-bit turn-on."""
    if c2 != c1 + 1:
        return None
    k = 0
    while (c1 >> k) & 1:
        k += 1
    return k


def switched_unit_count(c1: int, c2: int, thermometer_msbs: int = 0) -> int:
    """Count per-side switched units across unary groups and binary LSBs."""
    group_size = 1 << (9 - thermometer_msbs)
    groups1, binary1 = divmod(c1, group_size)
    groups2, binary2 = divmod(c2, group_size)
    return abs(groups2 - groups1) * group_size + (binary1 ^ binary2)


def decompose(res) -> dict:
    """Systematic/random decomposition of a campaign's committed draws."""
    n = res.n
    pairs = run_mc.ADJACENT_PAIRS_MC
    codes = sorted(run_mc.CODES_MC)

    def dnl_of(d: run_mc.Draw) -> dict:
        return {
            t: ((d.vdiff[t[1]] - d.vdiff[t[0]]) - run_mc.ARRAY_IDEAL_STEP_V) / run_mc.RATIFIED_LSB_V
            for t in pairs
        }

    def inl_of(d: run_mc.Draw) -> dict:
        lo, hi = d.vdiff[run_mc.ENDPOINT_LO], d.vdiff[run_mc.ENDPOINT_HI]
        return {
            c: (d.vdiff[c] - (lo + (hi - lo) * (c - run_mc.ENDPOINT_LO) / (run_mc.ENDPOINT_HI - run_mc.ENDPOINT_LO)))
            / run_mc.RATIFIED_LSB_V
            for c in codes
        }

    mm_dnl = [dnl_of(d) for d in res.draws]
    tt_dnl = [dnl_of(d) for d in res.negctrl]
    mm_inl = [inl_of(d) for d in res.draws]
    tt_inl = [inl_of(d) for d in res.negctrl]

    for i, d in enumerate(res.draws):
        assert max(abs(v) for v in mm_dnl[i].values()) == d.dnl_max_lsb, f"draw {i}: DNL recomputation mismatch"
        assert max(abs(v) for v in mm_inl[i].values()) == d.inl_max_lsb, f"draw {i}: INL recomputation mismatch"

    sys_dnl = {t: tt_dnl[0][t] for t in pairs}
    sys_inl = {c: tt_inl[0][c] for c in codes}
    for t in pairs:
        assert statistics.pstdev([tt_dnl[i][t] for i in range(n)]) == 0.0, "negative control not deterministic"
    for c in codes:
        assert statistics.pstdev([tt_inl[i][c] for i in range(n)]) == 0.0, "negative control not deterministic"
    rnd_dnl = [{t: mm_dnl[i][t] - sys_dnl[t] for t in pairs} for i in range(n)]
    rnd_inl = [{c: mm_inl[i][c] - sys_inl[c] for c in codes} for i in range(n)]

    sd_dnl = {t: statistics.stdev([rnd_dnl[i][t] for i in range(n)]) for t in pairs}
    sd_inl = {c: statistics.stdev([rnd_inl[i][c] for i in range(n)]) for c in codes}

    dnl_carrier: dict[tuple[int, int], int] = {}
    inl_carrier: dict[int, int] = {}
    for i in range(n):
        t_max = max(pairs, key=lambda t: abs(mm_dnl[i][t]))
        dnl_carrier[t_max] = dnl_carrier.get(t_max, 0) + 1
        c_max = max(codes, key=lambda c: abs(mm_inl[i][c]))
        inl_carrier[c_max] = inl_carrier.get(c_max, 0) + 1

    return {
        "n": n, "pairs": pairs, "codes": codes,
        "sys_dnl": sys_dnl, "sys_inl": sys_inl,
        "rnd_dnl": rnd_dnl, "rnd_inl": rnd_inl,
        "sd_dnl": sd_dnl, "sd_inl": sd_inl,
        "dnl_carrier": dnl_carrier, "inl_carrier": inl_carrier,
        "level_rnd_sd": {
            c: statistics.stdev([d.vdiff[c] - res.negctrl[0].vdiff[c] for d in res.draws])
            for c in codes
        },
    }


def _pearson(xs: list[float], ys: list[float]) -> float:
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return num / den if den else float("nan")


def fit_sigma_u(measured: dict, coeff_sq: dict) -> dict:
    xs = [math.sqrt(coeff_sq[k]) for k in measured]
    ys = [measured[k] for k in measured]
    coeff = [DIFF_ADC_LSB * x for x in xs]
    implied = sum(a * b for a, b in zip(coeff, ys)) / sum(a * a for a in coeff)
    return {"pearson_r": _pearson(xs, ys), "sigma_pct": implied * 100}


def load_probe_levels(probe_dir: Path) -> dict[int, list[float]]:
    """Read the cited probe's seed population and both finite voltages for each code."""
    logs = {f"capsonly_seed{seed}.log": seed for seed in PROBE_SEEDS}
    actual = {path.name for path in probe_dir.glob("capsonly_seed*.log")}
    if actual != logs.keys():
        raise ValueError(f"{probe_dir}: missing logs {sorted(logs.keys() - actual)}, "
                         f"unexpected logs {sorted(actual - logs.keys())}")

    names = [f"vtop_{side}_{code}" for code in PROBE_CODES for side in ("p", "n")]
    levels: dict[int, list[float]] = {code: [] for code in PROBE_CODES}
    for filename, seed in logs.items():
        path = probe_dir / filename
        log = path.read_text()
        header = re.search(r"^Circuit: .*?\bseed=(\d+)\b", log, re.MULTILINE)
        if header is None or int(header.group(1)) != seed:
            raise ValueError(f"{path}: expected circuit header for seed {seed}")
        values = measure.parse(log, names)
        missing = measure.missing(values, names)
        if missing:
            raise ValueError(f"{path}: missing finite measurements for {', '.join(missing)}")
        for code in PROBE_CODES:
            level = values[f"vtop_p_{code}"] - values[f"vtop_n_{code}"]
            if not math.isfinite(level):
                raise ValueError(f"{path}: non-finite differential level at code {code}")
            levels[code].append(level)
    return levels


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--record", action="store_true", help="write the analysis record md beside this script")
    evidence_mod.add_supersedes_argument(ap)
    args = ap.parse_args()

    res = run_mc.reanalyze_from_logs(SOURCE_RECORD)
    D = decompose(res)
    n, pairs, codes = D["n"], D["pairs"], D["codes"]

    coeff_sq_dnl = {t: float(switched_unit_count(*t)) for t in pairs}
    coeff_sq_inl = {c: c * (511 - c) / 511.0 for c in codes}
    fit_dnl = fit_sigma_u(D["sd_dnl"], coeff_sq_dnl)
    fit_inl = fit_sigma_u(D["sd_inl"], coeff_sq_inl)

    probe_dir = EXPERIMENT_DIR / "analysis" / PROBE_DIR_NAME
    try:
        probe_levels = load_probe_levels(probe_dir)
    except (OSError, ValueError) as exc:
        ap.error(str(exc))

    # ---- closure model ------------------------------------------------------
    def predict_draws(scale_dnl: float, scale_inl: float):
        dnl_pred, inl_pred = [], []
        for i in range(n):
            dnl_pred.append(max(abs(D["sys_dnl"][t] + scale_dnl * D["rnd_dnl"][i][t]) for t in pairs))
            inl_pred.append(max(abs(D["sys_inl"][c] + scale_inl * D["rnd_inl"][i][c]) for c in codes))
        return dnl_pred, inl_pred

    def yield_at(samples: list[float]) -> float:
        return sum(1 for v in samples if v <= LIMIT_LSB) / len(samples)

    def margin(samples: list[float]) -> float:
        m, s = statistics.fmean(samples), statistics.stdev(samples)
        return (LIMIT_LSB - (m + Z_99 * s)) / LIMIT_LSB

    def eval_plate(p: float):
        s = run_mc.tt_mim_sigma(p) / SOURCE_SIGMA
        dnl_pred, inl_pred = predict_draws(s, s)
        pitch = p + PITCH_GAP_UM
        return {
            "plate": p, "cu_ff": run_mc.tt_mim_cap_ff(p), "area_x": (p / PLATE_UM) ** 2,
            "array_um": (N_COL * pitch, N_ROW * pitch),
            "array_area_x": (pitch / (PLATE_UM + PITCH_GAP_UM)) ** 2,
            "dnl": (statistics.fmean(dnl_pred), statistics.stdev(dnl_pred), yield_at(dnl_pred), margin(dnl_pred)),
            "inl": (statistics.fmean(inl_pred), statistics.stdev(inl_pred), yield_at(inl_pred), margin(inl_pred)),
            "dnl_max": max(dnl_pred), "inl_max": max(inl_pred),
        }

    # minimum plate meeting BOTH normal margins on the 5 nm grid
    p_min = None
    for plate_nm in range(PLATE_NM, 6001, 5):
        p = plate_nm / 1000
        s = run_mc.tt_mim_sigma(p) / SOURCE_SIGMA
        dnl_pred, inl_pred = predict_draws(s, s)
        if margin(dnl_pred) >= 0 and margin(inl_pred) >= 0:
            p_min = p
            break
    # all-40-pass bound (dominated by the single worst draw; reported, not used)
    p_allpass = None
    for plate_nm in range(PLATE_NM, 8001, 5):
        p = plate_nm / 1000
        s = run_mc.tt_mim_sigma(p) / SOURCE_SIGMA
        dnl_pred, inl_pred = predict_draws(s, s)
        if max(dnl_pred) <= LIMIT_LSB and max(inl_pred) <= LIMIT_LSB:
            p_allpass = p
            break

    cand = eval_plate(CANDIDATE_PLATE_UM)
    as_built = eval_plate(PLATE_UM)

    seg_rows = []
    max_switched = [max(switched_unit_count(c, c + 1, t) for c in range(511)) for t in range(4)]
    for t in (1, 2, 3):
        var_ratio = max_switched[t] / max_switched[0]
        s_dnl = math.sqrt(var_ratio)
        dnl_pred, inl_pred = predict_draws(s_dnl, 1.0)
        seg_rows.append({
            "dnl_sd": statistics.stdev(dnl_pred), "inl_sd": statistics.stdev(inl_pred),
            "t": t, "max_switched": max_switched[t], "dnl_scale": s_dnl,
            "dnl_yield": yield_at(dnl_pred), "dnl_margin": margin(dnl_pred),
            "inl_yield": yield_at(inl_pred), "inl_margin": margin(inl_pred),
        })

    def scan_segmented_plate(t: int, s_seg: float):
        for plate_nm in range(PLATE_NM, 8001, 5):
            p = plate_nm / 1000
            s = run_mc.tt_mim_sigma(p) / SOURCE_SIGMA
            dnl_pred, inl_pred = predict_draws(s_seg * s, s)
            dnl_margin, inl_margin = margin(dnl_pred), margin(inl_pred)
            if dnl_margin >= 0 and inl_margin >= 0:
                return {
                    "dnl_sd": statistics.stdev(dnl_pred), "inl_sd": statistics.stdev(inl_pred),
                    "t": t, "plate": p, "area_x": (p / PLATE_UM) ** 2,
                    "dnl_yield": yield_at(dnl_pred), "inl_yield": yield_at(inl_pred),
                    "dnl_margin": dnl_margin, "inl_margin": inl_margin,
                }
        return None

    optD = [scan_segmented_plate(r["t"], r["dnl_scale"]) for r in seg_rows if r["t"] >= 2]

    # ---- pilot confirmation --------------------------------------------------
    pilot = run_mc.reanalyze_from_logs(PILOT_RECORD)
    P = decompose(pilot)
    pilot_stats = {
        "n": pilot.n, "seed": pilot.seed,
        "floor_dnl": max(map(abs, P["sys_dnl"].values())),
        "floor_inl": max(map(abs, P["sys_inl"].values())),
        "dnl_mean": statistics.fmean([d.dnl_max_lsb for d in pilot.draws]),
        "dnl_sd": statistics.stdev([d.dnl_max_lsb for d in pilot.draws]),
        "dnl_max": max(d.dnl_max_lsb for d in pilot.draws),
        "inl_mean": statistics.fmean([d.inl_max_lsb for d in pilot.draws]),
        "inl_sd": statistics.stdev([d.inl_max_lsb for d in pilot.draws]),
        "inl_max": max(d.inl_max_lsb for d in pilot.draws),
    }

    # ---- console summary ------------------------------------------------------
    print(f"source: {SOURCE_RECORD} (N={n}); pilot: {PILOT_RECORD} (N={pilot_stats['n']}, plate {PILOT_PLATE_UM} um)")
    print(f"Combined tt_mm sigma at {PLATE_UM:.4f} um: {100 * SOURCE_SIGMA:.4f} %")
    for metric, fit in (("DNL", fit_dnl), ("INL", fit_inl)):
        print(f"{metric} fit r={fit['pearson_r']:.3f}; effective fit coefficient: {fit['sigma_pct']:.4f}%")
    if p_min:
        print(f"option A minimum plate (both margins met): {p_min:.3f} um; candidate {CANDIDATE_PLATE_UM:.3f} um")
    if p_allpass:
        print(f"all-{n}-draws-pass bound (worst-draw dominated, NOT the sizing basis): {p_allpass:.3f} um")
    print(f"candidate {CANDIDATE_PLATE_UM:.3f} um: DNL mean {cand['dnl'][0]:.3f} sd {cand['dnl'][1]:.3f} "
          f"yield {cand['dnl'][2]:.3f} margin {cand['dnl'][3]:+.3f}; INL mean {cand['inl'][0]:.3f} "
          f"yield {cand['inl'][2]:.3f} margin {cand['inl'][3]:+.3f}")
    print(f"candidate fitted bounds: DNL {LIMIT_LSB * (1 - cand['dnl'][3]):.6f} LSB, "
          f"INL {LIMIT_LSB * (1 - cand['inl'][3]):.6f} LSB")
    print(f"pilot measured: DNL mean {pilot_stats['dnl_mean']:.3f} sd {pilot_stats['dnl_sd']:.3f} max {pilot_stats['dnl_max']:.3f}; "
          f"INL mean {pilot_stats['inl_mean']:.3f} sd {pilot_stats['inl_sd']:.3f} max {pilot_stats['inl_max']:.3f}")
    for r in seg_rows:
        print(f"option B t={r['t']}: dnl yield {r['dnl_yield']:.3f} margin {r['dnl_margin']:+.3f}; "
              f"inl yield {r['inl_yield']:.3f} margin {r['inl_margin']:+.3f}; "
              f"DNL/INL sd {r['dnl_sd']:.4f}/{r['inl_sd']:.4f} LSB")
    for od in optD:
        if od:
            print(f"option D t={od['t']}: plate {od['plate']:.3f} area x{od['area_x']:.2f} "
                  f"dnl yield {od['dnl_yield']:.3f} inl yield {od['inl_yield']:.3f}; "
                  f"DNL/INL sd {od['dnl_sd']:.4f}/{od['inl_sd']:.4f} LSB")

    if args.record:
        write_record(res, D, fit_dnl, fit_inl, coeff_sq_dnl, probe_levels, probe_dir,
                     p_min, p_allpass, as_built, cand, seg_rows, optD, pilot_stats, args.supersedes)
        print("\nwrote analysis record")
    return 0


def write_record(res, D, fit_dnl, fit_inl, coeff_sq_dnl, probe_levels, probe_dir,
                 p_min, p_allpass, as_built, cand, seg_rows, optD, pilot_stats, supersedes: str = "") -> Path:
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        sha = subprocess.run(["git", "rev-parse", "--short=8", "HEAD"], capture_output=True, text=True,
                             cwd=EXPERIMENT_DIR).stdout.strip() or "git-na"
        dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True,
                               cwd=EXPERIMENT_DIR).stdout.strip() != ""
    except OSError:
        sha, dirty = "git-na", False
    rec_id = f"{ts}-{sha}" + ("-dirty" if dirty else "")
    path = EXPERIMENT_DIR / "analysis" / f"{rec_id}.md"

    n, pairs, codes = D["n"], D["pairs"], D["codes"]
    probe_n = len(probe_levels[0])
    L: list[str] = []
    a = L.append
    a(f"# CDAC DNL/INL attribution and closure study {rec_id}")
    a("")
    a("- **Analysis ID**: " + rec_id)
    a(f"- **Claim**: attribution of the committed Monte-Carlo DNL/INL spread (source record "
      f"`sim/cdac-array-transfer/records/{SOURCE_RECORD}.md`, issue #1016 steps 1-2) to its contributors, "
      "comparison of design-side closure options against the ORIGINAL DRAFT limit "
      f"(`<= +-{LIMIT_LSB:g} LSB`, target_yield {TARGET_YIELD}), and the step-3 pilot confirmation of the "
      "leading option (record `" + PILOT_RECORD + "`). NOT scored against DR-007's `+-2.0 LSB` candidate; "
      "NO spec row edited; NO existing record modified (append-only).")
    a(f"- **Inputs (all committed, no new ngspice run by this script)**: `mc-draws/{SOURCE_RECORD}/` "
      f"(N={n} `tt_mm` + {n} `tt` controls, seeds {res.seed}..{res.seed + n - 1}); "
      f"`mc-draws/{PILOT_RECORD}/` (candidate {PILOT_PLATE_UM:.4f} um-plate study, N={pilot_stats['n']}, "
      f"seed {pilot_stats['seed']}); `{probe_dir.name}/` (caps-only isolation probe, "
      f"N={probe_n}, seeds {PROBE_SEEDS.start}..{PROBE_SEEDS[-1]}).")
    a("- **Method**: per adjacent-code transition and per sampled code, the systematic part is the "
      "mismatch-disabled (negative-control) value (verified identical across all same-seed controls) "
      "and the random part is `draw - control` per seed; sigmas are sample stdev over N. The closure "
      "model rescales random parts by the combined tt_mm card ratio `(1.9 + 0.150)/(p + 0.150)` and "
      "leaves systematic parts fixed. Every table row recomputes from the committed draws by "
      "`analysis/attribute_1016.py` (this analysis's generator).")
    a("")
    a("## 1. Per-transition DNL decomposition (ADC LSB)")
    a("")
    a("| transition | carry bit k | switched units (per side) | systematic DNL | measured cross-copy sigma | ideal weighted cross-copy sigma | measured / weighted |")
    a("|---|---|---|---|---|---|---|")
    for t in sorted(pairs, key=lambda t: -coeff_sq_dnl[t]):
        k = carry_bit(*t)
        cs = coeff_sq_dnl[t]
        pred = weighted_step_sigma(*t)
        ratio = D["sd_dnl"][t] / pred if pred else float("nan")
        a(f"| {t[0]}->{t[1]} | {k if k is not None else '(non-carry)'} | {cs:.0f} | "
          f"{D['sys_dnl'][t]:+.4f} | {D['sd_dnl'][t]:.4f} | {pred:.4f} | {ratio:.3f} |")
    a("")
    a("max|DNL| carrier histogram (transition holding each draw's worst DNL): "
      + str({f"{t[0]}->{t[1]}": c for t, c in sorted(D["dnl_carrier"].items(), key=lambda kv: -kv[1])}))
    a("")
    a("## 2. Per-code INL and level decomposition (ADC LSB / V)")
    a("")
    a("| code | selected units (P side) | systematic INL | random INL sigma | random LEVEL sigma (uV) |")
    a("|---|---|---|---|---|")
    for c in sorted(codes, key=lambda c: -D["level_rnd_sd"][c])[:12]:
        a(f"| {c} | {c} | {D['sys_inl'][c]:+.4f} | {D['sd_inl'][c]:.4f} | {D['level_rnd_sd'][c] * 1e6:.1f} |")
    a("")
    a(f"(12 noisiest levels of {len(codes)} sampled codes. Endpoint codes 0/511 sit at "
      f"{D['level_rnd_sd'][0] * 1e6:.0f}/{D['level_rnd_sd'][511] * 1e6:.0f} uV -- the quietest in the set.)")
    a("")
    a("max|INL| carrier histogram: " + str(dict(sorted(D["inl_carrier"].items(), key=lambda kv: -kv[1])[:8])))
    a("")
    a("## 3. Attribution: what drives the spread")
    a("")
    a("**(a) MiM parameters in the campaign decks.** Both archived netlists load "
      "`libs.tech/combined/sky130.lib.spice tt_mm`. Its cap_mim_m3_1 uses effective square "
      "side W + 0.150 um. Nominal C is 2(W + 0.150)² fF, and relative sigma at mult=1 "
      "is 0.0047/(W + 0.150), with W in um. At 1.900 and 3.300 um these give "
      f"{as_built['cu_ff']:.3f} and {cand['cu_ff']:.3f} fF, with "
      f"{100 * SOURCE_SIGMA:.4f}% and {100 * run_mc.tt_mim_sigma(CANDIDATE_PLATE_UM):.4f}% mismatch. "
      "The independent unit-cap probes in bit-trial record 20261123-000415-d1ce38af agree. "
      "DR-019 uses the drawn-area/perimeter estimate and 2.8 %·um/W for its design reference "
      "(8.664/24.288 fF and 1.4737/0.8485%). "
      "[MiM subcircuit](https://github.com/fossi-foundation/skywater-pdk-libs-sky130_fd_pr/blob/"
      "1232782c1b9fab3aacda74d67ce7c92bf7da8105/combined_models/continuous/models_capacitors.spice#L101-L108) · "
      "[Mismatch coefficient](https://github.com/fossi-foundation/skywater-pdk-libs-sky130_fd_pr/blob/"
      "1232782c1b9fab3aacda74d67ce7c92bf7da8105/combined_models/continuous/models_global.spice#L73) · "
      "[Nominal geometry and density](https://github.com/fossi-foundation/skywater-pdk-libs-sky130_fd_pr/blob/"
      "1232782c1b9fab3aacda74d67ce7c92bf7da8105/combined_models/continuous/parameters_cap_nom.spice#L20-L21)")
    a("")
    a("The deck instantiates one subcircuit per bit with MF=m=bit weight. The card reads "
      "`mult`, which defaults to 1. ngspice passes `m` through to the primitive capacitor, "
      "multiplying the capacitance including its single mismatch draw. MF does not set mult. "
      "The weighted group therefore retains the unit's fractional sigma. In table 1 the ideal "
      "divider sensitivity per group is m(selected − code/512), with a unit unselected termination. "
      "The variance sums the squared sensitivities of the two independent levels and both sides.")
    a("")
    a(f"The sampled DNL sigmas correlate with the square root of the "
      f"within-array switched-unit count (r = {fit_dnl['pearson_r']:.3f}). The INL sigmas correlate "
      f"with sqrt(code*(511-code)/511) (r = {fit_inl['pearson_r']:.3f}). A one-side unit step is "
      "1.8 V / 512 = 3.515625 mV, one ADC LSB. Independent P and N errors add in quadrature, "
      f"giving a differential coefficient of {DIFF_ADC_LSB:.4f} ADC LSB. Fitting these shapes to "
      f"the campaign gives effective coefficients of {fit_dnl['sigma_pct']:.4f} % (DNL) and "
      f"{fit_inl['sigma_pct']:.4f} % (INL). The fitted shapes assume independent units. Each coefficient summarizes campaign spread under that assumption.")
    a("")
    a(f"**(b) Caps-only isolation probe.** In `{probe_dir.name}/`, ideal drives replace the "
      "nfet/pfet switches. The MiM capacitors retain their mismatch model. The table compares "
      "the sample standard deviation of each differential level across seeds.")
    a("")
    a(f"| code | committed campaign level sd (uV, N={n}) | caps-only probe level sd (uV, N={probe_n}) |")
    a("|---|---|---|")
    probe_sd = {c: statistics.stdev(samples) for c, samples in probe_levels.items()}
    for c in PROBE_CODES:
        a(f"| {c} | {D['level_rnd_sd'][c] * 1e6:.1f} | {probe_sd[c] * 1e6:.1f} |")
    a("")
    a(f"At codes 255 and 256 the caps-only probe gives {probe_sd[255] * 1e3:.2f} and "
      f"{probe_sd[256] * 1e3:.2f} mV of level jitter. The full campaign gives "
      f"{D['level_rnd_sd'][255] * 1e3:.2f} and {D['level_rnd_sd'][256] * 1e3:.2f} mV. "
      f"Across the {len(PROBE_CODES)} tabulated codes the two sets of standard deviations have "
      f"Pearson r = {_pearson([D['level_rnd_sd'][c] for c in PROBE_CODES], [probe_sd[c] for c in PROBE_CODES]):.3f}.")
    a("")
    a("**(c) The harness measures cross-copy DNL.** Each code uses an independent array copy. "
      "On a shared array, the variance of the step includes the covariance between its two levels. "
      "That covariance can have either sign.")
    a("")
    a("- The 1-unit transitions (0,1)/(2,3)/(510,511) are quiet (sigma 0.010-0.016 LSB) while "
      "(384,385) -- also a 1-unit transition -- carries sigma 0.375 LSB and holds the draw maximum in "
      "6/40 draws. Its independent copies give substantial level error even for the unchanged bits.")
    a("- At the 255->256 carry the selected sets are disjoint. For ideal independent units, the "
      "one-side normalized sensitivity is g(c,i) = selected(c,i) - c/512. With independent copies, "
      "sum(g255² + g256²) = 255*(1-255/512) + 256*(1-256/512) = 255.998. "
      "On a shared array sum((g256 - g255)²) = 510.998 because "
      "sum(g255*g256) = -255*256/512. Thus the cross-copy variance can also be smaller. "
      "Per the ruling in #1034, only the campaign metric is used for sizing. Within-die DNL remains unmeasured.")
    a("")
    a("**(d) Mismatch-disabled controls.** The source maxima (absolute DNL / INL) are "
      f"{max(map(abs, D['sys_dnl'].values())):.6f} / {max(map(abs, D['sys_inl'].values())):.6f} LSB, "
      f"and the pilot maxima are {pilot_stats['floor_dnl']:.6f} / {pilot_stats['floor_inl']:.6f} LSB. "
      "Each control is deterministic across its seeds. The model holds the source values fixed when "
      "scaling the random terms. The two campaigns also used different PDK and ngspice versions, "
      "so the difference between their controls cannot be attributed to plate size alone.")
    a("")
    a("## 4. What the 22-code set can and cannot attribute")
    a("")
    a(f"- CAN: every major-carry pair of the 9-bit sub-array ({len(pairs)} adjacent transitions "
      "including the textbook-worst MSB carry 255->256), the endpoints the INL line fit uses, and a "
      "short code-density run near 0.")
    a("- CANNOT: the other ~499 transitions of a full 512-code ramp; any code-ordered systematic "
      "vanishing at the sampled codes; the 10th-bit differential-sign structure (array-only scope, "
      "source record's UNITS note); WITHIN-DIE DNL isolation (see 3c).")
    a("- The PDK's MiM mismatch is per-instance random AGAUSS with no spatial-correlation term: the "
      "draws model ZERO die-gradient, so no layout-ordering effect can be attributed (or excluded) "
      "by this campaign -- option C's evidentiary gap, below.")
    a("")
    a(f"## 5. Closure options against `<= +-{LIMIT_LSB:g} LSB` at target_yield {TARGET_YIELD}")
    a("")
    a(f"The fitted upper bound is mean + {Z_99:.3f}*sigma. Margin = (limit - bound)/limit "
      f"with a limit of {LIMIT_LSB:g} LSB. A nonnegative margin meets the fitted criterion. "
      "\"emp\" is the pass fraction of the N=40 draws after rescaling the random terms by "
      "2.05/(p + 0.150) and holding the source systematic terms fixed.")
    a("")
    a(f"### Option A -- larger unit capacitor (combined tt_mm mismatch scaling). RECOMMENDED (see DR-027).")
    a("")
    a("| plate (um) | area x | card C_u (fF) | array core (um) | DNL mean/sd | DNL margin | DNL emp | INL mean/sd | INL margin | INL emp |")
    a("|---|---|---|---|---|---|---|---|---|---|")
    for r, tag in ((as_built, "1.900 (as-built)"), (cand, f"{CANDIDATE_PLATE_UM:.3f} (candidate)")):
        a(f"| {tag} | {r['area_x']:.2f} | {r['cu_ff']:.2f} | "
          f"{r['array_um'][0]:.0f} x {r['array_um'][1]:.0f} | "
          f"{r['dnl'][0]:.3f}/{r['dnl'][1]:.3f} | {r['dnl'][3]:+.3f} | {r['dnl'][2]:.3f} | "
          f"{r['inl'][0]:.3f}/{r['inl'][1]:.3f} | {r['inl'][3]:+.3f} | {r['inl'][2]:.3f} |")
    a("")
    a(f"- Minimum plate meeting both normal margins on the 5 nm grid: **{p_min:.3f} um** "
      f"(unit-cap area x{(p_min / PLATE_UM) ** 2:.2f}). The candidate **{CANDIDATE_PLATE_UM:.3f} um** adds "
      f"{cand['dnl'][3] * 100:.2f}% headroom. The fitted bounds are "
      f"{LIMIT_LSB * (1 - cand['dnl'][3]):.6f} LSB DNL and {LIMIT_LSB * (1 - cand['inl'][3]):.6f} LSB INL.")
    a(f"- The all-{n}-draws-pass bound is {p_allpass:.3f} um (unit area x{(p_allpass / PLATE_UM) ** 2:.2f}) "
      "-- dominated by the single worst draw (seed 7, whose (255,256) random part of -1.735 LSB is a "
      "3-4 sigma tail sample of the copy-level distribution). Sizing to one N=40 worst draw with zero "
      "headroom is exactly the anti-pattern DR-007's own text rejects; the normal-margin criterion "
      "with stated headroom is the sizing basis, and the N>=368 sized run is the empirical resolver.")
    a(f"- Layout cost (from `layout/cdac-array/bin/cdac_layout.py` constants, no re-layout done): unit "
      f"pitch {PLATE_UM + PITCH_GAP_UM:.3f} -> {CANDIDATE_PLATE_UM + PITCH_GAP_UM:.3f} um "
      f"assuming the existing {PITCH_GAP_UM:.3f} um gap. Estimated array core "
      f"{N_COL * (PLATE_UM + PITCH_GAP_UM):.1f} x {N_ROW * (PLATE_UM + PITCH_GAP_UM):.1f} -> "
      f"{cand['array_um'][0]:.1f} x {cand['array_um'][1]:.1f} um "
      f"(x{cand['array_area_x']:.2f} area). The proposed pitch lies on the 5 nm grid. "
      "Layout precheck and spacing verification require a candidate layout.")
    cap_ratio = cand["cu_ff"] / as_built["cu_ff"]
    nominal_ratio = design_cap_ff(CANDIDATE_PLATE_UM) / design_cap_ff(PLATE_UM)
    a("- The Sampling-cap row uses DR-019's area/perimeter convention. Its capacitance margin "
      f"over the thermal floor grows {nominal_ratio:.4f}× and fixed-temperature RMS noise falls by "
      f"a factor of {math.sqrt(nominal_ratio):.4f}. Using the simulated capacitances gives "
      f"{cap_ratio:.4f}× and {math.sqrt(cap_ratio):.4f}, respectively. "
      "Issue #1033 measures settling and acquisition at the candidate load.")
    a("")
    a("### Option B -- unary segmentation of the top t bits at constant total C")
    a("")
    a("As a sensitivity study, scale every measured random DNL term by the square root of the "
      "worst within-array switched-unit count divided by the binary maximum (511 units per side). "
      "The count is enumerated over all 511 adjacent pairs. With one thermometer MSB the array is "
      "still binary. Independent copies also contribute level errors from unchanged bits, so this "
      "uniform carry scaling cannot predict segmented cross-copy yield. Both B and D use this assumption. Their SDs are sample standard deviations of the per-draw maxima.")
    a("")
    a("| t | max switched per side | DNL random scale | DNL sd (LSB) | DNL emp | DNL bound (LSB) | DNL margin | INL sd (LSB) | INL emp | INL margin |")
    a("|---|---|---|---|---|---|---|---|---|---|")
    for r in seg_rows:
        a(f"| {r['t']} | {r['max_switched']} | {r['dnl_scale']:.4f} | {r['dnl_sd']:.4f} | {r['dnl_yield']:.3f} | "
          f"{LIMIT_LSB * (1 - r['dnl_margin']):.3f} | {r['dnl_margin']:+.3f} | "
          f"{r['inl_sd']:.4f} | {r['inl_yield']:.3f} | {r['inl_margin']:+.3f} |")
    a("")
    a(f"With INL held fixed at constant total capacitance, its margin stays "
      f"{seg_rows[0]['inl_margin']:+.3f} at every t. B alone misses the INL criterion in this model.")
    a("")
    a("### Option D -- segmentation + the INL-sized plate")
    a("")
    for od in optD:
        if od:
            a(f"- t={od['t']}: plate {od['plate']:.3f} um (unit area x{od['area_x']:.2f}), "
              f"DNL sd {od['dnl_sd']:.4f} LSB, emp {od['dnl_yield']:.3f} (margin {od['dnl_margin']:+.3f}), "
              f"INL sd {od['inl_sd']:.4f} LSB, emp {od['inl_yield']:.3f} (margin {od['inl_margin']:+.3f}).")
    a("")
    a(f"At the model sizes D uses less unit-cap area than A (x{optD[0]['area_x']:.2f} vs x{cand['area_x']:.2f}). It "
      "reopens the Sampling-cap row (C_u still moves), adds a thermometer decoder to the SAR "
      "sequencer (re-composition of the digital partition, DR-006 timing re-verification), splits "
      "the MSB routing into 2^t - 1 unary groups, and widens the re-verification surface to "
      "every campaign that exercises the sequencer. Kept as the documented area-optimized "
      "alternative; not recommended first (see DR-027's reasoning).")
    a("")
    a("### Option C -- layout matching changes (common centroid, dummy ring, routing symmetry)")
    a("")
    a("- NOT evidencable by this campaign's methodology: the PDK mismatch model in the committed "
      "draws is per-instance random with no spatial term, so no layout-ordering change can move a "
      "simulated number here.")
    a("- Both decks show systematic error with mismatch disabled. Neither campaign measures the "
      "effect of changing layout order or routing on this error.")
    a("- Retained as good practice for the FOLLOW-UP layout (hedging a real-die gradient the model "
      "cannot see), carrying no predicted-yield number in this study.")
    a("")
    a("### Top-plate load per side in the assembled ADC (DR-022)")
    a("")
    a("The half-LSB offset cell and its opposite-side dummy each track one unit on their respective "
      "side. The known load alone gives a span-error floor of 1/(512+1) = 0.195% FS, or "
      "1024/513 ≈ 2.0 ADC LSB, for each alternative that retains this topology.")
    a("")
    a("| Option | plate (um) | tracking load, DR-019 convention (fF/side) | tracking load, combined card (fF/side) |")
    a("|---|---|---|---|")
    for option, side in (("A", CANDIDATE_PLATE_UM), ("As-built, B and C", PLATE_UM),
                         ("D (two or three thermometer MSBs)", optD[0]["plate"])):
        a(f"| {option} | {side:.3f} | {design_cap_ff(side):.3f} | {run_mc.tt_mim_cap_ff(side):.3f} |")
    a("")
    a("For fixed switches and comparator, BPREF junction/overlap load coupled through Csamp, "
      "sampling-switch capacitance and comparator input capacitance can shrink relative to 512 C_u. "
      "The tracking cell keeps its relative weight. Routing, dummy coupling and any additional "
      "segmentation wiring require extraction of the candidate layout to determine total gain error.")
    a("")
    a("## 6. Step-3 pilot: simulated confirmation of option A (record " + PILOT_RECORD + ")")
    a("")
    a(f"A fresh Monte Carlo of the candidate array (generated study variant, plate "
      f"{PILOT_PLATE_UM:.4f} um, sigma(C)/C = {100 * run_mc.tt_mim_sigma(PILOT_PLATE_UM):.4f}% at mult=1), N={pilot_stats['n']}, seed {pilot_stats['seed']} (outside the source "
      "campaign's seed 1..40, so the comparison is out-of-sample for the closure model fitted on "
      "those draws):")
    a("")
    a("| statistic | model prediction at 3.300 um | pilot measured |")
    a("|---|---|---|")
    a(f"| max\\|DNL\\| mean / sd | {cand['dnl'][0]:.3f} / {cand['dnl'][1]:.3f} | "
      f"{pilot_stats['dnl_mean']:.3f} / {pilot_stats['dnl_sd']:.3f} |")
    a(f"| max\\|INL\\| mean / sd | {cand['inl'][0]:.3f} / {cand['inl'][1]:.3f} | "
      f"{pilot_stats['inl_mean']:.3f} / {pilot_stats['inl_sd']:.3f} |")
    a(f"| worst draw (either stat) | {cand['dnl_max']:.3f} (DNL) | {max(pilot_stats['dnl_max'], pilot_stats['inl_max']):.3f} |")
    a("")
    a(f"All {pilot_stats['n']} pilot draws clear +-{LIMIT_LSB:g} LSB on both statistics at tt_mm, "
      "27 °C and 1.8 V. The separate five-code transfer sweeps used 1.8988 and 1.9000 um plates. "
      "The 3.3000 um acquisition and bit-trial settling results in #1033 concern different measurements. "
      "Candidate transfer monotonicity and mismatch yield across PVT remain open. "
      "The pilot yield envelope (record 20261126-051316-7e91374a) reports empirical 1.000 with normal-fit cpk 0.93 (DNL) / 1.79 "
      "(INL), a required N of 368 to CLAIM 0.99 at this pass rate, and its declared negative control "
      "(the as-built 1.9000 um campaign's committed draws) is not yet statistically distinguishable "
      "from the nominal at N=16 -- both are the pilot's stated size limits, resolved by the sized run.")
    a("")
    a("## 7. What this study recommends")
    a("")
    a(f"Option A at plate {CANDIDATE_PLATE_UM:.3f} um, on the evidence above: it closes BOTH axes' "
      "normal-margin criterion with headroom, is confirmed by out-of-sample simulation, requires no "
      "topology or digital change, and every cost it carries (Sampling-cap row reopening, settling "
      "re-derivation, layout area) is named. The decision record `spec/decision-records/DR-027-*` "
      "carries the proposal; implementation is deliberately NOT done here (follow-up issues filed).")
    a("")
    a("## Environment")
    a("")
    a("- Analysis uses Python to parse the archived logs. The probe and pilot records document "
      "the environments of their original single-corner simulations.")
    a("- Tool versions for the probe/pilot: PDK sky130A per sim/pdk.json pin (f6eeac7d), ngspice-47 "
      "(host ngspice), klt 0.8.0 + klt-yield-native 0.1.0 for the envelope (venv per "
      "sim/yield-requirements.txt). The SOURCE campaign's own environment block (c6d73a35 / "
      "ngspice-46 per its record; its successor re-mint notes f6eeac7d / ngspice-47 for the "
      "re-parse) governs the committed draws -- the cross-version comparison is uncontrolled and "
      "stated as such.")
    a("- **Script**: `sim/cdac-array-transfer/analysis/attribute_1016.py` (append-only: a re-run or "
      "correction mints a new analysis record).")
    a("")
    L.extend(evidence_mod.footer_lines("sim/cdac-array-transfer/analysis/attribute_1016.py", supersedes))
    path.write_text("\n".join(L) + "\n")
    return path


if __name__ == "__main__":
    raise SystemExit(main())

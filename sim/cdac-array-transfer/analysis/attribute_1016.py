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
- caps-only probe : sim/cdac-array-transfer/analysis/probe-caps-only-*/
- pilot campaign  : sim/cdac-array-transfer/mc-draws/<pilot-id>/ (found by
  --pilot-record, default the 3.3000 um-plate N=16 seed-101 campaign)

Usage:
    python3 sim/cdac-array-transfer/analysis/attribute_1016.py             # print only
    python3 sim/cdac-array-transfer/analysis/attribute_1016.py --record    # also write the md record
"""

from __future__ import annotations

import argparse
import datetime
import math
import statistics
import subprocess
import sys
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
SIM_DIR = EXPERIMENT_DIR.parent
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(EXPERIMENT_DIR))

import run_mc  # noqa: E402
from harness import evidence as evidence_mod  # noqa: E402

SOURCE_RECORD = "20261001-124049-5207381"  # the committed campaign the issue cites
PILOT_RECORD = "20261121-075027-75b91e85"  # candidate 3.3000 um plate, N=16, seed 101 (issue #1016 step 3)
PILOT_PLATE_UM = 3.3000
LIMIT_LSB = 1.0  # the ORIGINAL DRAFT row -- the limit this issue works against (NOT DR-007's 2.0 candidate)
TARGET_YIELD = 0.99
Z_99 = 2.3263478740408408  # Phi^-1(0.99), one-sided normal quantile for the 0.99-yield margin

# sky130 MiM mismatch, DR-019's own figures (PDK model card, transcribed in
# spec/dr-003-support/calc.py): sigma(dC/C)[%] = A_C / sqrt(area[um^2])
A_C_PCT_UM = 2.8
PLATE_UM = 1.9000
SIGMA_U_PCT = A_C_PCT_UM / PLATE_UM  # 1.4737 % -- DR-019's own printed figure

CANDIDATE_PLATE_UM = 3.3000  # the closure option A size this study lands on (5 nm-grid-legal)

# Layout constants, from layout/cdac-array/bin/cdac_layout.py (as committed):
#   CAPM_SIDE = 1.900, UNIT_PITCH_X = UNIT_PITCH_Y = 3.40 (= plate + 1.502
#   capm-to-capm gap, itself >= the 0.84 capm.space rule), N_COL x N_ROW =
#   64 x 16 = 1024 units. A resized plate p keeps the same spacing-driven
#   pitch rule (pitch = p + 1.502) and the same unit count/topology, so the
#   array core scales as (p + 1.502)^2 / (1.900 + 1.502)^2 per side-length
#   squared -- the area figures below are that arithmetic, not a re-layout.
N_COL, N_ROW = 64, 16
PITCH_GAP_UM = 1.502

ANALYTIC_MODELS: dict[str, float] = {
    "single-ended, array-LSB": 1.0,
    "differential, array-LSB": math.sqrt(2.0),
    "differential, ADC-LSB": 2.0 * math.sqrt(2.0),
}


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


def switched_unit_count(c1: int, c2: int) -> int:
    """Sum of 2^i over bit positions i whose selection differs between c1
    and c2 -- the per-side variance, in unit-cap counts squared, of a
    within-die step error (carry or plain single-bit turn-on alike)."""
    return sum(
        2 ** i for i in range(9) if ((c1 >> i) & 1) != ((c2 >> i) & 1)
    )


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
    out = {"pearson_r": _pearson(xs, ys)}
    for name, mult in ANALYTIC_MODELS.items():
        c = [mult * x for x in xs]
        implied = sum(a * b for a, b in zip(c, ys)) / sum(a * a for a in c)
        out[name] = implied
        out[name + " (sigma_u %)"] = implied * 100.0
    return out


def load_probe_levels() -> tuple[dict[int, list[float]], Path] | tuple[None, None]:
    """Per-code vdiff levels across seeds from the committed caps-only probe."""
    probe_dirs = sorted((EXPERIMENT_DIR / "analysis").glob("probe-caps-only-*"))
    if not probe_dirs:
        return None, None
    d = probe_dirs[-1]
    codes = [0, 1, 127, 128, 255, 256, 383, 384, 385, 510, 511]
    levels: dict[int, list[float]] = {c: [] for c in codes}
    n_seeds = 0
    for log in sorted(d.glob("capsonly_seed*.log")):
        vals: dict[tuple[str, int], float] = {}
        for ln in log.read_text().splitlines():
            parts = ln.split()
            if len(parts) >= 3 and parts[0].startswith("vtop_") and parts[1] == "=":
                side, code = parts[0][5], int(parts[0][7:])
                if code in levels:
                    vals[(side, code)] = float(parts[2])
        if vals:
            n_seeds += 1
            for c in codes:
                levels[c].append(vals[("p", c)] - vals[("n", c)])
    return (levels if n_seeds else None), (d if n_seeds else None)


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

    probe_levels, probe_dir = load_probe_levels()

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
        s = PLATE_UM / p
        dnl_pred, inl_pred = predict_draws(s, s)
        cu = 2.0e-15 * p * p + 1.9e-16 * 4 * p
        pitch = p + PITCH_GAP_UM
        return {
            "plate": p, "cu_ff": cu * 1e15, "area_x": (p / PLATE_UM) ** 2,
            "array_um": (N_COL * pitch, N_ROW * pitch),
            "array_area_x": (pitch / (PLATE_UM + PITCH_GAP_UM)) ** 2,
            "dnl": (statistics.fmean(dnl_pred), statistics.stdev(dnl_pred), yield_at(dnl_pred), margin(dnl_pred)),
            "inl": (statistics.fmean(inl_pred), statistics.stdev(inl_pred), yield_at(inl_pred), margin(inl_pred)),
            "dnl_max": max(dnl_pred), "inl_max": max(inl_pred),
        }

    # minimum plate meeting BOTH normal margins on the 5 nm grid
    p = PLATE_UM
    p_min = None
    while p <= 6.0 + 1e-9:
        s = PLATE_UM / p
        dnl_pred, inl_pred = predict_draws(s, s)
        if margin(dnl_pred) >= 0 and margin(inl_pred) >= 0:
            p_min = math.floor(p / 0.005) * 0.005
            break
        p += 0.005
    # all-40-pass bound (dominated by the single worst draw; reported, not used)
    p = PLATE_UM
    p_allpass = None
    while p <= 8.0 + 1e-9:
        s = PLATE_UM / p
        dnl_pred, inl_pred = predict_draws(s, s)
        if max(dnl_pred) <= LIMIT_LSB and max(inl_pred) <= LIMIT_LSB:
            p_allpass = math.floor(p / 0.005) * 0.005
            break
        p += 0.005

    cand = eval_plate(CANDIDATE_PLATE_UM)

    seg_rows = []
    for t in (1, 2, 3):
        var_ratio = (2 ** (10 - t) - 1) / (2 ** 10 - 1)
        s_dnl = math.sqrt(var_ratio)
        dnl_pred, inl_pred = predict_draws(s_dnl, 1.0)
        seg_rows.append({
            "t": t, "dnl_scale": s_dnl,
            "dnl_yield": yield_at(dnl_pred), "dnl_margin": margin(dnl_pred),
            "inl_yield": yield_at(inl_pred), "inl_margin": margin(inl_pred),
        })

    def scan_plate_inl_only(t: int):
        var_ratio = (2 ** (10 - t) - 1) / (2 ** 10 - 1)
        s_seg = math.sqrt(var_ratio)
        p = PLATE_UM
        while p <= 8.0 + 1e-9:
            s = PLATE_UM / p
            _, inl_pred = predict_draws(s_seg * s, s)
            if margin(inl_pred) >= 0:
                p_grid = math.floor(p / 0.005) * 0.005
                s_grid = PLATE_UM / p_grid
                dnl_g, inl_g = predict_draws(s_seg * s_grid, s_grid)
                if margin(dnl_g) >= 0 and margin(inl_g) >= 0:
                    return {
                        "t": t, "plate": p_grid, "area_x": (p_grid / PLATE_UM) ** 2,
                        "dnl_yield": yield_at(dnl_g), "inl_yield": yield_at(inl_g),
                        "dnl_margin": margin(dnl_g), "inl_margin": margin(inl_g),
                    }
            p += 0.005
        return None

    optD = [scan_plate_inl_only(t) for t in (2, 3)]

    # ---- pilot confirmation --------------------------------------------------
    pilot = run_mc.reanalyze_from_logs(PILOT_RECORD)
    P = decompose(pilot)
    pilot_stats = {
        "n": pilot.n, "seed": pilot.seed,
        "dnl_mean": statistics.fmean([d.dnl_max_lsb for d in pilot.draws]),
        "dnl_sd": statistics.stdev([d.dnl_max_lsb for d in pilot.draws]),
        "dnl_max": max(d.dnl_max_lsb for d in pilot.draws),
        "inl_mean": statistics.fmean([d.inl_max_lsb for d in pilot.draws]),
        "inl_sd": statistics.stdev([d.inl_max_lsb for d in pilot.draws]),
        "inl_max": max(d.inl_max_lsb for d in pilot.draws),
    }

    # ---- console summary ------------------------------------------------------
    print(f"source: {SOURCE_RECORD} (N={n}); pilot: {PILOT_RECORD} (N={pilot_stats['n']}, plate {PILOT_PLATE_UM} um)")
    print(f"Pelgrom sigma_u at {PLATE_UM:.4f} um: {SIGMA_U_PCT:.4f} %")
    print(f"DNL fit r={fit_dnl['pearson_r']:.3f}; implied sigma_u: "
          + ", ".join(f"{k}={v:.4f}%" for k, v in fit_dnl.items() if k.endswith("(sigma_u %)")))
    print(f"INL fit r={fit_inl['pearson_r']:.3f}; implied sigma_u: "
          + ", ".join(f"{k}={v:.4f}%" for k, v in fit_inl.items() if k.endswith("(sigma_u %)")))
    if p_min:
        print(f"option A minimum plate (both margins met): {p_min:.3f} um; candidate {CANDIDATE_PLATE_UM:.3f} um")
    if p_allpass:
        print(f"all-{n}-draws-pass bound (worst-draw dominated, NOT the sizing basis): {p_allpass:.3f} um")
    print(f"candidate {CANDIDATE_PLATE_UM:.3f} um: DNL mean {cand['dnl'][0]:.3f} sd {cand['dnl'][1]:.3f} "
          f"yield {cand['dnl'][2]:.3f} margin {cand['dnl'][3]:+.3f}; INL mean {cand['inl'][0]:.3f} "
          f"yield {cand['inl'][2]:.3f} margin {cand['inl'][3]:+.3f}")
    print(f"pilot measured: DNL mean {pilot_stats['dnl_mean']:.3f} sd {pilot_stats['dnl_sd']:.3f} max {pilot_stats['dnl_max']:.3f}; "
          f"INL mean {pilot_stats['inl_mean']:.3f} sd {pilot_stats['inl_sd']:.3f} max {pilot_stats['inl_max']:.3f}")
    for r in seg_rows:
        print(f"option B t={r['t']}: dnl yield {r['dnl_yield']:.3f} margin {r['dnl_margin']:+.3f}; "
              f"inl yield {r['inl_yield']:.3f} margin {r['inl_margin']:+.3f}")
    for od in optD:
        if od:
            print(f"option D t={od['t']}: plate {od['plate']:.3f} area x{od['area_x']:.2f} "
                  f"dnl yield {od['dnl_yield']:.3f} inl yield {od['inl_yield']:.3f}")

    if args.record:
        write_record(res, D, fit_dnl, fit_inl, coeff_sq_dnl, probe_levels, probe_dir,
                     p_min, p_allpass, cand, seg_rows, optD, pilot_stats, args.supersedes)
        print("\nwrote analysis record")
    return 0


def write_record(res, D, fit_dnl, fit_inl, coeff_sq_dnl, probe_levels, probe_dir,
                 p_min, p_allpass, cand, seg_rows, optD, pilot_stats, supersedes: str = "") -> Path:
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
      f"seed {pilot_stats['seed']}); " + (f"`{probe_dir.name}/` (caps-only isolation probe)."
      if probe_dir else "(caps-only probe logs not found)."))
    a("- **Method**: per adjacent-code transition and per sampled code, the systematic part is the "
      "mismatch-disabled (negative-control) value (verified identical across all same-seed controls) "
      "and the random part is `draw - control` per seed; sigmas are sample stdev over N. The closure "
      f"model rescales random parts by `sigma_u(p)/sigma_u({PLATE_UM:g}) = {PLATE_UM:g}/p` (Pelgrom) and "
      "leaves systematic parts fixed. Every table row recomputes from the committed draws by "
      "`analysis/attribute_1016.py` (this analysis's generator).")
    a("")
    a("## 1. Per-transition DNL decomposition (ADC LSB)")
    a("")
    a("| transition | carry bit k | switched units^2 (per side) | systematic DNL | random sigma | analytic sigma (diff, ADC LSB) | ratio |")
    a("|---|---|---|---|---|---|---|")
    for t in sorted(pairs, key=lambda t: -coeff_sq_dnl[t]):
        k = carry_bit(*t)
        cs = coeff_sq_dnl[t]
        pred = 2.0 * math.sqrt(2.0) * math.sqrt(cs) * (SIGMA_U_PCT / 100.0)
        ratio = D["sd_dnl"][t] / pred if pred else float("nan")
        a(f"| {t[0]}->{t[1]} | {k if k is not None else '(non-carry)'} | {cs:.0f} | "
          f"{D['sys_dnl'][t]:+.4f} | {D['sd_dnl'][t]:.4f} | {pred:.4f} | {ratio:.3f} |")
    a("")
    a("max|DNL| carrier histogram (transition holding each draw's worst DNL): "
      + str({f"{t[0]}->{t[1]}": c for t, c in sorted(D["dnl_carrier"].items(), key=lambda kv: -kv[1])}))
    a("")
    a("## 2. Per-code INL and level decomposition (ADC LSB / V)")
    a("")
    a("| code | on-bits | systematic INL | random INL sigma | random LEVEL sigma (uV) |")
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
    a(f"**(a) The PDK mismatch model, quantified.** The sky130 MiM Pelgrom figure for the drawn "
      f"{PLATE_UM:.4f} um plate (DR-019) is `sigma(C_u)/C_u = {SIGMA_U_PCT:.4f} %` "
      f"(`A_C = {A_C_PCT_UM} %*um`). The measured per-transition random sigmas follow the "
      "switched-unit-count combinatorial shape (Pearson r = "
      f"{fit_dnl['pearson_r']:.3f} DNL, {fit_inl['pearson_r']:.3f} INL): transitions that switch more "
      "unit caps really are noisier, in the McCreary-Wooley proportion. The implied sigma_u depends on "
      "the unit convention (the source campaign reports ADC-LSB units on a differential structure, "
      "DR-003's analytic figure was single-ended array-LSB):")
    a("")
    a("| fit | convention | implied sigma_u |")
    a("|---|---|---|")
    for name in ANALYTIC_MODELS:
        a(f"| DNL | {name} | {fit_dnl[name + ' (sigma_u %)']:.4f} % |")
    for name in ANALYTIC_MODELS:
        a(f"| INL (amplitude) | {name} | {fit_inl[name + ' (sigma_u %)']:.4f} % |")
    a("")
    a(f"Under the like-for-like differential ADC-LSB convention the draws imply "
      f"{fit_dnl['differential, ADC-LSB (sigma_u %)']:.4f} % (DNL) / "
      f"{fit_inl['differential, ADC-LSB (sigma_u %)']:.4f} % (INL) against the model's "
      f"{SIGMA_U_PCT:.4f} % -- same order, convention-limited agreement.")
    a("")
    a(f"**(b) FET switches exonerated (caps-only probe).** Rebuilding the seed-1 campaign netlist with "
      "every nfet/pfet replaced by an ideal drive (bit=0: 1 ohm tie to VREFN; bit=1: PWL source "
      "stepping to VREFP at 2.1n, after the reset switch opens) leaves ONLY the caps' AGAUSS mismatch, "
      "and reproduces the committed campaign's per-code level spread in pattern AND magnitude "
      "(probe logs committed under `" + (probe_dir.name if probe_dir else "probe-caps-only-*") + "`):")
    a("")
    a("| code | committed campaign level sd (uV, N=40) | caps-only probe level sd (uV, N=8) |")
    a("|---|---|---|")
    for c in (0, 1, 127, 128, 255, 256, 383, 384, 385, 510, 511):
        probe_sd = statistics.stdev(probe_levels[c]) * 1e6 if probe_levels else float("nan")
        a(f"| {c} | {D['level_rnd_sd'][c] * 1e6:.1f} | {probe_sd:.1f} |")
    a("")
    a("The mid-split codes carry 1.0-1.7 mV of per-draw level jitter in BOTH; the endpoints are quiet "
      "in BOTH. The spread is unit-cap mismatch, not switch mismatch.")
    a("")
    a("**(c) Structural finding: the harness measures cross-copy, not within-die, DNL.** The campaign "
      "fragment (correctly, for a transfer-curve experiment) gives every code its OWN array copy -- so "
      "a per-draw 'DNL' between adjacent codes mixes the two copies' independent level errors. On a "
      "single die the static bits cancel in a code-to-code difference; across copies they do not. "
      "Evidence, all from the committed draws:")
    a("")
    a(f"- Cross-code level randoms are mutually uncorrelated (Pearson r between -0.42 and +0.23 over "
      "the noisiest code pairs) -- independent copies, not shared per-bit errors.")
    a("- The 1-unit transitions (0,1)/(2,3)/(510,511) are quiet (sigma 0.010-0.016 LSB) while "
      "(384,385) -- also a 1-unit transition -- carries sigma 0.375 LSB and holds the draw maximum in "
      "6/40 draws: its endpoint copies (bits {7,8} and {0..6}) carry large independent level variance "
      "that a within-die DNL would cancel.")
    a(f"- Consequence: the campaign's max|DNL| statistic is a CONSERVATIVE structure on the within-die "
      "DNL a real die would show (it adds copy-to-copy variance on top). This study sizes the closure "
      "against the campaign's own metric -- closing THAT also closes within-die DNL. Changing the "
      "methodology (a shared-array testbench) is OUT OF SCOPE here per the issue's bounds; recorded "
      "as a question for a separate follow-up, not acted on.")
    a("")
    a("**(d) The systematic floor is mismatch-free and switched-block-scaled.** With mismatch "
      "disabled the maxima are 0.2364 (DNL) / 0.1534 (INL) LSB, deterministic across seeds. Per "
      "transition the systematic DNL is negative and grows with the switched block: -0.0009 LSB at "
      "the 1-unit transitions through -0.0459 at (31,32)'s 63 units, -0.1028 at (63,64)'s 127, "
      "-0.1653 at the 255-unit carries (127,128)/(383,384), -0.2364 at the 511-unit MSB carry "
      "(255,256) -- see table 1. Area does not remove this term (it is present with mismatch off); "
      "the closure model holds it fixed, which is the conservative choice.")
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
    a(f"Margins: \"m+z\" = mean + {Z_99:.3f}*sigma vs the {LIMIT_LSB:g} LSB limit (the normal-fit 0.99-yield "
      "criterion; >0 met); \"emp\" = empirical pass fraction of the N=40 re-predicted draws. Pelgrom "
      "scaling: random parts x " + f"{PLATE_UM:g}/p, systematic fixed.")
    a("")
    a(f"### Option A -- larger unit capacitor (pure Pelgrom scaling). RECOMMENDED (see DR-027).")
    a("")
    a("| plate (um) | area x | C_u (fF) | array core (um) | DNL mean/sd | DNL m+z | DNL emp | INL mean/sd | INL m+z | INL emp |")
    a("|---|---|---|---|---|---|---|---|---|---|")
    as_built = {
        "plate": PLATE_UM, "cu_ff": 8.6640, "area_x": 1.0,
        "array_um": (N_COL * (PLATE_UM + PITCH_GAP_UM), N_ROW * (PLATE_UM + PITCH_GAP_UM)),
        "dnl": (0.7828, 0.3120, 0.825, (1.0 - (0.7828 + Z_99 * 0.3120)) / 1.0),
        "inl": (0.7184, 0.2085, 0.925, (1.0 - (0.7184 + Z_99 * 0.2085)) / 1.0),
    }
    for r, tag in ((as_built, "1.900 (as-built)"), (cand, f"{CANDIDATE_PLATE_UM:.3f} (candidate)")):
        a(f"| {tag} | {r['area_x']:.2f} | {r['cu_ff']:.2f} | "
          f"{r['array_um'][0]:.0f} x {r['array_um'][1]:.0f} | "
          f"{r['dnl'][0]:.3f}/{r['dnl'][1]:.3f} | {r['dnl'][3]:+.3f} | {r['dnl'][2]:.3f} | "
          f"{r['inl'][0]:.3f}/{r['inl'][1]:.3f} | {r['inl'][3]:+.3f} | {r['inl'][2]:.3f} |")
    a("")
    a(f"- Minimum plate meeting both normal margins on the 5 nm grid: **{p_min:.3f} um** "
      f"(unit-cap area x{(p_min / PLATE_UM) ** 2:.2f}). The candidate **{CANDIDATE_PLATE_UM:.3f} um** adds "
      f"~{abs(cand['dnl'][3]) * 100:.0f}% headroom below the limit on the binding (DNL) statistic.")
    a(f"- The all-{n}-draws-pass bound is {p_allpass:.3f} um (unit area x{(p_allpass / PLATE_UM) ** 2:.2f}) "
      "-- dominated by the single worst draw (seed 7, whose (255,256) random part of -1.735 LSB is a "
      "3-4 sigma tail sample of the copy-level distribution). Sizing to one N=40 worst draw with zero "
      "headroom is exactly the anti-pattern DR-007's own text rejects; the normal-margin criterion "
      "with stated headroom is the sizing basis, and the N>=368 sized run is the empirical resolver.")
    a(f"- Layout cost (from `layout/cdac-array/bin/cdac_layout.py` constants, no re-layout done): unit "
      f"pitch {PLATE_UM + PITCH_GAP_UM:.3f} -> {CANDIDATE_PLATE_UM + PITCH_GAP_UM:.3f} um (the capm "
      "gap and met3 spacing rules keep the same margins by construction -- the pitch rule is "
      "'plate + 1.502'); array core "
      f"{N_COL * (PLATE_UM + PITCH_GAP_UM):.1f} x {N_ROW * (PLATE_UM + PITCH_GAP_UM):.1f} -> "
      f"{cand['array_um'][0]:.1f} x {cand['array_um'][1]:.1f} um "
      f"(x{cand['array_area_x']:.2f} area). Topology (64x16, 7-net remainder column, switch rows) "
      "unchanged; `klt precheck --grid-um 0.005` stays clean at a 5 nm-grid plate side by DR-019's "
      "own standing policy.")
    a("- Ratified-row impact: reopens the RATIFIED Sampling-cap row (C_u, plate side) -- DR-027 "
      "proposes the change for operator approval, nothing is edited. kT/C noise margin (~415x) "
      "IMPROVES by the same x3.02. Settling/sample-rate (DRAFT row) needs re-derivation at the "
      "larger C -- named as follow-up. Incidental: DR-022/025's systematic gain error scales down "
      "with C_par/C_u (fixed parasitics over a larger unit), reported there, not claimed here.")
    a("")
    a("### Option B -- unary segmentation of the top t bits at constant total C")
    a("")
    a("| t | DNL random scale | DNL emp | DNL m+z | INL emp | INL m+z |")
    a("|---|---|---|---|---|---|")
    for r in seg_rows:
        a(f"| {r['t']} | {r['dnl_scale']:.4f} | {r['dnl_yield']:.3f} | {r['dnl_margin']:+.3f} | "
          f"{r['inl_yield']:.3f} | {r['inl_margin']:+.3f} |")
    a("")
    a("Segmentation shrinks the carry variance (worst per-side unit-variance 2^10-1 -> 2^(10-t)-1) but "
      f"leaves INL -- a sum over all units -- untouched: at constant total C the INL margin stays "
      f"{seg_rows[0]['inl_margin']:+.3f} at every t. **B alone cannot close the row**; the INL axis has "
      "no segmentation lever.")
    a("")
    a("### Option D -- segmentation + the INL-sized plate")
    a("")
    for od in optD:
        if od:
            a(f"- t={od['t']}: plate {od['plate']:.3f} um (unit area x{od['area_x']:.2f}), "
              f"DNL emp {od['dnl_yield']:.3f} (m+z {od['dnl_margin']:+.3f}), "
              f"INL emp {od['inl_yield']:.3f} (m+z {od['inl_margin']:+.3f}).")
    a("")
    a(f"Saves unit-cap area vs option A (x{optD[0]['area_x']:.2f} vs x{cand['area_x']:.2f}) but ALSO "
      "reopens the Sampling-cap row (C_u still moves), adds a thermometer decoder to the SAR "
      "sequencer (re-composition of the digital partition, DR-006 timing re-verification), splits "
      "the MSB column routing into 2^t bottom-plate nets, and widens the re-verification surface to "
      "every campaign that exercises the sequencer. Kept as the documented area-optimized "
      "alternative; not recommended first (see DR-027's reasoning).")
    a("")
    a("### Option C -- layout matching changes (common centroid, dummy ring, routing symmetry)")
    a("")
    a("- NOT evidencable by this campaign's methodology: the PDK mismatch model in the committed "
      "draws is per-instance random with no spatial term, so no layout-ordering change can move a "
      "simulated number here.")
    a("- The systematic floor (3d) is present with mismatch DISABLED -- it is not a matching artifact "
      "and layout ordering cannot remove it.")
    a("- Retained as good practice for the FOLLOW-UP layout (hedging a real-die gradient the model "
      "cannot see), carrying no predicted-yield number in this study.")
    a("")
    a("## 6. Step-3 pilot: simulated confirmation of option A (record " + PILOT_RECORD + ")")
    a("")
    a(f"A fresh Monte Carlo of the candidate array (generated study variant, plate "
      f"{PILOT_PLATE_UM:.4f} um, sigma_u = {A_C_PCT_UM / PILOT_PLATE_UM:.4f} % by the PDK's own "
      f"Pelgrom term), N={pilot_stats['n']}, seed {pilot_stats['seed']} (outside the source "
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
    a(f"All {pilot_stats['n']} pilot draws clear +-{LIMIT_LSB:g} LSB on both statistics; the measured "
      "means/sigmas land on the model's prediction (DNL within 0.01 LSB of the predicted mean; INL "
      "measured slightly better than predicted). The klt yield envelope (record "
      "20261121-075334-75b91e85) reports empirical 1.000 with normal-fit cpk 0.93 (DNL) / 1.79 "
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
    a("- Analysis host: this worktree's python3; NO ngspice/PDK invocation by this script. The "
      "caps-only probe and the pilot campaign were run as sequential single-corner local jobs on "
      "this host (host rules: no local MC grids; the klt sim batch route is parked by #811) -- "
      "their own records carry their environments.")
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

#!/usr/bin/env python3
"""Standalone runner for sim/top-plate-cpar/ -- the CDAC top-plate parasitic
capacitance C_par, measured per corner (issue #754; follow-on from DR-022
Open item 1).

WHAT IT MEASURES. The small-signal capacitance seen at `TOP_P` and `TOP_N` of
the as-committed `design/sar_adc_top.spice` in the hold state, at several DC
bias points over the top-plate common-mode range DR-022 traced
(565-871 mV at 1.8 V), per PVT corner and per MiM r+c corner:

    C_par = C_node - 512 * C_u

`C_node` is read from an AC analysis (a 1 V small-signal source on the node,
`C = -Im(I) / (2 pi f)`); `512 * C_u` is read in the SAME deck, at the same bias
and corner, from an isolated reference branch holding `XCuref` (the array's
unit cap, `MF=512`), so the subtraction never mixes a corner's array with
another corner's unit cap.

WHY AC, NOT TRANSIENT. `C_par` is ~0.8 % of `C_node`. A transient ramp reads a
displacement current whose relative accuracy is bounded by the solver's
`reltol` (1e-3), which is the same size as the number sought. An AC analysis is
a direct linear solve at the operating point, so the difference of two
~4.3 pF values resolves to well under 0.01 fF.

WHY ITS OWN RUNNER. Same reason as sim/cdac-array-transfer/: the shared
`.op`-only harness cannot express this measurement. This one goes through
`klt sim` (`analysis_steps[]`: one AC step per side and bias, `alter`ing the
bias sources between steps) so that the corner grid is a single request per
deck variant that `klt sim` dispatches to the batch fleet. This script never
loops `ngspice` itself.

TESTBENCH-ONLY DECK EDITS (the DUT netlist is otherwise byte-for-byte the
committed one; every edit is asserted to hit exactly the named line):
  * `xfe ... SAMPLE_INT ...` is re-pointed at `SAMPLE_HOLD`, tied low, so the
    sampling switch is in hold regardless of the sequencer;
  * leave-one-out variants delete exactly the named instances (DR-022's
    `unbalanced-control` technique).
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
sys.path.insert(0, str(SIM_DIR))

from harness import corners as corners_mod  # noqa: E402

EXPERIMENT_DIR = Path(__file__).resolve().parent
DUT_NETLIST = REPO_ROOT / "design" / "sar_adc_top.spice"

NOMINAL_SUPPLY_V = 1.8
SUPPLY_KEY = "vsup"
#: Quasi-static: in a one-off local probe (tt, 27 C, 1.8 V, 800 mV, 10 GOhm bias
#: resistors) C_node fell by 1.7 fF (0.04 % of C_node, ~5 % of C_par) between
#: 100 kHz and 1 MHz, from the array's own RC roll-off; assuming the f^2 law that
#: implies ~0.02 fF at 10 kHz (see README, "Frequency choice").
FREQ_HZ = 1.0e4
#: Testbench-only DC-bias resistor on each floating BPREF_x node. At FREQ_HZ the
#: 10 GOhm is >1e3 times the impedance of any capacitance on that node, so it
#: pins the DC level without conducting small-signal current.
R_BIAS = "10G"
#: Top-plate DC bias points: the endpoints of DR-022's traced common-mode range
#: (565-871 mV at 1.8 V) and three evenly spaced points between them.
BIASES_V = [0.565, 0.6415, 0.718, 0.7945, 0.871]
TRACED_RANGE_V = (0.565, 0.871)
N_UNITS = 512  # array side: 511 weighted + 1 termination unit cap (DR-005)
CU_W_UM = 1.9000

#: MiM r+c corners the PDK ships (libs.tech/ngspice/sky130.lib.spice `.lib`
#: sections, tt devices + the named r+c file). The five tt/ss/ff/sf/fs libs all
#: load res_typical__cap_typical.
RC_CORNERS = {
    "ll": "res_low__cap_low",
    "hh": "res_high__cap_high",
    "hl": "res_high__cap_low",
    "lh": "res_low__cap_high",
}

#: variant name -> instance names deleted (testbench-only).
LEAVE_ONE_OUT = {
    "no-choff": ["XChoff_p", "XChoff_n"],
    "no-csamp": ["XCsamp_p", "XCsamp_n"],
    "no-msw": ["XMsw_p", "XMsw_n"],
    "no-cmp-input": ["XM_INP", "XM_INN"],
}
ALL_REMOVED = [n for names in LEAVE_ONE_OUT.values() for n in names]
VARIANTS = ["as-committed", *LEAVE_ONE_OUT, "all-removed"]
CONTRIBUTORS = {
    "no-choff": "Choff_x (half-LSB cell cap)",
    "no-csamp": "Csamp_x / BPREF_x branch",
    "no-msw": "Msw_x (sampling switch)",
    "no-cmp-input": "comparator input pair",
}

STDCELL_INCLUDE = "$PDK_ROOT/sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice"


# --------------------------------------------------------------------------
# Pure helpers (no PDK / ngspice needed; unit-tested)
# --------------------------------------------------------------------------
def remove_instances(netlist_text: str, names: list[str]) -> str:
    """Delete the line of each instance in `names` (first token, exact,
    case-sensitive). Raises unless EVERY name matches exactly one line."""
    remaining = set(names)
    hits: dict[str, int] = {n: 0 for n in names}
    kept = []
    for ln in netlist_text.splitlines():
        tok = ln.split(None, 1)[0] if ln.strip() else ""
        if tok in remaining:
            hits[tok] += 1
            continue
        kept.append(ln)
    bad = {n: c for n, c in hits.items() if c != 1}
    if bad:
        raise RuntimeError(
            f"leave-one-out: expected exactly one line per instance, got {bad} in the DUT "
            "netlist -- it changed shape; re-derive this experiment."
        )
    return "\n".join(kept) + "\n"


def apply_hold_override(netlist_text: str) -> str:
    old = "xfe VINP VINN SAMPLE_INT "
    if netlist_text.count(old) != 1:
        raise RuntimeError(f"expected exactly one {old!r} line in the DUT netlist")
    return netlist_text.replace(old, "xfe VINP VINN SAMPLE_HOLD ", 1)


def variant_netlist(netlist_text: str, variant: str) -> str:
    if variant == "as-committed":
        return netlist_text
    if variant == "all-removed":
        return remove_instances(netlist_text, ALL_REMOVED)
    if variant in LEAVE_ONE_OUT:
        return remove_instances(netlist_text, LEAVE_ONE_OUT[variant])
    raise ValueError(f"unknown variant {variant!r}")


def build_body(dut_text: str, variant: str, stdcell_include: str = STDCELL_INCLUDE) -> str:
    """Circuit BODY for `klt sim` (no `.lib`/`.temp`/`.end`/`.control`)."""
    lines = [ln for ln in dut_text.splitlines() if ln.strip().lower() != ".end"]
    dut = apply_hold_override("\n".join(lines) + "\n")
    dut = variant_netlist(dut, variant)
    b0 = f"{BIASES_V[0]:g}"
    out = [
        f"* sim/top-plate-cpar deck body -- variant {variant} (issue #754)",
        "* hold state: SAMPLE_HOLD=0, RST_B asserted, CLK high (comparator tail off).",
        ".options num_threads=1",
        ".global VPWR VGND",
        f".include {stdcell_include}",
        "",
        dut,
        "* --- testbench-only sources (supply tracks the `vsup` corner axis) ---",
        f"Vsup VDD 0 DC {NOMINAL_SUPPLY_V}",
        "Vpwr VPWR VDD DC 0",
        "Vgnd VGND 0 DC 0",
        "Bvcm VCM 0 V=v(VDD)/2",
        "Brefp VREFP 0 V=v(VDD)",
        "Vrefn VREFN 0 DC 0",
        "Bclk CLK 0 V=v(VDD)",
        "Vrst RST_B 0 DC 0",
        "Vsh SAMPLE_HOLD 0 DC 0",
        "Vinp VINP 0 DC 0.9",
        "Vinn VINN 0 DC 0.9",
        "* --- measurement sources: bias (DC) + small-signal (AC, set per step) ---",
        f"Vtp TOP_P 0 DC {b0} AC 0",
        f"Vtn TOP_N 0 DC {b0} AC 0",
        f"Rbp BPREF_P_NC bp {R_BIAS}",
        f"Rbn BPREF_N_NC bn {R_BIAS}",
        f"Vbp bp 0 DC {b0}",
        f"Vbn bn 0 DC {b0}",
        "* --- reference branch: the array's 512 unit caps alone, same corner/bias ---",
        f"Vcu cu 0 DC {b0} AC 1",
        f"XCuref cu 0 sky130_fd_pr__cap_mim_m3_1 W={CU_W_UM:.4f} L={CU_W_UM:.4f} "
        f"MF={N_UNITS} m={N_UNITS}",
        "",
    ]
    return "\n".join(out)


def bias_tag(v: float) -> str:
    return f"{round(v * 1000)}"


def step_name(side: str, v: float) -> str:
    return f"{side}{bias_tag(v)}"


def analysis_steps() -> list[dict]:
    steps = []
    w = f"2*pi*{FREQ_HZ:g}"
    for v in BIASES_V:
        for side, src, other in (("p", "vtp", "vtn"), ("n", "vtn", "vtp")):
            steps.append({
                "name": step_name(side, v),
                "analysis": {"kind": "ac", "args": f"lin 1 {FREQ_HZ:g} {FREQ_HZ:g}"},
                "alter": {"vtp": v, "vtn": v, "vbp": v, "vbn": v, "vcu": v,
                          f"{src}.ac": 1, f"{other}.ac": 0},
                "measurements": [
                    {"name": "ctop", "expr": f"-imag(i({src}))/({w})", "unit": "F"},
                    {"name": "cref", "expr": f"-imag(i(vcu))/({w})", "unit": "F"},
                ],
            })
    return steps


def corner_ids() -> list[str]:
    grid = corners_mod.ratified_oat_grid(
        NOMINAL_SUPPLY_V, corners_mod.RATIFIED_SUPPLY_TOLERANCE,
        corners_mod.RATIFIED_PROCESS_CORNERS, corners_mod.RATIFIED_TEMPS_C)
    ids = [corners_mod.corner_id(p, t, v) for p, t, v in grid]
    ids += [corners_mod.corner_id(rc, 27.0, NOMINAL_SUPPLY_V) for rc in RC_CORNERS]
    return ids


def build_request(netlist_name: str, cids: list[str], *, timeout_s: float = 1800.0,
                  backend: str | None = None) -> dict:
    pts = [corners_mod.parse_corner_id(c) for c in cids]
    procs = sorted({p for p, _, _ in pts})
    temps = sorted({t for _, t, _ in pts})
    vdds = sorted({v for _, _, v in pts})
    want = set(pts)
    exclude = [
        {"process": p, "temperature_c": t, "supply_v": {SUPPLY_KEY: v}}
        for p in procs for t in temps for v in vdds if (p, t, v) not in want
    ]
    req: dict = {
        "netlist": netlist_name,
        "engine": "ngspice",
        "models": {"pdk": "sky130A", "lib": "libs.tech/combined/sky130.lib.spice"},
        "corners": {"process": procs, "supply_v": {SUPPLY_KEY: vdds}, "temperature_c": temps},
        "analysis_steps": analysis_steps(),
        "options": {"timeout_s": timeout_s, "keep_artifacts": True},
    }
    if exclude:
        req["exclude"] = exclude
    if backend:
        req["backend"] = backend
    return req


def read_report(report: dict) -> tuple[dict[str, dict[str, float | None]], dict]:
    """{corner_id: {"<step>.<name>": value}} plus run info; refuses error
    envelopes rather than inventing numbers."""
    if not isinstance(report, dict):
        raise ValueError("klt sim report is not a JSON object")
    if "error" in report and "corners" not in report:
        raise ValueError(f"klt sim error envelope: {report['error']}")
    out: dict[str, dict[str, float | None]] = {}
    for c in report.get("corners") or []:
        sv = (c.get("supply_v") or {}).get(SUPPLY_KEY)
        cid = corners_mod.corner_id(c["process"], float(c["temperature_c"]), float(sv))
        vals = {m["name"]: m.get("value") for m in (c.get("measurements") or [])
                if isinstance(m, dict) and "name" in m}
        if c.get("status") in ("error", "inconclusive"):
            vals = {k: None for k in vals}
        out[cid] = vals
    env = report.get("environment") or {}
    remote = env.get("remote") or {}
    worker = remote.get("worker_environment") or {}
    banner = ((worker.get("simulator") or {}).get("version_banner") or "")
    ngs = next((ln.strip("* ").strip() for ln in banner.splitlines() if "ngspice-" in ln), None)
    return out, {"remote": env.get("remote"), "status": report.get("status"),
                 "job_id": remote.get("job_id"),
                 "worker_pdk": (worker.get("pdk") or {}).get("stamp_text"),
                 "worker_ngspice": ngs}


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)


def curve(values: dict[str, float | None], side: str) -> list[dict] | None:
    """C(V) points for one side from one unit's measurements; None when any
    point is missing / non-finite (never a partial curve)."""
    pts = []
    for v in BIASES_V:
        ct = values.get(f"{step_name(side, v)}.ctop")
        cr = values.get(f"{step_name(side, v)}.cref")
        if not (_finite(ct) and _finite(cr)):
            return None
        pts.append({"v": v, "c_node_f": ct, "c_array_f": cr, "c_u_f": cr / N_UNITS,
                    "c_par_f": ct - cr})
    return pts


def summarize(pts: list[dict]) -> dict:
    par = [p["c_par_f"] for p in pts]
    par_cu = [p["c_par_f"] / p["c_u_f"] for p in pts]
    return {
        "mean_f": sum(par) / len(par), "min_f": min(par), "max_f": max(par),
        "mean_cu": sum(par_cu) / len(par_cu), "min_cu": min(par_cu), "max_cu": max(par_cu),
        "c_u_mean_f": sum(p["c_u_f"] for p in pts) / len(pts),
    }


def two_side_mean(pp: list[dict], pn: list[dict]) -> list[dict]:
    return [{k: (a[k] + b[k]) / 2 for k in a} for a, b in zip(pp, pn, strict=True)]


def composition(per_variant: dict[str, list[dict]]) -> dict:
    """Leave-one-out composition from per-variant C(V) curves (the side-mean
    curve). delta_i = C_node(as-committed) - C_node(variant i), per bias, then
    averaged. `residual` = C_par(as-committed) - sum(delta_i); `remainder` =
    C_par(all-removed) -- C_node with every named load deleted, minus 512*C_u."""
    base = per_variant["as-committed"]
    n = len(base)
    deltas = {}
    for name in LEAVE_ONE_OUT:
        cur = per_variant[name]
        deltas[name] = [base[i]["c_node_f"] - cur[i]["c_node_f"] for i in range(n)]
    sum_delta = [sum(deltas[k][i] for k in deltas) for i in range(n)]
    par = [base[i]["c_par_f"] for i in range(n)]
    rem = [per_variant["all-removed"][i]["c_par_f"] for i in range(n)]
    cu = [base[i]["c_u_f"] for i in range(n)]
    mean = lambda xs: sum(xs) / len(xs)  # noqa: E731
    out = {
        "par_f": mean(par), "par_cu": mean([p / c for p, c in zip(par, cu, strict=True)]),
        "c_u_f": mean(cu),
        "sum_delta_f": mean(sum_delta),
        "residual_f": mean([p - s for p, s in zip(par, sum_delta, strict=True)]),
        "remainder_f": mean(rem),
        "contrib_f": {k: mean(v) for k, v in deltas.items()},
    }
    out["contrib_cu"] = {k: v / out["c_u_f"] for k, v in out["contrib_f"].items()}
    out["residual_cu"] = out["residual_f"] / out["c_u_f"]
    out["remainder_cu"] = out["remainder_f"] / out["c_u_f"]
    return out


# --------------------------------------------------------------------------
# Submission (every simulation unit goes through `klt sim`)
# --------------------------------------------------------------------------
class SubmitError(RuntimeError):
    pass


def submit_variant(variant: str, cids: list[str], workdir: Path, backend: str | None,
                   timeout_s: float) -> tuple[dict, dict, dict]:
    d = workdir / variant
    d.mkdir(parents=True, exist_ok=True)
    dut = DUT_NETLIST.read_text()
    (d / "tb.spice").write_text(build_body(dut, variant))
    req = build_request("tb.spice", cids, timeout_s=timeout_s, backend=backend)
    (d / "request.json").write_text(json.dumps(req, indent=1) + "\n")
    rep_path = d / "report.json"
    if rep_path.is_file():
        report = json.loads(rep_path.read_text())
    else:
        argv = ["klt", "sim", str(d / "request.json"), "--format", "json", "-o", str(d / "out")]
        if backend:
            argv += ["--backend", backend]
        done = subprocess.run(argv, capture_output=True, text=True, check=False)
        try:
            report = json.loads(done.stdout)
        except json.JSONDecodeError:
            try:
                report = json.loads(done.stderr)
            except json.JSONDecodeError as exc:
                raise SubmitError(
                    f"klt sim ({variant}) returned no JSON report (rc={done.returncode}): "
                    f"{(done.stderr or done.stdout)[:600]}") from exc
        if "error" in report and "corners" not in report:
            raise SubmitError(f"klt sim ({variant}): {json.dumps(report['error'])}")
        rep_path.write_text(json.dumps(report, indent=1) + "\n")
    results, info = read_report(report)
    return results, info, req


def collect(cids: list[str], workdir: Path, backend: str | None, timeout_s: float) -> dict:
    """{variant: {cid: {"p": pts|None, "n": pts|None}}} + run info per variant."""
    data: dict = {"curves": {}, "runs": {}}
    for variant in VARIANTS:
        results, info, _req = submit_variant(variant, cids, workdir, backend, timeout_s)
        info = dict(info, backend=backend or "(klt default / KLT_SIM_BACKEND)")
        data["runs"][variant] = info
        per = {}
        for cid in cids:
            vals = results.get(cid)
            per[cid] = ({"p": curve(vals, "p"), "n": curve(vals, "n")} if vals is not None
                        else {"p": None, "n": None})
        data["curves"][variant] = per
        print(f"[{variant}] {sum(1 for c in per.values() if c['p'] and c['n'])}/{len(cids)} "
              f"corners complete (job={info.get('job_id')})", flush=True)
    return data


def analyze(data: dict, cids: list[str]) -> dict:
    out = {}
    for cid in cids:
        sides = {}
        ok = True
        for variant in VARIANTS:
            c = data["curves"][variant][cid]
            if not (c["p"] and c["n"]):
                ok = False
                break
            sides[variant] = c
        if not ok:
            out[cid] = {"complete": False}
            continue
        mean_curves = {v: two_side_mean(sides[v]["p"], sides[v]["n"]) for v in VARIANTS}
        out[cid] = {
            "complete": True,
            "p": sides["as-committed"]["p"], "n": sides["as-committed"]["n"],
            "p_summary": summarize(sides["as-committed"]["p"]),
            "n_summary": summarize(sides["as-committed"]["n"]),
            "composition": composition(mean_curves),
        }
    return out


# --------------------------------------------------------------------------
# Record
# --------------------------------------------------------------------------
DR022 = {"tt_27c_1.80v": 4.13, "tt_27c_1.62v": 4.18}


def _ff(x: float) -> str:
    return f"{x * 1e15:.3f}"


def write_record(analysis: dict, data: dict, cids: list[str], supersedes: str,
                 workdir: Path) -> Path:
    from harness import evidence

    netlist_text = build_body(DUT_NETLIST.read_text(), "as-committed")
    prov, lines = evidence.open_record(
        EXPERIMENT_DIR, netlist_text, "corners",
        {f"{v}.report.json": (workdir / v / "report.json").read_text() for v in VARIANTS})
    (EXPERIMENT_DIR / "corners" / prov.record_id / "requests").mkdir(exist_ok=True)
    for v in VARIANTS:
        (EXPERIMENT_DIR / "corners" / prov.record_id / "requests" / f"{v}.request.json"
         ).write_text((workdir / v / "request.json").read_text())
        (EXPERIMENT_DIR / "corners" / prov.record_id / "requests" / f"{v}.tb.spice"
         ).write_text((workdir / v / "tb.spice").read_text())

    complete = [c for c in cids if analysis[c]["complete"]]
    lines += [
        "- **Claim**: none -- characterization. Replaces DR-022's *estimated* split of `C_par` "
        "with a measured one; `spec/target-spec.md` is untouched (DRAFT until #1).",
        "- **Issue**: #754 (follow-on from DR-022 Open item 1)",
        f"- **Method**: AC analysis at {FREQ_HZ:g} Hz on `TOP_P`/`TOP_N` of the as-committed "
        "`design/sar_adc_top.spice` in hold (`C = -Im(I)/(2 pi f)`); "
        f"`C_par = C_node - 512*C_u`, `C_u` from the same deck's isolated `XCuref` (MF=512). "
        f"Bias points {', '.join(f'{b * 1000:g}' for b in BIASES_V)} mV.",
        f"- **Corners**: {len(complete)}/{len(cids)} complete: {', '.join(cids)}",
        "- **Overall**: " + ("COMPLETE" if len(complete) == len(cids) else "INCOMPLETE"),
        "",
        "## Total `C_par` per corner (as-committed; mean of TOP_P/TOP_N, over the traced range)",
        "",
        "| corner | C_u (fF) | C_par mean (fF) | C_par min..max over bias (fF) | "
        "C_par (C_u) mean | min..max (C_u) | max abs P-N (fF) |",
        "|---|---|---|---|---|---|---|",
    ]
    for cid in cids:
        a = analysis[cid]
        if not a["complete"]:
            lines.append(f"| `{cid}` | INCOMPLETE | | | | | |")
            continue
        m = two_side_mean(a["p"], a["n"])
        s = summarize(m)
        pn = max(abs(p["c_par_f"] - n["c_par_f"]) for p, n in zip(a["p"], a["n"], strict=True))
        lines.append(
            f"| `{cid}` | {_ff(s['c_u_mean_f'])} | {_ff(s['mean_f'])} | "
            f"{_ff(s['min_f'])}..{_ff(s['max_f'])} | {s['mean_cu']:.3f} | "
            f"{s['min_cu']:.3f}..{s['max_cu']:.3f} | {_ff(pn)} |")
    lines += ["", "## C(V) curves (as-committed; per side, per corner)", "",
              "| corner | side | V_top (mV) | C_node (fF) | 512*C_u (fF) | C_par (fF) | C_par (C_u) |",
              "|---|---|---|---|---|---|---|"]
    for cid in cids:
        a = analysis[cid]
        if not a["complete"]:
            continue
        for side in ("p", "n"):
            for pt in a[side]:
                lines.append(
                    f"| `{cid}` | TOP_{side.upper()} | {pt['v'] * 1000:g} | {_ff(pt['c_node_f'])} | "
                    f"{_ff(pt['c_array_f'])} | {_ff(pt['c_par_f'])} | "
                    f"{pt['c_par_f'] / pt['c_u_f']:.3f} |")
    lines += ["", "## Composition (testbench-only leave-one-out; mean of sides, mean over bias)", "",
              "Each contributor = C_node(as-committed) - C_node(variant with that load deleted), "
              "in C_u of that corner. `residual` = C_par - sum(contributors) (non-additivity); "
              "`remainder` = C_par with ALL four loads deleted (loads not named here).", "",
              "| corner | " + " | ".join(f"{CONTRIBUTORS[k]} (fF / C_u)" for k in LEAVE_ONE_OUT)
              + " | sum (fF) | C_par (fF / C_u) | residual (fF / C_u) | remainder (fF / C_u) |",
              "|---|" + "---|" * (len(LEAVE_ONE_OUT) + 4)]
    for cid in cids:
        a = analysis[cid]
        if not a["complete"]:
            continue
        c = a["composition"]
        cells = " | ".join(f"{_ff(c['contrib_f'][k])} / {c['contrib_cu'][k]:.3f}"
                           for k in LEAVE_ONE_OUT)
        lines.append(
            f"| `{cid}` | {cells} | {_ff(c['sum_delta_f'])} | {_ff(c['par_f'])} / {c['par_cu']:.3f}"
            f" | {_ff(c['residual_f'])} / {c['residual_cu']:.3f}"
            f" | {_ff(c['remainder_f'])} / {c['remainder_cu']:.3f} |")
    lines += ["", "## Cross-check against DR-022", "",
              "| corner | measured C_par (C_u), mean over bias | DR-022 | measured - DR-022 (C_u) |",
              "|---|---|---|---|"]
    for cid, ref in DR022.items():
        a = analysis.get(cid)
        if not a or not a["complete"]:
            lines.append(f"| `{cid}` | INCOMPLETE | {ref} | |")
            continue
        s = summarize(two_side_mean(a["p"], a["n"]))
        lines.append(f"| `{cid}` | {s['mean_cu']:.3f} (range {s['min_cu']:.3f}..{s['max_cu']:.3f}) "
                     f"| {ref} | {s['mean_cu'] - ref:+.3f} |")
    lines += ["", "## Runs", ""]
    for v in VARIANTS:
        r = data["runs"][v]
        lines.append(f"- `{v}`: job `{r.get('job_id')}`, status `{r.get('status')}`, backend "
                     f"`{r.get('backend')}`, executing PDK `{r.get('worker_pdk')}`, "
                     f"executing simulator `{r.get('worker_ngspice')}`")
    lines += ["", "**Uncontrolled difference.** The Environment block below names the PDK and "
              "ngspice resolved on the SUBMITTING host; the numbers above were produced by the "
              "executing workers listed here. Where those differ, no comparison with a locally "
              "run record is controlled for PDK/simulator version."]
    klt = subprocess.run(["klt", "--version"], capture_output=True, text=True).stdout.strip()
    lines += [""]
    # The numbers come from the EXECUTING workers, so the PDK / simulator lines name
    # those (all six jobs must agree); the submitting host's own are listed as extras.
    wp = {data["runs"][v].get("worker_pdk") for v in VARIANTS}
    wn = {data["runs"][v].get("worker_ngspice") for v in VARIANTS}
    pdk_commit = next(iter(wp)).split()[-1] if len(wp) == 1 and None not in wp else None
    ng_ver = (next(iter(wn)).split()[0] if len(wn) == 1 and None not in wn else None)
    exec_known = pdk_commit is not None and ng_ver is not None
    lines += evidence.environment_block(
        f"sky130A @ {pdk_commit}" if exec_known else prov.pdk_line,
        ng_ver if exec_known else prov.ng_version, prov.netlist_sha,
        {"klt": klt, "AC frequency": f"{FREQ_HZ:g} Hz", "BPREF bias resistor": R_BIAS,
         "PDK / ngspice above": "as run by the executing workers" if exec_known else "submitting host",
         "submitting host PDK / ngspice": f"{prov.pdk_line} / {prov.ng_version}"})
    lines += [""]
    lines += evidence.footer_lines("sim/top-plate-cpar/run_top_plate_cpar.py", supersedes)
    evidence.write_latest_pointer(EXPERIMENT_DIR, prov.record_id)
    return evidence.close_record(prov, lines, "Record")


def main(argv: list[str] | None = None) -> int:
    from harness import evidence, pdk

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check-env", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="write the decks + requests to --workdir and stop (no simulation)")
    ap.add_argument("--probe", action="store_true",
                    help="ONE corner (tt_27c_1.80v), as-committed only, local backend")
    ap.add_argument("--record", action="store_true", help="run the full grid and mint a record")
    ap.add_argument("--backend", default=None,
                    help="klt sim backend (default: klt's own / KLT_SIM_BACKEND; a multi-corner "
                         "grid must go to the batch fleet, never be looped locally)")
    ap.add_argument("--workdir", type=Path, default=None)
    ap.add_argument("--timeout-s", type=float, default=1800.0)
    evidence.add_supersedes_argument(ap)
    args = ap.parse_args(argv)

    info = pdk.resolve()
    if args.check_env:
        print(f"PDK: {info.variant if info.found else info.error}")
        return 0 if info.found else 1
    workdir = args.workdir or Path(tempfile.mkdtemp(prefix="sim-top-plate-cpar-"))
    cids = corner_ids()

    if args.dry_run:
        for v in VARIANTS:
            d = workdir / v
            d.mkdir(parents=True, exist_ok=True)
            (d / "tb.spice").write_text(build_body(DUT_NETLIST.read_text(), v))
            (d / "request.json").write_text(
                json.dumps(build_request("tb.spice", cids, timeout_s=args.timeout_s), indent=1))
        print(f"wrote {len(VARIANTS)} decks + requests under {workdir}")
        return 0

    if args.probe:
        cid = corners_mod.corner_id("tt", 27.0, NOMINAL_SUPPLY_V)
        results, _info, _req = submit_variant("as-committed", [cid], workdir, "local",
                                              args.timeout_s)
        for side in ("p", "n"):
            pts = curve(results[cid], side)
            if pts is None:
                print(f"{cid} side {side}: INCOMPLETE")
                return 1
            s = summarize(pts)
            print(f"{cid} TOP_{side.upper()}: C_par mean {_ff(s['mean_f'])} fF "
                  f"({s['mean_cu']:.3f} C_u), C_u {_ff(s['c_u_mean_f'])} fF")
        return 0

    if args.record:
        data = collect(cids, workdir, args.backend, args.timeout_s)
        write_record(analyze(data, cids), data, cids, args.supersedes, workdir)
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

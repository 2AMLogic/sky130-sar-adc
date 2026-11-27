#!/usr/bin/env python3
"""Caps-only isolation probe for issue #1016's attribution analysis.

Question: is the committed Monte-Carlo campaign's per-draw DNL/INL spread
driven by the MiM unit-cap mismatch, or by the nfet/pfet bottom-plate
switches (which also carry local mismatch at the `tt_mm` corner)?

Method: rebuild the campaign netlist with every semiconductor switch
REPLACED by an ideal drive -- bit=0 cells get a 1 ohm tie to VREFN, bit=1
cells get a PWL voltage source (0 V until 1.9n, ramping to vdd_val by
2.1n, i.e. cleanly AFTER the shared reset switch has opened at ~1.1n)
through a 1 kohm Thevenin -- and run it at `tt_mm` across several seeds.
With no semiconductor device left in the signal path, ANY per-seed level
variation can only come from the caps' own AGAUSS mismatch, so comparing
the per-code level spread against the committed campaign's answers the
question directly.

This is a DEBUG PROBE, not a record-writing campaign: it exists to support
the attribution analysis record written by `analysis/attribute_1016.py`
(which cites this probe's committed logs and numbers). It runs a handful of
sequential single-corner ngspice jobs -- deliberately modest, per the host
rules that park Monte-Carlo grids on the batch fleet.

Usage:
    python3 sim/cdac-array-transfer/analysis/probe_caps_only.py            # 8 seeds, print table
    python3 sim/cdac-array-transfer/analysis/probe_caps_only.py --seeds 8 --commit
"""

from __future__ import annotations

import argparse
import datetime
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
from harness import pdk as pdk_mod, toolchain  # noqa: E402

PROBE_CODES = [0, 1, 127, 128, 255, 256, 383, 384, 385, 510, 511]


def build_caps_only_netlist(info, corner: str, seed: int) -> str:
    net = run_mc.build_netlist(info, corner, run_mc.TEMP_C, run_mc.NOMINAL_SUPPLY_V, seed)
    out: list[str] = []
    for ln in net.splitlines():
        if ln.startswith("Vsel_"):
            continue  # gate-drive sources leave with the FETs
        if ln.startswith("Xn_"):
            toks = ln.split()
            cname, gate = toks[1], toks[2]
            if gate == "vdd":  # bit==0: nfet permanently on -> plain tie
                out.append(f"Rn_tie_{cname} {cname} vrefn 1")
            continue  # bit==1 nfet ends off: gone
        if ln.startswith("Xp_"):
            toks = ln.split()
            cname, gate = toks[1], toks[2]
            if gate != "vdd":  # bit==1: pfet ends on -> ideal PWL drive, after reset opens
                out.append(f"Vbot_{cname} n_{cname} 0 pwl(0 0 1.9n 0 2.1n {{vdd_val}} 500n {{vdd_val}})")
                out.append(f"Rp_tie_{cname} {cname} n_{cname} 1k")
            continue  # bit==0 pfet off: gone
        out.append(ln)
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seeds", type=int, default=8, help="number of seeds (1..N) to run")
    ap.add_argument("--commit", action="store_true",
                    help="write the probe netlist + logs under analysis/probe-caps-only-<ts>/ for the record to cite")
    args = ap.parse_args()

    info = pdk_mod.resolve()
    if not info.found:
        print(f"PDK not resolvable: {info.error}")
        return 3

    out_dir = None
    if args.commit:
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            sha = subprocess.run(["git", "rev-parse", "--short=8", "HEAD"], capture_output=True, text=True,
                                 cwd=EXPERIMENT_DIR).stdout.strip() or "git-na"
        except OSError:
            sha = "git-na"
        out_dir = EXPERIMENT_DIR / "analysis" / f"probe-caps-only-{ts}-{sha}"
        out_dir.mkdir(parents=True, exist_ok=True)

    names: list[str] = []
    for c in PROBE_CODES:
        names += [f"vtop_p_{c}", f"vtop_n_{c}"]
    levels: dict[int, list[float]] = {c: [] for c in PROBE_CODES}

    from harness import measure  # imported late: only needed once a run succeeds

    for seed in range(1, args.seeds + 1):
        net = build_caps_only_netlist(info, "tt_mm", seed)
        if out_dir and seed == 1:
            (out_dir / "variant_seed1.spice").write_text(net)
        if out_dir:
            scratch = out_dir
            log_name = f"capsonly_seed{seed}.log"
            log = toolchain.run_ngspice(net, scratch, log_name)
            (out_dir / log_name).write_text(log)  # run_ngspice returns text; persist for the record
        else:
            import tempfile
            with tempfile.TemporaryDirectory(prefix="probe-caps-only-") as tmp:
                log = toolchain.run_ngspice(net, Path(tmp), f"capsonly_seed{seed}.log")
        parsed = measure.parse(log, names)
        for c in PROBE_CODES:
            vp, vn = parsed.get(f"vtop_p_{c}"), parsed.get(f"vtop_n_{c}")
            levels[c].append((vp - vn) if (vp is not None and vn is not None) else float("nan"))

    print(f"caps-only probe: per-code vdiff level spread across {args.seeds} seeds (tt_mm, caps keep AGAUSS mismatch)")
    print("code   sd(uV)    mean(V)")
    for c in PROBE_CODES:
        print(f"{c:4d}  {statistics.stdev(levels[c]) * 1e6:8.1f}  {statistics.fmean(levels[c]):+.6f}")
    if out_dir:
        print(f"\ncommitted probe artifacts under {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

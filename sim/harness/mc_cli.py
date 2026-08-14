"""CLI for sim/monte_carlo.py.

    python3 sim/monte_carlo.py --list
    python3 sim/monte_carlo.py mc-smoke --seed 1 --n 8
    python3 sim/monte_carlo.py mc-smoke --seed 1 --n 8 --record

See sim/README.md for the evidence-record format this writes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import mc_runner, testbench

SIM_DIR = Path(__file__).resolve().parent.parent


def _experiments() -> list[str]:
    return [p.parent.parent.name for p in sorted(SIM_DIR.glob("*/testbench/tb.json"))]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Monte Carlo runner (sim/harness)")
    ap.add_argument("experiment", nargs="?", help="experiment directory name under sim/")
    ap.add_argument("--list", action="store_true", help="list available experiments")
    ap.add_argument("--corner", default="tt", help="base process corner (mismatch corner is <corner>_mm)")
    ap.add_argument("--temp", type=float, default=27.0, help="temperature (C)")
    ap.add_argument("--supply", type=float, help="supply (V); defaults to the manifest's nominal_supply_v")
    ap.add_argument("--seed", type=int, required=False, default=1, help="base rndseed (recorded; draws use seed, seed+1, ...)")
    ap.add_argument("--n", type=int, required=False, default=10, help="sample count N")
    ap.add_argument("--record", action="store_true", help="write an evidence record under sim/<experiment>/records/")
    ap.add_argument("--supersedes", default="", help="record-id this run's evidence record supersedes")
    ap.add_argument("--note", default="", help="free-text note attached to the evidence record")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if args.list:
        for name in _experiments():
            print(name)
        return 0

    if not args.experiment:
        ap.print_help()
        return 2
    if args.n < 2:
        print("monte_carlo.py: --n must be >= 2 (a distribution needs more than one sample)", file=sys.stderr)
        return 2

    tb_json = SIM_DIR / args.experiment / "testbench" / "tb.json"
    if not tb_json.is_file():
        print(f"monte_carlo.py: no such experiment '{args.experiment}' (no {tb_json})", file=sys.stderr)
        return 1

    manifest = testbench.load(tb_json)
    supply_v = args.supply if args.supply is not None else manifest.nominal_supply_v

    result = mc_runner.run(
        manifest,
        process_corner=args.corner,
        temp_c=args.temp,
        supply_v=supply_v,
        seed=args.seed,
        n=args.n,
        quiet=args.quiet,
    )

    names = list(manifest.measure.keys())
    ctrl_ok, ctrl_failures = mc_runner.negative_control_ok(result, names)
    pos_ok, pos_failures = mc_runner.positive_control_ok(result, names, manifest.checks)

    if args.record:
        record_path = mc_runner.write_evidence(result, note=args.note, supersedes=args.supersedes)
        print(f"wrote {record_path}")

    dists = mc_runner.distributions(result.draws, names)
    if not args.quiet:
        for name, d in dists.items():
            print(f"{name}: N={d.n} mean={d.mean:.6g} stdev={d.stdev:.6g} min={d.minimum:.6g} max={d.maximum:.6g}")
        print(f"negative control: {'PASS' if ctrl_ok else 'FAIL: ' + '; '.join(ctrl_failures)}")
        print(f"positive control (mismatch draws must vary): {'PASS' if pos_ok else 'FAIL: ' + '; '.join(pos_failures)}")

    # Both arms must pass: a negative control that always passes AND a
    # positive control that always passes would together be
    # indistinguishable from a harness that never actually randomizes
    # anything (see mc_runner.positive_control_ok()'s docstring).
    return 0 if (ctrl_ok and pos_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())

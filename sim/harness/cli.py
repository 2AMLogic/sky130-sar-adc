"""CLI for sim/run_corners.py.

    python3 sim/run_corners.py --check-env
    python3 sim/run_corners.py --list
    python3 sim/run_corners.py --print-env
    python3 sim/run_corners.py harness-corner-smoke
    python3 sim/run_corners.py harness-corner-smoke --record
    python3 sim/run_corners.py harness-corner-smoke --sabotage-corners --quiet

See sim/README.md for the evidence-record format this writes.
"""

from __future__ import annotations

import argparse
import sys

from . import pdk, runner, testbench, toolchain


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PVT corner runner (sim/harness)")
    ap.add_argument("experiment", nargs="?", help="experiment directory name under sim/")
    ap.add_argument("--check-env", action="store_true", help="check toolchain + PDK, print summary")
    ap.add_argument("--list", action="store_true", help="list available experiments")
    ap.add_argument("--print-env", action="store_true", help="print PDK_ROOT/PDK exports (for sim/env.sh)")
    ap.add_argument("--corners", help="comma-separated process corners override")
    ap.add_argument("--temps", help="comma-separated temperature (C) override")
    ap.add_argument("--supply-tol", type=float, help="supply tolerance override (e.g. 0.1)")
    ap.add_argument("--sabotage-corners", action="store_true", help="force process corner to tt (negative control)")
    ap.add_argument("--record", action="store_true", help="write an evidence record under sim/<experiment>/records/")
    ap.add_argument("--supersedes", default="", help="record-id this run's evidence record supersedes")
    ap.add_argument("--note", default="", help="free-text note attached to the evidence record")
    ap.add_argument("--quiet", action="store_true", help="suppress per-corner progress output")
    ap.add_argument("--allow-toolchain-drift", action="store_true")
    args = ap.parse_args(argv)

    if args.print_env:
        info = pdk.resolve()
        sys.stdout.write(pdk.print_env(info))
        return 0

    if args.list:
        for name in testbench.experiments():
            print(name)
        return 0

    if args.check_env:
        result = toolchain.check_env(allow_drift=args.allow_toolchain_drift)
        print(toolchain.summary())
        for w in result.warnings:
            print(f"  ! warning: {w}")
        for m in result.messages:
            print(f"  - {m}")
        return result.status

    if not args.experiment:
        ap.print_help()
        return 2

    try:
        manifest = testbench.load_experiment(args.experiment)
    except FileNotFoundError as e:
        print(f"run_corners.py: no such experiment '{args.experiment}' (no {e})", file=sys.stderr)
        return 1

    process_corners = args.corners.split(",") if args.corners else None
    temperatures_c = [float(t) for t in args.temps.split(",")] if args.temps else None

    result, axis_spreads = runner.run(
        manifest,
        process_corners=process_corners,
        temperatures_c=temperatures_c,
        supply_tolerance=args.supply_tol,
        sabotage=args.sabotage_corners,
        quiet=args.quiet,
    )

    if args.record:
        record_path = runner.write_evidence(
            result, axis_spreads, note=args.note, supersedes=args.supersedes
        )
        print(f"wrote {record_path}")

    if not args.quiet:
        print(f"{'PASS' if result.overall_ok else 'FAIL'}: {args.experiment} ({result.record_id})")

    return 0 if result.overall_ok else 1

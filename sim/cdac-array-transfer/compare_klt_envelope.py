#!/usr/bin/env python3
"""Compare a `klt sim` envelope against a committed cdac-array-transfer
corner-log baseline (issue #564 pilot).

    python3 sim/cdac-array-transfer/compare_klt_envelope.py \\
        <report.json[.gz]> [--baseline-record 20261001-120402-d24f700]

Pass rule (pilot-local, NOT a spec value): every (corner, measurement) pair
has |klt - baseline| <= TOLERANCE_V, no pair is missing or non-finite, and the
envelope's corner set equals the baseline's. Exit 0 on pass, 1 on a miss,
2 on unreadable input. Read-only toward the baseline logs. The tolerance is
two print steps of the 6-significant-digit baseline logs; do not widen it to
make a result pass.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import corners as corners_mod  # noqa: E402
from harness import measure  # noqa: E402

EXPERIMENT_DIR = Path(__file__).resolve().parent
TOLERANCE_V = 2e-5
DEFAULT_BASELINE_RECORD = "20261001-120402-d24f700"
CODES = [0, 128, 256, 384, 511]
NAMES = [f"vtop_{s}_{c}" for c in CODES for s in "pn"]


def load_baseline(record_id: str, root: Path = EXPERIMENT_DIR) -> dict[str, dict[str, float]]:
    """{corner_id: {measurement: value}} parsed from the committed corner logs."""
    out: dict[str, dict[str, float]] = {}
    for log in sorted((root / "corners" / record_id).glob("*.log")):
        out[log.stem] = measure.parse(log.read_text(errors="replace"), NAMES)
    return out


def envelope_values(report: dict) -> dict[str, dict[str, float | None]]:
    """{baseline-style corner_id: {measurement: value|None}} from a klt report."""
    out: dict[str, dict[str, float | None]] = {}
    for corner in report.get("corners", []):
        vdd = (corner.get("params") or {}).get("vdd_val")
        cid = corners_mod.corner_id(corner["process"], float(corner["temperature_c"]), float(vdd))
        out[cid] = {m["name"]: m.get("value") for m in corner.get("measurements", [])}
    return out


def compare(report: dict, baseline: dict[str, dict[str, float]], tol: float = TOLERANCE_V) -> dict:
    env = envelope_values(report)
    problems: list[str] = []
    if set(env) != set(baseline):
        problems.append(
            f"corner sets differ: only-in-envelope={sorted(set(env) - set(baseline))} "
            f"only-in-baseline={sorted(set(baseline) - set(env))}"
        )
    pairs = 0
    max_delta = None
    max_at = None
    for cid in sorted(set(env) & set(baseline)):
        for name in NAMES:
            ref = baseline[cid].get(name)
            got = env[cid].get(name)
            if ref is None or got is None or not math.isfinite(got):
                problems.append(f"{cid}/{name}: missing or non-finite (klt={got!r}, baseline={ref!r})")
                continue
            pairs += 1
            delta = abs(got - ref)
            if max_delta is None or delta > max_delta:
                max_delta, max_at = delta, f"{cid}/{name}"
            if delta > tol:
                problems.append(f"{cid}/{name}: |delta|={delta:.3e} V > {tol:.1e} V")
    return {
        "passed": not problems,
        "pairs_compared": pairs,
        "corners_envelope": len(env),
        "corners_baseline": len(baseline),
        "max_abs_delta_v": max_delta,
        "max_at": max_at,
        "tolerance_v": tol,
        "problems": problems,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("report")
    ap.add_argument("--baseline-record", default=DEFAULT_BASELINE_RECORD)
    args = ap.parse_args(argv)
    try:
        path = Path(args.report)
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt") as fh:
            report = json.load(fh)
        baseline = load_baseline(args.baseline_record)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    result = compare(report, baseline)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())

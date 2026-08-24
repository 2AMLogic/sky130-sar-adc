"""Run a testbench manifest across a PVT corner grid and (optionally) write
an append-only evidence record under sim/<experiment>/records/.
"""

from __future__ import annotations

import statistics
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import corners as corners_mod
from . import evidence, measure, pdk, testbench, toolchain

SIM_DIR = Path(__file__).resolve().parent.parent


@dataclass
class CornerPointResult:
    process_corner: str
    temp_c: float
    supply_v: float
    corner_id: str
    measures: dict[str, float]
    log_path: Path
    log_text: str
    ok: bool
    check_failures: list[str] = field(default_factory=list)


@dataclass
class RunResult:
    manifest: testbench.Manifest
    points: list[CornerPointResult]
    record_id: str
    netlist_sha256: str
    overall_ok: bool


def _evaluate_checks(
    name: str,
    checks: dict,
    value: float,
    axis_spreads: dict[str, float],
) -> list[str]:
    failures = []
    if "min" in checks and value < checks["min"]:
        failures.append(f"{name}={value:.6g} < min {checks['min']}")
    if "max" in checks and value > checks["max"]:
        failures.append(f"{name}={value:.6g} > max {checks['max']}")
    for axis, floor in checks.get("min_spread_pct_by_axis", {}).items():
        spread = axis_spreads.get(axis)
        if spread is not None and spread < floor:
            failures.append(
                f"{name}: {axis}-axis spread {spread:.4g}% below floor {floor}%"
            )
    for axis, ceiling in checks.get("max_spread_pct_by_axis", {}).items():
        spread = axis_spreads.get(axis)
        if spread is not None and spread > ceiling:
            failures.append(
                f"{name}: {axis}-axis spread {spread:.4g}% above ceiling {ceiling}%"
            )
    return failures


def _spread_pct(values: list[float]) -> float:
    if not values:
        return 0.0
    lo, hi = min(values), max(values)
    denom = abs(statistics.fmean(values)) or 1e-30
    return abs(hi - lo) / denom * 100.0


def run(
    manifest: testbench.Manifest,
    process_corners: list[str] | None = None,
    temperatures_c: list[float] | None = None,
    supply_tolerance: float | None = None,
    sabotage: bool = False,
    quiet: bool = False,
) -> tuple[RunResult, dict]:
    info = pdk.resolve()
    if not info.found:
        raise RuntimeError(f"PDK not resolvable: {info.error}")

    process_corners = process_corners or manifest.process_corners
    temperatures_c = temperatures_c or manifest.temperatures_c
    tol = manifest.supply_tolerance if supply_tolerance is None else supply_tolerance
    supply_points = corners_mod.supply_points(manifest.nominal_supply_v, tol)

    baseline_process = "tt" if "tt" in process_corners else process_corners[0]
    baseline_temp = 27 if 27 in temperatures_c else temperatures_c[0]
    baseline_supply = manifest.nominal_supply_v

    record_id = evidence.new_record_id()
    netlist_sha = evidence.sha256_file(manifest.netlist_fragment)

    corners_out_dir = manifest.experiment_dir / "corners" / record_id
    points: list[CornerPointResult] = []

    # See corners_mod.oat_grid()'s docstring for why this is a one-at-a-time
    # (OAT / "star") grid rather than a full factorial |process|x|temp|x|supply|
    # grid.
    grid = corners_mod.oat_grid(
        baseline_process,
        baseline_temp,
        baseline_supply,
        process_corners,
        temperatures_c,
        supply_points,
    )

    with tempfile.TemporaryDirectory(prefix="sim-harness-") as scratch:
        scratch_dir = Path(scratch)
        for process_corner, temp_c, supply_v in grid:
            cid = corners_mod.corner_id(process_corner, temp_c, supply_v)
            netlist = testbench.build_netlist(
                manifest, info, process_corner, temp_c, supply_v, sabotage=sabotage
            )
            log_text = toolchain.run_ngspice(netlist, scratch_dir, cid)
            parsed = measure.parse(log_text, list(manifest.measure.keys()))
            log_path = corners_out_dir / f"{cid}.log"
            points.append(
                CornerPointResult(
                    process_corner=process_corner,
                    temp_c=temp_c,
                    supply_v=supply_v,
                    corner_id=cid,
                    measures=parsed,
                    log_path=log_path,
                    log_text=log_text,
                    ok=True,
                )
            )
            if not quiet:
                print(f"  {cid}: {parsed}")

    # Per-axis sensitivity, holding the other two axes at baseline.
    axis_spreads: dict[str, dict[str, float]] = {}
    for name in manifest.measure:
        process_slice = [
            p.measures[name]
            for p in points
            if p.temp_c == baseline_temp and p.supply_v == baseline_supply and name in p.measures
        ]
        temp_slice = [
            p.measures[name]
            for p in points
            if p.process_corner == baseline_process and p.supply_v == baseline_supply and name in p.measures
        ]
        supply_slice = [
            p.measures[name]
            for p in points
            if p.process_corner == baseline_process and p.temp_c == baseline_temp and name in p.measures
        ]
        axis_spreads[name] = {
            "process": _spread_pct(process_slice),
            "temperature": _spread_pct(temp_slice),
            "supply": _spread_pct(supply_slice),
        }

    overall_ok = True
    for p in points:
        failures: list[str] = []
        for name, checks in manifest.checks.items():
            if name not in p.measures:
                failures.append(f"{name}: no measurement parsed from log")
                continue
            failures.extend(
                _evaluate_checks(name, checks, p.measures[name], axis_spreads.get(name, {}))
            )
        p.check_failures = failures
        p.ok = not failures
        overall_ok = overall_ok and p.ok

    return RunResult(
        manifest=manifest,
        points=points,
        record_id=record_id,
        netlist_sha256=netlist_sha,
        overall_ok=overall_ok,
    ), axis_spreads


def write_evidence(
    result: RunResult, axis_spreads: dict, note: str = "", supersedes: str = ""
) -> Path:
    manifest = result.manifest
    experiment_dir = manifest.experiment_dir

    # Persist the logs already captured by run() -- no need to re-invoke
    # ngspice a second time (each sky130-library invocation costs ~15-20s on
    # this toolchain; doubling it here for a --record run would be wasteful
    # and could theoretically diverge from what was just evaluated).
    corners_dir = experiment_dir / "corners" / result.record_id
    corners_dir.mkdir(parents=True, exist_ok=True)
    info = pdk.resolve()
    for p in result.points:
        (corners_dir / f"{p.corner_id}.log").write_text(p.log_text)

    record_path = evidence.write_netlist_snapshot(
        experiment_dir, result.record_id, manifest.netlist_fragment
    )

    lines: list[str] = []
    a = lines.append
    a(f"# Record {result.record_id}")
    a("")
    a(f"- **Record ID**: {result.record_id}")
    a(f"- **Claim**: {manifest.claim}")
    a(f"- **Netlist provenance**: schematic (`{manifest.netlist_fragment.relative_to(evidence.REPO_ROOT)}`)")
    process_corners_run = sorted({p.process_corner for p in result.points})
    temps_run = sorted({p.temp_c for p in result.points})
    supplies_run = sorted({p.supply_v for p in result.points})
    a(
        f"- **Corner matrix run**: process={process_corners_run}, "
        f"temperature_c={temps_run}, supply_v={supplies_run} "
        f"({len(result.points)} points)"
    )
    if note:
        a(f"- **Note**: {note}")
    a(f"- **Overall**: {'PASS' if result.overall_ok else 'FAIL'}")
    a("")
    a("## Per-corner results")
    a("")
    measure_names = list(manifest.measure.keys())
    a("| corner-id | " + " | ".join(measure_names) + " | pass/fail |")
    a("|---|" + "---|" * (len(measure_names) + 1))
    for p in result.points:
        vals = " | ".join(f"{p.measures.get(m, float('nan')):.6g}" for m in measure_names)
        a(f"| `{p.corner_id}` | {vals} | {'PASS' if p.ok else 'FAIL: ' + '; '.join(p.check_failures)} |")
    a("")
    a("## Per-axis sensitivity (spread %, other axes held at baseline)")
    a("")
    a("| measurement | process | temperature | supply |")
    a("|---|---|---|---|")
    for name in measure_names:
        s = axis_spreads.get(name, {})
        a(
            f"| `{name}` | {s.get('process', 0):.4g} | "
            f"{s.get('temperature', 0):.4g} | {s.get('supply', 0):.4g} |"
        )
    a("")
    lines.extend(evidence.environment_block(
        pdk_line=f"{info.variant} @ {pdk.resolved_commit(info)}",
        ngspice_line=toolchain._ngspice_version() or "unknown",
        netlist_sha256=result.netlist_sha256,
    ))
    a("")
    lines.extend(evidence.footer_lines("sim/run_corners.py", supersedes))

    record_path.write_text("\n".join(lines))
    return record_path

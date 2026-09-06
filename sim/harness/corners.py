"""sky130 PVT corner definitions used by the harness.

Deliberately does NOT hardcode a supply nominal or a pass/fail threshold
anywhere in this module -- V_REF is an open, unratified spec value (see
spec/target-spec.md, gated on issue #1 / DR-001) and CLAUDE.md forbids
encoding an unratified spec value as a pass/fail threshold. A testbench
manifest (tb.json) must supply its own nominal_supply_v, process corners,
temperatures, and supply tolerance; this module only supplies PDK-derived
helpers (mismatch-corner lookup, corner-id formatting, supply-point
spreading), which are properties of the PDK and of repo convention, not of
the ADC spec.
"""

from __future__ import annotations

from .pdk import load_pdk_json


def default_mismatch_corners() -> list[str]:
    return list(load_pdk_json()["mismatch_corners"])


def mismatch_corner_for(process_corner: str) -> str:
    """tt -> tt_mm, ss -> ss_mm, ... -- the local-mismatch switch for a
    given base process corner (sim/pdk.json's "mismatch_corners" note)."""
    mm = f"{process_corner}_mm"
    if mm not in default_mismatch_corners():
        raise ValueError(
            f"no mismatch corner for process corner '{process_corner}' -- "
            f"available: {default_mismatch_corners()}"
        )
    return mm


def corner_id(process_corner: str, temp_c: float, supply_v: float) -> str:
    """<process>_<temp>c_<supply>v, e.g. ss_-40c_1.62v (gf180-sar-adc's
    sim/README.md naming convention, unchanged)."""
    temp_str = f"{temp_c:g}"
    supply_str = f"{supply_v:.2f}"
    return f"{process_corner}_{temp_str}c_{supply_str}v"


def supply_points(nominal_v: float, tolerance: float) -> list[float]:
    if tolerance <= 0:
        return [nominal_v]
    lo = round(nominal_v * (1 - tolerance), 6)
    hi = round(nominal_v * (1 + tolerance), 6)
    # De-dup in case rounding collapses lo/hi onto nominal (tolerance ~ 0).
    points = sorted({lo, nominal_v, hi})
    return points


def corner_matrix_summary_line(
    process_corners: list, temps_c: list, supplies_v: list, n_points: int
) -> str:
    """The "Corner matrix run" evidence-record bullet line shared by every
    experiment driver's OAT-corner-campaign record writer (cdac-array-transfer,
    comparator-decision, sar-sequencer-behavioral -- see sim/README.md's
    one-at-a-time convention). Callers still do their own sorted-unique
    extraction of the axis values (the input *shapes* differ per site --
    dicts vs. dataclass attributes) and pass the resulting lists in here;
    only the final formatted string is centralized."""
    return (
        f"- **Corner matrix run**: process={process_corners}, "
        f"temperature_c={temps_c}, supply_v={supplies_v} "
        f"({n_points} points, one-at-a-time per sim/README.md)"
    )


def oat_grid(
    baseline_process: str,
    baseline_temp: float,
    baseline_supply: float,
    process_corners: list[str],
    temperatures_c: list[float],
    supply_voltages: list[float],
) -> list[tuple[str, float, float]]:
    """Build a one-at-a-time (OAT / "star") PVT grid: the baseline point
    plus, for each axis in turn, every OTHER value on that axis with the
    remaining two axes held at baseline -- deduplicated, in the order the
    baseline/process/temperature/supply points are first encountered.

    This is deliberately NOT a full factorial |process|x|temp|x|supply|
    grid: it is exactly the set a per-axis sensitivity computation needs
    (each axis's spread is only ever computed from points held at baseline
    on the other two axes), and for a sky130 combined-library ngspice
    invocation (~15-20s each on this toolchain -- PDK model-library load
    dominates, not simulation time) a full grid would cost minutes per
    experiment for no additional signal. E.g. len(process)=5, len(temp)=3,
    len(supply)=3 costs 9 OAT runs instead of 45 full-factorial ones.
    """
    seen: set[tuple[str, float, float]] = set()
    grid: list[tuple[str, float, float]] = []

    def _add(pc: str, tc: float, sv: float) -> None:
        key = (pc, tc, sv)
        if key not in seen:
            seen.add(key)
            grid.append(key)

    _add(baseline_process, baseline_temp, baseline_supply)
    for process_corner in process_corners:
        _add(process_corner, baseline_temp, baseline_supply)
    for temp_c in temperatures_c:
        _add(baseline_process, temp_c, baseline_supply)
    for supply_v in supply_voltages:
        _add(baseline_process, baseline_temp, supply_v)

    return grid


def ratified_oat_grid(
    nominal_v: float,
    tolerance: float,
    process_corners: list[str],
    temps_c: list[float],
) -> list[tuple[str, float, float]]:
    """oat_grid() built on the ratified "tt"/27C baseline convention
    (spec/target-spec.md's "Numeric rows -- RATIFIED 2026-08-19" section:
    tt process corner, 27C, nominal supply, as the OAT star's center
    point). Every --corners driver in sim/ that sweeps the ratified corner
    set anchors its grid on this same baseline; this helper centralizes the
    supply_points() + oat_grid() chain those call sites previously
    hand-repeated (issue #211 -- see sim/harness/corners.py's docstring for
    why the baseline itself is a repo convention, not a hardcoded spec
    value: nominal_v/process_corners/temps_c are still supplied by the
    caller's own testbench manifest)."""
    return oat_grid(
        "tt", 27.0, nominal_v, process_corners, temps_c, supply_points(nominal_v, tolerance)
    )

"""sky130 PVT corner definitions used by the harness.

Deliberately does NOT hardcode a supply nominal or a pass/fail threshold
anywhere in this module -- V_REF is an open, unratified spec value (see
spec/target-spec.md, gated on issue #1 / DR-001) and CLAUDE.md forbids
encoding an unratified spec value as a pass/fail threshold. A testbench
manifest (tb.json) must supply its own nominal_supply_v; this module only
supplies the axis *lists* (which process corners exist, and this repo's
canary-standard default temperature/tolerance sweep), which are properties
of the PDK and of repo convention, not of the ADC spec.
"""

from __future__ import annotations

import json
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent


def _load_pdk_json() -> dict:
    with (SIM_DIR / "pdk.json").open() as f:
        return json.load(f)


def default_process_corners() -> list[str]:
    """The base MOS/BJT .lib sections -- verified present in
    libs.tech/combined/sky130.lib.spice (see sim/pdk.json's notes)."""
    return list(_load_pdk_json()["process_corners"])


def default_mismatch_corners() -> list[str]:
    return list(_load_pdk_json()["mismatch_corners"])


# "Canary standard" default sweep per CLAUDE.md ("PVT corners on every
# recorded result") and this workspace's sibling repos -- a *default*, not
# a spec value: a manifest may override it, and no check here asserts a
# spec pass/fail against it.
DEFAULT_TEMPERATURES_C: tuple[int, ...] = (-40, 27, 125)
DEFAULT_SUPPLY_TOLERANCE: float = 0.10


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

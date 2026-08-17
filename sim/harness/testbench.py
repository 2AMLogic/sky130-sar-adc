"""Load a sim/<experiment>/testbench/tb.json manifest and build a runnable
ngspice netlist for one PVT corner point.

Manifest schema (subset of gf180-sar-adc's sim/harness testbench schema,
ported/adapted -- see sim/README.md "Provenance"):

{
  "name": "harness-corner-smoke",
  "description": "...",
  "claim": "None -- harness self-test, not a spec claim. ...",
  "netlist_fragment": "harness_corner_smoke.spice",
  "nominal_supply_v": 1.8,
  "supply_tolerance": 0.10,
  "temperatures_c": [-40, 27, 125],
  "process_corners": ["tt", "ss", "ff", "sf", "fs"],
  "measure": {"vdiv_ratio": "v(ndiv)/v(vdd)", "vgs_nfet": "v(nbias)"},
  "checks": {
    "vgs_nfet": {"min": 0.3, "max": 1.2,
                 "min_spread_pct_by_axis": {"process": 1.0, "temperature": 3.0}}
  }
}

The netlist fragment is a plain SPICE deck fragment (devices/sources only)
that references `{vdd_val}` for its supply -- the harness prepends a
`.param vdd_val = <value>` line, the corner's `.lib ... <corner>` include,
and a `.temp` card, and appends a `.control ... op ... let/print ... .endc`
block built from the "measure" dict.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import pdk

SIM_DIR = Path(__file__).resolve().parent.parent


def experiments() -> list[str]:
    """Experiment directory names under sim/ that have a testbench manifest,
    i.e. sim/<experiment>/testbench/tb.json -- shared by run_corners.py's and
    monte_carlo.py's --list."""
    return [p.parent.parent.name for p in sorted(SIM_DIR.glob("*/testbench/tb.json"))]


@dataclass
class Manifest:
    path: Path
    experiment_dir: Path
    name: str
    description: str
    claim: str
    netlist_fragment: Path
    nominal_supply_v: float
    supply_tolerance: float
    temperatures_c: list[float]
    process_corners: list[str]
    measure: dict[str, str]
    checks: dict[str, dict]
    raw: dict


def load_experiment(experiment: str) -> Manifest:
    """Resolve an experiment name to its manifest, i.e.
    sim/<experiment>/testbench/tb.json -- shared by run_corners.py's and
    monte_carlo.py's experiment-argument resolution. Raises
    FileNotFoundError(tb_json) if the manifest is missing; callers are
    expected to catch it and print their own program-specific error."""
    tb_json = SIM_DIR / experiment / "testbench" / "tb.json"
    if not tb_json.is_file():
        raise FileNotFoundError(tb_json)
    return load(tb_json)


def load(tb_json_path: Path) -> Manifest:
    with tb_json_path.open() as f:
        raw = json.load(f)
    experiment_dir = tb_json_path.parent.parent  # .../<experiment>/testbench/tb.json
    fragment = tb_json_path.parent / raw["netlist_fragment"]
    if not fragment.is_file():
        raise FileNotFoundError(f"netlist_fragment not found: {fragment}")
    return Manifest(
        path=tb_json_path,
        experiment_dir=experiment_dir,
        name=raw["name"],
        description=raw.get("description", ""),
        claim=raw.get("claim", ""),
        netlist_fragment=fragment,
        nominal_supply_v=float(raw["nominal_supply_v"]),
        supply_tolerance=float(raw.get("supply_tolerance", 0.0)),
        temperatures_c=list(raw.get("temperatures_c", [27])),
        process_corners=list(raw.get("process_corners", [])),
        measure=dict(raw["measure"]),
        checks=dict(raw.get("checks", {})),
        raw=raw,
    )


def _render_body(
    manifest: Manifest,
    pdk_info: pdk.PdkInfo,
    lib_corner: str,
    temp_c: float,
    supply_v: float,
    extra_lines: tuple[str, ...] = (),
) -> list[str]:
    """Render the `.lib`/`.temp`/`.param vdd_val`/fragment/`.control` block
    shared by build_netlist() and mc_runner._build_mc_netlist() -- the only
    things that differ between the two callers are the header comment
    (theirs to prepend) and mc_runner's extra `.option rndseed=` line
    (passed via extra_lines, emitted right after `.param vdd_val`)."""
    lines: list[str] = []
    a = lines.append
    a(f".lib {pdk_info.ngspice_lib} {lib_corner}")
    a(f".temp {temp_c}")
    a(f".param vdd_val = {supply_v}")
    for extra in extra_lines:
        a(extra)
    a("")
    a(manifest.netlist_fragment.read_text())
    a("")
    a(".control")
    a("op")
    for name, expr in manifest.measure.items():
        a(f"let {name} = {expr}")
        a(f"print {name}")
    a(".endc")
    a(".end")
    return lines


def build_netlist(
    manifest: Manifest,
    pdk_info: pdk.PdkInfo,
    process_corner: str,
    temp_c: float,
    supply_v: float,
    sabotage: bool = False,
) -> str:
    """Render the full netlist for one PVT point.

    sabotage=True forces the process-corner .lib section to 'tt' regardless
    of the requested process_corner, while leaving .temp and vdd_val
    untouched -- the negative control sim/selftest.sh uses to prove corner
    switching specifically is taking effect. Deliberately does NOT also
    sabotage temperature: isolating the axes means a runner that switches
    .temp correctly but not the .lib section (or vice versa) is caught by
    the corresponding per-axis check instead of both failing together.
    """
    lib_corner = "tt" if sabotage else process_corner
    lib_temp = temp_c

    lines: list[str] = []
    a = lines.append
    a(f"* {manifest.name} -- generated by sim/harness (issue #2)")
    a(f"* corner={process_corner} temp={temp_c}C supply={supply_v}V" + (" [SABOTAGED]" if sabotage else ""))
    lines.extend(_render_body(manifest, pdk_info, lib_corner, lib_temp, supply_v))
    return "\n".join(lines) + "\n"

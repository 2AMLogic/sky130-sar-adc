"""Area of the declared digital partition, derived from COMMITTED routed
artifacts only (issue #619). PDK-free apart from the standard-cell LEF used
for the placed-cell sum, which is optional input.

Three different numbers, never conflated:

  * `placed_cell_area_um2`  -- sum of the LEF footprint (SIZE w x h) of every
    COMPONENT in the routed DEF, split into logic cells and physical-only
    cells (fill / tap / decap). A CELL area; it ignores routing channels and
    the die margin.
  * `macro_area_um2`        -- the DEF DIEAREA of each routed macro
    (`sar_sequencer`, `top_glue`). A MACRO area: it includes the placer's
    core margin and unused sites.
  * `composed_footprint_um2` -- the axis-aligned bounding box of the two
    macros as PLACED in the composed top-level (compose request origins +
    macro die sizes). A FOOTPRINT: it includes the gap between the macros.
    The plain sum of the two macro areas is reported only when the placed
    rectangles are proven disjoint, so no overlapping bounding boxes are ever
    summed; an overlap raises.

Area is geometry-derived and does not vary with the electrical corner.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


@dataclass
class DefInfo:
    design: str
    dbu_per_um: int
    die: tuple[int, int, int, int]  # x0 y0 x1 y1 in dbu
    components: list[tuple[str, str]]  # (instance, cell)

    @property
    def die_size_um(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.die
        return ((x1 - x0) / self.dbu_per_um, (y1 - y0) / self.dbu_per_um)

    @property
    def die_area_um2(self) -> float:
        w, h = self.die_size_um
        return w * h


_PHYSICAL_ONLY = re.compile(r"__(fill|decap|tap|tapvpwrvgnd|diode|lpflow_)")


def is_physical_only(cell: str) -> bool:
    return bool(_PHYSICAL_ONLY.search(cell))


def parse_def(text: str) -> DefInfo:
    m = re.search(r"^DESIGN\s+(\S+)\s*;", text, re.M)
    u = re.search(r"^UNITS\s+DISTANCE\s+MICRONS\s+(\d+)\s*;", text, re.M)
    d = re.search(r"^DIEAREA\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)\s*;", text, re.M)
    if not (m and u and d):
        raise ValueError("DEF is missing DESIGN / UNITS / DIEAREA")
    comps: list[tuple[str, str]] = []
    in_comp = False
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("COMPONENTS"):
            in_comp = True
            continue
        if s.startswith("END COMPONENTS"):
            break
        if in_comp and s.startswith("- "):
            parts = s.split()
            comps.append((parts[1], parts[2]))
    declared = re.search(r"^COMPONENTS\s+(\d+)\s*;", text, re.M)
    if declared and int(declared.group(1)) != len(comps):
        raise ValueError(f"DEF declares {declared.group(1)} components, parsed {len(comps)}")
    return DefInfo(m.group(1), int(u.group(1)), tuple(int(g) for g in d.groups()), comps)


def parse_lef_sizes(text: str) -> dict[str, tuple[float, float]]:
    """{macro name: (width_um, height_um)} from `MACRO ... SIZE w BY h ;`."""
    sizes: dict[str, tuple[float, float]] = {}
    cur = None
    for ln in text.splitlines():
        s = ln.strip()
        mm = re.match(r"MACRO\s+(\S+)", s)
        if mm:
            cur = mm.group(1)
            continue
        sz = re.match(r"SIZE\s+([0-9.eE+-]+)\s+BY\s+([0-9.eE+-]+)\s*;", s)
        if sz and cur:
            sizes[cur] = (float(sz.group(1)), float(sz.group(2)))
            cur = None
    return sizes


def placed_cell_area(info: DefInfo, lef_sizes: dict[str, tuple[float, float]]) -> dict:
    logic = phys = 0.0
    n_logic = n_phys = 0
    for _inst, cell in info.components:
        if cell not in lef_sizes:
            raise KeyError(f"cell {cell} has no LEF SIZE")
        w, h = lef_sizes[cell]
        if is_physical_only(cell):
            phys += w * h
            n_phys += 1
        else:
            logic += w * h
            n_logic += 1
    return {"logic_cell_area_um2": round(logic, 4), "logic_cell_count": n_logic,
            "physical_only_area_um2": round(phys, 4), "physical_only_count": n_phys,
            "placed_cell_area_um2": round(logic + phys, 4)}


Rect = tuple[float, float, float, float]  # x0 y0 x1 y1 (um)


def rects_overlap(a: Rect, b: Rect) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def compose_footprint(placed: dict[str, Rect]) -> dict:
    """Bounding box of disjoint placed rectangles, plus their plain area sum
    (valid only because disjointness is checked first)."""
    names = sorted(placed)
    for i, n in enumerate(names):
        for m in names[i + 1:]:
            if rects_overlap(placed[n], placed[m]):
                raise ValueError(f"macros {n} and {m} overlap; refusing to sum overlapping boxes")
    x0 = min(r[0] for r in placed.values())
    y0 = min(r[1] for r in placed.values())
    x1 = max(r[2] for r in placed.values())
    y1 = max(r[3] for r in placed.values())
    return {
        "bbox_um": [x0, y0, x1, y1],
        "composed_footprint_um2": round((x1 - x0) * (y1 - y0), 4),
        "sum_of_macro_areas_um2": round(sum((r[2] - r[0]) * (r[3] - r[1]) for r in placed.values()), 4),
        "disjoint": True,
    }


def derive(repo: Path, *, lef_path: Path | None = None) -> dict:
    """Area derivation from the macros the layout `reports/LATEST` pointers
    name, and the composed top-level's explicit placement. Raises if any
    source artifact is missing."""
    srcs = {}
    defs: dict[str, DefInfo] = {}
    for macro, d, fname in (("sar_sequencer", "layout/sar-sequencer", "sar_sequencer.def"),
                            ("top_glue", "layout/top-glue", "top_glue.def")):
        rid = (repo / d / "reports" / "LATEST").read_text().strip()
        p = repo / d / "reports" / rid / fname
        g = repo / d / "reports" / rid / fname.replace(".def", ".gds")
        srcs[macro] = {"report": f"{d}/reports/{rid}", "def": f"{d}/reports/{rid}/{fname}",
                       "def_sha256": sha256_file(p),
                       "gds": f"{d}/reports/{rid}/{g.name}", "gds_sha256": sha256_file(g)}
        defs[macro] = parse_def(p.read_text())

    top_rid = (repo / "layout/sar-adc-top/reports/LATEST").read_text().strip()
    creq = repo / "layout/sar-adc-top/reports" / top_rid / "compose.request.json"
    srcs["composition"] = {"compose_request": f"layout/sar-adc-top/reports/{top_rid}/compose.request.json",
                           "compose_request_sha256": sha256_file(creq)}
    origins = json.loads(creq.read_text())["placement"]["origins_um"]
    srcs["composition"]["origins_um"] = {m: origins[m] for m in ("sar_sequencer", "top_glue")}
    placed: dict[str, Rect] = {}
    macros = {}
    for macro, info in defs.items():
        w, h = info.die_size_um
        o = origins[macro]
        placed[macro] = (o["x"], o["y"], o["x"] + w, o["y"] + h)
        macros[macro] = {"die_um": [w, h], "macro_area_um2": round(info.die_area_um2, 4),
                         "origin_um": [o["x"], o["y"]], "component_count": len(info.components)}
    out: dict = {"sources": srcs, "macros": macros, **compose_footprint(placed)}
    out["macro_area_um2"] = round(sum(m["macro_area_um2"] for m in macros.values()), 4)
    if lef_path is not None and lef_path.is_file():
        sizes = parse_lef_sizes(lef_path.read_text())
        cells = {m: placed_cell_area(i, sizes) for m, i in defs.items()}
        out["cells"] = cells
        out["lef_sha256"] = sha256_file(lef_path)
        out["placed_cell_area_um2"] = round(sum(c["placed_cell_area_um2"] for c in cells.values()), 4)
        out["logic_cell_area_um2"] = round(sum(c["logic_cell_area_um2"] for c in cells.values()), 4)
    out["metric_notes"] = [
        "macro_area_um2 = sum of the two routed macros' DEF DIEAREA (MACRO area, includes core margin and unused sites)",
        "composed_footprint_um2 = bounding box of the two macros as placed in the composed top (FOOTPRINT, includes the gap between them)",
        "placed_cell_area_um2 = sum of LEF cell footprints of every routed DEF component (CELL area, incl. fill/tap); logic_cell_area_um2 excludes physical-only cells",
        "the digital decap macros placed in the composed top are physical-only and are NOT part of the partition's logic area",
        "area is geometry-derived and is not varied by electrical corner",
    ]
    return out

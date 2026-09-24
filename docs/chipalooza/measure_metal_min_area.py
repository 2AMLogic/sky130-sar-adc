#!/usr/bin/env python3
"""Measure sky130A's met1-met5 MINIMUM-AREA rules against this repo's own GDS.

Why this script exists (issue #326), and what it is now (issue #363)
--------------------------------------------------------------------
`klt drc --deck sky130` is this repo's layout sign-off gate. It was written
against a real gap: at the then-pinned `klayout-tools==0.5.0` the curated
sky130 deck authored 47 rules across five kinds (`width`, `space`,
`enclosing`, `separation`, `isolated`) and **no `area`-kind rule at all**, so
sky130A's own minimum-area rules --

    m1.6    min. m1 area  0.083  um^2
    m2.6    min. m2 area  0.0676 um^2
    m3.6    min. m3 area  0.240  um^2
    m4.4a   min. m4 area  0.240  um^2
    m5.4    min. m5 area  4.0    um^2

-- had never looked at any layout in this repository, and a `status: "clean"`
verdict said nothing about them. This script was the stand-in: it applies the
*same* KLayout primitive the PDK's own deck rule text calls
(`Region#with_area`), against the *same* thresholds and layer numbers, read out
of the pinned PDK install rather than transcribed here, so it cannot drift from
the PDK.

**That gap is closed.** `layout/requirements.txt` has since been bumped to
`klayout-tools==0.6.0` (issue #103, 2026-09-23), which contains commit
`50cc29c3` (2AMLogic/klayout-tools#1989). The pinned deck now authors 52 rules
including `met1.area.1` ... `met5.area.1` and `met1.holes_area.1` ...
`met5.holes_area.1` -- see any current record's own `drc.json`
`coverage.rules_checked`. `klt drc` is therefore the primary minimum-area
measurement again, and this script is no longer a stand-in for a missing rule.

It is kept as an **independent cross-check** rather than retired, because that
is what caught its own defect: for four days the two measurements disagreed
(this script claiming 145 residual sub-threshold shapes in the composed GDS,
`klt drc`'s own `met*.area.1` rules reporting 0), and the disagreement is what
exposed issue #363's under-merge bug *here*, not in the deck. Two independent
measurements of the same rule that must agree is a stronger gate than either
one alone; see `measure_gds()` for the property-aware-merge trap that made them
disagree, and `sim/tests/test_measure_metal_min_area.py` for the regression
fixture that now pins it.

Clean room: every number this script uses comes from this repo's own pinned
sky130A install (`sim/pdk.json`: open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b)
and from this repo's own committed GDS records. Nothing is transcribed from
any third-party layout.

WHAT IT MEASURES
----------------
For each of the five metal layers, on each target GDS:

  1. Read the layer number and the minimum-area threshold out of the pinned
     PDK's own `libs.tech/klayout/drc/sky130A_mr.drc` (the `mN_wildcard =
     "L/D"` assignments and the `mN.with_area(0..T).output("<rule>", ...)`
     calls). Nothing about the rule set is hardcoded below.
  2. Flatten the GDS's top cell onto that layer, drop the shapes' GDS user
     properties, and MERGE it (the DRC deck's `polygons(...)` input is
     merged-semantics *plain geometry*, so two abutting drawn rectangles are
     one polygon to the rule no matter what net each carries -- measuring
     under-merged shapes reports violations the foundry rule does not see,
     which is precisely the defect issue #363 found here), then select the
     polygons whose area is below the threshold with `Region#with_area`.
  3. Report every selected polygon's bounding box and area.

A non-empty selection is a real m1.6/m2.6/m3.6/m4.4a/m5.4 violation, and --
since the pinned deck now carries the same rules -- one `klt drc` should have
reported too. A disagreement between the two is a bug in one of them; do not
publish a count from this script without checking it against the same record's
own `drc.json` `met*.area.1` result.

USAGE
-----
    python3 docs/chipalooza/measure_metal_min_area.py [GDS ...] [options]

With no GDS arguments it measures the *current* record of the top-level
composition plus each of its five sub-block flows (each flow's own
`reports/LATEST` pointer, so it always grades the record the repo is
currently standing behind).

    --json          machine-readable output (per-target, per-layer, per-shape)
    --pdk-root DIR  PDK search root (default: $PDK_ROOT, else ~/.volare)
    --variant NAME  PDK variant (default: $PDK, else sky130A)
    --repo-root DIR repo root used to resolve the default targets

Exit status:

    0 - every measured layer is clear of its own minimum-area threshold
    1 - at least one shape is below threshold (each one listed)
    2 - usage/environment error (no PDK deck, no klayout module, bad path)

Requires the `klayout` Python module -- available in this repo's own
`layout/.venv` (`layout/bin/setup-venv.sh`), which is why this script is NOT
part of the always-on headless `checks` CI job: like `klt` itself it is
PDK- and KLayout-gated. Run it from that venv:

    layout/.venv/bin/python docs/chipalooza/measure_metal_min_area.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

#: Default measurement targets: `(label, flow directory, GDS basename)`.
#: The GDS basename is each flow's own top-level artefact -- the same file
#: `layout/sar-adc-top/bin/run-flow.sh` copies in as a composition input for
#: the five sub-blocks, and the composed cell that flow itself writes. Each
#: path is resolved through the flow's own `reports/LATEST` pointer, never a
#: hardcoded record id, so this measures whatever record the repo currently
#: stands behind.
DEFAULT_TARGETS: list[tuple[str, str, str]] = [
    ("sar-adc-top (composed)", "layout/sar-adc-top", "sar_adc_top.gds"),
    ("cdac-array", "layout/cdac-array", "cdac_array.gds"),
    ("comparator", "layout/comparator", "comparator.gds"),
    ("sampling-frontend", "layout/sampling-frontend", "sampling_frontend.gds"),
    ("sar-sequencer", "layout/sar-sequencer", "sar_sequencer.gds"),
    ("seln-inverters", "layout/seln-inverters", "seln_inverters.gds"),
]

#: The metal layer symbols the PDK deck names, in process order. Each one has
#: exactly one `mN.with_area(0..T).output("<rule>", ...)` minimum-area rule and
#: one `mN_wildcard = "L/D"` layer assignment in `sky130A_mr.drc`.
METAL_SYMBOLS = ["m1", "m2", "m3", "m4", "m5"]


class MeasurementError(RuntimeError):
    """Usage/environment problem (exit 2), as opposed to a real violation."""


# --------------------------------------------------------------------------- #
# PDK deck parsing -- the rule table is READ, never transcribed.
# --------------------------------------------------------------------------- #
def find_deck(pdk_root: Path, variant: str) -> Path:
    """Locate `<pdk_root>/<variant>/libs.tech/klayout/drc/<variant>_mr.drc`."""
    deck = pdk_root / variant / "libs.tech" / "klayout" / "drc" / f"{variant}_mr.drc"
    if not deck.is_file():
        raise MeasurementError(
            f"no {variant} DRC deck at {deck} -- see sim/pdk.json for the pin "
            f"(install: volare enable --pdk sky130 <open_pdks_commit>)"
        )
    return deck


def parse_min_area_rules(deck_text: str) -> list[dict]:
    """Extract `[{symbol, rule, layer, datatype, min_area_um2}, ...]`.

    Both halves come out of the deck's own text: the layer number from the
    `mN_wildcard = "L/D"` assignment, the threshold and the rule name from the
    `mN.with_area(0..T).output("<rule>", ...)` call that implements it.
    """
    wildcards: dict[str, tuple[int, int]] = {}
    for sym in METAL_SYMBOLS:
        m = re.search(rf'^\s*{sym}_wildcard\s*=\s*"(\d+)/(\d+)"', deck_text, re.MULTILINE)
        if m:
            wildcards[sym] = (int(m.group(1)), int(m.group(2)))

    rules: list[dict] = []
    for sym in METAL_SYMBOLS:
        m = re.search(
            rf"^\s*{sym}\.with_area\(0\.\.([0-9.]+)\)\.output\(\s*\"([^\"]+)\"",
            deck_text,
            re.MULTILINE,
        )
        if not m:
            continue
        if sym not in wildcards:
            raise MeasurementError(
                f"deck declares a minimum-area rule for {sym} but no {sym}_wildcard layer"
            )
        layer, datatype = wildcards[sym]
        rules.append(
            {
                "symbol": sym,
                "rule": m.group(2),
                "layer": layer,
                "datatype": datatype,
                "min_area_um2": float(m.group(1)),
            }
        )
    if not rules:
        raise MeasurementError("no mN.with_area(...) minimum-area rules found in the deck")
    return rules


# --------------------------------------------------------------------------- #
# Measurement
# --------------------------------------------------------------------------- #
def measure_gds(gds_path: Path, rules: list[dict]) -> dict:
    """Apply every rule in `rules` to `gds_path`'s top cell."""
    try:
        import klayout.db as kdb
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise MeasurementError(
            "the `klayout` python module is not importable -- run this from "
            "this repo's own layout venv (layout/bin/setup-venv.sh):\n"
            "  layout/.venv/bin/python docs/chipalooza/measure_metal_min_area.py"
        ) from exc

    layout = kdb.Layout()
    layout.read(str(gds_path))
    dbu = layout.dbu
    tops = layout.top_cells()
    if len(tops) != 1:
        names = ", ".join(c.name for c in tops)
        raise MeasurementError(f"{gds_path}: expected exactly one top cell, found: {names}")
    top = tops[0]

    layers = []
    for rule in rules:
        li = layout.find_layer(rule["layer"], rule["datatype"])
        if li is None:
            # Layer absent from this GDS entirely: nothing drawn, nothing to
            # measure. (Kept as an explicit branch because `begin_shapes_rec`
            # cannot be called with a null layer index.)
            region = kdb.Region()
        else:
            # Build the region from the recursive iterator via the CONSTRUCTOR,
            # then strip user properties, and only then merge (issue #363).
            #
            # The obvious-looking `kdb.Region(); region.insert(iter)` form is
            # WRONG here and silently overstates every count this script
            # reports. `Region#insert(RecursiveShapeIterator)` carries each
            # shape's GDS user properties into the region, and KLayout's merge
            # is property-AWARE: two polygons whose property sets differ are
            # never merged with each other, and `Region#area` then counts the
            # overlap twice. That is exactly the shape of this repo's routed
            # GDS, where the DEF->GDS merge attaches a net-name property
            # (`[[1, "VPWR"]]`, `[[1, "VGND"]]`) to each PDN strap while the
            # generated via cells sitting *inside* those straps carry none --
            # so a 1.42 x 1.60 um met5 via pad fully covered by a >130 um^2
            # strap on the same layer was reported as a standalone `m5.4`
            # violation. Measured on
            # `layout/sar-adc-top/reports/20260924-190817-f3622fc/sar_adc_top.gds`,
            # layer 72/20: the `insert()` form yields 24 polygons / 1058.75
            # um^2, the constructor form 5 polygons / 896.09 um^2 -- and a
            # correctly merged region's area IS its union area, so the larger
            # number is the double count, not the smaller one the loss.
            #
            # A DRC deck's own `polygons(...)` input is plain drawn geometry
            # with no property semantics, so dropping properties is what makes
            # this measurement agree with the rule it stands in for. The
            # `Region(iter)` constructor already drops them today; the explicit
            # `remove_properties()` states the requirement rather than relying
            # on that, and is a no-op when it already holds.
            region = kdb.Region(top.begin_shapes_rec(li))
            region.remove_properties()
        region.merge()
        # `Region#with_area` is the exact primitive the deck's own rule text
        # calls. Region coordinates are integer DBU, so the um^2 threshold is
        # converted to DBU^2 here (dbu is 0.001 um for every GDS in this repo,
        # making every threshold an exact integer, but the rounding keeps this
        # correct on any dbu).
        max_area_dbu2 = round(rule["min_area_um2"] / (dbu * dbu))
        below = region.with_area(0, max_area_dbu2, False)

        shapes = []
        for poly in below.each():
            box = poly.bbox()
            shapes.append(
                {
                    "area_um2": poly.area() * dbu * dbu,
                    "bbox_um": [
                        box.left * dbu,
                        box.bottom * dbu,
                        box.right * dbu,
                        box.top * dbu,
                    ],
                    "width_um": box.width() * dbu,
                    "height_um": box.height() * dbu,
                }
            )
        shapes.sort(key=lambda s: (s["area_um2"], s["bbox_um"]))
        layers.append(
            {
                "rule": rule["rule"],
                "symbol": rule["symbol"],
                "layer": rule["layer"],
                "datatype": rule["datatype"],
                "min_area_um2": rule["min_area_um2"],
                "merged_polygons": region.count(),
                "below_min_area": len(shapes),
                "shapes": shapes,
            }
        )

    return {
        "gds": str(gds_path),
        "top_cell": top.name,
        "dbu_um": dbu,
        "layers": layers,
        "total_below_min_area": sum(layer["below_min_area"] for layer in layers),
    }


# --------------------------------------------------------------------------- #
# Target resolution
# --------------------------------------------------------------------------- #
def resolve_default_targets(repo_root: Path) -> list[tuple[str, Path]]:
    """Resolve each `DEFAULT_TARGETS` entry through its flow's `reports/LATEST`."""
    targets: list[tuple[str, Path]] = []
    for label, flow_dir, gds_name in DEFAULT_TARGETS:
        pointer = repo_root / flow_dir / "reports" / "LATEST"
        if not pointer.is_file():
            raise MeasurementError(f"no reports/LATEST pointer at {pointer}")
        record = pointer.read_text().strip()
        gds = repo_root / flow_dir / "reports" / record / gds_name
        if not gds.is_file():
            raise MeasurementError(f"{pointer} -> {record}, but no {gds_name} in that record")
        targets.append((f"{label} [{record}]", gds))
    return targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure sky130A's met1-met5 minimum-area rules against a GDS."
    )
    parser.add_argument("gds", nargs="*", type=Path, help="GDS files to measure")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--pdk-root", type=Path, default=None)
    parser.add_argument("--variant", default=None)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repo root used to resolve the default targets",
    )
    args = parser.parse_args(argv)

    try:
        pdk_root = args.pdk_root or Path(os.environ.get("PDK_ROOT", "~/.volare")).expanduser()
        variant = args.variant or os.environ.get("PDK", "sky130A")
        deck = find_deck(Path(pdk_root).expanduser(), variant)
        rules = parse_min_area_rules(deck.read_text())

        if args.gds:
            targets = [(str(p), p) for p in args.gds]
            for _, path in targets:
                if not path.is_file():
                    raise MeasurementError(f"no such GDS: {path}")
        else:
            targets = resolve_default_targets(args.repo_root.resolve())

        results = [dict(measure_gds(path, rules), label=label) for label, path in targets]
    except MeasurementError as exc:
        print(f"measure_metal_min_area.py: {exc}", file=sys.stderr)
        return 2

    total = sum(r["total_below_min_area"] for r in results)

    if args.json:
        print(
            json.dumps(
                {
                    "pdk": {"root": str(pdk_root), "variant": variant, "deck": str(deck)},
                    "rules": rules,
                    "results": results,
                    "total_below_min_area": total,
                },
                indent=2,
            )
        )
        return 0 if total == 0 else 1

    print(f"PDK deck: {deck}")
    for result in results:
        print(f"\n{result['label']}")
        print(f"  GDS:  {result['gds']}  (top cell {result['top_cell']})")
        for layer in result["layers"]:
            print(
                f"  {layer['rule']:<8} {layer['symbol']} "
                f"({layer['layer']}/{layer['datatype']}): "
                f"{layer['merged_polygons']} merged polygons, "
                f"{layer['below_min_area']} below {layer['min_area_um2']} um2"
            )
            for shape in layer["shapes"]:
                x0, y0, x1, y1 = shape["bbox_um"]
                print(
                    f"      area {shape['area_um2']:.4f} um2  "
                    f"bbox ({x0:.3f}, {y0:.3f}) - ({x1:.3f}, {y1:.3f})  "
                    f"{shape['width_um']:.3f} x {shape['height_um']:.3f} um"
                )
        print(f"  subtotal: {result['total_below_min_area']} shape(s) below minimum area")

    print(f"\nTOTAL: {total} shape(s) below their metal's minimum area")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

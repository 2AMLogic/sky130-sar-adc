"""Regression tests for docs/chipalooza/measure_metal_min_area.py (issue #363).

WHAT IS PINNED HERE
-------------------
The script under test builds a KLayout `Region` from a recursive shape
iterator and merges it before applying the PDK's own `Region#with_area`
threshold. Until issue #363 it built that region as::

    region = kdb.Region()
    region.insert(top.begin_shapes_rec(li))
    region.merge()

which **under-merges**. `Region#insert(RecursiveShapeIterator)` carries each
shape's GDS user properties into the region, and KLayout's merge is
property-aware: polygons whose property sets differ are never merged with each
other, and `Region#area` counts their overlap twice. In this repo's routed
GDS the DEF->GDS merge attaches a net-name property (`[[1, "VPWR"]]`) to every
PDN strap while the generated via cells sitting *inside* those straps carry
none -- so fully-covered via pads were reported as standalone minimum-area
violations, and the composed top-level record's "145 residual shapes" figure
(and issue #333's waiver, written against it) were artifacts of that.

These tests therefore assert the two constructions **on a fixture where they
differ**, which is the acceptance criterion issue #363 states: a test that only
checked the fixed construction in isolation could not tell the bug from the fix.

`test_isolated_shape_is_still_reported` is the anti-vacuity half: the fixed
construction must still flag a genuinely isolated sub-threshold shape. A
"measurement" that merged everything into silence would pass the first test and
fail this one.

WHY THIS FILE LIVES UNDER sim/tests/
------------------------------------
Same reason as `sim/tests/test_proposal_citations.py`: `sim/tests/` is this
repo's only unittest root (`npm run test:unit` discovers from there), not
because the script belongs to the simulation harness.

RUNNING IT
----------
Needs the `klayout` Python module -- but, unlike the script itself, **no PDK**:
the rule table is supplied inline instead of being read out of `sky130A_mr.drc`,
and the GDS is synthesised in a temp dir. CI's headless `checks` job installs
the pinned engine into a throwaway venv and runs exactly this module (see
`.github/workflows/ci.yml`); `npm run test:unit`'s klayout-free interpreter
skips it. Locally, either of these works::

    layout/.venv/bin/python -m unittest discover -s sim/tests -t sim/tests \\
        -p 'test_measure_metal_min_area.py' -v
    python3 -m unittest discover -s sim/tests -t sim/tests   # skips this module
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
CHIPALOOZA_DIR = REPO_ROOT / "docs" / "chipalooza"
sys.path.insert(0, str(CHIPALOOZA_DIR))

import measure_metal_min_area as measurer  # noqa: E402

try:  # the module under test imports klayout lazily, so this import is safe
    import klayout.db as kdb
except ImportError:  # pragma: no cover - environment-dependent
    kdb = None


#: met5 / `m5.4` (4.0 um^2) stands in for the whole rule family: it is the
#: layer where the under-merge was found, and its threshold is coarse enough
#: that the fixture's numbers are readable by eye.
LAYER, DATATYPE = 72, 20
MIN_AREA_UM2 = 4.0
DBU = 0.001

#: Same shape as `parse_min_area_rules()`'s output, supplied inline so this
#: test needs no PDK install. The real rule table is still READ from the deck
#: at runtime -- that path is exercised by running the script itself.
RULES = [
    {
        "symbol": "m5",
        "rule": "m5.4",
        "layer": LAYER,
        "datatype": DATATYPE,
        "min_area_um2": MIN_AREA_UM2,
    }
]

#: 1.42 x 1.60 um = 2.272 um^2 -- the exact via-cell footprint
#: (`VIA_via5_6_1600_1600_1_1_1600_1600`) the buggy measurement reported as an
#: `m5.4` violation, and 57% of the 4.0 um^2 threshold standing alone.
VIA_W_DBU, VIA_H_DBU = 1420, 1600
VIA_AREA_UM2 = 2.272

#: A 40 x 1.6 um strap = 64.0 um^2, 16x the threshold, carrying a net-name
#: property exactly as the DEF->GDS merge attaches one to a PDN strap.
STRAP_X0_DBU, STRAP_X1_DBU = -10000, 30000
STRAP_AREA_UM2 = 64.0


def _build_fixture(directory: Path, *, covered: bool) -> Path:
    """Write a two-cell GDS: a via cell inside (or beside) a property-bearing strap.

    `covered=True` places the sub-threshold via pad wholly inside a strap on
    the same layer, so correct merged geometry has exactly one polygon, well
    over threshold. `covered=False` omits the strap, leaving the pad isolated
    and genuinely in violation.
    """
    layout = kdb.Layout()
    layout.dbu = DBU
    li = layout.layer(LAYER, DATATYPE)

    via = layout.create_cell("via_cell")
    via.shapes(li).insert(kdb.Box(0, 0, VIA_W_DBU, VIA_H_DBU))

    top = layout.create_cell("fixture_top")
    if covered:
        # The property is the whole point: without it the two shapes merge
        # even under the buggy construction and the fixture proves nothing.
        prop_id = layout.properties_id([[1, "VPWR"]])
        top.shapes(li).insert(kdb.Box(STRAP_X0_DBU, 0, STRAP_X1_DBU, VIA_H_DBU), prop_id)
    # Instantiated, not drawn flat, so `begin_shapes_rec` is what resolves it.
    top.insert(kdb.CellInstArray(via, kdb.Trans(kdb.Vector(1000, 0))))

    path = directory / ("covered.gds" if covered else "isolated.gds")
    layout.write(str(path))
    return path


def _measure_both_ways(gds_path: Path) -> dict:
    """Return the merged polygon count / area / below-threshold count for both
    region constructions: the pre-#363 `insert()` form and the fixed one."""
    layout = kdb.Layout()
    layout.read(str(gds_path))
    top = layout.top_cells()[0]
    li = layout.find_layer(LAYER, DATATYPE)
    scale = layout.dbu * layout.dbu
    max_area_dbu2 = round(MIN_AREA_UM2 / scale)

    buggy = kdb.Region()
    buggy.insert(top.begin_shapes_rec(li))
    buggy.merge()

    fixed = kdb.Region(top.begin_shapes_rec(li))
    fixed.remove_properties()
    fixed.merge()

    return {
        name: {
            "polygons": region.count(),
            "area_um2": round(region.area() * scale, 6),
            "below": region.with_area(0, max_area_dbu2, False).count(),
        }
        for name, region in (("buggy", buggy), ("fixed", fixed))
    }


@unittest.skipIf(kdb is None, "the `klayout` python module is not importable")
class RegionConstructionTest(unittest.TestCase):
    """The two constructions, pinned against a fixture where they disagree."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmpdir = Path(tmp.name)

    def test_constructions_disagree_on_a_covered_sub_threshold_shape(self):
        """The fixture must reproduce the defect, or it pins nothing."""
        measured = _measure_both_ways(_build_fixture(self.tmpdir, covered=True))

        # Pre-#363: the property-bearing strap and the property-less via pad
        # stay two polygons, their overlap is double-counted in the area, and
        # the pad is reported as a standalone m5.4 violation.
        self.assertEqual(measured["buggy"]["polygons"], 2)
        self.assertAlmostEqual(
            measured["buggy"]["area_um2"], STRAP_AREA_UM2 + VIA_AREA_UM2, places=6
        )
        self.assertEqual(measured["buggy"]["below"], 1)

        # Fixed: one polygon, union area (NOT the sum -- the pad is inside the
        # strap, so a correctly merged region's area is the strap's alone),
        # nothing below threshold.
        self.assertEqual(measured["fixed"]["polygons"], 1)
        self.assertAlmostEqual(measured["fixed"]["area_um2"], STRAP_AREA_UM2, places=6)
        self.assertEqual(measured["fixed"]["below"], 0)

        # Stated as the invariant rather than only as two literals: a merged
        # region's area IS its union area, so the construction reporting MORE
        # area over the same drawn shapes is the one that failed to merge.
        self.assertGreater(measured["buggy"]["area_um2"], measured["fixed"]["area_um2"])

    def test_script_reports_the_covered_shape_as_clear(self):
        """`measure_gds()` itself -- not a re-implementation -- must agree."""
        result = measurer.measure_gds(_build_fixture(self.tmpdir, covered=True), RULES)

        self.assertEqual(result["top_cell"], "fixture_top")
        self.assertEqual(result["total_below_min_area"], 0)
        (layer,) = result["layers"]
        self.assertEqual(layer["rule"], "m5.4")
        self.assertEqual(layer["merged_polygons"], 1)
        self.assertEqual(layer["below_min_area"], 0)
        self.assertEqual(layer["shapes"], [])

    def test_isolated_shape_is_still_reported(self):
        """Anti-vacuity: the fixed construction must still catch a real violation."""
        measured = _measure_both_ways(_build_fixture(self.tmpdir, covered=False))
        self.assertEqual(measured["fixed"]["polygons"], 1)
        self.assertEqual(measured["fixed"]["below"], 1)

        result = measurer.measure_gds(_build_fixture(self.tmpdir, covered=False), RULES)
        self.assertEqual(result["total_below_min_area"], 1)
        (layer,) = result["layers"]
        self.assertEqual(layer["below_min_area"], 1)
        (shape,) = layer["shapes"]
        self.assertAlmostEqual(shape["area_um2"], VIA_AREA_UM2, places=6)
        self.assertAlmostEqual(shape["width_um"], VIA_W_DBU * DBU, places=6)
        self.assertAlmostEqual(shape["height_um"], VIA_H_DBU * DBU, places=6)

    def test_absent_layer_measures_as_empty(self):
        """The `li is None` guard survives the region-construction change."""
        absent = [dict(RULES[0], layer=99, datatype=99, rule="unused")]
        result = measurer.measure_gds(_build_fixture(self.tmpdir, covered=True), absent)

        (layer,) = result["layers"]
        self.assertEqual(layer["merged_polygons"], 0)
        self.assertEqual(layer["below_min_area"], 0)
        self.assertEqual(result["total_below_min_area"], 0)


class RuleParsingTest(unittest.TestCase):
    """PDK-free, klayout-free: the rule table is read, never transcribed."""

    def test_layer_and_threshold_come_from_the_deck_text(self):
        deck = "\n".join(
            [
                'm5_wildcard = "72/20"',
                "m5 = polygons(72, 20)",
                'm5.with_area(0..4.0).output("m5.4", "m5.4 : min. m5 area : 4.0um^2")',
            ]
        )
        (rule,) = measurer.parse_min_area_rules(deck)
        self.assertEqual(rule["symbol"], "m5")
        self.assertEqual(rule["rule"], "m5.4")
        self.assertEqual((rule["layer"], rule["datatype"]), (LAYER, DATATYPE))
        self.assertEqual(rule["min_area_um2"], MIN_AREA_UM2)

    def test_area_rule_without_a_layer_assignment_is_an_error(self):
        deck = 'm5.with_area(0..4.0).output("m5.4", "m5.4 : min. m5 area : 4.0um^2")'
        with self.assertRaises(measurer.MeasurementError):
            measurer.parse_min_area_rules(deck)


if __name__ == "__main__":
    unittest.main()

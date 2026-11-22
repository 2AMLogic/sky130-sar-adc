"""Behaviour pins for the three emitters `layout/bin/` shares across blocks:
`_geometry_common.step_down_to_met1()`,
`_geometry_common.floorplan_pfet_well_islands()` and
`_pfet_devices.mos_array_params()`.

WHY THIS FILE EXISTS
--------------------
`layout/halflsb-offset/` needed two things `layout/sampling-frontend/` had
already worked out: the "walk a generator port down to met1" via-stack emitter
(three layer cases, each with a DRC finding behind it) and the `klt gen
mos_array` parameter dict this repo draws an unmatched single-finger FET with.
Issue #495 lifted both into `layout/bin/` but left sampling-frontend's own
byte-identical copies in place, because their output is the drawn geometry
behind that flow's committed, append-only DRC-clean / LVS-match record. While
both copies existed, this module's job was to drive them over the same inputs
and assert identical output, so a divergence was a test failure rather than a
silent difference between two blocks' geometry.

Issue #845 folded those copies in once sampling-frontend had re-run, and the
equivalence tests went with them -- they had already done their job, proving
the fold-in a no-op for drawn geometry. What this module pins now is the
surviving shared emitters' **own** output: the exact shape list each layer case
emits and the exact parameter dict, not "equal to a second copy of itself".
Both flows' committed records were minted against these exact values, so a
change here changes drawn geometry in two blocks at once and must be a
deliberate, re-recorded one.

Issue #909 added the third: the Row-1 PFET n-well island floorplan, which
`layout/sampling-frontend-wells/` and `layout/sampling-frontend/` carried as
two byte-identical copies (differing only in the function name, the docstring,
and whether the shared device table was spelled `PFET_DEVICES` or aliased to
`DEVICES`). Following the discipline above, what is pinned here is that one
surviving plan's **own** output -- the block origins, island rectangles and
tap rectangles it computes -- driven from each flow's own committed `klt gen`
block bboxes, and asserted against the island/tap geometry each flow's own
committed summary document carries. Not two copies against each other.

Pure stdlib -- no PDK, no KLayout, no `klt` -- so it belongs to the headless tier
(`npm run test:unit` standalone; reached in CI through `check:ci` ->
`npm run check:harness` -> `sim/selftest.sh` stage 1, in the "Repo checks
(headless, no PDK)" job), the same convention
`sim/tests/test_layout_entrypoint_imports.py` follows.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LAYOUT_BIN = REPO_ROOT / "layout" / "bin"

sys.path.insert(0, str(LAYOUT_BIN))

import _geometry_common as geometry_common  # noqa: E402
import _pfet_devices as pfet_devices  # noqa: E402

#: The probe point every layer case below is emitted at. Arbitrary, but fixed:
#: the expected shape lists are stated in absolute um, so moving it would
#: invalidate all of them at once.
PROBE_X, PROBE_Y = 1.449, 6.449

#: Every layer case `step_down_to_met1()` handles, as
#: `(label, layer, direction, met4_escape_y, expected_xy, expected_shapes)`.
#: `expected_shapes` is `(layer, rect.as_um())` in emission order -- the drawn
#: geometry itself, in the composed frame, exactly as both consumers' committed
#: records carry it. Layers are named from the shared module's own constants, so
#: a renumbered layer moves the table with it rather than going stale.
LAYER_CASES = (
    (
        "li1 (mos_array S/G/D)",
        geometry_common.L_LI1,
        180.0,
        None,
        (1.449, 6.449),
        (
            # One mcon reaches met1 directly; the port is already on li1.
            (geometry_common.L_MCON, [1.364, 6.364, 1.534, 6.534]),
        ),
    ),
    (
        "met3 (cap_array *_BOT, facing -x)",
        geometry_common.L_MET3,
        180.0,
        None,
        # direction 180 shifts the via MET3_VIA_INSET_UM into the plate, so the
        # effective x the caller jogs from moves with it.
        (1.649, 6.449),
        (
            (geometry_common.L_MET2, [1.439, 6.239, 1.859, 6.659]),
            (geometry_common.L_VIA2, [1.549, 6.349, 1.749, 6.549]),
            (geometry_common.L_MET1, [1.489, 6.289, 1.809, 6.609]),
            (geometry_common.L_VIA1, [1.574, 6.374, 1.724, 6.524]),
        ),
    ),
    (
        "met3 (cap_array *_BOT, facing +x)",
        geometry_common.L_MET3,
        0.0,
        None,
        (1.449, 6.449),
        (
            (geometry_common.L_MET2, [1.239, 6.239, 1.659, 6.659]),
            (geometry_common.L_VIA2, [1.349, 6.349, 1.549, 6.549]),
            (geometry_common.L_MET1, [1.289, 6.289, 1.609, 6.609]),
            (geometry_common.L_VIA1, [1.374, 6.374, 1.524, 6.524]),
        ),
    ),
    (
        "met4 (cap_array *_TOP)",
        geometry_common.L_MET4,
        90.0,
        9.62,
        # The met4 riser escapes the cell footprint first, so the effective y
        # the caller routes from is the escape y, not the port's own.
        (1.449, 9.62),
        (
            (geometry_common.L_MET4, [1.299, 6.299, 1.599, 9.77]),
            (geometry_common.L_MET4, [1.239, 9.41, 1.659, 9.83]),
            # MET3_ISLAND_PAD_UM, not STACK_PAD_UM: this pad is the only met3
            # shape at its own (x, y), so it must clear m3.6 alone (issue #326).
            (geometry_common.L_MET3, [1.199, 9.37, 1.699, 9.87]),
            (geometry_common.L_VIA3, [1.349, 9.52, 1.549, 9.72]),
            (geometry_common.L_MET2, [1.239, 9.41, 1.659, 9.83]),
            (geometry_common.L_VIA2, [1.349, 9.52, 1.549, 9.72]),
            (geometry_common.L_MET1, [1.289, 9.46, 1.609, 9.78]),
            (geometry_common.L_VIA1, [1.374, 9.545, 1.524, 9.695]),
        ),
    ),
)


class TestStepDownToMet1(unittest.TestCase):
    """The shared via-stack emitter's own drawn output and error cases."""

    def test_every_layer_case_emits_the_recorded_shapes(self):
        for label, layer, direction, escape_y, expected_xy, expected in LAYER_CASES:
            with self.subTest(case=label):
                shapes: list = []
                xy = geometry_common.step_down_to_met1(
                    shapes, PROBE_X, PROBE_Y, layer, direction, met4_escape_y=escape_y
                )
                self.assertEqual(expected_xy, xy)
                self.assertEqual(
                    [list(pair) for pair in expected],
                    [[lay, rect.as_um()] for lay, rect in shapes],
                    f"{label}: this emitter draws the geometry of every block "
                    "that calls it, and each one's committed record was minted "
                    "against these shapes -- if the change is intended, re-run "
                    "those flows and record the new geometry rather than just "
                    "updating this table",
                )

    def test_met4_case_requires_an_escape_y(self):
        with self.assertRaises(geometry_common.BuildError):
            geometry_common.step_down_to_met1(
                [], 1.0, 1.0, geometry_common.L_MET4, 90.0
            )

    def test_unknown_layer_raises(self):
        with self.assertRaises(geometry_common.BuildError):
            geometry_common.step_down_to_met1([], 1.0, 1.0, (12345, 67), 90.0)


class TestMosArrayParams(unittest.TestCase):
    """`_pfet_devices`' shared `klt gen mos_array` parameter dict."""

    def test_shared_emitter_dict_is_pinned_exactly(self):
        """The dict itself.

        Changing it would change what every full-custom block in `layout/`
        generates, and every committed record was minted against this exact
        dict.
        """
        self.assertEqual(
            pfet_devices.mos_array_params("pfet", 2.0, 0.15),
            {
                "w_um": 2.0,
                "l_um": 0.15,
                "fingers": 1,
                "rows": 1,
                "cols": 1,
                "dummy": 0,
                "flavor": "pfet",
                "gate_contact": True,
            },
        )

    def test_flavor_wrappers_only_set_the_flavor(self):
        """`pfet_params`/`nfet_params` are the names the block generators call;
        each must be exactly `mos_array_params` with its flavor pinned."""
        for w_um, l_um in ((1.0, 0.15), (2.0, 0.15), (16.0, 0.15), (1.0, 0.5)):
            with self.subTest(w=w_um, l=l_um):
                self.assertEqual(
                    pfet_devices.mos_array_params("pfet", w_um, l_um),
                    pfet_devices.pfet_params(w_um, l_um),
                )
                self.assertEqual(
                    pfet_devices.mos_array_params("nfet", w_um, l_um),
                    pfet_devices.nfet_params(w_um, l_um),
                )

    def test_unknown_flavor_raises(self):
        with self.assertRaises(ValueError):
            pfet_devices.mos_array_params("bjt", 1.0, 0.15)



#: Every Row-1 PFET block's own `klt gen` bbox as the named flow's committed
#: record reports it, transcribed from that record's own per-block `klt gen`
#: report (`<block id>.json` -> ``bbox_um``): ``{block id: (x1, y1)}``. ``x1`` and ``y1`` are the only bbox
#: fields the floorplan reads (the island's right edge and its top), so a
#: fixture carrying just those exercises every input the plan has.
#:
#: The two flows' blocks were generated by DIFFERENT `klt` versions, so the
#: same nine devices come back 0.30 um shorter in the older record -- which is
#: exactly why both are pinned below rather than one standing in for both. The
#: resulting 0.30 um difference in each island's own top edge is an **input**
#: difference between the two records, not a difference between the two copies
#: this fold-in merged: the plan itself is one function and both flows' island
#: x ranges and tap rectangles come out identical.
SF_BLOCK_BBOX = {
    "sa_p": (1.49, 1.97),
    "se_p": (1.24, 1.97),
    "scp_p": (1.24, 1.97),
    "cmswp_p": (1.24, 16.97),
    "invp": (1.24, 2.97),
    "cmswp_n": (1.24, 16.97),
    "scp_n": (1.24, 1.97),
    "se_n": (1.24, 1.97),
    "sa_n": (1.49, 1.97),
}
WELLS_BLOCK_BBOX = {
    "sa_p": (1.49, 2.27),
    "se_p": (1.24, 2.27),
    "scp_p": (1.24, 2.27),
    "cmswp_p": (1.24, 17.27),
    "invp": (1.24, 3.27),
    "cmswp_n": (1.24, 17.27),
    "scp_n": (1.24, 2.27),
    "se_n": (1.24, 2.27),
    "sa_n": (1.49, 2.27),
}

#: Drawn n-well island separation. Both consumers keep their own
#: `WELL_GAP_UM` at this value and pass it in -- it is deliberately NOT a
#: constant of the shared module (three readers per flow), so this table
#: states it the same way a consumer does.
WELL_GAP_UM = 1.60

#: The placement the plan computes, block id -> origin, in placement order.
#: Identical for both flows (every block's own ``x1`` agrees between the two
#: records, and the pitch is the same shared constant). The trailing-digit
#: values are the exact accumulated floats, not tidied ones: they are what
#: both flows' committed `klt gen-compose` requests carry.
EXPECTED_ORIGINS = {
    "sa_p": {"x": 2.0, "y": 0.0},
    "se_p": {"x": 5.2, "y": 0.0},
    "scp_p": {"x": 10.34, "y": 0.0},
    "cmswp_p": {"x": 13.54, "y": 0.0},
    "invp": {"x": 16.74, "y": 0.0},
    "cmswp_n": {"x": 19.939999999999998, "y": 0.0},
    "scp_n": {"x": 23.139999999999997, "y": 0.0},
    "se_n": {"x": 28.279999999999998, "y": 0.0},
    "sa_n": {"x": 31.479999999999997, "y": 0.0},
}


def _domains(island_tops: tuple[float, float, float]) -> list[dict]:
    """The three islands, parameterised only by their own top edges.

    Everything else -- ids, tap nets, members, island x ranges, tap
    rectangles, island y0 -- is identical between the two flows' committed
    records, so stating the tops is the whole difference.
    """
    top_p, top_vdd, top_n = island_tops
    return [
        {
            "id": "boost_p",
            "net": "BOOST_P",
            "members": ["sa_p", "se_p"],
            "well": {"x0": 0.0, "y0": -2.4, "x1": 6.74, "y1": top_p},
            "tap": {"x0": 0.4, "x1": 1.0, "y0": -1.8, "y1": -0.6},
        },
        {
            "id": "vdd",
            "net": "VDD",
            "members": ["scp_p", "cmswp_p", "invp", "cmswp_n", "scp_n"],
            "well": {
                "x0": 8.34,
                "y0": -2.4,
                "x1": 24.679999999999996,
                "y1": top_vdd,
            },
            "tap": {"x0": 8.74, "x1": 9.34, "y0": -1.8, "y1": -0.6},
        },
        {
            "id": "boost_n",
            "net": "BOOST_N",
            "members": ["se_n", "sa_n"],
            "well": {
                "x0": 26.279999999999998,
                "y0": -2.4,
                "x1": 33.269999999999996,
                "y1": top_n,
            },
            "tap": {
                "x0": 26.679999999999996,
                "x1": 27.279999999999998,
                "y0": -1.8,
                "y1": -0.6,
            },
        },
    ]


#: One case per consuming flow: `(label, record, bboxes, expected domains)`.
#: Each island top is that flow's own tallest member plus WELL_ABOVE_UM
#: (0.40), and matches the `well_um` the named record's own summary document
#: carries, to that document's own 3-decimal rounding.
FLOORPLAN_CASES = (
    (
        "sampling-frontend (Row 1)",
        "20261027-183401-b96026c2",
        SF_BLOCK_BBOX,
        _domains((2.37, 17.369999999999997, 2.37)),
    ),
    (
        "sampling-frontend-wells",
        "20261105-191510-bf27ff9d",
        WELLS_BLOCK_BBOX,
        _domains((2.67, 17.669999999999998, 2.67)),
    ),
)


class TestFloorplanPfetWellIslands(unittest.TestCase):
    """The shared Row-1 n-well island plan's own computed placement."""

    @staticmethod
    def _blocks(bboxes: dict) -> dict:
        return {
            bid: {"bbox": {"x1": x1, "y1": y1}} for bid, (x1, y1) in bboxes.items()
        }

    def _plan(self, bboxes: dict):
        return geometry_common.floorplan_pfet_well_islands(
            self._blocks(bboxes),
            pfet_devices.PFET_DEVICES,
            pfet_devices.DOMAIN_TAP_NET,
            WELL_GAP_UM,
        )

    def test_each_flow_gets_its_recorded_islands_and_origins(self):
        for label, record, bboxes, expected_domains in FLOORPLAN_CASES:
            with self.subTest(case=label):
                origins, domains = self._plan(bboxes)
                self.assertEqual(
                    EXPECTED_ORIGINS,
                    origins,
                    f"{label}: this plan places the devices of every block "
                    f"that calls it, and record {record} was minted against "
                    "these origins -- if the change is intended, re-run that "
                    "flow and record the new geometry rather than just "
                    "updating this table",
                )
                self.assertEqual(
                    expected_domains,
                    domains,
                    f"{label}: record {record}'s own summary document carries "
                    "these island and tap rectangles; changing them changes "
                    "drawn geometry and needs a re-run, not a table edit",
                )

    def test_blocks_are_placed_in_device_table_order(self):
        """Placement order is the shared table's order, not a sorted one.

        A domain is only a single n-well rectangle because all of one
        domain's devices are adjacent in `PFET_DEVICES` -- so the order the
        plan emits origins in is part of its contract, not an accident of
        dict iteration.
        """
        origins, domains = self._plan(SF_BLOCK_BBOX)
        self.assertEqual([row[0] for row in pfet_devices.PFET_DEVICES], list(origins))
        self.assertEqual(
            ["boost_p", "vdd", "boost_n"],
            [d["id"] for d in domains],
            "islands come out in the table's own left-to-right domain order",
        )

    def test_well_gap_is_the_argument_not_a_shared_constant(self):
        """`well_gap_um` stays each consumer's own constant (three readers
        there) and reaches the plan only as an argument -- so widening it in
        the call must move every island after the first, and nothing in the
        shared module may override it."""
        _, narrow = self._plan(SF_BLOCK_BBOX)
        wide = geometry_common.floorplan_pfet_well_islands(
            self._blocks(SF_BLOCK_BBOX),
            pfet_devices.PFET_DEVICES,
            pfet_devices.DOMAIN_TAP_NET,
            WELL_GAP_UM + 1.0,
        )[1]
        self.assertEqual(narrow[0]["well"]["x0"], wide[0]["well"]["x0"])
        for i in (1, 2):
            self.assertAlmostEqual(
                narrow[i]["well"]["x0"] + i * 1.0, wide[i]["well"]["x0"], places=9
            )
        self.assertFalse(
            hasattr(geometry_common, "WELL_GAP_UM"),
            "WELL_GAP_UM is deliberately NOT a constant of the shared module "
            "-- each consumer has three readers of its own copy, the same "
            "retention WIRE_UM records",
        )

    def test_plan_output_passes_the_shared_isolation_check(self):
        """The plan and `_assert_well_isolation` are each other's counterpart:
        the plan's own `domains` must be exactly what that check accepts at
        the same gap it was planned with."""
        for label, _record, bboxes, _expected in FLOORPLAN_CASES:
            with self.subTest(case=label):
                _, domains = self._plan(bboxes)
                geometry_common._assert_well_isolation(domains, WELL_GAP_UM)
                with self.assertRaises(geometry_common.BuildError):
                    geometry_common._assert_well_isolation(
                        domains, WELL_GAP_UM + 0.01
                    )


if __name__ == "__main__":
    unittest.main()

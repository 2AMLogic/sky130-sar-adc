"""Behaviour pins for what `layout/bin/` shares across blocks:
`_geometry_common.step_down_to_met1()`,
`_geometry_common.floorplan_pfet_well_islands()`,
`_pfet_devices.mos_array_params()`, and -- since issue #1109 -- the `klt`
request/report plumbing every full-custom sub-block `build_layout.py` builds
its documents with (`load_block`, `draw_request`, `compose_request`,
`summarize_pfet_domains`, `write_build_artifacts`).

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

Issue #1109 added the fourth group. The four sub-block scripts each
hand-rolled the same `klt gen` block-report reader, `klt draw` request,
`klt gen-compose` explicit-placement request, Row-1 n-well domain summary and
`main()` write-and-report step; nothing flagged when a copy drifted, because
nothing compared the copies. Those five are now `_geometry_common` helpers,
and what is pinned here is, first, each helper's own document -- key order
included, since `json.dumps` writes keys in insertion order and the flows'
request files are compared as bytes -- and second, the gate that matters: each
of the four scripts, run the way its `run-flow.sh` runs it against a COPY of
its committed `reports/LATEST` record, must rewrite that record's
`draw.request.json`, `compose.request.json` and summary byte-for-byte. A
third class reads the four source trees and pins that the local copies are
gone and the shared helpers are what they call; byte-identity alone would
pass just as well with every copy still in place.

Pure stdlib -- no PDK, no KLayout, no `klt` -- so it belongs to the headless tier
(`npm run test:unit` standalone; reached in CI through `check:ci` ->
`npm run check:harness` -> `sim/selftest.sh` stage 1, in the "Repo checks
(headless, no PDK)" job), the same convention
`sim/tests/test_layout_entrypoint_imports.py` follows.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import difflib
import io
import itertools
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar

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


# =========================================================================== #
# Issue #1109: the `klt` request/report plumbing shared by all four sub-block
# `build_layout.py` scripts
# =========================================================================== #

#: Every full-custom sub-block whose `build_layout.py` hands `klt` two request
#: documents, as `(block, name its own summary is written under)`. The summary
#: is the third file `main()` leaves in its record directory beside
#: `draw.request.json` and `compose.request.json`, and the only one whose name
#: differs between flows. `layout/sar-adc-top/` is deliberately absent: it
#: places prebuilt library cells rather than `<block>.json` generator reports
#: and writes four artifacts of its own, so it shares none of this.
SUB_BLOCKS = (
    ("comparator", "route.summary.json"),
    ("halflsb-offset", "layout.summary.json"),
    ("sampling-frontend", "layout.summary.json"),
    ("sampling-frontend-wells", "wells.summary.json"),
)

#: The two request documents every one of those flows writes under fixed names.
REQUEST_DOCUMENTS = ("draw.request.json", "compose.request.json")

#: Which module-level function of each sub-block script calls each shared
#: helper, as `{block: {helper: caller}}`. This is the shape the
#: consolidation states: the documents are built in `build()` and written in
#: `main()`. `load_block` belongs to the three flows that place `klt gen`
#: blocks from their reports -- `comparator` keeps its own `load_ports()`,
#: which hands its greedy router four-field port tuples instead -- and only
#: `sampling-frontend{,-wells}` carry Row-1 n-well domains to summarise.
HELPER_CALLERS = {
    "comparator": {
        "draw_request": "build",
        "compose_request": "build",
        "write_build_artifacts": "main",
    },
    "halflsb-offset": {
        "load_block": "build",
        "draw_request": "build",
        "compose_request": "build",
        "write_build_artifacts": "main",
    },
    "sampling-frontend": {
        "load_block": "build",
        "draw_request": "build",
        "compose_request": "build",
        "summarize_pfet_domains": "build",
        "write_build_artifacts": "main",
    },
    "sampling-frontend-wells": {
        "load_block": "build",
        "draw_request": "build",
        "compose_request": "build",
        "summarize_pfet_domains": "build",
        "write_build_artifacts": "main",
    },
}

#: Executed by a fresh interpreter, one per sub-block; argv is that block's
#: `bin/build_layout.py` and a scratch copy of its record directory. Sets up
#: the same two-line `sys.path` prelude the script sets up for itself and runs
#: it as `__main__`, which is exactly what `run-flow.sh` does. A process
#: apiece for the reason `sim/tests/test_layout_entrypoint_imports.py`
#: records: several blocks under `layout/` carry a sibling `gen_blocks.py`,
#: all claiming that one top-level module name.
MAIN_PROBE = """\
import runpy
import sys
from pathlib import Path

script, reports = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
sys.path.insert(0, str(script.parent.parent.parent / "bin"))
sys.path.insert(0, str(script.parent))
sys.argv = [str(script), str(reports)]
runpy.run_path(str(script), run_name="__main__")
"""


def _script(block: str) -> Path:
    return REPO_ROOT / "layout" / block / "bin" / "build_layout.py"


def _latest_record(block: str) -> Path:
    """The record directory `layout/<block>/reports/LATEST` points at."""
    reports = REPO_ROOT / "layout" / block / "reports"
    return reports / (reports / "LATEST").read_text(encoding="utf-8").strip()


def _parse(block: str) -> ast.Module:
    return ast.parse(
        _script(block).read_text(encoding="utf-8"), filename=str(_script(block))
    )


def _shared_imports(tree: ast.Module) -> dict[str, str]:
    """``{name imported from `_geometry_common`: name it is bound to locally}``
    -- the two differ wherever a script aliases the import to keep a local
    variable of its own (``draw_params``' neighbour ``compose_request``)."""
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "_geometry_common":
            for alias in node.names:
                bindings[alias.name] = alias.asname or alias.name
    return bindings


def _callers(tree: ast.Module, callee: str) -> set[str]:
    """Module-level functions that call ``callee(...)`` directly, by name."""
    callers: set[str] = set()
    for function in tree.body:
        if not isinstance(function, ast.FunctionDef):
            continue
        called = {
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        if callee in called:
            callers.add(function.name)
    return callers


def _first_divergence(want: bytes, got: bytes, limit: int = 12) -> str:
    """The leading lines of the diff between two documents, for a failure
    message -- enough to name what moved without dumping a 70 KB file."""
    lines = difflib.unified_diff(
        want.decode("utf-8").splitlines(),
        got.decode("utf-8").splitlines(),
        fromfile="committed",
        tofile="rebuilt",
        lineterm="",
        n=1,
    )
    return "\n".join(itertools.islice(lines, limit))


def _document(document: dict) -> str:
    """The serialisation `write_build_artifacts` gives every file it writes:
    `indent=2`, then one trailing newline."""
    return json.dumps(document, indent=2) + "\n"


class TestLoadBlock(unittest.TestCase):
    """The shared `klt gen` block-report reader's own output."""

    #: One report shaped as `klt gen` writes them: the three port flavours the
    #: flows route from (an li1 S/D port, an li1 gate port, a met4 top-plate
    #: port), and the top-level keys the reader ignores.
    REPORT: ClassVar[dict] = {
        "ports": [
            {
                "name": "U0_S",
                "net": "VDD",
                "x_um": 0.22,
                "y_um": 0.985,
                "width_um": 1.97,
                "direction_deg": 180.0,
                "layer": {"layer": 67, "datatype": 20, "name": None},
            },
            {
                "name": "U0_G",
                "net": "G_P",
                "x_um": 0.745,
                "y_um": 2.39,
                "width_um": 0.42,
                "direction_deg": 90.0,
                "layer": {"layer": 67, "datatype": 20, "name": None},
            },
            {
                "name": "C0_TOP",
                "net": "TOP_P",
                "x_um": 1.449,
                "y_um": 6.449,
                "width_um": 1.2,
                "direction_deg": 90.0,
                "layer": {"layer": 71, "datatype": 20, "name": None},
            },
        ],
        "bbox_um": {"x0": 0.0, "y0": -0.36, "x1": 1.49, "y1": 6.97},
        "generator": "cap_array",
    }

    def _load(self, report: dict) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "block.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            return geometry_common.load_block(path)

    def test_every_port_becomes_a_five_field_tuple(self):
        """``(x, y, width, direction, layer)`` per port, keyed by name.

        All five are read by `sampling-frontend`'s pin router, which walks the
        port down from `layer` and jogs it by `direction` -- so the one reader
        has to carry the two fields the wells flow's own three-field copy
        dropped.
        """
        self.assertEqual(
            {
                "ports": {
                    "U0_S": (0.22, 0.985, 1.97, 180.0, geometry_common.L_LI1),
                    "U0_G": (0.745, 2.39, 0.42, 90.0, geometry_common.L_LI1),
                    "C0_TOP": (1.449, 6.449, 1.2, 90.0, geometry_common.L_MET4),
                },
                "bbox": self.REPORT["bbox_um"],
            },
            self._load(self.REPORT),
        )

    def test_a_report_without_ports_still_gives_its_bbox(self):
        report = {"ports": [], "bbox_um": {"x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 1.0}}
        self.assertEqual({"ports": {}, "bbox": report["bbox_um"]}, self._load(report))


class TestDrawRequest(unittest.TestCase):
    """The `klt draw` request document, from the two lists a flow accumulates."""

    SHAPES = (
        (geometry_common.L_MET1, geometry_common.Rect.um(1.0, 2.0, 3.0, 4.0)),
        (geometry_common.L_MET2, geometry_common.Rect.centred(5.0, 6.0, 0.30, 0.30)),
    )
    LABELS = ((69, 5), "VDD", 7.5, 8.25)

    def test_shapes_and_labels_become_the_klt_draw_document(self):
        request = geometry_common.draw_request(list(self.SHAPES), [self.LABELS])
        self.assertEqual(
            {
                "shapes": [
                    {"layer": [68, 20], "rect_um": [1.0, 2.0, 3.0, 4.0]},
                    {"layer": [69, 20], "rect_um": [4.85, 5.85, 5.15, 6.15]},
                ],
                "labels": [{"layer": [69, 5], "text": "VDD", "at_um": [7.5, 8.25]}],
            },
            request,
        )

    def test_key_order_is_part_of_the_document(self):
        """`json.dumps` writes keys in insertion order and each flow's
        `draw.request.json` is an append-only record compared as bytes, so a
        helper that emitted the same mapping in another order would rewrite
        every record."""
        request = geometry_common.draw_request(list(self.SHAPES), [self.LABELS])
        self.assertEqual(["shapes", "labels"], list(request))
        self.assertEqual(["layer", "rect_um"], list(request["shapes"][0]))
        self.assertEqual(["layer", "text", "at_um"], list(request["labels"][0]))

    def test_nothing_drawn_and_nothing_labelled_is_an_empty_document(self):
        self.assertEqual(
            {"shapes": [], "labels": []}, geometry_common.draw_request([], [])
        )


class TestComposeRequest(unittest.TestCase):
    """The `klt.gen_compose.request/1` explicit-placement document."""

    ORIGINS: ClassVar[dict] = {
        "tail": {"x": 2.0, "y": 16.0},
        "inpair": {"x": 5.5, "y": 17.39},
    }

    def test_origins_alone_give_the_sky130a_placement_document(self):
        self.assertEqual(
            {
                "schema": "klt.gen_compose.request/1",
                "pdk": {"variant": "sky130A"},
                "blocks": [
                    {"id": "tail", "generator_report": "tail.json"},
                    {"id": "inpair", "generator_report": "inpair.json"},
                    {"id": "route", "generator_report": "draw.json"},
                ],
                "placement": {
                    "strategy": "explicit",
                    "order": ["tail", "inpair", "route"],
                    "origins_um": {
                        "tail": {"x": 2.0, "y": 16.0},
                        "inpair": {"x": 5.5, "y": 17.39},
                        "route": {"x": 0.0, "y": 0.0},
                    },
                },
                "connectivity": [],
            },
            geometry_common.compose_request(self.ORIGINS),
        )

    def test_key_order_is_part_of_the_document(self):
        request = geometry_common.compose_request(self.ORIGINS)
        self.assertEqual(
            ["schema", "pdk", "blocks", "placement", "connectivity"], list(request)
        )
        self.assertEqual(
            ["strategy", "order", "origins_um"], list(request["placement"])
        )
        self.assertEqual(["id", "generator_report"], list(request["blocks"][0]))

    def test_block_ids_set_the_block_and_order_sequence(self):
        """``block_ids`` is the sequence the placer is given, independent of
        the origins table's own order: the wells flow names its blocks from its
        device table and the comparator from ``BLOCK_X``, and neither may
        quietly start depending on dict order to place them."""
        request = geometry_common.compose_request(self.ORIGINS, ["inpair", "tail"])
        self.assertEqual(["inpair", "tail", "route"], request["placement"]["order"])
        self.assertEqual(
            ["inpair", "tail", "route"], [block["id"] for block in request["blocks"]]
        )
        self.assertEqual(
            ["tail", "inpair", "route"], list(request["placement"]["origins_um"])
        )

    def test_pdk_variant_is_an_argument_with_the_sky130a_default(self):
        defaulted = geometry_common.compose_request(self.ORIGINS)
        variant = geometry_common.compose_request(self.ORIGINS, pdk_variant="sky130B")
        self.assertEqual({"variant": "sky130A"}, defaulted["pdk"])
        self.assertEqual({"variant": "sky130B"}, variant["pdk"])
        self.assertEqual(defaulted["placement"], variant["placement"])

    def test_the_callers_origins_table_is_left_as_it_was(self):
        """The routing cell's origin is added to the request's own copy, never
        to the caller's table -- each flow's summary reports that same table
        as ``block_origins_um`` and must not gain a ``route`` entry."""
        origins = {"tail": {"x": 2.0, "y": 16.0}}
        before = copy.deepcopy(origins)
        geometry_common.compose_request(origins)
        self.assertEqual(before, origins)
        self.assertEqual(["tail"], list(origins))


class TestSummarizePfetDomains(unittest.TestCase):
    """The Row-1 n-well domain summary both sampling-frontend flows report."""

    def test_the_three_islands_come_out_rounded_with_devices_in_table_order(self):
        summary, gaps = geometry_common.summarize_pfet_domains(
            _domains((2.37, 17.369999999999997, 2.37)), pfet_devices.PFET_DEVICES
        )
        self.assertEqual(
            [
                {
                    "id": "boost_p",
                    "tap_net": "BOOST_P",
                    "members": ["sa_p", "se_p"],
                    "schematic_devices": ["Sa_p", "Se_p"],
                    "well_um": {"x0": 0.0, "y0": -2.4, "x1": 6.74, "y1": 2.37},
                    "tap_um": {"x0": 0.4, "x1": 1.0, "y0": -1.8, "y1": -0.6},
                },
                {
                    "id": "vdd",
                    "tap_net": "VDD",
                    "members": ["scp_p", "cmswp_p", "invp", "cmswp_n", "scp_n"],
                    "schematic_devices": [
                        "Scp_p",
                        "Cmswp_p",
                        "Invp",
                        "Cmswp_n",
                        "Scp_n",
                    ],
                    "well_um": {"x0": 8.34, "y0": -2.4, "x1": 24.68, "y1": 17.37},
                    "tap_um": {"x0": 8.74, "x1": 9.34, "y0": -1.8, "y1": -0.6},
                },
                {
                    "id": "boost_n",
                    "tap_net": "BOOST_N",
                    "members": ["se_n", "sa_n"],
                    "schematic_devices": ["Se_n", "Sa_n"],
                    "well_um": {"x0": 26.28, "y0": -2.4, "x1": 33.27, "y1": 2.37},
                    "tap_um": {"x0": 26.68, "x1": 27.28, "y0": -1.8, "y1": -0.6},
                },
            ],
            summary,
        )
        self.assertEqual([1.6, 1.6], gaps)

    def test_schematic_devices_follow_the_domain_not_the_member_list(self):
        """``schematic_devices`` is looked up in the device table by domain,
        which is what lets a summary name devices by their schematic name while
        the floorplan only knows block ids."""
        only_vdd = _domains((2.37, 17.369999999999997, 2.37))[1:2]
        summary, gaps = geometry_common.summarize_pfet_domains(
            only_vdd, pfet_devices.PFET_DEVICES
        )
        self.assertEqual(["vdd"], [entry["id"] for entry in summary])
        self.assertEqual(5, len(summary[0]["schematic_devices"]))
        self.assertEqual(
            [], gaps, "one island has no neighbour to be gap-sized against"
        )

    def test_a_domain_the_device_table_does_not_know_has_no_devices(self):
        unknown = [
            {
                "id": "spare",
                "net": "VDD",
                "members": ["x_p"],
                "well": {"x0": 0.0, "y0": -2.4, "x1": 3.0, "y1": 2.37},
                "tap": {"x0": 0.4, "x1": 1.0, "y0": -1.8, "y1": -0.6},
            }
        ]
        summary, gaps = geometry_common.summarize_pfet_domains(
            unknown, pfet_devices.PFET_DEVICES
        )
        self.assertEqual([], summary[0]["schematic_devices"])
        self.assertEqual([], gaps)


class TestWriteBuildArtifacts(unittest.TestCase):
    """`main()`'s write-and-report step, shared by all four flows."""

    DRAW_PARAMS: ClassVar[dict] = {
        "shapes": [{"layer": [68, 20], "rect_um": [1.0, 2.0, 3.0, 4.0]}],
        "labels": [
            {"layer": [69, 5], "text": "VDD", "at_um": [7.5, 8.25]},
            {"layer": [69, 5], "text": "GND", "at_um": [7.5, 8.75]},
        ],
    }
    COMPOSE_REQUEST: ClassVar[dict] = {"blocks": [{"id": "tail"}, {"id": "route"}]}
    SUMMARY: ClassVar[dict] = {"well_gap_drawn_um": 1.6, "island_gaps_um": [1.6, 1.6]}

    def _write(self, summary_filename: str) -> tuple[dict[str, bytes], str]:
        with tempfile.TemporaryDirectory() as tmp:
            reports_dir = Path(tmp)
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                geometry_common.write_build_artifacts(
                    reports_dir,
                    self.DRAW_PARAMS,
                    self.COMPOSE_REQUEST,
                    self.SUMMARY,
                    summary_filename,
                )
            written = {path.name: path.read_bytes() for path in reports_dir.iterdir()}
        return written, captured.getvalue()

    def test_writes_the_two_requests_and_the_named_summary(self):
        written, _ = self._write("wells.summary.json")
        self.assertEqual(
            {
                "draw.request.json": _document(self.DRAW_PARAMS),
                "compose.request.json": _document(self.COMPOSE_REQUEST),
                "wells.summary.json": _document(self.SUMMARY),
            },
            {name: text.decode("utf-8") for name, text in written.items()},
        )

    def test_the_summary_filename_is_the_callers(self):
        written, _ = self._write("route.summary.json")
        self.assertIn("route.summary.json", written)
        self.assertNotIn("wells.summary.json", written)

    def test_reports_the_document_sizes_on_stdout(self):
        """The one line every flow's `main()` prints first, before its own
        flow-specific lines."""
        _, stdout = self._write("layout.summary.json")
        self.assertEqual("build_layout.py: 1 shapes, 2 labels, 2 blocks\n", stdout)


class TestSubBlocksRewriteTheirCommittedRecords(unittest.TestCase):
    """The gate: each sub-block's `main()` reproduces its own `reports/LATEST`.

    A pure consolidation must move nothing, and this is the mechanical proof:
    the same script, on a copy of the same record directory, must put back the
    same bytes. From here on it is also the tripwire any real change to
    request-building trips -- the two request documents are a flow's input to
    `klt draw` / `klt gen-compose`, so a change here is a change of what that
    flow would build and belongs with a re-run, not with a quiet edit.
    """

    def test_main_rewrites_every_latest_record_byte_for_byte(self):
        for block, summary_name in SUB_BLOCKS:
            with self.subTest(block=block), tempfile.TemporaryDirectory() as tmp:
                record = _latest_record(block)
                # A copy, with the three outputs removed first: `main()` has
                # to put them back, so a run that wrote nothing cannot pass on
                # the strength of the files the copy brought along. The
                # committed record itself is only ever read.
                scratch = Path(tmp) / "record"
                shutil.copytree(record, scratch)
                for name in (*REQUEST_DOCUMENTS, summary_name):
                    (scratch / name).unlink()

                script = str(_script(block))
                proc = subprocess.run(
                    [sys.executable, "-c", MAIN_PROBE, script, str(scratch)],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
                self.assertEqual(
                    0,
                    proc.returncode,
                    f"layout/{block}/bin/build_layout.py failed on record "
                    f"{record.name}'s own block reports (exit {proc.returncode}).\n"
                    f"--- stderr ---\n{proc.stderr}",
                )

                for name in (*REQUEST_DOCUMENTS, summary_name):
                    rebuilt = scratch / name
                    self.assertTrue(
                        rebuilt.is_file(), f"{block}: main() did not write {name}"
                    )
                    want = (record / name).read_bytes()
                    got = rebuilt.read_bytes()
                    self.assertEqual(
                        want,
                        got,
                        f"{block}/{name}: rebuilt from record {record.name}'s own "
                        "block reports, it no longer matches what that record "
                        "committed. If the change is intended, re-run that flow "
                        "and record new documents rather than just updating this "
                        f"test. First differing lines:\n{_first_divergence(want, got)}",
                    )


class TestSubBlocksUseTheSharedPlumbing(unittest.TestCase):
    """The consolidation itself, read from the four scripts' source trees.

    Byte-identity above proves the refactor moved nothing, and would pass
    just as well with every local copy still in place. These pins are what
    keeps a copy from creeping back beside the shared helper.
    """

    def test_no_sub_block_defines_its_own_load_block(self):
        for block, _summary in SUB_BLOCKS:
            with self.subTest(block=block):
                defined = {
                    node.name
                    for node in _parse(block).body
                    if isinstance(node, ast.FunctionDef)
                }
                self.assertNotIn("load_block", defined)

    def test_each_script_calls_each_shared_helper_from_where_it_builds(self):
        for block, _summary in SUB_BLOCKS:
            tree = _parse(block)
            bindings = _shared_imports(tree)
            for helper, caller in HELPER_CALLERS[block].items():
                with self.subTest(block=block, helper=helper):
                    self.assertIn(
                        helper,
                        bindings,
                        f"layout/{block}/bin/build_layout.py no longer imports "
                        f"{helper} from _geometry_common",
                    )
                    self.assertEqual({caller}, _callers(tree, bindings[helper]))

    def test_no_sub_block_still_spells_the_compose_schema_itself(self):
        """A script that imported the helper and still assembled its own
        request would satisfy the check above; the schema literal is what
        only a hand-rolled copy spells."""
        for block, _summary in SUB_BLOCKS:
            with self.subTest(block=block):
                strings = {
                    node.value
                    for node in ast.walk(_parse(block))
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)
                }
                self.assertNotIn("klt.gen_compose.request/1", strings)

    def test_sampling_frontend_pin_routers_share_one_loop_body(self):
        """`_route_mos_pins` and `_route_cap_pins` differ only in the ports
        they name and whether a met4 escape is supplied; the step-down, the
        jog and the column claim are one loop, `_route_pins`."""
        tree = _parse("sampling-frontend")
        step_down = _shared_imports(tree)["step_down_to_met1"]
        self.assertEqual({"_route_pins"}, _callers(tree, step_down))
        self.assertEqual(
            {"_route_mos_pins", "_route_cap_pins"}, _callers(tree, "_route_pins")
        )


if __name__ == "__main__":
    unittest.main()

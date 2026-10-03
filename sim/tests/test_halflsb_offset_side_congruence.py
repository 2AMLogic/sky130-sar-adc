"""Anti-vacuity tests for `layout/halflsb-offset/bin/build_layout.py`'s
`_n`/`_p` congruence assertion (issue #495).

WHY THIS FILE EXISTS
--------------------
DR-009's `_p` half is a *matching dummy*: it injects nothing and exists only so
both comparator top plates carry the same capacitance and the same switch
junction parasitics. That makes it the one property of this block that **neither
DRC nor LVS can see** -- a layout that scattered the `_p` devices across the
floorplan would be DRC-clean and would LVS-match, while destroying the only
reason the dummy exists.

`build_layout.py` therefore asserts it at build time instead of claiming it in
prose: `_assert_side_congruence()` translates every `_n`-side shape by exactly
`(SIDE_PITCH_UM, 0)` and raises `BuildError` unless the result is the `_p` side's
shape set, checked in integer nanometres. The record then reports how much was
checked (shapes and met1 columns per side) rather than only that a check ran.

A build-time assertion is only worth as much as its ability to fail, and nothing
in the flow exercises that: every committed run is of a layout that *is*
congruent, so a silently-vacuous assertion (comparing a set against itself, or
against an empty set) would look identical in the record. These tests are what
close that: each perturbs one side of a synthetic shape set by one nanometre --
the smallest difference the database can express -- and asserts the assertion
raises, plus one test that the real floorplan's own shape sets are non-empty so
the committed run is not a vacuous pass either.

Pure stdlib -- no PDK, no KLayout, no `klt`: `build_layout.py` builds its
geometry as plain integer rectangles and only hands them to `klt draw` as JSON,
so this belongs to the headless tier (`npm run test` -> `test:unit`, CI's
"Repo checks (headless, no PDK)" job), like
`sim/tests/test_layout_entrypoint_imports.py`.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BLOCK_BIN = REPO_ROOT / "layout" / "halflsb-offset" / "bin"
LAYOUT_BIN = REPO_ROOT / "layout" / "bin"


def _load_build_layout():
    """`layout/halflsb-offset/bin/build_layout.py` as a module.

    Loaded by path with that block's own `bin/` ahead of the shared one on
    `sys.path`, the prelude the script sets up for itself -- it imports a
    sibling `gen_blocks`, and several blocks under `layout/` claim that same
    top-level module name (see `sim/tests/test_layout_entrypoint_imports.py`).

    **Both the `sys.path` entries and the `sys.modules` entries this pulls in
    are removed again afterwards.** Leaving `gen_blocks` cached would make a
    *later* test module that loads a DIFFERENT block's `build_layout.py`
    resolve `gen_blocks` to this one and fail on a missing name -- an ordering
    coupling between unrelated test modules, which is exactly the ambiguity
    those three same-named modules already cost this repo once.
    """
    sys.path.insert(0, str(BLOCK_BIN))
    sys.path.insert(1, str(LAYOUT_BIN))
    before = set(sys.modules)
    try:
        spec = importlib.util.spec_from_file_location(
            "_halflsb_offset_build_layout", BLOCK_BIN / "build_layout.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(BLOCK_BIN))
        sys.path.remove(str(LAYOUT_BIN))
        for name in set(sys.modules) - before - {"_halflsb_offset_build_layout"}:
            del sys.modules[name]


BL = _load_build_layout()
WORKING, DUMMY = BL.SIDES
DX = BL.nm(BL.SIDE_PITCH_UM)

#: A small synthetic `_n` side: three shapes on two layers, enough that a
#: perturbation of any one of them is a set difference rather than a reordering.
_N_SHAPES = (
    (BL.L_MET1, BL.Rect(0, 0, 300, 1000)),
    (BL.L_MET2, BL.Rect(100, 500, 800, 640)),
    (BL.L_NWELL, BL.Rect(-400, -2400, 6740, 3370)),
)

#: Three met1 columns, as `(net, x_um, y_um)` -- the shape
#: `_assert_side_congruence` reads them in.
_N_COLUMNS = (("TOP_N", 1.0, 2.0), ("BOT_OFF_N", 2.5, 2.0), ("VCM", 4.0, 2.0))


def _translate(shapes):
    return [(layer, BL.Rect(r.x0 + DX, r.y0, r.x1 + DX, r.y1)) for layer, r in shapes]


def _translate_columns(columns):
    return [(net, x + BL.SIDE_PITCH_UM, y) for net, x, y in columns]


class SideCongruenceAssertionTest(unittest.TestCase):
    """The assertion must accept a congruent pair and reject every 1 nm break."""

    def _run(self, n_shapes, p_shapes, n_columns=_N_COLUMNS, p_columns=None):
        if p_columns is None:
            p_columns = _translate_columns(n_columns)
        return BL._assert_side_congruence(
            {WORKING: list(n_shapes), DUMMY: list(p_shapes)},
            {WORKING: list(n_columns), DUMMY: list(p_columns)},
        )

    def test_congruent_sides_pass_and_report_what_was_checked(self):
        """The positive control. Without it, an assertion that rejected
        *everything* would pass every negative below."""
        summary = self._run(_N_SHAPES, _translate(_N_SHAPES))
        self.assertEqual(summary["translation_um"], BL.SIDE_PITCH_UM)
        self.assertEqual(summary["shapes_per_side"], len(_N_SHAPES))
        self.assertEqual(summary["columns_per_side"], len(_N_COLUMNS))
        self.assertTrue(summary["checked_in_dbu"])

    def test_one_nanometre_of_x_drift_on_the_dummy_side_raises(self):
        """One database unit: the tightest difference the assertion has to see,
        and the one a tolerant float comparison would miss."""
        shifted = _translate(_N_SHAPES)
        layer, rect = shifted[1]
        shifted[1] = (layer, BL.Rect(rect.x0 + 1, rect.y0, rect.x1 + 1, rect.y1))
        with self.assertRaises(BL.BuildError) as raised:
            self._run(_N_SHAPES, shifted)
        self.assertIn("translated by", str(raised.exception))

    def test_one_nanometre_of_y_drift_on_the_dummy_side_raises(self):
        """The translation is in x only, so a y difference is a pure asymmetry
        -- the axis a check written as "same x-pitch" would not cover."""
        shifted = _translate(_N_SHAPES)
        layer, rect = shifted[0]
        shifted[0] = (layer, BL.Rect(rect.x0, rect.y0 + 1, rect.x1, rect.y1 + 1))
        with self.assertRaises(BL.BuildError):
            self._run(_N_SHAPES, shifted)

    def test_wrong_layer_on_the_dummy_side_raises(self):
        """Same rectangle, different layer: identical junction *outline*, a
        different physical structure, so it is not a match."""
        shifted = _translate(_N_SHAPES)
        shifted[0] = (BL.L_MET2, shifted[0][1])
        with self.assertRaises(BL.BuildError):
            self._run(_N_SHAPES, shifted)

    def test_missing_shape_on_the_dummy_side_raises(self):
        with self.assertRaises(BL.BuildError) as raised:
            self._run(_N_SHAPES, _translate(_N_SHAPES)[:-1])
        self.assertIn("absent from side", str(raised.exception))

    def test_extra_shape_on_the_dummy_side_raises(self):
        extra = _translate(_N_SHAPES) + [(BL.L_MET1, BL.Rect(0, 0, 10, 10))]
        with self.assertRaises(BL.BuildError) as raised:
            self._run(_N_SHAPES, extra)
        self.assertIn("no translated counterpart", str(raised.exception))

    def test_both_sides_empty_is_not_silently_accepted_as_congruent(self):
        """Two empty sides *are* trivially congruent, which is exactly why the
        real run's non-emptiness is asserted separately (below) -- this test
        documents that the shape comparison alone cannot carry that weight."""
        summary = self._run((), (), n_columns=(), p_columns=())
        self.assertEqual(summary["shapes_per_side"], 0)
        self.assertEqual(summary["columns_per_side"], 0)

    def test_column_drift_raises_even_when_every_shape_matches(self):
        """The met1 columns are checked separately from the shapes: a column
        table that disagrees with a congruent shape set means the two sides'
        per-net risers would not land at translated x."""
        columns = _translate_columns(_N_COLUMNS)
        net, x, y = columns[2]
        columns[2] = (net, x + 0.001, y)
        with self.assertRaises(BL.BuildError) as raised:
            self._run(_N_SHAPES, _translate(_N_SHAPES), p_columns=columns)
        self.assertIn("met1 columns", str(raised.exception))


class RealFloorplanIsNotAVacuousPassTest(unittest.TestCase):
    """What the synthetic tests above cannot say: that the *committed* run's own
    congruence verdict covered a non-trivial amount of geometry."""

    def test_committed_record_reports_a_non_empty_congruence_check(self):
        import json

        latest = (
            REPO_ROOT / "layout" / "halflsb-offset" / "reports" / "LATEST"
        ).read_text(encoding="utf-8").strip()
        summary = json.loads(
            (
                REPO_ROOT
                / "layout"
                / "halflsb-offset"
                / "reports"
                / latest
                / "layout.summary.json"
            ).read_text(encoding="utf-8")
        )
        congruence = summary["side_congruence"]
        self.assertEqual(congruence["translation_um"], BL.SIDE_PITCH_UM)
        self.assertTrue(congruence["checked_in_dbu"])
        self.assertGreater(
            congruence["shapes_per_side"],
            0,
            "reports/LATEST's congruence verdict covered zero shapes -- the "
            "assertion passed vacuously, so DR-009's matching dummy is not "
            "actually held by anything",
        )
        self.assertGreater(congruence["columns_per_side"], 0)

    def test_matched_net_pairs_are_held_to_adjacent_tracks(self):
        """The one asymmetry the congruence assertion deliberately excludes (the
        per-net met1 risers above the track band) is bounded by a separate
        assertion; this is its anti-vacuity pin."""
        BL._assert_matched_pairs_adjacent()  # the committed TRACK_ORDER
        original = BL.TRACK_ORDER
        a, b = BL.MATCHED_NET_PAIRS[0]
        reordered = [net for net in original if net != b] + [b]
        self.assertNotEqual(tuple(reordered), original, "reorder was a no-op")
        BL.TRACK_ORDER = tuple(reordered)
        try:
            with self.assertRaises(BL.BuildError):
                BL._assert_matched_pairs_adjacent()
        finally:
            BL.TRACK_ORDER = original
        self.assertIn(a, BL.TRACK_ORDER)


if __name__ == "__main__":
    unittest.main()

"""Behaviour pins for the two helpers `layout/bin/` shares across blocks:
`_geometry_common.step_down_to_met1()` and `_pfet_devices.mos_array_params()`.

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


if __name__ == "__main__":
    unittest.main()

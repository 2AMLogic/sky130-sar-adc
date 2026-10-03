"""Equivalence pins for the two helpers issue #495 moved into `layout/bin/`
while deliberately leaving the original copy in place.

WHY THIS FILE EXISTS
--------------------
`layout/halflsb-offset/` needs two things `layout/sampling-frontend/` had already
worked out: the "walk a generator port down to met1" via-stack emitter (three
layer cases, each with a DRC finding behind it) and the `klt gen mos_array`
parameter dict this repo draws an unmatched single-finger FET with. Copying
either into a new block is the drift this repo has met before (#163, #208,
#251, #255); re-pointing `layout/sampling-frontend/` at a shared copy is not
free either, because that flow's output is the drawn geometry behind a committed,
append-only DRC-clean / LVS-match record, so a change there is work that belongs
with that flow's next re-run rather than with a sibling's first one.

So both copies exist for now, and this module is what makes that safe: it drives
the shared copy and the sampling-frontend copy over the same inputs and asserts
they emit identical output. A divergence is a test failure here rather than a
silent difference between two blocks' geometry, and the eventual fold-in becomes
a provable no-op.

Pure stdlib -- no PDK, no KLayout, no `klt` -- so it belongs to the headless tier
(`npm run test` -> `test:unit`, CI's "Repo checks (headless, no PDK)" job), the
same convention `sim/tests/test_layout_entrypoint_imports.py` follows.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LAYOUT_BIN = REPO_ROOT / "layout" / "bin"
SAMPLING_FRONTEND_BIN = REPO_ROOT / "layout" / "sampling-frontend" / "bin"

sys.path.insert(0, str(LAYOUT_BIN))

import _geometry_common as geometry_common  # noqa: E402
import _pfet_devices as pfet_devices  # noqa: E402


def _load_sampling_frontend_build_layout():
    """`layout/sampling-frontend/bin/build_layout.py` as a module.

    Loaded by path, with that block's own `bin/` ahead of the shared one on
    `sys.path`, exactly the prelude the script sets up for itself -- it imports
    a sibling `gen_blocks`, and three blocks under `layout/` claim that same
    top-level module name (see
    `sim/tests/test_layout_entrypoint_imports.py`'s docstring).

    The sibling modules this pulls in are removed from `sys.modules` again
    afterwards, so a later test module loading a different block's
    `build_layout.py` does not resolve `gen_blocks` to this one. See
    `sim/tests/test_halflsb_offset_side_congruence.py`'s own loader for the
    same guard from the other side.
    """
    script = SAMPLING_FRONTEND_BIN / "build_layout.py"
    sys.path.insert(0, str(SAMPLING_FRONTEND_BIN))
    before = set(sys.modules)
    try:
        spec = importlib.util.spec_from_file_location(
            "_sampling_frontend_build_layout", script
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SAMPLING_FRONTEND_BIN))
        for name in set(sys.modules) - before - {"_sampling_frontend_build_layout"}:
            del sys.modules[name]


#: Every layer case `step_down_to_met1` handles, as
#: `(label, layer, direction, met4_escape_y)`. Sourced from the shared module's
#: own layer constants, so a renumbered layer moves both sides together and this
#: table cannot go stale against one of them.
LAYER_CASES = (
    ("li1 (mos_array S/G/D)", geometry_common.L_LI1, 180.0, None),
    ("met3 (cap_array *_BOT, facing -x)", geometry_common.L_MET3, 180.0, None),
    ("met3 (cap_array *_BOT, facing +x)", geometry_common.L_MET3, 0.0, None),
    ("met4 (cap_array *_TOP)", geometry_common.L_MET4, 90.0, 9.62),
)


class TestStepDownToMet1Equivalence(unittest.TestCase):
    """The shared emitter and sampling-frontend's local one must agree."""

    @classmethod
    def setUpClass(cls):
        cls.sampling_frontend = _load_sampling_frontend_build_layout()

    def test_local_copy_still_exists(self):
        """Anti-vacuity: if the sampling-frontend copy is ever folded into the
        shared one, this suite stops covering anything and must be updated
        deliberately rather than passing empty."""
        self.assertTrue(
            hasattr(self.sampling_frontend, "_step_down_to_met1"),
            "layout/sampling-frontend/bin/build_layout.py no longer defines "
            "_step_down_to_met1 -- if it now delegates to "
            "_geometry_common.step_down_to_met1, that is the fold-in this "
            "module was holding safe: drop these equivalence tests in the same "
            "change, and say so in the flow's next record",
        )

    def test_every_layer_case_emits_identical_shapes(self):
        for label, layer, direction, escape_y in LAYER_CASES:
            with self.subTest(case=label):
                shared: list = []
                local: list = []
                shared_xy = geometry_common.step_down_to_met1(
                    shared, 1.449, 6.449, layer, direction, met4_escape_y=escape_y
                )
                local_xy = self.sampling_frontend._step_down_to_met1(
                    local, 1.449, 6.449, layer, direction, met4_escape_y=escape_y
                )
                self.assertEqual(shared_xy, local_xy)
                self.assertEqual(
                    [(lay, rect.as_um()) for lay, rect in shared],
                    [(lay, rect.as_um()) for lay, rect in local],
                    f"{label}: the shared and sampling-frontend emitters have "
                    "diverged -- they draw the geometry of two different blocks, "
                    "so fix the divergence rather than the test",
                )

    def test_met4_case_requires_an_escape_y_on_both(self):
        for emitter in (
            geometry_common.step_down_to_met1,
            self.sampling_frontend._step_down_to_met1,
        ):
            with self.subTest(emitter=emitter.__module__):
                with self.assertRaises(geometry_common.BuildError):
                    emitter([], 1.0, 1.0, geometry_common.L_MET4, 90.0)

    def test_unknown_layer_raises_on_both(self):
        bogus = (12345, 67)
        for emitter in (
            geometry_common.step_down_to_met1,
            self.sampling_frontend._step_down_to_met1,
        ):
            with self.subTest(emitter=emitter.__module__):
                with self.assertRaises(geometry_common.BuildError):
                    emitter([], 1.0, 1.0, bogus, 90.0)


class TestMosArrayParamsEquivalence(unittest.TestCase):
    """`_pfet_devices`' shared emitters vs sampling-frontend's local ones."""

    @classmethod
    def setUpClass(cls):
        script = SAMPLING_FRONTEND_BIN / "gen_blocks.py"
        sys.path.insert(0, str(SAMPLING_FRONTEND_BIN))
        before = set(sys.modules)
        try:
            spec = importlib.util.spec_from_file_location(
                "_sampling_frontend_gen_blocks", script
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            cls.gen_blocks = module
        finally:
            sys.path.remove(str(SAMPLING_FRONTEND_BIN))
            for name in set(sys.modules) - before - {"_sampling_frontend_gen_blocks"}:
                del sys.modules[name]

    def test_pfet_and_nfet_params_match_the_local_copies(self):
        for w_um, l_um in ((1.0, 0.15), (2.0, 0.15), (16.0, 0.15), (1.0, 0.5)):
            with self.subTest(w=w_um, l=l_um):
                self.assertEqual(
                    pfet_devices.pfet_params(w_um, l_um),
                    self.gen_blocks.pfet_params(w_um, l_um),
                )
                self.assertEqual(
                    pfet_devices.nfet_params(w_um, l_um),
                    self.gen_blocks.nfet_params(w_um, l_um),
                )

    def test_shared_emitter_dict_is_pinned_exactly(self):
        """The dict itself, not just "equal to the other copy".

        Both copies changing together would still change what every full-custom
        block in `layout/` generates, and every committed record was minted
        against this exact dict.
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

    def test_unknown_flavor_raises(self):
        with self.assertRaises(ValueError):
            pfet_devices.mos_array_params("bjt", 1.0, 0.15)


if __name__ == "__main__":
    unittest.main()

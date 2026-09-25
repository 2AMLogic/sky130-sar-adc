"""Unit tests for sim/ground-return-impedance/ (issue #378) -- the two
testbench-only deck rewrites, pinned without ngspice or the PDK.

Why these are worth pinning rather than trusting to a multi-minute transient:

1. The analog-ground rename is the whole campaign. ngspice aliases a node
   named `gnd` to the reference node 0, so if any `GND` token survives, that
   device's ground stays IDEAL no matter what network the arm attaches -- a
   silent, plausible-looking "no effect" result. Conversely, a rename that
   touched `VGND` would move the digital ground onto the analog one.
2. Each arm's network must be the one its name says: no package elements in
   ideal-bond arms, no `GND` pad source in no-pad arms, a substrate tie only
   where one is declared, and the fragment's original ideal supply lines gone.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(SIM_DIR / "ground-return-impedance"))

import run_ground_return as g  # noqa: E402

TOKEN = r"(?<![A-Za-z0-9_]){}(?![A-Za-z0-9_])"


def _code_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if not ln.lstrip().startswith("*")]


def _count(text: str, token: str, flags: int = 0) -> int:
    rx = re.compile(TOKEN.format(re.escape(token)), flags)
    return sum(len(rx.findall(ln)) for ln in _code_lines(text))


class TestRename(unittest.TestCase):
    def setUp(self):
        self.dut = g.fct.dut_text()
        self.renamed = g.rename_analog_ground(self.dut)

    def test_no_ground_aliased_token_survives(self):
        self.assertEqual(_count(self.renamed, "gnd", re.I), 0)

    def test_every_gnd_became_gnd_die(self):
        self.assertGreater(_count(self.dut, "GND"), 0)
        self.assertEqual(_count(self.dut, "GND"), _count(self.renamed, "GND_DIE"))

    def test_vgnd_untouched(self):
        self.assertEqual(_count(self.dut, "VGND"), _count(self.renamed, "VGND"))

    def test_comment_lines_unchanged(self):
        before = [ln for ln in self.dut.splitlines() if ln.lstrip().startswith("*")]
        after = [ln for ln in self.renamed.splitlines() if ln.lstrip().startswith("*")]
        self.assertEqual(before, after)

    def test_global_declaration_follows_the_rename(self):
        self.assertIn(".GLOBAL GND_DIE", self.renamed.splitlines())

    def test_rename_fails_loudly_when_nothing_to_rename(self):
        with self.assertRaises(RuntimeError):
            g.rename_analog_ground("R1 a b 1\n")


class TestSupplyRewrite(unittest.TestCase):
    def _deck(self, arm: g.Arm) -> str:
        frag = g.tb.FRAGMENT_PATH.read_text()
        return g.rewrite_supplies(frag, arm)

    def test_original_ideal_supply_lines_are_gone(self):
        # Ideal-bond arms legitimately re-emit the same direct source lines;
        # every package arm must have removed all three.
        for arm in [a for a in g.ARMS if a.package]:
            deck = self._deck(arm)
            for line in g.FRAGMENT_SUPPLY_LINES.values():
                self.assertNotIn(line, deck.splitlines(), f"{arm.name}: {line!r} left in place")

    def test_source_names_preserved_so_fragment_meas_still_resolve(self):
        for arm in g.ARMS:
            deck = self._deck(arm)
            for src in ("VVDD", "VVPWR", "VVGND"):
                self.assertEqual(
                    sum(1 for ln in _code_lines(deck) if ln.split()[:1] == [src]), 1,
                    f"{arm.name}: source {src} not defined exactly once",
                )

    def test_package_elements_only_in_package_arms(self):
        for arm in g.ARMS:
            deck = self._deck(arm)
            n_l = sum(1 for ln in _code_lines(deck) if ln.startswith("LPKG_"))
            n_bonded = 4 if arm.gnd_pad else 3
            self.assertEqual(n_l, n_bonded if arm.package else 0, arm.name)

    def test_gnd_pad_source_only_when_bonded(self):
        for arm in g.ARMS:
            has = any(ln.split()[:1] == ["VVGNDA"] for ln in _code_lines(self._deck(arm)))
            self.assertEqual(has, arm.gnd_pad, arm.name)

    def test_substrate_tie_only_when_declared(self):
        for arm in g.ARMS:
            deck = self._deck(arm)
            rsub = [ln for ln in _code_lines(deck) if ln.startswith("RSUB ")]
            if arm.r_sub_ohm is None:
                self.assertEqual(rsub, [], arm.name)
            else:
                self.assertEqual(len(rsub), 1, arm.name)
                self.assertEqual(float(rsub[0].split()[3]), arm.r_sub_ohm)

    def test_no_pad_arms_leave_gnd_die_a_substrate_only_node(self):
        # GND_DIE must have SOME DC path (else the deck is singular): in a
        # no-pad arm that path is exactly the substrate tie.
        for arm in g.ARMS:
            if not arm.gnd_pad:
                self.assertIsNotNone(arm.r_sub_ohm, arm.name)

    def test_reshaped_fragment_fails_loudly(self):
        with self.assertRaises(RuntimeError):
            g.rewrite_supplies("* nothing here\n", g.ARMS_BY_NAME["pkg"])

    def test_measure_lines_and_names_agree(self):
        for arm in g.ARMS:
            lines = "\n".join(g.extra_measure_lines(arm))
            for name in g.extra_measure_names(arm):
                self.assertEqual(lines.count(f".meas tran {name} "), 1, f"{arm.name}: {name}")


class TestPackageValues(unittest.TestCase):
    def test_bond_wire_values_from_geometry(self):
        # 2 mm x 25 um Au: ~2.0 nH, ~0.1 ohm -- the README's own derivation.
        self.assertAlmostEqual(g.L_PKG_H * 1e9, 2.01, places=2)
        self.assertAlmostEqual(g.R_PKG_OHM, 0.099, places=3)

    def test_arm_names_unique_and_baseline_present(self):
        names = [a.name for a in g.ARMS]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn(g.BASELINE_ARM, names)


class TestAnalysis(unittest.TestCase):
    @staticmethod
    def _pt(arm, cid, cs, gnd=(0.0, 0.0)):
        return dict(
            arm=arm, corner_id=cid, supply_v=1.8, n_phase_ok=5, n_conversions=5,
            conversions=[dict(code=c) for c in cs], missing=[],
            extra=dict(gnd_die_max=gnd[1], gnd_die_min=gnd[0], vdda_min=1.7),
        )

    def test_deltas_are_against_same_corner_ideal(self):
        pts = [
            self._pt("ideal", "tt", [1, 2, 3, 4, 5]),
            self._pt("ideal", "ss", [9, 9, 9, 9, 9]),
            self._pt("pkg", "tt", [1, 2, 4, 4, 5], gnd=(-0.01, 0.01)),
        ]
        self.assertEqual(g.code_deltas(pts[2], g.baseline_for(pts, pts[2])), [0, 0, 1, 0, 0])
        s = g.arm_summary(pts, "pkg")
        self.assertEqual((s["n_moved"], s["max_abs_delta"]), (1, 1))

    def test_controls_catch_a_moving_ideal_ground(self):
        pts = [self._pt("ideal", "tt", [1] * 5, gnd=(0.0, 0.001))]
        ok = dict((n, o) for n, o, _d in g.controls(pts, None))
        self.assertFalse(ok["ideal arm: GND_DIE is exactly 0 V throughout"])


if __name__ == "__main__":
    unittest.main()

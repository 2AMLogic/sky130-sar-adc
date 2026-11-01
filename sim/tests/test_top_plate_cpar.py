"""PDK-free unit tests for sim/top-plate-cpar/run_top_plate_cpar.py (issue #754):
deck editing, request shape, C(V) extraction arithmetic, and one ngspice-gated
check that the AC extraction returns the known value for ideal capacitors."""

from __future__ import annotations

import math
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(SIM_DIR / "top-plate-cpar"))

import run_top_plate_cpar as m  # noqa: E402

DUT = m.DUT_NETLIST.read_text()


class TestDeckEdits(unittest.TestCase):
    def test_remove_exact_instances_only(self):
        for variant, names in m.LEAVE_ONE_OUT.items():
            out = m.variant_netlist(DUT, variant)
            before = {ln.split()[0] for ln in DUT.splitlines() if ln.strip()}
            after = {ln.split()[0] for ln in out.splitlines() if ln.strip()}
            self.assertEqual(before - after, set(names), variant)
            self.assertEqual(after - before, set(), variant)

    def test_all_removed_is_union(self):
        out = m.variant_netlist(DUT, "all-removed")
        for n in m.ALL_REMOVED:
            self.assertNotIn(n, {ln.split()[0] for ln in out.splitlines() if ln.strip()})

    def test_missing_or_duplicate_instance_refused(self):
        with self.assertRaises(RuntimeError):
            m.remove_instances(DUT, ["XNoSuchInstance"])
        with self.assertRaises(RuntimeError):
            m.remove_instances("C1 a b 1f\nC1 a b 1f\n", ["C1"])

    def test_hold_override_hits_once(self):
        out = m.apply_hold_override(DUT)
        self.assertIn("xfe VINP VINN SAMPLE_HOLD ", out)
        self.assertNotIn("xfe VINP VINN SAMPLE_INT ", out)
        with self.assertRaises(RuntimeError):
            m.apply_hold_override("* nothing\n")

    def test_body_has_no_end_or_lib(self):
        body = m.build_body(DUT, "as-committed").lower()
        self.assertNotIn("\n.end\n", body)
        self.assertNotIn(".lib ", body)


class TestRequest(unittest.TestCase):
    def test_corner_set_includes_rc_and_ratified(self):
        ids = m.corner_ids()
        self.assertEqual(len(ids), 13)
        for rc in m.RC_CORNERS:
            self.assertIn(f"{rc}_27c_1.80v", ids)
        self.assertIn("tt_27c_1.62v", ids)

    def test_request_expands_to_exactly_the_wanted_corners(self):
        ids = m.corner_ids()
        req = m.build_request("tb.spice", ids)
        c = req["corners"]
        excl = {(e["process"], e["temperature_c"], e["supply_v"]["vsup"]) for e in req["exclude"]}
        got = {(p, t, v) for p in c["process"] for t in c["temperature_c"]
               for v in c["supply_v"]["vsup"]} - excl
        self.assertEqual(got, {m.parse_corner_id(i) for i in ids})
        self.assertEqual(len(req["analysis_steps"]), 2 * len(m.BIASES_V))


def _pts(c_node, c_array):
    return [{"v": v, "c_node_f": c_node, "c_array_f": c_array, "c_u_f": c_array / 512,
             "c_par_f": c_node - c_array} for v in m.BIASES_V]


class TestArithmetic(unittest.TestCase):
    def test_curve_requires_every_point(self):
        vals = {}
        for v in m.BIASES_V:
            vals[f"{m.step_name('p', v)}.ctop"] = 5e-12
            vals[f"{m.step_name('p', v)}.cref"] = 4.9e-12
        self.assertEqual(len(m.curve(vals, "p")), len(m.BIASES_V))
        vals[f"{m.step_name('p', m.BIASES_V[2])}.cref"] = None
        self.assertIsNone(m.curve(vals, "p"))
        self.assertIsNone(m.curve({}, "n"))

    def test_composition_additive_and_residual(self):
        arr = 5120e-15
        pv = {"as-committed": _pts(arr + 40e-15, arr),
              "no-choff": _pts(arr + 30e-15, arr),
              "no-csamp": _pts(arr + 25e-15, arr),
              "no-msw": _pts(arr + 38e-15, arr),
              "no-cmp-input": _pts(arr + 39e-15, arr),
              "all-removed": _pts(arr + 1e-15, arr)}
        c = m.composition(pv)
        self.assertAlmostEqual(c["contrib_f"]["no-choff"], 10e-15, places=20)
        self.assertAlmostEqual(c["contrib_f"]["no-csamp"], 15e-15, places=20)
        self.assertAlmostEqual(c["sum_delta_f"], 28e-15, places=20)
        self.assertAlmostEqual(c["residual_f"], 12e-15, places=20)
        self.assertAlmostEqual(c["remainder_f"], 1e-15, places=20)
        self.assertAlmostEqual(c["par_cu"], 40e-15 / 10e-15, places=9)


@unittest.skipUnless(shutil.which("ngspice"), "ngspice not installed")
class TestKnownCapacitance(unittest.TestCase):
    """C = -Im(I)/(2 pi f) on a bare ideal capacitor (and two in parallel)."""

    def _c(self, caps):
        deck = ["* known C", "V1 n 0 DC 0 AC 1"]
        deck += [f"C{i} n 0 {c}" for i, c in enumerate(caps)]
        deck += [".control", "ac lin 1 1e4 1e4", "let c = -imag(i(v1))/(2*pi*1e4)",
                 "print c", ".endc", ".end"]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "k.cir"
            p.write_text("\n".join(deck) + "\n")
            out = subprocess.run(["ngspice", "-b", str(p)], capture_output=True, text=True,
                                 cwd=d).stdout
        for ln in out.splitlines():
            if ln.strip().startswith("c ="):
                return float(ln.split("=")[1])
        self.fail(out)

    def test_single_and_parallel(self):
        self.assertTrue(math.isclose(self._c(["10f"]), 10e-15, rel_tol=1e-6))
        self.assertTrue(math.isclose(self._c(["10f", "25f"]), 35e-15, rel_tol=1e-6))


if __name__ == "__main__":
    unittest.main()

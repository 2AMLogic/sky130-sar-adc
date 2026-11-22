"""PDK-free deck-builder call test for sim/cdac-bit-trial-settling/run_bit_trial_settling.py (issue #591).

Same failure class as issue #296 (see test_run_hold_kick.py): a shared-helper
migration can leave a builder calling an undefined name, which only surfaces
when someone runs ngspice with the PDK. This test actually calls the builder
and checks the deck structure; no ngspice, no PDK."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import toolchain  # noqa: E402


RUNNER = SIM_DIR / "cdac-bit-trial-settling/run_bit_trial_settling.py"
_spec = importlib.util.spec_from_file_location("run_bit_trial_settling_under_test", RUNNER)
rt = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rt
_spec.loader.exec_module(rt)


class TestBuildTransient(unittest.TestCase):
    def test_both_directions_return_deck_and_analytics(self):
        for direction in ("fall", "rise"):
            with self.subTest(direction=direction):
                deck, analytics = rt.build_transient(test_bit=8, direction=direction)
                self.assertIsInstance(deck, str)
                self.assertIn(".control", deck)
                self.assertIn("\ntran ", deck)
                self.assertIn(".end", deck)
                self.assertIn(".lib", deck)
                self.assertIsInstance(analytics, dict)
                self.assertTrue(analytics)

    def test_non_default_corner_and_window(self):
        deck, _ = rt.build_transient(
            test_bit=0, direction="rise", corner="ss", temp_c=-40.0,
            vdd=1.62, tran_stop_ns=rt.CORNERS_TRAN_STOP_NS,
        )
        self.assertIn(".control", deck)
        self.assertIn("\ntran ", deck)

    def test_bad_direction_raises_value_error(self):
        with self.assertRaises(ValueError):
            rt.build_transient(test_bit=8, direction="sideways")


class TestToolchainWarningsReachTheOperator(unittest.TestCase):
    """This driver used to drop check_env()'s warnings on the floor.

    Before issue #854 its inline gate read only `check.status` and
    `check.messages`, never `check.warnings` -- so a run on a machine with
    an xschem version mismatch, or with a PDK install whose commit
    provenance cannot be verified ("evidence records from this install are
    marked unverified"), proceeded silently. Folding the gate into
    `toolchain.preflight()` fixes that; this test drives the real `main()`
    far enough to see the warning on stdout.

    No ngspice and no PDK: check_env() is patched, and `run_all()` (the first batch of ngspice runs) is
    stubbed to stop the run the moment the gate has let it through.
    """

    class _ReachedTheRun(Exception):
        """Raised by the stub below -- proof the gate returned None."""

    def test_a_check_env_warning_is_printed_before_the_run_starts(self):
        ok_with_warning = toolchain.CheckResult(
            status=0,
            warnings=["PDK commit provenance unverifiable at /fake/sky130A"],
        )
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["run_bit_trial_settling.py"]), \
                mock.patch.object(rt.toolchain, "check_env", return_value=ok_with_warning), \
                mock.patch.object(rt, "run_all", side_effect=self._ReachedTheRun), \
                contextlib.redirect_stdout(buf):
            with self.assertRaises(self._ReachedTheRun):
                rt.main()
        self.assertIn(
            "WARNING: PDK commit provenance unverifiable at /fake/sky130A",
            buf.getvalue(),
        )

    def test_a_missing_toolchain_still_skips_with_exit_zero(self):
        """The gate's exit codes are unchanged by the migration."""
        missing = toolchain.CheckResult(status=3, messages=["ngspice not found on PATH"])
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["run_bit_trial_settling.py"]), \
                mock.patch.object(rt.toolchain, "check_env", return_value=missing), \
                mock.patch.object(rt, "run_all", side_effect=self._ReachedTheRun), \
                contextlib.redirect_stdout(buf):
            self.assertEqual(rt.main(), 0)
        self.assertIn("ngspice not found on PATH", buf.getvalue())

    def test_toolchain_drift_still_fails_with_exit_one(self):
        drift = toolchain.CheckResult(status=1, messages=["installed PDK commit 'abc' != pinned 'def'"])
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["run_bit_trial_settling.py"]), \
                mock.patch.object(rt.toolchain, "check_env", return_value=drift), \
                mock.patch.object(rt, "run_all", side_effect=self._ReachedTheRun), \
                contextlib.redirect_stdout(buf):
            self.assertEqual(rt.main(), 1)
        self.assertIn("installed PDK commit 'abc' != pinned 'def'", buf.getvalue())


if __name__ == "__main__":
    unittest.main()


class TestDR027CandidateGeometry(unittest.TestCase):
    """issue #1033: the candidate deck is the SAME reduction at the 3.3000 um
    plate -- 512 unit positions per side including the termination unit, the
    ORIGINAL switch sizes and binary weights -- as six independent copies."""

    def test_every_capacitor_uses_the_candidate_plate_with_original_weights(self):
        body = rt.build_candidate_body()
        cap_lines = [
            ln for ln in body.splitlines()
            if ln.upper().startswith("XC") and "cap_mim_m3_1" in ln
        ]
        self.assertEqual(len(cap_lines), 60, "6 copies x 10 caps (9 bits + term)")
        for ln in cap_lines:
            self.assertIn(
                f"W={rt.CANDIDATE_UNIT_CAP_WL_UM:.4f} L={rt.CANDIDATE_UNIT_CAP_WL_UM:.4f}",
                ln,
            )
        # weights unchanged: MF sums to 511 + 1 termination per copy
        for tag in ("b0f", "b4r", "b8r"):
            mfs = [
                int(ln.split("MF=")[1].split()[0]) for ln in cap_lines
                if f"_{tag} " in ln
            ]
            self.assertEqual(sum(mfs), 512)
            self.assertEqual(len(mfs), 10)

    def test_switch_sizes_are_the_original_ones(self):
        body = rt.build_candidate_body()
        self.assertIn(
            f"sky130_fd_pr__nfet_01v8 L={rt.SWITCH_NFET_WL[1]:g} "
            f"W={rt.SWITCH_NFET_WL[0]:g} nf=1", body,
        )
        self.assertIn(
            f"sky130_fd_pr__pfet_01v8 L={rt.SWITCH_PFET_WL[1]:g} "
            f"W={rt.SWITCH_PFET_WL[0]:g} nf=1", body,
        )
        self.assertEqual(body.count("Xn_bit"), 6)
        self.assertEqual(body.count("Xp_bit"), 6)
        # termination unit present per copy, hardwired to the VREFN rail
        self.assertEqual(body.count("Xc_term"), 6)

    def test_candidate_plate_is_experimental_and_not_the_production_one(self):
        self.assertEqual(rt.CANDIDATE_UNIT_CAP_WL_UM, 3.3000)
        self.assertEqual(rt.UNIT_CAP_WL_UM, 1.9000)  # the default path is untouched
        self.assertIn("EXPERIMENTAL", rt.build_candidate_body())

    def test_copies_do_not_share_nodes_or_device_names(self):
        """Six copies in one body is only equivalent to six separate decks if
        they share nothing but the ideal rails -- enforced structurally on
        the device names (uniqueness; ngspice is case-insensitive, so a
        colliding pair was a real failure class during this mode's bring-up).
        """
        body = rt.build_candidate_body()
        names = [
            ln.split()[0].lower() for ln in body.splitlines()
            if ln and not ln.startswith(("*", ".", "+"))
        ]
        self.assertEqual(len(names), len(set(names)),
                         "every device name must be unique")
        # six independent top-plate nodes: one reset switch + leak + normalised
        # copy per copy, and no TOP_x node shared between copies
        self.assertEqual(body.count("Sreset_"), 6)
        self.assertEqual(body.count("Rdc_"), 6)
        self.assertEqual(body.count("Bnorm_"), 6)
        top_tokens = set()
        for ln in body.splitlines():
            if ln.upper().startswith("XC") and "cap_mim_m3_1" in ln:
                top_tokens.add(ln.split()[2])
        self.assertEqual(len(top_tokens), 6)

    def test_body_is_a_circuit_body_not_a_deck(self):
        body = rt.build_candidate_body()
        for line in body.splitlines():
            self.assertFalse(
                line.startswith((".control", ".tran", ".meas", ".lib", ".temp", ".end")),
                f"circuit body must not carry analysis cards: {line}",
            )


class TestDR027CandidateEndpointWindows(unittest.TestCase):
    """issue #1033: the endpoint measurement windows must place BOTH DR-006
    deadlines strictly inside them, with the fast window sized to the
    candidate's ~2.83x-slower settling."""

    def test_deadlines_are_the_draft_row_endpoints(self):
        self.assertAlmostEqual(rt.CAND_DEADLINE_FAST_NS, rt.T_PHASE_WORST_NS, places=9)
        self.assertAlmostEqual(rt.CAND_DEADLINE_SLOW_NS, rt.T_PHASE_SLOW_NS, places=9)
        self.assertAlmostEqual(rt.CAND_DEADLINE_FAST_NS, 1000.0 / 12.0, places=9)
        self.assertAlmostEqual(rt.CAND_DEADLINE_SLOW_NS, 1000.0 / 1.2, places=9)

    def test_each_deadline_falls_inside_its_step_window(self):
        self.assertLess(rt.CAND_DEADLINE_FAST_NS, rt.CAND_FAST_TRAN_STOP_NS)
        self.assertLess(rt.CAND_DEADLINE_SLOW_NS, rt.CAND_SLOW_TRAN_STOP_NS)
        self.assertLess(rt.CAND_LATE_AT_NS, rt.CAND_SLOW_TRAN_STOP_NS)
        # fast window keeps >= 2.5x margin over the C_u-ratio prediction
        # (13.2466 ns binding at 1.9 um x the 23.805/8.405 C_u ratio)
        predicted_worst_ns = 13.2466 * (23.805 / 8.405)
        self.assertGreaterEqual(
            rt.CAND_FAST_TRAN_STOP_NS / predicted_worst_ns, 2.5,
        )

    def test_crossing_thresholds_are_corner_independent_constants(self):
        steps = {s["name"]: s for s in rt.candidate_analysis_steps()}
        meas = {m["name"]: m for m in steps["fast"]["measurements"]}
        for bit, direction in rt.candidate_copies():
            tag = rt.candidate_tag(bit, direction)
            ratio = rt.candidate_ratio(bit)
            sign = 1.0 if direction == "rise" else -1.0
            for frac in rt.FRACTIONS:
                card = meas[f"t{int(frac * 100)}_{tag}"]["spice"]
                self.assertIn(f"VAL={sign * frac * ratio:.9f}", card)
                # read on the NORMALIZED node, not the raw top plate
                self.assertIn(f"TARG V(NORM_{tag})", card)
                self.assertIn("TRIG AT=1n", card)

    def test_phase_end_reads_cover_both_deadlines_and_a_late_read(self):
        steps = {s["name"]: s for s in rt.candidate_analysis_steps()}
        fast = " ".join(m["spice"] for m in steps["fast"]["measurements"])
        slow = " ".join(m["spice"] for m in steps["slow"]["measurements"])
        self.assertIn(f"at={rt.EDGE_TD_NS + rt.CAND_DEADLINE_FAST_NS:.6f}n", fast)
        self.assertIn(f"at={rt.EDGE_TD_NS + rt.CAND_DEADLINE_SLOW_NS:.6f}n", slow)
        self.assertIn(f"at={rt.CAND_LATE_AT_NS:.6f}n", slow)

    def test_measurement_names_never_collide_with_node_names(self):
        """The ngspice measurement-name/node collision (klt-sim #5446): a
        measurement named after a node overwrites that node's vector."""
        nodes = set()
        for line in rt.build_candidate_body().splitlines():
            if line and line[0].isalpha() and not line.startswith("*"):
                for tok in line.split()[1:]:
                    nodes.add(tok.split("[")[0].split(":")[0])
        for s in rt.candidate_analysis_steps():
            for m in s["measurements"]:
                self.assertNotIn(m["name"], nodes)

    def test_closed_form_reader_uses_the_corner_supply(self):
        rows = rt.candidate_rows({}, 1.8)
        self.assertEqual(len(rows), 6)
        for row in rows:
            span = -1.8 if row["direction"] == "fall" else 1.8
            self.assertAlmostEqual(
                row["v_final_ideal"], 0.9 + row["ratio"] * span, places=9,
            )
            self.assertIsNone(row["t99_ns"], "a missing crossing is retained as None")


class TestDR027CandidateRequest(unittest.TestCase):
    def test_one_request_shapes_the_oat_grid_via_exclude(self):
        cids = rt.candidate_corner_ids()
        req = rt.build_candidate_request("tb.spice", cids)
        self.assertEqual(len(cids), 9)
        self.assertEqual(len(req["exclude"]), 45 - 9)
        self.assertEqual(len(req["corners"]["process"]), 5)
        self.assertEqual(req["corners"]["supply_v"], {rt.CAND_SUPPLY_KEY: [1.62, 1.8, 1.98]})
        self.assertEqual(len(req["analysis_steps"]), 2)
        for s in req["analysis_steps"]:
            self.assertTrue(s["reset"])
            self.assertTrue(s["measurements"])

    def test_unit_cap_probe_deck_grounded_far_plate(self):
        """The probe's far plate must be grounded: the first version of this
        probe left it floating through a leak and measured the leak."""
        deck = rt.unit_cap_probe_deck(rt.CANDIDATE_UNIT_CAP_WL_UM)
        self.assertIn("Xc BOT 0 sky130_fd_pr__cap_mim_m3_1", deck)
        self.assertNotIn("BOT TOP", deck)


class TestReviewFixes(unittest.TestCase):
    def test_reads_are_measured_from_the_sel_edge(self):
        steps = {s["name"]: s for s in rt.candidate_analysis_steps()}
        fast = " ".join(m["spice"] for m in steps["fast"]["measurements"])
        self.assertIn("at=84.333333n", fast)
        slow = " ".join(m["spice"] for m in steps["slow"]["measurements"])
        self.assertIn("at=834.333333n", slow)

    def test_missing_fixed_time_read_makes_corner_incomplete(self):
        report_vals = {}
        rows = rt.candidate_rows(report_vals, 1.8)
        self.assertTrue(all(r["plate_err_mv"] is None for r in rows))

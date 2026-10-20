"""PDK-free, ngspice-free tests for the exit-code contract of
sim/harness/cli.py (run_corners.py) and sim/harness/mc_cli.py (monte_carlo.py).

All collaborators (runner, toolchain, pdk, testbench, mc_runner) are mocked;
nothing here touches ngspice or an installed PDK. Pins CURRENT behavior:
unknown experiment returns 1 (not 2); 2 is for usage errors only."""

from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import cli, mc_cli  # noqa: E402


def _run(main, argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


class TestCornerCli(unittest.TestCase):
    def setUp(self):
        self.manifest = SimpleNamespace(name="exp")
        patches = {
            "runner": mock.patch.object(cli, "runner"),
            "toolchain": mock.patch.object(cli, "toolchain"),
            "pdk": mock.patch.object(cli, "pdk"),
            "testbench": mock.patch.object(cli, "testbench"),
        }
        for k, p in patches.items():
            setattr(self, k, p.start())
            self.addCleanup(p.stop)
        self.testbench.load_experiment.return_value = self.manifest
        self.runner.write_evidence.return_value = "sim/exp/records/r.json"
        self._set_result(True)

    def _set_result(self, ok):
        self.result = SimpleNamespace(overall_ok=ok, record_id="rid-1")
        self.runner.run.return_value = (self.result, {"axis": 1})

    def test_print_env(self):
        self.pdk.print_env.return_value = "export PDK_ROOT=/x\n"
        rc, out, _ = _run(cli.main, ["--print-env"])
        self.assertEqual(rc, 0)
        self.assertEqual(out, "export PDK_ROOT=/x\n")
        self.pdk.resolve.assert_called_once_with()
        self.pdk.print_env.assert_called_once_with(self.pdk.resolve.return_value)
        self.runner.run.assert_not_called()

    def test_list(self):
        self.testbench.experiments.return_value = ["a", "b"]
        rc, out, _ = _run(cli.main, ["--list"])
        self.assertEqual(rc, 0)
        self.assertEqual(out.splitlines(), ["a", "b"])

    def test_check_env_returns_status_verbatim(self):
        for status in (0, 1, 3):
            with self.subTest(status=status):
                self.toolchain.check_env.return_value = SimpleNamespace(
                    status=status, warnings=["w1"], messages=["m1"]
                )
                self.toolchain.summary.return_value = "SUMMARY"
                rc, out, _ = _run(cli.main, ["--check-env"])
                self.assertEqual(rc, status)
                self.assertIn("SUMMARY", out)
                self.assertIn("warning: w1", out)
                self.assertIn("- m1", out)
                self.toolchain.check_env.assert_called_with(allow_drift=False)

    def test_check_env_forwards_allow_drift(self):
        self.toolchain.check_env.return_value = SimpleNamespace(status=0, warnings=[], messages=[])
        rc, _, _ = _run(cli.main, ["--check-env", "--allow-toolchain-drift"])
        self.assertEqual(rc, 0)
        self.toolchain.check_env.assert_called_once_with(allow_drift=True)

    def test_no_experiment_prints_help_returns_2(self):
        rc, out, _ = _run(cli.main, [])
        self.assertEqual(rc, 2)
        self.assertIn("usage:", out)
        self.runner.run.assert_not_called()

    def test_unknown_experiment_returns_1_with_stderr(self):
        self.testbench.load_experiment.side_effect = FileNotFoundError("manifest.toml")
        rc, _, err = _run(cli.main, ["nope"])
        self.assertEqual(rc, 1)
        self.assertIn("no such experiment 'nope'", err)
        self.runner.run.assert_not_called()

    def test_overall_pass_returns_0(self):
        rc, out, _ = _run(cli.main, ["exp"])
        self.assertEqual(rc, 0)
        self.assertIn("PASS: exp (rid-1)", out)

    def test_overall_fail_returns_1(self):
        self._set_result(False)
        rc, out, _ = _run(cli.main, ["exp"])
        self.assertEqual(rc, 1)
        self.assertIn("FAIL: exp (rid-1)", out)

    def test_defaults_forwarded(self):
        _run(cli.main, ["exp"])
        self.runner.run.assert_called_once_with(
            self.manifest,
            process_corners=None,
            temperatures_c=None,
            supply_tolerance=None,
            sabotage=False,
            quiet=False,
        )
        self.runner.write_evidence.assert_not_called()

    def test_sabotage_corners_forwarded(self):
        _run(cli.main, ["exp", "--sabotage-corners"])
        self.assertTrue(self.runner.run.call_args.kwargs["sabotage"])

    def test_sabotage_negative_control_failure_exit(self):
        # Sabotaged run is expected to FAIL the verdict -> exit 1.
        self._set_result(False)
        rc, _, _ = _run(cli.main, ["exp", "--sabotage-corners", "--quiet"])
        self.assertEqual(rc, 1)

    def test_corners_temps_supply_tol_parsed_and_forwarded(self):
        _run(cli.main, ["exp", "--corners", "tt,ss", "--temps=-40,27.5,125",
                        "--supply-tol", "0.1", "--quiet"])
        kw = self.runner.run.call_args.kwargs
        self.assertEqual(kw["process_corners"], ["tt", "ss"])
        self.assertEqual(kw["temperatures_c"], [-40.0, 27.5, 125.0])
        self.assertEqual(kw["supply_tolerance"], 0.1)
        self.assertTrue(kw["quiet"])

    def test_record_writes_evidence_and_prints_path(self):
        rc, out, _ = _run(cli.main, ["exp", "--record", "--note", "n", "--supersedes", "old"])
        self.assertEqual(rc, 0)
        self.runner.write_evidence.assert_called_once_with(
            self.result, {"axis": 1}, note="n", supersedes="old"
        )
        self.assertIn("wrote sim/exp/records/r.json", out)

    def test_record_with_quiet_still_prints_path_but_no_verdict(self):
        rc, out, _ = _run(cli.main, ["exp", "--record", "--quiet"])
        self.assertEqual(rc, 0)
        self.assertIn("wrote sim/exp/records/r.json", out)
        self.assertNotIn("PASS", out)

    def test_record_does_not_change_exit_on_fail(self):
        self._set_result(False)
        rc, _, _ = _run(cli.main, ["exp", "--record", "--quiet"])
        self.assertEqual(rc, 1)
        self.runner.write_evidence.assert_called_once()

    def test_bad_flag_is_usage_error_2(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                cli.main(["--bogus"])
        self.assertEqual(cm.exception.code, 2)

    def test_bad_type_is_usage_error_2(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                cli.main(["exp", "--supply-tol", "abc"])
        self.assertEqual(cm.exception.code, 2)


class TestMonteCarloCli(unittest.TestCase):
    def setUp(self):
        self.manifest = SimpleNamespace(
            nominal_supply_v=1.8, measure={"m1": 1, "m2": 2}, checks=["chk"]
        )
        self.mc_runner = mock.patch.object(mc_cli, "mc_runner").start()
        self.testbench = mock.patch.object(mc_cli, "testbench").start()
        self.addCleanup(mock.patch.stopall)
        self.testbench.load_experiment.return_value = self.manifest
        self.mc_runner.run.return_value = SimpleNamespace(draws=[])
        self.mc_runner.write_evidence.return_value = "sim/exp/records/mc.json"
        self.mc_runner.distributions.return_value = {
            "m1": SimpleNamespace(n=8, mean=1.0, stdev=0.1, minimum=0.8, maximum=1.2)
        }
        self._controls(True, True)

    def _controls(self, neg, pos):
        self.mc_runner.negative_control_ok.return_value = (neg, [] if neg else ["neg-bad"])
        self.mc_runner.positive_control_ok.return_value = (pos, [] if pos else ["pos-bad"])

    def test_list(self):
        self.testbench.experiments.return_value = ["x", "y"]
        rc, out, _ = _run(mc_cli.main, ["--list"])
        self.assertEqual(rc, 0)
        self.assertEqual(out.splitlines(), ["x", "y"])

    def test_no_experiment_prints_help_returns_2(self):
        rc, out, _ = _run(mc_cli.main, [])
        self.assertEqual(rc, 2)
        self.assertIn("usage:", out)
        self.mc_runner.run.assert_not_called()

    def test_n_below_2_returns_2(self):
        for n in ("1", "0", "-3"):
            with self.subTest(n=n):
                rc, _, err = _run(mc_cli.main, ["exp", f"--n={n}"])
                self.assertEqual(rc, 2)
                self.assertIn("--n must be >= 2", err)
        self.mc_runner.run.assert_not_called()

    def test_n_2_is_accepted(self):
        rc, _, _ = _run(mc_cli.main, ["exp", "--n", "2"])
        self.assertEqual(rc, 0)

    def test_unknown_experiment_returns_1(self):
        self.testbench.load_experiment.side_effect = FileNotFoundError("manifest.toml")
        rc, _, err = _run(mc_cli.main, ["nope"])
        self.assertEqual(rc, 1)
        self.assertIn("no such experiment 'nope'", err)
        self.mc_runner.run.assert_not_called()

    def test_control_combinations(self):
        cases = [(True, True, 0), (True, False, 1), (False, True, 1), (False, False, 1)]
        for neg, pos, expected in cases:
            with self.subTest(neg=neg, pos=pos):
                self._controls(neg, pos)
                rc, out, _ = _run(mc_cli.main, ["exp"])
                self.assertEqual(rc, expected)
                self.assertIn("negative control: " + ("PASS" if neg else "FAIL: neg-bad"), out)
                self.assertIn(
                    "positive control (mismatch draws must vary): "
                    + ("PASS" if pos else "FAIL: pos-bad"),
                    out,
                )

    def test_control_checks_called_with_manifest_names(self):
        result = self.mc_runner.run.return_value
        _run(mc_cli.main, ["exp"])
        self.mc_runner.negative_control_ok.assert_called_once_with(result, ["m1", "m2"])
        self.mc_runner.positive_control_ok.assert_called_once_with(result, ["m1", "m2"], ["chk"])

    def test_defaults_and_supply_from_manifest(self):
        _run(mc_cli.main, ["exp"])
        self.mc_runner.run.assert_called_once_with(
            self.manifest, process_corner="tt", temp_c=27.0, supply_v=1.8,
            seed=1, n=10, quiet=False,
        )

    def test_explicit_args_forwarded(self):
        _run(mc_cli.main, ["exp", "--corner", "ss", "--temp", "125", "--supply", "1.62",
                           "--seed", "7", "--n", "8", "--quiet"])
        self.mc_runner.run.assert_called_once_with(
            self.manifest, process_corner="ss", temp_c=125.0, supply_v=1.62,
            seed=7, n=8, quiet=True,
        )

    def test_record_writes_evidence(self):
        rc, out, _ = _run(mc_cli.main, ["exp", "--record", "--note", "n", "--supersedes", "old"])
        self.assertEqual(rc, 0)
        self.mc_runner.write_evidence.assert_called_once_with(
            self.mc_runner.run.return_value, note="n", supersedes="old"
        )
        self.assertIn("wrote sim/exp/records/mc.json", out)

    def test_record_not_called_by_default(self):
        _run(mc_cli.main, ["exp"])
        self.mc_runner.write_evidence.assert_not_called()

    def test_record_with_quiet_and_failed_control(self):
        self._controls(True, False)
        rc, out, _ = _run(mc_cli.main, ["exp", "--record", "--quiet"])
        self.assertEqual(rc, 1)
        self.assertIn("wrote sim/exp/records/mc.json", out)
        self.assertNotIn("negative control", out)

    def test_quiet_suppresses_distribution_output(self):
        rc, out, _ = _run(mc_cli.main, ["exp", "--quiet"])
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_nonquiet_prints_distribution(self):
        _, out, _ = _run(mc_cli.main, ["exp"])
        self.assertIn("m1: N=8 mean=1 stdev=0.1 min=0.8 max=1.2", out)

    def test_bad_flag_is_usage_error_2(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                mc_cli.main(["--sabotage-corners"])
        self.assertEqual(cm.exception.code, 2)

    def test_bad_type_is_usage_error_2(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                mc_cli.main(["exp", "--n", "many"])
        self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

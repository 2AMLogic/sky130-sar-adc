"""PDK-free deck-builder call test for sim/sampling-frontend/run_transient.py (issue #591).

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


RUNNER = SIM_DIR / "sampling-frontend/run_transient.py"
_spec = importlib.util.spec_from_file_location("run_transient_under_test", RUNNER)
rt = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rt
_spec.loader.exec_module(rt)


class TestBuildNetlist(unittest.TestCase):
    def test_returns_deck_with_tran(self):
        deck = rt.build_netlist(vinp=1.6, vinn=0.2, corner="tt")
        self.assertIsInstance(deck, str)
        self.assertIn(".control", deck)
        self.assertIn("\ntran ", deck)
        self.assertIn(".end", deck)
        self.assertIn(".lib", deck)

    def test_other_corner_and_temp(self):
        deck = rt.build_netlist(vinp=0.2, vinn=1.6, corner="ff", temp_c=-40.0)
        self.assertIn(".temp -40.0", deck)


class TestToolchainWarningsReachTheOperator(unittest.TestCase):
    """This driver used to drop check_env()'s warnings on the floor.

    Before issue #854 its inline gate read only `check.status` and
    `check.messages`, never `check.warnings` -- so a run on a machine with
    an xschem version mismatch, or with a PDK install whose commit
    provenance cannot be verified ("evidence records from this install are
    marked unverified"), proceeded silently. Folding the gate into
    `toolchain.preflight()` fixes that; this test drives the real `main()`
    far enough to see the warning on stdout.

    No ngspice and no PDK: check_env() is patched, and `run_point()` (the first per-test-point ngspice call) is
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
        with mock.patch.object(sys, "argv", ["run_transient.py"]), \
                mock.patch.object(rt.toolchain, "check_env", return_value=ok_with_warning), \
                mock.patch.object(rt, "run_point", side_effect=self._ReachedTheRun), \
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
        with mock.patch.object(sys, "argv", ["run_transient.py"]), \
                mock.patch.object(rt.toolchain, "check_env", return_value=missing), \
                mock.patch.object(rt, "run_point", side_effect=self._ReachedTheRun), \
                contextlib.redirect_stdout(buf):
            self.assertEqual(rt.main(), 0)
        self.assertIn("ngspice not found on PATH", buf.getvalue())

    def test_toolchain_drift_still_fails_with_exit_one(self):
        drift = toolchain.CheckResult(status=1, messages=["installed PDK commit 'abc' != pinned 'def'"])
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["run_transient.py"]), \
                mock.patch.object(rt.toolchain, "check_env", return_value=drift), \
                mock.patch.object(rt, "run_point", side_effect=self._ReachedTheRun), \
                contextlib.redirect_stdout(buf):
            self.assertEqual(rt.main(), 1)
        self.assertIn("installed PDK commit 'abc' != pinned 'def'", buf.getvalue())


if __name__ == "__main__":
    unittest.main()

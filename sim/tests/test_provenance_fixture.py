"""Tests for `sim/tests/provenance_fixture.py`, plus the structural guard that
keeps it the only `evidence.resolve_provenance` stub in `sim/tests/` (issue
#914).

The behaviour tests come first: the fixture's whole value is that thirteen
call sites now depend on it, so what it does to `experiment_dir`, what it
reports, and -- above all -- that it restores both patched names on the way
out are pinned here rather than inferred from the suites that use it.

`TestNoTestFileKeepsItsOwnProvenanceStub` is the structural half, modelled on
`sim/tests/test_harness_klt_sim.py`'s driver-side guard (and on the same
reasoning `sim/README.md` records for it): the thirteen copies were not a
design, they were what happened when each new record-writer test had no shared
fixture to import, and each assertion below is one property the copies had
already lost or were free to lose. A fourteenth copy fails here.
"""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
SIM_DIR = TESTS_DIR.parent
sys.path.insert(0, str(SIM_DIR))

import provenance_fixture  # noqa: E402
from harness import evidence  # noqa: E402

#: The record-writer test files consolidated onto the fixture by issue #914,
#: plus `test_harness.py`, whose own factory was folded in with them. Asserted
#: as a lower bound (not an equality) so a new file joining them is fine.
CONSOLIDATED = {
    "test_dynamic_enob_fft.py",
    "test_full_conversion.py",
    "test_harness.py",
    "test_run_vcm_drive_budget.py",
    "test_solver_policy.py",
    "test_supply_impedance.py",
}


class _Campaign:
    """Stand-in for a campaign module, which the context manager redirects by
    rebinding its module-level `EXPERIMENT_DIR`."""

    EXPERIMENT_DIR = Path("/nonexistent/real/experiment/dir")


class TestMakeFakeResolve(unittest.TestCase):
    def test_it_does_the_real_helpers_filesystem_work(self):
        """The directories and the snapshot are production behaviour: the stub
        calls `evidence.write_netlist_snapshot_text()`, the same helper the
        real `resolve_provenance()` calls."""
        fake = provenance_fixture.make_fake_resolve()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            info = fake(tmp_dir, "* deck\n")
            self.assertTrue((tmp_dir / "records").is_dir())
            snapshot = tmp_dir / "netlist-snapshots" / "REC.spice"
            self.assertTrue(snapshot.is_file())
            self.assertEqual(snapshot.read_text(), "* deck\n")
            self.assertEqual(info.record_path, tmp_dir / "records" / "REC.md")

    def test_it_reports_the_documented_constants(self):
        fake = provenance_fixture.make_fake_resolve()
        with tempfile.TemporaryDirectory() as tmp:
            info = fake(Path(tmp), "* deck\n")
        self.assertEqual(info.record_id, "REC")
        self.assertEqual(info.netlist_sha, "0" * 64)
        self.assertEqual(info.pdk_line, "sky130A @ testing")
        self.assertEqual(info.ng_version, "ngspice-46")

    def test_every_constant_is_overridable(self):
        fake = provenance_fixture.make_fake_resolve(
            record_id="OTHER", netlist_sha="f" * 64,
            pdk_line="sky130B @ elsewhere", ng_version="ngspice-47",
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            info = fake(tmp_dir, "* deck\n")
            self.assertTrue((tmp_dir / "netlist-snapshots" / "OTHER.spice").is_file())
        self.assertEqual(info.record_id, "OTHER")
        self.assertEqual(info.record_path, tmp_dir / "records" / "OTHER.md")
        self.assertEqual(info.netlist_sha, "f" * 64)
        self.assertEqual(info.pdk_line, "sky130B @ elsewhere")
        self.assertEqual(info.ng_version, "ngspice-47")

    def test_seen_records_every_netlist_in_call_order(self):
        seen: list[str] = []
        fake = provenance_fixture.make_fake_resolve(seen=seen)
        with tempfile.TemporaryDirectory() as tmp:
            for deck in ("* first\n", "* second\n"):
                fake(Path(tmp), deck)
        self.assertEqual(seen, ["* first\n", "* second\n"])

    def test_the_default_ngspice_version_is_the_one_the_suite_asserts_on(self):
        """`test_harness.py` asserts the stubbed `ng_version` by literal, so
        that assertion pins this constant -- the asymmetry issue #914 names
        (the consolidated site pinned it while the inline copies wandered, one
        of them onto `ngspice-47`). If the default moves, that assertion must
        move with it, which is only true while the two agree here."""
        asserted = re.findall(
            r'assertEqual\(info\.ng_version, "([^"]+)"\)',
            (TESTS_DIR / "test_harness.py").read_text(),
        )
        self.assertTrue(asserted, "test_harness.py no longer asserts ng_version")
        self.assertEqual(set(asserted), {provenance_fixture.NG_VERSION})


class TestFakeProvenanceContextManager(unittest.TestCase):
    def test_it_redirects_the_modules_experiment_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            with provenance_fixture.fake_provenance(_Campaign, tmp_dir):
                self.assertEqual(_Campaign.EXPERIMENT_DIR, tmp_dir)

    def test_it_installs_the_stub_and_yields_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            with provenance_fixture.fake_provenance(_Campaign, Path(tmp)) as fake:
                self.assertIs(evidence.resolve_provenance, fake)
                info = evidence.resolve_provenance(Path(tmp), "* deck\n")
        self.assertEqual(info.record_id, "REC")

    def test_kwargs_reach_the_stub(self):
        seen: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            with provenance_fixture.fake_provenance(
                _Campaign, Path(tmp), ng_version="ngspice-47", seen=seen
            ):
                info = evidence.resolve_provenance(Path(tmp), "* deck\n")
        self.assertEqual(info.ng_version, "ngspice-47")
        self.assertEqual(seen, ["* deck\n"])

    def test_both_names_are_restored_on_a_clean_exit(self):
        real_dir, real_resolve = _Campaign.EXPERIMENT_DIR, evidence.resolve_provenance
        with tempfile.TemporaryDirectory() as tmp:
            with provenance_fixture.fake_provenance(_Campaign, Path(tmp)):
                pass
        self.assertEqual(_Campaign.EXPERIMENT_DIR, real_dir)
        self.assertIs(evidence.resolve_provenance, real_resolve)

    def test_both_names_are_restored_when_the_body_raises(self):
        """The property the thirteen hand-written `try:`/`finally:` pairs each
        had to re-establish: a writer that raises must not leave the real
        `sim/<campaign>/` directory redirected at a deleted temp dir for every
        later test in the process."""
        real_dir, real_resolve = _Campaign.EXPERIMENT_DIR, evidence.resolve_provenance
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                with provenance_fixture.fake_provenance(_Campaign, Path(tmp)):
                    raise ValueError("writer blew up")
        self.assertEqual(_Campaign.EXPERIMENT_DIR, real_dir)
        self.assertIs(evidence.resolve_provenance, real_resolve)

    def test_it_accepts_a_str_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            with provenance_fixture.fake_provenance(_Campaign, tmp):
                self.assertEqual(_Campaign.EXPERIMENT_DIR, Path(tmp))


class TestNoTestFileKeepsItsOwnProvenanceStub(unittest.TestCase):
    """Issue #914: the record-writer tests import the stub, they do not
    re-copy it.

    Discovered by content over every `sim/tests/test_*.py`, never a hand-kept
    list, so a new test file is covered the day it is written.
    """

    @staticmethod
    def _test_files() -> list[Path]:
        return [p for p in sorted(TESTS_DIR.glob("test_*.py"))
                if p.name != Path(__file__).name]

    def test_the_consolidated_files_import_the_fixture(self):
        importers = {p.name for p in self._test_files()
                     if "import provenance_fixture" in p.read_text()}
        self.assertLessEqual(CONSOLIDATED, importers,
                             f"scan found only {sorted(importers)}")

    def test_no_test_file_defines_its_own_fake_resolve(self):
        for p in self._test_files():
            with self.subTest(test_file=p.name):
                self.assertNotRegex(
                    p.read_text(), r"\bdef _?fake_resolve\b",
                    "call provenance_fixture.make_fake_resolve() instead")

    def test_no_test_file_builds_its_own_provenance_info(self):
        """Constructing `ProvenanceInfo` by hand is the stub's tell: it is the
        five-field literal the copies drifted inside of."""
        for p in self._test_files():
            with self.subTest(test_file=p.name):
                self.assertNotIn(
                    "evidence.ProvenanceInfo(", p.read_text(),
                    "provenance_fixture owns the stubbed ProvenanceInfo")

    def test_no_test_file_assigns_resolve_provenance_by_hand(self):
        """A bare assignment is what needs a hand-written `finally:` to undo;
        the fixture installs with `mock.patch.object`, which cannot be
        forgotten."""
        for p in self._test_files():
            with self.subTest(test_file=p.name):
                self.assertNotRegex(
                    p.read_text(),
                    r"\bevidence\.resolve_provenance\s*=\s*[^=]",
                    "install it with provenance_fixture.fake_provenance()")

    def test_no_test_file_rebinds_a_campaigns_experiment_dir_by_hand(self):
        """The other half of the same save/restore pair. A module-level
        `EXPERIMENT_DIR = ...` constant is fine; `<module>.EXPERIMENT_DIR =
        ...` is the redirect the context manager owns."""
        for p in self._test_files():
            with self.subTest(test_file=p.name):
                self.assertNotRegex(
                    p.read_text(),
                    r"(?m)^\s*\w+(?:\.\w+)*\.EXPERIMENT_DIR\s*=\s*[^=]",
                    "redirect it with provenance_fixture.fake_provenance()")


if __name__ == "__main__":
    unittest.main()

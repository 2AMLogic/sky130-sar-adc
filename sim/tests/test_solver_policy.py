"""PDK-free unit tests for the full-conversion transient solver policy and the
DC baseline solver-sensitivity audit (issue #637,
spec/decision-records/DR-023-full-conversion-transient-solver-policy.md).

What is pinned here, because a five-minute-per-run simulation is the wrong
place to discover it:

1. Each named solver profile adds EXACTLY its intended `.options` card at
   deck assembly and nothing else; the reference profile adds nothing.
2. Every flag combination that would let a control profile stand in for
   reference evidence is refused BEFORE the toolchain is checked or anything
   is simulated.
3. A control record never moves `records/LATEST` and can never carry a
   **Supersedes** pointer -- refused in the writer itself, not only at the CLI.
4. The audit compares like with like (same instrumentation under every
   profile), names every moved observation, and its record supersedes nothing
   and never moves LATEST.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SIM_DIR = Path(__file__).resolve().parent.parent
EXPERIMENT_DIR = SIM_DIR / "full-conversion-transient"
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(EXPERIMENT_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import gen_full_conversion_tb as tb  # noqa: E402
import run_conversion as rc  # noqa: E402
from harness import evidence  # noqa: E402
from report import generate as report_generate  # noqa: E402
from test_full_conversion import _as_log, _ideal_codes, _synthetic_parsed  # noqa: E402


def _fake_pdk(tmp: Path) -> SimpleNamespace:
    stdcell = tmp / "libs.ref" / "sky130_fd_sc_hd" / "spice" / "sky130_fd_sc_hd.spice"
    stdcell.parent.mkdir(parents=True)
    stdcell.write_text("* stdcells\n")
    return SimpleNamespace(variant_dir=tmp, ngspice_lib=tmp / "sky130.lib.spice")


def _options_lines(deck: str) -> list[str]:
    return [ln for ln in deck.splitlines() if ln.strip().lower().startswith(".options")]


class TestSolverProfiles(unittest.TestCase):
    def test_profile_table_is_the_issue_637_set(self):
        self.assertEqual(rc.REFERENCE_SOLVER_PROFILE, "ngspice-default")
        self.assertEqual(rc.SOLVER_PROFILES, {
            "ngspice-default": (),
            "reltol-gear": ("reltol=1e-4", "method=gear"),
            "reltol-only": ("reltol=1e-4",),
            "gear-only": ("method=gear",),
        })
        self.assertFalse(rc.is_solver_control("ngspice-default"))
        for p in ("reltol-gear", "reltol-only", "gear-only"):
            self.assertTrue(rc.is_solver_control(p))

    def test_each_profile_adds_exactly_its_intended_options(self):
        expected = {
            "ngspice-default": [],
            "reltol-gear": [".options reltol=1e-4 method=gear"],
            "reltol-only": [".options reltol=1e-4"],
            "gear-only": [".options method=gear"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            pdk_info = _fake_pdk(Path(tmp))
            ref = rc.assemble_deck("* dut\nR1 a b 1\n", pdk_info)
            for profile, cards in expected.items():
                with self.subTest(profile=profile):
                    deck = rc.assemble_deck("* dut\nR1 a b 1\n", pdk_info, solver_profile=profile)
                    self.assertEqual(_options_lines(deck), cards)
                    # nothing but the profile's own lines differs from the reference deck
                    extra = [ln for ln in deck.splitlines() if ln not in ref.splitlines()]
                    self.assertEqual(extra, rc.solver_profile_deck_lines(profile))
                    if profile == rc.REFERENCE_SOLVER_PROFILE:
                        self.assertEqual(deck, ref)

    def test_reference_deck_carries_no_options_card_for_the_dc_or_sine_fragment(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdk_info = _fake_pdk(Path(tmp))
            for fragment in (None, tb.sine_fragment_text(
                    tb.SINE_RECORD_N, tb.SINE_TONE_BIN, tb.SINE_AMPLITUDE_FRACTION)):
                deck = rc.assemble_deck("* dut\n", pdk_info, fragment=fragment)
                self.assertEqual(_options_lines(deck), [])

    def test_card_sits_after_the_fragment_and_before_extra_probes(self):
        with tempfile.TemporaryDirectory() as tmp:
            deck = rc.assemble_deck("* dut\n", _fake_pdk(Path(tmp)),
                                    extra_meas=[".meas tran probe find v(x) at=1n"],
                                    solver_profile="gear-only")
        lines = deck.splitlines()
        card = lines.index(".options method=gear")
        self.assertLess(lines.index(".meas tran probe find v(x) at=1n"), len(lines))
        self.assertGreater(lines.index(".meas tran probe find v(x) at=1n"), card)
        self.assertGreater(card, max(i for i, ln in enumerate(lines) if ln.startswith(".tran")))

    def test_unknown_profile_fails_before_any_file_is_read(self):
        with self.assertRaises(ValueError):
            rc.assemble_deck("* dut\n", SimpleNamespace(variant_dir=Path("/nonexistent")),
                             solver_profile="reltol-1e-5")

    def test_settings_text_names_the_resolved_options(self):
        self.assertIn("reltol=1e-3, method=trapezoidal", rc.solver_settings_text("ngspice-default"))
        self.assertIn("`.options reltol=1e-4`", rc.solver_settings_text("reltol-only"))
        self.assertIn("SOLVER CONTROL", rc.solver_settings_text("gear-only"))


class TestCliRefusesControlAsReference(unittest.TestCase):
    """Every refused combination exits 2 before check_env() -- i.e. before
    anything could be simulated or written."""

    REFUSED = (
        ["--solver-profile", "reltol-gear", "--supersedes", "20261001-105439-c324f80"],
        ["--solver-profile", "reltol-gear", "--corners"],
        ["--solver-profile", "gear-only", "--mechanism-probe"],
        ["--solver-profile", "gear-only", "--node-trace"],
        ["--solver-profile", "reltol-only", "--cm-trace"],
        ["--solver-profile", "reltol-only", "--decision-margin-trace"],
        ["--coherent-sine", "--solver-profile", "gear-only",
         "--supersedes", "20261011-022915-877794b"],
        ["--solver-audit", "--corners"],
        ["--solver-audit", "--coherent-sine"],
        ["--solver-audit", "--solver-profile", "reltol-gear"],
        ["--solver-audit", "--supersedes", "20261001-105439-c324f80"],
        ["--solver-audit", "--jobs", "2"],
        ["--solver-audit", "--mechanism-probe"],
        ["--audit-profile", "gear-only"],
    )

    def test_refused_before_simulation(self):
        for extra in self.REFUSED:
            with self.subTest(argv=extra):
                argv = ["run_conversion.py", *extra]
                with mock.patch.object(sys, "argv", argv), mock.patch("sys.stderr"), \
                        mock.patch.object(rc.toolchain, "check_env") as check:
                    self.assertEqual(rc.main(), 2)
                check.assert_not_called()

    def test_reference_profile_cannot_be_an_audit_profile(self):
        argv = ["run_conversion.py", "--solver-audit", "--audit-profile", "ngspice-default"]
        with mock.patch.object(sys, "argv", argv), mock.patch("sys.stderr"), \
                mock.patch.object(rc.toolchain, "check_env") as check:
            with self.assertRaises(SystemExit) as cm:
                rc.main()
        self.assertEqual(cm.exception.code, 2)
        check.assert_not_called()

    def test_reference_profile_may_still_supersede(self):
        args = SimpleNamespace(
            solver_profile="ngspice-default", sine_solver_control=False, corners=True,
            mechanism_probe=False, node_trace=False, cm_trace=False,
            decision_margin_trace=False, solver_audit=False, coherent_sine=False,
            supersedes="20261001-105439-c324f80", jobs=3, audit_profile=[],
        )
        self.assertEqual(rc.resolve_solver_cli(args), ("ngspice-default", ""))

    def test_audit_profiles_default_and_dedupe(self):
        self.assertEqual(rc.audit_profiles(SimpleNamespace(audit_profile=[])),
                         ("reltol-gear", "reltol-only", "gear-only"))
        self.assertEqual(
            rc.audit_profiles(SimpleNamespace(audit_profile=["gear-only", "gear-only", "reltol-only"])),
            ("gear-only", "reltol-only"))


def _point(offset: int = 0, profile: str = "ngspice-default", guards=None) -> dict:
    codes = {c: v + offset for c, v in _ideal_codes().items()}
    point = rc.decode(_synthetic_parsed(codes), 1.8)
    point.update(process_corner="tt", temp_c=27.0, supply_v=1.8, corner_id="tt_27c_1.80v",
                 missing=[], log_text=f"* log {profile}\n", wall_s=100.0,
                 solver_profile=profile)
    point["guards"] = guards if guards is not None else [
        dict(conversion=c, unscheduled=[], first_unscheduled=None,
             excursions={"TOP_P": None, "TOP_N": None})
        for c in tb.measured_conversions()
    ]
    point["solver_stats"] = rc.parse_solver_stats("Transient timepoints = 1000\n")
    return point


class _TmpExperiment:
    """Redirect EXPERIMENT_DIR and provenance into a temp dir."""

    def __init__(self, tmp: Path):
        self.tmp = tmp

    def __enter__(self):
        self.real = rc.EXPERIMENT_DIR, evidence.resolve_provenance
        tmp = self.tmp

        def fake_resolve(experiment_dir: Path, netlist_text: str):
            (experiment_dir / "records").mkdir(parents=True, exist_ok=True)
            return evidence.ProvenanceInfo(
                record_id="REC", record_path=experiment_dir / "records" / "REC.md",
                netlist_sha="0" * 64, pdk_line="sky130A @ testing", ng_version="ngspice-47",
            )

        rc.EXPERIMENT_DIR = tmp
        evidence.resolve_provenance = fake_resolve
        (tmp / "records").mkdir(parents=True, exist_ok=True)
        (tmp / "records" / "LATEST").write_text("PRIOR.md\n")
        return self

    def __exit__(self, *exc):
        rc.EXPERIMENT_DIR, evidence.resolve_provenance = self.real
        return False


class TestControlRecordNeverReplacesReference(unittest.TestCase):
    def test_control_record_is_labelled_and_leaves_latest_alone(self):
        with tempfile.TemporaryDirectory() as tmp, _TmpExperiment(Path(tmp)):
            path = rc.write_record([_point(profile="reltol-gear")], "* n\n",
                                   solver_profile="reltol-gear")
            text = path.read_text()
            self.assertEqual((Path(tmp) / "records" / "LATEST").read_text(), "PRIOR.md\n")
        self.assertIn("SOLVER-CONTROL RUN (issue #637) -- NOT REFERENCE EVIDENCE", text)
        self.assertIn("simulator options: profile `reltol-gear` (SOLVER CONTROL): "
                      "`.options reltol=1e-4 method=gear`", text)
        self.assertEqual(report_generate.extract_field(text, "Supersedes"), "(none)")
        self.assertIn("--record --solver-profile reltol-gear", text)

    def test_control_record_refuses_supersedes_in_the_writer(self):
        with tempfile.TemporaryDirectory() as tmp, _TmpExperiment(Path(tmp)):
            with self.assertRaises(ValueError):
                rc.write_record([_point()], "* n\n", supersedes="PRIOR",
                                solver_profile="gear-only")
            self.assertFalse((Path(tmp) / "records" / "REC.md").exists())
            self.assertEqual((Path(tmp) / "records" / "LATEST").read_text(), "PRIOR.md\n")

    def test_reference_record_still_moves_latest_and_names_its_settings(self):
        with tempfile.TemporaryDirectory() as tmp, _TmpExperiment(Path(tmp)):
            text = rc.write_record([_point()], "* n\n").read_text()
            self.assertEqual((Path(tmp) / "records" / "LATEST").read_text().strip(), "REC.md")
        self.assertNotIn("SOLVER-CONTROL RUN", text)
        self.assertIn("simulator options: profile `ngspice-default` (reference)", text)


class TestTransitionGuard(unittest.TestCase):
    def test_guard_is_the_event_and_excursion_subset_of_the_switch_trace(self):
        full = set(rc.switch_trace_measure_lines(3, 1.8))
        guard = rc.transition_guard_measure_lines(3, 1.8)
        meas = [ln for ln in guard if ln.startswith(".meas")]
        self.assertTrue(set(meas) <= full)
        names = [ln.split()[2] for ln in meas]
        self.assertEqual(sorted(names), sorted(rc.transition_guard_flat_names(3)))
        self.assertEqual(len(names), len(set(names)))
        # none of the bulky per-phase snapshot / strobe probes
        self.assertFalse(any("_p0_" in n for n in names))

    def test_guard_names_do_not_collide_across_conversions(self):
        seen: set[str] = set()
        for c in tb.measured_conversions():
            names = set(rc.transition_guard_flat_names(c))
            self.assertFalse(names & seen)
            seen |= names
        self.assertFalse(seen & set(tb.all_measure_names()))


class TestAuditRunPoint(unittest.TestCase):
    def test_audit_instrumentation_is_identical_under_every_profile(self):
        log = _as_log(_synthetic_parsed(_ideal_codes())) + "Transient timepoints = 4242\n"
        decks = {}
        for profile in ("ngspice-default", "reltol-gear"):
            with mock.patch.object(rc, "assemble_deck", return_value="* deck\n") as deck, \
                    mock.patch.object(rc, "_run_ngspice", return_value=log):
                point = rc.run_point("* n\n", None, Path("/nonexistent"), "tt", 27.0, 1.8,
                                     solver_profile=profile, audit=True)
            decks[profile] = deck.call_args.kwargs
            self.assertEqual(deck.call_args.kwargs["solver_profile"], profile)
            self.assertTrue(point["all_ok"])
            self.assertEqual(point["solver_profile"], profile)
            self.assertEqual(len(point["guards"]), len(tb.measured_conversions()))
            self.assertEqual(point["solver_stats"]["stats"]["Transient timepoints"], 4242)
        self.assertEqual(decks["ngspice-default"]["extra_meas"], decks["reltol-gear"]["extra_meas"])
        extra = decks["reltol-gear"]["extra_meas"]
        self.assertEqual(extra[0], rc.SOLVER_AUDIT_STATS_CARD)
        # the only `.options` the instrumentation adds is the print-only acct card
        self.assertEqual([ln for ln in extra if ln.startswith(".options")], [".options acct"])

    def test_non_audit_run_point_adds_no_probes(self):
        with mock.patch.object(rc, "assemble_deck", return_value="* deck\n") as deck, \
                mock.patch.object(rc, "_run_ngspice",
                                  return_value=_as_log(_synthetic_parsed(_ideal_codes()))):
            point = rc.run_point("* n\n", None, Path("/nonexistent"), "tt", 27.0, 1.8)
        self.assertIsNone(deck.call_args.kwargs["extra_meas"])
        self.assertNotIn("guards", point)


class TestSolverStats(unittest.TestCase):
    def test_acct_lines_and_log_counts(self):
        log = (
            "Transient timepoints = 568\nAccepted timepoints = 560\n"
            "Rejected timepoints = 8\nTransient iterations = 1134\n"
            "Total analysis time (seconds) = 0.0043\nWarning: something\n"
            "doAnalyses: TRAN:  Timestep too small; trouble with x\n"
        )
        st = rc.parse_solver_stats(log)
        self.assertEqual(st["stats"]["Rejected timepoints"], 8)
        self.assertEqual(st["stats"]["Total analysis time (seconds)"], 0.0043)
        self.assertEqual(st["log_counts"]["timestep too small"], 1)
        self.assertEqual(st["log_counts"]["warning lines"], 1)
        self.assertEqual(st["log_counts"]["convergence trouble"], 1)


class TestCompareAuditRuns(unittest.TestCase):
    def test_identical_runs_move_nothing(self):
        self.assertEqual(rc.compare_audit_runs(_point(), _point(profile="gear-only")), [])

    def test_code_moving_inside_tolerance_is_a_value_change_not_a_failure_mode(self):
        moved = rc.compare_audit_runs(_point(0), _point(1, "gear-only"))
        self.assertTrue(moved)
        self.assertTrue(all(not m["failure_mode"] for m in moved))
        self.assertTrue(any("captured code" in m["observation"] for m in moved))

    def test_code_verdict_flip_is_a_failure_mode(self):
        moved = rc.compare_audit_runs(_point(0), _point(5, "reltol-gear"))
        fm = [m for m in moved if m["failure_mode"]]
        self.assertTrue(any("within +-1 LSB" in m["observation"] for m in fm))
        self.assertTrue(any("point verdict" in m["observation"] for m in fm))

    def test_unscheduled_transition_and_power_change_are_reported(self):
        ctl = _point(profile="reltol-only")
        ctl["guards"][2] = dict(
            conversion=ctl["guards"][2]["conversion"],
            unscheduled=[{"node": "DOUT8"}], first_unscheduled=None,
            excursions={"TOP_P": {"phase": 5, "offset_ns": 3.0}, "TOP_N": None},
        )
        ctl["power_w"] *= 1.05
        obs = [m["observation"] for m in rc.compare_audit_runs(_point(), ctl)]
        self.assertTrue(any("UNSCHEDULED" in o for o in obs))
        self.assertTrue(any("TOP_P below" in o for o in obs))
        self.assertTrue(any(o.startswith("total power") for o in obs))

    def test_power_change_within_audit_tolerance_is_not_reported(self):
        ctl = _point(profile="reltol-only")
        ctl["power_w"] *= 1.001
        self.assertEqual(rc.compare_audit_runs(_point(), ctl), [])


class TestLatestBaselineRow(unittest.TestCase):
    def test_reads_the_committed_latest_campaign_row(self):
        row = rc.latest_baseline_row()
        self.assertIsNotNone(row)
        latest = (EXPERIMENT_DIR / "records" / "LATEST").read_text().strip()
        self.assertEqual(row["record_id"] + ".md", latest)
        self.assertEqual(row["corner_id"], "tt_27c_1.80v")
        self.assertEqual(len(row["codes"]), len(tb.INPUT_FRACTIONS))
        self.assertTrue(all(isinstance(c, int) for c in row["codes"]))
        self.assertIsNotNone(row["power_w"])
        self.assertRegex(row["netlist_sha"], r"^[0-9a-f]{64}$")

    def test_missing_latest_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(rc.latest_baseline_row(Path(tmp)))


class TestSolverAuditRecord(unittest.TestCase):
    LATEST = dict(record_id="PRIOR", corner_id="tt_27c_1.80v",
                  codes=[cv for cv in _ideal_codes().values()], power_w=27.0e-6,
                  ngspice="ngspice-46", netlist_sha="0" * 64, fragment_sha=None)

    def _write(self, runs, tmp: Path) -> str:
        with _TmpExperiment(tmp):
            path = rc.write_solver_audit_record(
                runs, "* n\n", 400.0, self.LATEST,
                "sim/full-conversion-transient/run_conversion.py --solver-audit --record")
            self.assertEqual((tmp / "records" / "LATEST").read_text(), "PRIOR.md\n")
            for r in runs:
                self.assertTrue((tmp / "diagnostics" / "REC" /
                                 f"solver-audit-{r['solver_profile']}-tt_27c_1.80v.log").is_file())
            return path.read_text()

    def test_clean_audit(self):
        runs = [_point(), _point(profile="reltol-gear"), _point(profile="gear-only")]
        with tempfile.TemporaryDirectory() as tmp:
            text = self._write(runs, Path(tmp))
        self.assertIn("NO OBSERVATION MOVED", text)
        self.assertEqual(report_generate.extract_field(text, "Supersedes"), "(none)")
        self.assertIn("codes IDENTICAL", text)
        self.assertIn("simulator options [reltol-gear]: profile `reltol-gear` (SOLVER CONTROL)", text)
        self.assertIn("simulator options [ngspice-default]: profile `ngspice-default` (reference)", text)
        self.assertIn("excludes host/CI queueing and toolchain setup", text)

    def test_moved_failure_mode_is_named_solver_sensitive(self):
        runs = [_point(), _point(6, "reltol-gear")]
        with tempfile.TemporaryDirectory() as tmp:
            text = self._write(runs, Path(tmp))
        self.assertIn("SOLVER-SENSITIVE -- at least one observation moved under `reltol-gear`", text)
        self.assertIn("**yes -- SOLVER-SENSITIVE**", text)

    def test_audit_must_start_with_the_reference_profile(self):
        with tempfile.TemporaryDirectory() as tmp, _TmpExperiment(Path(tmp)):
            for runs in ([_point(profile="gear-only"), _point(profile="reltol-gear")], [_point()]):
                with self.assertRaises(ValueError):
                    rc.write_solver_audit_record(runs, "* n\n", 1.0, None, "x")


if __name__ == "__main__":
    unittest.main()

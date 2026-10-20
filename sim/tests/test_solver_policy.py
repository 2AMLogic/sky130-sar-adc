"""PDK-free unit tests for the full-conversion transient solver policy and the
DC baseline solver-sensitivity audit (issue #637,
spec/decision-records/DR-023-full-conversion-transient-solver-policy.md).

What is pinned here, because a five-minute-per-run simulation is the wrong
place to discover it:

1. Each named solver profile adds EXACTLY its intended `.options` card at
   deck assembly and nothing else; the reference profile adds nothing.
2. Every flag combination that would let a control profile stand in for
   reference evidence is refused BEFORE the toolchain is checked or anything
   is simulated -- while `ngspice-default` (the pre-DR-023 settings) may still
   re-run --corners and every diagnostic mode, as a labelled control, so the
   records minted before DR-023 stay reproducible.
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
from test_full_conversion import (  # noqa: E402
    _as_log, _ideal_codes, _synthetic_node_trace, _synthetic_parsed,
)


def _fake_pdk(tmp: Path) -> SimpleNamespace:
    stdcell = tmp / "libs.ref" / "sky130_fd_sc_hd" / "spice" / "sky130_fd_sc_hd.spice"
    stdcell.parent.mkdir(parents=True)
    stdcell.write_text("* stdcells\n")
    return SimpleNamespace(variant_dir=tmp, ngspice_lib=tmp / "sky130.lib.spice")


def _options_lines(deck: str) -> list[str]:
    return [ln for ln in deck.splitlines() if ln.strip().lower().startswith(".options")]


class TestSolverProfiles(unittest.TestCase):
    def test_profile_table_and_dr023_reference(self):
        self.assertEqual(rc.REFERENCE_SOLVER_PROFILE, "reltol-gear")  # DR-023
        self.assertEqual(rc.SOLVER_PROFILES, {
            "ngspice-default": (),
            "reltol-gear": ("reltol=1e-4", "method=gear"),
            "reltol-only": ("reltol=1e-4",),
            "gear-only": ("method=gear",),
        })
        self.assertFalse(rc.is_solver_control("reltol-gear"))
        for p in ("ngspice-default", "reltol-only", "gear-only"):
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
            # the no-card profile is the pre-#637 deck; every other profile
            # differs from it by its own labelled card and nothing else
            base = rc.assemble_deck("* dut\nR1 a b 1\n", pdk_info, solver_profile="ngspice-default")
            for profile, cards in expected.items():
                with self.subTest(profile=profile):
                    deck = rc.assemble_deck("* dut\nR1 a b 1\n", pdk_info, solver_profile=profile)
                    self.assertEqual(_options_lines(deck), cards)
                    extra = [ln for ln in deck.splitlines() if ln not in base.splitlines()]
                    self.assertEqual(extra, rc.solver_profile_deck_lines(profile))
                    self.assertEqual(len(deck.splitlines()) - len(base.splitlines()), len(extra))

    def test_default_deck_is_the_reference_policy_for_the_dc_and_sine_fragment(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdk_info = _fake_pdk(Path(tmp))
            for fragment in (None, tb.sine_fragment_text(
                    tb.SINE_RECORD_N, tb.SINE_TONE_BIN, tb.SINE_AMPLITUDE_FRACTION)):
                deck = rc.assemble_deck("* dut\n", pdk_info, fragment=fragment)
                self.assertEqual(_options_lines(deck), [".options reltol=1e-4 method=gear"])
                self.assertIn("reference policy, DR-023", deck)
                legacy = rc.assemble_deck("* dut\n", pdk_info, fragment=fragment,
                                          solver_profile="ngspice-default")
                self.assertEqual(_options_lines(legacy), [])

    def test_diagnostic_modes_inherit_the_reference_policy(self):
        # node/cm/decision-margin traces and the mechanism probe call
        # assemble_deck without a solver_profile: they run the reference policy
        with tempfile.TemporaryDirectory() as tmp:
            deck = rc.assemble_deck("xcmp VDD CLK a b c\n", _fake_pdk(Path(tmp)),
                                    delayed_comparator_strobe=True)
        self.assertEqual(_options_lines(deck), [".options reltol=1e-4 method=gear"])

    def test_card_sits_after_the_fragment_and_before_extra_probes(self):
        with tempfile.TemporaryDirectory() as tmp:
            deck = rc.assemble_deck("* dut\n", _fake_pdk(Path(tmp)),
                                    extra_meas=[".meas tran probe find v(x) at=1n"],
                                    solver_profile="gear-only")
        lines = deck.splitlines()
        card = lines.index(".options method=gear")
        self.assertGreater(lines.index(".meas tran probe find v(x) at=1n"), card)
        self.assertGreater(card, max(i for i, ln in enumerate(lines) if ln.startswith(".tran")))

    def test_unknown_profile_fails_before_any_file_is_read(self):
        with self.assertRaises(ValueError):
            rc.assemble_deck("* dut\n", SimpleNamespace(variant_dir=Path("/nonexistent")),
                             solver_profile="reltol-1e-5")

    def test_settings_text_names_the_resolved_options_and_role(self):
        self.assertEqual(
            rc.solver_settings_text("reltol-gear"),
            "profile `reltol-gear` (reference policy, DR-023): `.options reltol=1e-4 "
            "method=gear`; all other settings ngspice defaults")
        self.assertIn("(SOLVER CONTROL): no `.options` card -- reltol=1e-3, method=trapezoidal",
                      rc.solver_settings_text("ngspice-default"))
        self.assertIn("`.options reltol=1e-4`", rc.solver_settings_text("reltol-only"))
        self.assertIn("SOLVER CONTROL", rc.solver_settings_text("gear-only"))


# A check_env stand-in reporting "toolchain not installed" (status 3): a
# combination the runner wrongly ACCEPTS then returns 0 and fails the test,
# instead of going on to launch a real ngspice transient.
_NO_TOOLCHAIN = mock.Mock(status=3, messages=[], warnings=[])


class TestCliRefusesControlAsReference(unittest.TestCase):
    """Every refused combination exits 2 before check_env() -- i.e. before
    anything could be simulated or written."""

    REFUSED = (
        ["--solver-profile", "ngspice-default", "--supersedes", "20261001-105439-c324f80"],
        ["--solver-profile", "reltol-only", "--corners"],
        ["--solver-profile", "gear-only", "--corners", "--record"],
        ["--solver-profile", "ngspice-default", "--corners",
         "--supersedes", "20261001-105439-c324f80"],
        ["--solver-profile", "gear-only", "--mechanism-probe"],
        ["--solver-profile", "gear-only", "--node-trace"],
        ["--solver-profile", "reltol-only", "--cm-trace"],
        ["--solver-profile", "reltol-only", "--decision-margin-trace"],
        ["--coherent-sine", "--solver-profile", "ngspice-default",
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
                        mock.patch.object(rc.toolchain, "check_env",
                                          return_value=_NO_TOOLCHAIN) as check:
                    self.assertEqual(rc.main(), 2)
                check.assert_not_called()

    def test_reference_profile_cannot_be_an_audit_profile(self):
        argv = ["run_conversion.py", "--solver-audit", "--audit-profile", "reltol-gear"]
        with mock.patch.object(sys, "argv", argv), mock.patch("sys.stderr"), \
                mock.patch.object(rc.toolchain, "check_env", return_value=_NO_TOOLCHAIN) as check:
            with self.assertRaises(SystemExit) as cm:
                rc.main()
        self.assertEqual(cm.exception.code, 2)
        check.assert_not_called()

    def test_reference_profile_may_still_supersede_and_run_the_grid(self):
        args = SimpleNamespace(
            solver_profile=None, sine_solver_control=False, corners=True,
            mechanism_probe=False, node_trace=False, cm_trace=False,
            decision_margin_trace=False, solver_audit=False, coherent_sine=False,
            supersedes="20261001-105439-c324f80", jobs=3, audit_profile=[],
        )
        self.assertEqual(rc.resolve_solver_cli(args), ("reltol-gear", ""))
        args.solver_profile = "reltol-gear"
        self.assertEqual(rc.resolve_solver_cli(args), ("reltol-gear", ""))

    def test_ngspice_default_may_reproduce_the_grid_and_every_diagnostic(self):
        # issue #637 review: every pre-DR-023 record (records/LATEST's 9-corner
        # campaign, the mechanism probe and the three traces) must stay
        # reproducible -- as a labelled control, never as reference evidence.
        for mode in ("corners", "mechanism_probe", "node_trace", "cm_trace",
                     "decision_margin_trace"):
            with self.subTest(mode=mode):
                args = SimpleNamespace(
                    solver_profile="ngspice-default", sine_solver_control=False,
                    corners=False, mechanism_probe=False, node_trace=False,
                    cm_trace=False, decision_margin_trace=False, solver_audit=False,
                    coherent_sine=False, supersedes="", jobs=1, audit_profile=[],
                )
                setattr(args, mode, True)
                self.assertEqual(rc.resolve_solver_cli(args), ("ngspice-default", ""))
                args.solver_profile = "gear-only"
                self.assertIn("SOLVER CONTROL", rc.resolve_solver_cli(args)[1])

    def test_ngspice_default_grid_passes_the_cli_to_check_env(self):
        argv = ["run_conversion.py", "--solver-profile", "ngspice-default", "--corners",
                "--record"]
        with mock.patch.object(sys, "argv", argv), mock.patch("sys.stdout"), \
                mock.patch.object(rc.toolchain, "check_env", return_value=_NO_TOOLCHAIN) as check:
            self.assertEqual(rc.main(), 0)  # status 3 -> SKIP, nothing simulated
        check.assert_called_once()

    def test_audit_profiles_default_and_dedupe(self):
        self.assertEqual(rc.audit_profiles(SimpleNamespace(audit_profile=[])),
                         ("ngspice-default", "reltol-only", "gear-only"))
        self.assertEqual(
            rc.audit_profiles(SimpleNamespace(audit_profile=["gear-only", "gear-only", "reltol-only"])),
            ("gear-only", "reltol-only"))


def _point(offset: int = 0, profile: str = rc.REFERENCE_SOLVER_PROFILE, guards=None) -> dict:
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
            path = rc.write_record([_point(profile="ngspice-default")], "* n\n",
                                   solver_profile="ngspice-default")
            text = path.read_text()
            self.assertEqual((Path(tmp) / "records" / "LATEST").read_text(), "PRIOR.md\n")
        self.assertIn("SOLVER-CONTROL RUN (issue #637) -- NOT REFERENCE EVIDENCE", text)
        self.assertIn("simulator options: profile `ngspice-default` (SOLVER CONTROL): no "
                      "`.options` card -- reltol=1e-3, method=trapezoidal", text)
        self.assertIn("instead of the reference policy `reltol-gear`", text)
        self.assertEqual(report_generate.extract_field(text, "Supersedes"), "(none)")
        self.assertIn("--record --solver-profile ngspice-default", text)

    def test_control_record_refuses_supersedes_in_the_writer(self):
        with tempfile.TemporaryDirectory() as tmp, _TmpExperiment(Path(tmp)):
            with self.assertRaises(ValueError):
                rc.write_record([_point()], "* n\n", supersedes="PRIOR",
                                solver_profile="gear-only")
            self.assertFalse((Path(tmp) / "records" / "REC.md").exists())
            self.assertEqual((Path(tmp) / "records" / "LATEST").read_text(), "PRIOR.md\n")

    def test_control_corner_campaign_record_leaves_latest_alone(self):
        # `--solver-profile ngspice-default --corners --record` reproduces the
        # pre-DR-023 campaign: labelled control, LATEST untouched, and the
        # Written-by command is the one that reproduces it.
        pts = [_point(profile="ngspice-default") for _ in range(9)]
        with tempfile.TemporaryDirectory() as tmp, _TmpExperiment(Path(tmp)):
            text = rc.write_record(pts, "* n\n", solver_profile="ngspice-default").read_text()
            self.assertEqual((Path(tmp) / "records" / "LATEST").read_text(), "PRIOR.md\n")
        self.assertIn("SOLVER-CONTROL RUN (issue #637) -- NOT REFERENCE EVIDENCE", text)
        self.assertIn("run_conversion.py --corners --record --solver-profile ngspice-default",
                      text)
        self.assertEqual(report_generate.extract_field(text, "Supersedes"), "(none)")

    def test_reference_record_still_moves_latest_and_names_its_settings(self):
        with tempfile.TemporaryDirectory() as tmp, _TmpExperiment(Path(tmp)):
            text = rc.write_record([_point()], "* n\n").read_text()
            self.assertEqual((Path(tmp) / "records" / "LATEST").read_text().strip(), "REC.md")
        self.assertNotIn("SOLVER-CONTROL RUN", text)
        self.assertIn("simulator options: profile `reltol-gear` (reference policy, DR-023)", text)


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
        for profile in ("reltol-gear", "ngspice-default"):
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
        extra = decks["ngspice-default"]["extra_meas"]
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
        moved = rc.compare_audit_runs(_point(0), _point(5, "ngspice-default"))
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
        # issue #638: the committed LATEST is the DR-023 reference re-mint,
        # whose Environment block states its own resolved solver profile
        self.assertIn(f"profile `{rc.REFERENCE_SOLVER_PROFILE}` (reference",
                      row["simulator_options"])

    def test_pre_637_record_settings_are_named_not_blank(self):
        # a record minted before issue #637 states no simulator options; the
        # reader names the ngspice defaults it ran on instead of leaving it blank
        old = "20261001-105439-c324f80.md"
        with tempfile.TemporaryDirectory() as tmp:
            records = Path(tmp)
            (records / old).write_text((EXPERIMENT_DIR / "records" / old).read_text())
            (records / "LATEST").write_text(old + "\n")
            row = rc.latest_baseline_row(records)
        self.assertIsNotNone(row)
        self.assertEqual(row["record_id"] + ".md", old)
        self.assertIn("pre-#637 record", row["simulator_options"])

    def test_missing_latest_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(rc.latest_baseline_row(Path(tmp)))


class TestSolverAuditRecord(unittest.TestCase):
    LATEST = dict(record_id="PRIOR", corner_id="tt_27c_1.80v",
                  codes=[cv for cv in _ideal_codes().values()], power_w=27.0e-6,
                  ngspice="ngspice-46", netlist_sha="0" * 64, fragment_sha=None,
                  simulator_options="not stated (pre-#637 record: ngspice defaults)")

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
        runs = [_point(), _point(profile="ngspice-default"), _point(profile="gear-only")]
        with tempfile.TemporaryDirectory() as tmp:
            text = self._write(runs, Path(tmp))
        self.assertIn("NO OBSERVATION MOVED", text)
        self.assertEqual(report_generate.extract_field(text, "Supersedes"), "(none)")
        self.assertIn("codes IDENTICAL", text)
        self.assertIn("simulator options [ngspice-default]: profile `ngspice-default` (SOLVER CONTROL)", text)
        self.assertIn("simulator options [reltol-gear]: profile `reltol-gear` (reference policy, DR-023)", text)
        self.assertIn("this run: profile `reltol-gear`", text)
        self.assertIn("excludes host/CI queueing and toolchain setup", text)

    def test_moved_failure_mode_is_named_solver_sensitive(self):
        runs = [_point(), _point(6, "ngspice-default")]
        with tempfile.TemporaryDirectory() as tmp:
            text = self._write(runs, Path(tmp))
        self.assertIn("SOLVER-SENSITIVE -- at least one observation moved under `ngspice-default`", text)
        self.assertIn("**yes -- SOLVER-SENSITIVE**", text)

    def test_audit_must_start_with_the_reference_profile(self):
        with tempfile.TemporaryDirectory() as tmp, _TmpExperiment(Path(tmp)):
            for runs in ([_point(profile="gear-only"), _point(profile="ngspice-default")], [_point()]):
                with self.assertRaises(ValueError):
                    rc.write_solver_audit_record(runs, "* n\n", 1.0, None, "x")


if __name__ == "__main__":
    unittest.main()


class TestDiagnosticModesHonourTheProfile(unittest.TestCase):
    """The diagnostic runners assemble their deck under the resolved profile
    (not a hard-wired reference policy), and their records name it."""

    def test_node_trace_point_deck_carries_the_profile(self):
        decks: list[str] = []

        def fake_run(deck, scratch, tag, attempts=3):
            decks.append(deck)
            return ""

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(rc, "_run_ngspice", side_effect=fake_run):
            fake = _fake_pdk(Path(tmp))
            for profile in ("ngspice-default", "reltol-gear"):
                rc.run_node_trace_point("* dut\n", fake, Path(tmp), "tt", 27.0, 1.8,
                                        rc.NODE_TRACE_CONVERSIONS, solver_profile=profile)
                rc.run_decision_margin_point("* dut\n", fake, Path(tmp), "tt", 27.0, 1.8,
                                             "as-committed", solver_profile=profile)
        self.assertEqual([_options_lines(d) for d in decks], [
            [], [],
            [".options reltol=1e-4 method=gear"], [".options reltol=1e-4 method=gear"],
        ])

    def test_mechanism_probe_runs_both_variants_under_the_profile(self):
        seen = []
        with mock.patch.object(rc, "pdk"), mock.patch.object(rc, "dut_text", return_value=""), \
                mock.patch.object(rc, "run_point",
                                  side_effect=lambda *a, **k: seen.append(k["solver_profile"])
                                  or {}):
            rc.run_mechanism_probe(Path("/nonexistent"), True, "ngspice-default")
        self.assertEqual(seen, ["ngspice-default", "ngspice-default"])

    def _node_trace_record(self, profile: str) -> str:
        traces = {
            cid: _synthetic_node_trace(cid, pc, tc, sv, all_reset=True)
            for cid, pc, tc, sv in (("tt_27c_1.62v", "tt", 27.0, 1.62),
                                    ("ff_27c_1.80v", "ff", 27.0, 1.80))
        }
        with tempfile.TemporaryDirectory() as tmp, _TmpExperiment(Path(tmp)):
            text = rc.write_node_trace_record(traces, "* n\n", profile).read_text()
            self.assertEqual((Path(tmp) / "records" / "LATEST").read_text(), "PRIOR.md\n")
        return text

    def test_control_diagnostic_record_is_labelled_and_reproducible(self):
        text = self._node_trace_record("ngspice-default")
        self.assertIn("SOLVER-CONTROL RUN (issue #637) -- NOT REFERENCE EVIDENCE", text)
        self.assertIn("simulator options: profile `ngspice-default` (SOLVER CONTROL)", text)
        self.assertIn("run_conversion.py --node-trace --solver-profile ngspice-default", text)
        self.assertEqual(report_generate.extract_field(text, "Supersedes"), "(none)")

    def test_reference_diagnostic_record_names_its_settings(self):
        text = self._node_trace_record("reltol-gear")
        self.assertNotIn("SOLVER-CONTROL RUN", text)
        self.assertIn("simulator options: profile `reltol-gear` (reference policy, DR-023)", text)
        self.assertNotIn("--solver-profile", text)

"""PDK-free unit tests for sim/vcm-drive-budget/run_vcm_drive_budget.py.

Two things are covered here, neither needing ngspice or the PDK:

- The deck builder is actually called (issue #591, same failure class as
  issue #296 -- see test_run_hold_kick.py: a shared-helper migration can
  leave a builder calling an undefined name, which only surfaces when
  someone runs ngspice with the PDK).
- The verdict helpers `find_budget()`, `marginal_r_source()`,
  `marginal_r_source_is_fallback()` and `partition_decouple_rescue()` are
  pure functions over row dicts, so their failing sides are exercised
  directly (issue #874). Before #874 `find_budget()` counted the sweep's own
  control row -- whose error is identically zero by construction -- so it
  could not return None and every "none found" / "unrescued" branch in this
  driver was dead code. These tests are what keep the failing side
  reachable.
- The `klt sim` port of the `--corners` paths (issue #881): the request's
  shape and step counts, the deck body's `alter` targets, report decoding,
  the per-corner marginal-R_source selection the decouple leg does AFTER the
  report comes back, and the INCOMPLETE path a corner takes when a step is
  missing or non-finite. All of it runs against an injected report dict --
  no `klt`, no PDK, no fleet -- which is the point: the arithmetic that turns
  a report into a record is the part a fleet run cannot check for you."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))


RUNNER = SIM_DIR / "vcm-drive-budget/run_vcm_drive_budget.py"
_spec = importlib.util.spec_from_file_location("run_vcm_drive_budget_under_test", RUNNER)
rt = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rt
_spec.loader.exec_module(rt)


class TestBuildTransient(unittest.TestCase):
    def test_returns_deck_with_tran(self):
        deck = rt.build_transient(
            vinp=1.6, vinn=0.2, sample_width_ns=100.0, r_source_ohm=1000.0,
        )
        self.assertIsInstance(deck, str)
        self.assertIn(".control", deck)
        self.assertIn("\ntran ", deck)
        self.assertIn(".end", deck)
        self.assertIn(".lib", deck)

    def test_with_decoupling_cap_and_corner(self):
        deck = rt.build_transient(
            vinp=1.6, vinn=0.2, sample_width_ns=100.0, r_source_ohm=1000.0,
            c_decouple_f=1e-12, corner="ss", temp_c=125.0, vdd=1.62,
        )
        self.assertIn(".control", deck)
        self.assertIn("\ntran ", deck)


def _r_rows(pairs: list[tuple[float, float]]) -> list[dict]:
    """Bare R_source sweep rows: (r_source_ohm, diff_err_lsb). The first
    entry is the CONTROL row, exactly as run_sweep() builds it -- its error
    is the reference every later row is measured against."""
    return [{"r_source_ohm": r, "diff_err_lsb": e} for r, e in pairs]


def _c_rows(pairs: list[tuple[float, float]]) -> list[dict]:
    """C_decouple sweep rows: (c_decouple_f, diff_err_lsb), first entry the
    control row, exactly as run_decouple_sweep() builds it."""
    return [{"c_decouple_f": c, "diff_err_lsb": e} for c, e in pairs]


class TestFindBudget(unittest.TestCase):
    """`find_budget()` -- issue #874."""

    def test_no_passing_nonzero_point_is_none_not_a_zero_budget(self):
        """The regression this function existed to report and could not:
        the control row's own error is zero by construction, so counting it
        turned "no swept resistance works" into a budget of "<= 0 ohm"."""
        rows = _r_rows([(0.0, 0.0), (100.0, 4.0), (1e3, 9.0)])
        self.assertIsNone(rt.find_budget(rows, 1.0))

    def test_the_control_row_is_never_itself_the_budget(self):
        rows = _r_rows([(0.0, 0.0), (100.0, 2.0)])
        self.assertIsNone(rt.find_budget(rows, 1.0))

    def test_returns_the_last_passing_row_not_a_bare_float(self):
        rows = _r_rows([(0.0, 0.0), (100.0, 0.05), (1e3, 0.5), (3e3, 4.0)])
        hit = rt.find_budget(rows, 1.0)
        self.assertIsInstance(hit, dict)
        self.assertEqual(hit["r_source_ohm"], 1e3)
        # ...and a tighter tier stops one swept point earlier.
        self.assertEqual(rt.find_budget(rows, 0.1)["r_source_ohm"], 100.0)

    def test_every_swept_value_passing_is_the_largest_right_censored_row(self):
        rows = _r_rows([(0.0, 0.0), (100.0, 0.01), (1e3, 0.02), (10e3, 0.03)])
        self.assertEqual(rt.find_budget(rows, 1.0)["r_source_ohm"], 10e3)

    def test_the_threshold_is_inclusive_and_on_absolute_error(self):
        rows = _r_rows([(0.0, 0.0), (100.0, -1.0), (1e3, -1.0001)])
        self.assertEqual(rt.find_budget(rows, 1.0)["r_source_ohm"], 100.0)

    def test_a_later_passing_point_wins_over_an_earlier_failing_one(self):
        """find_budget() takes the LAST passing row, not the last row before
        the first failure -- the error is not monotonic in either axis, so
        this is a deliberate property, asserted rather than assumed."""
        rows = _r_rows([(0.0, 0.0), (100.0, 4.0), (1e3, 0.2)])
        self.assertEqual(rt.find_budget(rows, 1.0)["r_source_ohm"], 1e3)

    def test_the_control_row_is_excluded_positionally_not_by_value(self):
        """The same helper grades the C_decouple axis, so the exclusion is
        "the sweep's own first row", not "r_source_ohm == 0"."""
        rows = _r_rows([(100.0, 0.0), (1e3, 0.2)])
        self.assertEqual(rt.find_budget(rows, 1.0)["r_source_ohm"], 1e3)

    def test_c_decouple_axis_none_case(self):
        rows = _c_rows([(0.0, 0.0), (1e-12, 3.0), (10e-12, 5.0)])
        self.assertIsNone(rt.find_budget(rows, 1.0))

    def test_c_decouple_axis_passing_case(self):
        rows = _c_rows([(0.0, 0.0), (1e-12, 0.4), (10e-12, 0.9), (100e-12, 2.0)])
        self.assertEqual(rt.find_budget(rows, 1.0)["c_decouple_f"], 10e-12)

    def test_empty_and_control_only_sweeps_are_none(self):
        self.assertIsNone(rt.find_budget([], 1.0))
        self.assertIsNone(rt.find_budget(_r_rows([(0.0, 0.0)]), 1.0))


class TestSweepListShape(unittest.TestCase):
    """find_budget() reads its control row positionally and its budget as the
    LAST passing row; both assume every sweep list ascends from the control
    value. Assert that rather than leaving it to a reader."""

    def test_sweep_lists_ascend_from_zero(self):
        for sweep in (rt.R_SOURCE_SWEEP_OHM, rt.R_SOURCE_SWEEP_LEGACY_OHM,
                      rt.C_DECOUPLE_SWEEP_F):
            self.assertEqual(sweep, sorted(set(sweep)))
            self.assertEqual(sweep[0], 0.0)
            self.assertGreaterEqual(len(sweep), 2)

    def test_every_window_config_sweep_has_a_smallest_nonzero_point(self):
        """The record writers quote `r_source_list[1]` as "the smallest
        nonzero tested" in the none-found branches #874 made reachable."""
        for window, (_sample_ns, r_list) in rt.WINDOW_CONFIG.items():
            self.assertGreater(r_list[1], 0.0, window)


class TestMarginalRSource(unittest.TestCase):
    """`marginal_r_source()` / `marginal_r_source_is_fallback()` -- #874."""

    SWEEP = [0.0, 100.0, 1e3, 10e3]

    def test_picks_the_first_r_source_past_one_lsb(self):
        rows = _r_rows([(0.0, 0.0), (100.0, 0.2), (1e3, 1.5), (10e3, 9.0)])
        self.assertEqual(rt.marginal_r_source(rows, self.SWEEP), 1e3)
        self.assertFalse(rt.marginal_r_source_is_fallback(rows))

    def test_a_negative_excursion_past_one_lsb_counts(self):
        rows = _r_rows([(0.0, 0.0), (100.0, -1.5), (1e3, -9.0)])
        self.assertEqual(rt.marginal_r_source(rows, self.SWEEP), 100.0)
        self.assertFalse(rt.marginal_r_source_is_fallback(rows))

    def test_nothing_past_one_lsb_is_the_fallback_not_a_marginal_case(self):
        rows = _r_rows([(0.0, 0.0), (100.0, 0.1), (1e3, 0.2), (10e3, 0.9)])
        self.assertEqual(rt.marginal_r_source(rows, self.SWEEP), 10e3)
        self.assertTrue(rt.marginal_r_source_is_fallback(rows))

    def test_exactly_one_lsb_is_not_past_it(self):
        rows = _r_rows([(0.0, 0.0), (100.0, 1.0)])
        self.assertTrue(rt.marginal_r_source_is_fallback(rows))

    def test_the_predicate_and_the_value_never_disagree(self):
        for errs in ([0.0, 0.1, 0.2, 0.9], [0.0, 0.2, 1.5, 9.0],
                     [0.0, 1.01, 0.1, 0.1]):
            rows = _r_rows(list(zip(self.SWEEP, errs)))
            is_fallback = rt.marginal_r_source_is_fallback(rows)
            value = rt.marginal_r_source(rows, self.SWEEP)
            self.assertEqual(is_fallback, value == self.SWEEP[-1]
                             and not any(abs(e) > 1.0 for e in errs[:-1]),
                             errs)


def _point(cid: str, *, fallback: bool, budget_f: float | None) -> dict:
    return {"corner_id": cid, "marginal_is_fallback": fallback,
            "budget_1lsb_f": budget_f}


class TestPartitionDecoupleRescue(unittest.TestCase):
    """`partition_decouple_rescue()` -- the rescue verdict, issue #874."""

    def test_a_fallback_corner_is_on_neither_side_of_the_verdict(self):
        """The defect: a corner whose bare sweep never failed had nothing to
        rescue, yet was counted as rescued -- which is how the record could
        report "N of N corners rescued" for any data at all."""
        points = [_point("a", fallback=True, budget_f=10e-12)]
        split = rt.partition_decouple_rescue(points)
        self.assertEqual([p["corner_id"] for p in split["nothing_to_rescue"]],
                         ["a"])
        self.assertEqual(split["rescued"], [])
        self.assertEqual(split["unrescued"], [])
        self.assertEqual(split["needed"], [])

    def test_a_real_failing_corner_with_a_budget_is_rescued(self):
        points = [_point("a", fallback=False, budget_f=10e-12)]
        split = rt.partition_decouple_rescue(points)
        self.assertEqual([p["corner_id"] for p in split["rescued"]], ["a"])
        self.assertEqual(split["unrescued"], [])
        self.assertEqual(split["nothing_to_rescue"], [])

    def test_a_real_failing_corner_without_a_budget_is_unrescued(self):
        points = [_point("a", fallback=False, budget_f=None)]
        split = rt.partition_decouple_rescue(points)
        self.assertEqual([p["corner_id"] for p in split["unrescued"]], ["a"])
        self.assertEqual(split["rescued"], [])

    def test_the_three_groups_partition_the_points_exactly_once(self):
        points = [
            _point("a", fallback=True, budget_f=10e-12),
            _point("b", fallback=True, budget_f=None),
            _point("c", fallback=False, budget_f=1e-12),
            _point("d", fallback=False, budget_f=None),
        ]
        split = rt.partition_decouple_rescue(points)
        self.assertEqual(
            sorted(p["corner_id"] for p in split["nothing_to_rescue"]),
            ["a", "b"])
        self.assertEqual([p["corner_id"] for p in split["rescued"]], ["c"])
        self.assertEqual([p["corner_id"] for p in split["unrescued"]], ["d"])
        self.assertEqual(
            len(split["nothing_to_rescue"]) + len(split["rescued"])
            + len(split["unrescued"]), len(points))
        self.assertEqual(len(split["needed"]),
                         len(split["rescued"]) + len(split["unrescued"]))

    def test_the_rescue_count_is_not_automatically_n_of_n(self):
        """The count the record prints is over `needed`, not over every
        corner, so it can be less than the grid size."""
        points = [
            _point("a", fallback=True, budget_f=10e-12),
            _point("b", fallback=False, budget_f=None),
        ]
        split = rt.partition_decouple_rescue(points)
        self.assertEqual(len(split["rescued"]), 0)
        self.assertEqual(len(split["needed"]), 1)
        self.assertNotEqual(len(split["rescued"]), len(points))


class TestSingleCornerDecoupleRescueNote(unittest.TestCase):
    """`single_corner_decouple_rescue_note()` -- issue #882.

    `find_budget()` returns the LARGEST passing swept value, and the
    record's own C_decouple table note says this error is not monotonic in
    C_decouple, so the pre-#882 ">= X pF ... recovers differential error"
    wording claimed every untested capacitance above the largest TESTED one
    also works."""

    def test_the_note_does_not_claim_a_lower_bound(self):
        note = rt.single_corner_decouple_rescue_note(5e3, 10e-12)
        self.assertNotIn(">=", note)
        self.assertIn("10.00 pF", note)

    def test_the_note_reports_the_value_as_confirmed_not_as_a_floor(self):
        note = rt.single_corner_decouple_rescue_note(5e3, 10e-12)
        self.assertIn("largest swept C_decouple confirmed to work", note)
        self.assertIn("not a guaranteed floor", note)

    def test_the_note_carries_the_non_monotonicity_caveat(self):
        """The same caveat the `--corners` sibling note has carried since
        #874; this path was left behind."""
        note = rt.single_corner_decouple_rescue_note(5e3, 10e-12)
        self.assertIn("not monotonic in C_decouple", note)

    def test_the_marginal_r_source_and_window_are_still_stated(self):
        note = rt.single_corner_decouple_rescue_note(3200.0, 1e-12)
        self.assertIn("R_source=3200 ohm", note)
        self.assertIn("worst-case", note)
        self.assertIn("1.00 pF", note)

    def test_the_value_printed_is_the_value_find_budget_returns(self):
        """Wire the helper to its real input rather than a hand-made float:
        the sentence must print `find_budget()`'s row, not something else."""
        rows = _c_rows([(0.0, 0.0), (1e-12, 0.4), (10e-12, 0.9),
                        (100e-12, 2.0)])
        hit = rt.find_budget(rows, 1.0)
        note = rt.single_corner_decouple_rescue_note(5e3,
                                                     hit["c_decouple_f"])
        self.assertIn("10.00 pF", note)
        self.assertNotIn("100.00 pF", note)


class TestTtPointSeedComparisonNote(unittest.TestCase):
    """`tt_point_seed_comparison_note()` -- issue #882.

    Pre-#882 the full-grid record asserted its tt/27C/1.8V point was
    "consistent with (reproduces) the single-corner record's own finding"
    whenever that point had *a* budget, without ever comparing it to
    `SINGLE_CORNER_SEED_BUDGET_1LSB_OHM`. All four seed/measured cases are
    pinned here, plus the invariant that "reproduces" is reserved for
    agreement."""

    SMALLEST_NONZERO = 100.0

    def _note(self, measured, seed):
        return rt.tt_point_seed_comparison_note(measured, seed,
                                                self.SMALLEST_NONZERO)

    # -- case 1: both numeric and equal -> agreement -------------------
    def test_equal_figures_agree_and_may_say_reproduces(self):
        note = self._note(10e3, 10e3)
        self.assertIn("reproduces", note)
        self.assertNotIn("DIFFER", note)
        self.assertIn("<= 10000 ohm", note)

    # -- case 2: both numeric and different -> states both, differ -----
    def test_different_figures_state_both_and_say_they_differ(self):
        """The concrete regression: records/20260908-100413-f3e2914.md
        printed "<= 100000 ohm, consistent with (reproduces) ..." while the
        `worst` seed figure is 10000 ohm."""
        note = self._note(100e3, 10e3)
        self.assertNotIn("reproduces the single-corner record", note)
        self.assertIn("DIFFER", note)
        self.assertIn("100000 ohm", note)
        self.assertIn("10000 ohm", note)

    # -- case 3: exactly one None -> states that they differ -----------
    def test_measured_budget_with_no_seed_budget_differs(self):
        note = self._note(10e3, None)
        self.assertIn("DIFFER", note)
        self.assertIn("no positive", note)
        self.assertNotIn("reproduces", note)

    def test_no_measured_budget_with_a_seed_budget_differs(self):
        note = self._note(None, 10e3)
        self.assertIn("DIFFER", note)
        self.assertIn("NO positive 1-LSB", note)
        self.assertIn("<= 10000 ohm", note)
        self.assertNotIn("reproduces", note)

    # -- case 4: both None -> agreement --------------------------------
    def test_neither_has_a_positive_budget_and_that_is_agreement(self):
        note = self._note(None, None)
        self.assertIn("reproduces", note)
        self.assertNotIn("DIFFER", note)
        self.assertIn("NO positive 1-LSB", note)

    # -- invariants ----------------------------------------------------
    def test_reproduces_appears_only_in_the_agreement_cases(self):
        agree = [(10e3, 10e3), (None, None)]
        differ = [(100e3, 10e3), (10e3, 100e3), (10e3, None), (None, 10e3)]
        for measured, seed in agree:
            self.assertIn("reproduces", self._note(measured, seed),
                          (measured, seed))
        for measured, seed in differ:
            self.assertNotIn("reproduces", self._note(measured, seed),
                             (measured, seed))

    def test_every_case_names_the_record_it_compared_against(self):
        for measured, seed in [(10e3, 10e3), (100e3, 10e3), (10e3, None),
                               (None, 10e3), (None, None)]:
            note = self._note(measured, seed)
            self.assertIn(rt.SINGLE_CORNER_SEED_RECORD, note, (measured, seed))

    def test_the_no_budget_branch_still_reports_the_smallest_nonzero(self):
        """The pre-#882 "no positive budget" wording is preserved, not
        dropped in favour of the comparison."""
        note = self._note(None, 10e3)
        self.assertIn("100 ohm", note)
        self.assertIn("zero margin for any nonzero drive impedance", note)

    def test_the_ratified_seed_table_covers_every_configured_window(self):
        """The caller indexes SINGLE_CORNER_SEED_BUDGET_1LSB_OHM by window;
        a window without an entry would raise at record-writing time."""
        for window in rt.WINDOW_CONFIG:
            self.assertIn(window, rt.SINGLE_CORNER_SEED_BUDGET_1LSB_OHM)
            # Every entry must be a figure this helper can format or None.
            seed = rt.SINGLE_CORNER_SEED_BUDGET_1LSB_OHM[window]
            self.assertTrue(seed is None or isinstance(seed, float), window)
            self._note(10e3, seed)  # must not raise for any ratified entry


class TestCornersRecordTtNoteWiring(unittest.TestCase):
    """The call site, not just the helper (issue #882).

    The pure-helper tests above pin the wording; this one drives the real
    `write_corners_record()` over synthetic corner points to prove the
    record actually gets the measured tt budget and the window's seed
    figure -- the pre-#882 defect was a call site that compared nothing, so
    a correct helper wired to the wrong arguments would reproduce it. No
    ngspice: provenance resolution is stubbed into a temp dir the same way
    sim/tests/test_full_conversion.py stubs it, and no path under
    sim/vcm-drive-budget/ is written."""

    @staticmethod
    def _corner_point(cid: str, process: str, temp: float, supply: float,
                      budget_ohm: float | None) -> dict:
        """A `run_corners()` point, minus the `rows` the record writer does
        not read."""
        return {
            "corner": process, "temp_c": temp, "supply_v": supply,
            "corner_id": cid,
            "budget_1lsb_ohm": budget_ohm,
            "budget_1lsb_censored": False,
            "budget_p1lsb_ohm": None,
        }

    def _record_text(self, tt_budget_ohm: float | None,
                     window: str = "worst",
                     points: list[dict] | None = None,
                     info: dict | None = None,
                     artifacts: dict[str, str] | None = None) -> str:
        from harness import evidence

        points = points if points is not None else [
            self._corner_point("tt_27c_1.80v", "tt", 27.0, rt.VDD_NOM,
                               tt_budget_ohm),
            self._corner_point("ss_125c_1.62v", "ss", 125.0, 1.62, 1e3),
        ]
        real_dir, real_resolve = rt.EXPERIMENT_DIR, evidence.resolve_provenance

        def fake_resolve(experiment_dir: Path, netlist_text: str):
            (experiment_dir / "netlist-snapshots").mkdir(parents=True,
                                                         exist_ok=True)
            (experiment_dir / "netlist-snapshots" / "REC.spice").write_text(
                netlist_text)
            (experiment_dir / "records").mkdir(parents=True, exist_ok=True)
            return evidence.ProvenanceInfo(
                record_id="REC",
                record_path=experiment_dir / "records" / "REC.md",
                netlist_sha="0" * 64,
                pdk_line="sky130A @ testing",
                ng_version="ngspice-46",
            )

        with tempfile.TemporaryDirectory() as tmp:
            try:
                rt.EXPERIMENT_DIR = Path(tmp)
                evidence.resolve_provenance = fake_resolve
                path = rt.write_corners_record(
                    points, rt.DEFAULT_POINT, window=window,
                    info=info, artifacts=artifacts)
                return path.read_text()
            finally:
                rt.EXPERIMENT_DIR = real_dir
                evidence.resolve_provenance = real_resolve

    def test_a_tt_budget_unequal_to_the_seed_is_reported_as_differing(self):
        """The exact shape of the regression: the `worst` seed figure is
        10000 ohm, so a 100000 ohm tt measurement must not be written up as
        reproducing it."""
        self.assertEqual(rt.SINGLE_CORNER_SEED_BUDGET_1LSB_OHM["worst"], 10e3)
        text = self._record_text(100e3)
        self.assertIn("DIFFER", text)
        self.assertNotIn("reproduces the single-corner record's own finding",
                         text)

    def test_a_tt_budget_equal_to_the_seed_is_reported_as_agreement(self):
        text = self._record_text(
            rt.SINGLE_CORNER_SEED_BUDGET_1LSB_OHM["worst"])
        self.assertIn("reproduces the single-corner record's own finding",
                      text)

    def test_the_note_is_written_into_the_records_result_section(self):
        text = self._record_text(100e3)
        result = text.split("## Result", 1)[1]
        self.assertIn("The `tt`/27C/1.8V point in this grid", result)

    def test_no_path_under_the_real_experiment_dir_is_written(self):
        """`sim/` evidence is append-only; this test must mint nothing."""
        before = sorted(
            p.name for p in (rt.EXPERIMENT_DIR / "records").iterdir())
        self._record_text(100e3)
        after = sorted(
            p.name for p in (rt.EXPERIMENT_DIR / "records").iterdir())
        self.assertEqual(before, after)


# ---------------------------------------------------------------------------
# The `klt sim` port of the --corners paths (issue #881)
# ---------------------------------------------------------------------------
#: The per-(sweep, window) step counts the port is contracted to produce:
#: the bare sweep's own list, plus (for the decouple leg) one step per
#: (non-zero swept R_source, non-zero swept C_decouple) pair. 8 + 7x4 = 36
#: at the worst window; 3 + 2x4 = 11 at the legacy one.
EXPECTED_STEP_COUNTS = {
    ("rsource", "worst"): 8,
    ("rsource", "legacy"): 3,
    ("decouple", "worst"): 36,
    ("decouple", "legacy"): 11,
}


def _report(corner_values: dict[str, dict], *, statuses: dict | None = None,
            environment: dict | None = None) -> dict:
    """A minimal `klt sim` report over `{corner_id: {meas_name: value}}`."""
    statuses = statuses or {}
    corners = []
    for cid, values in corner_values.items():
        process, temp_c, supply_v = rt.corners_mod.parse_corner_id(cid)
        corners.append({
            "process": process,
            "temperature_c": temp_c,
            "supply_v": {rt.SUPPLY_KEY: supply_v},
            "status": statuses.get(cid, "pass"),
            "measurements": [
                {"name": name, "value": value, "unit": "V"}
                for name, value in values.items()
            ],
        })
    return {"status": "pass", "corners": corners,
            "environment": environment or {}}


def _step_values(diff_by_step: dict[str, float], *, vcm: float = 0.9) -> dict:
    """`{"<step>.<meas>": value}` for a corner, from a per-step differential.

    TOP_P carries the whole differential so `top_p_end - top_n_end` is
    exactly the requested value; the remaining three reads are finite
    constants, since the row decoder requires every one of MEASURE_NAMES to
    be finite before it will build a row."""
    out: dict[str, float] = {}
    for step, diff in diff_by_step.items():
        out[f"{step}.top_p_end"] = diff
        out[f"{step}.top_n_end"] = 0.0
        out[f"{step}.bp_p_end"] = vcm
        out[f"{step}.bp_n_end"] = vcm
        out[f"{step}.vcm_end"] = vcm
    return out


class TestCornersDeckBody(unittest.TestCase):
    """The one shared deck body (issue #881)."""

    def test_the_body_omits_what_klt_emits_itself(self):
        body = rt.build_corners_body("worst")
        for card in (".lib", ".temp", ".control", ".endc", ".end"):
            self.assertNotIn(f"\n{card}", f"\n{body}")

    def test_the_dut_fragment_is_inserted_verbatim(self):
        body = rt.build_corners_body("worst")
        fragment = rt.DUT_FRAGMENT.read_text().rstrip("\n")
        self.assertIn(fragment, body)

    def test_the_supply_source_is_named_for_the_corner_axis_key(self):
        """`klt sim` applies the supply axis as a literal `alter <key>=<v>`,
        so a deck that names the source anything else silently simulates the
        nominal supply at all nine corners."""
        body = rt.build_corners_body("worst")
        self.assertIn(f"{rt.SUPPLY_KEY} VDD 0 DC {rt.VDD_NOM}", body)
        req = rt.build_corners_request("tb.spice", rt.corner_ids(), "worst")
        self.assertEqual(list(req["corners"]["supply_v"]), [rt.SUPPLY_KEY])

    def test_vcm_and_sample_track_the_corners_own_supply(self):
        """The per-corner deck wrote both as corner-dependent literals; one
        shared body cannot, so both go through behavioural sources."""
        body = rt.build_corners_body("worst")
        self.assertIn(f"Bvcm VCM_IDEAL 0 V=v(VDD)*{rt.VCM_FRAC:g}", body)
        self.assertIn("Bsample SAMPLE 0 V=v(SMP_CTL)*v(VDD)", body)
        # ...and the SAMPLE pulse itself is normalised 0..1, carrying no
        # corner-dependent voltage.
        self.assertIn("Vsmp_ctl SMP_CTL 0 pulse(0 1 ", body)
        self.assertNotIn(f"pulse(0 {rt.VDD_NOM}", body)

    def test_both_alter_targets_are_present_in_every_body(self):
        """A step can only `alter` a card the body already carries -- which
        is why `Cdecouple` is present even though `build_transient()` omits
        it at C_decouple = 0."""
        for window in rt.WINDOW_CONFIG:
            body = rt.build_corners_body(window)
            self.assertIn(f"Rvcm VCM_IDEAL VCM {rt.R_IDEAL_OHM:g}", body)
            self.assertIn(f"Cdecouple VCM 0 {rt.C_IDEAL_F:g}", body)

    def test_the_test_point_voltages_are_the_selected_points(self):
        body = rt.build_corners_body("worst", "common_mode")
        vinp, vinn = rt.TEST_POINTS["common_mode"]
        self.assertIn(f"Vinp VINP 0 dc {vinp:g}", body)
        self.assertIn(f"Vinn VINN 0 dc {vinn:g}", body)


class TestCornersTimingMatchesTheLocalDeck(unittest.TestCase):
    """The ported deck's probe time and transient stop time are the SAME
    arithmetic `build_transient()` uses, not a re-derivation (issue #881).
    A drift here would make every ported figure read at a different instant
    than the records it supersedes, with nothing to show for it."""

    def test_the_probe_and_stop_times_match_build_transient(self):
        for window, (sample_ns, _r) in rt.WINDOW_CONFIG.items():
            deck = rt.build_transient(
                vinp=1.6, vinn=0.2, sample_width_ns=sample_ns,
                r_source_ohm=1e3,
            )
            self.assertIn(
                f"at={rt.corners_probe_ns(window)}n", deck,
                f"{window}: ported probe time is not build_transient()'s",
            )
            self.assertIn(
                f"tran {rt.TRAN_STEP_PS}p {rt.corners_tran_stop_ns(window)}n",
                deck,
                f"{window}: ported transient does not match build_transient()",
            )

    def test_the_steps_carry_that_same_timing(self):
        for window in rt.WINDOW_CONFIG:
            step = rt.corners_analysis_steps(window)[0]
            self.assertEqual(
                step["analysis"]["args"],
                f"{rt.TRAN_STEP_PS}p {rt.corners_tran_stop_ns(window)}n",
            )


class TestCornersRequestShape(unittest.TestCase):
    """The request the fleet is asked to solve (issue #881)."""

    def test_step_count_per_sweep_and_window(self):
        for (sweep, window), expected in EXPECTED_STEP_COUNTS.items():
            steps = rt.corners_analysis_steps(window, sweep)
            self.assertEqual(
                len(steps), expected,
                f"{sweep}/{window}: expected {expected} steps, got {len(steps)}",
            )

    def test_the_decouple_leg_is_the_bare_leg_plus_the_crossed_pairs(self):
        """Derived from the sweep lists rather than from the literal counts
        above, so changing a sweep list cannot leave the contract behind."""
        for window, (_s, r_list) in rt.WINDOW_CONFIG.items():
            nonzero_r = [r for r in r_list if r > 0]
            nonzero_c = [c for c in rt.C_DECOUPLE_SWEEP_F if c > 0]
            self.assertEqual(
                len(rt.corners_analysis_steps(window, "decouple")),
                len(r_list) + len(nonzero_r) * len(nonzero_c),
            )

    def test_step_names_are_unique(self):
        for (sweep, window) in EXPECTED_STEP_COUNTS:
            names = [s["name"] for s in rt.corners_analysis_steps(window, sweep)]
            self.assertEqual(len(names), len(set(names)), f"{sweep}/{window}")

    def test_every_step_alters_both_targets(self):
        """`reset: true` re-parses the deck per step, so a step that altered
        only one target would silently use the body's own stand-in for the
        other -- which is a measurement of a point nobody asked for."""
        for (sweep, window) in EXPECTED_STEP_COUNTS:
            for step in rt.corners_analysis_steps(window, sweep):
                self.assertTrue(step["reset"])
                self.assertEqual(set(step["alter"]), {"Rvcm", "Cdecouple"})

    def test_the_control_rows_are_stand_ins_never_literal_zero(self):
        steps = {s["name"]: s for s in rt.corners_analysis_steps("worst", "decouple")}
        bare0 = steps[rt.corners_step_name(0.0)]
        self.assertEqual(bare0["alter"]["Rvcm"], rt.R_IDEAL_OHM)
        self.assertEqual(bare0["alter"]["Cdecouple"], rt.C_IDEAL_F)
        for step in steps.values():
            self.assertGreater(step["alter"]["Rvcm"], 0.0)
            self.assertGreater(step["alter"]["Cdecouple"], 0.0)

    def test_the_decouple_pairs_cover_every_marginal_r_source_reachable(self):
        """`marginal_r_source()` returns either the largest swept value or
        the first row past 1 LSB -- never the control row, whose error is
        zero by construction. So enumerating the NON-ZERO swept resistances
        covers every value a corner's own bare sweep can select, which is
        what lets the two-stage campaign be one request."""
        for window, (_s, r_list) in rt.WINDOW_CONFIG.items():
            names = {s["name"] for s in rt.corners_analysis_steps(window, "decouple")}
            for r in r_list:
                rows = _r_rows([(x, 0.0 if x == 0 else (9.0 if x >= r else 0.0))
                                for x in r_list])
                marginal = rt.marginal_r_source(rows, r_list)
                for c in rt.C_DECOUPLE_SWEEP_F:
                    self.assertIn(rt.corners_step_name(marginal, c), names)

    def test_the_c_decouple_zero_control_is_the_bare_step(self):
        """The decouple leg's control row is that corner's own bare row at
        the same resistance, from the same solve -- not a duplicate step."""
        self.assertEqual(rt.corners_step_name(1e3, 0.0), rt.corners_step_name(1e3))
        names = [s["name"] for s in rt.corners_analysis_steps("worst", "decouple")]
        self.assertEqual(names.count(rt.corners_step_name(1e3)), 1)

    def test_the_oat_exclude_leaves_exactly_the_nine_grid_points(self):
        cids = rt.corner_ids()
        self.assertEqual(len(cids), 9)
        req = rt.build_corners_request("tb.spice", cids, "worst")
        axes = req["corners"]
        full = (len(axes["process"]) * len(axes["temperature_c"])
                * len(axes["supply_v"][rt.SUPPLY_KEY]))
        self.assertEqual(full - len(req["exclude"]), len(cids))

    def test_the_excluded_points_are_exactly_the_complement(self):
        cids = set(rt.corner_ids())
        req = rt.build_corners_request("tb.spice", sorted(cids), "worst")
        for ex in req["exclude"]:
            cid = rt.corners_mod.corner_id(
                ex["process"], ex["temperature_c"], ex["supply_v"][rt.SUPPLY_KEY]
            )
            self.assertNotIn(cid, cids)

    def test_measurement_names_are_the_drivers_own_and_never_a_node_name(self):
        """An ngspice `.meas` result is written as a vector into the step's
        own plot, so a measurement named after a node overwrites that node's
        waveform and breaks every later card in the step that reads it."""
        nodes = {"TOP_P", "TOP_N", "BPREF_P", "BPREF_N", "VCM"}
        for step in rt.corners_analysis_steps("worst", "decouple"):
            names = [m["name"] for m in step["measurements"]]
            self.assertEqual(names, rt.MEASURE_NAMES)
            for name in names:
                self.assertNotIn(name.upper(), nodes)

    def test_the_whole_job_bound_stays_inside_the_fleet_ceiling(self):
        """`timeout_s * units + 120` is the bound the fleet refuses a job
        on; 9 units at the default timeout must stay under the 3600 s
        ceiling DEFAULT_TIMEOUT_S's own comment names."""
        units = len(rt.corner_ids())
        self.assertLess(rt.DEFAULT_TIMEOUT_S * units + 120, 3600)


class TestReadCornersReport(unittest.TestCase):
    """Report decoding (issue #881)."""

    def test_measurements_are_keyed_by_step_dot_name(self):
        cid = "tt_27c_1.80v"
        values = _step_values({rt.corners_step_name(0.0): 1.4})
        results, _info = rt.read_corners_report(_report({cid: values}))
        self.assertEqual(results[cid], values)

    def test_an_error_corner_is_nulled_not_read_as_a_measurement(self):
        cid = "ss_125c_1.62v"
        values = _step_values({rt.corners_step_name(0.0): 1.4})
        for status in ("error", "inconclusive"):
            results, _info = rt.read_corners_report(
                _report({cid: values}, statuses={cid: status})
            )
            self.assertTrue(all(v is None for v in results[cid].values()), status)

    def test_an_error_envelope_is_refused_rather_than_read_as_zero_corners(self):
        with self.assertRaises(ValueError):
            rt.read_corners_report({"error": {"code": "batch_no_capacity"}})

    def test_run_info_is_threaded_through(self):
        report = _report(
            {"tt_27c_1.80v": _step_values({rt.corners_step_name(0.0): 1.4})},
            environment={"backend": "batch", "remote": {
                "job_id": "job-1", "state": "SUCCEEDED",
                "worker_environment": {
                    "pdk": {"variant": "sky130A", "stamp_text": "stamp abc123"},
                    "simulator": {"version_banner": "** ngspice-47 : x"},
                },
            }},
        )
        _results, info = rt.read_corners_report(report)
        self.assertEqual(info["job_id"], "job-1")
        self.assertEqual(info["worker_pdk"], "sky130A @ abc123")
        self.assertEqual(info["worker_ngspice"], "ngspice-47")


class TestCornerRowDecoding(unittest.TestCase):
    """`_rows_from_steps()` builds exactly the row shape `run_sweep()` /
    `run_decouple_sweep()` build, which is what lets `find_budget()` and
    both record writers be unchanged by the port (issue #881)."""

    def test_bare_rows_carry_the_sweep_axis_and_the_relative_error(self):
        window = "worst"
        _s, r_list = rt.WINDOW_CONFIG[window]
        diffs = {rt.corners_step_name(r): 1.4 + i * 1e-3
                 for i, r in enumerate(r_list)}
        rows = rt.corner_bare_rows(_step_values(diffs), window)
        self.assertEqual([r["r_source_ohm"] for r in rows], r_list)
        # Referenced to the sweep's OWN first row, exactly as run_sweep().
        self.assertEqual(rows[0]["diff_err_mv"], 0.0)
        self.assertAlmostEqual(rows[1]["diff_err_mv"], 1.0)
        self.assertAlmostEqual(
            rows[1]["diff_err_lsb"], 1.0 / rt.LSB_DIFF_MV_PROVISIONAL
        )
        for row in rows:
            for key in rt.MEASURE_NAMES + ["diff_v", "diff_err_mv", "diff_err_lsb"]:
                self.assertIn(key, row)

    def test_decouple_rows_read_the_requested_resistance(self):
        marginal = 10e3
        diffs = {rt.corners_step_name(marginal): 1.4}
        diffs.update({
            rt.corners_step_name(marginal, c): 1.4 + i * 1e-3
            for i, c in enumerate(rt.C_DECOUPLE_SWEEP_F[1:], start=1)
        })
        rows = rt.corner_decouple_rows(_step_values(diffs), marginal)
        self.assertEqual(
            [r["c_decouple_f"] for r in rows], rt.C_DECOUPLE_SWEEP_F
        )
        self.assertEqual(rows[0]["diff_err_mv"], 0.0)

    def test_a_missing_step_makes_the_whole_sweep_none(self):
        """Never a partial sweep: a budget read off one would silently be a
        budget over a different sweep list."""
        window = "worst"
        _s, r_list = rt.WINDOW_CONFIG[window]
        diffs = {rt.corners_step_name(r): 1.4 for r in r_list}
        values = _step_values(diffs)
        del values[f"{rt.corners_step_name(r_list[3])}.top_p_end"]
        self.assertIsNone(rt.corner_bare_rows(values, window))

    def test_a_non_finite_step_makes_the_whole_sweep_none(self):
        window = "worst"
        _s, r_list = rt.WINDOW_CONFIG[window]
        diffs = {rt.corners_step_name(r): 1.4 for r in r_list}
        for bad in (None, float("nan"), float("inf")):
            values = _step_values(diffs)
            values[f"{rt.corners_step_name(r_list[2])}.vcm_end"] = bad
            self.assertIsNone(rt.corner_bare_rows(values, window), repr(bad))


class TestRunCornersDecode(unittest.TestCase):
    """`run_corners()` / `run_corners_decouple()` over an injected report."""

    WINDOW = "worst"

    def _bare_diffs(self, failing_from_ohm: float | None) -> dict[str, float]:
        """Per-step differentials whose control-relative error first exceeds
        1 provisional LSB at `failing_from_ohm` (None: never)."""
        _s, r_list = rt.WINDOW_CONFIG[self.WINDOW]
        out = {}
        for r in r_list:
            over = failing_from_ohm is not None and r >= failing_from_ohm
            out[rt.corners_step_name(r)] = (
                1.4 + (2.0 * rt.LSB_DIFF_MV_PROVISIONAL * 1e-3 if over else 0.0)
            )
        return out

    def test_a_corner_with_no_usable_sweep_is_incomplete_not_unbudgeted(self):
        """The distinction the record turns on: `find_budget()` returning
        None is a measurement ("the smallest nonzero swept value already
        exceeds the tier"), an incomplete corner was never measured."""
        cids = rt.corner_ids()
        good = _step_values(self._bare_diffs(None))
        results = {cid: dict(good) for cid in cids}
        del results[cids[1]][f"{rt.corners_step_name(1e3)}.top_p_end"]
        points = rt.run_corners(results, cids, window=self.WINDOW, quiet=True)
        broken = next(p for p in points if p["corner_id"] == cids[1])
        self.assertFalse(broken["complete"])
        self.assertIsNone(broken["rows"])
        self.assertIsNone(broken["budget_1lsb_ohm"])
        self.assertTrue(all(p["complete"] for p in points if p is not broken))

    def test_a_corner_absent_from_the_report_is_incomplete(self):
        cids = rt.corner_ids()
        results = {cid: _step_values(self._bare_diffs(None))
                   for cid in cids if cid != cids[-1]}
        points = rt.run_corners(results, cids, window=self.WINDOW, quiet=True)
        self.assertEqual(len(points), len(cids))
        self.assertFalse(points[-1]["complete"])

    def test_each_corner_takes_its_marginal_from_its_own_bare_sweep(self):
        """The two-stage campaign's whole point: the bare budget spans more
        than an order of magnitude across the grid, so a borrowed tt value
        would not be the marginal case at most corners."""
        cids = rt.corner_ids()
        failing = {cids[0]: 1e3, cids[1]: 30e3}
        results = {}
        for cid in cids:
            diffs = self._bare_diffs(failing.get(cid))
            # The decoupled pairs exist for every non-zero swept resistance.
            _s, r_list = rt.WINDOW_CONFIG[self.WINDOW]
            for r in [x for x in r_list if x > 0]:
                for c in [x for x in rt.C_DECOUPLE_SWEEP_F if x > 0]:
                    diffs[rt.corners_step_name(r, c)] = 1.4
            results[cid] = _step_values(diffs)
        points = rt.run_corners_decouple(results, cids, window=self.WINDOW,
                                         quiet=True)
        by_cid = {p["corner_id"]: p for p in points}
        self.assertEqual(by_cid[cids[0]]["marginal_r_source_ohm"], 1e3)
        self.assertEqual(by_cid[cids[1]]["marginal_r_source_ohm"], 30e3)
        self.assertFalse(by_cid[cids[0]]["marginal_is_fallback"])
        self.assertFalse(by_cid[cids[1]]["marginal_is_fallback"])

    def test_a_corner_that_never_failed_bare_is_a_fallback_with_nothing_to_rescue(self):
        cids = rt.corner_ids()[:1]
        _s, r_list = rt.WINDOW_CONFIG[self.WINDOW]
        diffs = self._bare_diffs(None)
        for r in [x for x in r_list if x > 0]:
            for c in [x for x in rt.C_DECOUPLE_SWEEP_F if x > 0]:
                diffs[rt.corners_step_name(r, c)] = 1.4
        points = rt.run_corners_decouple(
            {cids[0]: _step_values(diffs)}, cids, window=self.WINDOW, quiet=True
        )
        self.assertEqual(points[0]["marginal_r_source_ohm"], r_list[-1])
        self.assertTrue(points[0]["marginal_is_fallback"])
        split = rt.partition_decouple_rescue(points)
        self.assertEqual(split["nothing_to_rescue"], points)
        self.assertEqual(split["needed"], [])

    def test_an_incomplete_decouple_corner_gets_no_marginal_and_no_budget(self):
        cids = rt.corner_ids()[:1]
        _s, r_list = rt.WINDOW_CONFIG[self.WINDOW]
        diffs = self._bare_diffs(1e3)
        for r in [x for x in r_list if x > 0]:
            for c in [x for x in rt.C_DECOUPLE_SWEEP_F if x > 0]:
                diffs[rt.corners_step_name(r, c)] = 1.4
        values = _step_values(diffs)
        values[f"{rt.corners_step_name(1e3, 10e-12)}.top_n_end"] = None
        points = rt.run_corners_decouple({cids[0]: values}, cids,
                                         window=self.WINDOW, quiet=True)
        self.assertFalse(points[0]["complete"])
        self.assertIsNone(points[0]["budget_1lsb_f"])
        # ...and such a corner is on NEITHER side of the rescue verdict.
        complete, incomplete = rt.split_complete(points)
        self.assertEqual(complete, [])
        self.assertEqual(incomplete, points)


class TestPredecessorEnvironment(unittest.TestCase):
    """The uncontrolled-difference statement is read out of the superseded
    record's own Environment block, never transcribed (issue #881)."""

    def test_every_mapped_predecessor_record_exists_and_parses(self):
        for key, record_id in rt.CORNERS_PREDECESSOR_RECORD.items():
            path = rt.EXPERIMENT_DIR / "records" / f"{record_id}.md"
            self.assertTrue(path.is_file(), f"{key}: missing {path}")
            env = rt.predecessor_environment(*key)
            self.assertEqual(env["record"], record_id)
            self.assertTrue(env["pdk"], f"{key}: no PDK line parsed")
            self.assertTrue(env["ngspice"], f"{key}: no ngspice line parsed")
            self.assertIn("@", env["pdk"])

    def test_every_sweep_and_window_combination_is_mapped(self):
        for sweep in ("rsource", "decouple"):
            for window in rt.WINDOW_CONFIG:
                self.assertIn((sweep, window), rt.CORNERS_PREDECESSOR_RECORD)
                self.assertIn((sweep, window), rt.CORNERS_SUPERSEDES_RECORD)

    def test_a_missing_record_yields_none_rather_than_a_guess(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = rt.predecessor_environment("rsource", "worst", Path(tmp))
            self.assertIsNone(env["pdk"])
            self.assertIsNone(env["ngspice"])


class TestCornersRecordPortSections(TestCornersRecordTtNoteWiring):
    """What a post-port `--corners` record must say (issue #881).

    Reuses the parent's record-writing fixture (synthetic points, stubbed
    provenance, nothing written under the real experiment dir)."""

    INFO = {
        "status": "pass",
        "backend": "batch",
        "job_id": "job-42",
        "jobs": [{"job_id": "job-42", "state": "SUCCEEDED", "exit_code": 0,
                  "instance_type": "m7i.4xlarge", "elapsed_seconds": 61,
                  "runner_klt_version": "klt 9.9.9"}],
        "worker_pdk": "sky130A @ deadbeef",
        "worker_ngspice": "ngspice-47",
        "sharded": False,
    }

    def _incomplete_point(self, cid: str) -> dict:
        p = self._corner_point(cid, "ff", -40.0, 1.8, None)
        p["complete"] = False
        return p

    def test_the_klt_run_block_names_the_job_and_the_committed_artifacts(self):
        text = self._record_text(100e3, info=self.INFO)
        self.assertIn("## `klt sim` run", text)
        self.assertIn("job `job-42`", text)
        self.assertIn("m7i.4xlarge", text)
        self.assertIn("request/", text)
        self.assertIn("report.json", text)

    def test_the_environment_names_the_executing_worker_not_the_submitter(self):
        text = self._record_text(100e3, info=self.INFO)
        self.assertIn("- PDK: sky130A @ deadbeef", text)
        self.assertIn("- ngspice: ngspice-47", text)
        self.assertIn("as run by the executing worker", text)
        self.assertIn("submitting host PDK / ngspice", text)
        self.assertIn("klt (client)", text)
        self.assertIn("klt (fleet runner)", text)
        self.assertIn("klt 9.9.9", text)

    def test_an_unreported_worker_falls_back_to_the_submitting_host_and_says_so(self):
        text = self._record_text(100e3, info={"status": "pass"})
        self.assertIn("submitting host (executing worker did not report)", text)
        self.assertIn("The worker did NOT report them for this run", text)

    def test_every_deck_change_the_port_made_is_stated(self):
        text = self._record_text(100e3, info=self.INFO)
        self.assertIn("Uncontrolled differences against the record this "
                      "supersedes", text)
        self.assertIn("Execution route", text)
        for change in rt.DECK_PORT_CHANGES:
            head = change.split(".**")[0].lstrip("*")
            self.assertIn(head, text)

    def test_the_pdk_and_simulator_difference_is_stated_against_the_predecessor(self):
        text = self._record_text(100e3, info=self.INFO)
        prev = rt.predecessor_environment("rsource", "worst")
        # The fixture's EXPERIMENT_DIR is a temp dir, so the predecessor
        # record is not readable from it -- the writer must say so rather
        # than invent a comparison.
        self.assertIn(prev["record"], text)
        self.assertIn("could not be read from this tree", text)

    def test_an_incomplete_corner_is_never_given_a_budget_or_counted(self):
        points = [
            self._corner_point("tt_27c_1.80v", "tt", 27.0, rt.VDD_NOM, 100e3),
            self._incomplete_point("ff_-40c_1.80v"),
        ]
        text = self._record_text(None, points=points, info=self.INFO)
        self.assertIn("| `ff_-40c_1.80v` | (incomplete) | (incomplete) |", text)
        result = text.split("## Result", 1)[1]
        self.assertIn("INCOMPLETE at 1 of 2 ratified corners", result)
        self.assertIn("`ff_-40c_1.80v`", result)
        # The incomplete corner must NOT be reported as a measured corner
        # with no budget -- that is a different, stronger statement.
        self.assertNotIn("no positive 1-LSB budget at all", result)

    def test_with_every_corner_complete_no_incomplete_note_is_written(self):
        text = self._record_text(100e3, info=self.INFO)
        self.assertNotIn("INCOMPLETE at", text)

    def test_the_reproduction_block_names_the_fleet_not_a_local_loop(self):
        text = self._record_text(100e3, info=self.INFO)
        self.assertIn("ONE `klt sim` request submitted to the batch fleet", text)
        self.assertIn(f"--wait-for-capacity {rt.CAPACITY_WAIT_S:g}", text)


class TestCornersDecoupleRecordPortSections(unittest.TestCase):
    """The same post-port sections on the C_decouple writer (issue #881)."""

    def _record_text(self, points: list[dict], window: str = "worst") -> str:
        from harness import evidence

        real_dir, real_resolve = rt.EXPERIMENT_DIR, evidence.resolve_provenance

        def fake_resolve(experiment_dir: Path, netlist_text: str):
            (experiment_dir / "netlist-snapshots").mkdir(parents=True,
                                                         exist_ok=True)
            (experiment_dir / "netlist-snapshots" / "REC.spice").write_text(
                netlist_text)
            (experiment_dir / "records").mkdir(parents=True, exist_ok=True)
            return evidence.ProvenanceInfo(
                record_id="REC",
                record_path=experiment_dir / "records" / "REC.md",
                netlist_sha="0" * 64,
                pdk_line="sky130A @ testing",
                ng_version="ngspice-46",
            )

        with tempfile.TemporaryDirectory() as tmp:
            try:
                rt.EXPERIMENT_DIR = Path(tmp)
                evidence.resolve_provenance = fake_resolve
                return rt.write_corners_decouple_record(
                    points, rt.DEFAULT_POINT, window=window,
                    info=TestCornersRecordPortSections.INFO,
                    artifacts={"request.json": "{}", "tb.spice": "* deck",
                               "report.json": "{}"},
                ).read_text()
            finally:
                rt.EXPERIMENT_DIR = real_dir
                evidence.resolve_provenance = real_resolve

    @staticmethod
    def _point(cid: str, *, complete: bool = True,
               budget_f: float | None = 10e-12,
               fallback: bool = False) -> dict:
        process, temp_c, supply_v = rt.corners_mod.parse_corner_id(cid)
        rows = [
            {"c_decouple_f": c, "vcm_end": 0.9,
             "diff_err_mv": 0.0, "diff_err_lsb": 0.0}
            for c in rt.C_DECOUPLE_SWEEP_F
        ] if complete else None
        return {
            "corner": process, "temp_c": temp_c, "supply_v": supply_v,
            "corner_id": cid, "rows": rows, "bare_rows": rows,
            "complete": complete,
            "marginal_r_source_ohm": 10e3 if complete else None,
            "marginal_is_fallback": fallback,
            "budget_1lsb_f": budget_f if complete else None,
            "budget_1lsb_censored": False,
        }

    def test_the_port_sections_are_present(self):
        text = self._record_text([self._point("tt_27c_1.80v")])
        self.assertIn("## `klt sim` run", text)
        self.assertIn("job `job-42`", text)
        self.assertIn("Uncontrolled differences against the record this "
                      "supersedes", text)
        self.assertIn("- PDK: sky130A @ deadbeef", text)
        self.assertIn("ONE `klt sim` request submitted to the batch fleet", text)
        for change in rt.DECK_PORT_CHANGES:
            self.assertIn(change.split(".**")[0].lstrip("*"), text)

    def test_an_incomplete_corner_is_excluded_from_the_rescue_counts(self):
        points = [
            self._point("tt_27c_1.80v", fallback=True),
            self._point("ff_-40c_1.80v", complete=False),
        ]
        text = self._record_text(points)
        self.assertIn("| `ff_-40c_1.80v` | (incomplete) | (incomplete) |", text)
        result = text.split("## Result", 1)[1]
        self.assertIn("INCOMPLETE at 1 of 2 ratified corners", result)
        # The verdict counts are over the ONE corner that completed.
        self.assertIn("1 of 1 ratified corners had nothing for decoupling "
                      "to rescue", result)

    def test_a_rescued_corner_is_counted_over_complete_corners_only(self):
        points = [
            self._point("tt_27c_1.80v", budget_f=10e-12),
            self._point("ss_125c_1.62v", complete=False),
        ]
        result = self._record_text(points).split("## Result", 1)[1]
        self.assertIn("1 of the 1 ratified corner(s) whose bare R_source "
                      "sweep actually failed", result)


if __name__ == "__main__":
    unittest.main()

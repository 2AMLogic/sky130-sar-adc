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
  reachable."""

from __future__ import annotations

import importlib.util
import sys
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


if __name__ == "__main__":
    unittest.main()

"""PDK-free unit tests for sim/input-drive-budget/run_input_drive_budget.py
(issue #847): budget tiers (right-censoring, the control-relative subtraction,
a control row outside a tier), the `klt sim` request shape (9 corners, both
windows, 0 and 1e3 ohm present, both axes as analysis steps), the deck body's
alter targets, and the report reader's error-envelope handling.

No ngspice, no PDK, no network: every test here builds its own report dict or
reads the committed DUT fragment.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(SIM_DIR / "input-drive-budget"))

import run_input_drive_budget as m  # noqa: E402


def _rows(window: str, pairs: list[tuple[float, float]]) -> list[dict]:
    """A sweep from (R_source, raw differential error in mV) pairs, routed
    through the real `sweep_rows()` so the control-relative arithmetic under
    test is the shipped one, not a re-implementation."""
    values: dict[str, float] = {}
    for r_source, raw_err_mv in pairs:
        name = m.step_name(window, r_source)
        # Put the whole error on TOP_P; the observable is the difference.
        values[f"{name}.budget_p"] = m.V_FINAL_P + raw_err_mv / 1e3
        values[f"{name}.budget_n"] = m.V_FINAL_N
        values[f"{name}.confirm_p"] = m.V_FINAL_P
        values[f"{name}.confirm_n"] = m.V_FINAL_N
    rows = m.sweep_rows(values, window, [r for r, _ in pairs])
    assert rows is not None
    return rows


class TestBudgetTiers(unittest.TestCase):
    SWEEP = [0.0, 100.0, 1e3, 10e3]

    def test_largest_passing_value_wins(self):
        # 1 LSB = 3.5156 mV. 1e3 passes 1 LSB, 10e3 does not.
        rows = _rows("worst", [(0.0, 0.0), (100.0, 0.1), (1e3, 2.0), (10e3, 40.0)])
        self.assertEqual(m.find_budget(rows, 1.0)["r_source_ohm"], 1e3)
        # ...and the 0.1-LSB tier (0.35156 mV) stops one point earlier.
        self.assertEqual(m.find_budget(rows, 0.1)["r_source_ohm"], 100.0)

    def test_every_value_passing_is_right_censored(self):
        rows = _rows("worst", [(0.0, 0.0), (100.0, 0.01), (1e3, 0.02), (10e3, 0.03)])
        s = m.budget_summary(rows, self.SWEEP)
        self.assertEqual(s["tiers"][1.0]["budget_ohm"], 10e3)
        self.assertTrue(s["tiers"][1.0]["right_censored"])
        self.assertIn("right-censored", m.format_budget(s["tiers"][1.0], s))
        self.assertIn(">= 10000", m.format_budget(s["tiers"][1.0], s))

    def test_a_measured_budget_is_not_labelled_censored(self):
        rows = _rows("worst", [(0.0, 0.0), (100.0, 0.1), (1e3, 2.0), (10e3, 40.0)])
        s = m.budget_summary(rows, self.SWEEP)
        self.assertFalse(s["tiers"][1.0]["right_censored"])
        self.assertEqual(m.format_budget(s["tiers"][1.0], s), "1000")

    def test_first_nonzero_already_failing_is_none_not_zero(self):
        rows = _rows("worst", [(0.0, 0.0), (100.0, 40.0), (1e3, 80.0), (10e3, 90.0)])
        s = m.budget_summary(rows, self.SWEEP)
        self.assertIsNone(s["tiers"][1.0]["budget_ohm"])
        self.assertEqual(m.format_budget(s["tiers"][1.0], s), "< 100 (none found)")

    def test_control_row_is_subtracted_not_ignored(self):
        """A corner whose R_source=0 row is already 2 mV off the ideal target
        must not spend that 2 mV of its own budget: every error is relative to
        that row, so an identical sweep shape yields an identical budget."""
        offset = 2.0
        shifted = _rows(
            "worst",
            [(0.0, offset), (100.0, offset + 0.1), (1e3, offset + 2.0),
             (10e3, offset + 40.0)],
        )
        clean = _rows(
            "worst", [(0.0, 0.0), (100.0, 0.1), (1e3, 2.0), (10e3, 40.0)]
        )
        self.assertAlmostEqual(shifted[0]["ctrl_err_mv"], offset, places=9)
        self.assertAlmostEqual(shifted[0]["err_mv"], 0.0, places=9)
        for a, b in zip(shifted, clean, strict=True):
            self.assertAlmostEqual(a["err_mv"], b["err_mv"], places=9)
        self.assertEqual(
            m.find_budget(shifted, 1.0)["r_source_ohm"],
            m.find_budget(clean, 1.0)["r_source_ohm"],
        )
        # ...and the raw error still reaches the record, so the offset is
        # visible rather than silently subtracted away.
        self.assertAlmostEqual(shifted[0]["raw_err_mv"], offset, places=9)

    def test_control_row_outside_a_tier_is_flagged(self):
        """tt_27c_1.62v's own -0.38 mV baseline (~0.11 LSB) is outside the
        0.1-LSB tier with no source resistance at all. The relative budget is
        still readable; the flag is what stops the record claiming a raw one."""
        rows = _rows(
            "worst",
            [(0.0, -0.38), (100.0, -0.38), (1e3, -0.30), (10e3, 40.0)],
        )
        s = m.budget_summary(rows, self.SWEEP)
        self.assertTrue(s["tiers"][0.1]["control_outside_tier"])
        self.assertFalse(s["tiers"][1.0]["control_outside_tier"])
        # The relative budget is unaffected by the offset baseline.
        self.assertEqual(s["tiers"][0.1]["budget_ohm"], 1e3)

    def test_sweep_must_start_at_zero(self):
        with self.assertRaises(ValueError):
            m.sweep_rows({}, "worst", [100.0, 1e3])

    def test_partial_sweep_is_refused_whole(self):
        """One missing point nulls the whole sweep: a budget read off a short
        sweep would silently be a budget over a different sweep list."""
        values: dict[str, float | None] = {}
        for r in self.SWEEP:
            name = m.step_name("worst", r)
            for meas in ("budget_p", "budget_n", "confirm_p", "confirm_n"):
                values[f"{name}.{meas}"] = 1.0
        values[f"{m.step_name('worst', 1e3)}.budget_p"] = None
        self.assertIsNone(m.sweep_rows(values, "worst", self.SWEEP))

    def test_non_finite_is_refused_like_missing(self):
        values: dict[str, float] = {}
        for r in self.SWEEP:
            name = m.step_name("worst", r)
            for meas in ("budget_p", "budget_n", "confirm_p", "confirm_n"):
                values[f"{name}.{meas}"] = 1.0
        values[f"{m.step_name('worst', 100.0)}.confirm_n"] = float("nan")
        self.assertIsNone(m.sweep_rows(values, "worst", self.SWEEP))


class TestSweepList(unittest.TestCase):
    def test_zero_and_one_kilohm_are_simulated_points(self):
        """0 is the control row; 1 kOhm is the series source impedance
        spec/target-spec.md's DRAFT Kickback row already names on these pins,
        so no statement about it may rest on interpolation."""
        self.assertEqual(m.R_SOURCE_SWEEP_OHM[0], 0.0)
        self.assertIn(1e3, m.R_SOURCE_SWEEP_OHM)

    def test_sweep_is_strictly_ascending(self):
        """find_budget() takes the LAST passing row, which is only the largest
        passing value if the list ascends."""
        self.assertEqual(
            m.R_SOURCE_SWEEP_OHM, sorted(set(m.R_SOURCE_SWEEP_OHM))
        )

    def test_zero_is_emitted_as_a_tiny_resistance_not_a_literal_zero(self):
        self.assertEqual(m.r_source_effective(0.0), m.R_IDEAL_OHM)
        self.assertEqual(m.r_source_effective(1e3), 1e3)
        with self.assertRaises(ValueError):
            m.r_source_effective(-1.0)


class TestWindows(unittest.TestCase):
    def test_both_campaign_windows_are_covered(self):
        """`sim/vcm-drive-budget/`'s two windows, which is what the issue's
        'both acquisition windows the sampling front end's campaigns use'
        resolves to."""
        self.assertEqual(sorted(m.WINDOWS), ["legacy", "worst"])
        self.assertAlmostEqual(m.WINDOWS["worst"], 1.0e3 / 12.0, places=9)
        self.assertEqual(m.WINDOWS["legacy"], 400.0)

    def test_worst_window_reproduces_the_mirrored_runner_timing(self):
        """The `worst` window must reproduce
        sim/sampling-acquisition-settling/run_acquisition_settling.py's own
        pulse #2 width (150 ns), probe (243.433... ns) and confirm (305 ns),
        because this campaign's control row is compared against that
        campaign's records."""
        t = m.window_timing(m.WINDOWS["worst"])
        self.assertAlmostEqual(t["sample2_width_ns"], 150.0, places=6)
        self.assertAlmostEqual(t["sample2_fall_ns"], 310.0, places=6)
        self.assertAlmostEqual(t["tran_stop_ns"], 330.0, places=6)
        self.assertAlmostEqual(t["probe_ns"], 160.1 + 1.0e3 / 12.0, places=9)
        self.assertAlmostEqual(t["confirm_ns"], 305.0, places=6)

    def test_legacy_window_widens_pulse_two_past_its_probe(self):
        """The 400 ns window does not fit the mirrored runner's fixed 150 ns
        pulse #2, so the pulse (and the transient) must grow with the window --
        otherwise the probe would land after SAMPLE fell and read the
        documented turn-off kick instead of the acquired value."""
        t = m.window_timing(m.WINDOWS["legacy"])
        self.assertGreater(t["sample2_fall_ns"], t["probe_ns"])
        self.assertGreater(t["confirm_ns"], t["probe_ns"])
        self.assertLess(t["confirm_ns"], t["sample2_fall_ns"])
        self.assertGreater(t["tran_stop_ns"], t["sample2_fall_ns"])

    def test_every_window_probes_strictly_inside_sample_pulse_two(self):
        for window, ns in m.WINDOWS.items():
            t = m.window_timing(ns)
            self.assertGreater(t["probe_ns"], m.T_SAMPLE2_RISE_NS, window)
            self.assertLess(t["probe_ns"], t["sample2_fall_ns"], window)

    def test_nonpositive_window_refused(self):
        for bad in (0.0, -1.0, None):
            with self.assertRaises((ValueError, TypeError)):
                m.window_timing(bad)

    def test_sample_waveform_is_normalised(self):
        """The SAMPLE pwl is altered per step and one deck serves every
        corner, so its levels must carry no supply voltage -- the deck's
        behavioural source multiplies by v(VDD)."""
        for ns in m.WINDOWS.values():
            levels = {v for _t, v in m.sample_pwl_points(ns)}
            self.assertEqual(levels, {0.0, 1.0})

    def test_input_waveform_spans_the_longest_window(self):
        """VINP/VINN are NOT altered per step, so their single vector must
        still be defined at the longest window's transient stop."""
        longest = max(m.window_timing(w)["tran_stop_ns"] for w in m.WINDOWS.values())
        for side, pts in m.input_pwl_points(longest).items():
            self.assertAlmostEqual(pts[-1][0], longest, places=6, msg=side)
            self.assertGreater(pts[-1][0], m.T_INPUT_TOGGLE_NS, side)

    def test_input_steps_during_hold_not_during_sampling(self):
        """The step must land while Msw is off, between pulse #1's fall and
        pulse #2's rise -- otherwise the source itself perturbs TOP_x."""
        self.assertGreater(m.T_INPUT_TOGGLE_NS, m.T_SAMPLE1_FALL_NS)
        self.assertLess(
            m.T_INPUT_TOGGLE_NS + m.EDGE_TR_NS, m.T_SAMPLE2_RISE_NS
        )


class TestRequestShape(unittest.TestCase):
    def setUp(self):
        self.cids = m.corner_ids()
        self.req = m.build_request("tb.spice", self.cids)

    def test_nine_ratified_corners(self):
        self.assertEqual(len(self.cids), 9)
        self.assertIn("tt_27c_1.80v", self.cids)
        self.assertIn("tt_27c_1.62v", self.cids)
        self.assertEqual(len(set(self.cids)), 9)

    def test_excluded_points_reduce_the_cross_product_to_the_oat_grid(self):
        c = self.req["corners"]
        full = (
            len(c["process"])
            * len(c["temperature_c"])
            * len(c["supply_v"][m.SUPPLY_KEY])
        )
        self.assertEqual(full - len(self.req["exclude"]), len(self.cids))

    def test_both_axes_are_analysis_steps_in_one_request(self):
        """The grid is ONE klt sim request carrying corners, windows and
        resistances -- not a hand-launched ngspice loop and not one request
        per sweep value."""
        steps = self.req["analysis_steps"]
        self.assertEqual(
            len(steps), len(m.WINDOWS) * len(m.R_SOURCE_SWEEP_OHM)
        )
        self.assertNotIn("analysis", self.req)
        for window in m.WINDOWS:
            for r in m.R_SOURCE_SWEEP_OHM:
                self.assertIn(
                    m.step_name(window, r), {s["name"] for s in steps}
                )

    def test_step_names_are_unique_and_vector_safe(self):
        names = [s["name"] for s in self.req["analysis_steps"]]
        self.assertEqual(len(names), len(set(names)))
        for name in names:
            self.assertRegex(name, r"^[A-Za-z_][A-Za-z0-9_]*$")

    def test_each_step_alters_both_series_resistors_together(self):
        for step in self.req["analysis_steps"]:
            self.assertEqual(step["alter"]["Rsp"], step["alter"]["Rsn"])
            self.assertGreater(step["alter"]["Rsp"], 0.0)

    def test_each_step_resets_so_no_override_leaks_forward(self):
        for step in self.req["analysis_steps"]:
            self.assertTrue(step["reset"])

    def test_each_step_carries_its_own_window_and_probe_times(self):
        for window, ns in m.WINDOWS.items():
            t = m.window_timing(ns)
            for r in m.R_SOURCE_SWEEP_OHM:
                step = next(
                    s for s in self.req["analysis_steps"]
                    if s["name"] == m.step_name(window, r)
                )
                self.assertEqual(step["analysis"]["kind"], "tran")
                self.assertIn(f"{t['tran_stop_ns']:.6f}n", step["analysis"]["args"])
                cards = {me["name"]: me["spice"] for me in step["measurements"]}
                self.assertIn(f"at={t['probe_ns']:.6f}n", cards["budget_p"])
                self.assertIn(f"at={t['confirm_ns']:.6f}n", cards["confirm_p"])

    def test_no_measurement_is_named_after_a_node_it_reads(self):
        """An ngspice `meas` result is written into the step's plot as a
        vector, so a measurement named `top_p` would overwrite v(TOP_P) and
        every later card in the same step reading it fails 'out of interval'.
        Found by running the deck; asserted here so it cannot come back."""
        nodes = {"top_p", "top_n", "vinp", "vinn", "vcm", "vdd", "sample",
                 "sampleb", "smp_ctl", "vinp_src", "vinn_src",
                 "bpref_p", "bpref_n", "boost_p", "boost_n", "g_p", "g_n"}
        for step in self.req["analysis_steps"]:
            for meas in step["measurements"]:
                self.assertNotIn(meas["name"].lower(), nodes, meas["name"])

    def test_pwl_alter_vector_is_in_seconds(self):
        """`alter @src[pwl]` takes an ngspice vector, which carries no unit
        suffixes -- an ns-valued vector would stretch the stimulus by 1e9."""
        step = self.req["analysis_steps"][0]
        vec = step["alter"]["Vsmp_ctl"]["pwl"]
        self.assertEqual(len(vec) % 2, 0)
        times = vec[0::2]
        self.assertEqual(times, sorted(times))
        self.assertLess(max(times), 1e-5)  # sub-microsecond, i.e. seconds

    def test_request_is_json_serialisable_and_names_ngspice(self):
        self.assertEqual(self.req["engine"], "ngspice")
        json.loads(json.dumps(self.req))

    def test_backend_is_threaded_only_when_asked(self):
        self.assertNotIn("backend", m.build_request("tb.spice", self.cids))
        self.assertEqual(
            m.build_request("tb.spice", self.cids, backend="batch")["backend"],
            "batch",
        )


class TestFleetJobBound(unittest.TestCase):
    """The batch fleet refuses a job whose conservative fully-serial bound
    (`options.timeout_s * units + 120`) exceeds its whole-job ceiling. A first
    submit at 3600 s was refused outright for exactly this reason, before any
    simulation ran, so the default is pinned against the ceiling here."""

    #: `max_job_seconds` from the fleet config at the time of writing. If the
    #: fleet raises it this test still passes; if a future edit raises
    #: DEFAULT_TIMEOUT_S past what the ceiling allows, it fails here instead of
    #: at submit time.
    FLEET_MAX_JOB_S = 3600
    FLEET_OVERHEAD_S = 120

    def test_default_timeout_fits_the_whole_job_ceiling(self):
        units = len(m.corner_ids())
        bound = m.DEFAULT_TIMEOUT_S * units + self.FLEET_OVERHEAD_S
        self.assertLessEqual(bound, self.FLEET_MAX_JOB_S, f"{bound}s bound")

    def test_a_single_unit_also_fits(self):
        """`--hosts` sharding cannot rescue a per-unit bound that is itself
        over the ceiling -- which is what the refused submit reported."""
        self.assertLess(
            m.DEFAULT_TIMEOUT_S + self.FLEET_OVERHEAD_S, self.FLEET_MAX_JOB_S
        )

    def test_the_request_carries_the_default(self):
        req = m.build_request("tb.spice", m.corner_ids())
        self.assertEqual(req["options"]["timeout_s"], m.DEFAULT_TIMEOUT_S)

    def test_default_leaves_headroom_over_the_measured_per_unit_cost(self):
        """~26 s measured for one corner's 16 steps; keep at least 5x."""
        self.assertGreaterEqual(m.DEFAULT_TIMEOUT_S, 5 * 26)


class TestSubmitArgv(unittest.TestCase):
    def test_batch_submit_waits_for_capacity(self):
        """CLAUDE.md's fleet rule: a vCPU-budgeted fleet refuses a burst with
        batch_no_capacity unless the submit may wait with backoff."""
        argv = m.submit_argv(Path("/w/request.json"), Path("/w/out"), "batch")
        self.assertIn("--wait-for-capacity", argv)
        self.assertEqual(argv[argv.index("--wait-for-capacity") + 1], "600")
        self.assertEqual(argv[:2], ["klt", "sim"])

    def test_default_backend_still_waits_for_capacity(self):
        """With no explicit backend, KLT_SIM_BACKEND decides -- which on a
        dispatch host is `batch`, so the flag must still be there."""
        argv = m.submit_argv(Path("/w/request.json"), Path("/w/out"), None)
        self.assertIn("--wait-for-capacity", argv)

    def test_local_backend_does_not_wait_for_a_fleet(self):
        argv = m.submit_argv(Path("/w/request.json"), Path("/w/out"), "local")
        self.assertNotIn("--wait-for-capacity", argv)
        self.assertIn("local", argv)


class TestDeckBody(unittest.TestCase):
    def setUp(self):
        self.body = m.build_body()

    def test_dut_fragment_is_inserted_verbatim(self):
        """Read in place, never duplicated or edited (the convention
        sim/sampling-frontend/run_hold_kick.py set)."""
        for line in m.DUT_FRAGMENT.read_text().splitlines():
            if line.strip() and not line.startswith("*"):
                self.assertIn(line, self.body)

    def test_both_inputs_carry_their_own_series_resistor(self):
        self.assertIn("Rsp VINP_SRC VINP", self.body)
        self.assertIn("Rsn VINN_SRC VINN", self.body)
        self.assertNotIn("Vinp VINP 0", self.body)
        self.assertNotIn("Vinn VINN 0", self.body)

    def test_supply_source_is_named_exactly_the_corner_axis_key(self):
        """klt sim applies corners.supply_v as a literal `alter <key>=<v>`, so
        a source named anything else would leave every corner at nominal."""
        decls = [
            ln.split()[0].lower()
            for ln in self.body.splitlines()
            if ln.strip() and not ln.startswith(("*", "."))
        ]
        self.assertIn(m.SUPPLY_KEY.lower(), decls)
        self.assertEqual(
            m.build_request("tb.spice", m.corner_ids())["corners"]["supply_v"]
            .keys().__iter__().__next__(),
            m.SUPPLY_KEY,
        )

    def test_sample_level_tracks_the_corner_supply(self):
        self.assertIn("Bsample SAMPLE 0 V=v(SMP_CTL)*v(VDD)", self.body)
        self.assertIn("Vsmp_ctl SMP_CTL 0 pwl(", self.body)

    def test_every_alter_target_is_declared_in_the_body(self):
        """An alter naming no element silently simulates the nominal value."""
        decls = {
            ln.split()[0].lower()
            for ln in self.body.splitlines()
            if ln.strip() and not ln.startswith(("*", ".", "+"))
        }
        for step in m.analysis_steps():
            for target in step["alter"]:
                self.assertIn(target.lower(), decls, target)

    def test_body_has_no_lib_temp_control_or_end(self):
        """klt sim emits all four; a body that carries its own would fight
        the corner axes."""
        lowered = [ln.strip().lower() for ln in self.body.splitlines()]
        for card in (".lib", ".temp", ".control", ".endc", ".end", ".tran"):
            self.assertFalse(
                [ln for ln in lowered if ln.startswith(card)], card
            )

    def test_vcm_is_the_mirrored_campaigns_fixed_ideal_value(self):
        """Carried over unchanged so this campaign's R_source = 0 control row
        stays comparable with sim/sampling-acquisition-settling/'s records."""
        self.assertIn(f"Vvcm VCM 0 DC {m.VCM_V}", self.body)


class TestReportReader(unittest.TestCase):
    def _report(self, **corner):
        base = {
            "process": "tt",
            "temperature_c": 27.0,
            "supply_v": {m.SUPPLY_KEY: 1.8},
            "status": "pass",
            "measurements": [
                {"name": "worst_r0.budget_p", "value": 1.6},
                {"name": "worst_r0.budget_n", "value": 0.2},
            ],
        }
        base.update(corner)
        return {
            "status": "pass",
            "corners": [base],
            "environment": {
                "remote": {
                    "job_id": "job-123",
                    "worker_environment": {
                        "pdk": {"stamp_text": "sky130A @ abc123"},
                        "simulator": {"version_banner": "** ngspice-47 : blah"},
                    },
                }
            },
        }

    def test_reads_values_and_run_info(self):
        results, info = m.read_report(self._report())
        self.assertEqual(results["tt_27c_1.80v"]["worst_r0.budget_p"], 1.6)
        self.assertEqual(info["job_id"], "job-123")
        self.assertEqual(info["worker_pdk"], "sky130A @ abc123")
        self.assertEqual(info["worker_ngspice"], "ngspice-47 : blah")

    def test_error_envelope_is_refused_not_read_as_zero_corners(self):
        with self.assertRaises(ValueError):
            m.read_report({"error": {"code": "batch_no_capacity"}})

    def test_non_object_report_is_refused(self):
        with self.assertRaises(ValueError):
            m.read_report([{"process": "tt"}])

    def test_an_error_corner_is_nulled_not_partially_read(self):
        for status in ("error", "inconclusive"):
            results, _info = m.read_report(self._report(status=status))
            self.assertEqual(
                set(results["tt_27c_1.80v"].values()), {None}, status
            )

    def test_an_error_envelope_beside_corners_is_still_readable(self):
        """`error` AND `corners` means a partially-failed run, not an envelope:
        the usable corners must survive (klt's own reader contract)."""
        report = self._report()
        report["error"] = {"code": "partial"}
        results, _info = m.read_report(report)
        self.assertEqual(results["tt_27c_1.80v"]["worst_r0.budget_p"], 1.6)

    def test_a_missing_corner_analyses_as_incomplete_not_as_zero(self):
        analysis = m.analyze({}, ["tt_27c_1.80v"])
        self.assertIsNone(analysis["tt_27c_1.80v"]["worst"])
        self.assertIsNone(analysis["tt_27c_1.80v"]["legacy"])


class TestDryRun(unittest.TestCase):
    def test_dry_run_writes_a_deck_and_a_request_and_runs_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            with contextlib.redirect_stdout(io.StringIO()):
                rc = m.main(["--dry-run", "--workdir", d])
            self.assertEqual(rc, 0)
            self.assertTrue((Path(d) / "tb.spice").is_file())
            req = json.loads((Path(d) / "request.json").read_text())
            self.assertEqual(len(req["analysis_steps"]), 16)
            self.assertFalse((Path(d) / "report.json").exists())


if __name__ == "__main__":
    unittest.main()

"""PDK-free tests for the digital-partition characterization tooling (issue #619).

No ngspice, no PDK, no network: bracket search, grading, power arithmetic,
deck/request construction, report parsing, area derivation and the freshness /
checklist predicates are all exercised against synthetic fixtures and the
committed repo artifacts."""

from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO = SIM_DIR.parent
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(SIM_DIR / "digital-partition"))

import digital_area as da  # noqa: E402
import digital_char as dc  # noqa: E402
import digital_report as dr  # noqa: E402
import run_digital_partition as rdp  # noqa: E402

CORNERS = [
    "tt_27c_1.80v", "ss_27c_1.80v", "ff_27c_1.80v", "sf_27c_1.80v", "fs_27c_1.80v",
    "tt_-40c_1.80v", "tt_125c_1.80v", "tt_27c_1.62v", "tt_27c_1.98v",
]


def perfect_values(codes=dc.CODES):
    return {c.name: c.expected for c in dc.expected_checks(codes)}


class TestGrid(unittest.TestCase):
    def test_base_and_octaves(self):
        self.assertEqual(dc.freq_mhz(0), 12.0)
        self.assertAlmostEqual(dc.freq_mhz(8), 24.0)
        self.assertAlmostEqual(dc.freq_mhz(dc.CEILING_INDEX), 12.0 * 128)
        self.assertAlmostEqual(dc.tolerance_pct(), 9.05, places=1)


class TestCornerSearch(unittest.TestCase):
    def drive(self, fmax_idx, ceiling=dc.CEILING_INDEX):
        s = dc.CornerSearch("c", ceiling)
        order = []
        while not s.done():
            i = s.next_index()
            order.append(i)
            s.record(i, i <= fmax_idx)
        return s, order

    def test_bracket_found_adjacent(self):
        s, order = self.drive(27)
        r = s.result()
        self.assertEqual(r["state"], dc.STATE_BRACKET)
        self.assertEqual(r["f_pass_mhz"], dc.freq_mhz(27))
        self.assertEqual(r["f_fail_mhz"], dc.freq_mhz(28))
        self.assertEqual(order[:4], [0, 8, 16, 24])
        self.assertEqual(order[4], 32)  # first coarse fail
        self.assertLess(len(order), 12)  # coarse ladder + <=3 bisection probes

    def test_exact_octave_boundary(self):
        s, _ = self.drive(16)
        r = s.result()
        self.assertEqual((r["f_pass_mhz"], r["f_fail_mhz"]), (dc.freq_mhz(16), dc.freq_mhz(17)))

    def test_never_fails_is_censored_lower_bound(self):
        s, order = self.drive(10**6)
        r = s.result()
        self.assertEqual(r["state"], dc.STATE_CENSORED)
        self.assertIsNone(r["f_fail_mhz"])
        self.assertEqual(r["f_pass_mhz"], dc.freq_mhz(dc.CEILING_INDEX))
        self.assertEqual(order[-1], dc.CEILING_INDEX)

    def test_fails_at_floor(self):
        s, order = self.drive(-1)
        self.assertEqual(order, [0])
        self.assertEqual(s.result()["state"], dc.STATE_FLOOR_FAIL)
        self.assertIsNone(s.result()["f_pass_mhz"])

    def test_invalid_probe_freezes_as_inconclusive(self):
        s = dc.CornerSearch("c")
        s.record(0, True)
        s.record(8, None)
        self.assertEqual(s.state(), dc.STATE_INVALID)
        self.assertIsNone(s.next_index())

    def test_non_monotone_flagged(self):
        s = dc.CornerSearch("c")
        for i, ok in ((0, True), (8, False), (4, True), (6, False), (5, True)):
            s.record(i, ok)
        # a later (higher) pass than the lowest fail is flagged
        s2 = dc.CornerSearch("c")
        for i, ok in ((0, True), (8, True), (16, False), (20, True)):
            s2.record(i, ok)
        self.assertTrue(s2.non_monotone())
        self.assertFalse(s.non_monotone())

    def test_double_observation_rejected(self):
        s = dc.CornerSearch("c")
        s.record(0, True)
        with self.assertRaises(ValueError):
            s.record(0, True)

    def test_plan_round_groups_shared_frequencies(self):
        a, b, c = (dc.CornerSearch(n) for n in "abc")
        a.record(0, True)
        b.record(0, True)
        c.record(0, True)
        c.record(8, False)
        plan = dc.plan_round([a, b, c])
        self.assertEqual(plan, {4: ["c"], 8: ["a", "b"]})

    def test_run_search_with_synthetic_fmax(self):
        fmax = {cid: 14 + 3 * i for i, cid in enumerate(CORNERS)}
        calls = []

        def submit(f, cids):
            calls.append((f, list(cids)))
            out = {}
            for cid in cids:
                idx = round(8 * math.log2(f / dc.F_BASE_MHZ))
                vals = perfect_values() if idx <= fmax[cid] else {k: 0.0 for k in perfect_values()}
                out[cid] = dc.UnitResult(cid, "pass", vals, [])
            return out, {"remote": {"job_id": "x"}, "status": "pass"}

        searches, log, units = dc.run_search(CORNERS, submit, max_workers=2)
        for cid, s in searches.items():
            r = s.result()
            self.assertEqual(r["state"], dc.STATE_BRACKET, cid)
            self.assertEqual(r["f_pass_mhz"], dc.freq_mhz(fmax[cid]))
        self.assertEqual(len(log), len(calls))
        # the first request covers every corner at the floor frequency
        self.assertEqual(calls[0][0], 12.0)
        self.assertEqual(sorted(calls[0][1]), sorted(CORNERS))
        # frequencies are shared: far fewer requests than corner-probes
        self.assertLess(len(calls), sum(len(s.obs) for s in searches.values()))
        self.assertIn(0, units["tt_27c_1.80v"])

    def test_all_invalid_request_stops_campaign(self):
        def submit(f, cids):
            return ({c: dc.UnitResult(c, "error", {}, ["batch_job_failed"], ["runner version skew"])
                     for c in cids}, {"status": "error"})

        with self.assertRaises(dc.InfrastructureError) as ctx:
            dc.run_search(CORNERS, submit)
        self.assertIn("runner version skew", str(ctx.exception))


class TestGrading(unittest.TestCase):
    def test_perfect_values_pass(self):
        g = dc.grade_values(perfect_values())
        self.assertTrue(g.passed)
        self.assertEqual(g.n_checks, len(dc.expected_checks()))

    def test_wrong_phase_fails(self):
        v = perfect_values()
        v["pc_c2_j5"] += 1.0
        g = dc.grade_values(v)
        self.assertIs(g.passed, False)
        self.assertTrue(any("pc_c2_j5" in f for f in g.failures))

    def test_wrong_bit_capture_fails(self):
        v = perfect_values()
        v["dout_c3"] -= 1.0
        self.assertIs(dc.grade_values(v).passed, False)

    def test_wrong_recode_and_sel_fail(self):
        for name in ("adc_c1", "seln_c0", "selp_c0"):
            v = perfect_values()
            v[name] += 2.0
            self.assertIs(dc.grade_values(v).passed, False, name)

    def test_wrong_control_output_fails(self):
        v = perfect_values()
        v["ctl_c0_j3"] = 5.0
        self.assertIs(dc.grade_values(v).passed, False)

    def test_missing_measurement_is_invalid_not_pass(self):
        v = perfect_values()
        del v["pc_c0_j0"]
        g = dc.grade_values(v)
        self.assertIsNone(g.passed)
        self.assertEqual(g.invalid, ["pc_c0_j0"])

    def test_nonfinite_measurement_is_invalid(self):
        for bad in (float("nan"), float("inf"), None, "x", True):
            v = perfect_values()
            v["dout_c0"] = bad
            self.assertIsNone(dc.grade_values(v).passed, repr(bad))

    def test_definite_failure_beats_a_missing_value(self):
        v = perfect_values()
        del v["pc_c0_j0"]
        v["dout_c1"] = 0.0
        self.assertIs(dc.grade_values(v).passed, False)

    def test_all_zero_values_fail(self):
        self.assertIs(dc.grade_values({k: 0.0 for k in perfect_values()}).passed, False)

    def test_grade_unit_error_status_is_invalid(self):
        u = dc.UnitResult("c", "error", perfect_values(), ["singular_matrix"])
        self.assertIsNone(dc.grade_unit(u).passed)
        self.assertIsNone(dc.grade_unit(None).passed)
        self.assertTrue(dc.grade_unit(dc.UnitResult("c", "pass", perfect_values(), [])).passed)

    def test_negative_control(self):
        fail = dc.ProbeGrade(False, ["x"], [], 1)
        ok = dc.ProbeGrade(True, [], [], 1)
        inv = dc.ProbeGrade(None, [], ["x"], 1)
        self.assertTrue(dc.negative_control_ok({"a": fail, "b": fail}))
        self.assertFalse(dc.negative_control_ok({"a": fail, "b": ok}))
        self.assertFalse(dc.negative_control_ok({"a": fail, "b": inv}))
        self.assertFalse(dc.negative_control_ok({}))


class TestExpectations(unittest.TestCase):
    def setUp(self):
        self.by = {c.name: c for c in dc.expected_checks()}

    def test_check_count(self):
        self.assertEqual(len(self.by), 2 + len(dc.CODES) * (2 * 12 + 4))

    def test_phase_sequence_one_hot(self):
        self.assertEqual(self.by["pc_rst"].expected, 1)
        self.assertEqual(self.by["pc_c0_j0"].expected, 2)      # ph_b9
        self.assertEqual(self.by["pc_c0_j10"].expected, 2048)  # ph_eoc
        self.assertEqual(self.by["pc_c0_j11"].expected, 1)     # restart: ph_sample
        self.assertEqual(self.by["pc_c3_j0"].expected, 2)      # auto-restart on every conversion

    def test_control_outputs(self):
        self.assertEqual(self.by["ctl_rst"].expected, 4)
        self.assertEqual(self.by["ctl_c0_j0"].expected, 5)   # BUSY, HALF_LSB_EN off (PH_B9)
        self.assertEqual(self.by["ctl_c0_j5"].expected, 3)
        self.assertEqual(self.by["ctl_c0_j11"].expected, 4)

    def test_recode_expectations(self):
        # 811 = 0b1100101011 : b9=1, low bits 100101011
        self.assertEqual(self.by["dout_c0"].expected, 811)
        self.assertEqual(self.by["selp_c0"].expected, 0b100101011)
        self.assertEqual(self.by["seln_c0"].expected, 0)
        self.assertEqual(self.by["adc_c0"].expected, 0b100101011)
        # 212 = 0b0011010100 : b9=0 ; ADCOUT_i = DOUT_i XNOR DOUT9 = NOT bit
        self.assertEqual(self.by["seln_c1"].expected, 0b011010100)
        self.assertEqual(self.by["selp_c1"].expected, 0)
        self.assertEqual(self.by["adc_c1"].expected, 0b100101011)

    def test_sample_times_precede_next_edge(self):
        f = 12.0
        for c in self.by.values():
            k, off = c.t_s_per_period
            self.assertLess(off, 1.0)
            self.assertGreater(dc.check_time_s(c, f), dc.edge_start_s(k, f))
        # reset checks happen before RST_B release
        rel = dc.RST_RELEASE_T * dc.period_s(f)
        self.assertLess(dc.check_time_s(self.by["pc_rst"], f), rel)

    def test_comp_events_follow_comp_eff_polarity(self):
        ev = dc.comp_events()
        by_edge = {k: lv for k, _d, lv in ev}
        # code 811 (b9=1): driven level == target bit; first bit (b9)=1
        self.assertEqual(by_edge[dc.edge_index(0, 0)], 1)
        self.assertEqual(by_edge[dc.edge_index(0, 1)], 1)  # b8 of 811
        self.assertEqual(by_edge[dc.edge_index(0, 2)], 0)  # b7
        # code 212 (b9=0): bits 8..0 are driven INVERTED
        self.assertEqual(by_edge[dc.edge_index(1, 0)], 0)  # b9 direct
        self.assertEqual(by_edge[dc.edge_index(1, 2)], 0)  # b7 target 1 -> driven 0

    def test_pwl_is_monotone_and_deduplicated(self):
        pts = dc.pwl_points(dc.comp_events(), 12.0, dc.t_stop_s(12.0))
        times = [t for t, _ in pts]
        self.assertEqual(times, sorted(times))
        self.assertEqual(len(times), len(set(times)))

    def test_power_windows_are_whole_periods(self):
        w = dc.power_windows(12.0)
        T = dc.period_s(12.0)
        self.assertAlmostEqual((w["reset"][1] - w["reset"][0]) / T, 2.0)
        self.assertAlmostEqual((w["active"][1] - w["active"][0]) / T,
                               dc.EDGES_PER_CONVERSION * w["active"][2])
        self.assertLess(w["active"][1], dc.t_stop_s(12.0))


class TestPower(unittest.TestCase):
    def test_sign_convention(self):
        self.assertAlmostEqual(dc.power_from_avg_current(-5e-6, 1.8), 9e-6)

    def test_rejects_bad_readings(self):
        for i in (None, float("nan"), float("inf"), 0.0, +3e-6):
            self.assertIsNone(dc.power_from_avg_current(i, 1.8), i)
        self.assertIsNone(dc.power_from_avg_current(-1e-6, float("nan")))

    def test_energy_per_conversion(self):
        e = dc.energy_per_conversion_j(10e-6, 12.0)
        self.assertAlmostEqual(e, 10e-6 * 12 / 12e6)
        self.assertIsNone(dc.energy_per_conversion_j(None, 12.0))

    def test_op_point_flags_nonfunctional(self):
        u = dc.UnitResult("tt_27c_1.80v", "pass", {"iavg_active": -6e-6, "iavg_reset": -3e-6}, [])
        bad = dc.ProbeGrade(False, ["x"], [], 1)
        p = dc.op_point_power(u, "tt_27c_1.80v", bad)
        self.assertIs(p["functional_at_op"], False)
        self.assertAlmostEqual(p["p_active_w"], 6e-6 * 1.8)
        missing = dc.op_point_power(dc.UnitResult("tt_27c_1.80v", "pass", {}, []), "tt_27c_1.80v", None)
        self.assertIsNone(missing["p_active_w"])
        self.assertIsNone(missing["energy_per_conversion_j"])


class TestDeckAndRequest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dut = dc.extract_dut((REPO / "design/sar_adc_top.spice").read_text())

    def test_extracts_the_declared_partition(self):
        self.assertEqual(len(self.dut["glue"]), dc.GLUE_EXPECTED_INSTANCES)
        self.assertEqual(len(self.dut["sequencer_pins"]), 26)
        self.assertTrue(self.dut["sequencer"][-1].lower().startswith(".ends"))
        self.assertTrue(all("sky130_fd_sc_hd__" in ln for ln in self.dut["glue"]))
        self.assertFalse(any(" sar_sequencer" in ln for ln in self.dut["glue"]))

    def test_extract_rejects_netlist_without_sequencer(self):
        with self.assertRaises(ValueError):
            dc.extract_dut(".subckt other a b\n.ends\n")

    def test_deck_is_a_circuit_body(self):
        deck = dc.build_netlist(12.0, self.dut)
        low = [ln.strip().lower() for ln in deck.splitlines()]
        self.assertNotIn(".end", low)
        self.assertFalse(any(ln.startswith(".control") for ln in low))
        self.assertIn(".global vpwr vgnd", low)
        self.assertIn(".options num_threads=1", low)
        self.assertTrue(any(ln.startswith("vdig vpwr 0 dc") for ln in low))
        self.assertTrue(any(ln.startswith("xseq ") for ln in low))
        for pin in self.dut["sequencer_pins"]:
            self.assertIn(pin, deck)
        # every declared output has a load
        for net in ("CLKN", "HALF_LSB_EN", "HALF_LSB_ENN", "BUSY", "PH_SAMPLE", "SELn8", "SELp0", "ADCOUT8", "DOUT9"):
            self.assertTrue(any(ln.startswith("cld") and f" {net.lower()} " in ln + " " for ln in low), net)

    def test_deck_scales_stimulus_with_frequency(self):
        a = dc.build_netlist(12.0, self.dut)
        b = dc.build_netlist(24.0, self.dut)
        self.assertNotEqual(a, b)
        self.assertIn("8.333333e-08", a)  # 1/12 MHz

    def test_request_corner_subset_via_exclude(self):
        req = dc.build_request("tb.spice", 12.0, ["tt_27c_1.80v", "ss_27c_1.80v", "tt_125c_1.62v"], backend="batch")
        self.assertEqual(req["corners"]["process"], ["ss", "tt"])
        self.assertEqual(req["corners"]["supply_v"], {"vdig": [1.62, 1.8]})
        self.assertEqual(req["corners"]["temperature_c"], [27.0, 125.0])
        # product is 2*2*2 = 8 points, 3 wanted -> 5 excluded
        self.assertEqual(len(req["exclude"]), 5)
        self.assertEqual(req["backend"], "batch")
        self.assertEqual(req["analysis"]["kind"], "tran")
        names = [m["name"] for m in req["measurements"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("iavg_active", names)
        self.assertIn("iavg_reset", names)

    def test_single_corner_request_has_no_exclude(self):
        req = dc.build_request("tb.spice", 12.0, ["tt_27c_1.80v"])
        self.assertNotIn("exclude", req)
        self.assertNotIn("backend", req)

    def test_batch_options_pass_through(self):
        req = dc.build_request("tb.spice", 12.0, ["tt_27c_1.80v"], batch={"capacity_wait_s": 5})
        self.assertEqual(req["batch"], {"capacity_wait_s": 5})

    def test_edges_stay_within_the_library_transition_limit(self):
        for f in (12.0, 24.0, 96.0, 1536.0, 6000.0):
            self.assertLessEqual(dc.rise_time_s(f), 0.3e-9 + 1e-18)
            self.assertGreaterEqual(dc.rise_time_s(f), 10e-12 - 1e-18)

    def test_time_step_is_tied_to_the_edge_not_the_period(self):
        # the solver step follows the (capped) edge time at every frequency
        for f in (12.0, 100.0, 1536.0, 6000.0):
            self.assertLessEqual(dc.max_step_s(f), dc.rise_time_s(f) / dc.STEP_DIVISOR + 1e-18)
            self.assertLessEqual(dc.max_step_s(f), dc.period_s(f) / 30.0 + 1e-18)
        self.assertAlmostEqual(dc.max_step_s(12.0), 0.15e-9, delta=1e-12)
        args = dc.analysis_args(12.0).split()
        self.assertEqual(float(args[0]), float(args[3]))

    def test_corner_id_round_trip(self):
        for cid in CORNERS:
            self.assertEqual(dc.make_corner_id(*dc.parse_corner_id(cid)), cid)
        with self.assertRaises(ValueError):
            dc.parse_corner_id("nonsense")

    def test_ratified_grid_matches_corner_ids(self):
        self.assertEqual(rdp.ratified_corner_ids(), CORNERS)


def klt_report(units, remote=None):
    corners = []
    for cid, (status, vals, diags) in units.items():
        p, t, v = dc.parse_corner_id(cid)
        corners.append({
            "corner_id": f"{p}/{v:.3f}V/{t:g}C", "process": p, "temperature_c": t,
            "supply_v": {"vdig": v}, "status": status,
            "measurements": [{"name": k, "value": x} for k, x in vals.items()],
            "diagnostics": diags,
        })
    return {"status": "pass", "corners": corners, "environment": {"remote": remote or {"job_id": "j1"}}}


class TestReportReading(unittest.TestCase):
    def test_reads_corners_and_remote(self):
        rep = klt_report({"tt_27c_1.80v": ("pass", perfect_values(), [])})
        res, info = dc.read_report(rep)
        self.assertEqual(list(res), ["tt_27c_1.80v"])
        self.assertEqual(info["remote"], {"job_id": "j1"})
        self.assertTrue(dc.grade_unit(res["tt_27c_1.80v"]).passed)

    def test_error_envelope_raises(self):
        with self.assertRaises(ValueError):
            dc.read_report({"error": {"message": "boom"}})
        with self.assertRaises(ValueError):
            dc.read_report({"status": "pass"})

    def test_corner_without_supply_raises(self):
        rep = klt_report({"tt_27c_1.80v": ("pass", {}, [])})
        rep["corners"][0]["supply_v"] = {}
        with self.assertRaises(ValueError):
            dc.read_report(rep)

    def test_error_diagnostic_makes_unit_invalid(self):
        rep = klt_report({"tt_27c_1.80v": ("pass", perfect_values(),
                                           [{"severity": "error", "code": "nonconvergence", "message": "m"}])})
        res, _ = dc.read_report(rep)
        self.assertIsNone(dc.grade_unit(res["tt_27c_1.80v"]).passed)


class TestSubmitter(unittest.TestCase):
    def test_capacity_refusal_is_retried_on_the_same_backend_only(self):
        dut = dc.extract_dut((REPO / "design/sar_adc_top.spice").read_text())
        rep = klt_report({"tt_27c_1.80v": ("pass", perfect_values(), [])})
        refusal = json.dumps({"error": {"message": "launch failed: 8 instance(s) already running + 1 "
                                        "requested exceeds BATCH_MAX_CONCURRENT_INSTANCES=8"}})
        outs = [refusal, refusal, json.dumps(rep)]
        calls, naps = [], []

        def runner(argv):
            calls.append(argv)
            o = outs.pop(0)
            # the real client writes its error envelope to STDERR with rc 1
            return (1, "", o) if o is refusal else (0, o, "")

        with tempfile.TemporaryDirectory() as td:
            sub = rdp.make_submitter(Path(td), dut, "batch", runner, retry_wait_s=7, sleep=naps.append)
            res, _ = sub(12.0, ["tt_27c_1.80v"])
            self.assertTrue(dc.grade_unit(res["tt_27c_1.80v"]).passed)
            self.assertEqual(naps, [7, 7])
            self.assertTrue(all(c[c.index("--backend") + 1] == "batch" for c in calls))
            # retries are bounded, then the campaign stops with the fleet's own message
            bad = rdp.make_submitter(Path(td) / "x", dut, "batch", lambda a: (1, "", refusal),
                                     capacity_retries=2, sleep=lambda s: None)
            with self.assertRaises(rdp.SubmitError) as ctx:
                bad(12.0, ["tt_27c_1.80v"])
            self.assertIn("BATCH_MAX_CONCURRENT_INSTANCES", str(ctx.exception))


    def test_runs_caches_and_reports_errors(self):
        dut = dc.extract_dut((REPO / "design/sar_adc_top.spice").read_text())
        rep = klt_report({"tt_27c_1.80v": ("pass", perfect_values(), [])})
        calls = []

        def runner(argv):
            calls.append(argv)
            return 0, json.dumps(rep), ""

        with tempfile.TemporaryDirectory() as td:
            sub = rdp.make_submitter(Path(td), dut, "batch", runner)
            res, info = sub(12.0, ["tt_27c_1.80v"])
            self.assertTrue(dc.grade_unit(res["tt_27c_1.80v"]).passed)
            self.assertEqual(info["backend"], "batch")
            self.assertIn("--backend", calls[0])
            self.assertEqual(calls[0][calls[0].index("--backend") + 1], "batch")
            sub(12.0, ["tt_27c_1.80v"])
            self.assertEqual(len(calls), 1, "completed probe must be served from cache")

            bad = rdp.make_submitter(Path(td) / "b", dut, "batch", lambda argv: (1, "not json", "boom"))
            with self.assertRaises(rdp.SubmitError):
                bad(12.0, ["tt_27c_1.80v"])
            env = rdp.make_submitter(Path(td) / "c", dut, "batch",
                                     lambda argv: (1, json.dumps({"error": {"message": "capacity"}}), ""))
            with self.assertRaises(rdp.SubmitError):
                env(12.0, ["tt_27c_1.80v"])


DEF_FIXTURE = """VERSION 5.8 ;
DESIGN blk ;
UNITS DISTANCE MICRONS 1000 ;
DIEAREA ( 0 0 ) ( 10000 20000 ) ;
COMPONENTS 3 ;
    - FILLER_0 sky130_fd_sc_hd__fill_1 + SOURCE DIST + PLACED ( 0 0 ) N ;
    - u1 sky130_fd_sc_hd__inv_1 + PLACED ( 0 0 ) N ;
    - u2 sky130_fd_sc_hd__dfrtp_1 + PLACED ( 0 0 ) N ;
END COMPONENTS
"""
LEF_FIXTURE = """MACRO sky130_fd_sc_hd__fill_1
  SIZE 0.46 BY 2.72 ;
END sky130_fd_sc_hd__fill_1
MACRO sky130_fd_sc_hd__inv_1
  SIZE 1.38 BY 2.72 ;
END sky130_fd_sc_hd__inv_1
MACRO sky130_fd_sc_hd__dfrtp_1
  SIZE 11.96 BY 2.72 ;
END sky130_fd_sc_hd__dfrtp_1
"""


class TestArea(unittest.TestCase):
    def test_parse_def(self):
        d = da.parse_def(DEF_FIXTURE)
        self.assertEqual(d.design, "blk")
        self.assertEqual(d.die_size_um, (10.0, 20.0))
        self.assertAlmostEqual(d.die_area_um2, 200.0)
        self.assertEqual(len(d.components), 3)

    def test_component_count_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            da.parse_def(DEF_FIXTURE.replace("COMPONENTS 3", "COMPONENTS 4"))

    def test_cell_area_splits_physical_only(self):
        d = da.parse_def(DEF_FIXTURE)
        a = da.placed_cell_area(d, da.parse_lef_sizes(LEF_FIXTURE))
        self.assertAlmostEqual(a["logic_cell_area_um2"], (1.38 + 11.96) * 2.72, places=3)
        self.assertAlmostEqual(a["physical_only_area_um2"], 0.46 * 2.72, places=3)
        self.assertEqual(a["physical_only_count"], 1)

    def test_missing_lef_cell_raises(self):
        with self.assertRaises(KeyError):
            da.placed_cell_area(da.parse_def(DEF_FIXTURE), {})

    def test_footprint_of_disjoint_macros(self):
        fp = da.compose_footprint({"a": (0, 0, 10, 10), "b": (20, 0, 30, 10)})
        self.assertEqual(fp["composed_footprint_um2"], 300.0)
        self.assertEqual(fp["sum_of_macro_areas_um2"], 200.0)

    def test_overlapping_macros_refuse_to_sum(self):
        with self.assertRaises(ValueError):
            da.compose_footprint({"a": (0, 0, 10, 10), "b": (5, 5, 15, 15)})
        # touching edges are not an overlap
        da.compose_footprint({"a": (0, 0, 10, 10), "b": (10, 0, 20, 10)})

    def test_derive_from_committed_artifacts(self):
        a = da.derive(REPO)
        self.assertEqual(set(a["macros"]), {"sar_sequencer", "top_glue"})
        self.assertAlmostEqual(a["macros"]["sar_sequencer"]["macro_area_um2"], 42.57 * 42.57, places=1)
        self.assertAlmostEqual(a["macros"]["top_glue"]["macro_area_um2"], 71.855 * 71.855, places=1)
        self.assertGreater(a["composed_footprint_um2"], a["macro_area_um2"])
        self.assertTrue(a["disjoint"])
        for macro in ("sar_sequencer", "top_glue"):
            self.assertTrue(a["sources"][macro]["def_sha256"].startswith("sha256:"))
        self.assertEqual(set(a["sources"]["composition"]["origins_um"]), {"sar_sequencer", "top_glue"})


def synthetic_campaign(meets=True):
    searches = {c: dc.CornerSearch(c) for c in CORNERS}
    for s in searches.values():
        for i, ok in ((0, True), (8, True), (16, False), (12, True), (14, True), (15, False)):
            s.record(i, ok)
    units = {c: {0: dc.UnitResult(c, "pass", dict(perfect_values(), iavg_active=-6e-6, iavg_reset=-3e-6), [])}
             for c in CORNERS}
    neg = {c: dc.ProbeGrade(False, ["x"], [], 1) for c in CORNERS}
    area = {"composed_footprint_um2": 100.0, "macro_area_um2": 80.0}
    if not meets:
        neg = {}
    return dc.summarize(searches, units, neg, area)


class TestChecklist(unittest.TestCase):
    def test_complete_campaign_meets(self):
        s = synthetic_campaign()
        self.assertTrue(s["checklist"]["meets"], s["checklist"]["reasons"])
        self.assertEqual(s["results"]["tt_27c_1.80v"]["f_pass_mhz"], dc.freq_mhz(14))

    def test_missing_negative_control_does_not_meet(self):
        s = synthetic_campaign(meets=False)
        self.assertFalse(s["checklist"]["meets"])
        self.assertTrue(any("negative control" in r for r in s["checklist"]["reasons"]))

    def test_each_gap_is_reported(self):
        s = synthetic_campaign()
        r = s["results"]
        p = s["power"]
        base = dict(corner_ids=CORNERS, results=r, power=p, area={"composed_footprint_um2": 1.0},
                    negative_control=True)
        self.assertTrue(dc.checklist_verdict(**base).meets)
        # nonfunctional corner
        r2 = dict(r)
        r2["ss_27c_1.80v"] = dict(r["ss_27c_1.80v"], state=dc.STATE_FLOOR_FAIL)
        v = dc.checklist_verdict(**dict(base, results=r2))
        self.assertFalse(v.meets)
        self.assertTrue(any("nonfunctional" in x for x in v.reasons))
        # invalid power
        p2 = dict(p)
        p2["ff_27c_1.80v"] = dict(p["ff_27c_1.80v"], p_active_w=None)
        self.assertFalse(dc.checklist_verdict(**dict(base, power=p2)).meets)
        # missing corner
        r3 = {k: v for k, v in r.items() if k != "tt_125c_1.80v"}
        self.assertFalse(dc.checklist_verdict(**dict(base, results=r3)).meets)
        # no area / non-monotone / inconclusive
        self.assertFalse(dc.checklist_verdict(**dict(base, area=None)).meets)
        r4 = dict(r)
        r4["fs_27c_1.80v"] = dict(r["fs_27c_1.80v"], non_monotone=True)
        self.assertFalse(dc.checklist_verdict(**dict(base, results=r4)).meets)
        r5 = dict(r)
        r5["fs_27c_1.80v"] = dict(r["fs_27c_1.80v"], state=dc.STATE_INVALID)
        self.assertFalse(dc.checklist_verdict(**dict(base, results=r5)).meets)
        # nonfunctional at operating point
        p3 = dict(p)
        p3["tt_27c_1.80v"] = dict(p["tt_27c_1.80v"], functional_at_op=False)
        self.assertFalse(dc.checklist_verdict(**dict(base, power=p3)).meets)

    def test_censored_lower_bound_is_acceptable_but_disclosed(self):
        s = synthetic_campaign()
        r = dict(s["results"])
        r["tt_27c_1.80v"] = dict(r["tt_27c_1.80v"], state=dc.STATE_CENSORED, f_fail_mhz=None)
        v = dc.checklist_verdict(corner_ids=CORNERS, results=r, power=s["power"],
                                 area={"composed_footprint_um2": 1.0}, negative_control=True)
        self.assertTrue(v.meets)


class TestRunnerSkew(unittest.TestCase):
    def test_reports_only_mismatching_runs(self):
        log = [{"run": {"remote": {"runner_klt_version": "0.5.0", "client_klt_version": "0.7.0",
                                   "runner_compatibility": "mismatch"}}},
               {"run": {"remote": {"runner_klt_version": "0.7.0", "client_klt_version": "0.7.0"}}},
               {"run": {"remote": None}}, {"run": {}}]
        self.assertEqual(dc.runner_skew(log), ["fleet runner klt 0.5.0 vs submitting client klt 0.7.0"])
        self.assertEqual(dc.runner_skew(log[1:]), [])


class TestRecordRendering(unittest.TestCase):
    def test_record_has_required_fields_and_disclosures(self):
        summ = synthetic_campaign()
        summ["area"] = dict(da.derive(REPO))
        camp = {
            "summary": summ,
            "probe_log": [{"index": 0, "f_mhz": 12.0, "corners": CORNERS,
                           "run": {"backend": "batch", "remote": {"job_id": "j"}, "status": "pass"}}],
            "negative_control_run": {"backend": "batch", "remote": {"job_id": "n"}, "status": "pass"},
            "pins": {"PDK": "sky130A @ c6d73a35f524070e85faff4a6a9eef49553ebc2b", "x": "y"},
            "environment": {"ngspice line": "ngspice-46", "12 MHz tt deck netlist sha256": "a" * 64,
                            "backend": "batch"},
        }
        text = "\n".join(rdp.render_record("R1", camp, "", "sim/digital-partition/run_digital_partition.py"))
        for needle in ("**Record ID**: R1", "**Claim**", "**Overall**", "**Supersedes**: (none)",
                       "- PDK: sky130A @ c6d73a35f524070e85faff4a6a9eef49553ebc2b",
                       "- ngspice: ngspice-46", "- DUT netlist sha256: `" + "a" * 64 + "`",
                       "Negative control", "NOT the ADC sample rate", "NOT extracted timing",
                       "Outside the DUT boundary", "Supply polarity", "Composed footprint", "\"job_id\": \"j\""):
            self.assertIn(needle, text)
        for cid in CORNERS:
            self.assertIn(f"`{cid}`", text)


class TestReportAndEnvelope(unittest.TestCase):
    def make_repo(self, td: Path, meets=True):
        (td / "sim/digital-partition/records").mkdir(parents=True)
        (td / "sim/digital-partition/runs/R1").mkdir(parents=True)
        (td / "sim/digital-partition/records/R1.md").write_text("- **Record ID**: R1\n- **Supersedes**: (none)\n")
        (td / "sim/digital-partition/records/LATEST").write_text("R1.md\n")
        camp = {"summary": synthetic_campaign(meets), "pins": {"digital partition netlist sha256": "sha256:x"}}
        (td / "sim/digital-partition/runs/R1/campaign.json").write_text(json.dumps(camp))
        return camp

    def test_no_record_states_the_gap(self):
        with tempfile.TemporaryDirectory() as td:
            text = dr.render(Path(td))
        self.assertIn("no digital characterization record minted", text)
        self.assertIn("unmeasured", text)

    def test_report_distinguishes_digital_from_adc_capability(self):
        with tempfile.TemporaryDirectory() as td:
            self.make_repo(Path(td))
            text = dr.render(Path(td))
        self.assertIn("is not the ADC's", text)
        self.assertIn("records/R1.md", text)
        self.assertIn("MET", text)

    def test_unmet_campaign_reports_reasons_and_refuses_envelope(self):
        with tempfile.TemporaryDirectory() as td:
            self.make_repo(Path(td), meets=False)
            text = dr.render(Path(td))
            self.assertIn("NOT MET", text)
            self.assertIn("unmet:", text)
            with self.assertRaises(ValueError):
                dr.build_envelope(Path(td), "sha256:abc")

    def test_envelope_shape_when_met(self):
        with tempfile.TemporaryDirectory() as td:
            self.make_repo(Path(td))
            env = dr.build_envelope(Path(td), "sha256:abc")
        self.assertEqual(env["kind"], "generic")
        self.assertEqual(env["status"], "pass")
        self.assertEqual(env["source"], dr.DOC_REL)
        self.assertEqual(env["provenance"]["input"]["content_hash"], "sha256:abc")

    def test_partition_hash_ignores_analog_only_edits(self):
        text = (REPO / "design/sar_adc_top.spice").read_text()
        base = dr.partition_netlist_sha(text)
        analog_edit = text.replace(".subckt comparator", ".subckt comparator_renamed", 1)
        self.assertNotEqual(analog_edit, text)
        self.assertEqual(dr.partition_netlist_sha(analog_edit), base)
        glue_edit = text.replace("sky130_fd_sc_hd__and2_1", "sky130_fd_sc_hd__and2_2", 1)
        self.assertNotEqual(dr.partition_netlist_sha(glue_edit), base)
        seq_edit = text.replace("xringb9 CLK", "xringb9 CLKX", 1)
        self.assertNotEqual(dr.partition_netlist_sha(seq_edit), base)

    def test_freshness_rejects_changed_netlist_and_layout(self):
        area = da.derive(REPO)
        camp = {"summary": {"area": area},
                "pins": {"digital partition netlist sha256":
                         dr.partition_netlist_sha((REPO / "design/sar_adc_top.spice").read_text())}}
        self.assertEqual(dr.freshness_problems(camp, REPO), [])
        stale = json.loads(json.dumps(camp))
        stale["pins"]["digital partition netlist sha256"] = "sha256:deadbeef"
        self.assertTrue(any("netlist changed" in p for p in dr.freshness_problems(stale, REPO)))
        stale = json.loads(json.dumps(camp))
        stale["summary"]["area"]["sources"]["top_glue"]["def_sha256"] = "sha256:00"
        self.assertTrue(any("top_glue routed DEF changed" in p for p in dr.freshness_problems(stale, REPO)))
        stale = json.loads(json.dumps(camp))
        stale["summary"]["area"]["sources"]["sar_sequencer"]["gds_sha256"] = "sha256:00"
        self.assertTrue(any("sar_sequencer routed GDS changed" in p for p in dr.freshness_problems(stale, REPO)))
        stale = json.loads(json.dumps(camp))
        stale["summary"]["area"]["sources"]["composition"]["origins_um"]["top_glue"] = {"x": 0, "y": 0}
        self.assertTrue(any("composed placement" in p for p in dr.freshness_problems(stale, REPO)))


if __name__ == "__main__":
    unittest.main()

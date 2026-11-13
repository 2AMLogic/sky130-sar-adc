"""PDK-free unit tests for
sim/reference-drive-budget/run_reference_drive_budget.py (issue #841).

Everything here runs without ngspice, without a PDK and without network: deck
assembly against the real committed fragment and DUT netlist, the `klt sim`
request shape (corner coverage, the two `corners.params` axes, the measurement
and saved-vector sets), report reading, and the budget arithmetic -- including
the two cases a five-minute-per-unit grid is the wrong place to discover, a
corner whose control row is unusable and a sweep where every value passes.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(SIM_DIR / "full-conversion-transient"))
sys.path.insert(0, str(SIM_DIR / "reference-drive-budget"))

import run_reference_drive_budget as m  # noqa: E402

FRAGMENT = m.tb.FRAGMENT_PATH.read_text()
DUT = m.DUT_NETLIST.read_text()
N_INPUTS = len(m.tb.measured_conversions())


# --------------------------------------------------------------------------
# Deck assembly
# --------------------------------------------------------------------------
class TestSplitFragment(unittest.TestCase):
    def test_splits_the_committed_fragment(self):
        body, meas, tran = m.split_fragment(FRAGMENT)
        self.assertEqual(sorted(c.split()[2] for c in meas),
                         sorted(m.tb.all_measure_names()))
        self.assertEqual(tran, "0.5n 6283.3333n")
        for line in body.splitlines():
            low = line.strip().lower()
            self.assertFalse(low.startswith(".meas"), line)
            self.assertFalse(low.startswith(".tran"), line)
        # the stimulus itself survives the split
        self.assertIn("VCLK CLK 0 PULSE(", body)
        self.assertIn("VINP VINP 0 PWL(", body)

    def test_two_tran_cards_refused(self):
        with self.assertRaises(RuntimeError):
            m.split_fragment(FRAGMENT + ".tran 1n 2n\n")

    def test_no_tran_card_refused(self):
        stripped = "\n".join(
            ln for ln in FRAGMENT.splitlines() if not ln.strip().lower().startswith(".tran")
        )
        with self.assertRaises(RuntimeError):
            m.split_fragment(stripped + "\n")

    def test_dropped_meas_card_refused(self):
        kept, dropped = [], 0
        for ln in FRAGMENT.splitlines():
            if ln.strip().lower().startswith(".meas") and dropped == 0:
                dropped = 1
                continue
            kept.append(ln)
        with self.assertRaises(RuntimeError):
            m.split_fragment("\n".join(kept) + "\n")


class TestPatchReferenceSources(unittest.TestCase):
    def setUp(self):
        body, _meas, _tran = m.split_fragment(FRAGMENT)
        self.patched = m.patch_reference_sources(body)

    def test_sources_repointed_and_resistors_added(self):
        self.assertIn(f"VVREFP {m.VREFP_DRIVE_NODE} 0 DC {{vdd_val}}", self.patched)
        self.assertIn(f"VVREFN {m.VREFN_DRIVE_NODE} 0 DC 0", self.patched)
        self.assertIn(f"RREFP {m.VREFP_DRIVE_NODE} VREFP {{{m.R_REF_PARAM}}}", self.patched)
        self.assertIn(f"RREFN {m.VREFN_DRIVE_NODE} VREFN {{{m.R_REF_PARAM}}}", self.patched)

    def test_no_ideal_reference_source_is_left_on_the_die_node(self):
        self.assertNotIn(m.VREFP_CARD, self.patched)
        self.assertNotIn(m.VREFN_CARD, self.patched)

    def test_source_instance_names_unchanged_so_current_meas_still_read(self):
        """`.meas tran i_vrefp avg i(vvrefp)` must keep measuring the same
        source, so the instance names may not move."""
        for inst in ("VVREFP", "VVREFN"):
            self.assertEqual(self.patched.count(f"\n{inst} "), 1, inst)

    def test_every_other_source_is_untouched(self):
        body, _meas, _tran = m.split_fragment(FRAGMENT)
        for card in ("VVDD VDD 0 DC {vdd_val}", "VVPWR VPWR 0 DC {vdd_val}",
                     "VVGND VGND 0 DC 0", "VVCM VCM 0 DC {vdd_val*0.5}"):
            self.assertIn(card, body)
            self.assertIn(card, self.patched)

    def test_changed_fragment_shape_refused(self):
        with self.assertRaises(RuntimeError):
            m.patch_reference_sources("* no reference sources here\n")
        with self.assertRaises(RuntimeError):
            m.patch_reference_sources(f"{m.VREFP_CARD}\n{m.VREFP_CARD}\n{m.VREFN_CARD}\n")


class TestBuildBody(unittest.TestCase):
    def setUp(self):
        self.body = m.build_body(DUT, FRAGMENT)

    def test_is_a_circuit_body_not_a_deck(self):
        """docs/cli/sim.md "Netlist convention": klt sim owns the corner
        cards, the analysis and the .control/.end wrapper."""
        cards = [ln.strip().lower().split()[0] for ln in self.body.splitlines()
                 if ln.strip().startswith(".")]
        # `.ends` (a subcircuit's own terminator) is part of the DUT body and
        # must survive; the top-level `.end` must not be there.
        for forbidden in (".lib", ".temp", ".end", ".control", ".endc", ".meas", ".tran"):
            self.assertNotIn(forbidden, cards)
        self.assertIn(".ends", cards)

    def test_declares_both_corners_params_axes_at_top_level(self):
        decls = [ln.strip() for ln in self.body.splitlines()
                 if ln.strip().lower().startswith(".param")]
        self.assertEqual(
            sorted(d.split()[1].lower() for d in decls),
            sorted([m.R_REF_PARAM, m.VDD_PARAM]),
        )

    def test_carries_the_reference_solver_policy_card(self):
        self.assertIn(m.fc.solver_options_card(m.SOLVER_PROFILE), self.body)

    def test_includes_the_dut_and_the_stdcell_library(self):
        self.assertIn("xfe VINP VINN SAMPLE_INT ", self.body)
        self.assertIn(f".include {m.STDCELL_INCLUDE}", self.body)
        self.assertIn(".global VPWR VGND", self.body)

    def test_dut_netlist_is_otherwise_verbatim(self):
        """Only the `.end` card is dropped; no DUT line is edited."""
        dut_lines = [ln for ln in DUT.splitlines() if ln.strip().lower() != ".end"]
        body_lines = self.body.splitlines()
        start = body_lines.index(dut_lines[0])
        self.assertEqual(body_lines[start:start + len(dut_lines)], dut_lines)


# --------------------------------------------------------------------------
# Request
# --------------------------------------------------------------------------
class TestRequest(unittest.TestCase):
    def setUp(self):
        self.points = m.ratified_points()
        self.r = list(m.DEFAULT_R_OHM)
        _body, self.meas, self.tran = m.split_fragment(FRAGMENT)
        self.req = m.build_request("tb.spice", self.points, self.r, self.meas, self.tran)

    def test_ratified_grid_is_the_nine_point_oat_star(self):
        self.assertEqual(len(self.points), 9)
        self.assertIn(("tt", 27.0, m.NOMINAL_SUPPLY_V), self.points)

    def test_expansion_minus_exclude_is_exactly_the_wanted_points(self):
        c = self.req["corners"]
        procs, temps = c["process"], c["temperature_c"]
        vdds = sorted(set(c["params"][m.VDD_PARAM]))
        full = {(p, t, v) for p in procs for t in temps for v in vdds}
        dropped = {(e["process"], e["temperature_c"], e["params"][m.VDD_PARAM])
                   for e in self.req["exclude"]}
        self.assertEqual(full - dropped, set(self.points))

    def test_unit_count_is_points_times_sweep(self):
        c = self.req["corners"]
        n_rows_per_pvt = len(self.r)
        self.assertEqual(len(c["params"][m.R_REF_PARAM]),
                         len(set(c["params"][m.VDD_PARAM])) * n_rows_per_pvt)
        self.assertEqual(len(self.points) * n_rows_per_pvt, 9 * len(self.r))

    def test_param_axes_zip_by_index_and_are_unique(self):
        c = self.req["corners"]["params"]
        rows = list(zip(c[m.VDD_PARAM], c[m.R_REF_PARAM], strict=True))
        self.assertEqual(len(rows), len(set(rows)))
        self.assertEqual(sorted(set(c[m.R_REF_PARAM])), sorted(self.r))

    def test_required_sweep_values_are_simulated_points(self):
        swept = set(self.req["corners"]["params"][m.R_REF_PARAM])
        for required in m.REQUIRED_R_OHM:
            self.assertIn(required, swept)

    def test_supply_is_a_param_axis_not_a_supply_v_axis(self):
        """Every source in the committed fragment reads `{vdd_val}`, and
        `alter` addresses instances, never a `.param`."""
        self.assertNotIn("supply_v", self.req["corners"])
        self.assertIn(m.VDD_PARAM, self.req["corners"]["params"])

    def test_measurements_are_the_committed_meas_cards(self):
        names = [e["name"] for e in self.req["measurements"]]
        self.assertEqual(sorted(names), sorted(m.tb.all_measure_names()))
        for entry in self.req["measurements"]:
            self.assertTrue(entry["spice"].lower().startswith(".meas tran "))
            self.assertEqual(entry["spice"].split()[2], entry["name"])

    def test_saved_vectors_cover_every_measured_signal(self):
        saved = set(self.req["options"]["save_vectors"])
        self.assertIn("v(dout9)", saved)
        self.assertIn("v(busy)", saved)
        self.assertIn("v(sample_int)", saved)
        for name, src, _pot in m.tb.SUPPLY_SOURCES:
            self.assertIn(f"i({src.lower()})", saved)

    def test_analysis_is_the_committed_tran_card(self):
        self.assertEqual(self.req["analysis"], {"kind": "tran", "args": self.tran})

    def test_batch_submit_waits_for_capacity_and_shards(self):
        req = m.build_request("tb.spice", self.points, self.r, self.meas, self.tran,
                              capacity_wait_s=600.0, hosts=11)
        self.assertEqual(req["batch"]["capacity_wait_s"], 600.0)
        self.assertEqual(req["remote"]["hosts"], 11)

    def test_single_shard_declares_no_hosts(self):
        req = m.build_request("tb.spice", self.points, self.r, self.meas, self.tran,
                              hosts=1)
        self.assertNotIn("remote", req)


class TestSweepValidation(unittest.TestCase):
    def test_control_and_five_ohm_are_mandatory_for_a_record(self):
        with self.assertRaises(ValueError):
            m.check_r_values([5.0, 50.0])          # no control
        with self.assertRaises(ValueError):
            m.check_r_values([0.0, 50.0])          # 5 Ohm would be interpolated
        self.assertEqual(m.check_r_values([50.0, 0.0, 5.0, 5.0]), [0.0, 5.0, 50.0])

    def test_negative_and_empty_refused(self):
        with self.assertRaises(ValueError):
            m.normalize_r_values([-1.0, 0.0, 5.0])
        with self.assertRaises(ValueError):
            m.normalize_r_values([])

    def test_probe_sweep_need_not_carry_five_ohm(self):
        self.assertEqual(m.normalize_r_values([m.CONTROL_R_OHM]), [0.0])


class TestShardSizing(unittest.TestCase):
    def test_every_shard_fits_the_ceiling_run_serially(self):
        for n_units in (1, 9, 54, 100):
            hosts = m.shard_count(n_units)
            largest = -(-n_units // hosts)
            bound = largest * m.SHARD_SERIAL_BUDGET_S + m.FLEET_JOB_OVERHEAD_S
            self.assertLessEqual(bound, m.FLEET_JOB_CEILING_S, n_units)

    def test_default_grid_shards(self):
        self.assertEqual(m.shard_count(9 * len(m.DEFAULT_R_OHM)), 11)

    def test_never_zero_shards(self):
        self.assertEqual(m.shard_count(1), 1)


# --------------------------------------------------------------------------
# Report reading
# --------------------------------------------------------------------------
def _corner(process, temp, vdd, r, values, status="pass", diagnostics=None):
    return {
        "process": process,
        "temperature_c": temp,
        "params": {m.VDD_PARAM: vdd, m.R_REF_PARAM: r},
        "status": status,
        "measurements": [{"name": k, "value": v} for k, v in values.items()],
        "diagnostics": diagnostics or [],
    }


def _code_values(codes, supply_v=1.8):
    """`.meas` values that decode to `codes` (one per measured conversion),
    with a correct 12-period phase structure."""
    hi, lo = supply_v, 0.0
    out = {}
    for code, conv in zip(codes, m.tb.measured_conversions(), strict=True):
        bits = format(code, f"0{m.tb.N_BITS}b")
        for name, bit in zip(m.tb.code_measure_names(conv), bits, strict=True):
            out[name] = hi if bit == "1" else lo
        for i, name in enumerate(m.tb.busy_measure_names(conv)):
            out[name] = lo if i == m.tb.PHASES_PER_CONVERSION - 1 else hi
        for i, name in enumerate(m.tb.sample_measure_names(conv)):
            out[name] = hi if i == m.tb.PHASES_PER_CONVERSION - 1 else lo
    for name, _src, _pot in m.tb.SUPPLY_SOURCES:
        out[name] = 1.0e-6
    return out


class TestReadReport(unittest.TestCase):
    def test_error_envelope_refused(self):
        with self.assertRaises(ValueError):
            m.read_report({"error": {"code": "batch_no_capacity"}})

    def test_report_without_corners_refused(self):
        with self.assertRaises(ValueError):
            m.read_report({"status": "pass"})

    def test_worker_that_ignored_corners_params_refused(self):
        """An older worker image drops the unknown field and returns corners
        with no `params` echo -- that must not be read as a result."""
        report = {"corners": [{"process": "tt", "temperature_c": 27.0, "status": "pass",
                               "measurements": []}]}
        with self.assertRaises(ValueError):
            m.read_report(report)

    def test_duplicate_unit_refused(self):
        c = _corner("tt", 27.0, 1.8, 0.0, {})
        with self.assertRaises(ValueError):
            m.read_report({"corners": [c, dict(c)]})

    def test_keys_and_run_info(self):
        report = {
            "status": "pass",
            "corners": [_corner("tt", 27.0, 1.8, 5.0, _code_values([1, 2, 3, 4, 5]))],
            "environment": {"remote": {
                "job_id": "klt-sim-abc",
                "worker_environment": {
                    "pdk": {"stamp_text": "sky130A @ deadbeef"},
                    "simulator": {"version_banner": "* ngspice-47 compiled"},
                },
            }},
        }
        units, info = m.read_report(report)
        self.assertEqual(list(units), [("tt", 27.0, 1.8, 5.0)])
        self.assertEqual(info["job_id"], "klt-sim-abc")
        self.assertEqual(info["worker_pdk"], "sky130A @ deadbeef")
        self.assertEqual(info["worker_ngspice"], "ngspice-47")

    def test_error_status_and_diagnostics_make_a_unit_unusable(self):
        units, _ = m.read_report({"corners": [
            _corner("tt", 27.0, 1.8, 0.0, _code_values([1, 2, 3, 4, 5]), status="error"),
            _corner("ss", 27.0, 1.8, 0.0, _code_values([1, 2, 3, 4, 5]),
                    diagnostics=[{"severity": "error", "code": "timeout"}]),
        ]})
        self.assertFalse(units[("tt", 27.0, 1.8, 0.0)].usable)
        self.assertFalse(units[("ss", 27.0, 1.8, 0.0)].usable)


# --------------------------------------------------------------------------
# Budget arithmetic
# --------------------------------------------------------------------------
def _rows(spec):
    """spec: {r_ohm: codes or None}. None = the unit never produced codes."""
    rows = []
    for r, codes in spec.items():
        complete = codes is not None
        rows.append({
            "r_ohm": float(r), "status": "pass" if complete else "error", "errors": [],
            "codes": list(codes) if complete else [None] * N_INPUTS,
            "phase_ok": [True] * N_INPUTS if complete else [],
            "all_phase_ok": complete, "complete": complete,
            "i_vrefp_a": None, "i_vrefn_a": None,
        })
    return m.apply_control(rows)


BASE = [214, 383, 511, 641, 1023]   # the committed tt/27C/1.80V row


class TestControlAndBudgets(unittest.TestCase):
    def test_delta_is_against_the_corners_own_control_not_the_ideal_code(self):
        rows = _rows({0: BASE, 5: BASE, 50: BASE})
        self.assertNotEqual(BASE, m.ideal_codes())   # the DUT is NOT ideal here
        for row in rows:
            self.assertEqual(row["max_abs_delta"], 0)

    def test_tiers_pick_the_largest_passing_value(self):
        rows = _rows({
            0: BASE,
            5: BASE,
            50: [214, 383, 511, 641, 1022],          # 1 LSB
            200: [214, 383, 511, 645, 1023],         # 4 LSB
        })
        self.assertEqual(m.find_budget(rows, 0.0)["r_ohm"], 5.0)
        self.assertEqual(m.find_budget(rows, 1.0)["r_ohm"], 50.0)

    def test_right_censored_when_every_value_passes(self):
        rows = _rows({0: BASE, 5: BASE, 50: BASE, 3200: BASE})
        for tier in m.TIER_LSB:
            b = m.find_budget(rows, tier)
            self.assertEqual(b["r_ohm"], 3200.0)
            self.assertTrue(b["censored"])

    def test_not_censored_when_the_top_value_fails(self):
        rows = _rows({0: BASE, 5: BASE, 3200: [0, 0, 0, 0, 0]})
        b = m.find_budget(rows, 1.0)
        self.assertEqual(b["r_ohm"], 5.0)
        self.assertFalse(b["censored"])
        self.assertTrue(b["monotone"])

    def test_non_monotone_sweep_is_flagged_not_hidden(self):
        rows = _rows({0: BASE, 5: [214, 383, 511, 641, 1000], 50: BASE})
        b = m.find_budget(rows, 0.0)
        self.assertEqual(b["r_ohm"], 50.0)      # same rule as vcm-drive-budget
        self.assertFalse(b["monotone"])

    def test_unusable_control_yields_no_budget_and_no_deltas(self):
        rows = _rows({0: None, 5: BASE, 50: BASE})
        for row in rows:
            self.assertIsNone(row["deltas"])
            self.assertIsNone(row["max_abs_delta"])
        for tier in m.TIER_LSB:
            self.assertIsNone(m.find_budget(rows, tier))

    def test_an_incomplete_row_is_never_a_pass(self):
        rows = _rows({0: BASE, 5: None, 50: BASE})
        at5 = next(r for r in rows if r["r_ohm"] == 5.0)
        self.assertIsNone(at5["max_abs_delta"])
        self.assertEqual(m.find_budget(rows, 0.0)["r_ohm"], 50.0)
        self.assertFalse(m.find_budget(rows, 0.0)["monotone"])


class TestAnalyze(unittest.TestCase):
    def _report_units(self, r_values, codes_by_r, points):
        corners = []
        for p, t, v in points:
            for r in r_values:
                codes = codes_by_r.get(r)
                if codes is None:
                    continue
                corners.append(_corner(p, t, v, r, _code_values(codes, v)))
        units, _ = m.read_report({"corners": corners})
        return units

    def test_missing_unit_is_reported_missing_never_passed(self):
        points = m.ratified_points()
        r_values = [0.0, 5.0, 50.0]
        units = self._report_units(r_values, {0.0: BASE, 5.0: BASE}, points)
        result = m.analyze(units, points, r_values)
        for p in points:
            self.assertEqual(result[p]["missing_r"], [50.0])
            self.assertFalse(result[p]["complete"])
            self.assertTrue(result[p]["control_complete"])
            self.assertEqual(result[p]["budgets"][0.0]["r_ohm"], 5.0)

    def test_control_codes_compared_with_ideal_is_context_only(self):
        points = [("tt", 27.0, 1.8)]
        r_values = [0.0, 5.0]
        units = self._report_units(r_values, {0.0: BASE, 5.0: BASE}, points)
        result = m.analyze(units, points, r_values)
        a = result[points[0]]
        self.assertFalse(a["control_ideal_match"])   # the known DR-021 droop
        self.assertTrue(a["complete"])               # but the budget still reads
        self.assertEqual(a["budgets"][1.0]["r_ohm"], 5.0)

    def test_ideal_match_true_when_the_control_does_hit_the_ideal_codes(self):
        points = [("tt", 27.0, 1.8)]
        r_values = [0.0, 5.0]
        ideal = m.ideal_codes()
        units = self._report_units(r_values, {0.0: ideal, 5.0: ideal}, points)
        result = m.analyze(units, points, r_values)
        self.assertTrue(result[points[0]]["control_ideal_match"])


class TestInterpretation(unittest.TestCase):
    def _analysis(self, codes_at_5):
        points = m.ratified_points()
        r_values = [0.0, 5.0]
        corners = []
        for p, t, v in points:
            corners.append(_corner(p, t, v, 0.0, _code_values(BASE, v)))
            corners.append(_corner(p, t, v, 5.0, _code_values(codes_at_5, v)))
        units, _ = m.read_report({"corners": corners})
        return m.analyze(units, points, r_values), points, r_values

    def test_says_inside_when_no_code_moves(self):
        text = "\n".join(m.interpretation_lines(*self._analysis(BASE)))
        self.assertIn("INSIDE the tolerance", text)
        self.assertIn("not an interpolation", text)
        self.assertIn("says nothing about a shared analog bus", text)

    def test_says_outside_when_a_code_moves_more_than_one_lsb(self):
        moved = [BASE[0] + 9, *BASE[1:]]
        text = "\n".join(m.interpretation_lines(*self._analysis(moved)))
        self.assertIn("OUTSIDE the 1 LSB tier", text)

    def test_says_nothing_when_no_corner_is_readable(self):
        points = m.ratified_points()
        result = m.analyze({}, points, [0.0, 5.0])
        text = "\n".join(m.interpretation_lines(result, points, [0.0, 5.0]))
        self.assertIn("Not readable", text)
        self.assertNotIn("INSIDE", text)


class TestDecodeUnit(unittest.TestCase):
    def test_round_trips_codes_through_the_shared_decoder(self):
        units, _ = m.read_report({"corners": [
            _corner("tt", 27.0, 1.8, 0.0, _code_values(BASE))]})
        row = m.decode_unit(units[("tt", 27.0, 1.8, 0.0)])
        self.assertEqual(row["codes"], BASE)
        self.assertTrue(row["all_phase_ok"])
        self.assertTrue(row["complete"])

    def test_supply_scaled_threshold_is_the_shared_one(self):
        """The 1/0 threshold is a fraction of that corner's own supply, so a
        1.62 V corner decodes with a 1.62 V threshold."""
        units, _ = m.read_report({"corners": [
            _corner("tt", 27.0, 1.62, 0.0, _code_values(BASE, 1.62))]})
        self.assertEqual(m.decode_unit(units[("tt", 27.0, 1.62, 0.0)])["codes"], BASE)

    def test_missing_bit_makes_the_row_incomplete(self):
        values = _code_values(BASE)
        values.pop(m.tb.code_measure_names(m.tb.measured_conversions()[0])[0])
        units, _ = m.read_report({"corners": [_corner("tt", 27.0, 1.8, 0.0, values)]})
        row = m.decode_unit(units[("tt", 27.0, 1.8, 0.0)])
        self.assertIsNone(row["codes"][0])
        self.assertFalse(row["complete"])


class TestFullConversionReference(unittest.TestCase):
    """The cross-check reads the committed record at write time rather than
    carrying a transcribed number, so a later re-run of that campaign cannot
    leave a stale figure in this runner."""

    def test_reads_every_corner_of_the_committed_power_table(self):
        ref = m.full_conversion_reference()
        self.assertIsNotNone(ref)
        rec_id, currents = ref
        self.assertEqual(
            (m.FULL_CONVERSION_RECORDS / "LATEST").read_text().strip(), f"{rec_id}.md")
        for point in m.ratified_points():
            self.assertIn(m.corners_mod.corner_id(*point), currents)
        for value in currents.values():
            self.assertGreater(value, 0.0)
            self.assertLess(value, 1e-3)

    def test_column_is_located_by_header_not_by_position(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "r.md").write_text(
                "| corner-id | I(VREFP) (uA) | I(VDD) (uA) |\n"
                "|---|---|---|\n"
                "| `tt_27c_1.80v` | 6.490 | 2.094 |\n"
            )
            (d / "LATEST").write_text("r.md\n")
            rec_id, currents = m.full_conversion_reference(d)
            self.assertEqual(rec_id, "r")
            self.assertAlmostEqual(currents["tt_27c_1.80v"], 6.490e-6)

    def test_missing_record_is_none_not_a_guess(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(m.full_conversion_reference(Path(tmp)))
            (Path(tmp) / "LATEST").write_text("absent.md\n")
            self.assertIsNone(m.full_conversion_reference(Path(tmp)))

    def test_power_table_without_the_column_is_none(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "r.md").write_text("| corner-id | I(VDD) (uA) |\n|---|---|\n| `tt` | 1 |\n")
            (d / "LATEST").write_text("r.md\n")
            self.assertIsNone(m.full_conversion_reference(d))


class TestReferenceCurrentSection(unittest.TestCase):
    def _analysis(self, control_i, swept_i):
        points = m.ratified_points()
        r_values = [0.0, 5.0]
        corners = []
        for proc, t, v in points:
            c0 = _corner(proc, t, v, 0.0, _code_values(BASE, v))
            c0["measurements"].append({"name": "i_vrefp", "value": control_i})
            c5 = _corner(proc, t, v, 5.0, _code_values(BASE, v))
            c5["measurements"].append({"name": "i_vrefp", "value": swept_i})
            corners += [c0, c5]
        units, _ = m.read_report({"corners": corners})
        return m.analyze(units, points, r_values), points, r_values

    def test_marks_the_control_row_and_names_the_cross_check(self):
        text = "\n".join(m.reference_current_lines(*self._analysis(4.6e-4, -6.49e-6)))
        self.assertIn("NOT a measurement", text)
        self.assertIn("1e-12 Ohm resistor floor", text)
        self.assertIn("No budget in this record depends on them", text)
        self.assertIn("sim/full-conversion-transient/records/", text)
        # the "sign is not consistent" claim must cite every corner it rests
        # on, not a prefix of them
        for point in m.ratified_points():
            self.assertIn(f"`{m.corners_mod.corner_id(*point)}` +460", text)

    def test_reports_the_worst_difference_against_the_committed_record(self):
        """A swept current far from the ideal-source record must show up as a
        large worst-difference, not be quietly omitted."""
        close = "\n".join(m.reference_current_lines(*self._analysis(4.6e-4, -6.49e-6)))
        far = "\n".join(m.reference_current_lines(*self._analysis(4.6e-4, -100e-6)))
        self.assertIn("Worst difference", close)
        self.assertIn("Worst difference", far)
        self.assertNotEqual(close, far)

    def test_control_row_current_is_flagged_in_the_per_row_table(self):
        analysis, points, r_values = self._analysis(4.6e-4, -6.49e-6)
        rows = analysis[points[0]]["rows"]
        control = next(r for r in rows if r["r_ohm"] == m.CONTROL_R_OHM)
        swept = next(r for r in rows if r["r_ohm"] == 5.0)
        self.assertAlmostEqual(control["i_vrefp_a"], 4.6e-4)
        self.assertAlmostEqual(swept["i_vrefp_a"], -6.49e-6)


class TestRunInfo(unittest.TestCase):
    """A sharded batch run carries job identity under
    `environment.remote.fleet[]`, not on `environment.remote` itself."""

    def _shard(self, job, pdk="f6eeac7", ng="ngspice-47"):
        return {
            "job_id": job, "state": "done", "exit_code": "0",
            "instance_type": "c7i.8xlarge", "elapsed_seconds": 258,
            "runner_klt_version": "0.9.0",
            "runner_request_features": {"status": "supported"},
            "worker_environment": {
                "pdk": {"variant": "sky130A", "stamp_text": f"open_pdks {pdk}"},
                "simulator": {"version_banner": f"** {ng} : Circuit level simulation"},
            },
        }

    def _info(self, remote, backend="batch"):
        report = {"status": "pass", "corners": [],
                  "environment": {"remote": remote, "backend": {"resolved": backend}}}
        _units, info = m.read_report(report)
        return info

    def test_sharded_run_reports_every_job_id(self):
        info = self._info({"fleet": [self._shard("a"), self._shard("b")]})
        self.assertTrue(info["sharded"])
        self.assertEqual([j["job_id"] for j in info["jobs"]], ["a", "b"])
        self.assertEqual(info["worker_pdk"], "sky130A @ f6eeac7")
        self.assertEqual(info["worker_ngspice"], "ngspice-47")
        self.assertEqual(info["resolved_backend"], "batch")
        self.assertEqual(info["request_feature_status"], "supported")

    def test_single_job_run_still_reads(self):
        info = self._info(dict(self._shard("solo")))
        self.assertFalse(info["sharded"])
        self.assertEqual(info["job_id"], "solo")
        self.assertEqual([j["job_id"] for j in info["jobs"]], ["solo"])

    def test_disagreeing_shards_report_no_single_environment(self):
        """One shard's PDK must not stand for the whole run."""
        info = self._info({"fleet": [self._shard("a"), self._shard("b", pdk="deadbee")]})
        self.assertIsNone(info["worker_pdk"])
        self.assertEqual(len(info["worker_pdks_seen"]), 2)
        info = self._info({"fleet": [self._shard("a"), self._shard("b", ng="ngspice-46")]})
        self.assertIsNone(info["worker_ngspice"])

    def test_no_fleet_and_no_job_id_yields_no_jobs(self):
        info = self._info({})
        self.assertEqual(info["jobs"], [])
        self.assertIsNone(info["job_id"])

    def test_ngspice_banner_parsing(self):
        self.assertEqual(
            m._ngspice_from_banner("******\n** ngspice-47 : Circuit level\n******"),
            "ngspice-47")
        self.assertIsNone(m._ngspice_from_banner(""))


class TestRequestIsJsonSerialisable(unittest.TestCase):
    def test_round_trips(self):
        _body, meas, tran = m.split_fragment(FRAGMENT)
        req = m.build_request("tb.spice", m.ratified_points(), list(m.DEFAULT_R_OHM),
                              meas, tran, capacity_wait_s=600.0, hosts=11)
        self.assertEqual(json.loads(json.dumps(req)), req)


# --------------------------------------------------------------------------
# Inputs pinned at a code rail (issue #841 review)
# --------------------------------------------------------------------------
#: `BASE` is the committed tt/27C/1.80V row and its FIFTH entry is already at
#: the converter's full-scale rail (the DR-021 near-full-scale droop), so the
#: real campaign exercises this path at every corner.
PINNED_INDEX = N_INPUTS - 1


class TestPinnedInputs(unittest.TestCase):
    def test_full_scale_and_zero_control_codes_are_pinned(self):
        self.assertEqual(m.RAIL_CODES, (0, m.fc.FULL_SCALE_CODE))
        self.assertEqual(m.pinned_inputs(BASE), [PINNED_INDEX])
        self.assertEqual(m.pinned_inputs([0, 384, 512, 640, 911]), [0])
        self.assertEqual(
            m.pinned_inputs([0, 384, 512, 640, m.fc.FULL_SCALE_CODE]),
            [0, PINNED_INDEX])

    def test_a_control_off_both_rails_pins_nothing(self):
        self.assertEqual(m.pinned_inputs(m.ideal_codes()), [])

    def test_no_control_codes_pins_nothing_rather_than_guessing(self):
        self.assertEqual(m.pinned_inputs(None), [])
        self.assertEqual(m.pinned_inputs([]), [])

    def test_analyze_reports_the_pinned_input_per_corner(self):
        points = [("tt", 27.0, 1.8)]
        r_values = [0.0, 5.0]
        corners = [_corner("tt", 27.0, 1.8, r, _code_values(BASE, 1.8)) for r in r_values]
        units, _ = m.read_report({"corners": corners})
        a = m.analyze(units, points, r_values)[points[0]]
        self.assertEqual(a["pinned_inputs"], [PINNED_INDEX])

    def test_an_unusable_control_pins_nothing(self):
        points = [("tt", 27.0, 1.8)]
        r_values = [0.0, 5.0]
        corners = [_corner("tt", 27.0, 1.8, 5.0, _code_values(BASE, 1.8))]
        units, _ = m.read_report({"corners": corners})
        a = m.analyze(units, points, r_values)[points[0]]
        self.assertFalse(a["control_complete"])
        self.assertEqual(a["pinned_inputs"], [])

    def test_delta_cell_reads_pin_not_plus_zero(self):
        rows = _rows({0: BASE, 5: BASE})
        for row in rows:
            cells = m._delta_cells(row, [PINNED_INDEX]).split(", ")
            self.assertEqual(cells[PINNED_INDEX], "pin")
            self.assertEqual(cells[:PINNED_INDEX], ["+0"] * PINNED_INDEX)

    def test_a_pinned_input_that_moves_inward_still_prints_its_delta(self):
        """The marker must never hide real movement off the rail."""
        moved = [*BASE[:PINNED_INDEX], BASE[PINNED_INDEX] - 3]
        rows = _rows({0: BASE, 5: moved})
        at5 = next(r for r in rows if r["r_ohm"] == 5.0)
        cells = m._delta_cells(at5, [PINNED_INDEX]).split(", ")
        self.assertEqual(cells[PINNED_INDEX], "-3")
        self.assertEqual(at5["max_abs_delta"], 3)   # and it still counts

    def test_unreadable_row_delta_cell_is_na(self):
        rows = _rows({0: BASE, 5: None})
        at5 = next(r for r in rows if r["r_ohm"] == 5.0)
        self.assertEqual(m._delta_cells(at5, [PINNED_INDEX]), "n/a")


class TestPinnedInputsInTheInterpretation(unittest.TestCase):
    """The `5 Ohm` statement must count only (corner, input) pairs that can
    register movement, and must name the ones it excluded."""

    def _analysis(self, control, codes_at_5):
        points = m.ratified_points()
        r_values = [0.0, 5.0]
        corners = []
        for proc, t, v in points:
            corners.append(_corner(proc, t, v, 0.0, _code_values(control, v)))
            corners.append(_corner(proc, t, v, 5.0, _code_values(codes_at_5, v)))
        units, _ = m.read_report({"corners": corners})
        return m.analyze(units, points, r_values), points, r_values

    def test_population_excludes_the_pinned_pairs(self):
        text = "\n".join(m.interpretation_lines(*self._analysis(BASE, BASE)))
        n_corners = len(m.ratified_points())
        self.assertIn(f"**{n_corners * (N_INPUTS - 1)} of {n_corners * N_INPUTS}**", text)
        self.assertNotIn(f"all {N_INPUTS} inputs", text)

    def test_names_the_excluded_input_and_refuses_to_bound_it(self):
        text = "\n".join(m.interpretation_lines(*self._analysis(BASE, BASE)))
        self.assertIn("+0.78*V_REF", text)
        self.assertIn("EXCLUDED", text)
        self.assertIn("does not bound the reference drive's effect on them at all", text)

    def test_an_unpinned_run_counts_every_pair_and_excludes_nothing(self):
        ideal = m.ideal_codes()
        text = "\n".join(m.interpretation_lines(*self._analysis(ideal, ideal)))
        n = len(m.ratified_points()) * N_INPUTS
        self.assertIn(f"**{n} of {n}**", text)
        self.assertNotIn("EXCLUDED", text)

    def test_movement_on_a_pinned_input_alone_does_not_make_the_claim(self):
        """Every countable pair is still 0, so the 5 Ohm verdict rests on the
        countable inputs -- the pinned column cannot carry it."""
        moved = [*BASE[:PINNED_INDEX], BASE[PINNED_INDEX] - 1]
        text = "\n".join(m.interpretation_lines(*self._analysis(BASE, moved)))
        self.assertIn("**0 LSB**", text)
        self.assertIn("only on the inputs counted above", text)

    def test_every_input_pinned_states_nothing(self):
        rails = [0] * N_INPUTS
        text = "\n".join(m.interpretation_lines(*self._analysis(rails, rails)))
        self.assertIn("Not readable", text)
        self.assertNotIn("INSIDE", text)


class TestPinnedInputLimitSection(unittest.TestCase):
    def _analysis(self, control, codes_at_5):
        points = m.ratified_points()
        r_values = [0.0, 5.0]
        corners = []
        for proc, t, v in points:
            corners.append(_corner(proc, t, v, 0.0, _code_values(control, v)))
            corners.append(_corner(proc, t, v, 5.0, _code_values(codes_at_5, v)))
        units, _ = m.read_report({"corners": corners})
        return m.analyze(units, points, r_values), points

    def test_limit_is_stated_when_an_input_is_pinned(self):
        moved = [BASE[0] + 1, *BASE[1:]]
        text = "\n".join(m.pinned_input_limit_lines(*self._analysis(BASE, moved)))
        self.assertIn("already at a code rail", text)
        self.assertIn("+0.78*V_REF", text)
        self.assertIn("NOT AT ALL", text)
        # the budget-setting input is READ OFF the sweep, not asserted
        self.assertIn("`-0.78*V_REF` at 9/9 usable corners", text)
        self.assertIn("opposite sign", text)

    def test_no_section_at_all_when_nothing_is_pinned(self):
        ideal = m.ideal_codes()
        self.assertEqual(m.pinned_input_limit_lines(*self._analysis(ideal, ideal)), [])

    def test_a_sweep_that_never_moves_says_so_instead_of_naming_an_input(self):
        text = "\n".join(m.pinned_input_limit_lines(*self._analysis(BASE, BASE)))
        self.assertIn("right-censored rather than set by a particular input", text)

    def test_first_movers_picks_the_lowest_moving_rung_only(self):
        rows = _rows({
            0: BASE,
            5: BASE,
            50: [BASE[0] + 1, *BASE[1:]],
            200: [BASE[0] + 2, BASE[1] - 2, *BASE[2:]],
        })
        fm = m.first_movers(rows, [PINNED_INDEX])
        self.assertEqual(fm, {"r_ohm": 50.0, "inputs": [0]})

    def test_first_movers_ignores_a_pinned_input(self):
        moved = [*BASE[:PINNED_INDEX], BASE[PINNED_INDEX] - 1]
        rows = _rows({0: BASE, 5: moved, 50: [BASE[0] + 1, *BASE[1:]]})
        self.assertEqual(m.first_movers(rows, [PINNED_INDEX])["r_ohm"], 50.0)

    def test_first_movers_is_none_when_nothing_countable_moves(self):
        self.assertIsNone(m.first_movers(_rows({0: BASE, 5: BASE}), [PINNED_INDEX]))


# --------------------------------------------------------------------------
# The control rows against the ideal-drive record (issue #841 review)
# --------------------------------------------------------------------------
class TestFullConversionCapturedCodes(unittest.TestCase):
    def test_reads_every_corner_of_the_committed_captured_code_table(self):
        ref = m.full_conversion_captured_codes()
        self.assertIsNotNone(ref)
        rec_id, codes = ref
        self.assertEqual(
            (m.FULL_CONVERSION_RECORDS / "LATEST").read_text().strip(), f"{rec_id}.md")
        for point in m.ratified_points():
            row = codes[m.corners_mod.corner_id(*point)]
            self.assertEqual(len(row), N_INPUTS)
            for code in row:
                self.assertGreaterEqual(code, 0)
                self.assertLessEqual(code, m.fc.FULL_SCALE_CODE)

    def test_strips_the_lsb_annotation_from_each_cell(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "r.md").write_text(
                "| corner-id | `-0.78*V_REF` (ideal 113) | `+0.78*V_REF` (ideal 911) |\n"
                "|---|---|---|\n"
                "| `tt_27c_1.80v` | 214 (+101 LSB) | 1023 (+112 LSB) |\n"
            )
            (d / "LATEST").write_text("r.md\n")
            rec_id, codes = m.full_conversion_captured_codes(d)
            self.assertEqual(rec_id, "r")
            self.assertEqual(codes["tt_27c_1.80v"], [214, 1023])

    def test_a_record_without_that_table_is_none_not_a_guess(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "r.md").write_text("| corner | I(VREFP) (uA) |\n|---|---|\n| `tt` | 6.49 |\n")
            (d / "LATEST").write_text("r.md\n")
            self.assertIsNone(m.full_conversion_captured_codes(d))

    def test_missing_record_is_none(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(m.full_conversion_captured_codes(Path(tmp)))


class TestFullConversionEnvironment(unittest.TestCase):
    def test_reads_the_compared_records_pdk_and_simulator(self):
        env = m.full_conversion_environment()
        self.assertRegex(env["pdk"], r"^sky130A @ [0-9a-f]{40}$")
        self.assertTrue(env["ngspice"].startswith("ngspice-"))
        self.assertRegex(env["dut_sha256"], r"^[0-9a-f]{64}$")

    def test_only_the_environment_block_is_read(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "r.md").write_text(
                "## Run\n\n- PDK: decoy\n\n## Environment\n\n"
                "- PDK: sky130A @ abc\n- ngspice: ngspice-47\n")
            (d / "LATEST").write_text("r.md\n")
            self.assertEqual(m.full_conversion_environment(d)["pdk"], "sky130A @ abc")

    def test_missing_record_is_an_empty_mapping(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(m.full_conversion_environment(Path(tmp)), {})


class TestControlVsIdealDriveSection(unittest.TestCase):
    def _analysis(self, control_by_corner):
        points = m.ratified_points()
        r_values = [0.0, 5.0]
        corners = []
        for proc, t, v in points:
            codes = control_by_corner[m.corners_mod.corner_id(proc, t, v)]
            corners.append(_corner(proc, t, v, 0.0, _code_values(codes, v)))
            corners.append(_corner(proc, t, v, 5.0, _code_values(codes, v)))
        units, _ = m.read_report({"corners": corners})
        return m.analyze(units, points, r_values), points

    def test_reports_the_whole_population_not_the_corner_that_matches(self):
        """The defect this section exists for: the record used to cite the one
        corner that agreed and say nothing about the other eight."""
        _rec_id, theirs = m.full_conversion_captured_codes()
        mine = {cid: list(codes) for cid, codes in theirs.items()}
        mine["sf_27c_1.80v"] = [theirs["sf_27c_1.80v"][0] + 1,
                                *theirs["sf_27c_1.80v"][1:]]
        text = "\n".join(m.control_vs_ideal_drive_lines(*self._analysis(mine)))
        self.assertIn("Over the 9 shared corners", text)
        self.assertIn("**8 agree on every input**", text)
        self.assertIn("**1 does not**", text)
        self.assertIn("`sf_27c_1.80v`", text)
        self.assertIn("+1 LSB", text)

    def test_names_both_unseparated_explanations_for_a_difference(self):
        _rec_id, theirs = m.full_conversion_captured_codes()
        mine = {cid: list(codes) for cid, codes in theirs.items()}
        mine["sf_27c_1.80v"] = [theirs["sf_27c_1.80v"][0] + 1,
                                *theirs["sf_27c_1.80v"][1:]]
        text = "\n".join(m.control_vs_ideal_drive_lines(*self._analysis(mine)))
        self.assertIn("separates NEITHER", text)
        self.assertIn("PDK-commit difference", text)
        self.assertIn("1e-12 Ohm series element", text)

    def test_full_agreement_states_it_without_a_caveat_paragraph(self):
        _rec_id, theirs = m.full_conversion_captured_codes()
        text = "\n".join(m.control_vs_ideal_drive_lines(
            *self._analysis({cid: list(c) for cid, c in theirs.items()})))
        self.assertIn("**9 agree on every input**", text)
        self.assertIn("**0 do not**", text)
        self.assertNotIn("What that bounds", text)


class TestCrossCheckUncontrolledDifference(unittest.TestCase):
    def test_names_the_pdk_commit_on_both_sides(self):
        text = "\n".join(m._cross_check_uncontrolled_lines(
            "sky130A @ " + "f" * 40))
        self.assertIn("NOT controlled for PDK commit", text)
        self.assertIn("f" * 40, text)
        self.assertIn(m.full_conversion_environment()["pdk"], text)

    def test_an_unknown_run_pdk_is_said_not_invented(self):
        text = "\n".join(m._cross_check_uncontrolled_lines(None))
        self.assertIn("unknown", text)

    def test_the_section_carries_it_next_to_the_agreement_claim(self):
        points = m.ratified_points()
        r_values = [0.0, 5.0]
        corners = []
        for proc, t, v in points:
            c0 = _corner(proc, t, v, 0.0, _code_values(BASE, v))
            c0["measurements"].append({"name": "i_vrefp", "value": 4.6e-4})
            c5 = _corner(proc, t, v, 5.0, _code_values(BASE, v))
            c5["measurements"].append({"name": "i_vrefp", "value": -6.49e-6})
            corners += [c0, c5]
        units, _ = m.read_report({"corners": corners})
        analysis = m.analyze(units, points, r_values)
        text = "\n".join(m.reference_current_lines(
            analysis, points, r_values, run_pdk="sky130A @ " + "f" * 40))
        self.assertIn("drives the same circuit rather than a differently-wired one",
                      text)
        self.assertIn("NOT controlled for PDK commit", text)
        # and the one-corner claim the review rejected is gone
        self.assertNotIn("for that corner exactly", text)


if __name__ == "__main__":
    unittest.main()

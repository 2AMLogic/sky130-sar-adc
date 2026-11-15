"""Unit tests for sim/full-conversion-transient/ (issue #254) -- pure text
generation, decoding and record rendering; no ngspice/PDK required (the
PDK-free unit-test convention sim/tests/test_harness.py and
sim/tests/test_cdac_fragment_gen.py established, sim/selftest.sh stage 1/4).

Three things are load-bearing enough to pin here rather than trust to a
five-minute-per-corner simulation:

1. The committed testbench fragment matches a fresh generation byte-for-byte
   (the same guarantee sim/tests/test_cdac_fragment_gen.py gives that
   experiment's generator), so a reviewer reading
   `testbench/full_conversion_tb_fragment.spice` is reading exactly what the
   driver runs.
2. The DR-006 timing schedule the fragment encodes is self-consistent --
   each conversion is 12 CLK periods, the code is read inside that
   conversion's own SAMPLE period, and each DC input step lands while the
   sampling switch is closed-loop-irrelevant (mid bit-trial), never inside a
   SAMPLE window.
3. `decode()` turns `.meas` values into the same code an ngspice log implies,
   and `write_record()` emits every base field `sim/report/generate.py`
   re-extracts (a missing field would silently degrade the characterization
   report rather than fail).
"""

from __future__ import annotations

import json
import math
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parent.parent
EXPERIMENT_DIR = SIM_DIR / "full-conversion-transient"
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(EXPERIMENT_DIR))

import gen_full_conversion_tb as tb  # noqa: E402
import provenance_fixture  # noqa: E402
import run_conversion as run_conversion_mod  # noqa: E402  (the runner's own CLI)
from full_conversion_campaigns import cm_trace as fc_cm  # noqa: E402
from full_conversion_campaigns import common as fc_common  # noqa: E402
from full_conversion_campaigns import dc_codes as fc_dc  # noqa: E402
from full_conversion_campaigns import decision_margin as fc_dm  # noqa: E402
from full_conversion_campaigns import node_trace as fc_node  # noqa: E402
from harness import toolchain as harness_toolchain  # noqa: E402
from report import generate as report_generate  # noqa: E402


class TestFragmentIsFresh(unittest.TestCase):
    def test_committed_fragment_matches_fresh_generation(self):
        self.assertEqual(
            tb.FRAGMENT_PATH.read_text(),
            tb.fragment_text(),
            "testbench/full_conversion_tb_fragment.spice is stale -- regenerate "
            "with `python3 sim/full-conversion-transient/gen_full_conversion_tb.py --write`",
        )

    def test_every_measurement_name_appears_exactly_once_in_the_fragment(self):
        text = tb.FRAGMENT_PATH.read_text()
        for name in tb.all_measure_names():
            self.assertEqual(
                text.count(f".meas tran {name} "), 1,
                f"measurement {name!r} is not emitted exactly once by the fragment",
            )

    def test_fragment_supplies_and_dut_ports_are_all_driven(self):
        text = tb.FRAGMENT_PATH.read_text()
        for source in ("VVDD VDD", "VVPWR VPWR", "VVGND VGND", "VVREFP VREFP",
                       "VVREFN VREFN", "VVCM VCM", "VCLK CLK", "VRSTB RST_B",
                       "VINP VINP", "VINN VINN"):
            self.assertIn(source, text, f"{source} missing from the fragment")


class TestTimingSchedule(unittest.TestCase):
    def test_conversion_is_twelve_clk_periods_of_the_dr006_worst_case_clock(self):
        self.assertEqual(tb.PHASES_PER_CONVERSION, 12)
        self.assertAlmostEqual(tb.T_CLK_NS, 1000.0 / 12.0, places=9)
        # 12 periods at 12 MHz is exactly 1 us per conversion.
        self.assertAlmostEqual(
            tb.t_edge_ns(12) - tb.t_edge_ns(0), 1000.0, places=9
        )

    def test_code_is_read_inside_that_conversions_own_sample_period(self):
        for c in tb.measured_conversions():
            t_read = tb.t_code_read_ns(c)
            # The code is complete at edge 12c+10 (DOUT0's capture) and is
            # overwritten at edge 12c+13 (the next conversion's DOUT9).
            self.assertGreater(t_read, tb.t_edge_ns(12 * c + 10))
            self.assertLess(t_read, tb.t_edge_ns(12 * c + 13))

    def test_input_steps_land_mid_bit_trial_never_inside_a_sample_window(self):
        sample_windows = [
            (tb.t_edge_ns(12 * c + 11), tb.t_edge_ns(12 * c + 12))
            for c in range(tb.N_CONVERSIONS)
        ]
        for c in range(1, tb.N_CONVERSIONS):
            t_step = tb.t_input_step_ns(c)
            for lo, hi in sample_windows:
                self.assertFalse(
                    lo <= t_step <= hi,
                    f"input step for conversion {c} at {t_step} ns lands inside a "
                    f"SAMPLE window ({lo}, {hi}) -- it would disturb acquisition",
                )
            # and it must precede the SAMPLE window it is meant to be ready for
            self.assertLess(t_step + tb.EDGE_NS, tb.t_edge_ns(12 * c - 1))

    def test_transient_span_covers_every_measurement(self):
        stop = tb.t_stop_ns()
        for c in tb.measured_conversions():
            self.assertLess(tb.t_code_read_ns(c), stop)
            self.assertLess(tb.t_phase_mid_ns(c, tb.PHASES_PER_CONVERSION - 1), stop)


class TestIdealCode(unittest.TestCase):
    def test_midscale_and_full_scale_mapping(self):
        self.assertEqual(tb.ideal_code(0.0), 512)
        self.assertEqual(tb.ideal_code(1.0), 1023)  # clamped at the top code
        self.assertEqual(tb.ideal_code(-1.0), 0)
        self.assertEqual(tb.ideal_code(0.25), 640)
        self.assertEqual(tb.ideal_code(-0.25), 384)

    def test_one_lsb_of_input_moves_the_ideal_code_by_one(self):
        one_lsb_fraction = 1.0 / 512.0  # LSB = 2*V_REF/1024, input is a fraction of V_REF
        self.assertEqual(tb.ideal_code(one_lsb_fraction) - tb.ideal_code(0.0), 1)

    def test_ideal_code_is_monotonic_in_the_input(self):
        codes = [tb.ideal_code(f) for f in tb.INPUT_FRACTIONS]
        self.assertEqual(codes, sorted(codes))
        self.assertEqual(len(set(codes)), len(codes))


def _synthetic_parsed(code_by_conversion: dict[int, int], supply_v: float = 1.8) -> dict:
    """A parsed-.meas dict standing in for one ngspice run: `code_by_conversion`
    maps a conversion index to the code its DOUT bits should decode to, with a
    correct 12-period BUSY/SAMPLE_INT phase structure and plausible currents."""
    hi, lo = supply_v, 0.0
    parsed: dict[str, float] = {}
    for c in tb.measured_conversions():
        code = code_by_conversion[c]
        bits = [(code >> b) & 1 for b in range(tb.N_BITS - 1, -1, -1)]
        for name, b in zip(tb.code_measure_names(c), bits):
            parsed[name] = hi if b else lo
        for p, name in enumerate(tb.busy_measure_names(c)):
            parsed[name] = lo if p == tb.PHASES_PER_CONVERSION - 1 else hi
        for p, name in enumerate(tb.sample_measure_names(c)):
            parsed[name] = hi if p == tb.PHASES_PER_CONVERSION - 1 else lo
    parsed.update(i_vdd=-2.0e-6, i_vpwr=-3.0e-6, i_vrefp=-2.5e-6, i_vrefn=1.0e-6, i_vcm=-0.5e-6)
    return parsed


class TestDecode(unittest.TestCase):
    def test_ideal_inputs_decode_to_the_ideal_codes_and_pass(self):
        ideal = {c: tb.ideal_code(tb.input_fraction(c)) for c in tb.measured_conversions()}
        result = fc_common.decode(_synthetic_parsed(ideal), 1.8)
        self.assertTrue(result["all_ok"])
        self.assertEqual(result["worst_error_lsb"], 0)
        self.assertEqual(result["n_code_ok"], result["n_conversions"])
        self.assertEqual(result["n_phase_ok"], result["n_conversions"])

    def test_a_one_lsb_error_still_passes_but_a_two_lsb_error_does_not(self):
        base = {c: tb.ideal_code(tb.input_fraction(c)) for c in tb.measured_conversions()}
        one_off = dict(base)
        one_off[tb.measured_conversions()[0]] += 1
        self.assertTrue(fc_common.decode(_synthetic_parsed(one_off), 1.8)["all_ok"])
        two_off = dict(base)
        two_off[tb.measured_conversions()[0]] += 2
        result = fc_common.decode(_synthetic_parsed(two_off), 1.8)
        self.assertFalse(result["all_ok"])
        self.assertEqual(result["worst_error_lsb"], 2)

    def test_a_broken_phase_structure_fails_even_when_the_code_is_right(self):
        ideal = {c: tb.ideal_code(tb.input_fraction(c)) for c in tb.measured_conversions()}
        parsed = _synthetic_parsed(ideal)
        # BUSY stuck high through the SAMPLE period == conversion did not finish
        c = tb.measured_conversions()[0]
        parsed[tb.busy_measure_names(c)[-1]] = 1.8
        result = fc_common.decode(parsed, 1.8)
        self.assertFalse(result["all_ok"])
        self.assertEqual(result["n_phase_ok"], result["n_conversions"] - 1)

    def test_power_sums_only_the_sources_at_a_nonzero_potential(self):
        ideal = {c: tb.ideal_code(tb.input_fraction(c)) for c in tb.measured_conversions()}
        result = fc_common.decode(_synthetic_parsed(ideal), 1.8)
        expected = 1.8 * (2.0e-6 + 3.0e-6 + 2.5e-6) + 0.9 * 0.5e-6
        self.assertAlmostEqual(result["power_w"], expected, places=12)

    def test_missing_measurements_do_not_decode_to_a_bogus_code(self):
        ideal = {c: tb.ideal_code(tb.input_fraction(c)) for c in tb.measured_conversions()}
        parsed = _synthetic_parsed(ideal)
        del parsed[tb.code_measure_names(tb.measured_conversions()[0])[0]]
        result = fc_common.decode(parsed, 1.8)
        self.assertIsNone(result["conversions"][0]["code"])
        self.assertFalse(result["all_ok"])


_NON_FINITE = (("+inf", math.inf), ("-inf", -math.inf), ("nan", math.nan))


def _ideal_codes() -> dict[int, int]:
    return {c: tb.ideal_code(tb.input_fraction(c)) for c in tb.measured_conversions()}


class TestDecodeRejectsNonFinite(unittest.TestCase):
    """Issue #569: a NaN/+-inf handed straight to decode() is unavailable --
    never a bit, never a margin entry, never a current or a power term."""

    SUPPLY_V = 1.8
    # synthetic levels are exactly 0 / V_DD against a V_DD/2 threshold
    IDEAL_MARGIN_V = 0.9

    def _assert_margin_is_finite_and_ideal(self, result: dict) -> None:
        self.assertTrue(math.isfinite(result["worst_margin_v"]))
        self.assertAlmostEqual(result["worst_margin_v"], self.IDEAL_MARGIN_V)

    def test_control_is_finite_and_passes(self):
        result = fc_common.decode(_synthetic_parsed(_ideal_codes()), self.SUPPLY_V)
        self.assertTrue(result["all_ok"])
        self._assert_margin_is_finite_and_ideal(result)

    def test_non_finite_code_bits_are_undecodable(self):
        parsed0 = _synthetic_parsed(_ideal_codes())
        c0 = tb.measured_conversions()[0]
        names = tb.code_measure_names(c0)
        high = next(n for n in names if parsed0[n] > 0.9)
        low = next(n for n in names if parsed0[n] < 0.9)
        for which, name in (("expected-high", high), ("expected-low", low)):
            for label, bad in _NON_FINITE:
                with self.subTest(bit=which, value=label):
                    parsed = dict(parsed0)
                    parsed[name] = bad
                    result = fc_common.decode(parsed, self.SUPPLY_V)
                    cv = result["conversions"][0]
                    self.assertIsNone(cv["bits"][names.index(name)])
                    self.assertIsNone(cv["code"])
                    self.assertFalse(cv["code_ok"])
                    self.assertFalse(result["all_ok"])
                    self._assert_margin_is_finite_and_ideal(result)

    def test_non_finite_busy_and_sample_fail_the_phase_structure(self):
        parsed0 = _synthetic_parsed(_ideal_codes())
        c0 = tb.measured_conversions()[0]
        cases = (
            ("busy-high", tb.busy_measure_names(c0)[0]),
            ("busy-low", tb.busy_measure_names(c0)[-1]),
            ("sample-low", tb.sample_measure_names(c0)[0]),
            ("sample-high", tb.sample_measure_names(c0)[-1]),
        )
        for which, name in cases:
            for label, bad in _NON_FINITE:
                with self.subTest(measure=which, value=label):
                    parsed = dict(parsed0)
                    parsed[name] = bad
                    result = fc_common.decode(parsed, self.SUPPLY_V)
                    cv = result["conversions"][0]
                    self.assertIn(None, cv["busy"] + cv["sample"])
                    self.assertFalse(cv["phase_ok"])
                    self.assertEqual(result["n_phase_ok"], result["n_conversions"] - 1)
                    self.assertFalse(result["all_ok"])
                    self._assert_margin_is_finite_and_ideal(result)

    def test_non_finite_current_never_yields_a_complete_passing_result(self):
        parsed0 = _synthetic_parsed(_ideal_codes())
        for name, _src, potential in tb.SUPPLY_SOURCES:
            for label, bad in _NON_FINITE:
                with self.subTest(current=name, value=label):
                    parsed = dict(parsed0)
                    parsed[name] = bad
                    result = fc_common.decode(parsed, self.SUPPLY_V)
                    self.assertNotIn(name, result["currents"])
                    self.assertFalse(result["all_ok"])
                    if potential != 0.0:
                        self.assertIsNone(result["power_w"])
                    else:
                        # zero-potential convention: no power term either way
                        self.assertAlmostEqual(
                            result["power_w"],
                            fc_common.decode(parsed0, self.SUPPLY_V)["power_w"],
                            places=15,
                        )
                    for v in result["currents"].values():
                        self.assertTrue(math.isfinite(v))

    def test_missing_current_marks_power_unavailable_not_a_partial_sum(self):
        parsed = _synthetic_parsed(_ideal_codes())
        del parsed["i_vdd"]
        result = fc_common.decode(parsed, self.SUPPLY_V)
        self.assertIsNone(result["power_w"])
        self.assertNotIn("i_vdd", result["currents"])
        self.assertFalse(result["all_ok"])


def _as_log(parsed: dict[str, float], override: dict[str, str] | None = None) -> str:
    """Serialize a parsed dict back into ngspice-shaped `name = value` lines."""
    override = override or {}
    return "".join(
        f"{name} = {override.get(name, f'{v:.6e}')}\n" for name, v in parsed.items()
    )


class TestRunPointRejectsOverflow(unittest.TestCase):
    """run_point() end to end with ngspice and deck assembly mocked out."""

    def _run(self, log_text: str) -> dict:
        with mock.patch.object(fc_common, "assemble_deck", return_value="* deck\n"), \
                mock.patch.object(fc_common, "_run_ngspice", return_value=log_text):
            return fc_common.run_point("* netlist\n", None, Path("/nonexistent"), "tt", 27.0, 1.8)

    def test_finite_control_passes(self):
        point = self._run(_as_log(_synthetic_parsed(_ideal_codes())))
        self.assertEqual(point["missing"], [])
        self.assertTrue(point["all_ok"])
        self.assertIsNotNone(point["power_w"])

    def test_one_overflowed_token_is_missing_and_fails_the_point(self):
        parsed = _synthetic_parsed(_ideal_codes())
        c0 = tb.measured_conversions()[0]
        for name in (tb.code_measure_names(c0)[0], tb.busy_measure_names(c0)[0], "i_vdd"):
            for token in ("1e999", "-1e999"):
                with self.subTest(name=name, token=token):
                    point = self._run(_as_log(parsed, {name: token}))
                    self.assertEqual(point["missing"], [name])
                    self.assertFalse(point["all_ok"])
                    self.assertTrue(math.isfinite(point["worst_margin_v"]))


class TestRecordRendering(unittest.TestCase):
    """write_record() must emit every base field sim/report/generate.py
    re-extracts, or the characterization report degrades silently."""

    def _point(self, corner_id: str, process: str, temp: float, supply: float, offset: int):
        codes = {
            c: tb.ideal_code(tb.input_fraction(c)) + offset for c in tb.measured_conversions()
        }
        point = fc_common.decode(_synthetic_parsed(codes, supply), supply)
        point.update(
            process_corner=process, temp_c=temp, supply_v=supply, corner_id=corner_id,
            missing=[], log_text=f"* synthetic log for {corner_id}\n", wall_s=1.0,
        )
        return point

    def test_record_carries_every_field_the_report_generator_extracts(self):
        points = [
            self._point("tt_27c_1.80v", "tt", 27.0, 1.8, 0),
            self._point("ss_27c_1.80v", "ss", 27.0, 1.8, 3),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            with provenance_fixture.fake_provenance(fc_common, tmp_dir):
                path = fc_dc.write_record(points, "* synthetic netlist\n")

            text = path.read_text()
            for field in ("Record ID", "Claim", "Netlist provenance", "Corner matrix run",
                          "Binding corner", "Overall", "Measured value(s)", "Supersedes"):
                self.assertIsNotNone(
                    report_generate.extract_field(text, field),
                    f"record is missing the {field!r} field generate.py extracts",
                )
            # the failing (3-LSB-off) corner must be the binding one and the
            # overall verdict must be FAIL, not quietly averaged away
            self.assertIn("FAIL", report_generate.extract_field(text, "Overall"))
            self.assertIn("ss_27c_1.80v", report_generate.extract_field(text, "Binding corner"))
            self.assertTrue((tmp_dir / "corners" / "REC" / "ss_27c_1.80v.log").is_file())
            self.assertEqual((tmp_dir / "records" / "LATEST").read_text().strip(), "REC.md")

    def test_finite_power_renders_as_before(self):
        point = self._point("tt_27c_1.80v", "tt", 27.0, 1.8, 0)
        expected_uw = f"{point['power_w'] * 1e6:.3f}"
        line = fc_common.format_point(point)
        self.assertIn(f"P={expected_uw}uW", line)
        self.assertIn(f"IDD={1e6 * (2.0e-6 + 3.0e-6 + 2.5e-6):.3f}uA", line)

    def test_unavailable_power_renders_as_n_a_in_console_and_record(self):
        good = self._point("tt_27c_1.80v", "tt", 27.0, 1.8, 0)
        bad = self._point("ss_27c_1.80v", "ss", 27.0, 1.8, 0)
        # what decode() yields when a powered current is missing/non-finite
        del bad["currents"]["i_vdd"]
        bad["power_w"] = None
        bad["all_ok"] = False

        line = fc_common.format_point(bad)
        self.assertIn("P=n/auW", line)
        self.assertIn("IDD=n/auA", line)
        self.assertIn("FAIL", line)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            with provenance_fixture.fake_provenance(fc_common, tmp_dir):
                path = fc_dc.write_record([good, bad], "* synthetic netlist\n")

            text = path.read_text()
            bad_row = next(
                ln for ln in text.splitlines()
                if ln.startswith("| `ss_27c_1.80v` |") and ln.rstrip().endswith("n/a |")
            )
            # I(VDD) n/a and total power n/a -- no fabricated partial sum
            self.assertEqual(bad_row.count("n/a"), 2)
            good_row = next(
                ln for ln in text.splitlines()
                if ln.startswith("| `tt_27c_1.80v` |")
                and ln.rstrip().endswith(f"{good['power_w'] * 1e6:.3f} |")
            )
            self.assertNotIn("n/a", good_row)
            self.assertIn("`n/a` total power", text)
            self.assertIn("FAIL", report_generate.extract_field(text, "Overall"))


class TestNodeTracePlan(unittest.TestCase):
    """Pure, PDK-free coverage of run_conversion.py's issue #259 `--node-trace`
    helpers: the measurement plan and the `.meas` lines it emits."""

    def test_ten_phases_msb_first(self):
        plan = fc_common.node_trace_plan(2)
        self.assertEqual(len(plan), tb.N_BITS)
        self.assertEqual([e["phase"] for e in plan], list(range(tb.N_BITS)))
        self.assertEqual([e["bit"] for e in plan], list(range(tb.N_BITS - 1, -1, -1)))

    def test_measure_lines_cover_every_name_exactly_once(self):
        plan = fc_common.node_trace_plan(2)
        lines = fc_common.node_trace_measure_lines(plan)
        for name in fc_common._node_trace_names(plan):
            self.assertEqual(
                sum(1 for ln in lines if f".meas tran {name} " in ln),
                1,
                f"node-trace measurement {name!r} is not emitted exactly once",
            )

    def test_measurement_names_are_unique_across_traced_conversions(self):
        """Two conversions are probed in one deck, so their `.meas` names must
        not collide -- a collision would silently make one conversion's table
        report the other's samples."""
        names: list[str] = []
        for conversion in fc_node.NODE_TRACE_CONVERSIONS:
            names += fc_common._node_trace_names(fc_common.node_trace_plan(conversion))
        self.assertEqual(len(names), len(set(names)), "duplicate .meas name across conversions")

    def test_traced_conversions_are_an_opposite_sign_msb_pair(self):
        """The MSB-trial control is only discriminating if the traced
        conversions disagree on the ideal MSB -- otherwise a matching
        mid-evaluate level proves nothing about input dependence."""
        msbs = set()
        for conversion in fc_node.NODE_TRACE_CONVERSIONS:
            code = tb.ideal_code(tb.input_fraction(conversion))
            msbs.add((code >> (tb.N_BITS - 1)) & 1)
        self.assertEqual(msbs, {0, 1})

    def test_mid_and_pre_edge_times_land_inside_the_bit_trials_own_period(self):
        conversion = 2
        plan = fc_common.node_trace_plan(conversion)
        for entry in plan:
            k_start = tb.PHASES_PER_CONVERSION * conversion + entry["phase"]
            t_start = tb.t_edge_ns(k_start)
            t_end = tb.t_edge_ns(k_start + 1)
            self.assertLess(t_start, entry["t_mid"])
            self.assertLess(entry["t_mid"], t_end)
            self.assertLess(t_start, entry["t_pre"])
            self.assertLess(entry["t_pre"], t_end)
            # t_pre sits inside the comparator's CLK-low reset half (the
            # second half of the period), not the CLK-high evaluate half.
            self.assertGreater(entry["t_pre"], t_start + tb.T_CLK_NS * 0.5)
            # t_post is after the capturing edge that ends this phase.
            self.assertGreater(entry["t_post"], t_end)


def _synthetic_node_trace(corner_id, process, temp, supply, *, all_reset, msb_tracks=True):
    """Build a run_node_trace_point()-shaped dict without invoking ngspice.

    `all_reset=True` mirrors the as-committed finding (every bit trial's
    COMP_OUT already at VDD before its capturing edge); `all_reset=False`
    mimics a hypothetical fix where the pre-edge/post-edge values track the
    ideal per-bit decision instead. `msb_tracks=False` mimics a comparator
    whose evaluate-half output is stuck low regardless of input -- the case
    where the MSB-trial control must refuse to conclude."""
    threshold = 0.5 * supply

    def hi(v: float) -> str:
        return "1" if v > threshold else "0"

    conversions = []
    for conversion in fc_node.NODE_TRACE_CONVERSIONS:
        plan = fc_common.node_trace_plan(conversion)
        frac = tb.input_fraction(conversion)
        ideal_code = tb.ideal_code(frac)
        phases = []
        for entry in plan:
            ideal_bit = (ideal_code >> entry["bit"]) & 1
            captured_v = supply if (all_reset or ideal_bit) else 0.0
            # The MSB trial is the only one whose evaluate-half output is
            # expected to follow the input; later trials are corrupted.
            is_msb = entry["phase"] == 0
            mid_v = supply if (msb_tracks and is_msb and ideal_bit) else 0.0
            v = dict(
                clk_mid=supply, clk_pre=0.0,
                compout_mid=mid_v,
                compout_pre=captured_v, compoutn_mid=supply, compoutn_pre=supply,
                dout_post=captured_v,
            )
            phases.append(
                dict(
                    phase=entry["phase"], bit=entry["bit"], ideal_bit=ideal_bit, v=v,
                    clk_mid_hi=hi(v["clk_mid"]), clk_pre_hi=hi(v["clk_pre"]),
                    compout_mid_hi=hi(v["compout_mid"]), compout_pre_hi=hi(v["compout_pre"]),
                    compoutn_mid_hi=hi(v["compoutn_mid"]), compoutn_pre_hi=hi(v["compoutn_pre"]),
                    dout_post_hi=hi(v["dout_post"]),
                )
            )
        conversions.append(
            dict(conversion=conversion, fraction=frac, ideal_code=ideal_code, phases=phases)
        )

    return dict(
        corner_id=corner_id, process_corner=process, temp_c=temp, supply_v=supply,
        conversions=conversions, missing=[],
        log_text=f"* synthetic log for {corner_id}\n", wall_s=1.0,
    )


class TestMsbEvaluateControl(unittest.TestCase):
    """The MSB-trial control separates 'the decision is made and then
    destroyed before capture' from 'no decision is ever made' -- issue #259.
    It must only report `tracks_input` when the traced conversions actually
    disagree on the ideal MSB AND every one of them matches."""

    def test_tracks_input_when_msb_follows_the_sign_of_each_input(self):
        point = _synthetic_node_trace("tt_27c_1.62v", "tt", 27.0, 1.62, all_reset=True)
        control = fc_node.msb_evaluate_control(point)
        self.assertTrue(control["discriminating"])
        self.assertTrue(control["tracks_input"])

    def test_does_not_track_input_when_the_comparator_is_stuck(self):
        point = _synthetic_node_trace(
            "tt_27c_1.62v", "tt", 27.0, 1.62, all_reset=True, msb_tracks=False
        )
        control = fc_node.msb_evaluate_control(point)
        self.assertFalse(control["tracks_input"])


class TestStripBalanceDummies(unittest.TestCase):
    """`_strip_balance_dummies()` builds `--decision-margin-trace`'s
    `unbalanced-control` half by deleting DR-009's two comparator-output
    balancing dummies from the DUT netlist, and refuses if it does not find
    exactly that many -- the anchor is the shape of design/sar_adc_top.spice,
    which is regenerated from schematics, so a stale anchor must fail here at
    the commit that moves the netlist rather than at a later hand run
    (issue #879; the same gap that let #873's probe sit broken).

    The control half is half the measurement: if it refuses, the mode
    produces nothing, so both directions are pinned on a small synthetic
    netlist. `test_todays_committed_netlist_still_matches_this_anchor` is
    the half that reads design/ -- the synthetic cases pin the guard's
    match/refuse logic, that one pins the anchor against the committed
    netlist, and only the pair makes the sentence above true.

    Not asserted of the guard, deliberately: it counts matching *lines*, not
    distinct prefixes, so two `xdum_mux_n` lines and no `xdum_xnor_n` are
    accepted. That is current behaviour, out of scope to change under
    issue #879, and left unpinned in either direction so a later fix does
    not have to fight a test. The committed-netlist test below does assert
    one line per prefix, but that is a statement about
    design/sar_adc_top.spice rather than about the guard: a stricter guard
    would still pass it.
    """

    def test_removes_both_dummies_and_keeps_every_other_line_in_order(self):
        text = (
            "* top\n"
            "xdum_mux_n a b c mux\n"
            "xkeep a b inv\n"
            # not a dummy: the prefixes include their trailing space, so a
            # longer instance name starting with one of them is kept.
            "xdum_mux_nx d e f mux\n"
            "xdum_xnor_n a b xnor\n"
            ".end\n"
        )
        self.assertEqual(
            fc_dm._strip_balance_dummies(text),
            "* top\nxkeep a b inv\nxdum_mux_nx d e f mux\n.end\n",
        )

    def test_refuses_a_netlist_with_no_balancing_dummies(self):
        with self.assertRaises(RuntimeError):
            fc_dm._strip_balance_dummies("* top\nxkeep a b inv\n.end\n")

    def test_refuses_a_netlist_with_only_one_balancing_dummy(self):
        with self.assertRaises(RuntimeError):
            fc_dm._strip_balance_dummies("* top\nxdum_mux_n a b c mux\n.end\n")

    def test_refuses_a_netlist_with_three_balancing_dummies(self):
        with self.assertRaises(RuntimeError):
            fc_dm._strip_balance_dummies(
                "* top\n"
                "xdum_mux_n a b c mux\n"
                "xdum_xnor_n a b xnor\n"
                "xdum_mux_n g h i mux\n"
                ".end\n"
            )

    def test_todays_committed_netlist_still_matches_this_anchor(self):
        """The committed-netlist counterpart of the synthetic cases above,
        mirroring what guard 2 already has in
        test_sequencer_port_map_comes_from_the_netlist: the cases above run
        the guard on inline literals, so only this one fails when a
        schematic regeneration renames or drops a balancing dummy.
        """
        text = fc_common.dut_text()
        # Raises RuntimeError unless design/sar_adc_top.spice still carries
        # exactly len(_BALANCE_DUMMY_PREFIXES) matching instance lines.
        stripped = fc_dm._strip_balance_dummies(text)
        self.assertEqual(
            len(text.splitlines()) - len(stripped.splitlines()),
            len(fc_dm._BALANCE_DUMMY_PREFIXES),
        )
        # One line per prefix. The guard itself counts matching lines, not
        # distinct prefixes (see the class docstring), so without this a
        # rename of one dummy could be masked by a second copy of the other.
        for prefix in fc_dm._BALANCE_DUMMY_PREFIXES:
            self.assertEqual(
                len([ln for ln in text.splitlines() if ln.startswith(prefix)]),
                1,
                f"expected exactly one '{prefix.strip()}' instance line",
            )


class TestWriteNodeTraceRecord(unittest.TestCase):
    """write_node_trace_record() must render the mechanism finding
    correctly from decoded per-phase data and never touch records/LATEST
    (that file names the corner-campaign record, not a targeted diagnostic
    like this one) -- issue #259."""

    def _write(self, traces: dict) -> tuple[Path, Path]:
        # mkdtemp(), not TemporaryDirectory() -- the caller reads the
        # returned path's contents AFTER this helper returns, so the
        # directory must outlive this method (a `with` block here would
        # delete it on return, before the caller ever reads the file).
        tmp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        with provenance_fixture.fake_provenance(fc_common, tmp_dir):
            path = fc_node.write_node_trace_record(traces, "* synthetic netlist\n")
        return path, tmp_dir

    def test_uniform_all_ones_capture_is_reported_as_uniform(self):
        traces = {
            "tt_27c_1.62v": _synthetic_node_trace("tt_27c_1.62v", "tt", 27.0, 1.62, all_reset=True),
            "ff_27c_1.80v": _synthetic_node_trace("ff_27c_1.80v", "ff", 27.0, 1.80, all_reset=True),
        }
        path, tmp_dir = self._write(traces)
        text = path.read_text()
        self.assertIn("**Uniform.**", text)
        self.assertIn("comparator core is alive and input-dependent", text)
        # Both traced conversions must appear as their own table.
        for conversion in fc_node.NODE_TRACE_CONVERSIONS:
            self.assertIn(f"### Conversion {conversion} ", text)
        self.assertFalse((tmp_dir / "records" / "LATEST").exists())
        for corner_id in traces:
            self.assertTrue(
                (tmp_dir / "diagnostics" / "REC" / f"node-trace-{corner_id}.log").is_file()
            )

    def test_a_mix_of_correct_and_stuck_bits_is_reported_as_not_uniform(self):
        traces = {
            "tt_27c_1.62v": _synthetic_node_trace("tt_27c_1.62v", "tt", 27.0, 1.62, all_reset=False),
            "ff_27c_1.80v": _synthetic_node_trace("ff_27c_1.80v", "ff", 27.0, 1.80, all_reset=False),
        }
        path, _tmp_dir = self._write(traces)
        text = path.read_text()
        self.assertIn("NOT uniform", text)

    def test_a_stuck_comparator_refuses_to_conclude_the_core_is_alive(self):
        """If the MSB control does not discriminate, the record must say so
        rather than asserting the capture-edge finding is sufficient."""
        traces = {
            "tt_27c_1.62v": _synthetic_node_trace(
                "tt_27c_1.62v", "tt", 27.0, 1.62, all_reset=True, msb_tracks=False
            ),
            "ff_27c_1.80v": _synthetic_node_trace(
                "ff_27c_1.80v", "ff", 27.0, 1.80, all_reset=True, msb_tracks=False
            ),
        }
        path, _tmp_dir = self._write(traces)
        text = path.read_text()
        self.assertIn("Inconclusive", text)
        self.assertNotIn("comparator core is alive and input-dependent", text)

    def test_no_design_fix_is_proposed_and_no_spec_row_is_claimed(self):
        traces = {
            "tt_27c_1.62v": _synthetic_node_trace("tt_27c_1.62v", "tt", 27.0, 1.62, all_reset=True),
        }
        path, _tmp_dir = self._write(traces)
        text = path.read_text()
        self.assertIn("No design fix is proposed or implemented", text)
        self.assertIn("diagnostic/investigation only", text)


class TestNodeTracePlanCommonModeProbes(unittest.TestCase):
    """issue #265: node_trace_plan()/node_trace_measure_lines() must also
    probe TOP_P/TOP_N (the comparator's own VINP/VINN), the node-level test
    for DR-008's common-mode-headroom hypothesis."""

    def test_plan_names_include_top_plate_probes(self):
        plan = fc_common.node_trace_plan(1)
        for entry in plan:
            for key in ("top_p_mid", "top_n_mid", "top_p_pre", "top_n_pre"):
                self.assertIn(key, entry["names"])

    def test_measure_lines_probe_top_p_and_top_n_nodes(self):
        plan = fc_common.node_trace_plan(5)
        lines = fc_common.node_trace_measure_lines(plan)
        top_p_lines = [ln for ln in lines if "find v(TOP_P)" in ln]
        top_n_lines = [ln for ln in lines if "find v(TOP_N)" in ln]
        # Two probes (mid, pre) per bit trial, ten bit trials.
        self.assertEqual(len(top_p_lines), 2 * tb.N_BITS)
        self.assertEqual(len(top_n_lines), 2 * tb.N_BITS)


def _synthetic_cm_trace(corner_id, process, temp, supply, *, droop_from_phase):
    """Build a run_node_trace_point()-shaped dict (with the TOP_P/TOP_N
    fields write_cm_trace_record() reads) without invoking ngspice. Before
    `droop_from_phase`, TOP_P/TOP_N straddle VCM symmetrically (a healthy
    common mode) and the captured bit matches the ideal bit; from
    `droop_from_phase` onward, the active side is parked near GND (mimicking
    the measured mechanism) and every later bit is captured as 1 regardless
    of its ideal value (mimicking the observed all-ones saturation)."""
    vcm = 0.5 * supply
    threshold = vcm

    def hi(v: float) -> str:
        return "1" if v > threshold else "0"

    conversions = []
    for conversion in fc_cm.CM_TRACE_CONVERSIONS:
        plan = fc_common.node_trace_plan(conversion)
        frac = tb.input_fraction(conversion)
        ideal_code = tb.ideal_code(frac)
        sign_hi = frac > 0
        phases = []
        for entry in plan:
            ideal_bit = (ideal_code >> entry["bit"]) & 1
            if entry["phase"] < droop_from_phase:
                top_p = vcm + (0.3 * supply if sign_hi else -0.3 * supply)
                top_n = vcm - (0.3 * supply if sign_hi else -0.3 * supply)
                captured_v = supply if ideal_bit else 0.0
            else:
                # active side parked near GND; common mode droops far below
                # VCM regardless of which side is "active".
                top_p = 0.05 * supply
                top_n = 0.08 * supply
                captured_v = supply  # saturates to 1 from here on
            v = dict(
                clk_mid=supply, clk_pre=0.0,
                compout_mid=supply, compout_pre=captured_v,
                compoutn_mid=supply, compoutn_pre=supply,
                dout_post=captured_v,
                top_p_mid=top_p, top_n_mid=top_n,
                top_p_pre=top_p, top_n_pre=top_n,
            )
            phases.append(
                dict(
                    phase=entry["phase"], bit=entry["bit"], ideal_bit=ideal_bit, v=v,
                    clk_mid_hi=hi(v["clk_mid"]), clk_pre_hi=hi(v["clk_pre"]),
                    compout_mid_hi=hi(v["compout_mid"]), compout_pre_hi=hi(v["compout_pre"]),
                    compoutn_mid_hi=hi(v["compoutn_mid"]), compoutn_pre_hi=hi(v["compoutn_pre"]),
                    dout_post_hi=hi(v["dout_post"]),
                )
            )
        conversions.append(
            dict(conversion=conversion, fraction=frac, ideal_code=ideal_code, phases=phases)
        )

    return dict(
        corner_id=corner_id, process_corner=process, temp_c=temp, supply_v=supply,
        conversions=conversions, missing=[],
        log_text=f"* synthetic log for {corner_id}\n", wall_s=1.0,
    )


class TestWriteCmTraceRecord(unittest.TestCase):
    """write_cm_trace_record() (issue #265) must render the confirmed
    common-mode-headroom mechanism from decoded per-phase TOP_P/TOP_N data,
    identify the first mismatching bit trial, and never touch
    records/LATEST (a targeted diagnostic, not the corner-campaign record)."""

    def _write(self, traces: dict) -> tuple[Path, Path]:
        tmp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        with provenance_fixture.fake_provenance(fc_common, tmp_dir):
            path = fc_cm.write_cm_trace_record(traces, "* synthetic netlist\n")
        return path, tmp_dir

    def test_confirmed_finding_and_first_mismatch_are_reported(self):
        traces = {
            "tt_27c_1.62v": _synthetic_cm_trace(
                "tt_27c_1.62v", "tt", 27.0, 1.62, droop_from_phase=3
            ),
            "ff_27c_1.80v": _synthetic_cm_trace(
                "ff_27c_1.80v", "ff", 27.0, 1.80, droop_from_phase=3
            ),
        }
        path, tmp_dir = self._write(traces)
        text = path.read_text()
        self.assertIn("## Finding: CONFIRMED", text)
        self.assertIn("First mismatch", text)
        self.assertFalse((tmp_dir / "records" / "LATEST").exists())
        for corner_id in traces:
            self.assertTrue(
                (tmp_dir / "diagnostics" / "REC" / f"cm-trace-{corner_id}.log").is_file()
            )

    def test_no_design_fix_is_proposed_in_this_record(self):
        traces = {
            "tt_27c_1.62v": _synthetic_cm_trace(
                "tt_27c_1.62v", "tt", 27.0, 1.62, droop_from_phase=3
            ),
        }
        path, _tmp_dir = self._write(traces)
        text = path.read_text()
        self.assertIn(
            "This record confirms the mechanism; it does not fix it", text
        )


class TestGainOffsetFit(unittest.TestCase):
    """Issue #757: PDK-free arithmetic for the gain / corrected-code columns."""

    IDEAL = [113, 384, 512, 640, 911]

    def _codes(self, g, off):
        return [round(g * x + off) for x in self.IDEAL]

    def test_recovers_known_gain_and_offset(self):
        pairs = list(zip(self.IDEAL,
                         [int(round(0.99 * x - 3.0)) for x in self.IDEAL]))
        fit = fc_common.fit_gain_offset(pairs)
        self.assertAlmostEqual(fit["g"], 0.99, places=2)
        self.assertAlmostEqual(fit["offset"], -3.0, delta=1.0)
        self.assertAlmostEqual(fit["eps_lsb"], 0.01 * 1024, delta=4.0)
        self.assertEqual(fit["n_used"], 5)

    def test_saturated_and_missing_codes_are_excluded(self):
        pairs = [(113, 112), (384, 383), (512, 511), (640, 639), (911, 1023)]
        fit = fc_common.fit_gain_offset(pairs)
        self.assertEqual(fit["n_used"], 4)
        self.assertAlmostEqual(fit["g"], 1.0, places=3)
        pairs[0] = (113, None)
        self.assertEqual(fc_common.fit_gain_offset(pairs)["n_used"], 3)

    def test_too_few_points_returns_none(self):
        self.assertIsNone(fc_common.fit_gain_offset([(512, 511), (640, 1023)]))
        self.assertIsNone(fc_common.fit_gain_offset([(512, None), (640, 0)]))

    def test_corrected_codes_are_exact_for_exact_line(self):
        g, off = 0.992, -2.5
        pairs = [(x, g * x + off) for x in self.IDEAL]
        errs = fc_common.corrected_code_errors(pairs, g, off)
        for e in errs:
            self.assertAlmostEqual(e, 0.0, places=9)
        self.assertEqual(fc_common.corrected_code_errors([(512, None)], g, off), [None])

    def test_resolution_bound_scales_with_span(self):
        wide = fc_common.fit_gain_offset([(113, 112), (512, 511), (911, 910)])
        narrow = fc_common.fit_gain_offset([(384, 383), (512, 511), (640, 639)])
        self.assertAlmostEqual(wide["resolution_lsb"], 2 * 1024 / 798)
        self.assertAlmostEqual(narrow["resolution_lsb"], 2 * 1024 / 256)

    def test_point_analysis_midscale_subset_ignores_outer_inputs(self):
        codes = {-0.78: 214, -0.25: 383, 0.0: 511, 0.25: 641, 0.78: 1023}
        point = dict(conversions=[
            dict(fraction=f, ideal_code=tb.ideal_code(f), code=c)
            for f, c in codes.items()
        ])
        an = fc_common.point_gain_analysis(point)
        self.assertEqual(an["mid"]["n_used"], 3)
        self.assertEqual(an["all"]["n_used"], 4)
        self.assertGreater(an["mid"]["g"], 1.0)  # (641-383)/(640-384)

    def test_gain_section_states_method_limits_and_rc_gap(self):
        codes = {-0.78: 214, -0.25: 383, 0.0: 511, 0.25: 641, 0.78: 1023}
        point = dict(corner_id="tt_27c_1.80v", conversions=[
            dict(fraction=f, ideal_code=tb.ideal_code(f), code=c)
            for f, c in codes.items()
        ])
        text = "\n".join(fc_common.gain_record_lines([point]))
        self.assertIn("not** DR-022's bit-8-pair", text)
        self.assertIn("res_typical__cap_typical", text)
        self.assertIn("0.99200", text)
        self.assertIn("not in this run", text)  # tt_27c_1.62v absent


# ==========================================================================
# The converging-range input sweep (issue #913, full_conversion_campaigns/
# input_sweep.py) -- PDK-free and fleet-free, on the same convention as
# test_reference_drive_budget.py: deck assembly against the real committed
# fragment, the request shape, report reading, the boundary arithmetic, and
# the record writers under the provenance fixture.
# ==========================================================================
from full_conversion_campaigns import input_sweep as fc_sweep  # noqa: E402


class TestInputSweepFragmentIsFresh(unittest.TestCase):
    """The committed sweep fragment is what the driver runs, byte for byte,
    and it is a parameterized deck, not a per-level literal schedule."""

    def test_committed_fragment_matches_fresh_generation(self):
        self.assertEqual(
            tb.SWEEP_FRAGMENT_PATH.read_text(),
            tb.sweep_fragment_text(),
            "testbench/input_sweep_tb_fragment.spice is stale -- regenerate "
            "with `python3 sim/full-conversion-transient/gen_full_conversion_tb.py --write`",
        )

    def test_generator_registers_all_three_committed_fragments(self):
        paths = [p for p, _text in tb._committed_fragments()]
        self.assertIn(tb.SWEEP_FRAGMENT_PATH, paths)
        self.assertIn(tb.FRAGMENT_PATH, paths)
        self.assertIn(tb.SINE_FRAGMENT_PATH, paths)

    def test_meas_names_are_exactly_the_sweep_set(self):
        text = tb.SWEEP_FRAGMENT_PATH.read_text()
        found = sorted(
            ln.strip().split()[2] for ln in text.splitlines()
            if ln.strip().lower().startswith(".meas")
        )
        self.assertEqual(found, sorted(tb.sweep_measure_names()))

    def test_input_is_a_dc_card_on_the_param_never_a_literal_schedule(self):
        text = tb.SWEEP_FRAGMENT_PATH.read_text()
        self.assertIn(f"VINP VINP 0 DC {{vdd_val*(0.5+{tb.SWEEP_INPUT_PARAM}/2)}}", text)
        self.assertIn(f"VINN VINN 0 DC {{vdd_val*(0.5-{tb.SWEEP_INPUT_PARAM}/2)}}", text)
        # No PWL input schedule and no per-conversion input literal: the
        # level lives in the `corners.params` axis, not in these bytes.
        self.assertNotIn("VINP VINP 0 PWL(", text)
        self.assertNotIn("{{vdd_val*0.11}}", text)

    def test_one_tran_card_and_the_span_covers_every_probe(self):
        text = tb.SWEEP_FRAGMENT_PATH.read_text()
        trans = [ln for ln in text.splitlines() if ln.strip().lower().startswith(".tran")]
        self.assertEqual(len(trans), 1)
        stop = float(trans[0].split()[2].rstrip("n"))
        for c in tb.sweep_conversions():
            self.assertLess(tb.t_phase_mid_ns(c, tb.PHASES_PER_CONVERSION - 1), stop)
        self.assertLess(tb.t_code_read_ns(1), stop)

    def test_two_conversions_only_startup_discarded(self):
        self.assertEqual(tb.sweep_conversions(), [0, 1])
        self.assertEqual(tb.sweep_measured_conversions(), [1])


class TestInputSweepLevels(unittest.TestCase):
    def test_default_list_is_both_signs_of_the_band(self):
        levels = list(fc_sweep.DEFAULT_INPUT_FRACTIONS)
        self.assertEqual(len(levels), 24)
        self.assertEqual(levels, sorted(levels))
        negatives = [f for f in levels if f < 0]
        positives = [f for f in levels if f > 0]
        self.assertEqual([-f for f in negatives], sorted(positives, reverse=True))
        self.assertEqual(positives, sorted(positives))
        for level in levels:
            self.assertTrue(0.25 <= abs(level) <= 0.78, level)

    def test_default_magnitudes_step_by_the_named_step_and_carry_the_endpoints(self):
        mags = fc_sweep.SWEEP_MAGNITUDES
        self.assertEqual(mags[0], 0.25)
        self.assertEqual(mags[-1], 0.78)
        rungs = [round(0.25 + fc_sweep.INPUT_SWEEP_STEP_F * k, 10) for k in range(11)]
        self.assertEqual(list(mags[:-1]), rungs)
        self.assertEqual(fc_sweep.INPUT_SWEEP_STEP_F, 0.05)

    def test_parse_sorts_and_dedupes(self):
        self.assertEqual(
            fc_sweep.parse_input_levels("0.78, -0.25 0.78 0.30"),
            [-0.25, 0.3, 0.78],
        )

    def test_parse_refuses_malformed_tokens(self):
        with self.assertRaises(ValueError):
            fc_sweep.parse_input_levels("0.25, zero")
        with self.assertRaises(ValueError):
            fc_sweep.parse_input_levels("   ")

    def test_out_of_band_levels_refused(self):
        for bad in ("0.0", "0.1", "0.20", "0.79", "1.0", "-0.9"):
            with self.assertRaises(ValueError, msg=bad):
                fc_sweep.parse_input_levels(bad)

    def test_recorded_sweep_must_carry_both_anchors_at_both_signs(self):
        fc_sweep.check_input_levels(fc_sweep.DEFAULT_INPUT_FRACTIONS)  # ok
        with self.assertRaises(ValueError):
            fc_sweep.check_input_levels([-0.78, -0.25, 0.25])          # no +0.78
        with self.assertRaises(ValueError):
            fc_sweep.check_input_levels([0.25, 0.78])                  # no negative sign

    def test_shard_count_never_zero_and_fits_the_ceiling(self):
        self.assertEqual(fc_sweep.shard_count(1), 1)
        for n in (4, 24, 100):
            hosts = fc_sweep.shard_count(n)
            largest = -(-n // hosts)
            self.assertLessEqual(
                largest * fc_sweep.SHARD_SERIAL_BUDGET_S + fc_sweep.FLEET_JOB_OVERHEAD_S,
                fc_sweep.FLEET_JOB_CEILING_S, n)


class TestInputSweepBody(unittest.TestCase):
    def setUp(self):
        self.fragment = tb.SWEEP_FRAGMENT_PATH.read_text()
        self.body = fc_sweep.build_body(fc_sweep.DUT_NETLIST.read_text(), self.fragment)

    def test_is_a_circuit_body_not_a_deck(self):
        cards = [ln.strip().lower().split()[0] for ln in self.body.splitlines()
                 if ln.strip().startswith(".")]
        for forbidden in (".lib", ".temp", ".end", ".control", ".endc", ".meas", ".tran"):
            self.assertNotIn(forbidden, cards)
        self.assertIn(".ends", cards)

    def test_declares_the_supply_and_the_swept_level_at_top_level(self):
        decls = [ln.strip() for ln in self.body.splitlines()
                 if ln.strip().lower().startswith(".param")]
        self.assertEqual(
            sorted(d.split()[1].lower() for d in decls),
            sorted([fc_sweep.INPUT_SWEEP_PARAM, fc_sweep.VDD_PARAM]),
        )

    def test_carries_the_reference_solver_policy_card(self):
        self.assertIn(
            fc_common.solver_options_card(fc_sweep.SOLVER_PROFILE), self.body)
        self.assertEqual(fc_sweep.SOLVER_PROFILE, fc_common.REFERENCE_SOLVER_PROFILE)

    def test_includes_the_dut_the_stdcell_library_and_the_global_tie(self):
        self.assertIn("xfe VINP VINN SAMPLE_INT ", self.body)
        self.assertIn(f".include {fc_sweep.STDCELL_INCLUDE}", self.body)
        self.assertIn(".global VPWR VGND", self.body)

    def test_dut_netlist_is_otherwise_verbatim(self):
        dut_lines = [ln for ln in fc_sweep.DUT_NETLIST.read_text().splitlines()
                     if ln.strip().lower() != ".end"]
        body_lines = self.body.splitlines()
        start = body_lines.index(dut_lines[0])
        self.assertEqual(body_lines[start:start + len(dut_lines)], dut_lines)

    def test_changed_fragment_shape_refused(self):
        with self.assertRaises(RuntimeError):
            fc_sweep.split_fragment("* no meas cards here\n")
        with self.assertRaises(RuntimeError):
            fc_sweep.split_fragment(self.fragment + ".tran 1n 2n\n")
        dropped = "\n".join(
            ln for ln in self.fragment.splitlines()
            if not ln.strip().lower().startswith(".meas tran d9_c1 ")
        )
        with self.assertRaises(RuntimeError):
            fc_sweep.split_fragment(dropped)


class TestInputSweepRequest(unittest.TestCase):
    def setUp(self):
        _body, self.meas, self.tran = fc_sweep.split_fragment(
            tb.SWEEP_FRAGMENT_PATH.read_text())
        self.levels = list(fc_sweep.DEFAULT_INPUT_FRACTIONS)
        self.req = fc_sweep.build_request(
            "tb.spice", self.levels, self.meas, self.tran,
            capacity_wait_s=None)

    def test_one_unit_per_level_as_the_only_params_axis(self):
        c = self.req["corners"]
        self.assertEqual(c["process"], ["tt"])
        self.assertEqual(c["temperature_c"], [27.0])
        self.assertEqual(c["params"][fc_sweep.INPUT_SWEEP_PARAM], self.levels)
        self.assertNotIn("supply_v", c)
        self.assertNotIn("exclude", self.req)

    def test_supply_is_not_an_axis_the_body_pins_it(self):
        self.assertNotIn(fc_sweep.VDD_PARAM, self.req["corners"]["params"])

    def test_measurements_are_the_committed_meas_cards(self):
        entries = self.req["measurements"]
        self.assertEqual(sorted(e["name"] for e in entries),
                         sorted(tb.sweep_measure_names()))
        for entry in entries:
            self.assertTrue(entry["spice"].lower().startswith(".meas tran "))
            self.assertEqual(entry["spice"].split()[2], entry["name"])

    def test_saved_vectors_cover_every_measured_signal_and_no_current(self):
        saved = set(self.req["options"]["save_vectors"])
        self.assertIn("v(dout9)", saved)
        self.assertIn("v(busy)", saved)
        self.assertIn("v(sample_int)", saved)
        for b in range(9):
            self.assertIn(f"v(adcout{b})", saved)
        # The sweep measures no supply current, so none is saved.
        self.assertFalse([v for v in saved if v.startswith("i(")])

    def test_analysis_is_the_committed_tran_card(self):
        self.assertEqual(self.req["analysis"], {"kind": "tran", "args": self.tran})

    def test_options_carry_the_unit_kill_and_artifacts(self):
        self.assertEqual(self.req["options"]["timeout_s"], fc_sweep.DEFAULT_TIMEOUT_S)
        self.assertTrue(self.req["options"]["keep_artifacts"])

    def test_backend_hosts_and_capacity_wait_reach_the_request(self):
        req = fc_sweep.build_request(
            "tb.spice", self.levels, self.meas, self.tran,
            backend="batch", capacity_wait_s=600.0, hosts=5)
        self.assertEqual(req["backend"], "batch")
        self.assertEqual(req["remote"]["hosts"], 5)
        self.assertEqual(req["batch"]["capacity_wait_s"], 600.0)
        req = fc_sweep.build_request("tb.spice", self.levels, self.meas, self.tran, hosts=1)
        self.assertNotIn("remote", req)
        self.assertNotIn("batch", req)


def _sweep_values(code: int, supply_v: float = 1.8) -> dict:
    """`.meas` values standing in for one sweep unit: conversion 1 decodes
    to `code`, both conversions carry a correct 12-period phase structure."""
    hi, lo = supply_v, 0.0
    out = {}
    bits = format(code, f"0{tb.N_BITS}b")
    for name, bit in zip(tb.code_measure_names(1), bits, strict=True):
        out[name] = hi if bit == "1" else lo
    for conv in tb.sweep_conversions():
        for i, name in enumerate(tb.busy_measure_names(conv)):
            out[name] = lo if i == tb.PHASES_PER_CONVERSION - 1 else hi
        for i, name in enumerate(tb.sample_measure_names(conv)):
            out[name] = hi if i == tb.PHASES_PER_CONVERSION - 1 else lo
    return out


def _corner(frac: float, code: int, status: str = "pass") -> dict:
    return {
        "process": "tt",
        "temperature_c": 27.0,
        "params": {fc_sweep.INPUT_SWEEP_PARAM: frac},
        "status": status,
        "measurements": [{"name": k, "value": v} for k, v in _sweep_values(code).items()],
        "diagnostics": [],
    }


def _report(corners: list[dict], job: str = "klt-sim-abc") -> dict:
    return {
        "status": "pass",
        "corners": corners,
        "environment": {"remote": {
            "job_id": job,
            "state": "done", "exit_code": "0",
            "instance_type": "c7i.8xlarge", "elapsed_seconds": 61,
            "runner_klt_version": "0.9.0", "client_klt_version": "0.9.2",
            "runner_compatibility": "match",
            "runner_request_features": {"status": "supported"},
            "worker_environment": {
                "pdk": {"variant": "sky130A",
                        "stamp_text": "open_pdks f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7"},
                "simulator": {"version_banner": "** ngspice-47 : Circuit"},
            },
        }},
    }


class TestInputSweepReadReport(unittest.TestCase):
    def test_keys_by_level_and_threads_run_info(self):
        units, info = fc_sweep.read_report(_report([_corner(0.25, 640)]))
        self.assertEqual(list(units), [0.25])
        self.assertEqual(info["job_id"], "klt-sim-abc")
        self.assertEqual(info["worker_ngspice"], "ngspice-47")

    def test_error_envelope_refused(self):
        with self.assertRaises(ValueError):
            fc_sweep.read_report({"error": {"code": "batch_no_capacity"}})

    def test_report_without_corners_refused(self):
        with self.assertRaises(ValueError):
            fc_sweep.read_report({"status": "pass"})

    def test_worker_that_ignored_the_param_refused(self):
        report = {"corners": [{"process": "tt", "temperature_c": 27.0,
                               "status": "pass", "measurements": []}]}
        with self.assertRaises(ValueError):
            fc_sweep.read_report(report)

    def test_duplicate_level_refused(self):
        with self.assertRaises(ValueError):
            fc_sweep.read_report(_report([_corner(0.25, 640), _corner(0.25, 641)]))

    def test_error_status_makes_a_unit_unusable(self):
        units, _ = fc_sweep.read_report(_report([_corner(0.25, 640, status="error")]))
        self.assertFalse(units[0.25].usable)


class TestInputSweepDecodeAndBoundary(unittest.TestCase):
    def test_decode_maps_code_ideal_error_and_phase(self):
        units, _ = fc_sweep.read_report(_report([
            _corner(-0.25, 384),   # ideal -0.25 -> 384, exact
            _corner(0.30, 667),    # ideal 666, +1 LSB
        ]))
        rows = fc_sweep.decode_units(units)
        self.assertEqual(rows[-0.25]["code"], 384)
        self.assertEqual(rows[-0.25]["ideal_code"], 384)
        self.assertEqual(rows[-0.25]["error_lsb"], 0)
        self.assertTrue(rows[-0.25]["within_tolerance"])
        self.assertEqual(rows[0.30]["code"], 667)
        self.assertEqual(rows[0.30]["ideal_code"], 666)
        self.assertEqual(rows[0.30]["error_lsb"], 1)
        self.assertTrue(rows[0.30]["within_tolerance"])
        self.assertTrue(all(r["phase_ok"] and r["startup_phase_ok"] for r in rows.values()))

    def test_boundary_picks_largest_converging_and_smallest_failing_per_sign(self):
        # -0.78 -> 0 (a real converter failure maps the input to a rail);
        # the positive side converges through 0.75 and fails at 0.78.
        rows = fc_sweep.decode_units(fc_sweep.read_report(_report([
            _corner(-0.78, 0),
            _corner(-0.25, 384),
            _corner(0.25, 641),
            _corner(0.75, 897),    # ideal 896, +1 LSB
            _corner(0.78, 1023),   # ideal 911, 112 LSB
        ]))[0])
        bounds = fc_sweep.boundary(rows)
        self.assertEqual(bounds["positive"]["largest_converging_f"], 0.75)
        self.assertEqual(bounds["positive"]["smallest_failing_f"], 0.78)
        self.assertTrue(bounds["positive"]["bracketed"])
        self.assertEqual(bounds["negative"]["largest_converging_f"], 0.25)
        self.assertEqual(bounds["negative"]["smallest_failing_f"], 0.78)
        # Only 0.25 and 0.78 were tested on the negative side, so the gap
        # (0.53*V_REF) exceeds the sweep's own step: bounded, not bracketed.
        self.assertFalse(bounds["negative"]["bracketed"])

    def test_an_incomplete_unit_states_nothing_about_the_boundary(self):
        rows = {
            0.25: dict(_sweep_row(0.25, 640), complete=False, code=None,
                       error_lsb=None, within_tolerance=False),
            0.78: _sweep_row(0.78, 1023),
        }
        bounds = fc_sweep.boundary(rows)
        self.assertIsNone(bounds["positive"]["largest_converging_f"])
        self.assertEqual(bounds["positive"]["smallest_failing_f"], 0.78)
        self.assertEqual(bounds["positive"]["unreadable_f"], [0.25])
        self.assertFalse(bounds["positive"]["bracketed"])

    def test_every_tested_level_failing_yields_no_converging_edge(self):
        rows = {0.25: _sweep_row(0.25, 100), 0.78: _sweep_row(0.78, 1023)}
        bounds = fc_sweep.boundary(rows)
        self.assertIsNone(bounds["positive"]["largest_converging_f"])
        self.assertEqual(bounds["positive"]["smallest_failing_f"], 0.25)


def _sweep_row(frac: float, code: int) -> dict:
    ideal = tb.ideal_code(frac)
    error = code - ideal
    return {
        "fraction": frac, "status": "pass", "errors": [],
        "code": code, "ideal_code": ideal, "error_lsb": error,
        "within_tolerance": abs(error) <= fc_sweep.BOUNDARY_TOLERANCE_LSB,
        "phase_ok": True, "startup_phase_ok": True, "complete": True,
    }


class TestInputSweepSubmitPath(unittest.TestCase):
    """The whole path on an injectable runner: submit() builds the deck and
    the ONE request, passes the shared capacity flag, decodes the report,
    and both record writers mint append-only evidence without touching
    records/LATEST."""

    LEVELS = [-0.78, -0.25, 0.25, 0.78]
    CODES = {-0.78: 0, -0.25: 384, 0.25: 641, 0.78: 1023}

    @staticmethod
    def _fake_runner(report_text: str):
        calls = []

        def runner(argv):
            calls.append(argv)
            return 0, report_text, ""

        return runner, calls

    def _canned_report(self) -> str:
        corners = [_corner(f, self.CODES[f]) for f in self.LEVELS]
        return json.dumps(_report(corners, job="klt-sim-deadbeef"))

    def test_submit_builds_one_request_and_passes_the_capacity_flag(self):
        runner, calls = self._fake_runner(self._canned_report())
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        units, info, req, d = fc_sweep.submit(
            self.LEVELS, scratch, runner=runner, hosts=1)
        self.assertEqual(len(calls), 1)
        argv = calls[0]
        self.assertEqual(argv[:2], ["klt", "sim"])
        self.assertIn("--wait-for-capacity", argv)
        self.assertEqual(argv[argv.index("--wait-for-capacity") + 1], "600")
        self.assertNotIn("--backend", argv)  # backend resolution stays klt's own
        self.assertEqual((d / "request.json").is_file(), True)
        self.assertEqual((d / "tb.spice").is_file(), True)
        echoed = json.loads((d / "request.json").read_text())
        self.assertEqual(
            echoed["corners"]["params"][fc_sweep.INPUT_SWEEP_PARAM], self.LEVELS)
        self.assertEqual(len(req["corners"]["params"][fc_sweep.INPUT_SWEEP_PARAM]),
                         len(self.LEVELS))
        self.assertEqual(info["job_id"], "klt-sim-deadbeef")
        self.assertEqual(len(units), len(self.LEVELS))

    def test_refused_submit_raises_the_shared_submit_error(self):
        runner = lambda argv: (1, "", '{"error": {"code": "batch_no_capacity"}}')  # noqa: E731
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        with self.assertRaises(fc_sweep.SubmitError) as ctx:
            fc_sweep.submit(self.LEVELS, scratch, runner=runner, hosts=1)
        self.assertIn("batch_no_capacity", str(ctx.exception))
        # the deck and request survive for the NOT RUN record
        self.assertTrue((scratch / "sweep" / "request.json").is_file())

    def _write_record_with_fixture(self):
        runner, _calls = self._fake_runner(self._canned_report())
        tmp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        scratch = tmp_dir / "scratch"
        result = fc_sweep.run_sweep(self.LEVELS, scratch, quiet=True, runner=runner,
                                    hosts=1)
        with provenance_fixture.fake_provenance(fc_common, tmp_dir):
            path = fc_sweep.write_record(
                result["rows"], result["info"], result["req"],
                result["workdir"],
                "sim/full-conversion-transient/run_conversion.py --input-sweep --record",
            )
        return path, tmp_dir, result

    def test_record_tabulates_codes_boundary_and_never_moves_latest(self):
        path, tmp_dir, result = self._write_record_with_fixture()
        text = path.read_text()
        # every level tabulated with code, ideal, error and the verdict
        self.assertIn("| input (*V_REF) | ideal code | captured code |", text)
        for f in self.LEVELS:
            self.assertIn(f"| {f:+.2f} |", text)
        self.assertIn("911", text)          # the ideal code at +-0.78
        # AC 3: the boundary, per sign, stated plainly -- and the disclaimer
        self.assertIn("largest tested magnitude that converges", text)
        self.assertIn("smallest tested magnitude that does not", text)
        self.assertIn("not a spec claim", text)
        self.assertIn("INFORMATIONAL", text)
        # AC 4: the solver policy is named
        self.assertIn("reltol-gear", text)
        self.assertIn(".options reltol=1e-4 method=gear", text)
        # append-only: supersedes nothing, LATEST untouched
        self.assertIn("**Supersedes**: (none)", text)
        self.assertFalse((tmp_dir / "records" / "LATEST").exists())
        self.assertTrue((tmp_dir / "corners" / "REC" / "request.json").is_file())
        self.assertTrue((tmp_dir / "corners" / "REC" / "report.json").is_file())
        self.assertTrue((tmp_dir / "corners" / "REC" / "tb.spice").is_file())
        self.assertTrue(result["all_read"])

    def test_not_run_record_quotes_the_refusal_and_never_moves_latest(self):
        refusal = ('klt sim (sweep): {"code": "batch_no_capacity"}')
        tmp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        scratch = tmp_dir / "scratch" / "sweep"
        scratch.mkdir(parents=True)
        (scratch / "request.json").write_text("{}\n")
        (scratch / "tb.spice").write_text("* deck\n")
        with provenance_fixture.fake_provenance(fc_common, tmp_dir):
            path = fc_sweep.write_not_run_record(
                scratch, refusal,
                "sim/full-conversion-transient/run_conversion.py --input-sweep --record",
            )
        text = path.read_text()
        self.assertIn("**Overall**: NOT RUN", text)
        self.assertIn("No local fallback was run", text)
        self.assertIn("batch_no_capacity", text)
        self.assertIn("**Supersedes**: (none)", text)
        self.assertFalse((tmp_dir / "records" / "LATEST").exists())

    def test_run_sweep_reports_incomplete_units_as_not_all_read(self):
        corners = [_corner(f, self.CODES[f]) for f in self.LEVELS]
        corners[0]["status"] = "error"       # -0.78 produces no usable code
        runner, _calls = self._fake_runner(json.dumps(_report(corners)))
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        result = fc_sweep.run_sweep(self.LEVELS, scratch, quiet=True, runner=runner,
                                    hosts=1)
        self.assertFalse(result["all_read"])
        self.assertEqual(result["n_complete"], len(self.LEVELS) - 1)
        bounds = result["bounds"]
        self.assertIsNone(bounds["negative"]["smallest_failing_f"])
        self.assertEqual(bounds["negative"]["unreadable_f"], [0.78])


class TestInputSweepCliRefusals(unittest.TestCase):
    """The dispatcher refuses every combination that would stand in for a
    boundary measurement -- before any toolchain check or submission."""

    def _main(self, *argv: str) -> int:
        with mock.patch.object(sys, "argv", ["run_conversion.py", *argv]):
            return run_conversion_mod.main()

    def test_mutually_exclusive_with_every_other_mode(self):
        for other in ("--corners", "--node-trace", "--cm-trace",
                      "--decision-margin-trace", "--coherent-sine", "--solver-audit"):
            self.assertEqual(self._main("--input-sweep", other), 2, other)

    def test_no_solver_profile_jobs_or_supersedes(self):
        self.assertEqual(
            self._main("--input-sweep", "--solver-profile", "ngspice-default"), 2)
        self.assertEqual(self._main("--input-sweep", "--jobs", "3"), 2)
        self.assertEqual(
            self._main("--input-sweep", "--supersedes",
                       "20261011-112119-188e94c"), 2)

    def test_input_levels_require_the_mode_and_the_band(self):
        self.assertEqual(self._main("--input-levels", "0.3"), 2)
        self.assertEqual(self._main("--input-sweep", "--input-levels", "0.1"), 2)
        self.assertEqual(self._main("--input-sweep", "--input-levels", "abc"), 2)

    def test_valid_levels_pass_validation_and_reach_the_toolchain_gate(self):
        """A well-formed custom list clears the flag checks and reaches the
        toolchain gate, which SKIPs (exit 0) before anything is submitted --
        proving the checks run before any gate that could simulate. A list
        beginning with a negative level passes as `--input-levels=<list>`
        (argparse's equals form; a space form would parse as an option)."""
        with mock.patch.object(run_conversion_mod.toolchain, "check_env") as check_env:
            check_env.return_value = harness_toolchain.CheckResult(
                status=3, messages=["synthetic: no toolchain"])
            self.assertEqual(
                self._main("--input-sweep",
                           "--input-levels=-0.78,-0.25,0.25,0.78"), 0)
            check_env.assert_called_once()


if __name__ == "__main__":
    unittest.main()

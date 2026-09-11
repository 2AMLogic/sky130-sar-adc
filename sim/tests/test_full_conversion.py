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

import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
EXPERIMENT_DIR = SIM_DIR / "full-conversion-transient"
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(EXPERIMENT_DIR))

import gen_full_conversion_tb as tb  # noqa: E402
import run_conversion as rc  # noqa: E402
from harness import evidence  # noqa: E402
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
        result = rc.decode(_synthetic_parsed(ideal), 1.8)
        self.assertTrue(result["all_ok"])
        self.assertEqual(result["worst_error_lsb"], 0)
        self.assertEqual(result["n_code_ok"], result["n_conversions"])
        self.assertEqual(result["n_phase_ok"], result["n_conversions"])

    def test_a_one_lsb_error_still_passes_but_a_two_lsb_error_does_not(self):
        base = {c: tb.ideal_code(tb.input_fraction(c)) for c in tb.measured_conversions()}
        one_off = dict(base)
        one_off[tb.measured_conversions()[0]] += 1
        self.assertTrue(rc.decode(_synthetic_parsed(one_off), 1.8)["all_ok"])
        two_off = dict(base)
        two_off[tb.measured_conversions()[0]] += 2
        result = rc.decode(_synthetic_parsed(two_off), 1.8)
        self.assertFalse(result["all_ok"])
        self.assertEqual(result["worst_error_lsb"], 2)

    def test_a_broken_phase_structure_fails_even_when_the_code_is_right(self):
        ideal = {c: tb.ideal_code(tb.input_fraction(c)) for c in tb.measured_conversions()}
        parsed = _synthetic_parsed(ideal)
        # BUSY stuck high through the SAMPLE period == conversion did not finish
        c = tb.measured_conversions()[0]
        parsed[tb.busy_measure_names(c)[-1]] = 1.8
        result = rc.decode(parsed, 1.8)
        self.assertFalse(result["all_ok"])
        self.assertEqual(result["n_phase_ok"], result["n_conversions"] - 1)

    def test_power_sums_only_the_sources_at_a_nonzero_potential(self):
        ideal = {c: tb.ideal_code(tb.input_fraction(c)) for c in tb.measured_conversions()}
        result = rc.decode(_synthetic_parsed(ideal), 1.8)
        expected = 1.8 * (2.0e-6 + 3.0e-6 + 2.5e-6) + 0.9 * 0.5e-6
        self.assertAlmostEqual(result["power_w"], expected, places=12)

    def test_missing_measurements_do_not_decode_to_a_bogus_code(self):
        ideal = {c: tb.ideal_code(tb.input_fraction(c)) for c in tb.measured_conversions()}
        parsed = _synthetic_parsed(ideal)
        del parsed[tb.code_measure_names(tb.measured_conversions()[0])[0]]
        result = rc.decode(parsed, 1.8)
        self.assertIsNone(result["conversions"][0]["code"])
        self.assertFalse(result["all_ok"])


class TestRecordRendering(unittest.TestCase):
    """write_record() must emit every base field sim/report/generate.py
    re-extracts, or the characterization report degrades silently."""

    def _point(self, corner_id: str, process: str, temp: float, supply: float, offset: int):
        codes = {
            c: tb.ideal_code(tb.input_fraction(c)) + offset for c in tb.measured_conversions()
        }
        point = rc.decode(_synthetic_parsed(codes, supply), supply)
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
            real_dir, real_resolve = rc.EXPERIMENT_DIR, evidence.resolve_provenance

            def fake_resolve(experiment_dir: Path, netlist_text: str):
                (experiment_dir / "netlist-snapshots").mkdir(parents=True, exist_ok=True)
                (experiment_dir / "netlist-snapshots" / "REC.spice").write_text(netlist_text)
                (experiment_dir / "records").mkdir(parents=True, exist_ok=True)
                return evidence.ProvenanceInfo(
                    record_id="REC",
                    record_path=experiment_dir / "records" / "REC.md",
                    netlist_sha="0" * 64,
                    pdk_line="sky130A @ testing",
                    ng_version="ngspice-46",
                )

            try:
                rc.EXPERIMENT_DIR = tmp_dir
                evidence.resolve_provenance = fake_resolve
                path = rc.write_record(points, "* synthetic netlist\n")
            finally:
                rc.EXPERIMENT_DIR = real_dir
                evidence.resolve_provenance = real_resolve

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


if __name__ == "__main__":
    unittest.main()

"""Unit tests for issue #603's coherent-sine dynamic test -- the stdlib-only
FFT/SNDR/ENOB analyzer (`sim/full-conversion-transient/dynamic_enob.py`) and
the `--coherent-sine` mode of `run_conversion.py`. Pure math and text; no
ngspice/PDK required (sim/tests/test_harness.py's PDK-free convention).

What is pinned here, because a 30-minute transient is the wrong place to
discover it:

1. The FFT is a correct DFT (against a direct O(N^2) sum) and the power
   spectrum obeys Parseval, so SNDR is a ratio of true powers.
2. The windowless coherent case: a pure on-bin sine has all its power in one
   bin, DC is excluded, and amplitude is recovered.
3. Known-ENOB code streams: a sine plus a second on-bin tone of known
   amplitude (SNDR exact in closed form), an ideal 10-bit quantizer on a long
   record (ENOB -> 10 bit), and an ideal quantizer plus seeded Gaussian noise
   of known sigma (SNDR from the quantization + noise power sum).
4. The coherent-sine fragment is committed byte-for-byte and its timing
   plan is coherent: consecutive sample instants are one conversion period
   apart and the stimulus phase matches the analyzer's reference phase.
5. `run_sine_point()` end to end with ngspice mocked: an ideal capture
   reproduces the ideal-quantizer analysis exactly; a missing code yields an
   explicit "not analysable", never a zero-filled spectrum.
6. `write_sine_record()` mints a new record with the fields
   sim/check_spec_coverage.py reads, and does NOT move records/LATEST.
"""

from __future__ import annotations

import cmath
import math
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parent.parent
EXPERIMENT_DIR = SIM_DIR / "full-conversion-transient"
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(EXPERIMENT_DIR))

import dynamic_enob as de  # noqa: E402
import gen_full_conversion_tb as tb  # noqa: E402
import run_conversion as rc  # noqa: E402
from harness import evidence  # noqa: E402


def _naive_dft(x: list[float]) -> list[complex]:
    n = len(x)
    return [
        sum(x[i] * cmath.exp(-2j * math.pi * k * i / n) for i in range(n)) for k in range(n)
    ]


class TestFft(unittest.TestCase):
    def test_matches_direct_dft(self):
        rng = random.Random(603)
        for n in (8, 16, 64):
            x = [rng.uniform(-1, 1) for _ in range(n)]
            fast = de.fft(x)
            slow = _naive_dft(x)
            for a, b in zip(fast, slow):
                self.assertAlmostEqual(a.real, b.real, places=9)
                self.assertAlmostEqual(a.imag, b.imag, places=9)

    def test_parseval(self):
        rng = random.Random(29)
        x = [rng.gauss(0, 1) for _ in range(128)]
        mean_square = sum(v * v for v in x) / len(x)
        self.assertAlmostEqual(sum(de.power_spectrum(x)), mean_square, places=9)

    def test_rejects_non_power_of_two(self):
        with self.assertRaises(ValueError):
            de.fft([0.0] * 12)


class TestCoherentPlan(unittest.TestCase):
    def test_valid_plans(self):
        for n, k in ((32, 7), (64, 13), (1024, 127), (8, 3)):
            de.check_coherent(n, k)

    def test_invalid_plans(self):
        for n, k in ((30, 7), (4, 1), (32, 0), (32, 16), (32, 17), (32, 6), (64, 12)):
            with self.subTest(n=n, k=k), self.assertRaises(ValueError):
                de.check_coherent(n, k)


class TestWindowlessCoherentSine(unittest.TestCase):
    N, BIN, AMP, OFFSET = 64, 13, 100.0, 512.0

    def test_all_power_in_tone_bin_and_dc_excluded(self):
        x = de.sine_samples(self.N, self.BIN, self.AMP, 0.7, self.OFFSET)
        spec = de.power_spectrum(x)
        self.assertAlmostEqual(spec[self.BIN], self.AMP**2 / 2, places=6)
        self.assertAlmostEqual(spec[0], self.OFFSET**2, places=6)
        leak = sum(p for k, p in enumerate(spec) if k not in (0, self.BIN))
        self.assertLess(leak, 1e-15 * spec[self.BIN])
        r = de.analyze(x, self.BIN, n_bits=10)
        self.assertEqual(r["peak_bin"], self.BIN)
        self.assertAlmostEqual(r["amplitude_codes"], self.AMP, places=6)
        self.assertAlmostEqual(r["dc_codes"], self.OFFSET, places=6)
        self.assertGreater(r["sndr_db"], 200.0)  # noise-free: essentially infinite

    def test_known_sndr_from_a_second_tone(self):
        # Signal A1 on bin 13 plus a "distortion" tone A2 on bin 5: SNDR is
        # exactly 20*log10(A1/A2) and ENOB follows from 6.02/1.76.
        a1, a2 = 400.0, 0.4
        x = [
            512 + s + d
            for s, d in zip(
                de.sine_samples(self.N, self.BIN, a1, 0.2),
                de.sine_samples(self.N, 5, a2, 1.1),
            )
        ]
        r = de.analyze(x, self.BIN, n_bits=10)
        self.assertAlmostEqual(r["sndr_db"], 60.0, places=6)
        self.assertAlmostEqual(r["enob_bit"], (60.0 - 1.76) / 6.02, places=6)
        self.assertEqual(r["spur_bin"], 5)
        self.assertAlmostEqual(r["sfdr_db"], 60.0, places=6)
        # Full-scale normalisation: A1 = 400 of a 512-code FS amplitude.
        self.assertAlmostEqual(r["sndr_fs_db"], 60.0 - 20 * math.log10(400 / 512), places=6)


class TestKnownEnobCodeStreams(unittest.TestCase):
    def test_ideal_10_bit_quantizer_long_record(self):
        codes = de.ideal_quantized_sine(4096, 1031, 0.99, 10, phase_rad=0.3)
        r = de.analyze(codes, 1031, 10)
        self.assertAlmostEqual(r["enob_fs_bit"], 10.0, delta=0.05)
        self.assertEqual(r["n_at_rails"], 0)

    def test_ideal_8_bit_quantizer(self):
        codes = de.ideal_quantized_sine(4096, 1031, 0.99, 8, phase_rad=0.3)
        self.assertAlmostEqual(de.analyze(codes, 1031, 8)["enob_fs_bit"], 8.0, delta=0.05)

    def test_quantizer_plus_known_gaussian_noise(self):
        # Ideal quantizer + additive Gaussian noise of sigma = 1 LSB before
        # quantization: total noise power ~ 1/12 + 1 LSB^2, so the expected
        # SNDR is closed-form; the seeded draw keeps the test deterministic.
        n, k, amp, sigma = 4096, 1031, 400.0, 1.0
        rng = random.Random(603)
        x = de.sine_samples(n, k, amp, 0.3, 512.0)
        codes = [de.ideal_quantize(v + rng.gauss(0, sigma), 10) for v in x]
        expected = 10 * math.log10((amp**2 / 2) / (1 / 12 + sigma**2))
        r = de.analyze(codes, k, 10)
        self.assertAlmostEqual(r["sndr_db"], expected, delta=0.3)
        self.assertAlmostEqual(r["enob_bit"], (expected - 1.76) / 6.02, delta=0.05)

    def test_clipping_is_counted(self):
        codes = de.ideal_quantized_sine(64, 13, 0.5, 10)
        self.assertEqual(de.analyze(codes, 13, 10)["n_at_rails"], 0)
        codes[3], codes[9] = 0, 1023
        self.assertEqual(de.analyze(codes, 13, 10)["n_at_rails"], 2)

    def test_missing_or_non_finite_code_refused(self):
        codes = de.ideal_quantized_sine(32, 7, 0.25, 10)
        for bad in (None, float("nan"), float("inf")):
            stream = list(codes)
            stream[5] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                de.analyze(stream, 7, 10)


class TestSineFragment(unittest.TestCase):
    def test_committed_fragment_matches_fresh_generation(self):
        self.assertEqual(tb.SINE_FRAGMENT_PATH.read_text(), tb.sine_fragment_text())

    def test_dc_fragment_unchanged_by_shared_helpers(self):
        self.assertEqual(tb.FRAGMENT_PATH.read_text(), tb.fragment_text())

    def test_plan_is_coherent(self):
        n, k = tb.SINE_RECORD_N, tb.SINE_TONE_BIN
        de.check_coherent(n, k)
        self.assertAlmostEqual(tb.sine_tone_hz(n, k) * n / tb.F_SAMPLE_HZ, k, places=12)
        convs = tb.sine_measured_conversions(n)
        self.assertEqual(len(convs), n)
        self.assertEqual(convs[0], tb.SINE_STARTUP_CONVERSIONS)
        for a, b in zip(convs, convs[1:]):
            self.assertAlmostEqual(
                tb.t_sample_ns(b) - tb.t_sample_ns(a), 1e9 / tb.F_SAMPLE_HZ, places=6
            )
        # Every code is read after its own sample instant and before the next.
        for c in convs:
            self.assertLess(tb.t_sample_ns(c), tb.t_code_read_ns(c))
            self.assertLess(tb.t_code_read_ns(c), tb.t_sample_ns(c + 1))
        self.assertLess(tb.t_phase_mid_ns(convs[-1], tb.PHASES_PER_CONVERSION - 1),
                        tb.sine_t_stop_ns(n))

    def test_stimulus_phase_matches_reference_phase(self):
        n, k, amp = tb.SINE_RECORD_N, tb.SINE_TONE_BIN, tb.SINE_AMPLITUDE_FRACTION
        ref = de.sine_samples(n, k, amp, tb.sine_phase_rad(n, k))
        for i, c in enumerate(tb.sine_measured_conversions(n)):
            self.assertAlmostEqual(tb.sine_input_fraction(c, n, k, amp), ref[i], places=9)

    def test_amplitude_stays_within_dc_verified_range(self):
        # The pilot amplitude is bounded by the DC bench's +-0.25*V_REF points.
        self.assertLessEqual(tb.SINE_AMPLITUDE_FRACTION, max(tb.INPUT_FRACTIONS[1:-1]))

    def test_sources_and_meas_cards(self):
        text = tb.sine_fragment_text()
        self.assertIn("VINP VINP 0 SIN({vdd_val*0.5} {vdd_val*0.125} 218750 0 0 0)", text)
        self.assertIn("VINN VINN 0 SIN({vdd_val*0.5} {vdd_val*0.125} 218750 0 0 180)", text)
        for name in tb.sine_measure_names():
            self.assertIn(f".meas tran {name} ", text)

    def test_invalid_plan_refused(self):
        for args in ((30, 7, 0.25), (32, 8, 0.25), (32, 7, 1.0), (32, 7, 0.0)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                tb.sine_fragment_text(*args)


def _sine_log(
    codes: dict[int, int | None], supply_v: float = 1.8, busy_stuck_high: bool = False
) -> str:
    """ngspice-shaped `name = value` lines for a capture of `codes`
    (conversion -> code; None omits that conversion's bits) with a correct
    phase structure -- or, with `busy_stuck_high`, the shape the first
    (ngspice-42, below the pinned floor) pilot probe actually produced:
    BUSY high and SAMPLE_INT low through all 12 periods of every conversion."""
    last = tb.PHASES_PER_CONVERSION - 1
    out = []
    for c, code in codes.items():
        if code is not None:
            for name, b in zip(tb.code_measure_names(c), range(tb.N_BITS - 1, -1, -1)):
                out.append(f"{name} = {supply_v if (code >> b) & 1 else 0.0:.6e}")
        for p, name in enumerate(tb.busy_measure_names(c)):
            high = busy_stuck_high or p < last
            out.append(f"{name} = {supply_v if high else 0.0:.6e}")
        for p, name in enumerate(tb.sample_measure_names(c)):
            high = (not busy_stuck_high) and p == last
            out.append(f"{name} = {supply_v if high else 0.0:.6e}")
    return "\n".join(out) + "\n"


def _ideal_capture() -> dict[int, int]:
    return {
        c: tb.ideal_code(tb.sine_input_fraction(c)) for c in tb.sine_measured_conversions()
    }


class TestRunSinePoint(unittest.TestCase):
    def _run(self, log_text: str) -> dict:
        with mock.patch.object(rc, "assemble_deck", return_value="* deck\n"), \
                mock.patch.object(rc, "_run_ngspice", return_value=log_text) as run:
            point = rc.run_sine_point(
                "* netlist\n", None, Path("/nonexistent"),
                tb.SINE_RECORD_N, tb.SINE_TONE_BIN, tb.SINE_AMPLITUDE_FRACTION,
            )
        self.assertEqual(run.call_args.kwargs.get("attempts"), 1)
        return point

    def test_ideal_capture_reproduces_ideal_analysis(self):
        point = self._run(_sine_log(_ideal_capture()))
        self.assertEqual(point["missing"], [])
        self.assertTrue(all(point["phase_ok"]))
        self.assertEqual(point["codes"], point["ideal_codes"])
        self.assertAlmostEqual(point["analysis"]["sndr_db"], point["ideal"]["sndr_db"], places=9)
        self.assertEqual(point["analysis"]["peak_bin"], tb.SINE_TONE_BIN)

        self.assertEqual(rc.sine_point_problems(point), [])

    def test_missing_code_is_not_analysable(self):
        capture = _ideal_capture()
        capture[tb.sine_measured_conversions()[3]] = None
        point = self._run(_sine_log(capture))
        self.assertIsNone(point["analysis"])
        self.assertIn("missing", point["analysis_error"])
        self.assertTrue(point["missing"])
        self.assertTrue(rc.sine_point_problems(point))

    def test_wrong_phase_structure_invalidates_an_analysable_stream(self):
        # The pilot probe's shape: codes collapsed onto the input's sign
        # (383 / 640) with BUSY never low. The FFT still returns a number;
        # the run must still be flagged as not a measurement.
        capture = {
            c: (640 if tb.sine_input_fraction(c) > 0 else 383)
            for c in tb.sine_measured_conversions()
        }
        point = self._run(_sine_log(capture, busy_stuck_high=True))
        self.assertIsNotNone(point["analysis"])
        self.assertFalse(any(point["phase_ok"]))
        problems = rc.sine_point_problems(point)
        self.assertTrue(any("phase structure wrong" in p for p in problems))
        self.assertIn("INVALID", rc.format_sine_point(point))


class TestOutlierDiagnostic(unittest.TestCase):
    def _point(self, capture: dict) -> dict:
        with mock.patch.object(rc, "assemble_deck", return_value="* deck\n"), \
                mock.patch.object(rc, "_run_ngspice", return_value=_sine_log(capture)):
            return rc.run_sine_point(
                "* netlist\n", None, Path("/nonexistent"),
                tb.SINE_RECORD_N, tb.SINE_TONE_BIN, tb.SINE_AMPLITUDE_FRACTION,
            )

    def _with_errors(self, errs: dict[int, int]) -> dict:
        cap = _ideal_capture()
        convs = tb.sine_measured_conversions()
        for k, e in errs.items():
            cap[convs[k]] += e
        return self._point(cap)

    def test_no_outlier(self):
        d = self._point(_ideal_capture())["outlier_diag"]
        self.assertEqual(d["outliers"], [])
        self.assertEqual(d["max_abs_error"], 0)
        self.assertIsNone(d["leave_out"])

    def test_exactly_at_boundary_is_not_an_outlier(self):
        b = rc.SINE_OUTLIER_BOUND_LSB
        d = self._with_errors({3: b, 5: -b})["outlier_diag"]
        self.assertEqual(d["outliers"], [])
        self.assertEqual(d["max_abs_error"], b)

    def test_beyond_boundary(self):
        b = rc.SINE_OUTLIER_BOUND_LSB
        point = self._with_errors({3: b + 1})
        d = point["outlier_diag"]
        self.assertEqual([o["sample"] for o in d["outliers"]], [3])
        o = d["outliers"][0]
        self.assertEqual(o["error"], b + 1)
        self.assertEqual(o["captured"] - o["ideal"], b + 1)
        self.assertEqual(o["conversion"], tb.sine_measured_conversions()[3])
        # a validity-clean capture stays valid
        self.assertEqual(rc.sine_point_problems(point), [])

    def test_multiple_outliers_signed(self):
        d = self._with_errors({2: -20, 9: 15, 11: 3})["outlier_diag"]
        self.assertEqual([(o["sample"], o["error"]) for o in d["outliers"]], [(2, -20), (9, 15)])
        self.assertEqual(d["max_abs_error"], 20)

    def test_conversion_9_shaped(self):
        point = self._with_errors({8: 438})
        d = point["outlier_diag"]
        self.assertEqual(len(d["outliers"]), 1)
        self.assertEqual(d["outliers"][0]["conversion"], tb.sine_measured_conversions()[8])
        self.assertEqual(d["max_abs_error"], 438)
        # headline is the unmodified stream and far worse than the leave-out
        self.assertEqual(point["codes"][8], point["ideal_codes"][8] + 438)
        self.assertLess(point["analysis"]["sndr_db"], d["leave_out"]["sndr_db"] - 10)
        self.assertAlmostEqual(d["leave_out"]["sndr_db"], point["ideal"]["sndr_db"], places=6)
        self.assertIn("OUTLIER", rc.format_outlier_summary(point))

    def test_record_labels_diagnostic_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = TestSineRecord()._write(self._with_errors({8: 438}), Path(tmp)).read_text()
        self.assertIn("Per-code outlier diagnostic", text)
        self.assertIn("DIAGNOSTIC-ONLY, NOT REPLACEMENT EVIDENCE", text)
        self.assertIn("signed error +438 LSB", text)
        self.assertNotIn("NOT A VALID MEASUREMENT", text)

    def test_validity_failures_unchanged(self):
        capture = _ideal_capture()
        capture[tb.sine_measured_conversions()[3]] = None
        point = self._point(capture)
        self.assertIsNone(point["analysis"])
        self.assertTrue(any("missing" in p for p in rc.sine_point_problems(point)))
        self.assertEqual(point["outlier_diag"]["outliers"], [])
        # wrong tone bin
        bad = self._point({
            c: 512 + round(300 * math.cos(2 * math.pi * 3 * i / tb.SINE_RECORD_N))
            for i, c in enumerate(tb.sine_measured_conversions())
        })
        self.assertTrue(any("not the drive bin" in p for p in rc.sine_point_problems(bad)))


class TestSineTrace(unittest.TestCase):
    def _trace(self, ideal: int, got: int) -> dict:
        conv = 9
        lines = []
        for entry in rc.node_trace_plan(conv):
            for k, name in entry["names"].items():
                val = 0.0
                if k == "dout_post":
                    val = 1.8 if (got >> entry["bit"]) & 1 else 0.0
                lines.append(f"{name} = {val:.6e}")
        parsed = rc.measure.parse("\n".join(lines), [n.split(" = ")[0] for n in lines], anchored=False)
        return rc.decode_sine_trace(parsed, conv, ideal, 1.8)

    def test_probes_use_sine_fragment_node_names(self):
        text = "\n".join(rc.sine_trace_measure_lines(9))
        self.assertIn("v(dout9)", text)
        self.assertIn("v(adcout0)", text)
        self.assertNotIn("v(dout0)", text)
        self.assertIn("nt_c9_samp_top_p", text)

    def test_record_renders_trace_and_rail_excursion(self):
        tr = self._trace(522, 960)
        tr["final_code"] = 960
        tr["rail_excursions"] = [(5, 4, "TOP_P", -0.5053)]
        point = TestOutlierDiagnostic()._point(_ideal_capture())
        point["traces"] = [tr]
        with tempfile.TemporaryDirectory() as tmp:
            text = TestSineRecord()._write(point, Path(tmp)).read_text()
        self.assertIn("### Conversion 9", text)
        self.assertIn("TOP_P = -0.5053 V", text)
        self.assertIn("NOT the final", text)

    def test_matching_code_has_no_divergence(self):
        self.assertIsNone(self._trace(522, 522)["first_divergent"])

    def test_first_divergent_bit_is_msb_first(self):
        tr = self._trace(522, 960)  # 0b1000001010 vs 0b1111000000
        fd = tr["first_divergent"]
        self.assertEqual(fd["bit"], 8)  # first (MSB-first) bit that differs
        self.assertEqual((fd["ideal_bit"], fd["captured_bit"]), (0, 1))


class TestSwitchTrace(unittest.TestCase):
    """issue #621: the read-only switching-event trace of one conversion."""

    CONV = 9

    def _event_lines(self, code: int, extra: list[tuple[str, str, float]] = ()) -> list[str]:
        """A synthetic log for a conversion that follows the SAR's own
        schedule for `code` (DOUT9 unchanged from the previous conversion),
        plus `extra` (node, direction, t_ns) transitions."""
        c = self.CONV
        base = tb.PHASES_PER_CONVERSION * c
        names = rc.switch_trace_names(c)["events"]
        ev: dict[tuple[str, str], list[float]] = {}

        def at(node, d, edge, delay=1.5):
            ev.setdefault((node, d), []).append(tb.t_edge_ns(edge) + delay)

        for p in range(tb.N_BITS):
            at(f"PH_B{tb.N_BITS - 1 - p}", "rise", base + p)
            at(f"PH_B{tb.N_BITS - 1 - p}", "fall", base + p + 1)
        at("PH_EOC", "rise", base + 10)
        at("PH_EOC", "fall", base + 11)
        at("BUSY", "rise", base)
        at("BUSY", "fall", base + 11)
        at("SAMPLE_INT", "fall", base)
        at("SAMPLE_INT", "rise", base + 11)
        at("xseq.BUSY_BITS", "rise", base)
        at("xseq.BUSY_BITS", "fall", base + 10)
        for k in range(tb.N_BITS - 1):
            at(f"DOUT{k}", "rise", base + 9 - k)
            at(f"DOUT{k}", "fall", base + (11 if (code >> k) & 1 else 10 - k))
        for node, d, t in extra:
            ev.setdefault((node, d), []).append(t)
        lines = []
        for (node, d), times in ev.items():
            for i, t in enumerate(sorted(times)[: rc.SWITCH_TRACE_MAX_EDGES], start=1):
                lines.append(f"{names[node][(d, i)]} = {t * 1e-9:.9e}")
        return lines

    def _decode(self, lines: list[str]) -> dict:
        parsed = rc.measure.parse("\n".join(lines), rc.switch_trace_flat_names(self.CONV))
        return rc.decode_switch_trace(parsed, self.CONV, 1.8)

    def test_schedule_following_conversion_has_no_unscheduled_event(self):
        st = self._decode(self._event_lines(522))
        self.assertTrue(st["events"])
        self.assertEqual(st["unscheduled"], [])
        self.assertIsNone(st["first_unscheduled"])
        self.assertEqual(st["excursions"], {"TOP_P": None, "TOP_N": None})

    def test_mid_phase_transition_is_unscheduled(self):
        base = tb.PHASES_PER_CONVERSION * self.CONV
        t = tb.t_edge_ns(base + 5) + 43.0  # phase 5, CLK-low half
        st = self._decode(self._event_lines(522, [("DOUT8", "rise", t)]))
        fu = st["first_unscheduled"]
        self.assertEqual((fu["node"], fu["direction"], fu["phase"]), ("DOUT8", "rise", 5))
        self.assertAlmostEqual(fu["offset_ns"], 43.0, places=3)
        self.assertFalse(fu["on_edge"])

    def test_on_edge_but_off_schedule_is_unscheduled(self):
        base = tb.PHASES_PER_CONVERSION * self.CONV
        t = tb.t_edge_ns(base + 5) + 1.0  # an edge, but not DOUT7's own edges
        st = self._decode(self._event_lines(522, [("DOUT7", "rise", t)]))
        fu = st["first_unscheduled"]
        self.assertEqual(fu["node"], "DOUT7")
        self.assertTrue(fu["on_edge"])
        self.assertFalse(fu["scheduled"])

    def test_edge_window_bounds(self):
        exp = rc.switch_trace_expected_edges(self.CONV)
        base = tb.PHASES_PER_CONVERSION * self.CONV
        lo, hi = rc.SWITCH_TRACE_EDGE_WINDOW_NS
        edge = tb.t_edge_ns(base + 1)
        self.assertTrue(rc.classify_switch_event("DOUT8", edge + hi, exp, "rise")["scheduled"])
        self.assertTrue(rc.classify_switch_event("DOUT8", edge + lo, exp, "rise")["scheduled"])
        self.assertFalse(rc.classify_switch_event("DOUT8", edge + hi + 0.5, exp, "rise")["scheduled"])

    def test_measure_lines_are_read_only_and_named_uniquely(self):
        lines = rc.switch_trace_measure_lines(self.CONV, 1.8)
        text = "\n".join(lines)
        self.assertTrue(all(ln.startswith((".meas tran ", "*")) for ln in lines))
        self.assertIn("when v(DOUT8)=0.9000 rise=1 from=", text)
        self.assertIn("find v(xcdac.BOT_p8) when v(TOP_P)=-0.2000 fall=1", text)
        # ring PORTS are probed on the nets the netlist wires them to
        # (`xseq.<port>` does not exist in ngspice); internal nets keep xseq.
        ports = rc.sequencer_port_nets()
        self.assertIn(f"v({ports['PH_B4']})", text)
        self.assertNotIn("v(xseq.PH_B4)", text)
        self.assertIn("v(xseq.DFEED8)", text)
        self.assertIn("v(xseq.MUXOUT9)", text)
        names = rc.switch_trace_flat_names(self.CONV)
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(names), sum(1 for ln in lines if ln.startswith(".meas")))
        for n in names:
            self.assertRegex(n, r"^[a-z_][a-z0-9_]*$")

    def test_excursion_and_snapshot_decode_and_render(self):
        names = rc.switch_trace_names(self.CONV)
        base = tb.PHASES_PER_CONVERSION * self.CONV
        t_off = tb.t_edge_ns(base + 5) + 44.0
        lines = self._event_lines(522, [("DOUT8", "rise", t_off - 1.0)])
        ex = names["excursion"]["TOP_P"]
        lines.append(f"{ex['t']} = {t_off * 1e-9:.9e}")
        lines.append(f"{ex['at']['SELp8']} = 1.8")
        lines.append(f"{ex['at']['xcdac.BOT_p8']} = 0.0")
        lines.append(f"{names['snapshots'][(5, 'pre')]['TOP_P']} = -0.505")
        st = self._decode(lines)
        self.assertEqual(st["excursions"]["TOP_P"]["phase"], 5)
        self.assertEqual(st["excursions"]["TOP_P"]["values"]["SELp8"], 1.8)
        self.assertEqual(st["snapshots"][(5, "pre")]["TOP_P"], -0.505)
        point = TestOutlierDiagnostic()._point(_ideal_capture())
        point["switch_traces"] = [st]
        with tempfile.TemporaryDirectory() as tmp:
            text = TestSineRecord()._write(point, Path(tmp)).read_text()
        self.assertIn("## Switching-event trace", text)
        self.assertIn("**First UNSCHEDULED transition (observed)**: `DOUT8` rise", text)
        self.assertIn("**UNSCHEDULED**", text)
        self.assertIn("Node values at the instant TOP_P crosses -0.2 V", text)
        self.assertIn("SELp8..0 `1????????`", text)
        self.assertIn("-0.505", text)
        self.assertIn("first UNSCHEDULED transition: DOUT8 rise",
                      rc.format_switch_trace_summary(st))

    def test_sequencer_port_map_comes_from_the_netlist(self):
        ports = rc.sequencer_port_nets()
        self.assertEqual(ports["PH_B9"], "PH_B9")
        self.assertEqual(ports["CLK"], "CLK")
        self.assertEqual(ports["PH_SAMPLE"], "SAMPLE_INT")
        for b in range(tb.N_BITS):
            self.assertIn(f"PH_B{b}", ports)
        with self.assertRaises(ValueError):
            rc.sequencer_port_nets("* no sequencer here\n")

    def test_context_nets_are_recorded_but_not_classified(self):
        base = tb.PHASES_PER_CONVERSION * self.CONV
        t = tb.t_edge_ns(base + 5) + 43.0
        st = self._decode(self._event_lines(522, [("xseq.DFEED8", "rise", t)]))
        ctx = [e for e in st["events"] if e["node"] == "xseq.DFEED8"]
        self.assertEqual(len(ctx), 1)
        self.assertIsNone(ctx[0]["scheduled"])
        self.assertEqual(st["unscheduled"], [])

    def test_strobe_window_rendered_for_first_unscheduled_phase(self):
        names = rc.switch_trace_names(self.CONV)
        base = tb.PHASES_PER_CONVERSION * self.CONV
        lines = self._event_lines(522, [("DOUT8", "rise", tb.t_edge_ns(base + 5) + 44.3)])
        lines.append(f"{names['strobe'][(5, 3)]['xseq.DFEED8']} = 1.8")
        lines.append(f"{names['strobe'][(5, 3)]['COMP_OUT']} = 0.48")
        st = self._decode(lines)
        self.assertEqual(st["strobe"][(5, 3)]["xseq.DFEED8"], 1.8)
        text = "\n".join(rc.switch_trace_record_lines([st]))
        self.assertIn("#### Strobe window, phase 5", text)
        self.assertIn("| 0.480 |", text)
        self.assertIn("`1????????` |", text)

    def test_logic_char_bands(self):
        self.assertEqual(rc._logic_char(None, 1.8), "?")
        self.assertEqual(rc._logic_char(0.9, 1.8), "x")
        self.assertEqual(rc._logic_char(1.7, 1.8), "1")
        self.assertEqual(rc._logic_char(0.1, 1.8), "0")


class TestBehavioralReference(unittest.TestCase):
    def test_parses_latest_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "R1.md").write_text(
                "- **Measured value(s)**: achieved ENOB (mean-case CDAC mismatch) = "
                "**8.507 bit**; achieved ENOB (worst-case CDAC mismatch) = **7.7 bit**\n"
            )
            (d / "LATEST").write_text("R1.md\n")
            ref = rc.behavioral_enob_reference(d)
        self.assertAlmostEqual(ref["enob_bit"], 8.507)

    def test_absent_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(rc.behavioral_enob_reference(Path(tmp)))

    def test_committed_latest_is_parseable(self):
        self.assertIsNotNone(rc.behavioral_enob_reference())


class TestSineRecord(unittest.TestCase):
    def _write(self, point: dict, tmp_dir: Path) -> Path:
        real_dir, real_resolve = rc.EXPERIMENT_DIR, evidence.resolve_provenance

        def fake_resolve(experiment_dir: Path, netlist_text: str):
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
            return rc.write_sine_record(
                point, "* netlist\n", "",
                "sim/full-conversion-transient/run_conversion.py --coherent-sine --record",
                {"record": "sim/enob-estimate/records/X.md", "enob_bit": 8.507},
            )
        finally:
            rc.EXPERIMENT_DIR = real_dir
            evidence.resolve_provenance = real_resolve

    def _point(self, capture: dict) -> dict:
        with mock.patch.object(rc, "assemble_deck", return_value="* deck\n"), \
                mock.patch.object(rc, "_run_ngspice", return_value=_sine_log(capture)):
            return rc.run_sine_point(
                "* netlist\n", None, Path("/nonexistent"),
                tb.SINE_RECORD_N, tb.SINE_TONE_BIN, tb.SINE_AMPLITUDE_FRACTION,
            )

    def test_record_fields_and_no_latest(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            path = self._write(self._point(_ideal_capture()), tmp_dir)
            text = path.read_text()
            for field in ("Record ID", "Claim", "Netlist provenance", "Corner matrix run",
                          "Dynamic-test (FFT) metadata", "Measured value(s)", "Supersedes"):
                self.assertIn(f"**{field}**", text)
            self.assertIn("`spec/target-spec.md#target-table`", text)
            self.assertIn("window = none", text)
            self.assertIn(f"N = {tb.SINE_RECORD_N} samples", text)
            self.assertIn(f"coherent bin = {tb.SINE_TONE_BIN}", text)
            self.assertIn("8.491", text)
            self.assertIn("8.507", text)
            self.assertIn("- PDK: sky130A @ testing", text)
            self.assertIn("- DUT netlist sha256: `" + "0" * 64 + "`", text)
            self.assertIn(
                "Written by `sim/full-conversion-transient/run_conversion.py "
                "--coherent-sine --record`", text,
            )
            self.assertFalse((tmp_dir / "records" / "LATEST").exists())
            self.assertTrue((tmp_dir / "corners" / "REC" / "coherent-sine-tt_27c_1.80v.log").is_file())
            self.assertEqual(
                (tmp_dir / "corners" / "REC" / "coherent_sine_tb_fragment.spice").read_text(),
                tb.sine_fragment_text(),
            )

    def test_valid_capture_has_no_validity_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = self._write(self._point(_ideal_capture()), Path(tmp)).read_text()
        self.assertNotIn("NOT A VALID MEASUREMENT", text)

    def test_wrong_phase_structure_is_stamped_invalid(self):
        capture = {
            c: (640 if tb.sine_input_fraction(c) > 0 else 383)
            for c in tb.sine_measured_conversions()
        }
        with mock.patch.object(rc, "assemble_deck", return_value="* deck\n"), \
                mock.patch.object(rc, "_run_ngspice",
                                  return_value=_sine_log(capture, busy_stuck_high=True)):
            point = rc.run_sine_point(
                "* netlist\n", None, Path("/nonexistent"),
                tb.SINE_RECORD_N, tb.SINE_TONE_BIN, tb.SINE_AMPLITUDE_FRACTION,
            )
        with tempfile.TemporaryDirectory() as tmp:
            text = self._write(point, Path(tmp)).read_text()
        self.assertIn("**VALIDITY: NOT A VALID MEASUREMENT OF THE CONVERTER**", text)
        self.assertIn(f"phase structure wrong at {tb.SINE_RECORD_N}/{tb.SINE_RECORD_N}", text)

    def test_unanalysable_capture_still_records_why(self):
        capture = _ideal_capture()
        capture[tb.sine_measured_conversions()[0]] = None
        with tempfile.TemporaryDirectory() as tmp:
            text = self._write(self._point(capture), Path(tmp)).read_text()
        self.assertIn("Measured value(s)**: NONE", text)
        self.assertIn("MISSING", text)


class TestCli(unittest.TestCase):
    def test_coherent_sine_is_exclusive(self):
        argv = ["run_conversion.py", "--coherent-sine", "--corners"]
        with mock.patch.object(sys, "argv", argv), mock.patch("sys.stderr"):
            self.assertEqual(rc.main(), 2)

    def test_bad_plan_refused_before_simulating(self):
        argv = ["run_conversion.py", "--coherent-sine", "--sine-n", "48"]
        with mock.patch.object(sys, "argv", argv), mock.patch("sys.stderr"), \
                mock.patch.object(rc.toolchain, "check_env") as check:
            self.assertEqual(rc.main(), 2)
        check.assert_not_called()

    def test_solver_control_cannot_supersede_or_run_alone(self):
        for argv in (
            ["run_conversion.py", "--sine-solver-control"],
            ["run_conversion.py", "--coherent-sine", "--sine-solver-control",
             "--supersedes", "20261010-070734-f968286"],
        ):
            with mock.patch.object(sys, "argv", argv), mock.patch("sys.stderr"), \
                    mock.patch.object(rc.toolchain, "check_env") as check:
                self.assertEqual(rc.main(), 2)
            check.assert_not_called()

    def test_solver_control_adds_options_only_and_is_labelled(self):
        # issue #621's control is now the named solver profile `reltol-gear`
        # (issue #637): run_sine_point hands the profile to deck assembly,
        # which is the one place an `.options` card is emitted.
        self.assertEqual(rc.SINE_SOLVER_CONTROL_OPTIONS, ".options reltol=1e-4 method=gear")
        with mock.patch.object(rc, "assemble_deck", return_value="* deck\n") as deck, \
                mock.patch.object(rc, "_run_ngspice", return_value=_sine_log(_ideal_capture())):
            point = rc.run_sine_point(
                "* netlist\n", None, Path("/nonexistent"),
                tb.SINE_RECORD_N, tb.SINE_TONE_BIN, tb.SINE_AMPLITUDE_FRACTION,
                solver_profile=rc.SINE_SOLVER_CONTROL_PROFILE,
            )
        self.assertEqual(deck.call_args.kwargs["solver_profile"], "reltol-gear")
        self.assertIsNone(deck.call_args.kwargs["extra_meas"])  # no probes, no stray card
        self.assertEqual(deck.call_args.args[0], "* netlist\n")
        with tempfile.TemporaryDirectory() as tmp:
            text = TestSineRecord()._write(point, Path(tmp)).read_text()
        self.assertIn("SOLVER-CONTROL RUN (issue #621) -- NOT THE REFERENCE CAPTURE", text)
        self.assertIn("simulator options: profile `reltol-gear` (SOLVER CONTROL): "
                      "`.options reltol=1e-4 method=gear`", text)

    def test_reference_sine_record_states_the_resolved_default_settings(self):
        with mock.patch.object(rc, "assemble_deck", return_value="* deck\n") as deck, \
                mock.patch.object(rc, "_run_ngspice", return_value=_sine_log(_ideal_capture())):
            point = rc.run_sine_point(
                "* netlist\n", None, Path("/nonexistent"),
                tb.SINE_RECORD_N, tb.SINE_TONE_BIN, tb.SINE_AMPLITUDE_FRACTION,
            )
        self.assertEqual(deck.call_args.kwargs["solver_profile"], rc.REFERENCE_SOLVER_PROFILE)
        with tempfile.TemporaryDirectory() as tmp:
            text = TestSineRecord()._write(point, Path(tmp)).read_text()
        self.assertNotIn("SOLVER-CONTROL RUN", text)
        self.assertIn("profile `ngspice-default` (reference): no `.options` card -- "
                      "reltol=1e-3, method=trapezoidal", text)

    def test_sine_solver_control_flag_conflicts_with_another_profile(self):
        argv = ["run_conversion.py", "--coherent-sine", "--sine-solver-control",
                "--solver-profile", "gear-only"]
        with mock.patch.object(sys, "argv", argv), mock.patch("sys.stderr"), \
                mock.patch.object(rc.toolchain, "check_env") as check:
            self.assertEqual(rc.main(), 2)
        check.assert_not_called()

    def test_switch_trace_requires_coherent_sine_and_a_measured_conversion(self):
        for argv in (
            ["run_conversion.py", "--sine-switch-trace", "9"],
            ["run_conversion.py", "--coherent-sine", "--sine-switch-trace", "9999"],
        ):
            with mock.patch.object(sys, "argv", argv), mock.patch("sys.stderr"), \
                    mock.patch.object(rc.toolchain, "check_env") as check:
                self.assertEqual(rc.main(), 2)
            check.assert_not_called()


if __name__ == "__main__":
    unittest.main()

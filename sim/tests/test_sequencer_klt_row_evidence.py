"""PDK-free unit tests for the `--klt-row-evidence` mode of
sim/sar-sequencer-behavioral/run_testbench.py (issue #1023).

Everything here runs without ngspice, without a PDK and without network:
deck assembly against the real committed fragment, the `klt sim` request
shape (the nine-point OAT star, the `corners.params` supply axis, the
margin measurement set with its limits and `spec_row` tags), the report
decoder, and the hash-checker's `sim` classification of the resulting
envelope shape.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(SIM_DIR / "sar-sequencer-behavioral"))
sys.path.insert(0, str(SIM_DIR.parent / "signoff"))

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "run_testbench", SIM_DIR / "sar-sequencer-behavioral" / "run_testbench.py"
)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

import check_evidence_hashes  # noqa: E402

FRAGMENT = m.FRAGMENT.read_text()


def oat_grid() -> list[tuple[str, float, float]]:
    return m.corners_mod.ratified_oat_grid(
        m.NOMINAL_SUPPLY_V,
        m.SUPPLY_TOLERANCE,
        m.PROCESS_CORNERS,
        m.TEMPS_C,
    )


# --------------------------------------------------------------------------
# Deck assembly
# --------------------------------------------------------------------------
class TestSplitRowFragment(unittest.TestCase):
    def test_splits_the_committed_fragment(self):
        body, meas, tran = m.split_row_fragment(FRAGMENT)
        self.assertEqual(tran, "0.5n 2700n")
        self.assertEqual(sorted(name for name, _, _, _ in meas),
                         sorted(m.EXPECTED_BITS))
        for line in body.splitlines():
            low = line.strip().lower()
            self.assertFalse(low.startswith(".meas"), line)
            self.assertFalse(low.startswith(".tran"), line)
        # the stimulus itself survives the split
        self.assertIn("VVPWR VPWR 0 DC {vdd_val}", body)
        self.assertIn("VCLK CLK 0 PULSE(", body)
        self.assertIn("VCOMP COMP_OUT 0 PWL(", body)

    def test_changed_meas_set_refused(self):
        with self.assertRaises(RuntimeError):
            m.split_row_fragment(
                FRAGMENT + ".meas tran extra_c3 find v(dout0) at=2600.0n\n"
            )

    def test_no_tran_card_refused(self):
        stripped = "\n".join(
            ln for ln in FRAGMENT.splitlines() if not ln.strip().lower().startswith(".tran")
        )
        with self.assertRaises(RuntimeError):
            m.split_row_fragment(stripped + "\n")

    def test_unparseable_meas_card_refused(self):
        mangled = FRAGMENT.replace(
            ".meas tran phsample_c1 find v(ph_sample) at=200.0n",
            ".meas tran phsample_c1 AVG v(ph_sample) FROM=100n TO=200n",
        )
        with self.assertRaises(RuntimeError):
            m.split_row_fragment(mangled)


class TestBuildRowBody(unittest.TestCase):
    def setUp(self):
        self.body = m.build_row_body("* header comment\nX1 a b cell\n.end\n", FRAGMENT)

    def test_is_a_circuit_body_not_a_deck(self):
        for line in self.body.splitlines():
            low = line.strip().lower()
            self.assertFalse(low.startswith(".tran"), line)
            self.assertFalse(low.startswith(".meas"), line)
            self.assertFalse(low.startswith(".control"), line)
            self.assertFalse(low == ".end", line)
        # klt sim owns the wrapper; the body must not carry it

    def test_declares_the_supply_param_the_fragment_reads(self):
        self.assertIn(".param vdd_val = 1.8", self.body)

    def test_includes_the_worker_resolved_stdcell_library(self):
        self.assertIn(
            ".include $PDK_ROOT/sky130A/libs.ref/sky130_fd_sc_hd/spice/"
            "sky130_fd_sc_hd.spice",
            self.body,
        )

    def test_dut_end_and_path_headers_stripped_devices_kept(self):
        for line in self.body.splitlines():
            self.assertNotEqual(line.strip().lower(), ".end", line)
        self.assertNotIn("** sch_path:", self.body)
        self.assertNotIn("** klt-netlist-inputs:", self.body)
        self.assertIn("X1 a b cell", self.body)
        self.assertIn("* header comment", self.body)

    def test_fragment_sources_verbatim(self):
        self.assertIn("VVPWR VPWR 0 DC {vdd_val}", self.body)
        self.assertIn("VRSTB RST_B 0 PWL(", self.body)

    def test_one_margin_helper_per_measured_node(self):
        nodes = {node for _, node, _, _ in m.split_row_fragment(FRAGMENT)[1]}
        self.assertEqual(len(nodes), 22)
        for node in nodes:
            self.assertIn(
                f"Bm_{node} {node}{m.MARGIN_SUFFIX} 0 V = v({node}) - 0.5*v(VPWR)",
                self.body,
            )

    def test_one_solver_thread(self):
        self.assertIn(".options num_threads=1", self.body)


# --------------------------------------------------------------------------
# Request
# --------------------------------------------------------------------------
class TestRowRequest(unittest.TestCase):
    def setUp(self):
        _body, self.meas, self.tran = m.split_row_fragment(FRAGMENT)
        self.points = oat_grid()
        self.req = m.build_row_request("tb.spice", self.tran, self.meas, self.points)

    def test_ratified_grid_is_the_nine_point_oat_star(self):
        self.assertEqual(len(self.points), 9)
        self.assertEqual(
            sorted(self.points),
            sorted(
                [
                    ("tt", 27.0, 1.8), ("ss", 27.0, 1.8), ("ff", 27.0, 1.8),
                    ("sf", 27.0, 1.8), ("fs", 27.0, 1.8),
                    ("tt", -40.0, 1.8), ("tt", 125.0, 1.8),
                    ("tt", 27.0, 1.62), ("tt", 27.0, 1.98),
                ]
            ),
        )

    def test_expansion_minus_exclude_is_exactly_the_star(self):
        procs = sorted({p for p, _, _ in self.points})
        temps = sorted({t for _, t, _ in self.points})
        vdds = sorted({v for _, _, v in self.points})
        excluded = {
            json.dumps(rule, sort_keys=True) for rule in self.req["exclude"]
        }
        kept = []
        for proc in procs:
            for temp in temps:
                for vdd in vdds:
                    rule = json.dumps(
                        {"process": proc, "temperature_c": temp,
                         "params": {m.VDD_PARAM: vdd}},
                        sort_keys=True,
                    )
                    if rule not in excluded:
                        kept.append((proc, temp, vdd))
        self.assertEqual(sorted(kept), sorted(self.points))
        self.assertEqual(len(self.req["exclude"]), 36)

    def test_supply_is_a_param_axis_not_a_supply_v_axis(self):
        self.assertIn("params", self.req["corners"])
        self.assertNotIn("supply_v", self.req["corners"])
        self.assertEqual(
            self.req["corners"]["params"],
            {m.VDD_PARAM: [1.62, 1.8, 1.98]},
        )

    def test_analysis_is_the_committed_tran_card(self):
        self.assertEqual(self.req["analysis"], {"kind": "tran", "args": "0.5n 2700n"})

    def test_every_measurement_tagged_limited_and_directed(self):
        entries = self.req["measurements"]
        self.assertEqual(len(entries), 35)
        for entry in entries:
            self.assertEqual(entry["spec_row"], "resolution_n")
            self.assertIn(m.MARGIN_SUFFIX, entry["spice"])
            self.assertEqual(entry["name"], entry["spice"].split()[2])
            if m.EXPECTED_BITS[entry["name"]] == 1:
                self.assertEqual(entry["limits"], {"min": 0.0})
            else:
                self.assertEqual(entry["limits"], {"max": 0.0})

    def test_limits_populated_for_both_expectations(self):
        entries = self.req["measurements"]
        mins = [e for e in entries if e["limits"] == {"min": 0.0}]
        maxs = [e for e in entries if e["limits"] == {"max": 0.0}]
        self.assertTrue(mins and maxs)
        self.assertEqual(len(mins) + len(maxs), len(entries))

    def test_saved_vectors_are_exactly_the_margin_nodes(self):
        nodes = {node for _, node, _, _ in self.meas}
        self.assertEqual(
            self.req["options"]["save_vectors"],
            sorted(f"v({node}{m.MARGIN_SUFFIX})" for node in nodes),
        )
        self.assertEqual(len(self.req["options"]["save_vectors"]), 22)

    def test_probe_request_drops_exclude(self):
        req = m.build_row_request(
            "tb.spice", self.tran, self.meas, [("tt", 27.0, 1.8)]
        )
        req.pop("exclude", None)
        self.assertNotIn("exclude", req)
        self.assertEqual(req["corners"]["process"], ["tt"])
        self.assertEqual(req["corners"]["temperature_c"], [27.0])


# --------------------------------------------------------------------------
# Report decoding
# --------------------------------------------------------------------------
def _fake_report(corner_specs: list[tuple[str, float, float, dict | None]]):
    """A minimal report shaped like `klt sim`'s: one corner per spec, each
    carrying a params row and a measurement list. A `None` measurement map
    renders the corner status `error`."""
    corners = []
    for proc, temp, vdd, values in corner_specs:
        corner = {
            "corner_id": f"{proc}/novdd/{temp:g}C/params:vdd_val={vdd:g}",
            "process": proc,
            "temperature_c": temp,
            "params": {m.VDD_PARAM: vdd},
            "status": "error" if values is None else "pass",
            "measurements": [
                {"name": name, "value": value}
                for name, value in (values or {}).items()
            ],
        }
        corners.append(corner)
    return {"status": "pass", "corners": corners}


def _nominal_margins() -> dict:
    """Every check at its expected bit: margin +0.9 for expected 1, -0.9
    for expected 0 -- the shape of a clean nominal corner."""
    return {
        name: (0.9 if bit == 1 else -0.9)
        for name, bit in m.EXPECTED_BITS.items()
    }


class TestDecodeRowReport(unittest.TestCase):
    def test_clean_corner_passes_with_runner_bit_rule(self):
        points, ok = m.decode_row_report(
            _fake_report([("tt", 27.0, 1.8, _nominal_margins())])
        )
        self.assertTrue(ok)
        self.assertEqual(len(points), 1)
        p = points[0]
        self.assertEqual(p["corner_id"], "tt_27c_1.80v")
        self.assertTrue(p["all_pass"])
        self.assertAlmostEqual(p["worst_margin_v"], 0.9)
        for name, expected, margin, raw, passed in p["rows"]:
            self.assertTrue(passed)
            self.assertAlmostEqual(raw, margin + 0.5 * 1.8)

    def test_wrong_bit_fails(self):
        bad = _nominal_margins()
        bad["dout0_c1"] = -0.9  # expected 1, reads as 0
        _points, ok = m.decode_row_report(
            _fake_report([("tt", 27.0, 1.8, bad)])
        )
        self.assertFalse(ok)

    def test_missing_measurement_fails_that_corner(self):
        bad = _nominal_margins()
        del bad["phb3_c1"]
        points, ok = m.decode_row_report(
            _fake_report([("tt", 27.0, 1.8, bad)])
        )
        self.assertFalse(ok)
        self.assertFalse(points[0]["all_pass"])

    def test_errored_corner_reports_missing_never_zero(self):
        points, ok = m.decode_row_report(
            _fake_report([("ss", 27.0, 1.8, None)])
        )
        self.assertFalse(ok)
        self.assertFalse(points[0]["all_pass"])
        self.assertTrue(all(margin is None for _, _, margin, _, _ in points[0]["rows"]))

    def test_supply_comes_from_the_params_axis(self):
        points, _ok = m.decode_row_report(
            _fake_report([
                ("tt", 27.0, 1.62, _nominal_margins()),
                ("tt", 27.0, 1.98, _nominal_margins()),
            ])
        )
        self.assertEqual(points[0]["corner_id"], "tt_27c_1.62v")
        self.assertEqual(points[1]["corner_id"], "tt_27c_1.98v")

    def test_error_envelope_refused(self):
        with self.assertRaises(ValueError):
            m.decode_row_report({"error": {"code": "batch_no_capacity"}})

    def test_binding_corner_is_the_tightest(self):
        tight = _nominal_margins()
        tight["phb1_c1"] = 0.8099
        points, _ok = m.decode_row_report(
            _fake_report([
                ("tt", 27.0, 1.8, _nominal_margins()),
                ("tt", 27.0, 1.62, tight),
            ])
        )
        binding = min(points, key=lambda p: p["worst_margin_v"])
        self.assertEqual(binding["corner_id"], "tt_27c_1.62v")


# --------------------------------------------------------------------------
# The hash checker classifies the envelope this run mints
# --------------------------------------------------------------------------
class TestHashCheckerSimClassification(unittest.TestCase):
    def test_sim_envelope_classified_sim(self):
        self.assertEqual(
            check_evidence_hashes.classify(
                {"schema_version": 3, "measurements": [], "corner_count": 9}
            ),
            "sim",
        )

    def test_yield_shape_still_classified_yield(self):
        self.assertEqual(
            check_evidence_hashes.classify(
                {
                    "schema_version": 3,
                    "measurements": [],
                    "measurement_count": 2,
                    "source": {"file": "x.json"},
                }
            ),
            "yield",
        )

    def test_sim_artifact_field_is_netlist(self):
        self.assertEqual(check_evidence_hashes.ARTIFACT_FIELD["sim"], "netlist")


if __name__ == "__main__":
    unittest.main()

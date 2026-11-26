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

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(SIM_DIR / "sar-sequencer-behavioral"))
sys.path.insert(0, str(SIM_DIR.parent / "signoff"))
sys.path.insert(0, str(SIM_DIR / "tests"))

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "run_testbench", SIM_DIR / "sar-sequencer-behavioral" / "run_testbench.py"
)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

import check_evidence_hashes  # noqa: E402
import provenance_fixture  # noqa: E402

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


class TestCornerIdentityAndFailureDiagnostics(unittest.TestCase):
    def test_missing_supply_is_refused_not_assumed_nominal(self):
        rep = _fake_report([("tt", 27.0, 1.62, _nominal_margins())])
        del rep["corners"][0]["params"][m.VDD_PARAM]
        with self.assertRaises(ValueError):
            m.decode_row_report(rep)

    def test_duplicate_corner_rejected_by_identity_check(self):
        pts, _ = m.decode_row_report(_fake_report([
            ("tt", 27.0, 1.8, _nominal_margins()),
            ("tt", 27.0, 1.8, _nominal_margins()),
        ]))
        why = m.check_corner_identities(
            pts, [("tt", 27.0, 1.8), ("tt", 27.0, 1.62)]
        )
        self.assertIsNotNone(why)
        self.assertIn("tt_27c_1.80v", why)
        self.assertIn("tt_27c_1.62v", why)

    def test_exact_grid_accepted(self):
        pts, _ = m.decode_row_report(_fake_report([
            (p, t, v, _nominal_margins()) for p, t, v in oat_grid()
        ]))
        self.assertIsNone(m.check_corner_identities(pts, oat_grid()))

    def test_empty_probe_report_is_refused(self):
        pts, _ = m.decode_row_report(
            {"status": "inconclusive", "corners": []}
        )
        self.assertIsNotNone(
            m.check_corner_identities(pts, [("tt", 27.0, m.NOMINAL_SUPPLY_V)])
        )

    def test_limit_failing_corner_keeps_its_readings(self):
        rep = _fake_report([("tt", 27.0, 1.8, _nominal_margins())])
        rep["corners"][0]["status"] = "fail"
        first = sorted(m.EXPECTED_BITS)[0]
        for meas in rep["corners"][0]["measurements"]:
            if meas["name"] == first:
                meas["value"] = -0.1 if m.EXPECTED_BITS[first] == 1 else 0.1
        pts, ok = m.decode_row_report(rep)
        self.assertFalse(ok)
        self.assertFalse(pts[0]["all_pass"])
        finite_rows = [r for r in pts[0]["rows"] if r[2] is not None]
        self.assertEqual(len(finite_rows), len(m.EXPECTED_BITS))
        self.assertAlmostEqual(pts[0]["worst_margin_v"], 0.1)
        self.assertEqual(len(m.failing_checks(pts)), 1)

    def test_binding_is_order_independent_with_a_nan_corner(self):
        failed = _fake_report([("ff", 27.0, 1.8, None)])["corners"]
        good = _fake_report([("tt", 27.0, 1.62, _nominal_margins())])["corners"]
        for order in (failed + good, good + failed):
            pts, _ = m.decode_row_report({"corners": order})
            self.assertEqual(m.binding_point(pts)["corner_id"], "tt_27c_1.62v")

    def test_no_finite_margin_gives_no_binding(self):
        pts, _ = m.decode_row_report(_fake_report([("ff", 27.0, 1.8, None)]))
        self.assertIsNone(m.binding_point(pts))


class TestWorkerEnvironment(unittest.TestCase):
    class _Prov:
        pdk_line = "sky130A @ hostpdk"
        ng_version = "ngspice-47"

    def _report(self, pdk, ng):
        return {"environment": {"remote": {
            "job_id": "j1",
            "worker_environment": {
                "pdk": {"variant": "sky130A", "stamp_text": f"x {pdk}"},
                "simulator": {"version_banner": f"** {ng} : Circuit level"},
            },
        }}}

    def test_worker_values_win_over_host(self):
        pdk, ng, notes = m.worker_environment(
            self._report("c6d73a3", "ngspice-46"), self._Prov
        )
        self.assertEqual((pdk, ng, notes), ("sky130A @ c6d73a3", "ngspice-46", []))

    def test_fallback_is_labelled(self):
        pdk, ng, notes = m.worker_environment({}, self._Prov)
        self.assertEqual((pdk, ng), ("sky130A @ hostpdk", "ngspice-47"))
        self.assertEqual(len(notes), 2)
        self.assertTrue(all("FALLBACK" in n for n in notes))


# --------------------------------------------------------------------------
# The record's Environment headlines (issue #1096)
# --------------------------------------------------------------------------
FROM_WORKER = " (executing worker)"
FROM_SUBMITTING_HOST = (
    " (submitting host; no single executing-worker value reported)"
)


def _batch_report(pdk: str | None, ng: str | None) -> dict:
    """A passing nine-point row report from one batch job whose worker
    reported `pdk` / `ng`; either may be None (not reported)."""
    report = _fake_report(
        [(proc, temp, vdd, _nominal_margins()) for proc, temp, vdd in oat_grid()]
    )
    worker = {}
    if pdk:
        worker["pdk"] = {"variant": "sky130A", "stamp_text": f"x {pdk}"}
    if ng:
        worker["simulator"] = {"version_banner": f"** {ng} : Circuit level"}
    report["environment"] = {
        "backend": "batch",
        "remote": {"job_id": "j1", "worker_environment": worker},
    }
    return report


def _headlines(record: str) -> list[str]:
    return [
        ln for ln in record.splitlines()
        if ln.startswith(("- PDK: ", "- ngspice: "))
    ]


class TestRecordEnvironmentAttribution(unittest.TestCase):
    """The record's `- PDK:` / `- ngspice:` lines say whose value each is.
    `worker_environment()` falls back to the submitting host per FIELD, so
    each line is labelled on its own -- asserted on the record the real
    `--klt-row-evidence --record` writer writes, not on a helper."""

    def _record(self, report: dict) -> str:
        """Run the real writer over `report` -- toolchain preflight, DUT
        netlisting and the `klt sim` submit stubbed, provenance under the
        shared fixture -- and return the record it wrote."""
        with tempfile.TemporaryDirectory() as tmp, \
                provenance_fixture.fake_provenance(m, tmp), \
                mock.patch.object(m.toolchain, "preflight", return_value=None), \
                mock.patch.object(m, "netlist_dut_klt", return_value="* stub DUT\n"), \
                mock.patch.object(m.klt_sim, "submit", return_value=report), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.run_row_evidence_campaign(record=True, quiet=True), 0)
            return (Path(tmp) / "records"
                    / f"{provenance_fixture.RECORD_ID}.md").read_text()

    def test_worker_reported_both_lines_unchanged(self):
        self.assertEqual(
            _headlines(self._record(_batch_report("c6d73a3", "ngspice-46"))),
            ["- PDK: sky130A @ c6d73a3" + FROM_WORKER,
             "- ngspice: ngspice-46" + FROM_WORKER],
        )

    def test_worker_reported_neither_lines_are_the_submitting_hosts(self):
        record = self._record(_batch_report(None, None))
        self.assertEqual(
            _headlines(record),
            ["- PDK: " + provenance_fixture.PDK_LINE + FROM_SUBMITTING_HOST,
             "- ngspice: " + provenance_fixture.NG_VERSION + FROM_SUBMITTING_HOST],
        )
        self.assertNotIn("(executing worker)", "\n".join(_headlines(record)))
        self.assertIn("- Environment fallback: PDK: ", record)
        self.assertIn(
            f"FALLBACK to the submitting host's {provenance_fixture.PDK_LINE}", record
        )

    def test_worker_value_equal_to_the_hosts_is_still_the_workers(self):
        self.assertEqual(
            _headlines(self._record(_batch_report("testing", "ngspice-46"))),
            ["- PDK: " + provenance_fixture.PDK_LINE + FROM_WORKER,
             "- ngspice: " + provenance_fixture.NG_VERSION + FROM_WORKER],
        )

    def test_worker_reported_one_each_line_labelled_on_its_own(self):
        host = provenance_fixture.PDK_LINE
        ng = provenance_fixture.NG_VERSION
        for pdk, sim, expected in [
            ("c6d73a3", None,
             ["- PDK: sky130A @ c6d73a3" + FROM_WORKER,
              "- ngspice: " + ng + FROM_SUBMITTING_HOST]),
            (None, "ngspice-46",
             ["- PDK: " + host + FROM_SUBMITTING_HOST,
              "- ngspice: ngspice-46" + FROM_WORKER]),
        ]:
            with self.subTest(pdk=pdk, ngspice=sim):
                self.assertEqual(
                    _headlines(self._record(_batch_report(pdk, sim))), expected
                )


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

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
import shutil
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


# --------------------------------------------------------------------------
# Issue #811: the same run written as the SUPERSEDING record of an earlier
# corner record of this campaign
# --------------------------------------------------------------------------
OLD_RECORD = "20260827-211956-e13bc1e"
_OLD_FAMILY = SIM_DIR / "sar-sequencer-behavioral"
OLD_RECORD_PATH = _OLD_FAMILY / "records" / f"{OLD_RECORD}.md"
OLD_SNAPSHOT_PATH = _OLD_FAMILY / "netlist-snapshots" / f"{OLD_RECORD}.spice"
WORKER_DIGEST = (
    "39ca1adb826660324c3626f72bd946ec40704f0f3fc8e243c623f76e24b3eee2"
)
CLIENT_DIGEST = (
    "e12148baf532d879d2e2053cecc5b498680bd4156a0dc3f69ce4f83e741e1314"
)
COMPARISON_HEADING = (
    f"## Comparison with the superseded record (`{OLD_RECORD}`, issue #811)"
)
FLEET_RECORD = "20261126-113902-4f1b0b9c"
# A distinguishable archived input for tests that run in shallow CI checkouts.
REPLAY_FRAGMENT = FRAGMENT.replace("1570.1n {vdd_val}", "1570.1n 0.00")


def _flat_margins(margin: float) -> dict:
    """Every check reading `margin` from half the rail on its expected side."""
    return {
        name: (margin if bit == 1 else -margin)
        for name, bit in m.EXPECTED_BITS.items()
    }


def _superseding_report(per_corner: dict[str, float] | None = None,
                        digest=WORKER_DIGEST) -> dict:
    """A passing nine-point row report from one batch job whose worker
    reported the target pin, ngspice-47 and `digest` (`None` leaves the
    worker-hash capture out entirely)."""
    grid = oat_grid()
    per_corner = per_corner or {}
    by_id = {}
    for proc, temp, vdd in grid:
        cid = m.corners_mod.corner_id(proc, temp, vdd)
        by_id[cid] = _flat_margins(per_corner.get(cid, 0.9))
    report = _fake_report([(proc, temp, vdd, by_id[m.corners_mod.corner_id(proc, temp, vdd)])
                           for proc, temp, vdd in grid])
    engine = {"remote": {"job_id": "j1", "worker_environment": {
        "pdk": {"variant": "sky130A", "stamp_text": "x f6eeac7"},
        "simulator": {"version_banner": "** ngspice-47 : Circuit level"},
    }},
        # the submitting client's own build, preserved apart from the
        # worker's by klayout-tools#7356
        "client_engine_build": {"probe": "ok", "binary_sha256": CLIENT_DIGEST},
    }
    if digest is not None:
        engine["engine_host"] = "worker"
        engine["engine_build"] = {"probe": "ok", "binary_sha256": digest,
                                  "reason": None}
    report["environment"] = engine
    report["provenance"] = {"klt_version": "0.9.3.devtest"}
    report["corners"][0]["runner_klt_version"] = "0.9.0"
    report["environment"]["remote"].update(
        runner_klt_version="0.9.0", client_klt_version="0.9.3.devtest",
        runner_compatibility="compatible",
    )
    return report


class TestParseCornerSummary(unittest.TestCase):
    def test_reads_the_real_superseded_record(self):
        old = m.parse_corner_summary(OLD_RECORD_PATH.read_text())
        self.assertEqual(len(old), 9)
        self.assertEqual(old["tt_27c_1.62v"], ("PASS", 0.8099))
        self.assertEqual(old["tt_27c_1.98v"], ("PASS", 0.99))
        self.assertTrue(all(v == "PASS" for v, _ in old.values()))

    def test_a_fail_row_and_a_negative_margin_parse(self):
        old = m.parse_corner_summary(
            "| corner-id | all checks correct? | worst digital margin (V) |\n"
            "|---|---|---|\n"
            "| `tt_27c_1.62v` | FAIL | -0.0000 |\n"
        )
        self.assertEqual(old, {"tt_27c_1.62v": ("FAIL", -0.0)})

    def test_a_record_without_the_table_compares_nothing(self):
        self.assertEqual(m.parse_corner_summary("# Record X\n\nno table\n"), {})

    def test_the_per_check_table_is_not_mistaken_for_the_summary(self):
        """The per-check rows carry a bit and a voltage, not a verdict; only
        the per-corner summary's `(verdict, margin)` shape is read."""
        text = (
            "| check | expected (bit) | measured (V) | pass/fail |\n"
            "|---|---|---|---|\n"
            "| `dout0_c1` | 1 | 1.6200 | PASS |\n"
            "| `tt_27c_1.62v` | PASS | 0.8099 |\n"
        )
        self.assertEqual(
            m.parse_corner_summary(text), {"tt_27c_1.62v": ("PASS", 0.8099)}
        )


class TestArchivedFragment(unittest.TestCase):
    def test_reads_the_tree_that_added_the_record(self):
        commit = "1234" * 10
        with mock.patch.object(m.klt_sim, "default_runner", side_effect=[
            (0, f"{commit} parent\n", ""), (0, REPLAY_FRAGMENT, "")
        ]) as git:
            fragment, source = m.archived_fragment(OLD_RECORD)
        self.assertEqual(fragment, REPLAY_FRAGMENT)
        lookup, show = (call.args[0] for call in git.call_args_list)
        self.assertIn("--diff-filter=A", lookup)
        self.assertEqual(lookup[-1], f"sim/sar-sequencer-behavioral/records/{OLD_RECORD}.md")
        self.assertEqual(source, f"{commit}:sim/sar-sequencer-behavioral/testbench/{m.FRAGMENT.name}")
        self.assertEqual(show[-2:], ["show", source])

    def test_shallow_boundary_cannot_identify_the_archived_fragment(self):
        with mock.patch.object(m.klt_sim, "default_runner", return_value=(0, "abc\n", "")):
            with self.assertRaisesRegex(ValueError, "fetch its git history"):
                m.archived_fragment(OLD_RECORD)


class TestSupersedingRecord(unittest.TestCase):
    """The real `--klt-row-evidence --record --supersedes <id>` writer, with
    toolchain preflight, DUT netlisting, the `klt sim` submit and git
    stubbed; the superseded record and its DUT snapshot are this campaign's
    real committed August pair, copied into the fixture experiment dir."""

    STUB_DUT = "* stub DUT\nX1 a b cell\nX2 c d cell\n"

    def _record(self, report: dict, supersedes: str = OLD_RECORD) -> tuple[str, int]:
        with tempfile.TemporaryDirectory() as tmp, \
                provenance_fixture.fake_provenance(m, tmp), \
                mock.patch.object(m.toolchain, "preflight", return_value=None), \
                mock.patch.object(m, "netlist_dut_klt", return_value=self.STUB_DUT), \
                mock.patch.object(m.klt_sim, "submit", return_value=report), \
                mock.patch.object(m, "archived_fragment", return_value=(REPLAY_FRAGMENT, "test-revision:fragment")) as archive, \
                contextlib.redirect_stdout(io.StringIO()):
            (Path(tmp) / "records").mkdir()
            (Path(tmp) / "netlist-snapshots").mkdir()
            (Path(tmp) / "records" / f"{OLD_RECORD}.md").write_bytes(
                OLD_RECORD_PATH.read_bytes())
            (Path(tmp) / "netlist-snapshots" / f"{OLD_RECORD}.spice").write_bytes(
                OLD_SNAPSHOT_PATH.read_bytes())
            if supersedes == FLEET_RECORD:
                for path in (f"records/{FLEET_RECORD}.md", f"netlist-snapshots/{FLEET_RECORD}.spice",
                             f"corners/{FLEET_RECORD}/report.json", f"corners/{FLEET_RECORD}/request/tb.spice",
                             f"corners/{FLEET_RECORD}/request/request.json"):
                    dest = Path(tmp) / path
                    dest.parent.mkdir(exist_ok=True, parents=True)
                    shutil.copyfile(_OLD_FAMILY / path, dest)
            rc = m.run_row_evidence_campaign(
                record=True, quiet=True, supersedes=supersedes
            )
            inputs = Path(tmp) / "corners" / provenance_fixture.RECORD_ID / "request"
            self.body = (inputs / "tb.spice").read_text()
            self.request = json.loads((inputs / "request.json").read_text())
            record = (Path(tmp) / "records"
                      / f"{provenance_fixture.RECORD_ID}.md").read_text()
            self.fragment_reads = archive.call_count
            return record, rc

    def _comparison_rows(self, record: str) -> list[str]:
        section = record.split(COMPARISON_HEADING, 1)[1].split("\n### ", 1)[0]
        return [ln for ln in section.splitlines() if ln.startswith("| `")]

    def test_the_footer_and_the_claim_name_the_predecessor(self):
        record, rc = self._record(_superseding_report())
        self.assertEqual(rc, 0)
        self.assertIn(f"- **Supersedes**: {OLD_RECORD}", record)
        self.assertNotIn("supersedes nothing", record)
        self.assertIn(COMPARISON_HEADING, record)

    def test_record_link_resolves_the_same_inputs(self):
        link = f"[`records/{OLD_RECORD}.md`]({OLD_RECORD}.md)"
        record, rc = self._record(_superseding_report(), supersedes=link)
        self.assertEqual(rc, 0)
        self.assertIn(f"- **Supersedes**: {link}", record)
        self.assertIn(COMPARISON_HEADING, record)

    def test_old_new_and_delta_per_corner_at_the_printed_precision(self):
        record, _rc = self._record(_superseding_report(
            {"tt_27c_1.62v": 0.81, "tt_27c_1.98v": 0.98}
        ))
        rows = self._comparison_rows(record)
        self.assertEqual(len(rows), 9)
        self.assertIn("| `tt_27c_1.80v` | PASS | PASS | 0.9000 | 0.9000 | +0.0000 |", rows)
        self.assertIn("| `fs_27c_1.80v` | PASS | PASS | 0.8999 | 0.9000 | +0.0001 |", rows)
        self.assertIn("| `tt_27c_1.62v` | PASS | PASS | 0.8099 | 0.8100 | +0.0001 |", rows)
        self.assertIn("| `tt_27c_1.98v` | PASS | PASS | 0.9900 | 0.9800 | -0.0100 |", rows)

    def test_the_campaign_tolerance_is_stated_as_its_binary_verdict(self):
        record, _rc = self._record(_superseding_report())
        section = record.split(COMPARISON_HEADING, 1)[1].split("\n### ", 1)[0]
        self.assertIn("35 checks", section)
        self.assertIn("informational", section)
        self.assertIn(
            "- **Verdict agreement**: 9/9 corners read the same verdict in "
            "both records (PASS there, PASS here).",
            section,
        )

    def test_a_changed_verdict_is_named_and_the_fail_is_kept(self):
        bad = _flat_margins(0.9)
        bad["dout0_c1"] = -0.9  # expected 1: this corner now reads a wrong bit
        report = _superseding_report()
        for corner in report["corners"]:
            if corner["process"] == "tt" and corner["params"][m.VDD_PARAM] == 1.62:
                corner["measurements"] = [
                    {"name": n, "value": v} for n, v in bad.items()]
                corner["status"] = "fail"
        record, rc = self._record(report)
        self.assertEqual(rc, 1)
        self.assertIn(
            "| `tt_27c_1.62v` | PASS | FAIL | 0.8099 | 0.9000 | +0.0901 |", record
        )
        self.assertIn("- **Overall**: FAIL (8/9 corners fully correct)", record)
        self.assertIn("`tt_27c_1.62v`", record.split("**Verdict agreement**", 1)[1]
                      .split("\n", 1)[0])

    def test_differences_from_the_predecessor_are_read_not_transcribed(self):
        record, _rc = self._record(_superseding_report())
        diffs = record.split("### Differences from the superseded record", 1)[1]
        # its own Environment block
        self.assertIn("sky130A @ c6d73a35f524070e85faff4a6a9eef49553ebc2b", diffs)
        self.assertIn("ngspice-46", diffs)
        # here: the executing worker's values
        self.assertIn("sky130A @ f6eeac7", diffs)
        self.assertIn("ngspice-47", diffs)
        self.assertIn(f"`{WORKER_DIGEST}`", diffs)
        self.assertIn("no binary digest recorded", diffs)
        self.assertIn("half-rail bit rule to raw node samples", diffs)
        self.assertIn("36 instance cards", diffs)
        self.assertIn("test-revision:fragment", diffs)
        self.assertNotIn("netlisted fresh", record)
        self.assertEqual(m.instance_cards(self.body), m.instance_cards(OLD_SNAPSHOT_PATH.read_text()))
        self.assertIn("1570.1n 0.00", self.body)
        self.assertNotIn("1570.1n {vdd_val}", self.body)

    def test_fleet_predecessor_replays_its_inputs_and_reports_its_own_worker(self):
        record, rc = self._record(_superseding_report(), supersedes=FLEET_RECORD)
        self.assertEqual(rc, 0)
        archive = _OLD_FAMILY / "corners" / FLEET_RECORD
        report = json.loads((archive / "report.json").read_text())
        digest = report["environment"]["engine_build"]["binary_sha256"]
        diffs = record.split("### Differences from the superseded record", 1)[1]
        self.assertIn(f"there (executing ngspice binary sha256 (worker): `{digest}`)", diffs)
        self.assertIn("previously klt sim graded signed half-rail margins", diffs)
        self.assertNotIn("raw node samples", diffs)
        self.assertEqual(self.body, (archive / "request/tb.spice").read_text())
        self.assertEqual(self.request, json.loads((archive / "request/request.json").read_text()))
        self.assertEqual(self.fragment_reads, 0)

    def test_a_missing_worker_digest_is_stated_as_unmet(self):
        record, _rc = self._record(_superseding_report(digest=None))
        self.assertIn(
            "- executing ngspice binary sha256 (worker): NOT REPORTED by the "
            "batch report (`environment.engine_build.binary_sha256` is absent "
            "or null) -- the worker-hash provenance condition is NOT met",
            record,
        )
        self.assertNotIn(WORKER_DIGEST, record)

    def test_the_missing_digest_never_falls_back_to_the_clients_own_build(self):
        """Same banner, different executable: the submitting client's digest
        is preserved beside a null worker digest and must stay the client's."""
        record, _rc = self._record(_superseding_report(digest=None))
        self.assertIn("NOT REPORTED by the batch report", record)
        self.assertNotIn(f"sha256 (worker): `{CLIENT_DIGEST}`", record)
        self.assertNotIn(f"binary sha256 (worker): `{CLIENT_DIGEST}`", record)

    def test_the_client_digest_is_labelled_as_the_non_executor(self):
        record, _rc = self._record(_superseding_report())
        self.assertIn(
            "- submitting client ngspice binary sha256 (not the executor): "
            f"`{CLIENT_DIGEST}`",
            record,
        )
        self.assertNotIn(f"(worker): `{CLIENT_DIGEST}`", record)

    def test_no_client_build_in_the_report_no_client_line(self):
        report = _superseding_report()
        del report["environment"]["client_engine_build"]
        record, _rc = self._record(report)
        self.assertNotIn("submitting client ngspice binary sha256", record)
        self.assertIn(f"- executing ngspice binary sha256 (worker): `{WORKER_DIGEST}`", record)

    def test_the_worker_digest_line_is_written_whether_or_not_it_supersedes(self):
        record, _rc = self._record(_superseding_report(), supersedes="")
        self.assertIn(
            f"- executing ngspice binary sha256 (worker): `{WORKER_DIGEST}`",
            record,
        )
        self.assertNotIn(COMPARISON_HEADING, record)
        self.assertIn("supersedes nothing", record)
        self.assertEqual(self.fragment_reads, 0)

    def test_invalid_predecessor_fails_before_submission_and_publication(self):
        for problem in ("missing", "bad summary", "missing corner", "bad snapshot", "missing stimulus", "typo"):
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as tmp, \
                    provenance_fixture.fake_provenance(m, tmp), \
                    mock.patch.object(m.toolchain, "preflight", return_value=None), \
                    mock.patch.object(m.klt_sim, "submit") as submit, \
                    mock.patch.object(m, "archived_fragment", side_effect=ValueError("missing git history")), \
                    contextlib.redirect_stderr(io.StringIO()) as error:
                records = Path(tmp) / "records"
                records.mkdir()
                latest = records / "LATEST"
                latest.write_text("previous.md\n")
                snapshots = Path(tmp) / "netlist-snapshots"
                snapshots.mkdir()
                if problem != "missing":
                    text = OLD_RECORD_PATH.read_text()
                    if problem == "bad summary":
                        text = text.replace("| PASS |", "| unreadable |")
                    if problem == "missing corner":
                        text = text.replace("tt_27c_1.62v", "tt_27c_1.44v")
                    (records / OLD_RECORD_PATH.name).write_text(text)
                    (snapshots / OLD_SNAPSHOT_PATH.name).write_text(
                        "wrong DUT" if problem == "bad snapshot" else OLD_SNAPSHOT_PATH.read_text())
                predecessor = f"{OLD_RECORD}-typo" if problem == "typo" else OLD_RECORD
                rc = m.run_row_evidence_campaign(record=True, quiet=True, supersedes=predecessor)
                self.assertNotEqual(rc, 0)
                self.assertIn(predecessor, error.getvalue())
                submit.assert_not_called()
                self.assertFalse((Path(tmp) / "corners").exists())
                self.assertFalse((records / f"{provenance_fixture.RECORD_ID}.md").exists())
                self.assertEqual(latest.read_text(), "previous.md\n")


if __name__ == "__main__":
    unittest.main()

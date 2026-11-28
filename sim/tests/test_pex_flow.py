"""Unit coverage for layout/bin/pex_flow.py's shared PEX helpers."""

import dataclasses
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "layout" / "bin"))

import pex_flow

FAKE_PDK = pex_flow.pdk.PdkInfo(
    root=Path("/pdkroot"),
    variant="sky130A",
    variant_dir=Path("/pdkroot/sky130A"),
    ngspice_lib=Path("/pdkroot/sky130A/libs.tech/combined/sky130.lib.spice"),
    open_pdks_commit_expected="0" * 40,
    found=True,
)


class CornerIdTests(unittest.TestCase):
    def test_bare_vdd(self):
        self.assertEqual(
            pex_flow.parse_corner_id("tt/1.620V/-40C"), ("tt", -40, {"vdd": 1.62})
        )

    def test_named_supplies(self):
        self.assertEqual(
            pex_flow.parse_corner_id("ff/vcm=0.900_vdd=1.800V/27C"),
            ("ff", 27, {"vcm": 0.9, "vdd": 1.8}),
        )

    def test_malformed_supply_is_rejected(self):
        for supplies in ("missing", "vcm=0.900_vdd=bad", "1.620junk", "vdd=1.8_vdd=1.62"):
            with self.subTest(supplies=supplies), self.assertRaises(pex_flow.PexFlowError):
                pex_flow.parse_corner_id(f"tt/{supplies}V/27C")


class RatifiedOatPointsTests(unittest.TestCase):
    def test_nine_point_star_with_center_and_oat_legs(self):
        pts = pex_flow.ratified_oat_points({})
        self.assertEqual(len(pts), 9)
        rails = {(p.process, p.temp_c, p.supply_v) for p in pts}
        self.assertIn(("tt", 27.0, 1.8), rails)
        for proc in ("ss", "ff", "sf", "fs"):
            self.assertIn((proc, 27.0, 1.8), rails)
        for temp in (-40.0, 125.0):
            self.assertIn(("tt", temp, 1.8), rails)
        for v in (1.62, 1.98):
            self.assertIn(("tt", 27.0, v), rails)

    def test_rail_always_present_under_vdd(self):
        for p in pex_flow.ratified_oat_points({}):
            self.assertEqual(p.supply_sources["vdd"], p.supply_v)

    def test_paired_sources_track_their_rail_in_order(self):
        pts = pex_flow.ratified_oat_points(
            {"vinp": lambda v: round(v / 2, 6), "vinn": lambda v: round(v / 2 - 0.005, 6)}
        )
        for p in pts:
            self.assertEqual(list(p.supply_sources), ["vdd", "vinp", "vinn"])
            self.assertEqual(p.supply_sources["vinp"], round(p.supply_v / 2, 6))
            self.assertEqual(p.supply_sources["vinn"], round(p.supply_v / 2 - 0.005, 6))


class NetTableTests(unittest.TestCase):
    EXTRACT_JSON = {
        "parasitics": {
            "nets": [
                {
                    "net": "OUTP",
                    "resistance_ohm": 12.5,
                    "capacitance_ff": 1.25,
                    "coupled": [
                        {"capacitance_ff": 0.5},
                        {"capacitance_ff": 0.25},
                    ],
                },
                {"net": "OUTN", "resistance_ohm": 13.0, "capacitance_ff": 2.0},
                {"net": "VDD", "resistance_ohm": 0.1, "capacitance_ff": 100.0},
            ]
        }
    }

    def test_wanted_nets_with_and_without_coupled_terms(self):
        table = pex_flow.net_table(self.EXTRACT_JSON, {"OUTP", "OUTN"})
        self.assertEqual(set(table), {"OUTP", "OUTN"})
        self.assertEqual(
            table["OUTP"],
            {
                "r_ohm": 12.5,
                "c_ground_ff": 1.25,
                "c_coupled_total_ff": 0.75,
                "c_total_ff": 2.0,
            },
        )
        self.assertEqual(
            table["OUTN"],
            {
                "r_ohm": 13.0,
                "c_ground_ff": 2.0,
                "c_coupled_total_ff": 0,
                "c_total_ff": 2.0,
            },
        )

    def test_escaped_net_names_are_matched_after_unescaping(self):
        extract_json = {
            "parasitics": {
                "nets": [
                    {
                        "net": "\\OUT_P\\",
                        "resistance_ohm": 1.0,
                        "capacitance_ff": 3.0,
                    }
                ]
            }
        }
        table = pex_flow.net_table(extract_json, {"OUT_P"})
        self.assertEqual(set(table), {"OUT_P"})
        self.assertEqual(table["OUT_P"]["c_total_ff"], 3.0)

    def test_absent_wanted_net_is_simply_missing(self):
        self.assertEqual(pex_flow.net_table(self.EXTRACT_JSON, {"NOWHERE"}), {})


class KltPexArgvTests(unittest.TestCase):
    def test_shared_argv_pinned_deck_and_absolute_scratch_paths(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            argv = pex_flow.klt_pex_argv(
                "/abs/gds/cdac_array.gds",
                "pex_request.json",
                FAKE_PDK,
                work,
                extracted_name="pex-extracted.spice",
                outdir_name="pex",
                backend="batch",
            )
            self.assertEqual(
                argv,
                [
                    "pex",
                    "/abs/gds/cdac_array.gds",
                    "pex_request.json",
                    "--deck",
                    "sky130",
                    "--pdk",
                    "sky130A",
                    "--pdk-root",
                    "/pdkroot",
                    "-o",
                    str((work / ".klt" / "pex-extracted.spice").resolve()),
                    "--outdir",
                    str((work / ".klt" / "pex").resolve()),
                    "--backend",
                    "batch",
                ],
            )

    def test_scratch_names_carry_the_per_call_tag(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            argv = pex_flow.klt_pex_argv(
                Path("/abs/gds/comparator.gds"),
                "pex_request_zero.json",
                FAKE_PDK,
                work,
                extracted_name="pex-extracted-zero.spice",
                outdir_name="pex-zero",
                backend="local",
            )
            self.assertEqual(argv[2], "pex_request_zero.json")
            self.assertEqual(Path(argv[argv.index("-o") + 1]).name, "pex-extracted-zero.spice")
            self.assertEqual(Path(argv[argv.index("--outdir") + 1]).name, "pex-zero")
            self.assertEqual(argv[argv.index("--backend") + 1], "local")


class PexMainTests(unittest.TestCase):
    """The shared --check-env/--pilot/--record CLI driver (issue #1069):
    comparator's richer semantics, one copy for every block flow."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.block = Path(self.tmp.name) / "block"
        self.record = self.block / "reports" / "20260101-000000-aabbccdd"
        self.record.mkdir(parents=True)
        (self.record / "block.gds").write_text("gds")
        (self.block / "reports" / "LATEST").write_text("20260101-000000-aabbccdd\n")
        self.calls = []

    def fake_run(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return 42

    def pex_main(self, argv):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = pex_flow.pex_main(
                self.block,
                "block.gds",
                self.block / "reports",
                self.fake_run,
                tmp_prefix="xx-pex-pilot-",
                description="block PEX flow (issue #0)",
                argv=argv,
            )
        return rc, out.getvalue()

    def test_check_env_reports_found_and_latest_layout(self):
        with mock.patch.object(pex_flow.pdk, "resolve", return_value=FAKE_PDK), mock.patch.object(
            pex_flow, "klt_bin", return_value=Path("/bin/true")
        ):
            rc, out = self.pex_main(["--check-env"])
        self.assertEqual(rc, 0)
        self.assertIn("PDK: variant=sky130A root=/pdkroot found=True", out)
        self.assertIn("layout: reports/20260101-000000-aabbccdd/block.gds", out)
        self.assertEqual(self.calls, [])

    def test_check_env_missing_pdk_prints_error_and_returns_3(self):
        missing = dataclasses.replace(
            FAKE_PDK, found=False, error="no PDK variant directory at /pdkroot/sky130A"
        )
        with mock.patch.object(pex_flow.pdk, "resolve", return_value=missing), mock.patch.object(
            pex_flow, "klt_bin", return_value=Path("/bin/true")
        ):
            rc, out = self.pex_main(["--check-env"])
        self.assertEqual(rc, 3)
        self.assertIn("found=False", out)
        self.assertIn("  error: no PDK variant directory at /pdkroot/sky130A", out)
        self.assertEqual(self.calls, [])

    def test_pilot_and_record_are_mutually_exclusive(self):
        rc, out = self.pex_main(["--pilot", "--record"])
        self.assertEqual(rc, 2)
        self.assertEqual(self.calls, [])

    def test_no_mode_prints_help_and_returns_2(self):
        rc, out = self.pex_main([])
        self.assertEqual(rc, 2)
        self.assertIn("usage:", out)
        self.assertEqual(self.calls, [])

    def test_pilot_dispatches_local_backend_in_a_prefixed_tempdir(self):
        rc, _ = self.pex_main(["--pilot"])
        self.assertEqual(rc, 42)
        (args, kwargs) = self.calls[0]
        self.assertEqual(args[1], "local")
        self.assertTrue(args[0].name.startswith("xx-pex-pilot-"), args[0])
        self.assertEqual(kwargs, {"pilot": True, "record": False, "quiet": False})

    def test_pilot_quiet_is_forwarded(self):
        self.pex_main(["--pilot", "--quiet"])
        self.assertEqual(self.calls[0][1]["quiet"], True)

    def test_record_dispatches_batch_backend_into_a_new_record_id(self):
        with mock.patch.object(
            pex_flow.evidence, "new_record_id", return_value="20260102-000000-00000000"
        ):
            rc, _ = self.pex_main(["--record"])
        self.assertEqual(rc, 42)
        (args, kwargs) = self.calls[0]
        self.assertEqual(args[0], self.block / "reports" / "20260102-000000-00000000")
        self.assertEqual(args[1], "batch")
        self.assertEqual(kwargs, {"pilot": False, "record": True, "quiet": False})

    def test_record_backend_override_is_forwarded(self):
        with mock.patch.object(
            pex_flow.evidence, "new_record_id", return_value="20260102-000000-00000000"
        ):
            self.pex_main(["--record", "--backend", "weird"])
        self.assertEqual(self.calls[0][0][1], "weird")


class BuildPexRequestTests(unittest.TestCase):
    """The one `klt pex` request shape (issue #1107): pinned model library
    and OAT carve shared, analysis window / measures / timeout per block."""

    def test_block_specific_fields_ride_the_shared_shape(self):
        pts = pex_flow.ratified_oat_points({"vcm": lambda v: round(v / 2, 6)})
        meas = [
            {
                "name": "vtop_p_0",
                "spice": ".meas tran vtop_p_0 find v(top_0p) at=500n",
                "unit": "V",
            }
        ]
        req = pex_flow.build_pex_request(
            pts, analysis_args="0.5n 500n", measurements=meas, timeout_s=900
        )
        corners, exclude = pex_flow.build_corners_spec(pts)
        self.assertEqual(
            req,
            {
                "netlist": "testbench.spice",
                "engine": "ngspice",
                "models": {"pdk": "sky130A", "lib": "libs.tech/combined/sky130.lib.spice"},
                "corners": corners,
                "exclude": exclude,
                "analysis": {"kind": "tran", "args": "0.5n 500n"},
                "measurements": meas,
                "options": {"timeout_s": 900, "keep_artifacts": False},
            },
        )
        self.assertEqual(
            list(req),
            [
                "netlist",
                "engine",
                "models",
                "corners",
                "exclude",
                "analysis",
                "measurements",
                "options",
            ],
        )


class ExtractAndCheckInterfaceTests(unittest.TestCase):
    """Steps 1-2 of every block flow (issue #1107): extract the per-net
    table, archive the envelope, and fail on a pin-list drift before
    anything simulates."""

    ENVELOPE = {"status": "extracted", "device_count": 3, "net_count": 2}
    PINS = ["VINP", "VINN", "OUTP", "OUTN", "VDD", "VSS"]
    HINT = "Re-derive testbench.spice's Xdut line against the new pin list."

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)

    def extract(self, header: str, expected_pins=PINS) -> dict:
        def fake_run_klt(args, cwd, **kwargs):
            self.assertEqual(Path(cwd), self.work)
            self.assertEqual(args[0], "extract")
            self.assertEqual(args[1], "/abs/gds/block.gds")
            self.assertEqual(args[args.index("-o") + 1], "block.pex-extract.spice")
            (self.work / "block.pex-extract.spice").write_text(
                f"* klt extract --parasitics\n.SUBCKT {header}\nM1 D G S B nfet\n.ENDS\n"
            )
            return self.ENVELOPE

        with mock.patch.object(pex_flow, "run_klt", side_effect=fake_run_klt) as run_klt:
            out = pex_flow.extract_and_check_interface(
                Path("/abs/gds/block.gds"),
                self.work,
                "block.pex-extract.spice",
                FAKE_PDK,
                "blk",
                expected_pins,
                drift_hint=self.HINT,
                quiet=True,
            )
        self.assertEqual(run_klt.call_args.kwargs["quiet"], True)
        return out

    def test_matching_interface_archives_the_envelope_and_returns_it(self):
        out = self.extract("blk VINP VINN OUTP OUTN VDD VSS")
        self.assertEqual(out, self.ENVELOPE)
        archived = self.work / "extract.json"
        self.assertEqual(archived.read_text(), json.dumps(self.ENVELOPE, indent=2) + "\n")

    def test_klt_extracts_continuation_lines_join_into_the_pin_list(self):
        self.assertEqual(self.extract("blk VINP VINN OUTP OUTN\n+ VDD VSS"), self.ENVELOPE)

    def test_tuple_expectation_compares_equal_to_the_extracted_list(self):
        out = self.extract("blk VINP VINN OUTP OUTN VDD VSS", tuple(self.PINS))
        self.assertEqual(out, self.ENVELOPE)

    def test_drift_raises_with_both_interfaces_and_the_block_hint(self):
        for header in (
            "other VINP VINN OUTP OUTN VDD VSS",
            "blk VINP VINN OUTN OUTP VDD VSS",
            "blk VINP VINN OUTP OUTN VDD",
        ):
            with self.subTest(header=header), self.assertRaises(pex_flow.PexFlowError) as ctx:
                self.extract(header)
            text = str(ctx.exception)
            self.assertIn("extracted interface drifted", text)
            self.assertIn(f"  got .SUBCKT {header}\n", text)
            self.assertIn("  want .SUBCKT blk VINP VINN OUTP OUTN VDD VSS\n", text)
            self.assertTrue(text.endswith(self.HINT), text)
            self.assertTrue((self.work / "extract.json").is_file())


class RunPexStepTests(unittest.TestCase):
    """One `klt pex` call (issue #1107): request as run, submit, archive the
    response -- and the `.klt/` scratch subtree never outlives the call."""

    REQUEST = {"netlist": "testbench.spice", "corners": {"process": ["tt"]}}
    RESPONSE = {"status": "pass", "delta": []}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("PEX_CAPACITY_WAIT_S", None)

    def step(self, response=RESPONSE, **kwargs):
        seen = {}

        def fake_run_klt(args, cwd, **run_kwargs):
            seen["args"], seen["cwd"], seen["kwargs"] = list(args), cwd, run_kwargs
            (self.work / ".klt" / "pex").mkdir(parents=True, exist_ok=True)
            (self.work / ".klt" / "pex" / "ngspice.log").write_text("scratch\n")
            if isinstance(response, Exception):
                raise response
            return response

        with mock.patch.object(pex_flow, "run_klt", side_effect=fake_run_klt):
            out = pex_flow.run_pex_step(
                "/abs/gds/block.gds", self.REQUEST, self.work, FAKE_PDK, **kwargs
            )
        return out, seen

    def test_writes_request_submits_and_archives_the_response(self):
        os.environ["PEX_CAPACITY_WAIT_S"] = "600"
        out, seen = self.step(backend="batch")
        self.assertEqual(out, self.RESPONSE)
        self.assertEqual(seen["cwd"], self.work)
        self.assertEqual(seen["kwargs"], {"backend": "batch", "quiet": False})
        self.assertEqual(
            seen["args"],
            pex_flow.klt_pex_argv(
                "/abs/gds/block.gds",
                "pex_request.json",
                FAKE_PDK,
                self.work,
                extracted_name="pex-extracted.spice",
                outdir_name="pex",
                backend="batch",
            ),
        )
        self.assertEqual(
            json.loads((self.work / "pex_request.json").read_text()),
            {**self.REQUEST, "batch": {"capacity_wait_s": 600.0}},
        )
        self.assertEqual(json.loads((self.work / "pex.json").read_text()), self.RESPONSE)
        self.assertFalse((self.work / ".klt").exists())

    def test_tagged_names_carry_the_comparators_two_call_suffixes(self):
        out, seen = self.step(
            backend="batch",
            request_name="pex_request_cal.json",
            result_name="pex_cal.json",
            extracted_name="pex-extracted-cal.spice",
            outdir_name="pex-cal",
            quiet=True,
        )
        self.assertEqual(out, self.RESPONSE)
        self.assertEqual(seen["args"][2], "pex_request_cal.json")
        self.assertEqual(
            Path(seen["args"][seen["args"].index("-o") + 1]).name, "pex-extracted-cal.spice"
        )
        self.assertEqual(
            Path(seen["args"][seen["args"].index("--outdir") + 1]).name, "pex-cal"
        )
        self.assertEqual(seen["kwargs"], {"backend": "batch", "quiet": True})
        self.assertEqual(
            json.loads((self.work / "pex_request_cal.json").read_text()), self.REQUEST
        )
        self.assertEqual(json.loads((self.work / "pex_cal.json").read_text()), self.RESPONSE)

    def test_request_is_written_unchanged_without_the_capacity_wait_variable(self):
        self.step(backend="local")
        self.assertEqual(json.loads((self.work / "pex_request.json").read_text()), self.REQUEST)

    def test_failed_submit_removes_scratch_and_leaves_no_result_file(self):
        boom = pex_flow.PexFlowError("klt pex failed (exit 1):\nboom")
        with self.assertRaises(pex_flow.PexFlowError) as ctx:
            self.step(response=boom, backend="batch")
        self.assertIs(ctx.exception, boom)
        self.assertFalse((self.work / ".klt").exists())
        self.assertFalse((self.work / "pex.json").exists())
        self.assertEqual(json.loads((self.work / "pex_request.json").read_text()), self.REQUEST)

    def test_non_pass_status_is_returned_for_the_block_to_report(self):
        error = {"status": "error", "error": "corner tt failed"}
        out, _ = self.step(response=error, backend="batch")
        self.assertEqual(out, error)
        self.assertEqual(json.loads((self.work / "pex.json").read_text()), error)
        self.assertFalse((self.work / ".klt").exists())


class RenderProvenanceLinesTests(unittest.TestCase):
    """The record's `## Provenance` block (issue #1107): one copy, with the
    repo commit bullet every block's record cites (comparator's was the only
    one that did)."""

    EXTRACT_JSON = {
        "provenance": {
            "klt_version": "0.9.0",
            "klayout_version": "0.30.13",
            "pdk": {"name": "sky130A", "version": "open_pdks f6eeac7"},
            "deck": {"content_hash": "sha256:abc"},
        }
    }
    PEX_JSON = {
        "body_bias": {"status": "biased", "unbiased_device_count": 0},
        "extraction": {"model": {"capacitance": "net-to-ground"}},
    }
    BODY_BIAS = (
        "- `body_bias.status`: **biased** (0 unbiased PMOS body nets) -- checked before "
        "any number below is read; an anonymous body net would make the extracted leg's "
        "resimulation physically wrong, not merely imprecise"
    )

    def render(self, dirty=True, **overrides):
        git = pex_flow.evidence.GitInfo(commit="a" * 40, branch="feature/x", dirty=dirty)
        kwargs = dict(
            block_name="cdac-array",
            gds_name="cdac_array.gds",
            latest_id="20261027-193302-4433671f",
        )
        kwargs.update(overrides)
        with mock.patch.object(pex_flow.evidence, "git_info", return_value=git):
            return pex_flow.render_provenance_lines(self.EXTRACT_JSON, self.PEX_JSON, **kwargs)

    def test_block_is_a_heading_bullets_and_a_trailing_blank_line(self):
        lines = self.render()
        self.assertEqual(lines[:2], ["## Provenance", ""])
        self.assertEqual(lines[-1], "")
        self.assertTrue(all(line.startswith("- ") for line in lines[2:-1]), lines)

    def test_bullets_quote_the_envelopes_the_layout_source_and_the_body_bias_gate(self):
        lines = self.render()
        for bullet in (
            f"- {pex_flow.klt_version_note('0.9.0')}",
            "- KLayout engine: 0.30.13",
            "- PDK: sky130A (open_pdks f6eeac7)",
            "- Extraction deck content hash: `sha256:abc`",
            (
                "- layout source: `layout/cdac-array/reports/20261027-193302-4433671f/"
                "cdac_array.gds` (this flow only reads `reports/LATEST`, never moves it)"
            ),
            self.BODY_BIAS,
            "- `extraction.model` (klt pex's own scope note): capacitance = net-to-ground",
        ):
            self.assertIn(bullet, lines)
        self.assertFalse(any("Floating substrate net" in line for line in lines))

    def test_repo_commit_bullet_sits_between_the_deck_hash_and_the_layout_source(self):
        lines = self.render(dirty=True)
        commit = f"- repo commit: `{'a' * 40}` on `feature/x` (dirty)"
        self.assertEqual(lines.count(commit), 1)
        i = lines.index(commit)
        self.assertEqual(lines[i - 1], "- Extraction deck content hash: `sha256:abc`")
        self.assertTrue(lines[i + 1].startswith("- layout source: "))

    def test_clean_tree_is_reported_as_clean(self):
        lines = self.render(dirty=False)
        self.assertIn(f"- repo commit: `{'a' * 40}` on `feature/x` (clean)", lines)
        self.assertFalse(any("(dirty)" in line for line in lines))

    def test_block_specific_suffix_and_substrate_note_are_the_tails(self):
        suffix = (
            "This block's PFET bodies deliberately sit on BOOST_P/BOOST_N islands "
            "(DR-004/DR-007), which the extracted netlist resolves from the drawn wells."
        )
        note = "same condition as the CDAC record of this issue."
        lines = self.render(
            body_bias_suffix=suffix, vsubs_note=note, block_name="sampling-frontend"
        )
        self.assertIn(f"{self.BODY_BIAS}. {suffix}", lines)
        self.assertNotIn(self.BODY_BIAS, lines)
        self.assertEqual(lines[-2], f"- **Floating substrate net**: {note}")
        self.assertIn(
            "- layout source: `layout/sampling-frontend/reports/20261027-193302-4433671f/",
            "\n".join(lines),
        )


class RenderNetRcTableTests(unittest.TestCase):
    NETS = {
        "TOP_P": {
            "r_ohm": 210.11,
            "c_ground_ff": 136.6102,
            "c_coupled_total_ff": 6.2291,
            "c_total_ff": 142.8393,
        },
        "TOP_N": {
            "r_ohm": 210.3,
            "c_ground_ff": 136.6933,
            "c_coupled_total_ff": 0,
            "c_total_ff": 136.6933,
        },
    }

    def test_header_separator_and_one_row_per_net_in_the_callers_order(self):
        self.assertEqual(
            pex_flow.render_net_rc_table(self.NETS, ("TOP_N", "TOP_P")),
            [
                "| Net | R (ohm) | C to ground (fF) | C coupled, total (fF) | C total (fF) |",
                "|---|---|---|---|---|",
                "| TOP_N | 210.30 | 136.6933 | 0.0000 | 136.6933 |",
                "| TOP_P | 210.11 | 136.6102 | 6.2291 | 142.8393 |",
            ],
        )

    def test_net_absent_from_the_extraction_renders_a_zero_row(self):
        table = pex_flow.render_net_rc_table({"TOP_P": self.NETS["TOP_P"]}, ("TOP_N", "TOP_P"))
        self.assertEqual(table[2], "| TOP_N | 0.00 | 0.0000 | 0.0000 | 0.0000 |")
        self.assertEqual(table[3], "| TOP_P | 210.11 | 136.6102 | 6.2291 | 142.8393 |")

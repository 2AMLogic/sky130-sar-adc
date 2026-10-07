"""Unit tests for sim/sar-sequencer-behavioral/run_testbench.py (issue #557) --
expected-bit table, deck text generation and the `--corners` grid only; no
xschem, ngspice or installed PDK is needed (mirrors
sim/tests/test_run_handoff.py's PDK-free convention).

Mistakes these tests exist to catch, which yield a plausible-looking record
rather than an error: a drifted target-code table, a deck that silently drops
the requested PVT point or leaves a stray `.end`, and a hand-rolled corner grid
instead of `corners.ratified_oat_grid()`.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parent.parent
RUNNER = SIM_DIR / "sar-sequencer-behavioral" / "run_testbench.py"
sys.path.insert(0, str(SIM_DIR))

from harness import corners as corners_mod, pdk, toolchain  # noqa: E402

_spec = importlib.util.spec_from_file_location("run_sar_sequencer_behavioral_under_test", RUNNER)
rt = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rt
_spec.loader.exec_module(rt)

# Independently stated (not read from the runner): 811 and 212, b9..b0.
CODE1_BITS = "1100101011"
CODE2_BITS = "0011010100"
STDCELL_REL = Path("libs.ref") / "sky130_fd_sc_hd" / "spice" / "sky130_fd_sc_hd.spice"
SYNTH_DUT = (
    ".subckt sar_sequencer CLK RST_B\n"
    "x1 CLK RST_B sky130_fd_sc_hd__inv_1\n"
    ".ends\n"
    ".end\n"
)


def _pdk_info(root: Path, with_stdcell: bool = True) -> pdk.PdkInfo:
    variant_dir = root / "sky130A"
    if with_stdcell:
        f = variant_dir / STDCELL_REL
        f.parent.mkdir(parents=True)
        f.write_text("")
    return pdk.PdkInfo(
        root=root, variant="sky130A", variant_dir=variant_dir,
        ngspice_lib=variant_dir / "libs.tech" / "ngspice" / "sky130.lib.spice",
        xschem_rc=variant_dir / "libs.tech" / "xschem" / "xschemrc",
        open_pdks_commit_expected="synthetic", found=True,
    )


class TestExpectedBits(unittest.TestCase):
    def test_code_integers(self):
        self.assertEqual(int(CODE1_BITS, 2), 811)
        self.assertEqual(int(CODE2_BITS, 2), 212)

    def test_both_target_codes_pinned(self):
        for c, bits in ((1, CODE1_BITS), (2, CODE2_BITS)):
            for i, ch in enumerate(bits):
                with self.subTest(cycle=c, bit=9 - i):
                    self.assertEqual(rt.EXPECTED_BITS[f"dout{9 - i}_c{c}"], int(ch))

    def test_phase_and_eoc_expectations(self):
        labels = [f"b{b}" for b in range(9, -1, -1)] + ["eoc"]
        for lab in labels + ["sample"]:
            self.assertEqual(rt.EXPECTED_BITS[f"ph{lab}_c1"], 1)
        self.assertEqual(rt.EXPECTED_BITS["phb9_c2"], 1)
        self.assertEqual(rt.EXPECTED_BITS["pheoc_c2"], 1)
        self.assertNotIn("phsample_c2", rt.EXPECTED_BITS)
        self.assertNotIn("phb8_c2", rt.EXPECTED_BITS)

    def test_early_msb(self):
        self.assertEqual(rt.EXPECTED_BITS["dout9_early_c1"], 1)

    def test_exact_name_set_matches_committed_fragment(self):
        meas = set(re.findall(r"^\.meas tran (\w+) ", rt.FRAGMENT.read_text(), re.M))
        self.assertEqual(set(rt.EXPECTED_BITS), meas)
        self.assertEqual(len(meas), 12 + 10 + 1 + 2 + 10)


class TestAssembleDeck(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_non_default_pvt_and_paths(self):
        info = _pdk_info(self.root)
        deck = rt.assemble_deck(SYNTH_DUT, info, "ss", -40.0, 1.62)
        lines = deck.splitlines()
        self.assertIn(f".lib {info.ngspice_lib} ss", lines)
        self.assertIn(".temp -40.0", lines)
        self.assertIn(".param vdd_val = 1.62", lines)
        self.assertIn(f".include {info.variant_dir / STDCELL_REL}", lines)
        self.assertIn("* corner=ss temp=-40.0C supply=1.62V", lines)

    def test_defaults_are_nominal(self):
        deck = rt.assemble_deck(SYNTH_DUT, _pdk_info(self.root))
        self.assertIn(" tt\n", deck)
        self.assertIn(".temp 27.0\n", deck)
        self.assertIn(".param vdd_val = 1.8\n", deck)

    def test_stimulus_and_measurements_from_committed_fragment(self):
        deck = rt.assemble_deck(SYNTH_DUT, _pdk_info(self.root))
        fragment = rt.FRAGMENT.read_text()
        self.assertIn(fragment, deck)
        for token in ("VCLK CLK 0 PULSE", "VRSTB RST_B 0 PWL", "VCOMP COMP_OUT 0 PWL", ".tran 0.5n 2700n"):
            self.assertIn(token, deck)
        for name in rt.EXPECTED_BITS:
            self.assertRegex(deck, rf"(?m)^\.meas tran {name} find ")

    def test_single_final_end_and_dut_kept(self):
        deck = rt.assemble_deck(SYNTH_DUT, _pdk_info(self.root))
        ends = [i for i, ln in enumerate(deck.splitlines()) if ln.strip() == ".end"]
        self.assertEqual(len(ends), 1)
        self.assertEqual(deck.rstrip("\n").splitlines()[-1], ".end")
        self.assertIn(".subckt sar_sequencer CLK RST_B", deck)
        self.assertIn(".ends", deck)
        self.assertTrue(deck.endswith(".end\n"))

    def test_missing_stdcell_spice_raises(self):
        info = _pdk_info(self.root, with_stdcell=False)
        with self.assertRaisesRegex(RuntimeError, "sky130_fd_sc_hd combined SPICE deck not found"):
            rt.assemble_deck(SYNTH_DUT, info)


class TestCornerCampaign(unittest.TestCase):
    def test_simulated_points_are_the_shared_ratified_grid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            info = _pdk_info(root)
            dut = root / "dut.spice"
            dut.write_text(SYNTH_DUT)

            seen: list[tuple[str, float, float]] = []

            def fake_ngspice(deck_text, scratch_dir, log_name):
                lib = re.search(r"(?m)^\.lib \S+ (\w+)$", deck_text).group(1)
                temp = float(re.search(r"(?m)^\.temp (\S+)$", deck_text).group(1))
                vdd = float(re.search(r"(?m)^\.param vdd_val = (\S+)$", deck_text).group(1))
                seen.append((lib, temp, vdd))
                out = []
                for c, bits in ((1, CODE1_BITS), (2, CODE2_BITS)):
                    for i, ch in enumerate(bits):
                        out.append(f"dout{9 - i}_c{c} = {vdd if ch == '1' else 0.0:e}")
                out.append(f"dout9_early_c1 = {vdd:e}")
                for lab in [f"b{b}" for b in range(9, -1, -1)] + ["eoc", "sample"]:
                    out.append(f"ph{lab}_c1 = {vdd:e}")
                out += [f"phb9_c2 = {vdd:e}", f"pheoc_c2 = {vdd:e}"]
                return "\n".join(out) + "\n"

            with mock.patch.object(rt.toolchain, "check_env",
                                   return_value=toolchain.CheckResult(0, [], [])), \
                 mock.patch.object(rt.pdk, "resolve", return_value=info), \
                 mock.patch.object(rt, "netlist_dut", return_value=dut), \
                 mock.patch.object(rt.toolchain, "run_ngspice", side_effect=fake_ngspice), \
                 mock.patch.object(rt.evidence, "resolve_provenance") as prov, \
                 mock.patch.object(rt.evidence, "write_latest_pointer") as ptr, \
                 contextlib.redirect_stdout(io.StringIO()) as out:
                rc = rt.run_corner_campaign(record=False, quiet=True)

        self.assertEqual(rc, 0)
        self.assertIn("OVERALL (all corners): PASS", out.getvalue())
        prov.assert_not_called()
        ptr.assert_not_called()

        expected = corners_mod.ratified_oat_grid(1.8, 0.10, ["tt", "ss", "ff", "sf", "fs"], [-40, 27, 125])
        self.assertEqual(len(seen), 9)
        self.assertEqual(seen, [(p, float(t), s) for p, t, s in expected])
        self.assertEqual(len(set(seen)), 9, "points must be unique")
        self.assertEqual(seen[0], ("tt", 27.0, 1.8), "baseline first")


if __name__ == "__main__":
    unittest.main()

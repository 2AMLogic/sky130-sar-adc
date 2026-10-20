"""PDK-free deck-builder call test for sim/sequencer-logic-delay/run_sequencer_logic_delay.py (issue #591).

Same failure class as issue #296 (see test_run_hold_kick.py): a shared-helper
migration can leave a builder calling an undefined name, which only surfaces
when someone runs ngspice with the PDK. This test actually calls the builder
and checks the deck structure; no ngspice, no PDK."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import pdk  # noqa: E402

RUNNER = SIM_DIR / "sequencer-logic-delay/run_sequencer_logic_delay.py"
_spec = importlib.util.spec_from_file_location("run_sequencer_logic_delay_under_test", RUNNER)
rt = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rt
_spec.loader.exec_module(rt)

SYNTH_DUT = (
    ".subckt sar_sequencer CLK RST_B\n"
    "x1 CLK RST_B sky130_fd_sc_hd__inv_1\n"
    ".ends\n"
    ".end\n"
)


def _info(root: Path) -> pdk.PdkInfo:
    variant_dir = root / "sky130A"
    stdcell = variant_dir / "libs.ref" / "sky130_fd_sc_hd" / "spice" / "sky130_fd_sc_hd.spice"
    stdcell.parent.mkdir(parents=True)
    stdcell.write_text("")
    return pdk.PdkInfo(
        root=root, variant="sky130A", variant_dir=variant_dir,
        ngspice_lib=variant_dir / "libs.tech" / "ngspice" / "sky130.lib.spice",
        xschem_rc=variant_dir / "libs.tech" / "xschem" / "xschemrc",
        open_pdks_commit_expected="synthetic", found=True,
    )


class TestBuildTransient(unittest.TestCase):
    def test_returns_deck_and_edge_times(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(rt.pdk, "resolve", return_value=_info(Path(td))):
                deck, edges = rt.build_transient(SYNTH_DUT)
                deck2, _ = rt.build_transient(
                    SYNTH_DUT, corner="ss", temp_c=125.0, vdd=1.62)
        self.assertIn(".tran", deck)
        self.assertIn(".end", deck)
        self.assertIn(".meas tran", deck)
        self.assertEqual(deck.count(".end\n"), 1)
        self.assertEqual(len(edges), len(rt.PHASE_NODES))
        self.assertIn(".tran", deck2)

    def test_missing_stdcell_raises_runtime_error(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            info = _info(Path(td))
            info.variant_dir.joinpath("libs.ref", "sky130_fd_sc_hd", "spice",
                                      "sky130_fd_sc_hd.spice").unlink()
            with mock.patch.object(rt.pdk, "resolve", return_value=info):
                with self.assertRaises(RuntimeError):
                    rt.build_transient(SYNTH_DUT)


if __name__ == "__main__":
    unittest.main()

"""Regression tests for layout/top-glue/bin/check-schematic-parity.py (issue #387).

WHAT IS PINNED HERE
-------------------
The failure this check exists to catch is *not* a wrong layout. It is a layout
and an LVS reference that were both generated from the same superseded netlist,
so they agree with each other perfectly and `klt lvs` reports a clean match
while neither matches the schematic the repo builds. Issue #56's
`SELp<i> = DOUT<i>` / `SELn<i> = NOT(DOUT<i>)` glue survived two weeks and
several DRC/LVS-clean runs after
`spec/decision-records/DR-008-cdac-top-level-switching-polarity.md` superseded
it, for exactly that reason: the compare had no independent anchor.

`check-schematic-parity.py` supplies the anchor by re-deriving the expected
instance list from `design/sar_adc_top.spice` itself. These tests assert it on
the cases that distinguish a real check from a vacuous one:

* `test_committed_netlist_matches_schematic` -- the anti-vacuity half. A check
  that failed on everything, or that silently dropped the cell types it does
  not know, would pass the negative tests below and fail this one.
* `test_dr008_polarity_swap_fails` -- the single most important negative: one
  `and2_1` input moved from `DOUT9N` to `DOUT9`. Electrically this is the
  pre-DR-008 behaviour re-introduced; structurally it is invisible to `klt lvs`
  once the reference is regenerated from it, since both sides would carry it.
* `test_superseded_inverter_bank_fails` -- the exact historical netlist that
  went stale (`layout/seln-inverters/netlist/seln_inverters.v`) must be
  rejected. This is the test that would have failed in 2026-09-11 had the check
  existed then.
* `test_dropped_instance_fails` / `test_extra_instance_fails` -- census drift in
  both directions.
* `test_supply_pin_drift_fails` -- the implicit `VGND`/`VNB`/`VPB`/`VPWR`
  defaults the Verilog omits and the LVS-reference generator fills in must also
  be the nets the schematic names; a netlist that names them differently is not
  equivalent.

Every test runs the script as a subprocess with `PDK_ROOT` pointed at a
nonexistent path, i.e. through the committed pin-order cache, so this file is
headless and runs in CI's always-on `checks` job -- the same reason the check
itself has a cache at all.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK = REPO_ROOT / "layout" / "top-glue" / "bin" / "check-schematic-parity.py"
NETLIST = REPO_ROOT / "layout" / "top-glue" / "netlist" / "top_glue.v"
SUPERSEDED = REPO_ROOT / "layout" / "seln-inverters" / "netlist" / "seln_inverters.v"


def run_check(netlist: Path) -> subprocess.CompletedProcess[str]:
    """Run the parity check on `netlist`, headless (no PDK resolvable)."""
    env = dict(os.environ, PDK_ROOT="/nonexistent-pdk-root-for-tests")
    return subprocess.run(
        [sys.executable, str(CHECK), "--netlist", str(netlist)],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )


class TopGlueSchematicParityTest(unittest.TestCase):
    def test_committed_netlist_matches_schematic(self) -> None:
        result = run_check(NETLIST)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("33 instances, 6 cell types", result.stdout)

    def test_dr008_polarity_swap_fails(self) -> None:
        text = NETLIST.read_text(encoding="utf-8")
        swapped = text.replace(
            "xand_seln0 (.A(DOUT0), .B(DOUT9N)",
            "xand_seln0 (.A(DOUT0), .B(DOUT9)",
        )
        self.assertNotEqual(text, swapped, "the seln0 instance line moved; fix the test")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "swapped.v"
            path.write_text(swapped, encoding="utf-8")
            result = run_check(path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("xand_seln0.B", result.stderr)
        self.assertIn("DOUT9N", result.stderr)

    def test_superseded_inverter_bank_fails(self) -> None:
        result = run_check(SUPERSEDED)
        self.assertEqual(result.returncode, 1)
        # Every one of the 33 current instances is absent from it, and its own
        # nine xinv_seln<i> instances are absent from the schematic.
        self.assertIn("MISSING from Verilog: xand_seln0", result.stderr)
        self.assertIn("EXTRA in Verilog (not in schematic): xinv_seln0", result.stderr)

    def test_dropped_instance_fails(self) -> None:
        text = NETLIST.read_text(encoding="utf-8")
        dropped = re.sub(
            r"^\s*sky130_fd_sc_hd__xor2_1 xxor_code8 .*?;\s*$\n",
            "",
            text,
            count=1,
            flags=re.M | re.S,
        )
        self.assertNotEqual(text, dropped, "the xxor_code8 line moved; fix the test")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dropped.v"
            path.write_text(dropped, encoding="utf-8")
            result = run_check(path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("MISSING from Verilog: xxor_code8", result.stderr)

    def test_extra_instance_fails(self) -> None:
        text = NETLIST.read_text(encoding="utf-8")
        extra = text.replace(
            "endmodule",
            "  sky130_fd_sc_hd__inv_1 xinv_bogus (.A(DOUT0), .Y(BOGUS));\nendmodule",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "extra.v"
            path.write_text(extra, encoding="utf-8")
            result = run_check(path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("EXTRA in Verilog (not in schematic): xinv_bogus", result.stderr)

    def test_supply_pin_drift_fails(self) -> None:
        # The Verilog omits the four supply pins and the LVS-reference
        # generator fills them in (VGND/VNB -> VGND, VPB/VPWR -> VPWR). A
        # netlist that names one of them explicitly and differently is NOT
        # equivalent to the schematic, and the check must say so.
        text = NETLIST.read_text(encoding="utf-8")
        drifted = text.replace(
            "xinv_clkcap (.A(CLK), .Y(CLKN))",
            "xinv_clkcap (.A(CLK), .Y(CLKN), .VNB(VPWR))",
        )
        self.assertNotEqual(text, drifted, "the clkcap line moved; fix the test")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "drifted.v"
            path.write_text(drifted, encoding="utf-8")
            result = run_check(path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("xinv_clkcap.VNB", result.stderr)


if __name__ == "__main__":
    unittest.main()

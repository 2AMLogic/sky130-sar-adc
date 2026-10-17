"""Regression tests for layout/sar-sequencer/bin/check-schematic-parity.py (issue #676).

`layout/sar-sequencer/netlist/sar_sequencer.v` is hand-transliterated from
`design/sar_sequencer.sch`, with no freshness mechanism of its own. The check
re-derives the expected instances from `design/sar_adc_top.spice`'s
`.subckt sar_sequencer` and diffs them against the Verilog.

The committed Verilog has fallen behind the schematic (issue #263 added the
per-conversion clear and decision-direction gates), so the check is NOT in
`npm run check:ci` yet and these tests do not assert that it passes on the
committed file. They build a conforming Verilog FROM the spice -- the inverse
of the transliteration -- and assert the check on that:

* `test_conforming_netlist_passes` -- anti-vacuity: a check that failed on
  everything would pass every negative below.
* mutations of that conforming netlist (one rewired pin, one dropped gate, one
  extra gate, a port removed, a changed cell type) must each fail by name.
* `test_committed_netlist_is_reported_stale` -- pins the real current finding,
  so fixing the Verilog forces this test (and signoff's item 1 digital
  envelope) to be updated rather than letting the claim rot either way.

Headless: PDK_ROOT points at a nonexistent path, i.e. the committed pin-order
cache is used.
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
CHECK = REPO_ROOT / "layout" / "sar-sequencer" / "bin" / "check-schematic-parity.py"
NETLIST = REPO_ROOT / "layout" / "sar-sequencer" / "netlist" / "sar_sequencer.v"
SPICE = REPO_ROOT / "design" / "sar_adc_top.spice"
PIN_ORDER = REPO_ROOT / "layout" / "sar-sequencer" / "netlist" / "sky130_fd_sc_hd-pin-order.json"


def conforming_verilog() -> str:
    """The Verilog the check expects, generated from the spice's own subckt."""
    import json

    pin_order = json.loads(PIN_ORDER.read_text())["pin_order"]
    text = SPICE.read_text()
    head = re.search(r"^\.subckt sar_sequencer\s+(.*)$", text, re.M)
    body = text[head.end() : text.index(".ends", head.end())]
    ports = head.group(1).split()
    lines = []
    for raw in body.splitlines():
        raw = raw.strip()
        if not raw or raw.startswith(("*", ".")):
            continue
        toks = raw.split()
        cell = toks[-1]
        conns = ", ".join(
            f".{pin}({net})"
            for pin, net in zip(pin_order[cell], toks[1:-1])
            if pin not in ("VGND", "VNB", "VPB", "VPWR")
        )
        lines.append(f"  {cell} {toks[0]} ({conns});")
    return "module sar_sequencer (\n  " + ", ".join(ports) + "\n);\n" + "\n".join(lines) + "\nendmodule\n"


def run_check(netlist: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PDK_ROOT="/nonexistent-pdk-root-for-tests")
    return subprocess.run(
        [sys.executable, str(CHECK), "--netlist", str(netlist)],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )


class SarSequencerSchematicParityTest(unittest.TestCase):
    def check_text(self, text: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sar_sequencer.v"
            path.write_text(text, encoding="utf-8")
            return run_check(path)

    def test_conforming_netlist_passes(self) -> None:
        result = self.check_text(conforming_verilog())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("every pin net-identical", result.stdout)

    def test_rewired_pin_fails(self) -> None:
        text = conforming_verilog()
        mutated = text.replace(".D(DFEED8)", ".D(MUXOUT8)", 1)
        self.assertNotEqual(text, mutated)
        result = self.check_text(mutated)
        self.assertEqual(result.returncode, 1)
        self.assertIn("xbreg8.D", result.stderr)

    def test_dropped_gate_fails(self) -> None:
        text = conforming_verilog()
        mutated = re.sub(r"^  sky130_fd_sc_hd__xnor2_1 xxnor_compeff .*\n", "", text, flags=re.M)
        self.assertNotEqual(text, mutated)
        result = self.check_text(mutated)
        self.assertEqual(result.returncode, 1)
        self.assertIn("MISSING from Verilog: xxnor_compeff", result.stderr)

    def test_extra_gate_fails(self) -> None:
        mutated = conforming_verilog().replace(
            "endmodule", "  sky130_fd_sc_hd__inv_1 xinv_bogus (.A(BUSY), .Y(BOGUS));\nendmodule"
        )
        result = self.check_text(mutated)
        self.assertEqual(result.returncode, 1)
        self.assertIn("EXTRA in Verilog (not in schematic): xinv_bogus", result.stderr)

    def test_changed_cell_type_fails(self) -> None:
        text = conforming_verilog()
        mutated = text.replace("sky130_fd_sc_hd__or3_1 xor_busy ", "sky130_fd_sc_hd__or3_2 xor_busy ", 1)
        self.assertNotEqual(text, mutated)
        result = self.check_text(mutated)
        self.assertNotEqual(result.returncode, 0)

    def test_module_port_drift_fails(self) -> None:
        text = conforming_verilog()
        mutated = text.replace("BUSY", "BUSYX", 1)
        result = self.check_text(mutated)
        self.assertEqual(result.returncode, 1)
        self.assertIn("module ports differ", result.stderr)

    def test_committed_netlist_is_reported_stale(self) -> None:
        # The real finding of issue #676: sar_sequencer.v predates #263.
        result = run_check(NETLIST)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("MISSING from Verilog: xxnor_compeff", result.stderr)
        self.assertIn("xbreg8.D", result.stderr)


if __name__ == "__main__":
    unittest.main()

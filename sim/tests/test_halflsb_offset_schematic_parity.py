"""Regression tests for layout/halflsb-offset/bin/check-schematic-parity.py
(issue #495).

WHAT IS PINNED HERE
-------------------
The failure this check exists to catch is not a wrong layout that DRC or LVS
would flag. It is a layout-side device table that has drifted from
`design/sar_adc_top.spice` in a way the flow's own verdicts cannot see, and this
block has a *measured* example of exactly that:

    `klt lvs` reports a clean **match** against a reference whose
    `HALF_LSB_EN` / `HALF_LSB_ENN` gate connections are exchanged.

`NetlistComparer` matches nets structurally rather than by name, and both
half-LSB enables enter this network only as ports, so exchanging them -- which
inverts DR-009's load-bearing enable polarity -- is a graph isomorphism. The
flow's own `swapped-enable` negative control records that verdict on every run
(see `layout/halflsb-offset/README.md`, "What `klt lvs` cannot see on this
block"). The parity gate is what does see it, and these tests are what hold the
gate to being non-vacuous.

Every defect below is injected into a COPY of `design/sar_adc_top.spice` in a
temp dir, never into the tree: the schematic is the thing that moves in real
life (a DR revision, a re-netlist), and the layout table is the committed
constant that has to keep up with it. That is the same direction
`sim/tests/test_top_glue_schematic_parity.py` tests from the other side (it
injects into the layout-side Verilog), and between them both edges of the diff
are covered.

Pure stdlib, no PDK: the check reads text only, so this file runs in CI's
always-on headless job -- which is the point of wiring the check into
`npm run check:ci` rather than only into the PDK-gated flow.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK = REPO_ROOT / "layout" / "halflsb-offset" / "bin" / "check-schematic-parity.py"
SPICE = REPO_ROOT / "design" / "sar_adc_top.spice"

#: A line inside the top-level `**.subckt sar_adc_top` region that the
#: insertion-based defects anchor on. Asserted present by every test that uses
#: it, so a netlist regeneration that moves it fails loudly instead of silently
#: injecting nothing.
ANCHOR = "XCdecap_a GND VDD sky130_fd_pr__cap_mim_m3_1"


def run_check(spice: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECK), "--spice", str(spice)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def run_on_mutated(
    test: unittest.TestCase, old: str, new: str
) -> subprocess.CompletedProcess[str]:
    """Run the check on a copy of the netlist with `old` replaced by `new`."""
    text = SPICE.read_text(encoding="utf-8")
    test.assertIn(old, text, f"{old!r} is no longer in the netlist; fix the test")
    mutated = text.replace(old, new, 1)
    test.assertNotEqual(text, mutated)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sar_adc_top.spice"
        path.write_text(mutated, encoding="utf-8")
        return run_check(path)


class HalfLsbOffsetSchematicParityTest(unittest.TestCase):
    def test_committed_netlist_matches_the_layout_table(self) -> None:
        """The anti-vacuity half: a check that failed on everything, or that
        silently skipped the cards it does not recognise, would pass every
        negative below and fail this one."""
        result = run_check(SPICE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("8 instances, 3 device types, 12 nets", result.stdout)
        self.assertIn("cap_mim: 2", result.stdout)
        self.assertIn("nfet: 2", result.stdout)
        self.assertIn("pfet: 4", result.stdout)

    def test_swapped_enable_polarity_fails(self) -> None:
        """The single most important negative: the defect class `klt lvs`
        reports as a clean match on this block."""
        result = run_on_mutated(
            self,
            "XMoff_n_refp BOT_OFF_N HALF_LSB_EN VREFP",
            "XMoff_n_refp BOT_OFF_N HALF_LSB_ENN VREFP",
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Moff_n_refp.g", result.stderr)
        self.assertIn("HALF_LSB_ENN", result.stderr)

    def test_dropped_instance_fails(self) -> None:
        text = SPICE.read_text(encoding="utf-8")
        dropped = "\n".join(
            line for line in text.splitlines() if not line.startswith("XMoff_p_cmp ")
        )
        self.assertNotEqual(text, dropped, "the XMoff_p_cmp line moved; fix the test")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sar_adc_top.spice"
            path.write_text(dropped + "\n", encoding="utf-8")
            result = run_check(path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("EXTRA in the layout table", result.stderr)
        self.assertIn("Moff_p_cmp", result.stderr)

    def test_extra_instance_on_an_owned_net_fails(self) -> None:
        """A ninth device on `BOT_OFF_N` is claimed by the ownership rule and
        then found to have no drawn counterpart."""
        result = run_on_mutated(
            self,
            ANCHOR,
            "XMoff_n_bogus BOT_OFF_N HALF_LSB_EN VCM VDD "
            "sky130_fd_pr__pfet_01v8 L=0.15 W=2 m=1\n" + ANCHOR,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("MISSING from the layout table", result.stderr)
        self.assertIn("Moff_n_bogus", result.stderr)

    def test_unowned_top_level_primitive_fails(self) -> None:
        """A new top-level primitive that is neither this block's nor a declared
        foreign instance must not be able to pass unnoticed -- that state (a
        primitive in the schematic with no drawn geometry anywhere) is what
        issues #387 and #495 were filed to end."""
        result = run_on_mutated(
            self,
            ANCHOR,
            "XCstray VDD GND sky130_fd_pr__cap_mim_m3_1 W=1 L=1 MF=1 m=1\n" + ANCHOR,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("belong to no drawn block", result.stderr)
        self.assertIn("XCstray", result.stderr)

    def test_device_size_drift_fails(self) -> None:
        result = run_on_mutated(
            self,
            "XMoff_n_refp BOT_OFF_N HALF_LSB_EN VREFP VDD "
            "sky130_fd_pr__pfet_01v8 L=0.15 W=2 ",
            "XMoff_n_refp BOT_OFF_N HALF_LSB_EN VREFP VDD "
            "sky130_fd_pr__pfet_01v8 L=0.15 W=4 ",
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Moff_n_refp", result.stderr)
        self.assertIn("W=", result.stderr)

    def test_multiplied_device_fails(self) -> None:
        """`m`/`MF` > 1 means the schematic wants that many drawn units; this
        block draws one per card, so it is not an implementation of it."""
        result = run_on_mutated(
            self,
            "XChoff_n BOT_OFF_N TOP_N sky130_fd_pr__cap_mim_m3_1 W=1.9000 L=1.9000 MF=1 m=1",
            "XChoff_n BOT_OFF_N TOP_N sky130_fd_pr__cap_mim_m3_1 W=1.9000 L=1.9000 MF=2 m=2",
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Choff_n", result.stderr)
        self.assertIn("draws exactly one device per card", result.stderr)

    def test_capacitor_plate_assignment_swap_fails(self) -> None:
        """Which node is drawn on which plate is a layout decision `gen_blocks.
        CAP_LEGS` declares; the card's own node order is what it is checked
        against, so a schematic that reverses it has to be looked at."""
        result = run_on_mutated(
            self,
            "XChoff_n BOT_OFF_N TOP_N sky130_fd_pr__cap_mim_m3_1",
            "XChoff_n TOP_N BOT_OFF_N sky130_fd_pr__cap_mim_m3_1",
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Choff_n.p1", result.stderr)

    def test_unknown_primitive_flavour_fails(self) -> None:
        """An unmodelled `sky130_fd_pr` model must raise rather than be skipped:
        a silently-ignored card is a primitive with no drawn geometry, which is
        the whole gap."""
        result = run_on_mutated(
            self,
            ANCHOR,
            "XMhv BOT_OFF_N HALF_LSB_EN VREFP VDD "
            "sky130_fd_pr__pfet_g5v0d10v5 L=0.5 W=2 m=1\n" + ANCHOR,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown sky130_fd_pr model", result.stderr)


if __name__ == "__main__":
    unittest.main()

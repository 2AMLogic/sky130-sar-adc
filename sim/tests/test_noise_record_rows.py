"""PDK-free tests for the noise record's op-point table rows (issue #927).

The failure class: a measured-value row whose LABEL asserts more than its VALUE
column shows. `write_noise_evidence()` used to emit

    | Op point: v(DIP)=v(DIN) | 0.3824 V | tt/27.0C/1.8V |

-- one number under a label asserting an equality between two nodes. The deck
measures and the runner parses BOTH nodes, so the `=` could have been backed by
a number from the same run and instead rested only on the deck's
by-construction symmetry (the same "a clean verdict read as proving more than
it said" failure CLAUDE.md's "verification is the product" rule exists to stop).

These tests pin the corrected contract on `noise._op_point_rows()`, which is
pure (no PDK, no ngspice, no record write) precisely so the row text can be
asserted here rather than only observed after a fleet run mints a record. They
follow the PDK-free unit-test convention of sim/tests/test_deck_builders_followon.py
(sim/selftest.sh stage 1/4).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(SIM_DIR / "comparator-decision"))

from comparator_campaigns import noise as cd_noise  # noqa: E402


def _result(op_tail=0.9123, op_dip=0.3824, op_din=0.3824):
    """A NoiseResult carrying only what _op_point_rows() reads."""
    return cd_noise.NoiseResult(
        single_ended_rms_v=7.1e-4, differential_rms_v=1.0e-3,
        op_tail_v=op_tail, op_dip_v=op_dip, op_din_v=op_din,
        log_text="", corner="tt", temp_c=27.0, supply_v=cd_noise.VDD,
    )


class TestOpPointRows(unittest.TestCase):
    def test_one_row_per_measured_node_plus_delta(self):
        rows = cd_noise._op_point_rows(_result())
        self.assertEqual(len(rows), 4)
        self.assertIn("| Op point: v(TAIL) | 0.9123 V |", rows[0])
        self.assertIn("| Op point: v(DIP) | 0.3824 V |", rows[1])
        self.assertIn("| Op point: v(DIN) | 0.3824 V |", rows[2])
        self.assertIn("abs(v(DIP) - v(DIN))", rows[3])

    def test_no_row_asserts_an_equality_it_does_not_print(self):
        """The regression this issue fixed: a label claiming v(DIP)=v(DIN)."""
        rows = cd_noise._op_point_rows(_result())
        for row in rows:
            label = row.split("|")[1]
            self.assertNotIn("=", label, f"row label asserts an equality: {row!r}")
        self.assertNotIn("v(DIP)=v(DIN)", "\n".join(rows))

    def test_asymmetry_is_visible_in_the_rows(self):
        """A DIP/DIN split must change the table -- under the old single-row
        form `op_din_v` had no reader, so any asymmetry was invisible in the
        record no matter how large."""
        rows = cd_noise._op_point_rows(_result(op_dip=0.3824, op_din=0.3791))
        self.assertIn("| Op point: v(DIP) | 0.3824 V |", rows[1])
        self.assertIn("| Op point: v(DIN) | 0.3791 V |", rows[2])
        self.assertIn("3.30e-03 V", rows[3])

    def test_delta_row_is_symmetric_in_its_arguments(self):
        """abs(): the reported asymmetry does not depend on which node is larger."""
        hi = cd_noise._op_point_rows(_result(op_dip=0.3824, op_din=0.3791))[3]
        lo = cd_noise._op_point_rows(_result(op_dip=0.3791, op_din=0.3824))[3]
        self.assertIn("3.30e-03 V", hi)
        self.assertIn("3.30e-03 V", lo)

    def test_rows_are_well_formed_three_column_markdown(self):
        """Each row must have exactly three cells -- an unescaped `|` inside a
        label (e.g. writing the delta as |v(DIP) - v(DIN)|) would silently
        split the cell and corrupt the record's table."""
        for row in cd_noise._op_point_rows(_result()):
            self.assertTrue(row.startswith("| "), row)
            self.assertTrue(row.endswith(" |"), row)
            self.assertEqual(row.count("|"), 4, f"not a 3-cell row: {row!r}")

    def test_every_row_carries_the_corner_condition(self):
        r = _result()
        cond = f"{r.corner}/{r.temp_c}C/{cd_noise.VDD}V"
        for row in cd_noise._op_point_rows(r):
            self.assertEqual(row.split("|")[3].strip(), cond, row)


if __name__ == "__main__":
    unittest.main()

"""Unit test for sim/cdac-array-transfer/gen_fragment.py -- pure text
generation, no ngspice/PDK required (mirrors sim/tests/test_harness.py's
PDK-free unit-test convention; see sim/selftest.sh stage 1/4).

This is the load-bearing check for issue #29's CDAC Monte Carlo campaign
(sim/cdac-array-transfer/run_mc.py): the generator MUST reproduce #53's
hand-authored testbench/tb_cdac_array_transfer.spice byte-for-byte for that
fragment's own 5 codes before it is trusted to generate the larger code set
run_mc.py actually simulates -- a generator bug here would silently corrupt
every downstream Monte Carlo draw."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
CDAC_DIR = SIM_DIR / "cdac-array-transfer"
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(CDAC_DIR))

from gen_fragment import gen_fragment  # noqa: E402


class TestGenFragmentMatchesHandAuthored(unittest.TestCase):
    def test_matches_tb_cdac_array_transfer_spice_byte_for_byte(self):
        reference_path = CDAC_DIR / "testbench" / "tb_cdac_array_transfer.spice"
        reference = reference_path.read_text()
        generated = gen_fragment([0, 128, 256, 384, 511])
        self.assertEqual(
            generated, reference,
            "gen_fragment() diverged from the hand-authored #53 fragment for its "
            "own 5 codes -- fix the generator before trusting it for any other "
            "code list (see this module's docstring)",
        )


class TestGenFragmentStructural(unittest.TestCase):
    def test_every_code_emits_both_sides_and_all_nodes_referenced(self):
        from gen_fragment import gen_fragment as gf

        codes = [0, 1, 2, 3, 511]
        text = gf(codes)
        for code in codes:
            self.assertIn(f"top_{code}p", text)
            self.assertIn(f"top_{code}n", text)
            # every code contributes exactly 9 cap instances per side
            self.assertEqual(text.count(f"Xc_{code}p"), 9)
            self.assertEqual(text.count(f"Xc_{code}n"), 9)

    def test_side_p_and_side_n_are_bitwise_complementary(self):
        """Side P is driven directly by `code`; side N by its 9-bit
        complement `511-code` -- verify no Vsel source exists for a bit
        position whose side_code bit is 0, and one DOES exist where it is
        1, for a spot-checked code (matches #53's own documented pattern)."""
        from gen_fragment import gen_fragment as gf

        code = 100  # bits lsb-first: 100 = 0b001100100
        text = gf([code])
        side_code_p = code
        side_code_n = 511 - code
        for i in range(9):
            bit_p = (side_code_p >> i) & 1
            bit_n = (side_code_n >> i) & 1
            self.assertEqual(f"Vsel_{code}p{i} " in text, bool(bit_p))
            self.assertEqual(f"Vsel_{code}n{i} " in text, bool(bit_n))


if __name__ == "__main__":
    unittest.main()

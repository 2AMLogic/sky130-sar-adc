"""Unit test for sim/enob-estimate/run_enob.py's `achieved_enob()` -- pure
math, no ngspice/PDK required (mirrors sim/tests/test_harness.py's PDK-free
unit-test convention; see sim/selftest.sh stage 1/4).

`achieved_enob()` is documented as the algebraic inverse of
spec/dr-003-support/calc.py's `total_budget()` (target ENOB -> required
noise budget). This test re-implements `total_budget()`'s formula
independently (not by importing calc.py, whose top-level prints make it
unsuitable as a library import) and checks the round trip: for a range of
target ENOB values, `total_budget()` -> `achieved_enob()` must recover the
original target exactly. A round-trip failure here would mean the two
scripts' formulas have silently diverged -- exactly the failure mode a
"combine with the ratified/DR-003 methodology, don't reinvent it" claim
needs caught mechanically, not by inspection."""

from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
ENOB_DIR = SIM_DIR / "enob-estimate"
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(ENOB_DIR))

from run_enob import LSB_V, achieved_enob, load_cdac_draws, per_draw_enob, sigma_quant  # noqa: E402


def _total_budget_reference(lsb: float, enob_target: float, n_bits: int = 10) -> float:
    """Independent re-implementation of spec/dr-003-support/calc.py's
    total_budget(), for round-trip testing only."""
    sq = sigma_quant(lsb)
    db_backoff = 6.02 * (n_bits - enob_target)
    power_ratio = 10 ** (db_backoff / 10)
    n_nonquant_over_n_quant = power_ratio - 1
    return sq * math.sqrt(n_nonquant_over_n_quant)


class TestAchievedEnobRoundTrip(unittest.TestCase):
    def test_round_trips_dr003_targets(self):
        for target in (8.0, 8.5, 9.0, 9.5, 10.0):
            sigma = _total_budget_reference(LSB_V, target)
            back = achieved_enob(sigma, LSB_V)
            self.assertAlmostEqual(back, target, places=9)

    def test_zero_nonquant_noise_gives_ideal_enob(self):
        # With sigma_nonquant = 0, achieved ENOB must equal N bits exactly
        # (an ideal quantizer's SNR IS the N-bit ideal).
        self.assertAlmostEqual(achieved_enob(0.0, LSB_V, n_bits=10), 10.0, places=9)

    def test_more_noise_means_fewer_bits(self):
        low = achieved_enob(0.1e-3, LSB_V)
        high = achieved_enob(1.0e-3, LSB_V)
        self.assertGreater(low, high)


def _write_draw_log(path: Path, offset_v: float) -> None:
    """Minimal ngspice-style log: a straight-line transfer with code 511 bowed
    by `offset_v` at the mid codes is awkward to fake, so give each draw a
    distinct deviation at ONE interior code; max|INL| is then known in closed
    form (see _expected_inl_lsb)."""
    mc = _mc()
    lines = []
    for code in mc.CODES_MC:
        v = 0.001 * code
        if code == mc.CODES_MC[len(mc.CODES_MC) // 2]:
            v += offset_v
        lines.append(f"vtop_p_{code} = {v / 2:.12e}")
        lines.append(f"vtop_n_{code} = {-v / 2:.12e}")
    path.write_text("\n".join(lines) + "\n")


_MC = None


def _mc():
    global _MC
    if _MC is None:
        import run_enob
        _MC = run_enob._load_run_mc()
    return _MC


def _expected_inl_lsb(offset_v: float) -> float:
    """Independent: deviation d at an interior code of an otherwise exactly
    linear transfer shifts the endpoint line by 0 (endpoints untouched), so
    max|INL| = |d| / LSB."""
    return abs(offset_v) / LSB_V


class TestPerDrawEnob(unittest.TestCase):
    OFFSETS = (0.4e-3, 1.1e-3, -2.0e-3, 3.3e-3)
    CMP = 0.8643e-3
    KTC = 0.1e-3

    def _make(self, root: Path, rid: str = "rec", offsets=None, extra_negctrl=True) -> None:
        d = root / rid
        d.mkdir(parents=True)
        for i, off in enumerate(self.OFFSETS if offsets is None else offsets):
            _write_draw_log(d / f"draw_{i}_seed{10 + i}.log", off)
            if extra_negctrl:
                _write_draw_log(d / f"negctrl_{i}_seed{10 + i}.log", 0.0)

    def test_one_sample_per_draw_with_traceability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make(root)
            draws = load_cdac_draws("rec", expected_n=4, draws_root=root)
        self.assertEqual([d["index"] for d in draws], [0, 1, 2, 3])
        self.assertEqual([d["seed"] for d in draws], [10, 11, 12, 13])
        for d, off in zip(draws, self.OFFSETS):
            self.assertAlmostEqual(d["inl_max_lsb"], _expected_inl_lsb(off), places=4)
        est = per_draw_enob(draws, self.CMP, self.KTC)
        self.assertEqual(len(est), 4)
        self.assertEqual(len({round(e["enob_bit"], 9) for e in est}), 4)

    def test_per_draw_enob_matches_independent_calculation(self):
        draws = [{"index": i, "seed": i, "inl_max_lsb": v} for i, v in enumerate((0.3, 0.72, 1.3147))]
        for e in per_draw_enob(draws, self.CMP, self.KTC):
            sq2 = LSB_V ** 2 / 12
            nonq2 = self.CMP ** 2 + self.KTC ** 2 + (e["inl_max_lsb"] * LSB_V) ** 2
            expect = 10 - 10 * math.log10((sq2 + nonq2) / sq2) / 6.02
            self.assertAlmostEqual(e["enob_bit"], expect, places=9)

    def test_missing_directory_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                load_cdac_draws("nope", draws_root=Path(tmp))

    def test_incomplete_draw_set_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make(root)
            with self.assertRaises(ValueError):
                load_cdac_draws("rec", expected_n=5, draws_root=root)

    def test_gap_in_indices_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make(root)
            (root / "rec" / "draw_1_seed11.log").unlink()
            with self.assertRaises(ValueError):
                load_cdac_draws("rec", draws_root=root)

    def test_missing_measurement_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make(root)
            log = root / "rec" / "draw_2_seed12.log"
            log.write_text("\n".join(l for l in log.read_text().splitlines() if "vtop_p_511" not in l) + "\n")
            with self.assertRaises(ValueError):
                load_cdac_draws("rec", expected_n=4, draws_root=root)

    def test_non_finite_and_empty_inputs_fail(self):
        with self.assertRaises(ValueError):
            per_draw_enob([{"index": 0, "seed": 1, "inl_max_lsb": float("nan")}], self.CMP, self.KTC)
        with self.assertRaises(ValueError):
            per_draw_enob([], self.CMP, self.KTC)


if __name__ == "__main__":
    unittest.main()

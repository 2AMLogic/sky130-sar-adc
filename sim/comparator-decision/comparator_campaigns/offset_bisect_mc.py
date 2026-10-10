"""offset bisect mc campaign for the comparator-decision driver (issue #613 split of run.py)."""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path

from .common import (
    DUT_FRAGMENT,
    EXPERIMENT_DIR,
    VDD,
    _dut_lines,
    _dut_provenance,
)
from .offset_bisect import (
    BISECT_SCAN_MV,
    BisectCornerResult,
    run_offset_bisect,
)
from .offset_bisect_evidence import (
    _bisect_edge_cell,
)
from .regen import (
    _finalize_record,
)
from harness import corners as corners_mod, evidence, pdk

# ---------------------------------------------------------------------------
# offset-bisect-mc: the decision boundary bisected PER Monte Carlo draw
# (issue #524). Composes run_offset_bisect() with the rndseed-per-draw scheme
# run_offset_mc() uses; nothing in the search itself is new.
# ---------------------------------------------------------------------------
#
# Why: the `offset` pick-off statistic is a fitted-gain linearization valid on
# Vindiff in [1, 10] mV and extrapolates to ~225 mV (DR-004 Decision 3 calls
# its magnitudes an upper bound / order of magnitude). The boundary is
# decision-referred, so it needs no gain and has no validity range.
#
# Coarse scan: the mismatch-free grid +-{50, 10, half-LSB} is sized for a
# boundary near zero. A mismatch draw can sit at tens of mV, so the MC scan
# adds +-200 mV: a draw whose boundary lies between 50 and 200 mV then starts
# its bisection from a bracket of at most 150 mV, instead of triggering
# Phase B's doubling expansion. It costs 2 more coarse probes per draw and
# saves the expansion (and a long first bracket) for the draws that need it.
BISECT_MC_SCAN_MV = [-200.0] + BISECT_SCAN_MV + [200.0]


@dataclass
class BisectMcResult:
    corner: str
    mismatch_corner: str
    temp_c: float
    seed: int
    n: int
    negctrl_n: int
    draws: list[BisectCornerResult]
    negctrl: list[BisectCornerResult]
    dut_fragment: Path = DUT_FRAGMENT

    @property
    def draw_seeds(self) -> list[int]:
        return [self.seed + i for i in range(self.n)]


def _bounded_offsets(results: list[BisectCornerResult]) -> list[float]:
    return [r.offset_mv for r in results if r.bounded and r.offset_mv is not None]


def bisect_mc_stats(results: list[BisectCornerResult]) -> dict[str, float | int]:
    """Distribution of the per-draw boundary-derived offset (mV) over the draws
    that BOUNDED. pstdev, to match the population convention
    `write_offset_evidence()` uses for the 97.0825 mV it is compared with. A
    draw that did not bound is counted in `n_total` but contributes no value;
    it is never imputed."""
    vals = _bounded_offsets(results)
    out: dict[str, float | int] = {"n_total": len(results), "n_bounded": len(vals)}
    if vals:
        out.update(
            mean=statistics.fmean(vals),
            stdev=statistics.pstdev(vals) if len(vals) > 1 else 0.0,
            min=min(vals), max=max(vals),
        )
    return out


NEGCTRL_MIN_N = 2  # one control draw compares its edges with themselves


def bisect_negctrl_status(negctrl: list[BisectCornerResult]) -> str:
    """The repo-wide negative-control contract: mismatch DISABLED, same seed
    sequence => the identical boundary on every draw, stdev exactly 0.

    Returns "PASS", "FAIL" or "NOT-EXERCISED". All draws must have bounded
    (an unbounded control proves nothing -> FAIL), and BOTH edges, not only
    their midpoint, must be identical (a midpoint can agree while the edges
    move). Seed-invariance needs at least two seeds to compare: a control
    with fewer than NEGCTRL_MIN_N draws is NOT-EXERCISED, never PASS -- it
    would only compare one boundary with itself."""
    if not negctrl or not all(r.bounded for r in negctrl):
        return "FAIL"
    if len(negctrl) < NEGCTRL_MIN_N:
        return "NOT-EXERCISED"
    edges = [(r.neg_lo_mv, r.neg_hi_mv, r.pos_lo_mv, r.pos_hi_mv) for r in negctrl]
    if any(e != edges[0] for e in edges):
        return "FAIL"
    return "PASS" if statistics.pstdev(_bounded_offsets(negctrl)) == 0.0 else "FAIL"


def bisect_negctrl_ok(negctrl: list[BisectCornerResult]) -> bool:
    """True only when the control was exercised (>= NEGCTRL_MIN_N draws) and
    passed; see bisect_negctrl_status()."""
    return bisect_negctrl_status(negctrl) == "PASS"


def run_offset_bisect_mc(
    corner: str = "tt", temp_c: float = 27.0, seed: int = 1, n: int = 16,
    negctrl_n: int | None = None, supply_v: float = VDD,
    scan_mv: list[float] | None = None, quiet: bool = False,
    dut_fragment: Path = DUT_FRAGMENT,
) -> BisectMcResult:
    """Bisect the boundary once per draw at `<corner>_mm` (rndseed seed+i), then
    run the negative control at the plain corner over the same seed sequence.
    `negctrl_n` defaults to `n`; set it lower only to save probes, and the
    record then states the control's smaller N (below NEGCTRL_MIN_N the
    control is reported NOT-EXERCISED). `dut_fragment` (issue #525's
    selector) is threaded to every probe of every draw and control search."""
    pdk.resolve_or_raise()
    mismatch_corner = corners_mod.mismatch_corner_for(corner)
    ncn = n if negctrl_n is None else negctrl_n
    scan = scan_mv if scan_mv is not None else BISECT_MC_SCAN_MV
    draws: list[BisectCornerResult] = []
    for i in range(n):
        if not quiet:
            print(f"draw {i} (seed={seed + i}, {mismatch_corner}):")
        draws.append(run_offset_bisect(
            corner=mismatch_corner, temp_c=temp_c, supply_v=supply_v,
            scan_mv=scan, quiet=quiet, rndseed=seed + i,
            dut_fragment=dut_fragment,
        ))
    negctrl: list[BisectCornerResult] = []
    for i in range(ncn):
        if not quiet:
            print(f"negctrl {i} (seed={seed + i}, {corner}):")
        negctrl.append(run_offset_bisect(
            corner=corner, temp_c=temp_c, supply_v=supply_v,
            scan_mv=scan, quiet=quiet, rndseed=seed + i,
            dut_fragment=dut_fragment,
        ))
    return BisectMcResult(
        corner=corner, mismatch_corner=mismatch_corner, temp_c=temp_c, seed=seed,
        n=n, negctrl_n=ncn, draws=draws, negctrl=negctrl,
        dut_fragment=dut_fragment,
    )


PICKOFF_REF_STDEV_MV = 97.0825  # record 20260821-071918-433a294
PICKOFF_REF_N = 16


def _bisect_mc_comparison_lines(st: dict[str, float | int]) -> list[str]:
    """Data-driven agreement statement against the pick-off record. The verdict
    sentence is computed from the numbers, never asserted: with N draws the
    relative standard error of a stdev is ~1/sqrt(2(N-1)). The reference is
    itself a sampled stdev (N=PICKOFF_REF_N), so 'agrees' means the difference
    lies inside +-2 combined SE, sqrt(SE_bisect^2 + SE_ref^2)."""
    out = ["## Agreement with the pick-off sigma", ""]
    n = int(st["n_bounded"])
    if n < 2:
        out.append("Fewer than 2 bounded draws: no sigma to compare.")
        return out
    s = float(st["stdev"])
    se = s / (2 * (n - 1)) ** 0.5
    se_ref = PICKOFF_REF_STDEV_MV / (2 * (PICKOFF_REF_N - 1)) ** 0.5
    se_comb = (se ** 2 + se_ref ** 2) ** 0.5
    ratio = PICKOFF_REF_STDEV_MV / s if s > 0 else float("inf")
    agrees = abs(PICKOFF_REF_STDEV_MV - s) <= 2 * se_comb
    out.append(
        f"Boundary-derived stdev {s:.4f} mV (N={n}, SE ~{se:.2f} mV) vs the "
        f"pick-off statistic's {PICKOFF_REF_STDEV_MV} mV (N={PICKOFF_REF_N}, "
        f"SE ~{se_ref:.2f} mV): ratio {ratio:.1f}x, difference "
        f"{abs(PICKOFF_REF_STDEV_MV - s):.2f} mV vs 2 x combined SE "
        f"{2 * se_comb:.2f} mV. **{'AGREES' if agrees else 'DISAGREES'}** at "
        "+-2 combined SE."
    )
    if not agrees:
        out += [
            "",
            "Divergence: the pick-off statistic divides a fixed-time output "
            "difference by a gain fitted over Vindiff in [1, 10] mV. A "
            "regenerative latch's output at a fixed time is compressive in "
            "its input, so draws whose pick-off lands outside the fitted range "
            "(DR-004 Decision 3's caveat) are overstated by the constant-gain "
            "division. That is the expected source and is directionally "
            "consistent with this result (bisected spread much smaller than "
            "pick-off spread), but this record does not isolate it: N is "
            "small, and it did not re-evaluate the pick-off on the same seeds. "
            "The boundary figure is decision-referred with no fitted gain, so "
            "it is the better-founded of the two; the 97.0825 mV figure should "
            "not be used as a random-offset sigma pending a converged-N "
            "boundary record.",
        ]
    return out


def write_offset_bisect_mc_evidence(
    result: BisectMcResult, note: str = "", supersedes: str = "",
) -> Path:
    raw_logs: dict[str, str] = {}
    for tag, group in (("draw", result.draws), ("negctrl", result.negctrl)):
        for i, r in enumerate(group):
            for p in r.probes:
                safe = f"{p.vindiff_mv:.6f}mV".replace("-", "neg").replace(".", "p")
                raw_logs[f"{tag}{i}__{r.corner_id}__vindiff_{safe}.log"] = p.log_text
    prov, lines = evidence.open_record(
        EXPERIMENT_DIR, _dut_lines(result.dut_fragment), "mc-draws", raw_logs,
    )
    a = lines.append
    st = bisect_mc_stats(result.draws)
    ctl_status = bisect_negctrl_status(result.negctrl)
    ctl_stats = bisect_mc_stats(result.negctrl)
    nb = st["n_bounded"]
    supplies = sorted({r.supply_v for r in result.draws + result.negctrl}) or [VDD]
    a("- **Claim**: None numeric -- boundary-bisected random-offset distribution "
      "(issue #524). No spec row (DR-020 declines one; its second prerequisite, "
      "a derived offset allocation, is separate).")
    a(f"- **Netlist provenance**: {_dut_provenance(result.dut_fragment)}")
    a(corners_mod.corner_matrix_summary_line(
        [result.mismatch_corner, result.corner], [result.temp_c], supplies,
        len(result.draws) + len(result.negctrl),
    ) + f" -- {len(result.draws)} `{result.mismatch_corner}` draw searches + "
        f"{len(result.negctrl)} `{result.corner}` negative-control searches, "
        "each a serial boundary bisection at one (corner, temp, supply) point")
    a(f"- **Statistical convention**: mismatch corner `{result.mismatch_corner}`, "
      f"temp={result.temp_c:g}C supply={supplies[0]}V, N={result.n} draws, seed={result.seed} "
      f"(draw i uses rndseed seed+i). N is set by probe cost, not by a "
      f"precision target: SE(s)/s ~= 1/sqrt(2(N-1)) = "
      f"{100.0 / (2 * (result.n - 1)) ** 0.5 if result.n > 1 else float('inf'):.0f}% "
      "for an approximately Gaussian statistic. Each draw is a ~15-30 probe "
      "serial bisection of 20 ns transients; this is an increment, not a "
      "converged sigma.")
    a("- **Reference**: `20260821-071918-433a294` pick-off statistic: N=16, "
      "mean +35.2441 mV, stdev 97.0825 mV, range [-136.4332, +224.9353] mV "
      "(fitted gain 4.2083 V/V, valid over 1-10 mV).")
    ctl_verdict = {
        "PASS": "PASS (identical boundary edges on every seed, stdev == 0)",
        "FAIL": "FAIL (edges differ or a control draw did not bound)",
        "NOT-EXERCISED": (
            f"NOT EXERCISED (fewer than {NEGCTRL_MIN_N} control draws: one "
            "boundary compared with itself cannot show seed-invariance)"
        ),
    }[ctl_status]
    a(f"- **Negative control**: {result.negctrl_n} "
      f"draw{'s' if result.negctrl_n != 1 else ''} at plain "
      f"`{result.corner}` (mismatch disabled), same seed sequence -- {ctl_verdict}")
    a("- **Batch path**: none. A sequential bisection (each probe's Vindiff "
      "depends on the previous outcome) is not expressible as one `klt sim` "
      "request, so this ran as one serial local process; the tool gap is "
      "2AMLogic/klayout-tools#2716.")
    if note:
        a(f"- **Note**: {note}")
    if ctl_status == "PASS" and nb > 1:
        overall = "PASS"
    elif ctl_status == "NOT-EXERCISED" and nb > 1:
        overall = "NOT GRADED (negative control not exercised)"
    else:
        overall = "FAIL"
    a(f"- **Overall**: {overall}")
    a("")
    a("## Boundary-derived offset distribution (mV)")
    a("")
    a("| N drawn | N bounded | mean | stdev (population) | min | max |")
    a("|---|---|---|---|---|---|")
    if nb:
        a(f"| {st['n_total']} | {nb} | {st['mean']:.4f} | {st['stdev']:.4f} | "
          f"{st['min']:.4f} | {st['max']:.4f} |")
    else:
        a(f"| {st['n_total']} | 0 | n/a | n/a | n/a | n/a |")
    a("")
    a("## Per-draw boundaries")
    a("")
    a("| draw | seed | status | neg edge (mV) | pos edge (mV) | offset (mV) | dead band (mV) | probes |")
    a("|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(result.draws):
        if r.bounded:
            a(f"| {i} | {result.seed + i} | {r.status} | "
              f"{_bisect_edge_cell(r.neg_edge_mv, r.neg_edge_unc_mv)} | "
              f"{_bisect_edge_cell(r.pos_edge_mv, r.pos_edge_unc_mv)} | "
              f"{r.offset_mv:+.4f} +-{r.offset_unc_mv:.4f} | "
              f"{r.dead_band_mv:.4f} +-{r.dead_band_unc_mv:.4f} | {len(r.probes)} |")
        else:
            a(f"| {i} | {result.seed + i} | {r.status} | n/a | n/a | n/a | n/a | {len(r.probes)} |")
    a("")
    a("## Negative control (mismatch disabled, same seed sequence)")
    a("")
    a("| draw | seed | status | neg edge (mV) | pos edge (mV) | offset (mV) |")
    a("|---|---|---|---|---|---|")
    for i, r in enumerate(result.negctrl):
        if r.bounded:
            a(f"| {i} | {result.seed + i} | {r.status} | "
              f"{_bisect_edge_cell(r.neg_edge_mv, r.neg_edge_unc_mv)} | "
              f"{_bisect_edge_cell(r.pos_edge_mv, r.pos_edge_unc_mv)} | {r.offset_mv:+.4f} |")
        else:
            a(f"| {i} | {result.seed + i} | {r.status} | n/a | n/a | n/a |")
    a("")
    lines.extend(_bisect_mc_comparison_lines(st))
    if ctl_stats["n_bounded"]:
        a("")
        a(f"Control offset stdev: {ctl_stats['stdev']:.6g} mV (must be exactly 0).")
    a("")
    for tag, group in (("draw", result.draws), ("negctrl", result.negctrl)):
        for i, r in enumerate(group):
            for note_text in r.notes:
                a(f"- {tag} {i}: {note_text}")
    a("")
    return _finalize_record(
        lines, prov.record_path, prov.pdk_line, prov.ng_version, prov.netlist_sha,
        "offset-bisect-mc",
        extra={"MC seed": str(result.seed), "MC N": str(result.n)},
        supersedes=supersedes,
    )

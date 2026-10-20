"""Shared constants, DUT fragments and ngspice helpers for the comparator-decision driver (issue #613 split of run.py)."""
from __future__ import annotations

import sys
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import corners as corners_mod, evidence, toolchain  # noqa: E402


EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
TESTBENCH_DIR = EXPERIMENT_DIR / "testbench"
DUT_FRAGMENT = TESTBENCH_DIR / "comparator_core.spice"
# EXPERIMENTAL mitigation-class variant (issue #434, DR-014 Consequences
# Sec.4 / Open items): the same 11-device latch plus two cross-coupled
# neutralization capacitors on the input pair. NOT the adopted design --
# see the file's own header for why a hand-authored (non-xschem-derived)
# fragment is appropriate here, same as sim/harness-corner-smoke's own
# testbenches. Used only by the `kickback-neutralized` subcommand below.
DUT_FRAGMENT_NEUTRALIZED = TESTBENCH_DIR / "comparator_core_neutralized.spice"
# POST-LAYOUT variant (issue #525): the comparator sub-block's committed
# `klt pex` extraction (layout/comparator/reports/20260906-152000-eace0b6/
# comparator.pex-extract.spice), `.SUBCKT`-wrapped with its R/C parasitics,
# plus one instantiation line so it drops into the same flat-deck slot the
# schematic fragment fills. Selected with `offset-bisect --dut extracted`;
# never the default, and `DUT_FRAGMENT` itself is untouched.
DUT_FRAGMENT_EXTRACTED = TESTBENCH_DIR / "comparator_core_extracted.spice"
DUT_CHOICES = {
    "schematic": DUT_FRAGMENT,
    "extracted": DUT_FRAGMENT_EXTRACTED,
}


def _dut_provenance(fragment: Path) -> str:
    """The `- **Netlist provenance**:` line body naming which fragment ran."""
    rel = f"`{fragment.relative_to(evidence.REPO_ROOT)}`"
    if fragment == DUT_FRAGMENT_EXTRACTED:
        return (
            f"post-layout extracted, `klt pex` parasitics ({rel}, from "
            "`layout/comparator/reports/20260906-152000-eace0b6/"
            "comparator.pex-extract.spice`)"
        )
    if fragment == DUT_FRAGMENT:
        return f"schematic ({rel})"
    return f"other ({rel})"

# --- Fixed testbench constants (all provisional -- see
# spec/decision-records/DR-004-comparator-topology-and-noise-budget.md) ---
VDD = 1.8  # V -- DR-003 Item 1's recommended V_REF = V_DD, cited here as a
# provisional planning value, NOT a ratified spec/target-spec.md row (issue
# #1/#27 have not ratified it). This testbench does not depend on
# ratification -- it characterizes the comparator core against whatever
# supply is asserted here, and would simply need this constant updated if a
# different value is ever ratified.
VCM = VDD / 2  # 0.9V -- common-mode input, matching a differential
# top-plate CDAC's bottom-plate-switching common mode (DR-003 Item 1).
RESET_NS = 5.0  # reset (CLK=0) duration before the single evaluate edge --
# empirically verified sufficient for a clean, symmetric start from an
# uninitialized circuit (see design/comparator.sch's header comment on the
# W=16um reset-device sizing this relied on).
RESET_TR_NS = 0.1  # clock edge rise/fall time
DECIDE_THRESHOLD_V = 0.5 * VDD  # |v(outp)-v(outn)| crossing this = "decided"
PICKOFF_NS = 0.3  # time after evaluate-start used as the "decision
# statistic" pick-off point for offset extraction (see `offset` subcommand
# docstring) -- chosen empirically as the point where the early
# differential-output-vs-Vindiff relationship is cleanly linear (verified
# for Vindiff in [1, 10] mV; see the decision record's derivation).
NOISE_FSTART_HZ = 1e3
NOISE_FSTOP_HZ = 1e9  # ~1/regeneration-time-constant order of magnitude
# (regen-sweep records below resolve sub-mV differentials within ~1-2 ns),
# not an arbitrary round number -- see the decision record.

# --- Ratified corner-set axes (issue #28), per spec/target-spec.md's
# "Numeric rows -- RATIFIED 2026-08-19" section: -40/27/125C, +-10% supply,
# sky130 process corners. VDD above (1.8V) is now also the ratified V_REF/
# V_DD value (DR-003 Item 1), not only a provisional planning constant.
SUPPLY_TOLERANCE = corners_mod.RATIFIED_SUPPLY_TOLERANCE
TEMPS_C = corners_mod.RATIFIED_TEMPS_C
PROCESS_CORNERS = corners_mod.RATIFIED_PROCESS_CORNERS
# Ratified comparator input-referred noise budget (DR-003 Item 4 /
# spec/target-spec.md's ratified row): baseline (ENOB>9.0) and stretch
# (ENOB>9.5) thresholds, in V rms (differential, input-referred).
NOISE_BUDGET_BASELINE_V = 1.0148e-3
NOISE_BUDGET_STRETCH_V = 0.5859e-3


def _dut_lines(fragment: Path = DUT_FRAGMENT) -> str:
    return fragment.read_text()


def _run(deck_text: str, scratch_dir: Path, log_name: str) -> str:
    return toolchain.run_ngspice(deck_text, scratch_dir, log_name)

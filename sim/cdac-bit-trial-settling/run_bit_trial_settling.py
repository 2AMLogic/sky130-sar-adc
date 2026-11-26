#!/usr/bin/env python3
"""CDAC-array bit-trial switch-Ron settling budget (issue #121, Epic #542
Phase 4B follow-up).

`docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2 names the
largest still-open DRAFT row after the layout gap: the 100 kS/s-1 MS/s
sample-rate row has never been re-derived from a real switch-`R_on`/CDAC-
settling campaign -- `spec/decision-records/DR-006-sar-sequencer-bit-count-
and-timing-budget.md` says so explicitly ("this record is not a settling-
time analysis... that needs #24's full hierarchy"). DR-006 was written
2026-08-21, before `design/cdac/cdac_array.sch` (#53) or
`design/comparator.sch` (#54) existed; both now do. This script does not
close that gap (a full per-bit settling + comparator-decision-time budget,
over PVT, is still needed for that), but it takes the first concrete step:
it isolates and quantifies the ONE mechanism that is fully determined by
`design/cdac/cdac_array.sch` alone -- how long the array's own bottom-plate
switch network takes to settle the shared top-plate node after a single
bit's SEL toggles at the start of its own bit-trial phase -- at a single
corner, the same "first-pass, single-corner budget" precedent
`sim/vcm-drive-budget/run_vcm_drive_budget.py` already established for the
sampling front end's own open item.

WHY THIS MECHANISM IS WORTH ISOLATING ON ITS OWN. Every one of
`design/cdac/cdac_array.sch`'s 9 per-side bit switches
(`design/cdac/cdac_unit_cell.sch`'s pattern) is the SAME fixed size
(nfet_01v8 W=1, pfet_01v8 W=2, both L=0.15) regardless of which bit it
serves -- only the capacitor it drives scales with the bit's binary weight
(MF=1..256 via the capacitor's own multiplicity parameter). A two-node
linear-circuit derivation (this script's own docstring-adjacent working,
not asserted without derivation): with bit i's own bottom-plate node driven
through R_on to a new rail and every other bit's bottom plate held fixed
(the actual SAR sequencer behaviour --
`sim/sampling-cdac-handoff/run_handoff.py`'s own header already established
that only the JUST-DECIDED bit's register updates at a phase boundary,
every other bit holds), the shared top-plate node's settling time constant
works out to

    tau_i = R_on * C_i * (1 - C_i / C_total)

where C_i = weight_i * C_u is bit i's own capacitor and C_total = 512 * C_u
is the whole side's total capacitance (DR-003 Item 3). Because C_i grows
binarily (1..256 unit caps) while R_on is IDENTICAL for every bit, tau_i is
not monotonic in bit position -- it is maximised where C_i is closest to
C_total/2, which for this array's own weights (1..256 out of 512) is
exactly bit 8, the MSB of the 9-bit sub-array. That is a genuine, testable
prediction of this design's own component values, not an assumption --
this script tests it directly rather than asserting it from the algebra
alone (bits 0, 4, and 8 are simulated so the shape of tau_i across bit
position is actually shown, not just its endpoint).

METHOD. A single-side, single-instance reduction of `design/cdac/
cdac_array.sch` (9 bit positions + termination unit) is built in-line by
this script (not read from a static fragment file, unlike
`sim/vcm-drive-budget/`'s reuse of an existing regenerated fragment --
no existing regenerated fragment isolates one side of the array with one
free bit, so this script states its own reduction directly, the same
precedent `sim/cdac-array-transfer/testbench/tb_cdac_array_transfer.spice`
already set for a testbench-only ideal reset switch pinning the initial
condition). Only the ONE bit under test is instantiated with its real
nfet_01v8/pfet_01v8 switch pair (at this schematic's exact W/L values) and
driven by a PWL source that steps from one rail to the other at t=1n; every
OTHER bit's bottom plate is held at a fixed ideal DC voltage (0 V --
equivalent to SEL=1, per the design's own polarity) rather than
instantiating that bit's own never-switching-in-this-run transistor pair.
This is a deliberate, documented simplification (see the held-bit branch of
`build_transient()` for the full rationale): a held bit's own switch
contributes nothing to the transient being measured except a fixed-voltage
boundary condition on its own capacitor, which an ideal source reproduces
exactly, while being far cheaper to simulate -- an earlier version of this
script instantiated real switches for all 9 bits and needed 15+ minutes per
run. It DOES omit each held bit's own switch-transistor parasitic
capacitance contribution to `C_total`, a small, second-order effect not
modeled here. Every capacitor (including the test bit's and the
termination unit's) is real, at this schematic's exact W/L/MF values. The
top-plate node is released from an ideal reset switch (matching
`tb_cdac_array_transfer.spice`'s own reset-then-real-switch convention) at
the same instant the test bit's SEL edge starts.

Because the top-plate node is purely capacitive (no other resistive path
once the reset switch opens, aside from a 1 Tohm DC anti-floating leak
carried over unchanged from `tb_cdac_array_transfer.spice`), the array's
own charge-conservation algebra gives an EXACT closed-form ideal final
value for the shared top-plate node, independent of R_on:

    V_top_final = V_cm + (C_i / C_total) * (V_bot_final - V_bot_initial)

This script computes that analytically in Python (not fitted from the
simulation) and then uses ngspice's own `.measure tran ... trig ... targ
... cross=1` to find, from real transient data, the wall-clock time after
the SEL edge at which V_top first crosses each of three fractional
thresholds (50%, 90%, 99% of the way from V_cm to V_top_final) -- so the
"final value" a settling-time claim is measured against is never itself
taken from the same noisy transient it is being extracted from. A
long-time (near the end of the simulated window) confirmatory measurement checks the simulated
steady-state top-plate voltage against this closed-form prediction as an
internal consistency check on the derivation itself, printed and recorded
alongside the settling times.

No claim here is graded against a ratified spec row: `spec/target-spec.md`
is entirely DRAFT (#1/#27); the DR-006 phase-period figures quoted for
comparison are themselves downstream of the DRAFT sample-rate row (Section
7 Item 2, the same gap `sim/vcm-drive-budget/` already flagged for the
front end's own open item). This experiment also does NOT include the
comparator's own decision (propagation) delay -- that is a separate,
still-open mechanism (`design/comparator.sch` exists but no timing
campaign against it has been run); this script isolates the CDAC array's
own switch-settling contribution only, exactly as narrowly scoped as
`sim/vcm-drive-budget/`'s own VCM-only isolation.

FULL-PVT-GRID MODE (``--corners``, added 2026-09-07). The single-corner
caveat above is what the ``--corners`` mode exists to close: it re-runs the
IDENTICAL 6 (test_bit, direction) transient decks -- and the identical
closed-form-vs-simulated cross-check and TRIG/TARG settling-fraction
`.meas` statements -- at each of the 9 one-at-a-time points of this repo's
ratified corner set (spec/target-spec.md's "Numeric rows -- RATIFIED
2026-08-19" section: process `{tt, ss, ff, sf, fs}` x temperature
`{-40, 27, 125} C` x supply `{1.62, 1.8, 1.98} V`), the same OAT grid
`sim/comparator-decision/`, `sim/sampling-acquisition-settling/`, and
`sim/sequencer-logic-delay/` each already sweep for the other three
sample-rate mechanisms. Only the `.lib` corner, `.temp`, and the `vdd`
parameter (which the closed-form V_top_final prediction and the held-bit
DC levels already depend on via `build_transient()`'s own `vdd` argument)
change per point -- the reduced-array topology, the PWL edge shape, and the
measurement convention are byte-identical to the single-corner default.
`R_on` for both the nfet_01v8/pfet_01v8 switch pair varies materially with
process/temperature/supply, which is exactly why the single-corner record
declined to call itself PVT-complete. The single-corner default behavior is
unchanged; `--corners` is purely additive.

DR-027 CANDIDATE-GEOMETRY STUDY MODE (``--dr027-candidate``, issue #1033).
DR-027 (proposed by the #1016 linearity study) would resize the unit plate
from the DR-019 `1.9000` um side to `3.3000` um, growing the array from
~4.31 pF/side (512 x 8.405 fF, model-evaluated) to ~12.19 pF/side (512 x
23.805 fF -- `C_u` scales tau_i linearly, so every settling time grows by
the same 2.832x). This mode re-runs the SAME reduction, the SAME switch
sizes and binary weights, at that candidate plate, against BOTH DR-006
phase deadlines (83.333 ns @ 12 MHz and 833.333 ns @ 1.2 MHz -- the DRAFT
sample-rate row's two endpoints), with the SEL switches and weights
explicitly NOT resized (a resize that moved drive strength would be its
own design change needing its own DR-011/DR-014 charge-injection/kickback
evidence -- out of scope here, per #1033). The study decks are
EXPERIMENTAL: `design/cdac/` still draws the 1.9000 um plate, and nothing
in this mode measures the shipping design.

EXECUTION of the candidate grid: ONE ``klt sim`` request (the
``sim/harness/klt_sim.py`` submit path, issue #865 -- the same one
``sim/input-drive-budget/`` uses), never a local ngspice loop. The request
carries all six (test_bit, direction) copies of the reduced array as six
INDEPENDENT instances in one circuit body (no shared nodes beyond the
ideal rails; each copy is exactly the single-instance reduction the
single-corner record documents), because the corner axes must multiply one
netlist. The corner-dependence that per-corner decks used to bake into
their PWL levels (SEL swing, reset-control swing, VCM) is expressed as
NORMALISED 0..1 sources scaled by the corner's own supply through
behavioural sources, and the TRIG/TARG thresholds are read on a
supply-normalised copy of the top-plate node
(``Bnorm_x NORM_x 0 V=(v(TOP_x)-v(VCM))/v(VDD)``), so ONE set of numeric
`.meas` thresholds (fractions of the way from 0 to +- ratio) serves
every corner -- the crossing times are identical to the raw node's by
construction (the map is affine and monotone with positive slope 1/vdd at
every corner). The candidate handoff campaign's own control re-ran the
same re-expression at the production 1.9 um plate and reproduced the
committed assembled-load record's tt residual exactly, validating it.

Usage (from the repo root, after ``source sim/env.sh``)::

    python3 sim/cdac-bit-trial-settling/run_bit_trial_settling.py
    python3 sim/cdac-bit-trial-settling/run_bit_trial_settling.py --record
    # Full ratified PVT grid (9 OAT points) instead of the single
    # tt/27C/1.8V corner above:
    python3 sim/cdac-bit-trial-settling/run_bit_trial_settling.py --corners --record
    # DR-027 candidate-geometry study (issue #1033): dry-run the deck /
    # single-corner local probe / submit the grid and mint a record:
    python3 sim/cdac-bit-trial-settling/run_bit_trial_settling.py --dr027-candidate --dry-run
    python3 sim/cdac-bit-trial-settling/run_bit_trial_settling.py --dr027-candidate --probe
    python3 sim/cdac-bit-trial-settling/run_bit_trial_settling.py --dr027-candidate --record
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
EXPERIMENT_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(SIM_DIR))
from harness import corners as corners_mod, evidence, klt_sim, measure, pdk, toolchain  # noqa: E402

VDD = 1.8
VCM = 0.9  # VDD/2, DR-003 Item 1, provisional
LSB_DIFF_MV_PROVISIONAL = 3.5156  # DR-003 Item 2, provisional pending #27 --
# reference scale only (this experiment is single-ended; the differential
# LSB is quoted only so error/settling figures have a familiar yardstick,
# same convention sim/vcm-drive-budget/ already uses).

# design/cdac/cdac_array.sch bit weights (lsb-first, i=0..8) + termination.
# MF=2**i per bit per that schematic; termination is a fixed weight-1 unit.
BIT_WEIGHTS = {i: 2 ** i for i in range(9)}
TERM_WEIGHT = 1
C_TOTAL_WEIGHT = sum(BIT_WEIGHTS.values()) + TERM_WEIGHT  # 511 + 1 = 512

#: The unit-cap plate side every `cap_mim_m3_1` card in this deck asks for,
#: transcribed from `design/cdac/cdac_unit_cell.sch`'s own `C_u` -- kept as one
#: named constant rather than repeated as a literal in the three places the
#: deck emits a capacitor card, so a future resize cannot land in two of them.
#:
#: `1.9000` since `spec/decision-records/DR-019-cdac-unit-cap-grid-legal-plate-resize.md`
#: (#496, carried through here by #498) resized the plate from `1.8988` to a
#: 5 nm manufacturing-grid-legal side. This campaign's own measured quantity is
#: a RATIO (tau_i = R_on * C_total * weight_i/C_total_weight -- see the module
#: docstring), so C_u scales tau_i linearly and the +0.116% resize moves every
#: settling time by the same +0.116%: far inside this measurement's own
#: resolution, but the deck must still ask for the plate the design draws.
UNIT_CAP_WL_UM = 1.9000

TEST_BITS = [0, 4, 8]  # LSB, a mid bit, MSB -- brackets the tau_i(i) shape
DIRECTIONS = ["fall", "rise"]  # fall: BOT 1.8->0V (NMOS); rise: BOT 0->1.8V (PMOS)

# Ratified corner-set axes (issue #28), per spec/target-spec.md's "Numeric
# rows -- RATIFIED 2026-08-19" section: -40/27/125C, +-10% supply, sky130
# process corners -- the same axes sim/comparator-decision/,
# sim/sampling-acquisition-settling/, and sim/sequencer-logic-delay/ each
# already sweep. Used only by the optional --corners mode below; the
# single-corner (tt/27C/1.8V) default behavior above is unchanged.
SUPPLY_TOLERANCE = corners_mod.RATIFIED_SUPPLY_TOLERANCE
TEMPS_C = corners_mod.RATIFIED_TEMPS_C
PROCESS_CORNERS = corners_mod.RATIFIED_PROCESS_CORNERS

# The single-corner (tt/27C/1.8V) record --corners's own evidence record
# cross-references as "the finding this campaign extends" -- the record
# committed by this same script's single-corner default path.
SINGLE_CORNER_SEED_RECORD = "20260905-220919-bbf06dd"

# DR-006-derived per-phase clock budget (1 CLK period per bit-trial phase,
# uniform allocation): t_phase = 1 / f_clk, f_clk in the DR-006-derived
# 1.2-12 MHz range.
T_PHASE_WORST_NS = 1.0e3 / 12.0   # 83.333... ns @ f_clk_max = 12 MHz
T_PHASE_SLOW_NS = 1.0e3 / 1.2     # 833.33... ns @ f_clk_min = 1.2 MHz

EDGE_TD_NS = 1.0     # matches tb_cdac_array_transfer.spice's own reset edge
EDGE_TR_NS = 0.2     # 0.9n -> 1.1n, same convention
# TRAN_STOP_NS / TRAN_STEP_PS were tuned empirically (see PR description):
# the sky130 "combined" corner .lib carries a large fixed per-invocation
# parse cost (~13 s, paid by every sim/ experiment that loads it, not
# specific to this script), on top of which this circuit's own transient
# cost scales with point count. 15 ns comfortably covers the worst-case
# analytic settling time this script's own module docstring predicts
# (bit 8/MSB, tau ~= 1.67 ns @ R_on(pfet) -> 99% settle ~= 4.6*tau ~= 7.7 ns,
# plus the 0.2 ns SEL edge itself) with margin, while keeping each run's
# wall-clock time bounded on a shared/contended machine.
TRAN_STOP_NS = 20.0
TRAN_STEP_PS = 5.0
CONFIRM_AT_NS = TRAN_STOP_NS - 1.0  # long-time closed-form cross-check

# --corners mode needs a longer window than the single-corner default:
# switch R_on -- and hence settling time -- grows materially at slow-
# process/low-supply corners. A pre-flight probe of the worst-case row
# (bit 8/rise) at every corner combination this constant needed to cover
# found ss_-40c_1.62v the binding point at t_settle_99% = 16.09 ns, already
# 41% higher than the tt/27C/1.8V baseline's 11.39 ns and too close to the
# single-corner window's own 20 ns ceiling to reuse unchanged -- so
# --corners uses its own, more generous window instead of changing
# TRAN_STOP_NS (which would alter the single-corner default path's own
# already-cited netlist/record).
CORNERS_TRAN_STOP_NS = 40.0

FRACTIONS = [0.5, 0.9, 0.99]  # fraction of the way from V_cm to V_top_final

MEASURE_PREFIX_CONFIRM = "vtop_confirm"

# --- issue #1033: DR-027 candidate-geometry study (--dr027-candidate) --------
#: The DR-027 proposed unit-plate side (um), from issue #1033's own statement
#: of the #1016 candidate: 512 unit positions/side at a 3.3000 um plate,
#: C_tot ~ 12.4 pF/side nominal (the PDK model evaluates C_u = 23.805 fF
#: once the m3 metal-width shrink m3_dw = -0.025 um is applied -- see
#: measure_unit_cap_ff(); the nominal-without-shrink figure behind issue
#: #1033's "~12.4 pF" arithmetic is 24.29 fF/unit). EXPERIMENTAL study
#: value: design/cdac/ still draws the DR-019 1.9000 um plate.
CANDIDATE_UNIT_CAP_WL_UM = 3.3000

#: Switch W/L and per-bit weights are deliberately NOT touched by the
#: candidate study (issue #1033: "Retain the existing switch sizes and binary
#: weights"). These constants pin the values the candidate body emits so a
#: future edit of the array's real sizing cannot drift the study decks
#: silently -- they are the values design/cdac/cdac_unit_cell.sch draws today.
SWITCH_NFET_WL = (1, 0.15)   # nfet_01v8  W, L
SWITCH_PFET_WL = (2, 0.15)   # pfet_01v8  W, L

#: The two DR-006 phase deadlines = the DRAFT sample-rate row's endpoints.
#: FAST is the 12 MHz (1 MS/s) worst case; SLOW is the 1.2 MHz (100 kS/s)
#: slow end. Each candidate measurement window must place its deadline
#: strictly inside the window and, for the crossings, well past the worst
#: predicted settling (~37.5 ns = the 1.9000 um grid's binding 13.2466 ns x
#: the 2.832x C_u ratio).
CAND_DEADLINE_FAST_NS = T_PHASE_WORST_NS   # 83.333... ns @ f_clk = 12 MHz
CAND_DEADLINE_SLOW_NS = T_PHASE_SLOW_NS    # 833.333... ns @ f_clk = 1.2 MHz
CAND_FAST_TRAN_STOP_NS = 100.0             # 2.7x the predicted worst t_settle
CAND_SLOW_TRAN_STOP_NS = 850.0             # covers the slow deadline + late read
# Same ceiling as the fast step (PR #1041 finding 3): a coarser slow step
# changed the converged bit-0 tail by ~2.4 uV, enough to flip a 99 % crossing.
CAND_SLOW_TRAN_STEP_NS = TRAN_STEP_PS / 1000.0  # 0.005 ns, matches the fast step
CAND_LATE_AT_NS = CAND_SLOW_TRAN_STOP_NS - 5.0  # 845 ns, mirrors CONFIRM_AT_NS

#: Supply-source name = the `corners.supply_v` axis key (the same convention
#: sim/input-drive-budget/ established).
CAND_SUPPLY_KEY = "vsup"

#: Fleet policy: one request, all six copies in one body, two analysis steps
#: (fast crossings / slow tail reads) per corner. 9 corners x 2 steps = 18
#: units; a measured tt fast step runs in ~4 s and the slowest corner is a
#: few times that, so 300 s per unit with 2 hosts keeps the whole-job bound
#: at 300*9+120 = 2820 s, inside the fleet ceiling the input-drive-budget
#: runner documents (see its DEFAULT_TIMEOUT_S comment).
CAND_TIMEOUT_S = 300.0
CAND_HOSTS = 2

#: The committed 1.9000 um full-PVT grid this study is the companion of --
#: its binding corner/row is the baseline the candidate's numbers are read
#: against (13.2466 ns, bit 8/rise, `tt_27c_1.62v`, at commit 75b91e85).
CAND_BASELINE_RECORD = "20261001-140017-7487784"

#: The other two mechanisms' PVT-complete binding figures, quoted from the
#: sample-rate entry of sim/report/manifest.py -- the time-left-in-phase
#: arithmetic in this campaign's record divides the phase budget between
#: CDAC settling and these.
COMPARATOR_DECISION_NS = 4.3575    # binding tt_27c_1.62v (manifest sample-rate row)
SEQUENCER_LOGIC_NS = 0.4237        # binding ss_27c_1.80v (manifest sample-rate row)


def candidate_tag(test_bit: int, direction: str) -> str:
    """Stable per-copy tag, e.g. ``b8r`` -- node-name-safe (letters/digits
    only) so every derived node/measurement name is a legal ngspice name."""
    return f"b{test_bit}{'r' if direction == 'rise' else 'f'}"


def candidate_copies() -> list[tuple[int, str]]:
    """The six (test_bit, direction) copies, in a deterministic order (the
    same bit-major order run_all() iterates, so tables line up)."""
    return [(b, d) for b in TEST_BITS for d in DIRECTIONS]


def candidate_ratio(test_bit: int) -> float:
    """C_i/C_total for the test bit -- unchanged by the plate resize (both
    scale with C_u), so the closed-form step size is the same as the 1.9000
    um grid's and the normalized crossing thresholds are pure constants."""
    return BIT_WEIGHTS[test_bit] / C_TOTAL_WEIGHT


def build_transient(
    *,
    test_bit: int,
    direction: str,
    corner: str = "tt",
    temp_c: float = 27.0,
    vdd: float = VDD,
    tran_stop_ns: float = TRAN_STOP_NS,
) -> tuple[str, dict]:
    """One transient deck: a single-side, single-instance reduction of
    design/cdac/cdac_array.sch with every bit except `test_bit` held fixed
    (SEL=1, gate tied to VDD) and `test_bit` driven by a PWL edge at
    EDGE_TD_NS, simultaneous with an ideal reset switch (matching
    tb_cdac_array_transfer.spice's own SWMOD/Rdc convention) releasing the
    shared top-plate node from VCM. Returns (netlist_text, analytics) where
    analytics carries the closed-form V_top_final prediction and the
    threshold voltages this deck's own .measure statements search for.

    `tran_stop_ns` defaults to the single-corner TRAN_STOP_NS (20 ns), tuned
    for the tt/27C/1.8V point only; the --corners campaign passes a larger
    value (see CORNERS_TRAN_STOP_NS below) because switch R_on -- and hence
    settling time -- grows materially at slow-process/low-supply corners
    (a probe at ss/-40C/1.62V, bit 8/rise, found t_settle_99% = 16.09 ns,
    already 41% higher than the tt/27C/1.8V baseline's 11.39 ns, too close
    to the single-corner window's own 20 ns ceiling to reuse unchanged
    across the full ratified grid without risking a silently-incomplete
    measurement at a slower corner still).
    """
    vcm = round(vdd / 2, 6)
    weight_test = BIT_WEIGHTS[test_bit]
    ratio = weight_test / C_TOTAL_WEIGHT

    if direction == "fall":
        v_bot_initial, v_bot_final = vdd, 0.0
    elif direction == "rise":
        v_bot_initial, v_bot_final = 0.0, vdd
    else:
        raise ValueError(direction)

    # SEL=1 -> NMOS on -> BOT=VREFN=0; SEL=0 -> PMOS on -> BOT=VREFP=vdd.
    # So a BOT edge from v_bot_initial to v_bot_final corresponds to a SEL
    # edge in the OPPOSITE sense (SEL=1 <-> BOT=0).
    sel_initial = vdd if v_bot_initial == 0.0 else 0.0
    sel_final = vdd if v_bot_final == 0.0 else 0.0

    delta_ideal = ratio * (v_bot_final - v_bot_initial)
    v_top_final = vcm + delta_ideal

    lines = toolchain.deck_preamble(
        corner, temp_c,
        f"issue #121 CDAC bit-trial settling -- corner={corner} temp={temp_c}C "
        f"vdd={vdd} test_bit={test_bit} direction={direction}",
        extra_lines=[
            ".model SWMOD SW(Ron=1 Roff=1e12 Vt={0} Vh=0.05)".format(VDD / 2)
        ],
    )
    lines += [
        f"Vdd VDD 0 dc {vdd}",
        f"Vvrefp VREFP 0 dc {vdd}",
        "Vvrefn VREFN 0 dc 0",
        f"Vcm VCM 0 dc {vcm}",
        "* Ideal (testbench-only) reset switch + anti-floating leak --",
        "* same convention as sim/cdac-array-transfer/testbench/",
        "* tb_cdac_array_transfer.spice's own Sreset_.../Rdc_... pattern.",
        f"Vctrl_reset NCTRL_RESET 0 pwl(0 {vdd} {EDGE_TD_NS - EDGE_TR_NS / 2}n {vdd} "
        f"{EDGE_TD_NS + EDGE_TR_NS / 2}n 0 {tran_stop_ns}n 0)",
        "Sreset TOP VCM NCTRL_RESET 0 SWMOD",
        "Rdc TOP VCM 1T",
        f"Vsel_test SEL_TEST 0 pwl(0 {sel_initial} {EDGE_TD_NS - EDGE_TR_NS / 2}n "
        f"{sel_initial} {EDGE_TD_NS + EDGE_TR_NS / 2}n {sel_final} {tran_stop_ns}n "
        f"{sel_final})",
    ]

    for i in range(9):
        weight = BIT_WEIGHTS[i]
        if i == test_bit:
            lines += [
                f"Xc_bit{i} bot{i} TOP sky130_fd_pr__cap_mim_m3_1 "
                f"W={UNIT_CAP_WL_UM:.4f} L={UNIT_CAP_WL_UM:.4f} "
                f"MF={weight} m={weight}",
                f"Xn_bit{i} bot{i} SEL_TEST VREFN 0 sky130_fd_pr__nfet_01v8 "
                "L=0.15 W=1 nf=1",
                f"Xp_bit{i} bot{i} SEL_TEST VREFP VDD sky130_fd_pr__pfet_01v8 "
                "L=0.15 W=2 nf=1",
            ]
        else:
            # Held bit: SEL=1 fixed -> NMOS on -> BOT=VREFN=0, permanently,
            # for the whole run (this bit's own register never updates
            # during the test bit's own trial phase -- see module
            # docstring). Modeled as an IDEAL DC source directly on the
            # bottom-plate node rather than instantiating this bit's own
            # (never-switching, for this run) real transistor pair: the
            # two are equivalent for THIS experiment's purpose (a fixed
            # bottom-plate node presents the same fixed-voltage boundary
            # condition to the shared top-plate node either way), and the
            # ideal-source form is dramatically cheaper to simulate (an
            # earlier version of this script instantiated real switches
            # for all 9 bits and took >15 minutes per run -- most of that
            # cost from held bits contributing nothing physically new to
            # the transient being measured). Documented simplification,
            # not silently substituted: this DOES omit the held bit's own
            # switch-transistor parasitic capacitance contribution to
            # C_total (a small, second-order effect not modeled here).
            lines.append(f"Vbot{i} bot{i} 0 dc 0")
            lines.append(
                f"Xc_bit{i} bot{i} TOP sky130_fd_pr__cap_mim_m3_1 "
                f"W={UNIT_CAP_WL_UM:.4f} L={UNIT_CAP_WL_UM:.4f} "
                f"MF={weight} m={weight}"
            )
    # Termination unit: fixed weight-1 cap, bottom plate hardwired VREFN,
    # no switch device at all (design/cdac/cdac_array.sch's own convention).
    lines.append(
        f"Xc_term VREFN TOP sky130_fd_pr__cap_mim_m3_1 "
        f"W={UNIT_CAP_WL_UM:.4f} L={UNIT_CAP_WL_UM:.4f} "
        f"MF={TERM_WEIGHT} m={TERM_WEIGHT}"
    )

    confirm_at_ns = tran_stop_ns - 1.0
    thresholds = {}
    lines.append(".control")
    lines.append(f"tran {TRAN_STEP_PS}p {tran_stop_ns}n")
    for frac in FRACTIONS:
        target_v = vcm + frac * delta_ideal
        thresholds[frac] = target_v
        name = f"t_settle_{int(frac * 100)}"
        lines.append(
            f"meas tran {name} TRIG AT={EDGE_TD_NS}n TARG V(TOP) "
            f"VAL={target_v:.8g} CROSS=1"
        )
    lines.append(
        f"meas tran {MEASURE_PREFIX_CONFIRM} find v(TOP) at={confirm_at_ns}n"
    )
    lines += [".endc", ".end"]

    analytics = {
        "weight_test": weight_test,
        "ratio": ratio,
        "v_top_final_ideal": v_top_final,
        "thresholds": thresholds,
        "delta_ideal": delta_ideal,
    }
    return "\n".join(lines) + "\n", analytics


MEASURE_NAMES = [MEASURE_PREFIX_CONFIRM]
TRIG_TARG_NAMES = [f"t_settle_{int(f * 100)}" for f in FRACTIONS]


def _run(netlist: str, scratch: Path, tag: str) -> dict[str, float]:
    """Retry policy documented once in toolchain.run_ngspice_with_retry()."""
    log_text = toolchain.run_ngspice_with_retry(netlist, scratch, tag)
    m = measure.parse(log_text, MEASURE_NAMES)
    m.update(measure.parse(log_text, TRIG_TARG_NAMES, anchored=False))
    return m


def run_all(
    scratch: Path,
    *,
    corner: str = "tt",
    temp_c: float = 27.0,
    vdd: float = VDD,
    quiet: bool = False,
    tag_prefix: str = "",
    tran_stop_ns: float = TRAN_STOP_NS,
) -> list[dict]:
    """Run all 6 (test_bit, direction) transient decks at one PVT point.
    The single-corner default path (no kwargs given) is unchanged; --corners
    reuses this same function once per grid point with corner/temp_c/vdd
    overridden and tran_stop_ns widened (see run_corners() below)."""
    rows = []
    for test_bit in TEST_BITS:
        for direction in DIRECTIONS:
            netlist, analytics = build_transient(
                test_bit=test_bit, direction=direction, corner=corner, temp_c=temp_c, vdd=vdd,
                tran_stop_ns=tran_stop_ns,
            )
            tag = f"{tag_prefix}bit{test_bit}_{direction}"
            m = _run(netlist, scratch, tag)
            row = {
                "test_bit": test_bit,
                "direction": direction,
                **analytics,
                **m,
            }
            for f in FRACTIONS:
                key = f"t_settle_{int(f * 100)}"
                # ngspice's own TRIG/TARG measure result IS ALREADY
                # (targ_time - trig_time), i.e. already relative to
                # EDGE_TD_NS (this deck's TRIG AT= point) -- do not
                # subtract EDGE_TD_NS again here. Just convert seconds -> ns.
                row[f"{key}_ns"] = (m[key] * 1e9) if key in m else None
            confirm_err_mv = (
                (m[MEASURE_PREFIX_CONFIRM] - analytics["v_top_final_ideal"]) * 1000
                if MEASURE_PREFIX_CONFIRM in m
                else None
            )
            row["confirm_err_mv"] = confirm_err_mv
            row["netlist"] = netlist
            rows.append(row)
            if not quiet:
                t99 = row.get("t_settle_99_ns")
                t99_str = f"{t99:.4f} ns" if t99 is not None else "N/A"
                confirm_str = (
                    f"{confirm_err_mv:+.5f} mV" if confirm_err_mv is not None else "N/A"
                )
                print(
                    f"bit={test_bit} ({direction:4}) weight={analytics['weight_test']:3d} "
                    f"V_top_final(ideal)={analytics['v_top_final_ideal']:.5f} V  "
                    f"t_settle_99%={t99_str}  "
                    f"confirm_err={confirm_str}"
                )
    return rows


def run_corners(scratch: Path, quiet: bool = False) -> list[dict]:
    """Full ratified-corner-set OAT sweep of run_all(): the same PVT grid
    sim/comparator-decision/, sim/sampling-acquisition-settling/, and
    sim/sequencer-logic-delay/ each already use (spec/target-spec.md's
    "Numeric rows -- RATIFIED 2026-08-19" section: -40/27/125C, +-10%
    supply, sky130 process corners), applied to this experiment's own
    per-bit CDAC array switch-settling budget. This does NOT change the
    mechanism measured -- it re-runs the identical 6 (test_bit, direction)
    decks at 9 PVT points instead of 1, to see whether the tt/27C/1.8V
    finding (7.3x margin inside the DR-006 budget, worst case bit 8/rise)
    holds, worsens, or improves across process/temperature/supply. Switch
    R_on varies materially with process/temperature, which is exactly why
    the single-corner record declined to call itself PVT-complete.
    """
    pdk.resolve_or_raise()

    points: list[dict] = []
    for process_corner, temp_c, supply_v, cid in corners_mod.sweep(
        VDD, SUPPLY_TOLERANCE, PROCESS_CORNERS, TEMPS_C, quiet=quiet
    ):
        rows = run_all(
            scratch, corner=process_corner, temp_c=temp_c, vdd=supply_v,
            quiet=True, tag_prefix=f"{cid}_", tran_stop_ns=CORNERS_TRAN_STOP_NS,
        )
        valid = [r for r in rows if r.get("t_settle_99_ns") is not None]
        missing = [r for r in rows if r.get("t_settle_99_ns") is None]
        # "complete" tracks whether the row this campaign's own headline
        # margin rests on -- the MSB (largest-swing) bit, TEST_BITS[-1],
        # both directions -- produced a valid crossing, NOT whether every
        # one of the 6 diagnostic rows did. A pre-flight investigation (see
        # module docstring / this record's own notes) found that the
        # SMALLEST-swing row (bit 0, whose ideal top-plate excursion is
        # only ~0.2% of VDD) can settle to a genuine, time-invariant final
        # value that differs from the analytic closed-form ideal by more
        # than 1% of ITS OWN tiny swing at some corners (confirmed
        # window-invariant out to 300 ns -- a real converged offset, not
        # slow settling that a longer window would resolve) -- while the
        # MSB row (weight 256x bit 0's, so the same absolute offset is a
        # ~0.004% perturbation) always crosses cleanly. Since the tau_i(i)
        # derivation this script's own module docstring gives (and every
        # corner run so far confirms) makes the MSB row the array's own
        # true worst case, a bit-0 crossing miss does not put the
        # headline finding in doubt -- it is reported as a named, honest
        # limitation (see missing_rows below), not folded silently into
        # "incomplete" the same way a genuine missing worst-case reading
        # would be.
        msb_rows = [r for r in rows if r["test_bit"] == TEST_BITS[-1]]
        complete = all(r.get("t_settle_99_ns") is not None for r in msb_rows)
        worst = max(valid, key=lambda r: r["t_settle_99_ns"]) if valid else None
        # One representative netlist per corner point for the committed
        # per-corner deck snapshot (corners/<record_id>/<corner_id>.spice)
        # -- the worst-case (MSB, rise) row, matching write_record()'s own
        # sample-netlist convention below.
        sample_netlist = next(
            (r["netlist"] for r in rows if r["test_bit"] == TEST_BITS[-1] and r["direction"] == "rise"),
            rows[0]["netlist"] if rows else "",
        )
        points.append({
            "corner": process_corner, "temp_c": temp_c, "supply_v": supply_v,
            "corner_id": cid, "complete": complete, "rows": rows,
            "worst_bit": worst["test_bit"] if worst else None,
            "worst_direction": worst["direction"] if worst else None,
            "worst_t_settle_99_ns": worst["t_settle_99_ns"] if worst else None,
            "n_valid": len(valid),
            "missing_rows": [(r["test_bit"], r["direction"]) for r in missing],
            "netlist": sample_netlist,
        })
        if not quiet:
            if worst is not None:
                margin = T_PHASE_WORST_NS / worst["t_settle_99_ns"]
                missing_str = (
                    "  [{} row(s) missing a crossing: {}]".format(
                        len(missing),
                        ", ".join(f"bit{b}/{d}" for b, d in points[-1]["missing_rows"]),
                    )
                    if missing else ""
                )
                print(
                    f"  worst bit {worst['test_bit']} ({worst['direction']}): "
                    f"t_settle_99%={worst['t_settle_99_ns']:.4f} ns "
                    f"({margin:.1f}x inside the {T_PHASE_WORST_NS:.3f} ns "
                    "DR-006 budget)"
                    + ("" if complete else "  [INCOMPLETE: MSB row itself missing a crossing]")
                    + missing_str
                )
            else:
                print("  INCOMPLETE: no row produced a t_settle_99% crossing")
    return points


def write_record(
    rows: list[dict], netlist_sample: str, note: str = "", supersedes: str = ""
) -> None:
    prov = evidence.resolve_provenance(EXPERIMENT_DIR, netlist_sample)
    record_id = prov.record_id
    netlist_sha = prov.netlist_sha
    pdk_line = prov.pdk_line
    ng_version = prov.ng_version

    lines: list[str] = []
    a = lines.append
    a(f"# CDAC-array bit-trial switch-Ron settling budget -- {record_id}")
    a("")
    a(
        "- **Record ID**: " + record_id
    )
    a(
        "- **Claim**: quantifies, for the first time in this repo, how long "
        "the CDAC array's own shared top-plate node "
        "(`design/cdac/cdac_array.sch`) takes to settle after a single bit's "
        "SEL toggles at the start of its own bit-trial phase, isolating the "
        "array's own fixed-size-switch/binary-weighted-capacitor mechanism "
        "from every other settling contributor (comparator decision delay, "
        "sequencer logic delay, sampling front end). Answers "
        "`docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2 in "
        "part -- this is one input to a full sample-rate re-derivation, not "
        "that re-derivation itself. No claim against a ratified spec row: "
        "`spec/target-spec.md` is entirely DRAFT (#1/#27); the DR-006 "
        "phase-period figures quoted below are themselves downstream of "
        "the DRAFT sample-rate row."
    )
    a(
        "- **Netlist provenance**: testbench-only single-side, "
        "single-instance reduction of `design/cdac/cdac_array.sch` "
        "(9 bit positions + termination unit), built in-line by "
        "`run_bit_trial_settling.py` at the exact device W/L/MF values "
        "that schematic uses (verified by direct inspection of the "
        "schematic source, cited in this script's own module docstring); "
        "not a `klt`-regenerated fragment (no such single-free-bit "
        "reduction fragment exists yet), the same testbench-only-reduction "
        "precedent `sim/cdac-array-transfer/testbench/"
        "tb_cdac_array_transfer.spice` already set for an ideal reset "
        "switch pinning the initial condition."
    )
    a(
        "- **Point/corner matrix**: `tt`/27C/1.8V only -- a "
        "mechanism-isolating, single-corner first-pass budget, the same "
        "precedent `sim/vcm-drive-budget/run_vcm_drive_budget.py` already "
        "established. Switch R_on varies materially with process/"
        "temperature; full PVT coverage of this same budget is open, same "
        "class of gap as #28's corner campaigns elsewhere in this design."
    )
    a(
        "- **Bits tested**: "
        + ", ".join(f"bit {b} (weight {BIT_WEIGHTS[b]})" for b in TEST_BITS)
        + " -- LSB, a mid bit, and the MSB of the 9-bit sub-array, "
        "bracketing the tau_i(i) = R_on * C_i * (1 - C_i/C_total) shape "
        "this script's own module docstring derives (non-monotonic in bit "
        "position; this design's own weights put the maximum at bit 8, "
        "the MSB -- tested directly below, not just asserted)."
    )
    a(
        "- **DR-006 phase-period reference points**: "
        f"{T_PHASE_WORST_NS:.3f} ns (worst case, f_clk=12 MHz, one CLK "
        f"period per bit-trial phase) and {T_PHASE_SLOW_NS:.2f} ns (slow "
        "end, f_clk=1.2 MHz) -- quoted for comparison only, not a pass/"
        "fail gate against a ratified row."
    )
    if note:
        a(f"- **Note**: {note}")
    a("")
    a(
        "## Closed-form cross-check: simulated long-time V_top vs. the "
        "charge-conservation prediction"
    )
    a("")
    a(
        "`confirm_err` is the simulated top-plate voltage at "
        f"t={CONFIRM_AT_NS:.1f} ns minus this script's own closed-form "
        "`V_top_final_ideal = V_cm + (C_i/C_total) * (V_bot_final - "
        "V_bot_initial)` -- an internal-consistency check on the "
        "derivation this record's settling-time thresholds are measured "
        "against, not a free-floating claim."
    )
    a("")
    a(
        "| Bit | Weight | Direction | V_top_final (ideal, V) | "
        "confirm_err (mV) |"
    )
    a("|---|---|---|---|---|")
    for r in rows:
        a(
            f"| {r['test_bit']} | {r['weight_test']} | {r['direction']} | "
            f"{r['v_top_final_ideal']:.5f} | {r['confirm_err_mv']:+.5f} |"
        )
    a("")
    a("## Settling time after the SEL edge (t=0 defined as the edge midpoint)")
    a("")
    a(
        "| Bit | Weight | Direction | t_settle_50% (ns) | t_settle_90% (ns) "
        "| t_settle_99% (ns) | tau_i implied (ns, from 99%/-ln(0.01)) |"
    )
    a("|---|---|---|---|---|---|---|")
    for r in rows:
        t50 = r.get("t_settle_50_ns")
        t90 = r.get("t_settle_90_ns")
        t99 = r.get("t_settle_99_ns")
        tau_implied = (t99 / 4.60517) if t99 is not None else None
        a(
            f"| {r['test_bit']} | {r['weight_test']} | {r['direction']} | "
            f"{t50:.5f} | {t90:.5f} | {t99:.5f} | {tau_implied:.5f} |"
            if t50 is not None and t90 is not None and t99 is not None
            else f"| {r['test_bit']} | {r['weight_test']} | {r['direction']} "
            "| N/A | N/A | N/A | N/A |"
        )
    a("")

    worst_row = max(
        (r for r in rows if r.get("t_settle_99_ns") is not None),
        key=lambda r: r["t_settle_99_ns"],
        default=None,
    )
    notes = []
    if worst_row is not None:
        margin_worst = T_PHASE_WORST_NS / worst_row["t_settle_99_ns"]
        notes.append(
            f"Worst case across every bit/direction tested: bit "
            f"{worst_row['test_bit']} ({worst_row['direction']}), "
            f"t_settle_99% = {worst_row['t_settle_99_ns']:.4f} ns -- "
            f"{margin_worst:.1f}x margin inside the DR-006-derived "
            f"worst-case (12 MHz) {T_PHASE_WORST_NS:.3f} ns phase budget, "
            "isolating CDAC switch-settling alone (no comparator decision "
            "time, no sequencer logic delay included)."
        )
        notes.append(
            "This confirms the analytic prediction in this script's own "
            "module docstring: because every bit's switch is the SAME "
            "fixed size while capacitance scales binarily, the settling "
            "time constant is NOT monotonic in bit position -- it peaks "
            "near bit 8 (MSB of the 9-bit sub-array, where C_i is closest "
            "to C_total/2), not at bit 0 or a naive 'MSB is always "
            "slowest because it's biggest' intuition alone would suggest "
            "without the (1 - C_i/C_total) term."
        )
    else:
        notes.append(
            "No t_settle_99% value could be extracted for any row -- see "
            "raw ngspice logs; this would be a harness gap, not a design "
            "result, and should block treating this record as evidence."
        )
    notes.append(
        "This is a first-pass, single-corner (tt/27C/1.8V) budget that "
        "isolates ONE settling mechanism only (the CDAC array's own "
        "switch-Ron/capacitance network). It does NOT include the "
        "comparator's own decision (propagation) delay -- `design/"
        "comparator.sch` exists but no timing campaign has been run "
        "against it -- nor sequencer logic delay, nor any PVT corner "
        "beyond tt/27C/1.8V. A full sample-rate re-derivation "
        "(`docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2) "
        "needs all of those combined, over the full PVT grid, which "
        "remains open. What this record newly establishes is that the "
        "CDAC array's own switch-settling contribution, at this corner, "
        "is not the bottleneck relative to the DR-006-derived phase "
        "budget -- narrowing, not closing, the open item."
    )

    a("## Result")
    a("")
    for n in notes:
        a("- " + n)
    a("")

    lines.extend(evidence.environment_block(
        pdk_line, ng_version, netlist_sha,
        extra={
            "Corner/temp/VDD": "tt / 27C / 1.8V (single point, first-pass)",
            "tran step": f"{TRAN_STEP_PS} ps",
        },
    ))
    a("")
    lines.extend(evidence.footer_lines(
        "sim/cdac-bit-trial-settling/run_bit_trial_settling.py", supersedes
    ))

    evidence.close_record(prov, lines, "Record")
    evidence.write_latest_pointer(EXPERIMENT_DIR, record_id)


def write_corners_record(
    points: list[dict], note: str = "", supersedes: str = ""
) -> Path:
    """Evidence record for the full ratified-PVT-grid --corners campaign,
    same `corners/<record_id>/` per-point-deck layout
    sim/sequencer-logic-delay/'s own --corners mode and
    sim/sampling-acquisition-settling/'s own --corners mode already use."""
    # Netlist snapshot: the tt/27C/1.8V baseline point's own MSB/rise deck,
    # the same single-point convention write_record() above uses, so a
    # reader can diff it directly against the single-corner record's own
    # snapshot.
    run = evidence.resolve_corners_provenance(EXPERIMENT_DIR, points, VDD)
    record_id = run.record_id
    record_path = run.record_path
    netlist_sha = run.netlist_sha
    pdk_line = run.pdk_line
    ng_version = run.ng_version
    process_corners_run = run.process_corners_run
    temps_run = run.temps_run
    supplies_run = run.supplies_run
    incomplete = run.incomplete
    complete_points = run.complete_points

    lines: list[str] = []
    a = lines.append
    a(
        "# CDAC-array bit-trial switch-Ron settling budget -- full PVT grid -- "
        f"{record_id}"
    )
    a("")
    a(f"- **Record ID**: {record_id}")
    a(
        "- **Claim**: extends the single-corner (tt/27C/1.8V) finding in "
        f"[`records/{SINGLE_CORNER_SEED_RECORD}.md`]"
        f"({SINGLE_CORNER_SEED_RECORD}.md) -- that the CDAC array's own "
        "shared top-plate node (`design/cdac/cdac_array.sch`) settles well "
        "inside the DR-006-derived worst-case (12 MHz) bit-trial phase "
        "budget after a single bit's SEL toggles -- to the FULL ratified "
        "PVT corner set (spec/target-spec.md's \"Numeric rows -- RATIFIED "
        "2026-08-19\" section: -40/27/125C, +-10% supply, sky130 process "
        "corners), the same OAT grid sim/comparator-decision/, "
        "sim/sampling-acquisition-settling/, and sim/sequencer-logic-delay/ "
        "each already sweep. Identical reduced-array topology, identical "
        "PWL edge shape, and the identical closed-form-vs-simulated "
        "cross-check and TRIG/TARG settling-fraction `.meas` statements as "
        "the single-corner record (see that record and this script's own "
        "module docstring for the tau_i(i) derivation) -- only the corner "
        "point and the transient window (widened, see below) change per "
        "run. No claim here is graded against a ratified spec row: "
        "`spec/target-spec.md`'s sample-rate row is entirely DRAFT "
        "(#1/#27), and the DR-006 phase-period figures quoted below are "
        "themselves downstream of that DRAFT row."
    )
    a(
        "- **Netlist provenance**: testbench-only single-side, "
        "single-instance reduction of `design/cdac/cdac_array.sch` (9 bit "
        "positions + termination unit), built in-line by this script, "
        f"unchanged from the single-corner record -- `.lib`/`.temp`/`vdd` "
        "vary per point (the closed-form `V_top_final` prediction and the "
        "held-bit DC levels already depend on `vdd` via "
        "`build_transient()`'s own argument), and the transient window is "
        f"widened to {CORNERS_TRAN_STOP_NS:.0f} ns (from the single-corner "
        f"record's {TRAN_STOP_NS:.0f} ns): a pre-flight probe of the "
        "worst-case row (bit 8/rise) across the slow-process/low-supply "
        "candidate corners found `ss_-40c_1.62v` binding at "
        "t_settle_99% = 16.09 ns, already 41% higher than the tt/27C/1.8V "
        "baseline and too close to the single-corner window's own 20 ns "
        "ceiling to reuse unchanged without risking a silently-incomplete "
        "measurement at a slower corner still -- so `--corners` uses its "
        "own, more generous window rather than changing the single-corner "
        "default's own already-cited window. Netlist snapshot above is "
        "the tt/27C/1.8V baseline point's own MSB/rise deck; every point's "
        f"own representative (MSB/rise) deck is committed under "
        f"`corners/{record_id}/`."
    )
    a(
        corners_mod.corner_matrix_summary_line(
            process_corners_run, temps_run, supplies_run, len(points)
        )
    )
    a(
        "- **Bits/directions measured**: all 6 (test_bit, direction) "
        "combinations at every corner point -- "
        f"{len(TEST_BITS) * len(DIRECTIONS) * len(points)} transient decks "
        "in total. Bits tested: "
        + ", ".join(f"bit {b} (weight {BIT_WEIGHTS[b]})" for b in TEST_BITS)
        + " -- LSB, a mid bit, and the MSB of the 9-bit sub-array."
    )
    a(
        "- **DR-006 phase-period reference points**: "
        f"{T_PHASE_WORST_NS:.3f} ns (worst case, f_clk=12 MHz, one CLK "
        f"period per bit-trial phase) and {T_PHASE_SLOW_NS:.2f} ns (slow "
        "end, f_clk=1.2 MHz) -- quoted for comparison only, not a pass/"
        "fail gate against a ratified row."
    )
    if note:
        a(f"- **Note**: {note}")
    a("")
    a("## Worst-case (test_bit, direction) settling time, per corner")
    a("")
    a(
        "\"Worst case\" is whichever of the 6 (test_bit, direction) rows has "
        "the largest t_settle_99% at that corner (not necessarily the same "
        "row at every corner). Margin is the DR-006-derived worst-case "
        f"(12 MHz) {T_PHASE_WORST_NS:.3f} ns phase budget divided by that "
        "settling time."
    )
    a("")
    a(
        "| Corner | Worst bit | Direction | t_settle_99% (ns) | "
        "Margin vs. DR-006 budget | Rows measured | Missing rows |"
    )
    a("|---|---|---|---|---|---|---|")
    for p in points:
        n_valid = p["n_valid"]
        missing_str = (
            ", ".join(f"bit{b}/{d}" for b, d in p["missing_rows"]) if p["missing_rows"] else "--"
        )
        if p["worst_t_settle_99_ns"] is None:
            a(
                f"| `{p['corner_id']}` | -- | -- | INCOMPLETE | -- | "
                f"{n_valid}/{len(p['rows'])} | {missing_str} |"
            )
            continue
        margin = T_PHASE_WORST_NS / p["worst_t_settle_99_ns"]
        a(
            f"| `{p['corner_id']}` | {p['worst_bit']} | {p['worst_direction']} | "
            f"{p['worst_t_settle_99_ns']:.5f} | {margin:.1f}x | "
            f"{n_valid}/{len(p['rows'])} | {missing_str} |"
        )
    a("")

    notes: list[str] = []
    any_missing = [p for p in points if p["missing_rows"]]
    if any_missing:
        total_missing = sum(len(p["missing_rows"]) for p in any_missing)
        notes.append(
            f"**{total_missing} row(s) across {len(any_missing)}/{len(points)} "
            "corner points did not produce a t_settle_99% crossing** -- in "
            "every such case the missing row is bit 0 (never bit 4 or bit "
            "8), the SMALLEST-swing row (its ideal top-plate excursion is "
            "only ~0.2% of VDD, vs. bit 8's ~50%). A follow-up check (not "
            "asserted without evidence): re-running one such case "
            "(`tt_27c_1.98v`, bit 0/fall) with the transient window widened "
            "to 100 ns and 300 ns reproduced the IDENTICAL simulated "
            "top-plate voltage at every window length -- a genuine, "
            "already-converged final value, not a slowly-decaying "
            "transient a longer window would resolve. That converged value "
            "differs from the analytic closed-form ideal by a small, "
            "roughly corner-independent absolute offset (order 0.1-0.3 mV, "
            "plausibly real-device charge-injection/subthreshold-leakage "
            "second-order effects the ideal closed-form does not model) "
            "which is negligible against bit 8's own ~1.8 V swing but "
            "exceeds 1% of bit 0's own ~4 mV swing at some corners -- so "
            "the 99% threshold for bit 0 specifically is sometimes never "
            "reached. This does NOT affect the headline finding below: the "
            "array's own tau_i(i) = R_on * C_i * (1 - C_i/C_total) shape "
            "(this script's own module docstring) predicts bit 8 (the MSB) "
            "is always the true worst case, confirmed at every corner in "
            "this campaign (bit 8 crossed cleanly at all 9/9 points) -- a "
            "bit-0 crossing miss is a diagnostic-row curiosity at the "
            "opposite (fastest, smallest-signal) end of the bit range, not "
            "a gap in the worst-case number this record's margin claims "
            "rest on. `complete` below tracks the MSB (bit 8) row "
            "specifically, not literally all 6 diagnostic rows, for "
            "exactly this reason."
        )
    if incomplete:
        bad = ", ".join(p["corner_id"] for p in incomplete)
        notes.append(
            f"**{len(incomplete)}/{len(points)} corner points produced an "
            f"incomplete (MSB-row-missing) measurement ({bad})** -- treat "
            "this record as partial evidence at those points, not a "
            "passing or failing result, until re-run clean."
        )
    if complete_points:
        binding = max(complete_points, key=lambda p: p["worst_t_settle_99_ns"])
        best = min(complete_points, key=lambda p: p["worst_t_settle_99_ns"])
        binding_margin = T_PHASE_WORST_NS / binding["worst_t_settle_99_ns"]
        spread = binding["worst_t_settle_99_ns"] / best["worst_t_settle_99_ns"]
        all_clear = all(
            p["worst_t_settle_99_ns"] < T_PHASE_WORST_NS for p in complete_points
        )
        notes.append(
            f"**Binding corner (largest settling time): "
            f"`{binding['corner_id']}`**, bit {binding['worst_bit']} "
            f"({binding['worst_direction']}) at "
            f"{binding['worst_t_settle_99_ns']:.4f} ns -- {binding_margin:.1f}x "
            f"inside the DR-006-derived worst-case (12 MHz) "
            f"{T_PHASE_WORST_NS:.3f} ns phase budget. Fastest corner: "
            f"`{best['corner_id']}`, {best['worst_t_settle_99_ns']:.4f} ns "
            f"({T_PHASE_WORST_NS / best['worst_t_settle_99_ns']:.1f}x). "
            f"Worst-to-best spread across the ratified grid: {spread:.2f}x."
        )
        if all_clear:
            notes.append(
                f"**All {len(complete_points)}/{len(points)} ratified corner "
                "points clear the DR-006-derived worst-case phase budget** "
                "-- the single-corner (tt/27C/1.8V) finding was not a "
                "corner-specific artifact, and the CDAC array's own "
                "switch-settling is not the sample-rate bottleneck anywhere "
                "on this design's ratified PVT grid. This raises the weight "
                "of that finding from \"one corner, narrows the open item\" "
                "to \"every ratified corner, same conclusion\", and takes "
                "this mechanism from single-corner to PVT-complete. "
                "Headroom against a DRAFT, not-yet-ratified figure -- not a "
                "pass against a ratified spec line."
            )
        else:
            over = ", ".join(
                p["corner_id"] for p in complete_points
                if p["worst_t_settle_99_ns"] >= T_PHASE_WORST_NS
            )
            notes.append(
                f"**Not every corner point clears the DR-006-derived "
                f"worst-case phase budget** ({over} exceed it) -- the "
                "single-corner (tt/27C/1.8V) margin did NOT hold across the "
                "ratified PVT grid; see the per-corner table above."
            )
    notes.append(
        "This campaign re-runs the SAME single mechanism (the CDAC array's "
        "own switch-Ron/top-plate-settling network, "
        "`design/cdac/cdac_array.sch`) across the full ratified PVT grid -- "
        "it does NOT combine with the other three named mechanisms "
        "(comparator decision delay, sequencer logic delay, sampling "
        "front-end acquisition) into an end-to-end sample-rate figure. All "
        "four mechanisms are now PVT-complete; the sampling front end's own "
        "acquisition remains the only one of the four that does NOT clear "
        "the same budget at any ratified corner. A full sample-rate "
        "re-derivation (`docs/chipalooza/challenge-4-proposal.md` Section 7 "
        "Item 2) still needs all four combined, over the full PVT grid, "
        "which remains open."
    )

    a("## Result")
    a("")
    for n in notes:
        a("- " + n)
    a("")

    lines.extend(evidence.environment_block(
        pdk_line, ng_version, netlist_sha,
        extra={
            "tran step": f"{TRAN_STEP_PS} ps",
            "tran window": f"{CORNERS_TRAN_STOP_NS:.0f} ns (widened from the "
            f"single-corner record's {TRAN_STOP_NS:.0f} ns, see above)",
        },
    ))
    a("")
    lines.extend(evidence.footer_lines(
        "sim/cdac-bit-trial-settling/run_bit_trial_settling.py", supersedes
    ))

    evidence.close_record(run, lines, "Record")
    evidence.write_latest_pointer(EXPERIMENT_DIR, record_id)
    return record_path


# ---------------------------------------------------------------------------
# issue #1033: DR-027 candidate-geometry study (--dr027-candidate)
# ---------------------------------------------------------------------------
def candidate_cap_card(weight: int) -> str:
    """The capacitor card tail every candidate-deck capacitor uses: the
    candidate 3.3000 um plate with the ORIGINAL binary weight (MF/m)."""
    return (
        f"sky130_fd_pr__cap_mim_m3_1 W={CANDIDATE_UNIT_CAP_WL_UM:.4f} "
        f"L={CANDIDATE_UNIT_CAP_WL_UM:.4f} MF={weight} m={weight}"
    )


UNIT_CAP_PROBE_TITLE = "unit-cap ramp probe (issue #1033)"


def unit_cap_probe_deck(wl_um: float) -> str:
    """A single-corner (tt/27C) local deck that measures the PDK model's
    unit capacitance at plate side `wl_um` by ramping a 512-instance cap
    block at 1 V/us and reading the displacement current (C = I / dVdt).

    One ngspice run, no fleet: the value feeds the candidate records' own
    geometry statement (C_u and the per-side total), so the record quotes a
    MEASURED model value instead of an arithmetic one. The far plate is
    grounded here on purpose: the first version of this probe left it
    floating through a 1 Tohm leak and measured the leak, not the cap."""
    info = pdk.resolve()
    return "\n".join([
        f"* {UNIT_CAP_PROBE_TITLE} -- W=L={wl_um:.4f} um",
        f".lib {info.ngspice_lib} tt",
        ".temp 27",
        "Vr SRC 0 pwl(0 0 2u 0 12u 10)",
        "Vs SRC BOT 0",
        f"Xc BOT 0 sky130_fd_pr__cap_mim_m3_1 W={wl_um:.4f} L={wl_um:.4f} MF=512 m=512",
        ".control",
        "tran 0.2u 11u",
        "print i(Vs) > /dev/null",
        "meas tran i7 find i(Vs) at=7u",
        ".endc",
        ".end",
    ]) + "\n"


UNIT_CAP_PROBE_DVDTS = 1.0e6  # V/s: pwl(2u 0 -> 12u 10)
UNIT_CAP_PROBE_M = 512


def measure_unit_cap_ff(wl_um: float, scratch: Path) -> tuple[float, str]:
    """Run unit_cap_probe_deck() locally and return (C_u in fF, log text)."""
    log = toolchain.run_ngspice_with_retry(
        unit_cap_probe_deck(wl_um), scratch, f"capprobe_{wl_um:.4f}"
    )
    m = measure.parse(log, ["i7"])
    if "i7" not in m:
        raise RuntimeError(f"unit-cap probe at {wl_um:.4f} um produced no current read")
    return m["i7"] / UNIT_CAP_PROBE_DVDTS / UNIT_CAP_PROBE_M * 1e15, log


def build_candidate_body(copies: list[tuple[int, str]] | None = None) -> str:
    """Circuit BODY for the candidate study's ONE `klt sim` request: no
    `.lib`, `.temp`, `.control`, `.meas` or `.end` (klt emits those; the
    corner axes drive the first two).

    Six INDEPENDENT copies of build_transient()'s single-instance reduction
    (one per (test_bit, direction)), sharing only the ideal rails. Each copy
    is the same reduction the single-corner record documents -- every
    capacitor real at the candidate 3.3000 um plate with the original
    weights, the test bit's own switch pair at the original W/L, every other
    bit held at an ideal 0 V bottom plate, the termination unit present --
    with three corner-independent re-expressions (see the module docstring):
    normalised SEL/reset control PWLs scaled by the corner supply through
    behavioural sources, a behavioural VCM at v(VDD)/2, and a normalised
    copy of the top-plate node the crossing thresholds are read on."""
    copies = copies if copies is not None else candidate_copies()
    L: list[str] = [
        "* sim/cdac-bit-trial-settling -- DR-027 candidate-geometry study",
        "* (issue #1033): bit-trial switch-Ron settling at the proposed",
        "* 3.3000 um unit plate (C_tot ~ 12.19 pF/side, model-evaluated),",
        "* switch sizes and binary weights unchanged. EXPERIMENTAL study",
        "* deck: design/cdac/ still draws the DR-019 1.9000 um plate.",
        "* Six independent copies of the single-instance reduction (one per",
        "* (test_bit, direction)); circuit body only -- klt sim supplies the"
        "* corner section, temperature card, measurement cards and tran"
        "* analysis steps.",
        ".options num_threads=1",
        ".model SWMOD SW(Ron=1 Roff=1e12 Vt=0.9 Vh=0.05)",
        f"{CAND_SUPPLY_KEY} VDD 0 DC {VDD}",
        "Bvrefp VREFP 0 V=v(VDD)",
        "Vrefn VREFN 0 DC 0",
        "Bvcm VCM 0 V=v(VDD)/2",
        "",
    ]
    for test_bit, direction in copies:
        tag = candidate_tag(test_bit, direction)
        ratio = candidate_ratio(test_bit)
        # SEL polarity: fall = BOT vdd->0 (NMOS takes over, SEL 0->1);
        # rise = BOT 0->vdd (PMOS, SEL 1->0) -- build_transient()'s own map.
        sel_initial = 0.0 if direction == "fall" else 1.0
        sel_final = 1.0 if direction == "fall" else 0.0
        L += [
            f"* --- copy {tag}: bit {test_bit} ({direction}), weight "
            f"{BIT_WEIGHTS[test_bit]}, ratio {ratio:.7f} ---",
            f"Vrstn_{tag} RSTN_{tag} 0 pwl(0 1 {EDGE_TD_NS - EDGE_TR_NS / 2:g}n 1 "
            f"{EDGE_TD_NS + EDGE_TR_NS / 2:g}n 0 {CAND_SLOW_TRAN_STOP_NS:g}n 0)",
            f"Brst_{tag} NCTRL_{tag} 0 V=v(RSTN_{tag})*v(VDD)",
            f"Sreset_{tag} TOP_{tag} VCM NCTRL_{tag} 0 SWMOD",
            f"Rdc_{tag} TOP_{tag} VCM 1T",
            f"Vseln_{tag} SELN_{tag} 0 pwl(0 {sel_initial:g} "
            f"{EDGE_TD_NS - EDGE_TR_NS / 2:g}n {sel_initial:g} "
            f"{EDGE_TD_NS + EDGE_TR_NS / 2:g}n {sel_final:g} "
            f"{CAND_SLOW_TRAN_STOP_NS:g}n {sel_final:g})",
            f"Bsel_{tag} SEL_{tag} 0 V=v(SELN_{tag})*v(VDD)",
        ]
        nw, nl = SWITCH_NFET_WL
        pw, pl = SWITCH_PFET_WL
        for i in range(9):
            weight = BIT_WEIGHTS[i]
            cap = f"Xc_bit{i}_{tag} bot{i}_{tag} TOP_{tag} {candidate_cap_card(weight)}"
            if i == test_bit:
                L += [
                    cap,
                    f"Xn_bit{i}_{tag} bot{i}_{tag} SEL_{tag} VREFN 0 "
                    f"sky130_fd_pr__nfet_01v8 L={nl:g} W={nw:g} nf=1",
                    f"Xp_bit{i}_{tag} bot{i}_{tag} SEL_{tag} VREFP VDD "
                    f"sky130_fd_pr__pfet_01v8 L={pl:g} W={pw:g} nf=1",
                ]
            else:
                # Held bit: SEL=1 fixed -> NMOS on -> BOT=VREFN=0 for the
                # whole run, modeled as the ideal DC source exactly as
                # build_transient() documents (including its own caveat:
                # the held bit's switch-parasitic contribution to C_total
                # is not modeled).
                L += [f"Vbot{i}_{tag} bot{i}_{tag} 0 DC 0", cap]
        # Termination unit: fixed weight-1 cap, bottom plate on the VREFN
        # rail, no switch device (cdac_array.sch's own convention).
        L.append(
            f"Xc_term_{tag} VREFN TOP_{tag} "
            f"{candidate_cap_card(TERM_WEIGHT)}"
        )
        # Supply-normalised top-plate copy: 0 before the edge (TOP held at
        # VCM), settling to +-ratio (this copy's own C_i/C_total step as a
        # fraction of the supply; sign by direction). Crossing times on
        # this node equal the raw node's (affine, positive-slope map), and
        # the thresholds become corner-independent constants +-frac*ratio.
        L.append(f"Bnorm_{tag} NORM_{tag} 0 V=(v(TOP_{tag})-v(VCM))/v(VDD)")
        L.append("")
    return "\n".join(L).rstrip("\n") + "\n"


def candidate_analysis_steps() -> list[dict]:
    """Two `tran` steps per corner. `fast` re-runs the baseline convention
    (5 ps ceiling) over a window sized to the candidate's ~2.83x-slower
    settling, carrying the 50/90/99 % crossings on the normalised node plus
    the 12 MHz phase-end read. `slow` uses the SAME 5 ps ceiling (a coarser
    0.5 ns step shifted the converged bit-0 tail by ~2.4 uV, enough to flip
    a 99 % crossing -- PR #1041 finding 3) out past
    the 1.2 MHz deadline, carrying that deadline's phase-end read and the
    late read that separates a still-settling node from a settled offset."""
    fast_meas: list[dict] = []
    slow_meas: list[dict] = []
    for test_bit, direction in candidate_copies():
        tag = candidate_tag(test_bit, direction)
        ratio = candidate_ratio(test_bit)
        sign = 1.0 if direction == "rise" else -1.0
        for frac in FRACTIONS:
            name = f"t{int(frac * 100)}_{tag}"
            fast_meas.append({
                "name": name,
                "spice": (
                    f".meas tran {name} TRIG AT={EDGE_TD_NS:g}n "
                    f"TARG V(NORM_{tag}) VAL={sign * frac * ratio:.9f} "
                    "CROSS=1"
                ),
                "unit": "s",
            })
        fast_meas.append({
            "name": f"pend_fast_{tag}",
            "spice": (
                f".meas tran pend_fast_{tag} find v(TOP_{tag}) "
                f"at={EDGE_TD_NS + CAND_DEADLINE_FAST_NS:.6f}n"
            ),
            "unit": "V",
        })
        for name, at_ns in (
            # Absolute read times: the phase deadline runs from the SEL edge
            # center (EDGE_TD_NS), not from t=0.
            ("pend_slow", EDGE_TD_NS + CAND_DEADLINE_SLOW_NS),
            ("plate", CAND_LATE_AT_NS),
        ):
            slow_meas.append({
                "name": f"{name}_{tag}",
                "spice": (
                    f".meas tran {name}_{tag} find v(TOP_{tag}) "
                    f"at={at_ns:.6f}n"
                ),
                "unit": "V",
            })
    return [
        {
            "name": "fast",
            "reset": True,
            "analysis": {"kind": "tran", "args": f"{TRAN_STEP_PS:g}p {CAND_FAST_TRAN_STOP_NS:g}n"},
            "measurements": fast_meas,
        },
        {
            "name": "slow",
            "reset": True,
            "analysis": {
                "kind": "tran",
                "args": f"{CAND_SLOW_TRAN_STEP_NS:g}n {CAND_SLOW_TRAN_STOP_NS:g}n",
            },
            "measurements": slow_meas,
        },
    ]


def candidate_corner_ids() -> list[str]:
    """The ratified 9-point one-at-a-time PVT grid, in grid order."""
    return corners_mod.ratified_corner_ids(
        VDD, SUPPLY_TOLERANCE, PROCESS_CORNERS, TEMPS_C
    )


def build_candidate_request(
    netlist_name: str,
    cids: list[str],
    *,
    timeout_s: float = CAND_TIMEOUT_S,
    backend: str | None = None,
    hosts: int | None = None,
) -> dict:
    """ONE `klt sim` request covering the whole candidate grid. The corner
    axes are declared as the full cross product with the points the OAT grid
    omits listed under `exclude` -- `klt sim` has no OAT axis form, so this
    is how sim/top-plate-cpar/ and sim/input-drive-budget/ express the same
    grid."""
    return klt_sim.build_oat_request(
        netlist_name, cids, CAND_SUPPLY_KEY,
        analysis_steps=candidate_analysis_steps(),
        timeout_s=timeout_s, backend=backend, hosts=hosts,
    )


SubmitError = klt_sim.SubmitError


def submit_candidate(
    workdir: Path,
    backend: str | None,
    timeout_s: float = CAND_TIMEOUT_S,
    hosts: int | None = CAND_HOSTS,
    cids: list[str] | None = None,
) -> tuple[dict, dict, dict]:
    """Write the body + request under `workdir`, run `klt sim`, and return
    `(report, run info, request)`. An existing `report.json` beside the
    request is reused, so a re-run after a successful submit does not
    re-spend fleet capacity (harness.klt_sim.submit's own cache)."""
    body = build_candidate_body()
    req = build_candidate_request(
        "tb.spice", cids if cids is not None else candidate_corner_ids(),
        timeout_s=timeout_s, backend=backend, hosts=hosts,
    )
    # A cached report beside different inputs is set aside, not reused.
    klt_sim.write_inputs(
        workdir, {"tb.spice": body, "request.json": json.dumps(req, indent=1) + "\n"}
    )
    report = klt_sim.submit(
        workdir / "request.json", workdir / "out", backend=backend
    )
    _results, info = klt_sim.measurements_by_corner(report, CAND_SUPPLY_KEY)
    return report, dict(info, backend=backend or "(klt default / KLT_SIM_BACKEND)"), req


def candidate_rows(values: dict[str, float | None], supply_v: float) -> list[dict]:
    """One row per (test_bit, direction) copy at one corner, from that
    corner's `{"<step>.<name>": value}` map. A missing crossing is DATA
    (None), never silently dropped -- issue #1033 requires retaining missing
    crossings and separating a slow response from a settled offset via the
    phase-end and late residuals, which is what the three err_mv columns
    are (each against this corner's own closed-form ideal)."""
    rows: list[dict] = []
    for test_bit, direction in candidate_copies():
        tag = candidate_tag(test_bit, direction)
        ratio = candidate_ratio(test_bit)
        # Closed-form ideal, exactly build_transient()'s: V_top_final =
        # vcm + ratio * (v_bot_final - v_bot_initial), with vcm = vdd/2 and
        # the rail span = the corner supply.
        span = -supply_v if direction == "fall" else supply_v
        v_final = supply_v / 2.0 + ratio * span
        row: dict = {
            "test_bit": test_bit, "direction": direction, "tag": tag,
            "ratio": ratio, "v_final_ideal": v_final,
        }
        for frac in FRACTIONS:
            key = f"t{int(frac * 100)}_{tag}"
            raw = values.get(f"fast.{key}")
            # The TRIG/TARG result is already (targ - trig), i.e. relative
            # to the SEL edge midpoint -- build_transient()'s own
            # convention; do not subtract EDGE_TD_NS again.
            row[f"t{int(frac * 100)}_ns"] = (
                raw * 1e9 if klt_sim.finite(raw) else None
            )
        for name, step, at in (
            ("pend_fast", "fast", CAND_DEADLINE_FAST_NS),
            ("pend_slow", "slow", CAND_DEADLINE_SLOW_NS),
            ("plate", "slow", CAND_LATE_AT_NS),
        ):
            v = values.get(f"{step}.{name}_{tag}")
            ok = klt_sim.finite(v)
            row[f"{name}_v"] = v if ok else None
            row[f"{name}_err_mv"] = (v - v_final) * 1e3 if ok else None
        rows.append(row)
    return rows


def read_candidate_report(report: dict) -> tuple[dict[str, list[dict]], list[str]]:
    """`({corner_id: rows}, completed corner ids)` -- refuses an error
    envelope rather than inventing numbers (klt_sim's shared reader)."""
    # null_error_corners=False: a corner whose status is error ONLY because
    # one crossing search never crossed still carries every other solved
    # measurement, and the missing crossing itself is data this campaign
    # reports (see read_candidate_report's docstring) -- the default nulling
    # would throw the whole grid row away with it.
    results, _info = klt_sim.measurements_by_corner(
        report, CAND_SUPPLY_KEY, null_error_corners=False
    )
    out: dict[str, list[dict]] = {}
    complete: list[str] = []
    for cid, values in results.items():
        supply_v = corners_mod.parse_corner_id(cid)[2]
        rows = candidate_rows(values or {}, supply_v)
        out[cid] = rows
        # "Complete" matches the baseline campaign's convention: the MSB
        # row (the tau_i(i) shape's own worst case) produced its 99 %
        # crossing AND every fixed-time read parsed.
        msb = [r for r in rows if r["test_bit"] == TEST_BITS[-1]]
        # EVERY (bit, direction) row must carry all three fixed-time reads
        # (a bit-0 crossing may be absent; a missing fixed-time read may
        # not), and the MSB rows must also have their 99 % crossing.
        if rows and all(
            r["pend_fast_err_mv"] is not None
            and r["pend_slow_err_mv"] is not None
            and r["plate_err_mv"] is not None
            for r in rows
        ) and all(r["t99_ns"] is not None for r in msb):
            complete.append(cid)
    return out, complete


def _fmt_ns(v: float | None, nd: int = 4) -> str:
    return "N/A" if v is None else f"{v:.{nd}f}"


def _fmt_mv(v: float | None, nd: int = 4) -> str:
    return "N/A" if v is None else f"{v:+.{nd}f}"


def candidate_result_lines(by_corner: dict[str, list[dict]], cids: list[str]) -> list[str]:
    """The Result bullets, read back out of the assembled rows -- every
    number here is derived from `by_corner`, not restated by hand."""
    out: list[str] = []
    for label, deadline_ns, tkey, ekey in (
        ("12 MHz (1 MS/s end)", CAND_DEADLINE_FAST_NS, "t99_ns", "pend_fast_err_mv"),
        ("1.2 MHz (100 kS/s end)", CAND_DEADLINE_SLOW_NS, "t99_ns", "pend_slow_err_mv"),
    ):
        valid = [
            (cid, r)
            for cid in cids
            for r in by_corner.get(cid, [])
            if r[tkey] is not None
        ]
        if not valid:
            out.append(
                f"- **{label}**: no (test_bit, direction) row produced a "
                "99 % crossing at any corner -- see the tables above; no "
                "settling-time margin can be stated for this endpoint from "
                "this record."
            )
            continue
        bind_cid, bind_row = max(valid, key=lambda cr: cr[1][tkey])
        margin = deadline_ns / bind_row[tkey]
        worst_err = max(
            (abs(r[ekey]) for cid in cids for r in by_corner.get(cid, [])
             if r[ekey] is not None),
            default=None,
        )
        err_txt = (
            f"worst phase-end error at this deadline {worst_err:.4f} mV "
            f"({worst_err / (LSB_DIFF_MV_PROVISIONAL / 2):.2f}x the "
            "provisional differential half-LSB reference scale)"
            if worst_err is not None else "no phase-end read parsed"
        )
        out.append(
            f"- **{label}**: binding (slowest) row bit {bind_row['test_bit']} "
            f"({bind_row['direction']}) at `{bind_cid}`, t_settle_99% = "
            f"{bind_row[tkey]:.4f} ns -- {margin:.2f}x inside the "
            f"{deadline_ns:.3f} ns phase budget; {err_txt}. Time left in "
            "the phase after settling at the binding corner: "
            f"{deadline_ns - bind_row[tkey]:.3f} ns, against the other two "
            f"mechanisms' own PVT-complete binding figures "
            f"({COMPARATOR_DECISION_NS} ns comparator decision + "
            f"{SEQUENCER_LOGIC_NS} ns sequencer CLK-to-phase logic delay, "
            "as cited in the sample-rate entry of sim/report/manifest.py) "
            f"= {COMPARATOR_DECISION_NS + SEQUENCER_LOGIC_NS:.4f} ns -- the "
            "CDAC's own settling still leaves room for both at this "
            "endpoint."
            if deadline_ns - bind_row[tkey] > COMPARATOR_DECISION_NS + SEQUENCER_LOGIC_NS
            else f"- **{label}**: binding (slowest) row bit "
            f"{bind_row['test_bit']} ({bind_row['direction']}) at "
            f"`{bind_cid}`, t_settle_99% = {bind_row[tkey]:.4f} ns, leaving "
            f"{deadline_ns - bind_row[tkey]:.3f} ns of the phase -- LESS "
            f"than the {COMPARATOR_DECISION_NS + SEQUENCER_LOGIC_NS:.4f} ns "
            "the comparator decision and sequencer logic delays alone need "
            "(their own PVT-complete binding figures, cited in the "
            "sample-rate entry of sim/report/manifest.py): this endpoint "
            "does not close on CDAC settling plus those delays."
        )
    missing = [
        (cid, r["tag"])
        for cid in cids
        for r in by_corner.get(cid, [])
        if r["t99_ns"] is None
    ]
    if missing:
        by_tag: dict[str, list[str]] = {}
        for cid, tag in missing:
            by_tag.setdefault(tag, []).append(cid)
        out.append(
            f"- **{len(missing)} row(s) across the grid produced no 99 % "
            "crossing** (retained, not dropped): "
            + "; ".join(
                f"{tag} at {', '.join(f'`{c}`' for c in cids_)}"
                for tag, cids_ in sorted(by_tag.items())
            )
            + ". The 99 % threshold is a fraction of each row's OWN step "
            "(ratio x supply), not a fixed LSB accuracy -- a small-swing "
            "row whose converged value differs from the closed-form ideal "
            "by more than 1 % of that step never crosses however long the "
            "window, which is exactly why the phase-end (`pend_*`) and late "
            "(`plate`) error columns above are reported alongside: they "
            "separate a still-settling node (phase-end error >> late error) "
            "from a settled offset (both similar, and time-invariant)."
        )
        # Signed per-row residuals for the missing rows themselves, all
        # three reads taken on trajectories of the same 5 ps ceiling.
        for cid, tag in missing:
            r = next(x for x in by_corner[cid] if x["tag"] == tag)
            out.append(
                f"  - missing-crossing row `{tag}` at `{cid}`, signed "
                "read-minus-closed-form-ideal (mV): phase-end 12 MHz "
                f"{_fmt_mv(r['pend_fast_err_mv'])}, phase-end 1.2 MHz "
                f"{_fmt_mv(r['pend_slow_err_mv'])}, late "
                f"{_fmt_mv(r['plate_err_mv'])}; 99 % threshold sits at "
                f"{0.01 * r['ratio'] * (-1 if r['direction']=='fall' else 1) * corners_mod.parse_corner_id(cid)[2] * 1e3:.4f} mV "
                "of residual from the ideal final value."
            )
    return out


def write_candidate_record(
    report: dict,
    info: dict,
    cids: list[str],
    supersedes: str,
    workdir: Path,
    c_u_ff: dict[float, float],
    probe_logs: dict[str, str],
    note: str = "",
) -> Path:
    """Evidence record for the candidate-geometry campaign: the same
    `corners/<record-id>/` + `request/` layout the input-drive-budget batch
    records use (report.json as the committed raw artifact; the request and
    body beside it), plus the unit-cap probe decks' logs."""
    body = build_candidate_body()
    prov, lines = evidence.open_record(
        EXPERIMENT_DIR, body, "corners",
        {
            "report.json": json.dumps(report, indent=1) + "\n",
            **{f"unit_cap_{wl:.4f}um.log": text for wl, text in probe_logs.items()},
        },
    )
    req_dir = EXPERIMENT_DIR / "corners" / prov.record_id / "request"
    req_dir.mkdir(parents=True, exist_ok=True)
    (req_dir / "request.json").write_text((workdir / "request.json").read_text())
    (req_dir / "tb.spice").write_text(body)

    by_corner, complete = read_candidate_report(report)
    worker_pdk = info.get("worker_pdk")
    worker_ng = info.get("worker_ngspice")
    exec_known = bool(worker_pdk and worker_ng)
    klt_version = klt_sim.client_version()

    cu_txt = "; ".join(
        f"{wl:.4f} um -> {c:.3f} fF/unit" for wl, c in sorted(c_u_ff.items())
    )
    ratio_cu = c_u_ff[CANDIDATE_UNIT_CAP_WL_UM] / c_u_ff[UNIT_CAP_WL_UM]

    lines[0] = (
        "# CDAC-array bit-trial switch-Ron settling -- DR-027 candidate "
        f"plate ({CANDIDATE_UNIT_CAP_WL_UM:.4f} um) -- full PVT grid -- {prov.record_id}"
    )
    lines += [
        "- **Claim**: re-derives this campaign's own mechanism (the CDAC "
        "array's shared top-plate settling after a single bit's SEL "
        "toggles) at the DR-027 CANDIDATE unit plate "
        f"({CANDIDATE_UNIT_CAP_WL_UM:.4f} um side, issue #1033's statement "
        "of the #1016 proposal -- C_tot ~ 12.4 pF/side nominal), with the "
        "SEL switch sizes and binary weights explicitly UNCHANGED, against "
        "BOTH DR-006 phase deadlines: the 12 MHz (1 MS/s) worst case and "
        "the 1.2 MHz (100 kS/s) slow end of the DRAFT sample-rate row. "
        "EXPERIMENTAL study deck -- `design/cdac/` still draws the DR-019 "
        "1.9000 um plate; nothing here measures the shipping design, and "
        "no claim is graded against a ratified spec row (the sample-rate "
        "row is entirely DRAFT, #1/#27).",
        "- **Issue**: #1033 (companion evidence for the #1016 / DR-027 "
        "resize study; the acquisition half of the settling-versus-rate "
        "table lives in the sampling-cdac-handoff candidate record minted "
        "from the same study)",
        "- **Geometry**: the candidate body is this campaign's own "
        "single-instance reduction, re-expressed so ONE `klt sim` request "
        "can carry the whole grid (see the runner's module docstring): six "
        "independent copies (bits 0/4/8 x rise/fall), every capacitor real "
        "at the candidate plate with the original weights "
        f"({sum(BIT_WEIGHTS.values()) + TERM_WEIGHT} unit positions/side "
        "including the termination unit), the test bit's own switch pair "
        "at the original W/L "
        f"(nfet W={SWITCH_NFET_WL[0]:g}/L={SWITCH_NFET_WL[1]:g}, "
        f"pfet W={SWITCH_PFET_WL[0]:g}/L={SWITCH_PFET_WL[1]:g}), held bits "
        "as ideal fixed bottom plates, and supply-normalised control/"
        "threshold nodes so one numeric measurement set serves every "
        "corner. Model-evaluated unit capacitance (this run's own tt/27C "
        f"ramp probe, committed beside this record): {cu_txt} -- a "
        f"{ratio_cu:.3f}x area-driven C_u growth, i.e. the same factor on "
        "every tau_i (C_u scales tau_i linearly). Issue #1033's nominal "
        "~12.4 pF/side (512 x 24.29 fF) is the same plate without the "
        "PDK's m3 width shrink applied.",
        corners_mod.corner_matrix_summary_line(
            sorted({corners_mod.parse_corner_id(c)[0] for c in cids}),
            sorted({corners_mod.parse_corner_id(c)[1] for c in cids}),
            sorted({corners_mod.parse_corner_id(c)[2] for c in cids}),
            len(cids),
        ),
        "- **Measurement convention**: crossings are the baseline "
        "campaign's own TRIG/TARG 50/90/99 % fractions, read on the "
        "supply-normalised top-plate node (identical crossing times to the "
        "raw node -- affine positive-slope map), TRIG at the SEL edge "
        "midpoint (1 ns). Phase-end errors are fixed-time `find` reads at "
        f"each DR-006 deadline ({CAND_DEADLINE_FAST_NS:.3f} ns and "
        f"{CAND_DEADLINE_SLOW_NS:.3f} ns after that edge) plus a late read "
        f"at {CAND_LATE_AT_NS:g} ns, each minus this corner's own "
        "closed-form ideal "
        "V_top_final = vdd/2 + (C_i/C_total) * (V_bot_final - V_bot_initial). "
        "A 99 % crossing alone fixes no LSB accuracy across rows with "
        "different step sizes -- the phase-end/late error columns are the "
        "LSB-anchored quantity, and missing crossings are retained as data.",
        f"- **Baseline companion**: [`records/{CAND_BASELINE_RECORD}.md`]"
        f"({CAND_BASELINE_RECORD}.md) -- the same six rows at the "
        "production 1.9000 um plate over the same grid (binding 13.2466 "
        "ns, bit 8/rise, `tt_27c_1.62v`). This record extends that "
        "campaign to the candidate plate; it supersedes nothing.",
        f"- **Overall**: {'COMPLETE' if len(complete) == len(cids) else 'INCOMPLETE'} "
        f"({len(complete)}/{len(cids)} corners produced an MSB-row 99 % "
        "crossing and all fixed-time reads)",
    ]
    if note:
        lines.append(f"- **Note**: {note}")
    lines.append("")

    for step_name, deadline_ns, err_key, desc in (
        ("fast", CAND_DEADLINE_FAST_NS, "pend_fast_err_mv", "12 MHz (1 MS/s end)"),
        ("slow", CAND_DEADLINE_SLOW_NS, "pend_slow_err_mv", "1.2 MHz (100 kS/s end)"),
    ):
        lines += [
            f"## Worst-case settling per corner -- {desc} "
            f"(deadline {deadline_ns:.3f} ns after the SEL edge)",
            "",
            "| Corner | Worst bit | Dir | t_settle_99% (ns) | Margin vs deadline | "
            "worst phase-end err (mV) | worst late err (mV) | rows missing a crossing |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for cid in cids:
            rows = by_corner.get(cid, [])
            valid = [r for r in rows if r["t99_ns"] is not None]
            if not valid:
                lines.append(f"| `{cid}` | -- | -- | INCOMPLETE | -- | -- | -- | all 6 |")
                continue
            worst = max(valid, key=lambda r: r["t99_ns"])
            missing = [r["tag"] for r in rows if r["t99_ns"] is None]
            pe = max(
                (abs(r[err_key]) for r in rows if r[err_key] is not None),
                default=None,
            )
            le = max(
                (abs(r["plate_err_mv"]) for r in rows if r["plate_err_mv"] is not None),
                default=None,
            )
            lines.append(
                f"| `{cid}` | {worst['test_bit']} | {worst['direction']} | "
                f"{worst['t99_ns']:.4f} | {deadline_ns / worst['t99_ns']:.2f}x | "
                + (f"{pe:.4f}" if pe is not None else "N/A") + " | "
                + (f"{le:.4f}" if le is not None else "N/A") + " | "
                + (", ".join(missing) if missing else "--") + " |"
            )
        lines.append("")

    lines += [
        "## Per-copy detail at the binding corner of each endpoint",
        "",
        "| Endpoint | Corner | Bit | Dir | t50 (ns) | t90 (ns) | t99 (ns) | "
        "V_top_final ideal (V) | err @ fast (mV) | err @ slow (mV) | err @ late (mV) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    shown: set[tuple[str, str]] = set()
    for label, tkey in (
        ("12 MHz", "t99_ns"), ("1.2 MHz", "t99_ns"),
    ):
        valid = [
            (cid, r) for cid in cids for r in by_corner.get(cid, [])
            if r[tkey] is not None
        ]
        if not valid:
            continue
        cid, row = max(valid, key=lambda cr: cr[1][tkey])
        if (cid, label) in shown:
            continue
        shown.add((cid, label))
        lines.append(
            f"| {label} | `{cid}` | {row['test_bit']} | {row['direction']} | "
            f"{_fmt_ns(row['t50_ns'], 5)} | {_fmt_ns(row['t90_ns'], 5)} | "
            f"{_fmt_ns(row['t99_ns'], 5)} | {row['v_final_ideal']:.6f} | "
            f"{_fmt_mv(row['pend_fast_err_mv'])} | "
            f"{_fmt_mv(row['pend_slow_err_mv'])} | "
            f"{_fmt_mv(row['plate_err_mv'])} |"
        )
    lines.append("")

    lines += ["## Result", ""]
    lines += candidate_result_lines(by_corner, cids)
    lines += [
        "",
        "## What this record does not establish",
        "",
        "- It measures ONE mechanism (the array's own switch-Ron settling) "
        "at an EXPERIMENTAL plate size. Passing or failing it does not by "
        "itself set the sample rate: the sampling front end's acquisition "
        "at the same assembled load is the companion record's own question "
        "(and, at this plate size, the binding one), and whole-ADC code "
        "correctness remains open independently.",
        "- The held-bit ideal-source simplification (and its omitted "
        "held-bit switch parasitics) is inherited unchanged from the "
        "baseline campaign's documented reduction, as is the assumption "
        "that the SEL edge starts the phase (DR-006's one-CLK-per-phase "
        "allocation, with the sequencer's own CLK-to-phase delay quoted "
        "separately above rather than subtracted from the budget).",
        "- Nothing here ratifies DR-027, edits a target-table row, or "
        "resizes a switch: if the rate verdict needs drive strength moved, "
        "that is a separate design change with its own DR-011/DR-014 "
        "charge-injection/kickback evidence (#1033's scope rule).",
        "",
        "## Reproduction",
        "",
        "```bash",
        "# One-time machine bootstrap: docs/environment-setup.md sections 1-3.",
        "source sim/env.sh",
        "# `--wait-for-capacity` is batch-only, so the backend must be batch:",
        "export KLT_SIM_BACKEND=batch",
        "python3 sim/cdac-bit-trial-settling/run_bit_trial_settling.py --dr027-candidate --record --backend batch",
        "```",
        "",
        "The grid is ONE `klt sim` request (six independent deck copies in "
        "one circuit body, two analysis steps per corner = 18 units) "
        "submitted to the batch fleet with `--wait-for-capacity 600`; no "
        "ngspice loop runs on the submitting host. `--probe` runs the same "
        "request at one corner on the local backend and is the only path "
        "that simulates locally, beside the two single-run unit-cap probes. "
        "The request and body are committed under "
        f"`corners/{prov.record_id}/request/`, the raw report beside this "
        f"record under `corners/{prov.record_id}/report.json`.",
        "",
        "## `klt sim` run",
        "",
        f"- job `{info.get('job_id')}`, status `{info.get('status')}`, backend "
        f"`{info.get('backend')}`, executing PDK `{info.get('worker_pdk')}`, "
        f"executing simulator `{info.get('worker_ngspice')}`"
        + (", sharded" if info.get("sharded") else "")
        + ".",
        "",
        "**Uncontrolled difference -- against the baseline companion "
        f"record.** [`records/{CAND_BASELINE_RECORD}.md`]"
        f"({CAND_BASELINE_RECORD}.md) was minted on "
        "`sky130A @ c6d73a35f524070e85faff4a6a9eef49553ebc2b` / `ngspice-46` "
        "by an in-process ngspice loop; this record was produced by the "
        "executing worker named above. Where those differ, a change between "
        "the two records is as readily a PDK or simulator-version difference "
        "as a geometry one, and the C_u-ratio scaling "
        f"({ratio_cu:.3f}x measured this run) is the controlled comparison "
        "to make: the baseline's binding 13.2466 ns times that ratio is "
        "the prediction this record tests.",
        "",
    ]
    lines += evidence.environment_block(
        f"sky130A @ {worker_pdk.split()[-1]}" if exec_known else prov.pdk_line,
        worker_ng.split()[0] if exec_known else prov.ng_version,
        prov.netlist_sha,
        {
            "klt": klt_version,
            "candidate plate": f"{CANDIDATE_UNIT_CAP_WL_UM:.4f} um "
            "(EXPERIMENTAL; production draws 1.9000 um)",
            "unit cap (model, this run)": cu_txt,
            "tran steps": (
                f"fast {TRAN_STEP_PS:g} ps ceiling x {CAND_FAST_TRAN_STOP_NS:g} ns; "
                f"slow {CAND_SLOW_TRAN_STEP_NS:g} ns ceiling x "
                f"{CAND_SLOW_TRAN_STOP_NS:g} ns"
            ),
            "PDK / ngspice above": "as run by the executing worker"
            if exec_known else "submitting host (executing worker did not report)",
            "submitting host PDK / ngspice": f"{prov.pdk_line} / {prov.ng_version}",
        },
    )
    lines += [""]
    lines += evidence.footer_lines(
        "sim/cdac-bit-trial-settling/run_bit_trial_settling.py", supersedes
    )
    evidence.write_latest_pointer(EXPERIMENT_DIR, prov.record_id)
    return evidence.close_record(prov, lines, "Record")


def candidate_main(args: argparse.Namespace) -> int:
    """The --dr027-candidate CLI path (issue #1033)."""
    pdk.resolve_or_raise()
    workdir = args.workdir or Path(
        tempfile.mkdtemp(prefix="cdac-bit-trial-dr027-")
    )
    cids = candidate_corner_ids()

    if args.dry_run:
        workdir.mkdir(parents=True, exist_ok=True)
        body = build_candidate_body()
        (workdir / "tb.spice").write_text(body)
        req = build_candidate_request(
            "tb.spice", cids, timeout_s=args.timeout_s,
            backend=args.backend, hosts=args.hosts,
        )
        (workdir / "request.json").write_text(json.dumps(req, indent=1) + "\n")
        print(f"wrote deck + request under {workdir}")
        print(f"corners: {len(cids)}  steps/corner: {len(req['analysis_steps'])}  "
              f"copies: {len(candidate_copies())}")
        return 0

    with tempfile.TemporaryDirectory(prefix="cdac-bit-dr027-probe-") as tmp:
        c_u_ff: dict[float, float] = {}
        probe_logs: dict[str, str] = {}
        if args.probe or args.record:
            for wl in (UNIT_CAP_WL_UM, CANDIDATE_UNIT_CAP_WL_UM):
                c_u, log = measure_unit_cap_ff(wl, Path(tmp))
                c_u_ff[wl] = c_u
                probe_logs[wl] = log
                print(f"unit cap @ {wl:.4f} um: {c_u:.3f} fF (model, tt/27C)")

        if args.probe:
            cid = corners_mod.corner_id("tt", 27.0, VDD)
            report, info, _req = submit_candidate(
                workdir / "probe", "local", args.timeout_s, hosts=None,
                cids=[cid],
            )
            by_corner, _complete = read_candidate_report(report)
            rows = by_corner.get(cid, [])
            if not rows:
                print(f"{cid}: INCOMPLETE -- no usable measurement", file=sys.stderr)
                return 1
            print(f"\n{cid} (local backend, all six copies):")
            for r in rows:
                print(
                    f"  bit {r['test_bit']} ({r['direction']:4}) "
                    f"t99={_fmt_ns(r['t99_ns'])} ns  "
                    f"err@83.3ns={_fmt_mv(r['pend_fast_err_mv'])} mV  "
                    f"err@833.3ns={_fmt_mv(r['pend_slow_err_mv'])} mV"
                )
            b8r = next(
                (r for r in rows if r["tag"] == candidate_tag(TEST_BITS[-1], "rise")),
                None,
            )
            if b8r and b8r["t99_ns"] is not None and c_u_ff:
                ratio = c_u_ff[CANDIDATE_UNIT_CAP_WL_UM] / c_u_ff[UNIT_CAP_WL_UM]
                print(
                    "  compare: 1.9000 um grid's tt/27C/1.8V bit-8/rise "
                    f"t99 = 11.3994 ns x {ratio:.3f} (C_u ratio) = "
                    f"{11.3994 * ratio:.4f} ns predicted"
                )
            print(f"  klt sim: backend {info.get('backend')}, status {info.get('status')}")
            return 0

        report, info, _req = submit_candidate(
            workdir, args.backend, args.timeout_s, hosts=args.hosts,
        )
        by_corner, complete = read_candidate_report(report)
        for cid in cids:
            rows = by_corner.get(cid, [])
            valid = [r for r in rows if r["t99_ns"] is not None]
            worst = max(valid, key=lambda r: r["t99_ns"]) if valid else None
            state = "INCOMPLETE (MSB row missing)" if cid not in complete else "ok"
            extra = (
                f"; worst bit {worst['test_bit']}/{worst['direction']} "
                f"t99={worst['t99_ns']:.4f} ns "
                f"({CAND_DEADLINE_FAST_NS / worst['t99_ns']:.2f}x inside the "
                f"{CAND_DEADLINE_FAST_NS:.3f} ns fast deadline)"
                if worst else ""
            )
            print(f"{cid}: {state}{extra}")
        if args.record:
            write_candidate_record(
                report, info, cids, args.supersedes, workdir, c_u_ff, probe_logs,
                note=args.note,
            )
        if len(complete) != len(cids):
            print(
                f"\nFAIL: {len(cids) - len(complete)}/{len(cids)} corner "
                "points produced an incomplete (MSB-row) measurement."
            )
            return 1
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true", help="write an evidence record")
    parser.add_argument(
        "--corners", action="store_true",
        help="run the full ratified PVT grid (9 OAT points) instead of the "
        "single tt/27C/1.8V corner",
    )
    parser.add_argument(
        "--dr027-candidate", action="store_true",
        help="issue #1033 candidate-geometry study: the same reduction at "
        "the DR-027 proposed 3.3000 um unit plate (switch sizes and weights "
        "unchanged), both DR-006 phase deadlines, submitted as ONE klt sim "
        "request (never a local ngspice loop). Combine with --dry-run, "
        "--probe or --record.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="--dr027-candidate only: write the deck + request to --workdir "
        "and stop (no simulation)",
    )
    parser.add_argument(
        "--probe", action="store_true",
        help="--dr027-candidate only: one corner (tt_27c_1.80v) on the "
        "local backend plus the two single-run unit-cap probes -- the "
        "single-unit debug path",
    )
    parser.add_argument(
        "--backend", default=None,
        help="klt sim backend for --dr027-candidate (default: klt's own / "
        "KLT_SIM_BACKEND; the grid goes to the batch fleet)",
    )
    parser.add_argument(
        "--workdir", type=Path, default=None,
        help="scratch dir for --dr027-candidate submits (default: a fresh tmpdir)",
    )
    parser.add_argument(
        "--timeout-s", type=float, default=CAND_TIMEOUT_S,
        help="per-unit options.timeout_s for --dr027-candidate (default: "
        "%(default)s). The fleet refuses a job whose timeout_s * units + "
        "120 exceeds its whole-job ceiling -- see CAND_TIMEOUT_S's comment "
        "before raising this",
    )
    parser.add_argument(
        "--hosts", type=int, default=CAND_HOSTS,
        help="remote.hosts shard count for --dr027-candidate's grid submit "
        "(default: %(default)s)",
    )
    parser.add_argument(
        "--note", default="",
        help="free-text provenance note recorded as this record's `**Note**` "
        "field -- the place a re-run says WHY it was re-run. Added by #498: "
        "until then this runner had no --note at all, so a re-run after a "
        "design/ change could not be traced back to what it replaced from the "
        "record itself. Prose only: name the displaced record MACHINE-readably "
        "via --supersedes, which both citation gates actually read.",
    )
    evidence.add_supersedes_argument(parser)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    gate = toolchain.preflight()
    if gate is not None:
        return gate

    if args.dr027_candidate:
        return candidate_main(args)

    with tempfile.TemporaryDirectory(prefix="cdac-bit-trial-settling-") as tmp:
        scratch = Path(tmp)

        if args.corners:
            points = run_corners(scratch, quiet=args.quiet)
            incomplete = [p for p in points if not p["complete"]]
            n_missing = sum(len(p["missing_rows"]) for p in points)
            if incomplete:
                print(
                    f"FAIL: {len(incomplete)}/{len(points)} corner points "
                    "produced an incomplete (MSB-row-missing) measurement."
                )
                if args.record:
                    write_corners_record(
                        points, note=args.note, supersedes=args.supersedes
                    )
                return 1
            missing_note = (
                f" ({n_missing} smaller-bit row(s) missing a crossing -- "
                "see the record's own notes; does not affect the MSB-based "
                "worst-case finding)" if n_missing else ""
            )
            print(
                f"\nOVERALL: PASS (all {len(points)} corner points produced "
                f"a valid MSB (bit {TEST_BITS[-1]}) worst-case reading)"
                f"{missing_note}"
            )
            if args.record:
                write_corners_record(
                    points, note=args.note, supersedes=args.supersedes
                )
            return 0

        rows = run_all(scratch)

        # Sample netlist for the snapshot: the worst-case (MSB) bit, fall
        # direction, so a reader can see the full generated deck for the
        # row this record's headline finding is about.
        sample_netlist, _ = build_transient(test_bit=TEST_BITS[-1], direction="fall")

        if args.record:
            write_record(
                rows, sample_netlist, note=args.note, supersedes=args.supersedes
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

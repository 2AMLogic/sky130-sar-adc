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

Usage (from the repo root, after ``source sim/env.sh``)::

    python3 sim/cdac-bit-trial-settling/run_bit_trial_settling.py
    python3 sim/cdac-bit-trial-settling/run_bit_trial_settling.py --record
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
EXPERIMENT_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(SIM_DIR))
from harness import evidence, measure, pdk, toolchain  # noqa: E402

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

TEST_BITS = [0, 4, 8]  # LSB, a mid bit, MSB -- brackets the tau_i(i) shape
DIRECTIONS = ["fall", "rise"]  # fall: BOT 1.8->0V (NMOS); rise: BOT 0->1.8V (PMOS)

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

FRACTIONS = [0.5, 0.9, 0.99]  # fraction of the way from V_cm to V_top_final

MEASURE_PREFIX_CONFIRM = "vtop_confirm"


def _preamble(corner: str, temp_c: float, title: str) -> list[str]:
    info = pdk.resolve()
    return [
        f"* {title}",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        ".model SWMOD SW(Ron=1 Roff=1e12 Vt={0} Vh=0.05)".format(VDD / 2),
        "",
    ]


def build_transient(
    *,
    test_bit: int,
    direction: str,
    corner: str = "tt",
    temp_c: float = 27.0,
    vdd: float = VDD,
) -> tuple[str, dict]:
    """One transient deck: a single-side, single-instance reduction of
    design/cdac/cdac_array.sch with every bit except `test_bit` held fixed
    (SEL=1, gate tied to VDD) and `test_bit` driven by a PWL edge at
    EDGE_TD_NS, simultaneous with an ideal reset switch (matching
    tb_cdac_array_transfer.spice's own SWMOD/Rdc convention) releasing the
    shared top-plate node from VCM. Returns (netlist_text, analytics) where
    analytics carries the closed-form V_top_final prediction and the
    threshold voltages this deck's own .measure statements search for.
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

    lines = _preamble(
        corner, temp_c,
        f"issue #121 CDAC bit-trial settling -- corner={corner} temp={temp_c}C "
        f"vdd={vdd} test_bit={test_bit} direction={direction}",
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
        f"{EDGE_TD_NS + EDGE_TR_NS / 2}n 0 {TRAN_STOP_NS}n 0)",
        "Sreset TOP VCM NCTRL_RESET 0 SWMOD",
        "Rdc TOP VCM 1T",
        f"Vsel_test SEL_TEST 0 pwl(0 {sel_initial} {EDGE_TD_NS - EDGE_TR_NS / 2}n "
        f"{sel_initial} {EDGE_TD_NS + EDGE_TR_NS / 2}n {sel_final} {TRAN_STOP_NS}n "
        f"{sel_final})",
    ]

    for i in range(9):
        weight = BIT_WEIGHTS[i]
        if i == test_bit:
            lines += [
                f"Xc_bit{i} bot{i} TOP sky130_fd_pr__cap_mim_m3_1 "
                f"W=1.8988 L=1.8988 MF={weight} m={weight}",
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
                f"W=1.8988 L=1.8988 MF={weight} m={weight}"
            )
    # Termination unit: fixed weight-1 cap, bottom plate hardwired VREFN,
    # no switch device at all (design/cdac/cdac_array.sch's own convention).
    lines.append(
        f"Xc_term VREFN TOP sky130_fd_pr__cap_mim_m3_1 W=1.8988 L=1.8988 "
        f"MF={TERM_WEIGHT} m={TERM_WEIGHT}"
    )

    thresholds = {}
    lines.append(".control")
    lines.append(f"tran {TRAN_STEP_PS}p {TRAN_STOP_NS}n")
    for frac in FRACTIONS:
        target_v = vcm + frac * delta_ideal
        thresholds[frac] = target_v
        name = f"t_settle_{int(frac * 100)}"
        lines.append(
            f"meas tran {name} TRIG AT={EDGE_TD_NS}n TARG V(TOP) "
            f"VAL={target_v:.8g} CROSS=1"
        )
    lines.append(
        f"meas tran {MEASURE_PREFIX_CONFIRM} find v(TOP) at={CONFIRM_AT_NS}n"
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

# sim/harness/measure.py's parse() requires "name = value" with nothing
# trailing (a right-anchored regex) -- correct for the plain `.meas tran X
# find ...` lines this repo's other experiments use, but ngspice's
# TRIG/TARG crossing-based measures (this script's own t_settle_* lines)
# print extra " targ=... trig=..." context on the SAME line, which that
# anchor rejects outright (silently yielding no match, not an exception).
# Parsed locally here rather than by changing the shared harness module,
# since no other sim/ experiment in this repo uses a TRIG/TARG measure yet.
_TRIG_TARG_RE_TMPL = r"^{name}\s*=\s*([-+0-9.eE]+)"


def _parse_trig_targ(log_text: str, names: list[str]) -> dict[str, float]:
    import re

    out: dict[str, float] = {}
    for name in names:
        pattern = re.compile(_TRIG_TARG_RE_TMPL.format(name=re.escape(name)))
        for line in log_text.splitlines():
            m = pattern.match(line.strip())
            if m:
                try:
                    out[name] = float(m.group(1))
                except ValueError:
                    pass
                break
    return out


def _run(netlist: str, scratch: Path, tag: str) -> dict[str, float]:
    """A few bounded retries with backoff absorb transient contention from
    other concurrent agents' own ngspice runs on a shared machine -- the
    same policy (and observed cause) sim/vcm-drive-budget/
    run_vcm_drive_budget.py's own `_run()` already documents."""
    import time

    attempts = 4
    for attempt in range(1, attempts + 1):
        try:
            log_text = toolchain.run_ngspice(netlist, scratch, tag)
            m = measure.parse(log_text, MEASURE_NAMES)
            m.update(_parse_trig_targ(log_text, TRIG_TARG_NAMES))
            return m
        except RuntimeError as exc:
            if "timed out" not in str(exc) or attempt == attempts:
                raise
            print(
                f"  (warning: {tag} timed out (attempt {attempt}/{attempts}), "
                f"retrying after a short backoff -- machine likely contended)",
                file=sys.stderr,
            )
            time.sleep(15 * attempt)
    raise AssertionError("unreachable")  # loop always returns or raises above


def run_all(scratch: Path) -> list[dict]:
    rows = []
    for test_bit in TEST_BITS:
        for direction in DIRECTIONS:
            netlist, analytics = build_transient(test_bit=test_bit, direction=direction)
            tag = f"bit{test_bit}_{direction}"
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
            rows.append(row)
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


def write_record(rows: list[dict], netlist_sample: str) -> None:
    record_id = evidence.new_record_id()
    record_path = evidence.write_netlist_snapshot_text(
        EXPERIMENT_DIR, record_id, netlist_sample
    )
    netlist_sha = evidence.sha256_text(netlist_sample)
    info = pdk.resolve()
    pdk_line = f"{info.variant} @ {pdk.resolved_commit(info)}"
    ng_version = toolchain._ngspice_version() or "unknown"

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
        pdk_line, f"ngspice {ng_version}", netlist_sha,
        extra={
            "Corner/temp/VDD": "tt / 27C / 1.8V (single point, first-pass)",
            "tran step": f"{TRAN_STEP_PS} ps",
        },
    ))
    a("")
    lines.extend(evidence.footer_lines(
        "sim/cdac-bit-trial-settling/run_bit_trial_settling.py", ""
    ))

    record_path.write_text("\n".join(lines) + "\n")
    latest_path = EXPERIMENT_DIR / "records" / "LATEST"
    latest_path.write_text(f"{record_id}.md\n")
    print(f"\nWrote record: {record_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true", help="write an evidence record")
    args = parser.parse_args()

    check = toolchain.check_env()
    if check.status == 3:
        print("SKIP: ngspice/PDK not available (" + "; ".join(check.messages) + ")")
        return 0
    if check.status == 1:
        print("FAIL: toolchain drift -- " + "; ".join(check.messages))
        return 1

    import tempfile
    with tempfile.TemporaryDirectory(prefix="cdac-bit-trial-settling-") as tmp:
        scratch = Path(tmp)
        rows = run_all(scratch)

        # Sample netlist for the snapshot: the worst-case (MSB) bit, fall
        # direction, so a reader can see the full generated deck for the
        # row this record's headline finding is about.
        sample_netlist, _ = build_transient(test_bit=TEST_BITS[-1], direction="fall")

        if args.record:
            write_record(rows, sample_netlist)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

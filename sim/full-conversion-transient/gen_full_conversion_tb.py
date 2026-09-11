#!/usr/bin/env python3
"""Stimulus + measurement fragment generator for
`sim/full-conversion-transient/` (issue #254).

The fragment this writes
(`testbench/full_conversion_tb_fragment.spice`) is the *whole* testbench
around the committed `design/sar_adc_top.spice` DUT: the supply/reference
sources, the DR-006 worst-case `f_clk = 12 MHz` master clock, the reset
release, the DC differential input schedule, the `.tran` card, and every
`.meas` card the driver parses. `run_conversion.py` only prepends the
per-corner preamble (`.lib` corner section, `.temp`, `.param vdd_val`, the
`sky130_fd_sc_hd` `.include`, the `.global VPWR VGND` tie) and the DUT
netlist body itself.

WHY A GENERATED-AND-COMMITTED FRAGMENT RATHER THAN A DECK BUILT ENTIRELY IN
THE DRIVER. The fragment is ~200 mechanically-derived lines (73 clock
periods' worth of measurement instants); hand-authoring it is error-prone
and building it invisibly inside the driver would leave the testbench
itself unreviewable in the diff. So it is generated here, committed under
`testbench/`, and pinned byte-for-byte by `sim/tests/test_full_conversion.py`
-- exactly the precedent `sim/cdac-array-transfer/gen_full_conversion_tb.py` +
`sim/tests/test_cdac_fragment_gen.py` already set in this repo.

Every voltage in the fragment is written as an expression in `{vdd_val}`,
so one committed fragment serves every supply point of the ratified corner
set without being regenerated per corner (the same rail-referenced
convention `sim/sar-sequencer-behavioral/testbench/`'s fragment uses).

    python3 sim/full-conversion-transient/gen_full_conversion_tb.py --check   # CI/test path
    python3 sim/full-conversion-transient/gen_full_conversion_tb.py --write   # regenerate

## The timing schedule this encodes (DR-006)

`spec/decision-records/DR-006-sar-sequencer-bit-count-and-timing-budget.md`
allocates `N + 2 = 12` uniform master-clock periods per conversion: one
SAMPLE phase, `N = 10` bit-trial phases (MSB first), one EOC phase. At the
DR-006 worst-case `f_clk = 12 MHz` a period is `1000/12 = 83.333... ns`, so
one conversion is exactly 1000 ns.

With CLK rising-edge 50% crossings at `t_k = T_FIRST_EDGE_NS + k *
T_CLK_NS`, `design/sar_sequencer.sch`'s ring puts conversion `c` at:

| CLK period `k` | phase | note |
| --- | --- | --- |
| `12c + 0` | `PH_B9` | MSB trial; `DOUT9` captured at edge `12c + 1` |
| ... | ... | ... |
| `12c + 9` | `PH_B0` | LSB trial; `DOUT0` captured at edge `12c + 10` |
| `12c + 10` | `PH_EOC` | code complete and stable from edge `12c + 10` |
| `12c + 11` | `PH_SAMPLE` | `BUSY` low; front end acquires conversion `c+1` |

so the code for conversion `c` is read in the middle of period `12c + 10`
(`PH_EOC` -- stable from edge `12c + 10` until it is CLEARED to 0 at edge
`12c + 11`, `design/sar_sequencer.sch`'s own per-conversion CDAC clear,
issue #263: `DOUT8..DOUT0` are forced to 0 starting at the `PH_EOC ->
PH_SAMPLE` edge, a full CLK period before `design/sar_adc_top.sch`'s
sampling switch opens at the following `PH_SAMPLE -> PH_B9` edge, so the
clear lands while the switch is still closed rather than racing its
opening). This is a NARROWER stable window than an earlier draft of this
fix assumed (mid-`PH_SAMPLE`, period `12c + 11`) -- reading mid-`PH_EOC`
instead is what that earlier draft's own re-run corner campaign exposed as
necessary: with the code cleared during `PH_SAMPLE`, a mid-`PH_SAMPLE`
read sees the CLEARED value (0), not the decided one. `BUSY` must still
read `1` for periods `12c + 0 .. 12c + 10` and `0` for period `12c + 11`
-- the "conversion completes inside 12 CLK periods, no missing or
duplicated phase" check -- unaffected by the code-read-timing change
above, since `BUSY` (unlike the clear's own `BUSY_BITS` gating signal)
still includes `PH_EOC`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent
FRAGMENT_PATH = EXPERIMENT_DIR / "testbench" / "full_conversion_tb_fragment.spice"

# --- DR-006 timing (worst-case end of the derived 1.2-12 MHz range) --------
N_BITS = 10
PHASES_PER_CONVERSION = N_BITS + 2  # 1 SAMPLE + 10 bit trials + 1 EOC
F_CLK_HZ = 12.0e6
T_CLK_NS = 1.0e9 / F_CLK_HZ  # 83.3333... ns
T_FIRST_EDGE_NS = 200.0  # 50% crossing of the first CLK rising edge
EDGE_NS = 1.0  # CLK / stimulus rise and fall time
T_RSTB_RELEASE_NS = 20.0  # RST_B released well before the first CLK edge
TRAN_STEP_NS = 0.5

# --- Conversion / input schedule ------------------------------------------
# Conversion 0 is a start-up conversion and is DISCARDED (it is the one whose
# CDAC bottom plates start from the RST_B-cleared all-zero register state and
# whose SAMPLE phase is the power-up interval, not a steady-state phase).
# Conversions 1..5 carry the five DC differential inputs below.
STARTUP_CONVERSIONS = 1
INPUT_FRACTIONS: tuple[float, ...] = (-0.78, -0.25, 0.0, 0.25, 0.78)
N_CONVERSIONS = STARTUP_CONVERSIONS + len(INPUT_FRACTIONS)

# The steady-state conversion the average supply currents are taken over (a
# whole 12-period cycle, sample phase included). Conversion 3 is mid-run:
# several conversions after start-up, several before the transient ends.
IDD_CONVERSION = 3

# Supply/reference sources whose average current is measured. Each entry is
# (measurement name, source instance name, node potential as a multiple of
# vdd_val) -- the potential is what turns a current into a power number.
SUPPLY_SOURCES: tuple[tuple[str, str, float], ...] = (
    ("i_vdd", "vvdd", 1.0),  # analog VDD (front end, comparator, CDAC wells)
    ("i_vpwr", "vvpwr", 1.0),  # sky130_fd_sc_hd digital rail (sequencer + inverters)
    ("i_vrefp", "vvrefp", 1.0),  # CDAC positive reference
    ("i_vrefn", "vvrefn", 0.0),  # CDAC negative reference (at 0 V: no power term)
    ("i_vcm", "vvcm", 0.5),  # front-end common-mode reference
)

DIGITAL_THRESHOLD_FRACTION = 0.5  # of vdd_val, for 1/0 decoding


def t_edge_ns(k: int) -> float:
    """50% crossing time of CLK rising edge `k` (k = 0 is the first edge)."""
    return T_FIRST_EDGE_NS + k * T_CLK_NS


def t_phase_mid_ns(conversion: int, phase: int) -> float:
    """Midpoint of CLK period `phase` (0..11) of conversion `conversion`."""
    return t_edge_ns(PHASES_PER_CONVERSION * conversion + phase) + 0.5 * T_CLK_NS


def t_code_read_ns(conversion: int) -> float:
    """When the 10 captured bits of `conversion` are read: the middle of that
    conversion's own PH_EOC period (period 10), where the code has been
    complete and stable since edge `12c + 10` and is not cleared until edge
    `12c + 11` (design/sar_sequencer.sch's per-conversion CDAC clear, issue
    #263 -- see this module's own docstring for why the stable window ends
    at PH_EOC, not PH_SAMPLE)."""
    return t_phase_mid_ns(conversion, PHASES_PER_CONVERSION - 2)


def t_input_step_ns(conversion: int) -> float:
    """When the DC differential input for `conversion` is stepped: three CLK
    periods before that conversion's first bit trial, i.e. two periods before
    its own SAMPLE phase opens. The sampling switch is OFF at that instant
    (the previous conversion is mid-bit-trial), so the step cannot disturb
    the conversion in flight, and the front end still gets its whole SAMPLE
    period to acquire the new value."""
    return t_edge_ns(PHASES_PER_CONVERSION * conversion - 3)


def t_stop_ns() -> float:
    """One CLK period past the last conversion's SAMPLE phase."""
    return t_edge_ns(PHASES_PER_CONVERSION * N_CONVERSIONS + 1)


def ideal_code(fraction: float) -> int:
    """Ideal offset-binary output code for a differential input of
    `fraction * V_REF`, using spec/target-spec.md's RATIFIED
    `LSB = 2*V_REF / 2^N` (`V_REF = V_DD`, so the LSB scales with each
    corner's own supply and the ideal code is the same integer at every
    corner). Mid-scale (0 V differential) maps to code 512."""
    half_scale = 2 ** (N_BITS - 1)
    code = round(fraction * half_scale) + half_scale
    return max(0, min(2**N_BITS - 1, code))


def vin_fractions(conversion: int) -> tuple[float, float]:
    """(VINP, VINN) for `conversion`, as multiples of vdd_val. The
    common mode is VCM = vdd_val/2 and the differential input is
    `INPUT_FRACTIONS[...] * V_REF`, split symmetrically about it."""
    frac = input_fraction(conversion)
    return 0.5 + frac / 2.0, 0.5 - frac / 2.0


def input_fraction(conversion: int) -> float:
    """The differential input fraction driven during `conversion`. The
    start-up conversion(s) reuse the first measured input, so the input
    schedule has one step per measured conversion and no special case."""
    if conversion < STARTUP_CONVERSIONS:
        return INPUT_FRACTIONS[0]
    return INPUT_FRACTIONS[conversion - STARTUP_CONVERSIONS]


def measured_conversions() -> list[int]:
    return list(range(STARTUP_CONVERSIONS, N_CONVERSIONS))


def code_measure_names(conversion: int) -> list[str]:
    """DOUT9..DOUT0 measurement names for `conversion`, MSB first."""
    return [f"d{b}_c{conversion}" for b in range(N_BITS - 1, -1, -1)]


def busy_measure_names(conversion: int) -> list[str]:
    return [f"busy_c{conversion}_p{p}" for p in range(PHASES_PER_CONVERSION)]


def sample_measure_names(conversion: int) -> list[str]:
    return [f"smpl_c{conversion}_p{p}" for p in range(PHASES_PER_CONVERSION)]


def all_measure_names() -> list[str]:
    names: list[str] = []
    for c in measured_conversions():
        names += code_measure_names(c)
        names += busy_measure_names(c)
        names += sample_measure_names(c)
    names += [name for name, _src, _pot in SUPPLY_SOURCES]
    return names


def _pwl(points: list[tuple[float, str]]) -> str:
    return "PWL(" + " ".join(f"{t:.4f}n {v}" for t, v in points) + ")"


def _input_pwl(side: str) -> str:
    """PWL for VINP (side='p') or VINN (side='n') over the whole run."""
    idx = 0 if side == "p" else 1

    def value(conversion: int) -> str:
        return f"{{vdd_val*{vin_fractions(conversion)[idx]:.6g}}}"

    points: list[tuple[float, str]] = [(0.0, value(0))]
    for c in range(1, N_CONVERSIONS):
        if input_fraction(c) == input_fraction(c - 1):
            continue  # no step needed (start-up conversion reuses input #1)
        t_step = t_input_step_ns(c)
        points.append((t_step, value(c - 1)))
        points.append((t_step + EDGE_NS, value(c)))
    points.append((t_stop_ns(), value(N_CONVERSIONS - 1)))
    return _pwl(points)


def fragment_text() -> str:
    stop = t_stop_ns()
    idd_from = t_edge_ns(PHASES_PER_CONVERSION * IDD_CONVERSION)
    idd_to = t_edge_ns(PHASES_PER_CONVERSION * (IDD_CONVERSION + 1))

    lines: list[str] = [
        "* full_conversion_tb_fragment.spice -- end-to-end full-conversion",
        "* transient testbench for design/sar_adc_top.spice (issue #254).",
        "*",
        "* GENERATED by sim/full-conversion-transient/gen_full_conversion_tb.py -- do not",
        "* edit by hand; sim/tests/test_full_conversion.py pins this file",
        "* byte-for-byte against a fresh generation.",
        "*",
        "* Devices/sources/measurements only: sim/full-conversion-transient/",
        "* run_conversion.py supplies the .lib corner section, .temp, the",
        "* .param vdd_val supply point, the sky130_fd_sc_hd .include, the",
        "* .global VPWR VGND tie (design/sar_adc_top.sch's own header names",
        "* this tie as the assembling testbench's job -- VPWR/VGND are literal",
        "* std-cell instance properties with no schematic-graph node), the DUT",
        "* netlist body, and the closing .end.",
        "*",
        f"* CLK: f_clk = {F_CLK_HZ / 1e6:g} MHz (DR-006 worst case), period "
        f"{T_CLK_NS:.4f} ns, 50% duty.",
        f"* First CLK rising edge (50%) at {T_FIRST_EDGE_NS:g} ns; RST_B released at "
        f"{T_RSTB_RELEASE_NS:g} ns.",
        f"* {N_CONVERSIONS} back-to-back conversions of {PHASES_PER_CONVERSION} CLK "
        f"periods each ({PHASES_PER_CONVERSION * T_CLK_NS:.0f} ns per conversion);",
        f"* conversion 0 is a start-up conversion and is discarded, conversions "
        f"{STARTUP_CONVERSIONS}..{N_CONVERSIONS - 1} carry the five DC",
        "* differential inputs below (as a fraction of V_REF = vdd_val):",
    ]
    for c in measured_conversions():
        frac = input_fraction(c)
        vp, vn = vin_fractions(c)
        lines.append(
            f"*   conversion {c}: Vd = {frac:+.2f}*V_REF  "
            f"(VINP = {vp:.3f}*vdd_val, VINN = {vn:.3f}*vdd_val)  "
            f"-> ideal code {ideal_code(frac)}"
        )
    lines += [
        "*",
        "* Rail-referenced throughout ({vdd_val} expressions): one committed",
        "* fragment serves every supply point of the ratified corner set, and",
        "* V_REF = V_DD (spec/target-spec.md, RATIFIED DR-003) means the ideal",
        "* code above is the same integer at every corner.",
        "",
        "* --- supplies and references -----------------------------------------",
        "VVDD VDD 0 DC {vdd_val}",
        "VVPWR VPWR 0 DC {vdd_val}",
        "VVGND VGND 0 DC 0",
        "VVREFP VREFP 0 DC {vdd_val}",
        "VVREFN VREFN 0 DC 0",
        "VVCM VCM 0 DC {vdd_val*0.5}",
        "",
        "* --- clock and reset --------------------------------------------------",
        f"VCLK CLK 0 PULSE(0 {{vdd_val}} {T_FIRST_EDGE_NS - EDGE_NS / 2:.4f}n "
        f"{EDGE_NS:g}n {EDGE_NS:g}n {T_CLK_NS / 2 - EDGE_NS:.5f}n {T_CLK_NS:.5f}n)",
        f"VRSTB RST_B 0 PWL(0 0 {T_RSTB_RELEASE_NS:.4f}n 0 "
        f"{T_RSTB_RELEASE_NS + EDGE_NS:.4f}n {{vdd_val}} {stop:.4f}n {{vdd_val}})",
        "",
        "* --- DC differential input schedule -----------------------------------",
        f"VINP VINP 0 {_input_pwl('p')}",
        f"VINN VINN 0 {_input_pwl('n')}",
        "",
        f".tran {TRAN_STEP_NS:g}n {stop:.4f}n",
        "",
        "* --- captured output code, read mid-PH_EOC of each conversion (issue",
        "* #263: DOUT8..0 are cleared during PH_SAMPLE, so this must be read",
        "* before PH_SAMPLE begins, not during it). Bits 8..0 read the",
        "* ADCOUT<i> offset-binary-recoded nodes (design/sar_adc_top.sch,",
        "* issue #263), NOT the internal DOUT<i> search register directly --",
        "* DOUT<i> is a sign+true-magnitude value for the DOUT9=0 branch, not",
        "* the ratified offset-binary code (see that recoding stage's own",
        "* header comment). Bit 9 (the sign bit) needs no recoding and reads",
        "* DOUT9 directly. ------------------------------------------------",
    ]
    for c in measured_conversions():
        t_read = t_code_read_ns(c)
        lines.append(
            f"* conversion {c}: Vd = {input_fraction(c):+.2f}*V_REF, "
            f"read at {t_read:.4f} ns"
        )
        for name, b in zip(code_measure_names(c), range(N_BITS - 1, -1, -1)):
            node = "dout9" if b == N_BITS - 1 else f"adcout{b}"
            lines.append(f".meas tran {name} find v({node}) at={t_read:.4f}n")
    lines += [
        "",
        "* --- phase structure: BUSY and PH_SAMPLE (SAMPLE_INT) per CLK period --",
        "* Expected per conversion: BUSY = 1 for periods 0..10 (10 bit trials +",
        "* EOC) and 0 for period 11 (SAMPLE); SAMPLE_INT is its complement.",
    ]
    for c in measured_conversions():
        for p in range(PHASES_PER_CONVERSION):
            t_mid = t_phase_mid_ns(c, p)
            lines.append(f".meas tran busy_c{c}_p{p} find v(busy) at={t_mid:.4f}n")
            lines.append(f".meas tran smpl_c{c}_p{p} find v(sample_int) at={t_mid:.4f}n")
    lines += [
        "",
        "* --- average supply/reference currents over one steady-state ----------",
        f"* conversion (conversion {IDD_CONVERSION}: {idd_from:.4f} ns to "
        f"{idd_to:.4f} ns, all {PHASES_PER_CONVERSION} periods).",
    ]
    for name, source, _potential in SUPPLY_SOURCES:
        lines.append(
            f".meas tran {name} avg i({source}) from={idd_from:.4f}n to={idd_to:.4f}n"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="(re)write the committed fragment")
    ap.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the committed fragment differs from a fresh generation",
    )
    args = ap.parse_args()

    text = fragment_text()
    if args.write:
        FRAGMENT_PATH.parent.mkdir(parents=True, exist_ok=True)
        FRAGMENT_PATH.write_text(text)
        print(f"wrote {FRAGMENT_PATH}")
        return 0
    if args.check:
        if not FRAGMENT_PATH.is_file():
            print(f"FAIL: {FRAGMENT_PATH} does not exist -- run with --write", file=sys.stderr)
            return 1
        if FRAGMENT_PATH.read_text() != text:
            print(
                f"FAIL: {FRAGMENT_PATH} is stale -- regenerate with "
                "`python3 sim/full-conversion-transient/gen_full_conversion_tb.py --write`",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {FRAGMENT_PATH} matches a fresh generation.")
        return 0
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

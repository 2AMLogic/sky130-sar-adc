"""Digital-partition characterization library (issue #619, T1 item 8 digital).

PDK-free, unit-testable logic behind `run_digital_partition.py`:

  * the frequency-grid / bracket-search state machine (`CornerSearch`,
    `plan_round`) -- adaptive per corner, but quantised to one shared grid so
    corners that need the same frequency share ONE `klt sim` request;
  * the transient deck (circuit BODY, per `klt sim`'s netlist convention) for
    the declared digital partition, assembled from the committed
    `design/sar_adc_top.spice` (the sequencer subcircuit + the 33 top-level
    standard-cell glue instances), a deterministic COMP_OUT stimulus, declared
    interface loads, and behavioural monitor nodes;
  * the `klt sim` request builder / report reader (the repo does not loop
    ngspice: every simulation unit is submitted through `klt sim`);
  * grading (phase order, reset/restart, bit capture, output recoding, control
    outputs), with missing / non-finite measurements treated as INVALID, never
    silently as pass or zero;
  * rail power / energy-per-conversion arithmetic and the checklist predicate
    that decides whether a campaign result may back an `8.digital` citation.

WHAT A "PASS" MEANS HERE (read before quoting a bracket). A probe passes when
every sampled check below holds for every conversion in the window. The
checks sample at 0.9 T after each launching clock edge, so "pass" means "the
registered outputs have settled one tenth of a period before the next edge",
under the declared loads and the declared COMP_OUT arrival (0.25 T after the
launching edge, from an ideal source -- comparator decision time is outside
this boundary). The resulting frequency bracket is a SCHEMATIC-LEVEL,
digital-partition-only bound. It is not extracted timing, it is not static
timing analysis, it is not the reciprocal of any one propagation delay, and it
does not set the ADC sample rate (which is also limited by the sampling front
end, the CDAC and the comparator).
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

# --------------------------------------------------------------------------
# Frequency grid and search
# --------------------------------------------------------------------------

#: Index-0 clock: the existing PROVISIONAL 12 MHz operating point
#: (DR-006's derived f_clk_max). Draft, not a ratified spec value.
F_BASE_MHZ = 12.0
#: Grid points per octave. Adjacent points differ by 2**(1/8) = 1.0905, so a
#: converged bracket is tight to ~9.05 % -- the declared search tolerance.
STEPS_PER_OCTAVE = 8
#: Coarse stride: one octave between ladder rungs.
COARSE_STRIDE = STEPS_PER_OCTAVE
#: Declared search ceiling: 12 MHz * 2**7 = 1536 MHz. A corner that still
#: passes here reports a LOWER BOUND, never an exact Fmax.
CEILING_INDEX = 7 * STEPS_PER_OCTAVE
#: Negative control: a clock the partition must NOT be able to follow. If any
#: corner "passes" here the checker itself is untrustworthy.
NEGATIVE_CONTROL_MHZ = 6000.0

TOLERANCE_RATIO = 2.0 ** (1.0 / STEPS_PER_OCTAVE)


def freq_mhz(index: int) -> float:
    return F_BASE_MHZ * 2.0 ** (index / STEPS_PER_OCTAVE)


def tolerance_pct() -> float:
    return (TOLERANCE_RATIO - 1.0) * 100.0


STATE_BRACKET = "bracket"
STATE_CENSORED = "censored_lower_bound"
STATE_FLOOR_FAIL = "nonfunctional_at_floor"
STATE_INVALID = "inconclusive"
STATE_OPEN = "open"


@dataclass
class CornerSearch:
    """Adaptive search state for one corner. `obs` maps a grid index to
    True (pass), False (fail) or None (INVALID: the probe could not be
    graded -- missing/non-finite measurement or simulator error). An invalid
    probe is never promoted to pass or fail; it freezes the search and the
    corner reports `inconclusive`."""

    corner_id: str
    ceiling_index: int = CEILING_INDEX
    obs: dict[int, bool | None] = field(default_factory=dict)

    def record(self, index: int, outcome: bool | None) -> None:
        if index in self.obs:
            raise ValueError(f"{self.corner_id}: grid index {index} observed twice")
        self.obs[index] = outcome

    # -- derived views --------------------------------------------------
    def _fails(self) -> list[int]:
        return sorted(i for i, o in self.obs.items() if o is False)

    def _passes(self) -> list[int]:
        return sorted(i for i, o in self.obs.items() if o is True)

    def _has_invalid(self) -> bool:
        return any(o is None for o in self.obs.values())

    def _hi(self) -> int | None:
        f = self._fails()
        return f[0] if f else None

    def _lo(self) -> int | None:
        hi = self._hi()
        cand = [i for i in self._passes() if hi is None or i < hi]
        return max(cand) if cand else None

    def non_monotone(self) -> bool:
        hi = self._hi()
        return hi is not None and any(i > hi for i in self._passes())

    def state(self) -> str:
        if self._has_invalid():
            return STATE_INVALID
        hi, lo = self._hi(), self._lo()
        if hi is None:
            top = max(self._passes(), default=None)
            if top is not None and top >= self.ceiling_index:
                return STATE_CENSORED
            return STATE_OPEN
        if lo is None:
            return STATE_FLOOR_FAIL if hi == 0 else STATE_OPEN
        return STATE_BRACKET if hi - lo == 1 else STATE_OPEN

    def done(self) -> bool:
        return self.state() != STATE_OPEN

    def next_index(self) -> int | None:
        """Grid index to probe next, or None when the search is finished."""
        if self.done():
            return None
        hi, lo = self._hi(), self._lo()
        if hi is None:
            top = max(self._passes(), default=-COARSE_STRIDE)
            return min(top + COARSE_STRIDE, self.ceiling_index)
        if lo is None:
            # A failure above an untested floor: probe the floor itself.
            return 0
        return (lo + hi) // 2

    def result(self) -> dict:
        state = self.state()
        lo, hi = self._lo(), self._hi()
        out = {
            "corner_id": self.corner_id,
            "state": state,
            "f_pass_mhz": freq_mhz(lo) if lo is not None else None,
            "f_fail_mhz": freq_mhz(hi) if hi is not None else None,
            "non_monotone": self.non_monotone(),
            "probes": {str(i): o for i, o in sorted(self.obs.items())},
            "n_probes": len(self.obs),
        }
        if state == STATE_CENSORED:
            out["f_pass_mhz"] = freq_mhz(max(self._passes()))
            out["f_fail_mhz"] = None
        return out


def plan_round(searches: Iterable[CornerSearch]) -> dict[int, list[str]]:
    """Group every unfinished corner by the grid index it wants probed next,
    so corners that need the same frequency share one `klt sim` request."""
    plan: dict[int, list[str]] = {}
    for s in searches:
        idx = s.next_index()
        if idx is not None:
            plan.setdefault(idx, []).append(s.corner_id)
    return dict(sorted(plan.items()))


# --------------------------------------------------------------------------
# Stimulus / timeline
# --------------------------------------------------------------------------

#: Deterministic comparator-data stimulus: ten-bit target codes, one per
#: conversion. Chosen for data activity, not for any spec: two codes
#: (811, 212) are the existing functional bench's (one per sign-bit branch);
#: 682 / 341 are the two alternating-bit patterns (maximum bit-to-bit
#: toggling). The all-ones / all-zeros codes are NOT exercised (each added
#: conversion costs ~1/N of every fleet unit's run time); their recode is
#: covered only through the sign-bit branches of the codes above.
CODES: tuple[int, ...] = (811, 212, 682, 341)
#: Conversions inside the steady-state power window (conversion 0 is skipped:
#: its data registers start from reset, not from a previous conversion).
POWER_WINDOW_CONVERSIONS = (1, len(CODES))  # [first, end) conversion index
EDGES_PER_CONVERSION = 12
FIRST_ADVANCING_EDGE = 5  # 1-based; edges 1..4 occur with RST_B asserted
RST_RELEASE_T = 4.2  # in clock periods
COMP_DELAY_T = 0.25  # COMP_OUT change, in periods after the launching edge
SAMPLE_T = 0.9  # check instant, in periods after the launching edge
RESET_SAMPLE_T = 0.6  # edge 4 + 0.6 T = 4.1 T, before the 4.2 T RST_B release

PHASE_NAMES = ["ph_sample", "ph_b9", "ph_b8", "ph_b7", "ph_b6", "ph_b5", "ph_b4",
               "ph_b3", "ph_b2", "ph_b1", "ph_b0", "ph_eoc"]
#: Output nets in the order monitored; also the pin names of the sequencer.
PHASE_NETS = [p.upper() for p in PHASE_NAMES]

#: Interface loads (EXPERIMENT ASSUMPTIONS, not ratified spec values). They
#: stand in for the analog-side gate loads the digital outputs drive in the
#: integrated ADC. farads.
LOADS_F: dict[str, float] = {
    "PH_SAMPLE": 20e-15,   # sampling-switch gate drive
    "PH_PHASE": 5e-15,     # each of PH_B9..PH_EOC (local routing + glue fanout)
    "BUSY": 5e-15,
    "DOUT": 5e-15,         # each DOUTn (downstream readout)
    "SEL": 20e-15,         # each SELnN / SELpN (CDAC bottom-plate switch gate)
    "CLKN": 50e-15,        # comparator clock input
    "HALF_LSB": 20e-15,    # HALF_LSB_EN / HALF_LSB_ENN (offset-network switch gates)
    "ADCOUT": 10e-15,      # each ADCOUTn (output pad / downstream)
}


def period_s(f_mhz: float) -> float:
    return 1e-6 / f_mhz


#: Input edges must stay inside the standard-cell library's own transition
#: limit (sky130_fd_sc_hd characterizes inputs up to ~1.5 ns) AND be realistic
#: for an on-chip clock. 1-2 ns edges were tried to save solver steps and were
#: found to corrupt cold-corner register captures (the ring skipped edges at
#: tt / -40 C / 12 MHz; a sign-bit register mis-captured at fs / 27 C), and the
#: same decks pass with 0.3 ns edges -- so a slow-edge failure is a stimulus
#: artifact, not a design result, and edges are capped well below the library
#: limit.
RISE_MAX_S = 0.3e-9
RISE_MIN_S = 10e-12
STEP_DIVISOR = 2.0  # solver max step = edge time / STEP_DIVISOR


def rise_time_s(f_mhz: float) -> float:
    """Input edge time: 5 % of the period, clamped to [RISE_MIN_S, RISE_MAX_S]."""
    return min(RISE_MAX_S, max(RISE_MIN_S, 0.05 * period_s(f_mhz)))


def edge_start_s(k: int, f_mhz: float) -> float:
    """Time at which the k-th (1-based) clock rising edge BEGINS to rise."""
    return (k - 0.5) * period_s(f_mhz)


def edge_index(conv: int, phase_j: int) -> int:
    """1-based clock-edge index that moves the ring into phase j of
    conversion `conv` (j=0 -> ph_b9 ... j=10 -> ph_eoc, j=11 -> ph_sample)."""
    return FIRST_ADVANCING_EDGE + EDGES_PER_CONVERSION * conv + phase_j


def comp_events(codes: Sequence[int] = CODES) -> list[tuple[int, float, int]]:
    """COMP_OUT level changes as (edge_index, delay_in_periods, level).

    Bit i (0 -> b9) of conversion c is decided during phase j=i and captured
    by edge j=i+1. The sequencer decides bits 8..0 from COMP_EFF =
    XNOR(COMP_OUT, DOUT9) (design/sar_sequencer.sch), so for a code whose b9
    is 0 the driven level is the INVERSE of the target bit. Levels are held
    between events."""
    events: list[tuple[int, float, int]] = []
    for c, code in enumerate(codes):
        b9 = (code >> 9) & 1
        for i in range(10):
            tb = (code >> (9 - i)) & 1
            level = tb if (i == 0 or b9 == 1) else 1 - tb
            events.append((edge_index(c, i), COMP_DELAY_T, level))
    return events


def pwl_points(events: Sequence[tuple[int, float, int]], f_mhz: float,
               t_stop: float) -> list[tuple[float, float]]:
    """Unit-amplitude PWL points (seconds, 0/1) for `events`, deduplicating
    redundant steps (an event that does not change the level emits nothing)."""
    tr = rise_time_s(f_mhz)
    pts: list[tuple[float, float]] = [(0.0, 0.0)]
    level = 0
    for k, dly, lv in events:
        if lv == level:
            continue
        t = edge_start_s(k, f_mhz) + dly * period_s(f_mhz)
        pts.append((t, float(level)))
        pts.append((t + tr, float(lv)))
        level = lv
    pts.append((t_stop, float(level)))
    return pts


def t_stop_s(f_mhz: float, n_conv: int = len(CODES)) -> float:
    last = edge_index(n_conv, 0)  # first edge of the (absent) next conversion
    return edge_start_s(last, f_mhz) + 0.95 * period_s(f_mhz)


# --------------------------------------------------------------------------
# Expectations (what the checks must read)
# --------------------------------------------------------------------------

#: monitor-code weights
PCODE_WEIGHT = {name: 1 << i for i, name in enumerate(PHASE_NAMES)}
CTL_WEIGHT = {"BUSY": 1, "HALF_LSB_EN": 2, "HALF_LSB_ENN": 4}
CODE_TOL = 0.25


@dataclass(frozen=True)
class Check:
    name: str          # `.meas` / klt measurement name
    expected: float
    t_s_per_period: tuple[int, float]  # (edge index, offset in periods) sampling instant
    node: str          # monitor node sampled
    what: str          # human description


def _pcode_expected(j: int) -> int:
    return PCODE_WEIGHT["ph_sample"] if j == 11 else PCODE_WEIGHT[PHASE_NAMES[j + 1]]


def _ctl_expected(j: int) -> int:
    busy = 1 if j <= 10 else 0
    hl = 1 if 1 <= j <= 10 else 0
    return busy * 1 + hl * 2 + (0 if hl else 1) * 4


def expected_checks(codes: Sequence[int] = CODES) -> list[Check]:
    out: list[Check] = []
    out.append(Check("pc_rst", float(PCODE_WEIGHT["ph_sample"]), (4, RESET_SAMPLE_T),
                     "PCODE", "reset state: only ph_sample set (RST_B asserted, clock running)"))
    out.append(Check("ctl_rst", float(CTL_WEIGHT["HALF_LSB_ENN"]), (4, RESET_SAMPLE_T),
                     "CTLCODE", "reset state: BUSY=0, HALF_LSB_EN=0, HALF_LSB_ENN=1"))
    for c, code in enumerate(codes):
        for j in range(EDGES_PER_CONVERSION):
            k = edge_index(c, j)
            out.append(Check(f"pc_c{c}_j{j}", float(_pcode_expected(j)), (k, SAMPLE_T),
                             "PCODE", f"conversion {c}: one-hot phase after edge j={j}"))
            out.append(Check(f"ctl_c{c}_j{j}", float(_ctl_expected(j)), (k, SAMPLE_T),
                             "CTLCODE", f"conversion {c}: BUSY/HALF_LSB control after edge j={j}"))
        k_eoc = edge_index(c, 10)
        b9 = (code >> 9) & 1
        adc = sum((1 << i) for i in range(9) if ((code >> i) & 1) == b9)
        seln = sum((1 << i) for i in range(9) if ((code >> i) & 1) and not b9)
        selp = sum((1 << i) for i in range(9) if ((code >> i) & 1) and b9)
        out.append(Check(f"dout_c{c}", float(code), (k_eoc, SAMPLE_T), "DCODE",
                         f"conversion {c}: captured code {code}"))
        out.append(Check(f"adc_c{c}", float(adc), (k_eoc, SAMPLE_T), "ADCCODE",
                         f"conversion {c}: ADCOUT recode (DOUT_i XNOR DOUT9)"))
        out.append(Check(f"seln_c{c}", float(seln), (k_eoc, SAMPLE_T), "SELNCODE",
                         f"conversion {c}: SELn = DOUT_i AND NOT DOUT9"))
        out.append(Check(f"selp_c{c}", float(selp), (k_eoc, SAMPLE_T), "SELPCODE",
                         f"conversion {c}: SELp = DOUT9 AND DOUT_i"))
    return out


def check_time_s(chk: Check, f_mhz: float) -> float:
    k, off = chk.t_s_per_period
    return edge_start_s(k, f_mhz) + off * period_s(f_mhz)


def power_windows(f_mhz: float) -> dict[str, tuple[float, float, int]]:
    """Measurement windows (start_s, end_s, n_conversions) for rail power.
    `reset`: RST_B asserted, clock running, two whole periods (n=0).
    `active`: whole conversions POWER_WINDOW_CONVERSIONS, edge to edge."""
    c0, c1 = POWER_WINDOW_CONVERSIONS
    return {
        "reset": (edge_start_s(2, f_mhz), edge_start_s(4, f_mhz), 0),
        "active": (edge_start_s(edge_index(c0, 0), f_mhz),
                   edge_start_s(edge_index(c1, 0), f_mhz), c1 - c0),
    }


# --------------------------------------------------------------------------
# Grading
# --------------------------------------------------------------------------

@dataclass
class ProbeGrade:
    passed: bool | None          # None => INVALID (not gradeable)
    failures: list[str]          # checks that read the wrong value
    invalid: list[str]           # checks that are missing / non-finite
    n_checks: int


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def grade_values(values: dict[str, float | None],
                 checks: Sequence[Check] | None = None) -> ProbeGrade:
    """Grade one probe's measured values against `checks`.

    A missing or non-finite value is INVALID (passed=None) unless some other
    check already read a definite wrong value, in which case the probe is a
    FAIL: a wrong value is evidence of non-function whether or not another
    measurement was also lost. A probe is a pass only if EVERY check is
    present, finite and within CODE_TOL of its expectation."""
    checks = list(checks if checks is not None else expected_checks())
    failures: list[str] = []
    invalid: list[str] = []
    for chk in checks:
        v = values.get(chk.name)
        if not _finite(v):
            invalid.append(chk.name)
        elif abs(v - chk.expected) > CODE_TOL:
            failures.append(f"{chk.name}: read {v:.3f}, expected {chk.expected:g}")
    if failures:
        return ProbeGrade(False, failures, invalid, len(checks))
    if invalid:
        return ProbeGrade(None, failures, invalid, len(checks))
    return ProbeGrade(True, [], [], len(checks))


# --------------------------------------------------------------------------
# Power
# --------------------------------------------------------------------------

def power_from_avg_current(i_avg_a: float | None, vdd: float) -> float | None:
    """Average power drawn from the digital rail. `i(Vdig)` is the current
    INTO the source's + terminal, so a supply sourcing current reads
    NEGATIVE; power is -i * V. Returns None (never 0) for a missing,
    non-finite or non-sourcing (<= 0 W) reading: the rail of a powered,
    clocked digital block always draws power, so a non-positive value means
    the measurement is wrong, and wrong numbers are not reported."""
    if not _finite(i_avg_a) or not _finite(vdd):
        return None
    p = -i_avg_a * vdd
    return p if p > 0.0 else None


def energy_per_conversion_j(p_active_w: float | None, f_mhz: float) -> float | None:
    """Rail energy per conversion = P_active * (12 clock periods)."""
    if p_active_w is None:
        return None
    return p_active_w * EDGES_PER_CONVERSION * period_s(f_mhz)


# --------------------------------------------------------------------------
# Netlist sources (from the committed schematic-derived netlist)
# --------------------------------------------------------------------------

def extract_dut(top_netlist_text: str) -> dict:
    """Pull the digital partition out of `design/sar_adc_top.spice` text:
    the `sar_sequencer` subcircuit (verbatim) and the top-level
    `sky130_fd_sc_hd` glue instances (the 33 instances the integration
    schematic adds directly). Returns {'sequencer', 'sequencer_pins',
    'glue'}."""
    lines = top_netlist_text.splitlines()
    sub_start = None
    sub_end = None
    for i, ln in enumerate(lines):
        if ln.lower().startswith(".subckt sar_sequencer"):
            sub_start = i
        elif sub_start is not None and ln.lower().startswith(".ends"):
            sub_end = i
            break
    if sub_start is None or sub_end is None:
        raise ValueError("no `.subckt sar_sequencer` ... `.ends` block found")
    sequencer = lines[sub_start:sub_end + 1]
    pins = sequencer[0].split()[2:]

    first_sub = next(i for i, ln in enumerate(lines) if ln.lower().startswith(".subckt"))
    glue = [ln for ln in lines[:first_sub]
            if ln.startswith("x") and "sky130_fd_sc_hd__" in ln]
    return {"sequencer": sequencer, "sequencer_pins": pins, "glue": glue}


GLUE_EXPECTED_INSTANCES = 33


def _weighted(nodes: Sequence[tuple[str, int]]) -> str:
    return " + ".join(f"{w}*h(v({n}))" for n, w in nodes)


def build_netlist(f_mhz: float, dut: dict, *, codes: Sequence[int] = CODES,
                  stdcell_include: str = "$PDK_ROOT/sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice"
                  ) -> str:
    """Circuit BODY (no `.end`/`.control`; `klt sim` adds `.lib`, `.temp`,
    the supply `alter` and the analysis) for one clock frequency.

    The rail is the DC source `Vdig` (the `klt sim` supply axis key `vdig`).
    CLK / RST_B / COMP_OUT are behavioural sources scaled by v(VPWR), so the
    stimulus tracks the supply corner without altering a waveform source.
    Their (ideal-source) energy is OUTSIDE the DUT boundary; the DUT's own
    cells, plus the charge its outputs deliver into the declared loads, are
    inside it because all of it is drawn through `Vdig`."""
    pins = dut["sequencer_pins"]
    tr = rise_time_s(f_mhz)
    T = period_s(f_mhz)
    t_stop = t_stop_s(f_mhz, len(codes))
    f = lambda x: f"{x:.6e}"  # noqa: E731

    L: list[str] = []
    a = L.append
    a(f"* digital-partition characterization deck body, f_clk = {f_mhz:.4f} MHz (issue #619)")
    a("* DUT = design/sar_sequencer subckt + the top-level sky130_fd_sc_hd glue,")
    a("* both copied verbatim from the committed design/sar_adc_top.spice.")
    a("* one solver thread per unit: concurrent units on a shared runner must not oversubscribe it")
    a(".options num_threads=1")
    a(".global VPWR VGND")
    a(f".include {stdcell_include}")
    a("")
    a("* --- rails: Vdig is the digital-rail ammeter (positive current = into the + pin) ---")
    a("Vdig VPWR 0 DC 1.8")
    a("Vgnd VGND 0 DC 0")
    a("")
    a("* --- stimulus (ideal; energy outside the DUT boundary) ---")
    a(f"VCLKU CLKU 0 PULSE(0 1 {f(0.5 * T)} {f(tr)} {f(tr)} {f(0.5 * T - tr)} {f(T)})")
    a("BCLK CLK 0 V = v(CLKU)*v(VPWR)")
    rst_pts = [(0.0, 0.0), (RST_RELEASE_T * T, 0.0), (RST_RELEASE_T * T + tr, 1.0), (t_stop, 1.0)]
    a("VRSTU RSTU 0 PWL(" + " ".join(f"{f(t)} {f(v)}" for t, v in rst_pts) + ")")
    a("BRST RST_B 0 V = v(RSTU)*v(VPWR)")
    cp = pwl_points(comp_events(codes), f_mhz, t_stop)
    a("VCMPU CMPU 0 PWL(" + " ".join(f"{f(t)} {f(v)}" for t, v in cp) + ")")
    a("BCMP COMP_OUT 0 V = v(CMPU)*v(VPWR)")
    a("* OUTN_NC is the comparator's OUTN output in the integrated ADC; here a fixed DC 0.")
    a("VOUTN OUTN_NC 0 DC 0")
    a("")
    a("* --- DUT ---")
    a("xseq " + " ".join(pins) + " sar_sequencer")
    L.extend(dut["sequencer"])
    L.extend(dut["glue"])
    a("")
    a("* --- declared interface loads (experiment assumptions, see digital_char.LOADS_F) ---")
    n = 0

    def cap(net: str, val: float) -> None:
        nonlocal n
        n += 1
        a(f"Cld{n} {net} 0 {val:.4e}")

    cap("PH_SAMPLE", LOADS_F["PH_SAMPLE"])
    for ph in PHASE_NETS[1:]:
        cap(ph, LOADS_F["PH_PHASE"])
    cap("BUSY", LOADS_F["BUSY"])
    for i in range(10):
        cap(f"DOUT{i}", LOADS_F["DOUT"])
    for i in range(9):
        cap(f"SELn{i}", LOADS_F["SEL"])
        cap(f"SELp{i}", LOADS_F["SEL"])
        cap(f"ADCOUT{i}", LOADS_F["ADCOUT"])
    cap("CLKN", LOADS_F["CLKN"])
    cap("HALF_LSB_EN", LOADS_F["HALF_LSB"])
    cap("HALF_LSB_ENN", LOADS_F["HALF_LSB"])
    a("")
    a("* --- behavioural monitors (high impedance; they load nothing) ---")
    a(".func h(x) '0.5*(1+tanh(((x)-0.5*v(VPWR))/0.05))'")
    a("BPCODE PCODE 0 V = " + _weighted([(p, PCODE_WEIGHT[p.lower()]) for p in PHASE_NETS]))
    a("BCTL CTLCODE 0 V = " + _weighted([("BUSY", 1), ("HALF_LSB_EN", 2), ("HALF_LSB_ENN", 4)]))
    a("BDCODE DCODE 0 V = " + _weighted([(f"DOUT{i}", 1 << i) for i in range(10)]))
    a("BADC ADCCODE 0 V = " + _weighted([(f"ADCOUT{i}", 1 << i) for i in range(9)]))
    a("BSELN SELNCODE 0 V = " + _weighted([(f"SELn{i}", 1 << i) for i in range(9)]))
    a("BSELP SELPCODE 0 V = " + _weighted([(f"SELp{i}", 1 << i) for i in range(9)]))
    return "\n".join(L) + "\n"


def measurement_cards(f_mhz: float, checks: Sequence[Check] | None = None) -> list[dict]:
    """`klt sim` measurement entries: one `.meas FIND ... AT=` per check and
    the two rail-current averages."""
    checks = list(checks if checks is not None else expected_checks())
    out = []
    for chk in checks:
        t = check_time_s(chk, f_mhz)
        out.append({"name": chk.name,
                    "spice": f".meas tran {chk.name} FIND v({chk.node.lower()}) AT={t:.6e}"})
    for tag, (t0, t1, _n) in power_windows(f_mhz).items():
        out.append({"name": f"iavg_{tag}",
                    "spice": f".meas tran iavg_{tag} AVG i(Vdig) FROM={t0:.6e} TO={t1:.6e}",
                    "unit": "A"})
    return out


def max_step_s(f_mhz: float) -> float:
    """Transient max / print step: edge time / STEP_DIVISOR (about two points
    per edge or finer). A cap of ~one point per 1 ns edge was the original
    suspect for the slow-edge failures described at RISE_MAX_S; with fast edges
    the corners that failed pass at 0.83 ns and at 0.06 ns steps alike, so the
    step is a cost/accuracy trade, not a correctness knob, and is tied to the
    edge time rather than the period."""
    return rise_time_s(f_mhz) / STEP_DIVISOR


def analysis_args(f_mhz: float, n_conv: int = len(CODES)) -> str:
    h = max_step_s(f_mhz)
    return f"{h:.6e} {t_stop_s(f_mhz, n_conv):.6e} 0 {h:.6e}"


# --------------------------------------------------------------------------
# klt sim request / report
# --------------------------------------------------------------------------

SUPPLY_KEY = "vdig"


def parse_corner_id(cid: str) -> tuple[str, float, float]:
    m = re.fullmatch(r"([a-z]+)_(-?[0-9.]+)c_([0-9.]+)v", cid)
    if not m:
        raise ValueError(f"unparseable corner id {cid!r}")
    return m.group(1), float(m.group(2)), float(m.group(3))


def make_corner_id(process: str, temp_c: float, vdd: float) -> str:
    return f"{process}_{temp_c:g}c_{vdd:.2f}v"


def build_request(netlist_name: str, f_mhz: float, corner_ids: Sequence[str], *,
                  timeout_s: float = 900.0, models_lib: str = "libs.tech/combined/sky130.lib.spice",
                  pdk: str = "sky130A", backend: str | None = None,
                  checks: Sequence[Check] | None = None,
                  batch: dict | None = None) -> dict:
    """One `klt sim` request covering exactly `corner_ids` at `f_mhz`.

    The corner axes are the full product of the distinct process /
    temperature / supply values; points not wanted are removed with
    `exclude`, so any subset of the OAT grid is one request."""
    pts = [parse_corner_id(c) for c in corner_ids]
    procs = sorted({p for p, _, _ in pts})
    temps = sorted({t for _, t, _ in pts})
    vdds = sorted({v for _, _, v in pts})
    want = set(pts)
    exclude = []
    for p in procs:
        for t in temps:
            for v in vdds:
                if (p, t, v) not in want:
                    exclude.append({"process": p, "temperature_c": t, "supply_v": {SUPPLY_KEY: v}})
    req: dict = {
        "netlist": netlist_name,
        "engine": "ngspice",
        "models": {"pdk": pdk, "lib": models_lib},
        "corners": {"process": procs, "supply_v": {SUPPLY_KEY: vdds}, "temperature_c": temps},
        "analysis": {"kind": "tran", "args": analysis_args(f_mhz)},
        "measurements": measurement_cards(f_mhz, checks),
        "options": {"timeout_s": timeout_s, "keep_artifacts": True},
    }
    if exclude:
        req["exclude"] = exclude
    if backend:
        req["backend"] = backend
    if batch:
        req["batch"] = dict(batch)
    return req


@dataclass
class UnitResult:
    corner_id: str
    status: str
    values: dict[str, float | None]
    errors: list[str]
    messages: list[str] = field(default_factory=list)


def read_report(report: dict) -> tuple[dict[str, UnitResult], dict]:
    """Per-corner results keyed by corner id, plus run-level environment
    facts (remote job id etc.). Raises ValueError for an error envelope or a
    report without a corner list -- a campaign must stop on those rather
    than invent measurements."""
    if not isinstance(report, dict):
        raise ValueError("klt sim report is not a JSON object")
    if "error" in report and "corners" not in report:
        raise ValueError(f"klt sim error envelope: {report['error']}")
    corners = report.get("corners")
    if not isinstance(corners, list):
        raise ValueError("klt sim report has no corners[] list")
    results: dict[str, UnitResult] = {}
    for c in corners:
        sv = (c.get("supply_v") or {}).get(SUPPLY_KEY)
        if not _finite(sv) or c.get("process") is None or not _finite(c.get("temperature_c")):
            raise ValueError(f"corner without process/temperature/{SUPPLY_KEY}: {c.get('corner_id')}")
        cid = make_corner_id(c["process"], float(c["temperature_c"]), float(sv))
        vals = {m["name"]: m.get("value") for m in (c.get("measurements") or [])
                if isinstance(m, dict) and "name" in m}
        errs = [str(d.get("code")) for d in (c.get("diagnostics") or [])
                if isinstance(d, dict) and d.get("severity") == "error"]
        msgs = [str(d.get("message")) for d in (c.get("diagnostics") or [])
                if isinstance(d, dict) and d.get("severity") == "error" and d.get("code") != "measurement"]
        results[cid] = UnitResult(cid, str(c.get("status")), vals, errs, msgs[:2])
    env = report.get("environment") or {}
    return results, {"remote": env.get("remote"), "status": report.get("status")}


def grade_unit(unit: UnitResult | None, checks: Sequence[Check] | None = None) -> ProbeGrade:
    """Grade one corner's unit. A missing unit, an `error` corner (the
    simulator produced nothing trustworthy) or an error-severity diagnostic
    is INVALID, never a design failure and never a pass."""
    checks = list(checks if checks is not None else expected_checks())
    if unit is None:
        return ProbeGrade(None, [], ["<corner absent from report>"], len(checks))
    if unit.status in ("error", "inconclusive") or unit.errors:
        return ProbeGrade(None, [], [f"corner status {unit.status} diagnostics {sorted(set(unit.errors))}"],
                          len(checks))
    return grade_values(unit.values, checks)


# --------------------------------------------------------------------------
# Campaign driver (injected submitter -> PDK-free testable)
# --------------------------------------------------------------------------

class InfrastructureError(RuntimeError):
    """Every unit of a submitted request was ungradeable (runner / fleet /
    simulator failure, not a design result). The campaign stops rather than
    freezing nine corners on one infrastructure fault."""


#: submit(freq_mhz, corner_ids) -> (per-corner UnitResult, run info)
Submitter = Callable[[float, Sequence[str]], tuple[dict[str, UnitResult], dict]]


def run_search(corner_ids: Sequence[str], submit: Submitter, *,
               ceiling_index: int = CEILING_INDEX, max_rounds: int = 64,
               checks: Sequence[Check] | None = None, max_workers: int = 1,
               ) -> tuple[dict[str, CornerSearch], list[dict], dict[str, dict[int, UnitResult]]]:
    """Lockstep adaptive search over all corners. Returns (searches, probe
    log, raw per-corner per-index units). The probe log lists every submit
    (index, frequency, corners, run info) for the evidence record.

    Each round submits one request per distinct grid index wanted
    (`max_workers` of them concurrently -- the host rule caps this at 2).
    A submit that raises stops the whole campaign: no corner's missing
    result is ever replaced by a guess."""
    from concurrent.futures import ThreadPoolExecutor

    searches = {c: CornerSearch(c, ceiling_index) for c in corner_ids}
    log: list[dict] = []
    units: dict[str, dict[int, UnitResult]] = {c: {} for c in corner_ids}
    for _ in range(max_rounds):
        plan = plan_round(searches.values())
        if not plan:
            break
        items = list(plan.items())
        if max_workers > 1 and len(items) > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                outs = list(pool.map(lambda it: submit(freq_mhz(it[0]), it[1]), items))
        else:
            outs = [submit(freq_mhz(idx), cids) for idx, cids in items]
        for (idx, cids), (results, info) in zip(items, outs):
            log.append({"index": idx, "f_mhz": freq_mhz(idx), "corners": list(cids), "run": info})
            grades = {cid: grade_unit(results.get(cid), checks) for cid in cids}
            if all(g.passed is None for g in grades.values()):
                msgs = sorted({m for cid in cids if results.get(cid) for m in results[cid].messages})
                raise InfrastructureError(
                    f"no unit of the {freq_mhz(idx):.3f} MHz request was gradeable "
                    f"(status {info.get('status')}): {'; '.join(msgs) or 'no diagnostics'}")
            for cid in cids:
                unit = results.get(cid)
                g = grades[cid]
                searches[cid].record(idx, g.passed)
                if unit is not None:
                    units[cid][idx] = unit
    else:
        raise RuntimeError("search did not terminate within max_rounds")
    return searches, log, units


# --------------------------------------------------------------------------
# Negative control and checklist predicate
# --------------------------------------------------------------------------

def negative_control_ok(grades: dict[str, ProbeGrade]) -> bool:
    """The too-fast clock must be graded FAIL (False) at every corner. A pass
    means the checker cannot detect failure; an invalid grade means the
    control did not run."""
    return bool(grades) and all(g.passed is False for g in grades.values())


@dataclass
class ChecklistVerdict:
    meets: bool
    reasons: list[str]


def checklist_verdict(*, corner_ids: Sequence[str], results: dict[str, dict],
                      power: dict[str, dict], area: dict | None,
                      negative_control: bool | None) -> ChecklistVerdict:
    """Does a campaign result satisfy item 8's digital requirement ("Fmax,
    area, and power across the corner set, not just functional pass/fail")
    well enough to back a citation? Every reason it does not is listed."""
    reasons: list[str] = []
    for cid in corner_ids:
        r = results.get(cid)
        if r is None:
            reasons.append(f"{cid}: no frequency result")
            continue
        st = r.get("state")
        if st == STATE_INVALID or st == STATE_OPEN:
            reasons.append(f"{cid}: search {st} (not a bracket or declared lower bound)")
        elif st == STATE_FLOOR_FAIL:
            reasons.append(f"{cid}: nonfunctional at the {F_BASE_MHZ:g} MHz operating point")
        if r.get("non_monotone"):
            reasons.append(f"{cid}: non-monotone pass/fail (a pass above a fail)")
        p = power.get(cid) or {}
        if p.get("p_active_w") is None or p.get("p_reset_w") is None:
            reasons.append(f"{cid}: missing/invalid rail power at the {F_BASE_MHZ:g} MHz point")
        if p.get("functional_at_op") is not True:
            reasons.append(f"{cid}: operating-point probe not functionally correct")
    if not area or area.get("composed_footprint_um2") is None:
        reasons.append("no routed-artifact area derivation")
    if negative_control is not True:
        reasons.append("too-fast-clock negative control missing or not failing at every corner")
    return ChecklistVerdict(not reasons, reasons)


def dumps(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


# --------------------------------------------------------------------------
# Campaign summary (pure; the runner supplies the raw pieces)
# --------------------------------------------------------------------------

def op_point_power(unit: UnitResult | None, corner_id: str,
                   grade: ProbeGrade | None) -> dict:
    """Rail power / energy at the provisional operating point for one corner.
    `functional_at_op` is the 12 MHz probe's own pass/fail: a nonfunctional
    corner keeps its numbers (flagged) but is never reported as clean."""
    _p, _t, vdd = parse_corner_id(corner_id)
    f = F_BASE_MHZ
    v = unit.values if unit else {}
    p_act = power_from_avg_current(v.get("iavg_active"), vdd)
    p_rst = power_from_avg_current(v.get("iavg_reset"), vdd)
    e = energy_per_conversion_j(p_act, f)
    return {
        "f_mhz": f, "vdd_v": vdd,
        "p_active_w": p_act, "p_reset_w": p_rst,
        "energy_per_conversion_j": e,
        "functional_at_op": (grade.passed if grade is not None else None),
    }


def summarize(searches: dict[str, CornerSearch], units: dict[str, dict[int, UnitResult]],
              neg_grades: dict[str, ProbeGrade], area: dict | None) -> dict:
    results = {c: s.result() for c, s in searches.items()}
    power = {}
    for c in searches:
        u = units.get(c, {}).get(0)
        power[c] = op_point_power(u, c, grade_unit(u) if u is not None else None)
    nc = negative_control_ok(neg_grades) if neg_grades else None
    verdict = checklist_verdict(corner_ids=list(searches), results=results, power=power,
                                area=area, negative_control=nc)
    return {
        "results": results, "power": power, "area": area,
        "negative_control": {
            "f_mhz": NEGATIVE_CONTROL_MHZ, "ok": nc,
            "per_corner": {c: {"passed": g.passed, "n_failures": len(g.failures),
                               "n_invalid": len(g.invalid)} for c, g in neg_grades.items()},
        },
        "checklist": {"meets": verdict.meets, "reasons": verdict.reasons},
    }


def runner_skew(probe_log: Sequence[dict], extra_runs: Sequence[dict] = ()) -> list[str]:
    """Distinct 'runner klt X vs client klt Y' statements from the submissions'
    `environment.remote` blocks, for every run whose runner and client
    versions differ (empty when none do)."""
    seen: list[str] = []
    runs = [e.get("run") or {} for e in probe_log] + list(extra_runs)
    for run in runs:
        rem = run.get("remote") or {}
        if not isinstance(rem, dict):
            continue
        r, c = rem.get("runner_klt_version"), rem.get("client_klt_version")
        if r and c and (rem.get("runner_compatibility") == "mismatch" or r != c):
            msg = f"fleet runner klt {r} vs submitting client klt {c}"
            if msg not in seen:
                seen.append(msg)
    return seen

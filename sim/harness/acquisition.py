"""Two-pulse acquisition stimulus for the sampling front end and CDAC handoff."""

from .testbench import pwl

# Precharge the bootstrap, sample the old inputs, then toggle them during hold.
EDGE_TR_NS = 0.2
T_SAMPLE1_RISE_NS = 10.0
T_SAMPLE1_WIDTH_NS = 100.0
T_SAMPLE1_FALL_NS = T_SAMPLE1_RISE_NS + T_SAMPLE1_WIDTH_NS
T_INPUT_TOGGLE_NS = T_SAMPLE1_FALL_NS + 20.0
T_SAMPLE2_RISE_NS = T_INPUT_TOGGLE_NS + 30.0
T_SAMPLE2_WIDTH_NS = 150.0
T_SAMPLE2_FALL_NS = T_SAMPLE2_RISE_NS + T_SAMPLE2_WIDTH_NS
TRAN_STOP_NS = T_SAMPLE2_FALL_NS + 20.0

# Read one DR-006 worst-case clock period after the acquiring edge's midpoint.
# The later confirm read is still inside the second pulse, clear of turn-off.
T_PHASE_WORST_NS = 1.0e3 / 12.0  # 12 MHz
T_PHASE_SLOW_NS = 1.0e3 / 1.2  # 1.2 MHz
TRIG_AT_NS = T_SAMPLE2_RISE_NS + EDGE_TR_NS / 2.0
BUDGET_PROBE_AT_NS = TRIG_AT_NS + T_PHASE_WORST_NS
CONFIRM_AT_NS = T_SAMPLE2_FALL_NS - 5.0

V_INITIAL_P, V_FINAL_P = 0.2, 1.6
V_INITIAL_N, V_FINAL_N = 1.6, 0.2
SIDES = {
    "p": ("TOP_P", V_INITIAL_P, V_FINAL_P),
    "n": ("TOP_N", V_INITIAL_N, V_FINAL_N),
}


def _input_step(initial: float, final: float) -> str:
    return pwl(
        [
            (0.0, initial),
            (T_INPUT_TOGGLE_NS, initial),
            (T_INPUT_TOGGLE_NS + EDGE_TR_NS, final),
            (TRAN_STOP_NS, final),
        ]
    )


def acquisition_sources(vdd: float) -> list[str]:
    """Render VINP, VINN and SAMPLE with the SAMPLE pulses at the corner's VDD."""
    sample = pwl(
        [
            (0.0, 0.0),
            (T_SAMPLE1_RISE_NS, 0.0),
            (T_SAMPLE1_RISE_NS + EDGE_TR_NS, vdd),
            (T_SAMPLE1_FALL_NS, vdd),
            (T_SAMPLE1_FALL_NS + EDGE_TR_NS, 0.0),
            (T_SAMPLE2_RISE_NS, 0.0),
            (T_SAMPLE2_RISE_NS + EDGE_TR_NS, vdd),
            (T_SAMPLE2_FALL_NS, vdd),
            (T_SAMPLE2_FALL_NS + EDGE_TR_NS, 0.0),
            (TRAN_STOP_NS, 0.0),
        ]
    )
    return [
        f"Vinp VINP 0 {_input_step(V_INITIAL_P, V_FINAL_P)}",
        f"Vinn VINN 0 {_input_step(V_INITIAL_N, V_FINAL_N)}",
        f"Vsample SAMPLE 0 {sample}",
    ]

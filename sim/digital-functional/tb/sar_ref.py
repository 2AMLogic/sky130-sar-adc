"""Reference model for the digital partition's two macros -- written from the
specification text, not from the gate netlists it is checked against:

  * sar_sequencer  (design/sar_sequencer.sch header; DR-006): an (N+1)-stage
    walking-one ring (N=10 bit-trial phases MSB first, plus EOC) and a 10-bit
    SAR register that captures COMP_OUT during its own bit-trial phase.
  * top_glue (DR-008 decision-directed drive + offset-binary recode; DR-009
    dummy load and half-LSB enable pair; issue #264 comparator clock polarity).

Pure Python, no simulator dependency: `python3 -I sar_ref.py` runs the
model's own self-check (see selfcheck()), which is what makes the reference
trustworthy independently of the DUT.

Timing convention: one call to SeqRef.step() is one rising CLK edge. All
next-state values are computed from PRE-edge values (flip-flop semantics);
reset is asynchronous and active low.
"""

N = 10  # bit-trial phases; DR-006 (provisional, spec DRAFT)

# Output ordering used everywhere: index 0 = MSB phase (B9) ... index 9 = B0.
PHASES = [f"PH_B{n}" for n in range(N - 1, -1, -1)]


class SeqRef:
    def __init__(self):
        self.reset()

    def reset(self):
        self.ring = [0] * (N + 1)   # [B9, B8, ..., B0, EOC]
        self.dout = [0] * N         # dout[0] is DOUT9 ... dout[9] is DOUT0

    @property
    def busy(self):
        return int(any(self.ring))

    @property
    def sample(self):
        return 1 - self.busy

    def step(self, comp):
        """One rising edge with reset released; `comp` is COMP_OUT's value
        in the cycle that ends at this edge."""
        sample, ring, dout = self.sample, self.ring, self.dout
        self.dout = [comp if ring[i] else dout[i] for i in range(N)]
        self.ring = [sample] + ring[:-1]

    def outputs(self):
        o = {name: self.ring[i] for i, name in enumerate(PHASES)}
        o["PH_EOC"] = self.ring[N]
        o["PH_SAMPLE"] = self.sample
        o["BUSY"] = self.busy
        for i in range(N):
            o[f"DOUT{N - 1 - i}"] = self.dout[i]
        return o

    def code(self):
        """DOUT9..DOUT0 as an unsigned integer."""
        return sum(b << (N - 1 - i) for i, b in enumerate(self.dout))


def glue(dout, ph_b9, busy, outn_nc, clk):
    """Combinational reference for top_glue. `dout` is the 10-bit integer
    DOUT9..DOUT0. Returns every output port as 0/1."""
    d9 = (dout >> 9) & 1
    d9n = 1 - d9
    o = {"CLKN": 1 - clk}
    for i in range(N - 1):
        di = (dout >> i) & 1
        o[f"SELp{i}"] = d9 & di          # DR-008: only the sign-selected side moves
        o[f"SELn{i}"] = d9n & di
        o[f"ADCOUT{i}"] = di ^ d9n       # DR-008 recode: pass if DOUT9, invert if not
    o["HALF_LSB_EN"] = busy & (1 - ph_b9)            # DR-009 item 2
    o["HALF_LSB_ENN"] = 1 - o["HALF_LSB_EN"]
    o["DUMLOAD_MUX_NC"] = outn_nc if ph_b9 else d9    # DR-009 item 1 (matched mux)
    o["DUMLOAD_XNOR_NC"] = 1 - (outn_nc ^ d9)         # DR-009 item 1 (matched xnor)
    return o


def adc_code(dout):
    """The user-facing 10-bit code {DOUT9, ADCOUT8..ADCOUT0}."""
    o = glue(dout, 0, 0, 0, 0)
    return (((dout >> 9) & 1) << 9) | sum(o[f"ADCOUT{i}"] << i for i in range(N - 1))


def closed_loop_comp(target, upper_bits_decided, bit):
    """Ideal comparator against an ideal DAC for the textbook binary search:
    keep the trial bit iff the input code is >= (decided upper bits | trial)."""
    return int(target >= (upper_bits_decided | (1 << bit)))


def selfcheck():
    # 1. Walking one: exactly one phase high at a time, MSB first, EOC last,
    #    then one all-low idle cycle (PH_SAMPLE) before the ring re-injects.
    m = SeqRef()
    seen = []
    for _ in range(3 * (N + 2)):
        m.step(0)
        seen.append(tuple(m.ring))
    period = N + 2
    assert seen[0] == (1,) + (0,) * N
    for k in range(N + 1):
        assert seen[k] == tuple(int(j == k) for j in range(N + 1)), k
    assert seen[N + 1] == (0,) * (N + 1)           # idle cycle
    assert seen[period] == seen[0]                 # period N+2 = 12 clocks
    # 2. Closed-loop textbook SAR: every code is recovered exactly, back to
    #    back, with no reset in between (stale lower bits must not matter).
    m = SeqRef()
    for target in range(1 << N):
        done = False
        while not done:
            ph = [i for i in range(N) if m.ring[i]]
            comp = 0
            if ph:
                bit = N - 1 - ph[0]
                upper = m.code() & ~((1 << (bit + 1)) - 1)
                comp = closed_loop_comp(target, upper, bit)
            m.step(comp)
            done = m.ring[N] == 1
        assert m.code() == target, (target, m.code())
    # 3. Async reset clears everything.
    m.reset()
    assert m.code() == 0 and m.busy == 0 and m.sample == 1
    # 4. Glue invariants (DR-008): one side only; recode round-trips.
    for d in range(1 << N):
        g = glue(d, 0, 0, 0, 0)
        d9 = (d >> 9) & 1
        for i in range(N - 1):
            assert (g[f"SELn{i}"] if d9 else g[f"SELp{i}"]) == 0
        mag = sum(g[f"ADCOUT{i}"] << i for i in range(N - 1))
        assert mag == ((d & 0x1FF) if d9 else (~d & 0x1FF))
    assert adc_code(0x3FF) == 0x3FF and adc_code(0x000) == 0x1FF
    return "sar_ref selfcheck OK"


if __name__ == "__main__":
    print(selfcheck())

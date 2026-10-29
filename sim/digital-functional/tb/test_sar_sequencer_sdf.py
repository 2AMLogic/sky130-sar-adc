"""SDF-annotated variant of test_sar_sequencer.py (issue #679).

Identical checks; only the timing is parameterised from the environment so the
post-route, back-annotated run can wait for real delays: SAR_TB_HALF_NS (clock
half period) and SAR_TB_SETTLE_NS (time allowed after an edge / input change
before outputs are compared). The zero-delay original is left untouched because
the cited zero-delay record hashes it.
"""
# Original docstring of test_sar_sequencer.py:
# Bit-exact gate-level regression for the sar_sequencer macro against
# sar_ref.SeqRef. Every test compares ALL 26 outputs to the model after every
# clock edge (and after every asynchronous reset), so a pass is bit-exact over
# the whole cycle-by-cycle trace, not just over end-of-conversion codes.
# 
# Run through `klt functional-verification` (see ../requests/).

import os
import os
import random

import cocotb
from cocotb.triggers import Timer

from sar_ref import N, SeqRef, closed_loop_comp

OUT_NAMES = list(SeqRef().outputs())
# Zero-delay default: 100 MHz clock, outputs sampled 1 ns after an edge. The
# SDF-annotated run (issue #679) overrides both from the environment: the clock
# half period (period >= the 12 MHz STA request's 83.33 ns) and the settle time
# after an edge/input change, which must cover the back-annotated delays.
HALF = float(os.environ.get("SAR_TB_HALF_NS", "5"))  # ns
SETTLE = float(os.environ.get("SAR_TB_SETTLE_NS", "1"))  # ns


def read(dut):
    got = {}
    for name in OUT_NAMES:
        v = getattr(dut, name).value
        got[name] = int(v) if v.is_resolvable else "x"
    return got


def check(dut, model, what):
    got, want = read(dut), model.outputs()
    bad = {k: (got[k], want[k]) for k in want if got[k] != want[k]}
    assert not bad, f"{what}: (dut, ref) mismatches {bad}"


class Bench:
    def __init__(self, dut):
        self.dut, self.model, self.edges = dut, SeqRef(), 0
        dut.CLK.value = 0
        dut.COMP_OUT.value = 0
        dut.RST_B.value = 0

    async def reset(self, cycles=2):
        self.dut.RST_B.value = 0
        self.model.reset()
        await Timer(SETTLE, unit="ns")
        check(self.dut, self.model, "asynchronous reset")
        for _ in range(cycles):
            await self.clock(0, check_reset=True)
        self.dut.RST_B.value = 1
        await Timer(SETTLE, unit="ns")
        check(self.dut, self.model, "reset release (no edge yet)")

    async def clock(self, comp, check_reset=False):
        """COMP_OUT=comp for the cycle that ends at this rising edge."""
        self.dut.COMP_OUT.value = comp
        await Timer(HALF, unit="ns")
        self.dut.CLK.value = 1
        await Timer(SETTLE, unit="ns")
        self.edges += 1
        if not check_reset:
            self.model.step(comp)
        check(self.dut, self.model, f"edge {self.edges}")
        await Timer(HALF - SETTLE, unit="ns")
        self.dut.CLK.value = 0

    def active_bit(self):
        ph = [i for i in range(N) if self.model.ring[i]]
        return N - 1 - ph[0] if ph else None

    async def convert(self, target):
        """One full conversion against an ideal DAC/comparator for `target`;
        returns the DUT's DOUT code at EOC. Decisions are computed from the
        DUT's own observed outputs, not from the model."""
        # run until a trial phase starts (idle cycle first)
        while True:
            g = read(self.dut)
            bit = next((n for n in range(N) if g[f"PH_B{n}"]), None)
            comp = 0
            if bit is not None:
                upper = sum(g[f"DOUT{n}"] << n for n in range(bit + 1, N))
                comp = closed_loop_comp(target, upper, bit)
            await self.clock(comp)
            if read(self.dut)["PH_EOC"]:
                break
        g = read(self.dut)
        return sum(g[f"DOUT{n}"] << n for n in range(N))


@cocotb.test()
async def reset_state(dut):
    """Power-up reset: ring and register clear; idle is PH_SAMPLE, BUSY low."""
    b = Bench(dut)
    await b.reset(3)
    g = read(dut)
    assert g["PH_SAMPLE"] == 1 and g["BUSY"] == 0
    assert all(g[k] == 0 for k in g if k.startswith(("PH_B", "DOUT")) or k == "PH_EOC")


@cocotb.test()
async def walking_one_phase_sequence(dut):
    """Reset release -> B9, B8 ... B0, EOC, one idle cycle, repeat (period 12),
    with COMP_OUT held low so the register trace is trivially all-zero."""
    b = Bench(dut)
    await b.reset()
    seq = []
    for _ in range(3 * (N + 2)):
        await b.clock(0)
        g = read(dut)
        seq.append([k for k in g if k.startswith("PH_B") or k == "PH_EOC" if g[k]])
    order = [f"PH_B{n}" for n in range(N - 1, -1, -1)] + ["PH_EOC"]
    for rep in range(3):
        base = rep * (N + 2)
        assert seq[base:base + N + 1] == [[p] for p in order], f"rep {rep}: {seq[base:base+N+1]}"
        assert seq[base + N + 1] == [], "idle cycle must have no phase high"


@cocotb.test()
async def code_all_ones(dut):
    """COMP_OUT held high for the whole conversion -> DOUT = 0x3FF."""
    b = Bench(dut)
    await b.reset()
    for _ in range(N + 3):
        await b.clock(1)
    assert b.model.code() == 0x3FF
    g = read(dut)
    assert sum(g[f"DOUT{n}"] << n for n in range(N)) == 0x3FF


@cocotb.test()
async def code_all_zeros(dut):
    """COMP_OUT held low after a full-scale conversion -> every bit is
    overwritten with 0 (no stale-bit retention across conversions)."""
    b = Bench(dut)
    await b.reset()
    for _ in range(N + 3):
        await b.clock(1)
    assert b.model.code() == 0x3FF
    for _ in range(N + 3):
        await b.clock(0)
    assert b.model.code() == 0
    g = read(dut)
    assert sum(g[f"DOUT{n}"] << n for n in range(N)) == 0


@cocotb.test()
async def codes_from_spice_campaign(dut):
    """Closed-loop conversions of the four codes the SPICE campaign drove
    (811, 212, 682, 341), back to back with no reset between them."""
    b = Bench(dut)
    await b.reset()
    for target in (811, 212, 682, 341):
        got = await b.convert(target)
        assert got == target, f"target {target}: DUT DOUT {got}"


@cocotb.test()
async def closed_loop_every_code(dut):
    """All 1024 codes in ascending order without reset: the register must
    recover each exactly, so a stale bit from the previous code cannot leak."""
    b = Bench(dut)
    await b.reset()
    for target in range(1 << N):
        got = await b.convert(target)
        assert got == target, f"target {target}: DUT DOUT {got}"


@cocotb.test()
async def mid_conversion_reset_every_phase(dut):
    """Assert RST_B asynchronously (between edges) while each of the 12
    sequencer states is active, with a partly built register: all outputs
    clear immediately, stay clear over clock edges while held, and after
    release a fresh conversion is bit-exact and correct."""
    for state in range(N + 2):
        b = Bench(dut)
        await b.reset()
        await b.clock(0)  # leave idle -> B9
        # advance to the requested state with alternating decisions
        for k in range(state):
            await b.clock(k & 1)
        pre = read(dut)
        # asynchronous assertion in the middle of the low phase
        await Timer(2, unit="ns")
        dut.RST_B.value = 0
        b.model.reset()
        await Timer(SETTLE, unit="ns")
        check(dut, b.model, f"state {state}: async reset (pre={pre})")
        assert read(dut)["BUSY"] == 0 and read(dut)["PH_SAMPLE"] == 1
        for _ in range(3):  # held in reset across edges, COMP_OUT toggling
            await b.clock(1, check_reset=True)
        dut.RST_B.value = 1
        await Timer(SETTLE, unit="ns")
        check(dut, b.model, f"state {state}: release")
        got = await b.convert(0x2A5)
        assert got == 0x2A5, f"state {state}: post-reset conversion read {got:#x}"


@cocotb.test()
async def randomized_lockstep(dut):
    """Seeded random COMP_OUT and random asynchronous resets, lockstep with
    the model on every output at every edge (4000 edges)."""
    rng = random.Random(0x5A12)
    b = Bench(dut)
    await b.reset()
    for _ in range(4000):
        if rng.random() < 0.01:
            await Timer(2, unit="ns")
            dut.RST_B.value = 0
            b.model.reset()
            await Timer(SETTLE, unit="ns")
            check(dut, b.model, "random async reset")
            for _ in range(rng.randint(1, 3)):
                await b.clock(rng.getrandbits(1), check_reset=True)
            dut.RST_B.value = 1
            await Timer(SETTLE, unit="ns")
        await b.clock(rng.getrandbits(1))

"""Bit-exact gate-level regression for the top_glue macro against
sar_ref.glue(). Purely combinational: the DR-008 decision-directed SELp/SELn
drive and offset-binary recode, the DR-009 dummy load and half-LSB enable
pair, and the comparator-clock inverter.

The first two tests sweep the WHOLE input space that matters
(2^10 DOUT x PH_B9 x BUSY x OUTN_NC x CLK), so the all-ones and all-zeros
codes are inside the exhaustive sweep as well as having their own named test.
"""
import cocotb
from cocotb.triggers import Timer

from sar_ref import N, adc_code, glue

IN_BITS = [f"DOUT{n}" for n in range(N)]
OUT_NAMES = list(glue(0, 0, 0, 0, 0))


async def apply(dut, dout, ph_b9, busy, outn, clk):
    for n in range(N):
        getattr(dut, f"DOUT{n}").value = (dout >> n) & 1
    dut.PH_B9.value = ph_b9
    dut.BUSY.value = busy
    dut.OUTN_NC.value = outn
    dut.CLK.value = clk
    await Timer(1, unit="ns")


def compare(dut, dout, ph_b9, busy, outn, clk):
    want = glue(dout, ph_b9, busy, outn, clk)
    got = {}
    for k in OUT_NAMES:
        v = getattr(dut, k).value
        got[k] = int(v) if v.is_resolvable else "x"
    bad = {k: (got[k], want[k]) for k in want if got[k] != want[k]}
    assert not bad, f"in=(dout={dout:#05x} ph_b9={ph_b9} busy={busy} outn={outn} clk={clk}) (dut, ref): {bad}"
    return got


@cocotb.test()
async def exhaustive_data_path(dut):
    """Every DOUT code (1024), PH_B9/BUSY/OUTN_NC all 8 combinations, CLK low."""
    for dout in range(1 << N):
        for ctl in range(8):
            args = (dout, ctl & 1, (ctl >> 1) & 1, (ctl >> 2) & 1, 0)
            await apply(dut, *args)
            compare(dut, *args)


@cocotb.test()
async def clock_inverter_both_polarities(dut):
    """CLKN = NOT(CLK) for both CLK values across a spread of input states."""
    for dout in (0x000, 0x3FF, 0x200, 0x1FF, 0x2A5, 0x155):
        for clk in (0, 1, 0, 1):
            args = (dout, 1, 1, 0, clk)
            await apply(dut, *args)
            compare(dut, *args)


@cocotb.test()
async def code_all_ones(dut):
    """DOUT=0x3FF: sign set -> every SELp asserts, no SELn, recode passes through."""
    args = (0x3FF, 0, 0, 0, 0)
    await apply(dut, *args)
    got = compare(dut, *args)
    assert all(got[f"SELp{i}"] == 1 and got[f"SELn{i}"] == 0 and got[f"ADCOUT{i}"] == 1 for i in range(N - 1))
    assert adc_code(0x3FF) == 0x3FF


@cocotb.test()
async def code_all_zeros(dut):
    """DOUT=0: sign clear, no switch asserts on either side, recode inverts
    the (all-zero) magnitude to all ones -- DR-008's ones'-complement rule."""
    args = (0x000, 0, 0, 0, 0)
    await apply(dut, *args)
    got = compare(dut, *args)
    assert all(got[f"SELp{i}"] == 0 and got[f"SELn{i}"] == 0 and got[f"ADCOUT{i}"] == 1 for i in range(N - 1))


@cocotb.test()
async def sign_branch_codes_from_spice_campaign(dut):
    """811, 212, 682, 341 (the SPICE campaign's codes): sign branch, single
    active side and recoded magnitude, against the DR-008 definitions."""
    for code in (811, 212, 682, 341):
        args = (code, 0, 1, 0, 0)
        await apply(dut, *args)
        got = compare(dut, *args)
        d9 = code >> 9
        side_off = "SELn" if d9 else "SELp"
        assert all(got[f"{side_off}{i}"] == 0 for i in range(N - 1)), code
        recoded = sum(got[f"ADCOUT{i}"] << i for i in range(N - 1))
        assert recoded == ((code & 0x1FF) if d9 else (~code & 0x1FF)), code


@cocotb.test()
async def dr009_enable_pair(dut):
    """HALF_LSB_EN = BUSY AND NOT(PH_B9), HALF_LSB_ENN its complement, for all
    four (BUSY, PH_B9) states, independent of the data code."""
    for dout in (0x000, 0x3FF, 0x155):
        for busy in (0, 1):
            for ph_b9 in (0, 1):
                args = (dout, ph_b9, busy, 0, 0)
                await apply(dut, *args)
                got = compare(dut, *args)
                assert got["HALF_LSB_EN"] == int(busy and not ph_b9)
                assert got["HALF_LSB_ENN"] == 1 - got["HALF_LSB_EN"]

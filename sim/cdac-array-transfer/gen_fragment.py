#!/usr/bin/env python3
"""Programmatic generator for the CDAC array transfer-characteristic
testbench fragment -- issue #29's Monte Carlo extension of #53's hand-
authored `testbench/tb_cdac_array_transfer.spice`.

WHY A GENERATOR, NOT MORE HAND-AUTHORED TEXT. #53's fragment hand-writes one
"code copy" block (27 device/source lines per side, two sides per code) for
each of 5 representative codes. Issue #29 needs many more codes -- a proper
INL/DNL Monte-Carlo campaign needs code-to-code (not just quartile-spaced)
coverage at the major-carry transitions, where a binary-weighted CDAC's worst
DNL structurally occurs -- and hand-authoring dozens of copies of the same
27-line block is exactly the kind of mechanical duplication a generator
should own instead. This module reproduces the SAME per-bit unit-cell
pattern #53's fragment uses, verified byte-for-byte against that
hand-authored file for its own 5 codes (see
sim/tests/test_cdac_fragment_gen.py) before being trusted for any other code
list -- so a bug in the generator cannot silently diverge from the
hand-verified pattern without failing that test first.

PATTERN (read off tb_cdac_array_transfer.spice's own text): for a "side" at
`side_code` (the code driving that side -- P side uses `code` directly, N
side uses its 9-bit complement `511-code`), bit position `i` (0..8, lsb
first, weight `2**i`):
  - bit==0: the pass-gate pair's gate is tied STATICALLY to `vdd` (nfet
    permanently selects vrefn, pfet permanently off) -- no Vsel source line.
  - bit==1: a `Vsel_<code><side><i>` pwl source (high before the shared
    t=1n reset release, low after) drives the gate, switching that unit
    cell's bottom plate from vrefn (baseline) to vrefp at reset release.
Every side additionally gets one non-switching MF=1 termination cap tied to
vrefn, plus the shared ideal reset switch + a 1T DC leak resistor to vcm
(both testbench-only, per #53's own header note).
"""

from __future__ import annotations

WEIGHTS = [1, 2, 4, 8, 16, 32, 64, 128, 256]  # bit i (lsb-first) -> MF


def gen_side(code: int, side: str, side_code: int) -> str:
    """Emit one side ('p' or 'n') of one code's array copy. `side_code` is
    the 9-bit value actually driving this side's bits (== `code` for side
    'p', == `511 - code` for side 'n', by construction of the differential
    mirrored-drive convention #53's fragment documents)."""
    bits = [(side_code >> i) & 1 for i in range(9)]
    side_label = "P" if side == "p" else "N"
    lines = [f"* ---- code={code} side={side_label} (side_code={side_code}, bits lsb-first={bits})"]
    for i in range(9):
        bit = bits[i]
        wt = WEIGHTS[i]
        cname = f"bot_{code}{side}{i}"
        top = f"top_{code}{side}"
        cap = f"Xc_{code}{side}{i}  {cname} {top}   sky130_fd_pr__cap_mim_m3_1 W=1.8988 L=1.8988 MF={wt} m={wt}"
        if bit == 0:
            lines.append(cap)
            lines.append(f"Xn_{code}{side}{i}  {cname} vdd vrefn vss sky130_fd_pr__nfet_01v8 L=0.15 W=1 nf=1")
            lines.append(f"Xp_{code}{side}{i}  {cname} vdd vrefp vdd  sky130_fd_pr__pfet_01v8 L=0.15 W=2 nf=1")
        else:
            selnode = f"sel_{code}{side}{i}"
            lines.append(f"Vsel_{code}{side}{i} {selnode} 0 pwl(0 {{vdd_val}} 0.9n {{vdd_val}} 1.1n 0 500n 0)")
            lines.append(cap)
            lines.append(f"Xn_{code}{side}{i}  {cname} {selnode} vrefn vss sky130_fd_pr__nfet_01v8 L=0.15 W=1 nf=1")
            lines.append(f"Xp_{code}{side}{i}  {cname} {selnode} vrefp vdd  sky130_fd_pr__pfet_01v8 L=0.15 W=2 nf=1")
    lines.append(f"Xterm_{code}{side} vrefn top_{code}{side} sky130_fd_pr__cap_mim_m3_1 W=1.8988 L=1.8988 MF=1 m=1")
    lines.append(f"Sreset_{code}{side} top_{code}{side} vcm nctrl_reset 0 SWMOD")
    lines.append(f"Rdc_{code}{side} top_{code}{side} vcm 1T")
    return "\n".join(lines)


def gen_code_block(code: int) -> str:
    """Both sides (P driven by `code`, N driven by its complement
    `511-code`) for one code, blank-line separated exactly as the
    hand-authored fragment does between code blocks."""
    p = gen_side(code, "p", code)
    n = gen_side(code, "n", 511 - code)
    return p + "\n\n" + n


HEADER = """* tb_cdac_array_transfer -- CDAC array DAC transfer characteristic (issue #53).
*
* Netlist FRAGMENT. sim/cdac-array-transfer/run_transfer.py supplies the
* .lib corner section, .temp, .param vdd_val, and the .control/.measure
* block; this fragment is transient-analysis-only (the harness's generic
* run_corners.py/tb.json path only emits `.control op`, which cannot
* express charge redistribution on a floating capacitor network -- see
* spec/decision-records/DR-005-cdac-array-design.md and
* sim/cdac-array-transfer/README.md for why this experiment ships its own
* small runner instead of reusing run_corners.py directly).
*
* METHOD. Each of the 5 representative 9-bit sub-array codes below (0,
* 128, 256, 384, 511 -- spanning the code range; the omitted 507 codes
* are, by construction, the same cap+2-switch unit-cell pattern per bit,
* per design/cdac/cdac_array.sch) gets its OWN copy of the array, on
* BOTH sides (P side driven with the code directly, N side driven with
* its 9-bit complement, 511-code, i.e. the standard differential-CDAC
* mirrored drive) so all 5 points are measured in ONE transient run.
* Every copy shares one reset event at t=1n: an IDEAL testbench-only
* switch (NOT part of the design source -- issue #53's acceptance
* criteria explicitly allow an ideal switch model for this exact
* purpose) pins each copy's top-plate node to Vcm while every bit's
* bottom plate sits at its pre-code baseline (all bits = 0, i.e. all
* bottom plates at VREFN); at t=1n the ideal switch opens and, in the
* SAME instant, every bit position whose target code bit is 1 transitions
* its REAL nfet_01v8/pfet_01v8 switch pair (design/cdac/cdac_unit_cell.sch's
* pattern) from VREFN to VREFP. Bit positions whose target bit is 0 never
* move (their SEL gate is tied directly to the vdd rail throughout, since
* SEL=1 is this array's 'bit=0 -> VREFN' state -- see
* design/cdac/cdac_unit_cell.sch header). The resulting top-plate voltage
* at t=500n (>>RC of any path active in this circuit) is the array's DAC
* output for that code, read via .measure.
*
* IDEAL EXPECTED VALUE (derived from charge conservation, VREFN=0,
* Vcm=vdd_val/2, C_total=512 unit caps/side per DR-003 Item 3):
*   vdiff_ideal(code) = vdd_val * (2*code - 511) / 512
* computed independently in Python by run_transfer.py and compared
* against the measured vdiff_<code> below.

Vrefp vrefp 0 dc {vdd_val}
Vrefn vrefn 0 dc 0
Vdd    vdd   0 dc {vdd_val}
Vss    vss   0 dc 0
Vcm    vcm   0 dc {vdd_val/2}

* Shared ideal reset switch control (testbench-only, NOT a design
* device): high (closed) before t=1n pins every top_<code><side> node to
* Vcm; low (open) after t=1n lets each float and redistribute charge as
* its bit-1 positions step to VREFP.
Vctrl_reset nctrl_reset 0 pwl(0 {vdd_val} 0.9n {vdd_val} 1.1n 0 500n 0)
.model SWMOD SW(Ron=1 Roff=1e12 Vt={vdd_val/2} Vh=0.05)
"""


def gen_fragment(codes: list[int]) -> str:
    """Full fragment text (header + one block per code, in the order
    given), matching #53's hand-authored file's own formatting exactly
    (verified for codes=[0,128,256,384,511] by
    sim/tests/test_cdac_fragment_gen.py)."""
    parts = [HEADER.rstrip("\n")]
    for code in codes:
        parts.append("")
        parts.append(gen_code_block(code))
    return "\n".join(parts) + "\n\n"


if __name__ == "__main__":
    import sys
    from pathlib import Path

    codes = [0, 128, 256, 384, 511]
    generated = gen_fragment(codes)
    reference = (Path(__file__).resolve().parent / "testbench" / "tb_cdac_array_transfer.spice").read_text()
    if generated == reference:
        print("OK: generator output matches tb_cdac_array_transfer.spice byte-for-byte for codes=[0,128,256,384,511]")
        sys.exit(0)
    else:
        print("MISMATCH vs tb_cdac_array_transfer.spice")
        import difflib
        diff = difflib.unified_diff(reference.splitlines(), generated.splitlines(), lineterm="")
        for line in list(diff)[:80]:
            print(line)
        sys.exit(1)

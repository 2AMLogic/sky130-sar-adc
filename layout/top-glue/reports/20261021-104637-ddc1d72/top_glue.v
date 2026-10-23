// Structural gate-level netlist for the SAR ADC's top-level standard-cell
// glue bank -- the 33 `sky130_fd_sc_hd` instances `design/sar_adc_top.spice`
// adds directly at the integration level, inside no sub-block.
//
// Hand-derived 1:1 from `design/sar_adc_top.spice`'s own instance lines
// (`xinv_clkcap`, `xinv_dout9n`, `xand_seln0..8`, `xand_selp0..8`,
// `xxor_code0..8`, `xdum_mux_n`, `xdum_xnor_n`, `xand_halflsb`,
// `xinv_halflsb`) as that file stands -- NOT from issue #56's superseded
// `xinv_seln0..8` inverter bank, which `spec/decision-records/
// DR-008-cdac-top-level-switching-polarity.md` retired on 2026-09-11 and
// which no longer appears in the netlist at all. Each instance's pin map
// below is the positional-to-named translation of that line against the
// PDK's own `.SUBCKT` pin order
// (`libs.ref/sky130_fd_sc_hd/cdl/sky130_fd_sc_hd.cdl`):
//
//   inv_1    A VGND VNB VPB VPWR Y
//   and2_1   A B VGND VNB VPB VPWR X
//   and2b_1  A_N B VGND VNB VPB VPWR X
//   mux2_1   A0 A1 S VGND VNB VPB VPWR X
//   xnor2_1  A B VGND VNB VPB VPWR Y
//   xor2_1   A B VGND VNB VPB VPWR X
//
// What each group is for, and which decision record owns it:
//
//   * `xand_seln<i>` / `xand_selp<i>` (18 x and2_1) -- DR-008's
//     decision-directed bottom-plate drive. `SELp<i> = DOUT9 AND DOUT<i>`,
//     `SELn<i> = DOUT9N AND DOUT<i>`: only the side the sign bit selects
//     moves on a bit trial, where issue #56 drove both sides
//     unconditionally and complementarily (`SELp<i> = DOUT<i>`,
//     `SELn<i> = NOT(DOUT<i>)`). The polarity is load-bearing and is the one
//     thing a self-consistent LVS compare cannot check -- see README.md.
//   * `xinv_dout9n` (inv_1) -- `DOUT9N = NOT(DOUT9)`, the sign-bit
//     complement both the `SELn<i>` AND gates and the readout recode need.
//     Internal to this macro: nothing outside it consumes `DOUT9N`.
//   * `xxor_code<i>` (9 x xor2_1) -- the read-only output recode,
//     `ADCOUT<i> = DOUT<i> XOR DOUT9N`, which turns DR-008's
//     sign-magnitude register content back into the offset-binary code.
//   * `xdum_mux_n` (mux2_1) + `xdum_xnor_n` (xnor2_1) -- DR-009 item 1's
//     matched dummy load on the comparator's `OUTN`: the same two cell types
//     on the same two pin positions `COMP_OUT` drives inside `xseq`, with
//     their other inputs on the same nets the real cells see, so the
//     state-dependent pin capacitance tracks cycle by cycle. Both outputs
//     are deliberate no-connects.
//   * `xand_halflsb` (and2b_1) + `xinv_halflsb` (inv_1) -- DR-009 item 2's
//     half-LSB offset enable, `HALF_LSB_EN = BUSY AND NOT(PH_B9)`, and its
//     complement. Both leave this macro: they gate the offset network's own
//     switch devices, which are `sky130_fd_pr` primitives and therefore live
//     outside this standard-cell macro (see README.md "What is NOT here").
//   * `xinv_clkcap` (inv_1) -- `CLKN = NOT(CLK)`, the comparator's own clock
//     polarity (issue #264).
//
// `VPWR`/`VGND` are deliberately NOT declared as module ports: `klt
// place-and-route`'s own `power` block names them (`requests/
// place-and-route.json`) and `pdngen` builds the real PDN from every cell's
// own `VPWR`/`VPB` and `VGND`/`VNB` pins. Same convention as
// `layout/sar-sequencer/netlist/sar_sequencer.v` and the superseded
// `layout/seln-inverters/netlist/seln_inverters.v`.
//
// Purely combinational -- no clock, no state, nothing for `klt synthesize`
// (RTL->gates) to usefully do, so this hand-written structural netlist goes
// straight to `klt place-and-route` exactly as `sar_sequencer.v` does.
//
// Clean room: transliterated from this repo's own captured schematic
// netlist and its own decision records, not from any other party's SAR ADC
// implementation.
module top_glue (
    CLK, DOUT9, DOUT8, DOUT7, DOUT6, DOUT5, DOUT4, DOUT3, DOUT2, DOUT1,
    DOUT0, PH_B9, BUSY, OUTN_NC,
    CLKN,
    SELp8, SELp7, SELp6, SELp5, SELp4, SELp3, SELp2, SELp1, SELp0,
    SELn8, SELn7, SELn6, SELn5, SELn4, SELn3, SELn2, SELn1, SELn0,
    ADCOUT8, ADCOUT7, ADCOUT6, ADCOUT5, ADCOUT4, ADCOUT3, ADCOUT2,
    ADCOUT1, ADCOUT0,
    HALF_LSB_EN, HALF_LSB_ENN, DUMLOAD_MUX_NC, DUMLOAD_XNOR_NC
);
  input  CLK, DOUT9, DOUT8, DOUT7, DOUT6, DOUT5, DOUT4, DOUT3, DOUT2;
  input  DOUT1, DOUT0, PH_B9, BUSY, OUTN_NC;
  output CLKN;
  output SELp8, SELp7, SELp6, SELp5, SELp4, SELp3, SELp2, SELp1, SELp0;
  output SELn8, SELn7, SELn6, SELn5, SELn4, SELn3, SELn2, SELn1, SELn0;
  output ADCOUT8, ADCOUT7, ADCOUT6, ADCOUT5, ADCOUT4, ADCOUT3, ADCOUT2;
  output ADCOUT1, ADCOUT0;
  output HALF_LSB_EN, HALF_LSB_ENN, DUMLOAD_MUX_NC, DUMLOAD_XNOR_NC;

  wire DOUT9N;

  // --- comparator clock polarity (issue #264) ------------------------------
  sky130_fd_sc_hd__inv_1 xinv_clkcap (.A(CLK), .Y(CLKN));

  // --- sign-bit complement -------------------------------------------------
  sky130_fd_sc_hd__inv_1 xinv_dout9n (.A(DOUT9), .Y(DOUT9N));

  // --- DR-008 decision-directed bottom-plate drive -------------------------
  // SELn<i> = DOUT<i> AND DOUT9N ; SELp<i> = DOUT9 AND DOUT<i>
  sky130_fd_sc_hd__and2_1 xand_seln0 (.A(DOUT0), .B(DOUT9N), .X(SELn0));
  sky130_fd_sc_hd__and2_1 xand_selp0 (.A(DOUT9), .B(DOUT0), .X(SELp0));
  sky130_fd_sc_hd__and2_1 xand_seln1 (.A(DOUT1), .B(DOUT9N), .X(SELn1));
  sky130_fd_sc_hd__and2_1 xand_selp1 (.A(DOUT9), .B(DOUT1), .X(SELp1));
  sky130_fd_sc_hd__and2_1 xand_seln2 (.A(DOUT2), .B(DOUT9N), .X(SELn2));
  sky130_fd_sc_hd__and2_1 xand_selp2 (.A(DOUT9), .B(DOUT2), .X(SELp2));
  sky130_fd_sc_hd__and2_1 xand_seln3 (.A(DOUT3), .B(DOUT9N), .X(SELn3));
  sky130_fd_sc_hd__and2_1 xand_selp3 (.A(DOUT9), .B(DOUT3), .X(SELp3));
  sky130_fd_sc_hd__and2_1 xand_seln4 (.A(DOUT4), .B(DOUT9N), .X(SELn4));
  sky130_fd_sc_hd__and2_1 xand_selp4 (.A(DOUT9), .B(DOUT4), .X(SELp4));
  sky130_fd_sc_hd__and2_1 xand_seln5 (.A(DOUT5), .B(DOUT9N), .X(SELn5));
  sky130_fd_sc_hd__and2_1 xand_selp5 (.A(DOUT9), .B(DOUT5), .X(SELp5));
  sky130_fd_sc_hd__and2_1 xand_seln6 (.A(DOUT6), .B(DOUT9N), .X(SELn6));
  sky130_fd_sc_hd__and2_1 xand_selp6 (.A(DOUT9), .B(DOUT6), .X(SELp6));
  sky130_fd_sc_hd__and2_1 xand_seln7 (.A(DOUT7), .B(DOUT9N), .X(SELn7));
  sky130_fd_sc_hd__and2_1 xand_selp7 (.A(DOUT9), .B(DOUT7), .X(SELp7));
  sky130_fd_sc_hd__and2_1 xand_seln8 (.A(DOUT8), .B(DOUT9N), .X(SELn8));
  sky130_fd_sc_hd__and2_1 xand_selp8 (.A(DOUT9), .B(DOUT8), .X(SELp8));

  // --- DR-008 readout recode: ADCOUT<i> = DOUT<i> XOR DOUT9N ---------------
  sky130_fd_sc_hd__xor2_1 xxor_code0 (.A(DOUT0), .B(DOUT9N), .X(ADCOUT0));
  sky130_fd_sc_hd__xor2_1 xxor_code1 (.A(DOUT1), .B(DOUT9N), .X(ADCOUT1));
  sky130_fd_sc_hd__xor2_1 xxor_code2 (.A(DOUT2), .B(DOUT9N), .X(ADCOUT2));
  sky130_fd_sc_hd__xor2_1 xxor_code3 (.A(DOUT3), .B(DOUT9N), .X(ADCOUT3));
  sky130_fd_sc_hd__xor2_1 xxor_code4 (.A(DOUT4), .B(DOUT9N), .X(ADCOUT4));
  sky130_fd_sc_hd__xor2_1 xxor_code5 (.A(DOUT5), .B(DOUT9N), .X(ADCOUT5));
  sky130_fd_sc_hd__xor2_1 xxor_code6 (.A(DOUT6), .B(DOUT9N), .X(ADCOUT6));
  sky130_fd_sc_hd__xor2_1 xxor_code7 (.A(DOUT7), .B(DOUT9N), .X(ADCOUT7));
  sky130_fd_sc_hd__xor2_1 xxor_code8 (.A(DOUT8), .B(DOUT9N), .X(ADCOUT8));

  // --- DR-009 item 1: matched dummy load on the comparator's OUTN ----------
  sky130_fd_sc_hd__mux2_1 xdum_mux_n (
      .A0(DOUT9), .A1(OUTN_NC), .S(PH_B9), .X(DUMLOAD_MUX_NC));
  sky130_fd_sc_hd__xnor2_1 xdum_xnor_n (
      .A(OUTN_NC), .B(DOUT9), .Y(DUMLOAD_XNOR_NC));

  // --- DR-009 item 2: half-LSB offset enable ------------------------------
  // HALF_LSB_EN = BUSY AND NOT(PH_B9) -- and2b_1's A_N is the inverted input.
  sky130_fd_sc_hd__and2b_1 xand_halflsb (
      .A_N(PH_B9), .B(BUSY), .X(HALF_LSB_EN));
  sky130_fd_sc_hd__inv_1 xinv_halflsb (.A(HALF_LSB_EN), .Y(HALF_LSB_ENN));
endmodule

// Structural gate-level netlist for the SAR logic/sequencer, hand-derived
// 1:1 from design/sar_sequencer.sch (the already-captured and behaviorally
// verified schematic -- see sim/sar-sequencer-behavioral/ for its own
// testbench). Every instance/net below matches that schematic's own
// extracted netlist exactly; compare against a snapshot in
// sim/sar-sequencer-behavioral/netlist-snapshots/*.spice, which this file
// was transliterated from (SPICE X-card connectivity -> Verilog module
// instantiation port-for-port), not re-derived by RTL synthesis. See
// layout/sar-sequencer/README.md for why `klt synthesize` (RTL->gates via
// Yosys/ABC) was deliberately skipped for this sub-block in favor of feeding
// this hand-authored netlist straight to `klt place-and-route`.
//
// Clean room: transliterated from this repo's own already-reviewed
// schematic and its own extracted netlist snapshot, not from any reference
// SAR ADC implementation.
module sar_sequencer (
    CLK, RST_B, COMP_OUT,
    PH_B9, PH_B8, PH_B7, PH_B6, PH_B5, PH_B4, PH_B3, PH_B2, PH_B1, PH_B0,
    PH_EOC, PH_SAMPLE, BUSY,
    DOUT9, DOUT8, DOUT7, DOUT6, DOUT5, DOUT4, DOUT3, DOUT2, DOUT1, DOUT0
);
  input  CLK, RST_B, COMP_OUT;
  output PH_B9, PH_B8, PH_B7, PH_B6, PH_B5, PH_B4, PH_B3, PH_B2, PH_B1, PH_B0;
  output PH_EOC, PH_SAMPLE, BUSY;
  output DOUT9, DOUT8, DOUT7, DOUT6, DOUT5, DOUT4, DOUT3, DOUT2, DOUT1, DOUT0;

  wire MUXOUT9, MUXOUT8, MUXOUT7, MUXOUT6, MUXOUT5;
  wire MUXOUT4, MUXOUT3, MUXOUT2, MUXOUT1, MUXOUT0;
  wire ORG1, ORG2, ORG3;

  // (N+1)-stage walking-one ring sequencer: PH_SAMPLE self-injects a token
  // into the ring while idle; each stage's D is the previous stage's Q.
  sky130_fd_sc_hd__dfrtp_1 xringb9  (.CLK(CLK), .D(PH_SAMPLE), .RESET_B(RST_B), .Q(PH_B9));
  sky130_fd_sc_hd__dfrtp_1 xringb8  (.CLK(CLK), .D(PH_B9),     .RESET_B(RST_B), .Q(PH_B8));
  sky130_fd_sc_hd__dfrtp_1 xringb7  (.CLK(CLK), .D(PH_B8),     .RESET_B(RST_B), .Q(PH_B7));
  sky130_fd_sc_hd__dfrtp_1 xringb6  (.CLK(CLK), .D(PH_B7),     .RESET_B(RST_B), .Q(PH_B6));
  sky130_fd_sc_hd__dfrtp_1 xringb5  (.CLK(CLK), .D(PH_B6),     .RESET_B(RST_B), .Q(PH_B5));
  sky130_fd_sc_hd__dfrtp_1 xringb4  (.CLK(CLK), .D(PH_B5),     .RESET_B(RST_B), .Q(PH_B4));
  sky130_fd_sc_hd__dfrtp_1 xringb3  (.CLK(CLK), .D(PH_B4),     .RESET_B(RST_B), .Q(PH_B3));
  sky130_fd_sc_hd__dfrtp_1 xringb2  (.CLK(CLK), .D(PH_B3),     .RESET_B(RST_B), .Q(PH_B2));
  sky130_fd_sc_hd__dfrtp_1 xringb1  (.CLK(CLK), .D(PH_B2),     .RESET_B(RST_B), .Q(PH_B1));
  sky130_fd_sc_hd__dfrtp_1 xringb0  (.CLK(CLK), .D(PH_B1),     .RESET_B(RST_B), .Q(PH_B0));
  sky130_fd_sc_hd__dfrtp_1 xringeoc (.CLK(CLK), .D(PH_B0),     .RESET_B(RST_B), .Q(PH_EOC));

  // BUSY = OR of every phase signal; PH_SAMPLE = NOT(BUSY) (idle/sample
  // phase, and the ring's own self-start injection point).
  sky130_fd_sc_hd__or4_1 xor_g1 (.A(PH_B9), .B(PH_B8), .C(PH_B7), .D(PH_B6), .X(ORG1));
  sky130_fd_sc_hd__or4_1 xor_g2 (.A(PH_B5), .B(PH_B4), .C(PH_B3), .D(PH_B2), .X(ORG2));
  sky130_fd_sc_hd__or3_1 xor_g3 (.A(PH_B1), .B(PH_B0), .C(PH_EOC), .X(ORG3));
  sky130_fd_sc_hd__or3_1 xor_busy (.A(ORG1), .B(ORG2), .C(ORG3), .X(BUSY));
  sky130_fd_sc_hd__inv_1 xinv_sample (.A(BUSY), .Y(PH_SAMPLE));

  // 10-bit SAR register: mux2_1 captures COMP_OUT during its own bit-trial
  // phase (S=PH_Bn), holds the current DOUTn (A0) otherwise; dfrtp_1
  // registers the mux output on CLK.
  sky130_fd_sc_hd__mux2_1 xmux9 (.A0(DOUT9), .A1(COMP_OUT), .S(PH_B9), .X(MUXOUT9));
  sky130_fd_sc_hd__dfrtp_1 xbreg9 (.CLK(CLK), .D(MUXOUT9), .RESET_B(RST_B), .Q(DOUT9));
  sky130_fd_sc_hd__mux2_1 xmux8 (.A0(DOUT8), .A1(COMP_OUT), .S(PH_B8), .X(MUXOUT8));
  sky130_fd_sc_hd__dfrtp_1 xbreg8 (.CLK(CLK), .D(MUXOUT8), .RESET_B(RST_B), .Q(DOUT8));
  sky130_fd_sc_hd__mux2_1 xmux7 (.A0(DOUT7), .A1(COMP_OUT), .S(PH_B7), .X(MUXOUT7));
  sky130_fd_sc_hd__dfrtp_1 xbreg7 (.CLK(CLK), .D(MUXOUT7), .RESET_B(RST_B), .Q(DOUT7));
  sky130_fd_sc_hd__mux2_1 xmux6 (.A0(DOUT6), .A1(COMP_OUT), .S(PH_B6), .X(MUXOUT6));
  sky130_fd_sc_hd__dfrtp_1 xbreg6 (.CLK(CLK), .D(MUXOUT6), .RESET_B(RST_B), .Q(DOUT6));
  sky130_fd_sc_hd__mux2_1 xmux5 (.A0(DOUT5), .A1(COMP_OUT), .S(PH_B5), .X(MUXOUT5));
  sky130_fd_sc_hd__dfrtp_1 xbreg5 (.CLK(CLK), .D(MUXOUT5), .RESET_B(RST_B), .Q(DOUT5));
  sky130_fd_sc_hd__mux2_1 xmux4 (.A0(DOUT4), .A1(COMP_OUT), .S(PH_B4), .X(MUXOUT4));
  sky130_fd_sc_hd__dfrtp_1 xbreg4 (.CLK(CLK), .D(MUXOUT4), .RESET_B(RST_B), .Q(DOUT4));
  sky130_fd_sc_hd__mux2_1 xmux3 (.A0(DOUT3), .A1(COMP_OUT), .S(PH_B3), .X(MUXOUT3));
  sky130_fd_sc_hd__dfrtp_1 xbreg3 (.CLK(CLK), .D(MUXOUT3), .RESET_B(RST_B), .Q(DOUT3));
  sky130_fd_sc_hd__mux2_1 xmux2 (.A0(DOUT2), .A1(COMP_OUT), .S(PH_B2), .X(MUXOUT2));
  sky130_fd_sc_hd__dfrtp_1 xbreg2 (.CLK(CLK), .D(MUXOUT2), .RESET_B(RST_B), .Q(DOUT2));
  sky130_fd_sc_hd__mux2_1 xmux1 (.A0(DOUT1), .A1(COMP_OUT), .S(PH_B1), .X(MUXOUT1));
  sky130_fd_sc_hd__dfrtp_1 xbreg1 (.CLK(CLK), .D(MUXOUT1), .RESET_B(RST_B), .Q(DOUT1));
  sky130_fd_sc_hd__mux2_1 xmux0 (.A0(DOUT0), .A1(COMP_OUT), .S(PH_B0), .X(MUXOUT0));
  sky130_fd_sc_hd__dfrtp_1 xbreg0 (.CLK(CLK), .D(MUXOUT0), .RESET_B(RST_B), .Q(DOUT0));

endmodule

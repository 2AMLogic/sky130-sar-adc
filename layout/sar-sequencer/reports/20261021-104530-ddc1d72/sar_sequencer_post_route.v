module sar_sequencer (BUSY,
    CLK,
    COMP_OUT,
    DOUT0,
    DOUT1,
    DOUT2,
    DOUT3,
    DOUT4,
    DOUT5,
    DOUT6,
    DOUT7,
    DOUT8,
    DOUT9,
    PH_B0,
    PH_B1,
    PH_B2,
    PH_B3,
    PH_B4,
    PH_B5,
    PH_B6,
    PH_B7,
    PH_B8,
    PH_B9,
    PH_EOC,
    PH_SAMPLE,
    RST_B);
 output BUSY;
 input CLK;
 input COMP_OUT;
 output DOUT0;
 output DOUT1;
 output DOUT2;
 output DOUT3;
 output DOUT4;
 output DOUT5;
 output DOUT6;
 output DOUT7;
 output DOUT8;
 output DOUT9;
 output PH_B0;
 output PH_B1;
 output PH_B2;
 output PH_B3;
 output PH_B4;
 output PH_B5;
 output PH_B6;
 output PH_B7;
 output PH_B8;
 output PH_B9;
 output PH_EOC;
 output PH_SAMPLE;
 input RST_B;

 wire MUXOUT0;
 wire MUXOUT1;
 wire MUXOUT2;
 wire MUXOUT3;
 wire MUXOUT4;
 wire MUXOUT5;
 wire MUXOUT6;
 wire MUXOUT7;
 wire MUXOUT8;
 wire MUXOUT9;
 wire ORG1;
 wire ORG2;
 wire ORG3;
 wire clknet_0_CLK;
 wire clknet_1_0__leaf_CLK;
 wire clknet_1_1__leaf_CLK;

 sky130_fd_sc_hd__fill_8 FILLER_0_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_0_16 ();
 sky130_fd_sc_hd__fill_4 FILLER_0_24 ();
 sky130_fd_sc_hd__fill_2 FILLER_0_28 ();
 sky130_fd_sc_hd__fill_8 FILLER_0_31 ();
 sky130_fd_sc_hd__fill_8 FILLER_0_39 ();
 sky130_fd_sc_hd__fill_8 FILLER_0_47 ();
 sky130_fd_sc_hd__fill_4 FILLER_0_55 ();
 sky130_fd_sc_hd__fill_1 FILLER_0_59 ();
 sky130_fd_sc_hd__fill_8 FILLER_0_8 ();
 sky130_fd_sc_hd__fill_2 FILLER_0_81 ();
 sky130_fd_sc_hd__fill_8 FILLER_10_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_10_31 ();
 sky130_fd_sc_hd__fill_8 FILLER_10_39 ();
 sky130_fd_sc_hd__fill_8 FILLER_10_47 ();
 sky130_fd_sc_hd__fill_1 FILLER_10_55 ();
 sky130_fd_sc_hd__fill_4 FILLER_10_76 ();
 sky130_fd_sc_hd__fill_2 FILLER_10_8 ();
 sky130_fd_sc_hd__fill_2 FILLER_10_80 ();
 sky130_fd_sc_hd__fill_1 FILLER_10_82 ();
 sky130_fd_sc_hd__fill_8 FILLER_11_0 ();
 sky130_fd_sc_hd__fill_2 FILLER_11_38 ();
 sky130_fd_sc_hd__fill_4 FILLER_11_8 ();
 sky130_fd_sc_hd__fill_2 FILLER_11_81 ();
 sky130_fd_sc_hd__fill_8 FILLER_12_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_12_31 ();
 sky130_fd_sc_hd__fill_8 FILLER_12_39 ();
 sky130_fd_sc_hd__fill_8 FILLER_12_47 ();
 sky130_fd_sc_hd__fill_4 FILLER_12_55 ();
 sky130_fd_sc_hd__fill_1 FILLER_12_59 ();
 sky130_fd_sc_hd__fill_2 FILLER_12_8 ();
 sky130_fd_sc_hd__fill_2 FILLER_12_81 ();
 sky130_fd_sc_hd__fill_8 FILLER_1_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_1_16 ();
 sky130_fd_sc_hd__fill_1 FILLER_1_24 ();
 sky130_fd_sc_hd__fill_8 FILLER_1_45 ();
 sky130_fd_sc_hd__fill_4 FILLER_1_53 ();
 sky130_fd_sc_hd__fill_2 FILLER_1_57 ();
 sky130_fd_sc_hd__fill_1 FILLER_1_59 ();
 sky130_fd_sc_hd__fill_8 FILLER_1_8 ();
 sky130_fd_sc_hd__fill_2 FILLER_1_81 ();
 sky130_fd_sc_hd__fill_8 FILLER_2_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_2_31 ();
 sky130_fd_sc_hd__fill_4 FILLER_2_39 ();
 sky130_fd_sc_hd__fill_2 FILLER_2_43 ();
 sky130_fd_sc_hd__fill_8 FILLER_2_48 ();
 sky130_fd_sc_hd__fill_1 FILLER_2_56 ();
 sky130_fd_sc_hd__fill_4 FILLER_2_77 ();
 sky130_fd_sc_hd__fill_2 FILLER_2_8 ();
 sky130_fd_sc_hd__fill_2 FILLER_2_81 ();
 sky130_fd_sc_hd__fill_8 FILLER_3_0 ();
 sky130_fd_sc_hd__fill_2 FILLER_3_16 ();
 sky130_fd_sc_hd__fill_1 FILLER_3_18 ();
 sky130_fd_sc_hd__fill_4 FILLER_3_28 ();
 sky130_fd_sc_hd__fill_1 FILLER_3_32 ();
 sky130_fd_sc_hd__fill_2 FILLER_3_42 ();
 sky130_fd_sc_hd__fill_1 FILLER_3_44 ();
 sky130_fd_sc_hd__fill_8 FILLER_3_51 ();
 sky130_fd_sc_hd__fill_1 FILLER_3_59 ();
 sky130_fd_sc_hd__fill_4 FILLER_3_79 ();
 sky130_fd_sc_hd__fill_8 FILLER_3_8 ();
 sky130_fd_sc_hd__fill_8 FILLER_4_0 ();
 sky130_fd_sc_hd__fill_2 FILLER_4_16 ();
 sky130_fd_sc_hd__fill_1 FILLER_4_18 ();
 sky130_fd_sc_hd__fill_2 FILLER_4_28 ();
 sky130_fd_sc_hd__fill_4 FILLER_4_31 ();
 sky130_fd_sc_hd__fill_1 FILLER_4_35 ();
 sky130_fd_sc_hd__fill_2 FILLER_4_56 ();
 sky130_fd_sc_hd__fill_4 FILLER_4_78 ();
 sky130_fd_sc_hd__fill_8 FILLER_4_8 ();
 sky130_fd_sc_hd__fill_1 FILLER_4_82 ();
 sky130_fd_sc_hd__fill_8 FILLER_5_0 ();
 sky130_fd_sc_hd__fill_1 FILLER_5_12 ();
 sky130_fd_sc_hd__fill_8 FILLER_5_33 ();
 sky130_fd_sc_hd__fill_8 FILLER_5_41 ();
 sky130_fd_sc_hd__fill_4 FILLER_5_49 ();
 sky130_fd_sc_hd__fill_1 FILLER_5_53 ();
 sky130_fd_sc_hd__fill_4 FILLER_5_8 ();
 sky130_fd_sc_hd__fill_2 FILLER_5_81 ();
 sky130_fd_sc_hd__fill_8 FILLER_6_0 ();
 sky130_fd_sc_hd__fill_4 FILLER_6_16 ();
 sky130_fd_sc_hd__fill_1 FILLER_6_20 ();
 sky130_fd_sc_hd__fill_4 FILLER_6_31 ();
 sky130_fd_sc_hd__fill_1 FILLER_6_35 ();
 sky130_fd_sc_hd__fill_8 FILLER_6_42 ();
 sky130_fd_sc_hd__fill_4 FILLER_6_50 ();
 sky130_fd_sc_hd__fill_1 FILLER_6_54 ();
 sky130_fd_sc_hd__fill_8 FILLER_6_75 ();
 sky130_fd_sc_hd__fill_8 FILLER_6_8 ();
 sky130_fd_sc_hd__fill_8 FILLER_7_0 ();
 sky130_fd_sc_hd__fill_1 FILLER_7_12 ();
 sky130_fd_sc_hd__fill_8 FILLER_7_33 ();
 sky130_fd_sc_hd__fill_8 FILLER_7_41 ();
 sky130_fd_sc_hd__fill_4 FILLER_7_49 ();
 sky130_fd_sc_hd__fill_1 FILLER_7_53 ();
 sky130_fd_sc_hd__fill_1 FILLER_7_61 ();
 sky130_fd_sc_hd__fill_4 FILLER_7_79 ();
 sky130_fd_sc_hd__fill_4 FILLER_7_8 ();
 sky130_fd_sc_hd__fill_8 FILLER_8_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_8_31 ();
 sky130_fd_sc_hd__fill_8 FILLER_8_39 ();
 sky130_fd_sc_hd__fill_8 FILLER_8_47 ();
 sky130_fd_sc_hd__fill_8 FILLER_8_75 ();
 sky130_fd_sc_hd__fill_2 FILLER_8_8 ();
 sky130_fd_sc_hd__fill_8 FILLER_9_0 ();
 sky130_fd_sc_hd__fill_2 FILLER_9_16 ();
 sky130_fd_sc_hd__fill_4 FILLER_9_47 ();
 sky130_fd_sc_hd__fill_1 FILLER_9_61 ();
 sky130_fd_sc_hd__fill_4 FILLER_9_76 ();
 sky130_fd_sc_hd__fill_8 FILLER_9_8 ();
 sky130_fd_sc_hd__fill_2 FILLER_9_80 ();
 sky130_fd_sc_hd__fill_1 FILLER_9_82 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_0_0 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_0_1 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_10_11 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_11_12 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_12_13 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_12_14 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_1_2 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_2_3 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_3_4 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_4_5 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_5_6 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_6_7 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_7_8 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_8_9 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_9_10 ();
 sky130_fd_sc_hd__buf_4 clkbuf_0_CLK (.A(CLK),
    .X(clknet_0_CLK));
 sky130_fd_sc_hd__buf_4 clkbuf_1_0__f_CLK (.A(clknet_0_CLK),
    .X(clknet_1_0__leaf_CLK));
 sky130_fd_sc_hd__buf_4 clkbuf_1_1__f_CLK (.A(clknet_0_CLK),
    .X(clknet_1_1__leaf_CLK));
 sky130_fd_sc_hd__inv_1 clkload0 (.A(clknet_1_0__leaf_CLK));
 sky130_fd_sc_hd__dfrtp_1 xbreg0 (.CLK(clknet_1_1__leaf_CLK),
    .D(MUXOUT0),
    .RESET_B(RST_B),
    .Q(DOUT0));
 sky130_fd_sc_hd__dfrtp_1 xbreg1 (.CLK(clknet_1_1__leaf_CLK),
    .D(MUXOUT1),
    .RESET_B(RST_B),
    .Q(DOUT1));
 sky130_fd_sc_hd__dfrtp_1 xbreg2 (.CLK(clknet_1_0__leaf_CLK),
    .D(MUXOUT2),
    .RESET_B(RST_B),
    .Q(DOUT2));
 sky130_fd_sc_hd__dfrtp_1 xbreg3 (.CLK(clknet_1_1__leaf_CLK),
    .D(MUXOUT3),
    .RESET_B(RST_B),
    .Q(DOUT3));
 sky130_fd_sc_hd__dfrtp_1 xbreg4 (.CLK(clknet_1_1__leaf_CLK),
    .D(MUXOUT4),
    .RESET_B(RST_B),
    .Q(DOUT4));
 sky130_fd_sc_hd__dfrtp_1 xbreg5 (.CLK(clknet_1_0__leaf_CLK),
    .D(MUXOUT5),
    .RESET_B(RST_B),
    .Q(DOUT5));
 sky130_fd_sc_hd__dfrtp_1 xbreg6 (.CLK(clknet_1_0__leaf_CLK),
    .D(MUXOUT6),
    .RESET_B(RST_B),
    .Q(DOUT6));
 sky130_fd_sc_hd__dfrtp_1 xbreg7 (.CLK(clknet_1_0__leaf_CLK),
    .D(MUXOUT7),
    .RESET_B(RST_B),
    .Q(DOUT7));
 sky130_fd_sc_hd__dfrtp_1 xbreg8 (.CLK(clknet_1_0__leaf_CLK),
    .D(MUXOUT8),
    .RESET_B(RST_B),
    .Q(DOUT8));
 sky130_fd_sc_hd__dfrtp_1 xbreg9 (.CLK(clknet_1_1__leaf_CLK),
    .D(MUXOUT9),
    .RESET_B(RST_B),
    .Q(DOUT9));
 sky130_fd_sc_hd__inv_1 xinv_sample (.A(BUSY),
    .Y(PH_SAMPLE));
 sky130_fd_sc_hd__mux2_1 xmux0 (.A0(DOUT0),
    .A1(COMP_OUT),
    .S(PH_B0),
    .X(MUXOUT0));
 sky130_fd_sc_hd__mux2_1 xmux1 (.A0(DOUT1),
    .A1(COMP_OUT),
    .S(PH_B1),
    .X(MUXOUT1));
 sky130_fd_sc_hd__mux2_1 xmux2 (.A0(DOUT2),
    .A1(COMP_OUT),
    .S(PH_B2),
    .X(MUXOUT2));
 sky130_fd_sc_hd__mux2_1 xmux3 (.A0(DOUT3),
    .A1(COMP_OUT),
    .S(PH_B3),
    .X(MUXOUT3));
 sky130_fd_sc_hd__mux2_1 xmux4 (.A0(DOUT4),
    .A1(COMP_OUT),
    .S(PH_B4),
    .X(MUXOUT4));
 sky130_fd_sc_hd__mux2_1 xmux5 (.A0(DOUT5),
    .A1(COMP_OUT),
    .S(PH_B5),
    .X(MUXOUT5));
 sky130_fd_sc_hd__mux2_1 xmux6 (.A0(DOUT6),
    .A1(COMP_OUT),
    .S(PH_B6),
    .X(MUXOUT6));
 sky130_fd_sc_hd__mux2_1 xmux7 (.A0(DOUT7),
    .A1(COMP_OUT),
    .S(PH_B7),
    .X(MUXOUT7));
 sky130_fd_sc_hd__mux2_1 xmux8 (.A0(DOUT8),
    .A1(COMP_OUT),
    .S(PH_B8),
    .X(MUXOUT8));
 sky130_fd_sc_hd__mux2_1 xmux9 (.A0(DOUT9),
    .A1(COMP_OUT),
    .S(PH_B9),
    .X(MUXOUT9));
 sky130_fd_sc_hd__or3_1 xor_busy (.A(ORG1),
    .B(ORG2),
    .C(ORG3),
    .X(BUSY));
 sky130_fd_sc_hd__or4_1 xor_g1 (.A(PH_B9),
    .B(PH_B8),
    .C(PH_B7),
    .D(PH_B6),
    .X(ORG1));
 sky130_fd_sc_hd__or4_1 xor_g2 (.A(PH_B5),
    .B(PH_B4),
    .C(PH_B3),
    .D(PH_B2),
    .X(ORG2));
 sky130_fd_sc_hd__or3_1 xor_g3 (.A(PH_B1),
    .B(PH_B0),
    .C(PH_EOC),
    .X(ORG3));
 sky130_fd_sc_hd__dfrtp_1 xringb0 (.CLK(clknet_1_1__leaf_CLK),
    .D(PH_B1),
    .RESET_B(RST_B),
    .Q(PH_B0));
 sky130_fd_sc_hd__dfrtp_1 xringb1 (.CLK(clknet_1_1__leaf_CLK),
    .D(PH_B2),
    .RESET_B(RST_B),
    .Q(PH_B1));
 sky130_fd_sc_hd__dfrtp_1 xringb2 (.CLK(clknet_1_1__leaf_CLK),
    .D(PH_B3),
    .RESET_B(RST_B),
    .Q(PH_B2));
 sky130_fd_sc_hd__dfrtp_1 xringb3 (.CLK(clknet_1_1__leaf_CLK),
    .D(PH_B4),
    .RESET_B(RST_B),
    .Q(PH_B3));
 sky130_fd_sc_hd__dfrtp_1 xringb4 (.CLK(clknet_1_1__leaf_CLK),
    .D(PH_B5),
    .RESET_B(RST_B),
    .Q(PH_B4));
 sky130_fd_sc_hd__dfrtp_1 xringb5 (.CLK(clknet_1_0__leaf_CLK),
    .D(PH_B6),
    .RESET_B(RST_B),
    .Q(PH_B5));
 sky130_fd_sc_hd__dfrtp_1 xringb6 (.CLK(clknet_1_0__leaf_CLK),
    .D(PH_B7),
    .RESET_B(RST_B),
    .Q(PH_B6));
 sky130_fd_sc_hd__dfrtp_1 xringb7 (.CLK(clknet_1_0__leaf_CLK),
    .D(PH_B8),
    .RESET_B(RST_B),
    .Q(PH_B7));
 sky130_fd_sc_hd__dfrtp_1 xringb8 (.CLK(clknet_1_0__leaf_CLK),
    .D(PH_B9),
    .RESET_B(RST_B),
    .Q(PH_B8));
 sky130_fd_sc_hd__dfrtp_1 xringb9 (.CLK(clknet_1_0__leaf_CLK),
    .D(PH_SAMPLE),
    .RESET_B(RST_B),
    .Q(PH_B9));
 sky130_fd_sc_hd__dfrtp_1 xringeoc (.CLK(clknet_1_1__leaf_CLK),
    .D(PH_B0),
    .RESET_B(RST_B),
    .Q(PH_EOC));
endmodule

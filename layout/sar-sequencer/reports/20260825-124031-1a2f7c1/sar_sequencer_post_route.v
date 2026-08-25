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
 sky130_fd_sc_hd__dfrtp_1 xbreg2 (.CLK(clknet_1_1__leaf_CLK),
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
 sky130_fd_sc_hd__dfrtp_1 xbreg8 (.CLK(clknet_1_1__leaf_CLK),
    .D(MUXOUT8),
    .RESET_B(RST_B),
    .Q(DOUT8));
 sky130_fd_sc_hd__dfrtp_1 xbreg9 (.CLK(clknet_1_0__leaf_CLK),
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
 sky130_fd_sc_hd__dfrtp_1 xringeoc (.CLK(clknet_1_0__leaf_CLK),
    .D(PH_B0),
    .RESET_B(RST_B),
    .Q(PH_EOC));
endmodule

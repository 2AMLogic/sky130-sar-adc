module top_glue (ADCOUT0,
    ADCOUT1,
    ADCOUT2,
    ADCOUT3,
    ADCOUT4,
    ADCOUT5,
    ADCOUT6,
    ADCOUT7,
    ADCOUT8,
    BUSY,
    CLK,
    CLKN,
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
    DUMLOAD_MUX_NC,
    DUMLOAD_XNOR_NC,
    HALF_LSB_EN,
    HALF_LSB_ENN,
    OUTN_NC,
    PH_B9,
    SELn0,
    SELn1,
    SELn2,
    SELn3,
    SELn4,
    SELn5,
    SELn6,
    SELn7,
    SELn8,
    SELp0,
    SELp1,
    SELp2,
    SELp3,
    SELp4,
    SELp5,
    SELp6,
    SELp7,
    SELp8);
 output ADCOUT0;
 output ADCOUT1;
 output ADCOUT2;
 output ADCOUT3;
 output ADCOUT4;
 output ADCOUT5;
 output ADCOUT6;
 output ADCOUT7;
 output ADCOUT8;
 input BUSY;
 input CLK;
 output CLKN;
 input DOUT0;
 input DOUT1;
 input DOUT2;
 input DOUT3;
 input DOUT4;
 input DOUT5;
 input DOUT6;
 input DOUT7;
 input DOUT8;
 input DOUT9;
 output DUMLOAD_MUX_NC;
 output DUMLOAD_XNOR_NC;
 output HALF_LSB_EN;
 output HALF_LSB_ENN;
 input OUTN_NC;
 input PH_B9;
 output SELn0;
 output SELn1;
 output SELn2;
 output SELn3;
 output SELn4;
 output SELn5;
 output SELn6;
 output SELn7;
 output SELn8;
 output SELp0;
 output SELp1;
 output SELp2;
 output SELp3;
 output SELp4;
 output SELp5;
 output SELp6;
 output SELp7;
 output SELp8;

 wire DOUT9N;

 sky130_fd_sc_hd__fill_8 FILLER_0_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_0_107 ();
 sky130_fd_sc_hd__fill_4 FILLER_0_115 ();
 sky130_fd_sc_hd__fill_1 FILLER_0_119 ();
 sky130_fd_sc_hd__fill_8 FILLER_0_121 ();
 sky130_fd_sc_hd__fill_8 FILLER_0_129 ();
 sky130_fd_sc_hd__fill_8 FILLER_0_137 ();
 sky130_fd_sc_hd__fill_1 FILLER_0_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_0_16 ();
 sky130_fd_sc_hd__fill_4 FILLER_0_24 ();
 sky130_fd_sc_hd__fill_2 FILLER_0_28 ();
 sky130_fd_sc_hd__fill_8 FILLER_0_31 ();
 sky130_fd_sc_hd__fill_8 FILLER_0_39 ();
 sky130_fd_sc_hd__fill_8 FILLER_0_47 ();
 sky130_fd_sc_hd__fill_4 FILLER_0_55 ();
 sky130_fd_sc_hd__fill_1 FILLER_0_59 ();
 sky130_fd_sc_hd__fill_8 FILLER_0_61 ();
 sky130_fd_sc_hd__fill_8 FILLER_0_69 ();
 sky130_fd_sc_hd__fill_8 FILLER_0_77 ();
 sky130_fd_sc_hd__fill_8 FILLER_0_8 ();
 sky130_fd_sc_hd__fill_4 FILLER_0_85 ();
 sky130_fd_sc_hd__fill_1 FILLER_0_89 ();
 sky130_fd_sc_hd__fill_8 FILLER_0_91 ();
 sky130_fd_sc_hd__fill_8 FILLER_0_99 ();
 sky130_fd_sc_hd__fill_8 FILLER_10_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_10_107 ();
 sky130_fd_sc_hd__fill_8 FILLER_10_115 ();
 sky130_fd_sc_hd__fill_8 FILLER_10_123 ();
 sky130_fd_sc_hd__fill_8 FILLER_10_131 ();
 sky130_fd_sc_hd__fill_4 FILLER_10_139 ();
 sky130_fd_sc_hd__fill_2 FILLER_10_143 ();
 sky130_fd_sc_hd__fill_1 FILLER_10_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_10_16 ();
 sky130_fd_sc_hd__fill_4 FILLER_10_24 ();
 sky130_fd_sc_hd__fill_2 FILLER_10_28 ();
 sky130_fd_sc_hd__fill_8 FILLER_10_31 ();
 sky130_fd_sc_hd__fill_8 FILLER_10_39 ();
 sky130_fd_sc_hd__fill_8 FILLER_10_47 ();
 sky130_fd_sc_hd__fill_8 FILLER_10_55 ();
 sky130_fd_sc_hd__fill_8 FILLER_10_63 ();
 sky130_fd_sc_hd__fill_8 FILLER_10_71 ();
 sky130_fd_sc_hd__fill_8 FILLER_10_79 ();
 sky130_fd_sc_hd__fill_8 FILLER_10_8 ();
 sky130_fd_sc_hd__fill_2 FILLER_10_87 ();
 sky130_fd_sc_hd__fill_1 FILLER_10_89 ();
 sky130_fd_sc_hd__fill_8 FILLER_10_91 ();
 sky130_fd_sc_hd__fill_8 FILLER_10_99 ();
 sky130_fd_sc_hd__fill_8 FILLER_11_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_11_101 ();
 sky130_fd_sc_hd__fill_8 FILLER_11_109 ();
 sky130_fd_sc_hd__fill_2 FILLER_11_117 ();
 sky130_fd_sc_hd__fill_1 FILLER_11_119 ();
 sky130_fd_sc_hd__fill_8 FILLER_11_121 ();
 sky130_fd_sc_hd__fill_8 FILLER_11_129 ();
 sky130_fd_sc_hd__fill_8 FILLER_11_137 ();
 sky130_fd_sc_hd__fill_1 FILLER_11_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_11_16 ();
 sky130_fd_sc_hd__fill_8 FILLER_11_24 ();
 sky130_fd_sc_hd__fill_8 FILLER_11_32 ();
 sky130_fd_sc_hd__fill_8 FILLER_11_40 ();
 sky130_fd_sc_hd__fill_8 FILLER_11_48 ();
 sky130_fd_sc_hd__fill_4 FILLER_11_56 ();
 sky130_fd_sc_hd__fill_8 FILLER_11_61 ();
 sky130_fd_sc_hd__fill_8 FILLER_11_69 ();
 sky130_fd_sc_hd__fill_8 FILLER_11_77 ();
 sky130_fd_sc_hd__fill_8 FILLER_11_8 ();
 sky130_fd_sc_hd__fill_8 FILLER_11_85 ();
 sky130_fd_sc_hd__fill_8 FILLER_11_93 ();
 sky130_fd_sc_hd__fill_8 FILLER_12_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_12_107 ();
 sky130_fd_sc_hd__fill_8 FILLER_12_115 ();
 sky130_fd_sc_hd__fill_8 FILLER_12_123 ();
 sky130_fd_sc_hd__fill_8 FILLER_12_131 ();
 sky130_fd_sc_hd__fill_4 FILLER_12_139 ();
 sky130_fd_sc_hd__fill_2 FILLER_12_143 ();
 sky130_fd_sc_hd__fill_1 FILLER_12_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_12_16 ();
 sky130_fd_sc_hd__fill_4 FILLER_12_24 ();
 sky130_fd_sc_hd__fill_2 FILLER_12_28 ();
 sky130_fd_sc_hd__fill_8 FILLER_12_31 ();
 sky130_fd_sc_hd__fill_8 FILLER_12_39 ();
 sky130_fd_sc_hd__fill_8 FILLER_12_47 ();
 sky130_fd_sc_hd__fill_8 FILLER_12_55 ();
 sky130_fd_sc_hd__fill_8 FILLER_12_63 ();
 sky130_fd_sc_hd__fill_8 FILLER_12_71 ();
 sky130_fd_sc_hd__fill_8 FILLER_12_79 ();
 sky130_fd_sc_hd__fill_8 FILLER_12_8 ();
 sky130_fd_sc_hd__fill_2 FILLER_12_87 ();
 sky130_fd_sc_hd__fill_1 FILLER_12_89 ();
 sky130_fd_sc_hd__fill_8 FILLER_12_91 ();
 sky130_fd_sc_hd__fill_8 FILLER_12_99 ();
 sky130_fd_sc_hd__fill_8 FILLER_13_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_13_101 ();
 sky130_fd_sc_hd__fill_8 FILLER_13_109 ();
 sky130_fd_sc_hd__fill_2 FILLER_13_117 ();
 sky130_fd_sc_hd__fill_1 FILLER_13_119 ();
 sky130_fd_sc_hd__fill_8 FILLER_13_121 ();
 sky130_fd_sc_hd__fill_8 FILLER_13_129 ();
 sky130_fd_sc_hd__fill_8 FILLER_13_137 ();
 sky130_fd_sc_hd__fill_1 FILLER_13_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_13_16 ();
 sky130_fd_sc_hd__fill_8 FILLER_13_24 ();
 sky130_fd_sc_hd__fill_8 FILLER_13_32 ();
 sky130_fd_sc_hd__fill_8 FILLER_13_40 ();
 sky130_fd_sc_hd__fill_8 FILLER_13_48 ();
 sky130_fd_sc_hd__fill_4 FILLER_13_56 ();
 sky130_fd_sc_hd__fill_8 FILLER_13_61 ();
 sky130_fd_sc_hd__fill_8 FILLER_13_69 ();
 sky130_fd_sc_hd__fill_8 FILLER_13_77 ();
 sky130_fd_sc_hd__fill_8 FILLER_13_8 ();
 sky130_fd_sc_hd__fill_8 FILLER_13_85 ();
 sky130_fd_sc_hd__fill_8 FILLER_13_93 ();
 sky130_fd_sc_hd__fill_8 FILLER_14_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_14_107 ();
 sky130_fd_sc_hd__fill_8 FILLER_14_115 ();
 sky130_fd_sc_hd__fill_8 FILLER_14_123 ();
 sky130_fd_sc_hd__fill_8 FILLER_14_131 ();
 sky130_fd_sc_hd__fill_4 FILLER_14_139 ();
 sky130_fd_sc_hd__fill_2 FILLER_14_143 ();
 sky130_fd_sc_hd__fill_1 FILLER_14_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_14_16 ();
 sky130_fd_sc_hd__fill_4 FILLER_14_24 ();
 sky130_fd_sc_hd__fill_2 FILLER_14_28 ();
 sky130_fd_sc_hd__fill_8 FILLER_14_31 ();
 sky130_fd_sc_hd__fill_8 FILLER_14_39 ();
 sky130_fd_sc_hd__fill_8 FILLER_14_47 ();
 sky130_fd_sc_hd__fill_8 FILLER_14_55 ();
 sky130_fd_sc_hd__fill_8 FILLER_14_63 ();
 sky130_fd_sc_hd__fill_8 FILLER_14_71 ();
 sky130_fd_sc_hd__fill_8 FILLER_14_79 ();
 sky130_fd_sc_hd__fill_8 FILLER_14_8 ();
 sky130_fd_sc_hd__fill_2 FILLER_14_87 ();
 sky130_fd_sc_hd__fill_1 FILLER_14_89 ();
 sky130_fd_sc_hd__fill_8 FILLER_14_91 ();
 sky130_fd_sc_hd__fill_8 FILLER_14_99 ();
 sky130_fd_sc_hd__fill_8 FILLER_15_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_15_101 ();
 sky130_fd_sc_hd__fill_8 FILLER_15_109 ();
 sky130_fd_sc_hd__fill_2 FILLER_15_117 ();
 sky130_fd_sc_hd__fill_1 FILLER_15_119 ();
 sky130_fd_sc_hd__fill_8 FILLER_15_121 ();
 sky130_fd_sc_hd__fill_8 FILLER_15_129 ();
 sky130_fd_sc_hd__fill_8 FILLER_15_137 ();
 sky130_fd_sc_hd__fill_1 FILLER_15_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_15_16 ();
 sky130_fd_sc_hd__fill_8 FILLER_15_24 ();
 sky130_fd_sc_hd__fill_8 FILLER_15_32 ();
 sky130_fd_sc_hd__fill_8 FILLER_15_40 ();
 sky130_fd_sc_hd__fill_8 FILLER_15_48 ();
 sky130_fd_sc_hd__fill_4 FILLER_15_56 ();
 sky130_fd_sc_hd__fill_8 FILLER_15_61 ();
 sky130_fd_sc_hd__fill_8 FILLER_15_69 ();
 sky130_fd_sc_hd__fill_8 FILLER_15_77 ();
 sky130_fd_sc_hd__fill_8 FILLER_15_8 ();
 sky130_fd_sc_hd__fill_8 FILLER_15_85 ();
 sky130_fd_sc_hd__fill_8 FILLER_15_93 ();
 sky130_fd_sc_hd__fill_8 FILLER_16_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_16_107 ();
 sky130_fd_sc_hd__fill_8 FILLER_16_115 ();
 sky130_fd_sc_hd__fill_8 FILLER_16_123 ();
 sky130_fd_sc_hd__fill_8 FILLER_16_131 ();
 sky130_fd_sc_hd__fill_4 FILLER_16_139 ();
 sky130_fd_sc_hd__fill_2 FILLER_16_143 ();
 sky130_fd_sc_hd__fill_1 FILLER_16_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_16_16 ();
 sky130_fd_sc_hd__fill_4 FILLER_16_24 ();
 sky130_fd_sc_hd__fill_2 FILLER_16_28 ();
 sky130_fd_sc_hd__fill_8 FILLER_16_31 ();
 sky130_fd_sc_hd__fill_8 FILLER_16_39 ();
 sky130_fd_sc_hd__fill_8 FILLER_16_47 ();
 sky130_fd_sc_hd__fill_8 FILLER_16_55 ();
 sky130_fd_sc_hd__fill_8 FILLER_16_63 ();
 sky130_fd_sc_hd__fill_8 FILLER_16_71 ();
 sky130_fd_sc_hd__fill_8 FILLER_16_79 ();
 sky130_fd_sc_hd__fill_8 FILLER_16_8 ();
 sky130_fd_sc_hd__fill_2 FILLER_16_87 ();
 sky130_fd_sc_hd__fill_1 FILLER_16_89 ();
 sky130_fd_sc_hd__fill_8 FILLER_16_91 ();
 sky130_fd_sc_hd__fill_8 FILLER_16_99 ();
 sky130_fd_sc_hd__fill_8 FILLER_17_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_17_101 ();
 sky130_fd_sc_hd__fill_8 FILLER_17_109 ();
 sky130_fd_sc_hd__fill_2 FILLER_17_117 ();
 sky130_fd_sc_hd__fill_1 FILLER_17_119 ();
 sky130_fd_sc_hd__fill_8 FILLER_17_121 ();
 sky130_fd_sc_hd__fill_8 FILLER_17_129 ();
 sky130_fd_sc_hd__fill_8 FILLER_17_137 ();
 sky130_fd_sc_hd__fill_1 FILLER_17_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_17_16 ();
 sky130_fd_sc_hd__fill_8 FILLER_17_24 ();
 sky130_fd_sc_hd__fill_8 FILLER_17_32 ();
 sky130_fd_sc_hd__fill_8 FILLER_17_40 ();
 sky130_fd_sc_hd__fill_8 FILLER_17_48 ();
 sky130_fd_sc_hd__fill_4 FILLER_17_56 ();
 sky130_fd_sc_hd__fill_8 FILLER_17_61 ();
 sky130_fd_sc_hd__fill_8 FILLER_17_69 ();
 sky130_fd_sc_hd__fill_8 FILLER_17_77 ();
 sky130_fd_sc_hd__fill_8 FILLER_17_8 ();
 sky130_fd_sc_hd__fill_8 FILLER_17_85 ();
 sky130_fd_sc_hd__fill_8 FILLER_17_93 ();
 sky130_fd_sc_hd__fill_8 FILLER_18_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_18_107 ();
 sky130_fd_sc_hd__fill_8 FILLER_18_115 ();
 sky130_fd_sc_hd__fill_8 FILLER_18_123 ();
 sky130_fd_sc_hd__fill_8 FILLER_18_131 ();
 sky130_fd_sc_hd__fill_4 FILLER_18_139 ();
 sky130_fd_sc_hd__fill_2 FILLER_18_143 ();
 sky130_fd_sc_hd__fill_1 FILLER_18_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_18_16 ();
 sky130_fd_sc_hd__fill_4 FILLER_18_24 ();
 sky130_fd_sc_hd__fill_2 FILLER_18_28 ();
 sky130_fd_sc_hd__fill_8 FILLER_18_31 ();
 sky130_fd_sc_hd__fill_8 FILLER_18_39 ();
 sky130_fd_sc_hd__fill_8 FILLER_18_47 ();
 sky130_fd_sc_hd__fill_8 FILLER_18_55 ();
 sky130_fd_sc_hd__fill_8 FILLER_18_63 ();
 sky130_fd_sc_hd__fill_8 FILLER_18_71 ();
 sky130_fd_sc_hd__fill_8 FILLER_18_79 ();
 sky130_fd_sc_hd__fill_8 FILLER_18_8 ();
 sky130_fd_sc_hd__fill_2 FILLER_18_87 ();
 sky130_fd_sc_hd__fill_1 FILLER_18_89 ();
 sky130_fd_sc_hd__fill_8 FILLER_18_91 ();
 sky130_fd_sc_hd__fill_8 FILLER_18_99 ();
 sky130_fd_sc_hd__fill_8 FILLER_19_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_19_102 ();
 sky130_fd_sc_hd__fill_8 FILLER_19_110 ();
 sky130_fd_sc_hd__fill_2 FILLER_19_118 ();
 sky130_fd_sc_hd__fill_8 FILLER_19_121 ();
 sky130_fd_sc_hd__fill_8 FILLER_19_129 ();
 sky130_fd_sc_hd__fill_8 FILLER_19_137 ();
 sky130_fd_sc_hd__fill_1 FILLER_19_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_19_16 ();
 sky130_fd_sc_hd__fill_2 FILLER_19_24 ();
 sky130_fd_sc_hd__fill_1 FILLER_19_26 ();
 sky130_fd_sc_hd__fill_8 FILLER_19_34 ();
 sky130_fd_sc_hd__fill_8 FILLER_19_42 ();
 sky130_fd_sc_hd__fill_8 FILLER_19_50 ();
 sky130_fd_sc_hd__fill_2 FILLER_19_58 ();
 sky130_fd_sc_hd__fill_8 FILLER_19_61 ();
 sky130_fd_sc_hd__fill_8 FILLER_19_69 ();
 sky130_fd_sc_hd__fill_8 FILLER_19_77 ();
 sky130_fd_sc_hd__fill_8 FILLER_19_8 ();
 sky130_fd_sc_hd__fill_4 FILLER_19_85 ();
 sky130_fd_sc_hd__fill_8 FILLER_19_94 ();
 sky130_fd_sc_hd__fill_8 FILLER_1_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_1_101 ();
 sky130_fd_sc_hd__fill_8 FILLER_1_109 ();
 sky130_fd_sc_hd__fill_2 FILLER_1_117 ();
 sky130_fd_sc_hd__fill_1 FILLER_1_119 ();
 sky130_fd_sc_hd__fill_8 FILLER_1_121 ();
 sky130_fd_sc_hd__fill_8 FILLER_1_129 ();
 sky130_fd_sc_hd__fill_8 FILLER_1_137 ();
 sky130_fd_sc_hd__fill_1 FILLER_1_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_1_16 ();
 sky130_fd_sc_hd__fill_8 FILLER_1_24 ();
 sky130_fd_sc_hd__fill_8 FILLER_1_32 ();
 sky130_fd_sc_hd__fill_8 FILLER_1_40 ();
 sky130_fd_sc_hd__fill_8 FILLER_1_48 ();
 sky130_fd_sc_hd__fill_4 FILLER_1_56 ();
 sky130_fd_sc_hd__fill_8 FILLER_1_61 ();
 sky130_fd_sc_hd__fill_8 FILLER_1_69 ();
 sky130_fd_sc_hd__fill_8 FILLER_1_77 ();
 sky130_fd_sc_hd__fill_8 FILLER_1_8 ();
 sky130_fd_sc_hd__fill_8 FILLER_1_85 ();
 sky130_fd_sc_hd__fill_8 FILLER_1_93 ();
 sky130_fd_sc_hd__fill_8 FILLER_20_0 ();
 sky130_fd_sc_hd__fill_2 FILLER_20_107 ();
 sky130_fd_sc_hd__fill_8 FILLER_20_114 ();
 sky130_fd_sc_hd__fill_8 FILLER_20_122 ();
 sky130_fd_sc_hd__fill_8 FILLER_20_130 ();
 sky130_fd_sc_hd__fill_8 FILLER_20_138 ();
 sky130_fd_sc_hd__fill_8 FILLER_20_16 ();
 sky130_fd_sc_hd__fill_4 FILLER_20_24 ();
 sky130_fd_sc_hd__fill_2 FILLER_20_28 ();
 sky130_fd_sc_hd__fill_8 FILLER_20_31 ();
 sky130_fd_sc_hd__fill_8 FILLER_20_39 ();
 sky130_fd_sc_hd__fill_1 FILLER_20_47 ();
 sky130_fd_sc_hd__fill_8 FILLER_20_53 ();
 sky130_fd_sc_hd__fill_8 FILLER_20_70 ();
 sky130_fd_sc_hd__fill_8 FILLER_20_78 ();
 sky130_fd_sc_hd__fill_8 FILLER_20_8 ();
 sky130_fd_sc_hd__fill_4 FILLER_20_86 ();
 sky130_fd_sc_hd__fill_8 FILLER_20_91 ();
 sky130_fd_sc_hd__fill_8 FILLER_20_99 ();
 sky130_fd_sc_hd__fill_8 FILLER_21_0 ();
 sky130_fd_sc_hd__fill_4 FILLER_21_101 ();
 sky130_fd_sc_hd__fill_1 FILLER_21_108 ();
 sky130_fd_sc_hd__fill_4 FILLER_21_114 ();
 sky130_fd_sc_hd__fill_2 FILLER_21_118 ();
 sky130_fd_sc_hd__fill_8 FILLER_21_121 ();
 sky130_fd_sc_hd__fill_8 FILLER_21_129 ();
 sky130_fd_sc_hd__fill_8 FILLER_21_137 ();
 sky130_fd_sc_hd__fill_1 FILLER_21_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_21_16 ();
 sky130_fd_sc_hd__fill_1 FILLER_21_24 ();
 sky130_fd_sc_hd__fill_2 FILLER_21_32 ();
 sky130_fd_sc_hd__fill_4 FILLER_21_41 ();
 sky130_fd_sc_hd__fill_2 FILLER_21_57 ();
 sky130_fd_sc_hd__fill_1 FILLER_21_59 ();
 sky130_fd_sc_hd__fill_4 FILLER_21_61 ();
 sky130_fd_sc_hd__fill_2 FILLER_21_65 ();
 sky130_fd_sc_hd__fill_1 FILLER_21_72 ();
 sky130_fd_sc_hd__fill_8 FILLER_21_8 ();
 sky130_fd_sc_hd__fill_8 FILLER_21_80 ();
 sky130_fd_sc_hd__fill_8 FILLER_21_93 ();
 sky130_fd_sc_hd__fill_8 FILLER_22_0 ();
 sky130_fd_sc_hd__fill_2 FILLER_22_104 ();
 sky130_fd_sc_hd__fill_1 FILLER_22_106 ();
 sky130_fd_sc_hd__fill_8 FILLER_22_112 ();
 sky130_fd_sc_hd__fill_8 FILLER_22_120 ();
 sky130_fd_sc_hd__fill_8 FILLER_22_128 ();
 sky130_fd_sc_hd__fill_8 FILLER_22_136 ();
 sky130_fd_sc_hd__fill_2 FILLER_22_144 ();
 sky130_fd_sc_hd__fill_4 FILLER_22_16 ();
 sky130_fd_sc_hd__fill_2 FILLER_22_20 ();
 sky130_fd_sc_hd__fill_1 FILLER_22_22 ();
 sky130_fd_sc_hd__fill_4 FILLER_22_31 ();
 sky130_fd_sc_hd__fill_4 FILLER_22_38 ();
 sky130_fd_sc_hd__fill_2 FILLER_22_42 ();
 sky130_fd_sc_hd__fill_1 FILLER_22_44 ();
 sky130_fd_sc_hd__fill_1 FILLER_22_50 ();
 sky130_fd_sc_hd__fill_2 FILLER_22_56 ();
 sky130_fd_sc_hd__fill_1 FILLER_22_58 ();
 sky130_fd_sc_hd__fill_4 FILLER_22_66 ();
 sky130_fd_sc_hd__fill_1 FILLER_22_70 ();
 sky130_fd_sc_hd__fill_8 FILLER_22_8 ();
 sky130_fd_sc_hd__fill_4 FILLER_22_86 ();
 sky130_fd_sc_hd__fill_2 FILLER_22_96 ();
 sky130_fd_sc_hd__fill_1 FILLER_22_98 ();
 sky130_fd_sc_hd__fill_8 FILLER_23_0 ();
 sky130_fd_sc_hd__fill_4 FILLER_23_104 ();
 sky130_fd_sc_hd__fill_4 FILLER_23_113 ();
 sky130_fd_sc_hd__fill_2 FILLER_23_117 ();
 sky130_fd_sc_hd__fill_1 FILLER_23_119 ();
 sky130_fd_sc_hd__fill_8 FILLER_23_121 ();
 sky130_fd_sc_hd__fill_8 FILLER_23_129 ();
 sky130_fd_sc_hd__fill_8 FILLER_23_137 ();
 sky130_fd_sc_hd__fill_1 FILLER_23_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_23_16 ();
 sky130_fd_sc_hd__fill_4 FILLER_23_24 ();
 sky130_fd_sc_hd__fill_2 FILLER_23_28 ();
 sky130_fd_sc_hd__fill_2 FILLER_23_31 ();
 sky130_fd_sc_hd__fill_8 FILLER_23_38 ();
 sky130_fd_sc_hd__fill_1 FILLER_23_46 ();
 sky130_fd_sc_hd__fill_8 FILLER_23_52 ();
 sky130_fd_sc_hd__fill_2 FILLER_23_67 ();
 sky130_fd_sc_hd__fill_2 FILLER_23_76 ();
 sky130_fd_sc_hd__fill_8 FILLER_23_8 ();
 sky130_fd_sc_hd__fill_4 FILLER_23_85 ();
 sky130_fd_sc_hd__fill_1 FILLER_23_89 ();
 sky130_fd_sc_hd__fill_2 FILLER_23_96 ();
 sky130_fd_sc_hd__fill_1 FILLER_23_98 ();
 sky130_fd_sc_hd__fill_8 FILLER_2_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_2_107 ();
 sky130_fd_sc_hd__fill_8 FILLER_2_115 ();
 sky130_fd_sc_hd__fill_8 FILLER_2_123 ();
 sky130_fd_sc_hd__fill_8 FILLER_2_131 ();
 sky130_fd_sc_hd__fill_4 FILLER_2_139 ();
 sky130_fd_sc_hd__fill_2 FILLER_2_143 ();
 sky130_fd_sc_hd__fill_1 FILLER_2_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_2_16 ();
 sky130_fd_sc_hd__fill_4 FILLER_2_24 ();
 sky130_fd_sc_hd__fill_2 FILLER_2_28 ();
 sky130_fd_sc_hd__fill_8 FILLER_2_31 ();
 sky130_fd_sc_hd__fill_8 FILLER_2_39 ();
 sky130_fd_sc_hd__fill_8 FILLER_2_47 ();
 sky130_fd_sc_hd__fill_8 FILLER_2_55 ();
 sky130_fd_sc_hd__fill_8 FILLER_2_63 ();
 sky130_fd_sc_hd__fill_8 FILLER_2_71 ();
 sky130_fd_sc_hd__fill_8 FILLER_2_79 ();
 sky130_fd_sc_hd__fill_8 FILLER_2_8 ();
 sky130_fd_sc_hd__fill_2 FILLER_2_87 ();
 sky130_fd_sc_hd__fill_1 FILLER_2_89 ();
 sky130_fd_sc_hd__fill_8 FILLER_2_91 ();
 sky130_fd_sc_hd__fill_8 FILLER_2_99 ();
 sky130_fd_sc_hd__fill_8 FILLER_3_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_3_101 ();
 sky130_fd_sc_hd__fill_8 FILLER_3_109 ();
 sky130_fd_sc_hd__fill_2 FILLER_3_117 ();
 sky130_fd_sc_hd__fill_1 FILLER_3_119 ();
 sky130_fd_sc_hd__fill_8 FILLER_3_121 ();
 sky130_fd_sc_hd__fill_8 FILLER_3_129 ();
 sky130_fd_sc_hd__fill_8 FILLER_3_137 ();
 sky130_fd_sc_hd__fill_1 FILLER_3_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_3_16 ();
 sky130_fd_sc_hd__fill_8 FILLER_3_24 ();
 sky130_fd_sc_hd__fill_8 FILLER_3_32 ();
 sky130_fd_sc_hd__fill_8 FILLER_3_40 ();
 sky130_fd_sc_hd__fill_8 FILLER_3_48 ();
 sky130_fd_sc_hd__fill_4 FILLER_3_56 ();
 sky130_fd_sc_hd__fill_8 FILLER_3_61 ();
 sky130_fd_sc_hd__fill_8 FILLER_3_69 ();
 sky130_fd_sc_hd__fill_8 FILLER_3_77 ();
 sky130_fd_sc_hd__fill_8 FILLER_3_8 ();
 sky130_fd_sc_hd__fill_8 FILLER_3_85 ();
 sky130_fd_sc_hd__fill_8 FILLER_3_93 ();
 sky130_fd_sc_hd__fill_8 FILLER_4_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_4_107 ();
 sky130_fd_sc_hd__fill_8 FILLER_4_115 ();
 sky130_fd_sc_hd__fill_8 FILLER_4_123 ();
 sky130_fd_sc_hd__fill_8 FILLER_4_131 ();
 sky130_fd_sc_hd__fill_4 FILLER_4_139 ();
 sky130_fd_sc_hd__fill_2 FILLER_4_143 ();
 sky130_fd_sc_hd__fill_1 FILLER_4_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_4_16 ();
 sky130_fd_sc_hd__fill_4 FILLER_4_24 ();
 sky130_fd_sc_hd__fill_2 FILLER_4_28 ();
 sky130_fd_sc_hd__fill_8 FILLER_4_31 ();
 sky130_fd_sc_hd__fill_8 FILLER_4_39 ();
 sky130_fd_sc_hd__fill_8 FILLER_4_47 ();
 sky130_fd_sc_hd__fill_8 FILLER_4_55 ();
 sky130_fd_sc_hd__fill_8 FILLER_4_63 ();
 sky130_fd_sc_hd__fill_8 FILLER_4_71 ();
 sky130_fd_sc_hd__fill_8 FILLER_4_79 ();
 sky130_fd_sc_hd__fill_8 FILLER_4_8 ();
 sky130_fd_sc_hd__fill_2 FILLER_4_87 ();
 sky130_fd_sc_hd__fill_1 FILLER_4_89 ();
 sky130_fd_sc_hd__fill_8 FILLER_4_91 ();
 sky130_fd_sc_hd__fill_8 FILLER_4_99 ();
 sky130_fd_sc_hd__fill_8 FILLER_5_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_5_101 ();
 sky130_fd_sc_hd__fill_8 FILLER_5_109 ();
 sky130_fd_sc_hd__fill_2 FILLER_5_117 ();
 sky130_fd_sc_hd__fill_1 FILLER_5_119 ();
 sky130_fd_sc_hd__fill_8 FILLER_5_121 ();
 sky130_fd_sc_hd__fill_8 FILLER_5_129 ();
 sky130_fd_sc_hd__fill_8 FILLER_5_137 ();
 sky130_fd_sc_hd__fill_1 FILLER_5_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_5_16 ();
 sky130_fd_sc_hd__fill_8 FILLER_5_24 ();
 sky130_fd_sc_hd__fill_8 FILLER_5_32 ();
 sky130_fd_sc_hd__fill_8 FILLER_5_40 ();
 sky130_fd_sc_hd__fill_8 FILLER_5_48 ();
 sky130_fd_sc_hd__fill_4 FILLER_5_56 ();
 sky130_fd_sc_hd__fill_8 FILLER_5_61 ();
 sky130_fd_sc_hd__fill_8 FILLER_5_69 ();
 sky130_fd_sc_hd__fill_8 FILLER_5_77 ();
 sky130_fd_sc_hd__fill_8 FILLER_5_8 ();
 sky130_fd_sc_hd__fill_8 FILLER_5_85 ();
 sky130_fd_sc_hd__fill_8 FILLER_5_93 ();
 sky130_fd_sc_hd__fill_8 FILLER_6_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_6_107 ();
 sky130_fd_sc_hd__fill_8 FILLER_6_115 ();
 sky130_fd_sc_hd__fill_8 FILLER_6_123 ();
 sky130_fd_sc_hd__fill_8 FILLER_6_131 ();
 sky130_fd_sc_hd__fill_4 FILLER_6_139 ();
 sky130_fd_sc_hd__fill_2 FILLER_6_143 ();
 sky130_fd_sc_hd__fill_1 FILLER_6_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_6_16 ();
 sky130_fd_sc_hd__fill_4 FILLER_6_24 ();
 sky130_fd_sc_hd__fill_2 FILLER_6_28 ();
 sky130_fd_sc_hd__fill_8 FILLER_6_31 ();
 sky130_fd_sc_hd__fill_8 FILLER_6_39 ();
 sky130_fd_sc_hd__fill_8 FILLER_6_47 ();
 sky130_fd_sc_hd__fill_8 FILLER_6_55 ();
 sky130_fd_sc_hd__fill_8 FILLER_6_63 ();
 sky130_fd_sc_hd__fill_8 FILLER_6_71 ();
 sky130_fd_sc_hd__fill_8 FILLER_6_79 ();
 sky130_fd_sc_hd__fill_8 FILLER_6_8 ();
 sky130_fd_sc_hd__fill_2 FILLER_6_87 ();
 sky130_fd_sc_hd__fill_1 FILLER_6_89 ();
 sky130_fd_sc_hd__fill_8 FILLER_6_91 ();
 sky130_fd_sc_hd__fill_8 FILLER_6_99 ();
 sky130_fd_sc_hd__fill_8 FILLER_7_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_7_101 ();
 sky130_fd_sc_hd__fill_8 FILLER_7_109 ();
 sky130_fd_sc_hd__fill_2 FILLER_7_117 ();
 sky130_fd_sc_hd__fill_1 FILLER_7_119 ();
 sky130_fd_sc_hd__fill_8 FILLER_7_121 ();
 sky130_fd_sc_hd__fill_8 FILLER_7_129 ();
 sky130_fd_sc_hd__fill_8 FILLER_7_137 ();
 sky130_fd_sc_hd__fill_1 FILLER_7_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_7_16 ();
 sky130_fd_sc_hd__fill_8 FILLER_7_24 ();
 sky130_fd_sc_hd__fill_8 FILLER_7_32 ();
 sky130_fd_sc_hd__fill_8 FILLER_7_40 ();
 sky130_fd_sc_hd__fill_8 FILLER_7_48 ();
 sky130_fd_sc_hd__fill_4 FILLER_7_56 ();
 sky130_fd_sc_hd__fill_8 FILLER_7_61 ();
 sky130_fd_sc_hd__fill_8 FILLER_7_69 ();
 sky130_fd_sc_hd__fill_8 FILLER_7_77 ();
 sky130_fd_sc_hd__fill_8 FILLER_7_8 ();
 sky130_fd_sc_hd__fill_8 FILLER_7_85 ();
 sky130_fd_sc_hd__fill_8 FILLER_7_93 ();
 sky130_fd_sc_hd__fill_8 FILLER_8_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_8_107 ();
 sky130_fd_sc_hd__fill_8 FILLER_8_115 ();
 sky130_fd_sc_hd__fill_8 FILLER_8_123 ();
 sky130_fd_sc_hd__fill_8 FILLER_8_131 ();
 sky130_fd_sc_hd__fill_4 FILLER_8_139 ();
 sky130_fd_sc_hd__fill_2 FILLER_8_143 ();
 sky130_fd_sc_hd__fill_1 FILLER_8_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_8_16 ();
 sky130_fd_sc_hd__fill_4 FILLER_8_24 ();
 sky130_fd_sc_hd__fill_2 FILLER_8_28 ();
 sky130_fd_sc_hd__fill_8 FILLER_8_31 ();
 sky130_fd_sc_hd__fill_8 FILLER_8_39 ();
 sky130_fd_sc_hd__fill_8 FILLER_8_47 ();
 sky130_fd_sc_hd__fill_8 FILLER_8_55 ();
 sky130_fd_sc_hd__fill_8 FILLER_8_63 ();
 sky130_fd_sc_hd__fill_8 FILLER_8_71 ();
 sky130_fd_sc_hd__fill_8 FILLER_8_79 ();
 sky130_fd_sc_hd__fill_8 FILLER_8_8 ();
 sky130_fd_sc_hd__fill_2 FILLER_8_87 ();
 sky130_fd_sc_hd__fill_1 FILLER_8_89 ();
 sky130_fd_sc_hd__fill_8 FILLER_8_91 ();
 sky130_fd_sc_hd__fill_8 FILLER_8_99 ();
 sky130_fd_sc_hd__fill_8 FILLER_9_0 ();
 sky130_fd_sc_hd__fill_8 FILLER_9_101 ();
 sky130_fd_sc_hd__fill_8 FILLER_9_109 ();
 sky130_fd_sc_hd__fill_2 FILLER_9_117 ();
 sky130_fd_sc_hd__fill_1 FILLER_9_119 ();
 sky130_fd_sc_hd__fill_8 FILLER_9_121 ();
 sky130_fd_sc_hd__fill_8 FILLER_9_129 ();
 sky130_fd_sc_hd__fill_8 FILLER_9_137 ();
 sky130_fd_sc_hd__fill_1 FILLER_9_145 ();
 sky130_fd_sc_hd__fill_8 FILLER_9_16 ();
 sky130_fd_sc_hd__fill_8 FILLER_9_24 ();
 sky130_fd_sc_hd__fill_8 FILLER_9_32 ();
 sky130_fd_sc_hd__fill_8 FILLER_9_40 ();
 sky130_fd_sc_hd__fill_8 FILLER_9_48 ();
 sky130_fd_sc_hd__fill_4 FILLER_9_56 ();
 sky130_fd_sc_hd__fill_8 FILLER_9_61 ();
 sky130_fd_sc_hd__fill_8 FILLER_9_69 ();
 sky130_fd_sc_hd__fill_8 FILLER_9_77 ();
 sky130_fd_sc_hd__fill_8 FILLER_9_8 ();
 sky130_fd_sc_hd__fill_8 FILLER_9_85 ();
 sky130_fd_sc_hd__fill_8 FILLER_9_93 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_0_0 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_0_1 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_0_2 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_0_3 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_10_22 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_10_23 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_11_24 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_11_25 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_12_26 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_12_27 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_13_28 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_13_29 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_14_30 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_14_31 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_15_32 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_15_33 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_16_34 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_16_35 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_17_36 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_17_37 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_18_38 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_18_39 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_19_40 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_19_41 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_1_4 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_1_5 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_20_42 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_20_43 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_21_44 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_21_45 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_22_46 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_22_47 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_23_48 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_23_49 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_23_50 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_23_51 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_2_6 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_2_7 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_3_8 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_3_9 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_4_10 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_4_11 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_5_12 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_5_13 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_6_14 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_6_15 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_7_16 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_7_17 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_8_18 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_8_19 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_9_20 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_9_21 ();
 sky130_fd_sc_hd__and2b_1 xand_halflsb (.A_N(PH_B9),
    .B(BUSY),
    .X(HALF_LSB_EN));
 sky130_fd_sc_hd__and2_1 xand_seln0 (.A(DOUT0),
    .B(DOUT9N),
    .X(SELn0));
 sky130_fd_sc_hd__and2_1 xand_seln1 (.A(DOUT1),
    .B(DOUT9N),
    .X(SELn1));
 sky130_fd_sc_hd__and2_1 xand_seln2 (.A(DOUT2),
    .B(DOUT9N),
    .X(SELn2));
 sky130_fd_sc_hd__and2_1 xand_seln3 (.A(DOUT3),
    .B(DOUT9N),
    .X(SELn3));
 sky130_fd_sc_hd__and2_1 xand_seln4 (.A(DOUT4),
    .B(DOUT9N),
    .X(SELn4));
 sky130_fd_sc_hd__and2_1 xand_seln5 (.A(DOUT5),
    .B(DOUT9N),
    .X(SELn5));
 sky130_fd_sc_hd__and2_1 xand_seln6 (.A(DOUT6),
    .B(DOUT9N),
    .X(SELn6));
 sky130_fd_sc_hd__and2_1 xand_seln7 (.A(DOUT7),
    .B(DOUT9N),
    .X(SELn7));
 sky130_fd_sc_hd__and2_1 xand_seln8 (.A(DOUT8),
    .B(DOUT9N),
    .X(SELn8));
 sky130_fd_sc_hd__and2_1 xand_selp0 (.A(DOUT9),
    .B(DOUT0),
    .X(SELp0));
 sky130_fd_sc_hd__and2_1 xand_selp1 (.A(DOUT9),
    .B(DOUT1),
    .X(SELp1));
 sky130_fd_sc_hd__and2_1 xand_selp2 (.A(DOUT9),
    .B(DOUT2),
    .X(SELp2));
 sky130_fd_sc_hd__and2_1 xand_selp3 (.A(DOUT9),
    .B(DOUT3),
    .X(SELp3));
 sky130_fd_sc_hd__and2_1 xand_selp4 (.A(DOUT9),
    .B(DOUT4),
    .X(SELp4));
 sky130_fd_sc_hd__and2_1 xand_selp5 (.A(DOUT9),
    .B(DOUT5),
    .X(SELp5));
 sky130_fd_sc_hd__and2_1 xand_selp6 (.A(DOUT9),
    .B(DOUT6),
    .X(SELp6));
 sky130_fd_sc_hd__and2_1 xand_selp7 (.A(DOUT9),
    .B(DOUT7),
    .X(SELp7));
 sky130_fd_sc_hd__and2_1 xand_selp8 (.A(DOUT9),
    .B(DOUT8),
    .X(SELp8));
 sky130_fd_sc_hd__mux2_1 xdum_mux_n (.A0(DOUT9),
    .A1(OUTN_NC),
    .S(PH_B9),
    .X(DUMLOAD_MUX_NC));
 sky130_fd_sc_hd__xnor2_1 xdum_xnor_n (.A(OUTN_NC),
    .B(DOUT9),
    .Y(DUMLOAD_XNOR_NC));
 sky130_fd_sc_hd__inv_1 xinv_clkcap (.A(CLK),
    .Y(CLKN));
 sky130_fd_sc_hd__inv_1 xinv_dout9n (.A(DOUT9),
    .Y(DOUT9N));
 sky130_fd_sc_hd__inv_1 xinv_halflsb (.A(HALF_LSB_EN),
    .Y(HALF_LSB_ENN));
 sky130_fd_sc_hd__xor2_1 xxor_code0 (.A(DOUT0),
    .B(DOUT9N),
    .X(ADCOUT0));
 sky130_fd_sc_hd__xor2_1 xxor_code1 (.A(DOUT1),
    .B(DOUT9N),
    .X(ADCOUT1));
 sky130_fd_sc_hd__xor2_1 xxor_code2 (.A(DOUT2),
    .B(DOUT9N),
    .X(ADCOUT2));
 sky130_fd_sc_hd__xor2_1 xxor_code3 (.A(DOUT3),
    .B(DOUT9N),
    .X(ADCOUT3));
 sky130_fd_sc_hd__xor2_1 xxor_code4 (.A(DOUT4),
    .B(DOUT9N),
    .X(ADCOUT4));
 sky130_fd_sc_hd__xor2_1 xxor_code5 (.A(DOUT5),
    .B(DOUT9N),
    .X(ADCOUT5));
 sky130_fd_sc_hd__xor2_1 xxor_code6 (.A(DOUT6),
    .B(DOUT9N),
    .X(ADCOUT6));
 sky130_fd_sc_hd__xor2_1 xxor_code7 (.A(DOUT7),
    .B(DOUT9N),
    .X(ADCOUT7));
 sky130_fd_sc_hd__xor2_1 xxor_code8 (.A(DOUT8),
    .B(DOUT9N),
    .X(ADCOUT8));
endmodule

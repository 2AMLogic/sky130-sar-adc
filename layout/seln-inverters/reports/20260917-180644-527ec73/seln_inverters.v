// Structural gate-level netlist for the SELn<i> = NOT(DOUT<i>) inverter
// bank -- nine independent sky130_fd_sc_hd__inv_1 instances, hand-derived
// 1:1 from design/sar_adc_top.sch's own xinv_seln0..xinv_seln8 instances
// (issue #56's top-level integration schematic; see that file's header,
// "SAR sequencer double-duty" section, for why the CDAC array needs a
// complementary SELn per bit rather than reusing DOUT directly).
//
// This is new top-level glue logic, not a sub-block: none of #99/#100/#101/
// #102's own schematics instantiate these cells -- design/sar_adc_top.sch
// adds them directly at the integration level, so their layout belongs to
// the top-level assembly issue (#103), not to any sub-block.
//
// Purely combinational (no clock, no state) -- fed straight to
// `klt place-and-route` the same way layout/sar-sequencer/netlist/
// sar_sequencer.v is, for the identical reason: this hand-written netlist
// already matches the reviewed schematic exactly, so there is nothing for
// `klt synthesize` (RTL->gates) to usefully do.
//
// Clean room: transliterated from this repo's own schematic, not from any
// reference SAR ADC implementation.
module seln_inverters (
    DOUT8, DOUT7, DOUT6, DOUT5, DOUT4, DOUT3, DOUT2, DOUT1, DOUT0,
    SELn8, SELn7, SELn6, SELn5, SELn4, SELn3, SELn2, SELn1, SELn0
);
  input  DOUT8, DOUT7, DOUT6, DOUT5, DOUT4, DOUT3, DOUT2, DOUT1, DOUT0;
  output SELn8, SELn7, SELn6, SELn5, SELn4, SELn3, SELn2, SELn1, SELn0;

  sky130_fd_sc_hd__inv_1 xinv_seln0 (.A(DOUT0), .Y(SELn0));
  sky130_fd_sc_hd__inv_1 xinv_seln1 (.A(DOUT1), .Y(SELn1));
  sky130_fd_sc_hd__inv_1 xinv_seln2 (.A(DOUT2), .Y(SELn2));
  sky130_fd_sc_hd__inv_1 xinv_seln3 (.A(DOUT3), .Y(SELn3));
  sky130_fd_sc_hd__inv_1 xinv_seln4 (.A(DOUT4), .Y(SELn4));
  sky130_fd_sc_hd__inv_1 xinv_seln5 (.A(DOUT5), .Y(SELn5));
  sky130_fd_sc_hd__inv_1 xinv_seln6 (.A(DOUT6), .Y(SELn6));
  sky130_fd_sc_hd__inv_1 xinv_seln7 (.A(DOUT7), .Y(SELn7));
  sky130_fd_sc_hd__inv_1 xinv_seln8 (.A(DOUT8), .Y(SELn8));
endmodule

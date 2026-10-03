// SUPERSEDED 2026-09-25 (issue #387). REPLACED BY layout/top-glue/netlist/
// top_glue.v. Do not re-derive, re-run or cite this netlist as current.
//
// The nine xinv_seln<i> instances below were removed from the schematic on
// 2026-09-11 by spec/decision-records/
// DR-008-cdac-top-level-switching-polarity.md (issue #263, PR #266), which
// replaced the unconditional complementary drive with a decision-directed
// one: SELp<i> = DOUT9 AND DOUT<i>, SELn<i> = DOUT9N AND DOUT<i>, eighteen
// and2_1 gates plus an xinv_dout9n complement. design/sar_adc_top.spice
// contains no xinv_seln instance at all -- grep it. Nothing re-derived this
// file when that landed, and the flow's own klt lvs verdict could not
// notice, because its reference is generated from this same netlist (see
// layout/top-glue/README.md, "The parity gate is the point of this
// directory"). It is kept only because layout/sar-adc-top/'s composition
// still consumes the GDS built from it.
//
// Structural gate-level netlist for the SELn<i> = NOT(DOUT<i>) inverter
// bank -- nine independent sky130_fd_sc_hd__inv_1 instances, hand-derived
// 1:1 from design/sar_adc_top.sch's own xinv_seln0..xinv_seln8 instances
// AS THAT SCHEMATIC STOOD UNDER ISSUE #56 (see that file's header,
// "SAR sequencer double-duty" section, for the wiring rationale DR-008
// went on to overturn).
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

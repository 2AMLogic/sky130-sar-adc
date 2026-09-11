v {xschem version=3.4.7 file_version=1.2
* sar_sequencer.sch -- SAR logic / sequencer + clock/phase generation (issue #55)
*
* Digital-only DUT: an (N+1)-stage walking-one ring sequencer (N bit-trial
* phases, MSB first, plus one EOC phase) generates the SAR conversion's clock
* phases from a single master CLK; each of the N SAR-register bits is a
* dfrtp_1 D flip-flop fed through a mux2_1 that captures an externally
* supplied (ideal) comparator decision COMP_OUT during its own bit-trial
* phase and holds otherwise. See spec/decision-records/DR-006-sar-sequencer-
* bit-count-and-timing-budget.md for the N=10 (provisional) bit-count and
* timing-budget derivation this schematic implements, and
* sim/sar-sequencer-behavioral/ for the standalone testbench that exercises
* it against an ideal comparator-decision stimulus.
*
* Every logic instance below is drawn from sky130_fd_sc_hd (via this
* project's sky130_stdcells xschem symbol library) -- no other digital
* library or non-ratified device flavour appears. No front end, CDAC array,
* or comparator netlist is referenced; COMP_OUT/CLK/RST_B are schematic
* ports (ipins), driven only by the standalone testbench.
*
* Clean room: this sequencer is designed forward from standard SAR-ADC
* control-loop theory (a token/ring phase generator gating a
* successive-approximation register) and sky130_fd_sc_hd cell semantics, not
* from any reference SAR ADC implementation.
*
* n-well (VPB) and substrate (VNB) taps are tied to VPWR/VGND respectively on
* every standard-cell instance (VNB=VGND VPB=VPWR overrides of the library's
* own per-instance defaults) so only VPWR/VGND need to be driven externally.
}
G {}
V {}
S {}
E {}
C {devices/ipin.sym} -1700 0 0 0 {name=pCLK lab=CLK}
C {devices/ipin.sym} -1700 200 0 0 {name=pRSTB lab=RST_B}
C {devices/ipin.sym} -1700 400 0 0 {name=pCOMP lab=COMP_OUT}
C {sky130_stdcells/dfrtp_1.sym} -1000 0 0 0 {name=xringb9 VNB=VGND VPB=VPWR}
C {sky130_stdcells/dfrtp_1.sym} -1000 200 0 0 {name=xringb8 VNB=VGND VPB=VPWR}
C {sky130_stdcells/dfrtp_1.sym} -1000 400 0 0 {name=xringb7 VNB=VGND VPB=VPWR}
C {sky130_stdcells/dfrtp_1.sym} -1000 600 0 0 {name=xringb6 VNB=VGND VPB=VPWR}
C {sky130_stdcells/dfrtp_1.sym} -1000 800 0 0 {name=xringb5 VNB=VGND VPB=VPWR}
C {sky130_stdcells/dfrtp_1.sym} -1000 1000 0 0 {name=xringb4 VNB=VGND VPB=VPWR}
C {sky130_stdcells/dfrtp_1.sym} -1000 1200 0 0 {name=xringb3 VNB=VGND VPB=VPWR}
C {sky130_stdcells/dfrtp_1.sym} -1000 1400 0 0 {name=xringb2 VNB=VGND VPB=VPWR}
C {sky130_stdcells/dfrtp_1.sym} -1000 1600 0 0 {name=xringb1 VNB=VGND VPB=VPWR}
C {sky130_stdcells/dfrtp_1.sym} -1000 1800 0 0 {name=xringb0 VNB=VGND VPB=VPWR}
C {sky130_stdcells/dfrtp_1.sym} -1000 2000 0 0 {name=xringeoc VNB=VGND VPB=VPWR}
C {sky130_stdcells/or4_1.sym} -1000 2600 0 0 {name=xor_g1 VNB=VGND VPB=VPWR}
C {sky130_stdcells/or4_1.sym} -1000 2800 0 0 {name=xor_g2 VNB=VGND VPB=VPWR}
C {sky130_stdcells/or3_1.sym} -1000 3000 0 0 {name=xor_g3 VNB=VGND VPB=VPWR}
C {sky130_stdcells/or3_1.sym} -1000 3200 0 0 {name=xor_busy VNB=VGND VPB=VPWR}
C {sky130_stdcells/inv_1.sym} -1000 3400 0 0 {name=xinv_sample VNB=VGND VPB=VPWR}
* --- BUSY_BITS = OR(PH_B9..PH_B0), PH_EOC excluded (issue #263) -- the
* per-conversion CDAC clear's own gating signal, distinct from the BUSY
* output pin (which still includes PH_EOC). See the long comment above
* the xpre<i>/xclr<i> instances for why this distinction is load-bearing.
C {sky130_stdcells/or2_1.sym} -1000 3600 0 0 {name=xor_g4 VNB=VGND VPB=VPWR}
C {sky130_stdcells/or3_1.sym} -1000 3800 0 0 {name=xor_busybits VNB=VGND VPB=VPWR}
C {sky130_stdcells/mux2_1.sym} 100 0 0 0 {name=xmux9 VNB=VGND VPB=VPWR}
C {sky130_stdcells/dfrtp_1.sym} 700 0 0 0 {name=xbreg9 VNB=VGND VPB=VPWR}
C {sky130_stdcells/mux2_1.sym} 100 200 0 0 {name=xmux8 VNB=VGND VPB=VPWR}
C {sky130_stdcells/dfrtp_1.sym} 700 200 0 0 {name=xbreg8 VNB=VGND VPB=VPWR}
C {sky130_stdcells/mux2_1.sym} 100 400 0 0 {name=xmux7 VNB=VGND VPB=VPWR}
C {sky130_stdcells/dfrtp_1.sym} 700 400 0 0 {name=xbreg7 VNB=VGND VPB=VPWR}
C {sky130_stdcells/mux2_1.sym} 100 600 0 0 {name=xmux6 VNB=VGND VPB=VPWR}
C {sky130_stdcells/dfrtp_1.sym} 700 600 0 0 {name=xbreg6 VNB=VGND VPB=VPWR}
C {sky130_stdcells/mux2_1.sym} 100 800 0 0 {name=xmux5 VNB=VGND VPB=VPWR}
C {sky130_stdcells/dfrtp_1.sym} 700 800 0 0 {name=xbreg5 VNB=VGND VPB=VPWR}
C {sky130_stdcells/mux2_1.sym} 100 1000 0 0 {name=xmux4 VNB=VGND VPB=VPWR}
C {sky130_stdcells/dfrtp_1.sym} 700 1000 0 0 {name=xbreg4 VNB=VGND VPB=VPWR}
C {sky130_stdcells/mux2_1.sym} 100 1200 0 0 {name=xmux3 VNB=VGND VPB=VPWR}
C {sky130_stdcells/dfrtp_1.sym} 700 1200 0 0 {name=xbreg3 VNB=VGND VPB=VPWR}
C {sky130_stdcells/mux2_1.sym} 100 1400 0 0 {name=xmux2 VNB=VGND VPB=VPWR}
C {sky130_stdcells/dfrtp_1.sym} 700 1400 0 0 {name=xbreg2 VNB=VGND VPB=VPWR}
C {sky130_stdcells/mux2_1.sym} 100 1600 0 0 {name=xmux1 VNB=VGND VPB=VPWR}
C {sky130_stdcells/dfrtp_1.sym} 700 1600 0 0 {name=xbreg1 VNB=VGND VPB=VPWR}
C {sky130_stdcells/mux2_1.sym} 100 1800 0 0 {name=xmux0 VNB=VGND VPB=VPWR}
C {sky130_stdcells/dfrtp_1.sym} 700 1800 0 0 {name=xbreg0 VNB=VGND VPB=VPWR}
* --- COMP_EFF = XNOR(COMP_OUT, DOUT9): sign-corrected comparator decision
* for bits 8..0 (issue #263, coupled to the decision-directed CDAC
* switching added in design/sar_adc_top.sch). DOUT9 (this design's free
* sign bit, decided before any of bits 8..0 move) selects which single
* CDAC side each subsequent bit's trial perturbation switches, and that
* switch only ever moves the residual TOWARD zero from the correct
* direction for ITS OWN sign branch -- but the comparator's own polarity
* (VINP-VINN>0 => COMP_OUT=1) is fixed regardless of branch, so "keep the
* trial" means COMP_OUT=1 for the DOUT9=1 (Vd>=0, subtracting) branch and
* COMP_OUT=0 for the DOUT9=0 (Vd<0, adding) branch: the same physical
* decision (keep vs revert) has opposite comparator polarity in the two
* branches. Capturing raw COMP_OUT for both branches turns the DOUT9=0
* branch's search into POSITIVE feedback (an intermediate debug run during
* this issue's own development, with decision-directed CDAC switching in
* place but COMP_EFF not yet added, showed exactly this signature: the
* DOUT9=1 branch searched correctly while the DOUT9=0 branch's magnitude
* bits saturated to 0 or 511, never a graded result). XNOR(COMP_OUT, DOUT9)
* passes COMP_OUT through
* unchanged when DOUT9=1 and inverts it when DOUT9=0 -- exactly the
* per-branch correction needed, and only for bits 8..0 (xmux9 below still
* reads raw COMP_OUT: the sign decision itself needs no correction, it IS
* the branch selector). No mux9/xbreg9 wiring changes.
C {sky130_stdcells/xnor2_1.sym} -400 2200 0 0 {name=xxnor_compeff VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} -460 2180 0 0 {name=l_xnor_a lab=COMP_OUT}
C {devices/lab_pin.sym} -460 2220 0 0 {name=l_xnor_b lab=DOUT9}
C {devices/lab_pin.sym} -340 2200 0 0 {name=l_xnor_y lab=COMP_EFF}
* --- trial-perturbation preset (or2_1) + per-conversion clear (and2_1),
* bits 8..0 only (issue #263). Bit 9 (the free/decision-directed MSB, per
* DR-003 Item 3) is decided directly off the sampled residual with NO
* trial perturbation applied -- that is correct top-plate-sampling
* behavior, not the bug -- so xmux9/xbreg9 above are left untouched.
* For each bit i in 8..0: PRESET<i> = MUXOUT<i> OR PH_B<i+1> (PH_B<i+1>
* is the ring phase signal active the cycle immediately BEFORE bit i's
* own trial phase begins -- the same net already wired as that ring
* stage's own D input above -- so this forces DOUT<i> to the trial value
* 1 at the exact edge that opens bit i's own trial, instead of holding
* whatever was left over from the previous conversion (root cause item
* 1). DFEED<i> = BUSY_BITS AND PRESET<i> additionally forces DOUT<i> to 0
* whenever no bit-trial phase is active, so every not-yet-decided bit
* starts each new conversion cleared rather than carrying the prior
* conversion's residual code into the new search (root cause item 2).
*
* BUSY_BITS -- NOT the pre-existing BUSY output pin -- is the clear's own
* gating signal, and the distinction is load-bearing. BUSY = OR(PH_B9..
* PH_B0, PH_EOC) (all conversion phases, unchanged, still drives the
* PH_SAMPLE/BUSY output pins and sim/full-conversion-transient's phase-
* structure check). BUSY_BITS = OR(PH_B9..PH_B0) ONLY -- PH_EOC excluded
* -- via the added xor_g4/xor_busybits gates below. Gating the clear on
* BUSY (as an earlier draft of this fix did) forces DOUT<i> to 0 starting
* only at the PH_SAMPLE -> next-PH_B9 edge, THE SAME EDGE
* design/sar_adc_top.sch's sampling switch opens on (SAMPLE_INT =
* PH_SAMPLE, bridged directly, issue #263's own re-run campaign caught
* this: 0/9 corners converged, with errors far larger and non-monotonic
* in the input, because the outgoing conversion's CDAC state -- up to
* full-scale -- was being dumped onto the just-opened, now-floating top
* plate). Gating on BUSY_BITS instead moves the actual register
* transition to 0 a full CLK period earlier, at the PH_EOC -> PH_SAMPLE
* edge: bits 8..0 are already 0 by the time SAMPLE begins, so the CDAC
* is settled at its neutral state WHILE the sampling switch is still
* closed (the switch does not open until a whole period later), exactly
* the constraint the issue's own suggested scope names ("the clear must
* land while the sampling switch is still closed, or the clear itself
* perturbs the sampled charge"). Consequence: the decided code is only
* guaranteed stable through PH_EOC now, not through PH_SAMPLE as an
* earlier draft of this schematic assumed --
* sim/full-conversion-transient/gen_full_conversion_tb.py's
* `t_code_read_ns()` reads mid-PH_EOC, not mid-PH_SAMPLE, to match.
C {sky130_stdcells/or2_1.sym} 280 200 0 0 {name=xpre8 VNB=VGND VPB=VPWR}
C {sky130_stdcells/and2_1.sym} 460 200 0 0 {name=xclr8 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 220 180 0 0 {name=lpreA8 lab=MUXOUT8}
C {devices/lab_pin.sym} 220 220 0 0 {name=lpreB8 lab=PH_B9}
C {devices/lab_pin.sym} 340 200 0 0 {name=lpreX8 lab=PRESET8}
C {devices/lab_pin.sym} 400 180 0 0 {name=lclrA8 lab=PRESET8}
C {devices/lab_pin.sym} 400 220 0 0 {name=lclrB8 lab=BUSY_BITS}
C {devices/lab_pin.sym} 520 200 0 0 {name=lclrX8 lab=DFEED8}
C {sky130_stdcells/or2_1.sym} 280 400 0 0 {name=xpre7 VNB=VGND VPB=VPWR}
C {sky130_stdcells/and2_1.sym} 460 400 0 0 {name=xclr7 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 220 380 0 0 {name=lpreA7 lab=MUXOUT7}
C {devices/lab_pin.sym} 220 420 0 0 {name=lpreB7 lab=PH_B8}
C {devices/lab_pin.sym} 340 400 0 0 {name=lpreX7 lab=PRESET7}
C {devices/lab_pin.sym} 400 380 0 0 {name=lclrA7 lab=PRESET7}
C {devices/lab_pin.sym} 400 420 0 0 {name=lclrB7 lab=BUSY_BITS}
C {devices/lab_pin.sym} 520 400 0 0 {name=lclrX7 lab=DFEED7}
C {sky130_stdcells/or2_1.sym} 280 600 0 0 {name=xpre6 VNB=VGND VPB=VPWR}
C {sky130_stdcells/and2_1.sym} 460 600 0 0 {name=xclr6 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 220 580 0 0 {name=lpreA6 lab=MUXOUT6}
C {devices/lab_pin.sym} 220 620 0 0 {name=lpreB6 lab=PH_B7}
C {devices/lab_pin.sym} 340 600 0 0 {name=lpreX6 lab=PRESET6}
C {devices/lab_pin.sym} 400 580 0 0 {name=lclrA6 lab=PRESET6}
C {devices/lab_pin.sym} 400 620 0 0 {name=lclrB6 lab=BUSY_BITS}
C {devices/lab_pin.sym} 520 600 0 0 {name=lclrX6 lab=DFEED6}
C {sky130_stdcells/or2_1.sym} 280 800 0 0 {name=xpre5 VNB=VGND VPB=VPWR}
C {sky130_stdcells/and2_1.sym} 460 800 0 0 {name=xclr5 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 220 780 0 0 {name=lpreA5 lab=MUXOUT5}
C {devices/lab_pin.sym} 220 820 0 0 {name=lpreB5 lab=PH_B6}
C {devices/lab_pin.sym} 340 800 0 0 {name=lpreX5 lab=PRESET5}
C {devices/lab_pin.sym} 400 780 0 0 {name=lclrA5 lab=PRESET5}
C {devices/lab_pin.sym} 400 820 0 0 {name=lclrB5 lab=BUSY_BITS}
C {devices/lab_pin.sym} 520 800 0 0 {name=lclrX5 lab=DFEED5}
C {sky130_stdcells/or2_1.sym} 280 1000 0 0 {name=xpre4 VNB=VGND VPB=VPWR}
C {sky130_stdcells/and2_1.sym} 460 1000 0 0 {name=xclr4 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 220 980 0 0 {name=lpreA4 lab=MUXOUT4}
C {devices/lab_pin.sym} 220 1020 0 0 {name=lpreB4 lab=PH_B5}
C {devices/lab_pin.sym} 340 1000 0 0 {name=lpreX4 lab=PRESET4}
C {devices/lab_pin.sym} 400 980 0 0 {name=lclrA4 lab=PRESET4}
C {devices/lab_pin.sym} 400 1020 0 0 {name=lclrB4 lab=BUSY_BITS}
C {devices/lab_pin.sym} 520 1000 0 0 {name=lclrX4 lab=DFEED4}
C {sky130_stdcells/or2_1.sym} 280 1200 0 0 {name=xpre3 VNB=VGND VPB=VPWR}
C {sky130_stdcells/and2_1.sym} 460 1200 0 0 {name=xclr3 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 220 1180 0 0 {name=lpreA3 lab=MUXOUT3}
C {devices/lab_pin.sym} 220 1220 0 0 {name=lpreB3 lab=PH_B4}
C {devices/lab_pin.sym} 340 1200 0 0 {name=lpreX3 lab=PRESET3}
C {devices/lab_pin.sym} 400 1180 0 0 {name=lclrA3 lab=PRESET3}
C {devices/lab_pin.sym} 400 1220 0 0 {name=lclrB3 lab=BUSY_BITS}
C {devices/lab_pin.sym} 520 1200 0 0 {name=lclrX3 lab=DFEED3}
C {sky130_stdcells/or2_1.sym} 280 1400 0 0 {name=xpre2 VNB=VGND VPB=VPWR}
C {sky130_stdcells/and2_1.sym} 460 1400 0 0 {name=xclr2 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 220 1380 0 0 {name=lpreA2 lab=MUXOUT2}
C {devices/lab_pin.sym} 220 1420 0 0 {name=lpreB2 lab=PH_B3}
C {devices/lab_pin.sym} 340 1400 0 0 {name=lpreX2 lab=PRESET2}
C {devices/lab_pin.sym} 400 1380 0 0 {name=lclrA2 lab=PRESET2}
C {devices/lab_pin.sym} 400 1420 0 0 {name=lclrB2 lab=BUSY_BITS}
C {devices/lab_pin.sym} 520 1400 0 0 {name=lclrX2 lab=DFEED2}
C {sky130_stdcells/or2_1.sym} 280 1600 0 0 {name=xpre1 VNB=VGND VPB=VPWR}
C {sky130_stdcells/and2_1.sym} 460 1600 0 0 {name=xclr1 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 220 1580 0 0 {name=lpreA1 lab=MUXOUT1}
C {devices/lab_pin.sym} 220 1620 0 0 {name=lpreB1 lab=PH_B2}
C {devices/lab_pin.sym} 340 1600 0 0 {name=lpreX1 lab=PRESET1}
C {devices/lab_pin.sym} 400 1580 0 0 {name=lclrA1 lab=PRESET1}
C {devices/lab_pin.sym} 400 1620 0 0 {name=lclrB1 lab=BUSY_BITS}
C {devices/lab_pin.sym} 520 1600 0 0 {name=lclrX1 lab=DFEED1}
C {sky130_stdcells/or2_1.sym} 280 1800 0 0 {name=xpre0 VNB=VGND VPB=VPWR}
C {sky130_stdcells/and2_1.sym} 460 1800 0 0 {name=xclr0 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 220 1780 0 0 {name=lpreA0 lab=MUXOUT0}
C {devices/lab_pin.sym} 220 1820 0 0 {name=lpreB0 lab=PH_B1}
C {devices/lab_pin.sym} 340 1800 0 0 {name=lpreX0 lab=PRESET0}
C {devices/lab_pin.sym} 400 1780 0 0 {name=lclrA0 lab=PRESET0}
C {devices/lab_pin.sym} 400 1820 0 0 {name=lclrB0 lab=BUSY_BITS}
C {devices/lab_pin.sym} 520 1800 0 0 {name=lclrX0 lab=DFEED0}
C {devices/opin.sym} 1400 0 0 0 {name=pPH_B9 lab=PH_B9}
C {devices/opin.sym} 1400 200 0 0 {name=pPH_B8 lab=PH_B8}
C {devices/opin.sym} 1400 400 0 0 {name=pPH_B7 lab=PH_B7}
C {devices/opin.sym} 1400 600 0 0 {name=pPH_B6 lab=PH_B6}
C {devices/opin.sym} 1400 800 0 0 {name=pPH_B5 lab=PH_B5}
C {devices/opin.sym} 1400 1000 0 0 {name=pPH_B4 lab=PH_B4}
C {devices/opin.sym} 1400 1200 0 0 {name=pPH_B3 lab=PH_B3}
C {devices/opin.sym} 1400 1400 0 0 {name=pPH_B2 lab=PH_B2}
C {devices/opin.sym} 1400 1600 0 0 {name=pPH_B1 lab=PH_B1}
C {devices/opin.sym} 1400 1800 0 0 {name=pPH_B0 lab=PH_B0}
C {devices/opin.sym} 1400 2000 0 0 {name=pPH_EOC lab=PH_EOC}
C {devices/opin.sym} 1400 2400 0 0 {name=pSAMPLE lab=PH_SAMPLE}
C {devices/opin.sym} 1400 2600 0 0 {name=pBUSY lab=BUSY}
C {devices/opin.sym} 2000 0 0 0 {name=pDOUT9 lab=DOUT9}
C {devices/opin.sym} 2000 200 0 0 {name=pDOUT8 lab=DOUT8}
C {devices/opin.sym} 2000 400 0 0 {name=pDOUT7 lab=DOUT7}
C {devices/opin.sym} 2000 600 0 0 {name=pDOUT6 lab=DOUT6}
C {devices/opin.sym} 2000 800 0 0 {name=pDOUT5 lab=DOUT5}
C {devices/opin.sym} 2000 1000 0 0 {name=pDOUT4 lab=DOUT4}
C {devices/opin.sym} 2000 1200 0 0 {name=pDOUT3 lab=DOUT3}
C {devices/opin.sym} 2000 1400 0 0 {name=pDOUT2 lab=DOUT2}
C {devices/opin.sym} 2000 1600 0 0 {name=pDOUT1 lab=DOUT1}
C {devices/opin.sym} 2000 1800 0 0 {name=pDOUT0 lab=DOUT0}
C {devices/lab_pin.sym} -1700 0 0 0 {name=l1 lab=CLK}
C {devices/lab_pin.sym} -1700 200 0 0 {name=l2 lab=RST_B}
C {devices/lab_pin.sym} -1700 400 0 0 {name=l3 lab=COMP_OUT}
C {devices/lab_pin.sym} -1090 -20 0 0 {name=l4 lab=CLK}
C {devices/lab_pin.sym} -1090 0 0 0 {name=l5 lab=PH_SAMPLE}
C {devices/lab_pin.sym} -1090 20 0 0 {name=l6 lab=RST_B}
C {devices/lab_pin.sym} -910 -20 0 0 {name=l7 lab=PH_B9}
C {devices/lab_pin.sym} -1090 180 0 0 {name=l8 lab=CLK}
C {devices/lab_pin.sym} -1090 200 0 0 {name=l9 lab=PH_B9}
C {devices/lab_pin.sym} -1090 220 0 0 {name=l10 lab=RST_B}
C {devices/lab_pin.sym} -910 180 0 0 {name=l11 lab=PH_B8}
C {devices/lab_pin.sym} -1090 380 0 0 {name=l12 lab=CLK}
C {devices/lab_pin.sym} -1090 400 0 0 {name=l13 lab=PH_B8}
C {devices/lab_pin.sym} -1090 420 0 0 {name=l14 lab=RST_B}
C {devices/lab_pin.sym} -910 380 0 0 {name=l15 lab=PH_B7}
C {devices/lab_pin.sym} -1090 580 0 0 {name=l16 lab=CLK}
C {devices/lab_pin.sym} -1090 600 0 0 {name=l17 lab=PH_B7}
C {devices/lab_pin.sym} -1090 620 0 0 {name=l18 lab=RST_B}
C {devices/lab_pin.sym} -910 580 0 0 {name=l19 lab=PH_B6}
C {devices/lab_pin.sym} -1090 780 0 0 {name=l20 lab=CLK}
C {devices/lab_pin.sym} -1090 800 0 0 {name=l21 lab=PH_B6}
C {devices/lab_pin.sym} -1090 820 0 0 {name=l22 lab=RST_B}
C {devices/lab_pin.sym} -910 780 0 0 {name=l23 lab=PH_B5}
C {devices/lab_pin.sym} -1090 980 0 0 {name=l24 lab=CLK}
C {devices/lab_pin.sym} -1090 1000 0 0 {name=l25 lab=PH_B5}
C {devices/lab_pin.sym} -1090 1020 0 0 {name=l26 lab=RST_B}
C {devices/lab_pin.sym} -910 980 0 0 {name=l27 lab=PH_B4}
C {devices/lab_pin.sym} -1090 1180 0 0 {name=l28 lab=CLK}
C {devices/lab_pin.sym} -1090 1200 0 0 {name=l29 lab=PH_B4}
C {devices/lab_pin.sym} -1090 1220 0 0 {name=l30 lab=RST_B}
C {devices/lab_pin.sym} -910 1180 0 0 {name=l31 lab=PH_B3}
C {devices/lab_pin.sym} -1090 1380 0 0 {name=l32 lab=CLK}
C {devices/lab_pin.sym} -1090 1400 0 0 {name=l33 lab=PH_B3}
C {devices/lab_pin.sym} -1090 1420 0 0 {name=l34 lab=RST_B}
C {devices/lab_pin.sym} -910 1380 0 0 {name=l35 lab=PH_B2}
C {devices/lab_pin.sym} -1090 1580 0 0 {name=l36 lab=CLK}
C {devices/lab_pin.sym} -1090 1600 0 0 {name=l37 lab=PH_B2}
C {devices/lab_pin.sym} -1090 1620 0 0 {name=l38 lab=RST_B}
C {devices/lab_pin.sym} -910 1580 0 0 {name=l39 lab=PH_B1}
C {devices/lab_pin.sym} -1090 1780 0 0 {name=l40 lab=CLK}
C {devices/lab_pin.sym} -1090 1800 0 0 {name=l41 lab=PH_B1}
C {devices/lab_pin.sym} -1090 1820 0 0 {name=l42 lab=RST_B}
C {devices/lab_pin.sym} -910 1780 0 0 {name=l43 lab=PH_B0}
C {devices/lab_pin.sym} -1090 1980 0 0 {name=l44 lab=CLK}
C {devices/lab_pin.sym} -1090 2000 0 0 {name=l45 lab=PH_B0}
C {devices/lab_pin.sym} -1090 2020 0 0 {name=l46 lab=RST_B}
C {devices/lab_pin.sym} -910 1980 0 0 {name=l47 lab=PH_EOC}
C {devices/lab_pin.sym} -1060 2540 0 0 {name=l48 lab=PH_B9}
C {devices/lab_pin.sym} -1060 2580 0 0 {name=l49 lab=PH_B8}
C {devices/lab_pin.sym} -1060 2620 0 0 {name=l50 lab=PH_B7}
C {devices/lab_pin.sym} -1060 2660 0 0 {name=l51 lab=PH_B6}
C {devices/lab_pin.sym} -940 2600 0 0 {name=l52 lab=ORG1}
C {devices/lab_pin.sym} -1060 2740 0 0 {name=l53 lab=PH_B5}
C {devices/lab_pin.sym} -1060 2780 0 0 {name=l54 lab=PH_B4}
C {devices/lab_pin.sym} -1060 2820 0 0 {name=l55 lab=PH_B3}
C {devices/lab_pin.sym} -1060 2860 0 0 {name=l56 lab=PH_B2}
C {devices/lab_pin.sym} -940 2800 0 0 {name=l57 lab=ORG2}
C {devices/lab_pin.sym} -1060 2960 0 0 {name=l58 lab=PH_B1}
C {devices/lab_pin.sym} -1060 3000 0 0 {name=l59 lab=PH_B0}
C {devices/lab_pin.sym} -1060 3040 0 0 {name=l60 lab=PH_EOC}
C {devices/lab_pin.sym} -940 3000 0 0 {name=l61 lab=ORG3}
C {devices/lab_pin.sym} -1060 3160 0 0 {name=l62 lab=ORG1}
C {devices/lab_pin.sym} -1060 3200 0 0 {name=l63 lab=ORG2}
C {devices/lab_pin.sym} -1060 3240 0 0 {name=l64 lab=ORG3}
C {devices/lab_pin.sym} -940 3200 0 0 {name=l65 lab=BUSY}
C {devices/lab_pin.sym} -1040 3400 0 0 {name=l66 lab=BUSY}
C {devices/lab_pin.sym} -960 3400 0 0 {name=l67 lab=PH_SAMPLE}
C {devices/lab_pin.sym} -1060 3580 0 0 {name=l_bb1 lab=PH_B1}
C {devices/lab_pin.sym} -1060 3620 0 0 {name=l_bb2 lab=PH_B0}
C {devices/lab_pin.sym} -940 3600 0 0 {name=l_bb3 lab=ORG4}
C {devices/lab_pin.sym} -1060 3760 0 0 {name=l_bb4 lab=ORG1}
C {devices/lab_pin.sym} -1060 3800 0 0 {name=l_bb5 lab=ORG2}
C {devices/lab_pin.sym} -1060 3840 0 0 {name=l_bb6 lab=ORG4}
C {devices/lab_pin.sym} -940 3800 0 0 {name=l_bb7 lab=BUSY_BITS}
C {devices/lab_pin.sym} 60 -20 0 0 {name=l68 lab=DOUT9}
C {devices/lab_pin.sym} 60 20 0 0 {name=l69 lab=COMP_OUT}
C {devices/lab_pin.sym} 60 60 0 0 {name=l70 lab=PH_B9}
C {devices/lab_pin.sym} 140 0 0 0 {name=l71 lab=MUXOUT9}
C {devices/lab_pin.sym} 610 -20 0 0 {name=l72 lab=CLK}
C {devices/lab_pin.sym} 610 0 0 0 {name=l73 lab=MUXOUT9}
C {devices/lab_pin.sym} 610 20 0 0 {name=l74 lab=RST_B}
C {devices/lab_pin.sym} 790 -20 0 0 {name=l75 lab=DOUT9}
C {devices/lab_pin.sym} 60 180 0 0 {name=l76 lab=DOUT8}
C {devices/lab_pin.sym} 60 220 0 0 {name=l77 lab=COMP_EFF}
C {devices/lab_pin.sym} 60 260 0 0 {name=l78 lab=PH_B8}
C {devices/lab_pin.sym} 140 200 0 0 {name=l79 lab=MUXOUT8}
C {devices/lab_pin.sym} 610 180 0 0 {name=l80 lab=CLK}
C {devices/lab_pin.sym} 610 200 0 0 {name=l81 lab=DFEED8}
C {devices/lab_pin.sym} 610 220 0 0 {name=l82 lab=RST_B}
C {devices/lab_pin.sym} 790 180 0 0 {name=l83 lab=DOUT8}
C {devices/lab_pin.sym} 60 380 0 0 {name=l84 lab=DOUT7}
C {devices/lab_pin.sym} 60 420 0 0 {name=l85 lab=COMP_EFF}
C {devices/lab_pin.sym} 60 460 0 0 {name=l86 lab=PH_B7}
C {devices/lab_pin.sym} 140 400 0 0 {name=l87 lab=MUXOUT7}
C {devices/lab_pin.sym} 610 380 0 0 {name=l88 lab=CLK}
C {devices/lab_pin.sym} 610 400 0 0 {name=l89 lab=DFEED7}
C {devices/lab_pin.sym} 610 420 0 0 {name=l90 lab=RST_B}
C {devices/lab_pin.sym} 790 380 0 0 {name=l91 lab=DOUT7}
C {devices/lab_pin.sym} 60 580 0 0 {name=l92 lab=DOUT6}
C {devices/lab_pin.sym} 60 620 0 0 {name=l93 lab=COMP_EFF}
C {devices/lab_pin.sym} 60 660 0 0 {name=l94 lab=PH_B6}
C {devices/lab_pin.sym} 140 600 0 0 {name=l95 lab=MUXOUT6}
C {devices/lab_pin.sym} 610 580 0 0 {name=l96 lab=CLK}
C {devices/lab_pin.sym} 610 600 0 0 {name=l97 lab=DFEED6}
C {devices/lab_pin.sym} 610 620 0 0 {name=l98 lab=RST_B}
C {devices/lab_pin.sym} 790 580 0 0 {name=l99 lab=DOUT6}
C {devices/lab_pin.sym} 60 780 0 0 {name=l100 lab=DOUT5}
C {devices/lab_pin.sym} 60 820 0 0 {name=l101 lab=COMP_EFF}
C {devices/lab_pin.sym} 60 860 0 0 {name=l102 lab=PH_B5}
C {devices/lab_pin.sym} 140 800 0 0 {name=l103 lab=MUXOUT5}
C {devices/lab_pin.sym} 610 780 0 0 {name=l104 lab=CLK}
C {devices/lab_pin.sym} 610 800 0 0 {name=l105 lab=DFEED5}
C {devices/lab_pin.sym} 610 820 0 0 {name=l106 lab=RST_B}
C {devices/lab_pin.sym} 790 780 0 0 {name=l107 lab=DOUT5}
C {devices/lab_pin.sym} 60 980 0 0 {name=l108 lab=DOUT4}
C {devices/lab_pin.sym} 60 1020 0 0 {name=l109 lab=COMP_EFF}
C {devices/lab_pin.sym} 60 1060 0 0 {name=l110 lab=PH_B4}
C {devices/lab_pin.sym} 140 1000 0 0 {name=l111 lab=MUXOUT4}
C {devices/lab_pin.sym} 610 980 0 0 {name=l112 lab=CLK}
C {devices/lab_pin.sym} 610 1000 0 0 {name=l113 lab=DFEED4}
C {devices/lab_pin.sym} 610 1020 0 0 {name=l114 lab=RST_B}
C {devices/lab_pin.sym} 790 980 0 0 {name=l115 lab=DOUT4}
C {devices/lab_pin.sym} 60 1180 0 0 {name=l116 lab=DOUT3}
C {devices/lab_pin.sym} 60 1220 0 0 {name=l117 lab=COMP_EFF}
C {devices/lab_pin.sym} 60 1260 0 0 {name=l118 lab=PH_B3}
C {devices/lab_pin.sym} 140 1200 0 0 {name=l119 lab=MUXOUT3}
C {devices/lab_pin.sym} 610 1180 0 0 {name=l120 lab=CLK}
C {devices/lab_pin.sym} 610 1200 0 0 {name=l121 lab=DFEED3}
C {devices/lab_pin.sym} 610 1220 0 0 {name=l122 lab=RST_B}
C {devices/lab_pin.sym} 790 1180 0 0 {name=l123 lab=DOUT3}
C {devices/lab_pin.sym} 60 1380 0 0 {name=l124 lab=DOUT2}
C {devices/lab_pin.sym} 60 1420 0 0 {name=l125 lab=COMP_EFF}
C {devices/lab_pin.sym} 60 1460 0 0 {name=l126 lab=PH_B2}
C {devices/lab_pin.sym} 140 1400 0 0 {name=l127 lab=MUXOUT2}
C {devices/lab_pin.sym} 610 1380 0 0 {name=l128 lab=CLK}
C {devices/lab_pin.sym} 610 1400 0 0 {name=l129 lab=DFEED2}
C {devices/lab_pin.sym} 610 1420 0 0 {name=l130 lab=RST_B}
C {devices/lab_pin.sym} 790 1380 0 0 {name=l131 lab=DOUT2}
C {devices/lab_pin.sym} 60 1580 0 0 {name=l132 lab=DOUT1}
C {devices/lab_pin.sym} 60 1620 0 0 {name=l133 lab=COMP_EFF}
C {devices/lab_pin.sym} 60 1660 0 0 {name=l134 lab=PH_B1}
C {devices/lab_pin.sym} 140 1600 0 0 {name=l135 lab=MUXOUT1}
C {devices/lab_pin.sym} 610 1580 0 0 {name=l136 lab=CLK}
C {devices/lab_pin.sym} 610 1600 0 0 {name=l137 lab=DFEED1}
C {devices/lab_pin.sym} 610 1620 0 0 {name=l138 lab=RST_B}
C {devices/lab_pin.sym} 790 1580 0 0 {name=l139 lab=DOUT1}
C {devices/lab_pin.sym} 60 1780 0 0 {name=l140 lab=DOUT0}
C {devices/lab_pin.sym} 60 1820 0 0 {name=l141 lab=COMP_EFF}
C {devices/lab_pin.sym} 60 1860 0 0 {name=l142 lab=PH_B0}
C {devices/lab_pin.sym} 140 1800 0 0 {name=l143 lab=MUXOUT0}
C {devices/lab_pin.sym} 610 1780 0 0 {name=l144 lab=CLK}
C {devices/lab_pin.sym} 610 1800 0 0 {name=l145 lab=DFEED0}
C {devices/lab_pin.sym} 610 1820 0 0 {name=l146 lab=RST_B}
C {devices/lab_pin.sym} 790 1780 0 0 {name=l147 lab=DOUT0}
C {devices/lab_pin.sym} 1400 0 0 0 {name=l148 lab=PH_B9}
C {devices/lab_pin.sym} 1400 200 0 0 {name=l149 lab=PH_B8}
C {devices/lab_pin.sym} 1400 400 0 0 {name=l150 lab=PH_B7}
C {devices/lab_pin.sym} 1400 600 0 0 {name=l151 lab=PH_B6}
C {devices/lab_pin.sym} 1400 800 0 0 {name=l152 lab=PH_B5}
C {devices/lab_pin.sym} 1400 1000 0 0 {name=l153 lab=PH_B4}
C {devices/lab_pin.sym} 1400 1200 0 0 {name=l154 lab=PH_B3}
C {devices/lab_pin.sym} 1400 1400 0 0 {name=l155 lab=PH_B2}
C {devices/lab_pin.sym} 1400 1600 0 0 {name=l156 lab=PH_B1}
C {devices/lab_pin.sym} 1400 1800 0 0 {name=l157 lab=PH_B0}
C {devices/lab_pin.sym} 1400 2000 0 0 {name=l158 lab=PH_EOC}
C {devices/lab_pin.sym} 1400 2400 0 0 {name=l159 lab=PH_SAMPLE}
C {devices/lab_pin.sym} 1400 2600 0 0 {name=l160 lab=BUSY}
C {devices/lab_pin.sym} 2000 0 0 0 {name=l161 lab=DOUT9}
C {devices/lab_pin.sym} 2000 200 0 0 {name=l162 lab=DOUT8}
C {devices/lab_pin.sym} 2000 400 0 0 {name=l163 lab=DOUT7}
C {devices/lab_pin.sym} 2000 600 0 0 {name=l164 lab=DOUT6}
C {devices/lab_pin.sym} 2000 800 0 0 {name=l165 lab=DOUT5}
C {devices/lab_pin.sym} 2000 1000 0 0 {name=l166 lab=DOUT4}
C {devices/lab_pin.sym} 2000 1200 0 0 {name=l167 lab=DOUT3}
C {devices/lab_pin.sym} 2000 1400 0 0 {name=l168 lab=DOUT2}
C {devices/lab_pin.sym} 2000 1600 0 0 {name=l169 lab=DOUT1}
C {devices/lab_pin.sym} 2000 1800 0 0 {name=l170 lab=DOUT0}

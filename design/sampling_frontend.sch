v {xschem version=3.4.7 file_version=1.2
* sampling_frontend.sch -- SAR ADC sampling front end (issue #52): input
* switches, common-mode reference switching, sample/hold clocking. This is
* sub-block 1 of #24's decomposition (#23 tracker); it does NOT depend on
* the CDAC array (#53), comparator (#54), or SAR logic (#55) existing.
*
* ============================================================================
* TOPOLOGY / DOCUMENTATION (required alongside the schematic per #52's AC)
* ============================================================================
*
* Devices: every instance below is nfet_01v8/pfet_01v8 (ratified 1.8V core
* flavor, DR-001) or a sky130_fd_pr__cap_mim_m3_1 MiM capacitor. No
* *_g5v0d10v5 or other higher-voltage device appears anywhere in this
* schematic -- the DR-002 tripwire (spec/target-spec.md) is NOT triggered.
*
* -- Per-side bootstrapped sampling switch (Msw_{p,n} + Sa/Sb/Scn/Scp/Sd/Se +
*    Cboot_{p,n}) --
* Rationale (DR-001 Consequence #4 / DR-004): at V_REF = VDD = 1.8V
* (DR-003 Item 1, provisional pending #27), a plain switch gated at VDD
* loses essentially all overdrive as the sampled input approaches VDD, so a
* gate-bootstrapped switch is used on BOTH differential inputs (VINP,
* VINN), not just one -- input full-scale spans the same range on either
* side of VCM = V_REF/2 = 0.9V.
*
* Mechanism: Cboot is precharged to VDD (top plate "BOOST", bottom plate
* "BSBOT") during the hold phase (SAMPLE=0): Sa (pfet) pulls BOOST to VDD,
* Sb (nfet) pulls BSBOT to GND, and Sd (nfet) independently pulls the
* switch's own gate node G to GND (guaranteeing Msw is OFF -- G is a node
* distinct from BOOST while Se is open, so the two "off-phase" precharge
* targets (BOOST=VDD, G=GND) do not conflict). When SAMPLE goes high: Sa,
* Sb, Sd open; Scn/Scp (an nfet+pfet transmission gate, needed because the
* input can be anywhere in the full [0, VDD] range and neither device alone
* has adequate overdrive at both rails) connect BSBOT to the analog input,
* and Se (pfet) connects G to BOOST. Because Cboot's charge is
* (approximately) conserved while BSBOT jumps from 0 to VIN, BOOST --and
* hence Msw's gate-- rises to approximately VIN + VDD, holding Msw's V_gs
* near VDD (constant, NOT degrading as VIN approaches the rail) instead of
* the VDD - VIN a plain switch would be left with.
*
* Floating-body note (verified against a real leakage bug found while
* deriving this circuit -- see spec/decision-records/DR-004): Sa and Se
* both tie their PFET body to the BOOST node itself (not to a fixed VDD
* well), because BOOST rises above VDD during sampling; a fixed-VDD body
* would forward-bias the drain/body junction once BOOST exceeds VDD by a
* diode drop, injecting substrate current and materially degrading the
* boosted voltage. Tying body=source=drain-side-node keeps every PFET
* junction here reverse-biased across the full input range.
*
* Sa/Sd sizing (L=0.5um, NOT minimum length): found and fixed during this
* circuit's own verification, not a stylistic choice -- see DR-004 Item 3
* for the full derivation. At minimum length (L=0.15um, matching every other
* switch here), Sa/Sd's off-state subthreshold leakage drooped the boosted
* BOOST_x/G_x node enough to produce a real, quantified 120mV in-sample
* settling error at VIN near the rail (verified with a long-transient check:
* the boosted node asymptoted to ~2.03V instead of the ideal ~3.4V at
* VIN=1.6V). Lengthening Sa/Sd to L=0.5um (W=1um unchanged) fixes this --
* in-sample settling is now sub-mV at every tested point, per
* sim/sampling-frontend/records/20260821-072657-433a294.md.
*
* Known, named-not-closed limitation (see DR-004 "Open items" and issue #61,
* NOT a settled problem): even with the Sa/Sd fix above, TOP_P/TOP_N move
* several hundred mV single-ended -- roughly two orders of magnitude above
* the provisional differential LSB -- within a few ns of the SAMPLE falling
* edge (i.e. AFTER correct in-sample settling, at the sample-to-hold
* transition). This is real, reproduced circuit behavior, not a measurement
* artifact. Diagnostic work ruled out a simple break-before-make fix (adding
* 2-10ns of dead time between SAMPLE/SAMPLEB reduced but did not eliminate
* it) and points at a common-mode capacitive kick onto the floating
* TOP_x/BPREF_x node pair from the switching SAMPLE/SAMPLEB signals, not
* fully root-caused. This does NOT invalidate the in-sample settling result
* above (a distinct measurement, at a distinct point in the cycle), but it
* IS a real, open, quantified risk to this front end's actual sample-and-
* HOLD function, tracked in issue #61 -- not something #52 resolves.
*
* -- Common-mode / reference switching (Cmswn_{p,n}, Cmswp_{p,n}) --
* Per the differential top-plate-sampling architecture in
* spec/target-spec.md's Architecture row: the per-side sampling node TOP_P
* / TOP_N is what a future CDAC array's top plate would be (the array
* itself, and its bit-trial bottom-plate switching, is #53's scope, out of
* this sub-block). This sub-block instead defines what the array's bottom
* plate is referenced to *during sampling*: a transmission-gate switch
* (Cmswn+Cmswp, gated by the same SAMPLE/SAMPLEB pair as the input
* switches) connects the bottom-plate reference node (BPREF_P / BPREF_N) to
* an external common-mode reference VCM while SAMPLE is high, then isolates
* it (floating, handed off to #53's DAC-switch network) once SAMPLE goes
* low. VCM = V_REF/2 = 0.9V is the DR-003 (provisional, pending #27)
* recommendation; this is a plain (non-bootstrapped) transmission gate
* because 0.9V is the best-case operating point for a fixed-level switch
* (equal, moderate overdrive on both the nfet and pfet half), unlike the
* full-range analog input the Msw/Scn/Scp devices must pass.
*
* Csamp_{p,n} are lumped PLACEHOLDER capacitors standing in for the not-yet
* -drawn CDAC array's total per-side capacitance (C_side, #53's scope) --
* NOT a claim about the array's actual unit-cell/array structure. Sized
* per DR-003's provisional C_side ~= 4.43 pF recommendation (itself
* pending #27); see spec/decision-records/DR-004-sampling-frontend-sizing.md.
*
* -- Sample/hold clocking (Invp/Invn) --
* This sub-block takes a single external phase, SAMPLE (1 = sample/track,
* 0 = hold), and generates its complement SAMPLEB on-die via one inverter,
* shared by both input switches and both CM-reference switches. The full
* non-overlapping multi-phase SAR clock generator is explicitly #55's scope
* ("SAR logic / sequencer ... plus clock/phase generation"), not this one;
* sim/sampling-frontend/'s testbench drives SAMPLE with an ideal pulse
* source standing in for that future generator.
*
* -- Net-label convention --
* Every connection below is made through devices/lab_pin.sym (or
* devices/gnd.sym for GND) rather than hand-routed wires: two pins with the
* same `lab=` text are the same net regardless of drawn geometry. This
* schematic was authored, and its connectivity independently checked
* against a hand-verified raw-SPICE prototype, without interactive GUI
* feedback -- see spec/decision-records/DR-004 for how it was verified
* (xschem netlist diffed against sim/sampling-frontend/'s transient run).
* A future pass may re-route it with visible wires for readability; that is
* a cosmetic change with no netlist effect.
}
G {}
K {}
V {}
S {}
E {}
C {sky130_fd_pr/nfet_01v8.sym} 0 0 0 0 {name=Msw_p W=2 L=0.15 nf=1 mult=1}
C {devices/lab_pin.sym} 20 -30 0 0 {name=l1 lab=VINP}
C {devices/lab_pin.sym} -20 0 0 0 {name=l2 lab=G_P}
C {devices/lab_pin.sym} 20 30 0 0 {name=l3 lab=TOP_P}
C {devices/gnd.sym} 20 0 0 0 {name=lgnd4 lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 300 0 0 0 {name=Sa_p W=1 L=0.5 nf=1 mult=1}
C {devices/lab_pin.sym} 320 30 0 0 {name=l5 lab=BOOST_P}
C {devices/lab_pin.sym} 280 0 0 0 {name=l6 lab=SAMPLE}
C {devices/lab_pin.sym} 320 -30 0 0 {name=l7 lab=VDD}
C {devices/lab_pin.sym} 320 0 0 0 {name=l8 lab=BOOST_P}
C {sky130_fd_pr/nfet_01v8.sym} 600 0 0 0 {name=Sb_p W=1 L=0.15 nf=1 mult=1}
C {devices/lab_pin.sym} 620 -30 0 0 {name=l9 lab=BSBOT_P}
C {devices/lab_pin.sym} 580 0 0 0 {name=l10 lab=SAMPLEB}
C {devices/gnd.sym} 620 30 0 0 {name=lgnd11 lab=GND}
C {devices/gnd.sym} 620 0 0 0 {name=lgnd12 lab=GND}
C {sky130_fd_pr/nfet_01v8.sym} 900 0 0 0 {name=Scn_p W=1 L=0.15 nf=1 mult=1}
C {devices/lab_pin.sym} 920 -30 0 0 {name=l13 lab=BSBOT_P}
C {devices/lab_pin.sym} 880 0 0 0 {name=l14 lab=SAMPLE}
C {devices/lab_pin.sym} 920 30 0 0 {name=l15 lab=VINP}
C {devices/gnd.sym} 920 0 0 0 {name=lgnd16 lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 1200 0 0 0 {name=Scp_p W=1 L=0.15 nf=1 mult=1}
C {devices/lab_pin.sym} 1220 30 0 0 {name=l17 lab=BSBOT_P}
C {devices/lab_pin.sym} 1180 0 0 0 {name=l18 lab=SAMPLEB}
C {devices/lab_pin.sym} 1220 -30 0 0 {name=l19 lab=VINP}
C {devices/lab_pin.sym} 1220 0 0 0 {name=l20 lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} 1500 0 0 0 {name=Sd_p W=1 L=0.5 nf=1 mult=1}
C {devices/lab_pin.sym} 1520 -30 0 0 {name=l21 lab=G_P}
C {devices/lab_pin.sym} 1480 0 0 0 {name=l22 lab=SAMPLEB}
C {devices/gnd.sym} 1520 30 0 0 {name=lgnd23 lab=GND}
C {devices/gnd.sym} 1520 0 0 0 {name=lgnd24 lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 0 300 0 0 {name=Se_p W=1 L=0.15 nf=1 mult=1}
C {devices/lab_pin.sym} 20 330 0 0 {name=l25 lab=G_P}
C {devices/lab_pin.sym} -20 300 0 0 {name=l26 lab=SAMPLEB}
C {devices/lab_pin.sym} 20 270 0 0 {name=l27 lab=BOOST_P}
C {devices/lab_pin.sym} 20 300 0 0 {name=l28 lab=BOOST_P}
C {sky130_fd_pr/nfet_01v8.sym} 300 300 0 0 {name=Cmswn_p W=1 L=0.15 nf=1 mult=1}
C {devices/lab_pin.sym} 320 270 0 0 {name=l29 lab=BPREF_P}
C {devices/lab_pin.sym} 280 300 0 0 {name=l30 lab=SAMPLE}
C {devices/lab_pin.sym} 320 330 0 0 {name=l31 lab=VCM}
C {devices/gnd.sym} 320 300 0 0 {name=lgnd32 lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 600 300 0 0 {name=Cmswp_p W=1 L=0.15 nf=1 mult=1}
C {devices/lab_pin.sym} 620 330 0 0 {name=l33 lab=BPREF_P}
C {devices/lab_pin.sym} 580 300 0 0 {name=l34 lab=SAMPLEB}
C {devices/lab_pin.sym} 620 270 0 0 {name=l35 lab=VCM}
C {devices/lab_pin.sym} 620 300 0 0 {name=l36 lab=VDD}
C {sky130_fd_pr/cap_mim_m3_1.sym} 900 300 0 0 {name=Cboot_p model=cap_mim_m3_1 W=9.8 L=9.8 MF=1 spiceprefix=X}
C {devices/lab_pin.sym} 900 270 0 0 {name=l37 lab=BOOST_P}
C {devices/lab_pin.sym} 900 330 0 0 {name=l38 lab=BSBOT_P}
C {sky130_fd_pr/cap_mim_m3_1.sym} 1200 300 0 0 {name=Csamp_p model=cap_mim_m3_1 W=46.9 L=46.9 MF=1 spiceprefix=X}
C {devices/lab_pin.sym} 1200 270 0 0 {name=l39 lab=TOP_P}
C {devices/lab_pin.sym} 1200 330 0 0 {name=l40 lab=BPREF_P}
C {sky130_fd_pr/nfet_01v8.sym} 0 600 0 0 {name=Msw_n W=2 L=0.15 nf=1 mult=1}
C {devices/lab_pin.sym} 20 570 0 0 {name=l41 lab=VINN}
C {devices/lab_pin.sym} -20 600 0 0 {name=l42 lab=G_N}
C {devices/lab_pin.sym} 20 630 0 0 {name=l43 lab=TOP_N}
C {devices/gnd.sym} 20 600 0 0 {name=lgnd44 lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 300 600 0 0 {name=Sa_n W=1 L=0.5 nf=1 mult=1}
C {devices/lab_pin.sym} 320 630 0 0 {name=l45 lab=BOOST_N}
C {devices/lab_pin.sym} 280 600 0 0 {name=l46 lab=SAMPLE}
C {devices/lab_pin.sym} 320 570 0 0 {name=l47 lab=VDD}
C {devices/lab_pin.sym} 320 600 0 0 {name=l48 lab=BOOST_N}
C {sky130_fd_pr/nfet_01v8.sym} 600 600 0 0 {name=Sb_n W=1 L=0.15 nf=1 mult=1}
C {devices/lab_pin.sym} 620 570 0 0 {name=l49 lab=BSBOT_N}
C {devices/lab_pin.sym} 580 600 0 0 {name=l50 lab=SAMPLEB}
C {devices/gnd.sym} 620 630 0 0 {name=lgnd51 lab=GND}
C {devices/gnd.sym} 620 600 0 0 {name=lgnd52 lab=GND}
C {sky130_fd_pr/nfet_01v8.sym} 900 600 0 0 {name=Scn_n W=1 L=0.15 nf=1 mult=1}
C {devices/lab_pin.sym} 920 570 0 0 {name=l53 lab=BSBOT_N}
C {devices/lab_pin.sym} 880 600 0 0 {name=l54 lab=SAMPLE}
C {devices/lab_pin.sym} 920 630 0 0 {name=l55 lab=VINN}
C {devices/gnd.sym} 920 600 0 0 {name=lgnd56 lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 1200 600 0 0 {name=Scp_n W=1 L=0.15 nf=1 mult=1}
C {devices/lab_pin.sym} 1220 630 0 0 {name=l57 lab=BSBOT_N}
C {devices/lab_pin.sym} 1180 600 0 0 {name=l58 lab=SAMPLEB}
C {devices/lab_pin.sym} 1220 570 0 0 {name=l59 lab=VINN}
C {devices/lab_pin.sym} 1220 600 0 0 {name=l60 lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} 1500 600 0 0 {name=Sd_n W=1 L=0.5 nf=1 mult=1}
C {devices/lab_pin.sym} 1520 570 0 0 {name=l61 lab=G_N}
C {devices/lab_pin.sym} 1480 600 0 0 {name=l62 lab=SAMPLEB}
C {devices/gnd.sym} 1520 630 0 0 {name=lgnd63 lab=GND}
C {devices/gnd.sym} 1520 600 0 0 {name=lgnd64 lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 0 900 0 0 {name=Se_n W=1 L=0.15 nf=1 mult=1}
C {devices/lab_pin.sym} 20 930 0 0 {name=l65 lab=G_N}
C {devices/lab_pin.sym} -20 900 0 0 {name=l66 lab=SAMPLEB}
C {devices/lab_pin.sym} 20 870 0 0 {name=l67 lab=BOOST_N}
C {devices/lab_pin.sym} 20 900 0 0 {name=l68 lab=BOOST_N}
C {sky130_fd_pr/nfet_01v8.sym} 300 900 0 0 {name=Cmswn_n W=1 L=0.15 nf=1 mult=1}
C {devices/lab_pin.sym} 320 870 0 0 {name=l69 lab=BPREF_N}
C {devices/lab_pin.sym} 280 900 0 0 {name=l70 lab=SAMPLE}
C {devices/lab_pin.sym} 320 930 0 0 {name=l71 lab=VCM}
C {devices/gnd.sym} 320 900 0 0 {name=lgnd72 lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 600 900 0 0 {name=Cmswp_n W=1 L=0.15 nf=1 mult=1}
C {devices/lab_pin.sym} 620 930 0 0 {name=l73 lab=BPREF_N}
C {devices/lab_pin.sym} 580 900 0 0 {name=l74 lab=SAMPLEB}
C {devices/lab_pin.sym} 620 870 0 0 {name=l75 lab=VCM}
C {devices/lab_pin.sym} 620 900 0 0 {name=l76 lab=VDD}
C {sky130_fd_pr/cap_mim_m3_1.sym} 900 900 0 0 {name=Cboot_n model=cap_mim_m3_1 W=9.8 L=9.8 MF=1 spiceprefix=X}
C {devices/lab_pin.sym} 900 870 0 0 {name=l77 lab=BOOST_N}
C {devices/lab_pin.sym} 900 930 0 0 {name=l78 lab=BSBOT_N}
C {sky130_fd_pr/cap_mim_m3_1.sym} 1200 900 0 0 {name=Csamp_n model=cap_mim_m3_1 W=46.9 L=46.9 MF=1 spiceprefix=X}
C {devices/lab_pin.sym} 1200 870 0 0 {name=l79 lab=TOP_N}
C {devices/lab_pin.sym} 1200 930 0 0 {name=l80 lab=BPREF_N}
C {sky130_fd_pr/pfet_01v8.sym} 0 1200 0 0 {name=Invp W=2 L=0.15 nf=1 mult=1}
C {devices/lab_pin.sym} 20 1230 0 0 {name=l81 lab=SAMPLEB}
C {devices/lab_pin.sym} -20 1200 0 0 {name=l82 lab=SAMPLE}
C {devices/lab_pin.sym} 20 1170 0 0 {name=l83 lab=VDD}
C {devices/lab_pin.sym} 20 1200 0 0 {name=l84 lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} 300 1200 0 0 {name=Invn W=1 L=0.15 nf=1 mult=1}
C {devices/lab_pin.sym} 320 1170 0 0 {name=l85 lab=SAMPLEB}
C {devices/lab_pin.sym} 280 1200 0 0 {name=l86 lab=SAMPLE}
C {devices/gnd.sym} 320 1230 0 0 {name=lgnd87 lab=GND}
C {devices/gnd.sym} 320 1200 0 0 {name=lgnd88 lab=GND}
C {devices/title.sym} 0 1500 0 0 {name=l89 author="2AM Logic (issue #52: sampling front end)"}
* --- Hierarchical port objects (issue #56 integration): added so this leaf
* schematic can generate an instantiable xschem symbol
* (design/sampling_frontend.sym, via make_sym.awk) with a drawn pin list,
* aligning with the ipin.sym/opin.sym convention already used by
* design/cdac/cdac_array.sch and design/sar_sequencer.sch. Pure additions at
* existing net labels (VINP/VINN/SAMPLE/VCM/VDD/TOP_P/TOP_N/BPREF_P/
* BPREF_N); no existing device or lab_pin instance above is touched. GND is
* intentionally NOT given a port object here: devices/gnd.sym is
* `global=true`, so it is already the same net at every level of hierarchy
* without a pin. BPREF_P/BPREF_N are exposed as opin (this sub-block drives
* them to VCM only during SAMPLE, per the header comment above) even though
* design/cdac/cdac_array.sch (#53) does not yet expose a matching
* combined-bottom-plate pin to receive them -- see design/sar_adc_top.sch's
* own header for how this known, named-not-closed integration gap
* (spec/decision-records/DR-004-sampling-frontend-sizing.md "Open items",
* issue #61) is handled at the top level.
C {devices/ipin.sym} -100 -30 0 0 {name=p_vinp lab=VINP}
C {devices/ipin.sym} -100 30 0 0 {name=p_vinn lab=VINN}
C {devices/ipin.sym} -100 90 0 0 {name=p_sample lab=SAMPLE}
C {devices/ipin.sym} -100 150 0 0 {name=p_vcm lab=VCM}
C {devices/ipin.sym} -100 210 0 0 {name=p_vdd lab=VDD}
C {devices/opin.sym} -100 270 0 0 {name=p_top_p lab=TOP_P}
C {devices/opin.sym} -100 330 0 0 {name=p_top_n lab=TOP_N}
C {devices/opin.sym} -100 390 0 0 {name=p_bpref_p lab=BPREF_P}
C {devices/opin.sym} -100 450 0 0 {name=p_bpref_n lab=BPREF_N}

v {xschem version=3.4.7 file_version=1.2
* sar_adc_top.sch -- top-level SAR ADC integration (issue #56): wires the
* four sub-block schematics (design/sampling_frontend.sch #52,
* design/cdac/cdac_array.sch #53, design/comparator.sch #54,
* design/sar_sequencer.sch #55) into one hierarchical top-level schematic,
* and defines this block's own instantiable symbol (design/sar_adc_top.sym,
* generated the same way as every sub-block's, via
* `awk -f <xschem-share-dir>/make_sym.awk design/sar_adc_top.sch`).
*
* Every sub-block is instantiated via its own generated symbol
* (design/<block>.sym); none of the four sub-block .sch files are modified
* by this integration beyond the port-object additions described below.
*
* ============================================================================
* PIN-CONVENTION NORMALIZATION (per this issue's "Verified corrections")
* ============================================================================
* design/cdac/cdac_array.sch (#53) and design/sar_sequencer.sch (#55) already
* used real xschem hierarchical port objects (devices/ipin.sym /
* devices/opin.sym), which is what lets xschem's make_sym.awk derive an
* instantiable symbol with a drawn pin list directly from the schematic.
* design/comparator.sch (#54) and design/sampling_frontend.sch (#52) used
* only devices/lab_pin.sym (net-label pins, not xschem port objects) --
* this issue adds ipin.sym/opin.sym port objects to both of those files
* (using each file's own header-comment pin list as the source of truth for
* which nets are ports), aligning all four sub-blocks on one convention
* before instantiating them here, per the issue's own recommendation. These
* are pure additions at each file's EXISTING net labels; no existing device
* or lab_pin instance in either file was touched, and neither file's
* internal connectivity changed. GND is deliberately NOT given a port
* object anywhere: devices/gnd.sym is `global=true`, so "GND" is already
* the same net at every level of hierarchy without needing a pin -- VDD is
* bridged the same way here via devices/vdd.sym (also `global=true`), for
* the same reason.
*
* ============================================================================
* TOP-LEVEL SIGNAL FLOW / ARCHITECTURE
* ============================================================================
* Classic top-plate-sampling differential charge-redistribution SAR ADC
* (per spec/target-spec.md's Architecture row and DR-003 Item 3):
*
*   VINP/VINN -[sampling_frontend #52]-> TOP_P/TOP_N, shared with
*   cdac_array #53's own TOP_P/TOP_N DAC-output nodes and with
*   comparator #54's own VINP/VINN analog inputs -- ONE node per side
*   across all three blocks, exactly as design/cdac/cdac_array.sch's own
*   header describes it ("TOP_P/TOP_N are this array's two DAC output
*   nodes (the future comparator's inputs)").
*
*   comparator.OUTP -> sar_sequencer.COMP_OUT: the sequencer (#55) wants a
*   single-ended ideal bit decision; comparator.OUTP is used directly
*   (non-inverting per comparator.sch's own documented convention:
*   Vin,diff = VINP-VINN > 0 => OUTP settles high = "1" decision).
*   comparator.OUTN is intentionally left on its own dead-end net
*   (OUTN_NC) at this integration level -- not needed by the sequencer,
*   which has no complementary-decision input.
*
*   sar_sequencer.PH_SAMPLE -> sampling_frontend.SAMPLE (bridged via the
*   SAMPLE_INT net below): the sequencer, not this schematic, is the
*   "clock/phase generation" sub-block per #55's own scope; the front end
*   takes a single external SAMPLE phase per its own header, so this
*   integration wires that phase from the sequencer's own PH_SAMPLE output
*   rather than driving it externally (only design/sampling_frontend.sch's
*   OWN standalone testbench does that, per its header).
*
*   sar_sequencer.DOUT8..DOUT0 (9 bits) double as BOTH this block's own
*   digital output code bits AND the CDAC array's per-bit switch control:
*   SELp<i> = DOUT<i> directly (bit value steers the P-side bottom plate);
*   SELn<i> = NOT(DOUT<i>) via a dedicated sky130_fd_sc_hd inv_1 instance
*   per bit (9 total, xinv_seln0..xinv_seln8 below) -- REQUIRED because
*   design/cdac/cdac_unit_cell.sch's single-control-line switch uses the
*   IDENTICAL SEL truth table on both array sides, so a differential DAC
*   needs the two sides' SEL to be complementary, not equal, or a bit
*   decision would move TOP_P and TOP_N the same way (pure common-mode,
*   zero differential contribution). DOUT9 (this design's "free" MSB, per
*   DR-003 Item 3 -- resolved directly from the sampled charge, no CDAC
*   switching) has no corresponding CDAC SEL pin; it is wired ONLY to this
*   block's own DOUT9 output.
*
*   This SELp=DOUT / SELn=NOT(DOUT) polarity is a STATED, DOCUMENTED
*   WIRING DECISION, not a verified-correct claim: no closed-loop SAR
*   conversion testbench has been run against this exact top-level netlist
*   as of this issue. End-to-end functional/polarity verification (does a
*   real conversion actually converge to the right code) is explicitly
*   deferred to the future per-row/Monte-Carlo testbenches this issue's own
*   acceptance criteria reference (#28/#29/#31) -- consistent with
*   CLAUDE.md's "no claim without a testbench": this schematic is a
*   structural wiring artifact, not itself a verification result.
*
*   comparator.CLK = sar_sequencer.CLK = this block's own top-level CLK
*   (the comparator evaluates/resets on the same master clock edge as
*   every SAR bit-trial phase). A more refined design might gate the
*   comparator's clock so it only toggles while BUSY; that refinement is
*   out of this issue's wiring-correctness scope and is not required by
*   any acceptance criterion here.
*
*   PH_B9..PH_B0/PH_EOC (the sequencer's internal one-hot phase signals)
*   are deliberately left unconnected at this integration level -- they
*   are internal to the SAR control loop, not needed by any other
*   sub-block or by this top-level symbol's own external pin list.
*
* ============================================================================
* KNOWN, NAMED-NOT-CLOSED INTEGRATION GAPS (documented, not silently papered
* over -- neither is fixed by this issue; both are flagged for a follow-up)
* ============================================================================
* 1. BPREF_P/BPREF_N (sampling_frontend #52's bottom-plate reference
*    outputs, driven to VCM only during SAMPLE) have NO corresponding pin
*    on design/cdac/cdac_array.sch (#53) to connect to: cdac_array's
*    per-bit bottom plates (BOT_p0..BOT_p8 / BOT_n0..BOT_n8) are each
*    ALWAYS actively driven to VREFP or VREFN by their own SEL switch (per
*    design/cdac/cdac_unit_cell.sch's truth table) -- there is no single
*    combined "bottom-plate common" node in the array as built for a
*    sample-phase common-mode short to land on. This is exactly what
*    spec/decision-records/DR-004-sampling-frontend-sizing.md's "Open
*    items" section already flags ("The real ADC's CDAC (#53) would take
*    over BPREF_x almost immediately after sampling ends" -- an assumption
*    that does not match #53's actual as-built switching architecture).
*    BPREF_P/BPREF_N are left on their own dead-end nets (BPREF_P_NC /
*    BPREF_N_NC below, named to make the "deliberately not joined to
*    anything else" intent unambiguous in the raw netlist) rather than
*    inventing a new CDAC circuit change here -- that would be new circuit
*    design on someone else's already-tested, already-merged sub-block, out
*    of this issue's own "wiring, not introducing new devices" scope per
*    its own spec-coupling note. Filed as a follow-up issue (see this
*    issue's closing PR).
* 2. VDD/GND (analog blocks: sampling_frontend/comparator/cdac_array, tied
*    together below via devices/vdd.sym + devices/gnd.sym, both
*    `global=true`) and VPWR/VGND (design/sar_sequencer.sch's digital
*    standard cells, referenced as bare literal net-name INSTANCE
*    PROPERTIES per the sky130_stdcells xschem symbol library's own format
*    string -- see that file's own header, "n-well (VPB) and substrate
*    (VNB) taps are tied to VPWR/VGND") are NOT the same xschem-tracked net
*    and CANNOT be tied together by schematic-level wiring here: VPWR/VGND
*    are not real ipin/opin/lab_pin objects anywhere in
*    design/sar_sequencer.sch, they are literal text substituted directly
*    onto each std-cell's SPICE device line by that symbol library's own
*    format string (`@VPWR`/`@VGND`, a property lookup, not `@@pin`, a net
*    lookup) -- there is no schematic-graph node for this integration to
*    connect to, at this or any hierarchy level. This is a deliberate,
*    precedented divergence, not an oversight: sim/sar-sequencer-behavioral/
*    run_testbench.py's OWN standalone testbench already drives VPWR/VGND
*    with its own dedicated sources (`VVPWR VPWR 0 DC 1.8` /
*    `VVGND VGND 0 DC 0`) independent of this schematic, exactly the
*    pattern a future full-ADC testbench (#28/#29/#31) must repeat when it
*    assembles its own simulation deck around this netlist -- adding a
*    `.global` equivalence or an ideal 0V tie source at THAT testbench's
*    assembly step, not inside this structural schematic.
*
* Every device instance anywhere in this hierarchy (including the 9 new
* inv_1 instances this file adds) is ratified-flavour: nfet_01v8/pfet_01v8
* (1.8V core, DR-001) or sky130_fd_sc_hd (via sky130_stdcells); no
* _g5v0d10v5 or other flavour appears anywhere -- see
* design/regen_netlist.sh's device-flavour check, run on every regeneration.
*
* Clean room: this is a wiring/integration schematic only -- no new circuit
* topology, sized from any other party's implementation. It connects
* already-designed-forward sub-blocks (#52-#55) per standard
* charge-redistribution SAR ADC control-loop theory (top-plate sampling,
* per-bit differential DAC switching, successive-approximation register
* feedback), consistent with CLAUDE.md's clean-room rule.
}
G {}
K {}
V {}
S {}
E {}

* --- Top-level external ports ---
C {devices/ipin.sym} -1200 -440 0 0 {name=p1 lab=VINP}
C {devices/ipin.sym} -1200 -400 0 0 {name=p2 lab=VINN}
C {devices/ipin.sym} -1200 -360 0 0 {name=p3 lab=VDD}
C {devices/ipin.sym} -1200 -320 0 0 {name=p4 lab=VREFP}
C {devices/ipin.sym} -1200 -280 0 0 {name=p5 lab=VREFN}
C {devices/ipin.sym} -1200 -240 0 0 {name=p6 lab=VCM}
C {devices/ipin.sym} -1200 -200 0 0 {name=p7 lab=CLK}
C {devices/ipin.sym} -1200 -160 0 0 {name=p8 lab=RST_B}
C {devices/opin.sym} -1200 -120 0 0 {name=p9 lab=DOUT9}
C {devices/opin.sym} -1200 -80 0 0 {name=p10 lab=DOUT8}
C {devices/opin.sym} -1200 -40 0 0 {name=p11 lab=DOUT7}
C {devices/opin.sym} -1200 0 0 0 {name=p12 lab=DOUT6}
C {devices/opin.sym} -1200 40 0 0 {name=p13 lab=DOUT5}
C {devices/opin.sym} -1200 80 0 0 {name=p14 lab=DOUT4}
C {devices/opin.sym} -1200 120 0 0 {name=p15 lab=DOUT3}
C {devices/opin.sym} -1200 160 0 0 {name=p16 lab=DOUT2}
C {devices/opin.sym} -1200 200 0 0 {name=p17 lab=DOUT1}
C {devices/opin.sym} -1200 240 0 0 {name=p18 lab=DOUT0}
C {devices/opin.sym} -1200 280 0 0 {name=p19 lab=BUSY}

* --- Sub-block instances ---
C {design/sampling_frontend.sym} 0 0 0 0 {name=xfe}
C {design/cdac/cdac_array.sym} 900 0 0 0 {name=xcdac}
C {design/comparator.sym} 1800 -400 0 0 {name=xcmp}
C {design/sar_sequencer.sym} 2700 0 0 0 {name=xseq}

* --- sampling_frontend (xfe) pins ---
C {devices/lab_pin.sym} -150 -40 0 0 {name=l20 lab=VINP}
C {devices/lab_pin.sym} -150 -20 0 0 {name=l21 lab=VINN}
C {devices/lab_pin.sym} -150 0 0 0 {name=l22 lab=SAMPLE_INT}
C {devices/lab_pin.sym} -150 20 0 0 {name=l23 lab=VCM}
C {devices/lab_pin.sym} -150 40 0 0 {name=l24 lab=VDD}
C {devices/lab_pin.sym} 150 -40 0 0 {name=l25 lab=TOP_P}
C {devices/lab_pin.sym} 150 -20 0 0 {name=l26 lab=TOP_N}
C {devices/lab_pin.sym} 150 0 0 0 {name=l27 lab=BPREF_P_NC}
C {devices/lab_pin.sym} 150 20 0 0 {name=l28 lab=BPREF_N_NC}

* --- cdac_array (xcdac) pins ---
C {devices/lab_pin.sym} 750 -210 0 0 {name=l29 lab=VREFP}
C {devices/lab_pin.sym} 750 -190 0 0 {name=l30 lab=VREFN}
C {devices/lab_pin.sym} 750 -170 0 0 {name=l31 lab=VDD}
C {devices/gnd.sym} 750 -150 0 0 {name=lgnd32 lab=GND}
C {devices/lab_pin.sym} 750 -130 0 0 {name=l33 lab=SELn0}
C {devices/lab_pin.sym} 750 -110 0 0 {name=l34 lab=DOUT0}
C {devices/lab_pin.sym} 750 -90 0 0 {name=l35 lab=SELn1}
C {devices/lab_pin.sym} 750 -70 0 0 {name=l36 lab=DOUT1}
C {devices/lab_pin.sym} 750 -50 0 0 {name=l37 lab=SELn2}
C {devices/lab_pin.sym} 750 -30 0 0 {name=l38 lab=DOUT2}
C {devices/lab_pin.sym} 750 -10 0 0 {name=l39 lab=SELn3}
C {devices/lab_pin.sym} 750 10 0 0 {name=l40 lab=DOUT3}
C {devices/lab_pin.sym} 750 30 0 0 {name=l41 lab=SELn4}
C {devices/lab_pin.sym} 750 50 0 0 {name=l42 lab=DOUT4}
C {devices/lab_pin.sym} 1050 -210 0 0 {name=l43 lab=TOP_N}
C {devices/lab_pin.sym} 1050 -190 0 0 {name=l44 lab=TOP_P}
C {devices/lab_pin.sym} 750 70 0 0 {name=l45 lab=DOUT5}
C {devices/lab_pin.sym} 750 90 0 0 {name=l46 lab=SELn5}
C {devices/lab_pin.sym} 750 110 0 0 {name=l47 lab=DOUT6}
C {devices/lab_pin.sym} 750 130 0 0 {name=l48 lab=SELn6}
C {devices/lab_pin.sym} 750 150 0 0 {name=l49 lab=SELn7}
C {devices/lab_pin.sym} 750 170 0 0 {name=l50 lab=DOUT7}
C {devices/lab_pin.sym} 750 190 0 0 {name=l51 lab=SELn8}
C {devices/lab_pin.sym} 750 210 0 0 {name=l52 lab=DOUT8}

* --- comparator (xcmp) pins ---
C {devices/lab_pin.sym} 1650 -430 0 0 {name=l53 lab=VDD}
C {devices/lab_pin.sym} 1650 -410 0 0 {name=l54 lab=CLK}
C {devices/lab_pin.sym} 1650 -390 0 0 {name=l55 lab=TOP_P}
C {devices/lab_pin.sym} 1650 -370 0 0 {name=l56 lab=TOP_N}
C {devices/lab_pin.sym} 1950 -430 0 0 {name=l57 lab=COMP_OUT}
C {devices/lab_pin.sym} 1950 -410 0 0 {name=l58 lab=OUTN_NC}

* --- sar_sequencer (xseq) pins ---
C {devices/lab_pin.sym} 2850 -220 0 0 {name=l59 lab=DOUT9}
C {devices/lab_pin.sym} 2550 -220 0 0 {name=l60 lab=CLK}
C {devices/lab_pin.sym} 2850 -160 0 0 {name=l61 lab=DOUT8}
C {devices/lab_pin.sym} 2550 -200 0 0 {name=l62 lab=RST_B}
C {devices/lab_pin.sym} 2850 -120 0 0 {name=l63 lab=DOUT7}
C {devices/lab_pin.sym} 2550 -180 0 0 {name=l64 lab=COMP_OUT}
C {devices/lab_pin.sym} 2850 -100 0 0 {name=l65 lab=DOUT6}
C {devices/lab_pin.sym} 2850 -40 0 0 {name=l66 lab=DOUT5}
C {devices/lab_pin.sym} 2850 -20 0 0 {name=l67 lab=DOUT4}
C {devices/lab_pin.sym} 2850 20 0 0 {name=l68 lab=DOUT3}
C {devices/lab_pin.sym} 2850 60 0 0 {name=l69 lab=DOUT2}
C {devices/lab_pin.sym} 2850 120 0 0 {name=l70 lab=DOUT1}
C {devices/lab_pin.sym} 2850 160 0 0 {name=l71 lab=DOUT0}
C {devices/lab_pin.sym} 2850 200 0 0 {name=l72 lab=SAMPLE_INT}
C {devices/lab_pin.sym} 2850 220 0 0 {name=l73 lab=BUSY}

* --- VDD tie for the three analog blocks (front end / comparator / cdac_array) ---
C {devices/vdd.sym} -1300 -480 0 0 {name=lvdd1 lab=VDD}
* --- SELn<i> = NOT(DOUT<i>) inverters (ratified sky130_fd_sc_hd inv_1) ---
C {sky130_stdcells/inv_1.sym} 1400 500 0 0 {name=xinv_seln0 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1360 500 0 0 {name=l_inv0_a lab=DOUT0}
C {devices/lab_pin.sym} 1440 500 0 0 {name=l_inv0_y lab=SELn0}
C {sky130_stdcells/inv_1.sym} 1400 600 0 0 {name=xinv_seln1 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1360 600 0 0 {name=l_inv1_a lab=DOUT1}
C {devices/lab_pin.sym} 1440 600 0 0 {name=l_inv1_y lab=SELn1}
C {sky130_stdcells/inv_1.sym} 1400 700 0 0 {name=xinv_seln2 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1360 700 0 0 {name=l_inv2_a lab=DOUT2}
C {devices/lab_pin.sym} 1440 700 0 0 {name=l_inv2_y lab=SELn2}
C {sky130_stdcells/inv_1.sym} 1400 800 0 0 {name=xinv_seln3 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1360 800 0 0 {name=l_inv3_a lab=DOUT3}
C {devices/lab_pin.sym} 1440 800 0 0 {name=l_inv3_y lab=SELn3}
C {sky130_stdcells/inv_1.sym} 1400 900 0 0 {name=xinv_seln4 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1360 900 0 0 {name=l_inv4_a lab=DOUT4}
C {devices/lab_pin.sym} 1440 900 0 0 {name=l_inv4_y lab=SELn4}
C {sky130_stdcells/inv_1.sym} 1400 1000 0 0 {name=xinv_seln5 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1360 1000 0 0 {name=l_inv5_a lab=DOUT5}
C {devices/lab_pin.sym} 1440 1000 0 0 {name=l_inv5_y lab=SELn5}
C {sky130_stdcells/inv_1.sym} 1400 1100 0 0 {name=xinv_seln6 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1360 1100 0 0 {name=l_inv6_a lab=DOUT6}
C {devices/lab_pin.sym} 1440 1100 0 0 {name=l_inv6_y lab=SELn6}
C {sky130_stdcells/inv_1.sym} 1400 1200 0 0 {name=xinv_seln7 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1360 1200 0 0 {name=l_inv7_a lab=DOUT7}
C {devices/lab_pin.sym} 1440 1200 0 0 {name=l_inv7_y lab=SELn7}
C {sky130_stdcells/inv_1.sym} 1400 1300 0 0 {name=xinv_seln8 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1360 1300 0 0 {name=l_inv8_a lab=DOUT8}
C {devices/lab_pin.sym} 1440 1300 0 0 {name=l_inv8_y lab=SELn8}

T {sar_adc_top: SAR ADC top-level integration (issue #56) -- see header for architecture, pin-convention normalization, and known integration gaps} -1300 -600 0 0 0.2 0.2 {}

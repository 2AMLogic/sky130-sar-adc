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
*   This SELp=DOUT / SELn=NOT(DOUT) polarity was a STATED, DOCUMENTED
*   WIRING DECISION, not a verified-correct claim, at issue #56: no
*   closed-loop SAR conversion testbench had been run against this exact
*   top-level netlist then, and end-to-end functional/polarity verification
*   was explicitly deferred. UPDATE (#254, #257): that verification has now
*   run (sim/full-conversion-transient/), and this wiring does NOT survive
*   it. Driving both array sides unconditionally and complementarily makes
*   every bit contribute +-2*w_i LSB (both plates move, oppositely), so the
*   array's own step is 2 LSB -- nine binary bits then span the whole
*   +-V_REF range by themselves, the bipolar array already encodes the sign,
*   and DOUT9 (the "free" MSB, which drives no CDAC pin) contributes nothing
*   to the DAC. DR-003 Item 3's free-MSB architecture wants
*   decision-directed single-side switching (1 LSB per unit weight, 9
*   magnitude bits + 1 sign bit = the ratified N=10) instead. Tracked, with
*   the measured evidence, in issue #263 -- this paragraph is left standing
*   (not deleted) because the wiring it describes is still what is drawn
*   below.
*
*   comparator.CLK = CLKN = NOT(sar_adc_top.CLK) (issue #257's fix). This
*   supersedes the "comparator.CLK = sar_sequencer.CLK ... gating the
*   comparator's clock is out of scope" wiring note this paragraph carried
*   through issue #56: that deferred risk has now been measured, and it was
*   real. Through #56 this pin was tied directly to the same top-level CLK
*   net every xbreg9..xbreg0 bit-capture register (design/sar_sequencer.sch,
*   sky130_fd_sc_hd dfrtp_1, positive-edge-triggered) samples on. A
*   node-level trace
*   (sim/full-conversion-transient/records/20260911-103820-fd35266.md, via
*   #259/#262) showed that is a structural half-period ORDERING defect, not
*   a skew/setup-hold margin: design/comparator.sch's dynamic latch destroys
*   its decision (precharges OUTP/OUTN back to VDD through XM_RST_P/XM_RST_N,
*   PFETs gated by its own CLK pin) for the ENTIRE CLK=0 half-period, while
*   xbreg9..xbreg0 capture on CLK's RISING edge -- the edge that ENDS that
*   reset half, a full half-period after the decision was destroyed, never
*   the CLK=1 evaluate half in which it briefly existed. COMP_OUT read VDD
*   1 ns before 20/20 traced capturing edges, and the captured code
*   saturated to 1023 for every input at every ratified corner, 910 LSB
*   worst-case error
*   (sim/full-conversion-transient/records/20260910-190240-2d1d196.md,
*   #254/#260, reproduced post-#258 by .../20260911-071010-f0e45fa.md).
*
*   The fix: xinv_clkcap (ratified sky130_fd_sc_hd inv_1, added below)
*   generates CLKN = NOT(CLK), and comparator.CLK is re-pointed from CLK to
*   CLKN -- design/comparator.sch itself is untouched, and so is
*   sar_sequencer.CLK (still the raw top-level CLK), so the ring sequencer's
*   own already-verified phase generation and every register's capture
*   instant are exactly where they were. What changes is only WHICH half of
*   each bit-trial period the comparator spends resetting: with CLKN on its
*   strobe, CLK=1 (the first half of the period, right after the
*   phase-advancing/bit-capturing edge, while the CDAC is still settling) is
*   the comparator's RESET half, and CLK=0 (the second half) is its EVALUATE
*   half -- which ends at the next CLK rising edge, the very edge
*   xbreg9..xbreg0 capture on. The capturing edge now lands at the END of a
*   live evaluate window instead of deep inside a reset window. That is a
*   structural reordering of the two halves, not a trimmed delay; the trace
*   above is explicit that no amount of skew can close a half-period
*   ordering fault, and none is attempted here.
*
*   Why this holds at every ratified PVT point, not just the simulated ones:
*   the ordering itself is PVT-independent (it is a half-period of the
*   master clock, not a delay). The one PVT-sensitive term left is the
*   margin at the capturing edge: reset now begins one xinv_clkcap gate
*   delay AFTER that edge (CLKN falls after CLK rises), plus the comparator's
*   own precharge ramp on OUTP/OUTN, versus dfrtp_1's hold requirement --
*   an inverter delay and a flip-flop hold time, both sky130_fd_sc_hd cells
*   evaluated at the same corner, so they track each other rather than
*   diverging at an extreme. Measured: the 9-corner campaign below captures
*   an input-dependent decision at every bit trial at all 9 ratified points,
*   with no corner-to-corner variation at all.
*
*   Verified by sim/full-conversion-transient/ (issue #254's campaign,
*   re-run post-fix; see the newest record there, which names this schematic
*   as its provenance and states which record it supersedes): the captured
*   code is no longer stuck at 1023 -- it now tracks the applied input, the
*   worst-case code error drops 910 -> 384 LSB, and the phase-timing /
*   completion check passes at 9/9 corners (it was 8/9 pre-fix,
*   ff_27c_1.80v being the exception). NOT YET CONVERGING, and this
*   schematic does not claim it does: the conversion still resolves to a
*   fixed wrong code sequence at every corner, for reasons that have nothing
*   to do with this clock relationship -- the SAR search applies no trial
*   perturbation before each decision and never clears the CDAC bits between
*   conversions, and the SELp/SELn wiring in the paragraph above drives both
*   array sides unconditionally. That residual is diagnosed and tracked in
*   issue #263; do not re-open the clock relationship for it.
*
*   PH_B9..PH_B0/PH_EOC (the sequencer's internal one-hot phase signals)
*   are deliberately left unconnected at this integration level -- they
*   are internal to the SAR control loop, not needed by any other
*   sub-block or by this top-level symbol's own external pin list.
*
* ============================================================================
* KNOWN, NAMED-NOT-CLOSED INTEGRATION GAP (one remains open; item 1 below was
* resolved by issue #95, kept here -- marked RESOLVED -- rather than deleted,
* so the BPREF_P_NC/BPREF_N_NC dead-end wiring a reader sees below still has
* an explanation attached at the point it's introduced)
* ============================================================================
* 1. [RESOLVED by #95] BPREF_P/BPREF_N (sampling_frontend #52's bottom-plate
*    reference outputs, driven to VCM only during SAMPLE) have NO
*    corresponding pin on design/cdac/cdac_array.sch (#53) to connect to:
*    cdac_array's per-bit bottom plates (BOT_p0..BOT_p8 / BOT_n0..BOT_n8)
*    are each ALWAYS actively driven to VREFP or VREFN by their own SEL
*    switch (per design/cdac/cdac_unit_cell.sch's truth table) -- there is
*    no single combined "bottom-plate common" node in the array as built
*    for a sample-phase common-mode short to land on. This was originally
*    flagged (not yet resolved) against
*    spec/decision-records/DR-004-sampling-frontend-sizing.md's "Open
*    items" section assumption ("The real ADC's CDAC (#53) would take over
*    BPREF_x almost immediately after sampling ends").
*    Issue #95 resolved this: that hand-off assumption is FALSE, not just
*    premature -- the real array never provides a node to hand off to, by
*    design, and BPREF_P/BPREF_N are left on their own dead-end nets
*    (BPREF_P_NC / BPREF_N_NC below) PERMANENTLY, not as an interim gap.
*    #95's own testbench (sim/sampling-cdac-handoff/run_handoff.py)
*    verified this dead-end wiring does not corrupt sampling: TOP_P/TOP_N
*    settle to VINP/VINN within 0.73mV at the tt corner, identically across
*    three different CDAC-array "previous conversion" bottom-plate code
*    states, when sampling_frontend and the real cdac_array are simulated
*    together exactly as wired below. Circuit argument (see DR-004's
*    "Update (issue #95)" section for the full writeup): during SAMPLE,
*    TOP_x is driven low-impedance by the front end's own bootstrapped
*    switch regardless of what the (always individually driven, never
*    floating) CDAC array bottom plates are doing; once SAMPLE ends, the
*    front end's own Csamp_p/Csamp_n become isolated two-terminal
*    capacitors (BPREF_x, their other terminal, touches nothing else,
*    exactly because of this dead-end wiring) and therefore inject zero
*    further current into TOP_x for the rest of the conversion.
*    sampling_frontend.sch's own Csamp_p/Csamp_n/BPREF_x/Cmswn/Cmswp
*    circuitry is left in place (not removed) -- see DR-004's Open items
*    for the sizing-re-verification reason and the new settling-headroom
*    residual (ss corner, doubled load) this leaves for a future pass.
* 2. VDD/GND (analog blocks: sampling_frontend/comparator/cdac_array, tied
*    together below via devices/vdd.sym + devices/gnd.sym, both
*    `global=true`) and VPWR/VGND (design/sar_sequencer.sch's digital
*    standard cells, referenced as bare literal net-name INSTANCE
*    PROPERTIES per the sky130_stdcells xschem symbol library's own format
*    string -- see that file's own header, "n-well (VPB) and substrate
*    (VNB) taps are tied to VPWR/VGND") are NOT the same xschem-tracked net,
*    and VPWR/VGND cannot be WIRED to anything by schematic-level
*    connectivity here: they are not real ipin/opin/lab_pin objects anywhere
*    in design/sar_sequencer.sch, they are literal text substituted directly
*    onto each std-cell's SPICE device line by that symbol library's own
*    format string (`@VPWR`/`@VGND`, a property lookup, not `@@pin`, a net
*    lookup) -- there is no schematic-graph node to draw a wire to, at this
*    or any hierarchy level. All of that remains true and unchanged.
*
*    REVISED (issue #258) -- what this file previously concluded FROM the
*    paragraph above was wrong, and the conclusion is replaced here rather
*    than left standing: "cannot be wired" is not the same as "cannot be
*    declared". Those literal names are ordinary SPICE node names, so
*    ordinary SPICE subcircuit scoping applies to them -- a node name that
*    is neither a formal port of its enclosing `.subckt` nor declared
*    `.GLOBAL` is PRIVATE to that one subcircuit instance. Because
*    design/sar_sequencer.sym carries no VPWR/VGND pins, the netlisted
*    `.subckt sar_sequencer` has neither rail in its formal port list, so
*    every standard cell inside the `xseq` instance below used to be
*    scoped to a private, unpowered copy of both rails whenever this
*    netlist was simulated as a whole. That failure mode is silent -- the
*    digital array drifts to intermediate voltages instead of erroring --
*    which is exactly why it survived until #254's first whole-ADC
*    campaign; #258 pinned it with four independent checks. The nine
*    xinv_seln* instances THIS file adds never showed it only because
*    sar_adc_top is netlisted flat (its own `.subckt` line is emitted
*    commented out), so their VPWR/VGND references were already top-level.
*
*    The fix is the two `global=true` label instances added below
*    (lvpwr1 / lvgnd1). They make the netlister emit `.GLOBAL VPWR` and
*    `.GLOBAL VGND` next to the `.GLOBAL GND` / `.GLOBAL VDD` cards this
*    file already produced for the analog rails, which is what makes each
*    rail ONE net across the whole hierarchy instead of one private copy
*    per subcircuit instance. No wire is needed for this, and none is drawn:
*    the devices/vdd.sym `lvdd1` instance below is likewise unattached and
*    is already exactly what emits `.GLOBAL VDD`. Declaring VPWR/VGND
*    global does NOT merge them into VDD/GND -- they stay distinct nets
*    from the analog rails, so the digital and analog supplies remain
*    separable for future noise-isolation work.
*
*    An enclosing testbench must still SOURCE these two rails; this
*    schematic declares them, it does not power them.
*    sim/sar-sequencer-behavioral/run_testbench.py's OWN standalone
*    testbench does that with `VVPWR VPWR 0 DC 1.8` / `VVGND VGND 0 DC 0`,
*    and sim/full-conversion-transient/ (#254) does the same at its own
*    deck-assembly step -- both remain correct and neither is made
*    redundant. One correction to the previous wording, though: it offered
*    "a `.global` equivalence OR an ideal 0V tie source" at the testbench
*    as equivalent alternatives. They were never equivalent for the nested
*    case. A tie source alone ties only the TOP-LEVEL node of that name and
*    never reaches `xseq`'s private copy; only the global declaration does.
*    With the declaration now made here, a testbench needs only the
*    sources.
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
C {devices/lab_pin.sym} 1650 -410 0 0 {name=l54 lab=CLKN}
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
* --- VPWR/VGND global declaration for the sky130_fd_sc_hd standard cells (#258) ---
* Both are `global=true` label instances, unattached on purpose (exactly like
* lvdd1 above): their only job is to make the netlister emit `.GLOBAL VPWR` /
* `.GLOBAL VGND`, so the digital rails are ONE net across the whole hierarchy
* rather than private per-`.subckt` copies -- without them the standard cells
* inside `xseq` float. Distinct nets from VDD/GND: declared here, sourced by
* the enclosing testbench. See header note 2 above for the full rationale.
C {devices/vdd.sym} -1300 -560 0 0 {name=lvpwr1 lab=VPWR}
C {devices/gnd.sym} -1300 -520 0 0 {name=lvgnd1 lab=VGND}
* --- CLKN = NOT(CLK) capture-clock generator (issue #257) -- feeds ONLY
* comparator.CLK below, so the comparator's own reset/evaluate halves are
* swapped relative to sar_sequencer.CLK (still raw CLK, unchanged), fixing
* the shared-CLK-net half-period capture-ordering defect. See the header
* comment's "comparator.CLK = CLKN" paragraph for the full derivation.
C {sky130_stdcells/inv_1.sym} 1650 -600 0 0 {name=xinv_clkcap VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1610 -600 0 0 {name=l_clkcap_a lab=CLK}
C {devices/lab_pin.sym} 1690 -600 0 0 {name=l_clkcap_y lab=CLKN}
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

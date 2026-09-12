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
*   comparator.OUTN is not needed by the sequencer (which has no
*   complementary-decision input), but it is NOT left unloaded: it carries
*   a matched dummy load mirroring COMP_OUT's own fanout, added by issue
*   #263 -- see "COMPARATOR DIFFERENTIAL-OUTPUT LOAD BALANCING" below for
*   why an unloaded OUTN is a systematic input-referred offset, not a
*   harmless dead end. The net keeps its historical name OUTN_NC (it was
*   genuinely a no-connect when #56 drew it); renaming it would churn
*   layout/sar-adc-top/'s LVS reference artifacts, which are issue #103's
*   to re-derive and are already stale against this schematic.
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
*   (not deleted) because it records the wiring's history; see the UPDATE
*   paragraph immediately below for what is actually drawn now.
*
*   UPDATE (#263, spec/decision-records/DR-008-cdac-top-level-switching-polarity.md):
*   the paragraph above is superseded -- decision-directed
*   single-side switching is now what is drawn. SELp<i>/SELn<i> are each
*   generated by a dedicated sky130_fd_sc_hd and2_1 (xand_selp0..8 /
*   xand_seln0..8 below, replacing the unconditional xinv_seln0..8
*   inverters), gated by DOUT9 (resolved BEFORE any of bits 8..0 move, off
*   the raw sampled residual, per DR-003 Item 3's free-MSB architecture) and
*   its complement DOUT9N (one added sky130_fd_sc_hd inv_1, xinv_dout9n):
*     SELp<i> = DOUT9 AND DOUT<i>          (only the P-side plate switches
*                                            when DOUT9=1, i.e. Vd >= 0)
*     SELn<i> = DOUT9N AND DOUT<i>         (only the N-side plate switches
*                                            when DOUT9=0, i.e. Vd < 0)
*   At the shared baseline DOUT<i>=0 both expressions are 0 regardless of
*   DOUT9, so BOT_p<i>=BOT_n<i>=VREFP (sign-independent zero state) -- the
*   per-conversion CDAC clear added in sar_sequencer.sch (#263 Root cause
*   item 2) returns every bit to exactly this state at the start of each new
*   conversion. Only ONE plate now moves per bit decision (never both), so
*   the array's own step is 1 LSB/bit, not 2 -- matching the w_i=2^i weights
*   sim/full-conversion-transient/gen_full_conversion_tb.py's ideal_code()
*   already assumes for the ratified N=10 offset-binary code. Verified by
*   the re-run sim/full-conversion-transient/ campaign (see its newest
*   record) alongside #263's sar_sequencer.sch trial-perturbation and
*   per-conversion-clear fixes -- all three defects were coupled and are
*   fixed together in this one pass, per the issue's own root-cause writeup.
*
*   CORRECTION (#263, found by that same re-run campaign): DOUT<i> read
*   directly is NOT the ratified offset-binary code for the DOUT9=0 branch
*   -- it is a sign+true-magnitude value (a necessary consequence of a
*   single-side search that always moves its one active plate TOWARD zero).
*   The ADCOUT8..0 = DOUT<i> XOR DOUT9N recoding stage below (near the
*   xand_selp/seln gates) fixes this for READOUT only, without touching
*   SELp/SELn or the search itself -- see that stage's own header comment
*   for the full derivation. sim/full-conversion-transient/ reads
*   ADCOUT8..0 (bit 9: DOUT9 directly, needs no recoding) as the captured
*   code's bits 8..0.
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
*   ff_27c_1.80v being the exception). At that point conversion was NOT YET
*   CONVERGING: the conversion resolved to a fixed wrong code sequence at
*   every corner, for reasons that had nothing to do with this clock
*   relationship -- the SAR search applied no trial perturbation before each
*   decision, never cleared the CDAC bits between conversions, and the
*   SELp/SELn wiring in the paragraph above drove both array sides
*   unconditionally. UPDATE (#263): all three of those are now fixed --
*   trial perturbation and per-conversion CDAC clear in sar_sequencer.sch,
*   decision-directed single-side SELp/SELn switching in this schematic (see
*   the "UPDATE (#263)" paragraph above, superseding the unconditional
*   SELp=DOUT/SELn=NOT(DOUT) wiring) -- and the re-run
*   sim/full-conversion-transient/ campaign is the record of whether
*   convergence now holds; do not re-open the clock relationship, it was
*   never implicated.
*
*   PH_B9..PH_B0/PH_EOC (the sequencer's internal one-hot phase signals)
*   are deliberately left unconnected at this integration level -- they
*   are internal to the SAR control loop, not needed by any other
*   sub-block or by this top-level symbol's own external pin list.
*
* ============================================================================
* COMPARATOR DIFFERENTIAL-OUTPUT LOAD BALANCING (issue #263, second pass)
* ============================================================================
* design/comparator.sch is a StrongARM-class dynamic latch (DR-004): a
* clocked tail pair whose two output nodes OUTP/OUTN start each evaluate
* phase pre-charged to VDD and then REGENERATE -- whichever node discharges
* first turns off its cross-coupled partner and wins. The differential pair
* only seeds that race; the race itself is decided by the two output nodes'
* own RC. Any capacitive imbalance between OUTP and OUTN therefore appears
* directly as a systematic, input-referred comparator OFFSET, with no
* device mismatch needed -- it is present in a nominal, mismatch-free
* netlist.
*
* As drawn by #56 this schematic loaded the two outputs ASYMMETRICALLY:
* COMP_OUT (= comparator.OUTP) drives two standard-cell input pins inside
* xseq (xmux9.A1 and xxnor_compeff.A -- see design/sar_sequencer.sch),
* while comparator.OUTN was a dead-end net with no load at all. The extra
* pin capacitance slows OUTP's discharge, so OUTN wins ties and COMP_OUT is
* biased toward reading 1 ("input differential is positive") -- exactly the
* sign and magnitude of the residual error issue #263's second pass
* measured: with the comparator's own differential input probed at every
* bit-trial decision instant, COMP_OUT read 1 at a true input of -7.0 mV
* (-2.0 LSB) and -10.5 mV (-3.0 LSB) at a top-plate common mode of ~897 mV,
* and at -3.7 mV (-1.05 LSB) at ~676 mV: an input-referred offset of about
* -5 mV at mid common mode growing past -10 mV near VDD/2 + 0.4 V, i.e.
* 1.5-3 LSB of code error, corner-invariant. (The common-mode dependence is
* consistent with the same mechanism: a higher input common mode discharges
* the tail-pair drains faster, shortening the integration window that
* amplifies the input before regeneration starts, so a FIXED output-node
* imbalance refers back to a LARGER input-equivalent offset.)
*
* Fix: load comparator.OUTN with a matched dummy -- xdum_mux_n /
* xdum_xnor_n below, one sky130_fd_sc_hd__mux2_1 and one
* sky130_fd_sc_hd__xnor2_1, the same two cells and the same two pin
* positions COMP_OUT drives inside xseq, with their OTHER inputs wired to
* the SAME nets the real cells see (xmux9's A0=DOUT9 / S=PH_B9,
* xxnor_compeff's B=DOUT9) so the dummy pins' state-dependent capacitance
* tracks the real ones cycle by cycle rather than only on average. Both
* dummy outputs are deliberate no-connects (DUMLOAD_MUX_NC /
* DUMLOAD_XNOR_NC): these cells exist only to present an input
* capacitance. This is a top-level integration fix, exactly like the
* SELp/SELn gating above -- design/comparator.sch itself is unchanged, so
* DR-004's ratified topology/sizing and sim/comparator-decision/'s own
* records stand. Measured effect (sim/full-conversion-transient, tt/27C/
* 1.8V): every bit-trial decision in the three mid-scale conversions now
* matches the sign of the comparator's own probed differential input, down
* to inputs of 0.18 LSB, where before three decisions per conversion were
* inverted.
*
* ============================================================================
* HALF-LSB QUANTIZER OFFSET (issue #263, second pass)
* ============================================================================
* With the comparator offset above removed, what is left is the SAR's own
* quantization convention. A successive-approximation search that keeps a
* trial only while the residual has not changed sign converges to a
* residual in [0, 1) LSB (DOUT9=1 branch) or (-1, 0] LSB (DOUT9=0 branch),
* so the captured code is floor(Vd/LSB)-like: its transitions sit at
* INTEGER multiples of the LSB, while spec/target-spec.md's ideal
* offset-binary code (sim/full-conversion-transient/gen_full_conversion_tb
* .py's ideal_code(), round(Vd/LSB) + 2^(N-1)) has its transitions at HALF
* integers. That is the textbook half-LSB misalignment between a mid-rise
* search and a mid-tread ideal: a systematic -0.5 LSB code offset, which on
* its own is within the +-1 LSB acceptance band but stacks with the array's
* gain error (see below) and pushed -0.25*V_REF to -2 LSB.
*
* Fix: the classic half-LSB offset capacitor, added here at the top level
* rather than inside the array. Choff_n is a CDAC-unit-sized MiM cap
* (W=L=1.8988, identical to design/cdac/cdac_unit_cell.sch's C_u) from
* TOP_N to its own bottom plate BOT_OFF_N, which is switched between VREFP
* and VCM by Moff_n_refp / Moff_n_cmn / Moff_n_cmp. One unit cap over HALF
* the reference swing (VREFP -> VCM = V_REF/2, since VCM = V_DD/2 = V_REF/2
* by DR-003) is exactly half the 1-LSB step one unit cap makes over the
* full swing under the decision-directed single-side switching above -- so
* the offset is set by the reference ratio, not by a sub-unit capacitor
* whose ratio to C_u would be a matching liability. Lowering TOP_N by
* 0.5 LSB raises TOP_P - TOP_N by +0.5 LSB, which is the direction that
* re-centres the quantizer: captured code becomes floor(Vd/LSB + 0.5) =
* round(Vd/LSB), matching ideal_code() (and the DOUT9=0 branch's own
* mirrored expression) to within the 1-LSB granularity of the ones'
* -complement output recoding.
*
* Enable timing is load-bearing. HALF_LSB_EN = BUSY AND NOT(PH_B9)
* (xand_halflsb, one and2b_1; HALF_LSB_ENN = its inverse, xinv_halflsb):
* the offset cap sits at VREFP through the whole SAMPLE phase and through
* the bit-9 (sign) trial, and switches to VCM only at the PH_B9 -> PH_B8
* edge, a full CLK period AFTER the sampling switch has opened. Gating on
* BUSY alone would switch it on the very edge SAMPLE_INT falls on, racing
* the sampling switch's own turn-off -- the injected charge would partly
* drain back into the input source and the offset would be a
* corner-dependent fraction of 0.5 LSB instead of 0.5 LSB. Applying it
* from PH_B8 (not PH_B9) means the sign decision itself is taken on the
* un-offset residual; that only matters for |Vd| < 1 LSB, where both
* branches land within the +-1 LSB band anyway.
*
* Choff_p + Moff_p_refp/Moff_p_cmn/Moff_p_cmp are the matching dummy on
* the other side: the same cap and the same three switch devices, with
* their gates tied off (VGND/VPWR) so that side's bottom plate is held at
* VREFP permanently. They inject no offset; they exist so both top plates
* see the same total capacitance and the same switch junction parasitics,
* i.e. so the two sign branches have the SAME gain.
*
* Residual, NOT closed here: the array's absolute gain. The measured
* per-bit step is ~0.99 LSB, not 1.000 LSB, because the top plates carry
* ~4-5 unit caps' worth of parasitic (the comparator's own input gate
* capacitance dominates) on top of the array's 512 C_u, and a top-plate
* -sampled CDAC divides its redistribution by that total while the sampled
* input is NOT divided. That is a ~0.8-1.0% GAIN error -- it is 0 at
* mid-scale, ~1 LSB at +-0.25*V_REF and ~3 LSB at +-0.78*V_REF, so it
* cannot be fixed by any offset and needs an array unit-cap sizing
* decision (or an explicit gain-error spec row). Tracked separately; see
* spec/decision-records/DR-009-comparator-output-load-balance-and-half-lsb
* -offset.md "Open items".
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
*    xinv_seln* instances THIS file added at the time never showed it only
*    because sar_adc_top is netlisted flat (its own `.subckt` line is
*    emitted commented out), so their VPWR/VGND references were already
*    top-level. (#263 later replaced those nine inverters with the
*    xand_seln0..8 / xand_selp0..8 / xinv_dout9n gates described above; the
*    same flat-netlisting argument applies unchanged to their VPWR/VGND.)
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
C {devices/lab_pin.sym} 750 -110 0 0 {name=l34 lab=SELp0}
C {devices/lab_pin.sym} 750 -90 0 0 {name=l35 lab=SELn1}
C {devices/lab_pin.sym} 750 -70 0 0 {name=l36 lab=SELp1}
C {devices/lab_pin.sym} 750 -50 0 0 {name=l37 lab=SELn2}
C {devices/lab_pin.sym} 750 -30 0 0 {name=l38 lab=SELp2}
C {devices/lab_pin.sym} 750 -10 0 0 {name=l39 lab=SELn3}
C {devices/lab_pin.sym} 750 10 0 0 {name=l40 lab=SELp3}
C {devices/lab_pin.sym} 750 30 0 0 {name=l41 lab=SELn4}
C {devices/lab_pin.sym} 750 50 0 0 {name=l42 lab=SELp4}
C {devices/lab_pin.sym} 1050 -210 0 0 {name=l43 lab=TOP_N}
C {devices/lab_pin.sym} 1050 -190 0 0 {name=l44 lab=TOP_P}
C {devices/lab_pin.sym} 750 70 0 0 {name=l45 lab=SELp5}
C {devices/lab_pin.sym} 750 90 0 0 {name=l46 lab=SELn5}
C {devices/lab_pin.sym} 750 110 0 0 {name=l47 lab=SELp6}
C {devices/lab_pin.sym} 750 130 0 0 {name=l48 lab=SELn6}
C {devices/lab_pin.sym} 750 150 0 0 {name=l49 lab=SELn7}
C {devices/lab_pin.sym} 750 170 0 0 {name=l50 lab=SELp7}
C {devices/lab_pin.sym} 750 190 0 0 {name=l51 lab=SELn8}
C {devices/lab_pin.sym} 750 210 0 0 {name=l52 lab=SELp8}

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
* PH_B9 is the one ring phase this integration level now names (issue #263):
* the MSB-trial phase gates both the half-LSB offset cap's enable
* (HALF_LSB_EN = BUSY AND NOT PH_B9, so the offset lands a full CLK period
* after the sampling switch opens) and the comparator-OUTN dummy mux's own
* select pin (so the dummy load mirrors xmux9's state cycle by cycle). The
* other ring phases PH_B8..PH_B0/PH_EOC stay unconnected here, exactly as
* the header's "internal to the SAR control loop" note describes.
C {devices/lab_pin.sym} 2850 -200 0 0 {name=l_phb9 lab=PH_B9}
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
* --- Decision-directed single-side CDAC switching (issue #263, Root cause
* item 3): SELp<i>/SELn<i> are no longer driven unconditionally and
* complementarily off DOUT<i> alone (that made every bit move BOTH array
* sides oppositely, a native 2-LSB-per-bit step that cannot decode to the
* ratified sign + 9-bit-magnitude N=10 code -- see the top header's
* "UPDATE (#263)" paragraph for the full derivation). Instead each bit's
* decision only switches the ONE side consistent with DOUT9 (the free sign
* bit, resolved before any of these bits move): DOUT9=1 (Vd>=0) enables ONLY
* SELp<i> = DOUT<i>, holding SELn<i> = 0 (BOT_n pinned at VREFP); DOUT9=0
* (Vd<0) enables ONLY SELn<i> = DOUT<i>, holding SELp<i> = 0 (BOT_p pinned
* at VREFP). At the shared baseline DOUT<i>=0, both SELp<i>=SELn<i>=0 (both
* plates at VREFP) regardless of DOUT9, so the array's zero-code state is
* sign-independent -- exactly the neutral starting point the per-conversion
* CDAC clear (issue #263 Root cause item 2, sar_sequencer.sch) needs. Each
* bit now moves exactly one plate by one reference swing, halving the
* array's native step to 1 LSB/bit, matching the w_i=2^i weights
* sim/full-conversion-transient's ideal_code() already assumes.
C {sky130_stdcells/inv_1.sym} 1400 1450 0 0 {name=xinv_dout9n VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1360 1450 0 0 {name=l_dout9n_a lab=DOUT9}
C {devices/lab_pin.sym} 1440 1450 0 0 {name=l_dout9n_y lab=DOUT9N}
C {sky130_stdcells/and2_1.sym} 1400 500 0 0 {name=xand_seln0 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1340 480 0 0 {name=l_seln0_a lab=DOUT0}
C {devices/lab_pin.sym} 1340 520 0 0 {name=l_seln0_b lab=DOUT9N}
C {devices/lab_pin.sym} 1460 500 0 0 {name=l_seln0_y lab=SELn0}
C {sky130_stdcells/and2_1.sym} 1650 500 0 0 {name=xand_selp0 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1590 480 0 0 {name=l_selp0_a lab=DOUT9}
C {devices/lab_pin.sym} 1590 520 0 0 {name=l_selp0_b lab=DOUT0}
C {devices/lab_pin.sym} 1710 500 0 0 {name=l_selp0_y lab=SELp0}
C {sky130_stdcells/and2_1.sym} 1400 600 0 0 {name=xand_seln1 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1340 580 0 0 {name=l_seln1_a lab=DOUT1}
C {devices/lab_pin.sym} 1340 620 0 0 {name=l_seln1_b lab=DOUT9N}
C {devices/lab_pin.sym} 1460 600 0 0 {name=l_seln1_y lab=SELn1}
C {sky130_stdcells/and2_1.sym} 1650 600 0 0 {name=xand_selp1 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1590 580 0 0 {name=l_selp1_a lab=DOUT9}
C {devices/lab_pin.sym} 1590 620 0 0 {name=l_selp1_b lab=DOUT1}
C {devices/lab_pin.sym} 1710 600 0 0 {name=l_selp1_y lab=SELp1}
C {sky130_stdcells/and2_1.sym} 1400 700 0 0 {name=xand_seln2 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1340 680 0 0 {name=l_seln2_a lab=DOUT2}
C {devices/lab_pin.sym} 1340 720 0 0 {name=l_seln2_b lab=DOUT9N}
C {devices/lab_pin.sym} 1460 700 0 0 {name=l_seln2_y lab=SELn2}
C {sky130_stdcells/and2_1.sym} 1650 700 0 0 {name=xand_selp2 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1590 680 0 0 {name=l_selp2_a lab=DOUT9}
C {devices/lab_pin.sym} 1590 720 0 0 {name=l_selp2_b lab=DOUT2}
C {devices/lab_pin.sym} 1710 700 0 0 {name=l_selp2_y lab=SELp2}
C {sky130_stdcells/and2_1.sym} 1400 800 0 0 {name=xand_seln3 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1340 780 0 0 {name=l_seln3_a lab=DOUT3}
C {devices/lab_pin.sym} 1340 820 0 0 {name=l_seln3_b lab=DOUT9N}
C {devices/lab_pin.sym} 1460 800 0 0 {name=l_seln3_y lab=SELn3}
C {sky130_stdcells/and2_1.sym} 1650 800 0 0 {name=xand_selp3 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1590 780 0 0 {name=l_selp3_a lab=DOUT9}
C {devices/lab_pin.sym} 1590 820 0 0 {name=l_selp3_b lab=DOUT3}
C {devices/lab_pin.sym} 1710 800 0 0 {name=l_selp3_y lab=SELp3}
C {sky130_stdcells/and2_1.sym} 1400 900 0 0 {name=xand_seln4 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1340 880 0 0 {name=l_seln4_a lab=DOUT4}
C {devices/lab_pin.sym} 1340 920 0 0 {name=l_seln4_b lab=DOUT9N}
C {devices/lab_pin.sym} 1460 900 0 0 {name=l_seln4_y lab=SELn4}
C {sky130_stdcells/and2_1.sym} 1650 900 0 0 {name=xand_selp4 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1590 880 0 0 {name=l_selp4_a lab=DOUT9}
C {devices/lab_pin.sym} 1590 920 0 0 {name=l_selp4_b lab=DOUT4}
C {devices/lab_pin.sym} 1710 900 0 0 {name=l_selp4_y lab=SELp4}
C {sky130_stdcells/and2_1.sym} 1400 1000 0 0 {name=xand_seln5 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1340 980 0 0 {name=l_seln5_a lab=DOUT5}
C {devices/lab_pin.sym} 1340 1020 0 0 {name=l_seln5_b lab=DOUT9N}
C {devices/lab_pin.sym} 1460 1000 0 0 {name=l_seln5_y lab=SELn5}
C {sky130_stdcells/and2_1.sym} 1650 1000 0 0 {name=xand_selp5 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1590 980 0 0 {name=l_selp5_a lab=DOUT9}
C {devices/lab_pin.sym} 1590 1020 0 0 {name=l_selp5_b lab=DOUT5}
C {devices/lab_pin.sym} 1710 1000 0 0 {name=l_selp5_y lab=SELp5}
C {sky130_stdcells/and2_1.sym} 1400 1100 0 0 {name=xand_seln6 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1340 1080 0 0 {name=l_seln6_a lab=DOUT6}
C {devices/lab_pin.sym} 1340 1120 0 0 {name=l_seln6_b lab=DOUT9N}
C {devices/lab_pin.sym} 1460 1100 0 0 {name=l_seln6_y lab=SELn6}
C {sky130_stdcells/and2_1.sym} 1650 1100 0 0 {name=xand_selp6 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1590 1080 0 0 {name=l_selp6_a lab=DOUT9}
C {devices/lab_pin.sym} 1590 1120 0 0 {name=l_selp6_b lab=DOUT6}
C {devices/lab_pin.sym} 1710 1100 0 0 {name=l_selp6_y lab=SELp6}
C {sky130_stdcells/and2_1.sym} 1400 1200 0 0 {name=xand_seln7 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1340 1180 0 0 {name=l_seln7_a lab=DOUT7}
C {devices/lab_pin.sym} 1340 1220 0 0 {name=l_seln7_b lab=DOUT9N}
C {devices/lab_pin.sym} 1460 1200 0 0 {name=l_seln7_y lab=SELn7}
C {sky130_stdcells/and2_1.sym} 1650 1200 0 0 {name=xand_selp7 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1590 1180 0 0 {name=l_selp7_a lab=DOUT9}
C {devices/lab_pin.sym} 1590 1220 0 0 {name=l_selp7_b lab=DOUT7}
C {devices/lab_pin.sym} 1710 1200 0 0 {name=l_selp7_y lab=SELp7}
C {sky130_stdcells/and2_1.sym} 1400 1300 0 0 {name=xand_seln8 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1340 1280 0 0 {name=l_seln8_a lab=DOUT8}
C {devices/lab_pin.sym} 1340 1320 0 0 {name=l_seln8_b lab=DOUT9N}
C {devices/lab_pin.sym} 1460 1300 0 0 {name=l_seln8_y lab=SELn8}
C {sky130_stdcells/and2_1.sym} 1650 1300 0 0 {name=xand_selp8 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1590 1280 0 0 {name=l_selp8_a lab=DOUT9}
C {devices/lab_pin.sym} 1590 1320 0 0 {name=l_selp8_b lab=DOUT8}
C {devices/lab_pin.sym} 1710 1300 0 0 {name=l_selp8_y lab=SELp8}

* --- offset-binary output recoding, bits 8..0 (issue #263). DOUT<i> (the
* internal SAR register, driving SELp<i>/SELn<i> above) is NECESSARILY a
* SIGN + TRUE-MAGNITUDE value for the DOUT9=0 branch: the search's own
* keep/revert decisions physically track |residual|, since only ONE side's
* plates ever move and they always move TOWARD zero from the DOUT9=0
* branch's own starting point (see the "UPDATE (#263)" header paragraph).
* Straight sum(DOUT<i>*2^i) therefore reproduces the ratified offset-binary
* code ONLY for DOUT9=1 (there, offset-binary magnitude and true magnitude
* are the same number by construction); for DOUT9=0 the ratified
* offset-binary magnitude is `512 - true_magnitude`, not `true_magnitude`
* itself -- the array's own DOUT8..0 bits, read directly, are the WRONG
* number for that branch (empirically: a -0.25*V_REF input's raw DOUT8..0
* read back true_magnitude~=128, not the ratified offset code's own
* magnitude field 384). ADCOUT<i> = DOUT<i> XOR DOUT9N recodes this for
* readout ONLY: passthrough (ADCOUT<i>=DOUT<i>) when DOUT9=1 (already
* correct), bitwise-complement when DOUT9=0 (511-true_magnitude, off from
* the exact ratified value 512-true_magnitude by at most 1 LSB -- the
* ones'-complement-vs-512-subtraction rounding gap, within the +-1 LSB
* acceptance tolerance). This does NOT feed back into SELp/SELn -- the
* internal search register DOUT<i> is unchanged and remains what the
* array/comparator loop actually operates on; ADCOUT<i> is a read-only
* final recoding stage, exactly the role a two's-complement/offset-binary
* output converter plays in many real SAR ADCs. ADCOUT9 is not a separate
* net -- the sign bit needs no recoding, so sim/full-conversion-transient/
* continues to read DOUT9 directly for bit 9.
C {sky130_stdcells/xor2_1.sym} 1900 500 0 0 {name=xxor_code0 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1840 480 0 0 {name=l_code0_a lab=DOUT0}
C {devices/lab_pin.sym} 1840 520 0 0 {name=l_code0_b lab=DOUT9N}
C {devices/lab_pin.sym} 1960 500 0 0 {name=l_code0_y lab=ADCOUT0}
C {sky130_stdcells/xor2_1.sym} 1900 600 0 0 {name=xxor_code1 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1840 580 0 0 {name=l_code1_a lab=DOUT1}
C {devices/lab_pin.sym} 1840 620 0 0 {name=l_code1_b lab=DOUT9N}
C {devices/lab_pin.sym} 1960 600 0 0 {name=l_code1_y lab=ADCOUT1}
C {sky130_stdcells/xor2_1.sym} 1900 700 0 0 {name=xxor_code2 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1840 680 0 0 {name=l_code2_a lab=DOUT2}
C {devices/lab_pin.sym} 1840 720 0 0 {name=l_code2_b lab=DOUT9N}
C {devices/lab_pin.sym} 1960 700 0 0 {name=l_code2_y lab=ADCOUT2}
C {sky130_stdcells/xor2_1.sym} 1900 800 0 0 {name=xxor_code3 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1840 780 0 0 {name=l_code3_a lab=DOUT3}
C {devices/lab_pin.sym} 1840 820 0 0 {name=l_code3_b lab=DOUT9N}
C {devices/lab_pin.sym} 1960 800 0 0 {name=l_code3_y lab=ADCOUT3}
C {sky130_stdcells/xor2_1.sym} 1900 900 0 0 {name=xxor_code4 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1840 880 0 0 {name=l_code4_a lab=DOUT4}
C {devices/lab_pin.sym} 1840 920 0 0 {name=l_code4_b lab=DOUT9N}
C {devices/lab_pin.sym} 1960 900 0 0 {name=l_code4_y lab=ADCOUT4}
C {sky130_stdcells/xor2_1.sym} 1900 1000 0 0 {name=xxor_code5 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1840 980 0 0 {name=l_code5_a lab=DOUT5}
C {devices/lab_pin.sym} 1840 1020 0 0 {name=l_code5_b lab=DOUT9N}
C {devices/lab_pin.sym} 1960 1000 0 0 {name=l_code5_y lab=ADCOUT5}
C {sky130_stdcells/xor2_1.sym} 1900 1100 0 0 {name=xxor_code6 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1840 1080 0 0 {name=l_code6_a lab=DOUT6}
C {devices/lab_pin.sym} 1840 1120 0 0 {name=l_code6_b lab=DOUT9N}
C {devices/lab_pin.sym} 1960 1100 0 0 {name=l_code6_y lab=ADCOUT6}
C {sky130_stdcells/xor2_1.sym} 1900 1200 0 0 {name=xxor_code7 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1840 1180 0 0 {name=l_code7_a lab=DOUT7}
C {devices/lab_pin.sym} 1840 1220 0 0 {name=l_code7_b lab=DOUT9N}
C {devices/lab_pin.sym} 1960 1200 0 0 {name=l_code7_y lab=ADCOUT7}
C {sky130_stdcells/xor2_1.sym} 1900 1300 0 0 {name=xxor_code8 VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1840 1280 0 0 {name=l_code8_a lab=DOUT8}
C {devices/lab_pin.sym} 1840 1320 0 0 {name=l_code8_b lab=DOUT9N}
C {devices/lab_pin.sym} 1960 1300 0 0 {name=l_code8_y lab=ADCOUT8}

* --- Comparator differential-output load balancing (issue #263, second
* pass): a matched dummy load on comparator.OUTN (net OUTN_NC), mirroring
* the two standard-cell input pins COMP_OUT drives inside xseq. Same cells
* (mux2_1 + xnor2_1), same pin positions (mux A1, xnor A), and the same
* nets on their other inputs (mux A0 = DOUT9, mux S = PH_B9, xnor B =
* DOUT9) as design/sar_sequencer.sch's xmux9 / xxnor_compeff, so the two
* comparator output nodes see equal, equally state-dependent capacitance.
* Without this, OUTP is the heavier node and the latch is biased toward
* COMP_OUT=1, a systematic 1.5-3 LSB input-referred offset -- see the
* header's "COMPARATOR DIFFERENTIAL-OUTPUT LOAD BALANCING" section for the
* measured numbers. Both outputs are deliberate no-connects.
C {sky130_stdcells/mux2_1.sym} 1700 1700 0 0 {name=xdum_mux_n VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1660 1680 0 0 {name=l_dummux_a0 lab=DOUT9}
C {devices/lab_pin.sym} 1660 1720 0 0 {name=l_dummux_a1 lab=OUTN_NC}
C {devices/lab_pin.sym} 1660 1760 0 0 {name=l_dummux_s lab=PH_B9}
C {devices/lab_pin.sym} 1740 1700 0 0 {name=l_dummux_x lab=DUMLOAD_MUX_NC}
C {sky130_stdcells/xnor2_1.sym} 1700 1850 0 0 {name=xdum_xnor_n VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 1640 1830 0 0 {name=l_dumxnor_a lab=OUTN_NC}
C {devices/lab_pin.sym} 1640 1870 0 0 {name=l_dumxnor_b lab=DOUT9}
C {devices/lab_pin.sym} 1760 1850 0 0 {name=l_dumxnor_y lab=DUMLOAD_XNOR_NC}

* --- Half-LSB quantizer offset (issue #263, second pass). HALF_LSB_EN =
* BUSY AND NOT(PH_B9): asserted from the PH_B9 -> PH_B8 edge (one whole
* CLK period after the sampling switch opens, so the offset charge cannot
* leak back into the input source) through PH_EOC, de-asserted for the
* whole SAMPLE phase. See the header's "HALF-LSB QUANTIZER OFFSET"
* section.
C {sky130_stdcells/and2b_1.sym} 2200 1700 0 0 {name=xand_halflsb VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 2140 1680 0 0 {name=l_hl_an lab=PH_B9}
C {devices/lab_pin.sym} 2140 1720 0 0 {name=l_hl_b lab=BUSY}
C {devices/lab_pin.sym} 2260 1700 0 0 {name=l_hl_x lab=HALF_LSB_EN}
C {sky130_stdcells/inv_1.sym} 2200 1800 0 0 {name=xinv_halflsb VNB=VGND VPB=VPWR}
C {devices/lab_pin.sym} 2160 1800 0 0 {name=l_hln_a lab=HALF_LSB_EN}
C {devices/lab_pin.sym} 2240 1800 0 0 {name=l_hln_y lab=HALF_LSB_ENN}

* --- Offset cell, n side (the one that actually creates the +0.5 LSB shift
* of TOP_P-TOP_N): one CDAC-unit-sized MiM cap from TOP_N to BOT_OFF_N,
* whose bottom plate sits at VREFP while HALF_LSB_EN=0 (Moff_n_refp) and at
* VCM while HALF_LSB_EN=1 (the Moff_n_cmn/Moff_n_cmp transmission pair --
* VCM is mid-rail, so a single device would be a poor switch there).
* Device flavours/sizes are copied from design/cdac/cdac_unit_cell.sch so
* this cell's switch parasitics match a real array bit's.
C {sky130_fd_pr/cap_mim_m3_1.sym} 2600 1700 0 0 {name=Choff_n model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=1 spiceprefix=X}
C {devices/lab_pin.sym} 2600 1670 0 0 {name=l_offn_bot lab=BOT_OFF_N}
C {devices/lab_pin.sym} 2600 1730 0 0 {name=l_offn_top lab=TOP_N}
C {sky130_fd_pr/pfet_01v8.sym} 2800 1700 0 0 {name=Moff_n_refp W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {devices/lab_pin.sym} 2820 1730 0 0 {name=l_offn_p_d lab=BOT_OFF_N}
C {devices/lab_pin.sym} 2780 1700 0 0 {name=l_offn_p_g lab=HALF_LSB_EN}
C {devices/lab_pin.sym} 2820 1670 0 0 {name=l_offn_p_s lab=VREFP}
C {devices/lab_pin.sym} 2820 1700 0 0 {name=l_offn_p_b lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} 2800 1850 0 0 {name=Moff_n_cmn W=1 L=0.15 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {devices/lab_pin.sym} 2820 1820 0 0 {name=l_offn_n_d lab=BOT_OFF_N}
C {devices/lab_pin.sym} 2780 1850 0 0 {name=l_offn_n_g lab=HALF_LSB_EN}
C {devices/lab_pin.sym} 2820 1880 0 0 {name=l_offn_n_s lab=VCM}
C {devices/gnd.sym} 2820 1850 0 0 {name=l_offn_n_b lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 2800 2000 0 0 {name=Moff_n_cmp W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {devices/lab_pin.sym} 2820 2030 0 0 {name=l_offn_cp_d lab=BOT_OFF_N}
C {devices/lab_pin.sym} 2780 2000 0 0 {name=l_offn_cp_g lab=HALF_LSB_ENN}
C {devices/lab_pin.sym} 2820 1970 0 0 {name=l_offn_cp_s lab=VCM}
C {devices/lab_pin.sym} 2820 2000 0 0 {name=l_offn_cp_b lab=VDD}

* --- Offset cell, p side: the matching dummy. Identical cap and switch
* devices to the n-side cell above, but with every gate tied off (VGND /
* VPWR) so BOT_OFF_P is held at VREFP for the whole conversion and this
* cell contributes NO offset. Its only job is to give TOP_P the same total
* capacitance and the same switch junction parasitics as TOP_N, so the
* DOUT9=1 and DOUT9=0 branches have the same gain.
C {sky130_fd_pr/cap_mim_m3_1.sym} 2600 2200 0 0 {name=Choff_p model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=1 spiceprefix=X}
C {devices/lab_pin.sym} 2600 2170 0 0 {name=l_offp_bot lab=BOT_OFF_P}
C {devices/lab_pin.sym} 2600 2230 0 0 {name=l_offp_top lab=TOP_P}
C {sky130_fd_pr/pfet_01v8.sym} 2800 2200 0 0 {name=Moff_p_refp W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {devices/lab_pin.sym} 2820 2230 0 0 {name=l_offp_p_d lab=BOT_OFF_P}
C {devices/lab_pin.sym} 2780 2200 0 0 {name=l_offp_p_g lab=VGND}
C {devices/lab_pin.sym} 2820 2170 0 0 {name=l_offp_p_s lab=VREFP}
C {devices/lab_pin.sym} 2820 2200 0 0 {name=l_offp_p_b lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} 2800 2350 0 0 {name=Moff_p_cmn W=1 L=0.15 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {devices/lab_pin.sym} 2820 2320 0 0 {name=l_offp_n_d lab=BOT_OFF_P}
C {devices/lab_pin.sym} 2780 2350 0 0 {name=l_offp_n_g lab=VGND}
C {devices/lab_pin.sym} 2820 2380 0 0 {name=l_offp_n_s lab=VCM}
C {devices/gnd.sym} 2820 2350 0 0 {name=l_offp_n_b lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 2800 2500 0 0 {name=Moff_p_cmp W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {devices/lab_pin.sym} 2820 2530 0 0 {name=l_offp_cp_d lab=BOT_OFF_P}
C {devices/lab_pin.sym} 2780 2500 0 0 {name=l_offp_cp_g lab=VPWR}
C {devices/lab_pin.sym} 2820 2470 0 0 {name=l_offp_cp_s lab=VCM}
C {devices/lab_pin.sym} 2820 2500 0 0 {name=l_offp_cp_b lab=VDD}

T {sar_adc_top: SAR ADC top-level integration (issue #56) -- see header for architecture, pin-convention normalization, and known integration gaps} -1300 -600 0 0 0.2 0.2 {}

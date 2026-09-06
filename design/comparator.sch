v {xschem version=3.4.7 file_version=1.2
* comparator.sch -- dynamic (StrongARM-class) latched comparator core (issue
* #54; reset-integrity topology amendment, issue #175 / DR-004 Amendment A)
*
* Topology: 11-device single-tail StrongARM dynamic latch -- tail switch +
* NMOS input pair (drains on the internal nodes DIP/DIN) + cross-coupled
* NMOS/PMOS regenerative latch (the NMOS half SOURCING from DIP/DIN) + two
* CLK-gated PMOS precharge pairs, one on the output nodes and one on DIP/DIN.
* No preamp stage -- see spec/decision-records/DR-004-comparator-topology-and-noise-budget.md
* for why a static preamp is not used at this supply (DR-001 Consequence #3: thin
* 1.8V headroom stack forecloses a static preamp; DR-003 Item 1 quantifies the
* ~23 mV nominal common-mode headroom margin this topology inherits).
*
* WHAT ISSUE #175 CHANGED, AND WHY. Through PR #176 this was a 9-device
* variant in which the input pair's drains WERE the output nodes and the
* cross-coupled NMOS pair's sources were hard-wired to GND. Those NMOS
* devices therefore conducted throughout the CLK=0 reset phase, fighting the
* reset PMOS pair: record sim/comparator-decision/records/
* 20260906-052758-662a84d.md measured a reset-phase output level of ~0.78*VDD
* rather than the rail, and 0.52-1.25 mA of STATIC reset-phase supply current
* -- both consequences of a DC path VDD -> reset PMOS -> output node -> latch
* NMOS -> GND being open the whole time. That balanced level was an UNSTABLE
* equilibrium (both latch NMOS above threshold, cross-coupled loop gain above
* unity), so corner/temperature asymmetry was amplified to the rails inside
* the reset window: its Vindiff = 0 mV reset-integrity negative control FAILED
* at 3 of the 9 ratified corner points, and at some corners the reset phase's
* own DC operating point was already a decided state. That is a functional
* defect, not merely a timing one -- the latch entered a bit trial already
* committed to an output.
*
* The amendment is the textbook StrongARM arrangement: give the input pair
* its own drain nodes DIP/DIN, return the latch NMOS sources to those nodes,
* and precharge DIP/DIN to VDD alongside OUTP/OUTN. During reset every latch
* device then sits at Vgs = 0 exactly (gate at VDD from the opposite
* precharged output, source at VDD), so the cross-coupled loop gain is zero,
* the reset state is a STABLE equilibrium, and no DC path exists at all.
*
* This is a generic, widely-published dynamic-comparator topology (textbook/
* literature circuit class, e.g. Razavi's 'Design of Analog CMOS Integrated
* Circuits'), sized here from first principles against sky130 device models --
* not reverse-engineered or ported from any specific implementation, per
* CLAUDE.md's clean-room rule.
*
* Node convention (differential decision, non-inverting) -- UNCHANGED by the
* amendment: XM_INN (gate VINN) discharges DIP, and DIP is the node XM_LATN_P
* (drain OUTP) sources from, so a larger VINN still pulls OUTP down.
*   Vin,diff = VINP - VINN > 0  =>  OUTP settles high (VDD), OUTN settles low (0)
*   Vin,diff = VINP - VINN < 0  =>  OUTN settles high (VDD), OUTP settles low (0)
*   CLK = 0 (reset/precharge): tail off, and all four of OUTP/OUTN/DIP/DIN
*     precharge to the rail. Verified at every ratified corner point after the
*     #175 amendment: pre-evaluate-edge v(OUTP)-v(OUTN) = 0.000000 V with zero
*     static supply current, where the pre-amendment device set settled to a
*     mid-rail unstable point and diverged at 3 of 9 corners (see above).
*   CLK = VDD (evaluate): tail on; the input pair discharges DIP/DIN at
*     differential rates (the integration phase, during which the latch pairs
*     are still off at Vgs ~ 0), and once DIP/DIN fall about a threshold below
*     the outputs the cross-coupled pairs turn on and regenerate to the rails.
*
* Ports (net labels below, no drawn wires -- xschem joins same-named labels):
*   VDD, GND -- supply rails
*   CLK      -- clock (0=reset/precharge, VDD=evaluate)
*   VINP, VINN -- differential inputs
*   OUTP, OUTN -- differential outputs (regenerate to the rails)
* Internal nodes (not ports): TAIL, and -- new with #175 -- DIP/DIN, the
* input pair's own drain nodes that the latch NMOS pair sources from.
*
* This is a leaf/core schematic only -- VDD/CLK/VINP/VINN have no on-page
* source, by design (stimulus lives in the sim/comparator-decision/
* testbench, kept decoupled from this schematic per this repo's existing
* convention -- see sim/harness-corner-smoke/testbench/*.spice, which are
* likewise hand-authored SPICE fragments, not derived from any schematic).
* Historical note (accurate through #54/#60, superseded by #56): before
* issue #56 added the ipin.sym/opin.sym port objects below, netlisting THIS
* file alone (docs/environment-setup.md's xschem -x -n -s -q flow) reported
* a NONZERO xschem exit code -- verified empirically to be xschem's own
* electrical-rule check flagging four undriven top-level nets, not a
* missing-symbol or netlisting error: stdout/stderr were both empty and the
* emitted netlist was complete and correct (9 devices at the time, all
* sky130_fd_pr__{n,p}fet_01v8). Declaring VDD/CLK/VINP/VINN/OUTP/OUTN as real
* hierarchical ports (needed so #56's top-level integration can generate an
* instantiable symbol from this schematic) satisfies that same
* electrical-rule check, so a fresh standalone netlist of this file now
* exits 0 -- verified empirically after #56's port additions, and re-verified
* after #175's amendment (exit 0, 11 devices). #175 DID re-generate
* sim/comparator-decision/testbench/comparator_core.spice from this file, by
* the documented xschem flow: that fragment is what the testbench simulates,
* so a topology change that did not propagate into it would leave every
* subsequent record describing a netlist that no longer exists. CLAUDE.md's
* append-only rule governs the RECORDS under sim/*/records/, which are never
* rewritten -- #175 mints new ones that supersede their predecessors rather
* than editing them.
*
* Device sizing (all L=0.5um, nf=1 -- provisional planning geometry, NOT a
* final sizing result; see the decision record above):
*   M_TAIL            W=8um  -- tail switch, wide for low Ron / adequate current
*   M_INN, M_INP      W=4um  -- input pair; matches DR-003's Vth-probe planning
*                                geometry (spec/dr-003-support/vth_probe.spice)
*   M_LATN_P/N        W=4um  -- NMOS cross-coupled latch pair (sources on
*                                DIP/DIN since #175, not GND)
*   M_LATP_P/N        W=8um  -- PMOS cross-coupled latch pair, 2x NMOS width to
*                                partially balance sky130's electron/hole mobility ratio
*   M_RST_P/N         W=16um -- PMOS reset/precharge switches on the OUTPUT
*                                nodes. HISTORICAL SIZING JUSTIFICATION, NOW
*                                SUPERSEDED: W=16um (4x the latch pair) was
*                                forced empirically because W=4um could not
*                                override the latch NMOS pair's direct-to-GND
*                                pull-down during reset. #175 removed that
*                                contention entirely (the pull-down path no
*                                longer exists), so the width is no longer
*                                required by that argument. It is deliberately
*                                left UNCHANGED here so #175 carries exactly
*                                one topology delta and its re-characterization
*                                is attributable to that delta alone; the
*                                now-unmotivated width is carried as an Open
*                                item in DR-004 Amendment A, not silently
*                                re-tuned. Oversizing costs output-node
*                                capacitance (slower regeneration), not
*                                correctness.
*   M_RST_DIP/DIN     W=4um  -- PMOS precharge switches on DIP/DIN, added by
*                                #175. These face no contention at all (the
*                                tail is off during reset, and once DIP/DIN
*                                reach VDD the latch NMOS pair is at Vgs=0),
*                                so they are sized to match the latch NMOS
*                                pair they precharge against rather than
*                                oversized like M_RST_P/N -- keeping the
*                                added parasitic on the signal-critical
*                                integration nodes small.
*
* Every device is nfet_01v8/pfet_01v8 (ratified 1.8V core flavour, DR-001) --
* no _g5v0d10v5 or other non-ratified flavour anywhere in this schematic.
}
G {}
V {}
S {}
E {}
C {sky130_fd_pr/nfet_01v8.sym} 0 0 0 0 {name=M_TAIL W=8 L=0.5 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 100 0 0 0 {name=M_INN W=4 L=0.5 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 200 0 0 0 {name=M_INP W=4 L=0.5 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 300 0 0 0 {name=M_LATN_P W=4 L=0.5 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 400 0 0 0 {name=M_LATN_N W=4 L=0.5 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 500 0 0 0 {name=M_LATP_P W=8 L=0.5 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 600 0 0 0 {name=M_LATP_N W=8 L=0.5 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 700 0 0 0 {name=M_RST_P W=16 L=0.5 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 800 0 0 0 {name=M_RST_N W=16 L=0.5 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 900 0 0 0 {name=M_RST_DIP W=4 L=0.5 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 1000 0 0 0 {name=M_RST_DIN W=4 L=0.5 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {devices/lab_pin.sym} 20 -30 0 0 {name=l1 sig_type=std_logic lab=TAIL}
C {devices/lab_pin.sym} -20 0 0 0 {name=l2 sig_type=std_logic lab=CLK}
C {devices/gnd.sym} 20 30 0 0 {name=lgnd3 lab=GND}
C {devices/gnd.sym} 20 0 0 0 {name=lgnd4 lab=GND}
C {devices/lab_pin.sym} 120 -30 0 0 {name=l5 sig_type=std_logic lab=DIP}
C {devices/lab_pin.sym} 80 0 0 0 {name=l6 sig_type=std_logic lab=VINN}
C {devices/lab_pin.sym} 120 30 0 0 {name=l7 sig_type=std_logic lab=TAIL}
C {devices/gnd.sym} 120 0 0 0 {name=lgnd8 lab=GND}
C {devices/lab_pin.sym} 220 -30 0 0 {name=l9 sig_type=std_logic lab=DIN}
C {devices/lab_pin.sym} 180 0 0 0 {name=l10 sig_type=std_logic lab=VINP}
C {devices/lab_pin.sym} 220 30 0 0 {name=l11 sig_type=std_logic lab=TAIL}
C {devices/gnd.sym} 220 0 0 0 {name=lgnd12 lab=GND}
C {devices/lab_pin.sym} 320 -30 0 0 {name=l13 sig_type=std_logic lab=OUTP}
C {devices/lab_pin.sym} 280 0 0 0 {name=l14 sig_type=std_logic lab=OUTN}
C {devices/lab_pin.sym} 320 30 0 0 {name=l15 sig_type=std_logic lab=DIP}
C {devices/gnd.sym} 320 0 0 0 {name=lgnd16 lab=GND}
C {devices/lab_pin.sym} 420 -30 0 0 {name=l17 sig_type=std_logic lab=OUTN}
C {devices/lab_pin.sym} 380 0 0 0 {name=l18 sig_type=std_logic lab=OUTP}
C {devices/lab_pin.sym} 420 30 0 0 {name=l19 sig_type=std_logic lab=DIN}
C {devices/gnd.sym} 420 0 0 0 {name=lgnd20 lab=GND}
C {devices/lab_pin.sym} 520 30 0 0 {name=l21 sig_type=std_logic lab=OUTP}
C {devices/lab_pin.sym} 480 0 0 0 {name=l22 sig_type=std_logic lab=OUTN}
C {devices/lab_pin.sym} 520 -30 0 0 {name=l23 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 520 0 0 0 {name=l24 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 620 30 0 0 {name=l25 sig_type=std_logic lab=OUTN}
C {devices/lab_pin.sym} 580 0 0 0 {name=l26 sig_type=std_logic lab=OUTP}
C {devices/lab_pin.sym} 620 -30 0 0 {name=l27 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 620 0 0 0 {name=l28 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 720 30 0 0 {name=l29 sig_type=std_logic lab=OUTP}
C {devices/lab_pin.sym} 680 0 0 0 {name=l30 sig_type=std_logic lab=CLK}
C {devices/lab_pin.sym} 720 -30 0 0 {name=l31 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 720 0 0 0 {name=l32 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 820 30 0 0 {name=l33 sig_type=std_logic lab=OUTN}
C {devices/lab_pin.sym} 780 0 0 0 {name=l34 sig_type=std_logic lab=CLK}
C {devices/lab_pin.sym} 820 -30 0 0 {name=l35 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 820 0 0 0 {name=l36 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 920 30 0 0 {name=l37 sig_type=std_logic lab=DIP}
C {devices/lab_pin.sym} 880 0 0 0 {name=l38 sig_type=std_logic lab=CLK}
C {devices/lab_pin.sym} 920 -30 0 0 {name=l39 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 920 0 0 0 {name=l40 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 1020 30 0 0 {name=l41 sig_type=std_logic lab=DIN}
C {devices/lab_pin.sym} 980 0 0 0 {name=l42 sig_type=std_logic lab=CLK}
C {devices/lab_pin.sym} 1020 -30 0 0 {name=l43 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 1020 0 0 0 {name=l44 sig_type=std_logic lab=VDD}
C {devices/title.sym} 0 -260 0 0 {name=l_title author="2AM Logic (issue #54: dynamic comparator core, no preamp; issue #175: reset-integrity topology fix)"}
* --- Hierarchical port objects (issue #56 integration): added so this
* leaf schematic can generate an instantiable xschem symbol
* (design/comparator.sym, via make_sym.awk) with a drawn pin list, aligning
* with the ipin.sym/opin.sym convention already used by
* design/cdac/cdac_array.sch and design/sar_sequencer.sch -- per this
* schematic's own "Ports" list in the header comment above. These are pure
* ADDITIONS at existing net labels (VDD/CLK/VINP/VINN/OUTP/OUTN); no
* existing device or lab_pin instance above is touched. GND is intentionally
* NOT given a port object here: devices/gnd.sym is `global=true`, so it is
* already the same net at every level of hierarchy without a pin.
C {devices/ipin.sym} -100 -30 0 0 {name=p_vdd lab=VDD}
C {devices/ipin.sym} -100 30 0 0 {name=p_clk lab=CLK}
C {devices/ipin.sym} -100 90 0 0 {name=p_vinp lab=VINP}
C {devices/ipin.sym} -100 150 0 0 {name=p_vinn lab=VINN}
C {devices/opin.sym} -100 210 0 0 {name=p_outp lab=OUTP}
C {devices/opin.sym} -100 270 0 0 {name=p_outn lab=OUTN}


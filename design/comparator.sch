v {xschem version=3.4.7 file_version=1.2
* comparator.sch -- dynamic (StrongARM-class) latched comparator core (issue #54)
*
* Topology: classic 9-device single-tail dynamic latch (tail switch + NMOS
* input pair + cross-coupled NMOS/PMOS regenerative latch + PMOS reset pair).
* No preamp stage -- see spec/decision-records/DR-004-comparator-topology-and-noise-budget.md
* for why a static preamp is not used at this supply (DR-001 Consequence #3: thin
* 1.8V headroom stack forecloses a static preamp; DR-003 Item 1 quantifies the
* ~23 mV nominal common-mode headroom margin this topology inherits).
*
* This is a generic, widely-published dynamic-comparator topology (textbook/
* literature circuit class, e.g. Razavi's 'Design of Analog CMOS Integrated
* Circuits'), sized here from first principles against sky130 device models --
* not reverse-engineered or ported from any specific implementation, per
* CLAUDE.md's clean-room rule.
*
* Node convention (differential decision, non-inverting):
*   Vin,diff = VINP - VINN > 0  =>  OUTP settles high (VDD), OUTN settles low (0)
*   Vin,diff = VINP - VINN < 0  =>  OUTN settles high (VDD), OUTP settles low (0)
*   CLK = 0 (reset/precharge): tail off, OUTP=OUTN settle to a symmetric
*     intermediate voltage (empirically ~1.4V at tt/27C/1.8V from a fresh/
*     uninitialized start -- NOT a clean rail-to-rail VDD precharge; see the
*     W=16um reset-sizing note below for why an exact VDD precharge is not
*     reached, and why a symmetric intermediate point is sufficient: the
*     latch only needs an equal, defined starting point for evaluate to
*     regenerate correctly from, not literally VDD on both sides).
*   CLK = VDD (evaluate): tail on, differential pair steers latch regeneration
*
* Ports (net labels below, no drawn wires -- xschem joins same-named labels):
*   VDD, GND -- supply rails
*   CLK      -- clock (0=reset/precharge, VDD=evaluate)
*   VINP, VINN -- differential inputs
*   OUTP, OUTN -- differential outputs (regenerate to the rails)
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
* emitted netlist was complete and correct (9 devices, all
* sky130_fd_pr__{n,p}fet_01v8). Declaring VDD/CLK/VINP/VINN/OUTP/OUTN as real
* hierarchical ports (needed so #56's top-level integration can generate an
* instantiable symbol from this schematic) satisfies that same
* electrical-rule check, so a fresh standalone netlist of this file now
* exits 0 -- verified empirically after #56's port additions, with an
* unchanged 9-device list. sim/comparator-decision/testbench/
* comparator_core.spice (the committed, hand-derived device fragment #54's
* testbench actually simulates) is untouched by this -- it is append-only
* evidence per CLAUDE.md, and the only netlist-level effect of #56's port
* additions is a handful of inert `*.ipin`/`*.opin` comment lines, not a
* device or connectivity change.
*
* Device sizing (all L=0.5um, nf=1 -- provisional planning geometry, NOT a
* final sizing result; see the decision record above):
*   M_TAIL            W=8um  -- tail switch, wide for low Ron / adequate current
*   M_INN, M_INP      W=4um  -- input pair; matches DR-003's Vth-probe planning
*                                geometry (spec/dr-003-support/vth_probe.spice)
*   M_LATN_P/N        W=4um  -- NMOS cross-coupled latch pair
*   M_LATP_P/N        W=8um  -- PMOS cross-coupled latch pair, 2x NMOS width to
*                                partially balance sky130's electron/hole mobility ratio
*   M_RST_P/N         W=16um -- PMOS reset/precharge switches, deliberately
*                                oversized (4x the NMOS latch pair's W=4um).
*                                Verified empirically (sim/comparator-decision/)
*                                that W=4um reset devices are too weak to override
*                                the cross-coupled NMOS latch pair's own direct-to-
*                                GND pull-down during reset -- CLK=0 left a stale,
*                                asymmetric state carried over from the previous
*                                decision instead of a clean symmetric precharge.
*                                W=16um reliably restores symmetry within the
*                                testbench's reset window.
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
C {devices/lab_pin.sym} 20 -30 0 0 {name=l1 sig_type=std_logic lab=TAIL}
C {devices/lab_pin.sym} -20 0 0 0 {name=l2 sig_type=std_logic lab=CLK}
C {devices/gnd.sym} 20 30 0 0 {name=lgnd3 lab=GND}
C {devices/gnd.sym} 20 0 0 0 {name=lgnd4 lab=GND}
C {devices/lab_pin.sym} 120 -30 0 0 {name=l5 sig_type=std_logic lab=OUTP}
C {devices/lab_pin.sym} 80 0 0 0 {name=l6 sig_type=std_logic lab=VINN}
C {devices/lab_pin.sym} 120 30 0 0 {name=l7 sig_type=std_logic lab=TAIL}
C {devices/gnd.sym} 120 0 0 0 {name=lgnd8 lab=GND}
C {devices/lab_pin.sym} 220 -30 0 0 {name=l9 sig_type=std_logic lab=OUTN}
C {devices/lab_pin.sym} 180 0 0 0 {name=l10 sig_type=std_logic lab=VINP}
C {devices/lab_pin.sym} 220 30 0 0 {name=l11 sig_type=std_logic lab=TAIL}
C {devices/gnd.sym} 220 0 0 0 {name=lgnd12 lab=GND}
C {devices/lab_pin.sym} 320 -30 0 0 {name=l13 sig_type=std_logic lab=OUTP}
C {devices/lab_pin.sym} 280 0 0 0 {name=l14 sig_type=std_logic lab=OUTN}
C {devices/gnd.sym} 320 30 0 0 {name=lgnd15 lab=GND}
C {devices/gnd.sym} 320 0 0 0 {name=lgnd16 lab=GND}
C {devices/lab_pin.sym} 420 -30 0 0 {name=l17 sig_type=std_logic lab=OUTN}
C {devices/lab_pin.sym} 380 0 0 0 {name=l18 sig_type=std_logic lab=OUTP}
C {devices/gnd.sym} 420 30 0 0 {name=lgnd19 lab=GND}
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
C {devices/title.sym} 0 -260 0 0 {name=l_title author="2AM Logic (issue #54: dynamic comparator core, no preamp)"}
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


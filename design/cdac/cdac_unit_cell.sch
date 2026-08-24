v {xschem version=3.4.7 file_version=1.2
* cdac_unit_cell.sch -- CDAC differential-array unit cell (issue #53).
*
* One binary-weighted-array bit position's storage element: a single
* sky130_fd_pr__cap_mim_m3_1 unit capacitor (sized per
* spec/decision-records/DR-003-numeric-spec-derivation.md Item 3,
* W=L=1.8988 (um, bare-number sky130_fd_pr xschem convention) -> C_u ~= 8.654 fF, provisional pending #27) whose bottom
* plate (BOT) is switched between the two supply-referenced DAC
* references (VREFP, VREFN) by a single-control-line CMOS pull-up/
* pull-down pair -- NOT a conventional transmission gate. Both M1 (NMOS,
* pulls BOT to VREFN) and M2 (PMOS, pulls BOT to VREFP) are gated from
* the SAME net, SEL, because their opposite polarities already make them
* mutually exclusive:
*   SEL = 0 (low)  -> M2 (PMOS) ON  -> BOT = VREFP
*   SEL = 1 (high) -> M1 (NMOS) ON  -> BOT = VREFN
* See design/cdac/README.md for the full derivation and the array-level
* dummy/termination and matching strategy this unit cell feeds.
*
* Both switch devices are ratified-flavour 1.8 V core (nfet_01v8/
* pfet_01v8, DR-001) -- no _g5v0d10v5 or other flavour appears anywhere
* in this cell, satisfying issue #53's device-flavour acceptance
* criterion.
*
* Clean-room: this topology (cap + single-control-line CMOS bottom-plate
* switch) is derived from standard SAR-ADC/CDAC device physics, not
* ported from any other party's netlist. Where the *method* resembles
* 2AMLogic/gf180-sar-adc's own CDAC work (top-plate sampling, binary
* weighting, a terminating dummy unit) that is the explicit port-parity
* instruction in CLAUDE.md, not a coincidence -- the concrete switch
* topology here is a deliberate, documented simplification relative to
* gf180-sar-adc's MCS/Vcm three-way scheme (DR-0011 there); see
* spec/decision-records/DR-005-cdac-array-design.md "Alternatives
* considered" for why.
}
G {}
K {}
V {}
S {}
E {}
C {sky130_fd_pr/cap_mim_m3_1.sym} 0 0 0 0 {name=C1 model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=1 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 200 -100 0 0 {name=M1 W=1 L=0.15 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 200 100 0 0 {name=M2 W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {lab_pin.sym} 0 30 0 0 {name=l1 lab=TOP}
C {lab_pin.sym} 0 -30 0 0 {name=l2 lab=BOT}
C {lab_pin.sym} 220 -130 0 0 {name=l3 lab=BOT}
C {lab_pin.sym} 180 -100 0 0 {name=l4 lab=SEL}
C {lab_pin.sym} 220 -70 0 0 {name=l5 lab=VREFN}
C {lab_pin.sym} 220 -100 0 0 {name=l6 lab=VSS}
C {lab_pin.sym} 220 130 0 0 {name=l7 lab=BOT}
C {lab_pin.sym} 180 100 0 0 {name=l8 lab=SEL}
C {lab_pin.sym} 220 70 0 0 {name=l9 lab=VREFP}
C {lab_pin.sym} 220 100 0 0 {name=l10 lab=VDD}
C {ipin.sym} -300 -30 0 0 {name=p_top lab=TOP}
C {ipin.sym} -300 30 0 1 {name=p_bot lab=BOT}
C {ipin.sym} -300 -150 0 0 {name=p_sel lab=SEL}
C {ipin.sym} -300 200 0 0 {name=p_vrefp lab=VREFP}
C {ipin.sym} -300 250 0 0 {name=p_vrefn lab=VREFN}
C {ipin.sym} -300 300 0 0 {name=p_vdd lab=VDD}
C {ipin.sym} -300 350 0 0 {name=p_vss lab=VSS}
T {cdac unit cell: C_u = 8.654 fF (provisional, DR-003), MF=1} -100 -350 0 0 0.2 0.2 {}
T {M1=nfet_01v8 (BOT->VREFN @ SEL=1), M2=pfet_01v8 (BOT->VREFP @ SEL=0)} -100 -300 0 0 0.2 0.2 {}

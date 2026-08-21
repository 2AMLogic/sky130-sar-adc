v {xschem version=3.4.7 file_version=1.2
* cdac_array.sch -- differential charge-redistribution CDAC array
* (issue #53): binary-weighted 9-bit-per-side sub-array + a fixed
* termination/dummy unit per side, built from the cdac_unit_cell.sch
* bit-cell pattern (shown inline here, replicated per bit -- see
* design/cdac/cdac_unit_cell.sch for the single-instance, annotated
* version of the same cell).
*
* ARCHITECTURE (per spec/decision-records/DR-003-numeric-spec-derivation.md
* Item 3, provisional pending #27): top-plate sampling gives this
* differential SAR ADC a "free" MSB decision resolved directly from the
* sampled charge with no array switching at all -- this array is the
* remaining (N-1)=9-bit sub-array only, per side. Each bit i (i=0..8,
* weight w=2^i) is one cdac_unit_cell-pattern instance whose capacitor
* is sized w times the unit cap via the MF (multiplicity) parameter on
* sky130_fd_pr__cap_mim_m3_1 -- MF=w is the netlist-level equivalent of
* w parallel unit-cell instances, NOT a claim about physical placement;
* see design/cdac/README.md for why, and for the future layout-stage
* common-centroid plan this schematic does not (cannot, pre-layout)
* realize.
*
* Weights 2^8..2^0 (256..1) sum to 511; a tenth, non-switching
* TERMINATION unit (weight 1, bottom plate hard-wired to VREFN, no
* switch device at all since it never toggles) brings each side's total
* to 512 unit caps -- DR-003 Item 3's C_side ~= 512*C_u ~= 4.43 pF,
* matching the kT/C-floor-vs-matching-floor derivation there. The
* termination unit is also this array's matching/etch-density dummy
* (see design/cdac/README.md and DR-004 for the strategy note the
* issue's acceptance criteria require).
*
* SIDES: P (in-phase) and N (complementary) sub-arrays are structurally
* identical; a differential SAR driver feeds complementary codes to
* SELp<i>/SELn<i> (out of scope here -- the SAR logic sub-block, per
* issue #53's own scoping). TOP_P/TOP_N are this array's two DAC output
* nodes (the future comparator's inputs).
*
* Every switch device is ratified-flavour 1.8 V core (nfet_01v8/
* pfet_01v8, DR-001); no _g5v0d10v5 or other flavour appears.
}
G {}
K {}
V {}
S {}
E {}
C {sky130_fd_pr/cap_mim_m3_1.sym} 0 0 0 0 {name=Cp0 model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=1 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 200 -50 0 0 {name=Mp0n W=1 L=0.15 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 400 50 0 0 {name=Mp0p W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {lab_pin.sym} 0 30 0 0 {name=l_p0_t lab=TOP_P}
C {lab_pin.sym} 0 -30 0 0 {name=l_p0_b lab=BOT_p0}
C {lab_pin.sym} 220 -80 0 0 {name=l_p0_nd lab=BOT_p0}
C {lab_pin.sym} 180 -50 0 0 {name=l_p0_ng lab=SELp0}
C {lab_pin.sym} 220 -20 0 0 {name=l_p0_ns lab=VREFN}
C {lab_pin.sym} 220 -50 0 0 {name=l_p0_nb lab=VSS}
C {lab_pin.sym} 420 80 0 0 {name=l_p0_pd lab=BOT_p0}
C {lab_pin.sym} 380 50 0 0 {name=l_p0_pg lab=SELp0}
C {lab_pin.sym} 420 20 0 0 {name=l_p0_ps lab=VREFP}
C {lab_pin.sym} 420 50 0 0 {name=l_p0_pb lab=VDD}
T {weight=1} 520 0 0 0 0.15 0.15 {}
C {ipin.sym} -300 0 0 0 {name=p_selp0 lab=SELp0}
C {sky130_fd_pr/cap_mim_m3_1.sym} 0 150 0 0 {name=Cp1 model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=2 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 200 100 0 0 {name=Mp1n W=1 L=0.15 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 400 200 0 0 {name=Mp1p W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {lab_pin.sym} 0 180 0 0 {name=l_p1_t lab=TOP_P}
C {lab_pin.sym} 0 120 0 0 {name=l_p1_b lab=BOT_p1}
C {lab_pin.sym} 220 70 0 0 {name=l_p1_nd lab=BOT_p1}
C {lab_pin.sym} 180 100 0 0 {name=l_p1_ng lab=SELp1}
C {lab_pin.sym} 220 130 0 0 {name=l_p1_ns lab=VREFN}
C {lab_pin.sym} 220 100 0 0 {name=l_p1_nb lab=VSS}
C {lab_pin.sym} 420 230 0 0 {name=l_p1_pd lab=BOT_p1}
C {lab_pin.sym} 380 200 0 0 {name=l_p1_pg lab=SELp1}
C {lab_pin.sym} 420 170 0 0 {name=l_p1_ps lab=VREFP}
C {lab_pin.sym} 420 200 0 0 {name=l_p1_pb lab=VDD}
T {weight=2} 520 150 0 0 0.15 0.15 {}
C {ipin.sym} -300 150 0 0 {name=p_selp1 lab=SELp1}
C {sky130_fd_pr/cap_mim_m3_1.sym} 0 300 0 0 {name=Cp2 model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=4 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 200 250 0 0 {name=Mp2n W=1 L=0.15 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 400 350 0 0 {name=Mp2p W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {lab_pin.sym} 0 330 0 0 {name=l_p2_t lab=TOP_P}
C {lab_pin.sym} 0 270 0 0 {name=l_p2_b lab=BOT_p2}
C {lab_pin.sym} 220 220 0 0 {name=l_p2_nd lab=BOT_p2}
C {lab_pin.sym} 180 250 0 0 {name=l_p2_ng lab=SELp2}
C {lab_pin.sym} 220 280 0 0 {name=l_p2_ns lab=VREFN}
C {lab_pin.sym} 220 250 0 0 {name=l_p2_nb lab=VSS}
C {lab_pin.sym} 420 380 0 0 {name=l_p2_pd lab=BOT_p2}
C {lab_pin.sym} 380 350 0 0 {name=l_p2_pg lab=SELp2}
C {lab_pin.sym} 420 320 0 0 {name=l_p2_ps lab=VREFP}
C {lab_pin.sym} 420 350 0 0 {name=l_p2_pb lab=VDD}
T {weight=4} 520 300 0 0 0.15 0.15 {}
C {ipin.sym} -300 300 0 0 {name=p_selp2 lab=SELp2}
C {sky130_fd_pr/cap_mim_m3_1.sym} 0 450 0 0 {name=Cp3 model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=8 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 200 400 0 0 {name=Mp3n W=1 L=0.15 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 400 500 0 0 {name=Mp3p W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {lab_pin.sym} 0 480 0 0 {name=l_p3_t lab=TOP_P}
C {lab_pin.sym} 0 420 0 0 {name=l_p3_b lab=BOT_p3}
C {lab_pin.sym} 220 370 0 0 {name=l_p3_nd lab=BOT_p3}
C {lab_pin.sym} 180 400 0 0 {name=l_p3_ng lab=SELp3}
C {lab_pin.sym} 220 430 0 0 {name=l_p3_ns lab=VREFN}
C {lab_pin.sym} 220 400 0 0 {name=l_p3_nb lab=VSS}
C {lab_pin.sym} 420 530 0 0 {name=l_p3_pd lab=BOT_p3}
C {lab_pin.sym} 380 500 0 0 {name=l_p3_pg lab=SELp3}
C {lab_pin.sym} 420 470 0 0 {name=l_p3_ps lab=VREFP}
C {lab_pin.sym} 420 500 0 0 {name=l_p3_pb lab=VDD}
T {weight=8} 520 450 0 0 0.15 0.15 {}
C {ipin.sym} -300 450 0 0 {name=p_selp3 lab=SELp3}
C {sky130_fd_pr/cap_mim_m3_1.sym} 0 600 0 0 {name=Cp4 model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=16 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 200 550 0 0 {name=Mp4n W=1 L=0.15 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 400 650 0 0 {name=Mp4p W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {lab_pin.sym} 0 630 0 0 {name=l_p4_t lab=TOP_P}
C {lab_pin.sym} 0 570 0 0 {name=l_p4_b lab=BOT_p4}
C {lab_pin.sym} 220 520 0 0 {name=l_p4_nd lab=BOT_p4}
C {lab_pin.sym} 180 550 0 0 {name=l_p4_ng lab=SELp4}
C {lab_pin.sym} 220 580 0 0 {name=l_p4_ns lab=VREFN}
C {lab_pin.sym} 220 550 0 0 {name=l_p4_nb lab=VSS}
C {lab_pin.sym} 420 680 0 0 {name=l_p4_pd lab=BOT_p4}
C {lab_pin.sym} 380 650 0 0 {name=l_p4_pg lab=SELp4}
C {lab_pin.sym} 420 620 0 0 {name=l_p4_ps lab=VREFP}
C {lab_pin.sym} 420 650 0 0 {name=l_p4_pb lab=VDD}
T {weight=16} 520 600 0 0 0.15 0.15 {}
C {ipin.sym} -300 600 0 0 {name=p_selp4 lab=SELp4}
C {sky130_fd_pr/cap_mim_m3_1.sym} 0 750 0 0 {name=Cp5 model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=32 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 200 700 0 0 {name=Mp5n W=1 L=0.15 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 400 800 0 0 {name=Mp5p W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {lab_pin.sym} 0 780 0 0 {name=l_p5_t lab=TOP_P}
C {lab_pin.sym} 0 720 0 0 {name=l_p5_b lab=BOT_p5}
C {lab_pin.sym} 220 670 0 0 {name=l_p5_nd lab=BOT_p5}
C {lab_pin.sym} 180 700 0 0 {name=l_p5_ng lab=SELp5}
C {lab_pin.sym} 220 730 0 0 {name=l_p5_ns lab=VREFN}
C {lab_pin.sym} 220 700 0 0 {name=l_p5_nb lab=VSS}
C {lab_pin.sym} 420 830 0 0 {name=l_p5_pd lab=BOT_p5}
C {lab_pin.sym} 380 800 0 0 {name=l_p5_pg lab=SELp5}
C {lab_pin.sym} 420 770 0 0 {name=l_p5_ps lab=VREFP}
C {lab_pin.sym} 420 800 0 0 {name=l_p5_pb lab=VDD}
T {weight=32} 520 750 0 0 0.15 0.15 {}
C {ipin.sym} -300 750 0 0 {name=p_selp5 lab=SELp5}
C {sky130_fd_pr/cap_mim_m3_1.sym} 0 900 0 0 {name=Cp6 model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=64 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 200 850 0 0 {name=Mp6n W=1 L=0.15 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 400 950 0 0 {name=Mp6p W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {lab_pin.sym} 0 930 0 0 {name=l_p6_t lab=TOP_P}
C {lab_pin.sym} 0 870 0 0 {name=l_p6_b lab=BOT_p6}
C {lab_pin.sym} 220 820 0 0 {name=l_p6_nd lab=BOT_p6}
C {lab_pin.sym} 180 850 0 0 {name=l_p6_ng lab=SELp6}
C {lab_pin.sym} 220 880 0 0 {name=l_p6_ns lab=VREFN}
C {lab_pin.sym} 220 850 0 0 {name=l_p6_nb lab=VSS}
C {lab_pin.sym} 420 980 0 0 {name=l_p6_pd lab=BOT_p6}
C {lab_pin.sym} 380 950 0 0 {name=l_p6_pg lab=SELp6}
C {lab_pin.sym} 420 920 0 0 {name=l_p6_ps lab=VREFP}
C {lab_pin.sym} 420 950 0 0 {name=l_p6_pb lab=VDD}
T {weight=64} 520 900 0 0 0.15 0.15 {}
C {ipin.sym} -300 900 0 0 {name=p_selp6 lab=SELp6}
C {sky130_fd_pr/cap_mim_m3_1.sym} 0 1050 0 0 {name=Cp7 model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=128 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 200 1000 0 0 {name=Mp7n W=1 L=0.15 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 400 1100 0 0 {name=Mp7p W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {lab_pin.sym} 0 1080 0 0 {name=l_p7_t lab=TOP_P}
C {lab_pin.sym} 0 1020 0 0 {name=l_p7_b lab=BOT_p7}
C {lab_pin.sym} 220 970 0 0 {name=l_p7_nd lab=BOT_p7}
C {lab_pin.sym} 180 1000 0 0 {name=l_p7_ng lab=SELp7}
C {lab_pin.sym} 220 1030 0 0 {name=l_p7_ns lab=VREFN}
C {lab_pin.sym} 220 1000 0 0 {name=l_p7_nb lab=VSS}
C {lab_pin.sym} 420 1130 0 0 {name=l_p7_pd lab=BOT_p7}
C {lab_pin.sym} 380 1100 0 0 {name=l_p7_pg lab=SELp7}
C {lab_pin.sym} 420 1070 0 0 {name=l_p7_ps lab=VREFP}
C {lab_pin.sym} 420 1100 0 0 {name=l_p7_pb lab=VDD}
T {weight=128} 520 1050 0 0 0.15 0.15 {}
C {ipin.sym} -300 1050 0 0 {name=p_selp7 lab=SELp7}
C {sky130_fd_pr/cap_mim_m3_1.sym} 0 1200 0 0 {name=Cp8 model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=256 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 200 1150 0 0 {name=Mp8n W=1 L=0.15 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 400 1250 0 0 {name=Mp8p W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {lab_pin.sym} 0 1230 0 0 {name=l_p8_t lab=TOP_P}
C {lab_pin.sym} 0 1170 0 0 {name=l_p8_b lab=BOT_p8}
C {lab_pin.sym} 220 1120 0 0 {name=l_p8_nd lab=BOT_p8}
C {lab_pin.sym} 180 1150 0 0 {name=l_p8_ng lab=SELp8}
C {lab_pin.sym} 220 1180 0 0 {name=l_p8_ns lab=VREFN}
C {lab_pin.sym} 220 1150 0 0 {name=l_p8_nb lab=VSS}
C {lab_pin.sym} 420 1280 0 0 {name=l_p8_pd lab=BOT_p8}
C {lab_pin.sym} 380 1250 0 0 {name=l_p8_pg lab=SELp8}
C {lab_pin.sym} 420 1220 0 0 {name=l_p8_ps lab=VREFP}
C {lab_pin.sym} 420 1250 0 0 {name=l_p8_pb lab=VDD}
T {weight=256} 520 1200 0 0 0.15 0.15 {}
C {ipin.sym} -300 1200 0 0 {name=p_selp8 lab=SELp8}
C {sky130_fd_pr/cap_mim_m3_1.sym} 0 1350 0 0 {name=Cp_term model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=1 spiceprefix=X}
C {lab_pin.sym} 0 1380 0 0 {name=l_p_term_t lab=TOP_P}
C {lab_pin.sym} 0 1320 0 0 {name=l_p_term_b lab=VREFN}
T {termination, weight=1, fixed to VREFN} 520 1350 0 0 0.15 0.15 {}
C {opin.sym} -300 600 0 0 {name=p_top_p lab=TOP_P}
C {sky130_fd_pr/cap_mim_m3_1.sym} 1600 0 0 0 {name=Cn0 model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=1 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 1800 -50 0 0 {name=Mn0n W=1 L=0.15 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 2000 50 0 0 {name=Mn0p W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {lab_pin.sym} 1600 30 0 0 {name=l_n0_t lab=TOP_N}
C {lab_pin.sym} 1600 -30 0 0 {name=l_n0_b lab=BOT_n0}
C {lab_pin.sym} 1820 -80 0 0 {name=l_n0_nd lab=BOT_n0}
C {lab_pin.sym} 1780 -50 0 0 {name=l_n0_ng lab=SELn0}
C {lab_pin.sym} 1820 -20 0 0 {name=l_n0_ns lab=VREFN}
C {lab_pin.sym} 1820 -50 0 0 {name=l_n0_nb lab=VSS}
C {lab_pin.sym} 2020 80 0 0 {name=l_n0_pd lab=BOT_n0}
C {lab_pin.sym} 1980 50 0 0 {name=l_n0_pg lab=SELn0}
C {lab_pin.sym} 2020 20 0 0 {name=l_n0_ps lab=VREFP}
C {lab_pin.sym} 2020 50 0 0 {name=l_n0_pb lab=VDD}
T {weight=1} 2120 0 0 0 0.15 0.15 {}
C {ipin.sym} 1300 0 0 0 {name=p_seln0 lab=SELn0}
C {sky130_fd_pr/cap_mim_m3_1.sym} 1600 150 0 0 {name=Cn1 model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=2 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 1800 100 0 0 {name=Mn1n W=1 L=0.15 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 2000 200 0 0 {name=Mn1p W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {lab_pin.sym} 1600 180 0 0 {name=l_n1_t lab=TOP_N}
C {lab_pin.sym} 1600 120 0 0 {name=l_n1_b lab=BOT_n1}
C {lab_pin.sym} 1820 70 0 0 {name=l_n1_nd lab=BOT_n1}
C {lab_pin.sym} 1780 100 0 0 {name=l_n1_ng lab=SELn1}
C {lab_pin.sym} 1820 130 0 0 {name=l_n1_ns lab=VREFN}
C {lab_pin.sym} 1820 100 0 0 {name=l_n1_nb lab=VSS}
C {lab_pin.sym} 2020 230 0 0 {name=l_n1_pd lab=BOT_n1}
C {lab_pin.sym} 1980 200 0 0 {name=l_n1_pg lab=SELn1}
C {lab_pin.sym} 2020 170 0 0 {name=l_n1_ps lab=VREFP}
C {lab_pin.sym} 2020 200 0 0 {name=l_n1_pb lab=VDD}
T {weight=2} 2120 150 0 0 0.15 0.15 {}
C {ipin.sym} 1300 150 0 0 {name=p_seln1 lab=SELn1}
C {sky130_fd_pr/cap_mim_m3_1.sym} 1600 300 0 0 {name=Cn2 model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=4 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 1800 250 0 0 {name=Mn2n W=1 L=0.15 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 2000 350 0 0 {name=Mn2p W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {lab_pin.sym} 1600 330 0 0 {name=l_n2_t lab=TOP_N}
C {lab_pin.sym} 1600 270 0 0 {name=l_n2_b lab=BOT_n2}
C {lab_pin.sym} 1820 220 0 0 {name=l_n2_nd lab=BOT_n2}
C {lab_pin.sym} 1780 250 0 0 {name=l_n2_ng lab=SELn2}
C {lab_pin.sym} 1820 280 0 0 {name=l_n2_ns lab=VREFN}
C {lab_pin.sym} 1820 250 0 0 {name=l_n2_nb lab=VSS}
C {lab_pin.sym} 2020 380 0 0 {name=l_n2_pd lab=BOT_n2}
C {lab_pin.sym} 1980 350 0 0 {name=l_n2_pg lab=SELn2}
C {lab_pin.sym} 2020 320 0 0 {name=l_n2_ps lab=VREFP}
C {lab_pin.sym} 2020 350 0 0 {name=l_n2_pb lab=VDD}
T {weight=4} 2120 300 0 0 0.15 0.15 {}
C {ipin.sym} 1300 300 0 0 {name=p_seln2 lab=SELn2}
C {sky130_fd_pr/cap_mim_m3_1.sym} 1600 450 0 0 {name=Cn3 model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=8 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 1800 400 0 0 {name=Mn3n W=1 L=0.15 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 2000 500 0 0 {name=Mn3p W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {lab_pin.sym} 1600 480 0 0 {name=l_n3_t lab=TOP_N}
C {lab_pin.sym} 1600 420 0 0 {name=l_n3_b lab=BOT_n3}
C {lab_pin.sym} 1820 370 0 0 {name=l_n3_nd lab=BOT_n3}
C {lab_pin.sym} 1780 400 0 0 {name=l_n3_ng lab=SELn3}
C {lab_pin.sym} 1820 430 0 0 {name=l_n3_ns lab=VREFN}
C {lab_pin.sym} 1820 400 0 0 {name=l_n3_nb lab=VSS}
C {lab_pin.sym} 2020 530 0 0 {name=l_n3_pd lab=BOT_n3}
C {lab_pin.sym} 1980 500 0 0 {name=l_n3_pg lab=SELn3}
C {lab_pin.sym} 2020 470 0 0 {name=l_n3_ps lab=VREFP}
C {lab_pin.sym} 2020 500 0 0 {name=l_n3_pb lab=VDD}
T {weight=8} 2120 450 0 0 0.15 0.15 {}
C {ipin.sym} 1300 450 0 0 {name=p_seln3 lab=SELn3}
C {sky130_fd_pr/cap_mim_m3_1.sym} 1600 600 0 0 {name=Cn4 model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=16 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 1800 550 0 0 {name=Mn4n W=1 L=0.15 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 2000 650 0 0 {name=Mn4p W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {lab_pin.sym} 1600 630 0 0 {name=l_n4_t lab=TOP_N}
C {lab_pin.sym} 1600 570 0 0 {name=l_n4_b lab=BOT_n4}
C {lab_pin.sym} 1820 520 0 0 {name=l_n4_nd lab=BOT_n4}
C {lab_pin.sym} 1780 550 0 0 {name=l_n4_ng lab=SELn4}
C {lab_pin.sym} 1820 580 0 0 {name=l_n4_ns lab=VREFN}
C {lab_pin.sym} 1820 550 0 0 {name=l_n4_nb lab=VSS}
C {lab_pin.sym} 2020 680 0 0 {name=l_n4_pd lab=BOT_n4}
C {lab_pin.sym} 1980 650 0 0 {name=l_n4_pg lab=SELn4}
C {lab_pin.sym} 2020 620 0 0 {name=l_n4_ps lab=VREFP}
C {lab_pin.sym} 2020 650 0 0 {name=l_n4_pb lab=VDD}
T {weight=16} 2120 600 0 0 0.15 0.15 {}
C {ipin.sym} 1300 600 0 0 {name=p_seln4 lab=SELn4}
C {sky130_fd_pr/cap_mim_m3_1.sym} 1600 750 0 0 {name=Cn5 model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=32 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 1800 700 0 0 {name=Mn5n W=1 L=0.15 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 2000 800 0 0 {name=Mn5p W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {lab_pin.sym} 1600 780 0 0 {name=l_n5_t lab=TOP_N}
C {lab_pin.sym} 1600 720 0 0 {name=l_n5_b lab=BOT_n5}
C {lab_pin.sym} 1820 670 0 0 {name=l_n5_nd lab=BOT_n5}
C {lab_pin.sym} 1780 700 0 0 {name=l_n5_ng lab=SELn5}
C {lab_pin.sym} 1820 730 0 0 {name=l_n5_ns lab=VREFN}
C {lab_pin.sym} 1820 700 0 0 {name=l_n5_nb lab=VSS}
C {lab_pin.sym} 2020 830 0 0 {name=l_n5_pd lab=BOT_n5}
C {lab_pin.sym} 1980 800 0 0 {name=l_n5_pg lab=SELn5}
C {lab_pin.sym} 2020 770 0 0 {name=l_n5_ps lab=VREFP}
C {lab_pin.sym} 2020 800 0 0 {name=l_n5_pb lab=VDD}
T {weight=32} 2120 750 0 0 0.15 0.15 {}
C {ipin.sym} 1300 750 0 0 {name=p_seln5 lab=SELn5}
C {sky130_fd_pr/cap_mim_m3_1.sym} 1600 900 0 0 {name=Cn6 model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=64 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 1800 850 0 0 {name=Mn6n W=1 L=0.15 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 2000 950 0 0 {name=Mn6p W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {lab_pin.sym} 1600 930 0 0 {name=l_n6_t lab=TOP_N}
C {lab_pin.sym} 1600 870 0 0 {name=l_n6_b lab=BOT_n6}
C {lab_pin.sym} 1820 820 0 0 {name=l_n6_nd lab=BOT_n6}
C {lab_pin.sym} 1780 850 0 0 {name=l_n6_ng lab=SELn6}
C {lab_pin.sym} 1820 880 0 0 {name=l_n6_ns lab=VREFN}
C {lab_pin.sym} 1820 850 0 0 {name=l_n6_nb lab=VSS}
C {lab_pin.sym} 2020 980 0 0 {name=l_n6_pd lab=BOT_n6}
C {lab_pin.sym} 1980 950 0 0 {name=l_n6_pg lab=SELn6}
C {lab_pin.sym} 2020 920 0 0 {name=l_n6_ps lab=VREFP}
C {lab_pin.sym} 2020 950 0 0 {name=l_n6_pb lab=VDD}
T {weight=64} 2120 900 0 0 0.15 0.15 {}
C {ipin.sym} 1300 900 0 0 {name=p_seln6 lab=SELn6}
C {sky130_fd_pr/cap_mim_m3_1.sym} 1600 1050 0 0 {name=Cn7 model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=128 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 1800 1000 0 0 {name=Mn7n W=1 L=0.15 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 2000 1100 0 0 {name=Mn7p W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {lab_pin.sym} 1600 1080 0 0 {name=l_n7_t lab=TOP_N}
C {lab_pin.sym} 1600 1020 0 0 {name=l_n7_b lab=BOT_n7}
C {lab_pin.sym} 1820 970 0 0 {name=l_n7_nd lab=BOT_n7}
C {lab_pin.sym} 1780 1000 0 0 {name=l_n7_ng lab=SELn7}
C {lab_pin.sym} 1820 1030 0 0 {name=l_n7_ns lab=VREFN}
C {lab_pin.sym} 1820 1000 0 0 {name=l_n7_nb lab=VSS}
C {lab_pin.sym} 2020 1130 0 0 {name=l_n7_pd lab=BOT_n7}
C {lab_pin.sym} 1980 1100 0 0 {name=l_n7_pg lab=SELn7}
C {lab_pin.sym} 2020 1070 0 0 {name=l_n7_ps lab=VREFP}
C {lab_pin.sym} 2020 1100 0 0 {name=l_n7_pb lab=VDD}
T {weight=128} 2120 1050 0 0 0.15 0.15 {}
C {ipin.sym} 1300 1050 0 0 {name=p_seln7 lab=SELn7}
C {sky130_fd_pr/cap_mim_m3_1.sym} 1600 1200 0 0 {name=Cn8 model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=256 spiceprefix=X}
C {sky130_fd_pr/nfet_01v8.sym} 1800 1150 0 0 {name=Mn8n W=1 L=0.15 nf=1 mult=1 model=nfet_01v8 spiceprefix=X}
C {sky130_fd_pr/pfet_01v8.sym} 2000 1250 0 0 {name=Mn8p W=2 L=0.15 nf=1 mult=1 model=pfet_01v8 spiceprefix=X}
C {lab_pin.sym} 1600 1230 0 0 {name=l_n8_t lab=TOP_N}
C {lab_pin.sym} 1600 1170 0 0 {name=l_n8_b lab=BOT_n8}
C {lab_pin.sym} 1820 1120 0 0 {name=l_n8_nd lab=BOT_n8}
C {lab_pin.sym} 1780 1150 0 0 {name=l_n8_ng lab=SELn8}
C {lab_pin.sym} 1820 1180 0 0 {name=l_n8_ns lab=VREFN}
C {lab_pin.sym} 1820 1150 0 0 {name=l_n8_nb lab=VSS}
C {lab_pin.sym} 2020 1280 0 0 {name=l_n8_pd lab=BOT_n8}
C {lab_pin.sym} 1980 1250 0 0 {name=l_n8_pg lab=SELn8}
C {lab_pin.sym} 2020 1220 0 0 {name=l_n8_ps lab=VREFP}
C {lab_pin.sym} 2020 1250 0 0 {name=l_n8_pb lab=VDD}
T {weight=256} 2120 1200 0 0 0.15 0.15 {}
C {ipin.sym} 1300 1200 0 0 {name=p_seln8 lab=SELn8}
C {sky130_fd_pr/cap_mim_m3_1.sym} 1600 1350 0 0 {name=Cn_term model=cap_mim_m3_1 W=1.8988 L=1.8988 MF=1 spiceprefix=X}
C {lab_pin.sym} 1600 1380 0 0 {name=l_n_term_t lab=TOP_N}
C {lab_pin.sym} 1600 1320 0 0 {name=l_n_term_b lab=VREFN}
T {termination, weight=1, fixed to VREFN} 2120 1350 0 0 0.15 0.15 {}
C {opin.sym} 1300 600 0 0 {name=p_top_n lab=TOP_N}
C {ipin.sym} -300 -300 0 0 {name=p_vrefp lab=VREFP}
C {ipin.sym} -300 -250 0 0 {name=p_vrefn lab=VREFN}
C {ipin.sym} -300 -200 0 0 {name=p_vdd lab=VDD}
C {ipin.sym} -300 -150 0 0 {name=p_vss lab=VSS}
T {cdac_array: 9-bit-per-side binary sub-array + termination (DR-003/DR-004, provisional)} 0 -450 0 0 0.2 0.2 {}

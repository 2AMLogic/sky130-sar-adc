#!/usr/bin/env python3
"""DR-003 support script — reproduces every numeric derivation in
spec/decision-records/DR-003-numeric-spec-derivation.md from stated inputs.

Run: python3 spec/dr-003-support/calc.py

Every device-level input below (camimc, cpmimc, the MIM mismatch coefficient,
nfet_01v8/pfet_01v8 vth0) is read directly from the installed sky130A PDK
(open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b, per sim/pdk.json) at the
paths cited inline. This script does not call ngspice; the two op-point
threshold numbers it uses (VTHN_TT_27C, VTHP_TT_27C) are transcribed from
spec/dr-003-support/vth_probe.spice's own printed output (rerun that deck to
reproduce them independently).
"""

import math

# ---------------------------------------------------------------------------
# Ratified / drafted inputs
# ---------------------------------------------------------------------------
VDD = 1.8  # V -- ratified core rail (DR-001, issue #1, 2026-08-13)
N = 10  # bit -- draft resolution row, target-spec.md

# ---------------------------------------------------------------------------
# Item 1/2: V_REF and LSB
# ---------------------------------------------------------------------------
V_REF = VDD  # this record's recommendation: V_REF = VDD, at the rail, not above it
LSB_DIFF = 2 * V_REF / (2**N)  # differential top-plate array, target-spec.md Architecture row

print("=== Item 1/2: V_REF, LSB ===")
print(f"V_REF = {V_REF} V")
print(f"LSB (differential) = 2*V_REF/2^{N} = {LSB_DIFF*1e3:.4f} mV")

# ---------------------------------------------------------------------------
# Comparator headroom check (Item 1) -- nfet_01v8/pfet_01v8 op-point Vth,
# transcribed from spec/dr-003-support/vth_probe.spice, tt corner, 27 C,
# representative W=4um/L=0.5um, Vds=VDD (saturation):
# ---------------------------------------------------------------------------
VTHN_TT_27C = 0.626922  # V, @m.xn.msky130_fd_pr__nfet_01v8[vth]
VTHP_TT_27C = 0.979856  # V, @m.xp.msky130_fd_pr__pfet_01v8[vth] (magnitude)

V_CM = V_REF / 2
VOV_ASSUMED = 0.125  # V -- planning assumption, input pair overdrive
VDSAT_TAIL_ASSUMED = 0.125  # V -- planning assumption, tail device Vdsat

V_CM_MIN_NMOS_TAIL = VTHN_TT_27C + VOV_ASSUMED + VDSAT_TAIL_ASSUMED
MARGIN = V_CM - V_CM_MIN_NMOS_TAIL

print()
print("=== Item 1: comparator headroom check (NMOS input pair, bottom tail) ===")
print(f"V_cm = V_REF/2 = {V_CM*1e3:.1f} mV")
print(f"Vth,n (tt, 27C, W=4/L=0.5, Vds=VDD) = {VTHN_TT_27C*1e3:.1f} mV")
print(f"Vth,p (tt, 27C, W=4/L=0.5, Vds=VDD, magnitude) = {VTHP_TT_27C*1e3:.1f} mV")
print(f"V_cm,min (planning Vov={VOV_ASSUMED*1e3:.0f} mV, "
      f"Vdsat,tail={VDSAT_TAIL_ASSUMED*1e3:.0f} mV) = {V_CM_MIN_NMOS_TAIL*1e3:.1f} mV")
print(f"Margin at tt/27C = {MARGIN*1e3:.1f} mV")

# ---------------------------------------------------------------------------
# Item 4 (worked before Item 3 because Item 3's kT/C floor consumes its share):
# total non-quantization noise budget, from standard ADC SNR theory
# (SNR = 6.02*ENOB + 1.76 dB; not gf180-specific -- reproducible from the
# quantization-noise / SNDR relationship alone).
# ---------------------------------------------------------------------------
def sigma_quant(lsb):
    return lsb / math.sqrt(12)


def total_budget(lsb, enob_target, n_bits=N):
    """sigma_total(non-quantization), 3-term equal-power split assumed downstream."""
    sq = sigma_quant(lsb)
    # power ratio between ideal N-bit SNR and the target ENOB's required SNDR
    db_backoff = 6.02 * (n_bits - enob_target)
    power_ratio = 10 ** (db_backoff / 10)  # = N_total/N_quant at the target
    n_total_over_n_quant = power_ratio
    n_nonquant_over_n_quant = n_total_over_n_quant - 1
    return sq * math.sqrt(n_nonquant_over_n_quant)


print()
print("=== Item 3/4: non-quantization noise budget ===")
sq = sigma_quant(LSB_DIFF)
print(f"sigma_quant = LSB/sqrt(12) = {sq*1e3:.4f} mV rms")

for enob in (9.0, 9.5):
    sigma_total = total_budget(LSB_DIFF, enob)
    share = sigma_total / math.sqrt(3)
    print(f"ENOB > {enob}: sigma_total(non-quant) = {sigma_total*1e3:.4f} mV rms "
          f"({sigma_total/LSB_DIFF*100:.2f}% LSB), "
          f"per-share (kT/C = comparator = ref+distortion) = {share*1e3:.4f} mV rms "
          f"({share/LSB_DIFF*100:.2f}% LSB)")

# ---------------------------------------------------------------------------
# Item 3: kT/C floor
# ---------------------------------------------------------------------------
K_B = 1.380649e-23  # J/K, exact SI (2019 redefinition)
T_HOT = 125 + 273.15  # K -- hot corner binds kT/C (kT increases with T)
ARRAY_SIDE = 2 ** (N - 1)  # top-plate sampling: bit 1 free, 2^(N-1)-position sub-array/side

print()
print("=== Item 3: kT/C floor (hot corner, 125 C = %.2f K) ===" % T_HOT)
kT_hot = K_B * T_HOT
print(f"kT(125C) = {kT_hot:.4e} J")

for enob in (9.0, 9.5):
    sigma_total = total_budget(LSB_DIFF, enob)
    share = sigma_total / math.sqrt(3)  # kT/C's 1/3 (power) share
    c_side_min = 2 * kT_hot / (share**2)  # v_n,rms = sqrt(2kT/C_side)
    c_u_min = c_side_min / ARRAY_SIDE
    print(f"ENOB > {enob}: kT/C share = {share*1e3:.4f} mV rms -> "
          f"C_side,min = {c_side_min*1e15:.4f} fF, C_u,min(kT/C) = {c_u_min*1e15:.5f} fF "
          f"(array = {ARRAY_SIDE}/side)")

# ---------------------------------------------------------------------------
# Item 3: matching floor -- sky130's own MIM mismatch model
# (sky130_fd_pr__cap_mim_m3_1 / _m3_2, montecarlo.spice, both cited inline)
# ---------------------------------------------------------------------------
# camimc (area term), cpmimc (perimeter term), at mim=0 (mean process point):
# libs.tech/ngspice/parameters/montecarlo.spice:
#   camimc = 2.81250e-19*mim^2 + 5.66250e-17*mim + 2.00000e-15  -> 2.000e-15 F/um^2 at mim=0
#   cpmimc = 4.00000e-17*mim + 1.90000e-16                       -> 1.900e-16 F/um  at mim=0
CAMIMC = 2.00000e-15  # F/um^2
CPMIMC = 1.90000e-16  # F/um

# libs.ref/sky130_fd_pr/spice/sky130_fd_pr__cap_mim_m3_{1,2}.model.spice:
#   czero = carea + cperim + MC_MM_SWITCH*AGAUSS(0,1,1)*0.01*2.8*(carea+cperim)/sqrt(wc*lc*mf)
# i.e. sigma(C)/C = 0.01*2.8/sqrt(W*L[um^2]) => Pelgrom-style A_C = 2.8 %*um
A_C = 2.8  # %*um, sigma(dC/C)[%] = A_C / sqrt(area[um^2])

# DNL/INL, standard top-plate-sampling SAR CDAC combinatorics (bit 1 free,
# 2^(N-1)-element binary sub-array resolves bits 2..N; independent per-unit
# variance sum at the sub-array's own MSB carry -- the standard
# charge-redistribution-SAR result, McCreary & Wooley 1975, re-derived here,
# not ported from any specific implementation):
M = ARRAY_SIDE  # 512
dnl_coeff = math.sqrt(M - 1)  # LSB per unit sigma_u (fractional)
inl_coeff = math.sqrt(M) / 2
gain_coeff = math.sqrt(2 * M)  # both sides' full array, 2*M unit caps total

print()
print("=== Item 3: matching floor (sky130 MIM local-mismatch model) ===")
print(f"camimc (area density, mim=0) = {CAMIMC*1e15:.4f} fF/um^2")
print(f"cpmimc (perimeter density, mim=0) = {CPMIMC*1e15:.4f} fF/um")
print(f"A_C (Pelgrom coefficient, from the subckt's own mismatch term) = {A_C} %*um")
print(f"DNL coeff sqrt(M-1) = {dnl_coeff:.4f}, INL coeff sqrt(M)/2 = {inl_coeff:.4f}, "
      f"gain-error coeff sqrt(2M) = {gain_coeff:.4f}  (M={M})")

DNL_TARGET_LSB = 1.0  # target-spec.md draft row, |DNL| <= 1 LSB -- carried as an input, not re-derived here
SIGMA_LEVEL = 3  # 3-sigma yield convention, stated policy (see record text)

sigma_dnl_1sigma = DNL_TARGET_LSB / SIGMA_LEVEL
sigma_u_pct = (sigma_dnl_1sigma / dnl_coeff) * 100  # required sigma(dC/C), percent

area_unit_um2 = (A_C / sigma_u_pct) ** 2
s_um = math.sqrt(area_unit_um2)
c_u_area = CAMIMC * area_unit_um2
c_u_perim = CPMIMC * (4 * s_um)
c_u_matching = c_u_area + c_u_perim

print(f"DNL <= {DNL_TARGET_LSB} LSB @ {SIGMA_LEVEL}sigma -> "
      f"required sigma_u = {sigma_u_pct:.4f}%")
print(f"-> unit area = {area_unit_um2:.4f} um^2, square side s = {s_um:.4f} um")
print(f"-> C_u (matching-limited, area+perimeter) = {c_u_matching*1e15:.4f} fF "
      f"(area term {c_u_area*1e15:.4f} fF + perimeter term {c_u_perim*1e15:.4f} fF)")

# Gain-error check at this sigma_u (same array, both sides):
gain_error_3sigma_lsb = SIGMA_LEVEL * gain_coeff * (sigma_u_pct / 100)
print(f"Gain error at this sigma_u, {SIGMA_LEVEL}sigma = {gain_error_3sigma_lsb:.4f} LSB "
      "(no ratified gain-error row exists in target-spec.md to compare against; reported for the record)")

print()
print("=== Item 3: dominant constraint ===")
c_u_kTC_worst = max(
    total_budget(LSB_DIFF, e) / math.sqrt(3) for e in (9.0, 9.5)
)
c_side_kTC_worst = 2 * kT_hot / (c_u_kTC_worst ** 2)
c_u_kTC_worst_val = c_side_kTC_worst / ARRAY_SIDE
ratio = c_u_matching / c_u_kTC_worst_val
print(f"C_u matching floor / C_u kT/C floor (worst-case, ENOB>9.0) = {ratio:.1f}x")

c_side_total = ARRAY_SIDE * c_u_matching
c_total = 2 * c_side_total
print()
print("=== Item 3: resulting array size (informational) ===")
print(f"C_u (chosen, matching-limited) = {c_u_matching*1e15:.4f} fF, "
      f"array = {ARRAY_SIDE}/side")
print(f"C_side = {c_side_total*1e12:.4f} pF, C_total (both sides) = {c_total*1e12:.4f} pF")

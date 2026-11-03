# sim/top-plate-cpar — CDAC top-plate parasitic capacitance (issue #754)

Measures `C_par`, the capacitance on `TOP_P`/`TOP_N` beyond the array's own
`512 * C_u`, of the as-committed `design/sar_adc_top.spice`, per PVT corner and
per MiM r+c corner. It replaces DR-022's *estimated* contributor table
(`spec/decision-records/DR-022-cdac-gain-error-specified-not-sized.md`, Open
item 1). It asserts no spec value and changes no spec row (the table stays DRAFT
until #1); it does not choose a closure path (that is #755).

Latest record: `records/20261101-183325-60421e38.md`.

## Run

```sh
source sim/env.sh
python3 sim/top-plate-cpar/run_top_plate_cpar.py --check-env
python3 sim/top-plate-cpar/run_top_plate_cpar.py --probe     # ONE corner, local, as-committed only
python3 sim/top-plate-cpar/run_top_plate_cpar.py --record    # 6 decks x 13 corners, via klt sim
```

`--record` submits six `klt sim` requests (one per deck variant, 13 corners each).
It sets no backend itself: `klt sim` follows `KLT_SIM_BACKEND` / the request, so on
the dispatch workers the grid goes to the batch fleet. A failed submit raises; it
never falls back to a local loop. Pass `--backend` to override.

Why its own runner and no `testbench/tb.json`: same reason as
`sim/cdac-array-transfer/README.md` ("Why this experiment does NOT have a
`testbench/tb.json`") — the node is purely capacitive, so the generic `.op`-only
manifest cannot measure it.

## Method

- **Extraction.** AC analysis, 1 V small-signal source directly on the node:
  `C = -Im(I) / (2 pi f)`. `TOP_P` and `TOP_N` are measured in separate steps with
  the other side held at the same DC bias and AC ground, so the figure is the
  single-ended capacitance (not a differential-mode one).
- **C(V).** `klt sim` `analysis_steps[]`: one AC step per side per bias,
  `alter`-ing the bias sources. Biases: 565, 641.5, 718, 794.5, 871 mV — the ends of
  DR-022's traced common-mode range (565–871 mV at 1.8 V) and three points between.
  The same absolute voltages are used at every supply; the range was only traced at
  1.8 V.
- **`C_par`.** `C_node - 512 * C_u`. `C_u` comes from an isolated reference branch
  in the same deck (`XCuref`, the array's unit cap with `MF=512`), at the same
  corner and bias, so `C_par` is also given in that corner's own `C_u`.
- **Why AC.** `C_par` is under 1 % of `C_node`; a transient displacement-current
  read is limited by solver `reltol` (1e-3), the same size as the number sought.
- **State.** Testbench-only edits: `xfe`'s `SAMPLE_INT` is re-pointed at a source tied
  low (sampling switch off); `RST_B` low (sequencer in reset, all `SEL` low, so every
  bottom plate sits at `VREFP`), `CLK` high (comparator tail off). The traced
  instants of `sim/full-conversion-transient/records/20260912-011519-9aaf1ca.md` have
  code-dependent bottom-plate levels; this experiment uses the all-`VREFP` state only
  and does not test sensitivity to the bottom-plate code.
- **Floating `BPREF_x`.** After sampling, `BPREF_x` floats. Each is tied through
  10 GOhm to a DC source at the same bias as the top plate (that is the state if the
  input was sampled at `VCM` and the top plate then moved to the bias point). At
  10 kHz the 10 GOhm is far above the impedance of any capacitance on that node.
  A different sampled input would shift the `BPREF_x` DC level; not swept here.
- **Frequency choice (10 kHz).** One local probe (tt, 27 C, 1.8 V, 800 mV) read
  `C_node` 4.3364 pF at 100 kHz and 4.3347 pF at 1 MHz (-1.7 fF, from the array's RC
  roll-off through the MSB bottom-plate switch). Assuming that rolloff goes as f^2,
  10 kHz is ~0.02 fF off the ideal quasi-static value. That extrapolation was not
  re-measured at 10 kHz vs lower frequencies. With 1 GOhm bias resistors the 1 kHz read
  was 4.3419 pF (+5 fF), which is why the bias resistor is 10 GOhm and f is not lower.
- **Leave-one-out.** Testbench-only deletion of exactly the named instances
  (asserted: each name must match exactly one line): `Choff_x` = `XChoff_p/n`;
  `Csamp_x`/`BPREF_x` branch = `XCsamp_p/n`; `Msw_x` = `XMsw_p/n`; comparator input
  pair = `XM_INP/XM_INN`; plus an `all-removed` variant. Contributor =
  `C_node(as-committed) - C_node(variant)`. Deleting `XCsamp_x` also removes the
  `Cmswn/Cmswp` junctions it exposes (they only load `TOP_x` through it).
- **Corners.** The 9-point ratified one-at-a-time grid (`tt/ss/ff/sf/fs` at 27 C /
  1.8 V; -40 and 125 C and 1.62 / 1.98 V at tt) plus the four MiM r+c corners at
  tt / 27 C / 1.8 V. The five `tt/ss/ff/sf/fs` libraries all load
  `res_typical__cap_typical`. The r+c corners are the combined library's `.lib`
  sections `ll` (res_low__cap_low), `hh` (res_high__cap_high), `hl`
  (res_high__cap_low), `lh` (res_low__cap_high); each is the tt device library plus
  that r+c file. They are requested as `klt sim` process tokens.

## Observations (record `20261101-183325-60421e38`)

All figures are means over the five bias points and both sides (P and N agree to
under 0.001 fF in every corner and at every bias).

- **Total.** At `tt_27c_1.80v` `C_par` = 33.3 fF = 3.96 `C_u` (3.92–4.01 over the
  traced range; falls ~0.7 fF with rising bias). DR-022 estimated 4.13 `C_u`
  (`tt_27c_1.80v`) and 4.18 (`tt_27c_1.62v`); measured here 3.96 and 4.00, i.e.
  -0.17 and -0.18 `C_u`. Different methods (AC at the schematic vs. gain read from a
  transient trace) and a different PDK stamp (below), so this is a comparison, not a
  controlled reproduction.
- **Ranking at `tt_27c_1.80v`** (fF / `C_u`): `Csamp_x`/`BPREF_x` branch 18.6 / 2.22;
  `Choff_x` 8.4 / 1.00; comparator input 4.8 / 0.57; `Msw_x` 1.5 / 0.18. The four
  sum to `C_par` within 0.001 fF (residual) and the `all-removed` variant leaves
  0.000 fF, so in this state these four loads account for all of `C_par`.
  The same ranking holds in all 13 corners.
- **DR-022 estimate vs. measurement.** `Choff_x` = 1.000 `C_u` as designed.
  `Csamp_x`/`BPREF_x` (2.22) sits inside DR-022's estimated 2.1–2.8. The comparator
  input (0.57) is inside its "inferred 0.13–0.83" and `Msw_x` (0.18) near its ~0.2.
- **Corners.** In fF, `C_par` spans 31.7 (ff, ll) to 35.2 (hh). In `C_u` of each corner:
  ss 4.13, fs 4.12, tt 3.96, ff 3.78, sf 3.79 `C_u`; -40 / 125 C: 3.93 / 4.10;
  1.62 / 1.98 V: 4.00 / 3.93. MiM corners: `C_u` = 8.405 fF typical, 6.803 fF at
  cap_low (`ll`, `hl`), 10.260 fF at cap_high (`hh`, `lh`). `C_par` (fF) barely
  moves (31.7 / 35.2) but, in that corner's `C_u`, is 4.66 at cap_low and 3.43 at
  cap_high. `ll` = `hl` and `hh` = `lh` to the printed precision: there are no
  resistors on this node, so only the cap corner matters. Process/temperature move
  the junction-dominated contributors; the `Choff_x` unit cap is exactly 1 `C_u` in
  every corner.
- **What this says about DR-022 item 2 (observation only; the choice is #755).** The
  `Csamp_x`/`BPREF_x` branch is the largest contributor (about 56 % of `C_par` at
  `tt_27c_1.80v`), so path (b), removing the `Csamp_x`/`Cmsw*` network, addresses
  the largest share; `Choff_x` is a fixed 1 `C_u` in every corner, which path (a)
  is built around. These numbers do not say whether (b), (c) or (d) closes the
  gain-error row, and only the `tt`-device cap corners were run, not the combination
  of cap corners with ss/ff devices.

## Limits of this evidence

- Schematic-level only: no routing or MiM parasitics (no layout PEX; see the
  `sim/supply-impedance-sensitivity` records citing klayout-tools#1878).
- Single-ended capacitance with the other top plate at AC ground; the differential
  conversion moves both plates oppositely.
- One bottom-plate state, one sampled-input state (see "State" and "Floating
  BPREF_x"). r+c corners only at tt / 27 C / 1.8 V.
- **Uncontrolled differences.** The batch workers ran PDK `open_pdks
  c6d73a35f524070e85faff4a6a9eef49553ebc2b` (the superseded volare-era pin, see
  `sim/pdk.json`) and ngspice-46; the submitting host resolved `f6eeac7` and
  ngspice-42; the client `klt` was a dev build and the runner `klt` was 0.8.0. A
  local `--probe` at `tt_27c_1.80v` (submitting-host PDK / ngspice-42) gave
  33.299 fF / 3.962 `C_u`, matching the fleet's 33.299 fF to the printed digits, so
  no PDK/simulator sensitivity was seen at that one point; the other corners were
  not cross-checked.
- Tests: `python3 -m unittest sim.tests.test_top_plate_cpar` (deck edits, request
  shape, arithmetic, and a known-capacitance AC check).

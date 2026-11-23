# Comparator PEX record: 20261121-103712-a71fe14a

Real `klt extract --parasitics --pdk sky130A` parasitic extraction of the composed comparator layout `reports/20261027-183338-b96026c2/comparator.gds` and a `klt pex` schematic-vs-extracted comparison of the pick-off statistic, at the ratified 9-point one-at-a-time PVT grid (spec/target-spec.md "Numeric rows -- RATIFIED 2026-08-19") -- issue #1017's re-mint on the current layout (see Provenance for the `klt` version used). Supersedes the three September 2026 envelopes (`20260905-213747-bbf06dd`, `20260906-101231-1250ff4`, `20260906-152000-eace0b6`), which ran on klt 0.4.0 at two tt/27C corner points against layouts the drawing flow has since re-drawn; those records stay exactly as minted (append-only).

## Provenance

- `klt` version: **0.9.0** (layout/requirements.txt pins 0.6.0). For the November 2026 records, the builder reported errors at every corner on the first batch attempt, attributed them to a client/runner version mismatch, and switched to a throwaway venv under issue #1017 step 4. Only the successful run's envelopes are archived here.
- KLayout engine: 0.30.13
- PDK: sky130A (open_pdks f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7)
- Extraction deck content hash: `sha256:029ef177c1f4e872c13cc81093f94a02a9bbfe1f51939a88194a83532d60bf7c`
- repo commit: `a71fe14ae80ae8bc75482d7c9f8bf44115b411f5` on `feature/issue-1017` (dirty)
- layout source: `layout/comparator/reports/20261027-183338-b96026c2/comparator.gds` (this flow only reads `reports/LATEST`, never moves it)
- `body_bias.status`: **biased** (0 unbiased PMOS body nets) -- checked before any number below is read; an anonymous body net would make the extracted leg's resimulation physically wrong, not merely imprecise
- `extraction.model` (klt pex's own scope note): capacitance = net-to-ground for every net's own (non-coupled) area/perimeter, plus net-to-net for the vertical-overlap coupling `coupling` describes below -- a coupled net pair gets a direct capacitor between their two hub nodes, not just capacitors to the deck's ground/substrate net
- **Floating substrate net**: the extracted netlist declares `.GLOBAL vsubs` with no DC tie anywhere in the emitted netlist (klayout-tools#7066); the extracted leg simulates a substrate node whose voltage moves with switching activity. The comparator's OUTP/OUTN pick-off at 6.3 ns reads mid-regeneration, so this artifact is part of the extracted-side numbers below, disclosed alongside the parasitics.

## AC1/AC2: parasitic-annotated extraction, OUTP/OUTN capacitance in farads

`klt extract --parasitics --pdk sky130A` on the composed layout: 13 devices, 10 nets. Full per-net R/C (ground + every coupled-net term; vertical-overlap coupling only unless a net is named `--critical-net`, which this run does not use -- the same Phase 1 scope every earlier record here states) is in `extract.json`'s `parasitics.nets[]`; the OUTP/OUTN and VINN/VINP pairs the wire-area record flagged are pulled out below.

| Net | R (ohm) | C to ground (fF) | C coupled, total (fF) | C total (fF) |
|---|---|---|---|---|
| OUTP | 1087.22 | 7.5211 | 0.3098 | 7.8309 |
| OUTN | 1086.64 | 7.4270 | 0.2524 | 7.6794 |
| VINP | 217.85 | 1.4035 | 0.0237 | 1.4272 |
| VINN | 217.27 | 1.2835 | 0.0615 | 1.3450 |

- **OUTP/OUTN total-capacitance imbalance: 1.954%** (7.8309 fF vs 7.6794 fF) -- the farads restatement of the wire-area record's 0.65% claim, re-measured on THIS layout.
- **VINN/VINP total-capacitance imbalance: 5.933%** (1.4272 fF vs 1.3450 fF) -- same qualitative question as the wire-area record's 15.54% figure (structural trunk crossing, see `layout/comparator/README.md`), re-measured on THIS layout.

## AC3: schematic-vs-extracted pick-off delta (`klt pex`, ratified OAT grid)

Pick-off statistic v(OUTP)-v(OUTN) at t=6.3ns after the evaluate edge starts (matches sim/comparator-decision/run.py's own `_pickoff_deck` methodology, including issue #187's corrected instant -- see testbench.spice's header for the derivation), at two corner points per OAT rail: Vindiff=0 (isolates the routing/parasitic-driven imbalance, device mismatch structurally excluded) and Vindiff=+10mV (gain calibration, one of run.py's own `VINDIFF_GAIN_CAL_MV` points). The evaluate clock tracks the rail at every corner (an ideal switch onto the VDD rail node), the way the regen-corners campaign drives it.

| corner | rail (V) | gain sch (V/V) | gain ext (V/V) | zero-diff sch (uV) | zero-diff ext (uV) | parasitic offset (mV) |
|---|---|---|---|---|---|---|
| `ff_27c_1.80v` | 1.80 | +30.4227 | +14.7900 | +0.00 | -12570.00 | -0.84990 |
| `fs_27c_1.80v` | 1.80 | +19.4660 | +9.3940 | +0.00 | -8950.00 | -0.95274 |
| `sf_27c_1.80v` | 1.80 | +32.9521 | +14.3470 | +0.00 | -12070.00 | -0.84129 |
| `ss_27c_1.80v` | 1.80 | +19.0420 | +9.4290 | +0.00 | -8860.00 | -0.93965 |
| `tt_-40c_1.80v` | 1.80 | +28.4342 | +13.6990 | +0.00 | -10210.00 | -0.74531 |
| `tt_27c_1.62v` | 1.62 | +11.6410 | +5.6010 | +0.00 | -6020.00 | -1.07481 |
| `tt_27c_1.80v` | 1.80 | +20.2830 | +12.1130 | +0.00 | -10670.00 | -0.88087 |
| `tt_27c_1.98v` | 1.98 | +106.2971 | +15.6520 | +0.00 | -13920.00 | -0.88934 |
| `tt_125c_1.80v` | 1.80 | +18.7168 | +10.2420 | +0.00 | -10870.00 | -1.06132 |

At the star's center (tt/27C/1.8V): schematic gain +20.2830 V/V, extracted gain +12.1130 V/V (both correctly signed at the corrected instant), input-referred parasitic-driven offset -0.88087 mV.
At tt/27C/1.98 V the schematic gain of +106.2971 V/V is the output differential at the 6.3 ns pick-off divided by the single +10 mV input. Faster regeneration can increase this ratio. A sweep of smaller inputs would be needed to establish small-signal linearity at this rail.
Across the grid the input-referred parasitic-driven offset ranges to **-1.07481 mV** worst-case at `tt/vdd=1.620_vinn=0.810_vinp=0.810V/27C`. Full per-corner rows in `pex_zero.json` / `pex_cal.json` (`delta[]`).

## AC4: is the routing-driven component material against device mismatch?

**Worst-case input-referred parasitic-driven offset across the ratified grid: -1.07481 mV** (Vindiff=0 pick-off differential on the extracted netlist, converted through the extracted side's own gain, worst of 9 OAT corners).

Compared against the device-mismatch-only offset `sim/comparator-decision/records/20260821-071918-433a294.md` reports (`tt_mm`, N=16, seed=1): mean **35.24 mV**, stdev **97.08 mV**.

- The worst-case magnitude 1.07481 mV is 3.050% of the mismatch record's mean and 1.107% of its stdev (i.e. the mean is 33x larger, the stdev 90x larger).
- **Conclusion at the ratified grid: the routing-driven component is noise against the device-mismatch term, not material at this block's offset budget.** Even the grid's worst corner is over an order of magnitude smaller than either the mean or the stdev of the device-mismatch-only offset distribution -- device mismatch, not routing/parasitic imbalance, is what would need to shrink to move this comparator's offset budget. No floorplan change is warranted on offset grounds (per the wire-area record's own note).
- This conclusion is about **offset** specifically. It does not re-open regeneration-time/speed symmetry (a second-order, non-offset contributor `layout/comparator/README.md` already scopes out of this issue's acceptance criteria) or noise.

## Files

```
20261121-103712-a71fe14a/
  comparator.pex-extract.spice   klt extract --parasitics output (per-net R/C table source)
  extract.json                   klt extract --parasitics JSON envelope
  comparator_pex_reference.spice schematic DUT snapshot (committed wrap)
  testbench.spice                pex testbench (klt pex swaps its .include per leg)
  pex_request_zero.json          zero-Vindiff OAT request (corners + exclude carve)
  pex_request_cal.json           +10mV gain-cal OAT request (corners + exclude carve)
  pex_zero.json / pex_cal.json   klt pex JSON responses (extraction summary + delta[])
  record.md                      this file
```


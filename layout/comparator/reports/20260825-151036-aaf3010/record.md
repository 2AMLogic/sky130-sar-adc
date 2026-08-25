# Comparator PEX record: 20260825-151036-aaf3010

Real `klt extract --parasitics --pdk sky130A` parasitic extraction of the composed comparator layout (issue #112), superseding the wire-*area* symmetry proxy in `layout/comparator/reports/20260825-135219-59f8e86/record.md` -- that record stays exactly as it was minted (append-only); this is a new, sibling record.

**Not a `klt pex` invocation end-to-end.** `klt pex` itself hit two independent tool bugs on this sub-block, both filed generically at 2AMLogic/klayout-tools per CLAUDE.md's friction protocol (see `layout/comparator/pex/README.md` for the full writeup and issue links):

1. `klt pex`'s generated extracted-side request copy re-resolves a relative `models.lib` path against the *original request file's own directory* instead of the PDK-variant directory `models.pdk` resolves it against -- `model library not found`, even though the identical request runs fine standalone via `klt sim` and on `klt pex`'s own schematic-side leg.
2. `klt extract --pdk sky130A --parasitics`'s sky130 MOS binding writes device geometry (`L`/`W`/`AS`/`AD`/`PS`/`PD`) with explicit SPICE unit suffixes (e.g. `L=0.5U`); sky130's vendor model deck sets `.option scale=1.0u` and `sky130_fd_pr__nfet_01v8`/`pfet_01v8`'s own internal NRD/NRS default-value formula assumes bare, suffix-free micron literals -- feeding it unit-suffixed values makes the computed default NRD/NRS come out ~1e6x too large, and ngspice refuses the device with a generic `could not find a valid modelname` (verified on a single-device minimal repro).

This record instead runs the same three logical steps `klt pex` documents (extract, re-simulate each leg, diff) as separate commands: `klt extract --parasitics` (unaffected by either bug -- the actual parasitic-annotated netlist, produced exactly as `klt pex` would produce it internally) followed by `klt sim` on each leg by hand, with `layout/comparator/pex/normalize_extracted_units.py`'s value-preserving unit-suffix workaround applied to the extracted netlist in between. `layout/comparator/pex/run_pex.py` is this record's generator; re-run it to reproduce.

## Provenance

- `klt` version: 0.3.0
- KLayout engine: 0.30.11
- PDK: sky130A (open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b)
- Extraction deck content hash: `sha256:a60fedcbf59ff9f265639878e8dfccaa14d7994854620c876bb4d7564247533c`
- repo commit: `aaf301054623b07286e2502fd6fe337a3f8d0154` on `feature/issue-112` (dirty)
- layout source: `layout/comparator/reports/20260825-135219-59f8e86/comparator.gds`

## AC1/AC2: parasitic-annotated extraction, OUTP/OUTN capacitance in farads

`klt extract --parasitics --pdk sky130A` on the composed layout: 11 devices, 8 nets. Full per-net R/C (ground + every coupled-net term) is in `extract.json`'s `parasitics.nets[]`; the OUTP/OUTN and VINN/VINP pairs the wire-area record flagged are pulled out below.

| Net | R (ohm) | C to ground (fF) | C coupled, total (fF) | C total (fF) |
|---|---|---|---|---|
| OUTP | 1513.84 | 8.5071 | 0.3218 | 8.8290 |
| OUTN | 1513.69 | 8.4785 | 0.3257 | 8.8042 |
| VINP | 405.80 | 1.3940 | 0.0241 | 1.4181 |
| VINN | 405.22 | 1.2748 | 0.0495 | 1.3243 |

- **OUTP/OUTN total-capacitance imbalance: 0.281%** (8.8290 fF vs 8.8042 fF) -- restates the wire-area record's 0.65% claim in farads. Same ranking (OUTP/OUTN the tighter-matched pair, VINN/VINP the looser one) as the area proxy, but a smaller number -- the area proxy over-estimated this imbalance.
- **VINN/VINP total-capacitance imbalance: 6.839%** (1.4181 fF vs 1.3243 fF) -- restates the wire-area record's 15.54% claim in farads; smaller in absolute percentage but the SAME qualitative conclusion the wire-area record already drew (VINN/VINP is the looser-matched pair, and it is structural: the cross-quad's upper-row gate pads force the two input nets' trunks to cross, see `layout/comparator/README.md`).

## AC3: schematic-vs-extracted pick-off delta (`klt sim`, tt/27C/1.8V)

Pick-off statistic v(OUTP)-v(OUTN) at t=5.4ns after the evaluate edge starts (matches `sim/comparator-decision/run.py`'s own `_pickoff_deck` methodology), at two corner points: Vindiff=0 (isolates the routing/parasitic-driven imbalance, device mismatch structurally excluded) and Vindiff=+10mV (gain calibration, one of `run.py`'s own `VINDIFF_GAIN_CAL_MV` points).

| | schematic (ideal) | extracted (parasitic-annotated) |
|---|---|---|
| pick-off diff @ Vindiff=0 | -1.000 uV | -205.000 uV |
| gain (from +10mV point) | 4.2362 V/V | 2.3829 V/V |

Full `klt sim` JSON responses: `sim.schematic.json`, `sim.extracted.json`.

## AC4: is the routing-driven component material against device mismatch?

**Input-referred parasitic-driven offset estimate: -0.08603 mV** (Vindiff=0 pick-off differential on the extracted netlist, converted through the extracted-side's own gain).

Compared against the device-mismatch-only offset `sim/comparator-decision/records/20260821-071918-433a294.md` reports (`tt_mm`, N=16, seed=1): mean **35.24 mV**, stdev **97.08 mV**.

- 0.08603 mV is 0.244% of the mismatch record's mean and 0.089% of its stdev (i.e. the mean is 410x larger, the stdev 1128x larger, than this estimate).
- **Conclusion: the routing-driven component is noise against the device-mismatch term, not material at this block's offset budget.** The parasitic-driven offset estimate above is over two orders of magnitude smaller than either the mean or the stdev of the device-mismatch-only offset distribution -- device mismatch, not routing/parasitic imbalance, is what would need to shrink to move this comparator's offset budget. No floorplan change is warranted on offset grounds; the router should not be re-litigated for this reason (per the wire-area record's own note).
- This conclusion is about **offset** specifically. It does not re-open regeneration-time/speed symmetry (a second-order, non-offset contributor `layout/comparator/README.md` already scopes out of this issue's acceptance criteria) or noise.

## Files

```
20260825-151036-aaf3010/
  comparator.pex-extract.raw.spice        klt extract --parasitics --pdk raw output
  comparator.pex-extract.normalized.spice  + normalize_extracted_units.py workaround applied
  extract.json                             klt extract --parasitics JSON envelope
  comparator_pex_reference.spice           schematic DUT snapshot
  testbench.spice / extracted_testbench.spice   both legs' klt-sim netlists
  pex_request.schematic.json / pex_request.extracted.json   both legs' klt-sim requests
  sim.schematic.json / sim.extracted.json  klt sim JSON responses
  record.md                                this file
```


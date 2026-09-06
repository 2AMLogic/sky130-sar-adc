# Comparator PEX pick-off timing re-derivation: 20260906-144802-eace0b6

Re-derives `layout/comparator/pex/testbench.spice`/`pex_request.json`'s fixed pick-off instant for the DR-004 Amendment A topology's *extracted* (parasitic-loaded) leg (issue #187), following `sim/comparator-decision/run.py`'s own reset->evaluate transient methodology. `layout/comparator/pex/regen_probe.py` is this record's generator; re-run it to reproduce.

**Why the prior instant (5.4ns absolute, i.e. 0.3ns after the evaluate edge) was wrong for this topology's extracted leg**: at that early instant the extracted netlist's differential output is still dominated by an early transient artifact (capacitive/resistive loading on the internal DIP/DIN and OUTP/OUTN nodes delays the true, correctly-signed regenerative response), not the device-level gm*Vindiff response the schematic leg already shows cleanly at that instant. The result is a *negative*-going pick-off differential for a *positive* applied Vindiff -- exactly the sign flip `reports/20260906-101231-1250ff4/record.md`'s AC3 found.

## Method

Reset(CLK=0, 5.0ns)->evaluate(CLK=1.8V) single-edge transient, identical stimulus to `sim/comparator-decision/run.py`'s `regen` subcommand (5.0ns reset, 0.1ns edge, Vcm=0.9V), but on the `.SUBCKT gen_compose_0`-wrapped DUT (matching `testbench.spice`'s own `Xdut ... gen_compose_0` instantiation, not `run.py`'s flat-fragment convention) for two DUTs: `comparator_pex_reference.spice` (ideal schematic) and a fresh `klt extract --parasitics --pdk sky130A` of the current `reports/LATEST` composed layout (`20260906-113406-2d66a6a/comparator.gds`).

Vindiff sweep: [0.0, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0] mV at the nominal tt/27C corner, for both legs. Two quantities are extracted per point: the full decision (regeneration) time -- first time |v(OUTP)-v(OUTN)| crosses 0.9V (0.5*VDD), same threshold `run.py`'s `regen` subcommand uses -- and the raw pick-off differential v(OUTP)-v(OUTN) at each of a grid of candidate instants after the evaluate edge starts: [0.3, 0.5, 0.7, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0] ns.

## Schematic-leg cross-check (methodology parity)

The schematic leg's regen times below should reproduce `sim/comparator-decision/records/20260906-075157-7724af3.md`'s own flat-fragment-driven numbers exactly, since the devices are identical and only the SUBCKT wrapper differs -- confirming this script's SUBCKT-instantiation methodology is equivalent, not a different measurement.

| Vindiff (mV) | schematic regen time (ns) |
|---|---|
| +0.50 | 2.3550 |
| +1.00 | 2.1750 |
| +2.00 | 1.9950 |
| +5.00 | 1.7550 |
| +10.00 | 1.5750 |
| +20.00 | 1.3950 |
| +50.00 | 1.1150 |

## Extracted-leg zero-input control: does it stay balanced?

With no differential input applied, the ideal schematic leg stays at exactly 0V forever (perfectly symmetric ideal netlist -- `run_pex.py`'s own AC3 table always reports its Vindiff=0 pick-off as +0.000 uV). The extracted leg does NOT: real, deterministic routing/parasitic asymmetry (documented in `reports/20260906-101231-1250ff4/record.md`'s AC1/AC2 per-net R/C table) gives it a genuine, if small, built-in differential that GROWS over time under the latch's own positive feedback -- eventually saturating to a rail with no input at all, given enough evaluate time. This is the routing-driven offset AC3/AC4 exist to quantify, seen directly rather than inferred.

| t after evaluate edge (ns) | extracted pick-off diff, Vindiff=0 (mV) |
|---|---|
| 0.3 | +0.1851 |
| 0.5 | -4.3041 |
| 0.7 | -6.8177 |
| 0.9 | -8.8552 |
| 1.0 | -9.6753 |
| 1.1 | -10.5213 |
| 1.2 | -11.3246 |
| 1.3 | -12.0676 |
| 1.4 | -12.7342 |
| 1.5 | -13.0839 |
| 1.6 | -13.2653 |
| 1.8 | -15.7292 |
| 2.0 | -23.1803 |

## Extracted-leg pick-off at the gain-calibration point (Vindiff=+10mV)

This is the column that was sign-flipped at the old 0.3ns instant. It crosses from negative (artifact-dominated) to positive (true, correctly-signed device response) within about half a nanosecond of the evaluate edge:

| t after evaluate edge (ns) | extracted pick-off diff, Vindiff=+10mV (mV) | schematic, same t (mV) |
|---|---|---|
| 0.3 | -5.3720 | +17.9470 |
| 0.5 | +15.5503 | +53.0664 |
| 0.7 | +40.1155 | +101.1471 |
| 0.9 | +70.7190 | +148.0755 |
| 1.0 | +85.2249 | +157.5303 |
| 1.1 | +101.8494 | +178.9932 |
| 1.2 | +118.8782 | +224.5396 |
| 1.3 | +135.8489 | +305.1888 |
| 1.4 | +153.0725 | +459.1440 |
| 1.5 | +165.4915 | +705.3466 |
| 1.6 | +174.8635 | +979.4858 |
| 1.8 | +218.2025 | +1373.2512 |
| 2.0 | +333.1495 | +1567.4549 |

## Recommendation

**PICKOFF_NS = 1.2ns after the evaluate edge (absolute PICKOFF_AT_NS = 6.3ns)**, chosen because at this instant:

1. The extracted leg's +10mV cal point is unambiguously positive with margin (+118.8782 mV), not near the sign-crossing boundary seen in the table above.
2. The extracted leg's zero-input control (-11.3246 mV) is still a small fraction of VDD (0.63%), i.e. this is still a genuine early PICK-OFF, not a saturated decision.
3. The schematic leg at the same instant (+224.5396 mV, 12.5% of VDD) is likewise not yet saturated, preserving the methodology's intended early-linear-region character on both legs -- pushing the instant much later (e.g. 3ns+) would drive the schematic leg's own "gain" number into a fully-decided, non-linear regime instead.
4. The resulting input-referred offset estimate (`ext_zero_diff / ext_gain`) is **-0.9526 mV** at this instant, and stays within the same order of magnitude across the whole 1.0-2.0ns window around it (see the two tables above) -- this is not a knife-edge choice sensitive to the exact instant.

## Corner spot check (Test Plan edge case)

Extracted leg only, at Vindiff in {0, +10} mV, spot-checked at `ss/-40C` (slow+cold) and `ff/125C` (fast+hot) -- the two ends of the ratified process/temp corner set (spec/target-spec.md) -- to check whether the recommended instant is corner-dependent. This is a spot check bracketing the skew, not a full PVT sweep: `pex_request.json`'s own corner matrix is tt/27C-only today (same subset-corner convention documented throughout `sim/README.md`), and this record does not change that.

| corner | Vindiff (mV) | pick-off diff @ 1.2ns (mV) |
|---|---|---|
| `ss/-40C` | +0.00 | -9.0831 |
| `ss/-40C` | +10.00 | +101.8308 |
| `ff/125C` | +0.00 | -10.8450 |
| `ff/125C` | +10.00 | +102.1913 |

Both skewed corners show the same qualitative behaviour as tt/27C at 1.2ns: a modest, non-saturated zero-input control and an unambiguously positive, comparable-magnitude +10mV cal point (compare +118.9 mV at tt/27C above) -- no evidence a corner-dependent instant is needed for this specific (Vindiff=0, Vindiff=+10mV) two-point methodology, though a full PVT sweep of `pex_request.json` itself is out of this record's scope (see Scope and caveats).

## Scope and caveats

- This record characterizes the extracted netlist's OWN early transient behaviour to justify a pick-off instant; it does not re-run `run_pex.py`'s AC1-AC4 (a separate, superseding PEX record does that with the corrected instant -- see `layout/comparator/pex/README.md`).
- The corner spot check above is two points bracketing the ratified process/temp skew, not the full ratified PVT grid; `pex_request.json` itself still runs tt/27C only, unchanged by this issue.
- `EVALUATE_NS` here is 12ns (vs `run.py`'s 40ns) -- long enough that every measured `regen_ns` above resolved well inside the window; a genuinely UNRESOLVED point would be reported as such, not silently truncated.

## Files

```
20260906-144802-eace0b6/
  comparator.pex-extract.spice   klt extract --parasitics output (extracted-leg DUT used by this sweep)
  extract.json                   klt extract --parasitics JSON envelope
  sweep.json                     full machine-readable sweep + corner-spot-check data
  record.md                      this file
```

## Environment

- PDK: sky130A @ c6d73a35f524070e85faff4a6a9eef49553ebc2b
- ngspice: ngspice-46
- Harness: sim/harness 0.1.0
- git: `eace0b613515752180a353e43eca6fd7c683cfdf` on `feature/issue-187` (dirty)
- DUT netlist sha256: `b248381da3cf8a36bda775b27824d6d12b556d3b54f1fea6110acbcdd72d3555`
- klt version: see extract.json's provenance.klt_version

- **Supersedes**: (none)

Written by `layout/comparator/pex/regen_probe.py`. Append-only: never edit or delete this file -- a re-run or correction mints a new record-id and points back here via **Supersedes** (see `sim/README.md`).

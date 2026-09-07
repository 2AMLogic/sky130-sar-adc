# Chipalooza Challenge #4 (Sky130) — 10-bit SAR ADC proposal

**Status of this document: DRAFT design record, not a submission-ready
proposal.** Open Circuit Design's [Chipalooza Challenge
#4](https://opencircuitdesign.com/chipalooza/) rules page (`rules-4.html`)
had not published as of this document's authoring (2026-09-05); the
epic tracking table (2AMLogic/2am#542) lists a 2026-11-09 publish date.
Per this issue's own acceptance criteria, this document assumes the common
structure shared by Challenges #2/#3 (`rules-2.html`/`rules-3.html`) until
`rules-4.html` publishes, and does not block on the unpublished rules. **When
`rules-4.html` publishes, a follow-up pass must re-verify every slot-budget
number and rail assumption in §2 against the actual text** — nothing here is
final.

**Source repository**: `2AMLogic/sky130-sar-adc` (`visibility: public`,
flipped 2026-08-25 per Epic #542 Phase 4A — confirmed via `gh repo view`
at authoring time). Every number in §4 is transcribed from this
repository's own append-only `sim/` evidence and from
[`spec/target-spec.md`](../../spec/target-spec.md) /
[`docs/characterization-report.md`](../../docs/characterization-report.md),
with a dated citation to the record it came from. Per `CLAUDE.md`'s
clean-room rule, nothing in this document is derived from, or checked
against, any other party's implementation — every figure traces to this
repo's own design sources or its own re-runnable `sim/` testbenches.

This document reports the design's status **honestly, including where it
falls short of the brief's full sign-off bar** — per `CLAUDE.md`'s "no claim
without a testbench" and "no spec row is relaxed to make a result pass"
rules, and per this issue's own acceptance criteria ("every spec row states
met/unmet... no row is relaxed to make it pass"). It is not written as if it
were submission-ready; it is a snapshot of where the design stands and what
remains before it would be.

---

## 1. Type of IP block

A 10-bit, single-channel, differential, top-plate-sampled
Successive-Approximation-Register (SAR) analog-to-digital converter,
implemented entirely on Sky130's 1.8 V core device flavor
(`nfet_01v8`/`pfet_01v8`) with `sky130_fd_sc_hd` standard cells for the
digital SEL-inverter drivers. Provisional sample rate range: 100 kS/s – 1
MS/s (DRAFT, not yet re-derived from settling data — see §4).

---

## 2. I/O list, including test ports

### 2.1 Rails: this block is ratified single-supply, 1.8 V core throughout

**This section corrects an assumption in this issue's own filed body.** The
issue that requested this document assumed, as a starting point, "Sky130's
native rails (1.8V digital / 3.3V analog)" — i.e. that the analog signal
path would run on a 3.3 V-class device. That is **not** what this repository
has designed or ratified. Per
[`spec/target-spec.md`](../../spec/target-spec.md) (supply flavor ratified
2026-08-13, [DR-001](../../spec/decision-records/DR-001-supply-flavor-scope.md);
numeric rows ratified 2026-08-19,
[DR-003](../../spec/decision-records/DR-003-numeric-spec-derivation.md)):

- The **entire** signal path — CDAC array, sampling front end, comparator,
  and SAR sequencer — is built on the **1.8 V core** device flavor
  (`nfet_01v8`/`pfet_01v8`), the same rail as the digital logic. There is no
  separate 3.3 V (or higher) analog rail anywhere in this design.
- `V_REF = V_DD = 1.8 V` — **at** the core rail, not above it. Per the
  ratified DR-002 tripwire in `spec/target-spec.md`, a higher-voltage or
  mixed-voltage arrangement (thick-oxide front end, `nfet_g5v0d10v5`/
  `pfet_g5v0d10v5`) is explicitly **deferred**, and would require its own
  ratification (a DR-002 follow-on) before any switch is drawn on it. This
  design has never simulated, laid out, or characterized any device above
  the 1.8 V core rail.
- CLAUDE.md's framing of the pass-device flavor for a "3.3 V input" as "a
  ratification question, not an assumption" describes a decision this repo
  has not had to make, because the ratified full-scale input range never
  exceeds 1.8 V (see §6). If a future Challenge #4 slot budget forces a
  wider input range, that would trip the DR-002 tripwire and require a new
  decision record — it is not assumed here.

Every row in §4 below is therefore reported at a single supply point,
1.8 V ± 10 % (1.62 / 1.80 / 1.98 V), not two rails.

### 2.2 Pad table, mapped to the assumed Challenge #4 slot budget

Per this issue's stated common structure: 24 digital control inputs, 12
digital test outputs, 4 shared (multiplexed) analog lines, 0–4 dedicated
pads, harness-supplied bias/bandgap reference, SPI control interface
supplied by the harness (not per-block).

| Signal | Dir | Assumed Challenge slot | Count used | Notes |
|---|---|---|---|---|
| `VDD` | supply | 1.8 V digital/analog rail (shared) | — (rail, not a slot line item) | Single supply for the whole block — analog and digital share the same rail (§2.1) |
| `VINP`, `VINN` | in, dedicated (2 pads) | dedicated pad (budget: 0–4) | 2 | Differential analog input, driven onto the sampling front end (`design/sampling_frontend.sch`), 0–`V_REF` single-ended range each side |
| `VREFP`, `VREFN` | in, dedicated (2 pads) | harness-supplied bandgap reference — **mismatch flagged below** | 2 | Differential reference into the CDAC array's bottom-plate switches. **Open item**: this design's reference is differential (two nodes), while the common structure names a single "bias/bandgap reference." Whether the harness can supply a differential pair, or whether this design would need to derive `VREFN` locally from a single-ended harness reference, is unresolved — named here, not guessed (see §7) |
| `VCM` | in, dedicated | dedicated pad (budget: 0–4) | 1 | Common-mode bias, `V_REF/2 = 0.9 V` nominal. Every functional testbench in this repo still drives it from an ideal source — no on-chip `VCM` buffer/reference network exists in this design. A single-corner (`tt`/27 °C/1.8 V) drive-impedance/decoupling *budget* now exists ([`sim/vcm-drive-budget/records/20260905-201703-f012255.md`](../../sim/vcm-drive-budget/records/20260905-201703-f012255.md)), quantifying — not yet closing — the same class of gap the port-parity sibling `gf180-sar-adc` names for its own `V_CM` row (see §7 Item 6) |
| `CLK` | in | digital control input (budget: ≤24) | 1 | Master clock; provisional range 1.2–12 MHz (DRAFT, [DR-006](../../spec/decision-records/DR-006-sar-sequencer-bit-count-and-timing-budget.md), not re-derived from settling data) |
| `RST_B` | in | digital control input | 1 | Active-low synchronous reset into the ring sequencer |
| `DOUT9..DOUT0` | out | digital test output (budget: ≤12) | 10 | 10-bit parallel output register, `DOUT9` = MSB |
| `BUSY` | out | digital test output | 1 | Conversion-in-progress strobe |

**Totals against the assumed budget**: 2 of ≤24 digital control inputs
(`CLK`, `RST_B`), 11 of ≤12 digital test outputs (`DOUT9..0` + `BUSY`), 3 of
0–4 dedicated pads if `VINP`/`VINN`/`VCM` alone are counted as dedicated, **or
5 of 0–4 if `VREFP`/`VREFN` must also be dedicated pads rather than a shared
harness reference** — the latter would exceed a 4-pad dedicated ceiling.
This is stated as an open slot-budget risk, not resolved by assumption (see
§7); it cannot be resolved definitively until `rules-4.html` publishes and
states the real per-signal budget categories.

There is **no on-chip SPI interface** in this design — `design/sar_adc_top.sch`
exposes only the parallel `CLK`/`RST_B`/`DOUT*`/`BUSY` port set (see §2.3).
This is a plain design fact (the netlist's own port list,
`design/sar_adc_top.spice`), not a ratified interface-scope decision record
the way the port-parity sibling `gf180-sar-adc` has one (`DR-0005`) — no
equivalent decision record exists in this repo. If Challenge #4's SPI
control interface must reach this block's own control/readback ports rather
than only global harness configuration, a small interface-adapter
sub-block would need to be designed; that is not assumed to already exist.

### 2.3 What this repo's own port list is, verbatim

`design/sar_adc_top.spice`'s top-level subcircuit port list (regenerated
from `design/sar_adc_top.sch`, staleness-checked in CI by
`design/regen_netlist.sh --check`):

```
.subckt sar_adc_top VINP VINN VDD VREFP VREFN VCM CLK RST_B \
  DOUT9 DOUT8 DOUT7 DOUT6 DOUT5 DOUT4 DOUT3 DOUT2 DOUT1 DOUT0 BUSY
```

Nothing is added or dropped in §2.2's mapping above — it is exactly this
netlist's own external port list, categorized against the assumed slot
budget.

---

## 3. Functional description

The converter samples a differential input onto a binary-weighted, 512
(unit-cap) positions-per-side capacitive DAC (CDAC) array
(`design/cdac/cdac_array.sch`), then resolves 10 bits by successive
approximation against an internal comparator
(`design/comparator.sch`), using top-plate sampling with a "free" MSB
decision resolved directly from the sampled charge — the sampling front
end (`design/sampling_frontend.sch`) holds the top plate through a
bootstrapped switch network during acquisition, and the CDAC array itself
implements the remaining 9-bit binary-weighted sub-array plus a
non-switching termination unit per side
([DR-005](../../spec/decision-records/DR-005-cdac-array-design.md)). A
synchronous ring sequencer (`design/sar_sequencer.sch`) runs the conversion
over `N + 2 = 12` master-clock periods, provisionally one clock per phase,
uniformly — 1 sample phase, 10 bit-trial phases (MSB first), and 1
end-of-conversion phase
([DR-006](../../spec/decision-records/DR-006-sar-sequencer-bit-count-and-timing-budget.md)).
The full hierarchy is captured in `design/sar_adc_top.sch` and its
regenerated netlist `design/sar_adc_top.spice`.

**Physical readiness, stated plainly**: schematic capture is complete and
regenerates cleanly for every sub-block and the assembled top level. Layout
exists **per sub-block, for all four sub-blocks** — `layout/comparator/`,
`layout/sar-sequencer/` (a standard-cell place-and-route flow),
`layout/cdac-array/`, and `layout/sampling-frontend/` are all DRC-clean and
LVS-clean; #99/#100/#101/#102 (the four sub-block layout issues) are all now
**closed**. `layout/cdac-array/`'s original LVS "match" verdict
(`reports/20260825-132454-51cbdd4/`) did not reproduce against its own
committed artefacts — a regression discovered 2026-09-05 and tracked as
#148 — but #148's own investigation found and fixed the root cause (`klt
lvs`'s `options.combine_devices` unreliably re-summing hundreds of
identical-valued parallel unit capacitors into one combined device; the
fix compares the array's 1024 drawn unit capacitors 1:1 against the
reference instead, with no folding needed on either side) and minted a
fresh record, `reports/20260905-220338-9fb9b04/`, whose LVS match
reproduces on repeat runs. The sampling front end (#99) closed via PR #152
(merged 2026-09-05T23:22:50Z): 24/24 devices, 17/17 nets, 12/12 pins,
DRC-clean and LVS-clean, with three negative-control mismatches confirming
the checker's sensitivity — see
[`layout/sampling-frontend/reports/20260905-204934-f012255/record.md`](../../layout/sampling-frontend/reports/20260905-204934-f012255/record.md).
**No top-level assembled ADC layout (GDS) exists yet** — the routed
integration of the four sub-block layouts into one top-level GDS matching
`design/sar_adc_top.sch`'s hierarchy is tracked as issue #103. All four of
#103's original sub-block dependencies are closed, and #103 has since
shipped a fifth composition-level block it needs directly,
`layout/seln-inverters/` (the nine `SELn<i> = NOT(DOUT<i>)` glue inverters
`design/sar_adc_top.sch` adds at the integration level; DRC-clean and
LVS-clean on its own, PR #166). That same PR's floorplan/routing
investigation — direct KLayout-API inspection of every sub-block's own
committed GDS geometry, not just each block's published pin-position table —
found a real sub-block-layout completeness gap: `cdac_array`'s (#100) `VDD`
pin is a bare `nwell` region with no drawn tap/contact anywhere on it, and
its `SELp<i>`/`SELn<i>` pins are bare-poly straps with no safe field-poly
landing area, so neither can be physically contacted by a top-level
composition without risking a silent electrical defect. That gap was
tracked as **#165** and has since **closed** — PR #170 (merged
2026-09-06T02:19:15Z) added a real n-well tap for `VDD` and a poly landing
pad for each of the 18 `SELp<i>`/`SELn<i>` nets, re-ran `cdac_array`'s own
DRC/LVS flow clean, and confirmed via a diff of the extracted netlist that
every switch transistor's `L`/`W`/`AS`/`AD`/`PS`/`PD` is byte-identical to
the prior record (no silent device-sizing change). #103 itself still
carries `loom:blocked` as of this pass — its own dependency re-check
against #165's closure has not yet landed — but every top-level pin,
including these 18 plus `VDD`, has now been independently verified to have
real, externally-reachable conductor, so the composition/routing plan is
ready to execute once #103 is reclaimed (see
`layout/sar-adc-top/README.md` for the full per-pin geometry investigation).
All roll up under the layout epic #25.

**Top-level assembly has since landed (PR #174, merged
2026-09-06T04:46:23Z), partially closing that gap.** A composed, routed
`sar_adc_top.gds` now exists at
[`layout/sar-adc-top/reports/20260906-043420-662a84d/sar_adc_top.gds`](../../layout/sar-adc-top/reports/20260906-043420-662a84d/),
placing all five sub-block layouts
(`sampling_frontend`/`cdac_array`/`comparator`/`sar_sequencer`/
`seln_inverters`) via `klt gen-compose` and hand-routing every net
`design/sar_adc_top.sch` calls for via `klt draw`:

- **`klt drc`**: **clean, 0 violations**, on the fully composed top-level
  layout ([`drc.json`](../../layout/sar-adc-top/reports/20260906-043420-662a84d/drc.json)).
- **Connectivity**: verified net-by-net against the intended interconnect via
  an unfiltered `klt extract` (no declared-pin restriction) — every one of
  this design's top-level nets extracts as its own distinct, correctly-scoped
  node with the intended cross-sub-block membership; see the record's own
  connectivity table
  ([`record.md`](../../layout/sar-adc-top/reports/20260906-043420-662a84d/record.md)).
  One row (`CLK`) shows three separate extracted net-name strings rather than
  a single match, which reads as a discrepancy in that table alone — but per
  `layout/sar-adc-top/README.md`'s "LVS pin declaration blocker" section this
  is a net-naming artifact of two sub-blocks' independently-synthesized
  standard-cell macros reusing generic internal labels (`A`/`X`), not a real
  electrical short or open; the true `CLK` net's device count is verified
  separately and correctly in that same investigation.
- **`klt lvs`**: **still reports a mismatch** — not from a routing defect,
  but because no available `klt extract` declared-pin mechanism
  (`--top-cell-pins`/`--pins`/`--def-pins`) reproducibly promotes exactly
  this design's own intended 19-port top-level interface once composed from
  five independently-labeled sub-blocks with no governing top-level DEF (two
  of the five are placed-and-routed standard-cell macros carrying their own
  internal, generic net labels that collide with this design's own ports
  once flattened for extraction: layout=867/reference=867 devices,
  matched=812, 23 pins promoted against an expected 19). Filed generically
  at [klayout-tools#1513](https://github.com/2AMLogic/klayout-tools/issues/1513)
  per this repo's friction protocol — the same class of gap
  klayout-tools#1385/#1390 already fixed for a single placed-and-routed
  macro, recurring one composition level up. **Update this pass**:
  klayout-tools#1513 **closed** 2026-09-06T06:45:36Z, fixed by
  klayout-tools#1515 (merged the same minute) adding `--pin-source-cells`, a
  new `klt extract`/`klt lvs` mechanism that resolves a composed assembly's
  top-level ports by physical label position rather than string matching —
  exactly this gap. **Not yet consumable**: PyPI's `klayout-tools` package
  still tops out at 0.4.0 (`pip index versions klayout-tools` /
  `pypi.org/pypi/klayout-tools/json`, checked 2026-09-06), the same version
  already pinned in `layout/requirements.txt` — the fix is merged to
  `klayout-tools`'s `main` but has not been cut into a release yet.

**#103 itself remains open, `loom:blocked`** — the Curator's 2026-09-06
dependency re-check confirmed the block reason changed from "no assembly
exists" to "assembly exists, DRC-clean and connectivity-verified, but an
automated LVS **match** verdict is blocked on the upstream klayout-tools#1513
pin-declaration gap," and no post-layout PVT re-simulation of the assembled
top level has been run. The upstream gap itself has since closed (fixed,
unreleased — see above), narrowing the block reason one step further to
"waiting on a `klayout-tools` release newer than the pinned 0.4.0," not an
open upstream question. This narrows, but does not close, the single
largest gap between this design and the brief's sign-off bar (§4, §7).

**Update this pass (2026-09-06)**: the composed layout above has since been
re-verified against a real geometry change, not just re-stated. Issue #175
(DR-004 Amendment A, §7 Item 3) changed `design/comparator.sch`'s device
count (9 → 11), which invalidated `layout/comparator/`'s own LVS match;
issue #180 closed via PR #188 (merged 2026-09-06T12:27:03Z), re-drawing that
sub-block against the amended topology and re-establishing its own LVS
match, then re-running `layout/sar-adc-top/`'s full flow against the updated
geometry. The outcome is unchanged in kind, restated with fresh numbers: DRC
stays clean, connectivity stays independently verified correct, and `klt
lvs` still mismatches for the identical upstream reason (now
layout=869/reference=869 devices, matched=794, 23 pins promoted vs. 19
expected — the small count shift from 867/867/812 tracks the comparator's
own +2-device change, not a new or different defect). See
[`layout/sar-adc-top/reports/20260906-101939-1250ff4/record.md`](../../layout/sar-adc-top/reports/20260906-101939-1250ff4/record.md)
(`reports/LATEST`), which supersedes the `20260906-043420-662a84d` record
cited above for the pre-#180 geometry. §4's rows below now cite this newer
record.

---

## 4. Target specification at Sky130's ratified 1.8 V rail

Every row below is reported at this repository's own ratified PVT grid —
process corners `{ff, fs, sf, ss, tt}`, temperature `{−40, 27, 125} °C`,
supply `{1.62, 1.80, 1.98} V`, one-at-a-time (9 points) — per
`spec/target-spec.md`'s "Numeric rows — RATIFIED 2026-08-19" section and
`sim/README.md`'s "Corner-grid shape." No row below has ever been measured
at, or claimed to hold at, any rail above 1.8 V core (§2.1).

The verdict column below distinguishes three cases per this issue's own
acceptance criterion ("every spec row states met/unmet... no row is
relaxed"):
- **MET** — spec row is ratified and evidence shows it passes at every
  bound corner.
- **UNMET** — spec row is ratified and evidence shows a specific,
  named shortfall at a specific corner (not relaxed to hide it).
- **DRAFT / not ratified** — the target-spec row itself is not yet an
  operator-ratified number; evidence may exist and is reported
  informationally, but there is no ratified line to grade a verdict
  against.
- **BLOCKED** — no evidence exists yet; names the specific issue that would
  produce it.

This table mirrors, and is derived from,
[`docs/characterization-report.md`](../../docs/characterization-report.md) —
a machine-checked, regenerable aggregation (`sim/report/generate.py --check`,
wired into CI) tying every `spec/target-spec.md` row to its evidence. Where
the two differ in wording, `docs/characterization-report.md` is the
authoritative, regenerable source; this table restates it for the Chipalooza
audience with an explicit Challenge-brief verdict column.

| Parameter | Target (min/typ/max) | Status | Verdict at Sky130 1.8 V rail | Source (dated) |
|---|---|---|---|---|
| Architecture | charge-redistribution SAR, differential, top-plate sampling | DRAFT (descriptive) | Implemented as described | `design/sar_adc_top.sch`, `design/cdac/cdac_array.sch`, `design/sampling_frontend.sch`, `design/comparator.sch`, `design/sar_sequencer.sch` |
| Resolution `N` | 10 bit | **RATIFIED** (DR-003 via #27) | **MET** — 9/9 corners, correct MSB-first bit-by-bit capture | [`sim/sar-sequencer-behavioral/records/20260827-211956-e13bc1e.md`](../../sim/sar-sequencer-behavioral/records/20260827-211956-e13bc1e.md) |
| `V_REF` | `1.8 V` (= `V_DD`, at the rail) | **RATIFIED** (DR-003 via #27) | **MET** — structural + functional/monotonicity check, 9/9 corners | [`sim/cdac-array-transfer/records/20260827-213107-e13bc1e.md`](../../sim/cdac-array-transfer/records/20260827-213107-e13bc1e.md) |
| LSB (differential) | `2·V_REF/2^N = 3.5156 mV` | **RATIFIED** (DR-003 via #27) | **MET** — same record as `V_REF` | same record |
| Sampling cap (CDAC unit × array) | `C_u ≈ 8.65 fF`, `2^9 = 512` positions/side | **RATIFIED** (DR-003 via #27) | **MET** — sim structural check (9/9 corners); independent layout evidence also exists and is now DRC- and LVS-confirmed (drawn `C_u = 8.6473 fF`, unit-cap count 1024 = 512/side × 2). The original record's LVS "match" did not reproduce against its own committed artefacts (#148); #148's fix compares the array's 1024 drawn unit capacitors 1:1 against the reference (no `combine_devices` folding) and its replacement record's match reproduces on repeat runs | same record; [`layout/cdac-array/reports/20260905-220338-9fb9b04/record.md`](../../layout/cdac-array/reports/20260905-220338-9fb9b04/record.md) (supersedes `reports/20260825-132454-51cbdd4/`, see #148) |
| Comparator input-referred noise | `≤ 1.0148 mV rms` (baseline) / `≤ 0.5859 mV rms` (stretch) | **RATIFIED** (DR-003 via #27) | **MET** vs. baseline at binding corner `tt_125c_1.80v` = 0.8643 mV rms; **UNMET** vs. stretch at the same corner. Reduced-sub-model methodology named ([DR-004](../../spec/decision-records/DR-004-comparator-topology-and-noise-budget.md)). Re-measured this pass against issue #175's amended (reset-integrity-fixed) device set — the binding-corner figure moved from 0.9591 to 0.8643 mV rms; the pass/fail outcome is unchanged | [`sim/comparator-decision/records/20260906-065109-eedd532.md`](../../sim/comparator-decision/records/20260906-065109-eedd532.md) |
| Corners | −40/27/125 °C, ±10 % supply, sky130 process corners | **RATIFIED** (DR-003 via #27) | **MET** — corner runner switches `.lib` process sections correctly, harness self-test negative control passes | `sim/harness-corner-smoke/records/`, `sim/mc-smoke/records/` |
| Sample rate | provisional 100 kS/s–1 MS/s | DRAFT | **UNMEASURED as an end-to-end figure (all four constituent mechanisms now checked individually — all four now PVT-complete, one of the four found NOT to clear the phase budget at ANY ratified corner)** — no full-hierarchy campaign exists; the 1.2–12 MHz timing budget is still a mechanical consequence of the DRAFT rate range, not independently derived ([DR-006](../../spec/decision-records/DR-006-sar-sequencer-bit-count-and-timing-budget.md)). (a) The CDAC array's own settling is now **PVT-complete** (full ratified OAT grid, 9 corners): binding corner `tt_27c_1.62v` at 13.2312 ns (bit 8/MSB, rise), 6.3× inside the DR-006-derived 83.333 ns phase budget; fastest corner `tt_27c_1.98v` at 10.3019 ns (8.1×); worst-to-best spread only 1.28× across the grid, and the tt/27 °C/1.8 V point reproduces the single-corner record's own 11.3861 ns exactly. All 9/9 corners clear the budget — not the bottleneck anywhere on the grid. A secondary, non-gating finding: the smallest-swing diagnostic row (bit 0, ~0.2% of VDD swing) failed to produce a 99%-settling crossing at 5/9 corners, root-caused (confirmed window-invariant out to 300 ns, not asserted without evidence) to a small, genuine, already-converged offset between the real simulated circuit and the analytic closed-form ideal — negligible against bit 8's own ~1.8 V swing but exceeding 1% of bit 0's own ~4 mV swing at some corners; bit 8 (the array's own true worst case, confirmed by its own tau_i(i) derivation) crossed cleanly at all 9/9 corners, so this does not affect the worst-case finding (see §7 Item 2 for the full root-cause trace). (b) The comparator's decision delay is now PVT-complete after issue #175 (DR-004 Amendment A) closed the reset-integrity defect: 9/9 corners' Vindiff = 0 mV negative control HELD, all 27/27 input-driven points decided, binding corner `tt_27c_1.62v` at +0.5 mV = 4.3575 ns, 19.1× inside the DR-006 budget (see §7 Item 2 and the now-resolved §7 Item 3). (c) The SAR sequencer's own CLK-to-phase-output logic delay is now **PVT-complete** (full ratified OAT grid, 9 corners), covering all 11 of its own ring-sequencer phase transitions at every corner (99 phase measurements): binding corner `ss_27c_1.80v` at 0.4237 ns (phase `b1`), 196.7× inside the DR-006 budget; fastest corner `ff_27c_1.80v` at 0.2480 ns (336.1×); worst-to-best spread only 1.71× across the grid. All 9/9 corners clear the budget by more than two orders of magnitude — the smallest of the four mechanisms measured, and not the bottleneck at any ratified corner. (d) **The sampling front end's own acquisition of a new, worst-case (rail-to-rail) differential input value is now ALSO PVT-complete (full ratified OAT grid, 9 corners) — and it is the only mechanism of the four found NOT to clear the budget, at EVERY ratified corner**: the single-corner (`tt`/27 °C/1.8 V) finding of a 23.43 mV residual (~13.3× the provisional differential LSB's half-step), traced to the bootstrap precharge PFET `Sa`'s imperfect off-state once `BOOST_x` is boosted above `VDD`, was not a corner-specific artifact — every one of the 9 ratified corners exceeds the half-LSB reference scale, with a binding corner of `tt_27c_1.62v` at 67.19 mV (~38.2× the half-LSB, 2.9× worse than the tt/27 °C/1.8 V baseline) and a best corner of `tt_27c_1.98v` at 9.00 mV (~5.1×). This is the opposite outcome from mechanisms (a)–(c); the front end's own acquisition, not the CDAC, comparator, or sequencer, is the likely bottleneck for an end-to-end sample-rate figure at the fast end of the DRAFT range, across the full ratified PVT grid, not just one corner — strengthening, not merely narrowing, the open item, and consistent with DR-006's own deferred "non-uniform phase allocation" alternative | [`sim/cdac-bit-trial-settling/records/20260905-220919-bbf06dd.md`](../../sim/cdac-bit-trial-settling/records/20260905-220919-bbf06dd.md) (CDAC mechanism, single-corner first pass); [`sim/cdac-bit-trial-settling/records/20260907-013225-5f176a6.md`](../../sim/cdac-bit-trial-settling/records/20260907-013225-5f176a6.md) (CDAC mechanism, full ratified PVT grid, PVT-complete — extends, does not formally supersede, the single-corner record); [`sim/comparator-decision/records/20260906-074451-7724af3.md`](../../sim/comparator-decision/records/20260906-074451-7724af3.md) (comparator mechanism, full grid, PVT-complete); [`sim/sequencer-logic-delay/records/20260906-192230-1b5c996.md`](../../sim/sequencer-logic-delay/records/20260906-192230-1b5c996.md) (sequencer mechanism, single-corner first pass); [`sim/sequencer-logic-delay/records/20260906-230516-0904419.md`](../../sim/sequencer-logic-delay/records/20260906-230516-0904419.md) (sequencer mechanism, full ratified PVT grid, PVT-complete — extends, does not formally supersede, the single-corner record); [`sim/sampling-acquisition-settling/records/20260906-202424-cb7e7aa.md`](../../sim/sampling-acquisition-settling/records/20260906-202424-cb7e7aa.md) (front-end acquisition mechanism, single-corner first pass); [`sim/sampling-acquisition-settling/records/20260906-211700-00d26af.md`](../../sim/sampling-acquisition-settling/records/20260906-211700-00d26af.md) (front-end acquisition mechanism, full ratified PVT grid, PVT-complete — extends, does not formally supersede, the single-corner record) |
| ENOB | > 7.5 bit (target), stretch > 8.0 (DR-007 candidate, was > 9.0/9.5) | DRAFT (target value, not ratified) | **Informational only — no ratified line exists to grade against.** Against `spec/target-spec.md`'s *current* DRAFT row (DR-007's candidate pair): 8.506 bit (mean-case CDAC mismatch) **meets** both the > 7.5 baseline and the > 8.0 stretch; 7.755 bit (worst-case CDAC mismatch) **meets the > 7.5 baseline but NOT the > 8.0 stretch**. Against the *original*, pre-DR-007 DRAFT row (> 9.0 / > 9.5) neither figure meets either bound. Re-composed this pass against DR-004 Amendment A's amended comparator-noise figure (0.8643 mV rms, down from 0.9591 — the same figure the comparator-noise row above already cites), moving the estimate from 8.491/7.749 to 8.506/7.755; the met/unmet outcome is unchanged in kind. **Correction**: this row previously headlined "DOES NOT MEET even the un-ratified DR-007 candidate", which overstated the shortfall — the source record's own scoring table marks the worst case as *meeting* the > 7.5 baseline, failing only the > 8.0 stretch (see §7 Item 4) | [`sim/enob-estimate/records/20260906-173830-6f04f59.md`](../../sim/enob-estimate/records/20260906-173830-6f04f59.md) (DR-007-candidate scoring, composed from the post-amendment comparator noise); [`sim/enob-estimate/records/20260906-082749-7724af3.md`](../../sim/enob-estimate/records/20260906-082749-7724af3.md) (identical figures scored against the original > 9.0 / > 9.5 row — the record `docs/characterization-report.md` pins) |
| INL / DNL | ≤ ±2.0 LSB (target, DR-007 candidate, was ≤ ±1 LSB) | DRAFT (target value, not ratified) | **Informational only**: empirical yield 0.825 (DNL) / 0.925 (INL) at N=40 against the *original* ≤ ±1 LSB target's 0.99 yield bar — `klt yield`'s own sample-size verdict on both is "insufficient" for a tight yield-fraction claim. A re-scoring against DR-007's wider ±2.0 LSB candidate **does** exist in-repo (a pure re-parse of the same 40 committed mismatch draws, no new ngspice run): its worst single draw is max\|DNL\| = 1.9716 LSB and max\|INL\| = 1.3147 LSB, i.e. every sampled draw falls inside the ±2.0 LSB candidate bound — but `klt yield` produced no report in that record's environment (a known, already-filed packaging gap, klayout-tools#1061), so there is **no machine-checked yield-fraction verdict against the candidate bound**, and N=40 is not sized for a tight yield-fraction claim in any case. Not graded met/unmet here: the candidate bound is not ratified | [`sim/cdac-array-transfer/records/20260828-005006-0c70212.md`](../../sim/cdac-array-transfer/records/20260828-005006-0c70212.md) (original ≤ ±1 LSB scoring — the record `docs/characterization-report.md` pins); [`sim/cdac-array-transfer/records/20260828-022618-f36913e.md`](../../sim/cdac-array-transfer/records/20260828-022618-f36913e.md) (DR-007-candidate re-scoring of the same draws) |
| Power | provisional, minimise at rate | DRAFT | **BLOCKED / UNMEASURED** — no full-block power campaign exists. One non-gating data point: `layout/sar-sequencer/`'s OpenROAD PnR static estimate (0.0155 mW) is for the digital sequencer sub-block only, not the full ADC, and is not a `sim/` evidence record | `layout/sar-sequencer/reports/20260825-124031-1a2f7c1/record.md` (non-gating, cited for completeness only) |
| Area | max, not yet specified in `spec/target-spec.md` | Not a spec row yet | **Informational only, not a spec-row verdict** — a composed top-level layout now exists (§3, §7): the full `gen_compose_0` bounding box is `(x0, y0) = (-20.2, -161.6)` µm to `(x1, y1) = (260.2, 223.9)` µm, i.e. 280.4 µm × 385.5 µm ≈ 0.108 mm². Unchanged by issue #180's comparator re-draw (re-verified against the latest report below). This is a raw `klt gen-compose` bounding-box readout, not an LVS-clean, sign-off-grade area figure — the composition's `klt lvs` verdict is still a mismatch (see §3, §7 Item 1), and no spec row exists yet to grade this number against | [`layout/sar-adc-top/reports/20260906-101939-1250ff4/compose.json`](../../layout/sar-adc-top/reports/20260906-101939-1250ff4/compose.json) |
| Digital sequencer/output register — physical implementation | transistor-level netlist + place-and-route layout | — | **MET** — netlist exists (`design/sar_sequencer.sch`); place-and-route layout exists and is DRC-clean and LVS-clean (#102) | `layout/sar-sequencer/README.md` |
| **Post-layout PVT simulation, full ADC** | brief sign-off bar | — | **UNMET / BLOCKED** — a top-level layout now exists (PR #174, re-verified against the amended comparator geometry by PR #188) but no extraction-based re-sim of the assembled `sar_adc_top` has been run against any PVT point; blocked on #103 (`loom:blocked`, now for the LVS-match reason below, not a missing assembly), under epic #25 | [`layout/sar-adc-top/reports/20260906-101939-1250ff4/record.md`](../../layout/sar-adc-top/reports/20260906-101939-1250ff4/record.md) |
| **DRC/LVS-clean GDS, full ADC, in-repo** | brief sign-off bar | — | **PARTIAL — DRC MET, LVS UNMET / BLOCKED**. `klt drc`: clean, 0 violations, on the composed top-level GDS, re-confirmed after issue #180's comparator re-draw. `klt lvs`: mismatch (869/869 devices, matched 794; 23 pins promoted vs. 19 expected — the device/matched-count shift from the prior record's 867/867/812 tracks the comparator's own +2-device topology change, not a new defect) — root-caused as an upstream `klt extract` declared-pin-promotion gap, not a routing defect (net-by-net connectivity independently verified correct via unfiltered extraction); filed at [klayout-tools#1513](https://github.com/2AMLogic/klayout-tools/issues/1513), which **closed 2026-09-06** fixed by klayout-tools#1515 (`--pin-source-cells`) but is not yet consumable — PyPI still tops out at 0.4.0, the version already pinned in `layout/requirements.txt`. #103 remains `loom:blocked`, now pending a `klayout-tools` release rather than an open upstream fix | [`layout/sar-adc-top/reports/20260906-101939-1250ff4/record.md`](../../layout/sar-adc-top/reports/20260906-101939-1250ff4/record.md), [`layout/sar-adc-top/README.md`](../../layout/sar-adc-top/README.md) |

### Reproducing this table

Every citation above is re-runnable from a clean clone with the PDK
installed, per [`docs/environment-setup.md`](../../docs/environment-setup.md).
`python3 sim/run_corners.py --list` enumerates the corner-run experiments
cited; `python3 sim/monte_carlo.py --list` enumerates the Monte Carlo
campaigns (ENOB/INL/DNL rows). `python3 sim/report/generate.py --check`
verifies `docs/characterization-report.md` — the machine-checked source this
table restates — is fresh against current `sim/`/`layout/` evidence; it was
run as part of authoring this document and passed
(`OK: ... is fresh and up to date (11 rows)`).

---

## 5. Test-plan outline (packaged part, if fabricated)

This section is written against this design's *current* port list (§2) and
would need revision once §7's open items (differential-reference budget,
top-level layout) close.

1. **Bring-up / DC sanity.** Apply `VDD` = 1.8 V, `VREFP`/`VREFN` (0/1.8 V or
   the harness-supplied equivalent), `VCM` = 0.9 V. Confirm quiescent supply
   current with no input applied, `CLK` free-running, `RST_B` deasserted.
2. **Functional / decode check.** Drive `VINP`/`VINN` to a small set of known
   DC levels spanning 0–`V_REF`. Capture `DOUT9..0` on each `BUSY`
   deassertion and confirm monotonically increasing codes with increasing
   differential input.
3. **Static linearity (INL/DNL).** A code-density (histogram) test against
   the target row's eventual ratified bound (currently DRAFT, DR-007
   candidate ≤ ±2.0 LSB).
4. **Dynamic performance (ENOB).** Drive a low-distortion sine near Nyquist,
   coherent with `CLK`, and FFT-derive SNDR/ENOB from a captured `DOUT*`
   record. Compare against whatever value DR-007 (or a superseding record)
   eventually ratifies — no ratified ENOB target exists today.
5. **Sample-rate / clock-margin sweep.** Sweep `CLK` frequency across the
   provisional 1.2–12 MHz range (§4) and record where functional decode
   first degrades — this is the silicon measurement that would finally
   produce the settling-time evidence `spec/target-spec.md`'s sample-rate row
   is still waiting on.
6. **Power.** Measure `VDD` supply current at a representative sample rate.

No test-equipment list or bench schedule is proposed here — that is
downstream of a packaged part existing, which is itself downstream of §3/§7's
open layout work.

---

## 6. Input interface note

- **Differential only.** This design has no single-ended mode; the unused
  gf180-sar-adc-style `MODE` pin does not exist here (a design divergence,
  not an oversight — this repo's CDAC/sampling-frontend topology was
  designed differential-only from the start,
  [DR-005](../../spec/decision-records/DR-005-cdac-array-design.md)).
- **Full-scale range**: 0–`V_REF` = 0–1.8 V single-ended per side; the
  differential LSB is `2·V_REF/2^N = 3.5156 mV`, i.e. a `2·V_REF = 3.6 V`
  differential full-scale span. This stays entirely within the 1.8 V core
  rail per §2.1 — it does not, and is not proposed to, extend to any
  higher-voltage rail.
- **Which pads carry the input and reference**: `VINP`/`VINN` (dedicated
  pads) carry the analog input; `VREFP`/`VREFN` set the full-scale
  reference (differential — see §2.2's open item on whether the harness's
  bandgap reference can supply this directly); `VCM` sets the common-mode
  operating point.

---

## 7. Open items before this design would be ready for the brief's sign-off bar

Stated in order of size, and each pointing at the issue that already tracks
it — this document does not invent new tracking for work this repo's issue
tracker already owns.

1. **Top-level layout does not exist (the largest gap).** No assembled,
   DRC/LVS-clean GDS for `sar_adc_top` exists in this repo. Tracked as
   #103 (top-level routing/assembly), which lists #99, #100, #101, and #102
   as its four sub-block dependencies — **all four are now closed.** #99
   (sampling front-end layout) closed via PR #152 (merged
   2026-09-05T23:22:50Z): DRC-clean and LVS-clean, 24/24 devices, 17/17
   nets, 12/12 pins matched, with three negative controls confirming the
   checker catches a body-tie, device-parameter, and capacitor-top-plate-net
   corruption respectively (record:
   [`layout/sampling-frontend/reports/20260905-204934-f012255/record.md`](../../layout/sampling-frontend/reports/20260905-204934-f012255/record.md)).
   #101 (comparator layout — **done**, DRC/LVS-clean) and #102 (SAR
   sequencer layout — **done**, DRC-clean and LVS-clean as of #141) are
   closed and settled. #100 (CDAC array layout) is closed and its layout is
   DRC-clean. Its original committed LVS "match" verdict was found,
   2026-09-05, not to reproduce against its own committed artefacts —
   byte-identical GDS/reference-SPICE inputs, the same toolchain versions
   its own provenance block stamps, reported mismatch (48 errors). That
   regression, tracked as #148, has since been root-caused (`klt lvs`'s
   `options.combine_devices` unreliably re-summing hundreds of
   identical-valued parallel unit capacitors into one combined device) and
   fixed (the array's 1024 drawn unit capacitors now compare 1:1 against
   the reference, with no folding needed); the replacement record's LVS
   match reproduces on repeat runs, so #100 is once again reported
   LVS-clean here. With all four original sub-block dependencies closed,
   #103 was promoted (`loom:issue`, 2026-09-05T23:47:57Z) and claimed by a
   Builder (`loom:building`, lease acquired 2026-09-05T23:52:56Z), which
   shipped a fifth composition-level block the assembly needs directly —
   `layout/seln-inverters/` (nine `SELn<i> = NOT(DOUT<i>)` glue inverters
   `design/sar_adc_top.sch` adds at the integration level; DRC-clean and
   LVS-clean, PR #166) — plus a floorplan/routing investigation that probed
   every sub-block's own committed GDS geometry directly (not just each
   block's published pin-position table). That investigation found a real
   sub-block-layout completeness gap, not a floorplan/routing question this
   issue can resolve on its own: `cdac_array`'s (#100) `VDD` pin is a bare
   `nwell` region with zero drawn tap/contact, and its `SELp<i>`/`SELn<i>`
   pins are bare-poly straps with no safe field-poly landing area — neither
   can be physically contacted by a top-level composition without risking a
   silent electrical defect (full detail in
   `layout/sar-adc-top/README.md`). That gap was tracked as **#165**
   (`cdac_array: VDD (nwell) and SELp/SELn (poly gate) pins have no
   externally-contactable landing geometry`) and has since **closed**: PR
   #170 (merged 2026-09-06T02:19:15Z) added a real n-well tap (contacted up
   through `licon1`/`mcon` to a met1 landing pad, mirroring
   `layout/comparator/`'s own `tap_shapes()` recipe) for `VDD`, and a poly
   landing pad for each of the 18 `SELp<i>`/`SELn<i>` gate-tie straps,
   placed inside the switch template's own diffusion-free clearance so the
   original channel width — and every switch transistor's extracted
   `L`/`W`/`AS`/`AD`/`PS`/`PD` — is unchanged. `cdac_array`'s own
   DRC/LVS/common-centroid checks were re-run clean against the new
   geometry. Every top-level pin — the 18 SEL nets and `VDD` included — has
   now been independently verified to have real, externally-reachable
   conductor, so the composition/routing plan was ready to execute — and it
   has since been executed. **PR #174 (merged 2026-09-06T04:46:23Z)** placed
   all five sub-block layouts via `klt gen-compose` and hand-routed every net
   `design/sar_adc_top.sch` calls for via `klt draw`, producing a committed
   `sar_adc_top.gds`
   ([`layout/sar-adc-top/reports/20260906-043420-662a84d/`](../../layout/sar-adc-top/reports/20260906-043420-662a84d/)):
   `klt drc` is clean (0 violations), and connectivity is verified net-by-net
   correct via an unfiltered `klt extract` against the intended interconnect.
   `klt lvs` itself still reports a mismatch (867/867 devices, matched 812;
   23 pins promoted vs. the design's own 19) — not from a routing defect, but
   because no `klt extract` declared-pin mechanism reliably promotes exactly
   this design's own top-level interface once composed from five
   independently-labeled sub-blocks with no governing top-level DEF (two of
   the five are placed-and-routed standard-cell macros whose own internal,
   generic net labels collide with this design's ports once flattened).
   Filed generically at
   [klayout-tools#1513](https://github.com/2AMLogic/klayout-tools/issues/1513)
   per this repo's friction protocol — full trace in
   `layout/sar-adc-top/README.md`'s "LVS pin declaration blocker" section.
   **Update this pass**: klayout-tools#1513 **closed** 2026-09-06T06:45:36Z,
   fixed by klayout-tools#1515 (merged the same minute), which adds
   `--pin-source-cells` — a `klt extract`/`klt lvs` mechanism that resolves a
   composed assembly's top-level ports by physical label position instead of
   string-matching internal net labels, exactly the mismatch this issue hit.
   **Not yet actionable**: PyPI's `klayout-tools` package still tops out at
   0.4.0 (checked 2026-09-06 via `pip index versions klayout-tools` and
   `pypi.org/pypi/klayout-tools/json`) — the same version already pinned in
   `layout/requirements.txt` — so the fix is merged to `main` upstream but
   not yet in a cuttable release; bumping the pin today would not pick it up.
   **#103 itself remains open, `loom:blocked`, for a narrower reason than
   before** (the Curator's 2026-09-06 re-checks tracked this in two steps:
   first confirming the block reason moved from "no assembly exists" to
   "assembly exists, DRC-clean and connectivity-verified, but an automated
   LVS match is blocked on klayout-tools#1513," then — once #1513 itself
   closed — confirming the block is "not yet actionable" rather than
   resolved, since the fix has no release to consume yet) — re-check once a
   `klayout-tools` release `> 0.4.0` publishes, then bump the pin and re-run
   `layout/sar-adc-top/`'s `klt lvs` with `--pin-source-cells` naming the two
   placed-and-routed macro sub-cells (`sar_sequencer`, `seln_inverters`) to
   confirm it actually clears the mismatch. All four original sub-block
   issues, #165, #103, and PR #174 roll up under epic #25 / tracker #23.
   **#103 is still the blocker for the brief's "post-layout PVT simulation
   and DRC/LVS-clean GDS in-repo" acceptance criterion** — DRC-clean is now
   met, LVS-clean is not, and no post-layout PVT re-simulation of the
   assembled top level has been run; that criterion is marked PARTIAL/UNMET
   in §4, not fabricated or optimistically assumed.

   **Update this pass (2026-09-06, following issue #180's comparator
   re-draw)**: `layout/sar-adc-top/` was re-verified against the amended
   comparator geometry (11-device topology, DR-004 Amendment A) in the same
   PR (#188) that closed #180, minting a fresh record that supersedes
   `reports/20260906-043420-662a84d/`:
   [`layout/sar-adc-top/reports/20260906-101939-1250ff4/record.md`](../../layout/sar-adc-top/reports/20260906-101939-1250ff4/record.md)
   (`reports/LATEST` now points here). Verdicts are unchanged in kind —
   `klt drc` clean (0 violations), connectivity independently verified
   net-by-net correct (same one net-naming artifact on `CLK`, still not a
   real short/open), `klt lvs` still a mismatch for the same upstream
   pin-declaration reason (devices layout=869/reference=869, matched=794;
   23 pins promoted vs. 19 expected — the small device/matched-count shift
   from the prior record's 867/867/812 is the comparator's own +2-device
   topology change (9 → 11) propagating through the composed count, not a
   new or different defect). #103 itself remains open/`loom:blocked`, still
   waiting on a `klayout-tools` release newer than the PyPI-pinned 0.4.0 to
   consume klayout-tools#1515's `--pin-source-cells` fix — unchanged by this
   update.

   **Re-verified 2026-09-06 (this pass, live, no new layout work)**: #103 is
   still open and still carries `loom:blocked`, and PyPI's `klayout-tools`
   still tops out at **0.4.0** — the version `layout/requirements.txt`
   already pins — so klayout-tools#1515's fix remains merged-but-unreleased
   and the LVS-match blocker is unchanged. No new top-level layout record
   was produced this pass, and none is claimed: §4's "post-layout PVT
   simulation, full ADC" row stays **UNMET / BLOCKED** and its "DRC/LVS-clean
   GDS, full ADC" row stays **PARTIAL (DRC met, LVS unmet)**, citing the same
   `20260906-101939-1250ff4` record as before. The brief's sign-off bar
   (acceptance criterion 3) is therefore still not met.
2. **Sample rate is not re-derived (narrowed this pass, not closed).**
   `spec/target-spec.md`'s 100 kS/s–1 MS/s row remains DRAFT. A first-pass,
   single-corner (`tt`/27 °C/1.8 V) settling-time budget for ONE mechanism —
   the CDAC array's own bottom-plate-switch/top-plate-node RC network
   (`design/cdac/cdac_array.sch`) — now exists
   ([`sim/cdac-bit-trial-settling/records/20260905-220919-bbf06dd.md`](../../sim/cdac-bit-trial-settling/records/20260905-220919-bbf06dd.md)),
   made possible by DR-006's own gating condition finally clearing (that
   record predates `design/cdac/cdac_array.sch` and `design/comparator.sch`
   existing; both now do). It isolates and quantifies a genuine, testable
   property of this array's own component values: every one of its 9
   per-side bit switches is the SAME fixed transistor size regardless of
   bit weight, while the capacitor each one drives scales binarily
   (1..256 unit caps) — so the top-plate settling time constant is **not**
   monotonic in bit position, and for this design's own weights it peaks
   at bit 8 (the MSB of the 9-bit sub-array, closest to half the array's
   total capacitance), not at the array's largest bit by a naive
   "biggest cap is always slowest" intuition. Measured worst case: 11.39 ns
   to settle to 99% at bit 8, a 7.3x margin inside the DR-006-derived
   worst-case (12 MHz) 83.33 ns bit-trial phase budget — ruling out the
   CDAC array's own switch-settling as the sample-rate bottleneck at this
   corner. This does **not** close the open item: the comparator's own
   decision (propagation) delay (`design/comparator.sch` exists, but no
   timing campaign has been run against it), sequencer logic delay, and
   full PVT coverage of even this one mechanism (switch `R_on` varies
   materially with process/temperature) were, at the time this record was
   written, all still unmeasured, and any of those could dominate where the
   CDAC array itself does not. This
   still gates the timing-budget row (DR-006) from becoming anything more
   than a mechanical consequence of an unratified number, but the sample-
   rate row is no longer entirely unmeasured — one candidate bottleneck
   has been checked and cleared.

   **The comparator's own decision delay was taken to the full ratified PVT
   grid this pass, and the pass is now a PVT-complete result** after issue
   #175 (DR-004 Amendment A) closed the reset-integrity defect Item 3 below
   originally described
   ([`sim/comparator-decision/records/20260906-074451-7724af3.md`](../../sim/comparator-decision/records/20260906-074451-7724af3.md),
   written by `sim/comparator-decision/run.py regen-corners`, superseding
   [`20260906-052758-662a84d.md`](../../sim/comparator-decision/records/20260906-052758-662a84d.md)).
   The campaign carries a Vindiff = 0 mV **reset-integrity negative
   control** at every corner point: with the inputs shorted to the common
   mode there is no correct decision to make, so the latch must stay
   balanced until the evaluate edge. That control now **HOLDS at all 9
   ratified corner points** (pre-edge `v(OUTP) - v(OUTN) = +0.0000 V` and
   reset-phase static supply current `= 0.00 µA` at every corner), and all
   27/27 input-driven decision points resolved within the 15.0 ns evaluate
   window. Binding corner `tt_27c_1.62v` at Vindiff = +0.5 mV: decision delay
   `4.3575 ns`, `19.1×` inside the DR-006-derived 83.333 ns worst-case
   bit-trial phase budget — headroom against a DRAFT, not-yet-ratified
   figure, not a pass against a ratified spec line. Item 3 below is now
   resolved rather than open; the comparator half of the bit-trial timing
   budget is no longer blocked by a design finding, though at the time this
   record was written the sequencer's logic delay and the sampling front
   end's acquisition remained wholly unmeasured, so this was still not an
   end-to-end sample-rate number.

   **The sequencer's own CLK-to-phase-output logic delay was measured this
   pass, single-corner (`tt`/27 °C/1.8 V) first-pass** — a third mechanism
   now checked, same "first-pass, single-corner budget" precedent
   `sim/vcm-drive-budget/` and `sim/cdac-bit-trial-settling/` already
   established
   ([`sim/sequencer-logic-delay/records/20260906-192230-1b5c996.md`](../../sim/sequencer-logic-delay/records/20260906-192230-1b5c996.md),
   written by the new `sim/sequencer-logic-delay/run_sequencer_logic_delay.py`).
   It isolates a genuinely different mechanism than either of the two above:
   `design/sar_sequencer.sch`'s own (N+2)-stage, N=10, one-hot walking-ring
   sequencer (built entirely from `sky130_fd_sc_hd` standard cells, per that
   schematic's own header comment) advances one phase per CLK rising edge;
   this record measures, for all 11 of its CLK-edge-driven phase transitions
   (`ph_b9`..`ph_b0`, `ph_eoc`), the propagation delay from the 50% crossing
   of the triggering CLK edge to the 50% crossing of that phase's own output
   node — the sequencer's own real gate delay, not an idealized digital
   abstraction, since the DUT is netlisted from real `nfet_01v8`/`pfet_01v8`
   transistor-level standard-cell models (the same DUT
   `sim/sar-sequencer-behavioral/` already proves functionally correct;
   `COMP_OUT` is tied fixed here because the ring's own phase outputs do not
   depend on it — only the separate `DOUT*` capture registers do). Measured
   worst case: 0.3123 ns at phase `b1`, a 266.9× margin inside the
   DR-006-derived worst-case (12 MHz) 83.333 ns bit-trial phase budget — by
   a wide margin the smallest of the three mechanisms checked so far
   (CDAC settling 11.39 ns, comparator decision 4.3575 ns, sequencer logic
   delay 0.3123 ns), consistent with a handful of standard-cell gate delays
   being intrinsically much faster than either an RC-settling or a
   regenerative-latch mechanism. At the time this record was written, this
   did **not** close the open item: the sampling front end's own
   acquisition-window timing remained wholly unmeasured (the fourth and
   last named mechanism), and none of the three mechanisms checked so far
   had been taken to the full ratified PVT grid except the comparator's —
   real standard-cell gate delay varies materially with process/
   temperature/supply, so this record's single-point margin, while large,
   is not yet a PVT-complete result the way the comparator's own
   decision-delay campaign now is.

   **The sampling front end's own acquisition-window timing was measured
   this pass, single-corner (`tt`/27 °C/1.8 V) first-pass — the fourth and
   last named mechanism, and the first one found NOT to clear the DR-006
   phase budget**
   ([`sim/sampling-acquisition-settling/records/20260906-202424-cb7e7aa.md`](../../sim/sampling-acquisition-settling/records/20260906-202424-cb7e7aa.md),
   written by the new
   `sim/sampling-acquisition-settling/run_acquisition_settling.py`). The
   experiment drives `design/sampling_frontend.sch`'s own bootstrapped
   sampling switch through two consecutive SAMPLE assertions: the first
   settles `TOP_P`/`TOP_N` to one rail-adjacent extreme, the input then
   steps to the opposite rail-adjacent extreme while `Msw` is off (the
   worst case for a near-Nyquist input changing by the full differential
   span between samples), and the second SAMPLE assertion is the one
   measured — the maximum simultaneous full-scale step this design's input
   range can present. Fast early settling (50%/90% of the way to the new
   value) is sub-ns on both nodes, consistent with the CDAC array's own
   fast switch time constant for a comparable total capacitance. But a
   slow secondary settling tail — traced during debugging (not asserted
   without evidence) to the bootstrap precharge PFET `Sa` sitting in a
   reverse-`Vds` orientation once `BOOST_x` is driven above `VDD` by the
   boost itself, letting its own imperfect off-state in that orientation
   allow `BOOST_x` to droop measurably over tens of ns, gradually reducing
   `Msw`'s gate overdrive — leaves a residual 23.4300 mV (single-ended,
   worst node, `TOP_P`) still uncorrected exactly 83.333 ns (the DR-006
   worst-case 12 MHz phase period) after the acquiring edge, ~13.3× the
   provisional differential LSB's half-step. **This is the opposite outcome
   from all three other mechanisms**, each of which cleared the same
   budget with a double-digit-or-larger margin: the sampling front end's
   own acquisition, not the CDAC array, comparator, or sequencer, is the
   likely bottleneck for an end-to-end sample-rate figure at the fast
   (12 MHz / ~1 MS/s) end of the DRAFT range, at this corner. This does
   **not** mean the design is broken or that any spec row is violated —
   `spec/target-spec.md`'s sample-rate row is entirely DRAFT, and DR-006's
   own uniform-one-phase-per-CLK-period allocation was always stated as a
   placeholder pending exactly this kind of settling-time evidence (see
   DR-006's "Alternatives considered": a non-uniform phase allocation, e.g.
   a longer SAMPLE phase, was explicitly deferred for lack of this data).
   What this record establishes is a concrete, first, real data point
   suggesting that eventual non-uniform allocation may be needed at the
   fast end of the DRAFT sample-rate range — narrowing, not closing, the
   open item, and surfacing a genuine design risk rather than a reassuring
   margin, honestly reported either way. This record's own methodology
   note is worth flagging generically for anyone reusing the same ngspice
   idiom: an earlier draft's `TRIG(AT=)/TARG(...CROSS=1)` measure for a
   tight (99%) settling fraction returned an implausible result traced to
   two distinct SPICE semantics traps — `CROSS=n` counts crossings from
   the start of the whole simulated waveform, not from the TRIG point
   (fixed with `TARG`'s own `TD=` qualifier), and a threshold close to the
   final value can pick up a *later* transient's own artifact (SAMPLE's
   own turn-off kick, the same mechanism issue #61 already documented)
   instead of genuine convergence — both documented in the script's own
   module docstring for the next experiment that reaches for this idiom.

   **Update this pass (2026-09-06): the front-end acquisition finding was
   taken to the full ratified PVT grid, and it is now the second mechanism
   (after the comparator's own decision delay) to reach PVT-complete
   coverage** — and the first one found NOT to clear the DR-006 budget
   anywhere on that grid
   ([`sim/sampling-acquisition-settling/records/20260906-211700-00d26af.md`](../../sim/sampling-acquisition-settling/records/20260906-211700-00d26af.md),
   the same OAT grid (9 one-at-a-time points: process
   `{ff, fs, sf, ss, tt}` × temperature `{-40, 27, 125} °C` × supply
   `{1.62, 1.8, 1.98} V`) `sim/comparator-decision/`'s own regen-corners
   campaign sweeps, added to `sim/sampling-acquisition-settling/
   run_acquisition_settling.py` as a new `--corners` mode alongside the
   existing single-corner default). **Every one of the 9 ratified corners
   exceeds the provisional differential LSB's half-step** at the DR-006
   worst-case (12 MHz) phase budget: binding corner `tt_27c_1.62v`
   (`TOP_P` residual 67.19 mV, ~38.2× the half-LSB — 2.9× worse than the
   tt/27 °C/1.8 V baseline point's own 23.43 mV/~13.3×), best corner
   `tt_27c_1.98v` (9.00 mV, ~5.1×). This confirms the single-corner finding
   was not a corner-specific artifact of the `tt`/27 °C/1.8 V point — the
   mechanism (the bootstrap precharge PFET `Sa`'s imperfect off-state once
   `BOOST_x` is boosted above `VDD`) does not clear the phase budget
   anywhere on this design's own ratified PVT grid at its current sizing.
   This still does not violate any ratified spec row — the sample-rate row
   remains entirely DRAFT — but it raises the weight of this finding from
   "one corner, narrows the open item" to "every ratified corner, same
   conclusion," strengthening (not merely narrowing) the case for DR-006's
   own deferred non-uniform-phase-allocation alternative. This campaign
   still measures ONLY this one mechanism in isolation — it does not
   combine with the other three named mechanisms into an end-to-end
   sample-rate figure, and at the time that record was written the
   CDAC-settling and sequencer-logic-delay mechanisms both remained
   single-corner only.

   **Update this pass (2026-09-06): the sequencer's own logic delay was
   taken to the same full ratified PVT grid, and it is now the third
   mechanism to reach PVT-complete coverage** — the second one (after the
   comparator's own decision delay) to clear the DR-006 budget at every
   ratified corner
   ([`sim/sequencer-logic-delay/records/20260906-230516-0904419.md`](../../sim/sequencer-logic-delay/records/20260906-230516-0904419.md),
   the same 9-point OAT grid (process `{ff, fs, sf, ss, tt}` × temperature
   `{-40, 27, 125} °C` × supply `{1.62, 1.8, 1.98} V`) the two campaigns
   above sweep, added to
   `sim/sequencer-logic-delay/run_sequencer_logic_delay.py` as a new
   `--corners` mode alongside the existing single-corner default). All 11
   ring phases were measured at all 9 points (99 phase measurements, all
   producing a valid crossing). **All 9/9 corners clear the
   DR-006-derived worst-case (12 MHz) 83.333 ns phase budget by more than
   two orders of magnitude**: binding (slowest) corner `ss_27c_1.80v`,
   phase `b1` at 0.4237 ns (196.7× inside the budget); fastest corner
   `ff_27c_1.80v` at 0.2480 ns (336.1×); worst-to-best spread across the
   whole grid only 1.71×. The `tt`/27 °C/1.8 V point reproduces the
   single-corner record's own 0.3123 ns exactly, so the two records are
   consistent, not competing. Both axes behave as standard-cell gate delay
   should — slow process and low supply are the two slow directions
   (`ss` 0.4237 ns, `tt_27c_1.62v` 0.4147 ns), fast process and high
   supply the two fast ones — and temperature is nearly inert here
   (0.3211 ns at −40 °C vs. 0.3038 ns at 125 °C, i.e. mildly *inverted*
   temperature dependence, consistent with these cells operating in the
   low-supply-sensitivity regime rather than a mobility-dominated one).
   This confirms the single-corner margin was not a corner-specific
   artifact: the sequencer's own logic delay is not the sample-rate
   bottleneck anywhere on this design's ratified PVT grid. Headroom
   against a DRAFT, not-yet-ratified figure, not a pass against a ratified
   spec line. This campaign still measures ONLY this one mechanism in
   isolation — it does not combine with the other three into an end-to-end
   sample-rate figure, and **the CDAC-settling mechanism now remains the
   only one of the four still single-corner only**.

   **Update this pass (2026-09-07): the CDAC array's own switch-settling
   was taken to the same full ratified PVT grid, and it is now the FOURTH
   and last mechanism to reach PVT-complete coverage** — closing this open
   item's own "still single-corner only" gap entirely
   ([`sim/cdac-bit-trial-settling/records/20260907-013225-5f176a6.md`](../../sim/cdac-bit-trial-settling/records/20260907-013225-5f176a6.md),
   the same 9-point OAT grid the three campaigns above sweep, added to
   `sim/cdac-bit-trial-settling/run_bit_trial_settling.py` as a new
   `--corners` mode alongside the existing single-corner default). A
   pre-flight probe found the single-corner script's own 20 ns transient
   window too tight to reuse unchanged across the full grid (a slow-corner
   candidate reached 16.09 ns, leaving only ~20% headroom to the window's
   own 20 ns ceiling), so `--corners` widens the window to 40 ns without
   touching the single-corner default's own already-cited window. **All
   9/9 corners clear the DR-006-derived
   worst-case (12 MHz) 83.333 ns phase budget**: binding (slowest) corner
   `tt_27c_1.62v`, bit 8 (rise) at 13.2312 ns (6.3× inside the budget);
   fastest corner `tt_27c_1.98v` at 10.3019 ns (8.1×); worst-to-best spread
   across the whole grid only 1.28×, and the `tt`/27 °C/1.8 V point
   reproduces the single-corner record's own 11.3861 ns exactly. This
   confirms the single-corner margin was not a corner-specific artifact:
   the CDAC array's own switch-settling is not the sample-rate bottleneck
   anywhere on this design's ratified PVT grid. **A secondary, honestly
   reported finding, not asserted without evidence**: the smallest-swing
   diagnostic row (bit 0, whose ideal top-plate excursion is only ~0.2% of
   VDD) failed to produce a 99%-settling crossing at 5 of the 9 corners.
   A follow-up check — re-running one such case (`tt_27c_1.98v`, bit
   0/fall) with the transient window widened to 100 ns and 300 ns —
   reproduced the IDENTICAL simulated top-plate voltage at every window
   length, confirming a genuine, already-converged final value rather than
   slow settling a longer window would resolve. That converged value
   differs from the analytic closed-form ideal by a small, roughly
   corner-independent absolute offset (order 0.1–0.3 mV, plausibly
   real-device charge-injection/subthreshold-leakage second-order effects
   the ideal closed-form does not model) which is negligible against bit
   8's own ~1.8 V swing but exceeds 1% of bit 0's own ~4 mV swing at some
   corners. This does **not** affect the headline finding: the array's own
   tau_i(i) = R_on × C_i × (1 − C_i/C_total) shape (this script's own
   module docstring) predicts bit 8 (the MSB) is always the true worst
   case, and bit 8 crossed cleanly at all 9/9 corners — a bit-0 crossing
   miss is a diagnostic-row curiosity at the opposite (fastest,
   smallest-signal) end of the bit range, not a gap in the worst-case
   number this finding rests on. This campaign still measures ONLY this
   one mechanism in isolation — it does not combine with the other three
   into an end-to-end sample-rate figure.

   With all four mechanisms now individually quantified AND all four now
   PVT-complete, `docs/characterization-report.md`'s
   sample-rate row and `sim/report/manifest.py`'s citations for it have
   been updated to cite all seven records (four mechanisms, three of them
   with both a single-corner and a full-grid record) and to state the
   front-end finding honestly, alongside the other three mechanisms'
   comfortable margins.
3. **The comparator's reset phase was not PVT-robust — FIXED this pass by
   issue #175 (DR-004 Amendment A), kept here as history rather than
   silently deleted.** The reset-integrity control described in Item 2
   isolated a real property of the pre-amendment `design/comparator.sch`:
   the cross-coupled NMOS latch pair (`XM_LATN_P`/`XM_LATN_N`) had both
   sources tied directly to `GND`, so it conducted throughout the CLK = 0
   reset phase, in opposition to the reset PMOS pair
   (`XM_RST_P`/`XM_RST_N`). Two independent measurements in the
   pre-amendment record confirmed the mechanism rather than assuming it:
   the reset-phase output level was **not** the rail (a winning precharge
   would sit at `v(OUTP) = v(OUTN) = V_DD`), and the reset phase drew
   **static supply current**, because a DC path `VDD → reset PMOS → output
   node → latch NMOS → GND` was open the whole time. That balanced level
   was an *unstable* equilibrium — both latch NMOS devices sat well above
   threshold, so the cross-coupled loop gain exceeded unity and any
   asymmetry (corner skew, temperature, or the input pair's own
   subthreshold conduction) was amplified to the rails inside the reset
   window. **Consequence** (as it stood before the fix): at those corners
   the comparator entered each bit trial already committed to an output, so
   the bit it produced was not determined by the charge on the CDAC top
   plate. This had not surfaced before because no ADC-level transient in
   this repository has ever exercised the real comparator inside the full
   hierarchy — the sequencer campaign is behavioural, and the ENOB estimate
   composes a comparator *noise* term rather than simulating the latch (both
   still true post-fix — this class of defect could recur undetected by
   those two campaigns alone). **Fix, landed this pass**: `design/
   comparator.sch` now returns the latch NMOS pair's sources to the input
   pair's own precharged drain nodes (`DIP`/`DIN`, new CLK-gated PMOS
   precharge devices, 9 devices → 11) instead of hard-wiring them to `GND`,
   per
   [DR-004 Amendment A](../../spec/decision-records/DR-004-comparator-topology-and-noise-budget.md#amendment-a-issue-175-2026-09-06-reset-integrity-topology-fix).
   The testbench fragment was re-netlisted, and every committed
   comparator-decision record (`regen`, `regen-corners`, `offset`, `noise`,
   `noise-corners`) was re-run against the amended device set, each minting
   a new record that supersedes its pre-amendment predecessor (Item 2's
   citation above is the `regen-corners` result: 9/9 reset-integrity
   controls now HELD). `layout/comparator/`'s LVS match, invalidated by that
   device-level change, is **fixed as of this pass** — issue #180 closed via
   PR #188 (merged 2026-09-06T12:27:03Z): the sub-block was re-drawn against
   the amended 11-device topology (a sixth `klt gen` block, `rstd`, for the
   new `M_RST_DIP`/`M_RST_DIN` CLK-gated PMOS precharge devices, plus
   `DIP`/`DIN` added to the floorplan/routing), and its own LVS **match** is
   re-established: 11/11 devices, 10/10 nets, 7/7 pins matched, both
   negative controls (device-parameter and topology corruption) still report
   mismatch as intended
   ([`layout/comparator/reports/20260906-113406-2d66a6a/record.md`](../../layout/comparator/reports/20260906-113406-2d66a6a/record.md)).
   `layout/sar-adc-top/` (which composes this sub-block) was re-verified
   against the updated geometry in the same PR — see the updated Item 1
   above for that record's citation and figures. A PEX re-run over the new
   geometry initially found the extracted-side gain sign-flipped vs. the
   schematic side for this topology, most likely a pick-off-timing
   calibration artifact from the pre-#175 topology; flagged as a distinct,
   non-gating finding and tracked as issue #187 — **since closed, this
   pass**, via PR #190 (merged 2026-09-06T15:29:27Z).

   **Update this pass (2026-09-06, issue #187 closed via PR #190)**: the
   root cause was confirmed exactly as hypothesized — the fixed pick-off
   instant (`PICKOFF_AT_NS=5.4ns`) was calibrated against the pre-#175
   topology's regeneration timing and was genuinely too early for the
   amended topology's *extracted* (parasitic-loaded) leg, whose real R/C on
   `DIP`/`DIN` and `OUTP`/`OUTN` measurably delays its regeneration onset
   relative to the ideal schematic leg
   ([`layout/comparator/reports/20260906-144802-eace0b6/record.md`](../../layout/comparator/reports/20260906-144802-eace0b6/record.md)).
   A corrected pick-off instant (`PICKOFF_NS=1.2ns` / `PICKOFF_AT_NS=6.3ns`,
   spot-checked at `ss/-40C` and `ff/125C`) was re-derived and applied to
   `testbench.spice`/`pex_request.json`/`run_pex.py`, and a fresh
   `run_pex.py --record` run reproduces AC3/AC4 with both legs now
   correctly signed and positive (schematic +22.7683 V/V, extracted
   +11.9740 V/V); the re-derived input-referred parasitic-driven offset
   estimate (−0.94872 mV) remains over an order of magnitude smaller than
   the device-mismatch-only offset distribution's mean/stdev, so the
   original "routing-driven offset is noise against device mismatch, not
   material" conclusion now rests on a validated, non-sign-flipped
   measurement instead of a timing artifact
   ([`layout/comparator/reports/20260906-152000-eace0b6/record.md`](../../layout/comparator/reports/20260906-152000-eace0b6/record.md),
   which supersedes the sign-flipped `20260906-101231-1250ff4` record —
   kept, untouched and append-only, as honest evidence of what that earlier
   run measured). A distinct, generic `klt pex` tool gap surfaced re-running
   the corrected timing (a relative `-o`/`--outdir` makes the extracted-side
   DUT-swap testbench's `.include` line unresolvable once `klt pex`'s
   internal `klt sim` call runs ngspice from its own per-corner working
   directory), filed at
   [klayout-tools#1525](https://github.com/2AMLogic/klayout-tools/issues/1525)
   per this repo's friction protocol and worked around locally with
   absolute paths. This finding remains non-gating — it does not bear on
   LVS/DRC cleanliness or on any spec row graded in §4.
4. **ENOB / INL-DNL target values are proposed, not ratified.**
   [DR-007](../../spec/decision-records/DR-007-revised-enob-inl-dnl-targets.md)
   proposes revised, evidence-derived candidates (ENOB > 7.5/8.0 bit,
   INL/DNL ≤ ±2.0 LSB) reading #29's own completed Monte Carlo campaign, but
   is `proposed`, awaiting operator ratification. Until it (or a superseding
   record) ratifies, §4's ENOB/INL-DNL rows stay informational, per
   `CLAUDE.md`'s "do not relax a spec line to make a result pass" rule —
   this document does not treat DR-007's candidate numbers as settled.

   **Update this pass (2026-09-06)**: DR-007's status was re-checked live —
   still `proposed`, still not ratified, so this item does not close. Two
   traceability defects in §4's rows were found and fixed, however:
   - The **ENOB row was one amendment stale**. It cited
     `sim/enob-estimate/records/20260828-005033-0c70212.md` (8.491/7.749
     bit), composed from the *pre*-DR-004-Amendment-A comparator-noise
     figure of 0.9591 mV rms — even though the comparator-noise row directly
     above it had already been updated to the amended 0.8643 mV rms figure.
     The machine-checked `docs/characterization-report.md` had already
     carried the re-composed 8.506/7.755 figures since issue #175's pass;
     §4 had not. No post-amendment record scored those figures against
     DR-007's *candidate* pair (the only candidate-scored record,
     `20260828-024246-f36913e.md`, is also pre-amendment), so this pass
     minted one —
     [`sim/enob-estimate/records/20260906-173830-6f04f59.md`](../../sim/enob-estimate/records/20260906-173830-6f04f59.md),
     a derived/composite re-scoring with no new ngspice run, per
     `sim/enob-estimate/run_enob.py`'s own `--target-baseline-bit`/
     `--target-stretch-bit` path — so §4's DR-007-candidate verdict now
     traces to current evidence instead of pre-amendment evidence.
   - The **ENOB row's verdict was mis-stated**. It headlined "DOES NOT MEET
     even the un-ratified DR-007 candidate", but DR-007's candidate pair is
     `> 7.5 bit` baseline / `> 8.0 bit` stretch, and both the old and the
     re-composed worst-case figures (7.749, now 7.755 bit) clear the > 7.5
     baseline — the shortfall is against the > 8.0 *stretch* only, exactly
     as the source records' own scoring tables report. Overstating a
     shortfall is as much a departure from the evidence as understating
     one; the row now states the baseline/stretch split explicitly rather
     than collapsing it.
   - The **INL/DNL row claimed no DR-007-candidate re-evaluation existed**
     ("not re-evaluated against DR-007's wider ±2.0 LSB candidate in this
     document"). One does:
     [`sim/cdac-array-transfer/records/20260828-022618-f36913e.md`](../../sim/cdac-array-transfer/records/20260828-022618-f36913e.md)
     re-parses the same 40 committed mismatch draws against the ±2.0 LSB
     candidate. It is now cited — with its own limitation stated rather
     than smoothed over: `klt yield` produced no report in that record's
     environment, so it establishes only that every sampled draw's worst
     case (max\|DNL\| = 1.9716 LSB, max\|INL\| = 1.3147 LSB) falls inside
     the candidate bound, **not** a machine-checked yield-fraction verdict
     against it. Unlike the ENOB estimate, this record is unaffected by
     DR-004 Amendment A (it composes no comparator term), so its numbers
     did not drift and no re-run was needed.

   Neither correction changes any met/unmet outcome in kind, and neither
   ratifies anything: DR-007's candidates remain candidates.
5. **Differential-reference vs. single "bandgap reference" slot mismatch**
   (§2.2). This design's `VREFP`/`VREFN` pair does not map cleanly onto a
   single bias/bandgap-reference budget line the way the port-parity
   sibling `gf180-sar-adc`'s single-ended `V_REF` does. Genuinely new,
   surfaced by writing this document — not previously tracked. Whether this
   is resolvable (harness-supplied differential pair) or needs a small
   on-chip single-to-differential conversion is unresolved and is not
   guessed at here; it should be revisited once `rules-4.html` states the
   real slot categories.
6. **`VCM` drive-impedance/decoupling budget: quantified, not yet closed.**
   A single-corner (`tt`/27 °C/1.8 V) sweep against the unmodified sampling
   front-end DUT
   ([`sim/vcm-drive-budget/records/20260905-201703-f012255.md`](../../sim/vcm-drive-budget/records/20260905-201703-f012255.md))
   replaces `VCM`'s ideal source with a series `R_source` (plus optional
   on-die `C_decouple`) and measures the resulting differential sampled-value
   error at the end of the SAMPLE window, at the DR-006-derived worst-case
   acquisition window (83.333 ns, `f_clk` = 12 MHz) and this repo's
   pre-existing 400 ns testbench convention:
   - Worst-case (83.3 ns) window: bare (undecoupled) `R_source` budget is
     ≤ 10 kΩ for ≤ 1 provisional LSB of differential error, ≤ 100 Ω for
     ≤ 0.1 LSB.
   - **Counterintuitive finding, stated plainly rather than smoothed over**:
     the *longer* 400 ns legacy window is the more demanding case for this
     mechanism, not the shorter DR-006 window — the smallest nonzero
     `R_source` tested (10 kΩ) already exceeds 1 LSB of error at 400 ns
     (−4.229 mV) versus 83.3 ns (−2.331 mV) at the same resistance. A longer
     acquisition window lets more net charge flow from `VCM` through
     `R_source` into the sampled network, so — for this particular error
     mechanism — a shorter window is *not* automatically the worst case, the
     opposite of the usual incomplete-settling assumption. This means any
     future full-PVT campaign for this budget must sweep both ends of the
     provisional sample-rate range, not just the fastest clock.
   - At a marginal `R_source` = 30 kΩ (worst-case window), a decoupling
     capacitor ≥ 100 pF at the on-die `VCM` node recovers the differential
     error to ≤ 1 provisional LSB.
   - This is a first-pass, single-corner budget, not a fabrication-ready
     spec: switch `R_on` (which sets the effective time constant this
     mechanism depends on) varies materially with process/temperature, so a
     full PVT sweep of this same budget is still open (same class of gap as
     #28's corner campaigns for the rest of this sub-block). It also does not
     establish what `R_source`/`C_decouple` an actual on-chip `VCM`
     buffer or off-chip reference network would present — no such buffer
     exists in this design yet. What it newly establishes is the *target*
     such a (not-yet-designed) block would need to meet.
   No claim here is graded against a ratified spec row (`spec/target-spec.md`
   is entirely DRAFT, #1/#27; the DR-006 acquisition window is itself
   downstream of the DRAFT sample-rate row, Item 2 above).
7. **`rules-4.html` has not published.** Every slot-budget assumption in §2
   is carried from Challenges #2/#3's common structure, not from Challenge
   #4's own (unpublished) text. Per this issue's own acceptance criterion, a
   follow-up pass is required once it publishes, to verify or correct §2's
   numbers — not performed here because the source does not exist yet.
   **Re-checked 2026-09-06**: `https://opencircuitdesign.com/chipalooza/rules-4.html`
   still returns HTTP 404, consistent with the epic's tracked 2026-11-09
   publish date. §2's numbers therefore stay assumptions, and no slot-budget
   figure in this document has been reconciled against Challenge #4's own
   rules — that reconciliation remains owed, not silently assumed done.

None of the above is treated as blocking the *existence* of this document —
per this issue's acceptance criteria, the document itself, honestly stating
current status against every spec row, is the deliverable this pass
produces. The brief's full sign-off bar (item 1 above, chiefly) is not met
and is not claimed to be met.

---

## 8. Licensing and EDA flow

- **License**: this repository — schematics, layout, testbenches, decision
  records, and every evidence record cited above — is licensed
  [Apache-2.0](../../LICENSE), Copyright 2026 2AM Logic. It satisfies the
  common structure's requirement for a standard open license with
  modifiable sources public. (Note: `README.md`'s "Private for now" section
  predates the 2026-08-25 visibility flip to public and is stale relative
  to the repository's actual current visibility, confirmed via `gh repo
  view` at authoring time — a pre-existing documentation gap, not
  introduced by this document, and out of this issue's scope to fix here.)
- **Flow**: fully open-source. Schematic capture and netlisting via
  [xschem](https://xschem.sourceforge.io/); simulation via
  [ngspice](https://ngspice.sourceforge.io/); layout, DRC, LVS, and
  extraction via [KLayout](https://www.klayout.de/) driven by
  [klayout-tools](https://github.com/2AMLogic/klayout-tools/) (`klt`); the
  sky130A PDK fetched and pinned via
  [volare](https://github.com/efabless/volare)
  (`docs/environment-setup.md`, `sim/pdk.json`). Every simulation record
  cites its exact pinned toolchain versions (`sim/toolchain.json`), and
  every layout record cites the `klt` version and PDK commit it ran
  against.

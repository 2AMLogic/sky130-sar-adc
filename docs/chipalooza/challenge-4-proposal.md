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
| `VCM` | in, dedicated | dedicated pad (budget: 0–4) | 1 | Common-mode bias, `V_REF/2 = 0.9 V` nominal. Every functional testbench in this repo still drives it from an ideal source — no on-chip `VCM` buffer/reference network exists in this design. A drive-impedance/decoupling *budget* now exists, full-ratified-PVT-grid on every one of its four legs (bare `R_source` at both the worst-case and legacy windows, `C_decouple` at both windows) — **re-derived this pass (2026-09-15) against the post-issue-#236 sampling front end** (the `Sa` gate-net move and `Cmsw` `W=1 µm`→`W=16 µm` widening that fixed the sampling acquisition-window bottleneck, §4/§7 Item 2, also changed this budget's own DUT netlist, per issues #245/#248 via PRs #249/#250). All four legs, at every one of the 9 ratified corners, now come back right-censored at ≤ 100 kΩ bare `R_source` (both the 1-LSB and 0.1-LSB thresholds) and ≤ 1000 pF `C_decouple` — a materially looser, corner-invariant result than the pre-#236 data superseded below (which spanned 1 kΩ–30 kΩ and hit zero bare-impedance margin at 4/9 legacy-window corners) ([`sim/vcm-drive-budget/records/20260908-074408-80df05e.md`](../../sim/vcm-drive-budget/records/20260908-074408-80df05e.md), [`sim/vcm-drive-budget/records/20260908-100413-f3e2914.md`](../../sim/vcm-drive-budget/records/20260908-100413-f3e2914.md), [`sim/vcm-drive-budget/records/20260908-101358-f3e2914.md`](../../sim/vcm-drive-budget/records/20260908-101358-f3e2914.md), [`sim/vcm-drive-budget/records/20260908-113002-f3e2914.md`](../../sim/vcm-drive-budget/records/20260908-113002-f3e2914.md), [`sim/vcm-drive-budget/records/20260908-115336-f3e2914.md`](../../sim/vcm-drive-budget/records/20260908-115336-f3e2914.md); each `Supersedes` its pre-#236 counterpart, [`sim/vcm-drive-budget/records/20260905-201703-f012255.md`](../../sim/vcm-drive-budget/records/20260905-201703-f012255.md) / [`20260907-052526-f589273.md`](../../sim/vcm-drive-budget/records/20260907-052526-f589273.md) / [`20260907-090200-7768162.md`](../../sim/vcm-drive-budget/records/20260907-090200-7768162.md) / [`20260907-104958-a546200.md`](../../sim/vcm-drive-budget/records/20260907-104958-a546200.md) / [`20260908-021006-f48a228.md`](../../sim/vcm-drive-budget/records/20260908-021006-f48a228.md), respectively), quantifying — not yet closing — the same class of gap the port-parity sibling `gf180-sar-adc` names for its own `V_CM` row (see §7 Item 6) |
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
[`layout/sampling-frontend/reports/20260915-120718-1e90b14/record.md`](../../layout/sampling-frontend/reports/20260915-120718-1e90b14/record.md)
(current `reports/LATEST`, PR #275's `klayout-tools` `v0.5.0` rebuild;
supersedes `reports/20260906-230125-0904419/` and, before it,
`reports/20260905-204934-f012255/`, all three at the identical DRC/LVS
verdict — see §7 Item 1's citation-freshness corrections).
**A top-level assembled ADC layout (GDS) now exists, but is not DRC/LVS-clean
end-to-end** — when this section was first written none existed at all; one
has since landed (PR #174 and successors, see "Top-level assembly has since
landed" below), is `klt drc`-clean and connectivity-verified net-by-net, and
its two remaining gaps are `klt lvs`'s device-level match and the absence of
any post-layout PVT re-simulation. The routed
integration of the four sub-block layouts into one top-level GDS matching
`design/sar_adc_top.sch`'s hierarchy is tracked as issue #103, still open
and `loom:blocked`. All four of
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

**Update this pass (2026-09-07)**: the klayout-tools#1513 pin-declaration
blocker described above is now resolved, not merely fixed-upstream-but-
unreleased. PR #227 found that this flow's own routing cell was named the
generic `ROUTE`, colliding with `comparator`'s and `sampling_frontend`'s own
internal `ROUTE` cells once all five sub-block GDS files are composed —
exactly what was defeating pin-declaration by physical position. Renaming
this flow's routing cell to a globally-unique `SAR_ADC_TOP_ROUTE` and
signing off with `klt lvs --pin-source-cells route__SAR_ADC_TOP_ROUTE`
(built against klayout-tools commit `2313dd0`, i.e. klayout-tools#1515,
via a `SAR_ADC_TOP_KLT` override — `--pin-source-cells` still predates the
PyPI-pinned `0.4.0`) reaches an exact 19/19/19 promoted/reference/matched
top-level pin correspondence for the first time. `klt lvs` itself still
does not reach a clean device-level match: with the pin gap gone, a second,
distinct gap surfaced — `klt lvs`'s `options.combine_devices` is a single
flag applied to the whole flattened netlist, with no per-subcircuit
scoping, and three of the five sub-blocks (comparator, sar_sequencer,
seln_inverters) need it `true` while the other two (cdac_array,
sampling_frontend) need it `false` — no single top-level setting satisfies
every sub-block's own already-verified requirement at once (devices:
layout=869/reference=869, matched=794 — unchanged from the prior record,
since the same 869/869 flattened netlist is being compared, only the pin
promotion changed). Filed generically at
[klayout-tools#1552](https://github.com/2AMLogic/klayout-tools/issues/1552)
per this repo's friction protocol. That issue has since closed too, fixed
by klayout-tools#1556 (commit `5598e540`) — but like klayout-tools#1515
before it, the fix has not reached a published release: `klayout-tools` is
still at `v0.4.0` on both PyPI and the upstream repo's own tags, predating
both fixes — **no longer true as of 2026-09-15, see the second update
below**. See
[`layout/sar-adc-top/reports/20260907-110058-a546200/record.md`](../../layout/sar-adc-top/reports/20260907-110058-a546200/record.md)
(`reports/LATEST` when this paragraph was written — **itself superseded
since 2026-09-08, see the first update below**), which supersedes the
`20260906-101939-1250ff4` record above.

**Update (2026-09-15), citation freshness — this paragraph and §4's Area
row were one record stale.** `layout/sar-adc-top/reports/LATEST` read
`20260908-072857-80df05e` from 2026-09-08 until PR #275 landed later on
2026-09-15 (it now reads `20260915-213439-bf2256f`; see the third update
below): the post-#236 re-run made by
issue #245 (PR #249), already cited in §4's sample-rate row and §7 Item 1's
own 2026-09-08 update but never propagated here or to the Area row. The
substantive readouts are unchanged, verified by comparing the two records'
artefacts directly rather than assumed from the re-run's intent:

- `compose.json` is **byte-identical** between the two records (`cmp`) — so
  the Area row's bounding box did not move;
- `drc.json` reports `violations: []` in both (the only differences are the
  absolute GDS path and its `content_hash`);
- `lvs.json`'s aggregate verdict fields are identical — `status:
  "mismatch"`, `mismatch_count: 98`, `error_count: 97`, `category_counts:
  {device.unmatched: 75, net.merged: 12, net.split: 10,
  topology.flattened: 1}`. The two files differ only in artefact SHA-256s
  and in anonymous / ordering-dependent net labels (`\$412` → `\$413`,
  `CDAC.P0` ↔ `CDAC.N_TERM`, …), not in any count or category.

This paragraph and §4's Area row cite `20260908-072857-80df05e` as of that
update; §4's two sign-off-bar rows are re-pointed by a separate increment
(see §7 Item 1 for why they are not touched here). **All three citations
have since moved again** — PR #275's merged `v0.5.0` rebuild
(`20260915-213439-bf2256f`) is now `reports/LATEST`; see the third update
below and §7 Item 1.

**Update (2026-09-15), the awaited release has published.**
`2AMLogic/klayout-tools` `v0.5.0` published at 2026-09-15T02:19:49Z (GitHub
Release and PyPI), carrying all three of the commits this paragraph's
blocker chain named as outstanding. The evidence, the ancestry check, and
#103's own resulting label change are recorded once in §7 Item 1 rather
than re-derived here; this note exists so that the "still at `v0.4.0`"
sentence above is not read as current.

**Update (2026-09-15, later), the `v0.5.0` rebuild has landed and
`reports/LATEST` has moved.** #103's PR #275 (merged 2026-09-15T22:00:46Z)
re-ran the whole top-level flow on the officially pinned
`klayout-tools==0.5.0`, minting
[`layout/sar-adc-top/reports/20260915-213439-bf2256f/record.md`](../../layout/sar-adc-top/reports/20260915-213439-bf2256f/record.md),
which `layout/sar-adc-top/reports/LATEST` now resolves to. `klt drc` stays
clean (`violations: []`) and the unfiltered connectivity check is unchanged,
but `klt lvs`'s device-level mismatch did **not** clear — it moved from 98
to 124, root-caused to two newly filed upstream gaps (klayout-tools#1876,
klayout-tools#1878). §4's Area row and its two sign-off-bar rows all cite
this record; the full trace, including why the count regressed, is recorded
once in §7 Item 1 rather than re-derived here. **No §4 verdict moves as a
result of this citation move.**

**Update (2026-09-16), the #1876 regression is neutralised and
`reports/LATEST` has moved twice more.** Two further partial increments on
#103 landed after the paragraph above was written, both `Part of #103`, not
`Closes`: PR #287 (merged 2026-09-15T23:27:08Z) found klayout-tools#1876's
regression is recoverable **locally** (`klt extract` still states every
device's class in its own per-instance provenance comment; a new
`layout/sar-adc-top/bin/restore-cap-device-class.py` restores it onto the
`C` card before the LVS request), re-running the flow on the identical
composed GDS and reproducing the **pre-0.5.0 98-mismatch / 412-matched-net**
baseline exactly (`device.unmatched` back to 75, the spurious
capacitor-class `topology: 2` category gone) —
[`layout/sar-adc-top/reports/20260915-222624-10afb15/record.md`](../../layout/sar-adc-top/reports/20260915-222624-10afb15/record.md).
PR #290 (merged 2026-09-16T00:02:07Z) then *measured, but did not adopt*, a
fourth LVS shape — `--abstract-cells` black-boxing three of the five
sub-blocks (the ones whose `combine_devices` needs conflict with the other
two, klayout-tools#1878's own root cause) plus a matching hollowed
reference — which narrows the same composed GDS to **6 mismatches**
(`device.unmatched: 3`), but traces all 6 to a new, distinct upstream defect
(a label-less 4th `cdac_array` port that `--abstract-cells` silently drops,
corrupting unrelated net names), filed generically as
[klayout-tools#1911](https://github.com/2AMLogic/klayout-tools/issues/1911)
and *not* adopted for signoff pending independent confirmation the
corruption is cosmetic — `run-flow.sh` is unchanged and keeps using the
audited 98-mismatch/412-matched-net compare as the recorded attempt. Both
increments are folded into one record,
[`layout/sar-adc-top/reports/20260915-234004-76f48b9/record.md`](../../layout/sar-adc-top/reports/20260915-234004-76f48b9/record.md)
(the current `reports/LATEST`; `compose.json`'s top-level `bbox_um` is
byte-identical to `20260915-213439-bf2256f`'s, verified directly — the Area
row's number does not move), which §4's Area row and its two sign-off-bar
rows are re-pointed onto below. **No §4 verdict moves**: DRC/LVS-clean GDS
stays UNMET/BLOCKED (98 mismatches, not a match — better than the 124 this
paragraph previously cited, but still not clean), and post-layout PVT stays
UNMET (still no extraction-based re-sim at any corner). #103 itself is
`loom:blocked` again as of this pass, now specifically on
klayout-tools#1878 (with #1911 as a further, not-yet-actionable open item).

**Update (2026-09-16, later), klayout-tools#1876 and #1878 have both
since closed upstream — one via a real fix, the other confirming a dead
end, neither in a published release yet.** Re-verified live against
`2AMLogic/klayout-tools` this pass (not assumed from #103's own
dependency-recheck comment, though it independently reports the same
facts): `klayout-tools#1876` closed 2026-09-16T03:44:54Z
(`stateReason: COMPLETED`) via
[klayout-tools#1921](https://github.com/2AMLogic/klayout-tools/pull/1921)
("fix: recover capacitor device class across bare-C-card SPICE round
trip", merged 2026-09-16T03:44:53Z, commit `c5438290`) — a genuine
`src/klayout_tools/lvs.py` behavior change, not a docs edit.
`klayout-tools#1878` closed 2026-09-16T03:43:13Z (`stateReason:
COMPLETED`) via
[klayout-tools#1924](https://github.com/2AMLogic/klayout-tools/pull/1924)
("docs(lvs): sharpen `combine_devices_per_circuit` no-op caveat for `klt
extract` composed netlists") — **documentation-only, no code change**;
its own body states this explicitly, and the Curator enhancement that
scoped #1878 before Champion approval confirmed no open klayout-tools
issue tracks giving `klt extract` a real hierarchical (per-macro
subcircuit) output mode, which is what `combine_devices_per_circuit`
would actually need to help this flow's composed netlist. So #1878's
closure resolves a *documentation* gap (the caveat is now written down
correctly) while leaving the *capability* gap it describes — the one
this item's blocker chain depends on — open and, as of this pass,
untracked by any single open klayout-tools issue. Neither fix is
reachable from a published release: `klayout-tools`'s latest tag is
still `v0.5.0` (`6bf56109`), and `gh api
repos/2AMLogic/klayout-tools/compare/v0.5.0...c5438290` reports
`status: "ahead", ahead_by: 48, behind_by: 0` — i.e. `c5438290` is 48
commits ahead of the `v0.5.0` tag, not contained in it.
`klayout-tools#1911` (§ above) remains **OPEN**, independently
reconfirmed this pass. **#103 itself is still `loom:blocked`** — its own
2026-09-16T03:53:30Z dependency re-check (the most recent comment on that
issue as of this pass) reaches the identical conclusion and restates the
blocking condition as "a merged-but-unreleased fix for the
capacitor-identity gap [#1876], plus a still-open gap on the alternate
`--abstract-cells` path [#1911]" — this repo's own established practice
(set by #103's PR #275) is to wait for an official release rather than
pin to an unreleased commit or reintroduce an env-var override. **No §4
verdict moves**: DRC/LVS-clean GDS stays UNMET/BLOCKED and post-layout
PVT stays UNMET, unchanged from the paragraph above — this update only
corrects the tracking-issue-status claim ("klayout-tools#1878 ... open")
that paragraph made, which is now stale.

**Update (2026-09-16, yet later): `klayout-tools#1911` has since closed
too, via a genuine code fix — the third and last of this item's three
tracked upstream gaps to close.** Re-verified live:
`gh issue view 1911 --repo 2AMLogic/klayout-tools` reports
`state: CLOSED`, `closedAt: 2026-09-16T09:50:34Z`, closed by
[klayout-tools#1934](https://github.com/2AMLogic/klayout-tools/pull/1934)
("fix(extract): stop `--abstract-cells` from corrupting unrelated net
names"), merged 2026-09-16T09:50:33Z, commit `ad3f8363` — a genuine
`extract_abstract.py`/`extract.py` behavior fix (captures each abstracted
cell's pre-erasure `nwell`/`substrate_isolation` cover and unions it back
into classification only, so black-boxing a cell no longer merges
unrelated substrate-tied nets), with its own regression test, not a docs
edit. **Still not reachable from a published release**: `klayout-tools`'s
latest tag is still `v0.5.0`, and `gh api
repos/2AMLogic/klayout-tools/compare/v0.5.0...ad3f8363` reports
`ahead_by: 61, behind_by: 0`. **#103 itself has not yet caught up**: its
own most recent dependency re-check (2026-09-16T03:53:31Z) predates
#1911's 09:50:34Z closure and still names it as an open gap; #103 remains
`loom:blocked`. **No §4 verdict moves**: DRC/LVS-clean GDS stays
UNMET/BLOCKED and post-layout PVT stays UNMET — the row's blocker is now
a release gate (three merged, unreleased fixes: #1921, #1924, #1934)
rather than any single open klayout-tools issue. This corrects the
"`klayout-tools#1911` ... remains **OPEN**" claim in the paragraph above,
which is now stale by about six hours as of this pass.

---

## 4. Target specification at Sky130's ratified 1.8 V rail

Every row below is reported at this repository's own ratified PVT grid —
process corners `{ff, fs, sf, ss, tt}`, temperature `{−40, 27, 125} °C`,
supply `{1.62, 1.80, 1.98} V`, one-at-a-time (9 points) — per
`spec/target-spec.md`'s "Numeric rows — RATIFIED 2026-08-19" section and
`sim/README.md`'s "Corner-grid shape." No row below has ever been measured
at, or claimed to hold at, any rail above 1.8 V core (§2.1).

The verdict column below states one of six kinds, per this issue's own
acceptance criterion ("every spec row states met/unmet... no row is
relaxed"). Every row opens its verdict cell with one of these, and the list
is **machine-checked in both directions** (check 8 of the
[citation gate](check_proposal_citations.py)): a row opening with a kind not
defined here fails CI, and a kind defined here that no row uses fails too —
so the vocabulary cannot drift away from the table, as it had before
2026-09-16 (this list said "three cases", named four kinds, and the table
used six, one of the four being a *Status* value rather than a verdict):
- **MET** — spec row is ratified and evidence shows it passes at every
  bound corner. For the one *descriptive* (non-numeric) spec row —
  Architecture — there is no corner to bound it at, and MET instead means the
  design implements exactly the topology the row describes, evidenced by the
  schematics its Source column names.
- **UNMET** — spec row is ratified and evidence shows a specific,
  named shortfall at a specific corner (not relaxed to hide it).
- **PARTIAL** — the row grades several distinct claims and they do not all
  land the same way; the cell then names each claim's own verdict.
- **UNMEASURED** — the spec row exists but no evidence campaign has produced
  the figure it asks for, as distinct from evidence that fell short.
- **Informational only** — the target-spec row states a number that is not
  yet operator-ratified (its Status is `DRAFT`); evidence may exist and is
  reported, but there is no ratified line to grade a verdict against. This is
  the verdict-column form of a `DRAFT` *numeric* Status, which is why it is
  stated here rather than in the Status column's vocabulary.
- **BLOCKED** — no evidence exists yet; names the specific issue that would
  produce it.

**The Target and Status columns are machine-checked against
[`spec/target-spec.md`](../../spec/target-spec.md) too** (check 7, added
2026-09-16): every row of that file's own Target table must appear below, with
every numeric bound it states (comparator and sign included) still present in
this table's Target cell, and the same leading Status word. That is the
mechanical form of this repository's standing rule that "agents do not relax a
spec line to make a result pass" — a bound softened, re-numbered, or dropped on
one side only is now a CI failure naming the bound, rather than something a
reader has to catch by diffing two tables by hand. It also means DR-007's
eventual ratification cannot pass unnoticed: the moment `spec/target-spec.md`
grades the ENOB and INL/DNL rows `RATIFIED`, the two "Informational only" rows
below fail the gate until they are re-graded to a real verdict.

This table mirrors, and is derived from,
[`docs/characterization-report.md`](../../docs/characterization-report.md) —
a machine-checked, regenerable aggregation (`sim/report/generate.py --check`,
wired into CI) tying every `spec/target-spec.md` row to its evidence. Where
the two differ in wording, `docs/characterization-report.md` is the
authoritative, regenerable source; this table restates it for the Chipalooza
audience with an explicit Challenge-brief verdict column.

| Parameter | Target (min/typ/max) | Status | Verdict at Sky130 1.8 V rail | Source (dated) |
|---|---|---|---|---|
| Architecture | charge-redistribution SAR, differential, top-plate sampling | DRAFT (descriptive) | **MET** — implemented as described: charge-redistribution SAR (`design/cdac/cdac_array.sch`), differential throughout (no single-ended mode exists, §6, [DR-005](../../spec/decision-records/DR-005-cdac-array-design.md)), top-plate sampling (`design/sampling_frontend.sch`). Graded against the descriptive-row form of MET defined above — a topology claim against the schematics, not a bounded number at a corner | `design/sar_adc_top.sch`, `design/cdac/cdac_array.sch`, `design/sampling_frontend.sch`, `design/comparator.sch`, `design/sar_sequencer.sch` |
| Resolution `N` | 10 bit | **RATIFIED** (DR-003 via #27) | **MET** — 9/9 corners, correct MSB-first bit-by-bit capture | [`sim/sar-sequencer-behavioral/records/20260827-211956-e13bc1e.md`](../../sim/sar-sequencer-behavioral/records/20260827-211956-e13bc1e.md) |
| `V_REF` | `1.8 V` (= `V_DD`, at the rail) | **RATIFIED** (DR-003 via #27) | **MET** — structural + functional/monotonicity check, 9/9 corners | [`sim/cdac-array-transfer/records/20260827-213107-e13bc1e.md`](../../sim/cdac-array-transfer/records/20260827-213107-e13bc1e.md) |
| LSB (differential) | `2·V_REF/2^N = 3.5156 mV` | **RATIFIED** (DR-003 via #27) | **MET** — same record as `V_REF` | same record |
| Sampling cap (CDAC unit × array) | `C_u ≈ 8.65 fF`, `2^9 = 512` positions/side | **RATIFIED** (DR-003 via #27) | **MET** — sim structural check (9/9 corners); independent layout evidence also exists and is now DRC- and LVS-confirmed (drawn `C_u = 8.6473 fF`, unit-cap count 1024 = 512/side × 2). The original record's LVS "match" did not reproduce against its own committed artefacts (#148); #148's fix compares the array's 1024 drawn unit capacitors 1:1 against the reference (no `combine_devices` folding) and its replacement record's match reproduces on repeat runs | same record; [`layout/cdac-array/reports/20260906-020815-38cdbd3/record.md`](../../layout/cdac-array/reports/20260906-020815-38cdbd3/record.md) (current `reports/LATEST`; supersedes `reports/20260905-220338-9fb9b04/` — issue #165's own tap/landing-pad fix (PR #170) re-ran this flow with an identical extraction/LVS/unit-cap outcome, see §7 Item 1 — which itself supersedes `reports/20260825-132454-51cbdd4/`, see #148) |
| Comparator input-referred noise | `≤ 1.0148 mV rms` (baseline) / `≤ 0.5859 mV rms` (stretch) | **RATIFIED** (DR-003 via #27) | **MET** vs. baseline at binding corner `tt_125c_1.80v` = 0.8643 mV rms; **UNMET** vs. stretch at the same corner. Reduced-sub-model methodology named ([DR-004](../../spec/decision-records/DR-004-comparator-topology-and-noise-budget.md)). Re-measured this pass against issue #175's amended (reset-integrity-fixed) device set — the binding-corner figure moved from 0.9591 to 0.8643 mV rms; the pass/fail outcome is unchanged | [`sim/comparator-decision/records/20260906-065109-eedd532.md`](../../sim/comparator-decision/records/20260906-065109-eedd532.md) |
| Corners | −40/27/125 °C, ±10 % supply, sky130 process corners | **RATIFIED** (DR-003 via #27) | **MET** — corner runner switches `.lib` process sections correctly, harness self-test negative control passes | `sim/harness-corner-smoke/records/`, `sim/mc-smoke/records/` |
| Sample rate | provisional 100 kS/s–1 MS/s | DRAFT | **UNMEASURED as an end-to-end figure (all four constituent mechanisms now checked individually and all four now PVT-complete; the one mechanism previously found NOT to clear the phase budget at any ratified corner has since been fixed by issue #236 and now clears it at all 9/9 — see (d)'s "Update this pass (2026-09-08)")** — **Update this pass (2026-09-15): a full-hierarchy, whole-ADC code-correctness campaign now exists (`sim/full-conversion-transient/`, issue #254) — this row previously stated none did; that is now stale.** Its most recent full-grid run ([`records/20260912-002315-9aaf1ca.md`](../../sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md), pre-dates the current schematic) found 0/9 corners code-correct; several of the defects it surfaced have since been fixed (DR-008, DR-009) but two architecture/sizing decisions remain open (`loom:operator-only`, issues #267 and #269) before a fresh 9-corner re-run would be meaningful. **Citation note (this pass)**: that record is also what `sim/full-conversion-transient/records/LATEST` resolves to (verified against the pointer file this pass); the pointer is `records/LATEST`, not `reports/LATEST` as this row previously wrote it, and this row now cites the record by full path so the citation does not depend on the pointer at all. See §7 Item 8 for the full campaign history and root causes. The four *mechanism-level* timing-budget checks below (a)–(d) are a distinct, narrower claim (does each stage clear its DR-006 phase budget in isolation) from this whole-ADC *code-correctness* campaign (does the assembled loop converge to the right code) — both are now evidenced, and both are open in different ways. The 1.2–12 MHz timing budget itself is still a mechanical consequence of the DRAFT rate range, not independently derived ([DR-006](../../spec/decision-records/DR-006-sar-sequencer-bit-count-and-timing-budget.md)). (a) The CDAC array's own settling is now **PVT-complete** (full ratified OAT grid, 9 corners): binding corner `tt_27c_1.62v` at 13.2312 ns (bit 8/MSB, rise), 6.3× inside the DR-006-derived 83.333 ns phase budget; fastest corner `tt_27c_1.98v` at 10.3019 ns (8.1×); worst-to-best spread only 1.28× across the grid, and the tt/27 °C/1.8 V point reproduces the single-corner record's own 11.3861 ns exactly. All 9/9 corners clear the budget — not the bottleneck anywhere on the grid. A secondary, non-gating finding: the smallest-swing diagnostic row (bit 0, ~0.2% of VDD swing) failed to produce a 99%-settling crossing at 5/9 corners, root-caused (confirmed window-invariant out to 300 ns, not asserted without evidence) to a small, genuine, already-converged offset between the real simulated circuit and the analytic closed-form ideal — negligible against bit 8's own ~1.8 V swing but exceeding 1% of bit 0's own ~4 mV swing at some corners; bit 8 (the array's own true worst case, confirmed by its own tau_i(i) derivation) crossed cleanly at all 9/9 corners, so this does not affect the worst-case finding (see §7 Item 2 for the full root-cause trace). (b) The comparator's decision delay is now PVT-complete after issue #175 (DR-004 Amendment A) closed the reset-integrity defect: 9/9 corners' Vindiff = 0 mV negative control HELD, all 27/27 input-driven points decided, binding corner `tt_27c_1.62v` at +0.5 mV = 4.3575 ns, 19.1× inside the DR-006 budget (see §7 Item 2 and the now-resolved §7 Item 3). (c) The SAR sequencer's own CLK-to-phase-output logic delay is now **PVT-complete** (full ratified OAT grid, 9 corners), covering all 11 of its own ring-sequencer phase transitions at every corner (99 phase measurements): binding corner `ss_27c_1.80v` at 0.4237 ns (phase `b1`), 196.7× inside the DR-006 budget; fastest corner `ff_27c_1.80v` at 0.2480 ns (336.1×); worst-to-best spread only 1.71× across the grid. All 9/9 corners clear the budget by more than two orders of magnitude — the smallest of the four mechanisms measured, and not the bottleneck at any ratified corner. (d) **The sampling front end's own acquisition of a new, worst-case (rail-to-rail) differential input value is now ALSO PVT-complete (full ratified OAT grid, 9 corners) — and it is the only mechanism of the four found NOT to clear the budget, at EVERY ratified corner**: the single-corner (`tt`/27 °C/1.8 V) finding of a 23.43 mV residual (~13.3× the provisional differential LSB's half-step), traced to the bootstrap precharge PFET `Sa`'s imperfect off-state once `BOOST_x` is boosted above `VDD`, was not a corner-specific artifact — every one of the 9 ratified corners exceeds the half-LSB reference scale, with a binding corner of `tt_27c_1.62v` at 67.19 mV (~38.2× the half-LSB, 2.9× worse than the tt/27 °C/1.8 V baseline) and a best corner of `tt_27c_1.98v` at 9.00 mV (~5.1×). This is the opposite outcome from mechanisms (a)–(c); the front end's own acquisition, not the CDAC, comparator, or sequencer, is the likely bottleneck for an end-to-end sample-rate figure at the fast end of the DRAFT range, across the full ratified PVT grid, not just one corner — strengthening, not merely narrowing, the open item, and consistent with DR-006's own deferred "non-uniform phase allocation" alternative. The design-fix follow-up this finding implies (a topology/sizing fix for the bootstrap precharge PFET `Sa`, or adopting the non-uniform-phase-allocation alternative) is now tracked as issue #236, filed this pass, since this document compiles evidence rather than designing circuit fixes. **Update this pass (2026-09-08): issue #236 closed with a circuit fix, not a phase reallocation — `design/sampling_frontend.sch`'s uniform DR-006 phase budget is UNCHANGED.** Instrumenting `BOOST_x` directly isolated two independent limiters, both fixed: (1) `Sa`'s gate moved from `SAMPLE` to the switch's own gate node `G_{p,n}` — `Sa`'s source is the boosted node itself, so gating it from a VDD-level `SAMPLE` left `V_sg ~= VIN` (an ON device discharging `BOOST_x` throughout the sample phase, not a leaky off one); gating it from `G_{p,n}` instead (GND during hold via `Sd`, shorted to `BOOST_x` by `Se` during sampling) makes `V_sg ~= 0`, genuinely off; (2) once (1) was applied, the common-mode reference transmission gate `Cmswn/Cmswp` — in series with `Csamp` on the acquisition path via the floating `BPREF_x` node — was the limiter that remained, fixed by widening it from W=1 µm to W=16 µm. Re-running the full ratified PVT grid ([`sim/sampling-acquisition-settling/records/20260908-051436-6ccd72d.md`](../../sim/sampling-acquisition-settling/records/20260908-051436-6ccd72d.md)) with both fixes applied: **all 9/9 ratified corners now clear the DR-006 worst-case (12 MHz) phase budget, worst case 0.380 mV (`tt_27c_1.62v`, ~0.2× the half-LSB) vs. the pre-fix 67.19 mV (~38.2×) at the same corner** — the sampling front end's own acquisition is no longer the standout bottleneck the pre-#236 schematic made it, alongside mechanisms (a)–(c). This does not itself produce an end-to-end sample-rate figure (still open, per the summary cell above). Three things this fix touched were explicitly NOT re-derived by #236 itself: `sim/vcm-drive-budget/`'s R_source/C_decouple budget (the wider `Cmsw` draws more peak current from the shared `VCM` rail), and `layout/sampling-frontend/`'s LVS match and `layout/sar-adc-top/`'s composition of it (both stale against the schematic's new `Sa` gate net and `Cmsw` width) — tracked as follow-up issue #245 (and its own follow-up, #248) rather than asserted clean here. **Update this pass (2026-09-15): all three have since been re-derived (issues #245/#248 via PRs #249/#250, merged 2026-09-08), closing this gap.** `layout/sampling-frontend/`'s reference netlist and drawn geometry were updated to match the post-#236 schematic and re-verified DRC-clean/LVS-clean (24/24 devices, 17/17 nets, 12/12 pins, all three negative-control fixtures still correctly mismatching) — [`layout/sampling-frontend/reports/20260915-120718-1e90b14/record.md`](../../layout/sampling-frontend/reports/20260915-120718-1e90b14/record.md). `layout/sar-adc-top/`'s composition was re-run against the updated sub-block GDS — DRC clean, and its LVS device-match verdict came back numerically identical to the pre-#245 baseline (869/869/794 devices, 444/446/412 nets, the same mismatch categories), confirming the pre-existing `combine_devices`-scoping gap (§7 Item 1) is unaffected and no new blocker was introduced — [`layout/sar-adc-top/reports/20260915-234004-76f48b9/record.md`](../../layout/sar-adc-top/reports/20260915-234004-76f48b9/record.md). **Both citations re-pointed 2026-09-16** off the `20260908-070934-80df05e` / `20260908-072857-80df05e` records that originally established these two claims and onto each flow's current `reports/LATEST` — the first §4 row found stale by this document's new [citation gate](check_proposal_citations.py) rather than by a hand re-read, and stale since 2026-09-08 (every other §4 row had been re-pointed in the meantime; this one, buried mid-narrative in the sample-rate cell, had not). Neither number above moves, and that is verified from the artefacts rather than assumed from the re-runs' intent: `layout/sampling-frontend/`'s `lvs.json` is field-identical across the two records (`status: "match"`, 24/24 devices, 17/17 nets, 12/12 pins, `category_counts: {device.body_unverified: 1, topology: 1}`) with `drc.json` clean in both, and all three negative controls still mismatch in the current record; `layout/sar-adc-top/`'s `lvs.json` is likewise field-identical (`status: "mismatch"`, `mismatch_count: 98`, `error_count: 97`, 869/869/794 devices, 444/446/412 nets, 19/19/19 pins, `category_counts: {device.unmatched: 75, net.merged: 12, net.split: 10, topology.flattened: 1}`) with `drc.json` clean in both. What the newer records add is provenance, not verdicts: both were re-run under `klayout-tools` `v0.5.0` rather than `0.4.0` (the sampling front end's MIM-cap arrays grow 0.92 µm in y under `v0.5.0`, the same growth §4's Area row already tracks — it changes no device, net, or pin count), and the top-level record additionally carries PR #287's capacitor-device-class restore. A follow-up pass (#250) then folded `layout/sampling-frontend-wells/` (issue #122) forward onto the same post-#236 device table too (byte-identical composed GDS confirmed, so `layout/sar-adc-top/`'s own composition needed no further re-run) and took the VCM drive budget's remaining `--corners` legs to the full ratified PVT grid — see §7 Item 6 for that budget's own (materially different, and looser) post-#236 results | [`sim/cdac-bit-trial-settling/records/20260905-220919-bbf06dd.md`](../../sim/cdac-bit-trial-settling/records/20260905-220919-bbf06dd.md) (CDAC mechanism, single-corner first pass); [`sim/cdac-bit-trial-settling/records/20260907-013225-5f176a6.md`](../../sim/cdac-bit-trial-settling/records/20260907-013225-5f176a6.md) (CDAC mechanism, full ratified PVT grid, PVT-complete — extends, does not formally supersede, the single-corner record); [`sim/comparator-decision/records/20260906-074451-7724af3.md`](../../sim/comparator-decision/records/20260906-074451-7724af3.md) (comparator mechanism, full grid, PVT-complete); [`sim/sequencer-logic-delay/records/20260906-192230-1b5c996.md`](../../sim/sequencer-logic-delay/records/20260906-192230-1b5c996.md) (sequencer mechanism, single-corner first pass); [`sim/sequencer-logic-delay/records/20260906-230516-0904419.md`](../../sim/sequencer-logic-delay/records/20260906-230516-0904419.md) (sequencer mechanism, full ratified PVT grid, PVT-complete — extends, does not formally supersede, the single-corner record); [`sim/sampling-acquisition-settling/records/20260906-202424-cb7e7aa.md`](../../sim/sampling-acquisition-settling/records/20260906-202424-cb7e7aa.md) (front-end acquisition mechanism, single-corner first pass, pre-#236); [`sim/sampling-acquisition-settling/records/20260906-211700-00d26af.md`](../../sim/sampling-acquisition-settling/records/20260906-211700-00d26af.md) (front-end acquisition mechanism, full ratified PVT grid, pre-#236, superseded); [`sim/sampling-acquisition-settling/records/20260908-051436-6ccd72d.md`](../../sim/sampling-acquisition-settling/records/20260908-051436-6ccd72d.md) (front-end acquisition mechanism, full ratified PVT grid, post-#236 fix, PVT-complete, all 9/9 corners clear the budget) |
| ENOB | > 7.5 bit (target), stretch > 8.0 (DR-007 candidate, was > 9.0/9.5) | DRAFT (target value, not ratified) | **Informational only — no ratified line exists to grade against.** Against `spec/target-spec.md`'s *current* DRAFT row (DR-007's candidate pair): 8.506 bit (mean-case CDAC mismatch) **meets** both the > 7.5 baseline and the > 8.0 stretch; 7.755 bit (worst-case CDAC mismatch) **meets the > 7.5 baseline but NOT the > 8.0 stretch**. Against the *original*, pre-DR-007 DRAFT row (> 9.0 / > 9.5) neither figure meets either bound. Re-composed this pass against DR-004 Amendment A's amended comparator-noise figure (0.8643 mV rms, down from 0.9591 — the same figure the comparator-noise row above already cites), moving the estimate from 8.491/7.749 to 8.506/7.755; the met/unmet outcome is unchanged in kind. **Correction**: this row previously headlined "DOES NOT MEET even the un-ratified DR-007 candidate", which overstated the shortfall — the source record's own scoring table marks the worst case as *meeting* the > 7.5 baseline, failing only the > 8.0 stretch (see §7 Item 4) | [`sim/enob-estimate/records/20260906-173830-6f04f59.md`](../../sim/enob-estimate/records/20260906-173830-6f04f59.md) (DR-007-candidate scoring, composed from the post-amendment comparator noise); [`sim/enob-estimate/records/20260906-082749-7724af3.md`](../../sim/enob-estimate/records/20260906-082749-7724af3.md) (identical figures scored against the original > 9.0 / > 9.5 row — the record `docs/characterization-report.md` pins) |
| INL / DNL | ≤ ±2.0 LSB (target, DR-007 candidate, was ≤ ±1 LSB) | DRAFT (target value, not ratified) | **Informational only**: empirical yield 0.825 (DNL) / 0.925 (INL) at N=40 against the *original* ≤ ±1 LSB target's 0.99 yield bar — `klt yield`'s own sample-size verdict on both is "insufficient" for a tight yield-fraction claim. A re-scoring against DR-007's wider ±2.0 LSB candidate **does** exist in-repo (a pure re-parse of the same 40 committed mismatch draws, no new ngspice run): its worst single draw is max\|DNL\| = 1.9716 LSB and max\|INL\| = 1.3147 LSB, i.e. every sampled draw falls inside the ±2.0 LSB candidate bound — but `klt yield` produced no report in that record's environment (a known, already-filed packaging gap, klayout-tools#1061), so there is **no machine-checked yield-fraction verdict against the candidate bound**, and N=40 is not sized for a tight yield-fraction claim in any case. Not graded met/unmet here: the candidate bound is not ratified | [`sim/cdac-array-transfer/records/20260828-005006-0c70212.md`](../../sim/cdac-array-transfer/records/20260828-005006-0c70212.md) (original ≤ ±1 LSB scoring — the record `docs/characterization-report.md` pins); [`sim/cdac-array-transfer/records/20260828-022618-f36913e.md`](../../sim/cdac-array-transfer/records/20260828-022618-f36913e.md) (DR-007-candidate re-scoring of the same draws) |
| Power | provisional, minimise at rate | DRAFT | **BLOCKED / UNMEASURED** — no full-block power campaign exists. One non-gating data point: `layout/sar-sequencer/`'s OpenROAD PnR static estimate (0.0154 mW) is for the digital sequencer sub-block only, not the full ADC, and is not a `sim/` evidence record | `layout/sar-sequencer/reports/20260905-191258-4c6c655/record.md` (current `reports/LATEST`, #102's own LVS-clean record via PR #141; non-gating, cited for completeness only — supersedes `reports/20260825-124031-1a2f7c1/`, which predates #102's LVS fix and still reports an LVS **mismatch**, see §7 Item 1) |
| Area | max, not yet specified in `spec/target-spec.md` | Not a spec row yet | **Informational only, not a spec-row verdict** — a composed top-level layout now exists (§3, §7): the full `gen_compose_0` bounding box is `(x0, y0) = (-20.2, -161.6)` µm to `(x1, y1) = (260.2, 223.9)` µm, i.e. 280.4 µm × 385.5 µm ≈ 0.108 mm². Unchanged by issue #180's comparator re-draw, and unchanged again by PR #227's routing-cell rename: this row now cites the current `reports/LATEST` record, and its `compose.json` bounding box is byte-identical to the superseded `20260906-101939-1250ff4` record's (the only two differences between those two files are a new `dbu_um: 0.001` field and the routing block's `cell_name`, `ROUTE` → `SAR_ADC_TOP_ROUTE` — no `bbox_um` or `offset_um` value moved). Verified by diffing the two artefacts, not assumed from the rename's intent. **Re-cited 2026-09-15** onto `20260908-072857-80df05e`, `reports/LATEST` at that moment (issue #245's post-#236 re-run, PR #249): its `compose.json` is **byte-identical** (`cmp`) to the `20260907-110058-a546200` file previously cited here, so this row's bounding box and area figure are unchanged — again verified by comparing the artefacts, not assumed from the re-run's intent (see §3). **Re-cited again 2026-09-15 (later)** onto the current `reports/LATEST`, `20260915-213439-bf2256f` (PR #275's `klayout-tools` `v0.5.0` rebuild, merged): this `compose.json` is *not* byte-identical to `20260908-072857-80df05e`'s, but the two differ in exactly two fields and neither moves this row's number — the `open_pdks` provenance string, and the `sampling_frontend` sub-block's own `bbox_um.y1` (146.3 → 147.22 µm, the 0.92 µm growth in that block's MIM-cap arrays under `v0.5.0` described in §7 Item 1). The composition's **top-level `bbox_um` is identical** in both (`x0, y0 = -20.2, -161.6` to `x1, y1 = 260.2, 223.9` µm), so 280.4 µm × 385.5 µm ≈ 0.108 mm² stands — verified by diffing the two artefacts field-by-field, not assumed. This is a raw `klt gen-compose` bounding-box readout, not an LVS-clean, sign-off-grade area figure — the composition's `klt lvs` verdict is still a device-level mismatch (see §3, §7 Item 1), and no spec row exists yet to grade this number against. **Re-cited 2026-09-16** onto `20260915-234004-76f48b9`, `reports/LATEST` after two further #103 increments (PR #287's #1876 neutralisation, PR #290's abstract-cells experiment, both `Part of #103` — see §7 Item 1): its `compose.json` top-level `bbox_um` is byte-identical to `20260915-213439-bf2256f`'s, verified directly, so this row's bounding box and area figure are unchanged | [`layout/sar-adc-top/reports/20260915-234004-76f48b9/compose.json`](../../layout/sar-adc-top/reports/20260915-234004-76f48b9/compose.json) (current `reports/LATEST`; top-level `bbox_um` byte-identical to [`20260915-213439-bf2256f/compose.json`](../../layout/sar-adc-top/reports/20260915-213439-bf2256f/compose.json), which is identical in turn to [`20260908-072857-80df05e/compose.json`](../../layout/sar-adc-top/reports/20260908-072857-80df05e/compose.json), which is byte-identical to [`20260907-110058-a546200/compose.json`](../../layout/sar-adc-top/reports/20260907-110058-a546200/compose.json), which in turn supersedes [`20260906-101939-1250ff4/compose.json`](../../layout/sar-adc-top/reports/20260906-101939-1250ff4/compose.json), same bounding box) |
| Digital sequencer/output register — physical implementation | transistor-level netlist + place-and-route layout | — | **MET** — netlist exists (`design/sar_sequencer.sch`); place-and-route layout exists and is DRC-clean and LVS-clean (#102) | `layout/sar-sequencer/README.md` |
| **Post-layout PVT simulation, full ADC** | brief sign-off bar | — | **UNMET** — a top-level layout now exists (PR #174, re-verified against the amended comparator geometry by PR #188, then again against PR #227's pin-declaration fix) but no extraction-based re-sim of the assembled `sar_adc_top` has been run against any PVT point; tracked under #103, under epic #25. **Update this pass (2026-09-15)**: #103's `klayout-tools` release blocker has cleared (`v0.5.0`, see §7 Item 1) and #103 is back in the ready queue as of this pass (`loom:issue`, no `loom:blocked`) — not yet MET, since no post-layout PVT sim has landed. **Citation re-pointed this pass** (the §7 Item 1 residual this document deliberately deferred until PR #273 landed): re-pointed off the one-record-old `20260907-110058-a546200` onto `20260908-072857-80df05e`, `reports/LATEST` at that moment — verified byte-for-byte equivalent (`compose.json` identical, `drc.json` clean in both, `lvs.json` aggregate fields identical: `status: "mismatch"`, `mismatch_count: 98`, `error_count: 97`, same four `category_counts`), so no verdict changes. **Update (2026-09-15, later): #103's PR #275 — now merged (2026-09-15T22:00:46Z) — has since run the deferred build against `klayout-tools` `v0.5.0`, and this row's citation is re-pointed again onto that build, the current `reports/LATEST` (`20260915-213439-bf2256f`).** Still **UNMET**: DRC stays clean and connectivity stays independently verified, but no PVT re-simulation of the assembled top level has been run either — that gap is unchanged by the layout-side rebuild. `klt lvs`'s device-level mismatch also did not clear on the rebuild (see the row below for the count); this row's own verdict does not move. **Update (2026-09-16)**: two further `Part of #103` increments (PR #287, PR #290 — see §7 Item 1) landed after the update above; neither runs a PVT re-simulation (both are LVS-shape measurements), so this row's verdict is unaffected — still **UNMET**. Citation re-pointed onto `20260915-234004-76f48b9`, the current `reports/LATEST` | [`layout/sar-adc-top/reports/20260915-234004-76f48b9/record.md`](../../layout/sar-adc-top/reports/20260915-234004-76f48b9/record.md) (current `reports/LATEST`; supersedes `20260915-213439-bf2256f`, the record this row previously cited) |
| **DRC/LVS-clean GDS, full ADC, in-repo** | brief sign-off bar | — | **PARTIAL — DRC MET, PIN DECLARATION MET, LVS DEVICE MATCH UNMET / BLOCKED**. `klt drc`: clean, 0 violations, on the composed top-level GDS, re-confirmed after PR #227. `klt lvs` pin promotion: **exact** — layout=19/reference=19/matched=19 — via PR #227's `--pin-source-cells` fix (klayout-tools#1513/#1515), resolving the prior pin-declaration mismatch. `klt lvs` device match: still a mismatch (869/869 devices, matched 794 — unchanged, since the same flattened netlist is compared, only pin promotion changed) — root-caused to a second, distinct upstream gap: `options.combine_devices` has no per-subcircuit scoping, and the five sub-blocks do not all need the same setting. Filed at [klayout-tools#1552](https://github.com/2AMLogic/klayout-tools/issues/1552), which **closed**, fixed by klayout-tools#1556 (commit `5598e540`), but like klayout-tools#1515 before it, not yet in a published release — PyPI still tops out at 0.4.0. klayout-tools#1556's own `combine_devices_per_circuit` helper turned out to skip the existing whole-netlist path's `#559`/`#1497` resistor-offset and capacitor-C corrections, flagged as an unverified caveat and filed at [klayout-tools#1557](https://github.com/2AMLogic/klayout-tools/issues/1557); that issue has since **closed** too, fixed by klayout-tools#1560 (commit `2d603ba5`), again not yet in a published release at the time this row was last graded. **Update this pass (2026-09-15)**: `klayout-tools` `v0.5.0` published 2026-09-15T02:19:49Z and verified to contain all three of #1515, #1556, and #1560 (each is an ancestor of the `v0.5.0` tag per `gh api .../compare/v0.5.0...<commit>`, see §7 Item 1) — the release-gate blocker has cleared. #103 is back in the ready queue as of this pass (`loom:issue`, no `loom:blocked`), but this row stays UNMET/BLOCKED rather than MET: no new `layout/sar-adc-top/` record has landed yet showing a v0.5.0-built device match, so whether the gap actually closes is still #103's open finding to report. **Citation re-pointed this pass** (same residual as the row above): re-pointed onto `20260908-072857-80df05e`, `reports/LATEST` at that moment, verified byte-for-byte equivalent to the prior `20260907-110058-a546200` citation — no verdict changes. **Update (2026-09-15, later): the v0.5.0 build this row was waiting on has since run, in #103's PR #275, now merged (2026-09-15T22:00:46Z) — the gap did not close, and in fact regressed before a second fix narrowed it back down.** `klt drc` stays clean; `klt lvs`'s device match moved from the pre-bump 98 mismatches to 128 (a stale hand-transcribed `sampling_frontend` pin table, unrelated to the tool bump, contributed 4 of those), then to 124 once that table was corrected against the current committed GDS — still not a match, and worse than the pre-bump baseline this row previously cited. Root-caused, per PR #275, to two distinct upstream gaps, both filed generically this pass and both still open: [klayout-tools#1876](https://github.com/2AMLogic/klayout-tools/issues/1876) (the `#1558`/`#1564` "write bare `C` cards for unbound capacitors" fix drops the capacitor device class's own name from extracted SPICE text, so this flow's pre-extracted-netlist `klt lvs` shape can no longer resolve capacitor devices to their reference-side counterpart by class name) and [klayout-tools#1878](https://github.com/2AMLogic/klayout-tools/issues/1878) (`options.combine_devices_per_circuit`, klayout-tools#1556's own fix for the *previous* blocker this row named, is a no-op for a `klt gen-compose`d layout: `klt extract`'s layout-side output is always one flat circuit — hierarchical extraction still doesn't exist, klayout-tools#1085 — so there is no per-macro subcircuit boundary left for the per-circuit flag to scope). This row stays **UNMET/BLOCKED**, now on #1876/#1878 rather than on the v0.5.0 release gate, which has cleared. **Citation re-pointed onto that build**: PR #275 merged, so `20260915-213439-bf2256f/` is part of this repo's own committed `reports/` tree and `layout/sar-adc-top/reports/LATEST` resolves to it — its `lvs.json` is the primary source for the 124 figure quoted above (`status: "mismatch"`, `mismatch_count: 124`, `error_count: 123`, `counts.devices` 869 layout / 869 reference / 794 matched, `counts.pins` 19/19/19, `category_counts: {device.unmatched: 99, net.merged: 12, net.split: 10, topology: 2, topology.flattened: 1}`), and its `drc.json` reports `violations: []`. **Update (2026-09-16): klayout-tools#1876 is now neutralised locally, `Part of #103` (PR #287, merged 2026-09-15T23:27:08Z)** — `layout/sar-adc-top/bin/restore-cap-device-class.py` restores each capacitor's device-class token onto its `C` card from `klt extract`'s own per-instance provenance comment before the LVS request, reproducing the **pre-0.5.0 98-mismatch / 412-matched-net** baseline exactly (`device.unmatched: 75`, `net.merged: 12`, `net.split: 10`, `topology.flattened: 1`; the spurious capacitor-class `topology: 2` category is gone). **klayout-tools#1878 remains the sole blocker** — still UNMET/BLOCKED, better than the 124-mismatch figure this row previously carried but not a match. A fourth LVS shape was then measured, `Part of #103` (PR #290, merged 2026-09-16T00:02:07Z): `--abstract-cells` black-boxing the three sub-blocks whose `combine_devices` need opposes the other two, against a matching hollowed reference, narrows the same composed GDS to **6 mismatches** (`device.unmatched: 3`) — but all 6 trace to a new, distinct defect (`--abstract-cells` silently drops `cdac_array`'s label-less 4th port, corrupting unrelated net names), filed generically as [klayout-tools#1911](https://github.com/2AMLogic/klayout-tools/issues/1911) and **not adopted for signoff** pending independent confirmation the corruption is cosmetic — `run-flow.sh` is unchanged and the recorded attempt stays the audited 98-mismatch compare. This row's verdict does not move: still **UNMET/BLOCKED**, on klayout-tools#1878 (with #1911 as a further open item, not yet actionable). **Update (2026-09-16, later)**: klayout-tools#1876 and #1878 have both since closed upstream (2026-09-16T03:44:54Z and 2026-09-16T03:43:13Z respectively) — #1876 via a genuine code fix ([klayout-tools#1921](https://github.com/2AMLogic/klayout-tools/pull/1921), merged, commit `c5438290`), #1878 via a **documentation-only** fix ([klayout-tools#1924](https://github.com/2AMLogic/klayout-tools/pull/1924)) that confirms, rather than closes, the underlying capability gap (`klt extract` still has no hierarchical/per-macro subcircuit output). Neither fix is in a published release — `klayout-tools` is still at `v0.5.0`, and `c5438290` is 48 commits ahead of that tag (`gh api .../compare/v0.5.0...c5438290`). klayout-tools#1911 remains open. **Update (2026-09-16, still later): klayout-tools#1911 has since closed too, via a genuine code fix** — [klayout-tools#1934](https://github.com/2AMLogic/klayout-tools/pull/1934) ("fix(extract): stop `--abstract-cells` from corrupting unrelated net names"), merged 2026-09-16T09:50:33Z, commit `ad3f8363`. Its own body traces the corruption to `--abstract-cells` erasing a black-boxed cell's `nwell`/`substrate_isolation` before the whole-layout body-identity classification pass reads them, which could merge unrelated substrate-tied nets under one bogus composite label — the same defect class this row's #1911 filing observed — and adds regression coverage for it (`test_abstract_cells_does_not_merge_unrelated_nets_onto_the_global_net`). This closes out all three of the upstream gaps this row has tracked (#1876, #1878, #1911), but **none of the three fixing commits is in a published release**: `klayout-tools`'s latest tag is still `v0.5.0`, and `gh api repos/2AMLogic/klayout-tools/compare/v0.5.0...ad3f8363` reports `ahead_by: 61, behind_by: 0`. Per this repo's own established practice (set by #103's PR #275), the row stays graded against what is released, not what is merged-but-unreleased. This row's verdict does not move: still **UNMET/BLOCKED**, now waiting solely on a `klayout-tools` release containing all three fixes rather than on any open upstream issue — see §7 Item 1 for the full trace. Citation re-pointed onto the record that produced both increments' numbers | [`layout/sar-adc-top/reports/20260915-234004-76f48b9/record.md`](../../layout/sar-adc-top/reports/20260915-234004-76f48b9/record.md) (current `reports/LATEST`; supersedes `20260915-213439-bf2256f`, the 124-mismatch record this row previously cited; the intermediate `20260915-222624-10afb15` record, PR #287's own first re-run of the neutralised flow, is superseded in turn), [`layout/sar-adc-top/README.md`](../../layout/sar-adc-top/README.md) |

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

**This document's own citations are now machine-checked too** (added
2026-09-16; `npm run check:proposal-citations`, wired into `npm run check:ci`
and therefore into the always-on headless CI job):
[`docs/chipalooza/check_proposal_citations.py`](check_proposal_citations.py)
verifies that every path this document cites resolves, that **every row of the
table above cites the *current* record of each `sim/`/`layout/` flow it draws
on** — as resolved from that flow's own `records/LATEST` / `reports/LATEST`
pointer, not merely a record that was current when the row was written — and
that every *attached* "current `…/LATEST`" claim in the prose is both true and
named against the right pointer file for its tree (`sim/` campaigns record
under `records/`; the `layout/` flows under `reports/`). Rows may still cite
superseded records alongside the current one, which is how this document keeps
a supersession trail visible; what they may no longer do is cite *only* a
superseded one.

The same gate also compares this table against
[`spec/target-spec.md`](../../spec/target-spec.md) row by row and grades the
verdict column against the vocabulary the section preamble defines (checks 7
and 8, added 2026-09-16). Those two are described once, in the preamble above
the table, and deliberately not restated here — the census paragraph below is
the standing reminder of what a second, hand-maintained copy of the same fact
does to this document.

**What "attached" excludes, stated rather than glossed over** (this paragraph
first claimed the pointer check covered *every* such phrase, which overstated
it): a pointer claim is checked only when the phrase directly follows the
record path it is about, with nothing between them but link/quote punctuation
and an optional "the"/"record:" connector.

**Census, machine-checked** (this paragraph counts itself, its own two quoted
examples below included): of the **22** "current `…/LATEST`" phrases in this
document, **9** are attached and therefore checked; of the **13** skipped,
**9** name a record stamp within 200 characters after the phrase, and **4**
name none at all.

Those two skipped shapes are skipped for different reasons, and neither is a
gap this document intends to close by rewriting itself:

- The ones naming **no** record are narration of a correction already made
  ("…that citation is now corrected to the current `reports/LATEST`" — the
  quotation in this sentence is itself one of them). There is nothing for a
  checker to resolve them against; matching them anyway would make the gate
  unusable on a document whose style is to narrate its own supersession
  trails.
- The ones naming a record **after** the phrase are genuine forward
  citations, but in this document they are overwhelmingly *dated historical*
  statements — "Re-cited again 2026-09-15 (later) onto the current
  `reports/LATEST`, `20260915-213439-bf2256f`" was true on the date it
  carries and is superseded by a later paragraph in the same item — or a
  contrast *with* the superseded record rather than a citation of the current
  one. Graded as present-tense claims they would fail the gate on prose that
  is correct, and the only way to "fix" that would be to delete the
  supersession trail, which is the opposite of what this gate is for. Where
  such a phrase sits inside a §4 row, that row's verdict is still held to
  current evidence by the spec-table freshness check above, which reads every
  record stamp in the cell wherever it falls.

**The census is gated, because it drifted the first time it was hand-written.**
This paragraph previously read "9 of the 19", and `.github/workflows/ci.yml`
and the checker's own module docstring each repeated that number. PR #312
(2026-09-16) then added two more pointer claims of the skipped kind, and all
three statements silently became wrong — the same "a fact was true when
written, and nothing re-derives it" failure mode the citation gate itself
exists for, one level up. The numbers above are now recomputed and compared by
check 6 of
[`check_proposal_citations.py`](check_proposal_citations.py), so a pass that
adds a pointer claim gets a CI failure naming the field that moved instead of
leaving a stale coverage claim behind; `python3
docs/chipalooza/check_proposal_citations.py --stats` prints the live census in
the same sentence form as above (minus the bold markers), to be pasted back in.
The other two copies of the number have been deleted rather than re-synced, so
this paragraph is the single place the coverage is stated.

This closes a loop rather than adding a new claim: every one of PRs #239,
#242, #276, #282, #295 and #300 was a pass that had to *correct* a citation of
exactly that kind after the fact, found by re-reading the document by hand.
The check was verified against those commits' own pre-fix trees — it flags
each drift at the commit where it existed — and on its first run against the
then-current document it found one more instance still live: §4's sample-rate
row, stale since 2026-09-08, now re-pointed (see that row's own
"Both citations re-pointed 2026-09-16" note, and the verification behind it).

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

1. **Top-level layout exists but is neither LVS-clean nor post-layout
   simulated (still the largest gap).** An assembled, routed `sar_adc_top`
   GDS *does* exist in this repo and is `klt drc`-clean (0 violations) and
   connectivity-verified net-by-net — it has since PR #174 (2026-09-06), and
   the full update trail below records every re-verification of it. This
   item's heading previously read "top-level layout does not exist", and its
   lede "no assembled, DRC/LVS-clean GDS for `sar_adc_top` exists in this
   repo"; both have been stale since that PR landed, and are corrected here
   rather than left to mislead a reader skimming §7's headings (§4's Area row
   and §3 both already stated that a composed top-level layout exists,
   contradicting them). **Nothing about the design's graded status changes
   with this correction** — what is still missing is exactly what the brief's
   sign-off bar grades, and both remain UNMET in §4: a `klt lvs`
   **device-level match** on the composed GDS (currently 98 mismatches), and
   **any post-layout PVT re-simulation** of the assembled top level (none has
   been run at any corner). Tracked as
   #103 (top-level routing/assembly), which lists #99, #100, #101, and #102
   as its four sub-block dependencies — **all four are now closed.** #99
   (sampling front-end layout) closed via PR #152 (merged
   2026-09-05T23:22:50Z): DRC-clean and LVS-clean, 24/24 devices, 17/17
   nets, 12/12 pins matched, with three negative controls confirming the
   checker catches a body-tie, device-parameter, and capacitor-top-plate-net
   corruption respectively (record:
   [`layout/sampling-frontend/reports/20260915-120718-1e90b14/record.md`](../../layout/sampling-frontend/reports/20260915-120718-1e90b14/record.md),
   current `reports/LATEST` — see this item's citation-freshness corrections
   below for why this supersedes `reports/20260906-230125-0904419/` and, in
   turn, the originally-cited `reports/20260905-204934-f012255/`).
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

   **Update this pass (2026-09-07, PR #227 — pin-declaration blocker
   resolved, a second, distinct blocker surfaces)**: PR #227 renamed this
   flow's own routing cell from the generic `ROUTE` (which collided with
   `comparator`'s and `sampling_frontend`'s own internal `ROUTE` cells once
   composed) to a globally-unique `SAR_ADC_TOP_ROUTE`, then re-signed off
   with `klt lvs --pin-source-cells route__SAR_ADC_TOP_ROUTE` (built against
   klayout-tools commit `2313dd0`, i.e. klayout-tools#1515, via a new
   `SAR_ADC_TOP_KLT` env override — the PyPI-pinned `0.4.0` in
   `layout/requirements.txt` still predates that commit). This reaches an
   **exact 19/19/19** promoted/reference/matched top-level pin
   correspondence — klayout-tools#1513 is resolved, not merely
   fixed-upstream-but-unreleased as the previous update described. `klt lvs`
   itself still does not reach a clean match: with the pin gap gone, a
   second, distinct gap surfaced — `options.combine_devices` is a single
   flag over the whole flattened netlist with no per-subcircuit scoping,
   and three sub-blocks (comparator, sar_sequencer, seln_inverters) need it
   `true` while the other two (cdac_array, sampling_frontend) need it
   `false`; devices remain layout=869/reference=869, matched=794 (unchanged
   from the prior record — the same flattened netlist, only pin promotion
   changed). Filed generically at
   [klayout-tools#1552](https://github.com/2AMLogic/klayout-tools/issues/1552)
   per this repo's friction protocol. That issue has since closed too,
   fixed by klayout-tools#1556 (commit `5598e540`) — but, like #1515 before
   it, not yet in a published release: `klayout-tools` is still `v0.4.0` on
   both PyPI and the upstream repo's own tags. `#1556`'s own
   `combine_devices_per_circuit` helper was then found to skip the existing
   whole-netlist path's `#559`/`#1497` resistor-offset and capacitor-C
   corrections — an unverified caveat for whether it is safe to adopt for
   this design's CDAC sub-block, filed at
   [klayout-tools#1557](https://github.com/2AMLogic/klayout-tools/issues/1557).
   That issue has since closed too, fixed by klayout-tools#1560 (commit
   `2d603ba5`), again not yet in a published release. New record,
   superseding `20260906-101939-1250ff4`:
   [`layout/sar-adc-top/reports/20260907-110058-a546200/record.md`](../../layout/sar-adc-top/reports/20260907-110058-a546200/record.md)
   (`reports/LATEST` now points here). §4's two blocked rows are updated to
   cite this record and the narrower (device-match-only, not
   pin-declaration) blocker. **#103 remains open, `loom:blocked`** — the
   Curator's 2026-09-07 re-checks confirm the block reason is now "waiting
   on a `klayout-tools` release newer than `v0.4.0` that includes commit
   `2313dd0` (#1515), commit `5598e540` (#1556), and commit `2d603ba5`
   (#1560)," not an open upstream question of any kind. The brief's
   sign-off bar (acceptance criterion 3) is therefore still not met, though
   the remaining gap is narrower than at any prior update in this section.

   **Update this pass (2026-09-15): the release blocker has cleared.**
   `2AMLogic/klayout-tools` published
   [`v0.5.0`](https://github.com/2AMLogic/klayout-tools/releases/tag/v0.5.0)
   at 2026-09-15T02:19:49Z (`gh api repos/2AMLogic/klayout-tools/releases`,
   this pass). Verified, not assumed, that it actually contains all three
   named commits — `gh api
   repos/2AMLogic/klayout-tools/compare/v0.5.0...<commit>` for each of
   `2313dd0` (#1515), `5598e540` (#1556), and `2d603ba5` (#1560) reports
   `status: behind` (each commit is an ancestor of the `v0.5.0` tag), not
   `diverged` or `ahead`. #103 itself has since been reclaimed off
   `loom:blocked` and is `loom:building` again as of this pass (no
   `loom:blocked` label present), consistent with the release landing. This
   document does not itself claim the device-match blocker is *resolved* —
   only that the upstream release gate #103 was waiting on has cleared and
   a build against it is in progress; whether `klt lvs` now reaches a clean
   match against the updated toolchain is #103's own finding to report, not
   this compilation's to anticipate. §4's two sign-off-bar rows below are
   corrected to drop the stale "still pending a klayout-tools release"
   framing accordingly; they are not yet updated to a MET verdict, since no
   new `layout/sar-adc-top/` record exists yet reflecting a v0.5.0-built
   result.

   **Citation-freshness correction (2026-09-08, no new layout work)**: that
   pass re-pointed §4's two sign-off-bar rows at the
   `20260907-110058-a546200` record but left §4's **Area** row still citing
   the superseded `20260906-101939-1250ff4/compose.json` — the last §4 row
   pointing at a superseded top-level layout record. That citation is now
   corrected to the current `reports/LATEST` artefact. The area figure
   itself does not change, and that is verified rather than assumed: a diff
   of the two `compose.json` files differs only in a new `dbu_um: 0.001`
   field and in the routing block's `cell_name` (`ROUTE` →
   `SAR_ADC_TOP_ROUTE`, PR #227's collision fix) — every `bbox_um` and
   `offset_um` value, including the top-level `gen_compose_0` bounding box
   §4 quotes, is identical between them. PR #227's rename therefore moved
   no geometry, and the ≈ 0.108 mm² readout stands on the current record.
   No met/unmet verdict in §4 changes. #103 is unaffected: re-verified live
   this pass, it remains open and `loom:blocked` for the
   klayout-tools-release reason above.

   **Citation-freshness correction (2026-09-08, second pass — three more
   superseded sub-block records)**: the correction immediately above fixed
   §4's Area row; auditing every other `layout/*/reports/LATEST` pointer in
   this repo against what this document actually cites turned up three more
   stale paths, each verified by diffing the superseded record against the
   current one directly rather than assumed from the record IDs alone:

   - `layout/cdac-array/`: `reports/LATEST` is `20260906-020815-38cdbd3`,
     minted by issue #165's own fix (PR #170 — the `VDD` n-well tap and 18
     `SELp`/`SELn` poly landing pads this section already describes above).
     §3 and §4 (the "Sampling cap" row) still cited the pre-#165 record,
     `reports/20260905-220338-9fb9b04/` (the #148 fix's own record, described
     earlier in this same paragraph). Diffing the two `record.md` files (and
     the underlying `extract.json`/`lvs.json`) shows the extraction/LVS
     verdicts, the drawn unit-cap value (8.6473 fF), every device/net count,
     and the common-centroid table are identical — only the drawn GDS
     geometry and the header provenance stamp differ, confirming #165's own
     "every switch transistor's `L`/`W`/`AS`/`AD`/`PS`/`PD` is byte-identical"
     claim from the layout-evidence side too. Both citations now point to
     `reports/20260906-020815-38cdbd3/`.
   - `layout/sampling-frontend/`: `reports/LATEST` was, at the time of this
     2026-09-08 audit, `20260906-230125-0904419`, minted by issue #208's
     refactor (PR #210,
     deduping the hand-transcribed PFET device table across the sub-block's
     own generator scripts). This section and §3 above still cited the
     pre-refactor record, `reports/20260905-204934-f012255/`. Diffing the two
     `record.md` files: identical except the header provenance stamp — the
     refactor changed no device count, DRC/LVS verdict, or pin count. Both
     citations were re-pointed to `reports/20260906-230125-0904419/` then,
     and have since been re-pointed again onto the current `reports/LATEST`
     — see the 2026-09-16 citation-freshness correction at the end of this
     item.
   - `layout/sar-sequencer/`: §4's Power row cited
     `reports/20260825-124031-1a2f7c1/`, which predates issue #102's own LVS
     fix (PR #141, "reach clean LVS for the SAR sequencer layout") and still
     reports an **LVS mismatch** (devices layout=760/reference=760/matched=0;
     nets layout=539/reference=395/matched=0) — a citation that actively
     contradicted this same document's own "#102 — done, DRC-clean and
     LVS-clean" statements elsewhere in this section and in §3. The current
     `reports/LATEST`, `20260905-191258-4c6c655` (#141's own record), reports
     an **LVS match** (devices 760/760/760; nets 395/395/395) and a
     marginally different non-gating power estimate (0.0154 mW vs. the
     stale record's 0.0155 mW, from the same PR's routing/utilization
     re-run, not a design change: utilization 52.9% vs. 51.5%, wirelength
     1260 µm vs. 1288 µm, fmax 713.6 MHz vs. 696.1 MHz). §4's Power row now
     cites this record and the updated 0.0154 mW figure.

   None of these three corrections changes any met/unmet verdict in §4 — the
   Sampling-cap and (implicitly, via §3's narrative) sampling-frontend
   evidence were already graded on a verdict whose substance is unchanged,
   and the Power row's own verdict is, and remains, BLOCKED/UNMEASURED (the
   cited figure is a non-gating data point, not a spec-row pass). Recorded
   here, not silently fixed, per this document's own citation-freshness
   convention established by the Area-row correction immediately above.

   **Update this pass (2026-09-15, post-issue-#236 re-verification, no new
   layout-record citations needed here):** issue #236's sampling-frontend
   circuit fix (§4/§7 Item 2) invalidated `layout/sampling-frontend/`'s own
   LVS reference netlist and, downstream of it, `layout/sar-adc-top/`'s
   composition. Both were re-verified by issues #245/#248 (PRs #249/#250,
   merged 2026-09-08): `layout/sampling-frontend/` is re-confirmed
   DRC-clean/LVS-clean against the current schematic, and
   `layout/sar-adc-top/`'s re-run composition is DRC clean with an LVS
   device-match verdict numerically identical to the pre-#245 baseline
   (869/869/794 devices, 444/446/412 nets, the same mismatch categories) —
   confirming the `combine_devices`-scoping blocker this item already
   describes is unaffected by the sampling-frontend change, not a new or
   different defect. Full citations and the VCM-budget-specific finding are
   in §4's sample-rate row and §7 Item 6, respectively, rather than
   duplicated here. #103 itself, and the acceptance-criterion-3 blocker
   this item exists to track, are unchanged: still `loom:blocked`, still
   waiting on the same `klayout-tools` release described above.

   **Citation freshness, corrected 2026-09-15.** §3 and §4's **Area** row
   were still citing `20260907-110058-a546200` as `reports/LATEST`, one
   record behind: `layout/sar-adc-top/reports/LATEST` read
   `20260908-072857-80df05e` from 2026-09-08 (the re-run this item's own
   2026-09-08 update above already cites in prose) until PR #275 moved it
   again later on 2026-09-15 (see the update below). Both are re-pointed,
   with the equivalence verified artefact-by-artefact — `compose.json`
   byte-identical (`cmp`), `drc.json` `violations: []` in both, `lvs.json`
   aggregate verdict fields identical (`status: "mismatch"`,
   `mismatch_count: 98`, `error_count: 97`, same four `category_counts`);
   full comparison in §3. **No verdict in §4 moves as a result.**
   **Residual, deliberately deferred (2026-09-15) — now resolved (this
   pass).** §4's two sign-off-bar rows (post-layout PVT, DRC/LVS-clean GDS)
   carried the same one-record-old citation at the time the paragraph above
   was written, deferred because an independent, concurrently-open increment
   on this issue (PR #273) was editing those two exact rows for a different
   reason (the `klayout-tools` v0.5.0 release), and re-pointing them there
   would have collided with it rather than composed. PR #273 has since
   merged, and its edits left the record ID untouched exactly as predicted —
   both rows were re-pointed onto what was then `reports/LATEST`
   (`20260908-072857-80df05e`; superseded again later the same day, see the
   update below), with the same artefact-by-artefact
   equivalence check as the Area row above (`compose.json` identical,
   `drc.json` clean in both, `lvs.json` aggregate fields identical). **No
   verdict in §4 moves as a result of this citation move** — #103's own
   status (back in the ready queue, `loom:issue`, no `loom:blocked`, no new
   `layout/sar-adc-top/` record showing a v0.5.0-built device match yet) is
   unchanged.

   **Update this pass (2026-09-15, later): the v0.5.0-built device-match
   result named above as still outstanding has since been produced, in
   #103's own PR #275 — merged 2026-09-15T22:00:46Z.** The build did not
   reach a clean match. Re-running against the officially-pinned
   `klayout-tools==0.5.0` (retiring the `SAR_ADC_TOP_KLT` env override this
   item's own history above needed to reach klayout-tools#1515 pre-release)
   kept DRC clean and connectivity independently verified, but `klt lvs`'s
   device match regressed from the 98 mismatches this item's prior citations
   carried to 124 — after PR #275 first found and fixed an unrelated, real
   defect (a stale hand-transcribed `sampling_frontend` pin table in
   `build_layout.py`, 0.92 µm off the pins the current committed GDS
   actually exposes, contributing 4 of an initial 128). The residual 124 is
   root-caused, per PR #275's own investigation, to two upstream gaps
   distinct from anything named earlier in this item, both filed generically
   this pass per this repo's friction protocol and both still open:
   [klayout-tools#1876](https://github.com/2AMLogic/klayout-tools/issues/1876)
   (klayout-tools#1558/#1564's "write bare `C` cards for unbound capacitors"
   fix — itself a correct, independently-motivated simulatability
   improvement — drops the capacitor device class's own name from the
   extracted SPICE text, so this flow's pre-extracted-netlist `klt lvs`
   shape can no longer resolve capacitor devices to their reference-side
   counterpart by class name; confirmed by diffing the same GDS's extracted
   `C` cards, pre-#1558 build vs. 0.5.0, byte-for-byte) and
   [klayout-tools#1878](https://github.com/2AMLogic/klayout-tools/issues/1878)
   (`options.combine_devices_per_circuit`, klayout-tools#1556's own fix for
   the pin-composition-era blocker this item names above, turns out to be a
   no-op for the layout side of any `klt gen-compose`d netlist: `klt
   extract` has no hierarchical extraction mode — klayout-tools#1085 remains
   open — so its layout-side output is always one flat circuit with no
   per-macro subcircuit boundary left for a per-circuit flag to scope).
   Trying `combine_devices_per_circuit` directly, per PR #275, produced 1154
   mismatches — substantially worse than the existing whole-request
   `combine_devices: true` compromise the flow keeps using instead. #103's
   acceptance criterion for LVS-clean therefore remains explicitly unmet in
   PR #275's own body (left unchecked, not glossed over), and this item's
   blocker chain is now two upstream issues deep rather than one. PR #275
   having merged, its
   [`layout/sar-adc-top/reports/20260915-213439-bf2256f/record.md`](../../layout/sar-adc-top/reports/20260915-213439-bf2256f/record.md)
   build **is** part of this repository's own committed evidence tree and
   `layout/sar-adc-top/reports/LATEST` now resolves to it, so §4's two
   sign-off-bar rows are re-pointed onto that record here — the same
   freshness convention §4's Area row and the §3 paragraph above already
   follow, and the same `reports/LATEST`-tracking move the two rows'
   2026-09-15 re-point (above) made onto the then-current record. **Neither
   row's verdict moves**: post-layout PVT stays UNMET (no extraction-based
   re-sim has been run at any corner) and DRC/LVS-clean stays UNMET/BLOCKED
   (the device match is 124 mismatches, worse than the 98 the superseded
   citation carried) — the citation now names the record that actually
   produced the numbers each row quotes. PR #275's blast-radius re-runs also
   moved three sub-block pointers — `layout/trivial-cell/reports/LATEST` to
   `20260915-120637-1e90b14`, `layout/comparator/reports/LATEST` to
   `20260915-120705-1e90b14`, and `layout/sampling-frontend/reports/LATEST`
   to `20260915-120718-1e90b14` — with **no verdict moved**: all three are
   DRC-clean (`violations: []`) and `klt lvs` `status: "match"` at the same
   counts this item's per-block audit above already reports (sampling
   frontend 24/24 devices, 17/17 nets, 12/12 pins; comparator 11/11, 10/10,
   7/7; trivial cell 4/4, 13/13, 1/1), verified by reading those records'
   own `drc.json`/`lvs.json` rather than inferred from the bump's intent. That
   audit list (and §3) still names the pre-bump record ID for
   `layout/sampling-frontend/`; since its verdict and every count are
   identical, re-pointing it is left to the next pass that touches those
   citations rather than folded into this one. **(Discharged 2026-09-16 —
   see the citation-freshness correction at the end of this item.)**

   **Update this pass (2026-09-16): the 124-mismatch regression named above
   is now neutralised, and a fourth LVS shape has been measured but not
   adopted.** Two further `Part of #103` increments landed after the
   2026-09-15-later update above, neither closing #103: PR #287 (merged
   2026-09-15T23:27:08Z) found klayout-tools#1876's capacitor-device-class
   loss is recoverable locally — `klt extract` still states every device's
   class in its own per-instance provenance comment, so a new
   `layout/sar-adc-top/bin/restore-cap-device-class.py` restores it onto the
   `C` card before the LVS request — and, re-running the identical composed
   GDS through the restored flow, reproduces the pre-0.5.0 baseline exactly:
   98 mismatches, 97 errors, `device.unmatched: 75`/`net.merged: 12`/
   `net.split: 10`/`topology.flattened: 1`, 412/446/444 nets matched, 794/869
   devices matched, 19/19/19 pins
   ([`layout/sar-adc-top/reports/20260915-222624-10afb15/record.md`](../../layout/sar-adc-top/reports/20260915-222624-10afb15/record.md)).
   klayout-tools#1876 is therefore neutralised for this flow's purposes;
   klayout-tools#1878 (the `combine_devices_per_circuit` no-op, unrelated to
   capacitor class names) remains the sole active blocker. PR #290 (merged
   2026-09-16T00:02:07Z) then *measured, without adopting*, a fourth LVS
   shape: `klt extract --abstract-cells` black-boxing the three sub-blocks
   whose `combine_devices` need conflicts with the other two (the same
   klayout-tools#1878 root cause), matched against a hollowed reference of
   equal shape (header + `.ENDS` only for the three abstracted subckts, no
   devices, mirroring the layout side's own opaque boundary), narrows the
   comparison to **6 mismatches** (`device.unmatched: 3`, `net.merged: 2`,
   `topology: 1`; nets 59 layout/61 reference/128 matched, devices
   35/35/32, pins 19/19/92, per the record's own addendum) — but all 6
   trace to a new, distinct upstream defect:
   `--abstract-cells` silently drops `cdac_array`'s label-less 4th port,
   corrupting unrelated net names in the process. Filed generically as
   [klayout-tools#1911](https://github.com/2AMLogic/klayout-tools/issues/1911)
   per this repo's friction protocol, and **not adopted for signoff** pending
   independent confirmation the corruption is cosmetic — `run-flow.sh` is
   unchanged and the flow's own recorded, audited attempt stays the
   98-mismatch/412-matched-net compare above. Both increments' artefacts are
   folded into one record,
   [`layout/sar-adc-top/reports/20260915-234004-76f48b9/record.md`](../../layout/sar-adc-top/reports/20260915-234004-76f48b9/record.md)
   (current `reports/LATEST`; `compose.json`'s top-level `bbox_um` is
   byte-identical to `20260915-213439-bf2256f`'s — the Area row does not
   move). **#103 itself is `loom:blocked` again as of this pass**, per its
   own 2026-09-16 dependency re-check, now specifically on
   klayout-tools#1878 (with #1911 as a further, not-yet-actionable open
   item; both confirmed still **OPEN** upstream as of this check, `gh issue
   view 1876/1878/1911 --repo 2AMLogic/klayout-tools`). §4's two sign-off-bar
   rows are re-pointed onto this record; **no verdict in §4 moves as a
   result** — DRC/LVS-clean GDS stays UNMET/BLOCKED (98 mismatches, not a
   match — better than the 124 this item previously cited, but still not
   clean) and post-layout PVT stays UNMET (still no extraction-based re-sim
   at any corner, regardless of which LVS shape is used).

   **Update (2026-09-16, later): klayout-tools#1876 and #1878 have both
   closed — one with a real fix, one confirming a dead end — and #103's
   own dependency re-check has already caught up to this.** Re-verified
   live: `klayout-tools#1876` closed 2026-09-16T03:44:54Z
   (`stateReason: COMPLETED`) via
   [klayout-tools#1921](https://github.com/2AMLogic/klayout-tools/pull/1921)
   ("fix: recover capacitor device class across bare-C-card SPICE round
   trip", merged, commit `c5438290`) — a genuine `lvs.py` behavior fix, not
   a docs edit. `klayout-tools#1878` closed 2026-09-16T03:43:13Z
   (`stateReason: COMPLETED`) via
   [klayout-tools#1924](https://github.com/2AMLogic/klayout-tools/pull/1924)
   ("docs(lvs): sharpen `combine_devices_per_circuit` no-op caveat for `klt
   extract` composed netlists") — **documentation-only**; its own body
   states no `src/klayout_tools/lvs.py` behavior changed, and the Curator
   pass that scoped #1878 before Champion approval separately confirmed no
   open klayout-tools issue tracks giving `klt extract` a real
   hierarchical/per-macro subcircuit output mode (the capability
   `combine_devices_per_circuit` would actually need). So #1878's closure
   fixes a documentation gap while the *capability* gap this item's
   blocker chain depends on stays open, now untracked by any single open
   klayout-tools issue. Neither fix is reachable from a published release:
   `klayout-tools`'s latest tag is still `v0.5.0` (`6bf56109`), and `gh api
   repos/2AMLogic/klayout-tools/compare/v0.5.0...c5438290` reports
   `ahead_by: 48, behind_by: 0` — `c5438290` postdates the tag by 48
   commits. `klayout-tools#1911` remains **OPEN**, independently
   reconfirmed. **#103 itself is still `loom:blocked`**: its own
   2026-09-16T03:53:30Z dependency re-check (the issue's most recent
   comment as of this pass) reaches the same conclusion and restates the
   block as "a merged-but-unreleased fix for the capacitor-identity gap
   [#1876], plus a still-open gap on the alternate `--abstract-cells` path
   [#1911]" — this repo's own established practice (set by #103's PR #275)
   is to wait for an official release rather than pin to an unreleased
   commit. **No §4 verdict moves**: DRC/LVS-clean GDS stays UNMET/BLOCKED
   and post-layout PVT stays UNMET, unchanged from the paragraph above —
   this update corrects only the "both still open" tracking-issue-status
   claim that paragraph made about klayout-tools#1876/#1878, which is now
   stale.

   **Update (2026-09-16, yet later): klayout-tools#1911 has now closed too,
   via a genuine code fix, independently re-verified live.** `gh issue view
   1911 --repo 2AMLogic/klayout-tools` reports `state: CLOSED`,
   `closedAt: 2026-09-16T09:50:34Z`, closed by
   [klayout-tools#1934](https://github.com/2AMLogic/klayout-tools/pull/1934)
   ("fix(extract): stop `--abstract-cells` from corrupting unrelated net
   names"), merged 2026-09-16T09:50:33Z, commit `ad3f8363`. The fix captures
   each abstracted cell's pre-erasure `nwell`/`substrate_isolation` cover and
   unions it back into the classification-only side before
   `_erase_abstracted_cell_geometry()` runs, so `tap - nwell` (and the
   derived-tap/isolation-island variants) classify as a flat extraction
   would — the same net-corruption defect class #1911 reported for
   `cdac_array`'s label-less 4th port — and ships a regression test
   reproducing the exact cross-net merge. This is the third and last of the
   three upstream gaps this item has tracked (#1876, #1878, #1911) to close.
   **None of the three fixes is reachable from a published release**:
   `klayout-tools`'s latest tag is still `v0.5.0` (unchanged since the prior
   update in this item), and `gh api
   repos/2AMLogic/klayout-tools/compare/v0.5.0...ad3f8363` reports
   `ahead_by: 61, behind_by: 0`. **#103 itself has not yet caught up to this
   closure**: its own most recent dependency re-check (2026-09-16T03:53:31Z)
   predates #1911's 09:50:34Z closure by about six hours and still cites
   #1911 as an open, not-yet-actionable gap; #103 remains `loom:blocked` as
   of this check. **No §4 verdict moves**: DRC/LVS-clean GDS stays
   UNMET/BLOCKED and post-layout PVT stays UNMET — what changes is only that
   the row's blocker is now a release gate (three merged, unreleased fixes)
   rather than any single open upstream issue. This makes the
   `klayout-tools#1911 remains open` claim two paragraphs above stale as of
   this pass, by about six hours.

   **Update (2026-09-16, later still): #103 has now caught up, and its
   blocker is a bare release gate with no open upstream issue behind it.**
   The paragraph immediately above flagged — correctly at the time — that
   #103 "has not yet caught up to this closure," its most recent dependency
   re-check (2026-09-16T03:53:30Z) predating klayout-tools#1911's
   09:50:34Z closure by about six hours. That claim is now itself stale:
   #103 has since posted two further dependency re-checks,
   **2026-09-16T11:42:31Z** (marker
   `103-blocked-pending-klt-release-gt-v0.5.0-incorporating-ad3f8363`) and
   **2026-09-16T12:26:38Z** (marker
   `103-blocked-pending-klt-release-gt-0.5.0-and-gt-ad3f836`), both of which
   record #1911's closure via klayout-tools#1934 (`ad3f8363`) and restate
   the block as, in the first one's words, "a single release gate now — no
   individual open upstream issue remains." The stale claim is superseded
   here rather than edited away, so the dated trail stays readable.

   Every load-bearing fact in that catch-up was re-verified live this pass
   against the forge and PyPI directly, not taken from #103's comment text:

   - All three tracked upstream gaps are **CLOSED**: klayout-tools#1876
     (`closedAt: 2026-09-16T03:44:54Z`), #1878 (`03:43:13Z`), #1911
     (`09:50:34Z`).
   - The release gate holds on all three surfaces, each checked separately
     so that "still `v0.5.0`" does not rest on one endpoint's quirk:
     `gh api repos/2AMLogic/klayout-tools/tags` tops out at **`v0.5.0`**
     (`6bf56109`); `gh api .../releases` tops out at the same **`v0.5.0`**,
     published 2026-09-15T02:19:49Z with `draft: false` and
     `prerelease: false` (read explicitly — so this is a real published
     release, not a draft or pre-release being miscounted in either
     direction); and PyPI's `klayout-tools` latest is **`0.5.0`**, exactly
     what `layout/requirements.txt` already pins. `gh api
     .../compare/v0.5.0...ad3f8363` reports `status: ahead`,
     `ahead_by: 61`, `behind_by: 0`.
   - **The gate is currently untracked upstream**: no *open*
     `2AMLogic/klayout-tools` issue asks for a release past `v0.5.0`
     (searched this pass). The tool's tracker does have closed precedent for
     exactly this friction shape — klayout-tools#342, #953, #1020 and #1249
     were each filed when a release-pinned consumer needed behavior that was
     merged but untagged — so the absence is a tracking gap, not evidence
     that the gate is not real. Filing (or not) is #103's call under the
     friction protocol, not this compilation's.
   - #103 itself is still **OPEN** and still carries `loom:blocked`, and no
     open PR in this repo references it (`closedByPullRequestsReferences`
     returns only the merged #227 and #275, per #103's own re-check).

   **No §4 verdict moves and no new layout or simulation work is claimed
   this pass**: the "DRC/LVS-clean GDS, full ADC" row stays **PARTIAL —
   DRC MET, PIN DECLARATION MET, LVS DEVICE MATCH UNMET/BLOCKED** at 98
   mismatches on the current `reports/LATEST`
   (`20260915-234004-76f48b9`), and "Post-layout PVT simulation, full ADC"
   stays **UNMET** — still no extraction-based re-simulation of the
   assembled top level at any corner, under any of the four LVS shapes
   measured so far. The brief's sign-off bar (acceptance criterion 3) is
   therefore still not met; what changed is only the blocker's tracking
   status.

   **Citation-freshness correction (2026-09-16, third pass — the deferred
   `layout/sampling-frontend/` re-point, plus this item's own stale
   heading).** Two residuals, both internal to this document; **no §4 verdict
   moves and no new layout or simulation work is claimed**:

   - **The deferred re-point is discharged.** The 2026-09-15 update above
     explicitly left `layout/sampling-frontend/`'s citation on the pre-bump
     `20260906-230125-0904419` "to the next pass that touches those
     citations." That pass is this one: §3 and this item's own #99 paragraph
     now cite
     [`layout/sampling-frontend/reports/20260915-120718-1e90b14/record.md`](../../layout/sampling-frontend/reports/20260915-120718-1e90b14/record.md),
     which is what `layout/sampling-frontend/reports/LATEST` actually
     resolves to (read from the pointer file this pass, not assumed).
     Verified by diffing the two records directly rather than trusting the
     earlier "identical counts" summary: the graded verdicts are indeed
     unchanged — DRC clean (`violation_count=0`), `klt lvs` **match** at
     24/24 devices, 17/17 nets, 12/12 pins, and all three negative controls
     (body-tie, device-parameter, capacitor top-plate) still correctly report
     `mismatch`. Three things *do* differ and are recorded here rather than
     glossed: the `klt` stamp (0.4.0 → 0.5.0) and DRC-deck hash, the MiM-cap
     geometry growth already described earlier in this item (the block's own
     compose bbox `y1` 58.05 → 58.97 µm, the same +0.92 µm), and the
     capacitor top-plate negative control's mismatch *count* (9 → 4, category
     mix changed). The last of these is a negative control, so only its
     `mismatch` outcome is load-bearing — it still holds — but the count is
     not identical, which the earlier summary's "at the same counts" wording
     did not distinguish. A superseded record ID remains valid for the
     v0.4.0-era claims it was minted for; `20260915-121529-1e90b14` is *not*
     used here, being a concurrent v0.4.0 run (PR #277) that `reports/LATEST`
     correctly does not point at despite its later wall-clock name.
   - **This item's own heading and lede were stale by ten days.** They read
     "Top-level layout does not exist" / "No assembled, DRC/LVS-clean GDS for
     `sar_adc_top` exists in this repo" — true when first written, false
     since PR #174 (2026-09-06) committed a composed, `klt drc`-clean,
     connectivity-verified `sar_adc_top.gds`, as this item's own update trail
     and §4's Area row have said since. §3 carried the same stale bolded lede
     ("No top-level assembled ADC layout (GDS) exists yet") immediately above
     its own "Top-level assembly has since landed" update. Both are corrected
     to state the *current* gap. This is a presentation fix, not a status
     change: the brief's two sign-off-bar rows in §4 are **UNMET** before and
     after, because what is missing was never the GDS itself but the `klt
     lvs` device-level match (98 mismatches, klayout-tools#1878's capability
     gap) and any post-layout PVT re-simulation (never run, at any corner).
     Correcting a stale heading *upward* is not relaxing a spec row — no
     target was loosened and no unmet row was re-graded.

   **Update (2026-09-16, later still — the release gate is unchanged in kind
   but has grown in content; three further LVS/extract fixes now sit behind
   it, one of them in this item's own module).** The update above recorded
   the gate at `ahead_by: 61` (`v0.5.0`…`ad3f8363`). Re-checked live this
   pass, on all three surfaces separately, as before: `gh api
   repos/2AMLogic/klayout-tools/tags` still tops out at **`v0.5.0`**; `gh api
   .../releases/latest` still returns **`v0.5.0`**, published
   2026-09-15T02:19:49Z; and PyPI's `klayout-tools` latest is still
   **`0.5.0`** (its full release list is `0.1.0`–`0.5.0`, newest uploaded
   2026-09-15T02:19:59Z), exactly what `layout/requirements.txt` pins. **No
   release has happened** — but `gh api .../compare/v0.5.0...main` now
   reports `status: ahead`, **`ahead_by: 79`**, `behind_by: 0`, head
   `208203d6` (2026-09-16T19:28:24Z), so eighteen further commits have landed
   upstream since `ad3f8363`. Three of them touch the LVS/extract surface
   this item's blocker lives on, and each is recorded here with what it does
   **and does not** mean for this design, checked against this repo's own
   artefacts rather than inferred from the commit messages:

   - **[klayout-tools#1944](https://github.com/2AMLogic/klayout-tools/pull/1944)**
     (commit `08dc79e3`, merged 2026-09-16T17:50:33Z, closes
     klayout-tools#1942) — "recognise round-tripped custom device classes as
     devices, not abstract circuits". This is the one that lands in *this
     item's own module*: its file list includes
     `src/klayout_tools/netlist_capacitor_recovery.py`, the module
     klayout-tools#1876's fix (`c5438290`) introduced — i.e. the upstream
     behaviour whose release would retire this repo's local
     `layout/sar-adc-top/bin/restore-cap-device-class.py` workaround. **It
     does not subsume that workaround, and is not claimed to**: its shape is
     a device class with *no native SPICE element letter* round-tripping
     through an `X … PARAMS:` subcircuit-call card (sg13g2's MoM caps,
     klayout-tools#1466). This design's capacitors are not that shape —
     counted directly in the current `reports/LATEST` artefacts this pass,
     `sar_adc_top.extract.spice` carries **1028 bare `C` cards and zero
     `X … PARAMS:` cards**, which is precisely the #1876 bare-`C` shape the
     local script annotates (it appends the extractor's own
     `sky130_fd_pr__model__cap_mim` class token, verified present on the
     restored `…extract.lvs.spice` cards and matching the reference side's).
   - **[klayout-tools#1943](https://github.com/2AMLogic/klayout-tools/pull/1943)**
     (commit `e6fbd17a`, merged 2026-09-16T18:25:21Z, closes
     klayout-tools#1928) — adds `options.compare_parameters` to scope
     device-class parameter compares. Recorded as *present in the gate*, not
     as a fix for anything here: this assembly's 98 mismatches are
     `device.unmatched: 75`, `net.merged: 12`, `net.split: 10`,
     `topology.flattened: 1` (read from the current record's `lvs.json` this
     pass), none of which is a parameter finding. Whether the new option
     bears on the `combine_devices`-scoping gap is #103's to measure, not
     this compilation's to assert.
   - **[klayout-tools#1947](https://github.com/2AMLogic/klayout-tools/pull/1947)**
     (commit `208203d6`, merged 2026-09-16T19:28:24Z, closes
     klayout-tools#1927) — carries a drawn resistor's L/W onto its written
     `R` card, so that reading a pre-extracted `layout.netlist` back through
     `klt lvs` stops producing false `device.property` findings. That is
     exactly this flow's LVS shape, so it is worth stating explicitly that it
     **does not apply to this design**: grepped this pass, all eight netlist
     artefacts in `reports/20260915-234004-76f48b9/` — the four from the
     recorded compare (layout-side extracted, unfiltered, class-restored, and
     the hierarchical reference) plus the four from the abstract-cells
     experiment — contain **zero `R` cards**, and the record carries no
     `device.property` category.

   **No §4 verdict moves, and no new layout or simulation work is claimed
   this pass**: "DRC/LVS-clean GDS, full ADC" stays **PARTIAL — DRC MET, PIN
   DECLARATION MET, LVS DEVICE MATCH UNMET/BLOCKED** at 98 mismatches on the
   unchanged current `reports/LATEST` (`20260915-234004-76f48b9`), and
   "Post-layout PVT simulation, full ADC" stays **UNMET**. #103 is still
   **OPEN** and still `loom:blocked` (re-read this pass). The blocker remains
   what the update above established — a bare release gate, with no open
   upstream issue behind it (re-searched this pass: zero open
   `2AMLogic/klayout-tools` issues request a release past `v0.5.0`) — and
   this repo's practice of grading against what is *released*, not what is
   merged, is unchanged. What this update adds is only that the gate's
   contents have grown, including in the module the local capacitor-class
   workaround stands in for.
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

   **Update this pass (2026-09-08): the design-fix follow-up this finding
   implies is now tracked as its own issue, #236**, since this document
   compiles evidence rather than designing circuit fixes — #236 scopes
   either a topology/sizing fix for the bootstrap precharge PFET `Sa`'s
   reverse-`Vds` off-state droop, or adopting DR-006's own deferred
   non-uniform-phase-allocation alternative, gated on re-running this
   campaign's own `--corners` mode (and, if the phase allocation changes,
   the other three mechanisms' `--corners` campaigns too) to confirm any
   fix actually clears the budget at all 9 ratified corners. Not closing
   this open item — #236 is a design task, this document's own job is
   evidence compilation, not circuit design.

   **Update this pass (2026-09-08): issue #236 closed, choosing the
   circuit-fix direction over DR-006's non-uniform-phase-allocation
   alternative** — `design/sampling_frontend.sch`'s uniform one-`CLK`-
   period-per-phase budget is unchanged, so this update is scoped to this
   one mechanism alone; the other three mechanisms' own `--corners`
   campaigns did not need re-running. Instrumenting `BOOST_x` directly
   (rather than inferring from `TOP_x` alone) found TWO independent
   limiters, not one: (1) `Sa`'s gate was tied to `SAMPLE`, a VDD-level
   signal, while `Sa`'s own source is `BOOST_x` (driven to `~VIN + VDD`
   during sampling) — that left `V_sg = BOOST_x - VDD ~= VIN`, an ON device
   discharging the boosted node throughout the sample phase, not the
   leaky-off device the original root-cause trace assumed. Re-gating `Sa`
   from `G_{p,n}` instead (already GND during hold via `Sd`, shorted to
   `BOOST_x` by `Se` during sampling — so `V_sg ~= 0` and `Sa` is genuinely
   off) holds `BOOST_P` flat and moves the tt/27 °C/1.8 V residual from
   23.4 mV to 7.9 mV. (2) With (1) applied, the common-mode reference
   transmission gate `Cmswn/Cmswp` — in series with `Csamp` on the
   acquisition path via the floating `BPREF_x` node — was the limiter that
   remained; widening it from W=1 µm to W=16 µm moved the binding corner's
   (`tt_27c_1.62v`) residual from 30.2 mV (`Sa` fix only) to 0.8 mV, while
   widening `Msw` 4× instead barely helped (7.9 → 3.2 mV at tt/27 °C/
   1.8 V) — confirming the gate, not the sampling switch, as the limiter.
   Re-running the full ratified PVT grid with both fixes applied
   ([`sim/sampling-acquisition-settling/records/20260908-051436-6ccd72d.md`](../../sim/sampling-acquisition-settling/records/20260908-051436-6ccd72d.md),
   supersedes `records/20260906-211700-00d26af.md`): **all 9/9 ratified
   corners now clear the DR-006 worst-case (12 MHz) phase budget**, worst
   case `tt_27c_1.62v` at 0.380 mV (~0.2× the half-LSB) vs. that same
   corner's pre-fix 67.190 mV (~38.2×); every other corner lands at or
   below 0.001 mV. This removes the sampling front end's own acquisition
   from the list of reasons a uniform-phase DR-006 allocation could not
   hold at the fast (12 MHz) end of the DRAFT range — it is no longer the
   standout bottleneck the pre-#236 schematic made it, alongside
   mechanisms (a)–(c) above. Three things this fix touches are explicitly
   NOT re-derived by it, and remain open follow-up work: `sim/vcm-drive-
   budget/`'s R_source/C_decouple budget (a wider `Cmsw` draws more peak
   current from the shared `VCM` rail every SAMPLE assertion), and
   `layout/sampling-frontend/`'s previously LVS-clean match and
   `layout/sar-adc-top/`'s composition of it (both now stale against the
   schematic's new `Sa` gate net and `Cmsw` width).

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
6. **`VCM` drive-impedance/decoupling budget: as of this pass, quantified at
   every ratified corner on all four legs (bare `R_source` and `C_decouple`,
   each at both the worst-case and legacy windows) — the "still
   single-corner-only" gap this item tracked is now closed; the item stays
   open only because no on-chip `VCM` buffer/reference network exists yet
   for this budget to size.**
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
     ≤ 0.1 LSB, **at the `tt`/27 °C/1.8 V point only** (see the full-grid
     update below for how this holds across the ratified PVT grid).
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
     error to ≤ 1 provisional LSB. (The `≥` is too generous — see the
     full-grid `C_decouple` update below, which reproduces this same sweep
     and finds the next swept point up, 1000 pF, already back outside
     1 LSB at this corner.)
   - This is a first-pass, single-corner budget, not a fabrication-ready
     spec: switch `R_on` (which sets the effective time constant this
     mechanism depends on) varies materially with process/temperature, so a
     full PVT sweep of this same budget is still open (same class of gap as
     #28's corner campaigns for the rest of this sub-block). It also does not
     establish what `R_source`/`C_decouple` an actual on-chip `VCM`
     buffer or off-chip reference network would present — no such buffer
     exists in this design yet. What it newly establishes is the *target*
     such a (not-yet-designed) block would need to meet.

   **Update this pass (2026-09-07): the bare (undecoupled) `R_source` budget
   at the worst-case (83.333 ns) window was taken to the full ratified PVT
   grid** — the same 9-point one-at-a-time (OAT) sweep (process
   `{ff, fs, sf, ss, tt}` × temperature `{−40, 27, 125} °C` × supply
   `{1.62, 1.8, 1.98} V`) every other mechanism in this section now uses —
   added to `sim/vcm-drive-budget/run_vcm_drive_budget.py` as a new
   `--corners` mode alongside the existing single-corner default
   ([`sim/vcm-drive-budget/records/20260907-052526-f589273.md`](../../sim/vcm-drive-budget/records/20260907-052526-f589273.md)).
   Scope is deliberately narrower than the single-corner pass above: only
   the bare (undecoupled) `R_source` sweep at the worst-case window is
   repeated per corner; the legacy (400 ns) window and the `C_decouple`
   sweep remain single-corner (`tt`/27 °C/1.8 V) only, deferred to a future
   pass. **This is the opposite outcome from the CDAC-settling, comparator,
   and sequencer mechanisms above (§7 Item 2), whose single-corner margins
   all held up as PVT-complete comfortably — here the single-corner figure
   under-states the real worst case**: the `tt`/27 °C/1.8 V point in the
   grid reproduces the single-corner record's own ≤ 10 kΩ figure exactly,
   but the binding corners across the full grid — `fs_27c_1.80v` and
   `tt_27c_1.62v`, tied — are ≤ 1 kΩ, **10× tighter**. The loosest corners
   — `ss_27c_1.80v` and `tt_-40c_1.80v`, tied — are ≤ 30 kΩ, so the bare
   1-LSB budget spans a full **30× across the ratified grid**, confirming
   the single-corner caveat ("switch `R_on` varies materially with
   process/temperature") was not overstated: this budget is genuinely far
   from corner-invariant. A future on-chip `VCM` buffer or off-chip
   reference network sized only against the `tt`/27 °C/1.8 V figure would
   under-budget the real worst-case corner by an order of magnitude. This
   does not violate any ratified spec row — `spec/target-spec.md` is
   entirely DRAFT, and no on-chip `VCM` buffer exists yet to size against
   this budget in the first place — but it sharpens, not merely narrows,
   the open item: any future full-PVT pass over the legacy (400 ns) window
   (already shown, single-corner, to be the *more* demanding case for this
   mechanism than the worst-case window) is a natural, and now higher-
   priority, next step.

   **Update this pass (2026-09-07, second full-grid campaign): the legacy
   (400 ns) window's own bare `R_source` budget was also taken to the full
   ratified PVT grid** — closing the "higher-priority next step" flagged
   immediately above, via a new `--window legacy` option added to the same
   `--corners` mode
   ([`sim/vcm-drive-budget/records/20260907-090200-7768162.md`](../../sim/vcm-drive-budget/records/20260907-090200-7768162.md)).
   Scope matches the worst-case-window full-grid pass above: only the bare
   (undecoupled) `R_source` sweep is repeated per corner, over the legacy
   window's own reduced 3-point sweep list (`{0, 10, 100} kΩ`, the same
   reduced-runtime subset the single-corner record already used for this
   window, since the legacy window's tran runs cover ~5× more simulated
   time per point than the worst-case window's); the `C_decouple` sweep
   remains single-corner (`tt`/27 °C/1.8 V) only.

   **Result, stated plainly rather than smoothed over — the legacy window's
   own single-corner finding of ≤ 0 Ω (zero margin) is itself
   corner-dependent, not a uniform floor**: 4 of the 9 ratified corners
   (`tt_27c_1.80v`, `fs_27c_1.80v`, `tt_125c_1.80v`, `tt_27c_1.62v`)
   reproduce that same ≤ 0 Ω floor — offering zero margin for any nonzero
   drive impedance at those corners — but the remaining 5 corners recover a
   positive budget: `ss_27c_1.80v` and `ff_27c_1.80v` at ≤ 10 kΩ, and
   `sf_27c_1.80v`, `tt_-40c_1.80v`, and `tt_27c_1.98v` at ≤ 100 kΩ
   (right-censored — every value up to the largest swept stayed under
   threshold, so the true budget for those three corners is ≥ 100 kΩ, not
   necessarily equal to it). **This is the opposite shape from the
   worst-case-window full-grid finding above**: there, the single-corner
   `tt`/27 °C/1.8 V point was the LOOSEST corner and the full grid tightened
   it by 10×; here, the single-corner `tt`/27 °C/1.8 V point is one of the
   TIGHTEST (worst) corners, tied with three others at the zero-margin
   floor, while a different subset of the grid (the `sf` process corner,
   cold temperature, and high supply) recovers substantial margin instead.
   Because `tt`/27 °C/1.8 V happens to already sit at the binding floor for
   this window, a future on-chip `VCM` buffer or off-chip reference network
   sized only against that single point would, for the legacy window
   specifically, not under-budget the true worst case — but this is
   coincidental to this window's own corner shape, not a general property:
   a design sized against a *different* single corner (e.g. `sf`'s own
   generous 100 kΩ headroom) would badly under-budget the four zero-margin
   corners. This sharpens, rather than merely confirms, the open item: this
   budget is genuinely non-monotonic across the grid at the legacy window,
   not simply "the same everywhere" or "worse everywhere" as either
   window's own single-corner record alone could have shown — any eventual
   buffer/reference-network sizing must be checked against the full grid,
   not any single assumed-representative corner. With both full-PVT-grid
   `R_source` sweeps now complete, the only remaining single-corner-only
   leg of this budget is the `C_decouple` sweep (both windows).

   **Update this pass (2026-09-07, third full-grid campaign): the
   `C_decouple` sweep at the worst-case (83.333 ns) window was also taken
   to the full ratified PVT grid** — closing that leg at this window, via a
   new `--sweep decouple` option on the same `--corners` mode
   ([`sim/vcm-drive-budget/records/20260907-104958-a546200.md`](../../sim/vcm-drive-budget/records/20260907-104958-a546200.md)).
   Scope note that matters for reading the numbers: unlike the two bare
   `R_source` full-grid passes, **each corner here is decoupled against its
   OWN marginal `R_source`**, re-derived from that same corner's own bare
   sweep in the same invocation rather than borrowed from the
   `tt`/27 °C/1.8 V point — the bare budget was already shown above to span
   30× across this grid, so a single borrowed resistance would not be the
   marginal case at most corners. Those re-derived marginal resistances
   reproduce the bare full-grid campaign's own per-corner shape
   (3 kΩ at the two tightest corners `fs_27c_1.80v`/`tt_27c_1.62v`, 100 kΩ
   at the loosest `tt_-40c_1.80v`), so the two campaigns are consistent, not
   competing.

   **Result: at every one of the 9 ratified corners, decoupling alone does
   bring the differential error back inside 1 provisional LSB — but the
   capacitance required is not corner-invariant, and the error is not
   monotonic in `C_decouple`.** The working values found span three orders
   of magnitude: 1 pF at `ss_27c_1.80v` and `tt_-40c_1.80v`, 10 pF at
   `fs_27c_1.80v`/`tt_125c_1.80v`/`tt_27c_1.62v`, 100 pF at
   `tt_27c_1.80v`/`ff_27c_1.80v`/`tt_27c_1.98v`, and 1000 pF
   (right-censored — every swept value stayed under threshold) at
   `sf_27c_1.80v`. The `tt`/27 °C/1.8 V point reports ≤ 100 pF, and its
   whole swept row set is numerically identical to the single-corner
   record's own `C_decouple` table (same `R_source` = 30 kΩ, same five
   points, same values to the digit) — the two records reproduce each other
   rather than merely agreeing in verdict. **One correction that falls out
   of that comparison**: the third bullet above restates the single-corner
   record's own "a decoupling capacitor ≥ 100 pF … recovers the
   differential error to ≤ 1 provisional LSB" phrasing, and the `≥` is
   slightly too generous — at that very corner the next swept point up,
   1000 pF, is already back *outside* 1 LSB (−1.0271 LSB). Read that bullet
   as "100 pF, the largest swept value that works", not as an open-ended
   floor. **Stated plainly rather than smoothed over**:
   because the single-corner record already established that this error is
   *not* monotonic in `C_decouple` (a larger cap lengthens the same node's
   settling time constant as much as it stiffens its DC impedance), each
   per-corner figure names a value already confirmed to work at that
   corner's own marginal `R_source`, **not** a floor above which every
   larger value also works — the full-grid data shows this directly, e.g.
   at `ss_27c_1.80v` the 1 pF point is inside 1 LSB while 10 / 100 / 1000 pF
   are all outside it. A future on-chip `VCM` buffer or off-chip reference
   network therefore cannot be sized by picking the largest number in this
   table and assuming it covers every corner; the sizing has to be checked
   per corner, against both axes. This does not violate any ratified spec
   row (`spec/target-spec.md` is entirely DRAFT, and no such buffer exists
   yet to size), and it does not close this open item: **the legacy (400 ns)
   window's own `C_decouple` sweep is now the sole remaining
   single-corner-only leg of this budget**, and the legacy window was
   already shown, single-corner, to be the *more* demanding case for this
   mechanism — so that pass is the natural next step, on the same
   one-window-per-pass precedent the two bare `R_source` full-grid passes
   established.

   **Update this pass (2026-09-08): the legacy (400 ns) window's own
   `C_decouple` sweep was also taken to the full ratified PVT grid** —
   closing the "sole remaining single-corner-only leg" flagged immediately
   above, via `--corners --window legacy --sweep decouple`, the same option
   combination the worst-case-window `C_decouple` campaign already
   established
   ([`sim/vcm-drive-budget/records/20260908-021006-f48a228.md`](../../sim/vcm-drive-budget/records/20260908-021006-f48a228.md)).
   Scope matches that precedent exactly: each of the 9 ratified corners is
   decoupled against its OWN marginal `R_source`, re-derived from that
   corner's own bare legacy-window sweep in the same invocation (reproducing
   the legacy-window bare-`R_source` full-grid campaign's own per-corner
   shape: 10 kΩ at four corners, 100 kΩ at the other five) — never a value
   borrowed from the `tt`/27 °C/1.8 V point. **Result: decoupling alone
   brings the differential error inside 1 provisional LSB at all 9/9
   ratified corners at this window too**, closing out the finding this
   item's own legacy-window bare-`R_source` pass left open (that window
   offers zero bare-impedance margin at 4 of 9 corners) — a decoupling
   capacitor rescues every one of those corners when sized per-corner.
   The working values span three orders of magnitude across the grid
   (1 pF at `ss_27c_1.80v`, 10 pF at `ff_27c_1.80v`/`fs_27c_1.80v`/
   `tt_125c_1.80v`/`tt_27c_1.62v`, 100 pF at `tt_27c_1.80v`, 1000 pF,
   right-censored, at the remaining three: `sf_27c_1.80v`/`tt_-40c_1.80v`/
   `tt_27c_1.98v`), the same
   non-corner-invariant, non-monotonic-in-`C_decouple` shape the
   worst-case-window campaign already established — so, as with that
   campaign, no single capacitor value read off this table covers every
   corner; sizing still has to be checked per corner, against both axes.
   **With all four legs of this budget (bare `R_source` and `C_decouple`,
   each at both windows) now PVT-complete, this open item is no longer
   gated on corner coverage** — it stays open only because no on-chip `VCM`
   buffer or off-chip reference network exists yet in this design to size
   against the target these four campaigns jointly establish (§2.2).

   No claim here is graded against a ratified spec row (`spec/target-spec.md`
   is entirely DRAFT, #1/#27; the DR-006 acquisition window is itself
   downstream of the DRAFT sample-rate row, Item 2 above).

   **Update this pass (2026-09-15): every figure above was measured against
   the pre-issue-#236 sampling front end and is now superseded.** Issue #236
   (§4/§7 Item 2, PR #246) moved the bootstrap precharge PFET `Sa`'s gate
   from `SAMPLE` to `G_{p,n}` and widened `Cmswn`/`Cmswp` from `W=1 µm` to
   `W=16 µm` — both devices this budget's own harness drives current
   through, so every number above (the 30× corner spread, the 4/9
   zero-margin legacy-window corners, the per-corner marginal-`R_source`
   values feeding the `C_decouple` tables) was measured against a netlist
   this design no longer uses. Follow-up issues #245 and #248 (PRs #249 and
   #250, both merged 2026-09-08) re-ran all four legs — bare `R_source` and
   `C_decouple`, at both the worst-case and legacy windows — against the
   post-#236 DUT fragment, plus the single-corner seed:
   - Single-corner (`tt`/27 °C/1.8 V) re-derivation:
     [`sim/vcm-drive-budget/records/20260908-074408-80df05e.md`](../../sim/vcm-drive-budget/records/20260908-074408-80df05e.md)
     (supersedes `20260905-201703-f012255.md`).
   - Full-grid bare `R_source`, worst-case window:
     [`sim/vcm-drive-budget/records/20260908-100413-f3e2914.md`](../../sim/vcm-drive-budget/records/20260908-100413-f3e2914.md)
     (supersedes `20260907-052526-f589273.md`).
   - Full-grid bare `R_source`, legacy window:
     [`sim/vcm-drive-budget/records/20260908-101358-f3e2914.md`](../../sim/vcm-drive-budget/records/20260908-101358-f3e2914.md)
     (supersedes `20260907-090200-7768162.md`).
   - Full-grid `C_decouple`, worst-case window:
     [`sim/vcm-drive-budget/records/20260908-113002-f3e2914.md`](../../sim/vcm-drive-budget/records/20260908-113002-f3e2914.md)
     (supersedes `20260907-104958-a546200.md`).
   - Full-grid `C_decouple`, legacy window:
     [`sim/vcm-drive-budget/records/20260908-115336-f3e2914.md`](../../sim/vcm-drive-budget/records/20260908-115336-f3e2914.md)
     (supersedes `20260908-021006-f48a228.md`).

   **The post-#236 result is a materially different, and looser, budget —
   stated plainly rather than smoothed over**: at every one of the 9
   ratified corners, both windows, the bare `R_source` budget now comes back
   right-censored at ≤ 100 kΩ for both the 1-LSB and 0.1-LSB thresholds (a
   flat 1.0× worst-to-best spread — the pre-#236 30× corner spread and the
   legacy window's 4-of-9 zero-margin corners are both gone), and the
   `C_decouple` budget comes back right-censored at ≤ 1000 pF at all 9
   corners, both windows (up from the pre-#236 three-orders-of-magnitude
   spread, 1 pF–1000 pF). Every swept value in the current sweep lists stays
   inside the 1-LSB bound at every corner, so these are right-censored
   floors, not exact budgets — the true headroom is `>= these values`,
   consistent with (not contradicting) the earlier finding that a wider
   `Cmsw` was the fix for the sampling acquisition-window bottleneck this
   same issue (#236) closed. This does not change the open item itself (no
   on-chip `VCM` buffer or off-chip reference network exists yet to size
   against this target) but it does mean a future buffer sized against the
   pre-#236 numbers above would have been needlessly over-specified — any
   such sizing work should read the current-DUT records above, not the
   superseded ones this item's own body still narrates in detail (kept,
   per `CLAUDE.md`'s append-only evidence convention, as the historical
   record of the pre-#236 finding — not as the current budget).

   A related, narrower gap surfaced during this re-derivation and was
   folded in by the same follow-up (#248 via PR #250, not itself a VCM
   drive-budget change): `layout/sampling-frontend-wells/` (issue #122's
   well-isolation composition study) still encoded the pre-#236
   `Sa`/`Cmsw` connectivity/sizing in its own reference netlist; that
   sub-block's own claim (PMOS body-tie domain isolation) depends on
   neither changed field, so it was brought forward to track the current
   schematic rather than left pinned, and re-verified LVS-clean against it.
   `layout/sampling-frontend/`'s own composed GDS was independently
   confirmed byte-identical before and after that fold-in, so
   `layout/sar-adc-top/`'s composition (§7 Item 1) needed no further re-run
   beyond the one already described in §4's sample-rate row above.
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

   **Re-checked 2026-09-08**: `https://opencircuitdesign.com/chipalooza/rules-4.html`
   still returns HTTP 404 (the parent `chipalooza/` index itself returns 200
   and still names "Challenge #4" only in the launch-date table, not as a
   published brief). Cross-checked live against 2AMLogic/2am#542's own
   tracking table, which still lists Challenge #4 as "launches 2026-11-09" —
   unchanged from the prior re-check, no date slip either direction. Nothing
   in §2 changes as a result; recorded here only to keep this item's own
   "not silently assumed done" discipline current rather than let the last
   live check go stale.

   **Re-checked 2026-09-15**: `https://opencircuitdesign.com/chipalooza/rules-4.html`
   still returns HTTP 404 (`curl -sI`, this pass); the parent `chipalooza/`
   index still returns HTTP 200. 2AMLogic/2am#542's own tracking table still
   lists row 4 (Sky130, ChipFoundry) as "launches 2026-11-09" — unchanged
   across all three re-checks (2026-09-06, -08, -15). §2's slot-budget
   assumptions therefore still carry no rules-4.html-derived correction; this
   issue's acceptance criterion 4 remains not-yet-triggerable.

   **Re-checked 2026-09-16**: `https://opencircuitdesign.com/chipalooza/rules-4.html`
   still returns HTTP 404 (`curl -sI`, this pass); the parent `chipalooza/`
   index still returns HTTP 200 (`Last-Modified: Sun, 06 Sep 2026 15:06:32
   GMT` — unchanged since well before the prior re-check, so the index
   itself has not been touched either). 2AMLogic/2am#542's own tracking
   table still lists row 4 (Sky130, ChipFoundry) as "launches 2026-11-09" —
   unchanged across all four re-checks (2026-09-06, -08, -15, -16). §2's
   slot-budget assumptions therefore still carry no rules-4.html-derived
   correction; this issue's acceptance criterion 4 remains
   not-yet-triggerable.

8. **Whole-ADC (end-to-end) code correctness is not yet demonstrated — a
   campaign exists, found real defects, several are already fixed, and two
   remaining fixes are operator-decision items.** Added this pass: this
   document previously stated (Sample rate row, §4) that "no full-hierarchy
   campaign exists" for an end-to-end conversion check. That is now stale —
   `sim/full-conversion-transient/` (issue #254, opened 2026-09-10) drives
   the transistor-level `sar_adc_top` through complete conversions at the
   DR-006 worst-case 12 MHz clock across the ratified 9-corner grid, and its
   first record (`20260910-190240-2d1d196.md`) found **0/9 corners
   code-correct** — every corner decoded the near-full-scale inputs
   (`±0.78·V_REF`) to a saturated 1023/0, with the mid-scale inputs already
   off by 1 LSB.

   Root-causing that FAIL drove five design-fix issues, in order: #257
   (comparator reset and bit-capture register shared one `CLK` edge, so the
   loop never converged — fixed, `CLKN`-strobed capture, PR #264), #258
   (`sar_sequencer`'s own `.subckt` port list omitted `VGND`/`VPWR`, so it
   floated once nested — fixed, PR #261), #259 (a node-level trace pinned
   the residual saturation on comparator reset/capture-edge ordering — the
   mechanism #257 then fixed, PR #262), #263 in two passes (no trial
   perturbation and no per-conversion CDAC clear, DR-008, PR #266; then a
   comparator differential-output load imbalance plus a half-LSB
   quantizer-alignment gap, DR-009, PR #270) and #265 (confirmed, by a
   targeted common-mode trace, that the near-full-scale inputs still fail
   under a distinct mechanism — see below). Every fix is evidenced by its
   own `sim/full-conversion-transient/records/` entry, cross-referenced from
   DR-008 and DR-009.

   **Two root causes are now root-caused, evidenced, and confirmed still
   open — but are architecture/sizing decisions, not compilable design
   fixes, so this document reports them rather than resolving them**,
   matching this issue's own established scope (compile evidence, file
   design gaps as issues, do not design circuit fixes here — the same
   pattern used for issue #236 in Item 6 above):
   - **#267** — decision-directed single-side CDAC switching (DR-008)
     freezes the inactive array side's top plate at its sampled value for
     the whole conversion; at a near-full-scale differential input the
     resulting common-mode droop (measured 600–755 mV, ~30× DR-004's ~23 mV
     comparator common-mode-headroom margin) saturates the comparator. Not
     a PVT-corner effect (present even at `tt`/27 °C/nominal) and not a
     `cdac_array` defect (the array itself is monotonic and correctly
     polarized in isolation, per `sim/cdac-array-transfer/`) — an
     integration-level architecture choice.
   - **#269** — the array's absolute gain is ~0.99 LSB/unit (a ~0.8–1.0 %
     gain error), root-caused to top-plate parasitic capacitance
     (dominated by the comparator's own ~17 fF input-pair gate area) being
     comparable to the array's own `C_u` (~7 fF, DR-003 Item 3) — "this
     array's unit capacitor is smaller than the parasitic it drives," a
     sizing relationship no offset/timing/logic change can correct.

   Both #267 and #269 carry `loom:operator-only` + `loom:operator-decision`
   (verified live, this pass) — this repo's escape-hatch labels for a
   defensible-but-consequential authority call, not a mechanically checkable
   fix, so autonomous dispatch correctly does not attempt either. Until one
   is chosen and lands, **no full 9-corner re-run of
   `sim/full-conversion-transient/` exists against the current (post-DR-009)
   schematic** — the most recent full corner-grid record,
   [`sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md`](../../sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md)
   — which is also what `sim/full-conversion-transient/records/LATEST`
   resolves to, verified against the pointer file this pass — still
   predates PR #270's merge (2026-09-12T02:07:51Z) and still reports
   0/9 corners code-correct at the near-full-scale inputs it does not yet
   cover the fix for. **Citation correction, this pass**: the pointer file
   is `records/LATEST`, not `reports/LATEST` as this item previously wrote
   it (`sim/` campaigns record under `records/`; `reports/` is the `layout/`
   flows' convention), and this item now also gives the record's full path
   so the citation does not depend on the pointer. A *later-timestamped*
   record exists in the same directory —
   [`20260912-011519-9aaf1ca.md`](../../sim/full-conversion-transient/records/20260912-011519-9aaf1ca.md),
   a diagnostic mechanism-trace record ("issue #263 (second pass) /
   DR-009 — diagnostic/mechanism evidence, NOT a spec row and NOT a corner
   campaign," per its own `Claim` line) created 2026-09-12T01:15Z, *before*
   PR #270 merged — but `LATEST` deliberately does not point at it: both
   files landed in the same commit (`9a256a1`, PR #270's merge), which set
   `LATEST` to the corner campaign rather than to that narrower diagnostic,
   and nothing has moved `LATEST` since. It is the evidence that informed
   the DR-009 fix, not a post-fix corner re-run. No full corner-grid record
   exists after PR #270 at all, so the conclusion above is unchanged in
   substance. The **Sample rate** row in §4 is updated this pass
   to reflect this campaign's existence and status rather than asserting
   none exists.

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

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
implemented entirely on Sky130's 1.8 V core transistor flavor
(`nfet_01v8`/`pfet_01v8`) plus the MiM capacitor its CDAC array and sampling
front end are built from (`cap_mim_m3_1`), with `sky130_fd_sc_hd` standard
cells for all of its digital logic — the SAR sequencer and the top level's own
SEL-drive/readout glue alike (§3). Provisional sample rate range: 100 kS/s – 1
MS/s (DRAFT, not yet re-derived from settling data — see §4).

**That device inventory is re-derived, not asserted** (check 20 of the
[citation gate](check_proposal_citations.py), added 2026-09-25): this design
instantiates **3** `sky130_fd_pr` primitive flavours — `cap_mim_m3_1`,
`nfet_01v8`, `pfet_01v8` — and that set is compared, in both directions,
against every instance line of
[`design/sar_adc_top.spice`](../../design/sar_adc_top.spice) (the full
hierarchy, not just the top cell). This is the sentence §2.1's rail position
rests on: a thick-oxide `nfet_g5v0d10v5`/`pfet_g5v0d10v5` pass device entering
the netlist — the DR-002 tripwire §2.1 names — fails CI here instead of
leaving §2.1's "no device above the 1.8 V core rail" claim to a reader's
attention. `design/regen_netlist.sh --check` carries its own DR-001
device-flavour gate over the same netlist, against a hard-coded allow-list —
but it runs only in `.github/workflows/ci.yml`'s PDK-gated `pdk-smoke` job
(nightly / `workflow_dispatch` / an opt-in `run-pdk-smoke` label), whereas
this check runs in `Repo checks` on every pull request, and it grades the
*document* rather than the netlist. Neither substitutes for the other.

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
  (`nfet_01v8`/`pfet_01v8`), at the same 1.8 V supply point as the digital
  logic. There is no separate 3.3 V (or higher) analog rail anywhere in this
  design. **One voltage, two domains** (issue #355,
  [DR-010](../../spec/decision-records/DR-010-digital-supply-domain-partition.md)):
  the analog side is on `VDD`/`GND` and the standard cells on `VPWR`/`VGND`,
  which are separate nets with separate top-level pins and are deliberately
  not tied on-die — a partition of supply *domains*, not of supply
  *voltages*, so every §4 row below is still reported at one supply point.
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
| `VDD` | supply | 1.8 V analog rail | — (rail, not a slot line item) | The **analog** supply: sampling front end, CDAC array, comparator, and the DR-009 offset network. Same 1.8 V supply point as the digital rail below, but a **separate domain** — see the `VPWR`/`VGND` row and §2.1 |
| `VINP`, `VINN` | in, dedicated (2 pads) | dedicated pad (budget: 0–4) | 2 | Differential analog input, driven onto the sampling front end (`design/sampling_frontend.sch`), 0–`V_REF` single-ended range each side |
| `VREFP`, `VREFN` | in, dedicated (2 pads) | harness-supplied bandgap reference — **mismatch flagged below** | 2 | Differential reference into the CDAC array's bottom-plate switches. **Open item**: this design's reference is differential (two nodes), while the common structure names a single "bias/bandgap reference." Whether the harness can supply a differential pair, or whether this design would need to derive `VREFN` locally from a single-ended harness reference, is unresolved — named here, not guessed (see §7) |
| `VCM` | in, dedicated | dedicated pad (budget: 0–4) | 1 | Common-mode bias, `V_REF/2 = 0.9 V` nominal. Every functional testbench in this repo still drives it from an ideal source — no on-chip `VCM` buffer/reference network exists in this design. A drive-impedance/decoupling *budget* now exists, full-ratified-PVT-grid on every one of its four legs (bare `R_source` at both the worst-case and legacy windows, `C_decouple` at both windows) — **re-derived this pass (2026-09-15) against the post-issue-#236 sampling front end** (the `Sa` gate-net move and `Cmsw` `W=1 µm`→`W=16 µm` widening that fixed the sampling acquisition-window bottleneck, §4/§7 Item 2, also changed this budget's own DUT netlist, per issues #245/#248 via PRs #249/#250). All four legs, at every one of the 9 ratified corners, now come back right-censored at ≤ 100 kΩ bare `R_source` (both the 1-LSB and 0.1-LSB thresholds) and ≤ 1000 pF `C_decouple` — a materially looser, corner-invariant result than the pre-#236 data superseded below (which spanned 1 kΩ–30 kΩ and hit zero bare-impedance margin at 4/9 legacy-window corners) ([`sim/vcm-drive-budget/records/20260908-074408-80df05e.md`](../../sim/vcm-drive-budget/records/20260908-074408-80df05e.md), [`sim/vcm-drive-budget/records/20260908-100413-f3e2914.md`](../../sim/vcm-drive-budget/records/20260908-100413-f3e2914.md), [`sim/vcm-drive-budget/records/20260908-101358-f3e2914.md`](../../sim/vcm-drive-budget/records/20260908-101358-f3e2914.md), [`sim/vcm-drive-budget/records/20260908-113002-f3e2914.md`](../../sim/vcm-drive-budget/records/20260908-113002-f3e2914.md), [`sim/vcm-drive-budget/records/20260908-115336-f3e2914.md`](../../sim/vcm-drive-budget/records/20260908-115336-f3e2914.md); each `Supersedes` its pre-#236 counterpart, [`sim/vcm-drive-budget/records/20260905-201703-f012255.md`](../../sim/vcm-drive-budget/records/20260905-201703-f012255.md) / [`20260907-052526-f589273.md`](../../sim/vcm-drive-budget/records/20260907-052526-f589273.md) / [`20260907-090200-7768162.md`](../../sim/vcm-drive-budget/records/20260907-090200-7768162.md) / [`20260907-104958-a546200.md`](../../sim/vcm-drive-budget/records/20260907-104958-a546200.md) / [`20260908-021006-f48a228.md`](../../sim/vcm-drive-budget/records/20260908-021006-f48a228.md), respectively), quantifying — not yet closing — the same class of gap the port-parity sibling `gf180-sar-adc` names for its own `V_CM` row (see §7 Item 6) |
| `CLK` | in | digital control input (budget: ≤24) | 1 | Master clock; provisional range 1.2–12 MHz (DRAFT, [DR-006](../../spec/decision-records/DR-006-sar-sequencer-bit-count-and-timing-budget.md), not re-derived from settling data) |
| `RST_B` | in | digital control input | 1 | Active-low synchronous reset into the ring sequencer |
| `DOUT9..DOUT0` | out | digital test output (budget: ≤12) | 10 | 10-bit parallel output register, `DOUT9` = MSB |
| `BUSY` | out | digital test output | 1 | Conversion-in-progress strobe |
| `VPWR`, `VGND` | supply | 1.8 V digital rail + its return | — (rails, not slot line items) | The **digital** supply for the two `sky130_fd_sc_hd` standard-cell macros (`sar_sequencer`, `seln_inverters`). Added to the block's interface on 2026-09-24 by issue #355 / [DR-010](../../spec/decision-records/DR-010-digital-supply-domain-partition.md): the rails are deliberately **not** tied to `VDD`/`GND` *in metal* on-die (digital switching is coincident with the comparator decision by construction, so a shared metal rail would put the standard-cell bank's switching current on the comparator's own supply), and before #355 they reached no top-level supply at all — which `klt erc` graded as a structural power-delivery failure (§3, §7 item 9). Same 1.8 V supply point as `VDD`; the star point between the two domains is off-die. `VGND` and `GND` are nevertheless **one electrical node** in bulk sky130 (see the `GND` row) |
| `GND` | supply | analog return | — (rail, not a slot line item) | The **analog** return: the node `sampling_frontend`, `cdac_array` and `comparator` all return through. Added to the block's interface on 2026-09-24 by issue #362 / [DR-012](../../spec/decision-records/DR-012-analog-ground-pad.md) — before it, `VDD` was a port and its return was not, so the block had `.GLOBAL GND` and no terminal a package could bond to. The pad is the **p-substrate node's own drawn front-side terminal, not a second node**: bulk sky130 offers no isolation, and this block's own composed extraction reports `GND` and `VGND` as one net (`GND|VGND|VSS`, 692 devices — the third label is `cdac_array`'s own ground terminal, drawn by issue #377 / [DR-013](../../spec/decision-records/DR-013-analog-ground-mesh.md), joining the same node, not a new one). Two ground pads on one node is the intended shape — two bond points, so the digital return travels off-die rather than through the die's substrate past the comparator |

**Totals against the assumed budget, machine-checked** (check 10 of the
[citation gate](check_proposal_citations.py), added 2026-09-17): **2** of ≤24
digital control inputs (`CLK`, `RST_B`), **11** of ≤12 digital test outputs
(`DOUT9..DOUT0` + `BUSY`), **3** of 0–4 dedicated pads (`VINP`, `VINN`,
`VCM`), and **2** harness-supplied reference lines (`VREFP`, `VREFN`). Each of
those four counts is recomputed from this table's own Count and slot columns
rather than re-added by hand, so a row added, re-counted, or re-categorised
fails CI here instead of leaving a stale total behind — and a row that is
charged against the budget while matching none of the four categories fails
too, so a new signal cannot slip past the totals by being uncategorised. If
the harness cannot supply a differential reference, its two lines must become
dedicated pads as well — **5 dedicated pads against a 0–4 ceiling**, which
exceeds it (that number is gated too, as the dedicated pads plus the
harness-supplied reference lines). This is stated as an open slot-budget risk,
not resolved by assumption (see §7); it cannot be resolved definitively until
`rules-4.html` publishes and states the real per-signal budget categories.

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
  DOUT9 DOUT8 DOUT7 DOUT6 DOUT5 DOUT4 DOUT3 DOUT2 DOUT1 DOUT0 BUSY VPWR VGND \
  GND
```

Nothing is added or dropped in §2.2's mapping above — it is exactly this
netlist's own external port list, categorized against the assumed slot
budget. **That sentence is now machine-checked rather than asserted** (check
10, added 2026-09-17): the quoted `.subckt` line above is compared port for
port and in order against `design/sar_adc_top.spice`'s own, and §2.2's Signal
column is compared against the same list in both directions — a port with no
row, and a row naming something that is not a port, are each a CI failure
naming the signal. This matters because the netlist is *regenerated* from
`design/sar_adc_top.sch` (staleness-checked in CI by `design/regen_netlist.sh
--check`), and this repo does change that schematic: DR-004 Amendment A moved
the comparator's device count, and DR-008/DR-009 changed sub-block interfaces.
A future port change would previously have left §2 describing an interface
this repo no longer builds, with only a hand re-read to catch it — the same
drift class §4's citation checks already gate one section down.

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

**The top level's own glue logic, machine-checked** (check 20 of the
[citation gate](check_proposal_citations.py), added 2026-09-25). The four
sub-blocks above are not the whole design: outside every sub-block,
`design/sar_adc_top.sch` adds **33** `sky130_fd_sc_hd` instances of **6** cell
types — `and2_1` **×18**, `and2b_1` **×1**, `inv_1` **×3**, `mux2_1` **×1**,
`xnor2_1` **×1**, `xor2_1` **×9** — and **8** `sky130_fd_pr` instances of
**3** device types — `cap_mim_m3_1` **×2**, `nfet_01v8` **×2**, `pfet_01v8`
**×4**. Both censuses are recomputed from `design/sar_adc_top.spice`'s own
instance lines and graded in both directions, per cell type, so a glue cell
added, removed, or swapped for another fails CI here. What each group is:

- The **eighteen `and2_1`** are
  [DR-008](../../spec/decision-records/DR-008-cdac-top-level-switching-polarity.md)'s
  decision-directed bottom-plate drive, `SELp<i> = DOUT9 AND DOUT<i>` and
  `SELn<i> = DOUT9N AND DOUT<i>` (`i = 0..8`), with one of the three `inv_1`
  (`xinv_dout9n`) producing `DOUT9N`. Exactly one array side moves per bit
  decision, which is what makes the array's native step 1 LSB/bit rather
  than 2.
- The **nine `xor2_1`** are the read-only offset-binary readout recode
  (`ADCOUT<i> = DOUT<i> XOR DOUT9N`); `ADCOUT<i>` is not a top-level port
  (§2.3) and the conversion loop operates on `DOUT<i>`.
- The **`mux2_1` + `xnor2_1`** pair is
  [DR-009](../../spec/decision-records/DR-009-comparator-output-load-balance-and-half-lsb-offset.md)'s
  matched dummy load on the comparator's otherwise-unloaded `OUTN`, and the
  **`and2b_1` + one `inv_1`** (`xand_halflsb`, `xinv_halflsb`) are that same
  record's half-LSB enable and its complement,
  `HALF_LSB_EN = BUSY AND NOT(PH_B9)`.
- The **third `inv_1`** (`xinv_clkcap`) inverts `CLK` to `CLKN` so the
  comparator is strobed at the end of the evaluate phase rather than its start
  (issue #264) — not a DR-008/DR-009 device.
- All **eight `sky130_fd_pr` instances** are DR-009's half-LSB quantizer-offset
  network (two `cap_mim_m3_1` injection caps and their six drive FETs) — the
  only analog devices this design draws outside a sub-block, and the reason
  §2.2's `VDD` row names "the DR-009 offset network" as a load on the analog
  rail.

**None of those 33 cells is a `SELn<i>` inverter.** Issue #56's original
integration drew `SELn<i> = NOT(DOUT<i>)` as nine dedicated `inv_1`
instances; DR-008 (issue #263, PR #266, 2026-09-11) replaced that
unconditional complementary drive with the `and2_1` pairs above, because a
2-LSB native array step cannot represent every ratified `N = 10`
offset-binary code. This census is gated rather than narrated because the
document did not notice: §3 and §7 below each described the top level's glue
as "the nine `SELn<i> = NOT(DOUT<i>)` glue inverters" for two weeks after
DR-008 landed, and nothing in the citation gate could see it — check 10
grades the *port list*, which DR-008 did not move. See §7 Item 1 for what
that same staleness still costs `layout/seln-inverters/` and the composed
top-level GDS, which is a layout gap rather than a documentation one.

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
[`layout/sampling-frontend/reports/20260924-232823-66dca3c/record.md`](../../layout/sampling-frontend/reports/20260924-232823-66dca3c/record.md)
(current `reports/LATEST`, issue #377's `GND` pin promotion — one `PIN_NETS`
entry, no geometry moved, and one LVS finding fewer because the substrate net
now carries a drawn label; supersedes `reports/20260918-191227-935ce76/`
(issue #326's minimum-area rebuild), which superseded
`reports/20260915-120718-1e90b14/` (PR #275's `klayout-tools` `v0.5.0`
rebuild), `reports/20260906-230125-0904419/` and, before it,
`reports/20260905-204934-f012255/`, all four at the identical DRC/LVS
verdict — the #326 record differs from its predecessor in one respect only,
the width of four isolated met3 via-landing pads, see §7 Item 1's
citation-freshness corrections).
**A top-level assembled ADC layout (GDS) now exists, but is not DRC/LVS-clean
end-to-end** — when this section was first written none existed at all; one
has since landed (PR #174 and successors, see "Top-level assembly has since
landed" below), is `klt drc`-clean and connectivity-verified net-by-net, and
its two remaining gaps are `klt lvs`'s device-level match and the absence of
any post-layout PVT re-simulation. The routed
integration of the four sub-block layouts into one top-level GDS matching
`design/sar_adc_top.sch`'s hierarchy is tracked as issue #103, which is
**still open and, since 2026-09-24, escalated to a human operator** — its
remaining blocker is a ruling, not a dependency an automated re-check can
clear. §7 Item 1 carries the dated tracking-state trail and is now the only
section of this document that names a tracking label at all (check 27 of the
[citation gate](check_proposal_citations.py), added 2026-09-25: until this
pass this sentence carried its own copy of that label, which had been stale
since the escalation, while §7's copy stayed current). All four of
#103's original sub-block dependencies are closed, and #103 has since
shipped a fifth composition-level block it needs directly,
`layout/seln-inverters/` (nine `sky130_fd_sc_hd__inv_1` instances laying out
`SELn<i> = NOT(DOUT<i>)`; DRC-clean and LVS-clean **against its own
hand-written gate-level netlist**, PR #166 — but that netlist is issue #56's
top-level glue, which DR-008 superseded on 2026-09-11 and which the census
above shows the current schematic no longer contains; see §7 Item 1). That
same PR's floorplan/routing
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
the prior record (no silent device-sizing change). #103 itself was still
blocked when that gap closed, on its own not-yet-landed dependency re-check
against #165's closure — but every top-level pin,
including these 18 plus `VDD`, has now been independently verified to have
real, externally-reachable conductor, so the composition/routing plan has
been ready to execute since, and now waits on #103's operator ruling (see
`layout/sar-adc-top/README.md` for the full per-pin geometry investigation).
All roll up under the layout epic #25.

**Sub-block sign-off readouts, machine-checked** (added 2026-09-17). Every
"DRC-clean and LVS-clean" in the paragraph above was, until this pass, prose —
and so was the one §4 row that grades a verdict on it: *Digital
sequencer/output register — physical implementation* reads **MET** on
"place-and-route layout exists and is DRC-clean and LVS-clean", citing only
`layout/sar-sequencer/README.md`, a hand-written file rather than a dated flow
record. No check in this document's [citation gate](check_proposal_citations.py)
could see that claim at all: check 3 grades the records a §4 row cites, and
that row cited none, while check 9 recomputed DRC/LVS figures for exactly one
flow, `layout/sar-adc-top/`. The five sub-block flows the top-level
composition is built from now state their live verdicts in the same gated
sentence form, each recomputed field by field from that flow's own
`reports/LATEST` `drc.json`/`lvs.json` by check 9 (`python3
docs/chipalooza/check_proposal_citations.py --stats` prints them, so a re-run
that moves a number is pasted back rather than hand-transcribed):

> - on the record `layout/cdac-array/reports/LATEST` resolves to, `klt drc`
> reports status **clean** with **0** violations, and `klt lvs` reports status
> **match** with **1** mismatches and **0** errors; devices **1060** layout /
> **1060** reference / **1060** matched; nets **42** / **42** / **42**
> matched; pins **24** / **24** / **24** matched; by category `topology: 1`.
> - on the record `layout/comparator/reports/LATEST` resolves to, `klt drc`
> reports status **clean** with **0** violations, and `klt lvs` reports status
> **match** with **1** mismatches and **0** errors; devices **11** layout /
> **11** reference / **11** matched; nets **10** / **10** / **10** matched;
> pins **7** / **7** / **7** matched; by category `topology: 1`.
> - on the record `layout/sampling-frontend/reports/LATEST` resolves to, `klt
> drc` reports status **clean** with **0** violations, and `klt lvs` reports
> status **match** with **1** mismatches and **0** errors; devices **24**
> layout / **24** reference / **24** matched; nets **17** / **17** / **17**
> matched; pins **12** / **12** / **12** matched; by category `topology: 1`.
> - on the record `layout/sar-sequencer/reports/LATEST` resolves to, `klt drc`
> reports status **clean** with **0** violations, and `klt lvs` reports status
> **match** with **0** mismatches and **0** errors; devices **760** layout /
> **760** reference / **760** matched; nets **395** / **395** / **395**
> matched; pins **30** / **28** / **30** matched; no mismatch categories.
> - on the record `layout/seln-inverters/reports/LATEST` resolves to, `klt
> drc` reports status **clean** with **0** violations, and `klt lvs` reports
> status **match** with **9** mismatches and **0** errors; devices **18**
> layout / **18** reference / **18** matched; nets **20** / **20** / **20**
> matched; pins **20** / **20** / **20** matched; by category `topology: 9`.

Three things those readouts state that the prose above does not, each read out
of the records themselves rather than inferred from the verdict word:

- **A `match` verdict with a non-zero mismatch count is this flow's normal
  shape, not a hidden failure.** Four of the five report mismatch entries (9
  for `seln-inverters`, 2 each for `cdac-array` and `sampling-frontend`, 1 for
  `comparator`) while `klt lvs` still returns `match`. Every one of those
  entries is `severity: warning` against `error_count: 0` and an empty
  `category_error_counts` — checked in each record's own `lvs.json` — and they
  are all `topology` ("nets were paired ambiguously; the comparer resolved it
  structurally") or `device.body_unverified` entries. Stating both numbers is
  the point: an entry that changes *kind*, a warning becoming an error, moves a
  figure this document is now gated on instead of leaving the word "match"
  unchanged.
- **`layout/sar-sequencer/`'s pin counts are asymmetric** — 30 layout / 28
  reference / 30 matched — and that is the flow's own `lvs.json`, not a
  transcription slip. Its reference side,
  `sar_sequencer.lvs-reference.spice`'s `.SUBCKT sar_sequencer` line, declares
  28 ports, while the record's pin correspondence carries 30 entries; the two
  extra pairs resolve against post-CTS clock-tree leaf nets
  (`CLKNET_1_0__LEAF_CLK`, `CLKNET_1_1__LEAF_CLK`) that are not ports of that
  subcircuit. Named here rather than smoothed over. **Root-caused (issue
  #322)**: the two extra entries come from `klt extract`'s own net-label-
  merging pin-flagging — a merged net whose constituent GDS labels happen to
  include the real `CLK` port's label alongside internal clock-buffer
  instance labels still gets promoted to a pin, even with `--def-pins`
  supplied and even though that merged net is not itself in the DEF's
  declared 28-pin set (confirmed against this record's own `extract.json`,
  `sar_sequencer.def`, and the reference `.SUBCKT` line). This is a `klt`
  behaviour gap, not a choice in this flow's own request files — filed
  generically at
  [`2AMLogic/klayout-tools#2000`](https://github.com/2AMLogic/klayout-tools/issues/2000)
  — so 30/28/30 is kept as the correct, understood sign-off figure for this
  record rather than hand-corrected; see
  [`layout/sar-sequencer/README.md`](../../layout/sar-sequencer/README.md)'s
  "Why the pin counts read 30/28/30, not 28/28/28" section for the full
  trace.
- **The five records are now all built under the same `klt` build.**
  `layout/comparator/` and `layout/sampling-frontend/` were re-run under
  `klt 0.5.0` first (PR #275, the release `layout/requirements.txt` pins);
  `layout/cdac-array/`, `layout/sar-sequencer/` and `layout/seln-inverters/`
  still signed off on `klt 0.4.0`-built records at that point, as each
  record's own Provenance block stated. That mattered because the
  0.4.0→0.5.0 bump demonstrably changed extraction behaviour on this design
  elsewhere — the sampling front end's MIM-cap arrays grew 0.92 µm in y, and
  the capacitor-device-class regression (klayout-tools#1876) moved the
  *top-level* mismatch count from 98 to 124 before PR #287 neutralised it
  (§7 Item 1) — so the question was open for the three sub-blocks that had
  not yet been re-confirmed under the newer build. **Resolved this pass
  (issue #323)**: all three were re-run under the pinned `klt 0.5.0` and each
  new record's `drc.json`/`lvs.json` is field-identical to its superseded
  `klt 0.4.0` predecessor — same DRC-clean verdict, same LVS verdict, same
  device/net/pin counts, same mismatch categories (see each flow's own
  README for the record-pair comparison). No regression, so no upstream
  `klt` issue was filed for this pass.

**What the composed top level is actually built from, machine-checked** (added
2026-09-18). The five readouts above are recomputed from each sub-block flow's
*current* record. §4's two sign-off-bar rows and its Area row are graded on a
different artefact — the *composed* record `layout/sar-adc-top/reports/LATEST`
resolves to — and nothing tied the two together.
[`layout/sar-adc-top/bin/run-flow.sh`](../../layout/sar-adc-top/bin/run-flow.sh)
resolves each sub-block's `reports/LATEST` at run time and copies that flow's
top-cell GDS in as `<block>.gds`; which record it took is not recorded anywhere
afterwards, because `klt gen-compose`'s `compose.json` names each block's offset
and bounding box but carries no provenance for the geometry it composed (filed
generically upstream as
[`2AMLogic/klayout-tools#2065`](https://github.com/2AMLogic/klayout-tools/issues/2065)).
So a sub-block could be re-run, its readout above advance, and §4 keep grading a
composition of the superseded geometry — with every other check in the
[citation gate](check_proposal_citations.py) green, because each of those
grades a claim against the record it cites and none of them looks at that
record's inputs.

That was this tree's state on 2026-09-18 (morning): the re-run described in
the bullet above happened on 2026-09-17, while the composition `reports/LATEST`
then resolved to had been built on 2026-09-15. **Issue #326's re-composition
(2026-09-18) cleared it** — that pass re-ran
[`layout/sar-adc-top/bin/run-flow.sh`](../../layout/sar-adc-top/bin/run-flow.sh),
which resolves every sub-block's `reports/LATEST` at run time, so all five
inputs are now current by construction (the mechanism this paragraph predicted
would clear them, exercised rather than argued). Check 14 states each composed
input's provenance, recomputed per CI run by fingerprinting the embedded copy
against every record of the named flow (`--stats` prints these, so a
re-composition is pasted back rather than hand-transcribed):

> - the composition on `layout/sar-adc-top/reports/LATEST` embeds a
> `cdac_array.gds` that reproduces **2** records of `layout/cdac-array/`,
> newest `20260924-233346-66dca3c`, while `reports/LATEST` there names
> `20260924-233346-66dca3c`: **current**.
> - the composition on `layout/sar-adc-top/reports/LATEST` embeds a
> `sampling_frontend.gds` that reproduces **1** record of
> `layout/sampling-frontend/`, newest `20260924-232823-66dca3c`, while
> `reports/LATEST` there names `20260924-232823-66dca3c`: **current**.
> - the composition on `layout/sar-adc-top/reports/LATEST` embeds a
> `comparator.gds` that reproduces **4** records of `layout/comparator/`,
> newest `20260915-121226-1e90b14`, while `reports/LATEST` there names
> `20260915-120705-1e90b14`: **current**.
> - the composition on `layout/sar-adc-top/reports/LATEST` embeds a
> `sar_sequencer.gds` that reproduces **1** record of `layout/sar-sequencer/`,
> newest `20260917-180601-527ec73`, while `reports/LATEST` there names
> `20260917-180601-527ec73`: **current**.
> - the composition on `layout/sar-adc-top/reports/LATEST` embeds a
> `seln_inverters.gds` that reproduces **1** record of
> `layout/seln-inverters/`, newest `20260917-180644-527ec73`, while
> `reports/LATEST` there names `20260917-180644-527ec73`: **current**.

Five things those lines state, each read out of the artefacts rather than
inferred:

- **"Current" means the flow's own pointer is among the records the embedded
  copy reproduces — not that it is the newest of them.** Those are different
  claims, and `layout/comparator/` is where they come apart: its
  `20260915-121226-1e90b14` record was minted *after* the
  `20260915-120705-1e90b14` its `reports/LATEST` names (a `klt 0.4.0` run from
  a different branch, where the pointer names the `klt 0.5.0` one), and both
  reproduce the composed copy. The input is current because the pointer
  matches; the newest match is reported alongside it rather than instead of
  it, so that discrepancy is visible rather than smoothed away.
- **All five inputs are current as of issue #326's re-composition
  (2026-09-18).** Two were **superseded** when this section was written the
  morning of the same day, both of them flows PR #327 re-ran: the composition
  then embedded `sar_sequencer` geometry from `20260905-191258-4c6c655` and
  `seln_inverters` geometry from `20260906-002022-a36e06f`, the `klt 0.4.0`-era
  records their own flows no longer point at. #326's re-run of
  `layout/sar-adc-top/bin/run-flow.sh` picked up both current pointers (and
  `layout/sampling-frontend/`'s own new `20260918-191227-935ce76`) by
  construction. `cdac_array`'s PR #327 re-run, by contrast, reproduced its
  predecessor exactly (which is why that input matches **2** records).
- **No §4 verdict moved when those two lines said superseded, and that was
  verified rather than assumed.** A layer-by-layer XOR of the embedded copy
  against each flow's current record — over every layer present in either
  file, using `klayout`'s own `Region` boolean, run once by hand on the
  2026-09-18 morning pass — was **empty for all five**. It needs the `klayout`
  Python module (`layout/bin/setup-venv.sh`), which is why it is a hand check
  rather than part of the gate:

  ```python
  # A = the composed copy, layout/sar-adc-top/reports/<stamp>/<cell>.gds
  # B = layout/<flow>/reports/<that flow's LATEST>/<cell>.gds
  import klayout.db as db
  la, lb = db.Layout(), db.Layout()
  la.read(A), lb.read(B)
  # By top cell, not by name: two of the five files name their top
  # `gen_compose_0` rather than after the block (`compose.json` records that).
  ca, cb = la.top_cell(), lb.top_cell()
  layers = {(i.layer, i.datatype) for i in
            [la.get_info(x) for x in la.layer_indexes()]
            + [lb.get_info(x) for x in lb.layer_indexes()]}
  for ln, dt in sorted(layers):
      xor = (db.Region(ca.begin_shapes_rec(la.layer(ln, dt)))
             ^ db.Region(cb.begin_shapes_rec(lb.layer(ln, dt))))
      assert xor.is_empty(), (ln, dt, xor.count(), xor.area())
  ```

  Run on that pass over all five inputs: XOR empty over 20 / 16 / 11 / 34 / 34
  layers for `cdac_array` / `sampling_frontend` / `comparator` /
  `sar_sequencer` / `seln_inverters` respectively.

  The two then-superseded inputs were byte-different from their successors but
  *geometrically identical* to them; what had moved is GDS element ordering,
  which a re-run of OpenROAD place-and-route (`layout/sar-sequencer/`,
  `layout/seln-inverters/`) does not reproduce bit-for-bit. So the composed
  GDS §4 graded was already the same geometry the current sub-block records
  hold, and neither the two sign-off-bar rows nor the Area row moved on that
  account — as #326's re-composition then confirmed directly: its DRC verdict,
  LVS verdict, device/net/pin counts and mismatch categories are all identical
  to the superseded record's.
- **The gate cannot make that XOR claim for itself**, which is why the stated
  readout is record identity rather than geometric equivalence: the always-on
  headless CI job installs no PDK and no `klayout` module. The fingerprint is
  exact on everything but the two GDS timestamp records, so it is
  conservative in the safe direction — it reports a re-ordered rebuild as
  **superseded** and asks for the XOR, rather than reporting a real input
  drift as current.
- **What cleared the two superseded lines was a re-composition, not an edit
  here** — as this bullet said it would have to be. #326's re-run of
  `layout/sar-adc-top/bin/run-flow.sh` (2026-09-18) picked up the current
  pointers by construction and the readout above is the recomputed result, not
  a hand-corrected one. This document compiles evidence and does not mint
  layout records, so a future drift here is likewise cleared by re-running
  that flow, never by re-typing these lines.

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
- **`klt erc` (power delivery, structural)**: **all four declared supplies
  now pass the continuity check; the checklist item as a whole is still
  unmet.** The connectivity bullet above is a *signal*-net check: its net list
  is this design's top-level ports plus `VDD`/`VREFP`/`VREFN`, and it never
  included the standard-cell macros' own `VPWR`/`VGND` rails, so it neither
  confirmed nor contradicted them. A `klt erc` supply run grades exactly that
  question. Its **first** run
  ([`erc-reports/20260923-143401-1ee4ba8/record.md`](../../layout/sar-adc-top/erc-reports/20260923-143401-1ee4ba8/record.md),
  issue #344) found a real gap: `VDD` and `GND` each at exactly one electrical
  island, but `VPWR` and `VGND` each at **two** disconnected islands —
  `sar_sequencer`'s and `seln_inverters`' own self-contained rails, neither
  reaching a top-level supply, corroborated independently by that layout
  record's `lvs.json` `net_correspondence` (`VPB|VPWR` ↔ `VPWR_SEQ`,
  `VPB|VPWR$1` ↔ `VPWR_SELN`). It was not tuned away; issue #355 fixed the
  **layout** (the supply spec's *graded* fields — `stackup`, `vias`, `nets[]`,
  `ties_disclosure.kind` — hash identically across every run, `7f48fd89…`;
  issue #364 refreshed the spec's prose comments three times — once before
  and once after issue #377 drew an analog ground mesh, and a third time to
  correct two GDS-specific shape counts a later Judge round found still
  described the superseded pre-mesh run — which moves the whole-file hash and
  nothing the tool reads), and the current run
  ([`erc-reports/20260925-044420-f039594/record.md`](../../layout/sar-adc-top/erc-reports/20260925-044420-f039594/record.md),
  which supersedes `20260925-011943-f981dc9` (issue #364's second prose
  re-mint), `20260924-234116-66dca3c` (issue #377's analog ground mesh),
  `20260924-214731-b323061` (issue #362's analog ground pad), and
  `20260924-190825-f3622fc` (issue #355), none of which moved a number in
  this bullet)
  reports `erc_status: clean`, 0 findings — all four supplies at one island
  each, no `erc.supply_short`. **That is the continuity half only**: the
  checklist item also requires zero `erc.missing_tie` from a tie the run
  actually checked, and no `ties[]` is declared (klayout-tools#2169 would turn
  a correct declaration into a false `erc.supply_short`), so `klt signoff`
  still renders the row `unmet`. See §7 item 9.
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

**#103 itself was open and blocked at that pass** — the Curator's 2026-09-06
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
(superseded on 2026-09-18 by issue #326's minimum-area re-composition,
[`layout/sar-adc-top/reports/20260918-191315-935ce76/record.md`](../../layout/sar-adc-top/reports/20260918-191315-935ce76/record.md),
and in turn on 2026-09-19 by this issue's own `--abstract-cells` ablation-probe
re-run,
[`layout/sar-adc-top/reports/20260919-050355-fb11617/record.md`](../../layout/sar-adc-top/reports/20260919-050355-fb11617/record.md),
and on 2026-09-23 by issue #103's `klayout-tools==0.6.0` pin-bump re-run,
[`layout/sar-adc-top/reports/20260923-131726-fa1e0af/record.md`](../../layout/sar-adc-top/reports/20260923-131726-fa1e0af/record.md),
and on 2026-09-24 by issue #355's digital supply-rail tie, then by issue
#362's analog ground pad
([`layout/sar-adc-top/reports/20260924-214710-b323061/record.md`](../../layout/sar-adc-top/reports/20260924-214710-b323061/record.md)),
and finally by issue #377's analog ground mesh,
[`layout/sar-adc-top/reports/20260924-234053-66dca3c/record.md`](../../layout/sar-adc-top/reports/20260924-234053-66dca3c/record.md),
the current `reports/LATEST` — every hop up to and including 2026-09-23 at an
identical DRC/LVS verdict, identical device/net/pin counts and identical
mismatch categories, and the 2026-09-24 hop the first that moves them at all,
in the improving direction (19/19/19 → 21/21/21 pins, 98 → 88 mismatches,
794 → 803 devices matched: two new top-level digital supply pins, and each
digital rail one net instead of two — see the sign-off-bar readout in §4); `compose.json`'s
top-level `bbox_um` was in turn byte-identical to `20260915-213439-bf2256f`'s,
verified directly, moved by 0.05 µm in x0 only at the #326 re-composition,
where the external `VDD` pin's own met4 landing pad widened, and is
byte-identical again across the 2026-09-19 re-run), which §4's Area
row and its two sign-off-bar rows are re-pointed onto below. **No §4 verdict moves**: DRC/LVS-clean GDS
stays UNMET/BLOCKED (88 mismatches on the current record, 98 on every record
from `20260915-234004-76f48b9` through 2026-09-23 — better than the 124 this paragraph once
cited, but still not clean), and post-layout PVT stays
UNMET (still no extraction-based re-sim at any corner). #103 itself was
re-blocked at that pass, now specifically on
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
reconfirmed this pass. **#103 itself was still blocked at that pass** — its own
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
#1911's 09:50:34Z closure and still names it as an open gap; #103 remained
blocked. **No §4 verdict moves**: DRC/LVS-clean GDS stays
UNMET/BLOCKED and post-layout PVT stays UNMET — the row's blocker is now
a release gate (three merged, unreleased fixes: #1921, #1924, #1934)
rather than any single open klayout-tools issue. This corrects the
"`klayout-tools#1911` ... remains **OPEN**" claim in the paragraph above,
which is now stale by about six hours as of this pass.

---

## 4. Target specification at Sky130's ratified 1.8 V rail

The grid the rows below are reported at, where the record a row cites
declares a grid at all, is this repository's own ratified PVT grid —
process corners `{ff, fs, sf, ss, tt}`, temperature `{−40, 27, 125} °C`,
supply `{1.62, 1.80, 1.98} V`, one-at-a-time (9 points) — per
`spec/target-spec.md`'s "Numeric rows — RATIFIED 2026-08-19" section and
`sim/README.md`'s "Corner-grid shape." No row below has ever been measured
at, or claimed to hold at, any rail above 1.8 V core (§2.1).

**How much of this table stands on all nine of those points is counted, not
asserted.** That qualifier is new. Until 2026-09-25 this paragraph opened
"Every row below is reported at this repository's own ratified PVT grid",
and measured against the records the table actually cites, that sentence was
false for **10 of its 22** (spec row, `sim/` record) citation pairs. The
census below — added 2026-09-25 and graded in both directions by check 28 of
the [citation gate](check_proposal_citations.py), whose rationale is in
[`docs/citation-gate.md`](../citation-gate.md) — is what replaces the
blanket claim:

> of the **24** (spec row, `sim/` record) citation pairs in Section 4's
> table, **12** name a record that declares the full **9**-point grid,
> **10** name one that declares a smaller PVT point set, and **2** name one
> that declares no PVT point set of its own:
> `sim/cdac-array-transfer/records/20260828-005006-0c70212.md` (**1**
> point), `sim/cdac-array-transfer/records/20260828-022618-f36913e.md`
> (**1** point),
> `sim/cdac-bit-trial-settling/records/20260905-220919-bbf06dd.md` (**1**
> point), `sim/comparator-decision/records/20260924-041815-afcb1b5.md`
> (**1** point),
> `sim/comparator-decision/records/20260925-050027-0259924.md` (**1**
> point),
> `sim/comparator-decision/records/20260925-182138-23ad4d8.md` (**1**
> point), `sim/enob-estimate/records/20260906-082749-7724af3.md` (no PVT
> point set), `sim/enob-estimate/records/20260925-090023-c3a6872.md` (no
> PVT point set),
> `sim/sampling-acquisition-settling/records/20260906-202424-cb7e7aa.md`
> (**1** point),
> `sim/sequencer-logic-delay/records/20260906-192230-1b5c996.md` (**1**
> point),
> `sim/supply-impedance-sensitivity/records/20260925-073912-0e385e5.md`
> (**1** point),
> `sim/supply-impedance-sensitivity/records/20260925-204633-7339971.md`
> (**1** point).

**One name in that list was stale the moment the census landed, and was
re-pointed by #419 later the same day (2026-09-25).** As first written, the
exception list named `sim/enob-estimate/records/20260906-173830-6f04f59.md`
as the second of the two records declaring no PVT point set of their own.
That was right against the tree the census was derived from and wrong against
the tree it merged into, two minutes later: issue #405 had just minted this
flow's first `records/LATEST` pointer and moved the **ENOB** row's
DR-007-candidate citation onto
[`sim/enob-estimate/records/20260925-090023-c3a6872.md`](../../sim/enob-estimate/records/20260925-090023-c3a6872.md)
— a same-inputs re-run whose committed `Composite-inputs manifest` line is
byte-identical to `6f04f59`'s (sha256 of that line, `6022b531…`, is also what
both records carry as their `DUT netlist sha256`) and which reports the same
8.506 / 7.755 bit. Neither change could see the other before merging, and
because check 28 grades the census in **both** directions it reported two
findings rather than one: the superseded record still listed, and the current
record not listed. **#419 made the one-line repair** at 2026-09-25T10:34:50Z,
which is why the list above already names `c3a6872`; this paragraph is the
write-up of the race, not the repair of it. **No count moved** — still **22**
pairs, **12** / **8** / **2** — because the re-run declares no PVT point set
of its own for exactly the reason its predecessor did (it runs no ngspice;
see the paragraph below), and no Section 4 verdict, figure, Target or Status
moved either. The race was reported as #417, which is **closed**
(`completed`, 2026-09-25T11:13:01Z) — closed by PR #421, the write-up this
paragraph began as, not by #419's repair, so its closure marks this record of
the race landing and adds no fix of its own. Nothing about it stays open; the
both-directions rule is what made a two-minute merge race visible at all,
rather than leaving the census quietly one record behind.

**No cited record hides this — the sentence above them did.** Each of the
eight single-point records states its own subset-corner justification in its
own header (the phrase is the harness's, not this document's), and the two
that declare no PVT point set of their own are derived re-analyses that run
no ngspice at all: `sim/enob-estimate/` composes the comparator campaign's
binding-corner noise figure with the already-committed CDAC mismatch draws,
and inherits whatever coverage those carry. Which rows the ten pairs sit
under, and what each costs:

- **Sample rate** (3 pairs) — the three mechanism budgets it cites at their
  single-corner first pass (`sim/cdac-bit-trial-settling/`,
  `sim/sampling-acquisition-settling/`, `sim/sequencer-logic-delay/`) are
  each cited *alongside* the 9-point campaign that superseded them, and that
  campaign is in the same Source cell. **No figure this row reports rests on
  a single-corner record** — its own verdict cell reads every (a)–(d)
  mechanism figure off the full grid, and the first-pass records are cited
  for the supersession trail (§7 Item 2). The benign three of the ten.
- **Kickback** (2 pairs) — both cited comparator runs are single-point
  (`tt`/27 °C/1.8 V). This row already says so in its own cell ("**Single
  corner only** … a first-pass baseline, not a corner campaign"), and
  [DR-011](../../spec/decision-records/DR-011-comparator-kickback-target-row.md)
  Consequences §5 already obliges a full-corner campaign before the row
  could be ratified. Informational only either way.
- **ENOB** (2 pairs) and **INL / DNL** (2 pairs) — the ENOB records are the
  two derived re-analyses above; the two INL/DNL records are Monte Carlo
  mismatch campaigns at the nominal PVT point (`tt_mm`, 27 °C, 1.8 V, N=40),
  which sample the *mismatch* axis rather than the PVT one and say so in
  their own statistical convention. Both rows are Informational only — no
  ratified line exists to grade either against — and **neither states its
  corner coverage in its own cell**, which is precisely what the blanket
  sentence was covering for. Stated here rather than added to four cells.
- **Power** (1 pair) — `sim/supply-impedance-sensitivity/` is single-point by
  construction: it measures a *difference* between four supply-return
  networks driving one stimulus at one corner, and this row cites it
  non-gating, for completeness. The row's own µW figures come from the
  9-point full-conversion campaign beside it.

None of this moves a verdict — the four rows carrying those ten pairs are
graded UNMEASURED or Informational only already, for reasons that have
nothing to do with corner count. What it cost was a reader's right to take
one sentence at the top of the table as speaking for every row beneath it.

The verdict column below states one of five kinds, per this issue's own
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

A sixth kind, **BLOCKED** ("no evidence exists yet; names the specific issue
that would produce it"), was defined here until 2026-09-17 and is now gone:
the Power row was its last user, and that row turned out to have had
whole-ADC evidence since 2026-09-12 (see its own Correction note, and check
11 below). Deleting the definition rather than leaving it unused is what
check 8's both-directions rule requires — a kind no row is graded with is a
vocabulary this table does not actually use. The word still appears *inside*
the compound verdict of the DRC/LVS sign-off-bar row, describing one
component of a `PARTIAL` grade; that is prose about a blocker, not a row-level
verdict kind, and check 8 grades only the kind a row opens with.

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
| Resolution `N` | 10 bit | **RATIFIED** (DR-003 via #27) | **MET** — 9/9 corners, correct MSB-first bit-by-bit capture. **Re-pointed 2026-09-25** (issue #405, which minted this flow's first `records/LATEST` pointer): the cited record is now the flow's most recent, `20260912-004028-9aaf1ca` (issue #263's SAR-trial-perturbation / decision-directed-CDAC-switching fix, PR #266) — a re-run of the same ratified claim against the post-#263 schematic, still 9/9 PASS, binding corner and worst digital margin unchanged (`tt_27c_1.62v`, 0.8099 V); the record this row previously cited, `20260827-211956-e13bc1e`, pre-dates that fix. No verdict changes | [`sim/sar-sequencer-behavioral/records/20260912-004028-9aaf1ca.md`](../../sim/sar-sequencer-behavioral/records/20260912-004028-9aaf1ca.md) (current `records/LATEST`; supersedes `20260827-211956-e13bc1e` in substance, though that record's own `Supersedes` field is not set — a pre-existing gap in its own metadata, not touched by this re-point) |
| `V_REF` | `1.8 V` (= `V_DD`, at the rail) | **RATIFIED** (DR-003 via #27) | **MET** — structural + functional/monotonicity check, 9/9 corners | [`sim/cdac-array-transfer/records/20260827-213107-e13bc1e.md`](../../sim/cdac-array-transfer/records/20260827-213107-e13bc1e.md) |
| LSB (differential) | `2·V_REF/2^N = 3.5156 mV` | **RATIFIED** (DR-003 via #27) | **MET** — same record as `V_REF` | same record |
| Sampling cap (CDAC unit × array) | `C_u ≈ 8.65 fF`, `2^9 = 512` positions/side | **RATIFIED** (DR-003 via #27) | **MET** — sim structural check (9/9 corners); independent layout evidence also exists and is now DRC- and LVS-confirmed (drawn `C_u = 8.6473 fF`, unit-cap count 1024 = 512/side × 2). The original record's LVS "match" did not reproduce against its own committed artefacts (#148); #148's fix compares the array's 1024 drawn unit capacitors 1:1 against the reference (no `combine_devices` folding) and its replacement record's match reproduces on repeat runs. **Re-cited 2026-09-17** (issue #323) onto the flow's `klt 0.5.0` re-run, `reports/LATEST` as of this pass: `drc.json`/`lvs.json` are field-identical to the superseded `klt 0.4.0` record this row previously cited — same DRC-clean, same LVS match (2 mismatches, 0 errors), same 1060/1060/1060 device and 42/42/42 net counts — no verdict change. **Re-cited 2026-09-24** (issue #377) onto the flow's first `klt 0.6.0` run, which also draws this block's new `VSS` p-substrate tap and pin: `drc.json` still clean at 0 violations and `lvs.json` still `match`, with the same 1060/1060/1060 device, 42/42/42 net and 24/24/24 pin counts; the mismatch count goes 2 → 1 because the substrate net now carries a drawn `VSS` label and `device.body_unverified` stops firing — a naming fact about the deck's global tie, not a newly verified body tie. The drawn unit capacitance and unit-cap count are untouched, so this row's own quantity does not move | same record; [`layout/cdac-array/reports/20260924-233346-66dca3c/record.md`](../../layout/cdac-array/reports/20260924-233346-66dca3c/record.md) (current `reports/LATEST`, issue #377's `VSS` tap; supersedes `reports/20260917-180543-527ec73/`, the `klt 0.5.0` version-parity re-run, which supersedes `reports/20260906-020815-38cdbd3/`, the `klt 0.4.0`-built record — issue #323's version-parity re-run, no verdict change — which itself supersedes `reports/20260905-220338-9fb9b04/` — issue #165's own tap/landing-pad fix (PR #170) re-ran this flow with an identical extraction/LVS/unit-cap outcome, see §7 Item 1 — which itself supersedes `reports/20260825-132454-51cbdd4/`, see #148) |
| Comparator input-referred noise | `≤ 1.0148 mV rms` (baseline) / `≤ 0.5859 mV rms` (stretch) | **RATIFIED** (DR-003 via #27) | **MET** vs. baseline at binding corner `tt_125c_1.80v` = 0.8643 mV rms; **UNMET** vs. stretch at the same corner. Reduced-sub-model methodology named ([DR-004](../../spec/decision-records/DR-004-comparator-topology-and-noise-budget.md)). Re-measured this pass against issue #175's amended (reset-integrity-fixed) device set — the binding-corner figure moved from 0.9591 to 0.8643 mV rms; the pass/fail outcome is unchanged | [`sim/comparator-decision/records/20260906-065109-eedd532.md`](../../sim/comparator-decision/records/20260906-065109-eedd532.md) |
| Kickback | `≤ 5 mV` peak pin disturbance into a `1 kΩ` series source impedance, single decision edge (target); stretch `≤ 2 mV` | DRAFT (new row, DR-011 candidate) | **Informational only — no ratified line exists to grade against.** This row is new as of 2026-09-24 ([DR-011](../../spec/decision-records/DR-011-comparator-kickback-target-row.md) via #361), and its bound is **adopted verbatim** from the sibling `2AMLogic/sky130-comparator` canary's own DR-002-ratified row as a stated interim choice — not derived from this block's own system-level budget (DR-011 "Alternatives considered" names the derivation this repo cannot do yet, and why). Against it, informationally: the cited record measures **73.3673 mV** worst-case peak pin disturbance (`Vindiff = +50 mV`, `VINP` at 5.108 ns), i.e. `≈ 14.7×` the `≤ 5 mV` target and `≈ 36.7×` the `≤ 2 mV` stretch. **Single corner only** (`tt`/27 °C/1.8 V, 1 PVT point) — this is a first-pass baseline, not a corner campaign, so the figure is not a worst-case-over-PVT one. Against the record's own `Vindiff = 0 mV` control row (**−70.3419 mV**, `VINP` at 5.108 ns): `≈ 95.9 %` of that peak is already present with no decision to make, and `3.0254 mV` (`≈ 4.1 %`) is what the `+50 mV` point adds on top of it. **That subtraction is not a common-mode/differential split, and this row does not read it as one** — until 2026-09-25 it stated the `≈ 4.1 %` term as "the decision transient itself", which overstates what a per-pin subtraction can separate: both figures above are the extremum over *either* pin independently (`sim/comparator-decision/run.py`'s `run_kickback_sweep` tracks one maximum and one minimum across `VINP` and `VINN` together), so neither bounds the *differential* part of the disturbance. The cited record now measures that split directly, and this row reads it off the measurement instead of inferring it: the record's own `Measured value(s)` table carries **9** columns — `Vindiff (mV)`, `peak+ (mV)`, `pin / time (ns)`, `peak- (mV)`, `pin / time (ns)`, `CM+ (mV) @ t (ns)`, `CM- (mV) @ t (ns)`, `diff+ (mV) @ t (ns)`, `diff- (mV) @ t (ns)` — at least one of them is a common-mode or differential quantity, so restate the split from the record instead of subtracting per-pin peaks. **The measured split** (issue #390, the first gate [DR-014](../../spec/decision-records/DR-014-comparator-kickback-mitigation-no-static-preamp.md) names, record `20260925-050027-0259924` superseding #346's baseline): the common-mode component barely moves with overdrive — `−70.3419 mV` at the `Vindiff = 0 mV` symmetry-control point, `−70.4415 mV` at `+50 mV` — so essentially all of the `73.3673 mV` per-pin figure is common-mode, which a differential top-plate CDAC rejects to first order. The differential component, which it does not reject and which therefore lands on a decision, is `−10.9153 mV` at `+50 mV` (`≈ 2.2×` the `≤ 5 mV` target) and `+4.1918 mV` at the half-LSB overdrive `+1.7578 mV` that a marginal SAR decision actually presents (`≈ 0.84×` the target, `≈ 2.1×` the `≤ 2 mV` stretch). Both components are back below `0.001 mV` by `t = 10 ns`, about 4.9 ns after the CLK ramp ends. So the `≈ 14.7×` above stands as the multiple on the quantity the row bounds, while the decision-relevant component is a far smaller multiple of it — not negligible, and still over the target at the large-overdrive point. DR-011's Context reads the old subtraction as a clock-coupled/decision-coupled split, and its Consequences §3 draws a mitigation direction from it ("clock-edge and reset/tail-switch shaping … matters far more here"); that direction was read off a per-pin quantity, and the measured split above is what any re-derivation of it now has to rest on. **Mitigation selection is no longer open work on #349.** [DR-014](../../spec/decision-records/DR-014-comparator-kickback-mitigation-no-static-preamp.md) (2026-09-25, the record #349 closed on) answers DR-011's "Mitigation selection" open item by adopting **no** mitigation: a static preamp is not adopted and [DR-004](../../spec/decision-records/DR-004-comparator-topology-and-noise-budget.md) Decision §1 stands, on DR-003 Item 1's `876.9 mV` common-mode headroom stack against a continuously biased stage at this rail, and clock-edge shaping is rejected as a gap-closer in the same record. So the `≈ 14.7×` above is a gap left **unmitigated by decision**, not one awaiting a chosen fix. DR-014's own first gate was #390's split rather than a topology change, and that gate is now measured (above); what remains open on this track is DR-014 Consequences §4 — measuring the headroom-neutral mitigation classes it names, now that the differential component is known to exceed the target at large overdrive. That follow-on was filed as #434 (double-tail latch, cross-coupled neutralization, complementary-clock charge compensation, per DR-014 §(c)/Open items), and one of the three is now measured. **Cross-coupled neutralization** — added to the same 11-device latch as an EXPERIMENTAL, non-adopted DUT variant (`sim/comparator-decision/testbench/comparator_core_neutralized.spice`; no `design/comparator.sch` change), sized from the input pair's own BSIM4 `Cgd` overlap term rather than fitted or hand-tuned — moves the worst-case peak differential deviation from `−10.9153 mV` to `−10.8355 mV` at `Vindiff = +50 mV` (`≈ −0.7 %`; `sim/comparator-decision/records/20260925-182138-23ad4d8.md`, informational, not graded against the DRAFT row per `spec/README.md`), and the worst-case peak per-pin disturbance from `73.3673 mV` to `69.9461 mV` (`≈ −4.7 %`). **[DR-016](../../spec/decision-records/DR-016-kickback-headroom-neutral-mitigation-measurement.md)** (2026-09-25, the record #434 closed on) weighs that result: a `0.7 %` differential reduction does not close enough of the gap to reconsider a mitigation, so **DR-014's Decision stands** — no static preamp, no mitigation adopted — and this measured class is why: the input pair's own coupling capacitance is a small fraction of the charge this latch's larger, `CLK`-gated tail and reset devices inject, so neutralizing only that path barely moves the differential figure. The double-tail latch and complementary-clock charge compensation classes remain unmeasured; per #434's own acceptance criteria, landing one class was sufficient to close it, so it is closed on this evidence rather than left open pending the other two. `sim/spec-coverage.json` carries that disposition too — its Kickback row's `tracking` field now names DR-016 alongside DR-014/#390/#434 — and check 22 of the [citation gate](check_proposal_citations.py) fails this row if it falls behind that field again. Ratification would additionally oblige a full-corner kickback campaign (DR-011 Consequences §5) | [`sim/comparator-decision/records/20260924-041815-afcb1b5.md`](../../sim/comparator-decision/records/20260924-041815-afcb1b5.md) (#346's baseline, superseded 2026-09-25); [`sim/comparator-decision/records/20260925-050027-0259924.md`](../../sim/comparator-decision/records/20260925-050027-0259924.md) (#390's decomposition, the record this row's figures are re-derived from) |
| Corners | −40/27/125 °C, ±10 % supply, sky130 process corners | **RATIFIED** (DR-003 via #27) | **MET** — corner runner switches `.lib` process sections correctly, harness self-test negative control passes | `sim/harness-corner-smoke/records/`, `sim/mc-smoke/records/` |
| Sample rate | provisional 100 kS/s–1 MS/s | DRAFT | **UNMEASURED as an end-to-end figure (all four constituent mechanisms now checked individually and all four now PVT-complete; the one mechanism previously found NOT to clear the phase budget at any ratified corner has since been fixed by issue #236 and now clears it at all 9/9 — see (d)'s "Update this pass (2026-09-08)")** — **Update this pass (2026-09-15): a full-hierarchy, whole-ADC code-correctness campaign now exists (`sim/full-conversion-transient/`, issue #254) — this row previously stated none did; that is now stale.** Its most recent full-grid run ([`records/20260912-002315-9aaf1ca.md`](../../sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md), pre-dates the current schematic) found 0/9 corners code-correct; several of the defects it surfaced have since been fixed (DR-008, DR-009) but two architecture/sizing decisions remain open (issues #267 and #269, both escalated to a human operator — §7 Item 8 carries their dated tracking state) before a fresh 9-corner re-run would be meaningful. **Citation note (this pass)**: that record is also what `sim/full-conversion-transient/records/LATEST` resolves to (verified against the pointer file this pass); the pointer is `records/LATEST`, not `reports/LATEST` as this row previously wrote it, and this row now cites the record by full path so the citation does not depend on the pointer at all. See §7 Item 8 for the full campaign history and root causes. The four *mechanism-level* timing-budget checks below (a)–(d) are a distinct, narrower claim (does each stage clear its DR-006 phase budget in isolation) from this whole-ADC *code-correctness* campaign (does the assembled loop converge to the right code) — both are now evidenced, and both are open in different ways. The 1.2–12 MHz timing budget itself is still a mechanical consequence of the DRAFT rate range, not independently derived ([DR-006](../../spec/decision-records/DR-006-sar-sequencer-bit-count-and-timing-budget.md)). (a) The CDAC array's own settling is now **PVT-complete** (full ratified OAT grid, 9 corners): binding corner `tt_27c_1.62v` at 13.2312 ns (bit 8/MSB, rise), 6.3× inside the DR-006-derived 83.333 ns phase budget; fastest corner `tt_27c_1.98v` at 10.3019 ns (8.1×); worst-to-best spread only 1.28× across the grid, and the tt/27 °C/1.8 V point reproduces the single-corner record's own 11.3861 ns exactly. All 9/9 corners clear the budget — not the bottleneck anywhere on the grid. A secondary, non-gating finding: the smallest-swing diagnostic row (bit 0, ~0.2% of VDD swing) failed to produce a 99%-settling crossing at 5/9 corners, root-caused (confirmed window-invariant out to 300 ns, not asserted without evidence) to a small, genuine, already-converged offset between the real simulated circuit and the analytic closed-form ideal — negligible against bit 8's own ~1.8 V swing but exceeding 1% of bit 0's own ~4 mV swing at some corners; bit 8 (the array's own true worst case, confirmed by its own tau_i(i) derivation) crossed cleanly at all 9/9 corners, so this does not affect the worst-case finding (see §7 Item 2 for the full root-cause trace). (b) The comparator's decision delay is now PVT-complete after issue #175 (DR-004 Amendment A) closed the reset-integrity defect: 9/9 corners' Vindiff = 0 mV negative control HELD, all 27/27 input-driven points decided, binding corner `tt_27c_1.62v` at +0.5 mV = 4.3575 ns, 19.1× inside the DR-006 budget (see §7 Item 2 and the now-resolved §7 Item 3). (c) The SAR sequencer's own CLK-to-phase-output logic delay is now **PVT-complete** (full ratified OAT grid, 9 corners), covering all 11 of its own ring-sequencer phase transitions at every corner (99 phase measurements): binding corner `ss_27c_1.80v` at 0.4237 ns (phase `b1`), 196.7× inside the DR-006 budget; fastest corner `ff_27c_1.80v` at 0.2480 ns (336.1×); worst-to-best spread only 1.71× across the grid. All 9/9 corners clear the budget by more than two orders of magnitude — the smallest of the four mechanisms measured, and not the bottleneck at any ratified corner. (d) **The sampling front end's own acquisition of a new, worst-case (rail-to-rail) differential input value is now ALSO PVT-complete (full ratified OAT grid, 9 corners) — and it is the only mechanism of the four found NOT to clear the budget, at EVERY ratified corner**: the single-corner (`tt`/27 °C/1.8 V) finding of a 23.43 mV residual (~13.3× the provisional differential LSB's half-step), traced to the bootstrap precharge PFET `Sa`'s imperfect off-state once `BOOST_x` is boosted above `VDD`, was not a corner-specific artifact — every one of the 9 ratified corners exceeds the half-LSB reference scale, with a binding corner of `tt_27c_1.62v` at 67.19 mV (~38.2× the half-LSB, 2.9× worse than the tt/27 °C/1.8 V baseline) and a best corner of `tt_27c_1.98v` at 9.00 mV (~5.1×). This is the opposite outcome from mechanisms (a)–(c); the front end's own acquisition, not the CDAC, comparator, or sequencer, is the likely bottleneck for an end-to-end sample-rate figure at the fast end of the DRAFT range, across the full ratified PVT grid, not just one corner — strengthening, not merely narrowing, the open item, and consistent with DR-006's own deferred "non-uniform phase allocation" alternative. The design-fix follow-up this finding implies (a topology/sizing fix for the bootstrap precharge PFET `Sa`, or adopting the non-uniform-phase-allocation alternative) is now tracked as issue #236, filed this pass, since this document compiles evidence rather than designing circuit fixes. **Update this pass (2026-09-08): issue #236 closed with a circuit fix, not a phase reallocation — `design/sampling_frontend.sch`'s uniform DR-006 phase budget is UNCHANGED.** Instrumenting `BOOST_x` directly isolated two independent limiters, both fixed: (1) `Sa`'s gate moved from `SAMPLE` to the switch's own gate node `G_{p,n}` — `Sa`'s source is the boosted node itself, so gating it from a VDD-level `SAMPLE` left `V_sg ~= VIN` (an ON device discharging `BOOST_x` throughout the sample phase, not a leaky off one); gating it from `G_{p,n}` instead (GND during hold via `Sd`, shorted to `BOOST_x` by `Se` during sampling) makes `V_sg ~= 0`, genuinely off; (2) once (1) was applied, the common-mode reference transmission gate `Cmswn/Cmswp` — in series with `Csamp` on the acquisition path via the floating `BPREF_x` node — was the limiter that remained, fixed by widening it from W=1 µm to W=16 µm. Re-running the full ratified PVT grid ([`sim/sampling-acquisition-settling/records/20260908-051436-6ccd72d.md`](../../sim/sampling-acquisition-settling/records/20260908-051436-6ccd72d.md)) with both fixes applied: **all 9/9 ratified corners now clear the DR-006 worst-case (12 MHz) phase budget, worst case 0.380 mV (`tt_27c_1.62v`, ~0.2× the half-LSB) vs. the pre-fix 67.19 mV (~38.2×) at the same corner** — the sampling front end's own acquisition is no longer the standout bottleneck the pre-#236 schematic made it, alongside mechanisms (a)–(c). This does not itself produce an end-to-end sample-rate figure (still open, per the summary cell above). Three things this fix touched were explicitly NOT re-derived by #236 itself: `sim/vcm-drive-budget/`'s R_source/C_decouple budget (the wider `Cmsw` draws more peak current from the shared `VCM` rail), and `layout/sampling-frontend/`'s LVS match and `layout/sar-adc-top/`'s composition of it (both stale against the schematic's new `Sa` gate net and `Cmsw` width) — tracked as follow-up issue #245 (and its own follow-up, #248) rather than asserted clean here. **Update this pass (2026-09-15): all three have since been re-derived (issues #245/#248 via PRs #249/#250, merged 2026-09-08), closing this gap.** `layout/sampling-frontend/`'s reference netlist and drawn geometry were updated to match the post-#236 schematic and re-verified DRC-clean/LVS-clean (24/24 devices, 17/17 nets, 12/12 pins, all three negative-control fixtures still correctly mismatching) — [`layout/sampling-frontend/reports/20260924-232823-66dca3c/record.md`](../../layout/sampling-frontend/reports/20260924-232823-66dca3c/record.md), re-pointed 2026-09-24 onto issue #377's `GND` pin promotion (same 24/24/17/17/12/12 counts; supersedes `20260918-191227-935ce76`). `layout/sar-adc-top/`'s composition was re-run against the updated sub-block GDS — DRC clean, and its LVS device-match verdict came back numerically identical to the pre-#245 baseline (869/869/794 devices, 444/446/412 nets, the same mismatch categories), confirming the pre-existing `combine_devices`-scoping gap (§7 Item 1) is unaffected and no new blocker was introduced — [`layout/sar-adc-top/reports/20260923-131726-fa1e0af/record.md`](../../layout/sar-adc-top/reports/20260923-131726-fa1e0af/record.md), superseded 2026-09-24 by issue #355's digital supply-rail tie, then by #362's analog ground pad (`20260924-214710-b323061`), then by issue #377's analog ground mesh, [`layout/sar-adc-top/reports/20260924-234053-66dca3c/record.md`](../../layout/sar-adc-top/reports/20260924-234053-66dca3c/record.md), the current `reports/LATEST` (#355's was the first hop whose DRC/LVS verdict is NOT field-identical: 21/21/21 pins and 88 mismatches, an improvement; #362 moved the pins to 21/22/22 and #377 moved nothing at all — and none of the three is a simulation, so this row's UNMEASURED status is untouched). **Both citations re-pointed 2026-09-16** off the `20260908-070934-80df05e` / `20260908-072857-80df05e` records that originally established these two claims, again 2026-09-18 off `20260915-120718-1e90b14` / `20260915-234004-76f48b9` onto issue #326's minimum-area re-runs (`20260918-191227-935ce76` / `20260918-191315-935ce76`), and the `layout/sar-adc-top/` half once more 2026-09-19 onto this issue's own `--abstract-cells` ablation-probe re-run (`20260919-050355-fb11617`), and 2026-09-23 onto issue #103's `klayout-tools==0.6.0` pin-bump re-run (`20260923-131726-fa1e0af`); each is its own flow's current `reports/LATEST` — every hop again field-identical on `drc.json` and `lvs.json` to the record it supersedes — the first §4 row found stale by this document's new [citation gate](check_proposal_citations.py) rather than by a hand re-read, and stale since 2026-09-08 (every other §4 row had been re-pointed in the meantime; this one, buried mid-narrative in the sample-rate cell, had not). Neither number above moves, and that is verified from the artefacts rather than assumed from the re-runs' intent: `layout/sampling-frontend/`'s `lvs.json` is field-identical across the two records (`status: "match"`, 24/24 devices, 17/17 nets, 12/12 pins, `category_counts: {device.body_unverified: 1, topology: 1}`) with `drc.json` clean in both, and all three negative controls still mismatch in the current record; `layout/sar-adc-top/`'s `lvs.json` is likewise field-identical (`status: "mismatch"`, `mismatch_count: 98`, `error_count: 97`, 869/869/794 devices, 444/446/412 nets, 19/19/19 pins, `category_counts: {device.unmatched: 75, net.merged: 12, net.split: 10, topology.flattened: 1}`) with `drc.json` clean in both. What the newer records add is provenance, not verdicts: both were re-run under `klayout-tools` `v0.5.0` rather than `0.4.0` (the sampling front end's MIM-cap arrays grow 0.92 µm in y under `v0.5.0`, the same growth §4's Area row already tracks — it changes no device, net, or pin count), and the top-level record additionally carries PR #287's capacitor-device-class restore. A follow-up pass (#250) then folded `layout/sampling-frontend-wells/` (issue #122) forward onto the same post-#236 device table too (byte-identical composed GDS confirmed, so `layout/sar-adc-top/`'s own composition needed no further re-run) and took the VCM drive budget's remaining `--corners` legs to the full ratified PVT grid — see §7 Item 6 for that budget's own (materially different, and looser) post-#236 results | [`sim/cdac-bit-trial-settling/records/20260905-220919-bbf06dd.md`](../../sim/cdac-bit-trial-settling/records/20260905-220919-bbf06dd.md) (CDAC mechanism, single-corner first pass); [`sim/cdac-bit-trial-settling/records/20260907-013225-5f176a6.md`](../../sim/cdac-bit-trial-settling/records/20260907-013225-5f176a6.md) (CDAC mechanism, full ratified PVT grid, PVT-complete — extends, does not formally supersede, the single-corner record); [`sim/comparator-decision/records/20260906-074451-7724af3.md`](../../sim/comparator-decision/records/20260906-074451-7724af3.md) (comparator mechanism, full grid, PVT-complete); [`sim/sequencer-logic-delay/records/20260906-192230-1b5c996.md`](../../sim/sequencer-logic-delay/records/20260906-192230-1b5c996.md) (sequencer mechanism, single-corner first pass); [`sim/sequencer-logic-delay/records/20260906-230516-0904419.md`](../../sim/sequencer-logic-delay/records/20260906-230516-0904419.md) (sequencer mechanism, full ratified PVT grid, PVT-complete — extends, does not formally supersede, the single-corner record); [`sim/sampling-acquisition-settling/records/20260906-202424-cb7e7aa.md`](../../sim/sampling-acquisition-settling/records/20260906-202424-cb7e7aa.md) (front-end acquisition mechanism, single-corner first pass, pre-#236); [`sim/sampling-acquisition-settling/records/20260906-211700-00d26af.md`](../../sim/sampling-acquisition-settling/records/20260906-211700-00d26af.md) (front-end acquisition mechanism, full ratified PVT grid, pre-#236, superseded); [`sim/sampling-acquisition-settling/records/20260908-051436-6ccd72d.md`](../../sim/sampling-acquisition-settling/records/20260908-051436-6ccd72d.md) (front-end acquisition mechanism, full ratified PVT grid, post-#236 fix, PVT-complete, all 9/9 corners clear the budget); [`sim/vcm-drive-budget/records/20260908-100413-f3e2914.md`](../../sim/vcm-drive-budget/records/20260908-100413-f3e2914.md) (the interface *precondition* on mechanism (d) — how much external `VCM` drive resistance the front end tolerates while still acquiring inside these windows; full ratified PVT grid, bare `R_source`, DR-006 worst-case window, post-#236) and [`sim/vcm-drive-budget/records/20260908-115336-f3e2914.md`](../../sim/vcm-drive-budget/records/20260908-115336-f3e2914.md) (the same budget's `C_decouple` axis at the legacy window, full grid, post-#236 — the record this campaign's current `records/LATEST` resolves to; all four post-#236 legs are listed in §7 Item 6, which is also where this budget's own open item lives). This last campaign is indexed under this row in [`sim/spec-coverage.json`](../../sim/spec-coverage.json) — "rather than under a row of its own", since it measures the same quantity as the acquisition bench with the `VCM` drive made non-ideal — and was cited only from §7 until this pass, which check 11 reports as a gap in this row rather than in that section |
| ENOB | > 7.5 bit (target), stretch > 8.0 (DR-007 candidate, was > 9.0/9.5) | DRAFT (target value, not ratified) | **Informational only — no ratified line exists to grade against.** Against `spec/target-spec.md`'s *current* DRAFT row (DR-007's candidate pair): 8.506 bit (mean-case CDAC mismatch) **meets** both the > 7.5 baseline and the > 8.0 stretch; 7.755 bit (worst-case CDAC mismatch) **meets the > 7.5 baseline but NOT the > 8.0 stretch**. Against the *original*, pre-DR-007 DRAFT row (> 9.0 / > 9.5) neither figure meets either bound. Re-composed this pass against DR-004 Amendment A's amended comparator-noise figure (0.8643 mV rms, down from 0.9591 — the same figure the comparator-noise row above already cites), moving the estimate from 8.491/7.749 to 8.506/7.755; the met/unmet outcome is unchanged in kind. **Correction**: this row previously headlined "DOES NOT MEET even the un-ratified DR-007 candidate", which overstated the shortfall — the source record's own scoring table marks the worst case as *meeting* the > 7.5 baseline, failing only the > 8.0 stretch (see §7 Item 4). **Re-pointed 2026-09-25** (issue #405, which minted this flow's first `records/LATEST` pointer): the DR-007-candidate citation now names `20260925-090023-c3a6872`, a same-inputs re-run of `20260906-173830-6f04f59` (identical `--cdac-mc-record`/target flags) that reproduces its figures byte-for-byte (8.506 / 7.755 bit) — the prior record is not wrong, just no longer this flow's `records/LATEST`; no verdict changes | [`sim/enob-estimate/records/20260925-090023-c3a6872.md`](../../sim/enob-estimate/records/20260925-090023-c3a6872.md) (current `records/LATEST`; DR-007-candidate scoring, composed from the post-amendment comparator noise, reproduces `20260906-173830-6f04f59`); [`sim/enob-estimate/records/20260906-082749-7724af3.md`](../../sim/enob-estimate/records/20260906-082749-7724af3.md) (identical figures scored against the original > 9.0 / > 9.5 row — the record `docs/characterization-report.md` pins) |
| INL / DNL | ≤ ±2.0 LSB (target, DR-007 candidate, was ≤ ±1 LSB) | DRAFT (target value, not ratified) | **Informational only**: empirical yield 0.825 (DNL) / 0.925 (INL) at N=40 against the *original* ≤ ±1 LSB target's 0.99 yield bar — `klt yield`'s own sample-size verdict on both is "insufficient" for a tight yield-fraction claim. A re-scoring against DR-007's wider ±2.0 LSB candidate **does** exist in-repo (a pure re-parse of the same 40 committed mismatch draws, no new ngspice run): its worst single draw is max\|DNL\| = 1.9716 LSB and max\|INL\| = 1.3147 LSB, i.e. every sampled draw falls inside the ±2.0 LSB candidate bound — but `klt yield` produced no report in that record's environment (a known, already-filed packaging gap, klayout-tools#1061), so there is **no machine-checked yield-fraction verdict against the candidate bound**, and N=40 is not sized for a tight yield-fraction claim in any case. Not graded met/unmet here: the candidate bound is not ratified | [`sim/cdac-array-transfer/records/20260828-005006-0c70212.md`](../../sim/cdac-array-transfer/records/20260828-005006-0c70212.md) (original ≤ ±1 LSB scoring — the record `docs/characterization-report.md` pins); [`sim/cdac-array-transfer/records/20260828-022618-f36913e.md`](../../sim/cdac-array-transfer/records/20260828-022618-f36913e.md) (DR-007-candidate re-scoring of the same draws) |
| Power | provisional, minimise at rate | DRAFT | **UNMEASURED as a spec-row figure** — this row asks for power *at a rate*, and there is neither a ratified power line to grade against nor an established rate to report it at (the Sample rate row above is itself UNMEASURED). What does exist, and is reported here rather than left absent, is the first whole-ADC supply-current measurement on this block — average ADC-core power over one steady-state conversion at the DR-006 worst-case `f_clk = 12 MHz`: min **21.600 µW** at `tt_27c_1.62v`, typ **27.971 µW** at `tt_27c_1.80v`, max **34.237 µW** at `tt_27c_1.98v`, over **9** corners. Those five figures are recomputed from the cited record's own Power table by check 12 of the [citation gate](check_proposal_citations.py) rather than hand-transcribed. **Two scope caveats, both load-bearing**: (i) every rail and reference in that testbench is an *ideal* source and this design has no reference buffer, clock generator or output driver yet, so this is the ADC core only — a real system's reference and clock power is not included; (ii) the same record's code-correctness check FAILS at 9/9 corners (the three mid-scale inputs land within ±1 LSB, the two near-full-scale inputs do not — §7 Item 8, open decisions #267/#269), so these are the currents of a conversion that is not yet correct across its full input range, and a re-measurement is owed once either decision lands. **Correction (2026-09-17)**: this row read "BLOCKED / UNMEASURED — no full-block power campaign exists" until this pass, which had been stale since 2026-09-12 — [`docs/characterization-report.md`](../../docs/characterization-report.md)'s own Power row (the regenerable source this table mirrors) and [`sim/spec-coverage.json`](../../sim/spec-coverage.json) (this repo's spec-row → evidence index) both carried this campaign meanwhile. It was found by check 11, not by a re-read. One non-gating extra, unchanged: `layout/sar-sequencer/`'s OpenROAD PnR static estimate (0.0154 mW) is for the digital sequencer sub-block only, not the full ADC, is not a `sim/` evidence record, and is not tied to the ratified corner set | [`sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md`](../../sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md) (current `records/LATEST`; issue #254's end-to-end campaign — both the figures above and the code-correctness caveat are read out of this one record); `layout/sar-sequencer/reports/20260917-180601-527ec73/record.md` (current `reports/LATEST`, #102's own LVS-clean record, re-run under `klt 0.5.0` this pass — issue #323, field-identical DRC/LVS to the superseded `klt 0.4.0` record `reports/20260905-191258-4c6c655/`, no verdict change; non-gating, cited for completeness only — supersedes in turn `reports/20260825-124031-1a2f7c1/`, which predates #102's LVS fix and still reports an LVS **mismatch**, see §7 Item 1); [`sim/supply-impedance-sensitivity/records/20260925-073912-0e385e5.md`](../../sim/supply-impedance-sensitivity/records/20260925-073912-0e385e5.md) (issue #378's supply-return impedance sensitivity campaign, replaying this same figure's stimulus with DR-015's package-style R+L / lumped-substrate arms driving the four supply terminals instead of ideal sources — DR-012's own "the impedance argument is unmeasured" open item, not a re-measurement of the figures above: at the baseline corner the as-built `package` arm's total power (27.238 µW) is within 3% of the `ideal` control (27.971 µW), while its analog-ground return current rises from 2.177 µA to 2.204 µA and its die-side `GND_DIE` excursion is 37.333 mV peak-to-peak — non-gating for this row, cited for completeness only, per check 11); [`sim/supply-impedance-sensitivity/records/20260925-204633-7339971.md`](../../sim/supply-impedance-sensitivity/records/20260925-204633-7339971.md) (current `records/LATEST` as of 2026-09-25, issue #409's item 2 — the same campaign's `ideal`/`package`/`no-gnd-pad` run, which prices DR-012's *rejected* null option: it **supersedes nothing**, and in particular does not replace the four-arm record beside it, which is still where this campaign's bond-inductance ablation lives. It moved the pointer because it is that flow's newest arm-comparison record, which is what the pointer names. Same non-gating status for this row: at the baseline corner the `no-gnd-pad` arm's total power is 27.296 µW against the `package` arm's 27.248 µW and the `ideal` control's 27.957 µW, with no `I(GND)` column at all on that row — the arm has no ground bond for a current to be measured in — while its die-side `GND_DIE` excursion is 65.237 mV peak-to-peak against `package`'s 37.590 mV. Neither figure is a power claim for this row, and the two records' `package` arms differ by 0.010 µW across two hosts) |
| Area | max, not yet specified in `spec/target-spec.md` | Not a spec row yet | **Informational only, not a spec-row verdict** — a composed top-level layout now exists (§3, §7), and its extent is stated here in the fixed form check 13 of the [citation gate](check_proposal_citations.py) recomputes from that record's own `compose.json` (**area readout, machine-checked**): the composed cell `gen_compose_0` on the record `layout/sar-adc-top/reports/LATEST` resolves to spans **-20.250** µm to **260.200** µm in x and **-161.600** µm to **223.900** µm in y, i.e. **280.450** µm × **385.500** µm ≈ **0.108** mm². Every figure in that sentence is recomputed from `compose.json`'s top-level `bbox_um` on each CI run, so the by-hand `cmp`/field-diff verification each re-citation below records is now done by the gate instead. Unchanged by issue #180's comparator re-draw, and unchanged again by PR #227's routing-cell rename: this row now cites the current `reports/LATEST` record, and its `compose.json` bounding box is byte-identical to the superseded `20260906-101939-1250ff4` record's (the only two differences between those two files are a new `dbu_um: 0.001` field and the routing block's `cell_name`, `ROUTE` → `SAR_ADC_TOP_ROUTE` — no `bbox_um` or `offset_um` value moved). Verified by diffing the two artefacts, not assumed from the rename's intent. **Re-cited 2026-09-15** onto `20260908-072857-80df05e`, `reports/LATEST` at that moment (issue #245's post-#236 re-run, PR #249): its `compose.json` is **byte-identical** (`cmp`) to the `20260907-110058-a546200` file previously cited here, so this row's bounding box and area figure are unchanged — again verified by comparing the artefacts, not assumed from the re-run's intent (see §3). **Re-cited again 2026-09-15 (later)** onto the current `reports/LATEST`, `20260915-213439-bf2256f` (PR #275's `klayout-tools` `v0.5.0` rebuild, merged): this `compose.json` is *not* byte-identical to `20260908-072857-80df05e`'s, but the two differ in exactly two fields and neither moves this row's number — the `open_pdks` provenance string, and the `sampling_frontend` sub-block's own `bbox_um.y1` (146.3 → 147.22 µm, the 0.92 µm growth in that block's MIM-cap arrays under `v0.5.0` described in §7 Item 1). The composition's **top-level `bbox_um` is identical** in both (`x0, y0 = -20.2, -161.6` to `x1, y1 = 260.2, 223.9` µm), so 280.4 µm × 385.5 µm ≈ 0.108 mm² stands — verified by diffing the two artefacts field-by-field, not assumed. This is a raw `klt gen-compose` bounding-box readout, not an LVS-clean, sign-off-grade area figure — the composition's `klt lvs` verdict is still a device-level mismatch (see §3, §7 Item 1), and no spec row exists yet to grade this number against. **Re-cited 2026-09-16** onto `20260915-234004-76f48b9`, `reports/LATEST` after two further #103 increments (PR #287's #1876 neutralisation, PR #290's abstract-cells experiment, both `Part of #103` — see §7 Item 1): its `compose.json` top-level `bbox_um` is byte-identical to `20260915-213439-bf2256f`'s, verified directly. **Re-cited again 2026-09-18** onto `20260918-191315-935ce76`, issue #326's minimum-area re-composition — the first re-run since PR #174 on which this box *moves*, and by exactly the amount the fix predicts: `x0` goes −20.200 → **−20.250** µm (width 280.400 → **280.450** µm) because the external `VDD` pin's own met4 landing pad, which carries only that pin's label and so has to clear `m4.4a` (0.240 µm²) unaided, widened from 0.36 to 0.50 µm and that pad is the composition's own leftmost shape. No other coordinate moves, and the mm² figure is unchanged at ≈ 0.108. **Re-cited again 2026-09-19** onto `20260919-050355-fb11617`, this issue's own `--abstract-cells` ablation-probe re-run: its `compose.json` is byte-identical to `20260918-191315-935ce76`'s, verified directly (`diff` over both files), so no coordinate in this row moves at this hop. **Re-cited again 2026-09-24** onto `20260924-234053-66dca3c`, issue #377's analog ground mesh: its `compose.json` top-level `bbox_um` is field-identical to the two records it supersedes (`x0` −20.250, `y0` −161.600, `x1` 260.200, `y1` 223.900, verified directly) — the mesh's westernmost geometry is a met4 corridor track at x = −16.0, 4 µm inside the external `VDD` pin's landing pad that still sets `x0` — so no coordinate in this row moves | [`layout/sar-adc-top/reports/20260924-234053-66dca3c/compose.json`](../../layout/sar-adc-top/reports/20260924-234053-66dca3c/compose.json) (current `reports/LATEST`, issue #377's analog ground mesh; supersedes `20260924-214710-b323061`, issue #362's analog ground pad, and `20260924-190817-f3622fc`, issue #355's digital supply-rail tie, 2026-09-24: the composed `bbox_um` is unchanged by any of them — the two new met5 rails and their pin labels sit well inside the existing extent — so no coordinate in this row moves; it supersedes `20260923-131726-fa1e0af`, issue #103's `klayout-tools==0.6.0` pin-bump re-run of 2026-09-23: identical placement and `bbox_um` to `20260919-050355-fb11617`'s, differing only by the `source_path`/`source_digest` provenance fields 0.6.0's `gen-compose` adds, so no coordinate in this row moves; that record was in turn byte-identical to, and superseded, [`20260918-191315-935ce76/compose.json`](../../layout/sar-adc-top/reports/20260918-191315-935ce76/compose.json), which supersedes [`20260915-234004-76f48b9/compose.json`](../../layout/sar-adc-top/reports/20260915-234004-76f48b9/compose.json), whose top-level `bbox_um` was byte-identical to [`20260915-213439-bf2256f/compose.json`](../../layout/sar-adc-top/reports/20260915-213439-bf2256f/compose.json), which is identical in turn to [`20260908-072857-80df05e/compose.json`](../../layout/sar-adc-top/reports/20260908-072857-80df05e/compose.json), which is byte-identical to [`20260907-110058-a546200/compose.json`](../../layout/sar-adc-top/reports/20260907-110058-a546200/compose.json), which in turn supersedes [`20260906-101939-1250ff4/compose.json`](../../layout/sar-adc-top/reports/20260906-101939-1250ff4/compose.json), same bounding box) |
| Digital sequencer/output register — physical implementation | transistor-level netlist + place-and-route layout | — | **MET** — netlist exists (`design/sar_sequencer.sch`); place-and-route layout exists and is DRC-clean and LVS-clean (#102). **This row's evidence changed shape on 2026-09-17**: it cited only `layout/sar-sequencer/README.md`, a hand-written file, so its DRC/LVS claim was the one §4 verdict no check in the [citation gate](check_proposal_citations.py) could reach — check 3 grades the dated records a row cites, and this row cited none. It now cites that flow's own dated record, and the numbers behind the verdict (`klt drc` clean, 0 violations; `klt lvs` match, 0 mismatches, 0 errors; devices 760/760/760, nets 395/395/395) are recomputed from that record's `drc.json`/`lvs.json` by check 9, in §3's sub-block readout. The verdict itself does not move. One asymmetry that readout surfaces and this row does not hide: the same record's pin counts are 30 layout / 28 reference / 30 matched, traced to two post-CTS clock-tree leaf nets appearing in the pin correspondence but not in the reference `.SUBCKT`'s own 28 ports — root-caused and documented, issue #322: a `klt extract` net-label-merging pin-flagging gap not fully superseded by `--def-pins` (filed generically at `2AMLogic/klayout-tools#2000`), so 30/28/30 stands as the record's own correct figure rather than a hand-corrected one, per `layout/sar-sequencer/README.md`'s own provenance section. **Re-cited 2026-09-17** (issue #323): this flow was re-run under the `klt 0.5.0` this repo now pins, and its `drc.json`/`lvs.json` are field-identical to the superseded `klt 0.4.0` record this row previously cited — same clean DRC, same 0-mismatch LVS match, same 760/760/760 device and 395/395/395 net counts, and the same 30/28/30 pin-count asymmetry issue #322 root-causes (unchanged by the tool bump, so #322's root cause is not `klt`-version-sensitive) | [`layout/sar-sequencer/reports/20260917-180601-527ec73/record.md`](../../layout/sar-sequencer/reports/20260917-180601-527ec73/record.md) (current `reports/LATEST`; #102's own LVS-clean record, now built under `klt 0.5.0` — supersedes `reports/20260905-191258-4c6c655/`, the `klt 0.4.0`-built record via PR #141, no verdict change, see §3 and issue #323), [`layout/sar-sequencer/README.md`](../../layout/sar-sequencer/README.md) |
| **Post-layout PVT simulation, full ADC** | brief sign-off bar | — | **UNMET** — a top-level layout now exists (PR #174, re-verified against the amended comparator geometry by PR #188, then again against PR #227's pin-declaration fix) but no extraction-based re-sim of the assembled `sar_adc_top` has been run against any PVT point; tracked under #103, under epic #25. **Update this pass (2026-09-15)**: #103's `klayout-tools` release blocker has cleared (`v0.5.0`, see §7 Item 1) and #103 was back in this repo's ready queue at that pass (§7 Item 1 carries the dated tracking-state trail; it has moved several times since — see this row's 2026-09-25 update below) — not yet MET, since no post-layout PVT sim has landed. **Citation re-pointed this pass** (the §7 Item 1 residual this document deliberately deferred until PR #273 landed): re-pointed off the one-record-old `20260907-110058-a546200` onto `20260908-072857-80df05e`, `reports/LATEST` at that moment — verified byte-for-byte equivalent (`compose.json` identical, `drc.json` clean in both, `lvs.json` aggregate fields identical: `status: "mismatch"`, `mismatch_count: 98`, `error_count: 97`, same four `category_counts`), so no verdict changes. **Update (2026-09-15, later): #103's PR #275 — now merged (2026-09-15T22:00:46Z) — has since run the deferred build against `klayout-tools` `v0.5.0`, and this row's citation is re-pointed again onto that build, the current `reports/LATEST` (`20260915-213439-bf2256f`).** Still **UNMET**: DRC stays clean and connectivity stays independently verified, but no PVT re-simulation of the assembled top level has been run either — that gap is unchanged by the layout-side rebuild. `klt lvs`'s device-level mismatch also did not clear on the rebuild (see the row below for the count); this row's own verdict does not move. **Update (2026-09-16)**: two further `Part of #103` increments (PR #287, PR #290 — see §7 Item 1) landed after the update above; neither runs a PVT re-simulation (both are LVS-shape measurements), so this row's verdict is unaffected — still **UNMET**. Citation re-pointed onto `20260915-234004-76f48b9`, then again this pass. **Update this pass (2026-09-18)**: issue #326 re-ran the flow to eliminate 17 sub-minimum-area metal shapes (see the row below), minting `20260918-191315-935ce76`; it is a layout-geometry pass, not a simulation one, so this row's verdict is unaffected — still **UNMET**, no extraction-based re-sim at any corner. **Update this pass (2026-09-19)**: this issue's own `--abstract-cells` ablation probe re-ran the flow to measure against a freshly built composition, minting `20260919-050355-fb11617` at a field-identical DRC/LVS verdict; it is an LVS-shape measurement, not a simulation one, so this row's verdict is again unaffected — still **UNMET**, no extraction-based re-sim at any corner. **Update this pass (2026-09-24, later)**: issue #362 re-ran the flow after adding the top-level analog `GND` pad ([DR-012](../../spec/decision-records/DR-012-analog-ground-pad.md)), minting `20260924-214710-b323061`; it is a layout/interface change, not a simulation, so this row's verdict is unaffected — still **UNMET**, no extraction-based re-sim at any corner. **Update this pass (2026-09-24, later still)**: issue #377 re-ran it again after meshing the three analog blocks' ground terminals ([DR-013](../../spec/decision-records/DR-013-analog-ground-mesh.md)), minting `20260924-234053-66dca3c`; again a layout change and not a simulation, so this row is again unaffected — still **UNMET**. **Update this pass (2026-09-25): no evidence has moved, but the *kind* of blocker behind this row has.** The 2026-09-15 update above read "#103 … back in this repo's ready queue", which was this row's newest word on its own tracking issue and is no longer what that issue's state means: since 2026-09-24T06:38:37Z #103 is escalated to a **human operator ruling** — a decision, not a dependency an automated re-check can clear — after a `blocked`↔`issue` re-check oscillation independently tracked as #342. This row's verdict is unchanged (**UNMET**: no extraction-based re-sim of the assembled top level at any corner) and this document does not attempt #103's work; what changes is that the gap is now correctly reported as waiting on a ruling rather than on a queue position. §7 Item 1's 2026-09-24 update is the dated tracking-state trail, and is the only place in this document that names the labels themselves (check 27) | [`layout/sar-adc-top/reports/20260924-234053-66dca3c/record.md`](../../layout/sar-adc-top/reports/20260924-234053-66dca3c/record.md) (current `reports/LATEST`, issue #377's 2026-09-24 analog ground mesh — a layout change, not a simulation, so this row stays **UNMET**; supersedes `20260924-214710-b323061`, issue #362's analog-ground pad, which supersedes `20260924-190817-f3622fc`, issue #355's digital supply-rail tie, which superseded `20260923-131726-fa1e0af`, issue #103's `klayout-tools==0.6.0` pin-bump re-run, which was field-identical and which in turn superseded supersedes `20260919-050355-fb11617`, `20260918-191315-935ce76`, `20260915-234004-76f48b9` and, before it, `20260915-213439-bf2256f`, the records this row previously cited) |
| **DRC/LVS-clean GDS, full ADC, in-repo** | brief sign-off bar | — | **PARTIAL — DRC MET, PIN DECLARATION MET, LVS DEVICE MATCH UNMET / BLOCKED**. `klt drc`: clean, 0 violations, on the composed top-level GDS, re-confirmed after PR #227. `klt lvs` pin promotion: **exact** — layout=19/reference=19/matched=19 — via PR #227's `--pin-source-cells` fix (klayout-tools#1513/#1515), resolving the prior pin-declaration mismatch. `klt lvs` device match: still a mismatch (869/869 devices, matched 794 — unchanged, since the same flattened netlist is compared, only pin promotion changed) — root-caused to a second, distinct upstream gap: `options.combine_devices` has no per-subcircuit scoping, and the five sub-blocks do not all need the same setting. Filed at [klayout-tools#1552](https://github.com/2AMLogic/klayout-tools/issues/1552), which **closed**, fixed by klayout-tools#1556 (commit `5598e540`), but like klayout-tools#1515 before it, not yet in a published release — PyPI still tops out at 0.4.0. klayout-tools#1556's own `combine_devices_per_circuit` helper turned out to skip the existing whole-netlist path's `#559`/`#1497` resistor-offset and capacitor-C corrections, flagged as an unverified caveat and filed at [klayout-tools#1557](https://github.com/2AMLogic/klayout-tools/issues/1557); that issue has since **closed** too, fixed by klayout-tools#1560 (commit `2d603ba5`), again not yet in a published release at the time this row was last graded. **Update this pass (2026-09-15)**: `klayout-tools` `v0.5.0` published 2026-09-15T02:19:49Z and verified to contain all three of #1515, #1556, and #1560 (each is an ancestor of the `v0.5.0` tag per `gh api .../compare/v0.5.0...<commit>`, see §7 Item 1) — the release-gate blocker has cleared. #103 was back in this repo's ready queue at that pass (§7 Item 1 carries the dated tracking-state trail; it has moved several times since — see this row's 2026-09-25 update below), but this row stays UNMET/BLOCKED rather than MET: no new `layout/sar-adc-top/` record has landed yet showing a v0.5.0-built device match, so whether the gap actually closes is still #103's open finding to report. **Citation re-pointed this pass** (same residual as the row above): re-pointed onto `20260908-072857-80df05e`, `reports/LATEST` at that moment, verified byte-for-byte equivalent to the prior `20260907-110058-a546200` citation — no verdict changes. **Update (2026-09-15, later): the v0.5.0 build this row was waiting on has since run, in #103's PR #275, now merged (2026-09-15T22:00:46Z) — the gap did not close, and in fact regressed before a second fix narrowed it back down.** `klt drc` stays clean; `klt lvs`'s device match moved from the pre-bump 98 mismatches to 128 (a stale hand-transcribed `sampling_frontend` pin table, unrelated to the tool bump, contributed 4 of those), then to 124 once that table was corrected against the current committed GDS — still not a match, and worse than the pre-bump baseline this row previously cited. Root-caused, per PR #275, to two distinct upstream gaps, both filed generically this pass and both still open: [klayout-tools#1876](https://github.com/2AMLogic/klayout-tools/issues/1876) (the `#1558`/`#1564` "write bare `C` cards for unbound capacitors" fix drops the capacitor device class's own name from extracted SPICE text, so this flow's pre-extracted-netlist `klt lvs` shape can no longer resolve capacitor devices to their reference-side counterpart by class name) and [klayout-tools#1878](https://github.com/2AMLogic/klayout-tools/issues/1878) (`options.combine_devices_per_circuit`, klayout-tools#1556's own fix for the *previous* blocker this row named, is a no-op for a `klt gen-compose`d layout: `klt extract`'s layout-side output is always one flat circuit — hierarchical extraction still doesn't exist, klayout-tools#1085 — so there is no per-macro subcircuit boundary left for the per-circuit flag to scope). This row stays **UNMET/BLOCKED**, now on #1876/#1878 rather than on the v0.5.0 release gate, which has cleared. **Citation re-pointed onto that build**: PR #275 merged, so `20260915-213439-bf2256f/` is part of this repo's own committed `reports/` tree and `layout/sar-adc-top/reports/LATEST` resolves to it — its `lvs.json` is the primary source for the 124 figure quoted above (`status: "mismatch"`, `mismatch_count: 124`, `error_count: 123`, `counts.devices` 869 layout / 869 reference / 794 matched, `counts.pins` 19/19/19, `category_counts: {device.unmatched: 99, net.merged: 12, net.split: 10, topology: 2, topology.flattened: 1}`), and its `drc.json` reports `violations: []`. **Update (2026-09-16): klayout-tools#1876 is now neutralised locally, `Part of #103` (PR #287, merged 2026-09-15T23:27:08Z)** — `layout/sar-adc-top/bin/restore-cap-device-class.py` restores each capacitor's device-class token onto its `C` card from `klt extract`'s own per-instance provenance comment before the LVS request, reproducing the **pre-0.5.0 98-mismatch / 412-matched-net** baseline exactly (`device.unmatched: 75`, `net.merged: 12`, `net.split: 10`, `topology.flattened: 1`; the spurious capacitor-class `topology: 2` category is gone). **klayout-tools#1878 remains the sole blocker** — still UNMET/BLOCKED, better than the 124-mismatch figure this row previously carried but not a match. A fourth LVS shape was then measured, `Part of #103` (PR #290, merged 2026-09-16T00:02:07Z): `--abstract-cells` black-boxing the three sub-blocks whose `combine_devices` need opposes the other two, against a matching hollowed reference, narrows the same composed GDS to **6 mismatches** (`device.unmatched: 3`) — but all 6 trace to a new, distinct defect (`--abstract-cells` silently drops `cdac_array`'s label-less 4th port, corrupting unrelated net names), filed generically as [klayout-tools#1911](https://github.com/2AMLogic/klayout-tools/issues/1911) and **not adopted for signoff** pending independent confirmation the corruption is cosmetic — `run-flow.sh` is unchanged and the recorded attempt stays the audited 98-mismatch compare. This row's verdict does not move: still **UNMET/BLOCKED**, on klayout-tools#1878 (with #1911 as a further open item, not yet actionable). **Update (2026-09-16, later)**: klayout-tools#1876 and #1878 have both since closed upstream (2026-09-16T03:44:54Z and 2026-09-16T03:43:13Z respectively) — #1876 via a genuine code fix ([klayout-tools#1921](https://github.com/2AMLogic/klayout-tools/pull/1921), merged, commit `c5438290`), #1878 via a **documentation-only** fix ([klayout-tools#1924](https://github.com/2AMLogic/klayout-tools/pull/1924)) that confirms, rather than closes, the underlying capability gap (`klt extract` still has no hierarchical/per-macro subcircuit output). Neither fix is in a published release — `klayout-tools` is still at `v0.5.0`, and `c5438290` is 48 commits ahead of that tag (`gh api .../compare/v0.5.0...c5438290`). klayout-tools#1911 remains open. **Update (2026-09-16, still later): klayout-tools#1911 has since closed too, via a genuine code fix** — [klayout-tools#1934](https://github.com/2AMLogic/klayout-tools/pull/1934) ("fix(extract): stop `--abstract-cells` from corrupting unrelated net names"), merged 2026-09-16T09:50:33Z, commit `ad3f8363`. Its own body traces the corruption to `--abstract-cells` erasing a black-boxed cell's `nwell`/`substrate_isolation` before the whole-layout body-identity classification pass reads them, which could merge unrelated substrate-tied nets under one bogus composite label — the same defect class this row's #1911 filing observed — and adds regression coverage for it (`test_abstract_cells_does_not_merge_unrelated_nets_onto_the_global_net`). This closes out all three of the upstream gaps this row has tracked (#1876, #1878, #1911), but **none of the three fixing commits is in a published release**: `klayout-tools`'s latest tag is still `v0.5.0`, and `gh api repos/2AMLogic/klayout-tools/compare/v0.5.0...ad3f8363` reports `ahead_by: 61, behind_by: 0`. Per this repo's own established practice (set by #103's PR #275), the row stays graded against what is released, not what is merged-but-unreleased. This row's verdict does not move: still **UNMET/BLOCKED**, now waiting solely on a `klayout-tools` release containing all three fixes rather than on any open upstream issue — see §7 Item 1 for the full trace. Citation re-pointed onto the record that produced both increments' numbers. **Update this pass (2026-09-18), issue #326 — the DRC half of this row was narrower than it read.** `klt drc`'s clean verdict covers the 47 rules the curated `sky130` deck authors at the pinned `klayout-tools==0.5.0`, across five kinds (`width`, `space`, `enclosing`, `separation`, `isolated`) — it authors **no `area`-kind rule**, so sky130A's own metal minimum-area rules (`m1.6`, `m2.6`, `m3.6`, `m4.4a`, `m5.4`) had never looked at this layout. Measured directly with [`docs/chipalooza/measure_metal_min_area.py`](measure_metal_min_area.py) (added this pass: it reads the thresholds and layer numbers out of the pinned PDK's own deck and applies KLayout's own `Region#with_area`, the primitive that deck's rule text calls), the superseded record's composed GDS carried **17 shapes below `m3.6`/`m4.4a`** that this flow's own router drew — 12 met3 + 1 met4 from `layout/sar-adc-top/bin/build_layout.py`'s via risers and 4 met3 from `layout/sampling-frontend/bin/build_layout.py`'s stacked-via pads. Both generators now size a pad that stands alone on its own layer to clear that layer's own minimum-area rule, and the re-composed record cited here measures **0** sub-minimum met3/met4 shapes, at an unchanged DRC verdict (clean, 0 violations) and an unchanged LVS verdict (98 mismatches, 869/869/794 devices, 444/446/412 nets, 19/19/19 pins, same four categories). What remains below threshold in the composed GDS is **145 shapes on met1/met2/met3/met5 that `klt`'s own place-and-route emitted** inside the two digital macros (generated via cells `VIA_L1M1_PR_MR`/`VIA_M2M3_PR`/`VIA_via5_6_*` plus router-drawn stubs; no `sky130_fd_sc_hd__*` library cell violates anything) — tracked as #333 here and filed generically upstream as [klayout-tools#2072](https://github.com/2AMLogic/klayout-tools/issues/2072). So the DRC component of this row is **MET for the deck's 47 rules and, for this repo's own drawn geometry, for minimum area as well** — scope-limited only by the 145 tool-emitted shapes and by the fact that minimum area is still measured out-of-band until a `klayout-tools` release carries [#1989](https://github.com/2AMLogic/klayout-tools/pull/1989)'s `met1.area.1`…`met5.area.1` rules. The row's overall verdict does not move: still **UNMET/BLOCKED** on the LVS half. **Update this pass (2026-09-19)**: this issue's own `--abstract-cells` ablation probe re-ran the flow so the probe measures against a freshly built composition, minting `20260919-050355-fb11617` — DRC still clean at 0 violations, LVS still `mismatch` at 98 mismatches/97 errors, 869/869/794 devices, 444/446/412 nets, 19/19/19 pins and the same four mismatch categories, i.e. field-identical to the record it supersedes, and the probe's corrected diagnosis (see §7 Item 1) does not change any of them. Verdict unchanged: still **UNMET/BLOCKED** on the LVS half. **Update this pass (2026-09-24): the DRC half's minimum-area scope limit above is stale, and minimum area is now graded in-deck.** The paragraph above, dated 2026-09-18, scoped the DRC component to "the deck's 47 rules" plus an out-of-band minimum-area measurement "until a `klayout-tools` release carries #1989's `met1.area.1`…`met5.area.1` rules". That release has landed and is pinned: issue #103's `klayout-tools==0.6.0` bump (PR #352, `layout/requirements.txt`) carries them. Read directly from the cited record's own `drc.json` `coverage`: **52** rules checked, **0** skipped, **5** inapplicable (`capm2.*` and `met4.enclosing.capm2.1`, all `no_applicable_geometry` — this layout draws no `capm2`), and the 52 include `met1.area.1`, `met2.area.1`, `met3.area.1`, `met4.area.1` and `met5.area.1` plus the matching `met*.holes_area.1` rules — status **clean**, **0** violations. The 0.6.0 re-run it supersedes, `20260923-131726-fa1e0af`, already checked the same 52 rules including all five `met*.area.1`, also clean at 0. So the DRC component of this row is now **MET against the curated deck's own minimum-area rules**, not only against an out-of-band stand-in, and the "145 tool-emitted shapes" residual no longer scopes it: that figure came from [`docs/chipalooza/measure_metal_min_area.py`](measure_metal_min_area.py), which issue #363 (open at the time) had since found **under-merges** the region it measures and so overstates its sub-minimum counts — on this same composition's met5 it reported via-cell shapes lying wholly inside a PDN strap as sub-minimum, where the deck's own `met5.area.1` reports none. **Resolved (2026-09-24, issue #363)**: the under-merge is fixed — `Region#insert(RecursiveShapeIterator)` carries GDS user properties into the region and KLayout's merge is property-aware, so a property-tagged PDN strap never merged with the untagged via cells inside it — and the corrected re-measurement of this same record reports **0** shapes below every one of `m1.6`/`m2.6`/`m3.6`/`m4.4a`/`m5.4`, matching the deck's own `met*.area.1` result exactly. The "145 residual shapes" figure is retracted, and issue #333's waiver of those residuals is **withdrawn rather than reaffirmed** — there was nothing to waive (see `layout/sar-sequencer/README.md` and `layout/seln-inverters/README.md`, whose 112- and 33-shape waivers both correct to 0). This row's grading is unaffected either way: it cites the deck's own in-deck `met*.area.1` result, not the out-of-band script. The row's overall verdict does not move: still **UNMET/BLOCKED** on the LVS half (88 mismatches on the cited record, §4's machine-checked sign-off-bar readout). **Update this pass (2026-09-24, later)**: the `--abstract-cells` path's two blockers, klayout-tools#2396 and #2398, have both since closed upstream via real code fixes (commits `a34fd79`/`c01c50c`, merged 2026-09-24T06:04:21Z/08:09:47Z respectively) — neither is in a published release yet (`klayout-tools==0.6.0`, the current PyPI/tag, was published 2026-09-22T18:52:45Z, and `gh api .../compare/v0.6.0...<commit>` reports each fix commit `ahead_by` 51/54, `behind_by` 0 — downstream of the tag, not an ancestor of it; see §7 Item 1 for the full re-check). This row's verdict is unaffected either way: the whole-request compare above, not the never-adopted `--abstract-cells` shape, is what grades it.. **Update this pass (2026-09-24, later still)**: issue #362 gave the analog ground its own top-level pin ([DR-012](../../spec/decision-records/DR-012-analog-ground-pad.md)) and re-ran the flow, minting `20260924-214710-b323061`. The verdict does not move and neither does a single LVS number: DRC still clean at 0 violations, still **88** mismatches in the same four categories, same 803/869 devices and 411/443 nets. What does move is the pin row, to **21 layout / 22 reference / 22 matched** — the reference now carries `GND` and `VGND` as two ports of what the layout extracts as one net (`GND|VGND`, the shared p-substrate that bulk sky130 offers no way to split), so one promoted layout pin answers both reference ports. `layout < reference` here is DR-012's central physical fact showing up in a count, not a missing pin. **Update this pass (2026-09-24, later still)**: issue #377 meshed all three analog blocks' own drawn ground terminals into that pad ([DR-013](../../spec/decision-records/DR-013-analog-ground-mesh.md)), minting `20260924-234053-66dca3c`, and **not one LVS or DRC number moves**: still clean at 0 violations across the same 52 rules, still **88** mismatches in the same four categories, same 803/869 devices, 411/443 nets and 21/22/22 pins. That immobility is the point rather than a disappointment — the p-substrate already joined those nets, so no ordinary verdict here can see a ground mesh appear or disappear; the evidence that the drawn conductor is what joins them is an ERC ablation (`layout/sar-adc-top/bin/probe-ground-mesh.py`: remove the mesh and nothing else, and `GND` splits into 2 islands), committed at `erc-reports/20260924-234116-66dca3c/ground-mesh-ablation.json`. This row's verdict does not move: still **UNMET/BLOCKED** on the LVS half. **Update this pass (2026-09-25): same correction as the row above — the LVS half's blocker is now a human ruling, not a queue position.** #103, which owns the composed-GDS LVS work this row grades, has been escalated to a human operator since 2026-09-24T06:38:37Z (see #342 for the re-check oscillation that prompted it); the 2026-09-15 update above, which read "#103 … back in this repo's ready queue", was this row's newest word on that issue and no longer describes it. No LVS or DRC number moves and no verdict moves: still **PARTIAL — DRC MET, PIN DECLARATION MET, LVS DEVICE MATCH UNMET/BLOCKED** at 88 mismatches on the cited record. §7 Item 1's 2026-09-24 update carries the dated tracking-state trail (check 27) | [`layout/sar-adc-top/reports/20260924-234053-66dca3c/record.md`](../../layout/sar-adc-top/reports/20260924-234053-66dca3c/record.md) (current `reports/LATEST`, issue #377's 2026-09-24 analog ground mesh: DRC clean at 0 violations, LVS still `mismatch` at **88**, pin promotion **21/22/22**, 803/869 devices matched — field-identical to the record it supersedes; supersedes `20260924-214710-b323061`, issue #362's analog-ground pad, which reported the same 88 mismatches and introduced the 21/22/22 pin row (DR-012), and which supersedes `20260924-190817-f3622fc`, issue #355's digital supply-rail tie, which reported the same 88 mismatches at pin promotion 21/21/21 — the two new top-level digital supply pins `VPWR`/`VGND` (DR-010) — and which superseded `20260923-131726-fa1e0af`, issue #103's `klayout-tools==0.6.0` pin-bump re-run, which reported DRC clean at 0 violations and LVS `mismatch` at 98, field-identical to `20260919-050355-fb11617`; the `--abstract-cells` path is now blocked on klayout-tools#2396/#2398 rather than #2142, see `layout/sar-adc-top/README.md`; supersedes `20260919-050355-fb11617`, this issue's `--abstract-cells` ablation-probe re-run, which superseded `20260918-191315-935ce76`, issue #326's minimum-area re-composition, at a field-identical DRC/LVS verdict, which in turn superseded `20260915-234004-76f48b9` at a field-identical DRC/LVS verdict, which in turn superseded `20260915-213439-bf2256f`, the 124-mismatch record this row previously cited, and the intermediate `20260915-222624-10afb15`), [`layout/sar-adc-top/README.md`](../../layout/sar-adc-top/README.md) |

### Reproducing this table

Every citation above is re-runnable from a clean clone with the PDK
installed, per [`docs/environment-setup.md`](../../docs/environment-setup.md).
`python3 sim/run_corners.py --list` enumerates the corner-run experiments
cited; `python3 sim/monte_carlo.py --list` enumerates the Monte Carlo
campaigns (ENOB/INL/DNL rows). `python3 sim/report/generate.py --check`
verifies `docs/characterization-report.md` — the machine-checked source this
table restates — is fresh against current `sim/`/`layout/` evidence; it is
run in CI on every pull request, and passes
(`OK: ... is fresh and up to date (12 rows)`).

**That row count is re-derived, not transcribed** (check 24 of the [citation
gate](check_proposal_citations.py), added 2026-09-25). It read `11 rows` from
this document's first pass (PR #140, 2026-09-05) until this one, which was
true when it was written and stopped
being true on 2026-09-24, when commit `86e905e` (PR #366, issue #361) added
the DRAFT Kickback row [DR-011](../../spec/decision-records/DR-011-comparator-kickback-target-row.md)
proposes to `sim/report/manifest.py` — the twelfth row of the report this
table mirrors. Three later passes then edited that same Kickback row in §4
(PRs #393, #395, #396) without the sentence one paragraph above the table
moving, because nothing re-derived it: the quoted line is a *machine output
living in prose*, the same shape as the census two paragraphs below, which
drifted for the same reason and was gated for it. The number now comes from
`sim/report/manifest.py`'s own `ROWS` table, in both directions — a document
that names the command and quotes none of its output fails too, so deleting
the quotation is not a way to pass.

**This document's own citations are now machine-checked too** (added
2026-09-16; `npm run check:proposal-citations`, wired into `npm run check:ci`
and therefore into the always-on headless CI job):
[`docs/chipalooza/check_proposal_citations.py`](check_proposal_citations.py)
verifies that every path this document cites resolves, that **every row of the
table above cites the *current* record of each `sim/`/`layout/` flow that
publishes one** — as resolved from that flow's own `records/LATEST` /
`reports/LATEST` pointer, not merely a record that was current when the row
was written — and that every *attached* "current `…/LATEST`" claim in the
prose is both true and named against the right pointer file for its tree
(`sim/` campaigns record under `records/`; the `layout/` flows under
`reports/`). Rows may still cite superseded records alongside the current one,
which is how this document keeps a supersession trail visible; what they may
no longer do is cite *only* a superseded one.

**What that row-freshness claim excludes, stated rather than glossed over**
(the sentence above read "of each `sim/`/`layout/` flow it draws on" until
2026-09-25, which overstated it in the same way the pointer-claim sentence
further down once did): the check resolves "the current record" of a flow from
that flow's own `LATEST` pointer file, so a flow that publishes **no** pointer
has nothing to be stale against and the citation is skipped — silently, and
in a cell that reads exactly like a graded one. **Two** of the `sim/`
campaigns this table cites publish no pointer (down from four as of
2026-09-25, issue #405 — see below), and for both that is **correct rather
than an oversight**, and for the same underlying reason:

- `sim/comparator-decision`'s thirteen records are not a supersession chain
  but three distinct claims — input-referred noise, decision delay, and
  kickback — which three different rows above cite separately, so no single
  record of that campaign is "the current" one and minting a pointer would
  force a false answer.
- `sim/cdac-array-transfer`'s four records are likewise not a supersession
  chain, just along a different axis: a ratified V_REF/LSB
  structural-and-functional check (cited alone by the `V_REF` row) and two
  INL/DNL Monte Carlo scorings against two different DRAFT target candidates
  (cited together by the `INL / DNL` row) are three distinct claims about the
  same DUT — every one of the four records carries `Supersedes: (none)`.
  Issue #405 set out to mint `records/LATEST` for this flow alongside
  `sim/enob-estimate` and `sim/sar-sequencer-behavioral` (its own filing
  named all three as "unambiguous, single-mode" campaigns) and found, while
  implementing it, that `sim/cdac-array-transfer` is not: whichever of the
  four records a single tree-wide pointer named, its stamp would be disjoint
  from at least one of the two rows citing this flow, forcing a false
  "superseded" reading of a citation that is not stale, merely about a
  different claim. So this flow joins `sim/comparator-decision` in staying
  pointerless, on the same reasoning, rather than being forced into the
  "one campaign, one current record" shape the other two newly-pointed flows
  below actually have.

What can drift unnoticed is not that either set exists but its *size and
membership*, so that is gated (check 18), in the same shape check 6 gates the
pointer-claim census below:

> of the **22** (spec row, evidence flow) citation pairs in Section 4's
> table, **17** name a flow that publishes a `LATEST` pointer and are
> therefore freshness-checked by check 3; the remaining **5** name a flow that
> publishes none, whose current record nothing grades:
> `sim/cdac-array-transfer` (**4** records), `sim/comparator-decision`
> (**14** records).

`python3 docs/chipalooza/check_proposal_citations.py --stats` prints that
sentence live, to be pasted back in when it moves. It is graded in both
directions: a campaign that starts publishing a pointer must leave the list,
and a row that starts citing a pointerless campaign must join it — shrinking
the list is the cheapest way to make this gate's coverage read better than it
is. The record count is stated per flow because it is what says how large each
hole is: `sim/cdac-array-transfer`'s four records narrow what either of its
two rows' citations could have meant far less than a one-record campaign
would, and `sim/comparator-decision`'s thirteen widen that same uncertainty
further still — a citation chosen out of a set nothing re-derives.

`sim/enob-estimate` and `sim/sar-sequencer-behavioral` are the two campaigns
that *did* turn out to be single-current-record, and now publish
`records/LATEST` (issue #405): each is cited from exactly one row above (`ENOB`
and `Resolution N` respectively), so a tree-wide pointer cannot land on two
rows' disjoint stamp sets the way `sim/cdac-array-transfer`'s can. Minting
their pointers surfaced one genuinely stale citation apiece — `Resolution N`
was still citing `sim/sar-sequencer-behavioral`'s pre-#263 record, and `ENOB`
was citing an `sim/enob-estimate` record one re-run behind the flow's own
`records/LATEST` — both re-pointed above, in each case reproducing the same
figures the superseded record already reported (no verdict moved).

The same gate also compares this table against
[`spec/target-spec.md`](../../spec/target-spec.md) row by row and grades the
verdict column against the vocabulary the section preamble defines (checks 7
and 8, added 2026-09-16). Those two are described once, in the preamble above
the table, and deliberately not restated here — the census paragraph below is
the standing reminder of what a second, hand-maintained copy of the same fact
does to this document.

As of 2026-09-17 the gate also reaches outside §4: check 10 compares §2's I/O
table, and the `.subckt` line §2.3 quotes, against
`design/sar_adc_top.spice`'s own top-level port list in both directions, and
recomputes §2.2's slot totals from that table's own Count and slot columns.
That one is described once too, in §2.2 and §2.3.

**What "attached" excludes, stated rather than glossed over** (this paragraph
first claimed the pointer check covered *every* such phrase, which overstated
it): a pointer claim is checked only when the phrase directly follows the
record path it is about, with nothing between them but link/quote punctuation
and an optional "the"/"record:" connector.

**Census, machine-checked** (this paragraph counts itself, its own two quoted
examples below included): of the **28** "current `…/LATEST`" phrases in this
document, **16** are attached and therefore checked; of the **12** skipped,
**7** name a record stamp within 200 characters after the phrase, and **5**
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

**The sign-off-bar numbers are gated too, not just the citation they hang
off** (check 9, added 2026-09-17). Checks 3 to 5 above gate *which* record a
row cites; until this check they said nothing about the figures the row quotes
*out of* that record — and those are exactly what the brief's two sign-off-bar
rows are graded on. They move: this document has already carried 98, then 128,
then 124, then 98 again as `layout/sar-adc-top/` was re-run against successive
`klt` builds, and on each of those moves it was a human re-read, not a check,
that carried the numbers forward with the citation. The readout below is now
the document's single present-tense statement of them, recomputed from that
record's own `drc.json`/`lvs.json` and compared field by field (including the
whole mismatch-category mapping, in both directions):

> **Sign-off-bar readout, machine-checked:**
> on the record `layout/sar-adc-top/reports/LATEST` resolves to, `klt drc`
> reports status **clean** with **0** violations, and `klt lvs` reports status
> **mismatch** with **88** mismatches and **87** errors; devices **869**
> layout / **869** reference / **803** matched; nets **443** / **444** /
> **411** matched; pins **21** / **22** / **22** matched; by category
> `device.unmatched: 66`, `net.merged: 11`, `net.split: 10`,
> `topology.flattened: 1`.

The readout above moved on 2026-09-24, for the first time in this document's
history in the *improving* direction: issue #355 tied the two standard-cell
macros' own digital supply rails together and out to two new top-level supply
pins (`VPWR`/`VGND`, [DR-010](../../spec/decision-records/DR-010-digital-supply-domain-partition.md)),
which takes the pin counts from 19/19/19 to **21/21/21** and the compare from
98 mismatches to **88** (nine more devices matched, 794 → 803, and one fewer
`net.merged`). Nothing about the LVS *blocker* changed — the remaining 88 are
the same klayout-tools#1878 `combine_devices`-scoping category mix as before,
now over two fewer nets on each side because each rail is one net instead of
two. What changed is that the digital section is now structurally powerable,
which is a separate claim graded by `klt erc` (§3's ERC bullet and §7 item 9),
not by this readout.

`python3 docs/chipalooza/check_proposal_citations.py --stats` prints that
sentence for every `layout/` flow, so a pass whose re-run moves the numbers
pastes the new one in rather than hand-transcribing it.

**That gate now covers six flows, not one** (2026-09-17). Check 9 grades every
readout the document states, and the document stated exactly one — the composed
top level's, above — which left the five sub-block flows it is composed from
ungated: their verdicts lived in §3 as the words "DRC-clean and LVS-clean", and
the one §4 row that grades on them (*Digital sequencer/output register —
physical implementation*) cited a README rather than a dated record. §3's
"Sub-block sign-off readouts" block now states all five in this same sentence
form, so a sub-block re-run that moves a device count, a category, or a verdict
word fails CI here. That is not a hypothetical drift class for this design:
`layout/cdac-array/`'s first LVS "match" verdict did not reproduce against its
own committed artefacts (#148), and a hand re-read is what caught it.

What this check deliberately does **not** do is parse figures out of §4's or
§7's prose: those
sections are full of *dated historical* numbers that were true when written
(the 128 and 124 above among them), and grading them as present-tense claims
would fail the gate on correct prose — the same reason checks 4 and 5 skip the
stamp-after-claim form. **No verdict moves because of this check**: the
readout states the same DRC-clean / LVS-mismatch result §4's two sign-off-bar
rows already carry, which is why it could be added without re-grading either.

**The gate now also grades what a row does *not* cite** (check 11, added
2026-09-17), because checks 3 to 9 structurally cannot. Each of those grades a
row against the evidence it already cites; none can see the opposite defect —
a row graded while ignoring a campaign this repository has already indexed as
that row's own evidence. That is exactly what had happened to the Power row:
`sim/full-conversion-transient/` had carried a 9-corner whole-ADC power table
since 2026-09-12, indexed under the Power row of
[`sim/spec-coverage.json`](../../sim/spec-coverage.json) and written out in
full in
[`docs/characterization-report.md`](../../docs/characterization-report.md) —
the very source this section says this table is derived from — while this
table still read "no full-block power campaign exists" and cited only a
digital sub-block's PnR estimate. Every other check passed on that row: its
one citation was current, its bounds matched, its status word agreed. The
defect was an *absence*, and an absence cites nothing that can go stale.

Check 11 compares the row set against `sim/spec-coverage.json`, this repo's
own spec-row → bench → evidence-record index (T1 item 9, issue #31), whose own
completeness and pinning are already gated by `sim/check_spec_coverage.py`:
for every indexed row whose claim rests on committed evidence
(`ratified-measured` / `draft-informational`), the §4 row of the same
parameter must cite a record of every `sim/` campaign indexed under it. That
index is the basis rather than a list inside the checker, so a campaign
indexed under a spec row is discovered here automatically rather than when
someone remembers to add it. `structural` and `methodology` rows are excluded
by *class*, not by name — the index's own vocabulary says they name no DUT
quantity, and their rows cite schematics and corner-harness directories rather
than records — and this table's `| same record |` deferral is resolved rather
than skipped, so inheriting a citation is held to the same parity as making
one.

It found two live gaps, both fixed in the same pass: the Power row above, and
the Sample rate row, which had never cited `sim/vcm-drive-budget/` in §4 even
though the index files that campaign under it (§7 Item 6 cited it; the graded
row did not).

**Check 12 then gates the figures a reporting row carries**, on the same
reasoning as check 9. A min/typ/max readout is hand-copied out of a record
that is re-run whenever the design changes — this campaign alone has already
carried four different power sets as issue #257, DR-008 and DR-009 landed —
and check 3 would dutifully force the *citation* forward while leaving every
number behind it untouched. The Power row therefore states its readout once,
in a fixed form naming the corner each figure was measured at, and check 12
recomputes all of it (lowest, nominal and highest corner, each with its own
power, plus how many corners the table has) from that record's own Power
table. `--stats` prints the live sentence for every `sim/` campaign whose
current record carries one, so a fix there is a paste too.

**Neither check relaxes anything, and the Power row does not become a pass**:
it moves from "BLOCKED — no evidence exists yet" to "UNMEASURED as a spec-row
figure", with informational whole-ADC evidence reported under two stated scope
caveats — which is what `docs/characterization-report.md` already said. It
stays ungraded because no ratified power line exists to grade it against, and
because the conversion those currents were measured on is not yet correct
across its full input range.

**Check 13 closes the last hand-transcribed figure in this table** (added
2026-09-17), on the same reasoning a third time. The Area row quotes a
bounding box out of `layout/sar-adc-top/`'s own `compose.json`, and that flow
has now been re-run five times (`20260906-101939-1250ff4` →
`20260907-110058-a546200` → `20260908-072857-80df05e` →
`20260915-213439-bf2256f` → `20260915-234004-76f48b9`). On every one of those
re-runs check 3 forced the *citation* forward, and a human then established by
hand — `cmp`, or a field-by-field diff of the two artefacts — that the numbers
had not moved; that row's text is a five-deep record of exactly that manual
labour. It is also labour that gets skipped precisely when it matters, because
the one re-run where the box really does change is the one where
"byte-identical, verified directly" is the wrong sentence to carry forward.
That a re-run can move geometry without moving the composed extent is not
hypothetical here: the `v0.5.0` rebuild moved `sampling_frontend`'s own
`bbox_um.y1` (146.3 → 147.22 µm) while leaving the top-level box alone. The
Area row's readout is now this document's single present-tense statement of
the extent, and check 13 recomputes all of it — the composed `cell_name`, the
four `bbox_um` coordinates, and the width, height and mm² derived from them —
from whichever record `reports/LATEST` resolves to. Figures are compared as
*formatted* at the three decimals both the sentence and the records' own
`dbu_um` use, rather than with a numeric tolerance, so a `--stats` paste can
never be rejected by a rounding edge case.

**No verdict moves because of check 13 either**: the readout states the same
bounding box and the same ≈ 0.108 mm² the Area row already carried, which is
why it could be added without re-grading anything. That row remains
*informational only* — this is a raw `klt gen-compose` extent, not an
LVS-clean sign-off-grade area figure, and `spec/target-spec.md` states no area
line to grade it against.

**Check 14 then grades the composed record's own inputs** (added 2026-09-18),
which is the one thing checks 3–13 structurally cannot see: each of those
grades a claim against the record it cites, and none looks at what that record
was built *from*. Three rows of this table — the two sign-off-bar rows and the
Area row — are graded on `layout/sar-adc-top/`'s composition, while §3's five
sub-block readouts are recomputed from each sub-block flow's own current
record. Re-run a sub-block and check 9 moves §3 forward while the composition
keeps grading the superseded geometry, every other check green. §3's "What the
composed top level is actually built from" block now states each composed
input's provenance — how many records of its own flow the embedded copy
reproduces, the newest of them, and whether that flow's pointer is among them
— and check 14 recomputes all of it by fingerprint on every CI run. **No row
below is re-graded by it**: two of the five inputs do trace to superseded
records today, but a layer-by-layer XOR (run by hand this pass, recorded in
§3) shows the composed geometry is identical to what those flows publish now,
so the three rows stand as written.

**Check 15 gates the Status column's upstream** (added 2026-09-18). Check 7
holds this table's Status cells to `spec/target-spec.md`'s own words, which is
the right comparison but not the *earliest* one: this repo ratifies a numeric
row by the operator approving the PR that carries its decision record, so the
record's own `- **Status**:` field moves from `proposed` to `accepted` first
and the spec table follows. In that window a §4 row can read `DRAFT` against a
spec file that also reads `DRAFT`, with both checks green, while the record
they rest on has already been ratified. Check 15 recomputes every
`spec/decision-records/` record's status from the record itself and compares it
against the readout §7 Item 4 now states, both directions. **No row in this
table is re-graded by it**: all ten records report the same statuses this
document already assumed — DR-001 and DR-003 `accepted`, the other eight
`proposed` — so the two DR-007-gated rows (ENOB, INL/DNL) stay *Informational
only*, exactly as before. What changes is that DR-007's eventual ratification
now fails CI at the moment the record moves, rather than at the later moment
someone edits `spec/target-spec.md`.

---

## 5. Test-plan outline (packaged part, if fabricated)

This section is written against this design's *current* port list (§2) and
would need revision once §7's open items (differential-reference budget,
top-level layout) close. **That first claim is machine-checked rather than
asserted** (check 19 of the [citation gate](check_proposal_citations.py), added
2026-09-25): every port of `design/sar_adc_top.spice` must be named somewhere
in this section, so a port added to the block's interface fails CI here instead
of leaving a bench plan that quietly describes an older part. It had gone stale
in exactly that way for a day before this check landed — **three** of the four
supply terminals below joined the interface on 2026-09-24, after this section
was first written (`VPWR`/`VGND` by
[DR-010](../../spec/decision-records/DR-010-digital-supply-domain-partition.md)
via issue #355, `GND` by
[DR-012](../../spec/decision-records/DR-012-analog-ground-pad.md) via issue
#362), and step 1 went on powering the 19-port block meanwhile.

**Supply terminals, machine-checked too**: this part presents **4** supply
terminals — `VDD`, `VPWR`, `VGND`, `GND` — and that set is recomputed from
§2.2's own rail rows (the rows charged against no slot) in both directions, so
neither a rail dropped from this list nor one invented in it survives CI.

1. **Bring-up / DC sanity.** Feed the **analog** rail `VDD` = 1.8 V and the
   **digital** rail `VPWR` = 1.8 V from the same 1.8 V supply point but on
   separate feeds, and bring the analog return `GND` and the digital return
   `VGND` back separately to a single **off-die** star point. Both
   [DR-010](../../spec/decision-records/DR-010-digital-supply-domain-partition.md)
   (Decision item 5) and
   [DR-012](../../spec/decision-records/DR-012-analog-ground-pad.md) (Decision
   item 5) put that star point off-die deliberately and neither specifies it
   further; `sim/full-conversion-transient/`'s own testbench already drives
   `VDD`, `VPWR` and `VGND` as independent sources returning to one node, so
   the bench arrangement mirrors the simulated one rather than inventing a
   second convention. **Do not bond `GND` and `VGND` together at the socket.**
   On-die they are already one node — bulk sky130 offers no isolation, and this
   composition's own extraction reports them as the single net `GND|VGND`
   (692 devices, per DR-012's "Verified, not assumed") — so a package-level
   short between them changes nothing electrically *and* destroys the one thing
   the split buys: a digital return that travels off-die instead of through the
   substrate past the comparator. A board that ties them makes DR-010's
   partition unmeasurable on silicon, which is the same reason DR-010 and
   DR-012 both rejected tying them in metal. Then apply `VREFP`/`VREFN`
   (0/1.8 V or the harness-supplied equivalent) and `VCM` = 0.9 V, and confirm
   quiescent supply current on **each** of `VDD` and `VPWR` separately (see
   step 6) with no input applied, `CLK` free-running, `RST_B` deasserted.
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
6. **Power.** Measure supply current **per terminal**, not on `VDD` alone.
   §4's Power row carries a simulated ADC-core figure over the ratified
   9-corner grid to compare a bench measurement against, but that figure is
   a sum over the **5** current columns of
   `sim/full-conversion-transient/records/LATEST`'s own Power table —
   `I(VDD)`, `I(VPWR)`, `I(VREFP)`, `I(VCM)`, `I(VREFN)` — of which `VDD` is
   one term, and not the dominant one. A single `VDD` ammeter reading is
   therefore **not** comparable to the µW figure that row quotes; each of
   those five feeds needs its own series measurement, which is also why step 1
   asks for quiescent current on `VDD` and `VPWR` separately. (Four of the five
   carry a *power* term: the cited record states that `VREFN` sits at 0 V and so
   contributes none, which is why its current is recorded but does not enter the
   sum. Meter it anyway — a nonzero `VREFN` potential on a bench is itself the
   finding.) That term list is
   recomputed from the cited record's own Power-table header by check 19, so a
   re-measurement that adds or drops a source cannot leave this step metering a
   different set of terminals than §4 sums over. The comparison's own caveats
   are §4's and are unchanged: the simulated figure is the ADC core only (every
   rail and reference in that testbench is an ideal source — this design has no
   reference buffer, clock generator or output driver yet), and it is the
   current of a conversion that is not yet code-correct across its full input
   range (§7 Item 8), so it is a sanity scale rather than an expected result.

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
   **device-level match** on the composed GDS (currently 88 mismatches — see
   §4's machine-checked sign-off-bar readout; 98 before issue #355's
   2026-09-24 digital supply-rail tie), and
   **any post-layout PVT re-simulation** of the assembled top level (none has
   been run at any corner). Tracked as
   #103 (top-level routing/assembly), which lists #99, #100, #101, and #102
   as its four sub-block dependencies — **all four are now closed.** #99
   (sampling front-end layout) closed via PR #152 (merged
   2026-09-05T23:22:50Z): DRC-clean and LVS-clean, 24/24 devices, 17/17
   nets, 12/12 pins matched, with three negative controls confirming the
   checker catches a body-tie, device-parameter, and capacitor-top-plate-net
   corruption respectively (record:
   [`layout/sampling-frontend/reports/20260924-232823-66dca3c/record.md`](../../layout/sampling-frontend/reports/20260924-232823-66dca3c/record.md),
   current `reports/LATEST` — issue #377's `GND` pin promotion, which
   supersedes `20260918-191227-935ce76/` (issue #326's minimum-area rebuild,
   itself at a field-identical DRC/LVS verdict to the
   `20260915-120718-1e90b14/` it superseded); see this item's citation-freshness corrections below for why
   that one in turn superseded `reports/20260906-230125-0904419/` and, in
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
   `layout/seln-inverters/` (nine `sky130_fd_sc_hd__inv_1` instances laying
   out `SELn<i> = NOT(DOUT<i>)`; DRC-clean and LVS-clean against its own
   hand-written gate-level netlist, PR #166 — see "The composed top level
   still implements issue #56's superseded glue" below, added 2026-09-25,
   for why that netlist is no longer this design's top-level glue) — plus a
   floorplan/routing investigation that probed
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
   **That last clause is a dated statement, superseded 2026-09-17**: the
   Power row is now graded `UNMEASURED as a spec-row figure` and reports
   9-corner informational whole-ADC power evidence from
   `sim/full-conversion-transient/` (see the row itself, and §4's
   "Reproducing this table" note on check 11, which found the omission). What
   is unchanged is the subject of the correction above: this `layout/`
   estimate stays a non-gating sub-block data point, not spec-row evidence.

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
   (superseded 2026-09-18 by issue #326's minimum-area re-composition,
   [`layout/sar-adc-top/reports/20260918-191315-935ce76/record.md`](../../layout/sar-adc-top/reports/20260918-191315-935ce76/record.md),
   and in turn 2026-09-19 by this issue's own `--abstract-cells`
   ablation-probe re-run,
   [`layout/sar-adc-top/reports/20260919-050355-fb11617/record.md`](../../layout/sar-adc-top/reports/20260919-050355-fb11617/record.md),
   and on 2026-09-23 by issue #103's `klayout-tools==0.6.0` pin-bump re-run,
   [`layout/sar-adc-top/reports/20260923-131726-fa1e0af/record.md`](../../layout/sar-adc-top/reports/20260923-131726-fa1e0af/record.md),
   and on 2026-09-24 by issue #355's digital supply-rail tie, then by #362's
   analog ground pad and #377's analog ground mesh,
   [`layout/sar-adc-top/reports/20260924-234053-66dca3c/record.md`](../../layout/sar-adc-top/reports/20260924-234053-66dca3c/record.md),
   the current `reports/LATEST` — every hop through 2026-09-23 at a
   field-identical DRC/LVS verdict, and the 2026-09-24 hop the first to move
   it (21/21/21 pins, 88 mismatches, 803/869 devices matched; DRC still
   clean), for a reason that is not about this blocker: the two digital rails
   became one net each with their own top-level pins;
   `compose.json`'s top-level `bbox_um` was byte-identical to
   `20260915-213439-bf2256f`'s, moved by 0.05 µm in `x0` only at the #326
   re-composition, and is byte-identical again across the 2026-09-19 re-run
   — see §4's Area row). **#103 itself is `loom:blocked` again as of this pass**, per its
   own 2026-09-16 dependency re-check, now specifically on
   klayout-tools#1878 (with #1911 as a further, not-yet-actionable open
   item; both confirmed still **OPEN** upstream as of this check, `gh issue
   view 1876/1878/1911 --repo 2AMLogic/klayout-tools`). §4's two sign-off-bar
   rows are re-pointed onto this record; **no verdict in §4 moves as a
   result** — DRC/LVS-clean GDS stays UNMET/BLOCKED (88 mismatches on the
   current record, 98 on every record from `20260915-234004-76f48b9` through
   2026-09-23 —
   better than the 124 this item once cited, but still not clean) and post-layout PVT stays UNMET (still no extraction-based re-sim
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
   DECLARATION MET, LVS DEVICE MATCH UNMET/BLOCKED** at 98 mismatches on
   `20260915-234004-76f48b9`, `reports/LATEST` at the time of this
   2026-09-16 update (since superseded three more times — see the
   2026-09-24 update below for the current pointer), and "Post-layout PVT
   simulation, full ADC" stays **UNMET**. #103 is still **OPEN** and still
   `loom:blocked` (re-read this pass). The blocker remains what the update
   above established — a bare release gate, with no open upstream issue
   behind it (re-searched this pass: zero open `2AMLogic/klayout-tools`
   issues request a release past `v0.5.0`) — and this repo's practice of
   grading against what is *released*, not what is merged, is unchanged.
   What this update adds is only that the gate's contents have grown,
   including in the module the local capacitor-class workaround stands in
   for.

   **Update (2026-09-24): the release gate cleared, the LVS mismatch did
   not, two newly-diagnosed upstream gaps now sit behind the
   `--abstract-cells` path, and #103 itself has been escalated to a human
   operator rather than re-blocked automatically.** `klayout-tools` `v0.6.0`
   published on PyPI 2026-09-22T18:52:45Z, and `gh api
   repos/2AMLogic/klayout-tools/compare/v0.6.0...3cc085c` confirms `3cc085c`
   (the fix this item's prior updates were waiting on, klayout-tools#2142)
   is an ancestor of the tag (`ahead_by: 0, behind_by: 107`) — the bare
   release gate the 2026-09-16 update above named has cleared. #103's own
   PR #352 (`Part of #103`, merged) bumped `layout/requirements.txt`'s pin
   from `0.5.0` to `0.6.0` and re-ran the whole flow on it:

   - The trivial-cell proof still passes all six verdicts on `klt` 0.6.0
     (`layout/trivial-cell/reports/20260923-131710-fa1e0af/`).
   - `sar-adc-top`'s whole-request `klt lvs` is **field-identical to the
     0.5.0 result**: 98 mismatches, 869/869/794 devices, 444/446/412 nets,
     19/19/19 pins, the same four categories
     (`device.unmatched: 75`, `net.merged: 12`, `net.split: 10`,
     `topology.flattened: 1` — read directly from this pass's own
     `lvs.json`). `klt drc` stays clean, 0 violations. So the release did
     not move this row's verdict either way.
   - The `--abstract-cells` collapse this item's earlier updates measured
     but never adopted for signoff **persists on 0.6.0**, and this pass
     locates why klayout-tools#2142's fix (a real bug — macro pins
     collapsing onto a parent power strap) does not touch it: abstraction
     erases a MiM capacitor's top plate but keeps the via that lands on it,
     shorting every unit cap in a black-boxed sub-block's top plate to its
     bottom plate — filed generically as
     [klayout-tools#2396](https://github.com/2AMLogic/klayout-tools/issues/2396).
     Behind that (on the modified GDS this diagnosis produced, not a
     signoff artefact), abstraction also erases a macro's well tap,
     isolating `cdac_array`'s `VDD` body pin from the parent net — filed
     generically as
     [klayout-tools#2398](https://github.com/2AMLogic/klayout-tools/issues/2398).
     Both are open as of this pass. A third finding,
     [klayout-tools#2397](https://github.com/2AMLogic/klayout-tools/issues/2397),
     is not itself a blocker but confirms
     `layout/sar-adc-top/bin/restore-cap-device-class.py` (the
     klayout-tools#1876 local workaround, §7 Item 1 above) stays load-bearing
     on 0.6.0: the upstream #1921 fix keys off a case-sensitive `.SUBCKT`
     name while `klt` upper-cases it, so it recovers 0 of this design's 1028
     capacitors. None of the three is adopted for signoff — `run-flow.sh`'s
     audited whole-request compare stays the recorded attempt, now minted at
     [`layout/sar-adc-top/reports/20260924-234053-66dca3c/record.md`](../../layout/sar-adc-top/reports/20260924-234053-66dca3c/record.md),
     the current `reports/LATEST` (superseding `20260924-214710-b323061`,
     which superseded `20260923-131726-fa1e0af`, which superseded
     `20260919-050355-fb11617`, this item's prior citations).
     Its verdict is **88** mismatches, not the 98 this item's earlier passes
     recorded: issue #355's digital supply-rail tie (DR-010) took the pins
     from 19/19/19 to 21/21/21 and matched nine more devices. None of the
     three findings above is affected — the `--abstract-cells` collapse and
     the capacitor-class workaround are unchanged, and the residual mismatch
     is the same klayout-tools#1878 category mix over two fewer nets per
     side.

   **No §4 verdict moves**: "DRC/LVS-clean GDS, full ADC" stays **PARTIAL —
   DRC MET, PIN DECLARATION MET, LVS DEVICE MATCH UNMET/BLOCKED** and
   "Post-layout PVT simulation, full ADC" stays **UNMET**. **#103's own
   label state no longer reduces to a simple OPEN/`loom:blocked` read,
   though**: a same-day Curator dependency re-check (2026-09-23T20:02:54Z)
   removed `loom:blocked`, but it addressed only the already-resolved
   `3cc085c`/`v0.6.0`-release blocker — a different blocker from
   klayout-tools#2396/#2398, which the same-day Builder re-measurement above
   had already found open. A Champion evaluation (2026-09-23T22:21:05Z)
   caught the contradiction and returned NEEDS REVISION; a second,
   unrevised cycle (2026-09-24T06:38:35Z) escalated to a human operator,
   citing both the unresolved klayout-tools#2396/#2398 gap and this issue's
   own repeated label churn — independently tracked as issue #342
   ("`blocked<->issue` re-check flip-flops on #103"). As of this pass, #103
   carries `loom:operator-only` and `loom:operator-decision` rather than
   `loom:blocked` or `loom:issue`: a human decision, not an automatable
   dependency check. This document (issue #121) is itself gated on #103 for
   acceptance criterion 3 and, per #121's own established convention, does
   not attempt #103's layout-assembly work — this update records the state
   change and the now-current citation rather than acting on it.

   **Update this pass (2026-09-24, later): both klayout-tools#2396 and
   #2398 have since closed, each via a real code fix, but neither fix is in
   a published release yet.** Re-checked live (`gh issue view 2396 2398
   --repo 2AMLogic/klayout-tools`): #2396 closed 2026-09-24T06:04:21Z via
   [klayout-tools#2433](https://github.com/2AMLogic/klayout-tools/pull/2433)
   ("fix(extract): capture the capacitor top-plate-via exclusion before
   `--abstract-cells` erasure", merged, commit `a34fd79`); #2398 closed
   2026-09-24T08:09:47Z via
   [klayout-tools#2434](https://github.com/2AMLogic/klayout-tools/pull/2434)
   ("fix(extract): restore an abstracted macro's own well tie for body
   pins", merged, commit `c01c50c`). Both commits postdate the currently
   published `klayout-tools==0.6.0` (PyPI and the `v0.6.0` tag, both dated
   2026-09-22T18:52:45Z / T18:52:48Z): `gh api
   repos/2AMLogic/klayout-tools/compare/v0.6.0...a34fd79` reports
   `ahead_by: 51, behind_by: 0`, and the same compare against `c01c50c`
   reports `ahead_by: 54, behind_by: 0` — each fix is downstream of the
   tag, not an ancestor of it, so `v0.6.0` (the pin
   `layout/requirements.txt` already carries) does not contain either.
   No newer distribution has appeared since: PyPI still gives `0.6.0` as
   the latest `klayout-tools` (`curl -s
   https://pypi.org/pypi/klayout-tools/json` → `info.version: 0.6.0`,
   with `releases` topping out at the same), and `gh api
   repos/2AMLogic/klayout-tools/tags` still tops out at the `v0.6.0` tag.
   (GitHub's Releases feature is *not* the check to use here: `gh api
   repos/2AMLogic/klayout-tools/releases` / `gh release list --repo
   2AMLogic/klayout-tools` show `v0.5.0` still marked `Latest`, because
   no Release object was ever cut for `v0.6.0` — the tag and the PyPI
   package are what "published" means for the pin this row grades
   against.)
   Per this item's own established practice (set by #103's PR #275,
   restated at every prior upstream-closure update above), the row stays
   graded against what is *released*, not what is merged — so **no §4
   verdict moves**: "DRC/LVS-clean GDS, full ADC" stays PARTIAL — DRC MET,
   LVS DEVICE MATCH UNMET/BLOCKED (88 mismatches, the whole-request compare
   that is this flow's actual signoff attempt), unaffected either way since
   the never-adopted `--abstract-cells` shape is not what grades this row.
   What changes is only the blocker's own bookkeeping: both upstream issues
   are now closed-with-fix-pending-release rather than open, consistent
   with the pattern this item has tracked for every prior upstream gap
   (#1515, #1556/#1560, #1876/#1878/#1911, #2142) — a future pass should
   re-check for a `klayout-tools` release past `v0.6.0` before re-running
   the `--abstract-cells` probe. #103's own state is unchanged by this
   check: still `loom:operator-only`/`loom:operator-decision`, a human
   decision this document does not act on.

   **Update this pass (2026-09-25): the third of PR #352's three findings,
   klayout-tools#2397, closed too — and it closed first, before either of the
   two the paragraph above records.** That paragraph's summary sentence reads
   "both upstream issues are now closed-with-fix-pending-release rather than
   open", which enumerates #2396 and #2398 only, so a reader tracking which of
   the three findings is still open would infer #2397 is. It is not.
   Re-checked live this pass (`gh api
   repos/2AMLogic/klayout-tools/issues/2397`): #2397 closed
   **2026-09-24T02:11:27Z** (`state_reason: completed`) via
   [klayout-tools#2425](https://github.com/2AMLogic/klayout-tools/pull/2425)
   ("fix(lvs): case-fold circuit/device names in capacitor recovery map key",
   merged 2026-09-24T02:11:26Z, commit `2808823`) — about four hours before
   #2396 and six before #2398, and so already closed when the
   2026-09-24T06:38:35Z Champion escalation named that trio's two blockers as
   the live gap. Like both of those, it is **not in a published release**: `gh
   api repos/2AMLogic/klayout-tools/compare/v0.6.0...2808823` reports
   `ahead_by: 43, behind_by: 0` — downstream of the `v0.6.0` tag, not an
   ancestor of it — and PyPI still gives `0.6.0` as the latest
   `klayout-tools` while `gh api repos/2AMLogic/klayout-tools/tags` still
   tops out at that same tag, which is exactly what `layout/requirements.txt`
   pins. So the release gate the paragraph above leaves open is now one gate
   over three commits (`2808823`, `a34fd79`, `c01c50c`), not two.

   **Why this third closure gets its own line rather than a footnote to the
   other two.** #2396 and #2398 sit behind the `--abstract-cells` shape this
   flow has measured but never adopted for signoff, so their release changes
   nothing this document grades until someone re-runs that probe. #2397 sits
   on the **adopted** path: it is the finding that explains why
   klayout-tools#1876's own upstream fix (#1921's reader-side capacitor-class
   recovery) recovers 0 of this design's 1028 capacitors, and the 2026-09-16
   update above had already named that upstream behaviour as the one "whose
   release would retire this repo's local
   `layout/sar-adc-top/bin/restore-cap-device-class.py` workaround" while
   correctly ruling out klayout-tools#1944 as the commit that would do it.
   `2808823` is the commit that would. Until it ships, the workaround stays
   load-bearing — and on the pinned `klayout-tools==0.6.0` that is a property
   of this tree rather than an expectation, read this pass out of the current
   record's own
   [`layout/sar-adc-top/reports/20260924-234053-66dca3c/capclass.json`](../../layout/sar-adc-top/reports/20260924-234053-66dca3c/capclass.json):
   `c_cards: 1028`, `restored: 1028`, all to
   `sky130_fd_pr__model__cap_mim`, and `noop: false`. That last field is the
   one #2397's filing predicted could never read `true` off a reader-side fix,
   so its value here is the direct in-repo evidence that the local script —
   not the pinned tool — is still what resolves this compare's capacitor class
   at all.

   **No §4 verdict moves, and nothing about #103's own state changes.**
   "DRC/LVS-clean GDS, full ADC" stays **PARTIAL — DRC MET, PIN DECLARATION
   MET, LVS DEVICE MATCH UNMET/BLOCKED** at 88 mismatches on the cited
   record, and "Post-layout PVT simulation, full ADC" stays **UNMET**; per
   this item's established practice the rows stay graded against what is
   *released*, and nothing has been. #103 was re-read live this pass and
   still carries `loom:operator-only` + `loom:operator-decision` — still a
   human ruling, not a queue position and not a self-clearing release wait,
   which is the distinction a reader skimming this item's long
   "waiting-on-a-release" trail is most likely to lose. What this update adds
   is only the third line of the same bookkeeping, and the correction that
   the trio's remaining gate is a single release rather than a partly-open
   upstream investigation.

   **The composed top level still implements issue #56's superseded glue
   (found 2026-09-25, this pass; a layout gap, newly stated here rather than
   newly created).** §3's machine-checked census is what surfaced it. Two
   artefacts of this flow were built 1:1 from the pre-DR-008 top level and
   say so in their own headers, and neither was revisited when DR-008 landed
   (2026-09-11, issue #263 / PR #266):
   `layout/seln-inverters/netlist/seln_inverters.v` ("hand-derived 1:1 from
   `design/sar_adc_top.sch`'s own `xinv_seln0..xinv_seln8` instances"), and
   `layout/sar-adc-top/bin/generate-lvs-reference.py`, whose wrapper states
   it is "mirrored 1:1 from `design/sar_adc_top.spice`'s own
   `xfe`/`xcdac`/`xcmp`/`xseq`/`xinv_seln<i>` instantiation lines" and wires
   each of that instance's `SELp<i>` pins straight to `DOUT<i>`. Neither
   `xinv_seln<i>` nor a `SELp<i> = DOUT<i>` connection exists in
   `design/sar_adc_top.spice` any more. Concretely, the composed
   `sar_adc_top.gds` contains **none** of the 33 `sky130_fd_sc_hd` and 8
   `sky130_fd_pr` instances §3's census reads out of the current schematic —
   DR-008's eighteen `and2_1`, the nine `xor2_1` readout recode, the
   `xinv_dout9n` complement, and DR-009's whole half-LSB offset network have
   no drawn geometry anywhere under `layout/`.

   **What that does and does not mean.** It is *not* a new cause of the 88
   `klt lvs` mismatches above: the reference and the layout were generated
   from the same superseded wiring, so they agree with each other, and the
   compare cannot see the divergence at all. That is precisely the problem —
   **a clean device-level match on this flow, once klayout-tools#1878 is
   fixed, would not establish that the composed GDS implements the schematic
   this repo now builds.** So the gap is not visible in any number this
   document quotes, and it widens rather than narrows criterion 3: the
   assembly needs the current glue laid out and the reference re-derived from
   `design/sar_adc_top.spice` before an LVS verdict on it means anything. **No
   §4 verdict moves** — "DRC/LVS-clean GDS, full ADC" is already PARTIAL (DRC
   MET, LVS device match UNMET/BLOCKED) and post-layout PVT re-simulation is
   already UNMET, so this adds a reason to an existing shortfall rather than
   changing a grade; nothing is relaxed. One consequence worth stating
   plainly for a reader of §4's Area row: the **0.108 mm²** composed extent it
   quotes is the extent of an assembly that omits this glue, so it is a floor
   on the real top-level area, not an estimate of it.

   Filed as **#387** against the top-level assembly (#103's scope, not this
   document's — this document compiles evidence rather than drawing
   layout), since fixing it means re-laying out the top-level glue bank and
   re-deriving the LVS reference, neither of which a documentation pass can
   do. `layout/seln-inverters/README.md` and `layout/sar-adc-top/README.md`
   carry the same stale description and are left for that issue to correct in
   the same pass that corrects the geometry, rather than edited here into
   agreement with a layout that does not yet exist.

   **#387 is now decomposed into three pieces, none of which has landed in
   this tree (re-checked live against the forge and against `layout/`,
   2026-09-25).** The gap itself is unchanged; what changed is that it has
   named owners instead of one open issue, which is worth recording here
   because a later pass will otherwise re-derive the same split. #387 stays
   open (`loom:blocked`) and keeps the whole gap. Its **first increment** — a
   dedicated place-and-route flow for the standard-cell half of §3's census — is
   open for review as **PR #402** and is **not merged**: no such flow exists
   under [`layout/`](../../layout/) at this document's own HEAD, so there is
   no in-repo record of it to cite — the citation gate's own path check
   refuses one — and nothing in §3 or §4 cites one. **#400** (open)
   carves out the other, non-standard-cell half — DR-009's `sky130_fd_pr`
   primitives, which a `klt place-and-route` flow structurally cannot draw
   (no MiM capacitor, no hand-sized analog switch, and the wrong floorplan
   home: those devices hang off the comparator's own `TOP_P`/`TOP_N` nodes).
   **#401** (open, and dependent on #400) is the composition itself:
   re-placing `layout/sar-adc-top/` against the current schematic and
   re-deriving its LVS reference from `design/sar_adc_top.spice` instead of
   from the superseded instance list — the piece that actually makes this
   flow's two compare sides independent, and therefore the piece criterion 3
   waits on. **Nothing a number in this document depends on moves**: the
   composed extent §4's Area row quotes is still the extent of an assembly
   that omits this glue (a floor, not an estimate), the LVS mismatch count is
   the same category mix over the same nets, and both §4 sign-off-bar rows
   keep the verdicts they already carry. As with #103 itself, this document
   records the state rather than acting on it — laying out a glue bank is not
   something a documentation pass does.

   **Update this pass (2026-09-25): #103's tracking state re-verified live,
   and this item is now the only place in the document that states it.**
   `gh api repos/2AMLogic/sky130-sar-adc/issues/103` returns `state: open`
   with `loom:operator-only`, `loom:operator-decision`, `loom:curated` and
   `tier:goal-advancing`, last touched 2026-09-24T06:38:37Z — unchanged from
   the 2026-09-24 escalation above, and confirming that no automated
   re-check has flipped it since. That re-verification is why this pass
   found a drift worth fixing outside this item: **§3 still read "#103 …
   still open and `loom:blocked`" and §4's two sign-off-bar rows still read
   "#103 is back in the ready queue" as their newest word on the issue** —
   two independent copies of a live forge fact, both left behind while this
   item's dated trail moved on. Both are corrected in place (no verdict
   moves in either row; the correction is to the *kind* of blocker reported,
   from a queue position to a human ruling), and the recurrence is closed
   structurally rather than by care: **check 27** of the [citation
   gate](check_proposal_citations.py) now fails CI on any `loom:` label
   stated outside this section, so a second copy cannot be started again.
   The gate cannot read the forge — nothing offline can — so what it
   enforces is that there is exactly one copy to keep current, in the
   section whose whole job is to narrate tracking state paragraph by
   paragraph and date.

   **Update this pass (2026-09-25, later): #387's three-way split has lost
   one of its three named owners, and not because that third of the work was
   done.** #400 — the carve-out for DR-009's `sky130_fd_pr` primitives, which
   a `klt place-and-route` flow structurally cannot draw — was **closed
   `not_planned`** at 2026-09-25T08:32:09Z (`gh api
   repos/2AMLogic/sky130-sar-adc/issues/400` → `state: closed`,
   `state_reason: not_planned`, read this pass). The closure grades that
   proposal draft's own citations, not the gap it describes: the draft
   presented the first increment as landed and pointed a Builder at
   `layout/top-glue/bin/check-schematic-parity.py` (not in this tree) as an
   existing precedent to copy, and the closing comment re-verified against
   `origin/main` that it is not there. That comment says the rest in terms —
   the underlying gap, the eight undrawn primitives in
   [`design/sar_adc_top.spice`](../../design/sar_adc_top.spice), is "still
   real and still worth tracking", and a revised draft would be promotable.
   So the carve-out is now **unowned**, falling back to #387, which keeps the
   whole gap and stays open (`loom:blocked`). What a later pass must not read
   into this closure is that a third of the gap closed with it.

   The other two owners, both re-read live this pass. **#401** — the
   composition, and the piece acceptance criterion 3 actually waits on — is
   still open and still `loom:blocked`. Its checklist declares **two**
   blockers, and the closure moved only one of them: the first — PR #402, the
   first increment, must merge — is still an open blocker and still clears
   the ordinary way, by that PR landing; the second, the half-LSB-offset
   carve-out, was tracked by #400 alone, and #400 closing `not_planned` left
   it with no open issue to clear at all. So the accurate statement is not
   that #401 has no open blocker left — it has one, and it is clearable —
   but that it has **no route by which it self-clears**: even after #402
   merges, a fresh proposal for the carve-out has to be filed and land
   first. **PR #402**, the first increment, is still open and still unmerged
   (`merged_at: null`), and its label state has moved again since the last
   pass recorded it here — this paragraph's own prior word (cleared back to
   `loom:review-requested` at 2026-09-25T09:30:02Z) is exactly the kind of
   live-state sentence that rots the moment written, which is why it is
   corrected in place rather than left to compound. Re-checked live this
   pass (`gh api repos/2AMLogic/sky130-sar-adc/issues/402/events`,
   2026-09-25T15:53Z): a second merge-conflict rejection and Doctor fix
   cycle (07:27Z-11:30Z) reached Judge approval and `loom:pr` at 11:49:56Z,
   then Champion's critical-file hold added `loom:operator` at 12:22:45Z —
   `.github/workflows/ci.yml`'s diff is comment-only (documenting the new
   `check:glue-parity` step, no job/step logic touched), but the
   version-only carve-out this repo's Champion config exempts is scoped to
   six named version-bearing files and does not extend to workflow files,
   so the hold is a hard fail on the path alone and stands until a human
   runs `./.loom/scripts/merge-pr.sh 402`. Champion's own automated
   re-check additionally flagged, at 15:00:40Z, that `main` has since moved
   underneath the held PR (`mergeStateStatus: DIRTY` against merge base
   `0d5a4ff5`, 3 shared files, classified "possible structural overlap" —
   a rebase read, not necessarily a conflict) without itself acting on it.
   None of this changes what #401 waits on: PR #402 still has to merge, by a
   human, and this document still only reports that state rather than acting
   on it, the same restraint it already states for #103. So `layout/top-glue/` (not in this tree)
   and `layout/halflsb-offset/` (not in this tree) are both still absent from
   `origin/main` — `git ls-tree -r origin/main --name-only` returns neither —
   and §3 and §4 still cite no record from either flow, because there is none
   to cite.

   **Nothing a number in this document depends on moves**, for the same
   reason the split itself moved none when it was recorded: the composed
   extent §4's Area row quotes is still the extent of an assembly that omits
   this glue (a floor on the real top-level area, not an estimate), the LVS
   mismatch count is the same category mix over the same nets, and both §4
   sign-off-bar rows keep the verdicts they already carry. What does change
   is that the two absent paths above are **named rather than gestured at,
   and their absence is machine-checked**. Until this pass they could not be
   named: the citation gate's own path check (check 2) fails on any backticked
   path into this repo's trees that does not resolve, so the only sayable form
   was the vague "no such flow exists under [`layout/`](../../layout/)" the
   paragraph above uses — and a vague absence claim is exactly the kind that
   rots unnoticed, because on the day PR #402 merges and the path appears,
   nothing here can tell. **Check 29** of the [citation
   gate](check_proposal_citations.py) inverts check 2 for a path marked "not
   in this tree": it fails CI if that path ever *does* exist. This paragraph
   therefore cannot outlive the state it describes — the same structural
   shape check 27 applied to the label copies above, applied to the absences.

   **Update this pass (2026-09-25, later still): a fourth requirement now
   lands on the composed top level, and it is the first tracked one whose
   arrival moves this document's *numbers* rather than only the reasons
   behind its verdicts.** #440 was filed at 2026-09-25T18:06:01Z (open,
   `loom:blocked` + `loom:triage`, read live this pass) to place two
   per-domain decoupling capacitors in `layout/sar-adc-top/`'s composition —
   one across the analog `VDD`/`GND` pair, one across the digital
   `VPWR`/`VGND` pair — and to re-run `klt drc`, `klt lvs` and `klt erc`
   against the result. It is not a defect report against the assembly: the
   capacitors are a schematic-level sizing decision (#431, open and
   `loom:building`) that deliberately left placement to a separate pass, and
   #440 is that pass. **Nothing in this document moves yet, and the reason is
   checkable offline rather than taken from either issue's text** — the design
   those capacitors belong to has not landed. At this document's own HEAD,
   `git grep -i cdecap origin/main -- design/ spec/` returns nothing,
   `git ls-tree -r origin/main --name-only -- spec/decision-records/` carries
   no on-die-decoupling record, and #431 has no open PR. So
   `design/sar_adc_top.spice` still declares exactly the devices the composed
   GDS draws, `layout/sar-adc-top/reports/LATEST` is still
   `20260924-234053-66dca3c`, §4's machine-checked sign-off-bar readout is
   still that record's own numbers, both §4 sign-off-bar rows keep the
   verdicts they already carry, and criterion 3 waits on exactly what it
   waited on before.

   What *is* new is that this item now has a tracked event that will
   invalidate those numbers, where every earlier one changed only their
   explanation: #440 quotes #431's proposed netlist growth — 869 → 871 device
   instances, two MiM capacitors — as the thing every existing record under
   `layout/sar-adc-top/reports/` would then describe a die without. That
   figure is #431's *proposed* content as filed, not committed fact, and is
   quoted here as such; either way the staleness is caught rather than
   remembered. **Check 9** of the [citation
   gate](check_proposal_citations.py) grades every device, net and pin count
   and every mismatch category in §4's readout against `reports/LATEST`'s own
   `lvs.json`, so the first re-run that mints a record with different counts
   fails CI here until this document is restated from it — the same
   structural shape as checks 27 and 29 above, applied to the counts.

   **One thing not to read out of #440's text**: the decision record it names
   throughout,
   `spec/decision-records/DR-016-on-die-decoupling-budget.md`
   (not in this tree), is *not* the DR-016 that Item 4's status readout below
   reports. That
   number is already taken by
   [DR-016](../../spec/decision-records/DR-016-kickback-headroom-neutral-mitigation-measurement.md),
   the unrelated kickback-mitigation record #434 closed on (§4's Kickback
   row), so Item 4's "**DR-016** … is **proposed**" line says nothing about an
   on-die decoupling budget and no such record exists to carry a status of its
   own. #440's own verified-corrections note records the same collision and
   points a future builder at re-deriving the number from whatever #431 lands
   with. This document records that collision rather than resolving it:
   choosing #431's record number is #431's to do, exactly as laying out a
   decoupling capacitor is #440's.
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

   **Update this pass (2026-09-18): this item's status claim is now
   machine-checked — for every decision record, not only DR-007.** "DR-007 is
   still `proposed`" is a volatile, present-tense fact about a file in this
   repository, and every pass that touched this item re-verified it by hand
   (the update above says so in as many words: "re-checked live"). That is the
   same hand re-read checks 9, 12, 13 and 14 each replaced elsewhere in this
   document. It is also the *earliest* signal of a ratification, which is why
   leaving it ungated mattered: this repo ratifies a decision record by the
   operator's approval of the PR that carries it (the standing policy
   `spec/target-spec.md`'s own "Numeric rows — RATIFIED 2026-08-19" section
   records), so the record's Status field moves **first** and
   `spec/target-spec.md` follows only when the spec table is updated too.
   Check 7 gates §4's Status column against `spec/target-spec.md`; between the
   record moving and the spec table following it, nothing gated anything.
   Check 15 of the [citation gate](check_proposal_citations.py) now recomputes
   each record's status from that record's own `- **Status**:` field, and
   grades the readout in both directions — a record with no line below fails
   as loudly as a line carrying the wrong word, so dropping the line for the
   record that just moved is not an escape (**decision-record status readout,
   machine-checked**):

   > **DR-001** (`spec/decision-records/DR-001-supply-flavor-scope.md`) is
   > **accepted**.
   > **DR-003** (`spec/decision-records/DR-003-numeric-spec-derivation.md`) is
   > **accepted**.
   > **DR-004**
   > (`spec/decision-records/DR-004-comparator-topology-and-noise-budget.md`)
   > is **proposed**.
   > **DR-004** (`spec/decision-records/DR-004-sampling-frontend-sizing.md`)
   > is **proposed**.
   > **DR-005** (`spec/decision-records/DR-005-cdac-array-design.md`) is
   > **proposed**.
   > **DR-006**
   > (`spec/decision-records/DR-006-sar-sequencer-bit-count-and-timing-budget.md`)
   > is **proposed**.
   > **DR-007**
   > (`spec/decision-records/DR-007-revised-enob-inl-dnl-targets.md`) is
   > **proposed**.
   > **DR-007**
   > (`spec/decision-records/DR-007-sampling-frontend-nwell-domains.md`) is
   > **proposed**.
   > **DR-008**
   > (`spec/decision-records/DR-008-cdac-top-level-switching-polarity.md`) is
   > **proposed**.
   > **DR-009**
   > (`spec/decision-records/DR-009-comparator-output-load-balance-and-half-lsb-offset.md`)
   > is **proposed**.
   > **DR-010**
   > (`spec/decision-records/DR-010-digital-supply-domain-partition.md`) is
   > **proposed**.
   > **DR-011**
   > (`spec/decision-records/DR-011-comparator-kickback-target-row.md`) is
   > **proposed**.
   > **DR-012** (`spec/decision-records/DR-012-analog-ground-pad.md`) is
   > **proposed**.
   > **DR-013** (`spec/decision-records/DR-013-analog-ground-mesh.md`) is
   > **proposed**.
   > **DR-014**
   > (`spec/decision-records/DR-014-comparator-kickback-mitigation-no-static-preamp.md`)
   > is **proposed**.
   > **DR-015**
   > (`spec/decision-records/DR-015-package-parasitic-assumption.md`) is
   > **proposed**.
   > **DR-016**
   > (`spec/decision-records/DR-016-kickback-headroom-neutral-mitigation-measurement.md`)
   > is **proposed**.

   **Two facts that readout surfaces, which this item had not stated.** First,
   `spec/decision-records/` carries **two DR-004s** and **two DR-007s** — the
   comparator-topology record and a sampling-front-end sizing record share
   `DR-004`, and the revised-ENOB/INL-DNL record shares `DR-007` with an
   n-well-domains record. This document names decision records by bare number
   throughout ("DR-004 Amendment A", "DR-007's candidate pair", "per DR-006"),
   and a bare number is only unambiguous about *status* while every record
   sharing it agrees. Today they do — all four are `proposed` — so every bare
   reference in this document is correct as written, and nothing is re-worded
   on that account. The moment one of a colliding pair moves and the other does
   not, check 15 fails naming both files, rather than leaving this document
   asserting a status of "DR-007" that is true of only one of the two records
   that answer to the name. Second, the readout is the whole directory, so a
   decision record added by a future pass is discovered by the gate rather than
   remembered: `DR-008` and `DR-009` both post-date this item's original text
   and neither was mentioned here until now.

   **What check 15 deliberately does not cover**, stated rather than glossed:
   a bare `DR-<n>` naming no file in `spec/decision-records/` is not reported.
   Two such references are correct as written and would be broken by a
   stricter rule — §2.1's `DR-002` is a *tripwire clause* inside
   `spec/target-spec.md` rather than a record of its own, and §2.2's `DR-0005`
   is the port-parity sibling `gf180-sar-adc`'s record, explicitly named there
   as one this repo does **not** have. **No §4 row is re-graded by this
   check**: DR-007 is still `proposed`, the ENOB and INL/DNL rows are still
   *Informational only*, and this item does not close.
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

   **Re-checked 2026-09-24**: `https://opencircuitdesign.com/chipalooza/rules-4.html`
   still returns HTTP 404 (`curl -sI`, this pass); the parent `chipalooza/`
   index still returns HTTP 200 with `Last-Modified: Sun, 06 Sep 2026
   15:06:32 GMT` — byte-for-byte the same `Last-Modified`, `ETag`
   (`"1c94-65ad1d8cdb1fa"`) and `Content-Length` (7316) as the 2026-09-16
   re-check, so the index page itself has not been republished either.
   2AMLogic/2am#542's own tracking table still lists row 4 (Sky130,
   ChipFoundry) as "launches 2026-11-09" (submission 2026-11-23) — unchanged
   across all five re-checks (2026-09-06, -08, -15, -16, -24). §2's
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

9. **Power delivery is now structurally graded — the two digital rails failed
   it on 2026-09-23 and pass the continuity check as of 2026-09-24, while the
   checklist item itself stays unmet.** Nothing in this document mentioned ERC
   at all before the 2026-09-23 pass. The T1 evidence checklist this repo
   grades itself against grew an eleventh item on 2026-09-17 (*Power delivery,
   structural*, upstream klayout-tools#2025), and issue **#344** — closed, PR
   #356 merged 2026-09-23T22:21:03Z — answered it with a committed,
   hash-pinned `klt erc` supply run rather than a reading:
   [`layout/sar-adc-top/erc-reports/20260923-143401-1ee4ba8/record.md`](../../layout/sar-adc-top/erc-reports/20260923-143401-1ee4ba8/record.md)
   (`erc.json` beside it; driven by
   [`layout/sar-adc-top/erc-supply-spec.json`](../../layout/sar-adc-top/erc-supply-spec.json),
   run by [`layout/sar-adc-top/bin/run-erc.sh`](../../layout/sar-adc-top/bin/run-erc.sh),
   `klt` 0.6.0 / KLayout 0.30.12). That run reported `VPWR` and `VGND` each
   resolving to **two** disconnected islands, neither reaching a top-level
   supply.

   **Issue #355 (2026-09-24) fixed it, in the layout and not in the gate.**
   The supply spec's graded fields — `stackup`, `vias`, `nets[]` and
   `ties_disclosure.kind`, the only content `klt erc` reads — canonicalise to
   the same digest `7f48fd89…` on every run from #344 to today, printed by
   `run-erc.sh` itself (issue #364, which refreshed the spec's prose comments
   three times — once before and once after issue #377's ground mesh, and a
   third time to correct two GDS-specific shape counts a later Judge round
   found still described the superseded pre-mesh run — and so moved its
   whole-file hash each time while leaving that digest fixed). What
   changed is `layout/sar-adc-top/bin/build_layout.py`, which now ties both
   standard-cell macros' own met5 PDN straps together and out to two new
   top-level supply pins, per
   [DR-010](../../spec/decision-records/DR-010-digital-supply-domain-partition.md)
   (the digital domain stays independent of the analog `VDD`/`GND` domain —
   the sequencer switches coincidentally with the comparator decision by
   construction, so a shared metal rail would land the standard-cell bank's
   switching current on the comparator's own supply). The current run,
   [`layout/sar-adc-top/erc-reports/20260925-044420-f039594/record.md`](../../layout/sar-adc-top/erc-reports/20260925-044420-f039594/record.md),
   reports `erc_status: clean`, **0** findings:

   | Supply | Islands, 2026-09-23 | Islands, now | Continuity verdict |
   |---|---:|---:|---|
   | `VDD` | 1 | 1 | pass |
   | `GND` | 1 | 1 | pass — and since #362 on conductor that reaches a drawn top-level pin, since #377 on a mesh joining all three analog blocks' own ground terminals; still **read narrowly**, see below |
   | `VPWR` | 2 | **1** | pass |
   | `VGND` | 2 | **1** | pass |

   The citation above is the *third* ERC record of this flow, not #355's own:
   `erc-reports/` is append-only like every other evidence tree here, so #362
   (`20260924-214731-b323061`) and then #377 (`20260924-234116-66dca3c`) each
   minted a fresh verdict beside #355's `20260924-190825-f3622fc`. None of the
   three moved a number in the table above — which is exactly why this
   paragraph cited a superseded record for a day without any number looking
   wrong, and why the citation itself is now gated (check 23, below).

   No `erc.supply_short` and no `erc.floating_gate` is reported anywhere. That
   the new met5 geometry is what joins the islands is not asserted: ablating
   met5 from the spec puts both digital rails back at two islands, and
   ablating `via4` alone splits each into three against the pre-#355 stream's
   four — the #355 record's own "Cross-checks" table. Each successor record
   adds the same style of check for its own change, and the current one's is
   the strongest of the three, because it had the most to prove: `GND` read
   "1 island" before #362 drew a pad on it, "1 island" after, and "1 island"
   again after #377 meshed three sub-block ground terminals into it, so the
   integer is evidence about none of them. What is evidence is the ablation.
   `layout/sar-adc-top/bin/probe-ground-mesh.py` rebuilds this assembly twice
   from the record's own committed sub-block GDS — once as shipped, once with
   `build_layout.py --ablate-ground-mesh`, which draws DR-012's pad exactly as
   #362 shipped it and omits *only* #377's mesh — and grades both against the
   byte-identical spec: as shipped, `clean` / 0 findings / `GND` one island;
   mesh ablated, `violations` / 1 finding / `erc.unconnected_net` naming two
   islands (`sampling_frontend`'s own met1 ground and the comparator's plus
   its pad, on met4), with `VDD`/`VPWR`/`VGND` unmoved as controls and the
   full variant's recomposed GDS byte-identical (sha256) to the one the record
   grades. The stackup ablations #362 introduced are re-run on both streams
   and now say more than they did: removing `via3` splits `GND` into **3**
   islands on this GDS against **2** on the pre-#377 one, removing `via2` the
   same 3-against-2, and removing met4 from the stackup — which deletes the
   droppers but leaves the met3 trunk — splits it into **2** where the
   pre-#377 layout had nothing to disconnect. The third mesh leg is reached by
   a separate probe rather than counted in with the other two: `cdac_array`'s
   terminal is labelled `VSS` (its own schematic port name) and the graded
   spec deliberately does not declare `VSS`, so the probe re-grades both
   streams against a scratch `+VSS` spec written to its work directory and
   never committed — as shipped, `erc.supply_short` between `GND` and `VSS`
   (here the *measurement*: this model sees drawn conductor and nothing else,
   so "one electrical net" is a statement about metal); mesh ablated, no short
   at all. The probe exits 3 rather than 0 if either prediction ever fails.

   **The "Islands, now" column above is hand-transcribed, and as of this pass
   the gate recomputes it** (check 16 of the
   [citation gate](check_proposal_citations.py) — **ERC supply readout,
   machine-checked**):

   > on the record `layout/sar-adc-top/erc-reports/LATEST` resolves to, `klt
   > erc` reports `erc_status` **clean** with **0** findings; the declared
   > supplies resolve to `GND` **1**, `VDD` **1**, `VGND` **1**, `VPWR` **1**
   > electrical islands; and it grades `20260924-234053-66dca3c`, while
   > `reports/LATEST` there names `20260924-234053-66dca3c`: **current**.

   Three things that readout closes, none of which any earlier check could
   see. First, **an ERC record was invisible to the gate entirely**: this
   flow keeps its supply verdicts in a separate `erc-reports/` tree with a
   pointer file of its own, and checks 3 and 4 match `records/`/`reports/`
   only — so the one sentence in §3 and the table above could both have gone
   on describing a superseded run indefinitely, which is precisely the drift
   class the gate exists for (PR #239/#242/#276/#282, one directory over).
   Second, **the island counts themselves are now recomputed**, per supply
   and in both directions: a supply dropped from the spec's `nets[]` — the
   cheapest way to make a failing continuity table read clean — fails CI here
   rather than quietly shrinking the table. `klt erc` states an island count
   only on the *failing* side (inside the `erc.unconnected_net` finding that
   carries the islands), so the passing "1" against each supply is
   reconstructed from that record's own `erc_coverage.checked` list: a net
   that was graded and drew no finding resolved to exactly one island.
   Third, the closing verdict word is **this record's own "Staleness rule"
   made mechanical** — `current` requires both that the ERC run graded the
   record `reports/LATEST` names *and* that the stream's sha256 still matches
   the `provenance.input.content_hash` `run-erc.sh` pinned at run time.
   A future `run-flow.sh` re-run that is not followed by `run-erc.sh` turns
   that word to `stale` and fails CI, instead of leaving this item asserting
   a supply verdict about bytes this repo no longer carries — exactly the
   qualification the 2026-09-23 pass had to carry by hand and the 2026-09-24
   pass had to discharge by hand (the "no longer a revision behind" bullet
   below).

   **No verdict moves because of check 16**: the readout states the same four
   one-island supplies and the same `erc_status: clean` / 0 findings this item
   already carried, item 11 stays UNMET for the two reasons below, and both
   §4 sign-off-bar rows are untouched.

   **What check 16 could not see, and check 23 now does (added this pass).**
   That readout is generated from the pointer, so it was correct the day #377
   minted a new ERC record — while the *prose* three paragraphs above it went
   on introducing #355's fix with "the current run" and a citation of
   `20260924-214731-b323061`, the run that graded the GDS before the current
   one. The two passages contradicted each other for a day and no check could
   say so: check 16 never reads what path the surrounding prose cites, and
   checks 3/4 match the `records/`/`reports/` trees only, so an
   `erc-reports/` citation is invisible to them however it is written. Nor
   would a reader have caught it by arithmetic — #362 and #377 each minted a
   successor record **without moving a single number in the island table
   above**, which is precisely why a stale stamp could sit behind a page of
   correct-looking figures. Check 23 of the
   [citation gate](check_proposal_citations.py) closes that shape: a
   present-tense currency claim (*"the current run"*, *"the current record"*)
   stated immediately before a stamped citation must name the record that
   tree's own `LATEST` resolves to, in whichever of the three evidence trees
   the cited path itself names. Its scope and its deliberate limits — in
   particular why no word may sit between the claim and the path, and why it
   gates currency rather than content — are in
   [`docs/citation-gate.md`](../citation-gate.md).

   **Item 11 is nevertheless still UNMET**, and this document does not round
   that up. `klt signoff` renders both item-11 rows `unmet` / **`check_failed`**
   — because its grading path checks the cited LVS part before the supply spec,
   and item 4's own `mismatch` verdict (klayout-tools#1878) stops it there. The
   tie gap is a second, *latent* reason rather than an independent one: the item
   also requires zero `erc.missing_tie` *from a tie the run actually checked*
   and no `ties[]` is declared at all — the state
   `supply_spec_disclosed_tool_limitation` names — but grading never reaches it
   today. What changed is the *reason*:
   [`signoff/t1-report.json`](../../signoff/t1-report.json)'s two item-11 rows
   moved from `no_evidence` to `check_failed`, with the run cited as a
   compound entry — "the ERC ran and the supplies are continuous, and the item
   still is not met" is a materially more useful statement than silence. See
   [`docs/t1-gap.md`](../t1-gap.md) and `signoff/README.md`'s "Item 11" — and
   item 10 below, which states the same report's whole scorecard (and is
   machine-checked against it) rather than only the two rows this item quotes.

   Five honest qualifications this document owes a reader — the first four
   taken from the record rather than inferred, the fifth from the decision
   record whose geometry this item grades:
   - **`GND`'s pass is geometric only.** `klt erc` models drawn wire/via
     connectivity with no device recognition, and this block's analog ground
     return is partly the p-substrate. `GND: 1 island` therefore means *the
     drawn `GND` conductor is one island*, not *every NMOS body reaches it*.
   - **`erc.missing_tie` was not computed at all** — an absence of evidence,
     not evidence of absence, and disclosed as such in machine-readable form
     (`ties_disclosure.kind = "tool_limitation"`). No `ties[]` is declared
     because klayout-tools#2169 turns a correct `ties[]` on a routed
     standard-cell design into a *false* `erc.supply_short`; declaring one
     would replace a stated gap with a misleading finding. Tap-cell
     instances, `VPB`/`VNB` body labels and the LVS `net_correspondence`
     stand in and are named in the record, but they are weaker than a clean
     LVS would make them — item 4 does not itself pass, and neither `GND` nor
     `VGND` appears in that LVS run's `net_correspondence`.
   - **The ERC record is no longer a revision behind** — that qualification,
     carried by the 2026-09-23 pass, is now discharged. The current ERC record
     grades
     `layout/sar-adc-top/reports/20260924-234053-66dca3c/sar_adc_top.gds`
     (`sha256:bbb9b537…`, hash-asserted at run time), which is exactly what
     `layout/sar-adc-top/reports/LATEST` resolves to. Its own "Staleness rule"
     still applies to the next layout re-run: a newer `reports/<id>/` makes
     this ERC record stale, not wrong, and `run-erc.sh` is what mints a fresh
     verdict beside it. That discharge is not a standing one and is not
     asserted from this bullet: it is the closing word of check 16's readout
     above, recomputed from the pointer and the stream's own sha256 on every
     CI run.
   - **"One island" is not "reaches a pad" — and that gap is now closed, by
     the layout rather than by the report.** `klt erc` grades continuity, not
     whether a continuous net terminates anywhere a package could bond to. On
     2026-09-23 `GND` passed this row while having no top-level pin at all
     (`.GLOBAL GND`, absent from the netlist's own port list). Issue **#362** /
     [DR-012](../../spec/decision-records/DR-012-analog-ground-pad.md) gave it
     one: a via riser on `comparator`'s own drawn `GND` pin and a met4 stub out
     to a top-level pin label, plus the matching schematic port. `GND` reads
     "1 island" before and after — the number could not move, which is exactly
     why the caveat had to be retired by changing the geometry. What DR-012
     does **not** claim: that `GND` and `VGND` are two electrical nodes. Bulk
     sky130 has no isolation between them and the composed extraction reports
     them as one net (`GND|VGND|VSS` on the current record, 692 devices); the two pads are two bond
     points on one node, which is what keeps the digital return off-die.
   - **The ground plan's benefit was reasoned, not measured — and as of this
     pass it is measured, at a stated scope (added 2026-09-25, closed
     2026-09-25).** Every verdict this item reports is *connectivity*: drawn
     metal graded by a tool with no notion of impedance. Why this block draws
     that metal at all is a separate claim, and
     [DR-012](../../spec/decision-records/DR-012-analog-ground-pad.md) — the
     record that put the pad there, and which
     [DR-013](../../spec/decision-records/DR-013-analog-ground-mesh.md)'s mesh
     extends — declined to present it as evidence, in its own words: "no
     simulation in this repo measures ground-return impedance, substrate
     coupling, or bond-wire inductance… CLAUDE.md's *no claim without a
     testbench* rule applies to it." It carried that as a standing open item
     ("The impedance argument is unmeasured"), tracked as issue **#378**,
     naming the testbench that would settle it: drive the assembled
     `sar_adc_top` through package-like R+L on each of the four supply
     terminals, run `sim/full-conversion-transient/`'s own stimulus, and
     compare code errors against the ideal-ground case.
     [`sim/supply-impedance-sensitivity/`](../../sim/supply-impedance-sensitivity/README.md)
     is that testbench, landed this pass, and its first record
     (`records/20260925-073912-0e385e5.md`) is what DR-012's own "Open items"
     now cites to retire this one: at the ratified baseline corner
     (`tt_27c_1.80v`), [DR-015](../../spec/decision-records/DR-015-package-parasitic-assumption.md)'s
     package-style R+L (a *stated assumption* derived from wire geometry, not
     a package selection) moves no mid-scale captured code (**0 LSB** against
     the ideal-ground control, in every bonded/lumped-substrate arm), while
     the die-side `GND_DIE` excursion is **37.333 mV** peak-to-peak for the
     as-built R+L shape — of which a strict one-element ablation
     (`package` vs `package-r-only`, R unchanged, only `L` zeroed) attributes
     **37.274 mV** of it to the bond inductance alone (`0.059 mV` remains with
     `L = 0`), and **10.779 mV** to a lumped, on-die-only substrate return of
     this same record's stated order. So DR-012's reasoning is now a
     measurement at this one corner, not only prose — real impedance,
     inductance-dominated, not (yet) fatal to a captured code at this
     magnitude.
     **This closes the item at a stated scope, not without residue — and the
     residue has a tracker of its own (pointer added 2026-09-25).** This
     section's rule is that each item points at the issue that already owns
     the work rather than inventing new tracking for it; this retirement's
     leftovers were the one place that rule was not being kept. Issue **#409**
     (open) is where they live, and it names four, of which this paragraph
     previously stated two: the nine-point ratified corner grid is deferred
     (the campaign's own "Subset-corner justification" names three binding
     constraints — a shared-host policy against a local multi-corner ngspice
     grid, `klt sim`'s request/response contract not being able to mint a
     record in this repo's own format, and the batch fleet's ngspice build
     sitting below `sim/toolchain.json`'s `ngspice_min_major = 46` pin);
     DR-012's *rejected* `no-gnd-pad` null option **has since been run** (see
     the arm census below — it cost 487 s, not the several hours the ~17×
     slice projection claimed, and priced the rejected option at +27.6 mV of
     die-side ground excursion and 0 LSB of captured code); the `R`/`L` ×
     substrate-resistance sweep **has since been walked** too, over a bounded
     box at this same corner — this clause read "absent" until 2026-09-25 and
     then "implemented but not run", and both are now behind it (the paragraph
     after next states what landed, what it cost, and the census that grades
     it); and `R_SUB`/`R_SUBX`
     remain lumped stand-ins with no extracted substrate network behind them —
     the one of the four items that has not moved at all.
     Neither a worst-corner claim nor a priced-rejected-option claim may be
     read from **this** record, and it says so in its own words; the price of
     the rejected option is a *different* record's number, which is why the
     census below is scoped to one record at a time. It is also, on
     the same honesty rule DR-015 states of itself, evidence about *a* supply
     return and *a* lumped substrate stand-in of this record's own assumed
     magnitude, not a measurement of any real package or of this die's actual
     substrate.

     **The unrun arm is now counted, not only described (added 2026-09-25).**
     "Implemented but not run" is a claim about this campaign's *arm* axis —
     the supply-return networks its runner drives one DUT through — and that
     axis is not the PVT grid check 28 censuses. A record covering a subset
     of it is bounded by the arms it left out, exactly as `sim/README.md`
     requires a corner subset to be justified, and the campaign's own
     renderer states that per record (its "Arms this record does not contain"
     section, plus a standing omission note per arm). Nothing graded *this*
     document's version of it, so on the day #409's item 2 mints a record
     pricing the null option, the paragraph above would still read "not run"
     with every number beside it still true — the shape check 30 was added
     for, one axis over. Check 31 of the [citation
     gate](check_proposal_citations.py) now re-derives it from the runner's
     own arm table and the record's own header, in both directions:

     > of the **5** supply-return arms
     > `sim/supply-impedance-sensitivity/run_supply_impedance.py` implements,
     > the record `sim/supply-impedance-sensitivity/records/LATEST` names runs
     > **3** and leaves **2** unrun: `package-r-only`, `substrate`

     **That census moved on 2026-09-25 (later), and the arms it names moved
     with it — read the sentence, not the count.** #409's item 2 minted the
     record the paragraph above was written in anticipation of
     ([`20260925-204633-7339971`](../../sim/supply-impedance-sensitivity/records/20260925-204633-7339971.md),
     `ideal`/`package`/`no-gnd-pad` at `tt_27c_1.80v`), and because that is
     this campaign's newest *arm-comparison* record it is what
     `records/LATEST` now resolves to — so the census above is now the arm
     coverage of **that** record. It says two arms are unrun *in it*, and both
     of them (`package-r-only`, `substrate`) are run in the four-arm record
     beside it, which nothing supersedes. **Across the campaign's two arm
     records all five arms have now been run**, and no single record carries
     more than four of them; a reader wanting the bond-inductance ablation
     reads the older record and one wanting the ground-pad ablation reads the
     newer, exactly as each record's own "Arms this record does not contain"
     section directs. The count going *up* on the unrun axis while coverage
     went up in fact is the honest behaviour of a per-record census, not a
     regression, and is why this paragraph states the campaign-level fact in
     prose rather than pretending the census is one.

     **What that record actually priced, and the projection it falsified.**
     PR #429 (issue #409) had landed the machinery that turns the arm into a
     price — the runner computes the `package` vs `no-gnd-pad` one-element
     ablation and refuses to present an unpaired `no-gnd-pad` row as one — and
     minted no record, because the run was believed to be the several-hour one
     #409 describes. It was not: **487 s, 1.67× the `ideal` control and less
     than the `package` arm's 678 s** in the same record. The ~17×-per-ns
     figure behind "several hours" came from a truncated calibration slice,
     which prices this deck's start-up transient rather than the steady-state
     conversions the stimulus spends its span on; the cost-probe route is a
     convergence and runnability check, and this document should not have
     carried its projection as a reason an arm could not be run. The
     measurement itself: deleting DR-012's analog ground pad costs
     **+27.6 mV** of die-side `GND_DIE` excursion (**65.237 mV** against the
     `package` arm's **37.590 mV**, 1.74×) and **0 LSB** of captured code, at
     one corner and at DR-015's lumped `R_SUB`/`R_SUBX` = 30 Ω stand-in — a
     number about *a* substrate-only return of that order, undecoupled, not
     about this die's substrate. **No §4 row, verdict, Target or Status moves
     on it**: the Power row's citation list gains the record (check 3's
     freshness rule) and nothing it grades changes, because this campaign
     measures a difference against an ideal-source control rather than a
     spec-row quantity.

     **The sweep box is counted too — first as committed-but-unrun, then as
     walked, both on 2026-09-25 (corrected twice in one day).** The
     residue paragraph above said, until this pass, that *no* `R`/`L` ×
     substrate-resistance sweep existed. That stopped being true at
     2026-09-25T15:29Z, when PR #432 (issue #409, its third item) landed
     [`--sweep`](../../sim/supply-impedance-sensitivity/README.md) — a
     bounded 2-D box around DR-015's single assumption point, on the as-built
     `package` topology: **3** bond-inductance multipliers (`0×`, `1×`, `10×`
     of DR-015's per-terminal value) × **3** lumped substrate-link `R_SUBX`
     values (`3`, `30`, `300` Ω, a decade either side of DR-015's assumed 30)
     = **9** grid points, plus the same `ideal` control, and *anchored*: the
     `1× / 30 Ω` point is card-for-card the committed `package` arm and the
     `0× / 30 Ω` corner is `package-r-only`, asserted before the run starts,
     again at record-write time, and pinned by
     [`sim/tests/test_supply_impedance.py`](../../sim/tests/test_supply_impedance.py).
     A row of the grid moves only `L` and a column only `R_SUBX`, so either
     may be attributed to its own mechanism — DR-015 item 5's requirement,
     satisfied by construction rather than argued after the fact.

     **The box has since been walked (2026-09-25, later still).** What was
     owed after PR #432 was the measurement itself, and
     `sim/supply-impedance-sensitivity/records/20260925-164447-722fcb0.md`
     is it: the ten decks of the default box, sequential, at `tt_27c_1.80v`,
     **3049 s** of wall clock, every point converged. What it found is a
     **bounded null on codes** — worst `|Δ code|` = **0 LSB** at all **9**
     grid points, out to `L = 10×` DR-015's bond inductance and `R_SUBX`
     across two decades — while the die-side analog-ground excursion keeps
     climbing behind it: `0.059 mV` → `37.590 mV` → `99.749 mV` along the
     `R_SUBX = 30 Ω` column, worst **111.622 mV** (≈31.8 LSB, undecoupled by
     construction) at `10× / 300 Ω`. Read that as *the threshold is outside
     this box*, not as *there is none*: the record says so in its own words,
     and the `R_SUBX` axis is non-monotonic between the `1×` and `10×` rows,
     so neither axis may be quoted as a trend on its own. The sweep's writer
     deliberately never moves
     `sim/supply-impedance-sensitivity/records/LATEST` (it supersedes
     nothing, so the arm-comparison record stays the one DR-012 and §4's
     Power row cite). **No §4 row, verdict, Target or Status moves here
     either**: the box is a sensitivity map around DR-015's assumption
     point, and no `spec/target-spec.md` row is graded by it.

     **The cost probe PR #432 bought can now be graded against the run it
     priced.** `--cost-probe` re-ran each grid point's own deck over a
     truncated transient and concluded that **no point exceeds its own
     anchor** — the `10×` inductance row *cheaper* than DR-015's assumption
     point, not dearer, because more `L` lowers the bond-wire resonance and
     so relaxes the solver's timestep. The full run says the **decision** was
     right (the `10×` row is not the unaffordable row) and the **per-point
     numbers** were not a forecast: that row came in at up to `1.16×` the
     anchor against a predicted `0.47–0.96×`, so three points do exceed the
     anchor rather than none, a truncated slice being exactly the part of the
     transient that does not pay for the ring-down `L` scales. The box total
     was the transferable part: `≈ 7.0` anchors predicted, **7.8** measured
     (≈ 2.7 h scaled by the `package` arm's committed **1261 s** run, against
     the **≈ 2.5 h** projected). Read all of those as **wall clock, not
     evidence**: they live in the campaign's README rather than in a
     `records/` entry because a probe measures nothing about this block by
     construction (the committed fragment's `.meas` cards sit outside the
     sliced span, which is why `--cost-probe --record` is refused outright).

     **Why nothing already in the gate could have caught that clause.** A
     sweep record is, by the design above, never
     `sim/supply-impedance-sensitivity/records/LATEST` — so checks 3, 4, 6
     and 23, which grade pointers and stamps, cannot see one arrive. It runs
     at one corner, so check 28's PVT-grid census would not move. It carries
     no `- **Arms**:` line at all, so check 31's census immediately above
     would not move either. Check 32 of the [citation
     gate](check_proposal_citations.py) grades the axis those three leave
     uncovered, re-derived from the runner's own box definition and from any
     sweep record's own `- **Grid**:` header, in both directions:

     > of the **9** grid points the default `--sweep` box in
     > `sim/supply-impedance-sensitivity/run_supply_impedance.py` defines
     > (**3** bond-inductance multipliers × **3** substrate-link
     > resistances), the records under
     > `sim/supply-impedance-sensitivity/records/` carry **9**, in **1**
     > sweep record: `20260925-164447-722fcb0`

     That census has now moved, which is what check 32 was added to notice:
     it read `0` of `9` when the mode was committed and unrun, and reads
     `9` of `9` since #409's third item was paid for. DR-015's own "Open
     items" moved with it — its "No `R`/`L` sweep" entry is struck through
     and marked **CLOSED at a stated scope**, naming the box that closed it
     and, just as explicitly, what a *bounded* null does not license outside
     that box. The other three items #409 tracks (the ratified PVT grid, the
     `no-gnd-pad` record, an extracted substrate network) are untouched by
     this record and stay open.

     This retirement is **not** what turns check 25's own ground-return
     census (below) non-zero, and that is itself worth stating rather than
     leaving a reader to expect it: that check's `SIM_DECK_GLOB` scans
     committed `**/*.spice` files under `sim/` — the fixed testbench
     fragments and DUT netlist snapshots this repo authors once and reuses —
     while the campaign's per-arm `R + L` networks are assembled at run time
     into `.cir` decks (committed as evidence in
     `sim/supply-impedance-sensitivity/corners/`, alongside the `.spice`
     snapshot of the renamed DUT netlist that check 25 *does* see, which is
     why the deck count below still moves by one):

     > across the **106** SPICE decks under `sim/`, **0** carry an inductor
     > card

     Read this census the way it already reads itself: **a floor on the gap,
     not a proof of it, and it never claimed to be the thing that retires
     DR-012's item** — the record above does that, by citation, and this
     paragraph is what keeps the two from being mistaken for each other. What
     the census still correctly says is that no *committed, reusable* deck
     hard-codes ground-return impedance into the block's own fixed testbench
     material; the impedance this pass measured lives in a per-run,
     per-corner assembly instead, which is exactly what a *sensitivity*
     campaign (as opposed to a permanent testbench change) is supposed to
     produce. **No §4 verdict moves**: no `spec/target-spec.md` row grades
     ground-return impedance, and adding one here to hold this gap would be a
     spec change, which this document does not make.

     **The word every excursion figure above is qualified by now has an owner
     (added 2026-09-26).** `0.059`, `10.779`, `37.274`, `37.333`, `37.590`,
     `65.237`, `99.749` and `111.622 mV` are each an **undecoupled** upper
     bound, and that is not this document's gloss on them —
     [DR-012](../../spec/decision-records/DR-012-analog-ground-pad.md)'s own
     Consequences attach the qualifier to its `65.237 mV` figure and defer for
     it to "the last open item", and
     [DR-015](../../spec/decision-records/DR-015-package-parasitic-assumption.md)
     carries the same item forward in the same words. §7's rule is that an
     open item points at the issue that already owns the work; for this one
     there was no issue to point at, which is why the qualifier has travelled
     with every number above while naming nobody. **#431** (filed
     2026-09-25T13:47:43Z) is now that tracker — it asks for a decision record
     that sizes on-die decoupling per supply domain *or* records why none is
     needed, and for this campaign to be re-run with the result in the
     netlist. Placement of whatever it decides is split out as #440, whose own
     tracking state §7 Item 1 above carries; this paragraph does not keep a
     second copy of either issue's labels.

     **What #431 does not give this item is a number, and the distinction
     matters because its own title carries one.** #431 is headlined
     `129–259 mV` of die-side analog-ground bounce over the ratified grid.
     That figure is **not from this tree and may not be read against any
     figure above**: it comes from a parallel #378 build —
     `sim/ground-return-impedance/` (not in this tree), record
     `20260925-134451-5b3f175` — that lost the race to the campaign this item
     narrates and was never merged, under a *different* package model —
     `spec/decision-records/DR-015-testbench-package-model.md`
     (not in this tree), an isolated bond-wire `2.01 nH`/`0.099 Ω` per supply
     terminal — than the `1.914 nH` package total DR-015 ratifies here. #431
     says so itself and tells a Builder to re-verify against `main` rather
     than quote it. The comparable committed number under this repo's own
     ratified model is the `37.590 mV` the `package` arm measures at
     `tt_27c_1.80v`, and `111.622 mV` as the worst point of the bounded box —
     both already above, both already cited by record.

     **Nothing moves, and the census is what will notice when it does.** No §4
     row, verdict, Target or Status changes: #431 has landed no decision
     record and no design change, so `design/sar_adc_top.spice` still declares
     the devices the composed GDS draws and every figure above stands exactly
     as its record states it. What *is* new is that the ownership claim can go
     stale the moment a record strikes the item or names its tracker, and no
     check here could see that — checks 3, 4, 22 and 23 grade evidence
     citations, check 15 grades a decision record's *Status* line and nothing
     else, and checks 31 and 32 grade one campaign's own axes. **Check 33** of
     the [citation gate](check_proposal_citations.py) re-derives it from the
     records themselves, counting only *unstruck* bullets whose own bold lead
     names the gap (so DR-012's rejected-null-option item, which merely quotes
     the word "undecoupled", is not miscounted as a fourth carrier):

     > of the **3** decision records under `spec/decision-records/` whose own
     > *Open items* still carry the on-die-decoupling gap, **0** name the
     > issue that tracks it and **3** do not:
     > `spec/decision-records/DR-010-digital-supply-domain-partition.md`,
     > `spec/decision-records/DR-012-analog-ground-pad.md`,
     > `spec/decision-records/DR-015-package-parasitic-assumption.md`

     Read the `0` as the finding it is: three records carry this gap in their
     own words and **none** of them yet points at #431, so the pointer exists
     only here. The day one of them does — or strikes the item because #431's
     decision record landed — that clause fails CI until this passage is
     restated from what the tree then holds.

   **Does this move any §4 row? Not in verdict, but two rows' numbers move.**
   Item 11 is not a `spec/target-spec.md` row and no row is added for it here;
   the two sign-off-bar rows (post-layout PVT, DRC/LVS-clean GDS) stay
   UNMET/PARTIAL exactly as written. What *does* move is the DRC/LVS-clean
   row's readout — 88 mismatches, from 98, and pins 19/19/19 → 21/21/21 (#355)
   → **21/22/22** (#362) — because each new top-level supply pin is a new
   top-level pin, and §2.2's pad table carries them too. The last hop is the
   only asymmetric one: `GND` becomes a 22nd *reference* port while the layout
   still promotes 21 pins, because `GND` and `VGND` are one extracted net, and
   `matched=22` records that one layout pin answering both. And what the
   2026-09-23 pass wrote here still
   holds as the reason this item belongs in §7 at all: the brief's sign-off bar
   is about a *fabricable* assembly, and a composed top level whose digital
   section has no structural path from any top-level supply to its own cells
   was a gap this section should have been carrying and was not.

10. **The repository's own T1 evidence-tier scorecard is machine-graded, and
    it reads 3 of 22 — stated here because this document had been quoting one
    row of it and not the total.** Items 1–9 above each name a specific gap.
    This item names the *scorecard that counts them*, which until this pass
    appeared in this document only obliquely: item 9 quotes
    [`signoff/t1-report.json`](../../signoff/t1-report.json)'s two item-11
    rows and nothing else, so a reader could come away with the grade of the
    one item this document happened to be discussing and no idea what the
    same report makes of the other ten.

    Since 2026-09-24 (issue #345, PR #357) this block carries a committed
    `klt signoff` block manifest (`signoff/block-manifest.json`) and the
    machine-graded report it renders to (`signoff/t1-report.json`). That
    report — not prose in this document, and no longer
    [`docs/t1-gap.md`](../t1-gap.md)'s former hand-maintained item table — is
    this repository's T1 verdict of record. It is a *different* scorecard from
    §4's: §4 grades this design against the brief's own sign-off bar and
    against `spec/target-spec.md`'s rows, while this one grades it against
    `klt signoff`'s generic evidence-tier checklist. Both are reported; neither
    is used to soften the other.

    **The readout is machine-checked** (check 17 of the [citation
    gate](check_proposal_citations.py), added this pass — the third evidence
    tree, after `reports/` at check 9 and `erc-reports/` at check 16):

    > on the report `signoff/t1-report.json`, `klt signoff` **0.6.0** grades
    > **3** of **22** T1 items met, block tier **none**; the items whose cited
    > evidence was read and still failed are `4 analog`, `4 digital`,
    > `11 analog`, `11 digital`; and its manifest cites
    > `layout/sar-adc-top/erc-reports/LATEST` at **20260925-044420-f039594**
    > against a pointer naming **20260925-044420-f039594**,
    > `layout/sar-adc-top/reports/LATEST` at **20260924-234053-66dca3c**
    > against a pointer naming **20260924-234053-66dca3c**: **current**.

    Four things that readout states, each read out of the committed report
    rather than asserted here:

    - **Three of twenty-two.** The checklist is eleven T1 items graded once
      per partition (analog, digital), so 22 rows. The three met are item 3
      (*DRC clean*) on both partitions and item 8 (*Characterization report*)
      on the analog partition. Every other row is `unmet`, and the manifest
      leaves them that way deliberately rather than borrowing an unrelated
      passing envelope to turn one green.
    - **`check_failed` is not `no_evidence`, and the readout keeps them
      apart.** Four rows — item 4 (*LVS clean*) and item 11 (*Power delivery,
      structural*), on both partitions — cite real evidence that was read and
      graded and did not pass. The other fifteen unmet rows cite nothing at
      all. "The ERC ran, the supplies are continuous, and the item still is
      not met" (item 9 above) is a materially different statement from
      silence, and it is the one the gate now holds this document to: a row
      that starts failing and is left out of the list is a CI failure, and so
      is a listed row that has since started passing.
    - **Block tier `none`.** `klt signoff` awards no tier, which follows from
      T1 not being complete — the T2/T3/T4 rows render `tier_not_supported`.
      Stating the word is what makes a tier appearing later a visible change
      rather than a silent one.
    - **The closing verdict word is a freshness rule nothing else in this
      repository evaluates.** `signoff/check_evidence_hashes.py` already
      re-hashes every artefact the manifest cites against the file on disk, so
      no cited evidence can be rewritten underneath the sign-off. What it
      structurally cannot ask is whether the cited record is still the one that
      tree's own `LATEST` names: a manifest pinned to a **superseded but still
      committed** record passes the hash check with every hash intact, while
      the sign-off grades a layout this repo has moved on from. Check 17 asks
      exactly that, for both trees the manifest cites, and turns the word to
      `stale` if either has moved.

    **No §4 verdict moves because of this item**, and none is claimed to. A
    3-of-22 T1 grade is not a brief verdict; it is this repository's own
    checklist reporting the same gaps §7 items 1–9 already name, counted. The
    two sign-off-bar rows stay UNMET and PARTIAL exactly as written, for the
    same reasons stated there.

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
  (`docs/environment-setup.md`, `sim/pdk.json`).
- **How far that pin actually reaches, counted rather than claimed**: a
  brief's deliverable is evidence a third party can re-run, so this section
  used to assert that "every simulation record cites its exact pinned
  toolchain versions (`sim/toolchain.json`), and every layout record cites
  the `klt` version and PDK commit it ran against." The second half of that
  sentence was **not true when it was written**, and the census below — added
  2026-09-25 and graded in both directions by check 26 of the
  [citation gate](check_proposal_citations.py), whose rationale is in
  [`docs/citation-gate.md`](../citation-gate.md) — is what replaces it:

  > **65** of the **65** records under `sim/*/records/` name both an
  > `ngspice` version and a 40-hex `open_pdks` commit, while of the **67**
  > records under `layout/*/reports/` and `layout/*/erc-reports/` **66** name
  > a `klt` version and **34** name the `open_pdks` commit.

  The `sim/` half is uniform because `sim/run_corners.py --check-env`
  resolves and enforces the pin before any corner runs (`sim/toolchain.json`,
  `sim/pdk.json`), and a drift is fatal there by default. The `layout/` half
  was not, for two measured reasons. The first was **renderer divergence**:
  four of the eight `layout/` flows' record renderers resolved the commit
  (`klt pdk find`) and four printed only the variant *name*, which is not a
  pin — `layout/sar-adc-top/` and `layout/cdac-array/` among them. That half
  was tracked as issue #407 and **closed by PR #420 on 2026-09-25**, which
  added `resolve_pdk_commit()` to `layout/bin/_record_common.py` and applied
  it to the four flow renderers and to the ERC driver
  (`layout/sar-adc-top/bin/run-erc.sh`). The counted statement of where that
  leaves the tree, graded in both directions by check 30 of the
  [citation gate](check_proposal_citations.py):

  > of the **9** record-minting entry points under `layout/`, **9** resolve
  > the `open_pdks` commit before writing a record and **0** do not:
  > **none** — every entry point resolves it.

  The second reason is unchanged and is not #407's to close: **`klt`'s own
  provenance stamps no PDK at all** for the invocations these flows use —
  `provenance.pdk` is `null` in the `--deck sky130`-invoked
  `drc.json`/`lvs.json`/`extract.json`, and
  `{"source": "built-in", "version": null}` in the ERC report — a property
  of how these flows invoke `klt` rather than of any one record, re-confirmed
  against this tree's own artefacts when #420 landed. So the pin a record
  minted from here on carries is one the *renderer* resolved independently,
  not one the tool stamped; the DRC and LVS verdicts Section 4's layout rows
  rest on still record *which rule deck* ran (`deck.content_hash`, itself
  gated by `layout/bin/check_drc_evidence.py`) on their own.

  **The two censuses above are deliberately not the same number, and moved at
  different times.** Records are append-only and are not re-minted
  (`CLAUDE.md`), so #420 could not and did not change any record already in
  the tree: the **34 of 67** figure is a statement about history, and each
  flow's share of it retires only as that flow next re-runs. Until then the
  record census stays where it is while the renderer census reads 9 of 9 —
  which is precisely why both are stated. Neither moves a Section 4 verdict,
  and no verdict above is graded as though any of this were otherwise.

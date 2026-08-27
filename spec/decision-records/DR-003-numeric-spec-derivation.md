# DR-003: Numeric spec derivation — V_REF, LSB, CDAC unit cap, comparator noise budget, corner scope

- **Status**: **accepted** — ratified by the operator's approval of PR #46
  (resolving #27), per the canary spec/DR ratification-via-PR standing
  policy (2AMLogic/2am#357: "a builder drafts the ratification/DR as a PR
  on the evidence, and the operator's PR approval is the ratification act"
  — de-parking #27 from `loom:operator-only` on 2026-08-19).
- **Date**: 2026-08-17 (drafted, #26); 2026-08-19 (ratifying PR #46 opened)
- **Decided by**: Builder agent, issue #26
- **Ratified in**: #27 (Ratify the numeric rows of `spec/target-spec.md`),
  via the operator's approval of PR #46. The operator ruled **for this
  record's Decision section without modification** — no value below was
  relaxed, invented, or negotiated to close #27; every recommendation
  stands exactly as drafted in #26.
- **Supersedes**: none
- **Superseded by**: (none while this record stands)
- **Related**: #26 (this derivation), #27 (operator ratification request this
  record feeds), #23 (T1-gap tracker), #16 (T1 checklist re-read that opened
  #23), #24 (design-sources gap this record's V_REF/LSB numbers unblock),
  `spec/decision-records/DR-001-supply-flavor-scope.md` (ratified rail this
  record derives from), `spec/target-spec.md` (read, not modified — see
  "Spec lines affected"), `spec/dr-003-support/calc.py` and
  `spec/dr-003-support/vth_probe.spice` (the reproducible derivations this
  record's numbers are transcribed from)

## Context

DR-001 ratified the 1.8 V core supply flavor (`nfet_01v8`/`pfet_01v8`,
`sky130_fd_sc_hd`) in #1 but deliberately set no numbers: `V_REF`, the LSB,
the CDAC unit-cap floor, and the comparator input-referred-noise budget were
all left **TBD**, explicitly not portable from gf180-sar-adc's 3.3 V figures.
#16's T1 checklist re-read (`main`@`d3fda4c`) found items 5 and 6 (full-corner
verification against a ratified spec; Monte-Carlo evidence on the statistical
rows) both FAIL for exactly this reason — there is no ratified numeric table
to verify against — and #23 filed that root cause once, as #26 (this
derivation) feeding #27 (the operator ratification act). This record is #26's
output.

**What is verified, and against what.** Every device-level number below is
read from the installed sky130A PDK, `open_pdks`
`c6d73a35f524070e85faff4a6a9eef49553ebc2b` (`sim/pdk.json`'s pin, the same
commit DR-001 enumerated the device menu against), by grepping the shipped
model/parameter files directly — the same method DR-001 used — plus one
one-transistor ngspice `.op` probe
(`spec/dr-003-support/vth_probe.spice`) for the two threshold figures that
are not directly readable off a BSIM4 model card (a model's `vth0` is a
long-channel fitting parameter, not a usable device Vth at a real bias — see
Item 1). `spec/dr-003-support/calc.py` reproduces every arithmetic result in
this record from those inputs; run it (`python3 spec/dr-003-support/calc.py`)
rather than trusting the transcribed numbers below.

**What this record is not.** This repo has no ADC schematic yet (#24 is
still open; `design/` holds only the throwaway `smoke_test.sch`), so nothing
here is a circuit sizing — it is a spec-level derivation: what number goes in
each DRAFT row of `spec/target-spec.md`, and why, at the level of rigor a
decision record (not a full comparator/CDAC sizing memo) can support. Where a
number depends on a design choice this repo has not made yet (comparator
topology, CDAC switching scheme), that dependency is named explicitly rather
than assumed.

**Clean room.** No number below is ported from, or checked against,
gf180-sar-adc's 3.3 V figures or any other party's implementation — each is
re-derived from the ratified 1.8 V rail, standard ADC/CDAC theory (reproduced
from first principles, not cited as an external result), and the sky130A
device data cited inline. Where the *method* (not the number) matches
gf180-sar-adc's — e.g. the equal three-way noise-budget split, or the
top-plate-sampling free-MSB array combinatorics — that is because both are
standard SAR-ADC engineering practice independently reproducible from
textbook ADC/CDAC theory, not because a value was carried over; each is
re-derived here from sky130 inputs.

## Decision

The following values are ratified into `spec/target-spec.md`, per the
operator's approval of PR #46 (this record's own status
change above). Each is recommended below exactly as originally drafted in
#26 — the operator ruled for the recommendation without modification.

### Item 1 — V_REF / input full-scale: recommend `V_REF = V_DD = 1.8 V` (at the rail, not above it)

**This does not trigger the DR-002 tripwire.** The recommended full-scale is
the ratified 1.8 V core rail itself, not above it — deferral (3) in DR-001
(mixed HV front end + 1.8 V core) stays closed under this recommendation.

**Derivation.** The differential top-plate array (`spec/target-spec.md`'s
Architecture row) switches its bottom plates between `GND` and `V_REF`, so
the comparator's common-mode input is `V_cm = V_REF/2` in this topology
regardless of which `V_REF` is chosen. Two headroom mechanisms pull in
*opposite* directions as `V_REF` moves, and both must be checked rather than
assuming DR-001's informally-stated expectation ("a lower `V_REF` buys
comparator headroom") without testing it against real sky130 numbers:

1. **Sampling-switch pass headroom** (favors a *lower* `V_REF`): an NMOS
   switch gated at `VDD` loses overdrive as the passed voltage approaches
   `VDD`; a `V_REF` below `VDD` leaves margin. DR-001 Consequence §4 already
   concluded bootstrapped/clock-boosted sampling switches are "probably
   required" at 1.8 V regardless of `V_REF` — so this mechanism is
   **already paid for** by the bootstrapping DR-001 anticipates, and does
   not independently push `V_REF` down.
2. **Comparator input-pair/tail headroom** (favors a *higher* `V_REF`, for
   the NMOS-input/bottom-tail topology DR-001 Consequence §3 judges "close to
   mandatory" for a dynamic comparator at 1.8 V): the input pair's tail
   device needs `V_cm ≥ V_th,n + V_ov,in + V_dsat,tail` measured up from
   `GND`. A **higher** `V_cm` (hence higher `V_REF`) gives *more* room here,
   not less.

Mechanism (2) is quantified against real sky130 device data
(`spec/dr-003-support/vth_probe.spice`, ngspice `.op` probe against the
installed PDK, tt corner, 27 °C, a **representative planning geometry**
`W=4 µm / L=0.5 µm` — not a locked design point; final sizing is the future
comparator-topology DR DR-001's Open Items name):

```
Vth,n (BSIM4 op-point "vth", NOT the model card's raw vth0 -- see note below) = 626.9 mV
Vth,p (same bias convention, magnitude)                                       = 979.9 mV
```

*Why the op-point `vth`, not `vth0`.* `sky130_fd_pr__nfet_01v8`'s model card
carries `vth0 = 0.519 V` and `sky130_fd_pr__pfet_01v8`'s carries
`vth0 = -1.060 V` (both from
`libs.ref/sky130_fd_pr/spice/sky130_fd_pr__{n,p}fet_01v8__tt.pm3.spice`) —
these are BSIM4 long-channel fitting parameters, not the device's actual
threshold at any real operating point (short-channel/DIBL/`Vds` effects move
the apparent threshold substantially away from `vth0`, and the pfet's
`-1.060 V` in particular is not a usable "Vtp" on its own). ngspice's `.op`
analysis reports a bias-dependent `vth` for BSIM4 devices that already folds
those effects in; that is the number used here.

At `V_REF = 1.8 V`, `V_cm = 0.9 V`. Taking planning values
`V_ov,in = V_dsat,tail = 125 mV` (each a modest, deliberately conservative
overdrive/saturation-margin guess for a low-power dynamic stage — not a
sizing result):

```
V_cm,min = Vth,n + V_ov,in + V_dsat,tail = 626.9 + 125 + 125 = 876.9 mV
Margin (tt, 27 C)                       = 900 - 876.9         = 23.1 mV
```

**This margin is small — 23 mV, at the typical corner, before any
process/temperature derating.** Two things follow, stated plainly per this
record's "no guessing" guardrail rather than glossed over:

- **The margin is expected to worsen, not improve, at the slow/cold
  corner.** MOSFET threshold voltage rises at the slow process corner and at
  colder temperature (standard device physics; this repo's own harness
  self-test independently measured an 11.8 % `Vgs` shift between -40 °C and
  125 °C at fixed bias current, `sim/harness-corner-smoke/testbench/tb.json`)
  — both push in the same direction the 23 mV margin cannot absorb. An
  ngspice corner sweep of `spec/dr-003-support/vth_probe.spice` at `ss`/
  `-40 °C` was attempted while drafting this record and did not converge in a
  reasonable time on this machine; rather than guess a number, **this is
  named as open work for the future comparator-topology DR**, not asserted
  here.
- **A lower `V_REF` would make this worse, not better** — the opposite of
  DR-001's informally-stated expectation. This record's contribution is
  testing that expectation against real numbers rather than repeating it:
  for the NMOS-input/bottom-tail topology DR-001 itself judges most likely,
  headroom favors staying **at** the rail, not below it.

**Recommendation: `V_REF = V_DD = 1.8 V`.** This maximizes both the
comparator's common-mode headroom (mechanism 2) and the absolute LSB (Item
2), which loosens the absolute-volts noise/kT-C budgets (Items 3–4) — the
rail is the best point on every axis this record can check except the
already-anticipated bootstrapping cost of mechanism (1). The 23 mV nominal
margin is real but thin and is **named, not closed**: escalation paths for
the future comparator-topology DR, in likely order of cost, are (a) a longer
input-pair channel to lower `V_ov,in` at fixed bias current, (b) an
asymmetric/offset common-mode switching scheme (a CDAC design freedom this
record does not evaluate), and (c) accepting the margin and verifying it
empirically once a comparator netlist exists (#28's corner campaign is the
natural home for that check). This record does **not** claim the margin is
sufficient at every corner — only that the rail is the better of the two
directions available, quantified at the one corner this record could
evaluate.

### Item 2 — LSB and resolution: `LSB_diff = 2·V_REF/2^N = 3.5156 mV`, `N = 10` confirmed

```
LSB_diff = 2 * 1.8 / 1024 = 3.515625 mV
```

**`N = 10` confirmed, not challenged.** Item 3's matching-limited unit cap
(below) comes out to `C_u ≈ 8.65 fF`, `s ≈ 1.9 µm` square — a small,
easily-manufacturable device by sky130 MiM standards, with the array's total
capacitance (`C_total ≈ 8.86 pF`, both sides) well inside what a 1.8 V
reference/decoupling network needs to drive (no reference-drive contract is
ratified yet in this repo, unlike gf180-sar-adc's DR-0002 — flagged as future
work, not derived here). Nothing in this derivation identifies an area,
matching, or kT/C reason to move off `N = 10`; the ENOB budget (Item 3/4)
also clears with substantial margin (50 % of the LSB, rms, at the baseline
target). This record does not appeal to any other party's ADC results to
make this case (per `CLAUDE.md`'s clean-room rule) — it rests entirely on
this repo's own budget arithmetic.

### Item 3 — CDAC unit cap and array size: matching-limited at `C_u ≈ 8.65 fF`, `≈ 415×` above the kT/C floor

**Two independent floors, both re-derived against sky130's own capacitor
devices** (per DR-001 Consequence §1, which named this the load-bearing
open item and explicitly warned it must be re-derived, not assumed
V_REF-independent by analogy).

**kT/C floor.** Top-plate sampling means each side samples its own full
per-side array (`C_side`) independently through its sampling switch; the
differential-referred sampled-noise variance is `2kT/C_side` (the standard
top-plate-sampling result, McCreary & Wooley 1975 combinatorics — re-derived
here from first principles, not cited from any specific implementation). The
binding temperature is the **hot** corner (`kT` increases with `T`;
`target-spec.md`'s draft corner row's high end is 125 °C = 398.15 K):

```
kT(125 C) = 1.380649e-23 * 398.15 = 5.4971e-21 J
```

The noise budget itself needs the standard ADC SNR relationship
(`SNR = 6.02*ENOB + 1.76 dB`) — reproduced here from first principles, not
cited from gf180-sar-adc, because it is basic ADC theory: the allowable
non-quantization noise power at a target ENOB is set by the power gap
between the ideal `N`-bit SNR and the target SNDR. Working it through:

```
sigma_quant = LSB/sqrt(12) = 1.0149 mV rms
ENOB > 9.0: sigma_total(non-quant) = LSB/2            = 1.7577 mV rms (50.00% LSB)
ENOB > 9.5: sigma_total(non-quant) = LSB/sqrt(12)      = 1.0149 mV rms (28.87% LSB)
```

(The `ENOB > 9.0` result reducing exactly to `LSB/2` is a general identity —
a one-bit ENOB backoff is *always* a 4× noise-power allowance, independent
of `V_REF` or `N` — not a coincidence worth over-reading.)

**Three-way equal-power split** (kT/C sampling noise, comparator noise, and
reference/distortion) is adopted here as **stated policy, not derived** —
the same policy choice gf180-sar-adc's memo made, restated and re-applied to
this repo's own budget numbers because equal allocation is the least-
informative prior available before any of the three terms has been sized:

```
ENOB > 9.0 (baseline): each share = 1.0148 mV rms (28.86% LSB)
ENOB > 9.5 (stretch):  each share = 0.5859 mV rms (16.67% LSB)
```

Inverting `v_n,rms = sqrt(2kT/C_side)` at kT/C's share, and dividing by the
`2^(N-1) = 512`-position per-side sub-array (top-plate sampling's free MSB —
bit 1 is resolved directly from the sampled charge with no array switching,
a property of top-plate sampling itself, already named in
`spec/target-spec.md`'s Architecture row, not a gf180-specific switching
scheme):

```
ENOB > 9.0: C_side,min = 10.68 fF  -> C_u,min(kT/C) = 0.0209 fF
ENOB > 9.5: C_side,min = 32.03 fF  -> C_u,min(kT/C) = 0.0625 fF
```

**Matching floor — sky130's own local-mismatch model, not a placeholder.**
Unlike gf180mcu (whose open PDK ships no local capacitor mismatch model,
forcing gf180-sar-adc's memo to use a literature `A_C` planning value with a
stated 2× derating), **sky130A's MIM capacitor subcircuits carry their own
local-mismatch term directly**, verified by reading the shipped model files
rather than assumed:

- `libs.ref/sky130_fd_pr/spice/sky130_fd_pr__cap_mim_m3_1.model.spice` (and
  the identical-form `_m3_2` variant) computes
  `czero = carea + cperim + MC_MM_SWITCH*AGAUSS(0,1,1)*0.01*2.8*(carea+cperim)/sqrt(wc*lc*mf)`
  — i.e. `sigma(C)/C = 0.028/sqrt(W*L[um^2])`, a Pelgrom-style area law with
  coefficient **`A_C = 2.8 %·µm`**, read directly off the PDK's own
  mismatch term (not a literature planning value).
- `libs.tech/ngspice/parameters/montecarlo.spice` gives the nominal
  (`mim = 0`) density coefficients:
  `camimc = 2.0000 fF/µm²` (area term), `cpmimc = 0.1900 fF/µm` (perimeter
  term).
- This is a real, sky130-specific divergence from DR-001 Consequence §1's
  stated *expectation* (that the matching floor would be flavor-independent
  by analogy to gf180): sky130's coefficient (`2.8 %·µm`) is **not** the same
  number as gf180's literature planning value (`2.0 %·µm`, itself
  `literature-assumption-with-derating`, not a foundry-verified figure) —
  they cannot be compared as a ratio meaningfully since gf180's number was
  never foundry-verified, but the point stands that this record re-derived
  sky130's coefficient from the PDK rather than inheriting gf180's.

Using `spec/target-spec.md`'s existing DRAFT DNL/INL target (`≤ ±1 LSB`,
carried unchanged here — re-deriving that target is out of this record's
scope) at a 3σ yield convention (standard capacitor-matching sizing
practice, adopted here as stated policy for the same reason gf180-sar-adc's
memo adopted it — no area/schedule pressure identified to justify a looser
2σ criterion, per Item 3's own headroom below):

```
sigma(DNL)_max = sqrt(2^(N-1) - 1) * sigma_u = sqrt(511) * sigma_u = 22.605 * sigma_u   LSB
```

(the standard top-plate-sampling binary-array combinatorial result — the
sub-array's own MSB carry, `2^8` vs. the rest, is the worst transition —
re-derived here from the array size this repo's own architecture implies,
not ported from any specific coefficient table.)

```
DNL <= 1 LSB @ 3-sigma  =>  sigma(DNL) <= 1/3 LSB (1-sigma)
required sigma_u = (1/3) / 22.605 = 1.4746 %
```

Inverting the Pelgrom law (`A_unit = (A_C/sigma_u)^2`) against sky130's own
`A_C = 2.8 %·µm`:

```
A_unit = (2.8 / 1.4746)^2 = 3.6056 um^2   =>   s = 1.8988 um (square unit)
C_u = camimc*A_unit + cpmimc*(4*s) = 7.2112 fF + 1.4431 fF = 8.6544 fF
```

**Dominant constraint: matching, by `≈ 415×` over the kT/C floor at the
worst-case (ENOB > 9.0, 125 °C) evaluation** — kT/C is not close to binding,
the same qualitative conclusion DR-001 Consequence §1 expected, now
quantified against sky130's own devices rather than assumed by analogy. At
this `C_u`, the array totals `C_side ≈ 4.43 pF`, `C_total ≈ 8.86 pF` (both
sides) — an informational figure for #24's design work, not a ratified
value.

**One finding flagged, not fixed:** at this `sigma_u`, the total-array gain
error (`sigma(gain error) = sqrt(2*512)*sigma_u = 32*sigma_u = 1.42 LSB`
at 3σ) exceeds 1 LSB — but `spec/target-spec.md`'s draft table carries **no
gain-error row at all** (unlike gf180-sar-adc's ratified spec, which has
one). This record does not add one; it flags the gap as a spec-completeness
question for a future record, consistent with the "explicitly deferred, not
guessed" guardrail — inventing a gain-error target here would be closing a
row this record was not asked to derive.

### Item 4 — Comparator input-referred noise budget

**Recommend: `≤ 1.0148 mV rms` (baseline, ENOB > 9.0) / `≤ 0.5859 mV rms`
(stretch, ENOB > 9.5) — `28.86 %` / `16.67 %` of the LSB, rms**, exactly
one-third of Item 3's total non-quantization budget (the same equal
three-way split, applied to the comparator's own share). **The rest of the
budget, allocated by name:**

| Term | Share (power) | Baseline (ENOB > 9.0) | Stretch (ENOB > 9.5) |
|---|---|---|---|
| Sampling kT/C noise | 1/3 | 1.0148 mV rms | 0.5859 mV rms |
| **Comparator input-referred noise** | 1/3 | **1.0148 mV rms** | **0.5859 mV rms** |
| Reference noise + distortion | 1/3 | 1.0148 mV rms | 0.5859 mV rms |

This is a **budget, not a topology check** — no comparator schematic exists
yet in this repo (#24), so this record cannot verify any topology meets it
the way gf180-sar-adc's `comparator-budget-memo.md` verified an actual
netlist against its own budget. What this record *can* say: the budget in
absolute volts is loose relative to typical sky130 device thermal-noise
floors at modest bias currents (a dynamic latch's regeneration-node kT/C
noise at tens of fF, referred through a preamp gain of order 10, lands in
the tens-of-µV range in comparable designs' order of magnitude — stated here
as a plausibility check on the budget's shape, not as a measurement of any
sky130-sar-adc circuit). **Whether any specific topology clears this budget
is deferred, by name, to the future comparator-topology DR** (DR-001's Open
Items already name this DR as outstanding) and the noise-verification
campaign it will need (`.noise`-based if the topology has a static DC
operating point, `trnoise` Monte Carlo otherwise — the methodology choice
itself is deferred with the topology, not decided here).

### Item 5 — Sample rate and the corner row

**Sample rate: the draft `100 kS/s–1 MS/s` row is not independently
re-derived here** — no switch-`R_on` or settling data exists yet in this
repo (that needs a CDAC/switch netlist, #24) to compute a settling-limited
rate the way gf180-sar-adc's `cdac-sizing-memo.md` §5 did from a real
transistor-level deck. The array is modest (`C_total ≈ 8.86 pF`, Item 3),
which is favorable but not a substitute for a simulated settling number;
this is named as follow-on work for #24/#28, not guessed here.

**Corner row — recommend holding the draft `−40/27/125 °C` row for this
repo's actual verification methodology, with an explicit scope note rather
than a blanket re-anchor to 100 °C.** DR-001 Consequence §6 flagged a real
tension: `sky130_fd_sc_hd`'s **Liberty timing-characterization** libraries
top out at 100 °C, while `sky130_fd_sc_hvl` goes to 150 °C but carries none
of `hd`'s complex-gate depth (DR-001's Context). Two options, and the
scope-dependent recommendation:

- **Option A — hold 125 °C, accept no Liberty-characterized STA signoff
  above 100 °C for the SAR logic.** Cost: any *STA-based* timing claim for
  the digital sequencer above 100 °C has no characterized-library backing.
- **Option B — re-anchor the whole corner row to 100 °C.** Cost: narrows the
  corner claim for the **entire block**, including the analog signal path
  (comparator, CDAC, sampling switches), whose transistor-level
  `sky130_fd_pr` models are fully characterized to 125 °C and lose nothing
  by staying there — re-anchoring the whole row to fix a digital-only gap
  would give up real, valid analog coverage for no reason.
- **Recommended: Option A, with a stated scope note, because Option B's
  cost does not apply here.** This repo's actual verification methodology,
  read from `sim/pdk.json`/`sim/toolchain.json`/`sim/harness` and confirmed
  by `docs/t1-gap.md`'s own characterization ("no RTL/synthesis flow
  in-repo"), is **transistor-level ngspice simulation only** — there is no
  OpenSTA/Liberty-based digital signoff step anywhere in this repo's
  toolchain, committed or planned. `sky130_fd_sc_hd`'s standard cells are
  themselves built from `nfet_01v8`/`pfet_01v8`, the same devices
  characterized to 125 °C; a transistor-level SPICE simulation of the SAR
  sequencer (this repo's actual and only committed methodology) is
  unaffected by the 100 °C Liberty ceiling, because it never touches
  Liberty at all. **The gap DR-001 flagged is real but currently latent**:
  it binds only if and when a future digital-synthesis/STA step is added to
  this repo's flow, which is not decided and not scheduled. Recommendation:
  hold `−40/27/125 °C` for the corner row as drafted, and record — here,
  not silently — that **any future Liberty/STA-based signoff of the SAR
  logic inherits a 100 °C ceiling automatically**, without needing to be
  re-litigated when that step is added.

### Item 6 — Statistical vs. corner-only rows

`spec/target-spec.md`'s own "What T1 (bronze) will require" section already
names ENOB, INL/DNL, and offset as the Monte-Carlo-gated statistical rows;
this item makes that classification explicit and complete against every row
this record touches, for #28 (corner campaign) and #29 (Monte Carlo
campaign) to target unambiguously:

| Row | Classification | Why |
|---|---|---|
| `V_REF`, LSB | Fixed design constants | Set by this record's recommendation (Items 1–2); not a simulated or sampled quantity. |
| CDAC unit cap (nominal value/area) | Corner-only (deterministic) | The *nominal* value is a design choice (Item 3); PVT corners move its absolute capacitance (temperature/voltage coefficients) deterministically, with no mismatch draw involved. |
| DNL / INL, ENOB, offset | **Statistical — Monte-Carlo-gated** | Each is a distribution over device-mismatch draws (the CDAC unit-cap local-mismatch model, Item 3; comparator input-pair mismatch, once a topology exists) — requires seed, sample count, and negative control per `spec/target-spec.md`'s T1 section, not a single corner-point pass/fail. |
| CDAC gain error (unmodeled row, Item 3) | Statistical, if a row is ever added | Same mechanism as DNL/INL — a mismatch-draw sum over the whole array, not a corner quantity. Not added as a spec row by this record (Item 3). |
| Comparator input-referred noise budget | Corner-only (deterministic per corner) | Evaluated by a small-signal `.noise` integral (if the topology has a DC operating point) or a `trnoise` transient at *each* PVT corner independently — not a mismatch-sampled quantity, and not compared across a distribution; a per-corner pass/fail against the budget in Item 4. |
| Sample rate / settling margin | Corner-only | A deterministic RC/settling-time check per PVT corner (once a switch/CDAC netlist exists), not mismatch-dependent. |
| Power | Corner-only | Measured per corner, per `spec/target-spec.md`'s existing "report, don't pre-commit" note. |

## Alternatives considered

- **Porting gf180-sar-adc's `A_C = 2.0 %·µm` matching coefficient.**
  Rejected outright — `CLAUDE.md` and this issue both forbid it, and it
  would have been wrong regardless: gf180mcu's own coefficient was never a
  foundry-verified number (`literature-assumption-with-derating`), while
  sky130A's `2.8 %·µm` is read directly off the installed PDK's own
  mismatch model. There is no meaningful "does it port" question here; the
  two numbers come from different kinds of evidence entirely.
- **Setting `V_REF` below the rail for "comparator headroom," per DR-001's
  informal expectation, without checking it.** Rejected once quantified
  (Item 1): for the NMOS-input/bottom-tail topology DR-001 itself judges
  most likely, a lower `V_REF` *narrows* the relevant headroom margin, not
  widens it. Accepting DR-001's hedge uncritically would have closed this
  row on a plausible-sounding but numerically wrong basis.
- **Re-anchoring the whole corner row to 100 °C (Item 5, Option B).**
  Rejected — it would discard real, valid 125 °C analog coverage to fix a
  digital-signoff gap that is not live in this repo's actual (SPICE-only)
  verification methodology. Named as the right call *if* a future STA step
  is added, not foreclosed, just not adopted preemptively.
- **Inventing a gain-error spec row to close the finding in Item 3.**
  Rejected per this record's own "explicitly deferred, not guessed"
  guardrail — `spec/target-spec.md` has no such row today, adding one is a
  scope decision beyond "derive the existing rows," and doing it inside this
  record would blur a genuine spec-completeness question with the six items
  #26 actually asked for.
- **Skipping the ngspice `.op` Vth probe and reasoning from the model
  card's raw `vth0` alone.** Rejected — `vth0` is a fitting parameter, and
  using it directly would have produced a materially wrong (and, for the
  pfet, physically implausible) headroom number; the probe is cheap
  (one `.op` analysis) and its deck is committed
  (`spec/dr-003-support/vth_probe.spice`) so the result is reproducible, not
  asserted.

## Spec lines affected

**Ratified into `spec/target-spec.md` by PR #46**, per #27 /
2AMLogic/2am#357:

| `spec/target-spec.md` row | This record's recommendation | Status |
|---|---|---|
| `V_REF` | `1.8 V` (= `V_DD`, at the rail) | RATIFIED |
| LSB (differential) | `3.5156 mV` (`2·V_REF/2^10`) | RATIFIED |
| Resolution `N` | `10` (confirmed, not changed) | RATIFIED |
| Sampling cap (CDAC unit × array) | `C_u ≈ 8.65 fF`, `2^9 = 512` positions/side (matching-limited; kT/C floor is `≈ 415×` looser) | RATIFIED |
| Comparator input-referred noise | `≤ 1.0148 mV rms` (baseline) / `≤ 0.5859 mV rms` (stretch), `28.86 %`/`16.67 %` of LSB | RATIFIED |
| Corners | Hold `−40/27/125 °C` as drafted, with the Item 5 scope note on a future Liberty/STA step | RATIFIED |
| Sample rate | **not re-derived** — draft row stands unconfirmed pending settling data (#24/#28) | still DRAFT |

## Consequences

1. **#24 (design sources) can now size the CDAC unit cell and the sampling
   array to the ratified number** (`C_u ≈ 8.65 fF`, `512`/side) instead of a
   TBD placeholder — no longer provisional; #24's schematics may cite this
   record and `spec/target-spec.md`'s ratified row directly.
2. **The comparator-topology DR (DR-001's Open Items) inherits a concrete
   noise budget and a quantified, not-yet-closed headroom risk** (Item 1's
   23 mV nominal margin) rather than an open question — it can now be
   falsified or confirmed against a real netlist instead of starting from
   nothing.
3. **The 100 °C-vs-125 °C tension is resolved *for this repo's current
   toolchain*, not resolved in general.** If a future issue adds an
   OpenSTA/Liberty-based digital signoff step for the SAR logic, Item 5's
   scope note already states the consequence (100 °C ceiling on that step
   specifically) — that future issue does not need to re-derive it, but it
   does need to re-read this record before assuming 125 °C covers
   everything.
4. **A spec-completeness gap is now on record, not silently absorbed**: no
   gain-error row exists in `spec/target-spec.md` despite Item 3 finding
   that this repo's own DNL/INL-sized unit cap would not clear a
   gf180-sar-adc-style gain-error target if one existed. This is not a
   defect in this record — it is a genuine question for whoever next
   revises `spec/target-spec.md`'s table shape, named here so it is not
   rediscovered from scratch.
5. **The sky130-vs-gf180 matching-coefficient divergence is now evidence,
   not expectation.** DR-001 Consequence §1 predicted the matching floor
   would dominate kT/C "in the design's favor" without a sky130-specific
   number; this record supplies one (`A_C = 2.8 %·µm`, sky130's own PDK
   value) and confirms the qualitative prediction (`≈ 415×` margin) while
   correcting the naive assumption that the *coefficient itself* would
   resemble gf180's.
6. **Sample rate remains genuinely open.** Nothing in this record closes
   the draft `100 kS/s–1 MS/s` row; #24's netlist and #28's corner campaign
   are still required before that row can be derived rather than asserted.

## Open items

- **Item 1's worst-corner (ss, −40 °C) headroom margin** — attempted during
  drafting (`spec/dr-003-support/vth_probe.spice` at the `ss` corner) and
  did not converge in a reasonable time on this machine; a clean re-run (or
  a different extraction method) is required before the 23 mV nominal
  margin can be called sufficient or insufficient at the worst corner. Owner:
  the future comparator-topology DR.
- **Comparator topology itself** — DR-001's Open Items already name this;
  Item 4's noise budget and Item 1's headroom numbers are now concrete
  inputs to it, not open questions it has to derive from scratch.
- **CDAC switching scheme** (whether this repo adopts an MCS/Vcm-style
  scheme, a plain binary array, or something else) — Item 3's free-MSB
  array size (`2^(N-1)`/side) follows from top-plate sampling alone, not
  from a specific switching scheme, but the exact switching sequence and any
  further redundancy/relief technique is still open and belongs in a future
  DR when the CDAC design starts.
- **Sample rate** — not derived here; needs a switch/CDAC settling deck
  (#24) and a corner sweep (#28).
- **The gain-error spec-completeness gap** (Consequence §4) — flagged, not
  closed. A future record should decide whether `spec/target-spec.md` gets
  a gain-error row at all, and if so, size it the way this record sized
  DNL/INL.
- **Reference-drive contract** — this repo has no ratified analogue to
  gf180-sar-adc's DR-0002 (`Z_ref`/`C_dec` envelope). `C_total ≈ 8.86 pF`
  (Item 3) is small enough that this is not expected to bind, but it is not
  checked here.
- **Ratification itself** — resolved. The operator's approval of the PR
  resolving #27 was the ratification act (2AMLogic/2am#357), per
  `CLAUDE.md`'s "the spec is a gate" rule; this record's Decision section
  is binding as of that approval.

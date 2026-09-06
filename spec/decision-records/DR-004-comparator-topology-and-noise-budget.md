# DR-004: Comparator topology (no static preamp) and input-referred noise budget

- **Status**: **proposed** — this record ratifies nothing. Like DR-003, it is
  an input a future operator ratification act rules against (no ratification
  issue is filed for this record yet; #1/#27 have not ratified
  `spec/target-spec.md`'s comparator input-referred-noise row, and this
  record does not close that either). Nothing here is binding until that act
  happens.
- **Date**: 2026-08-21
- **Amended**: 2026-09-06 — **Amendment A (issue #175)**, at the end of this
  record: the reset-phase topology decision this record's Decision §1 left
  implicit is changed, and Decision §2's noise measurement is re-taken against
  the amended device set. **Read Amendment A before acting on anything in the
  body below**: the body describes the 9-device variant, which no longer
  exists. Nothing in the body is deleted or rewritten — a decision record's
  history is the point of having one.
- **Decided by**: Builder agent, issue #54 (body); Builder agent, issue #175
  (Amendment A)
- **Supersedes**: none
- **Superseded by**: (none while this record stands; Amendment A amends it in
  place rather than superseding it — the no-preamp decision and the noise
  budget both survive unchanged)
- **Related**: #54 (this design sub-block), #175 (Amendment A — the
  reset-integrity defect and its fix), `spec/decision-records/DR-001-supply-flavor-scope.md`
  (Consequence §3 — headroom argument this record's topology decision rests
  on), `spec/decision-records/DR-003-numeric-spec-derivation.md` (Item 1 — the
  23 mV nominal common-mode headroom margin; Item 4 — the provisional
  input-referred noise budget this record inherits and tests), `design/comparator.sch`
  (the schematic this record documents), `sim/comparator-decision/` (the
  standalone testbench and evidence records this record cites)

## Context

DR-001 Consequence §3 flagged, without a netlist to check it against, that
the 1.8 V core flavour leaves the comparator a thin headroom stack: tail
device, input pair, and cross-coupled latch must all fit between `GND` and
`VDD`, with the input common mode fixed near `V_REF/2` by the differential
top-plate CDAC topology. Its stated expectation was that **a static-preamp
topology is likely foreclosed and a dynamic (StrongARM- or double-tail-class)
comparator is close to mandatory** — but DR-001 explicitly declined to settle
this, naming it as a downstream DR (its Open Items: "The comparator topology
at 1.8 V, and whether the sibling's choice carries").

DR-003 Item 1 quantified the headroom side of that argument against real
sky130 device data (an ngspice `.op` probe on `nfet_01v8`/`pfet_01v8` at a
representative `W=4 µm/L=0.5 µm` planning geometry, `tt` corner, 27 °C):
`V_cm,min = Vth,n + V_ov,in + V_dsat,tail = 876.9 mV` against `V_cm = 900 mV`
at the recommended `V_REF = V_DD = 1.8 V` — a **23.1 mV nominal margin**,
named explicitly as "small" and "expected to worsen, not improve, at the
slow/cold corner" (not evaluated there — the `ss`/`-40°C` sweep of
`spec/dr-003-support/vth_probe.spice` did not converge in a reasonable time
while DR-003 was drafted). DR-003 Item 4 also set a provisional
input-referred noise budget for the comparator: `≤ 1.0148 mV rms` (baseline,
`ENOB > 9.0`) / `≤ 0.5859 mV rms` (stretch, `ENOB > 9.5`), one-third of the
non-quantization noise budget under the equal three-way split policy DR-003
adopted, but explicitly **not verified against any topology** because no
comparator schematic existed yet.

This record is that downstream DR: it now has a netlist
(`design/comparator.sch`) and a standalone testbench
(`sim/comparator-decision/`) to check the topology choice and the noise
budget against, closing the two items DR-001/DR-003 left open by name rather
than by omission.

**What is verified, and against what.** The topology decision below is
argued from the same headroom mechanism DR-003 Item 1 quantified — this
record does not re-derive that arithmetic, it applies it. The noise-budget
comparison is verified against a real ngspice `.noise` run of a reduced
sub-model of `design/comparator.sch`'s own devices (Sizing/Methodology
below), not asserted; the regeneration-time and offset behavior are verified
against real ngspice transient/Monte-Carlo runs of the same schematic's
xschem-netlisted device fragment. All three evidence records are committed
under `sim/comparator-decision/records/`.

**Clean room.** The topology (a 9-device single-tail dynamic latch — tail
switch, NMOS input pair, cross-coupled NMOS/PMOS regenerative latch, PMOS
reset pair) is a generic, widely-published circuit class (e.g. the
StrongARM/dynamic-latch family covered in Razavi's *Design of Analog CMOS
Integrated Circuits*), sized here from first principles against sky130
device models. No specific implementation — gf180-sar-adc's or any other
party's — was consulted, cited, or reverse-engineered; per `CLAUDE.md`, this
record and the schematic it documents own their sizing independently.

## Decision

**1. No static preamp.** `design/comparator.sch` is a single dynamic latch
stage with no preceding static (continuously-biased) preamplifier. Rationale:

- DR-001 Consequence §3's headroom argument, now quantified by DR-003 Item 1:
  the 1.8 V rail leaves only a 23.1 mV nominal common-mode margin (`tt`,
  27 °C) for the *dynamic latch's own* input pair and tail device. A static
  preamp would need its own input pair, its own tail/bias device, and its
  own load — stacking a second headroom-consuming device group into a
  budget that does not clear the first group comfortably. There is no
  quantified headroom left to spend on a preamp stage at this supply.
  Adding one would either fail to bias correctly at the slow/cold corner
  (the corner DR-003 flagged as *worse*, not better, for this margin, and
  left unresolved) or force the input pair devices themselves to be sized so
  aggressively small/low-overdrive that the preamp's own noise and gain
  advantage would likely be given back to headroom compromises — a tradeoff
  this record does not need to resolve quantitatively because the simpler
  alternative (no preamp) already has a measured path to a usable noise
  number (Decision §2 below).
- A static preamp's own noise contribution would need to clear the same
  budget with less than one-third of a share consumed by the input pair
  alone, on top of the latch's own regeneration noise, and this record found
  no headroom-neutral way to fit it. This is a design-judgement call made on
  the headroom argument, not on a computed preamp-noise number that
  disqualifies it — future work could revisit this if the negative
  consequences of a thin, un-power-optimized dynamic latch (Consequences,
  below) prove worse than expected.
- The comparator remains within budget without a preamp (Decision §2), so
  there is no forcing function to add stage complexity, headroom
  consumption, or static power that the budget does not require.

**This is a design-judgement call, made explicitly, not a default.** It
follows DR-001's stated expectation and is consistent with it, but this
record is the one that commits to it for `design/comparator.sch` and states
the rationale plainly, per this record's own "no guessing" standard.

**2. Input-referred noise budget: DR-003 Item 4's budget is carried
unchanged, and this record's own measurement is reported against it as
informational verification, not a ratified pass/fail.**

- **Budget** (unchanged from DR-003 Item 4, restated here as this record's
  own commitment for the topology it now covers): `≤ 1.0148 mV rms`
  (baseline, `ENOB > 9.0`) / `≤ 0.5859 mV rms` (stretch, `ENOB > 9.5`),
  differential input-referred.
- **Measurement methodology** (documented in full in
  `sim/comparator-decision/run.py`'s `noise` subcommand): the full latch has
  no stable small-signal DC operating point once regeneration begins — the
  cross-coupled NMOS/PMOS pair is a positive-feedback loop, so a direct
  `.noise` analysis on the evaluate-phase circuit does not converge to a
  usable bias point. This record instead uses a **reduced sub-model**: the
  same tail switch and input pair from `design/comparator.sch`, but with the
  cross-coupled latch pair's gates diode-connected to their own drains
  (self-biased) instead of cross-coupled to the opposite side — a standard
  "break the loop for small-signal analysis" technique, generic
  circuit-analysis practice and not specific to any implementation. `CLK` is
  held at `VDD` (steady evaluate bias, tail on) and a single-ended AC
  stimulus (`Vinp` AC=1, `Vinn` pure DC) drives an ngspice `.noise` analysis
  from `1 kHz`–`1 GHz`; ngspice's `inoise_total` (referred through `Vinp`) is
  a single-ended input-referred rms figure, converted to a differential
  estimate via the standard diff-pair noise-doubling identity
  (`rms_differential = sqrt(2) * rms_single_ended`, applied here as a named,
  flagged approximation, not independently re-derived).
- **This measurement excludes the cross-coupled latch pair's own
  regenerative-phase noise contribution** (Decision §2's reduced sub-model
  removes exactly that positive-feedback path to make the `.noise` analysis
  well-posed at all) — it characterizes the input pair + tail's
  noise contribution only, which for a bottom-tail dynamic latch is expected
  to be the dominant term (the input pair is the only stage that is
  continuously conducting and correlated with the differential input signal
  before the latch regenerates; the latch pair's own noise contributes
  during regeneration, when the signal is already being amplified toward the
  rails, and is a known limitation of this measurement approach, named here
  rather than hidden). **The reported number is therefore a lower bound on
  the true regeneration-inclusive input-referred noise, not a complete
  measurement** — see Open items.
- **Measured result** (`tt` corner, 27 °C —
  `sim/comparator-decision/records/20260821-072003-433a294.md`): single-ended
  `inoise_total = 0.4995 mV rms`, differential estimate
  (`sqrt(2)×` single-ended) `= 0.7064 mV rms`. Against DR-003 Item 4's
  budget, this clears the **baseline** target (`0.7064 < 1.0148 mV rms`,
  `ENOB > 9.0`) but **does not clear the stretch target**
  (`0.7064 > 0.5859 mV rms`, `ENOB > 9.5`) — reported exactly as measured,
  per `CLAUDE.md`'s "no claim without a testbench" / "do not relax a spec
  line to make a result pass" rules, with no sizing adjustment made to force
  either outcome. It is **not** compared as a ratified pass/fail because
  neither `spec/target-spec.md`'s comparator-noise row nor this record
  itself is ratified, and because the sub-model is a documented lower bound
  on the true regeneration-inclusive figure (immediately above) — a
  same-topology result that already sits above the stretch budget on a
  lower-bound measurement is a real signal that the stretch target may not
  be reachable without resizing, named here rather than glossed over.

**3. Regeneration and offset are exercised, not budgeted.** This record does
not set a numeric target for regeneration time (no settling/timing row for
the comparator alone is ratified in `spec/target-spec.md`) or offset (no
offset row exists in the DRAFT table at all — DR-003 Consequence §4 already
flagged the related gain-error gap). `sim/comparator-decision/`'s `regen`
and `offset` subcommands exist so this record's topology has real,
inspectable decision-time and mismatch-offset behavior on file, for the
future comparator work (#28's corner campaign, #29's Monte Carlo campaign,
and any future gain/timing spec rows) to build on rather than start from
zero:

- **Regeneration time vs. differential input**
  (`sim/comparator-decision/records/20260821-065653-433a294.md`, `tt`,
  27 °C, single reset→evaluate edge per point): monotonically decreasing
  from `1.3975 ns` at `Vindiff = 0.5 mV` to `0.5325 ns` at `Vindiff = 50 mV`,
  the expected `ln(V_decided/Vindiff)`-shaped positive-feedback latch
  behavior, and symmetric at `±10 mV` (`0.8325 ns` both signs) — a basic
  correctness check on the topology's differential symmetry, not a claim
  against any ratified settling-time row (none exists).
- **Mismatch-driven offset**
  (`sim/comparator-decision/records/20260821-071918-433a294.md`, `tt_mm`
  corner, `N = 16`, seed `1`): input-referred offset mean `35.24 mV`, stdev
  `97.08 mV`, range `[-136.43, +224.94] mV` across the 16 draws; the
  same-seed `tt` (mismatch-disabled) negative control reproduced the
  identical pick-off value on every draw (stdev exactly `0`), the standard
  negative-control pass this repo's other Monte Carlo records use. **Caveat,
  named rather than hidden**: the linearized gain (`4.2083 V/V`) used to
  convert the pick-off statistic to an input-referred offset was calibrated
  against ideal-device `Vindiff` in `[1, 10] mV` (ideal-device linear
  regime); several draws' raw pick-off differentials fall well outside the
  range that calibration validates (the largest corresponds to an
  extrapolated `≈225 mV` offset), where the true input-output relationship
  is expected to be compressive (approaching the rails) rather than linear.
  **The reported offset magnitudes are therefore an upper-bound / order-of-
  magnitude statistic for the larger draws, not a precise linear
  extraction** — real device mismatch at this input-pair sizing (`W = 4 µm`)
  is evidently large enough that a plain, single-point linear pick-off
  calibration is not the right methodology for a precise offset number; a
  future record should either narrow `PICKOFF_NS` further (closer to the
  evaluate edge, where the relationship stays linear over a wider range) or
  fit the calibration curve nonlinearly. Named here as Open items, not
  worked around silently.

## Alternatives considered

- **A static preamp ahead of the dynamic latch (StrongARM-with-preamp, or a
  two-stage preamp+latch topology).** Rejected under this record — see
  Decision §1. Not ruled out permanently: if a future corner/Monte-Carlo
  campaign (#28/#29) finds the no-preamp latch's offset or noise
  unacceptable at a corner this record did not evaluate (only `tt`/27 °C is
  characterized here — see Open items), a preamp becomes the natural next
  escalation, and this record's headroom argument would need to be
  revisited with a specific preamp sizing in hand, not just the general
  argument made here.
- **A double-tail (two-stage dynamic) latch instead of the single-tail
  topology chosen.** Not evaluated in this record — the single-tail topology
  was chosen as the simpler starting point that DR-001 Consequence §3
  already named as the likely-mandatory class ("dynamic (StrongARM- or
  double-tail-class)"), and it clears the noise budget informationally
  (Decision §2) without needing the extra complexity, isolation, and area of
  a double-tail pre-amplification stage. This is named as a real
  alternative not pursued here, not as a class this record disqualifies.
- **Deferring the topology decision until a full PVT/Monte-Carlo campaign
  exists.** Rejected as a process matter, mirroring DR-001/DR-003's own
  reasoning: issue #54 is independently designable and simulatable without
  the rest of the SAR ADC, and a `tt`/27 °C first-pass characterization
  (this record) is exactly the "first-pass, not sigma-adequate" convention
  the rest of this repo's evidence records already use
  (`sim/mc-smoke/`'s own N-count justification). Waiting for a full
  campaign before any topology commits would block #54 on work (#28, #29)
  that itself needs a topology to exercise.

## Spec lines affected

**None yet — this record changes no line of `spec/target-spec.md`.** The
"Comparator input-referred noise" row remains DRAFT/TBD exactly as DR-003
left it; this record supplies a candidate topology and a measured
(sub-model, lower-bound) value against DR-003's budget, for a future
ratification act to weigh alongside DR-003 itself — it does not ratify
anything on its own, and `spec/target-spec.md` is not edited by this record
or by issue #54's PR.

## Consequences

1. **#54's acceptance criteria on topology and noise budget are now closed
   with a concrete, evidence-backed answer** instead of the open item
   DR-001/DR-003 both named — a future comparator-topology revision (if the
   corner/MC campaign below finds a problem) has a documented baseline to
   diff against rather than starting from nothing.
2. **The noise number this record reports is a lower bound, not a complete
   figure** (Decision §2) — if the full evidence-inclusive regeneration
   noise turns out to exceed the reduced sub-model's estimate by enough to
   blow the DR-003 budget, this record's "no preamp" conclusion would need
   re-examination. This is a real, named limitation, not a footnote after
   the fact.
3. **Only one PVT point (`tt`, 27 °C) is characterized here.** DR-003 Item 1
   already flagged that the comparator's headroom margin is expected to
   worsen at the slow/cold corner, and that expectation was never confirmed
   (the `ss`/`-40°C` `vth_probe.spice` sweep did not converge while DR-003
   was drafted). This record does not resolve that gap either — it is
   carried forward as open work for #28's corner campaign, which now has a
   real netlist to run rather than a hypothetical one.
4. **No offset or regeneration-time spec row exists to check the `regen`/
   `offset` evidence against.** Those two testbench modes exist and produce
   real numbers (see the committed records), but until `spec/target-spec.md`
   grows an offset row and/or a comparator-level timing row, this record's
   own data is informational only — consistent with how DR-003 Item 4's
   noise budget itself was informational until this record existed to test
   it, and how this record's noise measurement is informational until a
   ratification act rules on it.
5. **Reset-device sizing was already forced wider than a first guess**
   (`design/comparator.sch`'s header note: `W=4 µm` PMOS reset devices left
   a stale, asymmetric post-reset state; `W=16 µm` was required) — a small,
   concrete instance of the thin-headroom cost DR-001 Consequence §3
   predicted in general, now observed on a real netlist rather than
   theorized.

## Open items

- **The slow/cold (`ss`, `-40 °C`) headroom margin** — DR-003 Item 1's open
  item, still open here. This record's topology choice rests on the `tt`/
  27 °C margin only; #28's corner campaign against `design/comparator.sch`
  is the next owner.
- **A full regeneration-inclusive noise measurement** (Decision §2's stated
  lower-bound limitation) — an alternative methodology (e.g. periodic/
  time-varying noise analysis across the regeneration transient, or a
  `trnoise`-driven Monte Carlo of the full latch rather than the reduced
  sub-model) would close this gap; not attempted in this record.
- **Offset and regeneration-time spec rows** — `spec/target-spec.md` has
  neither today (Consequences §4); a future record should decide whether
  either belongs in the table, using this record's `sim/comparator-decision/`
  evidence as a starting data set if so.
- **A precise (not order-of-magnitude) offset extraction methodology** —
  Decision §3's caveat: the current linearized pick-off calibration is only
  valid over the small `Vindiff` range it was fit against, and several
  mismatch draws fall outside it. Narrowing the pick-off time further or
  fitting a nonlinear calibration curve are the two escalation paths named
  there; neither is implemented in this record.
- **PVT/Monte-Carlo campaign scale-up** — this record's `offset` evidence
  uses `N=16`, explicitly a first-pass plumbing-scale sample (matching
  `sim/mc-smoke/`'s own convention), not a sigma-adequate yield claim; #29
  owns scaling it up once a full comparator design (and, likely, the CDAC it
  drives) exists to size a real sigma target against.
- **Ratification** — like DR-003, nothing in this record is binding until an
  operator ratification act rules on it; no such issue is filed yet for this
  record specifically (it is closer to DR-003's status than DR-001's).

## Amendment A (issue #175, 2026-09-06): reset-integrity topology fix

**Read this section before acting on anything in the body above.** The body
documents a 9-device variant of `design/comparator.sch` that no longer
exists. This amendment changes the topology, re-measures Decision §2's noise
claim against the new device set, and leaves everything else in the body
(Decision §1's no-preamp call, the noise budget itself, the Alternatives
considered) standing unchanged — it amends this record in place rather than
superseding it, per this record's own header.

### Context: what the pre-amendment topology got wrong

Issue #121's decision-delay PVT campaign carries a Vindiff = 0 mV
reset-integrity **negative control**: with the inputs shorted to the common
mode there is no correct decision to make, so the latch must stay balanced
until the evaluate edge. Record
[`sim/comparator-decision/records/20260906-052758-662a84d.md`](../../sim/comparator-decision/records/20260906-052758-662a84d.md)
found that control **failed at 3 of the 9 ratified corner points**
(`sf_27c_1.80v`, `tt_-40c_1.80v`, `tt_27c_1.62v`), with the outputs
separating to opposite rails *during* the CLK = 0 reset phase with no input
applied — onset as early as 2.746 ns into a 5.0 ns reset window, and at some
corners the divergence was already present at `t = 0.000 ns` (a bistable DC
operating point, not a slow settle). Counting applied-input runs too, 4 of 9
corner points showed at least one reset-not-held run.

The mechanism, read off that record's own measurements: the pre-amendment
9-device topology tied the cross-coupled NMOS latch pair's (`XM_LATN_P`/
`XM_LATN_N`) sources directly to `GND`, so those devices conducted
throughout the CLK = 0 reset phase, in opposition to the reset PMOS pair
(`XM_RST_P`/`XM_RST_N`). Two measurements followed directly: the reset-phase
output level sat at ~0.78·V_DD rather than the rail, and the reset phase
drew 0.52–1.25 mA of **static** supply current, because a DC path
`VDD → reset PMOS → output node → latch NMOS → GND` was open the whole time.
That balanced level was an **unstable equilibrium** — both latch NMOS
devices sat well above threshold, so the cross-coupled loop gain exceeded
unity and any asymmetry (corner skew, temperature, input-pair subthreshold
conduction) was amplified to the rails inside the reset window. This is a
**functional** exposure, not only a timing one: at the affected corners the
comparator entered each bit trial already committed to an output, so the bit
it produced was not determined by the charge on the CDAC top plate.

### Decision: return the latch NMOS sources to a precharged internal node

`design/comparator.sch` is amended to the textbook StrongARM arrangement:
the NMOS input pair's drains land on their own internal nodes `DIP`/`DIN`
(previously they were `OUTP`/`OUTN` directly), the cross-coupled NMOS latch
pair's sources move from `GND` onto those same `DIP`/`DIN` nodes, and two new
CLK-gated PMOS precharge devices (`M_RST_DIP`, `M_RST_DIN`, `W = 4 µm` — sized
to match the latch NMOS pair they precharge against, not oversized like
`M_RST_P`/`M_RST_N`, since they face no reset-phase contention at all) precharge
`DIP`/`DIN` to `VDD` alongside the existing `OUTP`/`OUTN` precharge pair. The
device count goes from 9 to 11.

**Why this closes the defect.** During CLK = 0 reset, once `DIP`/`DIN` reach
`VDD` (precharged by `M_RST_DIP`/`M_RST_DIN`), every latch NMOS device sits at
`Vgs = 0` exactly — gate at `VDD` from the opposite precharged output, source
at `VDD` from its own precharged drain node. The cross-coupled loop gain is
therefore zero, the reset state is a **stable** equilibrium rather than an
amplified one, and no DC path from `VDD` to `GND` exists through the latch at
all. `M_RST_P`/`M_RST_N` (`W = 16 µm`) are left at their pre-amendment size
on purpose, so this amendment carries exactly one topology delta and the
re-characterization below is attributable to that delta alone — the width's
now-unmotivated justification (it was sized to *fight* the very NMOS
pull-down this amendment removes) is carried forward as an open item, not
silently re-tuned.

**Node convention is unchanged**: `XM_INN` (gate `VINN`) still discharges the
node `XM_LATN_P` (drain `OUTP`) sources from — that node is now called `DIP`
instead of being `OUTP` itself — so a larger `VINN` still pulls `OUTP` down,
exactly as before the amendment.

**Re-netlist.** `sim/comparator-decision/testbench/comparator_core.spice` was
regenerated from the amended schematic via the documented xschem flow
(`xschem -x -n -s -q --rcfile sim/xschemrc -o <dir> design/comparator.sch`,
per that file's own header) and verified, independently of the driver script,
to reproduce byte-for-byte against a fresh netlist run for this PR. `design/
sar_adc_top.spice`'s pinned `design/comparator.sch` SHA-256 was updated to
match.

### Re-characterization: every committed comparator-decision campaign re-run

Per `sim/README.md`'s append-only convention, each campaign below mints a
**new** record that supersedes its pre-amendment predecessor via that
record's own `Supersedes` field — no committed record is edited, and no
citation elsewhere in this repo is left pointing at the superseded device set
without a fix (see the file list in the PR that lands this amendment).

- **`regen-corners` (the fix's own acceptance test)** —
  [`sim/comparator-decision/records/20260906-074451-7724af3.md`](../../sim/comparator-decision/records/20260906-074451-7724af3.md),
  supersedes `20260906-052758-662a84d`. **PASS: 9/9 reset-integrity controls
  now HELD** (every corner's pre-edge `v(OUTP) - v(OUTN) = +0.0000 V`, and
  reset-phase static supply current `= 0.00 µA` at every corner — both
  direct confirmations that the DC path the pre-amendment topology opened no
  longer exists), and all 27/27 input-driven decision points resolved within
  the 15.0 ns evaluate window. This is the **PVT-complete decision-delay
  figure** the pre-amendment record could not produce: binding corner
  `tt_27c_1.62v` at `Vindiff = +0.5 mV`, decision delay `4.3575 ns`, `19.1×`
  inside DR-006's provisional 83.333 ns worst-case bit-trial phase budget
  (a headroom statement against a DRAFT, not-yet-ratified figure, not a pass
  against a ratified spec line).
- **`regen`** (nominal `tt`/27 °C single-corner sweep) — re-run, superseding
  `20260821-065653-433a294`, against the amended 11-device netlist.
- **`offset`** (mismatch-driven offset Monte Carlo, `tt_mm`, `N = 24`,
  seed `1`) — re-run, superseding `20260828-004101-0c70212`, against the
  amended 11-device netlist.
- **`noise`** (nominal-point reduced sub-model) —
  [`sim/comparator-decision/records/20260906-064530-eedd532.md`](../../sim/comparator-decision/records/20260906-064530-eedd532.md),
  supersedes `20260821-072003-433a294`: `0.6808 mV rms` differential
  (`tt`/27 °C), down slightly from the pre-amendment `0.7064 mV rms`.
- **`noise-corners`** (full ratified PVT grid, reduced sub-model) —
  [`sim/comparator-decision/records/20260906-065109-eedd532.md`](../../sim/comparator-decision/records/20260906-065109-eedd532.md),
  supersedes `20260827-212404-e13bc1e`: **PASS** vs. the ratified baseline
  (`≤ 1.0148 mV rms`) at every corner, binding corner `tt_125c_1.80v` =
  `0.8643 mV rms` (down from the pre-amendment `0.9591 mV rms`); still does
  **not** meet the stretch threshold (`≤ 0.5859 mV rms`) at that corner — the
  same qualitative outcome as before the amendment, at a slightly better
  number.

**Why the noise sub-model's device selection changed.** The reduced sub-model
(Decision §2) breaks the cross-coupled latch's positive-feedback loop for a
`.noise` analysis by diode-connecting whichever devices sit on the input
pair's own drain nodes. Pre-amendment, that was the cross-coupled latch pair
itself (its sources were `GND`, its drains were `OUTP`/`OUTN`, the input
pair's own drains). Post-amendment, the input pair's drains are `DIP`/`DIN`,
so the rule now selects the `DIP`/`DIN` precharge PMOS pair
(`M_RST_DIP`/`M_RST_DIN`) instead — the selection **rule** is unchanged; the
device list it names changed because the netlist did.
`sim/comparator-decision/run.py`'s module comment documents two alternative
sub-models measured and rejected against that same rule (a literal loop-break
of all nine original devices, which turned out to bias the input pair
subthreshold, and that same loop-break plus diode-connected precharge
devices, which biases correctly but forces the latch NMOS pair to conduct —
exactly what they do not do during integration).

**Every quantitative comparator claim in this repository as of this
amendment now derives from the 11-device topology.** No committed
`sim/comparator-decision/records/*.md` file cites the superseded 9-device
device set as its own PVT-complete or corner-complete claim without either
being superseded above or (for the single-corner nominal records this
amendment did not itself re-derive further downstream numbers from, e.g. the
issue #29 offset campaign) being re-run as part of this same PR.

### Layout: LVS invalidated, tracked as its own issue

A device-level topology change invalidates `layout/comparator/`'s existing
LVS "match" verdict, since the drawn geometry still implements the
pre-amendment 9-device topology. Re-checked rather than assumed:
`layout/comparator/reports/20260906-064104-eedd532/` runs the identical `klt
lvs` request twice against the identical, unmodified composed GDS, changing
only the reference netlist — **match** against the superseded 9-device
reference (the toolchain reproduces the previously-recorded verdict) and
**mismatch** against the amended 11-device `layout/comparator/reference.spice`
(8 unmatched devices, `DIP`/`DIN` merged away in the drawn geometry). Re-drawing
the block is a full sub-block layout job — the same scale of work as the
original layout (#101) — and is deliberately **not** bundled into this
amendment; it is tracked as issue #180.

### Spec lines affected

**Still none.** As with the body above, this amendment changes no line of
`spec/target-spec.md`. The re-measured noise figures (`noise`/`noise-corners`
above) test the same ratified baseline/stretch thresholds the body already
cited — this amendment updates which record substantiates that claim, not
the claim's own numeric target.

### Consequences

1. **The functional exposure named in issue #175 is closed**, with a direct,
   re-runnable negative control (`regen-corners`, 9/9 HELD) rather than an
   inference from the mechanism alone.
2. **The comparator's decision-delay figure is now PVT-complete** for the
   first time — `sim/report/manifest.py`'s sample-rate row and
   `docs/chipalooza/challenge-4-proposal.md` §7 Item 2/3 are updated in the
   same PR to cite it and to retire the "BLOCKED by a design finding"
   wording that described the pre-amendment attempt.
3. **The reduced sub-model's own limitation (Decision §2 — it excludes the
   cross-coupled latch pair's regenerative-phase noise contribution) is
   unchanged by this amendment** — it is a methodology gap independent of
   which devices happen to sit on the input pair's drain nodes, and remains
   open (see Open items, unchanged, and the updated item below on the
   now-unmotivated `M_RST_P`/`M_RST_N` sizing).
4. **`M_RST_P`/`M_RST_N`'s `W = 16 µm` sizing is no longer motivated by its
   original justification** (overriding the latch NMOS pair's own
   direct-to-`GND` pull-down, which no longer exists) but is deliberately
   left unchanged in this amendment, per the Decision section above — a new
   open item, not a silent re-tune.
5. **`layout/comparator/`'s LVS match is invalidated** and re-drawing the
   block is deferred to issue #180, per the Layout section above.

### Updated open items (in addition to the unchanged list above)

- **`layout/comparator/` re-draw** (issue #180) — the block must be redrawn
  against the amended 11-device schematic with `DIP`/`DIN` routed on the
  mirror-symmetric axis, and the full six-verdict DRC+LVS proof re-run.
- **`M_RST_P`/`M_RST_N` re-sizing** — now unmotivated by the reset-contention
  argument that originally forced `W = 16 µm` (Consequences §4 above); a
  future record could re-tune these down to reduce output-node capacitance
  (faster regeneration) now that the DC-path defect they were compensating
  for no longer exists. Not attempted here, to keep this amendment to a
  single topology delta.
- **Ratification** — unchanged from the body: nothing in this record,
  including this amendment, is binding until an operator ratification act
  rules on it.

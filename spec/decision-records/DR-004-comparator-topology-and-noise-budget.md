# DR-004: Comparator topology (no static preamp) and input-referred noise budget

- **Status**: **proposed** — this record ratifies nothing. Like DR-003, it is
  an input a future operator ratification act rules against (no ratification
  issue is filed for this record yet; #1/#27 have not ratified
  `spec/target-spec.md`'s comparator input-referred-noise row, and this
  record does not close that either). Nothing here is binding until that act
  happens.
- **Date**: 2026-08-21
- **Decided by**: Builder agent, issue #54
- **Supersedes**: none
- **Superseded by**: (none while this record stands)
- **Related**: #54 (this design sub-block), `spec/decision-records/DR-001-supply-flavor-scope.md`
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

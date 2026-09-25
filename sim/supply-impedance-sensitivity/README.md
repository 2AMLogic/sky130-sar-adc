# `sim/supply-impedance-sensitivity/` — does the ground return matter?

[DR-012](../../spec/decision-records/DR-012-analog-ground-pad.md) decided this
block presents a **drawn** analog `GND` pad rather than bonding its analog
ground through the substrate only — and then said, against itself, that the
reasoning was a design-time argument rather than a measurement. Its own "Open
items", filed as issue #378:

> **The impedance argument is unmeasured.** No `sim/` campaign in this repo
> models the ground return at all — no package parasitics, no substrate
> resistance, no bond-wire inductance. A testbench that would settle it: drive
> the assembled `sar_adc_top` through package-like R+L on each of the four
> supply terminals, run `sim/full-conversion-transient/`'s own stimulus, and
> compare code errors against the ideal-ground case.

This directory is that campaign. It runs
[`sim/full-conversion-transient/`](../full-conversion-transient/)'s committed
stimulus fragment **verbatim** against the same committed
[`design/sar_adc_top.spice`](../../design/sar_adc_top.spice), once per arm per
corner point, changing nothing but the network between the board's star point
and the die's four supply terminals.

## The five arms

| arm | `VDD` | `GND` | `VPWR` | `VGND` | what it isolates |
| --- | --- | --- | --- | --- | --- |
| `ideal` | ideal source at the die | ideal source at the die | ideal | ideal | **the control** — what every existing `sim/` campaign runs today |
| `package-r-only` | package R | package R | package R | package R | the bond's own **resistance**, with no inductance anywhere |
| `package` | R+L | R+L | R+L | R+L | DR-012's as-built shape: four drawn pads, star point off-die |
| `substrate` | ideal | lumped `R_SUB` | ideal | lumped `R_SUB` | an **on-die-only** resistive return of DR-012's stated order |
| `no-gnd-pad` | R+L | *no bond at all* — reaches the board only through the lumped substrate resistance to `VGND`'s die node | R+L | R+L | DR-012's **rejected null option** — implemented, but *not* in the committed record (cost; see Runtime) |

**Read the ladder, not a single row.**

- `package` vs `package-r-only` is a **strict one-element ablation**: same
  resistance, same terminals, the only difference is the series `L`. Their
  difference is bond inductance's own contribution and nothing else. It is one
  of the **two** single-mechanism numbers this campaign can produce — the
  `no-gnd-pad` vs `package` bullet below is the other — and it is the only one
  in a record whose arm set omits `no-gnd-pad` (`ablation_lines()` says which
  case a given record is in rather than asserting uniqueness unconditionally).
- `package-r-only` vs `ideal` is the bond resistance's own contribution.
- `substrate` is **not** an ablation of `package`. Its resistance is ~300×
  larger (tens of ohms, vs ~100 mΩ), so a difference against `package` would
  confound two changes at once. It answers a different question — what an
  on-die-only resistive return of the magnitude DR-012 argues from would cost.
- `no-gnd-pad` vs `package` is the **second** strict one-element ablation: same
  three bonded terminals at the same R+L, same lumped substrate link, and the
  only difference is whether `GND` has a bond of its own. That difference is the
  drawn analog ground pad's own contribution — the price of the option
  [DR-012](../../spec/decision-records/DR-012-analog-ground-pad.md) rejected,
  measured against the option it chose. A record that contains both arms
  reports it automatically (`gnd_pad_ablation_lines()`); one that contains
  `no-gnd-pad` without `package` says so instead of presenting an unpaired row
  as a price. **No committed record contains that pair yet** — `no-gnd-pad` has
  not been run (cost; see Runtime below), so the pricing is computable but not
  yet measured.
- Per
  [DR-015](../../spec/decision-records/DR-015-package-parasitic-assumption.md)'s
  own open item, the `no-gnd-pad` arm is above all a function of `R_SUB`, so it
  must always be read as "at this assumed magnitude" and never as a prediction.

Every arm also carries one lumped resistor between `GND_DIE` and `VGND`,
because DR-012's own extraction evidence says those two are one net through the
p-substrate. In `ideal` both of its ends are held at 0 V, so it carries no
current and the control stays a true zero-impedance reference.

The R+L values, the substrate stand-in's magnitude, and where each one comes
from are ratified as a *stated assumption* by
[DR-015](../../spec/decision-records/DR-015-package-parasitic-assumption.md)
and re-rendered from the runner's own constants into every record this campaign
writes. **They are an assumption, not a measurement of any package**, and the
substrate resistor is a *lumped stand-in*, not an extracted network.
`sim/tests/test_supply_impedance.py` parses DR-015's table back out of the
Markdown and compares it against the code, so the record and the runner cannot
drift apart silently.

## Two load-bearing deck details

1. **The DUT's `GND` net is renamed `GND_DIE`** at deck-assembly time
   (testbench-only; never written back to `design/`). This is not cosmetic:
   **ngspice aliases a node named `gnd` onto the global ground node `0`**, so a
   series element on a net still called `GND` is silently shorted out and the
   campaign would measure the ideal case five times over — five identical
   answers, with nothing in the log to say why. It also explains why the
   existing full-conversion campaign is already an exact ideal-ground baseline
   even though its fragment declares no `GND` source at all.
2. **The fragment's own `VVDD`/`VVPWR`/`VVGND` cards are re-pointed to
   board-side nodes** on the arms that bond them, keeping the *source instance
   names* unchanged — so the fragment's own `.meas tran i_vdd avg i(vvdd)`
   cards still measure the current delivered from the board, and the `.tran`
   card, the clock, the reset, the input schedule and all 300+ code/phase
   `.meas` cards are used exactly as committed. `VREFP`/`VREFN`/`VCM` stay
   ideal at the die: this campaign is about the four *supply* terminals DR-012
   names, and a reference-network campaign is a different experiment.

The clock, reset and input sources stay referenced to node `0` — the board's
star point — which is where off-die stimulus really is, and which is what makes
a die-side ground excursion appear as a shift between the die's own reference
and everything the outside world drives.

Both transformations are asserted rather than assumed: a shape change in
`design/sar_adc_top.spice` or in the committed fragment fails the run loudly
instead of quietly producing a deck that measures something else.

### How to check this campaign did not fool itself

Two cross-checks are readable straight off the committed artefacts, and both
must hold or nothing else here means anything:

1. **The control arm must reproduce the existing ideal-ground baseline, code
   for code.** Renaming `GND` to `GND_DIE` and driving it from a 0 V source is
   supposed to be electrically identical to letting ngspice alias it onto node
   `0`. Compare the `ideal` row of this campaign's record against the same
   corner's row in
   [`sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md`](../full-conversion-transient/records/20260912-002315-9aaf1ca.md):
   at `tt_27c_1.80v` both read **214 / 383 / 511 / 641 / 1023**. A mismatch
   would mean the deck assembly changed the circuit, not just its ground
   network.
2. **The control arm's die-side ground excursion must be exactly zero.** An
   ideal source holds `GND_DIE` at 0 V, so `gnd_die_pp` is `0.000 mV` in the
   `ideal` row. A nonzero value there would mean the arm network is not wired
   the way the record says it is.

## What it measures

| Quantity | How |
| --- | --- |
| Captured code per arm, and its **difference from the `ideal` arm** | the fragment's own `DOUT9`/`ADCOUT8..0` reads, decoded by `sim/full-conversion-transient/run_conversion.py`'s own `decode()` (imported, not reimplemented) |
| Die-side rail excursion | `.meas tran <rail>_pp/_max/_min` on `GND_DIE`, `VGND`, `VDD`, `VPWR`, over the same steady-state conversion the fragment averages its currents over |
| Ground-return current | `.meas tran i_gnda avg i(vgnda)` — the analog ground's own bond current, which no campaign here had before |
| Average rail current / power | the fragment's own `i_vdd`/`i_vpwr`/`i_vrefp`/`i_vcm`/`i_vrefn` cards, unchanged |
| Wall clock per run | reported per arm, because the bonded arms' cost *is* a finding (below) and because it is the input to the corner-subset justification |

**The code comparison is read on the three mid-scale inputs only.** The two
near-full-scale inputs (`±0.78·V_REF`) are already wrong by ~100 LSB at every
corner in
[`sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md`](../full-conversion-transient/records/20260912-002315-9aaf1ca.md)
(issue #267, common-mode saturation at large differential input — still open),
so a change there cannot be attributed to supply impedance. They are still
printed in full in every record: excluded from the comparison, not from the
evidence.

**No decoupling exists anywhere in this design** — on-die decoupling is an
explicit open item of both DR-010 and DR-012, and no board decoupling is
modelled here either. The bonded arms are therefore an *undecoupled* package,
and the rail excursions they report are an upper bound rather than a prediction
for a decoupled system. That is stated in the record, not left for a reader to
infer.

## Cold start

```sh
source sim/env.sh                                                            # PDK_ROOT / PDK
python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --check-env  # toolchain + PDK pin

# all five arms at the ratified baseline corner:
SIM_NGSPICE_TIMEOUT_S=25200 python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --record
```

Other invocations:

```sh
python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --arms ideal,package
python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --corners --record
python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --record \
    --supersedes <record-id>   # name the prior record this one replaces

# the bounded 2-D R/L sweep (DR-015's own open item; see its own section below):
python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --sweep --record

# what that sweep would cost, and whether its points converge, WITHOUT running
# it: each grid point's own deck over a truncated transient. Measures nothing
# about the DUT, so it refuses --record.
python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --sweep --cost-probe 400

# the exact invocation that produced the committed baseline-corner record
# (records/20260925-073912-0e385e5.md; no-gnd-pad omitted on cost, see below):
python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --arms ideal,package-r-only,package,substrate --record

# restartable: reuse the logs of arms that already finished
python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --record \
    --log-cache .cache/supply-impedance
```

### `--log-cache`: because one arm outlives most process supervisors

A single arm here is a tens-of-minutes whole-ADC transient, and four or five in
sequence is hours — long enough that on a contended or preemptible host an
interruption is the normal case, not the exception. Losing four finished arms
because the fifth was killed is a real and repeated cost: it happened twice
while this campaign was being brought up, costing about an hour each time.

`--log-cache DIR` stores each completed run's ngspice log in `DIR` and reuses a
stored log instead of re-simulating. The **integrity rule** is what makes that
safe rather than a shortcut: a cached log is reused only when its **deck
sha256**, its **open_pdks commit** and its **ngspice version** all match the run
about to be made. Any mismatch re-simulates, loudly, naming the field that
differed. So a reused log is provably the log of this same deck on this same
toolchain — the cache is a restart mechanism, never a path by which a stale
number reaches an append-only record — and each record marks which of its runs
were reused rather than presenting them as fresh.

The open_pdks commit the gate uses is the **verified** one —
`pdk.resolved_commit_verified()`, the commit volare encodes into the install
path — not the display string records print. A non-volare install is only a
*warning* in `--check-env`, and for every such install the display string is the
same constant (`<pin> (unverified -- non-volare layout)`), so gating on it would
make two genuinely different hand-installed model libraries look identical to
the cache. A host that cannot verify its own open_pdks commit, or cannot report
its ngspice version, therefore neither stores nor reuses: it simulates every
time. Unverifiable provenance is a cache **miss**, never a match on a
placeholder.

This matters most for the deferred work in
[#409](https://github.com/2AMLogic/sky130-sar-adc/issues/409): the ratified
nine-point grid is 36–45 transients of this size, which is many hours of
sequential simulation and effectively cannot be run without restartability.

**The committed record is the four cheaper arms**, not all five: `no-gnd-pad`
is omitted on cost (see Runtime below), and each record states its own arm
subset and the reason, the same way it states its corner subset. Every record
also states verbatim the invocation that produced it, so its arm set is
reproducible from the record alone rather than from this README.

The `ideal` control arm is mandatory in every invocation — every number this
campaign reports is a difference against it — and the runner refuses a
`--arms` list that omits it rather than writing a record with no baseline.

**Runtime, and why it is a finding.** Each run is the same ~6.3 µs whole-ADC
transient `sim/full-conversion-transient/` runs. The arms are *not* equally
expensive: an undecoupled bond-wire inductance against the die's own
capacitance rings far above the clock rate and forces the transient solver's
timestep down, so a bonded arm costs multiples of the ideal one for the same
simulated span, and the `no-gnd-pad` arm — a high-impedance, lightly-damped
ground — is the most expensive of all. Each record states its own measured
per-arm wall clock. Consequences:

- `SIM_NGSPICE_TIMEOUT_S` must be raised well above the 120 s `sim/harness`
  default, as in the cold-start command above.
- The arms run one after another on purpose: this is a serial,
  single-simulation-at-a-time campaign, not a parallel grid.
- **`no-gnd-pad` is the expensive one, by roughly an order of magnitude.** Its
  ground is a high-impedance, lightly-damped node, and a bounded calibration
  slice of the same deck measured it at ~17× the control arm's wall clock per
  simulated nanosecond — which projects to several hours for one run of this
  stimulus. That is why it is implemented and documented but not in the
  committed record; the arm that would price DR-012's *rejected* option is
  therefore still owed, and the record says so in its own words rather than
  leaving a reader to notice the missing row.

**Before spending those hours, index the invocation you are about to run.**
Every record states the command that minted it in its `Written by` footer, and
`sim/check_spec_coverage.py` requires every token of that footer after the
runner path to appear in the bench's documented `cold_start`
(`cold-start-record-mismatch`). Exactly **one** invocation of this runner is
indexed today — the four-arm one that minted the committed arm-comparison
record — so a run with any other `--arms` list or any sweep box, including the
`ideal,package,no-gnd-pad` shape that would price the rejected option and
`--sweep --record` (below), needs its own bench entry in
`sim/spec-coverage.json` and its own verbatim documented command here, the same
way `sar-sequencer-behavioral` indexes its `--corners` variant separately.

A bench entry cannot be added *ahead* of its record: `sim/check_spec_coverage.py`
fails an entry that lists no evidence record (`bench-has-no-record`), because a
committed testbench with no record substantiates nothing. So the two halves of
the gate land at different times, and both are pre-checked here rather than
after the hours:

- the **documented** half is checkable now, and is checked now —
  `sim/tests/test_supply_impedance.py` asserts that the verbatim command this
  README documents for `--sweep --record` is character-for-character the footer
  the runner would write for the default box;
- the **indexed** half lands with the record, in the same commit: mint the
  record, then add the bench entry naming it, and the footer/`cold_start` rule
  is enforced from then on for every indexed entry by the same test.

(`--log-cache` never appears in a
footer: it cannot change a number, and its argument is one machine's scratch
path. Which runs reused a stored log is stated per row in the record's
wall-clock table instead.)

Also verified once, by hand, at `sim/pdk.json`'s pinned open_pdks commit and
then wired into the runner as a pre-flight guard: **neither the
`sky130_fd_sc_hd` cell deck nor the ngspice model library names a node `GND`**
(they use `VGND`/`VNB`, or take bulk from a port). If either did, those devices
would reach global node `0` without passing through this campaign's series
network and every arm would silently understate its effect — so the runner
scans both and refuses to run rather than trusting it.

## The bounded 2-D `R`/`L` sweep (`--sweep`)

The five arms are five **networks** at **one** point of DR-015's assumed
magnitudes. That can show whether the mechanism matters at that magnitude; it
cannot find the magnitude at which it starts to.
[DR-015](../../spec/decision-records/DR-015-package-parasitic-assumption.md)
says so against itself — its "Alternatives considered" calls sweeping "the
better experiment", deferred only on cost, and its "Open items" names the shape:
"a bounded 2-D sweep (bond inductance × substrate resistance) at one corner".
That is issue [#409](https://github.com/2AMLogic/sky130-sar-adc/issues/409)'s
third item, and `--sweep` is it:

```sh
python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --sweep --record
```

**What it sweeps.** The **as-built `package` topology** — all four supply
terminals bonded, DR-012's chosen shape — over two axes, plus the same `ideal`
control every number is a difference against:

| axis | default box | what moving it means |
| --- | --- | --- |
| per-terminal bond **inductance** | `0×`, `1×`, `10×` of DR-015's 1.914 nH | `0×` is an inductance-free bond, `1×` is DR-015's assumption point, `10×` is a deliberately bad bond (a long wire, or a return with no nearby ground plane) |
| the lumped substrate link **`R_SUBX`** | `3`, `30`, `300` Ω (DR-015 assumes 30) | how hard the p-substrate ties the analog and digital ground die nodes together — which decides how much of the digital ground's switching current returns through the analog bond |

Both axes are configurable (`--sweep-l-mult`, `--sweep-rsubx`); a run that
departs from the default box says so in its own record footer, and would need
its own indexed bench entry the same way a different `--arms` list does.

**A row moves one element and a column moves one other.** The bond *resistance*
is held at DR-015's value throughout, so the `L` ladder at a fixed `R_SUBX` is a
strict one-element family and so is the `R_SUBX` ladder at a fixed `L`. That is
DR-015 item 5's requirement — attribute an effect to an element only by a
difference that moves that element and nothing else — satisfied by construction
on both axes rather than argued after the fact.

**The grid is anchored to the committed arm comparison**, which is what makes it
a walk *away from* DR-015's assumption point rather than an unrelated box: the
`1× / 30 Ω` point is, card for card, the `package` arm, and the `0× / 30 Ω`
point is `package-r-only`. Both identities are asserted before the run starts
and again when the record is written (`sweep_anchor_matches_base_arm()`), and
`sim/tests/test_supply_impedance.py` pins them, so a later edit cannot quietly
re-centre the sweep.

**`R_SUBX`, not `R_SUB`.** They are different stand-ins and only one of them is
in this deck. `R_SUB` is a substrate-only *return* path and appears in the
`substrate` and `no-gnd-pad` arms, not in the as-built network, so sweeping it
here would sweep an element the swept topology does not contain. The arm where
`R_SUB` is load-bearing is `no-gnd-pad` — the expensive one (see Runtime) — so
an `R_SUB` sweep is that arm's own campaign and stays open on #409. Each sweep
record says this in its own "What this sweep does not cover" section rather than
letting "substrate resistance" be read as both.

**The sweep record does not move `records/LATEST`, and supersedes nothing.** It
is a *distinct* claim about the same DUT: the arm-comparison record compares
five networks at DR-015's assumption point, the sweep walks a box around that
point on one of them, and both stand. `records/LATEST` keeps naming the
arm-comparison record — the one [DR-012](../../spec/decision-records/DR-012-analog-ground-pad.md)
and `docs/chipalooza/challenge-4-proposal.md`'s Power row cite by id — because
moving it would make a citation of a record nothing had superseded read as
*stale* to this repo's citation gate. Same disposition, for the same reason, as
`sim/full-conversion-transient/run_conversion.py`'s diagnostic record writers.

**Cost, and `--sweep --corners`.** The default box is nine whole-ADC transients
plus the control, run one at a time, which is hours — use `--log-cache`, and see
the cost probe below for what those hours actually are. The combination
`--sweep --corners` is **refused**: it is #409's two deferred costs multiplied
together, and this host may not run a multi-corner grid at all (next section).

**No record of this sweep exists yet.** The mode, its anchors and its record
writer are committed and unit-tested; the box itself has not been run. That is a
cost deferral, stated here rather than left for a reader to infer from an empty
`records/` row — the same disposition as the `no-gnd-pad` arm above, and still
[#409](https://github.com/2AMLogic/sky130-sar-adc/issues/409)'s third item. When
it is run, the record and its `sim/spec-coverage.json` bench entry land together
(see "Before spending those hours" above).

### Pricing the box before paying for it (`--cost-probe`)

The first question about a ten-transient box is what it costs, and the second is
whether its points converge at all — and for seven of the ten points neither was
knowable from anything committed here, because the arm-comparison record contains
only the `1× / 30 Ω` anchor, the `0× / 30 Ω` corner and the control. The intuition available
instead was actively misleading: an undecoupled bond inductance forces the
transient solver's timestep down, so `10×` the inductance reads like `10×` the
ringing and therefore like the row nobody can afford.

`--cost-probe NS` answers both cheaply. It re-runs **each grid point's own deck**
over a truncated transient of `NS` nanoseconds and reports only wall clock and
solver status:

```sh
python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --sweep --cost-probe 400
```

It **measures nothing about this block**, by construction: the committed
fragment's `.meas` cards sit at conversion times outside the sliced span, so a
probe run captures no codes and no currents. That is why `--cost-probe --record`
is refused outright (a truncated run may never become evidence about the DUT),
why `--cost-probe --log-cache` is refused (a probe's log shares its point-id with
the real run of that point, so caching it would overwrite the stored log a
restarted campaign resumes from), and why the probe must be strictly shorter than
the stimulus it prices — a bound read out of the fragment itself rather than
restated in the runner.

The numbers it gives are **relative**, and that is the point: the `1× / 30 Ω`
point is card-for-card the `package` arm, whose full-run wall clock is already
recorded, so
`full(point) ≈ full(package) × probe(point) / probe(anchor)` projects the whole
box from a number this repo already has. Absolute seconds from a probe are a
contended shared host's and are not a benchmark of anything.

**What the probe says about the default box.** Run on this repo's dispatch host
(`ngspice-46`, `sky130A @ c6d73a3`, `tt/27 °C/1.80 V`, 400 ns slice, one
simulation at a time), every point of the default box converged, and the whole
box turned out to be **bounded by its own anchor** — as a multiple of the
`1× / 30 Ω` point's probe:

| bond `L` (× DR-015) | `R_SUBX` = 3 Ω | `R_SUBX` = 30 Ω | `R_SUBX` = 300 Ω |
|---|---|---|---|
| `0×` | 0.49× | 0.53× | 0.52× |
| `1×` | 0.96× | **1.00×** (anchor) | 0.96× |
| `10×` | 0.96× | 0.63× | 0.47× |

(the `ideal` control probed at 0.52× of the anchor, and is included in the ten.)
Two consequences, bought for ≈ 30 minutes of probing:

- **The `10×` row is not the expensive row.** The intuition that it would be
  gets the mechanism backwards: raising `L` *lowers* the bond-wire resonance
  (`f ≈ 1/2π√(LC)`), which *relaxes* the timestep the solver needs, so `10×`
  costs at most what DR-015's own assumption point costs and mostly less. No
  point of the box exceeds the anchor. Nothing in the box is a cost surprise
  waiting to happen.
- **The full box projects to ≈ 2.5 h on a host like this one** — the ratios sum
  to ≈ 7.0 anchors, and the anchor's own committed full run is 1261 s. That is
  ≈ 3.4× the committed four-arm campaign's own 2582 s, not the open-ended cost
  the `10×` row was assumed to carry.

Read these as ratios only. Absolute probe seconds move with whatever else the
host is doing (the `10×` row's spread here is mostly contention, not physics),
and the projection inherits that: it is the order of the box's cost, not a
schedule.

## Why the committed record is not the full nine-point grid

`--corners` (every arm × the nine-point ratified OAT grid) is implemented and
is the command a **simulation host** should run. The record committed here is
the baseline corner only, and each record states its own
"Subset-corner justification" per `sim/README.md`'s rule. Three constraints
bind at once:

- **Host policy.** The record was produced on a shared dispatch worker whose
  operating rules forbid running a multi-corner ngspice grid locally; a grid
  there must be expressed as a `klt sim` request and submitted to an EDA batch
  fleet. Sequential single-corner runs are the shape those rules allow.
- **The batch route cannot mint a record in this repo's format.** `klt sim`
  owns its own request/response JSON contract and its own corner expansion,
  while every record under `sim/` is written by this repo's
  `sim/harness/evidence.py` against a deck this repo assembles — so routing the
  grid there produces a different artefact, not this one. Separately, the
  fleet's runner image installs ngspice from the distribution archive, and this
  repo's own [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)
  already records what that means: the archive build is **ngspice-42**, below
  `sim/toolchain.json`'s `ngspice_min_major = 46` floor, which is exactly why
  CI builds ngspice from source instead. A record minted below that floor is
  refused by `sim/check_spec_coverage.py`'s pin gate and would not be
  comparable with anything already under `sim/`.
- **Cost.** Five arms × nine corner points is 45 whole-ADC transients at the
  per-arm cost above — a campaign in its own right, not a longer version of
  this one. (`no-gnd-pad` alone would account for most of it.)

So the grid is **deferred, not skipped**: the code exists, the command is
written down, and what is missing is a host whose ngspice satisfies the pin and
whose policy allows a grid. Until then nothing here is a corner-worst-case
claim; it is a mechanism comparison at the baseline corner.

## Findings

The first recorded campaign
([`records/20260925-073912-0e385e5.md`](records/20260925-073912-0e385e5.md),
`ideal`/`package-r-only`/`package`/`substrate` at `tt_27c_1.80v`) is what
retires [DR-012](../../spec/decision-records/DR-012-analog-ground-pad.md)'s
"the impedance argument is unmeasured" open item, at this scope:

- **No mid-scale code moved, at this corner and this assumed magnitude.**
  Every bonded/lumped-substrate arm reproduces the `ideal` arm's five captured
  codes exactly — worst `|delta code|` = **0 LSB** in every row, including the
  as-built `package` arm.
- **The die-side excursion is real, and inductance dominates it.** `GND_DIE`
  peak-to-peak: `package-r-only` (R only) **0.059 mV**; `package` (R+L,
  DR-012's as-built shape) **37.333 mV**; `substrate` (a lumped 30 Ω on-die
  return, DR-012's own stated order) **10.779 mV**. `package` vs
  `package-r-only` is a strict one-element ablation — same R, same terminals,
  only the series `L` differs — so bond inductance alone accounts for a
  **~630×** jump in excursion, the only single-mechanism number **in this
  record** (its four arms do not include `no-gnd-pad`, so the ground-pad
  ablation is not among its numbers).
- **Read this as "not fatal at this magnitude", not as "impedance does not
  matter".** A 37 mV undecoupled excursion (≈10.6 LSB at the nominal supply)
  on the comparator's own reference not flipping a captured code at `tt/27
  °C/1.80 V` is a property of this corner and this assumed R+L, not a
  guarantee at every corner or every package. DR-015's stated-assumption
  values, not a real package, are what was driven.
- **Two things this record does not price**, named rather than left implicit:
  the nine-point ratified corner grid (deferred — see "Why the committed
  record is not the full nine-point grid" above), and DR-012's *rejected*
  `no-gnd-pad` null option (implemented, not run, on cost — see "Runtime"
  above). Neither a worst-corner claim nor a "the rejected option would have
  cost N mV/LSB" claim may be made from this record alone.

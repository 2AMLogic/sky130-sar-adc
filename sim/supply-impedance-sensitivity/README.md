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
| `no-gnd-pad` | R+L | *no bond at all* — reaches the board only through the lumped substrate resistance to `VGND`'s die node | R+L | R+L | DR-012's **rejected null option** — priced in its own record (`20260925-204633-7339971`), not in the first one |

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
  as a price. **That pair is committed as of
  [`records/20260925-204633-7339971.md`](records/20260925-204633-7339971.md)**
  (issue #409 item 2): deleting the pad costs **+27.6 mV** of die-side ground
  excursion (65.237 mV vs 37.590 mV, 1.74×) and **0 LSB** of captured code, at
  the baseline corner and DR-015's assumed magnitudes.
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

**Why the substrate one cannot yet be replaced by an extraction** (issue #409
item 4, checked against `klt 0.6.0` on 2026-09-25): nothing in the layout
toolchain can produce a substrate network to put here. `klt extract
--parasitics` models conductor parasitics only — per-net R along drawn
interconnect and net-to-*ground* C, where ground is a single ideal reference
node — so two taps on the same bulk net are shorted with zero impedance
between them however far apart they are drawn; no `klt` command mentions a
substrate at all; and `klt pdk stackup`'s own `substrate` entry carries
permittivity but neither resistivity nor thickness, so even the material input
such a solve needs is missing. Per `CLAUDE.md`'s friction protocol that
capability gap is filed generically at
[`2AMLogic/klayout-tools#2515`](https://github.com/2AMLogic/klayout-tools/issues/2515)
— tool gap only, no design detail. Filing it does **not** close the item:
until an extraction exists, `R_SUB`/`R_SUBX` stay assumptions and every number
that leans on them is evidence about *a* substrate-style return of that order,
not about this die's.

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

**Which decoupling is in the deck changed on 2026-09-25, and a record's own
`DUT netlist sha256` is how you tell which case it is.** This campaign always
runs whatever `design/sar_adc_top.spice` commits; it adds no decoupling of its
own and never has.

- **Before [DR-017](../../spec/decision-records/DR-017-on-die-decoupling-budget.md)**
  (issue #431) the design had none at all, which is what
  [DR-015](../../spec/decision-records/DR-015-package-parasitic-assumption.md)
  item 6 records as a deliberate modelling choice. `records/20260925-073912-0e385e5.md`
  is that undecoupled case, and stays the only committed measurement of it.
- **Since DR-017** the design carries one `cap_mim_m3_1` per supply domain
  (`Cdecap_a` across `VDD`/`GND`, `Cdecap_d` across `VPWR`/`VGND`, `MF = 2` →
  8.870 pF each), so every record minted after it is the *decoupled* case.
  **No such record exists yet**, for a reason that is this campaign's problem
  rather than DR-017's: the `package` arm on the decoupled netlist outruns the
  dispatch host's per-process budget (> 3800 s and never completing across five
  attempts, against 1261 s undecoupled). Tracked as
  [#448](https://github.com/2AMLogic/sky130-sar-adc/issues/448), which needs a
  host, not code — see "Runtime" below.

**No board decoupling is modelled in either case**, so the bonded arms' rail
excursions remain an upper bound rather than a prediction for a real, decoupled
system. That is stated in the record, not left for a reader to infer.

**Budget a decoupled run from decoupled numbers.** DR-015 rejected adding
decoupling partly on the expectation that it would make the bonded arms "ring
less and simulate faster." Every arm measured on the decoupled netlist so far
went the other way: `ideal` 2073 s vs 554 s, `package-r-only` 1534 s vs 312 s,
`package` > 3800 s vs 1261 s. Host load is not controlled for across those
pairs, but the `ideal` arm is *electrically unchanged* by two capacitors sitting
across ideal sources and still took 3.7× longer, which load alone does not
explain — the PDK MiM subcircuit carries its own internal series resistance
(`r1 = rm3·l/w`), and the resulting sub-picosecond pole is something the
transient solver has to resolve. Use `--log-cache` (below); on the decoupled
netlist it is no longer optional.

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

# the exact invocation that opened the ratified grid's corner axis
# (records/20260926-012944-a966fdf.md): the control and the as-built arm at the
# baseline corner and the slow-process corner, the first non-baseline point any
# record of this campaign contains. A NAMED SUBSET of the same nine-point
# ratified grid -- `--corner-points` can narrow that grid, never extend it --
# because the whole grid is hours and a dispatch session is not (see "Why the
# corner grid arrives in pieces").
python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --arms ideal,package --corner-points tt_27c_1.80v,ss_27c_1.80v --record

# the bounded 2-D R/L sweep (DR-015's own open item; see its own section below):
python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --sweep --record

# the bounded null-option substrate ladder: DR-012's REJECTED topology swept
# over the resistance that is its whole ground return (see its own section):
python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --null-sweep --record

# what that sweep would cost, and whether its points converge, WITHOUT running
# it: each grid point's own deck over a truncated transient. Measures nothing
# about the DUT, so it refuses --record.
python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --sweep --cost-probe 400

# the exact invocation that produced the committed baseline-corner record
# (records/20260925-073912-0e385e5.md; no-gnd-pad omitted on cost, see below):
python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --arms ideal,package-r-only,package,substrate --record

# the exact invocation that priced DR-012's rejected null option
# (records/20260925-204633-7339971.md): the ground-pad ablation pair plus the
# control. `no-gnd-pad` is only readable as a price NEXT TO `package`, so the
# two run together or not at all.
python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --arms ideal,package,no-gnd-pad --record

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

**No single committed record carries all five arms**, and none needs to: the
first record is the four cheaper arms (`no-gnd-pad` omitted on a cost
projection, see Runtime below) and the third is the ground-pad ablation pair
plus the control (`ideal`, `package`, `no-gnd-pad`), which is what prices the
arm the first one left out. Each record states its own arm subset and the
reason, the same way it states its corner subset, and every record states
verbatim the invocation that produced it — so its arm set is reproducible from
the record alone rather than from this README. What a *reader* must not do is
add the two together: the bond-inductance ablation is a difference between two
arms of the **first** record and the ground-pad ablation is a difference
between two arms of the **third**, and neither record licenses a number that
spans both.

The `ideal` control arm is mandatory in every invocation — every number this
campaign reports is a difference against it — and the runner refuses a
`--arms` list that omits it rather than writing a record with no baseline.

**Runtime, and why it is a finding.** Each run is the same ~6.3 µs whole-ADC
transient `sim/full-conversion-transient/` runs. The arms are *not* equally
expensive: an undecoupled bond-wire inductance against the die's own
capacitance rings far above the clock rate and forces the transient solver's
timestep down, so a bonded arm costs multiples of the ideal one for the same
simulated span. Each record states its own measured per-arm wall clock.
Consequences:

- `SIM_NGSPICE_TIMEOUT_S` must be raised well above the 120 s `sim/harness`
  default, as in the cold-start command above.
- The arms run one after another on purpose: this is a serial,
  single-simulation-at-a-time campaign, not a parallel grid.
- ~~**`no-gnd-pad` is the expensive one, by roughly an order of magnitude.**
  Its ground is a high-impedance, lightly-damped node, and a bounded
  calibration slice of the same deck measured it at ~17× the control arm's
  wall clock per simulated nanosecond — which projects to several hours for one
  run of this stimulus. That is why it is implemented and documented but not in
  the committed record; the arm that would price DR-012's *rejected* option is
  therefore still owed, and the record says so in its own words rather than
  leaving a reader to notice the missing row.~~ **Measured, and the projection
  was wrong by about an order of magnitude** (issue #409 item 2,
  [`records/20260925-204633-7339971.md`](records/20260925-204633-7339971.md)):
  the full-stimulus `no-gnd-pad` run took **487 s**, **1.67×** the `ideal`
  control in the same record — *cheaper* than the `package` arm beside it
  (678 s, 2.32×), not "the most expensive of all", and about 25 minutes for the
  whole three-arm campaign rather than the several hours projected. Left
  struck-through rather than deleted because the deletion would hide the
  methodological finding underneath it, which is the durable part:
  **a truncated-slice cost calibration did not predict this deck's
  full-stimulus cost.** The ~17×/ns slice ratio, and a later pair of
  re-calibrations on another host (~3.6× at a 200 ns slice, ~1.5× at 800 ns —
  mutually inconsistent, minutes apart), all disagree with the 1.67× the real
  run measured. The mechanism is physical, not a flaw in the probe's clock: a
  high-impedance ground's cost is concentrated in the ringing that follows a
  switching event, so a slice that starts at `t = 0` prices the start-up
  transient and not the steady-state conversions the stimulus spends its span
  on. Read `--cost-probe` (below) as a **convergence and runnability** check
  with an order-of-magnitude cost hint attached, and prefer *this* table — a
  measured full run of the same deck — when deciding whether an arm is
  affordable. One arm sat unrun across several passes on a projection that an
  eight-minute run falsified; the correction is to price an arm by running it
  when the projection says "hours", not to trust the slice.

**Before spending those hours, index the invocation you are about to run.**
Every record states the command that minted it in its `Written by` footer, and
`sim/check_spec_coverage.py` requires every token of that footer after the
runner path to appear in the bench's documented `cold_start`
(`cold-start-record-mismatch`). **Five** invocations of this runner are
indexed today, one per committed record — the four-arm arm comparison
(`--arms ideal,package-r-only,package,substrate --record`), the default sweep
box (`--sweep --record`), the ground-pad ablation pair
(`--arms ideal,package,no-gnd-pad --record`), the default null-option
substrate ladder (`--null-sweep --record`) and the two-point corner slice
(`--arms ideal,package --corner-points tt_27c_1.80v,ss_27c_1.80v --record`) —
so a run with any *other* `--arms` list, any other sweep box, or any other
corner subset needs its own bench entry in `sim/spec-coverage.json` and its own
verbatim documented command here, the same way `sar-sequencer-behavioral`
indexes its `--corners` variant separately. Every widening of the corner subset
is therefore a new indexed invocation, not a re-run of an existing one — the
price of `--corner-points` being part of a record's identity rather than a
scheduling detail.

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
`R_SUB` is load-bearing is `no-gnd-pad`, which now has a record of its own at
the single assumed `R_SUB = 30 Ω` (see Findings) but no sweep of it — so an
`R_SUB` sweep is that arm's own campaign and stays open on #409. Each sweep
record says this in its own "What this sweep does not cover" section rather than
letting "substrate resistance" be read as both.

**The sweep record does not move `records/LATEST`, and supersedes nothing.** It
is a *distinct* claim about the same DUT: an arm-comparison record compares
networks at DR-015's assumption point, the sweep walks a box around that
point on one of them, and both stand. Moving the pointer from an arm record to
a sweep record would make a citation of a record nothing had superseded read as
*stale* to this repo's citation gate. Same disposition, for the same reason, as
`sim/full-conversion-transient/run_conversion.py`'s diagnostic record writers.

**An arm record does move it, on purpose.** `records/LATEST` names this flow's
most recent *arm-comparison* record, which since 2026-09-25 is
[`20260925-204633-7339971`](records/20260925-204633-7339971.md) (the ground-pad
ablation pair) rather than `20260925-073912-0e385e5` (the four-arm comparison).
Nothing was superseded by that move and no earlier number was retracted: what
the pointer feeds is `check_proposal_citations.py`'s **arm census** (check 31),
which is deliberately a statement about *one* record's arm coverage — "the
record `records/LATEST` names runs N and leaves M unrun" — and is the
mechanism that stopped "implemented but not run" from being remembered only in
prose. Freezing the pointer on the older record to keep a tidier census would
have hidden exactly the arm this campaign had just run. The consequence a
reader must carry instead: **the campaign's five arms are covered by two
records, not one.** `package-r-only` and `substrate` are unrun *in the current
record* and run in `20260925-073912-0e385e5`; both records stand, neither
supersedes the other, and any document citing this flow cites the record
carrying the number it wants rather than the pointer alone.

**Cost, and `--sweep --corners`.** The default box is nine whole-ADC transients
plus the control, run one at a time, which is hours — use `--log-cache`, and see
the cost probe below for what those hours actually are. The combination
`--sweep --corners` (and `--sweep --corner-points`) is **refused**: it is two
of #409's costs multiplied together — nine boxes of whole-ADC transients, a
campaign in its own right rather than a longer version of this one
(see "Why the corner grid arrives in pieces").

**The box has been run**, and its record is
[`records/20260925-164447-722fcb0.md`](records/20260925-164447-722fcb0.md) —
ten whole-ADC transients (nine swept points plus the `ideal` control) at
`tt_27c_1.80v`, 3049 s of sequential wall clock, every point converged. Its
bench entry landed in `sim/spec-coverage.json` in the same commit, as the
paragraph above requires. What it found is in "Findings" below; what it
deliberately does not cover (`R_SUB`, an extracted substrate network, the other
eight corners) is in the record's own "What this sweep does not cover", not
left to a reader to infer.

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

**How the projection held up, now that the box has been run.** The full run
([`records/20260925-164447-722fcb0.md`](records/20260925-164447-722fcb0.md))
prices the same ten points at full stimulus, so the probe can be graded instead
of trusted. Measured full-run cost, as a multiple of the anchor's own full run
(389 s) — the probe's prediction in parentheses:

| bond `L` (× DR-015) | `R_SUBX` = 3 Ω | `R_SUBX` = 30 Ω | `R_SUBX` = 300 Ω |
|---|---|---|---|
| `0×` | 0.32× (0.49×) | 0.38× (0.53×) | 0.54× (0.52×) |
| `1×` | 1.08× (0.96×) | **1.00×** (anchor) | 0.98× (0.96×) |
| `10×` | 1.07× (0.96×) | 1.16× (0.63×) | 0.95× (0.47×) |

- **The decision the probe was bought for was correct.** It was asked whether
  the `10×` row is the row nobody can afford; it is not, and the full run agrees
  — the dearest point in the box costs `1.16×` the anchor, not multiples of it.
- **Its per-point numbers are not a forecast.** The `10×` row came in higher
  than predicted (up to `1.16×` against a predicted `0.47–0.96×`), so three
  points do exceed the anchor rather than none. A 400 ns slice starts inside the
  solver's start-up transient and ends before the ring-down the full stimulus
  pays for, which is exactly the part that scales with `L`.
- **The box total was predicted within ~12 %**: `≈ 7.0` anchors predicted
  against `7.8` measured (3049 s at this host's 389 s anchor). Scaled by the
  *committed* arm-comparison record's own 1261 s anchor the same 7.8 is ≈ 2.7 h,
  against the ≈ 2.5 h projected — the ratio is the transferable part, the
  absolute hours are whichever host you scale by.

## The bounded null-option substrate ladder (`--null-sweep`)

The 2-D box above deliberately does **not** sweep a substrate *return*, and
says so in its own scope section: on the as-built `package` topology `GND` has
a bond of its own, so the resistor that box moves sits **beside** that bond as a
shunt between the two ground die nodes. The topology where that same resistor
**is** the analog ground's entire path to the board is `no-gnd-pad` — DR-012's
rejected null option — and sweeping it there is a different experiment with a
different reading. That is `--null-sweep`:

```sh
python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --null-sweep --record
```

**The gap it closes is a claim, not an absence.**
[DR-015](../../spec/decision-records/DR-015-package-parasitic-assumption.md)'s
Consequences section says of that arm:

> The `no-gnd-pad` arm … is **entirely** a function of `R_SUB`: with a small
> `R_SUB` it looks harmless, with a large one it looks fatal.

Both halves of that sentence are predictions about magnitudes the campaign had
only ever run at **one** value (DR-015's assumed 30 Ω). The `no-gnd-pad` record
priced the option at that point; this ladder is what turns "harmless … fatal"
into a measured sensitivity.

**What it sweeps.** One axis, on the `no-gnd-pad` topology, plus the same
`ideal` control every number is a difference against:

| axis | default ladder | what moving it means |
| --- | --- | --- |
| the lumped substrate **return** | `3`, `30`, `300` Ω (DR-015 assumes 30) | how well the p-substrate alone gets the analog ground's current off the die, with no analog ground bond to help it — the assumption the whole rejected-option result rests on |

The three bonded terminals (`VDD`, `VPWR`, `VGND`) keep DR-015's R+L unchanged
at every rung, so each step moves one element and nothing else (DR-015 item 5).
This is a **one-axis ladder on purpose**: crossing it with the inductance
ladder would be a second 2-D box and would confound the question, which is what
the rejected topology costs as the substrate assumption moves.

**Which stand-in moves, and what it is called.** DR-015 item 2 defines two
lumped stand-ins — `R_SUB`, a substrate-only ground *return*, and `R_SUBX`, the
link "between the analog and digital ground die nodes". In this topology **one
resistor is both**: it spans `GND_DIE` and `VGND` (so the deck names its
instance `RSUBX`, after the node pair it bridges) and, with `GND` unbonded, it
is also the only path the analog ground has to the board (so it plays `R_SUB`'s
role). DR-015 sets both to the same 30 Ω, so at the anchor the distinction
changes no number — but a ladder that swept "the substrate resistance" without
saying which element moved would be unreadable next to the 2-D box, which moved
an element of the same name in a topology where it does something else. Every
record this mode writes states it in its own section.

**The ladder is anchored to the committed ground-pad ablation.** Its `30 Ω`
rung is, card for card, the `no-gnd-pad` arm of
[`records/20260925-204633-7339971.md`](records/20260925-204633-7339971.md) —
same three bonded terminals at DR-015's R+L, same unbonded `GND`, same
stimulus. That identity is asserted before the run starts and again when the
record is written (`null_sweep_anchor_matches_base_arm()`), and
`sim/tests/test_supply_impedance.py` pins it, so a later edit cannot quietly
re-centre the ladder onto a topology that is no longer DR-012's rejected
option.

**It supersedes nothing and does not move `records/LATEST`**, for the same
reason the 2-D sweep record does not: that pointer names this flow's newest
*arm-comparison* record, which is what the citation gate's arm census (check
31) reads, and a ladder record carries no arm census to offer. It is also
invisible to the *sweep* census (check 32) by construction — its header line is
`- **Ladder**:` rather than `- **Grid**:`, because it is not a point of that
box — and `sim/tests/test_supply_impedance.py` asserts both censuses' parses
against what this writer actually emits.

### What the first ladder found, and the one thing it changes

[`records/20260926-000929-ce12f9b.md`](records/20260926-000929-ce12f9b.md) is
the first run of this mode. Two of its results need reading carefully, because
neither is the shape DR-015's prose predicts.

**The excursion is not monotone in the substrate return.** Down the ladder the
die-side analog ground moves `72.130 mV → 67.307 mV → 137.093 mV` for
`3 Ω → 30 Ω → 300 Ω`, while `VGND`'s own die node falls monotonically
(`72.288 → 71.425 → 57.388 mV`). So the middle rung is the *quietest* of the
three, and "small `R_SUB` looks harmless" — the first half of DR-015's sentence
— is **not** what the measurement says at this corner: 3 Ω is slightly worse
than the assumed 30 Ω, not better. Only the second half survives, and only
directionally: at 300 Ω the excursion roughly doubles. The two halves of the
ladder are doing different things — at a small return the analog ground is
welded to `VGND` and inherits its bond's ringing, at a large one it floats free
of the board altogether — and a single resistor sweeping across that crossover
is not a curve anyone should read a slope off. The endpoint ratio the record
reports (**1.90×** over 100× of resistance) is exactly that: an endpoint ratio,
stated instead of a trend.

**No captured code moves anywhere on the ladder** (worst mid-scale
`|Δ code|` = 0 LSB at every rung). That is a *bounded* null, over 3–300 Ω at
`tt_27c_1.80v` only, and it is not a finding that the pad does not matter — the
rail moves where the code does not.

### Reproducing a deck across hosts: what agrees, and to what

The `30 Ω` rung and the `no-gnd-pad` arm of
[`records/20260925-204633-7339971.md`](records/20260925-204633-7339971.md) are
the same deck — `diff` of the two committed `.cir` files differs only in
comments and in the `.lib` path prefix — at the same pinned
`open_pdks c6d73a35…` and the same ngspice major. They do not print the same
numbers, and the four committed records between them say exactly why: the
`.lib` prefix is `/home/ubuntu/…` in two of them and `/Users/rwalters/…` in the
other two, so this campaign has, by accident, run the same decks on **two
hosts**.

| deck | host A (`/home/ubuntu`) | host B (`/Users/rwalters`) | difference |
| --- | --- | --- | --- |
| `ideal`, total power | `27.971 µW` (`…073912`, `…000929`) | `27.957 µW` (`…164447`, `…204633`) | 0.05 % |
| `ideal`, `I(VDD)` | `2.097 µA` | `2.094 µA` | 0.14 % |
| `package`, `GND_DIE` pp | `37.333 mV` (`…073912`) | `37.590 mV` (`…204633`) | 0.69 % |
| `no-gnd-pad` (= `30 Ω` rung), `GND_DIE` pp | `67.307 mV` (`…000929`) | `65.237 mV` (`…204633`) | 3.2 % |

**Within a host the same deck is bit-identical across separate records** — the
`ideal` control prints `2.097 / 6.966 / 2.177 µA` in both host-A records and
`2.094 / 6.961 / 2.174 µA` in both host-B ones — so the spread in the right
column is host, not run-to-run noise. Across hosts the *averaged* quantities
agree to a tenth of a percent, while a *peak-to-peak* disagrees by ten to fifty
times that, and it disagrees most on the arm whose ground rings hardest: 0.69 %
on the bonded `package` ground, 3.2 % on the unbonded one. That is what a pp
figure is — a value read off whichever timesteps an adaptive solver happened to
place on a lightly-damped waveform — and not a defect in either run.

**The consequence is a reading rule.** A few percent of difference in a `pp`
column taken *across* records is inside the host's own spread, so pp numbers
may only be subtracted *within* one record, where every arm saw the same solver
on the same machine. Every delta this campaign actually claims — in every
record — is already within-record; this table is what licenses that restriction
instead of leaving it to etiquette. It also bounds the anchor check: the `30 Ω`
rung is the committed `no-gnd-pad` arm *by construction* (asserted card for
card, twice, in code), and reproduces it *numerically* to 3.2 % on a different
machine.

**Cost, and why it could be paid now and not before.** This ladder was owed
from the day `--sweep` landed, and was not run for the same reason the
`no-gnd-pad` arm itself was not: a truncated-slice projection of roughly an
order of magnitude per run. The full `no-gnd-pad` run then measured **1.67×**
the control — see the struck-through bullet under "Runtime" above — so the
ladder is three runs of that order plus the control, not the day-long campaign
the projection implied. `--cost-probe` accepts `--null-sweep` as well, under
exactly the same refusals (`--record`, `--log-cache`, `--supersedes` and a
slice not shorter than the stimulus are all rejected), and `--null-sweep
--corners` is refused for the same reason `--sweep --corners` is.

## Why the corner grid arrives in pieces

`--corners` (every arm × the nine-point ratified OAT grid) is implemented, and
until issue #409 item 1 this section said the grid was waiting for a host whose
**policy** allowed a local multi-corner ngspice run at all. That reason was
re-checked on a measuring host on 2026-09-25 and **retired** rather than
re-stated, because it was not what binds:

- **The ngspice pin is satisfied here.** `--check-env` on the host that minted
  `records/20260926-012944-a966fdf.md` reports `ngspice-46`, at
  `sim/toolchain.json`'s `ngspice_min_major = 46` floor. The pin was never the
  obstacle on this host; it is the obstacle on the *batch fleet* (below).
- **Local multi-corner simulation is not forbidden here.** The non-baseline
  point in that record was simulated locally, in one session, one deck at a
  time. A blanket "this host may not run a grid" is therefore false, and the
  two `--sweep --corners` / `--null-sweep --corners` refusals in the runner no
  longer cite it either — they cite the cost of nine boxes, which is true.

What *does* bind is a cost against a session that must end, and it is measured
rather than projected:

- **The grid is hours; a dispatch session is not.** Five arms × nine points is
  45 whole-ADC transients; even the two-arm slice this README documents is 18.
  At the per-arm wall clock in the records (`ideal` 292 s, `package` 678 s on
  an uncontended host) two arms × nine points is ≈ 2.4 h *before* contention.
  With contention it is much worse, and that was measured too: on 2026-09-25
  this host was simultaneously running another repo's Monte-Carlo ngspice
  campaign, and the `ideal` deck that costs 292 s alone was getting ≈ 26 % of
  one core — about 19 minutes of wall clock for the same 5 minutes of CPU.
  Under that load the 18-run slice projects to ≈ 9 h.
- **No process may outlive the session that started it.**
  `.loom/docs/long-running-compute.md` is explicit: an agent session may run
  ngspice locally, but backgrounding a multi-hour job past the end of the
  session is forbidden (a real 12-hour outage is the reason), and the
  sanctioned answer is to *scope the run to the session, land the increment,
  and name what is left*. That is the shape this campaign now uses.
- **The batch route still cannot mint a record in this repo's format.** `klt
  sim` owns its own request/response JSON contract and its own corner
  expansion, while every record under `sim/` is written by this repo's
  `sim/harness/evidence.py` against a deck this repo assembles — so routing the
  grid there produces a different artefact, not this one. Separately, the
  fleet's runner image installs ngspice from the distribution archive, and this
  repo's own [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)
  already records what that means: the archive build is **ngspice-42**, below
  the floor above, which is exactly why CI builds ngspice from source instead.
  A record minted below that floor is refused by
  `sim/check_spec_coverage.py`'s pin gate and would not be comparable with
  anything already under `sim/`. This constraint is unchanged.

**So the grid is completed by accumulation, and `--corner-points` is the
mechanism.** It names a subset of the *same* `ratified_oat_grid()` — it can
narrow that grid and can never invent a point outside it — and
[`--log-cache`](#--log-cache-because-one-arm-outlives-most-process-supervisors)
carries finished points across sessions on a host, so a later run of a wider
subset re-simulates only what it does not already have. Each such record states
its own "Subset-corner justification" per `sim/README.md`'s rule, naming which
points it holds and that the rest are owed.

### What the first non-baseline corner found

**Where the grid stands: 2 of 9 points, for 2 of 5 arms** —
`tt_27c_1.80v` and `ss_27c_1.80v`, `ideal` + `package`
([`records/20260926-012944-a966fdf.md`](records/20260926-012944-a966fdf.md)).

- **The null holds at the slow-process corner.** Worst mid-scale
  `|Δ code|` = **0 LSB** at `ss_27c_1.80v`, as at the baseline. The two
  near-full-scale codes do move with the corner (`-0.78·V_REF` reads 223 at
  `ss` against 214 at `tt`), but they move **identically in the `ideal`
  control and in the `package` arm**, so that is the corner acting on the ADC
  and not the supply return acting on anything — which is exactly why the
  mid-scale delta is taken against the control *at the same corner*.
- **The excursion is _smaller_ at the slow corner, not larger**: `GND_DIE`
  peak-to-peak **28.472 mV** at `ss` against **37.590 mV** at `tt` (0.76×),
  and every other die node moves the same way. Consistent with the mechanism —
  slower edges mean less `di/dt` into the same bond inductance — and it is a
  reason **not** to read `ss` as the worst corner for this campaign.
- **Cost, for the next session's planning**: `package@ss` took **1400 s**,
  2.07× the `ideal` arm at the same corner and 2.07× the same arm at `tt` —
  most of that a contended host rather than the corner itself.

**What is owed, and tracked in issue #409**: the seven remaining points, and
the three arms that have never left the baseline corner. The two points most
likely to *move* the excursion are not yet among them — `ff_27c_1.80v` and
`tt_-40c_1.80v`, where the fastest edges make the largest `L·di/dt`, and where
the `ss` result above says to look. So no excursion figure in these records may
be read as corner-worst-case.

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
  the nine-point ratified corner grid (partially done since, and still open —
  see "Why the corner grid arrives in pieces" above), and DR-012's *rejected*
  `no-gnd-pad` null option (implemented, not run, on cost — see "Runtime"
  above). Neither a worst-corner claim nor a "the rejected option would have
  cost N mV/LSB" claim may be made from this record alone. The second of those
  is now priced by a record of its own (next section but one); the first is
  still open.

### What the bounded `R`/`L` sweep adds

The second record
([`records/20260925-164447-722fcb0.md`](records/20260925-164447-722fcb0.md),
the default box at `tt_27c_1.80v`) does not supersede the first: that one
compares five *networks* at DR-015's assumption point, this one walks a box
around that point on the as-built network. It is what retires
[DR-015](../../spec/decision-records/DR-015-package-parasitic-assumption.md)'s
"No `R`/`L` sweep" open item, at this scope:

- **A bounded null on codes.** No mid-scale captured code moves anywhere in the
  box — worst `|delta code|` = **0 LSB** at every one of the nine points, out to
  `L = 10×` DR-015's bond inductance and `R_SUBX` over two decades (3–300 Ω).
  The threshold the sweep went looking for is **outside** the box, not located
  inside it; a wider box or another corner could still find one, and this is not
  a claim that none exists.
- **Die-side excursion keeps climbing while the codes do not.** `GND_DIE`
  peak-to-peak along the `R_SUBX = 30 Ω` column: **0.059 mV** (`0×`) →
  **37.590 mV** (`1×`) → **99.749 mV** (`10×`). Only `L` moves along that row,
  so it is the bond inductance's own contribution (DR-015 item 5). The box's
  worst point is **111.622 mV** (≈31.8 LSB at the nominal supply) at
  `10× / 300 Ω` — undecoupled by construction, so an upper bound, not a
  prediction.
- **The `R_SUBX` axis is the weak one here.** At `L = 0×` the column is flat
  (0.056 → 0.059 → 0.059 mV); it only does anything once there is an inductance
  for it to steer current around, and even then non-monotonically (40.688 →
  37.590 → 22.556 mV at `1×`, but 101.539 → 99.749 → 111.622 mV at `10×`).
  Nothing here licenses "looser substrate coupling is safer": the two mechanisms
  interact, and the record reports the pair rather than a trend.
- **The anchor reproduces the committed `package` arm across hosts, to 0.7 %.**
  The sweep's `1× / 30 Ω` deck and the arm-comparison record's `package` deck
  differ only in their comment lines and the PDK install prefix (`diff` the two
  `.cir` files under `corners/`) — same open_pdks pin, same `ngspice-46` — but
  they ran on different machines — the committed deck's PDK prefix is
  `/home/ubuntu/...` (a Linux dispatch host), this one's is `/Users/...` on an
  `arm64` Darwin host — and report **37.333 mV** and **37.590 mV**. Every captured code is identical
  (214/383/511/641/1023). Read the mV figures at two significant figures when
  comparing across records; the LSB verdict is the part that transferred exactly.

### What the `no-gnd-pad` record adds: the price of the rejected option

The third record
([`records/20260925-204633-7339971.md`](records/20260925-204633-7339971.md),
`ideal`/`package`/`no-gnd-pad` at `tt_27c_1.80v`) supersedes neither of the
others. It exists for one number the first record explicitly could not carry:
what DR-012's **rejected** null option — no analog-ground pad at all, `GND`
reaching the board only through the lumped substrate link — would have cost,
measured against the option DR-012 **chose**. It is issue #409's item 2:

- **The ground-pad ablation, at last a measurement.** `no-gnd-pad` vs
  `package` is a strict one-element ablation (same three bonded terminals,
  same `R_SUBX`, the only difference is whether `GND` has a bond of its own):
  die-side `GND_DIE` excursion **65.237 mV** against **37.590 mV**, i.e.
  **1.74×**, or **+27.6 mV** of extra excursion charged to deleting the pad.
  In LSB at the nominal supply that is 18.556 against 10.692.
- **And it is still a null on codes.** Worst mid-scale `|delta code|` vs the
  `ideal` control = **0 LSB** for `no-gnd-pad`, the same verdict every other
  arm and every sweep point returns. So at this corner and these assumed
  magnitudes the rejected option is *worse on the rail and indistinguishable
  on the output* — which is exactly why DR-012's decision could not have been
  made on captured codes, and was not.
- **Read it at DR-015's assumed substrate magnitude or not at all.** This arm
  is a function of the lumped `R_SUB`/`R_SUBX` stand-ins above all else
  (DR-015's own Consequences say so): with a small one it looks harmless, with
  a large one it looks fatal, and 30 Ω is an assumption taken from DR-012's
  prose, not an extraction. The `+27.6 mV` is a number about *a* substrate-only
  return of that order, not about this die's substrate.
- **The `package` arm reproduces a third time, exactly.** Its `GND_DIE`
  excursion here is **37.590 mV**, the same figure to three decimals as the
  sweep's `1× / 30 Ω` anchor on this host (and 37.333 mV on the Linux host that
  minted the first record) — so the two records this section compares are
  anchored to each other, not merely adjacent.
- **What this record does not carry**: no bond-inductance ablation (it has no
  `package-r-only` arm — that number stays in the first record), no
  `substrate` arm, and no corner other than the baseline. The nine-point
  ratified grid remains #409's item 1, and the extracted substrate network its
  item 4.

### What the decoupled netlist has and has not shown (2026-09-26, issue #431)

Every record above measures the **undecoupled** design.
[DR-017](../../spec/decision-records/DR-017-on-die-decoupling-budget.md) (issue
#431) put one `cap_mim_m3_1` per supply domain into
`design/sar_adc_top.spice`, and sized it using this campaign — so three more
`package`-arm measurements at `tt_27c_1.80v` now bear on it. **None of them is a
record here**: one is a probe against a netlist that is not the committed
design, and two are arms of an invocation that never finished. They are cited
from DR-017, which says of each what it is.

- **`MF = 32` per domain (141.9 pF, a MiM area 1.3× the whole composed die):**
  `GND_DIE` **9.214 mV**, `VPWR_DIE` **12.153 mV**, captured code unchanged. The
  comparison is against the **first** record's 37.333 / 61.755 mV rather than the
  sweep's or the null-option record's 37.590 mV, because the probe ran on the
  same Linux dispatch host that minted the first one (see the anchor-reproduction
  bullet two sections up for why the host matters at the third significant
  figure). A factor of only **4.05** for 16× the capacitance DR-017 ships — the
  ~1/√C response that is DR-017's central finding, and the reason it sizes from
  an area budget rather than from a bounce target.
- **The as-committed `MF = 2` netlist, `ideal` and `package-r-only` arms:**
  captured codes and all five average rail currents identical to the first
  record's own rows for the same arms, and `GND_DIE` unchanged at **0.059 mV**
  with the inductance zeroed. Two capacitors across *ideal* sources change
  nothing, and two across a purely *resistive* return change nothing — both as
  they must, and together the no-regression check DR-017 needed before adding
  any device.
- **The as-committed `MF = 2` netlist, `package` arm: not measured.** This is the
  number DR-017's decision would most like to cite, and
  [#448](https://github.com/2AMLogic/sky130-sar-adc/issues/448) is its tracker.
  It is a host problem, not a code problem — see "Budget a decoupled run from
  decoupled numbers" above. Note that the sweep and null-option records above
  were minted on a **Darwin arm64** host, so a host that can hold this arm may
  well already be in the fleet; #448 is not waiting on new hardware, only on a
  run.

So `records/LATEST` continues to name an **undecoupled** record, correctly: no
committed record in this directory measures the decoupled netlist yet, and
DR-012's retirement and `docs/chipalooza/challenge-4-proposal.md`'s Power row
both rest on records that do exist rather than on a number nobody has run.

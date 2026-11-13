# sim/input-drive-budget — VINP/VINN source-impedance budget (issue #847)

How much series source resistance the `VINP`/`VINN` pads tolerate while the
sampling front end still acquires a new full-scale differential input inside
the acquisition window, at every ratified PVT corner and at both acquisition
windows this repo's sampling-frontend campaigns use.

Before this campaign, no `sim/` testbench put any source impedance on the
signal inputs: `sim/full-conversion-transient/testbench/full_conversion_tb_fragment.spice`
drives them from ideal `PWL` sources, and `sim/vcm-drive-budget/`'s only series
element is on `VCM`. Challenge #4's `get-involved.html` asks the proposal's I/O
list to "note any special requirements such as low resistance to the pad";
`docs/chipalooza/challenge-4-proposal.md`'s `VINP`/`VINN` rows cite this
campaign for that figure.

It grades no spec row and changes none (`spec/target-spec.md` is DRAFT until
#1). `spec/target-spec.md`'s DRAFT Kickback row already names a 1 kOhm series
source impedance on these pins, which is why 1 kOhm is a **simulated** point in
the sweep rather than an interpolation — but this campaign does not grade that
row.

Latest record: `records/LATEST`.

## Run

```sh
source sim/env.sh
python3 sim/input-drive-budget/run_input_drive_budget.py --check-env
python3 sim/input-drive-budget/run_input_drive_budget.py --dry-run   # deck + request only
python3 sim/input-drive-budget/run_input_drive_budget.py --probe     # ONE corner/R/window, local
python3 sim/input-drive-budget/run_input_drive_budget.py --record    # 9 corners x 16 steps, via klt sim
```

`--record` submits **one** `klt sim` request — 9 corner units, each running 16
transient steps (2 windows x 8 resistances) — with `--wait-for-capacity 600`,
so a vCPU-budgeted fleet queues the launch instead of refusing it. It sets no
backend itself (`klt sim` follows `KLT_SIM_BACKEND` / the request), and a
failed submit raises rather than falling back to a local `ngspice` loop. Pass
`--backend` to override.

`--probe` is the only path that runs on the submitting host: a single corner,
`R_source = 0`, the worst-case window, `--backend local`. It prints the per-node
residual next to the value
`sim/sampling-acquisition-settling/records/20260908-051436-6ccd72d.md` reports
for the same corner and probe time, so the harness can be checked against that
campaign before any fleet capacity is spent.

## Method

- **DUT.** `sim/sampling-frontend/testbench/sampling_frontend_dut.spice`,
  unmodified and **read in place** — the committed-fragment convention
  `sim/sampling-frontend/run_hold_kick.py` set and both mirrored campaigns
  follow. The only harness addition on the signal path is one ideal source in
  series with one resistor per input pin (`Rsp`, `Rsn`, always swept together).
- **Stimulus.** The two-pulse old-value-to-new-value full-scale step of
  `sim/sampling-acquisition-settling/run_acquisition_settling.py`: SAMPLE
  pulse #1 settles the OLD value; `VINP`/`VINN` step to the opposite
  rail-adjacent extreme (0.2 V ↔ 1.6 V per side) during HOLD, while `Msw` is
  off; SAMPLE pulse #2 acquires the NEW value. For an input-side resistance the
  previous held sample *is* the stimulus, which is why a single SAMPLE pulse
  from ngspice's own bias-point guess (`sim/vcm-drive-budget/`'s shape) is not
  usable here.
- **Reading.** A FIXED-TIME `find v(node) at=<t>` probe, exactly one acquisition
  window after SAMPLE pulse #2's 50 % rising edge (160.1 ns). **No crossing
  search**: that runner's docstring records two separate ngspice `.meas
  TRIG/TARG` pitfalls found by debugging implausible crossing results against
  raw transient data, and a single point sample can reproduce neither. A
  long-time `confirm` read, clear of pulse #2's own documented turn-off kick,
  is reported alongside.
- **Windows.** Both of `sim/vcm-drive-budget/`'s: `worst` = the DR-006-derived
  worst-case acquisition window (12 MHz, 83.333 ns) and `legacy` = this repo's
  pre-existing 400 ns sampling-frontend testbench convention. The `worst`
  window reproduces the mirrored runner's own pulse-#2 width, probe and confirm
  times exactly; the 400 ns window does not fit that fixed 150 ns pulse, so
  pulse #2 and the transient grow with the window.
- **Observable and control.** The sampled differential value at the probe,
  against its ideal target (1.4 V). **Every corner and window carries its own
  `R_source = 0` row**, the record shows the raw error against the ideal
  target, and every budget is computed on the error *relative to that row*.
  This is not cosmetic: `sim/sampling-acquisition-settling/`'s `LATEST` reports
  a −0.3800 mV per-node residual at `tt_27c_1.62v` with an **ideal** source
  (~0.11 provisional LSB), so a 0.1-LSB tier read against the ideal target
  could "fail" there with no source resistance at all.
- **Budget rule.** `sim/vcm-drive-budget/`'s `find_budget()`: the **largest
  swept** resistance still within the tier, at 1.0 and 0.1 provisional LSB
  (3.5156 mV, DR-003 Item 2 pending #27 — a reference scale, never a gate).
  A result equal to the top of the sweep is reported **right-censored**
  (`>= 100000`), i.e. a lower bound, not a measured limit. A sweep where even
  the smallest non-zero value fails reports `< 100 (none found)`, never a
  budget of 0 — the `R_source = 0` row is the *reference*, so it is excluded
  from the candidates (see `find_budget()`'s docstring for why the mirrored
  implementation's own None branch is unreachable and this one's is not).
- **Sweep.** `sim/vcm-drive-budget/`'s own list, unchanged:
  `0, 100, 300, 1e3, 3e3, 10e3, 30e3, 100e3` ohm. `0` is emitted as a 1 µOhm
  resistor rather than a literal 0 — the same ngspice singular-matrix
  avoidance that runner documents; at 1 µOhm the series time constant is ten
  orders of magnitude below the window.

## Why its own runner, and why it goes through `klt sim`

`sim/vcm-drive-budget/` and `sim/sampling-acquisition-settling/` both loop
`ngspice` in-process and never call `klt sim`, so only their **reporting**
convention and **stimulus** are reused here, not their execution. Copying
either would hand-launch an `ngspice` grid on the dispatch host, which this
campaign is explicitly not allowed to do. The execution pattern is
`sim/top-plate-cpar/`'s — plus the `--wait-for-capacity 600` that runner does
not pass. Neither of those two runners is converted (they are 1316 and 1049
lines; that is separate work).

Both sweep axes fit inside the single request as `analysis_steps[]`: one
`tran` step per (window, resistance), each with `reset: true`, an `alter` of
the two series resistors, an `alter` of the SAMPLE control source's `pwl`
vector, and its own transient stop and `.meas` times. So `--batch-set` is not
needed and the corner axes stay where `klt sim` puts them.

**One deck serves all nine corners**, so SAMPLE cannot have the corner's supply
baked into literal `pwl` values the way a per-corner regenerated deck can. It
is a normalised 0..1 `pwl` control scaled through `Bsample SAMPLE 0
V=v(SMP_CTL)*v(VDD)` — which is also what makes the vector corner-independent
and therefore `alter`-able per step.

**Measurement names avoid node names.** An ngspice `meas` result is written as
a vector into the step's own plot, so a measurement named `top_p` overwrites
`v(TOP_P)` with a length-1 scalar and every *later* card in that step reading
it fails with `out of interval`. Hence `budget_p` / `confirm_p`, the same
naming the mirrored acquisition-settling runner uses. Asserted in
`sim/tests/test_input_drive_budget.py`, and filed upstream as a
request-validation gap (`klt sim` already parses the netlist to validate
`alter` targets): 2AMLogic/klayout-tools#5446.

## What this testbench does not model

Series resistance only — **no** pad capacitance, ESD network, anti-alias
capacitor at the pad node, or package/bond-wire inductance. The stimulus is a
**full-scale** step between consecutive samples (the worst case for a
near-Nyquist input), the front end's `Csamp` stands in for the CDAC array, and
`VCM`, the references and the supply are ideal. `VCM` is the mirrored
campaign's fixed 0.9 V and does **not** track the supply corner; the 0.2/1.6 V
input extremes are likewise fixed at every corner, exactly as in that runner.
A budget is the largest *swept* value, so it is quantised to the log-spaced
list above. SAMPLE pulse #1, which settles the OLD value, is a fixed 100 ns
inherited from the mirrored runner (ideal source there); the `R_source` under
test slows that settling too, so at large swept resistances the realised step
is smaller than the full-scale span and those rows understate the error — the
deviation grows with `R_source`, is largest at the top of the sweep list, and
is not quantified here. The record repeats this list in full — read it there,
not here.

## Tests

`sim/tests/test_input_drive_budget.py` — PDK-free: budget tiers (censoring,
control-relative subtraction, a control row outside a tier), the request shape
(9 corners, both windows, `0` and `1e3` present, both axes as steps), the deck
body's `alter` targets and supply-source naming, and the report reader's
error-envelope handling.

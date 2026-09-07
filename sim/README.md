# sim/ — harness and evidence-record format

This directory holds the simulation harness (`sim/harness/`, driven by
`sim/run_corners.py` and `sim/monte_carlo.py`), the testbenches it runs, and
the results those runs produce.

Results are **append-only evidence**: once a record is written it is never
edited or deleted. A re-run — even one that corrects a mistake — mints a new
record with a new ID; a correction references the record it supersedes rather
than overwriting it in place.

This convention exists because `CLAUDE.md` commits this repo to two rules that
need a concrete schema to be enforceable:

- **Verification is the product.** No claim without a testbench. PVT corners
  on every recorded result (see "Corner matrix run" below).
- **`sim/` results are append-only evidence.** Re-runs get new records;
  records are never edited or deleted.

## Provenance

Per `CLAUDE.md`'s "Harness bootstrap" rule, this format and the harness that
writes it are **ported from the sibling canaries rather than designed from
scratch**:

| Piece | Ported from | Commit |
| --- | --- | --- |
| Record format, `<record-id>` / `<corner-id>` schemes, append-only + `Supersedes` semantics, ADC-specific field groups | `2AMLogic/gf180-sar-adc` `sim/README.md` | `f613571aee5b80eff1eea37bdce9dfc88c5cf396` |
| `sim/run_corners.py` / `sim/harness/*` module split, `sim/toolchain.json` pin-check convention, `sim/env.sh` | `2AMLogic/gf180-sar-adc` `sim/` | `f613571aee5b80eff1eea37bdce9dfc88c5cf396` |
| sky130 PDK plumbing: `sim/pdk.json`, `sim/spiceinit`, `sim/xschemrc`, `docs/environment-setup.md` | `2AMLogic/sky130-bandgap` | `1f04e8524cc2d8c2c7154773749b1b2d3be2ce64` |

Divergences from those sources, each deliberate:

1. **The corner matrix is not fixed to a numeric list here.** `spec/target-spec.md`
   is DRAFT until issue #1 ratifies it, and `CLAUDE.md` forbids encoding an
   unratified spec value as a pass/fail threshold. So `sim/harness/corners.py`
   supplies only the *axis lists* that are properties of the PDK and of repo
   convention (which `.lib` process-corner sections exist; the canary-standard
   −40/27/125 °C and ±10 % default sweep); every testbench manifest states its
   own `nominal_supply_v` and its own checks. The "Corner matrix run" field
   below is normative on *what a record must state*, not on a specific numeric
   list. When #1 (and `spec/decision-records/DR-001-supply-flavor-scope.md`)
   ratifies the supply flavor, a manifest's `nominal_supply_v` is the single
   place that changes — no harness code does.
2. **A first-class Monte Carlo runner** (`sim/monte_carlo.py`) with a
   *mechanical* negative control. gf180-sar-adc's `sim/README.md` documents a
   Monte Carlo *record convention*; this repo also ships the runner that
   produces one, because ENOB / INL / DNL / offset are distributions rather
   than corner points. See "Monte Carlo records" below.
3. **`sim/harness/` is a Python package, not `sim/bin/corner-run.py`.**
   sky130-bandgap uses a single script; splitting the corner runner and the MC
   runner over shared `pdk`/`toolchain`/`testbench`/`measure`/`evidence`
   modules keeps the two runners from drifting apart in how they resolve the
   PDK or stamp a record. Stdlib only, no virtualenv, in both repos.

## Quick start

```sh
python3 sim/run_corners.py --check-env        # toolchain + PDK pin check
python3 sim/run_corners.py --list             # available experiments
source sim/env.sh                             # export PDK_ROOT / PDK

python3 sim/run_corners.py <experiment> --record
python3 sim/monte_carlo.py  <experiment> --seed 1 --n 100 --record

sim/selftest.sh                               # the harness acceptance test
```

`--check-env` distinguishes its failure modes on purpose: exit **3** means a
tool or the PDK is simply *missing* (skippable on an unbootstrapped machine),
exit **1** means everything is installed but a pinned version *drifted* — a
real problem, because results from a drifted toolchain are not comparable with
the records already in this directory.

## Harness self-test experiments

Two of the experiment directories here are **harness proofs, not design
claims**, and neither will ever substantiate a spec row:

- **`harness-corner-smoke/`** — an ideal resistive divider (PVT-invariant
  control) plus a diode-connected `nfet_01v8` at a fixed 10 µA bias
  (process/temperature-sensitive probe). Its per-axis sensitivity checks prove
  the corner runner actually switches the `.lib` process-corner section, the
  `.temp` card, and `vdd_val` — independently, so a bug on one axis cannot
  hide behind a pass on another.
- **`mc-smoke/`** — one small diode-connected `nfet_01v8`, drawn N times at
  the `tt_mm` local-mismatch corner, with N deterministic draws at the plain
  `tt` corner as the negative control.

They exist because issue #2 stands the harness up *before* any ADC schematic
exists. Once a real testbench lands, it adds an experiment directory alongside
these and reuses the same two runners unchanged; these two stay as the
regression that proves the plumbing still works.

That exclusion is enforced, not merely stated: `sim/check_spec_coverage.py`
fails if either experiment is listed as the bench for a spec row, or if either
one's `tb.json` `claim` stops starting with `None` (see the next section).

## Spec-row coverage index (T1 item 9)

**Which spec row is addressed by which testbench, resting on which record, run
with which command:** [`sim/spec-coverage.md`](spec-coverage.md), generated
from [`sim/spec-coverage.json`](spec-coverage.json). Read that instead of
opening every directory here.

`klayout-tools/docs/design-evidence-tiers.md` item 9 grades three things no
single campaign owns — **completeness** (a bench for every claimed row, no
claim resting on prose), **cold start** (a documented invocation a third party
can run from `docs/environment-setup.md`), and **pinning** (the PDK revision
and tool versions each bench is claimed against). All three regress *silently*:
adding one more claimed spec row without its bench fails the item while every
individual campaign still looks green. So they are checked mechanically:

```sh
npm run check:spec-coverage      # part of npm run check:ci; no PDK needed
npm run render:spec-coverage     # regenerate sim/spec-coverage.md after editing the JSON
```

What the check enforces (each failure mode has its own unit test in
`sim/tests/test_spec_coverage.py` — a completeness check that cannot be made to
fail proves nothing):

- Every row of `spec/target-spec.md`'s **Target table** is indexed, with a
  status matching what the spec itself says. A newly-added spec row fails until
  it is indexed.
- Every row carrying a claim has **≥ 1 committed bench and ≥ 1 committed
  record**, and for numeric rows at least one of those records must cite
  `spec/target-spec.md` in its own **Claim** field — the index cannot attach a
  record to a row the record does not claim.
- The one class allowed to have no bench (`unbenched`) is allowed **only on a
  DRAFT row**, and only with a stated reason. Ratifying a row therefore
  mechanically obliges a bench for it; `Sample rate` and `Power` are the two
  rows deliberately in that state today, each with its reason recorded.
- Each bench's **cold-start invocation** appears verbatim in the file the index
  says documents it, passes only flags/subcommands its runner actually accepts,
  and names the same script the record's own `Written by` footer names — so the
  documented command cannot drift away from the private one an agent ran.
- Every indexed record **pins** its PDK variant + `open_pdks` commit against
  `sim/pdk.json`, its ngspice major against `sim/toolchain.json`'s floor, and
  carries its DUT netlist SHA-256 (the per-record, xschem-side provenance —
  stage 2's rule that an xschem version difference is a warning while the
  netlist hash is the real pin).
- The two harness proofs above are never counted, and any experiment directory
  that has minted records but appears nowhere in the index is reported as an
  **orphan** — a bench indexed by nothing is the same gap as a row benched by
  nothing.

What the check *cannot* tell you is whether a documented command reaches a
result on **your** machine: `sim/harness/toolchain.py` enforces a hardcoded
120 s ngspice timeout, and the `sar-sequencer-behavioral` transient exceeds it
on a host slower than the one that minted its records (#133). That is a runner
portability gap, not a gap in the evidence.

No spec *value* lives in the checker. Row names and statuses come from
`spec/target-spec.md`, the process-corner list from `sim/pdk.json`, and the
ratified corner row is checked by *shape* (every PDK process corner; three
points on each of the temperature and supply axes) rather than by a hardcoded
−40/27/125 or 1.62/1.8/1.98 — `sim/harness/corners.py`'s own docstring rules
out putting ratified spec numbers in harness code, and this check follows it.

## Directory / naming convention

```
sim/
  <experiment-slug>/                 # e.g. inl-dnl, enob-fft, comparator-noise,
                                     # mc-cdac-mismatch, harness-corner-smoke
    testbench/
      tb.json                        # manifest: netlist fragment, PVT axes,
                                     # measurements, checks
      <fragment>.spice               # SPICE fragment (devices/sources only)
    netlist-snapshots/
      <record-id>.spice              # frozen DUT netlist used for this record
    corners/
      <record-id>/
        <corner-id>.log              # raw ngspice output per PVT point
    mc-draws/
      <record-id>/
        draw_<i>_seed<n>.log         # raw ngspice output per Monte Carlo draw
        negctrl_<i>_seed<n>.log      # ... and per negative-control draw
    records/
      <record-id>.md                 # append-only summary record
```

- **`<experiment-slug>`** — short kebab-case name for *what is being
  verified*, one directory per distinct claim, not per run.
- **`<record-id>`** — `<YYYYMMDD>-<HHMMSS>-<short-git-sha>`, e.g.
  `20260813-143000-9f2a1cd`. Minted by `sim/harness/evidence.py`. The same
  `<record-id>` ties together the netlist snapshot, the raw logs, and the
  summary record for one run.
- **`<corner-id>`** — `<process>_<temp>c_<supply>v`, e.g. `ss_-40c_1.62v`,
  `tt_27c_1.80v`.
- **`testbench/`** is *not* versioned per record; it holds the current
  testbench. If it changes in a way that affects comparability across records,
  say so in the new record's note. (The per-record `netlist-snapshots/` copy
  and the netlist SHA-256 stamped into every record are what make a stale
  comparison detectable.)

### `tb.json` manifest

```jsonc
{
  "name": "<experiment-slug>",
  "description": "...",
  "claim": "spec/<file>.md#<anchor> — ... (or: None — harness self-test)",
  "netlist_fragment": "<fragment>.spice",
  "nominal_supply_v": 1.8,          // stated per testbench, never in harness code
  "supply_tolerance": 0.10,
  "temperatures_c": [-40, 27, 125],
  "process_corners": ["tt", "ss", "ff", "sf", "fs"],
  "measure": { "<name>": "<ngspice expression>" },
  "checks": {
    "<name>": {
      "min": 0.3, "max": 1.2,
      "min_spread_pct_by_axis": { "process": 1.0, "temperature": 3.0 },
      "max_spread_pct_by_axis": { "supply": 0.001 },
      "description": "why this check exists"
    }
  }
}
```

The fragment is a plain SPICE deck fragment (devices and sources only) that
refers to `{vdd_val}` for its supply. The harness prepends the `.lib` corner
include, `.temp`, `.param vdd_val`, and (for Monte Carlo) `.option rndseed`,
and appends the `.control`/`let`/`print` block built from `measure`.

`min_spread_pct_by_axis` is this repo's sharpest tool and deserves a note: it
asserts a measurement *must* move by at least some amount along a given PVT
axis. That is what catches the failure mode a corner runner is most prone to —
silently simulating typical everywhere while printing a plausible-looking
table. `sim/selftest.sh` stage 4 exercises exactly this (see below).

### Corner-grid shape (one-at-a-time, not full factorial)

`sim/run_corners.py` runs a baseline point plus, for each axis in turn, every
other value on that axis with the remaining two axes held at baseline. This is
precisely the set the per-axis sensitivity computation consumes, and a single
ngspice invocation against sky130's combined model library costs ~15–20 s on
the reference toolchain (library load dominates, not the simulation). A record
therefore states 9 points where a full grid would state 45, at no loss of
per-axis signal. A record whose claim genuinely needs corner *interactions*
(e.g. worst-case ss/−40 °C/low-supply simultaneously) must say so and run
those points explicitly — the OAT default is a cost choice, not a statement
that interactions do not exist.

## Summary record format

Each run writes one `records/<record-id>.md`. All records carry the base
fields; records substantiating a particular kind of claim also carry the
matching extension fields.

### Base fields

- **Record ID** — matches the filename and the `netlist-snapshots/` /
  `corners/` / `mc-draws/` subdirectory names.
- **Claim** — which spec parameter/line this record substantiates
  (`spec/<file>.md#<anchor>`), or an explicit "None — harness self-test".
  Until #1 ratifies `spec/target-spec.md`, a claim naming a draft row must say
  `pending #1`; a DRAFT value is never quoted as if settled.
- **Netlist provenance** — `schematic` (`design/...`) or `extracted`
  (post-layout, `layout/...`).
- **Corner matrix run** — the explicit (process, temperature, supply) points
  actually executed, with a count.
- **Statistical convention** — for Monte Carlo records; see below.
- **Result** — per-corner pass/fail plus an overall verdict.
- **Environment** — PDK variant + resolved open_pdks commit, ngspice version,
  harness version, git commit + branch + **dirty flag**, and the DUT netlist's
  **SHA-256**. Written by `sim/harness/evidence.py`; a record produced from a
  dirty tree says so rather than pretending otherwise.
- **Supersedes** — the prior `<record-id>` this record replaces, or `(none)`.

gf180-sar-adc's schema also lists *Timestamp / author* and *Links* as separate
fields. They are not separate fields here because the harness already carries
both structurally and a hand-typed copy could disagree with the machine-written
one: the UTC timestamp is the first two components of the `<record-id>`, the
author is the git commit in **Environment**, and the links are the
`corners/<record-id>/`, `mc-draws/<record-id>/` and
`netlist-snapshots/<record-id>.spice` paths that the same `<record-id>` names
by construction.

#### Subset-corner justification

A record may legitimately run fewer than the full matrix (a mismatch
distribution at nominal PVT only, a bounded sweep to keep runtime tractable).
That is allowed, but the record must **state which corners ran and why the
rest were omitted**. An unexplained subset is not a valid record.

#### Correction-supersession vs distinct-claim

`Supersedes` is only for a record that **replaces** a prior result for the
*same claim* (a correction, or a schematic → extracted re-run). A record
testing a *different* claim about the same DUT leaves `Supersedes` empty, even
when the two are closely related.

## Monte Carlo records

`sim/monte_carlo.py` writes a record that additionally states:

- **Statistical convention** — the mismatch corner used (`<corner>_mm`), the
  **sample count N**, the **base seed** (draws use `seed, seed+1, …,
  seed+N−1`, so the exact draw set is reconstructible), and the fixed PVT
  point the draws were taken at.
- **Distributions** — per measurement: N, mean, stdev, min, max. A
  distribution, not a corner point; ENOB, INL, DNL and offset are statistical
  rows and a single number does not substantiate them.
- **Negative control** — N draws at the *plain* (non-`_mm`) corner with the
  same seed sequence, which must reproduce every measurement **exactly**
  (stdev == 0).

The negative control is the load-bearing part. sky130's per-instance mismatch
is gated by `MC_MM_SWITCH`, entered through the `_mm` `.lib` sections; at a
plain corner the `AGAUSS()` terms inside the device subcircuits are disabled,
so `rndseed` has no effect at all. A nonzero negative-control stdev therefore
means either mismatch leaked into the disabled corner or the measurement is
seed-sensitive for some unrelated reason — either way the accompanying
distribution is not trustworthy and the record is marked FAIL. Conversely a
zero-stdev control alongside a nonzero-stdev `_mm` distribution is direct
evidence that the spread reported is device mismatch and not harness noise.

When ADC statistical rows land, a Monte Carlo record also states:

- **Scope** — `mismatch-only` or `mismatch+process`.
- **Sigma level** — the sigma the pass/fail criterion corresponds to.
- **N justification** — why N is large enough for the sigma claimed.

## Statistical-row Monte Carlo campaigns (issue #29)

Issue #29 applies the Monte Carlo machinery above (proven by `mc-smoke`) to
the three statistical rows T1 item 6 names: ENOB, INL/DNL, and
comparator/ADC offset. Distinct from `mc-smoke` (a harness self-test) and
from issue #28's PVT corner campaigns (which validate the RATIFIED
deterministic rows — `V_REF`/LSB/`N`/CDAC sizing/comparator noise — against
process/temperature/supply, not mismatch): these records combine WITH that
corner evidence rather than substituting for it, per each record's own
"Statistical convention" / "Subset-corner justification" text.

- **`sim/cdac-array-transfer/run_mc.py`** — Monte Carlo DNL/INL campaign.
  Extends #53/#28's deterministic 5-code transfer-curve experiment (same
  directory) with mismatch draws (`tt_mm`) over a larger, programmatically
  generated code set (`sim/cdac-array-transfer/gen_fragment.py`, verified
  byte-for-byte against the hand-authored 5-code fragment by
  `sim/tests/test_cdac_fragment_gen.py`) covering every major-carry
  transition — the textbook worst-DNL location for a binary-weighted CDAC.
  Reports max|DNL| / max|INL| distributions in ratified-LSB units, against
  the target-spec.md's DRAFT (not ratified) `<= 1 LSB` target row,
  informationally.
- **`sim/comparator-decision/run.py offset`** (existing driver, reused) —
  re-run at a CI-justified `N` (see each record's own N-justification
  field, computed by the same relative-standard-error formula
  `cdac-array-transfer/run_mc.py` uses) rather than issue #54's original
  N=16 first-pass. No ratified (or even DRAFT) numeric offset row exists
  in target-spec.md, so this stays a distribution-only characterization
  (no `klt yield` step — see that record for why a limit-less measurement
  cannot feed one).
- **`sim/enob-estimate/run_enob.py`** — a new experiment directory. A
  `behavioral-accelerated` ENOB estimate (sim/README.md's own Linearity/
  Dynamic-test methodology vocabulary) composing quantization noise
  (analytic), comparator input-referred noise (issue #28's ratified corner
  campaign, NOT re-simulated), CDAC-mismatch nonlinearity (this issue's own
  `cdac-array-transfer` Monte Carlo campaign), and kT/C sampling noise
  (analytic) in quadrature via the same `SNR = 6.02·ENOB + 1.76 dB`
  relationship `spec/dr-003-support/calc.py` already uses in the forward
  direction. Explicitly NOT a dynamic-test (FFT) measurement — see the
  script's module docstring for why a full-chip transient FFT campaign
  (needing a top-level testbench that does not exist yet) is out of scope,
  and the record's own "LIMITATIONS" field for what this estimate excludes.

### `klt yield` — machine-checkable yield evidence

Per `klayout-tools/docs/design-evidence-tiers.md` item 6, a statistical
row's machine-checkable evidence is a `klt yield` JSON report: yield
estimate + confidence interval + sample-size verdict + Cpk/sigma-to-spec
against the row's own limits. The records above invoke it directly
(`klt yield <sample-set.json> --format json`), writing the raw JSON report
under `sim/<experiment>/yield-reports/<record-id>.json` alongside a summary
table in the `.md` record. Because ENOB and INL/DNL are still DRAFT (not
ratified) target-spec.md rows, these `klt yield` invocations use the DRAFT
target values as an **informational** limit — explicitly labeled DRAFT
throughout, never presented as a pass/fail against a ratified line, per
`CLAUDE.md`'s "do not invent settled numbers to replace the drafts" rule.
Comparator offset has no numeric row at all (not even DRAFT), so it gets no
`klt yield` step — a limit-less measurement is a `klt yield` input error by
design, not a tool gap.

`klt yield`'s native `klt_yield_native` extension (the Rust statistics core
behind the yield/Cpk math) is not published as a prebuilt wheel — a fresh
`uv tool install klayout-tools@git+...` install (this repo's documented
`klt` install path) hits `the klt_yield_native extension is not installed`
until it is built from a `2AMLogic/klayout-tools` source checkout via
`maturin develop --release` inside `native/yield/` (matching the Python
interpreter `klt`'s own install actually runs on — a `uv tool install`
resolves its own pinned interpreter, which may differ from the system
default; `maturin build --release --interpreter <that interpreter>` plus
`uv pip install --python <that interpreter> <wheel>` handles the mismatch).
This exact packaging gap is already filed and tracked generically at
`2AMLogic/klayout-tools#1061` (closed `COMPLETED`, documents this same
build-from-checkout remediation) per `CLAUDE.md`'s friction protocol — this
record does not re-file it.

## ADC-specific extensions (ported from gf180-sar-adc)

Required only on records substantiating the corresponding kind of claim; kept
verbatim in intent from the ported source so the two ports read alike.

- **Dynamic-test (FFT) metadata** — on any FFT-derived claim (ENOB, SNDR,
  SFDR, THD): N samples (FFT record length); input frequency and the integer
  coherent bin (`f_in = bin · f_s / N`, `bin` coprime to `N`); window (`none`
  for coherent sampling — the preferred method — otherwise the window name and
  why coherent sampling was not used); sampling rate `f_s`.
- **Linearity methodology** — on any INL/DNL record, one of
  `full-<n>-code-ramp`, `reduced-code-set-major-carry`, `code-density`,
  `behavioral-accelerated`, followed by the exact code count / transition list
  / acceleration method used.
- **Noise methodology** — on any noise-budget record: `transient-noise` (with
  seed and a duration justification), `ac-based` (with integration bandwidth),
  or `both` (with how they were reconciled).
- **Characterization-record variant** — records that report *measured values
  under stated conditions* rather than pass/fail against a ratified line
  replace **Result** with **Measured value(s)** (each paired with its corner
  condition) and add **Data provenance** (`model-card-monte-carlo`,
  `foundry-documentation`, `literature-assumption-with-derating`, naming the
  specific source and any derating applied).

## Extracted vs schematic semantics

**Netlist provenance** states `schematic` or `extracted`. A post-layout
extracted re-run of an existing claim lives in the *same* experiment directory
with its own `<record-id>`, `Netlist provenance: extracted`, and a
`Supersedes` field, carrying the schematic-vs-extracted delta in its Result
section. The extracted record **appends alongside** the schematic one; it
never replaces or edits it.

## Append-only rule

`records/*.md` are never edited or deleted after creation, and neither are the
raw logs under `corners/` / `mc-draws/` or the snapshots under
`netlist-snapshots/`. This applies even to typo fixes: the append-only
guarantee is what makes `sim/` usable as an evidence trail, and "just fixing"
a record in place defeats it. Note that `.gitignore` carves `*.log` exceptions
for `sim/*/corners/**` and `sim/*/mc-draws/**` precisely so this raw evidence
is committed rather than swept up by the generic log-ignore rule.

## The aggregated characterization report (issue #30)

`records/*.md` are the append-only evidence trail; `docs/characterization-
report.md` is the **aggregated, generated artifact** that ties every
`spec/target-spec.md` Target-table row (including DRAFT/unratified/
unmeasured rows -- coverage is stated honestly, not just the rows that
pass) to the specific record(s) its verdict rests on, per
`klayout-tools/docs/design-evidence-tiers.md` T1 item 8.

- **Generator**: `sim/report/generate.py`, driven by the row-to-citation
  data in `sim/report/manifest.py`. Every citation's `Record ID`,
  `Overall`/`Statistical convention`/`Measured value(s)`, `Corner matrix
  run`, and `Supersedes` fields are re-extracted from the cited record file
  at generation time rather than hand-transcribed, so the report cannot
  silently drift from what a cited record currently says.
- **Mechanical freshness**: `sim/report/generate.py --check` (wired into
  `npm run check:report`, part of `npm run check:ci`) regenerates the
  report in memory and fails if it differs from the committed
  `docs/characterization-report.md`, if a cited record path no longer
  exists, or if any cited record has been superseded by a sibling record in
  the same `records/` directory (via that sibling's own **Supersedes**
  field) -- see `find_superseding_sibling()`/`check_freshness()` in that
  module.
- **Regenerate after any evidence change**: `python3 sim/report/generate.py
  --write`, then re-run `--check` before committing.
- This report records no operator grant; see its own "No-grant statement"
  section.

## The harness acceptance test (`sim/selftest.sh`)

`sim/selftest.sh` is the harness's own gate, wired into `npm run check:ci`:

| Stage | What it proves | Needs PDK? |
| --- | --- | --- |
| 1/4 | `sim/harness/*` unit tests (`sim/tests/`) | no |
| 2/4 | toolchain + PDK pin match `sim/toolchain.json` | — |
| 3/4 | `harness-corner-smoke` PVT run and `mc-smoke` Monte Carlo run (incl. its negative control) both pass end to end | yes |
| 4/4 | **negative control**: re-running `harness-corner-smoke` with `--sabotage-corners` (the process-corner `.lib` section forced to `tt`, everything else untouched) must **FAIL** its process-axis sensitivity floor | yes |

Stage 4 is the one that matters most. Stages 1–3 can all pass while the corner
runner silently simulates typical everywhere — every number would look
plausible and every downstream record would be worthless. Stage 4 is the check
that a pass means something.

On a machine without ngspice or the pinned PDK, stages 3–4 **skip** (exit 0
with a loud SKIP) so headless CI stays useful; `--require-pdk` turns that skip
into a failure, and `--quick` stops after stage 2. A *drifted* toolchain never
skips — it fails.

Stage 2 distinguishes drift from a warning by asking which tool the evidence
depends on. ngspice below the pinned floor, or a different open_pdks commit,
is **fatal**: every number under `sim/` comes out of ngspice reading the PDK
model library, so those make records incomparable. A differing **xschem**
version is a **warning**: xschem only turns a schematic into a netlist, and
each record already pins the exact netlist it ran by SHA-256, so the drift is
reported and recorded without blocking a PVT run.

Runtime: the default run is 17 ngspice invocations, ~5 minutes measured on the
reference toolchain and dominated by sky130 model-library load (~15–20 s per
invocation, largely independent of the circuit). `--full` runs the complete
corner grid and a larger Monte Carlo N and is meant as a deliberate periodic
deeper pass. On a runner without ngspice or the PDK it costs seconds.

## Bootstrap smoke test

`sim/smoke_test.spice` and `sim/smoke_test.ngspice.out` are the committed
output of the one-off xschem → ngspice bootstrap described in
`docs/environment-setup.md` §4 (netlisted from `design/smoke_test.sch`, a
throwaway resistor divider with no design content). They are kept as the
first, simplest proof that this machine's toolchain resolves sky130 models at
all — the same artifacts `2AMLogic/sky130-bandgap` commits for the same
reason. The generated netlist carries the absolute PDK path of the machine
that produced it; that is a property of xschem's netlister and is exactly the
provenance detail the file is here to record.

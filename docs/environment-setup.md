# Environment setup

Bootstrap steps for the open-source analog flow used by this repo: xschem
(schematic capture / netlisting) + ngspice (simulation) against the sky130
PDK (fetched/managed via [ciel](https://github.com/fossi-foundation/ciel)).

This doc is meant to be followed verbatim from a fresh shell on a machine
that already has the xschem/ngspice/ciel binaries installed (see
"Toolchain versions" below for what a from-scratch install looks like).
klayout-tools (`klt`) layout-flow setup is covered separately in
`layout/README.md` — this doc is the schematic/sim bootstrap only.

**Provenance**: this document is adapted from
`2AMLogic/sky130-bandgap`'s `docs/environment-setup.md`
(commit `1f04e8524cc2d8c2c7154773749b1b2d3be2ce64`), per `CLAUDE.md`'s
"Harness bootstrap" instruction to copy the sky130 flow pattern from that
repo rather than reinvent it. Toolchain versions, the PDK pin, and the repo
name below are re-recorded against *this* repo's own install rather than
copied — the mechanism is what's ported, not the numbers.

## Toolchain versions (recorded 2026-08-13)

| Tool | Version | Install path |
|---|---|---|
| xschem | `XSCHEM V3.4.7` | `/opt/homebrew/bin/xschem` (Homebrew) |
| ngspice | `ngspice-47` | `/opt/homebrew/bin/ngspice` (Homebrew) |
| ciel | `2.6.1` | `pip`/`pipx`-installed (or `uvx --from "ciel==2.6.1" ciel`) |
| python3 | `3.14.6` | system / Homebrew |

`sim/toolchain.json` is the machine-checked pin (floors, not exact matches
except where noted) — `sim/harness/toolchain.py` / `sim/run_corners.py
--check-env` verify the installed toolchain against it before any PVT point
is simulated. Verify by hand first.

ciel is **not** machine-checked by `sim/toolchain.json`. The pin that is
authoritative for CI is `pip install "ciel==2.6.1"` in the `pdk-smoke` job of
`.github/workflows/ci.yml`; the table above records the same version. Bump
both together. (The PDK *contents* are machine-checked: the harness reads the
`SOURCES` file at the root of the resolved variant tree and fails on an
open_pdks revision other than `sim/pdk.json`'s.)

```sh
xschem -v         # expect: XSCHEM V3.4.7 ...
ngspice --version  # expect: ngspice-47 (>= ngspice-46 floor) ...
ciel --version    # expect: Ciel v2.6.1 ...
```

If any are absent, install via Homebrew (`brew install xschem ngspice`) or
pip/pipx (`pipx install ciel==2.6.1`) — this repo does not pin a from-scratch
install recipe beyond that; see the sibling repos'
(`2AMLogic/sky130-bandgap`, `2AMLogic/gf180-bandgap#18`) bootstrap notes if
a from-scratch build is needed on a machine with no Homebrew formula
available.

## 1. Verify xschem works headlessly

```sh
xschem -n -q -x /opt/homebrew/share/doc/xschem/examples/nand2.sch -o /tmp/xschem_check
```

This should exit 0 and write a `.spice` netlist to `/tmp/xschem_check` with
no errors printed — a bare sanity check that doesn't need any PDK wiring at
all.

## 2. Fetch + enable the sky130 PDK via ciel

```sh
ciel ls-remote --pdk-family sky130   # lists open_pdks build commits, newest first
ciel enable --pdk-family sky130 -l sky130_fd_pr f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7
```

(`sim/pdk.json`'s `install_command` is the machine-readable form of the
second line. Omit `-l` to install ciel's default library set, which also
includes the `sky130_fd_sc_hd` standard cells the `layout/` flows use. The
PDK root defaults to `~/.ciel`.)

**Recorded PDK version (pinned, not "latest"):**

- PDK family: `sky130`
- open_pdks build commit: `f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`
- Chosen because: fleet decision of 2026-10-15 (2AMLogic/sky130-sar-adc#668)
  moved every 2AM Logic sky130 canary from volare to ciel at this commit, so
  PVT/model provenance stays consistent across the workspace. The previous
  pin, `c6d73a35f524070e85faff4a6a9eef49553ebc2b` (volare, `~/.volare`), is
  what the existing records under `sim/` and `layout/` were minted against;
  they are evidence and are re-qualified separately (#670). A leftover
  `~/.volare` at that commit is **not** usable: the harness reports it as a
  pin mismatch.

After `ciel enable`, `~/.ciel` contains the PDK variant trees:

```sh
ls -la ~/.ciel | grep sky130
cat ~/.ciel/sky130A/SOURCES    # expect: open_pdks f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7
```

This repo standardizes on the **`sky130A`** variant (matching
`sky130-bandgap` and `sim/pdk.json` below).

## 3. Environment convention: `PDK_ROOT` / `PDK`

Export these two variables in any shell before running xschem/ngspice
against sky130 in this repo:

```sh
export PDK_ROOT="$HOME/.ciel"   # -> the ciel-managed PDK store root
export PDK=sky130A
```

The `layout/*/bin/run-*.sh` flow scripts export `PDK=sky130A` themselves, so
klt cannot resolve a sibling PDK from a shell that lacks it.

Verify:

```sh
echo "$PDK_ROOT"          # e.g. /Users/<you>/.ciel
echo "$PDK_ROOT/$PDK"     # must exist and be a real (symlinked) directory
ls "$PDK_ROOT/$PDK/libs.tech/ngspice/sky130.lib.spice"   # model include file (via libs.tech/combined, see below)
```

`sim/env.sh` (`source sim/env.sh`) exports the same two variables by asking
`sim/run_corners.py --print-env` to resolve them (honoring `sim/pdk.json`'s
default and any `$PDK_ROOT`/`$PDK` already set), so an interactive
xschem/ngspice session sees exactly the PDK the harness itself uses. They
must be set before invoking `xschem` with
`--rcfile "$PDK_ROOT/$PDK/libs.tech/xschem/xschemrc"` (below, or via this
repo's own `sim/xschemrc`, which sources the PDK's own), since that rcfile
reads `$env(PDK_ROOT)` / `$env(PDK)` to resolve `$::SKYWATER_MODELS`.

## 4. Smoke test: xschem netlist -> ngspice run against sky130 models

`design/smoke_test.sch` is a throwaway circuit — a 1:1 resistor divider
built from two `sky130_fd_pr__res_generic_po` primitives across a fixed
1.8 V source — used only to prove the toolchain end-to-end. It carries no
SAR ADC design content, spec values, or measurement data.

```sh
export PDK_ROOT="$HOME/.ciel"
export PDK=sky130A

# 1. Netlist the schematic with xschem (headless, no X server needed),
#    using this repo's own sim/xschemrc (which sources the PDK's xschemrc
#    and adds the repo root to the symbol search path).
xschem -x -n -s -q --rcfile sim/xschemrc -o sim design/smoke_test.sch
# -> writes sim/smoke_test.spice

# 2. Run the netlist through ngspice (operating-point analysis)
ngspice -b sim/smoke_test.spice | tee sim/smoke_test.ngspice.out
```

Expected result: the run completes with exit code 0, resolves
`.lib $::SKYWATER_MODELS/sky130.lib.spice tt` to an absolute path under
`$PDK_ROOT/$PDK/libs.tech/combined/`, and prints an operating-point node
voltage table (`vdd`, `net1`) plus resistor device parameters — no
`error`/`warning` lines. `sim/smoke_test.spice` (the netlist) and
`sim/smoke_test.ngspice.out` (the ngspice run output) are committed as
append-only evidence per `CLAUDE.md`.

## 5. Layout flow (klt / DRC / LVS)

Covered in `layout/README.md`: `klt` install pin, the sky130 DRC/LVS decks
it ships, and the trivial-cell proof (`layout/bin/run-trivial-cell-flow.sh`)
that DRC and LVS both catch injected defects, not just pass on a clean
cell.

## 6. PVT corner runner and Monte-Carlo runner

Covered in `sim/README.md`: the evidence-record convention, and
`sim/run_corners.py` / `sim/monte_carlo.py`, the two harness entry points
this repo's ADC testbenches will run against once a design exists (issue
#2's own self-test runs them against harness-proof circuits, not the ADC —
see `sim/README.md` "Harness self-test experiments").

### 6a. Reproducing a specific spec row's evidence

Sections 1–3 above are the whole one-time bootstrap. From there, the
**per-bench cold-start invocation** for every claimed `spec/target-spec.md`
row — which testbench covers it, which record it rests on, and the exact
command that mints that record — is `sim/spec-coverage.md`:

```sh
source sim/env.sh
python3 sim/run_corners.py --check-env   # exit 3 = tools/PDK missing, 1 = pin drifted

# then the row's own command from sim/spec-coverage.md, e.g.
python3 sim/comparator-decision/run.py noise-corners --record
```

Those commands are the ones agents and the evidence records themselves
actually use — `sim/check_spec_coverage.py` (run by `npm run check:ci`)
fails if a documented invocation drifts from the one a record was minted
with, or if a claimed spec row has no committed testbench at all.

## 7. Confirm the whole bootstrap in one command

```sh
sim/selftest.sh                # the harness acceptance test (a few minutes)
sim/selftest.sh --quick        # unit tests + environment check only, no ngspice
sim/selftest.sh --require-pdk  # fail rather than skip if ngspice/the PDK are missing

npm run check:ci               # lint + unit tests + spec-row coverage + sim/selftest.sh
npm run check:spec-coverage    # spec row -> testbench -> record index only (no PDK needed)
npm run check:layout           # the klt DRC/LVS trivial-cell proof (layout/README.md)
```

`sim/selftest.sh` is the acceptance test for everything in sections 2–6: it
runs the harness unit tests, checks the installed toolchain against
`sim/toolchain.json`, runs an end-to-end PVT sweep and a Monte-Carlo sweep,
and then — the part that makes the rest mean anything — re-runs the PVT sweep
with the process corner deliberately forced to `tt` and requires that run to
**fail**. On a machine where ngspice or the pinned PDK are missing it skips
the simulation stages with a loud SKIP and exits 0, so `check:ci` stays useful
in headless CI; a *drifted* pinned toolchain is never skipped, it fails.

## Troubleshooting

- **`SKYWATER_MODELS: unable to resolve variable`** / `.lib` path is
  literally `$::SKYWATER_MODELS/...` in the emitted netlist (not expanded
  to a real path): the `code.sym` block emitting the `.lib` line needs
  `format="tcleval( @value )"` so xschem evaluates the Tcl variable at
  netlist time — see `design/smoke_test.sch` for the working pattern.
- **`Warning: PDK_ROOT environment variable is set but path not found`**
  (printed by the PDK's own `xschemrc`): `$PDK_ROOT`/`$PDK` aren't exported
  in the shell running `xschem`, or `ciel enable` hasn't been run for the
  recorded hash above.
- **xschem opens a GUI window instead of running headless**: pass `-x` (no
  X) in addition to `-n -q`.
- **`sim/run_corners.py --check-env` exits 1 (not 3)**: a pinned tool
  *drifted* (e.g. an older ngspice than `sim/toolchain.json`'s floor, or a
  different open_pdks commit) — this is a real problem, not "PDK missing";
  see that file's `_comment` block for the floor-vs-exact-match rules per
  tool. Note that an xschem version difference is reported as a **warning**
  and does not fail the check: PVT/MC evidence is ngspice-level and every
  record pins the netlist it ran by SHA-256.
- **Debian/Ubuntu's packaged ngspice is too old.** `apt install ngspice` on
  Ubuntu 24.04 gives `ngspice-42`, below this repo's floor, so `--check-env`
  will exit 1 there. Build from source (the CI job in
  `.github/workflows/ci.yml` does exactly this and is a working recipe), or
  use a distribution that ships a new enough build — Homebrew's `ngspice`
  formula is current. Do **not** lower the floor in `sim/toolchain.json` to
  make a local install pass: the floor is what makes the records in `sim/`
  comparable with each other.

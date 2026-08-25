# layout/ — klt DRC/LVS flow (sky130)

Layout work for this block is done headlessly with
[`klayout-tools`](https://github.com/2AMLogic/klayout-tools) (`klt`) against
the same pinned sky130A PDK the simulation harness uses (`sim/pdk.json`).

`trivial-cell/` below is the **proof that the flow works and that its
verdicts are falsifiable** — the gating prerequisite for every later layout
claim (issue #2). `sar-sequencer/` is the first real SAR ADC sub-block layout
(issue #102, digital standard-cell logic via `klt place-and-route` rather
than the full-custom `klt draw` flow — see that directory's own README for
the flow choice and its current DRC-clean/LVS-blocked status).
`cdac-array/` is the differential CDAC array (issue #100): full-custom,
generator-drawn, DRC-clean and LVS-clean against `design/cdac/*.sch`, and
the block's matching-critical sub-block — see that directory's own README
for the common-centroid/unit-element strategy and the four extra verdicts
its flow asserts *because* DRC and LVS say nothing about matching.
`comparator/` is the full-custom analog counterpart (issue #101, DRC-clean
and LVS-clean): `klt gen`'s matched-device generators for the transistors,
a hand-written floorplan/router emitted through `klt draw` for every wire,
and `klt gen-compose` used as a placer only — see that directory's own README
for the flow choice, the matching strategy, and its six verdicts.
`sampling-frontend-wells/` is the sampling front end's **n-well isolation
composition** (issue #122, DRC-clean and LVS-clean): the sub-block's nine
PFETs partitioned into three physically separate, individually tapped n-well
islands, because `design/sampling_frontend.sch`'s DR-004 requires `Sa`/`Se`
to tie their PFET body to `BOOST_P`/`BOOST_N` rather than VDD — see
`spec/decision-records/DR-007-sampling-frontend-nwell-domains.md` for the
binding rule and that directory's own README for the recipe, its eleven
verdicts, and the n-well DRC gap it works around.

## Install

```sh
layout/bin/setup-venv.sh          # creates layout/.venv with the pinned klt
layout/bin/setup-venv.sh --force  # reinstall (after bumping requirements.txt)
```

`layout/.venv/` is git-ignored; `layout/requirements.txt` is the pin
(`klayout-tools==0.3.0` from PyPI — see that file for why a PyPI release pin
rather than the git-commit pin `2AMLogic/sky130-bandgap` had to use; the
0.2.0 → 0.3.0 bump came with issue #100, whose MiM-cap array needs the
met2–met5 / via2–via4 connectivity 0.2.0's sky130 extraction deck did not
have, and carried a dummy-device-suppression fix that forced the
trivial-cell LVS references to be re-derived — issue #104). `klt`
brings its own KLayout wheel, so no system KLayout install is required. The
PDK itself comes from `volare` — see `docs/environment-setup.md`.

## The trivial-cell proof

```sh
layout/bin/run-trivial-cell-flow.sh    # ~1 minute; exit 0 iff all six verdicts hold
cat layout/trivial-cell/reports/$(cat layout/trivial-cell/reports/LATEST)/record.md
```

The flow generates a trivial known-good cell (`klt gen mos_array`, generator
defaults: a 2×2 NMOS array with one dummy column per side) and asserts six
verdicts, three positive and three negative:

| # | Verdict | Why it is here |
| --- | --- | --- |
| 1 | `klt drc` reports **clean** on the generated cell | the deck runs and the generator's output is legal |
| 2 | `klt lvs` reports **match** against `trivial-cell/reference.spice` | extraction + comparison round-trips |
| 3 | `klt lvs` reports **mismatch** against `reference.broken-device.spice` | LVS notices a *device-parameter-only* corruption (W changed, connectivity untouched) |
| 4 | `klt lvs` reports **mismatch** against `reference.broken-topology.spice` | LVS notices a *topology-only* corruption (two drains shorted, parameters untouched) |
| 5 | `klt draw` writes `drc_violation_fixture.gds` | the negative-control fixture is produced by the tool itself, not checked in as an opaque binary |
| 6 | `klt drc` reports **violations**, naming `diff.width.1`, on that fixture | the DRC deck can *fail* — "clean" in verdict 1 means something |

Verdicts 3–4 are two *independent* corruption classes on purpose: an LVS
comparison that only checked connectivity would pass verdict 3, and one that
only compared device parameters would pass verdict 4. Verdicts 5–6 are this
repo's addition over `2AMLogic/sky130-bandgap`'s flow, which proves DRC clean
on a good cell but never shows the deck flagging anything — a deck that
matched no rules at all would look identical from the outside. `klt draw`
writes geometry verbatim with no rule checking, which is exactly what a DRC
negative control needs; the fixture is a single `diff.drawing` rectangle
2.0 × 0.05 µm, narrower than sky130's 0.15 µm minimum diff width (see
`layout/bin/drc_violation_fixture.json`).

The runner asserts every verdict from the `klt` **JSON envelopes**, not from
process exit status. `klt` does distinguish the two cases by exit code (3 =
"ran fine, verdict was bad"; 1 = "did not run"), but exit 3 says only that
*something* was flagged, whereas the envelope names the rule that fired —
which is what verdict 6 has to prove.

## Files

```
layout/
  requirements.txt                 # pinned klt
  bin/
    setup-venv.sh                  # create/refresh layout/.venv
    run-trivial-cell-flow.sh       # the six-verdict flow
    render-record.py               # renders record.md, asserts the verdicts
    drc_violation_fixture.json     # `klt draw` params for the illegal fixture
  trivial-cell/
    reference.spice                # known-good LVS reference (4 M-cards; see header)
    reference.broken-device.spice  # negative control: device-parameter corruption
    reference.broken-topology.spice# negative control: topology corruption
    reports/
      LATEST                       # record-id of the most recent run
      <record-id>/                 # append-only: gen/drc/extract/lvs/draw JSON,
                                   # the GDS, the extracted netlist, report.md,
                                   # record.md
  cdac-array/                      # differential CDAC array (issue #100)
  comparator/                      # dynamic comparator (issue #101)
  sampling-frontend-wells/         # sampling front end n-well isolation (issue #122)
  sar-sequencer/                   # SAR logic/sequencer (issue #102)
```

## Records are append-only

`layout/trivial-cell/reports/<record-id>/` follows the same rule as `sim/`
(see `sim/README.md`): a re-run mints a new `<record-id>`
(`<YYYYMMDD>-<HHMMSS>-<short-git-sha>`, UTC) and never edits an existing
report directory. `record.md` stamps the `klt` version, the KLayout engine
version, the resolved PDK variant + open_pdks commit, and the repo commit with
its dirty flag.

Two honest caveats about the bootstrap record committed with issue #2:

- It was minted from a **dirty** working tree — by construction, since the
  flow writes its own report files into the repo before `record.md` is
  rendered, and the harness itself was not yet committed when it first ran.
  The record says so rather than hiding it.
- This flow does **not** hard-enforce the PDK pin the way
  `sim/run_corners.py --check-env` does; `record.md` prints the resolved
  open_pdks commit so a mismatch against `sim/pdk.json` is visible as a
  reproducibility note.

## Provenance

Ported from `2AMLogic/sky130-bandgap`'s `layout/` (commit
`1f04e8524cc2d8c2c7154773749b1b2d3be2ce64`) per `CLAUDE.md`'s "Harness
bootstrap" instruction: `setup-venv.sh` and `requirements.txt`'s
pin-and-document-why discipline are near-verbatim; `run-trivial-cell-flow.sh`
and `render-record.py` follow its structure with the DRC negative control
(verdicts 5–6) added, as issue #2 requires. The LVS reference netlists were
re-derived against *this* repo's pinned `klt` version rather than copied — see
`trivial-cell/reference.spice`'s header for the full history: all three
references (`reference.spice` and both negative controls) carried 8 M-cards on
the 0.2.0 pin, which could not tell a generated dummy MOS from a real one, and
carry 4 on the current 0.3.0 pin, which can — one M-card per *real* unit
device, the generator's physical-only dummy columns having no schematic
counterpart.

Per `CLAUDE.md`'s friction protocol, any awkwardness, gap, or wrong behaviour
found in `klt` while doing layout work here is filed **generically** at
`2AMLogic/klayout-tools` — tool gap, no design detail, since that tracker is
public and this repo is not.

# `klt erc` supply record `20261021-104830-ddc1d72` — T1 item 11 re-run under open_pdks f6eeac7 (issue #708)

**Verdict: `erc_status: "clean"`, `erc_finding_count: 0`** (`run-erc.sh`: "T1 item 11
verdict: MET"). This is a re-run of the same graded spec as
`20261018-005757-5d07fe65` (`erc-supply-spec.graded.json` hash identical,
`sha256:47f37718…9b6`) against the current top-level assembly, minted so the
ERC evidence carries the `f6eeac7` pin (#669, #670 split into #708). It does
**not** change `signoff/block-manifest.json` or `signoff/t1-report.json`; it
only advances `erc-reports/LATEST`.

## What changed since `20261018-005757-5d07fe65`

| | `20261018-005757-5d07fe65` | this record |
|---|---|---|
| Graded layout | `reports/20261001-211249-1ca34e6/sar_adc_top.gds`, `sha256:9d7c1a4c…916d14b` | `reports/20261021-104809-ddc1d72/sar_adc_top.gds`, `sha256:a2b58035…c4a93` |
| open_pdks | `c6d73a3` (volare) | `f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7` (ciel) |
| `klt` / KLayout | 0.7.0 / 0.30.12 | 0.7.0 / 0.30.12 (controlled) |
| Spec as graded | `sha256:47f37718…` | `sha256:47f37718…` (controlled) |
| `erc_status` / findings | clean / 0 | clean / 0 |
| `gate_count` | 257 | 257 |

**The graded GDS is not the same file as the earlier record's.** The earlier
ERC graded `20261001-211249-1ca34e6`; this one grades the current
`sar-adc-top/reports/LATEST` composition (the same bytes, `a2b58035…`, as the
`c6d73a3`-era `20261003-041400-571f036` DRC/LVS record). So the old→new
comparison here changes both the PDK pin and the layout; the observation is
"clean before, clean now", not an isolated PDK effect. `klt erc --pdk sky130
--deck sky130` uses the built-in deck (`pdk.source: "built-in"`), and the deck
hash is the same in both records (`sha256:f8f2c3f4…70ba`), so the `f6eeac7`
install is recorded by `run-erc.sh`'s resolution line, not read by the deck.

## Coverage — unchanged caveat

`erc_coverage.skipped`, `inapplicable` and `checked_by_assertion` are 0.
`checked_by_well_assertion` is **not empty** (3 entries):

```
erc.missing_tie:["nwell_tap_boost_n"], ["nwell_tap_boost_p"], ["nwell_tap_vdd"]
```

Those select wells by caller-named coordinates, not a drawn marker (see
`20261018-005757-5d07fe65/record.md` and `spec/decision-records/DR-024-boost-well-tie-declaration.md`).
Nothing was re-derived here: the boxes are the spec's, and I did not re-check
that they still sit on the right wells in the new GDS beyond `klt erc` finding a
tap tied to the named net inside each.

`erc.stderr` carries the same single warning as the earlier record: the `met3`
stackup entry declares label layer 70/5 but the stream carries no text on it.

## Provenance

| | |
|---|---|
| Invocation | `layout/sar-adc-top/bin/run-erc.sh` (graded `reports/LATEST` at the time, `20261021-104809-ddc1d72`; single local run) |
| pdk | `sky130A (open_pdks f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7)` (printed by `run-erc.sh`) |
| Venv | `layout/.venv-erc` via `layout/bin/setup-erc-venv.sh`, `layout/erc-requirements.txt` (`klayout-tools==0.7.0`) |
| Committed spec file | `layout/sar-adc-top/erc-supply-spec.json`, `sha256:a5eded0f…fbdfb8b` |

## What this record does NOT say

- Not a re-measurement of the negative control (a wrong `net` on
  `nwell_tap_boost_p`) from the earlier record; it was not re-run.
- Not the p-substrate half, which stays ungraded.
- Not that the layout is unchanged: see the table above.

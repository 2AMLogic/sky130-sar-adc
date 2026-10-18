# `klt erc` supply record `20261018-005757-5d07fe65` — T1 item 11 (Power delivery, structural), BOOST_P / BOOST_N well ties declared

**Verdict: `erc_status: "clean"`, `erc_finding_count: 0`.** The earlier record
`20261017-225729-4bb47e17` reported 2 `erc.missing_tie` findings, the two
n-wells issue #684 tracks. `run-erc.sh` prints "T1 item 11 verdict: MET" for
this record. This record does **not** change `signoff/block-manifest.json` or
`signoff/t1-report.json`; see "What this record does NOT say".

## What was found, and what changed in the spec

The two wells, (63.825, 85.850)–(70.565, 90.620) µm and (90.105, 85.850)–(97.095,
90.620) µm, are not missing a tap. The probe record
`probe-reports/20261017-201500-9522693e/summary.md` found one `65/44` tap in
each, on a licon1 / li1 / mcon / met1 stack, and traced the west tap to a net
carrying text `BOOST_P` and the east tap to `BOOST_N` (text on 69/5). That is the
DR-007 well assignment (boosted-side PFET bodies on `BOOST_P` / `BOOST_N`). The
flags came from the spec grading them against `VDD`, which they are not tied to.

Spec change, `layout/sar-adc-top/erc-supply-spec.json`, recorded in
`spec/decision-records/DR-024-boost-well-tie-declaration.md`:

- two new `ties[]` entries, `nwell_tap_boost_p` (net `BOOST_P`) and
  `nwell_tap_boost_n` (net `BOOST_N`), each selecting its well with
  `well_requires_boxes` set to that well's tap box;
- `nwell_tap_vdd` gains `well_excludes_boxes` naming the same two tap boxes, so
  each of the two wells is graded once, against its own net.

No layout change, no `stackup`, `vias` or `nets[]` change, and no spec row
changed. Nothing was waived: the tap, its reach to `li1`, and the net it sits on
are still measured by `klt erc`.

## Coverage — read this before relying on the verdict

`erc_coverage.skipped`, `inapplicable` and `checked_by_assertion` are empty, and
`checked` contains `erc.missing_tie` for `nwell_tap_vdd`, `nwell_tap_vpwr`,
`nwell_tap_boost_p` and `nwell_tap_boost_n`. But
`checked_by_well_assertion` is **not empty**:

```
erc.missing_tie:["nwell_tap_boost_n"], ["nwell_tap_boost_p"], ["nwell_tap_vdd"]
```

Those three entries select wells by caller-named coordinates, not by a drawn
marker. So for them the verdict rests on my word about **which** wells belong to
each class; klt still measures the tap and its net. I looked for a drawn marker
instead and found none: of the 26 merged n-well shapes in the graded GDS, no
layer interacts with these two wells and not with others except `65/20` and
`66/20`, and each of those also interacts with 17 of the 26 wells. The
`nwell_tap_vpwr` entry is still selected by the drawn `81/4` marker and is not
in the assertion bucket.

Consequence of the box selection: a *new* n-well drawn later is graded against
`VDD` (or `VPWR` inside 81/4), not against a BOOST net, unless the boxes are
extended. The boxes are the two taps' own bounding boxes
([64.225, 86.450, 64.825, 87.650] and [90.505, 86.450, 91.105, 87.650] µm); they
interact with one n-well each.

## Provenance and uncontrolled differences

| | |
|---|---|
| Graded layout | `layout/sar-adc-top/reports/20261001-211249-1ca34e6/sar_adc_top.gds`, `sha256:9d7c1a4c…916d14b` — identical to the earlier record's |
| Spec as committed | `layout/sar-adc-top/erc-supply-spec.json`, `sha256:d149536b4df4c2c1547b7a13f4ab1b33d43b451fd3ee58aa7425b226074c43a3` |
| Spec as graded | `erc-supply-spec.graded.json` in this directory, `sha256:47f377188e612ab2279dbe5ce81efb2089c01bfe306faf0a195fd91509d9b3a6` (comment-stripped; the hash `provenance.spec.content_hash` carries) |
| Tool | `klt` **0.7.0** / KLayout 0.30.12, same as `20261017-225729-4bb47e17`. Tool version is therefore **controlled** against that record; the only input that differs is the spec |
| Venv | built for this run with `uv venv` + `uv pip install -r layout/erc-requirements.txt` (the host has no `python3-venv`, so `setup-erc-venv.sh` could not run); same pin file |
| PDK | `klt erc --pdk sky130 --deck sky130` (built-in); open_pdks f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7 resolved by `run-erc.sh` |
| Invocation | `layout/sar-adc-top/bin/run-erc.sh layout/sar-adc-top/reports/20261001-211249-1ca34e6/sar_adc_top.gds` (single local run, one `klt erc` process, no grid) |

`erc.stderr` carries one warning, unchanged from `20261017-225729-4bb47e17`: the
`met3` stackup entry declares label layer 70/5 but the stream carries no text on
it. No finding refers to `met3`.

## What this record does NOT say

- **Not a layout fix and not a defect finding.** The wells were never missing
  taps. Whether `BOOST_P` / `BOOST_N` is the *right* tie for those bodies is
  DR-007's decision, not this record's.
- **Not that the probe's net trace equals klt's.** The trace was a plain
  layer-connectivity model run on host KLayout 0.28.16 (see the probe summary's
  limits). What this record adds is that `klt erc` 0.7.0 itself finds a tap
  inside each well connected to `BOOST_P` / `BOOST_N` when graded against those
  nets; it did not check that each well holds exactly the PFETs DR-007 assigns.
- **Not more than one negative control.** Re-running `klt erc` 0.7.0 on the
  same GDS with a copy of the graded spec in which only `nwell_tap_boost_p`'s
  `net` was changed to `BOOST_N` (copy not committed; one local run) gave
  `erc_status: "violations"`, 1 finding: `erc.missing_tie`, net `BOOST_N`, bbox
  (63.825, 85.850)–(70.565, 90.620) µm, the west well. So the tap-to-net check
  does bite on a wrong net for one of the two wells; the east well and the
  `nwell_tap_vdd` exclusion were not separately perturbed.
- **Not that item 11 changed in the manifest.** `signoff/block-manifest.json`
  still cites `20261017-193237-9522693e` and `signoff/t1-report.json` was not
  re-rendered; this record only moves `erc-reports/LATEST`.
- **Not the p-substrate half**, which stays ungraded (see
  `erc-reports/20261017-193237-9522693e/record.md`).

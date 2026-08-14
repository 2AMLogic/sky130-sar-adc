# Layout DRC/LVS record: 20260814-020537-98d9186

Trivial-cell proof of the `klt`-driven sky130 DRC/LVS flow (issue #2) -- **not** SAR ADC layout, which is a later issue's scope, and not a spec claim of any kind. This record substantiates exactly one thing: that the flow runs headlessly end to end *and* that both of its verdicts are falsifiable on this toolchain.

## Overall verdict: PASS

- [x] DRC on the generated known-good cell is clean
- [x] LVS matches the known-good reference
- [x] LVS negative control (device-parameter corruption) reports mismatch
- [x] LVS negative control (topology corruption) reports mismatch
- [x] the deliberately-illegal DRC fixture was written
- [x] DRC negative control flags the injected `diff.width.1` violation

## Flow

1. `klt gen mos_array --pdk sky130A --cell-name trivial_mos_array` -- generator defaults (2x2 array, 1 dummy column per side, nfet, no well drawn).
2. `klt drc trivial_mos_array.gds --deck sky130` -- must be clean.
3. `klt extract trivial_mos_array.gds --deck sky130 --top trivial_mos_array`
4. `klt lvs` against `reference.spice` (known-good) and two negative-control references (`reference.broken-device.spice`, `reference.broken-topology.spice`).
5. `klt draw --params drc_violation_fixture.json` -- writes a known-illegal shape verbatim, no rule checking.
6. `klt drc drc_violation_fixture.gds --deck sky130` -- must NOT be clean, and must name `diff.width.1`.

## Cell

- Generator: `mos_array` (`klt gen --list` for the full params schema)
- `device_count` (real, non-dummy): 4
- bbox (um): {'x0': -1.52, 'y0': 0.0, 'x1': 4.16, 'y1': 2.08}
- `matched_group_id`: mos_array:2x2:common_centroid

## Results

| Stage | Status | Detail |
| --- | --- | --- |
| DRC (known-good cell) | clean | violation_count=0 |
| Extract | extracted | device_count=8, net_count=25, pin_count=1 |
| LVS (good reference) | match | mismatch_count=12, category_counts={'device.body_unverified': 1, 'topology': 11} |
| LVS negative control: device parameter | mismatch | mismatch_count=62, category_counts={'device.body_unverified': 1, 'device.unmatched': 9, 'net.unmatched': 50, 'topology': 2} |
| LVS negative control: topology (shorted net) | mismatch | mismatch_count=60, category_counts={'device.body_unverified': 1, 'device.unmatched': 8, 'net.unmatched': 49, 'topology': 2} |
| DRC negative control: injected violation | violations | violation_count=1, rules=['diff.width.1'] |

The good-reference LVS run's `mismatch_count` (12) is nonzero while `status` is `"match"` -- all 12 entries are `severity: "warning"` (0 at `severity: "error"`; see `lvs.json`), and are documented, expected quirks of this minimal, fully symmetric cell:
- `device.body_unverified` (x1): the curated sky130 extraction deck draws no distinct NMOS substrate/tap layer, so every body terminal compares against a deck-synthesized `vsubs` net rather than a real schematic net (documented in `klt extract`'s own "Coverage" docs).
- `topology`, ambiguous net pairing (x9): the array's unit devices are electrically interchangeable (no two devices share a net that would anchor a unique pairing), so `NetlistComparer` resolves the correspondence structurally rather than uniquely -- expected for a fully symmetric matched array, not a defect.
- `topology`, unused device class on both sides (x2): device classes the sky130 deck can recognise (e.g. `pfet`, `pnp`, `resistor`) that this cell draws none of -- not a real mismatch.

## Provenance

- Record ID: `20260814-020537-98d9186`
- `klt` version: `klt 0.2.0` (pinned, see `layout/requirements.txt`)
- KLayout engine version: `0.30.10`
- PDK: `sky130A`, `open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b`
- PDK pin cross-check: compare `version` above against `sim/pdk.json`'s `open_pdks_commit`. This flow does not itself enforce the pin (unlike `sim/run_corners.py --check-env`), so a mismatch here is a manual reproducibility note, not a hard failure.
- Repo state: `98d9186a23a127dcfa3e3c967a7e3d46f002b35f` on `feature/issue-2` (dirty)

Append-only, same rule as `sim/`: a re-run mints a new record id under `layout/trivial-cell/reports/` rather than editing this one.

## Links

- [`gen.json`](gen.json), [`trivial_mos_array.gds`](trivial_mos_array.gds)
- [`drc.json`](drc.json)
- [`extract.json`](extract.json), [`trivial_mos_array.extract.spice`](trivial_mos_array.extract.spice)
- [`lvs.request.json`](lvs.request.json), [`lvs.json`](lvs.json), [`reference.spice`](reference.spice)
- [`lvs.broken-device.request.json`](lvs.broken-device.request.json), [`lvs.broken-device.json`](lvs.broken-device.json), [`reference.broken-device.spice`](reference.broken-device.spice)
- [`lvs.broken-topology.request.json`](lvs.broken-topology.request.json), [`lvs.broken-topology.json`](lvs.broken-topology.json), [`reference.broken-topology.spice`](reference.broken-topology.spice)
- [`drc_violation_fixture.json`](drc_violation_fixture.json), [`draw.json`](draw.json), [`drc_violation_fixture.gds`](drc_violation_fixture.gds), [`drc.injected.json`](drc.injected.json)
- [`report.md`](report.md) -- combined `klt report --format github-summary`


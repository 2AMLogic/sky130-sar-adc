# `met2.enclosing_adjacent.via2.1` (`via2.5`): fix (issue #738, child of #729)

Dated 2026-10-27. Adds a file; earlier notes in this directory are untouched. Follows `triage-via2-rule-target-20261027.md` §5.

## Before / after on the top-level stream

0.8.0 numbers: `uvx --from "klayout-tools==0.8.0" klt drc <gds> --deck sky130 --format json` (klt 0.8.0, klayout 0.30.12,
deck hash `sha256:ba0f97887e3d231aec8b54f1f52f2941ded0228f0234b6759712bcaca0e942e6`, `klayout_version_mismatch: false`).
0.8.0 reports are not stored per record; the commands are re-runnable on the named GDS files.

| family | before (`sar-adc-top/reports/20261027-183429-b96026c2`) | after (`sar-adc-top/reports/20261027-193335-4433671f`) |
|---|---|---|
| `met2.enclosing_adjacent.via2.1` (`via2.5`) | 1171 | **0** |
| `poly.endcap.diff.1` (`poly.8`, not in scope) | 91 | 91 |
| `via3.width.1` (not in scope) | 10 | 10 |
| `met2.enclosing_adjacent.via.1`, `met1.enclosing_adjacent.via.1` (`m2.5`, `via.5a`) | 0 | 0 |

New top-level GDS sha256 prefix `7f768bb1e1057db0`. The recorded pinned (klt 0.6.0) DRC verdict is clean (0 violations) before and after.
Top-level LVS: `mismatch`, `mismatch_count` 67 and the same `category_counts` before and after (known blocker, unchanged).

## Per source

Measure-first result: all markers come from pads this repo draws; none from `klt gen`. No generic tool issue was needed.

- `cdac_array` (1110 of the 1171 on the top stream): `cdac_layout.py` `Canvas.via2` drew a 0.32 um met2 pad under a 0.20 um via2,
  i.e. 0.06 um per side. Now a 0.37 um pad (`VIA2_PAD_HALF` = 0.10 + 0.085). Standalone `cdac_array.gds`: 1090 -> 0
  (new record `layout/cdac-array/reports/20261027-193302-4433671f`; the other 18 markers there are `poly.endcap.diff.1`).
- `route__*` cells (61: 45 in `SAR_ADC_TOP_ROUTE`, 16 in `ROUTE`/`ROUTE$1`/`ROUTE$2`): `sar-adc-top/bin/build_layout.py`
  `Canvas.via` drew `PAD_UM` = 0.36 um met2 pads (0.08 um per side) at via2 cuts. Now met2 pads at via2 cuts are at least `VIA2_MET2_PAD_UM` = 0.37 um.
  The 16 `ROUTE*` markers were attributed to different source-cell names than `SAR_ADC_TOP_ROUTE`; I did not trace why, only that all
  `route__*` via2 markers are gone.
- `layout/bin/_geometry_common.py` (the issue's other suspect) already drew 0.42 um via2 pads; not changed.

## Flow runs

`cdac-array/bin/run-flow.sh` calls raw `xschem` (step 0, LVS-reference regeneration), which this host's rules forbid. It was run from a
throwaway copy with only that step and its `xschem` presence check removed; the committed LVS references were used (the schematics are unchanged).
Everything else ran as written, on the pinned `layout/.venv` (klt 0.6.0): DRC clean, both precheck grids pass. `sar-adc-top/bin/run-flow.sh` ran unmodified.
Not re-run: comparator, halflsb-offset, sampling-frontend, sar-sequencer, top-glue (their code is unchanged).
`layout/bin/check_drc_evidence.py`: OK. Record dirty-tree note: both records were produced before this change was committed.

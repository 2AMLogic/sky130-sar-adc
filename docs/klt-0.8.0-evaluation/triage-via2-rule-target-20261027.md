# `via2.5` rule target: DRM vs deck (issue #732, child of #729)

Dated 2026-10-27. Adds a file; `triage-20261027.md` is untouched (its "Not checked" section is closed here for `via2.5` only).

## Disposition: drawn geometry

The 1171 `met2.enclosing_adjacent.via2.1` markers are real violations of the rule the DRM states. The deck-side-labelling
reading in `triage-20261027.md` (row `met2.enclosing_adjacent.via2.1`) was inferred, and this check **refutes** it. No spec line
was touched and no deck was edited. Layout fix is a follow-up for the drawn-geometry child of #729 (not done here).

## 1. DRM text

SkyWater PDK rules, "Periphery rules", table "Function: Via2 connects met2 to met3 ..." (section `via2.-`),
<https://skywater-pdk.readthedocs.io/en/main/rules/periphery.html>, fetched as raw HTML 2026-10-27 and read from the page text:

- `via2.4`: "Via2 must be enclosed by Met2 by at least ... 0.040 um" (flag AL)
- `via2.5`: "Via2 must be enclosed by Met2 on one of two adjacent sides by at least ... 0.085 um" (flag AL)

So `via2.5` constrains **met2**, as the official runset's code (`m2.enclosing(via2, 0.085, projection)`) and klt do. Only the
runset's *message string* ("min. m3 enclosure of via2 ...") says m3; that string is the inconsistent part. The AL flag means the
DRM scopes the rule to Al back-end flows; whether this block's flow is in that set was not checked.

## 2. Official runset on current LATEST

Input: `layout/sar-adc-top/reports/20261021-104926-ddc1d72/sar_adc_top.gds` (`sha256:a2b58035a62d...`, current `LATEST`).
Runset: `sky130A_mr.drc` (sha256 `caf4a6b08cb1...`, open_pdks `f6eeac7d`, from `~/.ciel`), run with system `klayout -b`
(**KLayout 0.28.16**; klt used 0.30.12 - an uncontrolled difference), `-rd feol=false -rd beol=true -rd offgrid=false -rd seal=false -rd thr=2`,
`-rd top_cell=gen_compose_0` (the GDS top cell is `gen_compose_0`). FEOL/offgrid/seal groups were off, so poly/diff rules were not run.

| rule (official) | markers |
|---|---|
| `via2.5` | **1171** |
| `via.5a` | 157 |
| `m2.5` | 66 |
| `via3.1_b` | 40 |

All 1171 `via2.5` marker centres fall inside a klt `met2.enclosing_adjacent.via2.1` marker bbox (1171 klt markers; matching by
containment, not exact polygon equality). The `via.5a`/`m2.5` counts equal klt's 157/66 for the corresponding
`enclosing_adjacent` families. `via3.1_b` is 40 official vs 10 klt `via3.width.1`: not reconciled here (different rule scope), not needed for this issue.

## 3. klt 0.8.0 reproduction

`uvx --from "klayout-tools==0.8.0" klt drc <gds> --deck sky130 --format json`: `klt 0.8.0`, klayout 0.30.12, deck hash
`sha256:ba0f97887e3d231a...`, `klayout_version_mismatch: false`; 1495 violations, 1171 of them `met2.enclosing_adjacent.via2.1`
(same counts as `triage-20261027.md`). Raw outputs were in `/tmp` and are not committed; their hashes: klt JSON `6caa9c5f872b...`, official lyrdb `6f2aa2d4cf79...`.

## 4. Tool-side issue

None filed. klt matches both the DRM and the official runset code on layer and count; the only discrepancy is the runset's message string,
which is upstream PDK text, not a klayout-tools gap. The earlier note's open question (rule id naming a different layer than the DRM) is closed: it does not.

## 5. Follow-up

Drawn-geometry child of #729: the 1110 `cdac_array` and 45 `route__SAR_ADC_TOP_ROUTE` marker sources (per `triage-20261027.md`) need
met2 enclosure >= 0.085 um on one of two adjacent sides of each via2. Typical measured margins there are 0.65 um on L/R but 0.06 um on B/T opposite edges only.

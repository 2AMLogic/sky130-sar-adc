# `klt erc` supply record `20261001-211722-1ca34e6` — T1 item 11 (Power delivery, structural)

**Verdict: unchanged from the record it supersedes, on a layout whose drawn
geometry really did move** — every one of this composition's 1026 CDAC/offset
unit capacitor plates grew from 1.898 µm to 1.900 µm on a side, because issue
#501 re-composed the top level against
[DR-019](../../../../spec/decision-records/DR-019-cdac-unit-cap-grid-legal-plate-resize.md)'s
grid-legal `C_u` resize. Both halves of item 11, stated up front so neither
hides behind the other:

- **Passing:** all four of this block's drawn supplies (`VDD`, `GND`, `VPWR`,
  `VGND`) resolve to **exactly one** electrical island each, with no
  `erc.unconnected_net` and no `erc.supply_short` anywhere —
  `erc_status: "clean"`, `erc_finding_count: 0`.
- **Still unmet:** item 11 also requires zero `erc.missing_tie` *from a tie the
  run actually checked*, and this spec declares no `ties[]` (disclosed,
  unchanged, see the spec's `ties_disclosure`). `klt signoff` renders that state
  `unmet` / `supply_spec_disclosed_tool_limitation`. A second, independent
  reason is that item 11's grading path consults item 4's LVS report first,
  which reports `mismatch` (klayout-tools#1878 — unchanged by #501 and not
  closed by it, see `reports/20261001-211249-1ca34e6/record.md`).

## Why this record exists: the graded GDS moved, so the verdict about it had to

It supersedes `erc-reports/20261001-022622-455b772/` (issue #401's first ERC
record on the re-composed top level). That record grades
`reports/20261001-022205-455b772/sar_adc_top.gds`, which issue #501 superseded:
#498 carried DR-019's resize (`W = L` 1.8988 → 1.9000 µm) through `design/`,
`layout/cdac-array/` (`reports/20261001-133221-7487784`) and
`layout/halflsb-offset/` (`reports/20261001-084713-79abbf8`) but deliberately
left the composition alone, so the top level still embedded the pre-resize
plate in both sub-block GDS files. #501 re-ran `bin/run-flow.sh`; this record
grades what that run composed.

**An ERC record is a verdict about one GDS, and this one no longer exists in the
`reports/LATEST` chain.** Inheriting the superseded record here would have left
`signoff/block-manifest.json`'s item 11 citation pinned, by content hash, to a
layout the repo no longer builds — which is the staleness `docs/t1-gap.md`
treats as failure. It is re-graded rather than re-pointed.

The change this re-grade covers is a *dimensional* one on a layer `klt erc`
reads for antenna ratios, not a connectivity edit: no supply conductor, no via,
no tie and no label moved. Measured on the two composed GDS (from
`reports/20261001-211249-1ca34e6/decap-ties.json`, whose baseline arm is the
superseded record):

| layer | superseded GDS | this record's GDS | delta |
|---|---:|---:|---:|
| `capm` | 17085.807 µm² (1034 shapes) | 17093.600 µm² (1034 shapes) | **+7.793 µm²**, same shape count |
| `met3` | 22296.048 µm² (1609 shapes) | 22296.071 µm² (1609 shapes) | +0.023 µm² |
| `via3`, `met4`, `via4`, `met5` | — | — | identical, shape for shape |
| composed bounding box | 290.500 × 386.200 µm | 290.500 × 386.200 µm | **unmoved** |

The `capm` delta is exactly the resize and nothing else: 1026 × (1.900² −
1.898²) = 7.793 µm². (1.898 µm, not 1.8988 µm, is what the pre-resize drawing
actually reached on the database grid — which is the whole reason DR-019 exists.)

**So the question this record re-asks is the antenna arm's, and it is asked of
exactly two gates.** 255 of the 257 gate entries in `erc.json` are
field-identical to the superseded record. The two that move are the comparator's
own differential inputs, the gates the CDAC top-plate rails drive:

| gate | net | cumulative met4 area | antenna ratio | verdict |
|---|---|---|---|---|
| `gate251` | `TOP_P,VINP` | 965.20458 → **965.2046** µm² | 482.60229 → **482.6023** | `pass_partial`, unchanged |
| `gate255` | `TOP_N,VINN` | 1024.17958 → **1024.1796** µm² | 512.08979 → **512.0898** | `pass_partial`, unchanged |

Both deltas are +2 × 10⁻⁵ µm² of met4 on the step that collects the top-plate
rails — the fifth decimal place, and the only numbers in 257 gates' worth of
antenna accounting that the resize reaches. Neither crosses a limit, and neither
could: `met4` carries no `antenna_ratio_max` in the built-in sky130 table at this
pin, which is why both verdicts read `pass_partial` rather than `pass` and did so
before the resize too. That partial coverage is the envelope-level
`status: "violations"` in the table below; it is not a supply finding.

Produced by `layout/sar-adc-top/bin/run-erc.sh`. This is a verdict *about* an
existing layout record; it regenerates no geometry.

| | |
|---|---|
| Graded layout | `layout/sar-adc-top/reports/20261001-211249-1ca34e6/sar_adc_top.gds` — **a new GDS**, the first composing DR-019's resized `cdac_array`/`halflsb_offset` |
| Layout content hash | `sha256:9d7c1a4cf91cc23878f198bf7de7574ef10d72c8ca62d01466312696f916d14b`, moved from `sha256:ea954d318110ee5d2a39da926857393f42d96d17582734a7b6930e5520ca3346` (the superseded record's pin) |
| Spec | `layout/sar-adc-top/erc-supply-spec.json` — `sha256:8b69c6a2fb03e1e7459899c3edf4daa6e953348d42c08d63332428ed4d79c554`, **unchanged** from the superseded record, byte for byte |
| Tool | `klt` 0.6.0 / KLayout 0.30.12 (`layout/erc-requirements.txt`) |
| PDK | sky130A (open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b) |
| Invocation | `klt erc <gds> <spec> --pdk sky130 --deck sky130 --format json`, from the repo root with **repo-relative** paths |
| `status` / `erc_status` | `violations` / `clean` (exit 0) — the envelope-level `status` carries the antenna arm's partial coverage, not a supply finding; `erc_status`/`erc_finding_count` are the supply verdict |
| `erc_finding_count` | 0 |
| Gate nets checked | 257 (unchanged) |

## The non-tuning argument

The spec did not move at all this time — neither its whole-file hash (quoted
above, identical to the superseded record's) nor the graded-content digest
`run-erc.sh` computes over `stackup`, `vias`, `nets[]` and
`ties_disclosure.kind`:

```
run-erc.sh: graded-spec subset sha256=7f48fd89387b64b24c379baff04e6ef38361610240eac2c2d0adb8470584d982
```

Identical to the superseded record's digest and to every one of its
predecessors'. So this is the same gate, unchanged, applied to a materially
different layout — the only configuration in which "the verdict did not move" is
evidence about the layout rather than about the gate.

## Mesh ablation cross-check, re-run on the new geometry

`ground-mesh-ablation.json` in this record is a fresh run of
`bin/probe-ground-mesh.py` against the graded GDS (exit 0):

```
as_predicted: true          full_reproduces_record_gds: true
full_is_one_island: true    ablated_splits: true
controls_unmoved: true      controls_moved: []
third_leg_as_predicted: true
```

It is re-run rather than inherited for the same reason the ERC verdict is: both
of its arms are keyed to the graded GDS's own content hash, and
`full_reproduces_record_gds` is only meaningful when the un-ablated variant it
composes reproduces *this* record's layout (`sha256:9d7c1a4c…` on both sides,
and it does).

Every finding is field-identical to the superseded record's:

- `ablated_splits: true` at **3** islands, with the same three bboxes to the
  nanometre — `halflsb_offset`'s own ground terminal (5 shapes, 122.851–139.451
  × 65.200–78.980 µm), `sampling_frontend`'s own met1 ground (13 shapes,
  103.495–130.115 × 86.450–140.720 µm) and `comparator`'s own met4 stub (10
  shapes, 100.200–227.900 × 150.000–197.900 µm). All four mesh legs are still
  load-bearing by the same measurement.
- `controls_unmoved: true` (`controls_moved: []`) — ablating the analog mesh
  still moves `VDD`, `VPWR` and `VGND`'s island counts not at all.
- `third_leg_as_predicted: true` — the scratch-spec diagnostic still reports
  `VSS` and `GND` as one electrical net in the full variant and not in the
  ablated one, i.e. `cdac_array`'s differently-named terminal is still joined by
  metal rather than by assumption.

That immobility is expected: DR-019 resized a capacitor plate, and nothing in
the mesh, the ties or the pad is drawn from that dimension.

## What this record does NOT say

- **Not that the substrate half of `GND` is graded.** `klt erc` sees drawn
  conductor only. Every ground terminal here lands on the one extracted net
  `GND|VGND|VSS` — bulk sky130 offers no way to split it, per
  `spec/decision-records/DR-012-analog-ground-pad.md` — and a one-island verdict
  on `GND` still means "the drawn `GND` conductor is one island", not "every NMOS
  body reaches it".
- **Not that the composed LVS blocker moved.** It did not: `klt lvs` on the
  graded GDS still reports `mismatch`, at the same 67 mismatches / 66 errors in
  the same four categories as the superseded record, for the one open reason it
  already had (klayout-tools#1878). Closing that is its own work and #501 was
  not scoped to it.
- **Not that the resize is electrically verified here.** `klt erc` models
  connectivity; a 2 nm change in a plate's side is invisible to it except in the
  antenna arithmetic quoted above. DR-019's own electrical claim rests on
  `design/` and the `sim/` records its decision cites, not on this record.
- **Not that the decoupling meets DR-017's bounce target.** It does not, and
  DR-017's Decision §4 says so. Nothing in #501 touched the ties.

# `klt erc` supply record `20261017-193237-9522693e` — T1 item 11 (Power delivery, structural)

**Verdict: the n-well half of `erc.missing_tie` is now computed for the first
time, and it reports findings.** `erc_status: "violations"`,
`erc_finding_count: 28`, every one an `erc.missing_tie`. Stated up front so
neither half hides behind the other:

- **Supply continuity — unchanged:** all four declared supplies (`VDD`, `GND`,
  `VPWR`, `VGND`) still resolve to one island each; no `erc.unconnected_net` and
  no `erc.supply_short` anywhere in the 28 findings. In particular, the false
  `erc.supply_short` that klayout-tools#2169 produced from a `ties[]`
  declaration did **not** appear on klt 0.6.0 — that is what made it possible to
  retire the spec's `ties_disclosure` (`tool_limitation`).
- **Tie half — computed, findings open:** `erc_coverage.checked` contains
  `erc.missing_tie:["nwell_tap_vdd"]` and `erc.missing_tie:["nwell_tap_vpwr"]`;
  `erc_coverage.skipped` and `.inapplicable` are empty. The report's
  `ties_disclosure` key is present and `null` (the tool always emits it).
- **Not graded — the p-substrate half.** See "What this record does NOT say".
- **Item 11 still renders `unmet` / `check_failed`**, for the LVS reason only
  (item 4's `lvs.json` is `mismatch`, #103; the grader tests it first). This
  record changes no rendered verdict: `signoff/t1-report.json` re-renders
  byte-identical.

## What the 28 findings are

A `ties[]` entry applies to **every** island of its `well_layer`, and klt 0.6.0
has no well-side selector, so a block whose n-wells are tied to two different
rails (DR-010 splits analog `VDD` from digital `VPWR`) cannot be graded with one
entry. The spec declares two (`nwell_tap_vdd`, `nwell_tap_vpwr`; same
`well_layer 64/20`, `tap_layer 65/44`, `tap_is_dedicated`, `connect_to li1`), and
each therefore also flags the wells that belong to the other rail. Read off
`erc.json` by well bounding box (28 findings, 26 distinct wells):

| population | wells | how it is read |
|---|---:|---|
| flagged by `nwell_tap_vdd` only (21 − 2) | 19 | no tap reaching `VDD`, **but** none flagged for `VPWR`, so each has a tap reaching `VPWR` — digital-domain wells (x ≈ 23–153 µm, y ≈ −146…−83 µm) |
| flagged by `nwell_tap_vpwr` only (7 − 2) | 5 | converse: has a `VDD` tap — analog wells |
| flagged by **both** | 2 | **no tap reaching either rail**: bounding boxes (63.825, 85.850)–(70.565, 90.620) µm and (90.105, 85.850)–(97.095, 90.620) µm |

The two-sided reading is an inference from the findings' set structure, not
something the tool states, and only the 2 wells in the last row are candidate
real defects. They are **not** fixed or declared acceptable here (layout changes
are out of scope for #677); they are findings to triage, and item 11 cannot be
`met` while they stand. The 24 cross-domain flags are an artefact of declaring
one `well_layer` for two rails, not 24 defects.

## Provenance

| | |
|---|---|
| Graded layout | `layout/sar-adc-top/reports/20261001-211249-1ca34e6/sar_adc_top.gds` — the GDS the manifest's items 3, 4 and 11 already cite. **Not** `reports/LATEST` (`20261003-041400-571f036`): grading the cited GDS keeps the change in this record to the spec, not the layout |
| Layout content hash | `sha256:9d7c1a4cf91cc23878f198bf7de7574ef10d72c8ca62d01466312696f916d14b` — identical to `erc-reports/20261001-211722-1ca34e6/`'s |
| Spec | `layout/sar-adc-top/erc-supply-spec.json` — `sha256:a6910c3b2274704a904d22aa1ae8258b4dc2e0b6f10d167112a59604234c288d` (previous record: `8b69c6a2…`) |
| Graded-spec digest | `36ade38f8e4e22bd78bc819ae33fe31edf2d2857d3f25fd260e9b5a170bb2ef5` (previous records: `7f48fd89…`) — **moved on purpose**: `ties[]` is now part of what `klt erc` grades, so `run-erc.sh` folds it into the digest. `stackup`, `vias` and `nets[]` are unchanged |
| Tool | `klt` 0.6.0 / KLayout 0.30.12 (`layout/requirements.txt`) — same as the previous record |
| PDK | sky130A (open_pdks f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7). The previous record names `c6d73a35…`. This is an uncontrolled difference between the two runs; `klt erc --pdk sky130` reads the built-in antenna table, not the install (see `run-erc.sh`), so no effect is expected, but it was not tested. Pin question: #669 / #670 |
| Invocation | `klt erc <gds> <spec> --pdk sky130 --deck sky130 --format json`, repo-relative paths |
| `status` / `erc_status` | `violations` / `violations` (exit 3) |
| `erc_finding_count` | 28 (`erc.missing_tie` ×28: `VDD` ×21, `VPWR` ×7) |
| Gate nets checked | 257 (unchanged) |

## The non-tuning argument

Moving the spec is what this issue is, so the usual "spec did not move"
argument does not apply; the relevant invariant is the other direction: nothing
was relaxed to get a result. `stackup`, `vias` and `nets[]` are untouched, no
declared supply was added or dropped, and the new `ties[]` produced findings
that this record reports rather than adjusts around. The `tool_limitation`
disclosure was removed, not re-added to mask them.

## Ground-mesh ablation: not re-minted

The ablation summary (`bin/probe-ground-mesh.py`) is **not** part of this
record. It recomposes the layout from `bin/build_layout.py` and requires its
`full` arm to reproduce the record's GDS byte for byte. `build_layout.py` has
changed since `reports/20261001-211249-1ca34e6` was composed (issue #103's
re-measure), so a re-run today recomposes `sha256:a2b58035…`, not the record's
`sha256:9d7c1a4c…`, and reports `full_reproduces_record_gds: false`. The mesh
verdict for this GDS stays the one in
`erc-reports/20261001-211722-1ca34e6/ground-mesh-ablation.json`, which is keyed
to the same GDS hash and is unaffected by a `ties[]` change (it grades `GND`
island counts).

## What this record does NOT say

- **Not that the substrate half is graded.** The spec declares no p-substrate
  tie: sky130 draws no substrate shape to name as `well_layer`, and the
  `well_layer: null` + `well_boxes` alternative cannot describe "everywhere
  outside the n-wells" without covering the whole die (graded as skipped,
  `degenerate_well_assertion`) or hand-listing every gap. Filed generically as
  klayout-tools#3750. A one-island `GND`/`VGND` verdict still means "the drawn
  conductor is one island", not "every NMOS body reaches it".
- **Not that the 2 untapped wells are real defects.** A tap that the tie model
  cannot see (for example one not on `65/44`, or not reaching `li1` through
  `licon1`) would produce the same finding. They need a look at the layout.
- **Not that the other 24 flags are fine for a stated reason beyond set
  arithmetic.** The "tied to the other rail" reading follows from the two
  entries' findings; no separate per-well net query was run.
- **Not a verdict on the current layout.** It grades the GDS the manifest cites,
  which `reports/LATEST` has since moved past.

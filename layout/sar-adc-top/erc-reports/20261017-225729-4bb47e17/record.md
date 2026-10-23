# `klt erc` supply record `20261017-225729-4bb47e17` — T1 item 11 (Power delivery, structural), per-rail n-well selectors

**Verdict: `erc_status: "violations"`, `erc_finding_count: 2`.** Both are
`erc.missing_tie` against `VDD` from the `nwell_tap_vdd` entry, on the two wells
issue #684 tracks. The earlier record `20261017-193237-9522693e` reported 28.
Item 11 is **not** met by this record.

- **Tie half:** 28 → 2. The 26 findings that are gone are the 24 single-entry
  flags (19 `nwell_tap_vdd`-only, 5 `nwell_tap_vpwr`-only) plus 2 of the 4
  findings on the two wells flagged by both entries (each of those wells was
  reported once per entry; it is now reported once). The expectation in #685
  ("the 24 cross-domain flags disappear, only #684's two wells remain") held on
  this run; the bounding boxes of the two remaining findings,
  (63.825, 85.850)–(70.565, 90.620) µm and (90.105, 85.850)–(97.095, 90.620) µm,
  are the same two wells as in the earlier record.
- **Supply continuity:** unchanged. No `erc.unconnected_net` / `erc.supply_short`;
  `VDD`, `GND`, `VPWR`, `VGND` each resolve to one island (run-erc.sh: PASS).
- **Coverage:** `erc_coverage.checked` contains `erc.missing_tie:["nwell_tap_vdd"]`
  and `erc.missing_tie:["nwell_tap_vpwr"]`; `skipped`, `inapplicable`,
  `checked_by_assertion` and `checked_by_well_assertion` are all empty. So neither
  selector degenerated (kept all or none) and neither rests on caller-named
  coordinates.
- **Not graded:** the p-substrate half (unchanged; see
  `erc-reports/20261017-193237-9522693e/record.md`).

## What changed in the spec

`ties[]` is now `nwell_tap_vdd` with `well_excludes: ["81/4"]` and `nwell_tap_vpwr`
with `well_requires: ["81/4"]` (klayout-tools#2339). 81/4 is areaid.standardc.
In the graded GDS it has exactly 2 merged shapes, (23.418, −147.280)–(61.598,
−111.920) and (86.055, −147.280)–(153.215, −82.000) µm, which is the area of the
two std-cell macros. Each of the 19 `nwell_tap_vdd`-only findings of the earlier record
overlaps one of those two boxes (the wells' bounding boxes extend slightly past
them, e.g. left edge 23.228 µm against 23.418 µm; selection is by interaction, not
containment). The marker form was chosen over
`well_*_boxes` because it is drawn geometry, not a coordinate list the spec
asserts. No spec row, `stackup`, `vias` or `nets[]` entry changed.

The partition is only as good as the marker: a digital well drawn outside 81/4
would be graded against `VDD` and appear as a finding. This run shows none do,
and it does not show that no analog well sits inside 81/4 — such a well would be
graded against `VPWR` and would have appeared as a finding, and none did.

## Provenance and uncontrolled differences

| | |
|---|---|
| Graded layout | `layout/sar-adc-top/reports/20261001-211249-1ca34e6/sar_adc_top.gds`, `sha256:9d7c1a4c…` — identical to the earlier record's |
| Spec as committed | `layout/sar-adc-top/erc-supply-spec.json`, `sha256:025b1c6f07a0624d005182408b2f70994aa7e9c71f79698687169bf86f6a4166` |
| Spec as graded | `erc-supply-spec.graded.json` in this directory, `sha256:7053bf8623dbce9d13023de8f8fafd72fd800202ef8afcc6d688cad48a96674b` (the committed spec with every underscore-prefixed key dropped). This is the hash `provenance.spec.content_hash` carries |
| Graded-spec digest | `3838d75617e31f08179975bf0815877f157317aee13fb76ef7de1a19490d34e3` (earlier record: `36ade38f…`) — **moved on purpose**: `well_excludes` / `well_requires` are part of what `ties[]` grades |
| Tool | `klt` **0.7.0** / KLayout 0.30.12, from `layout/erc-requirements.txt` into `layout/.venv-erc`. The earlier record was `klt` 0.6.0. **Uncontrolled difference:** the tool version moved together with the spec, so this record cannot attribute the 28 → 2 change to the selectors alone — a 0.6.0 spec cannot carry them, and a 0.7.0 run of the *old* spec was not made |
| PDK | `klt erc --pdk sky130 --deck sky130` (built-in). open_pdks f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7, resolved by `run-erc.sh`; the earlier record names the same commit. `klt erc` reads no install, so the PDK revision is not expected to matter |
| Deck | `sky130`, content hash `sha256:f8f2c3f4…`, `released: true` |
| Invocation | `layout/sar-adc-top/bin/run-erc.sh layout/sar-adc-top/reports/20261001-211249-1ca34e6/sar_adc_top.gds` (single local run); `klt erc` exit 3 |
| Host | `loom-worker`, one `klt erc` process, no grid |

Also in this directory: `erc.stderr`, one `klt erc` warning new on 0.7.0: the
`met3` stackup entry declares label layer 70/5 but the stream carries no text on
it. Not investigated here; no finding in this record refers to `met3`.

## Why the pin is split

`layout/requirements.txt` stays at 0.6.0. `docs/klt-0.7.0-evaluation/note-20261012.md`
(#649) found that 0.7.0's DRC deck reports violations on the cited top-level
stream where 0.6.0 reports clean, and that finding is untriaged. Bumping the
shared pin would also invalidate `layout/bin/check-klt-pin-evidence.sh`'s
trivial-cell proof. `klt erc` reads only a GDS and a JSON spec, so the ERC run
alone moves to 0.7.0. This departs from #685's first acceptance bullet
("`layout/requirements.txt` pins 0.7.0") on purpose.

`klt` 0.7.0 also rejects the `_comment` annotation keys this spec carries
(klayout-tools#2822; the fix merged 2026-10-12, after the v0.7.0 tag of
2026-10-08). `run-erc.sh` therefore grades a comment-stripped copy kept in the
record. No new tool issue was filed.

## What this record does NOT say

- **Not that the two wells are defects, nor that they are digital or analog.**
  They sit outside 81/4, so they are graded against `VDD` only; that is a
  consequence of the selector, not a finding about which rail they belong to.
  #684 owns them.
- **Not that item 11 or the manifest changed.** `signoff/block-manifest.json`
  still cites `20261017-193237-9522693e`, and `signoff/t1-report.json` was not
  re-rendered. This record only moves `erc-reports/LATEST`.
- **Not that the 24 flags were verified per well.** The disappearance is the
  observation; the earlier "tied to the other rail" reading was set arithmetic
  and no per-well net query was run here either.
- **Not a `klt` 0.7.0 vs 0.6.0 comparison on the old spec.** See the tool row.

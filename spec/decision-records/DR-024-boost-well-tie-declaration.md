# DR-024: The two boosted-side n-wells are declared to `klt erc` as ties to `BOOST_P` / `BOOST_N`

- **Status**: proposed — scopes how the ERC supply spec describes DR-007's well
  assignment; it sets no numeric row of `spec/target-spec.md` and inherits the
  provisional status of the records it rests on.
- **Date**: 2026-10-18
- **Decided by**: Builder agent, issue #684
- **Supersedes**: none
- **Superseded by**: (none while this record stands)
- **Related**: #684, #685 (per-rail selectors, klt 0.7.0), #677 / PR #682
  (`ties[]`), DR-007 (`BOOST_P` / `BOOST_N` well domains), DR-010,
  `layout/sar-adc-top/probe-reports/20261017-201500-9522693e/summary.md`,
  `layout/sar-adc-top/erc-reports/20261017-225729-4bb47e17/` (2 findings),
  `layout/sar-adc-top/erc-reports/20261018-005757-5d07fe65/` (0 findings).

## Context

After #685, `klt erc` reported exactly two `erc.missing_tie` findings against
`VDD`: the n-wells at (63.825, 85.850)–(70.565, 90.620) µm and (90.105, 85.850)–
(97.095, 90.620) µm. **Verified** by a stock-KLayout probe on the graded GDS
(not by `klt`): each well holds one `65/44` tap with a licon1 / li1 / mcon / met1
stack, and the taps sit on nets labelled `BOOST_P` (west) and `BOOST_N` (east).
DR-007 assigns the boosted-side PFET bodies to those nets. So the layout matches
DR-007 and the ERC spec was grading the wells against the wrong rail.

## Decision

1. Declare the wells as their own `ties[]` entries, `nwell_tap_boost_p` and
   `nwell_tap_boost_n`, graded against `BOOST_P` and `BOOST_N`.
2. Exclude them from `nwell_tap_vdd` so each is graded once, against its own net.
3. Select the wells with `well_requires_boxes` / `well_excludes_boxes` on the
   taps' bounding boxes. No drawn layer separates these wells from the other
   analog wells (measured on the graded GDS), so the marker-layer selectors
   (`well_requires` / `well_excludes`) cannot express the class. The cost is that
   klt lists these entries, and `nwell_tap_vdd`, under
   `erc_coverage.checked_by_well_assertion`.

No layout change, no `target-spec.md` row, and no `stackup` / `vias` / `nets[]`
change. No finding was waived: the tap, its reach to `li1`, and the net it is
on remain measured.

## Consequences

- A new n-well drawn later is graded against `VDD` (or `VPWR` inside 81/4)
  unless the boxes are extended; a BOOST well added without editing the spec shows
  as a finding, not as a pass.
- The wells' membership in the BOOST class rests on the boxes, which follow
  DR-007 and the probe. This record does not check that each well holds exactly
  the PFETs DR-007 assigns.
- If a drawn class marker is later added to the layout, the boxes should be
  replaced by it (a new record supersedes this one).

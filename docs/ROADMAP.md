# Roadmap

A 10-bit charge-redistribution SAR ADC on the open sky130 PDK, designed forward
from `spec/target-spec.md` with xschem, ngspice and klayout-tools (`klt`).

Status as of 2026-11-13, `main` @ `1b3ab461`.

Verdict of record: [`signoff/t1-report.json`](../signoff/t1-report.json), explained
in [`signoff/README.md`](../signoff/README.md). Counts below are copied from it.

## Where it stands

- **T1 (bronze) evidence checklist: 13 of 22 rows met, tier `null`.** The block
  is graded as `mixed-signal`, so each of the eleven items has an analog and a
  digital row. Met: items 2, 3, 8, 9, 10 on both partitions, item 1 analog,
  items 5 and 7 digital (both narrow; see `signoff/README.md`).
- **Unmet rows and their reasons:**
  - Item 1 digital (`check_failed`): `layout/sar-sequencer/netlist/sar_sequencer.v`
    is behind `design/sar_sequencer.sch` (#680, PR #772).
  - Item 4 both (`check_failed`): top-level LVS reports `mismatch` against the
    full-block reference; root cause filed upstream as klayout-tools#1878 (#103).
  - Item 5 analog (`no_evidence`): no `klt sim` envelope is cited, and the ENOB
    and INL/DNL target values are still DRAFT.
  - Item 6 both (`no_evidence`): six `klt yield` envelopes exist, all
    `status: "fail"`, none citable (`signoff/README.md`, "Item 6").
  - Item 7 analog (`no_evidence`): no top-level `klt pex`; waits on item 4.
  - Item 11 both (`check_failed`): supply continuity passes, but item 4's LVS
    is tested first, and `erc.missing_tie` findings come next.
- **Spec: partly ratified.** Supply flavour (DR-001) and resolution, `V_REF`,
  LSB, unit cap, comparator noise budget and corner set (DR-003) are RATIFIED.
  Sample rate, ENOB, INL/DNL, kickback, gain error and power are DRAFT.
  DR-022 is accepted as a DRAFT row; DR-007, DR-011, DR-018, DR-020, DR-021,
  DR-023, DR-024 and DR-025 are `proposed`.
- **Conversion: overall FAIL.** The newest full-conversion record
  (`sim/full-conversion-transient/records/20261011-112119-188e94c.md`) resolves
  3 of 5 inputs within ±1 LSB at each of the nine ratified corners; the two
  near-full-scale inputs do not converge. DR-021 proposes the fix and DR-025
  the gain-error closure path; neither is ratified or implemented.
- **Pins and freshness.** `layout/requirements.txt` is `klayout-tools==0.6.0`;
  the grader in `signoff/requirements.txt` is `0.8.0`. `sim/pdk.json` pins
  open_pdks `f6eeac7`, superseding `c6d73a3`. The manifest cites top-level run
  `20261001-211249-1ca34e6` for items 3, 4 and 11, while
  `layout/sar-adc-top/reports/LATEST` is `20261027-193335-4433671f` (#743).

## Now

Can start today. None of these moves a T1 row; see "Blocked and waiting".

| What | Done when | Issue |
|---|---|---|
| Correct the fixed-text sentences in the vcm-drive-budget full-grid records | superseding records minted whose text agrees with their own tables | #894 (in progress) |
| Challenge #4 proposal: grade the two pages the earlier passes missed | PR #843 rebased, review findings resolved, `check:proposal-citations` passes | #121, PR #843 |
| Dead-code and import cleanup already in review | PRs #899, #900, #901 merged with `check:ci` green | #877, #895, #884 |
| Refresh the README status section | README no longer says "6 of 22", "Private for now", or links closed #265 as open; a test ties any met-count in the README to the report | none (seed 1) |
| Give the CDAC DNL/INL `klt yield` envelope a committed samples file | new `sim/cdac-array-transfer/yield-reports/<id>.json` naming a committed `<id>.samples.json`; "Item 6" text updated | none (seed 2) |
| Converging-range boundary sweep (DR-021 Open items) | a `sim/full-conversion-transient/` record stating, per input between 0.25 and 0.78·`V_REF`, whether the code lands within ±1 LSB | none (seed 3) |
| Three maintenance proposals awaiting promotion | one composite CI action for ngspice + PDK provisioning; `run_info()` shared by digital-partition; unit suite runs once in `check:ci` | #875, #888, #889 |

## Next

1. **Digital re-route chain.** After the #869 decision: merge PR #798 into its
   parent branch, land PR #788 (#784, PnR pins off li1 onto met2), close #790.
   Done when `check:report` passes on `main` with the re-minted
   digital-partition campaign.
2. **Regenerated sequencer netlist.** PR #772 (#680) turns item 1 digital to
   `met`; it waits on re-minted STA and SDF evidence (#771), which needs a
   batch image carrying OpenROAD/OpenSTA, and on the citation restatement in
   PR #774 (#773). Done when item 1 digital and items 5/7 digital are `met`
   against the regenerated netlist.
3. **Top-level re-run on current tools.** After items 1 and 2: re-run
   `sar-adc-top` on klt 0.9.0 with every child regenerated (#785). Done when a
   new dated `layout/sar-adc-top/reports/` run exists with a fix or a recorded
   disposition per DRC/LVS finding.
4. **Layout pin bump.** After #785: `layout/requirements.txt` moves off 0.6.0
   and every layout flow is re-run (#734, closes tracker #729).
5. **Repoint the manifest.** After #734: items 3, 4 and 11 cite the run that
   matches `reports/LATEST`, with ERC on the same stream (#743).
6. **Re-run records under the current PDK pin.** Multi-corner and Monte Carlo
   records re-minted through `klt sim` as superseding records (#811, under
   #709/#670/#668). Waits on the client/runner version mismatch recorded in
   #811 (klayout-tools#5061, klayout-tools#5060).
7. **Per-corner gain extraction and corrected-code column** across all nine
   corners (#757). Waits on DR-025's ratification.

## Later

- **Near-full-scale conversion.** Implement DR-021's common-mode-neutral CDAC
  switching and re-run the nine-corner campaign. First: is DR-021 ratified,
  and does `--cm-trace` at ±0.78·`V_REF` keep the common mode inside what the
  comparator resolves?
- **Gain error.** Implement DR-025's closure path and re-measure `C_par`.
  First: is DR-025 ratified, and does it close the DRAFT `<= 1.42 LSB` row?
- **Item 4, strict LVS.** A match against `design/sar_adc_top.spice` with no
  relaxed criterion. First: does klayout-tools#1878 land, or is there another
  supported method for the `GND`/`VGND` shared-substrate reference (DR-012)?
- **Items 7 analog and 11.** Top-level `klt pex` with post-layout simulation,
  and every `erc.missing_tie` finding resolved or filed. First: does item 4
  match, and can the p-substrate ties be declared (klayout-tools#3750)?
- **Items 5 analog and 6.** `klt sim` and Monte Carlo evidence against
  ratified ENOB and INL/DNL rows. First: which target values are ratified
  (DR-007), how many draws are run (the tool asks for 368 to claim 0.99 at the
  observed ENOB rate), and how does one manifest entry cover two rows?

## Blocked and waiting

On an operator decision:

- #869: break the PR #788 / PR #798 merge-order deadlock.
- #103: whether the strict real-reference LVS hold still binds.
- #836: Challenge #4 dedicated-pad overrun (5 needed against 3 published) and
  padframe overvoltage protection; proposals are due 2026-11-23
  (`docs/chipalooza/challenge-4-proposal.md`).
- PR #842 (#834, absolute limits in DR-026): approved, held for a merge
  decision; #844 is the related PDK file-count discrepancy.
- #621 (verify the merged outlier records and close), #23 (shape of the
  tracker issue), #428 (required-status-checks ruleset), and ratification of
  the `proposed` decision records listed above.

On upstream klayout-tools: #1878 (item 4), #3750 (item 11), #2467 (item 6),
#5060 and #5061 (batch `klt sim` requests).

**Dispatchable today:** only the maintenance, documentation and measurement
items under "Now"; every item that would move a T1 row is parked.

## Not planned

- T2, T3 and T4 rows (`tier_not_supported` in the report) and silicon
  measurements (`measurements/` stays empty until there is silicon).
- Relaxing a spec row or an LVS/DRC criterion to turn a row `met`, or
  recording a tier grant in this repo.

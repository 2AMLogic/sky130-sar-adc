# Citation gate: per-check drift evidence and replacement coverage

Issue #588. This is an evidence deliverable only. It changes no check, no test,
no `package.json` / `.github/workflows/ci.yml` wiring, and no line of
`docs/citation-gate.md` (including its "Scope freeze" section, issue #543).
The operator ruled on 2026-10-15 (issue #588): keep every existing citation
gate, and produce a check-by-check drift-history and replacement-coverage
proposal before any retirement. The **Proposed disposition** column below is a
recommendation for a later, separate, evidence-backed proposal. It is not an
action and authorizes nothing. Any retirement needs that proposal and
operator/ratification review.

Measured on `origin/main` @ `15ea2eae`, 2026-11-06.

## 1. What is being counted

```
$ grep -cE '^def check_' docs/chipalooza/check_proposal_citations.py
38
$ grep -nE '^def check_document' docs/chipalooza/check_proposal_citations.py
6264:def check_document(doc: Path) -> list[str]:
```

`check_document` has no `Check N` docstring. It is the driver that
concatenates the other 37 functions. So there are **37 check functions**
covering **38 numbered checks** (`check_pointer_claims` is "Checks 4 and 5").
The "38 `check_*` functions" count in the issue body and in the "Scope freeze"
wording counts the driver; the table below has 37 rows. I did not edit the
scope-freeze line.

Line counts: checker 6582, tests 7670 (`sim/tests/test_proposal_citations.py`),
rationale 2043 (`docs/citation-gate.md`), proposal 5934. The three gate files
have 43 / 49 commits (`git log --oneline -- <checker>` / `-- <checker> docs/citation-gate.md sim/tests/test_proposal_citations.py`).

## 2. Method

### 2a. Introduction commit (git history)

```
git log -S"def <check_fn>(" --format='%h %ad %s' --date=short --diff-filter=A -- docs/chipalooza/check_proposal_citations.py
git show --numstat --format= <hash> -- docs/chipalooza/challenge-4-proposal.md
```

The column shows the commit that added the function, and the `+added/-removed`
line counts that same commit made to `challenge-4-proposal.md`. "Subject says
it corrected the document" means only that the commit *subject* names a
correction (`correct`, `re-point`, `overstated`, `mischaracterization`,
`lost`); I did not re-derive from each diff that the correction was a stale
citation the new check would have caught. A `+N/-0` proposal diff or a
subject with no correction word is recorded as "no correction indicated",
which is not evidence that no drift existed.

Not counted as catches (per the issue's edge cases):

- `72bd0ee7`, `38887808` (2026-10-18) and `f6d7d0e8` (2026-10-05): refactors of
  checks 30-34 / the numeric-field comparison. They changed no document claim.
- False-positive and docstring fixes to the checks themselves, which are
  upkeep cost rather than catches: `b5d91408` (check 30 counted a comment as a
  pin, #424), `ea2e3fb1` (check 25 scanned `.control` bodies, #406),
  `d865b21d` (check 17 failed-row scope, #379), `c1d7292e` (check 37
  docstring), `4164edd1` (provenance fetch dedup).

### 2b. CI fires (failed `ci.yml` runs)

```
gh run list --workflow ci.yml --status failure --limit 1000 \
  --json databaseId,createdAt,headBranch,displayTitle \
  --jq '[.[]|select(.createdAt>="2026-09-16")]'        # gate landed 2026-09-16 (01154ef5)
  -> 153 failed runs, earliest 2026-09-19, latest 2026-11-06
for id in <each>: gh run view $id --log-failed | grep -oE 'challenge-4-proposal\.md:[0-9]+: .*'
  -> 99 of the 153 failed runs contain at least one citation-gate message
```

Each message was attributed to a check by matching its text against the
f-strings in the checker (`grep -n` of each phrase, e.g.
`4547: the ground-return census says`, `6044: states ... in the present
tense, but`, `1846: only at superseded record(s)`).

Findings that qualify every CI number below:

1. **All 99 runs surfaced the message through the unit-test step, not the
   script step.** Every one of those 99 logs contains
   `AssertionError: Lists differ: ['challenge-4-proposal.md:...` and none
   contains `OK: every citation`. `check:ci` is an `&&` chain that runs the
   unit suite before `npm run check:proposal-citations` (`package.json`), so
   the script step never ran in those runs. In the runs counted here that
   first step was `npm run test` -> `test:unit`; since issue #889 the suite
   reaches the same position through `npm run check:harness` ->
   `sim/selftest.sh` stage 1, and the order is held by
   `sim/tests/test_check_ci_unit_suite_once.py`. The unit suite
   (`sim/tests/test_proposal_citations.py`) runs the checks over the
   live tree, so the live-tree tests and the script duplicate each other in CI.
2. **Fires are not classified as "real stale citation" vs "branch mid-update".**
   Every fire is on a feature branch that regenerated or superseded records
   (or on `main` on 2026-09-25, three runs). I did not follow each branch to
   see whether the next push edited the proposal, so a fire means "the check
   rejected a push", which is the intended behaviour but not proof of a
   claim a human would have missed.
3. **Run counts overlap** (one run can fire several checks), so rows cannot be
   summed. 88 of the 99 runs are attributed to a check by an untruncated
   message; 11 carry only a truncated assertion line
   (`the proven[N chars]`) and are not attributed to any row.
4. The log window starts 2026-09-19; the first 3 days of the gate have no
   failed-run record.

Reproduce a row: `gh run view <run-id> --log-failed | grep -E 'challenge-4-proposal.md:[0-9]+:'`.

Literal samples (one per fired check; `<run>` is the `gh run` id):

```
<42093627793> challenge-4-proposal.md:1248: spec row "Power" cites `layout/sar-sequencer/` only at superseded record(s) `20260917-180601-527ec73`, `20261012-113813-743bcd0`, `20261021-104530-ddc1d72` -- that flow's current reports/LATEST is `20261105-191625-bf27ff9d`
<42262451493> challenge-4-proposal.md:971: states `67 mismatches on the current record` in the present tense, but `layout/sar-adc-top/reports/LATEST` reports 633 mismatches -- restate it ...
<42093513310> challenge-4-proposal.md:5802: the provenance census says layout_records=112, but the evidence tree reports layout_records=114 -- restate it from `python3 docs/chipalooza/check_proposal_citations.py --stats`, ...
```

The other fired checks' messages are in the matching logs
(`ground-return census says decks=...`, `T1 sign-off readout says met=...`,
`decision-record readout says ...`, `freshness-coverage census says ...`,
`corner-grid census lists ...`, `sweep census says covered=...`).

### 2c. Replacement coverage

Per row, what would still guard the claim if the check were retired. **Every
entry is inferred** from the check's own docstring and the names in
`package.json` `check:ci`; none was tested by removing the check. "None" means
no other automated gate that I could identify reads that claim.

## 3. Per-check table

Columns: **#** = the checker's own `Check N`. **Intro** = introducing commit
and its proposal diff (2a). **CI fires** = failed `ci.yml` runs since
2026-09-19 whose log contained that check's message (2b). **Replacement
coverage** (2c). **Disposition**: `keep` or `candidate-to-retire`. Rule
applied: `keep` if the check is mechanical (path/link/pointer resolution), or
has any CI fire, or its introducing subject says it corrected the document;
otherwise `candidate-to-retire` (meaning only "no evidence of a catch was
found by these searches").

| # | Function | Intro (hash, proposal +/-) | Introduction subject says it corrected the doc? | CI fires | Replacement coverage (inferred) | Disposition |
|---|---|---|---|---|---|---|
| 1 | `check_links` | `01154ef5` +48/-1 | yes: "re-point one stale §4 row" (shared with 2-5) | none | none (mechanical link existence) | keep (mechanical) |
| 2 | `check_bare_paths` | `01154ef5` | same commit as 1 | none | none (mechanical path existence) | keep (mechanical) |
| 3 | `check_spec_table_freshness` | `01154ef5` | same commit as 1 | 28 runs, 5 branches (#103, #647, #680, #733, #784), 2026-09-19..2026-11-06 | none | keep |
| 4+5 | `check_pointer_claims` | `01154ef5` | same commit as 1 | none by own message (its census text is check 6's) | none (`LATEST` pointer resolution; mechanical) | keep (mechanical) |
| 6 | `check_census` | `b7bcb661` +45/-18 | no correction indicated | none | none | candidate-to-retire |
| 7 | `check_spec_row_parity` | `873c29d3` +43/-8 | no correction indicated | none | `check:spec-coverage` (`sim/check_spec_coverage.py`) reads the ratified spec; whether it also covers the proposal's restated table is not verified | candidate-to-retire |
| 8 | `check_verdict_vocabulary` | `873c29d3` | same commit as 7 | none | none | candidate-to-retire |
| 9 | `check_signoff_readout` | `c21e2340` +32/-0 | no correction indicated | none | `check:drc-evidence`, `check:signoff-hashes` cover the records, not the prose readout | candidate-to-retire |
| 10 | `check_io_table_parity` | `531d2f93` +34/-9 | no correction indicated | none | none for the prose list; `check:glue-parity` covers other netlist parity (not verified for this list) | candidate-to-retire |
| 11 | `check_coverage_index_parity` | `936e92e1` +85/-8 | yes: "re-grade the Power row" | none | none | keep |
| 12 | `check_power_readout` | `936e92e1` | same commit as 11 | none | none | candidate-to-retire |
| 13 | `check_area_readout` | `95f58a4e` +31/-1 | no correction indicated | none | none | candidate-to-retire |
| 14 | `check_composition_inputs` | `fc0f4d70` +131/-0 | no correction indicated | none | `check:composition-parity` covers the composition's inputs, not the prose (not verified) | candidate-to-retire |
| 15 | `check_decision_record_status` | `7e1b8ed5` +92/-0 | no correction indicated | 6 runs, #753, 2026-11-01 | none | keep |
| 16 | `check_erc_readout` | `f9bc8d7e` +43/-1 | no correction indicated | none | none | candidate-to-retire |
| 17 | `check_t1_readout` | `b5f701f3` +76/-1 | no correction indicated | 17 runs, 4 branches (#364, #678, #679, #727), 2026-09-24..2026-11-01 | `check:signoff-attest` covers the report, not the prose readout | keep |
| 18 | `check_freshness_coverage` | `6384e274` +44/-9 | no correction indicated | 5 runs, #756, 2026-11-01 | none (meta-check over check 3's reach) | keep |
| 19 | `check_test_plan_ports` | `7c41ab49` +63/-11 | yes: "make the bench plan executable on the 22-port part" | none | none | keep |
| 20 | `check_top_cell_inventory` | `3d930d32` +130/-9 | yes: "find the glue the layout lost" | none | `check:glue-parity` | keep |
| 21 | `check_kickback_decomposition` | `cbcada2e` +1/-1 | yes: "correct a mischaracterization" | none | none | keep |
| 22 | `check_tracked_records` | `bfb372cc` +1/-1 | no correction indicated | none | none | candidate-to-retire |
| 23 | `check_stamped_currency_claims` | `7573a96a` +75/-15 | no correction indicated | none | check 3 resolves the pointer; the "stamped" currency form is not covered elsewhere | candidate-to-retire |
| 24 | `check_report_row_count` | `33a500ba` +19/-3 | no correction indicated | none | `check:report` (`sim/report/generate.py --check`; the checker's docstring says it compares against that row count) | candidate-to-retire |
| 25 | `check_ground_return` | `945290c7` +73/-2 | no correction indicated | 15 runs, 4 branches (#603, #621, #754, #756), 2026-10-09..2026-11-01 | none | keep |
| 26 | `check_provenance_census` | `f24e5550` +34/-4 | yes: "count the layout third it overstated" | 63 runs, 13 branches, 2026-10-10..2026-11-06 | none | keep |
| 27 | `check_label_claim_section` | `d149c5d8` +44/-16 | yes: "correct #103's tracking state" | none | none | keep |
| 28 | `check_corner_grid_census` | `6693881c` +75/-1 | no correction indicated | 11 runs, 3 branches (#121 absent-path gate, #406, `main`), 2026-09-25 | none | keep |
| 29 | `check_absent_paths` | `8a4d3e5a` +60/-0 | yes: "record #400's not-planned closure" | none | none | keep |
| 30 | `check_renderer_census` | `8ab0410e` +35/-15 | no correction indicated | none | none | candidate-to-retire |
| 31 | `check_arm_census` | `ba8b1e93` +51/-13 | no correction indicated | none | none | candidate-to-retire |
| 32 | `check_sweep_census` | `c62e886b` +73/-3 | no correction indicated | 2 runs, #409, 2026-09-25 | none | keep |
| 33 | `check_decoupling_census` | `6dafa59f` +63/-0 | no correction indicated | none | none | candidate-to-retire |
| 34 | `check_null_sweep_census` | `619bfd4b` +66/-4 | yes: "correct #409's item status" | none | none | keep |
| 35 | `check_excursion_enumeration` | `c9729640` +41/-16 | no correction indicated | none | none | candidate-to-retire |
| 36 | `check_present_tense_mismatch` | `5f002fd4` +92/-18 | yes: "correct six present-tense LVS counts left at 88" | 17 runs, 2 branches (#680, #733), 2026-10-27..2026-11-06 | none | keep |
| 37 | `check_campaign_census` | `2dee1750` +64/-17 | no correction indicated | none | none | candidate-to-retire |
| 38 | `check_extracted_dut_records` | `6df466a5` +1/-1 | no correction indicated | none | none | candidate-to-retire |

Notes on the table:

- Rows 1-5 share introducing commit `01154ef5`, and rows 7-8, 11-12 each share
  one, so a "correction indicated" flag on one is the commit's, not that
  check's alone.
- Rows 4+5 are one function. Its census message is check 6's text (`the
  stated pointer-claim census says`, `check_census`), so a `check_census` fire
  would be counted under row 6; neither fired.
- Rows 30-34 and 37-38 were reworked together on 2026-10-18 into
  `CensusSpec`-driven code (`72bd0ee7`). That refactor is upkeep, not a catch.

## 4. Tally (37 check functions)

| Disposition | Rows (by `Check N`) | Functions |
|---|---|---|
| `keep` | 1, 2, 3, 4+5, 11, 15, 17, 18, 19, 20, 21, 25, 26, 27, 28, 29, 32, 34, 36 | 19 |
| `candidate-to-retire` | 6, 7, 8, 9, 10, 12, 13, 14, 16, 22, 23, 24, 30, 31, 33, 35, 37, 38 | 18 |

19 + 18 = 37 functions.

Checks that fired in CI: 3, 15, 17, 18, 25, 26, 28, 32, 36 (9 functions). The
other 28 functions had no CI fire in the window above.

## 5. Limits of this evidence

- A check with no CI fire may be deterring drift, or may only ever fire in
  the PR that introduced it. This document cannot distinguish those.
- A CI fire is not classified as a human-would-have-missed stale citation (2b
  point 2).
- Introduction-time corrections are read off commit subjects only (2a).
- Replacement coverage is inferred, not tested (2c). Before any retirement
  proposal relies on a "covered by X" entry, the retirement proposal must show
  X failing on the same drift with the check removed.
- The `candidate-to-retire` label does not mean "should retire". The first
  step in a later proposal would be to pick one low-risk candidate, remove its
  call from `check_document` on a branch, and show which unit tests and
  which real drift (replayed from a pre-fix commit) go unnoticed.

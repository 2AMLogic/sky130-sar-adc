# Work Log

Merged pull requests and closed issues from the preceding 30 days. Entries record completion events, not signoff verdicts.

## Archives

- [2026-09](work_log/WORK_LOG_2026-09.md)

### 2026-11-27

- **PR #1106**: refactor(sim): add _usage_error() to the supply-impedance runner
- **Issue #1105** (closed): Consolidate 39 repeated CLI error returns in the supply-impedance runner

### 2026-11-26

- **PR #1097**: fix(sim): share executing-worker environment in klt_sim
- **Issue #1094** (closed): Consolidate executing-worker environment resolution across the 7 klt sim drivers onto klt_sim.py
- **PR #1098**: fix(sim): label fallback PDK/ngspice lines as the submitting host's
- **Issue #1096** (closed): run_testbench.py stamps "(executing worker)" on the submitting host's fallback PDK/ngspice lines

### 2026-11-25

- **PR #1090**: fix(sim): use the shared klt version probe for digital partition
- **Issue #1088** (closed): digital-partition record writer keeps its own klt client-version placeholder
- **PR #1087**: fix(sim): share klt --version probe in harness.klt_sim
- **Issue #1086** (closed): Share the klt client version probe so a missing executable cannot abort record rendering

### 2026-11-24

- **PR #1085**: refactor: remove dead --dr027-candidate helpers from settling runners
- **Issue #1084** (closed): Remove unused --dr027-candidate helpers and write-only _CODE_OF global in the settling runners
- **Issue #1075** (closed): Remove duplicated streamed SHA-256 file helpers in favor of harness.evidence.sha256_bytes_file
- **PR #1077**: refactor: dedupe streamed SHA-256 file helpers onto harness.evidence
- **Issue #1078** (closed): chore: gitignore the daemon runtime artifact .loom/account-ranking.codex
- **PR #1081**: chore: ignore .loom/account-ranking.* outside loom-managed block
- **PR #1074**: docs: reword the 2026-11-21 census note's clause as historical
- **Issue #1073** (closed): challenge-4-proposal: a "census above now states" clause re-drifted onto main after #1055 fixed the class
- **PR #1072**: refactor: fold the three PEX run_pex.py main()/klt-pex argv copies into pex_flow
- **Issue #1071** (closed): sim/ records cite per-corner ngspice.log files that are not committed (klt sim flow)
- **Issue #1069** (closed): Fold the three run_pex.py main()/klt-pex argv copies into pex_flow.py (copies have already drifted)
- **PR #1028**: signoff: declare item-5 analog spec rows and cite the comparator-noise klt sim envelope
- **PR #1068**: refactor: drop local pass-through wrappers in schematic-parity gates
- **Issue #930** (closed): Remove the three leftover pass-through wrappers in the two schematic-parity gates

### 2026-11-23

- **PR #1064**: fix: draw each GND mesh leg from the member pair it records
- **Issue #1063** (closed): GND mesh member check records hand-copied literals, so a call-site change can still drift
- **Issue #1034** (closed): Question for the operator: should the CDAC transfer campaign ever measure within-die DNL (shared-array testbench), given the cross-copy finding?
- **PR #1024**: Add cdac-array-transfer ff-corner PDK A/B diagnostic record ruling out the pin bump
- **Issue #1013** (closed): Isolate the ff_27c_1.80v 3e-5 V delta that parks #811 (klt sim batch vs baseline 20261001-120402-d24f700)
- **Issue #921** (closed): Remove GND_MESH_MEMBERS: a declared-but-never-read member list the mesh builder does not consult
- **PR #1062**: feat: assert GND_MESH_MEMBERS against the analog ground mesh's drawn legs
- **PR #1061**: pex: finish comparator pex_flow delegation, drop #1017 leftovers
- **PR #1060**: consolidate the last two private OAT request builders onto build_oat_request()
- **PR #1037**: signoff: bind the digital item-5 Resolution row to a klt sim envelope
- **PR #1057**: docs: reword stale census "now states" clauses as historical in challenge-4 proposal
- **PR #1056**: sim: consolidate the four private OAT klt sim request builders into harness klt_sim
- **Issue #917** (closed): Wire up or remove GND_MESH_MEMBERS: an inert declaration nothing reads
- **Issue #1059** (closed): Remove #1017 PEX extraction leftovers and finish comparator pex_flow delegation
- **Issue #1054** (closed): Consolidate the two remaining private OAT klt sim request builders (cdac-bit-trial-settling, sampling-cdac-handoff) onto klt_sim.build_oat_request()
- **Issue #1023** (closed): T1 item 5: bind the Resolution N row (sar-sequencer behavioral bench) to the digital partition's item 5 row set
- **Issue #1055** (closed): challenge-4 proposal: deck-census ledger double-counts issue #1023's two decks; "census above now states" clauses are stale
- **Issue #1052** (closed): Consolidate four copy-pasted OAT klt sim request builders into sim/harness/klt_sim.py
- **PR #1041**: sim: DR-027 candidate-plate settling/rate study and DRAFT sample-rate row verdict (3.3000 um)
- **Issue #1033** (closed): Re-derive the settling / sample-rate budget at the DR-027 array size (C_tot ~12.4 pF/side) against DR-006

### 2026-11-22

- **PR #1039**: fix(report): read plot data from the record each figure cites
- **PR #1042**: feat(layout): klt pex flows and OAT records for the analog sub-blocks (cdac_array, sampling_frontend, comparator)
- **PR #1026**: refactor: share acquisition waveforms and probe timing across deck builders
- **Issue #1035** (closed): Read plot data from the record each figure cites
- **Issue #1020** (closed): Share the two-pulse acquisition stimulus between the front-end and CDAC handoff runners
- **Issue #1017** (closed): T1 item 7 (analog): klt pex records for the LVS-matching analog sub-blocks (cdac_array, sampling_frontend, refreshed comparator)

### 2026-11-21

- **PR #1045**: ci: stop re-running required checks on PR label writes; move run-pdk-smoke opt-in to its own workflow
- **Issue #1043** (closed): ci.yml: every PR label write re-runs the full checks job, and the Judge claim label can starve a PR of review
- **Issue #1029** (closed): Remove the stale “entirely DRAFT” spec claim from VCM drive-budget records
- **PR #1038**: docs(sim): state VCM drive-budget campaign limits instead of blanket spec status
- **Issue #1030** (closed): Share SPICE fragment parsing between the reference-drive budget and input sweep
- **PR #1040**: refactor(sim): share the SPICE fragment split and save-set scan in harness.klt_sim

### 2026-11-20

- **Issue #1025** (closed as not planned): test
- **Issue #1015** (closed): T1 item 6: declare the statistical rows in spec_rows and cite the two freshness-pinnable klt yield envelopes
- **PR #1019**: feat: declare item-6 statistical rows and cite the two pinnable yield envelopes
- **PR #1011**: docs: point the summary-plot guide at the manifest instead of pinned record IDs
- **Issue #1010** (closed): Remove duplicate source-record pins from the summary plot guide

### 2026-11-19

- **Issue #869** (closed): Merge-sequencing deadlock: PR #788 and stacked child PR #798 block each other

### 2026-11-18

- **PR #1004**: ci: add the merge_group trigger and resolve the queue base/head for the append-only gate
- **Issue #1002** (closed): Merge queue: add the merge_group trigger and adapt the PR-metadata gates

### 2026-11-17

- **PR #999**: fix: reject unknown checks block keys at tb.json load
- **Issue #997** (closed): A typo in a tb.json spread *block key* name (min_spread_pct_by_axi) is still silently ungraded
- **PR #996**: fix: reject unknown spread-axis keys at tb.json load instead of silently ungrading
- **Issue #984** (closed): Spread-axis typo in a harness tb.json is silently ungraded (ported hole; fixed upstream in sky130-comparator)
- **PR #992**: Retire the #475 worktree.sh resync pin; accept upstream stale_ref fast-forward in the pushed-tip guard
- **Issue #990** (closed): Re-evaluate the .loom/resync-ignore pin on worktree.sh: upstream now resets against origin/<branch>, not BASE_REF
- **PR #994**: chore(loom): resync installed Loom to v0.19.1306

### 2026-11-16

- **PR #987**: remove write-only Row.spec_anchor field from report manifest
- **Issue #985** (closed): Remove or render write-only Row.spec_anchor in sim/report/manifest.py
- **PR #981**: refactor: drop seven never-read fields from comparator-campaign result dataclasses
- **Issue #977** (closed): Remove seven write-only dataclass fields in the comparator-decision campaigns
- **PR #980**: test: gate README/ROADMAP record citations against sim/*/records/LATEST
- **Issue #974** (closed): Guard the hand-kept 'newest record' pointers in README.md / docs/ROADMAP.md against sim/*/records/LATEST drift
- **PR #979**: fix(sim): attribute full-conversion runtime figures to committed corner logs
- **Issue #972** (closed): sim: two remaining "reference toolchain" runtime figures carry no hardware or date attribution
- **PR #978**: fix(sim): shape note withholds "reproduces" when the reference is censored
- **Issue #960** (closed): vcm-drive-budget: marginal_r_source_shape_note()'s exact-match branch claims figure-for-figure agreement with a right-censored reference value
- **PR #975**: refactor: drop write-only Draw.dnl_lsb/inl_lsb fields from cdac MC parser
- **Issue #971** (closed): Remove write-only Draw.dnl_lsb / Draw.inl_lsb fields from cdac-array-transfer run_mc.py
- **PR #970**: fix(sim): key fresh-run Claim bullet on the actual target limit
- **Issue #948** (closed): run_mc.py: fresh-run Claim bullet is not limit-keyed, so a non-default --target-limit-lsb mints a self-contradicting record

### 2026-11-15

- **PR #969**: docs: fix the #913 provenance-census entry's record total and stale census clause
- **Issue #964** (closed): Follow-on: Work identified in PR #949 — two stale figures in the proposal's provenance-census narrative
- **PR #967**: docs: attribute harness ngspice timing figures to their measured runner
- **Issue #958** (closed): sim/selftest.sh header's "~5 minutes / 15-20s per ngspice invocation" is ~4x slower than a measured pdk-smoke run
- **PR #966**: docs: retire finished rows from ROADMAP's Now table, bump the status stamp
- **Issue #961** (closed): docs/ROADMAP.md lists the already-finished README status refresh under "## Now"
- **PR #962**: test: catch a dropped `|| true` on `klt drc` in the flow-common self-test
- **Issue #940** (closed): test_flow_common.sh does not cover drc_blocks_fanout's `|| true` violation-tolerance guard
- **PR #955**: fix(sim): shape note no longer denies its exact-match identity claim or quotes a ratio over the legacy reference's censored span
- **Issue #905** (closed): vcm-drive-budget: marginal_r_source_shape_note()'s match branch denies the identity it just asserted, and its legacy reference quotes a ratio that record withheld
- **PR #949**: sim: converging-range input sweep as one klt sim request (--input-sweep)
- **Issue #913** (closed): sim: converging-range boundary sweep of the current architecture (DR-021 Open items)
- **PR #957**: docs: drop stale private-visibility note from proposal licensing bullet
- **Issue #953** (closed): challenge-4-proposal.md's 'README is stale' parenthetical is now itself stale (README was fixed by #936)
- **PR #956**: fix(check:ci): run the cheap check:* gates before the full sim selftest
- **Issue #925** (closed): check:ci: the full sim/selftest.sh now runs before 11 cheap gates, losing fast-fail on PDK hosts
- **PR #954**: harness: remove write-only CornerPointResult.log_path and PdkInfo.xschem_rc
- **Issue #945** (closed): Remove write-only CornerPointResult.log_path and PdkInfo.xschem_rc from the sim harness
- **PR #952**: docs: correct stale private-visibility claims in CLAUDE.md to public
- **Issue #937** (closed): CLAUDE.md still says the repo is private, after README was corrected
- **PR #951**: test(harness): key the sharded-envelope guard on AST structure, not accessor spellings
- **Issue #944** (closed): test(harness): sharded-envelope regex enumerates accessors — .pop("fleet") and .setdefault("fleet", []) still evade the guard
- **PR #947**: refactor: fold the drive-budget rule and ratified OAT corner-id list into shared harness helpers
- **Issue #939** (closed): Consolidate mirrored find_budget()/corner_ids() copies in the drive-budget drivers
- **PR #946**: refactor: drop write-only Citation.rel_path/kind fields
- **Issue #942** (closed): Remove write-only Citation.kind/rel_path fields in sim/report/generate.py
- **PR #941**: refactor: remove never-read BisectMcResult.draw_seeds property
- **Issue #926** (closed): Remove dead BisectMcResult.draw_seeds: a property no commit has ever read
- **PR #938**: sim: mint freshness-pinnable CDAC DNL/INL yield envelope; key target prose on the limit
- **Issue #912** (closed): Mint a CDAC DNL/INL klt yield envelope that names a committed samples file
- **PR #920**: refactor(layout): share the Row-1 PFET well-island floorplan
- **Issue #909** (closed): Fold the duplicated Row-1 PFET well-island floorplan into layout/bin/_geometry_common.py
- **PR #943**: test(sim): match the sharded-fleet-envelope read spelling-insensitively
- **Issue #918** (closed): test(harness): sharded-envelope guard matches three literal spellings, misses .get("fleet", default) and ['fleet']
- **PR #936**: docs: correct stale README status claims, guard the T1 count with a test
- **Issue #911** (closed): README status section is stale: "6 of 22 rows met", "Private for now", and a closed issue cited as open
- **PR #922**: refactor(layout): hoist run-flow preamble, DRC fan-out and record tail into _flow_common.sh
- **Issue #915** (closed): Finish the _flow_common.sh factoring: hoist the duplicated run-flow preamble, per-block DRC fan-out and record tail
- **PR #935**: ci: extract pinned ngspice+sky130-PDK provisioning into one composite action
- **Issue #875** (closed): Extract the ngspice + sky130 PDK provisioning copied into four ci.yml jobs into one composite action
- **PR #932**: fix(noise): print v(DIN) instead of asserting v(DIP)=v(DIN) unbacked
- **Issue #927** (closed): Remove NoiseResult.op_din_v, or print it: a measured op-point the record's v(DIP)=v(DIN) row never reads
- **PR #934**: refactor(sim): one harness reader for the three byte-identical klt sim corner-measurement readers
- **Issue #904** (closed): Consolidate the three byte-identical klt sim read_report bodies onto one harness helper
- **PR #933**: fix(harness): accept only error envelopes from the klt stderr scan
- **Issue #898** (closed): harness/klt_sim: envelope_from_stderr accepts any JSON dict, so a non-envelope object on stderr could be cached as a report

### 2026-11-14

- **PR #923**: test: consolidate the 13 inline resolve_provenance stubs onto one fixture
- **Issue #914** (closed): Consolidate the 13 copied evidence.resolve_provenance stubs in sim/tests onto one shared fixture
- **PR #910**: docs: roadmap as of 2026-11-13
- **Issue #889** (closed): check:ci runs the full sim/tests unit suite twice: once via npm run test, again as sim/selftest.sh stage 1
- **PR #919**: refactor(check:ci): reach the sim/tests unit suite once, via selftest stage 1
- **Issue #908** (closed): Guide docs-PR template claims work_log/ archive rotations qualify for the docs-only fast path; the allowlist is three exact root filenames
- **Issue #888** (closed): Put digital-partition's run-info read on harness.klt_sim.run_info(): its private copy makes runner_skew() blind to sharded reports
- **PR #916**: refactor(digital-partition): read run info through harness.run_info() so version skew is seen on every shard
- **Issue #894** (closed): vcm-drive-budget: full-grid records carry fixed-text sentences their own data and sibling records contradict
- **PR #902**: fix(vcm-drive-budget): derive record interpretation sentences from the data
- **Issue #884** (closed): Remove dead npm script worktree:return: its target .loom/scripts/worktree-return.sh does not exist
- **PR #901**: chore: drop dangling worktree:return npm script
- **Issue #877** (closed): Remove dead parse_ac_print() and two other unread leftovers in sim drivers
- **PR #899**: refactor: drop three unread leftovers from the sim drivers
- **Issue #895** (closed): Remove 13 unused imports flagged by ruff F401 in supply_impedance common.py and three sim tests
- **PR #900**: chore: drop 13 unused imports from sim campaign common and three tests
- **Issue #892** (closed): harness/klt_sim: a klt error envelope behind a warning line on stderr is misreported, and defeats capacity-retry
- **PR #897**: fix(harness): scan klt stderr for the error envelope instead of parsing it whole

### 2026-11-13

- **Issue #891** (closed): vcm-drive-budget: the full-grid record states "not corner-invariant" even when the spread it just printed is 1.0x
- **PR #893**: sim: run the vcm-drive-budget PVT grid as one klt sim request
- **Issue #881** (closed): vcm-drive-budget: port --corners to klt sim and re-mint the four full-grid records after #874
- **Issue #879** (closed): test: the decision-margin and sequencer-port netlist-shape guards have no test in either direction
- **PR #883**: test: cover both netlist-shape guards on synthetic netlists
- **Issue #880** (closed): vcm-drive-budget: mint superseding records after #874 and restate text citing the old '<= 0 ohm' / '9 of 9 rescued' wording
- **PR #885**: docs(challenge-4): restate vcm rescue counts under the post-#874 convention
- **Issue #882** (closed): vcm-drive-budget: two record notes overclaim — ">= X pF" on the single-corner path and an unchecked "reproduces the single-corner record"
- **PR #886**: fix(vcm-drive-budget): drop the ">= X pF" claim and check tt/seed agreement before saying "reproduces"
- **Issue #873** (closed): bug: --mechanism-probe's delayed-strobe variant refuses against the committed netlist, and no test covers the guard
- **PR #878**: refactor: retire --mechanism-probe from the full-conversion runner
- **Issue #874** (closed): vcm-drive-budget: find_budget() can never return None — the 'none found'/'unrescued' branches are dead and the rescue verdict cannot fail
- **PR #876**: fix(vcm-drive-budget): exclude the control row so find_budget() can report "none found"
- **Issue #854** (closed): Fold the 10 copy-pasted toolchain SKIP/FAIL gates in sim drivers into one harness helper (two copies drop warnings)
- **PR #868**: refactor(sim): fold ten inline toolchain gates into toolchain.preflight()
- **Issue #861** (closed): Split the 4.7k-line run_conversion.py into per-campaign modules behind the existing CLI
- **PR #872**: refactor(sim): split run_conversion.py into per-campaign modules behind the same CLI
- **Issue #865** (closed): Consolidate four copy-pasted klt sim submit blocks (three different fleet-capacity policies) into one sim/harness helper
- **PR #870**: refactor(sim): one klt_sim submit helper for the four batch campaign drivers
- **Issue #860** (closed): Consolidate three xschem netlisting helpers with conflicting exit-code policies onto toolchain.netlist_with_xschem()
- **PR #867**: refactor(sim): one xschem exit-code policy on netlist_with_xschem()
- **Issue #859** (closed): Consolidate four hand-rolled PDK-root lookups onto sim/harness/pdk.resolve()
- **PR #866**: refactor: route four PDK-root lookups through sim/harness/pdk.resolve()
- **Issue #862** (closed): sim/README.md does not list the sim/input-drive-budget campaign
- **PR #864**: docs(sim): list the input-drive-budget campaign in sim/README.md
- **Issue #847** (closed): sim: no campaign puts a source impedance on VINP/VINN — input-drive-impedance budget
- **PR #857**: sim: add a VINP/VINN source-impedance budget campaign and record it at 9 corners
- **Issue #841** (closed): sim: no campaign puts a drive impedance on VREFP/VREFN — reference-drive-impedance budget
- **PR #856**: sim: measure the VREFP/VREFN series drive-resistance budget per PVT corner
- **Issue #848** (closed): Split the 5.8k-line run_supply_impedance.py into per-campaign modules behind the existing CLI
- **PR #858**: refactor(sim): split run_supply_impedance.py into per-campaign modules
- **Issue #839** (closed): spec: no pad carries a declared special requirement — Challenge #4's I/O list asks for them (e.g. low resistance to the pad)
- **PR #849**: docs(chipalooza): declare per-pad special requirements against get-involved.html
- **Issue #851** (closed): Dedupe the verdict-checklist, block-table, DRC-coverage and LVS-count sections copied across the strict layout render-record.py scripts
- **PR #855**: refactor: hoist five duplicated record sections into _record_common_strict
- **Issue #835** (closed): sim: no result is summarized in a plot — Challenge #4 asks for plots, not raw data
- **PR #840**: feat(sim): render summary plots of committed evidence into docs/plots/
- **Issue #850** (closed): Dedupe the instance-compare/report core duplicated across the top-glue and sar-sequencer check-schematic-parity scripts
- **PR #853**: refactor(layout): share one instance-compare core between the two std-cell parity gates
- **Issue #845** (closed): Fold sampling-frontend's local _step_down_to_met1 / pfet_params copies into the shared layout/bin helpers
- **PR #852**: refactor(layout): drop sampling-frontend's duplicate step-down and FET param helpers
- **Issue #838** (closed): Remove 9 defined-but-never-read module constants across layout/ and sim/ drivers
- **PR #846**: refactor: delete 9 unread module constants from layout and sim drivers
- **Issue #833** (closed): Consolidate duplicated SHA-256 file-hash helpers onto evidence.sha256_bytes_file
- **PR #837**: docs(chipalooza): reconcile rules-4.html's proposal, repository and AI clauses

### 2026-11-12

- **PR #831**: Bump Repo Skills 0.25.10 -> 0.26.1

### 2026-11-10

- **PR #828**: docs: record freeze on new citation-checker check_* functions
- **Issue #820** (closed): Simplify: citation gate for challenge-4-proposal is ~16k lines guarding one doc
- **PR #826**: docs: reconcile proposal slot budget with published rules-4.html

### 2026-11-07

- **PR #822**: Bump Repo Skills 0.25.1 -> 0.25.10
- **PR #821**: chore: drop unused subprocess import from test_evidence_store
- **Issue #817** (closed): Remove redundant imports in two SDF testbenches and test_evidence_store.py

### 2026-11-06

- **PR #819**: sim: replay old netlist snapshots at the f6eeac7 pin to isolate PDK effect
- **Issue #814** (closed): sim: #810 re-runs show deltas that are not like-for-like (design changed since old records)
- **PR #815**: sim: re-run local-slice records under open_pdks f6eeac7 as superseding records
- **Issue #810** (closed): Re-run local single-corner/analytic sim records under open_pdks f6eeac7 as superseding records (#709 split)
- **PR #812**: sim: record klt sim batch route probe for cdac-array-transfer under a 0.9.0 client
- **PR #809**: refactor: reuse sha256_bytes_file in digital_area, rename wrapper sha256_prefixed
- **Issue #805** (closed): Consolidate duplicated streaming-SHA-256 helpers; stop reusing the name sha256_file for three contracts
- **PR #808**: feat: mint n=40 ENOB yield envelope and derive yield pin hint from requirements
- **Issue #803** (closed): Mint the missing ENOB klt yield envelope now that klt-yield-native 0.1.0 is on PyPI
- **PR #807**: feat: klt sim request and envelope comparator for CDAC transfer bench (pilot NOT RUN: runner mismatch)
- **Issue #564** (closed): Pilot: express one PVT corner campaign as a klt sim request (first klt sim envelope)
- **PR #806**: chore: remove retired seln-inverters flow and fix stale consumer claims
- **Issue #782** (closed): Remove retired seln-inverters run flow and fix its false 'still consumed' header
- **PR #804**: docs: add citation-gate per-check drift evidence and replacement coverage
- **Issue #588** (closed): Simplify the Chipalooza proposal citation gate: ~16k lines of checker, tests and rationale guard one prose document
- **PR #802**: refactor: share pin-order cache resolver between schematic-parity checks
- **Issue #801** (closed): Dedupe resolve_pin_orders/_cdl_text_if_available duplicated across two check-schematic-parity scripts
- **Issue #658** (closed): Refresh stale tracker #23 body to point at signoff/t1-report.json instead of the 2026-08-15 analog/10-item table

### 2026-11-05

- **PR #797**: refactor(sim): remove unused record_path locals in sim drivers
- **Issue #795** (closed): chore(sim): drop dead record_path locals left by close_record() adoption
- **PR #794**: refactor(sim): route record-closing tails through evidence.close_record()
- **Issue #791** (closed): Adopt evidence.close_record() in sim drivers: ~19 hand-rolled record closers
- **PR #793**: refactor(sim): share one binary-safe file-hash helper across digital run drivers
- **Issue #789** (closed): Dedup byte-identical sha() file-hash helpers in digital sim run drivers
- **PR #786**: fix(layout): widen sampling-frontend-wells via1 pads for adjacent enclosure
- **Issue #783** (closed): layout: sampling-frontend-wells via-enclosure DRC (51 met1/met2 enclosing_adjacent.via.1) under the new klt deck
- **Issue #780** (closed): Bump klayout-tools pin 0.6.0 → 0.8.0

### 2026-11-04

- **PR #776**: feat: report per-corner gain and corrected-code error in full-conversion record
- **PR #763**: docs: propose CDAC gain-error closure path (DR-025)
- **Issue #755** (closed): design: close or supersede the CDAC gain-error miss (DR-022 options a-d or looser-value DR)

### 2026-11-03

- **PR #681**: feat(signoff): bind T1 items 1, 2, 9, 10 to audited artifacts; add sequencer parity check
- **Issue #676** (closed): Bind T1 items 1, 2, 9 and 10 to audited artifacts (both partitions) with artifact-anchored envelopes

### 2026-11-01

- **PR #766**: refactor: share parse_corner_id and pwl helpers via sim/harness
- **Issue #764** (closed): Dedupe corner-id and pwl helpers in sim drivers (use sim/harness/corner helpers)
- **PR #758**: docs(DR-022): record post-#722 status and file open items
- **Issue #753** (closed): spec: record DR-022 post-#722 status and file its open items
- **PR #761**: sim: measure CDAC top-plate C_par composition per PVT and MiM r+c corner
- **Issue #754** (closed): sim: measure CDAC top-plate C_par composition per corner (C(V) extraction, incl. r+c corners)
- **Issue #756** (closed): sim: CDAC gain error, mismatch half (Monte Carlo check of analytic 1.42 LSB 3-sigma)
- **PR #759**: sim: add CDAC mismatch gain-error reanalysis and record
- **PR #722**: spec(DR-022): add DRAFT systematic gain-error row as the ratification vehicle
- **Issue #269** (closed): design: CDAC absolute gain error (~1%) from top-plate parasitic loading -- the array's unit cap is smaller than the parasitic it drives
- **PR #747**: sim: SDF-annotated post-route functional verification for digital partition (T1 item 7)
- **Issue #679** (closed): Digital partition, item 7: re-run the functional suite on the post-route netlists with back-annotated SDF

### 2026-10-31

- **PR #748**: Bump Repo Skills 0.24.7 -> 0.25.1

### 2026-10-29

- **PR #683**: feat: digital partition STA and functional-verification evidence for T1 item 5
- **Issue #678** (closed): Digital partition, item 5: multi-corner klt sta plus a bit-exact klt functional-verification suite
- **Issue #351** (closed): README: embed the fleet burndown chart (one line)

### 2026-10-27

- **PR #728**: chore(deps): bump klayout-tools signoff/ERC/yield pins to 0.8.0
- **Issue #727** (closed): Bump klayout-tools pin 0.6.0, 0.7.0 → 0.8.0
- **PR #739**: fix: widen met2 pads at via2 cuts to clear via2.5 enclosure
- **Issue #738** (closed): Fix or disposition met2.enclosing_adjacent.via2.1 drawn geometry (klt 0.8.0 via2.5)
- **PR #736**: fix(layout): widen via1 landing pads to clear klt 0.8.0 via.5a/m2.5
- **Issue #733** (closed): klt 0.8.0 triage: fix or record drawn-geometry DRC families (via.5a, m2.5, poly.8, via3.width)
- **PR #735**: docs: record via2.5 as a met2 rule and the drawn-geometry disposition
- **Issue #732** (closed): klt 0.8.0 triage: resolve met2.enclosing_adjacent.via2.1 rule target (DRM vs deck)
- **PR #730**: docs: triage klt 0.8.0 DRC families on top-level streams; hold pin at 0.6.0

### 2026-10-23

- **PR #718**: feat: store new corner-run evidence via klt artifact, commit only manifests
- **Issue #717** (closed): Adopt the common artifact store for sim evidence (manifests in git, bytes via klt artifact)

### 2026-10-21

- **PR #710**: layout: re-run sign-off flows under open_pdks f6eeac7 as new reports
- **Issue #708** (closed): Re-qualify layout sign-off reports under open_pdks f6eeac7 (#670 split)
- **PR #530**: docs(spec): DR-022 proposes a systematic gain-error spec row instead of resizing the CDAC or comparator
- **PR #703**: Bump Repo Skills 0.24.3 -> 0.24.7
- **PR #707**: refactor: share Stimulus and Netlist-provenance record bullets via helpers
- **Issue #705** (closed): Dedup Stimulus/Netlist-provenance prose copied across run_supply_impedance.py record writers

### 2026-10-20

- **PR #671**: build: re-pin open_pdks to f6eeac7 (ciel) and verify PDK SOURCES revision
- **Issue #669** (closed): Re-pin open_pdks to f6eeac7 + ciel 2.6.1 + revision-checked PDK search (#668 phase 1)
- **Issue #629** (closed): Dedupe repeated testbench entries in the generated spec-coverage index

### 2026-10-18

- **PR #694**: refactor: drive checks 30-34 from one table-driven census checker
- **Issue #688** (closed): Dedupe repeated census checks in check_proposal_citations.py
- **PR #692**: layout: declare the BOOST_P/BOOST_N n-wells as ERC ties, re-mint ERC record (2 -> 0 findings)
- **Issue #684** (closed): ERC: 2 n-wells flagged erc.missing_tie by both ties[] entries (no tap on VDD or VPWR)

### 2026-10-17

- **PR #690**: layout: grade n-well ties per rail with the std-cell marker on klt 0.7.0, re-mint sar-adc-top ERC record (28 -> 2 findings)
- **Issue #685** (closed): ERC: per-rail well selector for the n-well ties[] (24 cross-domain erc.missing_tie flags)
- **PR #686**: docs(layout): classify the two both-flagged n-wells as BOOST_P/BOOST_N-tied
- **PR #682**: layout(sar-adc-top): declare n-well ties[] in the ERC supply spec and compute erc.missing_tie
- **Issue #677** (closed): Item 11: declare ties[] in the top-level ERC supply spec now that klayout-tools#2169 is fixed

### 2026-10-16

- **PR #673**: Bump Repo Skills 0.24.1 -> 0.24.3

### 2026-10-15

- **PR #664**: docs(proposal): record #2722 closure and 2026-10-14 hierarchical-LVS probes
- **PR #663**: Bump Repo Skills 0.19.5 -> 0.24.1

### 2026-10-14

- **PR #662**: layout(sar-adc-top): re-run hierarchical-LVS probe on newer klt -- GND/VGND merge still the only blocker (#103)
- **PR #660**: layout(sar-adc-top): hierarchical extract measured -- LVS mismatch is DR-012's merge (Part of #103)

### 2026-10-13

- **PR #659**: fix(signoff): verify lvs environment digests even when an input hash is present
- **Issue #657** (closed): signoff README: item 4 'missing pin' premise (klt 0.5.0 null provenance) contradicts the cited 0.6.0 lvs.json

### 2026-10-12

- **PR #655**: layout: export PDK=sky130A in flow scripts
- **PR #653**: docs: evaluate klayout-tools 0.7.0 against pinned 0.6.0 (no bump)
- **PR #651**: refactor(layout): fold shared P&R/DRC/LVS pipeline into run_pnr_drc_lvs_flow
- **PR #650**: layout: retire erc-requirements.txt, run ERC on the DRC/LVS venv (#648)
- **Issue #652** (closed): Flow scripts rely on ambient $PDK=sky130A; a shell without it makes klt resolve a gf180mcu PDK
- **Issue #649** (closed): Evaluate klayout-tools 0.7.0 against the pinned 0.6.0 grader before the next pin bump
- **Issue #648** (closed): Retire layout/erc-requirements.txt: the second klt pin's 0.5.0 premise no longer holds
- **Issue #647** (closed): Dedupe P&R flow scaffolding shared by sar-sequencer, seln-inverters, top-glue run-flow.sh

### 2026-10-11

- **PR #644**: docs(claude): check interpretations against raw results before review
- **PR #643**: Consolidate klt-precheck helpers in render-record scripts
- **PR #641**: Re-mint full-conversion reference campaign and coherent-sine capture under the DR-023 solver policy
- **PR #639**: sim: named full-conversion solver policy, DC solver audit, and DR-023
- **PR #636**: sim: root-cause coherent-sine conversion 9 (solver artefact) + switching diagnostics
- **Issue #640** (closed): Auditor process pattern: verify evidence interpretations against raw results before review
- **Issue #642** (closed): Consolidate klt-precheck helpers in render-record scripts; two copies read the wrong key
- **Issue #638** (closed): Re-mint the full-conversion reference campaign and coherent-sine capture under the DR-023 solver policy
- **Issue #637** (closed): Harness: default ngspice solver settings produced a spurious register flip; audit transient evidence
- **Issue #632** (closed): Auditor guard decision: keep stash-scope:create-redirect; use worktree stash wrappers

### 2026-10-10

- **PR #634**: docs(signoff): scope item 7 no-pex claim (#633)
- **Issue #633** (closed): signoff/README: item 7 says no klt pex report exists, but three comparator pex envelopes do
- **PR #631**: sim: conversion-9 trace in the coherent-sine run + new record (Part of #621)
- **PR #630**: chore: remove unused imports (ruff F401)
- **Issue #624** (closed): Remove 10 unused imports flagged by ruff F401 (L_MET3/L_MET4 regression, test files)
- **PR #627**: Characterize the digital partition: Fmax bracket, rail power, routed area (#619)
- **Issue #619** (closed): Characterize the digital partition: measured frequency limit, rail power and routed area
- **PR #626**: Pin klt yield toolchain; refresh Item 6 narrative (#625)
- **Issue #625** (closed): Mint klt yield envelopes from the persisted item-6 samples and pin the yield toolchain
- **PR #623**: Coherent-sine per-code outlier diagnostic (#621, partial)
- **PR #620**: Mint first pinned-toolchain coherent-sine ENOB record via manual CI dispatch (#605)
- **Issue #605** (closed): Mint the first --coherent-sine ENOB record on a pinned (ngspice >= 46) toolchain
- **PR #618**: test: pin sweep-checkpoint write confinement as intended behavior (#615)
- **Issue #615** (closed): Guard telemetry: routine sweep checkpoint writes blocked by worktree-write-confinement
- **PR #617**: test: unit tests for _record_common_strict and _gen_common (#612)
- **Issue #612** (closed): Add PDK-free unit tests for strict layout record and generator helpers
- **PR #614**: refactor: split comparator-decision run.py into per-campaign modules (#613)
- **Issue #613** (closed): Split the 4.5k-line sim/comparator-decision/run.py into per-campaign modules behind a thin CLI
- **PR #611**: test: PDK-free exit-code tests for harness cli and mc_cli
- **Issue #604** (closed): test: PDK-free exit-code tests for sim/harness/cli.py and mc_cli.py (entry points with zero tests)
- **Issue #600** (closed): Guard telemetry: investigate scoped path resolution for worktree-write-confinement-unresolved-var

### 2026-10-09

- **PR #608**: CI gate: mechanically enforce the append-only rule for sim/ evidence (#599)
- **Issue #599** (closed): CI gate: mechanically enforce the append-only rule for sim/ evidence records
- **PR #606**: Coherent-sine FFT SNDR/ENOB mode for the full-conversion transient (#603)
- **Issue #603** (closed): Dynamic coherent-tone ENOB from the full-conversion transient (replace the behavioral-only estimate)
- **PR #601**: test: PDK-free unit tests for _lvs_reference_common.py
- **Issue #598** (closed): test: PDK-free unit tests for layout/bin/_lvs_reference_common.py (shared by five LVS-reference and parity callers, zero tests)
- **PR #597**: CI: pin volare in the pdk-smoke job
- **Issue #596** (closed): CI: pin volare in the pdk-smoke job (the one unpinned link in the toolchain chain)
- **PR #594**: test: PDK-free deck-builder tests for three more sim runners (#593)
- **Issue #593** (closed): test: PDK-free deck-builder tests for cdac-array-transfer, sampling-acquisition-settling and comparator-decision kickback/pickoff/noise decks (follow-on to #591)
- **PR #592**: test: PDK-free deck-builder tests for four sim runners
- **Issue #591** (closed): test: PDK-free deck-builder tests for four untested sim runners (bit-trial, sequencer-delay, vcm-drive, sampling-frontend transient)

### 2026-10-08

- **PR #589**: ENOB yield: per-draw conditional estimates from real CDAC draws (#587)
- **Issue #587** (closed): ENOB yield: derive conditional estimates per real CDAC draw instead of grading two summaries
- **PR #586**: docs(t1-gap): reduce item-11 row to a pointer
- **Issue #583** (closed): docs/t1-gap.md: item-11 row is a 3 KB hand-kept status cell the file's own preamble disclaims
- **PR #585**: lint: discover shell scripts for bash -n (4 unchecked)
- **Issue #582** (closed): lint: discover shell scripts for bash -n instead of a hand-maintained list (4 scripts unchecked)
- **PR #581**: docs(signoff): align layout/LVS/ERC narrative with manifest-selected October evidence
- **Issue #579** (closed): Align signoff layout, LVS and ERC narrative with manifest-selected October evidence
- **PR #578**: refactor(sim): shared corner-sweep iterator in harness.corners (#576)
- **Issue #576** (closed): Extract the shared corner-sweep loop from five sim drivers into harness.corners
- **PR #574**: fix(sim): reject non-finite SPICE measurements before conversion verdicts
- **PR #575**: docs(report): refresh superseded layout and whole-ADC limitations (#572)
- **PR #571**: refactor(sim): centralize ratified corner-set constants (#546)
- **PR #570**: docs: freeze citation gate at 38 checks
- **PR #567**: Persist klt yield samples document beside report
- **Issue #573** (closed): Render unavailable power (power_w=None) as n/a in supply-impedance records
- **Issue #569** (closed): Reject non-finite SPICE measurements before conversion verdicts
- **Issue #572** (closed): Refresh superseded layout and whole-ADC limitations in characterization narrative
- **Issue #546** (closed): Dedup SUPPLY_TOLERANCE/TEMPS_C/PROCESS_CORNERS constants copied across 9 sim drivers
- **Issue #543** (closed): Freeze or trim the proposal-citation gate: ~16k lines guarding one document
- **Issue #561** (closed): Refine S3 download-to-stdout classification
- **Issue #563** (closed): Persist klt yield samples document so item-6 yield envelopes are freshness-pinnable
- **PR #565**: docs: refresh README status against current evidence
- **Issue #560** (closed): docs: refresh README status against existing layout, conversion and ratified spec evidence

### 2026-10-07

- **PR #559**: test: PDK-free unit tests for sar-sequencer-behavioral runner
- **Issue #557** (closed): test: add PDK-free unit tests for sar-sequencer-behavioral runner

### 2026-10-07

- **PR #553**: ci: run on GitHub-hosted runners; the shared self-hosted runner is retired
- **PR #554**: docs(chipalooza): record #103/klayout-tools#2722 state as of 2026-10-07 in §7 Item 1 (Part of #121)

### 2026-10-05

- **Issue #483** (closed): Dedup guard/compare/miss-message shape across 6 check_*_census functions in check_proposal_citations.py
- **PR #552**: refactor: share census numeric-field comparison helper (#483)

### 2026-10-04

- **PR #551**: docs(chipalooza): record epic #25 and #31 as closed in proposal roll-up pointers

### 2026-10-03

- **Issue #267** (closed): Architecture-level fix for large-differential-input (±0.78·V_REF) common-mode saturation (confirmed, issue #265)
- **Issue #342** (closed): loom-fleet-dispatch: blocked<->issue re-check flip-flops on #103 despite unchanged live blocker state
- **Issue #448** (closed): sim: mint the supply-impedance record for DR-016's shipped decoupling value -- the MF=2 package arm outruns this host's per-process budget
- **Issue #518** (closed): Remove unused imports: L_MET3, L_MET4 in layout/halflsb-offset/bin/build_layout.py
- **Issue #524** (closed): Comparator offset: bisect the decision boundary per Monte Carlo draw, for a precise random-offset sigma
- **Issue #525** (closed): Comparator offset/dead band: replicate the offset-bisect measurement post-layout, once comparator PEX exists
- **Issue #528** (closed): docs(chipalooza): §4 pointerless-flow prose states stale record counts for comparator-decision and cdac-array-transfer
- **PR #526**: spec: DR-021 recommends common-mode-neutral CDAC switching for near-full-scale droop (#267)
- **PR #527**: docs(chipalooza): re-file check 37, the sim/ campaign-citation census (issue #121)
- **PR #529**: layout: sar-adc-top abstract-cells LVS match on klt with #2396/#2398 fixes (Part of #103)
- **PR #531**: docs(chipalooza): record #103's unparking and PR #529's unreleased-klt abstract-cells match
- **PR #532**: docs(chipalooza): re-derive pointerless-flow prose counts and per-record claims (issue #121)
- **PR #533**: feat(sim): post-layout extracted DUT for offset-bisect (#525, part 1)
- **PR #534**: layout: re-measure sar-adc-top on post-#2396/#2398 klt; halflsb grid snap (#103)
- **PR #535**: docs(chipalooza): extracted-DUT offset-bisect harness is capability, not evidence (check 38)
- **PR #536**: Comparator offset: per-draw boundary bisection (offset-bisect-mc) + N=3 smoke record (#524)
- **PR #537**: docs(chipalooza): de-stale §7 Item 8 -- #267/#269 no longer operator-decision; cite the current full-conversion record
- **PR #538**: docs(chipalooza): re-check rules-4.html 2026-10-03, record index republish and challenge-4.html stub (issue #121)
- **PR #539**: Comparator offset-bisect post-layout replication on PEX netlist (#525)
- **PR #540**: spec(DR-021): name the #267-closing PR as DR-021's ratification vehicle
- **PR #541**: docs(layout): re-point sar-adc-top LVS blocker at klayout-tools#2722 (issue #103)
- **PR #542**: docs(chipalooza): note DR-021 ratification-vehicle amendment (Part of #121)
- **PR #544**: docs(chipalooza): re-point flat-compare tracker note at klayout-tools#2722 (Part of #121)
- **PR #545**: docs(chipalooza): de-stale comparator-decision record census and offset axis (Part of #121)
- **PR #547**: docs(chipalooza): restate #267 as closed via PR #540, DR-021 still proposed (Part of #121)
- **PR #548**: docs(DR-017): erratum retiring stale #448 pending pointers
- **PR #549**: docs(chipalooza): note DR-017 #448 erratum in pointerless-carrier clause (Part of #121)
- **PR #550**: docs(chipalooza): record #103's return to loom:blocked on klayout-tools#2722 (Part of #121)

### 2026-10-02

- **Issue #509** (closed): signoff envelope and manifest Row.status mis-attribute the statistical rows' grading target to DR-007's candidates
- **Issue #511** (closed): layout/sar-adc-top/README.md: 'Why the mesh needs an ablation' still reports the pre-#401 2-island ablated readout
- **Issue #513** (closed): sim/: two runners' Supersedes pointer is hardcoded in source, so a re-run must edit code to re-aim it
- **Issue #515** (closed): Comparator: post-layout decision-polarity findings from sky130-comparator (methodology + two measurements)
- **Issue #517** (closed): layout/sar-adc-top/README.md: 'The analog ground pad (#362) and mesh (#377)' section still describes a three-legged mesh
- **Issue #520** (closed): layout/sar-adc-top/bin/build_layout.py: analog_ground_mesh()'s own docstring still describes a three-legged mesh
- **PR #514**: fix(signoff): correct envelope _comment's claim about which targets ENOB/INL-DNL grade
- **PR #516**: docs(sar-adc-top): restate the ground-mesh ablation from the current 3-island record
- **PR #519**: docs(sar-adc-top): restate the analog ground mesh as four-legged, from the script and record
- **PR #521**: feat(sim): make both hardcoded Supersedes pointers a --supersedes default
- **PR #522**: docs(sar-adc-top): restate analog_ground_mesh docstring as four-legged
- **PR #523**: Comparator offset-bisect: separate the systematic decision offset from a dead band, and DR-020 declining both spec rows

### 2026-10-01

- **Issue #354** (closed): CI stuck queued on the self-hosted 'heavy' runner — 50+ min with no job start
- **Issue #387** (closed): layout/sar-adc-top: the composed GDS and its LVS reference still implement issue #56's DR-008-superseded top-level glue
- **Issue #401** (closed): layout/sar-adc-top: re-compose the top level against the current schematic and re-derive its LVS reference
- **Issue #426** (closed): Loom's setup-branch-protection.sh splits comma-bearing required-check names, which would block every merge
- **Issue #439** (closed): merge-pr.sh's partial-increment reset silently no-ops on a backtick-wrapped 'Part of #N' trailer
- **Issue #496** (closed): spec: is a 1898 nm MiM plate acceptable? the unit cap cannot satisfy sky130's 5 nm manufacturing grid
- **Issue #498** (closed): Carry DR-019's grid-legal C_u resize (1.8988 -> 1.9000 um) through design/cdac, layout/cdac-array, layout/halflsb-offset
- **Issue #501** (closed): layout/sar-adc-top: re-compose the top level against DR-019's resized cdac_array / halflsb_offset
- **Issue #502** (closed): sim/: four campaign runners cannot express Supersedes, so a stale citation of them is undetectable
- **Issue #504** (closed): sim/spec-coverage.json's Sampling-cap note still states the superseded pre-DR-019 C_u (8.65 fF) as ratified
- **Issue #505** (closed): sim/report/manifest.py's ENOB row cites a pre-DR-019 record and grades against the DRAFT >9.0 row, not DR-007's candidate
- **Issue #506** (closed): sim/spec-coverage.json's ENOB and INL/DNL notes state the pre-DR-007 draft targets (>9.0/>9.5 bit, +-1 LSB) as the current DRAFT targets
- **PR #499**: spec: DR-019 resizes CDAC unit cap to a 5 nm-grid-legal plate (1.9000 um)
- **PR #500**: layout/sar-adc-top: re-compose the top level against the current schematic and re-derive its LVS reference
- **PR #503**: Carry DR-019's grid-legal C_u resize (1.8988 -> 1.9000 um) through design, layout and sim
- **PR #507**: docs(sim): correct spec-coverage Sampling-cap note to post-DR-019 C_u
- **PR #508**: docs(report): record the ENOB row's pre-DR-019 citation drift instead of re-pointing it
- **PR #510**: layout(sar-adc-top): re-compose the top level against DR-019's resized sub-blocks
- **PR #512**: feat(sim): let every evidence-writing runner declare Supersedes, and gate it

### 2026-09-30

- **Issue #338** (closed): CI: gate the metal minimum-area measurement so a new isolated sub-minimum pad cannot land silently
- **Issue #495** (closed): layout/halflsb-offset: DR-009's 8-primitive half-LSB offset network has no drawn geometry
- **PR #124**: fix(ratification): remove unwrapped private-repo reference from market-key/SKILL.md
- **PR #343**: ci: gate the metal minimum-area measurement in the PDK-smoke job
- **PR #402**: feat(layout): lay out the current top-level glue bank and gate it against the schematic
- **PR #497**: layout/halflsb-offset: draw DR-009's 8-primitive half-LSB offset network (DRC-clean, LVS-clean)

### 2026-09-29

- **Issue #493** (closed): Dedup render-record.py markdown sections shared by comparator/sampling-frontend/sampling-frontend-wells
- **PR #494**: Dedup render-record.py markdown sections shared by comparator/sampling-frontend/sampling-frontend-wells

### 2026-09-28

- **Issue #474** (closed): Dedup klt-version/pdk-info provenance fetch across three strict render-record.py scripts
- **Issue #488** (closed): Remove unused, pin-bypassing npm script: package.json's check:signoff
- **Issue #491** (closed): Remove unused extra_meas parameter in run_hold_kick.py's build_transient()
- **PR #489**: chore: remove unused, pin-bypassing check:signoff npm script
- **PR #490**: Dedup klt-version/pdk-info provenance fetch into _record_common_strict
- **PR #492**: refactor: drop unused extra_meas parameter from hold-kick build_transient()

### 2026-09-27

- **Issue #477** (closed): Remove unused variable in build_layout.py's via4-landing check
- **Issue #478** (closed): Primary checkout carries an uncommitted, stale-base Loom resync (18 files, main 43 behind origin/main)
- **Issue #482** (closed): Dedup records/LATEST pointer-write across eight sim/*/run_*.py drivers
- **Issue #486** (closed): Dedup sim/supply-impedance-sensitivity/run_supply_impedance.py's four record-writer table blocks
- **PR #484**: Remove unused variable in build_layout.py's via4-landing check
- **PR #485**: refactor(sim): fold the records/LATEST pointer write into evidence.write_latest_pointer()
- **PR #487**: refactor(#486): dedup run_supply_impedance.py's four record-writer table blocks

### 2026-09-26

- **Issue #409** (closed): Supply-return impedance sensitivity: full PVT grid, no-gnd-pad price, R/L sweep, extracted substrate network all deferred by #378
- **Issue #431** (closed): design: size on-die supply decoupling -- #378 measured 129-259 mV die-ground bounce with the GND pad bonded
- **Issue #440** (closed): layout: place DR-016's two per-domain decoupling caps in layout/sar-adc-top/ and re-verify DRC/LVS/ERC
- **Issue #450** (closed): Citation gate: nothing grades §7 Item 11's excursion-figure enumeration for completeness
- **Issue #453** (closed): spec: DR-017 names the wrong records/LATEST and claims a uniqueness that four other records contradict
- **Issue #455** (closed): sim: mid-scale conversion at fs_27c_1.80v moves 6 LSB under a 0.1-Ohm supply resistor -- deterministic, not the supply-return mechanism
- **Issue #464** (closed): spec: DR-017's "they move when #448 mints the decoupled one" prediction has been overtaken — the decoupled record exists and records/LATEST did not move
- **Issue #465** (closed): layout/sim: measure whether cutting the decoupling ties' via-dominated ESR (13.8 Ω/domain) actually helps, before drawing via arrays
- **Issue #469** (closed): sim: take the combined front-end + CDAC top-plate load to the ratified PVT grid (mechanism (d) at the assembled load)
- **Issue #475** (closed): worktree.sh stale-reset moves a local branch backwards past its own pushed tip, risking a force-push over an open PR
- **Issue #476** (closed): Dedup evidence-record open boilerplate in sim/comparator-decision/run.py's seven writers
- **PR #445**: feat(sim): sweep the substrate return on DR-012's rejected topology, and correct the DR-015 sentence it falsifies
- **PR #446**: docs(chipalooza): give the on-die-decoupling gap its tracker, and gate it (issue #121)
- **PR #447**: docs(chipalooza): grade the null-option ladder axis, correct #409's item status (issue #121)
- **PR #449**: design: size on-die supply decoupling per domain (DR-017) -- one MiM cap each, from an area budget the bounce response cannot be sized against
- **PR #451**: feat(sim): advance #409's corner grid in session-sized pieces and file its substrate-extraction gap
- **PR #452**: docs(chipalooza): finish §7's ladder pass — the pp reading rule, the enumeration, and check 34's positive guard (issue #121)
- **PR #454**: docs(chipalooza): re-check rules-4.html's publish status (issue #121)
- **PR #456**: feat(sim): run #409's full ratified corner grid -- all five arms x nine points (issue #409 item 1)
- **PR #457**: docs(chipalooza): close #409 item 1 in §7, cite the full 9-point/5-arm grid record (issue #121)
- **PR #458**: spec(DR-017): grade the shipped decoupling value -- Amendment A refutes the 1/sqrt(C) sizing model (issue #431)
- **PR #459**: docs(chipalooza): record #409's closure in §7 item 9, disclose item 4's untracked residue (issue #121)
- **PR #460**: feat(docs): grade §7's undecoupled excursion enumeration from the tree
- **PR #461**: docs(chipalooza): correct the INL/DNL row's klt-yield gap citation, file the unaddressed successor (issue #121)
- **PR #462**: docs(chipalooza): re-verify #440/#431 tracking state in §7 Item 1 (issue #121)
- **PR #463**: docs(spec): erratum DR-017's mis-cited records/LATEST and false uniqueness claim (issue #453)
- **PR #466**: layout: place DR-017's two per-domain decoupling caps and re-verify DRC/LVS/ERC (issue #440)
- **PR #467**: docs(chipalooza): correct six present-tense LVS counts left at 88, and gate the form (issue #121)
- **PR #468**: docs(chipalooza): record #440 and #431 closures and PR #402 conflict (issue #121)
- **PR #471**: docs: strike DR-017's overtaken decoupled-record prediction
- **PR #472**: sim+spec: the mid-scale code is a coin flip on a metastable MSB, not a supply-return sensitivity (issue #455)
- **PR #473**: layout/sim: measure that the decoupling ties' ESR AMPLIFIES the die-side bounce, then cut it with 2x2 via arrays (issue #465)
- **PR #479**: fix(loom): stop worktree.sh resetting a branch back past its own pushed tip (issue #475)
- **PR #480**: refactor(#476): migrate six evidence writers to evidence.open_record()
- **PR #481**: sim: take the assembled front-end + CDAC top-plate load to the ratified PVT grid (#469)

### 2026-09-25

- **Issue #349** (closed): comparator kickback: static-preamp topology (DR-004) closes the gap slew-limiting left open — follow-on to #346
- **Issue #364** (closed): erc-supply-spec.json's prose comments describe the pre-#355 run and are now stale
- **Issue #377** (closed): Two of the four analog blocks still draw no ground conductor — the analog ground mesh DR-012 left open
- **Issue #378** (closed): No testbench measures the ground return — DR-012's impedance argument is design-time reasoning, not evidence
- **Issue #379** (closed): check 17: t1_readout()'s failed-row list is not tier-filtered, while the counts beside it are
- **Issue #383** (closed): Remove unused import: DOMAIN_TAP_NET in sampling-frontend(-wells) gen_blocks.py
- **Issue #390** (closed): comparator kickback: split the kickback measurement into common-mode and differential components (gate for DR-014)
- **Issue #394** (closed): PR #388 (issue #383) broke DOMAIN_TAP_NET import: ImportError in sampling-frontend(-wells) build_layout.py/render-record.py
- **Issue #399** (closed): test(layout): add import-smoke coverage for layout entry-point scripts (the gap that let PR #388's ImportError reach main)
- **Issue #400** (closed): layout/halflsb-offset: DR-009's 8-primitive half-LSB offset network has no drawn geometry
- **Issue #405** (closed): sim: four campaigns publish no records/LATEST, so a third of Section 4's citations are not freshness-checked
- **Issue #406** (closed): citation gate check 25: `.control` block bodies are scanned as device cards (a `let` line counts as an inductor)
- **Issue #407** (closed): layout records do not pin the PDK commit their DRC/LVS/ERC verdicts ran against (33 of 67)
- **Issue #417** (closed): main is red: §4 corner-grid census (check 28) does not know about the enob-estimate record #415 minted
- **Issue #422** (closed): CI: a PR can merge onto a moved base without re-running its checks, so a cross-cutting census gate only catches the conflict on main
- **Issue #424** (closed): check 30's pin predicate is satisfied by a prose mention of `klt pdk find`, not only by an invocation
- **Issue #434** (closed): comparator kickback: measure headroom-neutral mitigation classes (double-tail latch, cross-coupled neutralization, complementary-clock compensation) — DR-014 Consequences §4
- **PR #380**: evidence(layout): refresh erc-supply-spec.json's stale prose and re-mint the ERC record
- **PR #384**: docs(chipalooza): make the bench plan executable on the 22-port part (issue #121)
- **PR #385**: feat(layout): mesh all three analog blocks' drawn grounds to the GND pad
- **PR #386**: docs(chipalooza): gate the directory list check 2's coverage rests on (issue #121)
- **PR #388**: fix(layout): remove unused DOMAIN_TAP_NET import from sampling-frontend(-wells) gen_blocks.py
- **PR #389**: docs(chipalooza): gate the device inventory, and find the glue the layout lost (issue #121)
- **PR #391**: fix(chipalooza): scope check 17's failed-row list to tier T1 (#379)
- **PR #392**: docs(spec): DR-014, static preamp not adopted for comparator kickback; DR-004 §1 stands
- **PR #393**: docs(chipalooza): gate the Kickback row's derived arithmetic, correct a mischaracterization (issue #121)
- **PR #395**: docs(chipalooza): fold DR-014's kickback disposition into §4, gate it (issue #121)
- **PR #396**: docs(chipalooza): gate the currency claim a stamped citation carries (issue #121)
- **PR #397**: docs(chipalooza): gate the row count a quoted command output carries (issue #121)
- **PR #398**: fix(layout): restore DOMAIN_TAP_NET re-export in both sampling-frontend gen_blocks.py
- **PR #403**: feat(sim): split comparator kickback into common-mode and differential parts
- **PR #404**: docs(chipalooza): gate the ground plan's unmeasured half, record #387's split (issue #121)
- **PR #408**: docs(chipalooza): gate §8's provenance claim, and count the layout third it overstated (issue #121)
- **PR #410**: evidence(sim): supply-return impedance sensitivity campaign, retires DR-012's open item (issue #378)
- **PR #411**: docs(chipalooza): correct #103's tracking state in §3/§4, gate the second copy (issue #121)
- **PR #412**: feat(sim): make the supply-return campaign restartable with a gated log cache
- **PR #413**: test(layout): import-smoke gate for layout/*/bin entry points (issue #399)
- **PR #414**: docs(chipalooza): count how much of §4 stands on the ratified PVT grid, gate it (issue #121)
- **PR #415**: sim: mint records/LATEST for the 2 genuinely single-current-record campaigns
- **PR #416**: docs(chipalooza): record #400's not-planned closure, gate an absence claim (issue #121)
- **PR #418**: fix(chipalooza): skip .control block bodies in the ground-return deck scan
- **PR #419**: docs(chipalooza): repoint the census's stale ENOB record after #405's re-point (issue #121)
- **PR #420**: fix(layout): pin the resolved open_pdks commit in every record renderer
- **PR #421**: docs(chipalooza): re-point §4's corner-grid census onto the current enob-estimate record
- **PR #423**: docs(chipalooza): grade the renderer half of §8's provenance census (issue #121)
- **PR #425**: ci: arm the merge-time base-freshness guard with one required status check
- **PR #427**: docs(chipalooza): record #417's closure where §4 still called it tracking (issue #121)
- **PR #429**: feat(sim): compute the no-gnd-pad vs package ground-pad ablation (issue #409)
- **PR #430**: docs(chipalooza): grade the arm axis behind §7's DR-012 retirement (issue #121)
- **PR #432**: feat(sim): bounded 2-D R/L sweep for the supply-return campaign, and a cost probe that prices it (issue #409)
- **PR #433**: fix(chipalooza): stop check 30's pin regex from counting a comment as a pin
- **PR #435**: docs(chipalooza): grade the sweep-box axis §7's DR-012 retirement leans on (issue #121)
- **PR #436**: docs(chipalooza): re-verify PR #402's live label state, §7 Item 1 (issue #121)
- **PR #437**: docs(chipalooza): give DR-014's headroom-neutral follow-on a tracker
- **PR #438**: feat(sim): run the bounded 2-D R/L sweep and mint its record (issue #409)
- **PR #441**: Measure cross-coupled neutralization; DR-016 closes DR-014's headroom-neutral gate (issue #434)
- **PR #442**: feat(sim): run the no-gnd-pad arm and price DR-012's rejected ground-pad option
- **PR #443**: docs(chipalooza): record klayout-tools#2397's closure, the third of PR #352's findings (issue #121)
- **PR #444**: docs(chipalooza): record #440's decoupling-cap placement requirement in §7 Item 1 (issue #121)


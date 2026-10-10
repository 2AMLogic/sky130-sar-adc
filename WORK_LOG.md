# Work Log

Merged pull requests and closed issues from the preceding 30 days. Entries record completion events, not signoff verdicts.

### 2026-10-10

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

### 2026-09-24

- **Issue #345** (closed): Commit a klt signoff block manifest so this block's T1 state is graded, not hand-read
- **Issue #346** (closed): comparator kickback: measured decomposition + mitigation option table from the sky130-comparator canary (same-PDK StrongARM prior art)
- **Issue #355** (closed): Top-level digital rails VPWR/VGND each resolve to two disconnected islands — T1 item 11 finding
- **Issue #361** (closed): spec: propose a DRAFT Kickback decision record for target-spec.md, informed by #346's baseline measurement
- **Issue #362** (closed): Analog GND has no top-level pin — the same structural gap #355 fixed for the digital rails
- **Issue #363** (closed): measure_metal_min_area.py under-merges its region, overstating sub-minimum-area counts (and its 'deck has no area rule' premise is stale)
- **Issue #368** (closed): signoff evidence-hash checker rejects every candidate when REPO_ROOT contains a symlink (10 test failures on macOS)
- **Issue #373** (closed): Withdraw klayout-tools#2139 upstream: its sub-minimum-area reproducer rested on this repo's own under-merging measurement
- **Issue #374** (closed): npm run test:unit is red on main: 10 signoff evidence-hash fixtures assert a pre-#357 contract
- **PR #339**: ci(layout): gate DRC-clean verdicts on curated-deck provenance (issue #121)
- **PR #357**: feat(signoff): commit a klt signoff block manifest as the T1 verdict of record
- **PR #358**: feat(sim): add comparator kickback probe testbench (issue #346)
- **PR #359**: docs(chipalooza): carry the newly-graded power-delivery (ERC) gap (issue #121)
- **PR #360**: docs(chipalooza): record #103's v0.6.0 re-measurement and operator escalation (issue #121)
- **PR #365**: feat(layout): tie VPWR/VGND into one island each, out to top-level pins (#355)
- **PR #366**: docs(spec): add a DRAFT Kickback row proposed by DR-011
- **PR #367**: docs(chipalooza): gate the ERC supply readout, the second evidence tree (issue #121)
- **PR #369**: docs(chipalooza): grade the DRC half on the pinned deck's own area rules (issue #121)
- **PR #370**: docs(chipalooza): record klayout-tools#2396/#2398's closure-but-no-release
- **PR #371**: fix(signoff): resolve REPO_ROOT before is_relative_to comparison (issue #368)
- **PR #372**: fix: stop the metal min-area script under-merging its region
- **PR #375**: docs(chipalooza): gate the T1 sign-off scorecard, the third evidence tree (issue #121)
- **PR #376**: feat(layout): draw a top-level analog GND pad, per DR-012
- **PR #381**: docs(chipalooza): gate how much of Section 4 the freshness check reaches (issue #121)
- **PR #382**: docs(layout): record the corrected klayout-tools#2139 reproducer re-run (issue #373)

### 2026-09-23

- **Issue #344** (closed): T1 item 11 (power delivery, structural): no klt erc supply spec or report in this repo
- **Issue #347** (closed): 2am: reuse rule 9 — in-tree comparator duplicates sibling canary sky130-comparator — add reuse.lock.json in_tree entry (evaluate), then adopt or record
- **PR #352**: layout: re-measure sar-adc-top on klayout-tools 0.6.0 -- LVS still not clean, real --abstract-cells mechanism located (#103)
- **PR #353**: chore: record the in-tree comparator against sibling sky130-comparator
- **PR #356**: feat(layout): commit klt erc supply spec and report for T1 item 11

### 2026-09-22

- **Issue #350** (closed): comparator noise: regeneration-inclusive measurement methodology (equivalent-source transient-noise MC) demonstrated on the sky130-comparator canary

### 2026-09-19

- **Issue #333** (closed): layout/sar-sequencer + layout/seln-inverters: 145 place-and-route-generated metal shapes violate sky130A's m1.6/m2.6/m3.6/m5.4 minimum-area rules
- **PR #340**: docs(layout): waive the 145 place-and-route minimum-area shapes, with a reproducing upstream filing (issue #333)
- **PR #341**: docs(layout): correct the --abstract-cells LVS collapse diagnosis (issue #103)

### 2026-09-18

- **Issue #322** (closed): layout/sar-sequencer: LVS pin counts are asymmetric (30 layout / 28 reference / 30 matched)
- **Issue #326** (closed): layout/sar-adc-top: 17 metal shapes violate sky130A's m3.6/m4.4a minimum-area rules, invisible to the deck klt drc runs
- **Issue #330** (closed): chore(ci): ci.yml's citation-gate inventory comment duplicates docs/citation-gate.md
- **Issue #331** (closed): layout/comparator/README.md names a stale reports/LATEST, and an unexplained post-pointer record sits beside it
- **PR #325**: docs: explain the sar-sequencer LVS pin-count asymmetry
- **PR #328**: docs(chipalooza): gate the Area row's bounding box, the last hand-carried figure (issue #121)
- **PR #332**: docs(chipalooza): gate what the composed top level is built from (issue #121)
- **PR #334**: docs: update stale layout/comparator record citations (issue #331)
- **PR #335**: chore(ci): point ci.yml's citation-gate comment at docs/citation-gate.md
- **PR #336**: fix(layout): size isolated via pads to clear sky130A's metal minimum-area rules
- **PR #337**: docs(chipalooza): gate the decision-record statuses the Status column rests on (issue #121)

### 2026-09-17

- **Issue #321** (closed): refactor(chipalooza): check_proposal_citations.py is 1584 lines / 12 checks — consider splitting parsing, evidence readers and rationale
- **Issue #323** (closed): layout: three sub-block sign-off records still rest on klt 0.4.0 while the pinned build is 0.5.0
- **PR #318**: docs(chipalooza): gate the sign-off-bar numbers, not just their citation (issue #121)
- **PR #319**: docs(chipalooza): gate the I/O list against the top-level netlist (issue #121)
- **PR #320**: docs(chipalooza): gate what a §4 row fails to cite, re-grade the Power row (issue #121)
- **PR #324**: docs(chipalooza): gate the five sub-block layout verdicts, not just the top level's (issue #121)
- **PR #327**: layout: re-run cdac-array, sar-sequencer, seln-inverters under klt 0.5.0
- **PR #329**: refactor(chipalooza): move the citation gate's rationale into a sibling document

### 2026-09-16

- **Issue #280** (closed): merge-pr.sh silently exits 1 on any loom:pr PR with no champion:hold-state comment (set -e + pipefail interaction)
- **Issue #288** (closed): verify-proposal-refs.sh: nondeterministic false-positive MISSING FILE (SIGPIPE/pipefail race)
- **Issue #291** (closed): Repair local guard fix in .loom/scripts/merge-pr.sh reverted by resync (champion-hold-state grep crash)
- **Issue #296** (closed): Fix: two hold-kick experiments crash with NameError after PR #289's _preamble() dedup
- **Issue #299** (closed): Dedup ngspice-retry-with-backoff wrapper across 5 sim run scripts
- **Issue #301** (closed): verify-proposal-refs.sh: SIGPIPE/pipefail false-MISSING-FILE bug is back — a resync silently reverted the merged fix
- **Issue #303** (closed): Drop now-empty local Rect(_Rect) subclass in sampling-frontend / sampling-frontend-wells build_layout.py
- **Issue #304** (closed): Dedup generate-lvs-reference.py main() boilerplate between sar-sequencer and seln-inverters
- **Issue #313** (closed): verify-proposal-refs.sh: pipefail+SIGPIPE race falsely reports existing files as missing
- **Issue #314** (closed): Dedup evidence-record open/close boilerplate across run_conversion.py's four writers
- **PR #290**: layout(sar-adc-top): measure --abstract-cells black-boxing, narrows LVS to 6 mismatches, files klayout-tools#1911
- **PR #292**: fix(loom): guard grep no-match in champion hold-state check
- **PR #293**: docs(chipalooza): re-point §3/§4 at #103's post-#275 LVS neutralization (issue #121)
- **PR #294**: fix(loom): eliminate SIGPIPE/pipefail race in verify-proposal-refs.sh
- **PR #295**: docs(chipalooza): fold #103's PR #287/#290 findings into §7 Item 1, fix stale reports/LATEST citations (issue #121)
- **PR #297**: docs(chipalooza): correct klayout-tools#1876/#1878 status — both closed, one is docs-only
- **PR #298**: Fix: two hold-kick experiments crash with NameError after PR #289's _preamble() dedup
- **PR #300**: docs(chipalooza): correct stale "top-level layout does not exist" ledes in §7 Item 1 / §3, discharge deferred sampling-frontend re-point (issue #121)
- **PR #302**: fix(loom): re-apply SIGPIPE/pipefail fix in verify-proposal-refs.sh, fix dead cache (#301)
- **PR #305**: refactor: consolidate ngspice retry-with-backoff into toolchain.py
- **PR #306**: refactor(layout): drop empty Rect(_Rect) pass-through subclasses
- **PR #307**: docs(chipalooza): note klayout-tools#1911 closed via genuine fix, still unreleased
- **PR #308**: refactor(layout): dedup generate-lvs-reference.py main() boilerplate
- **PR #309**: docs(chipalooza): re-check rules-4.html publish status
- **PR #310**: docs(chipalooza): record #103's catch-up — LVS blocker is now a bare release gate (issue #121)
- **PR #311**: docs(chipalooza): machine-check the proposal's citations, re-point one stale §4 row
- **PR #312**: docs(chipalooza): record the klayout-tools release gate's grown contents (issue #121)
- **PR #315**: docs(chipalooza): gate the citation checker's own coverage census (issue #121)
- **PR #316**: refactor(sim/full-conversion-transient): dedup evidence-record open/close boilerplate
- **PR #317**: docs(chipalooza): gate the proposal's spec table against the ratified spec (issue #121)

### 2026-09-15

- **Issue #143** (closed): sampling-frontend-wells run-flow.sh: 'gap evidence' verdict fails after klt 0.3.0 -> 0.4.0 pin bump
- **Issue #161** (closed): Dedup layout/sampling-frontend/bin/render-record.py onto _record_common_strict
- **Issue #163** (closed): Dedup tap_shapes/_assert_well_isolation/_assert_column_pitch across layout build_layout.py scripts
- **Issue #205** (closed): Dedup xschem netlist_dut()/TRIG-TARG parsing reinvented by sequencer-logic-delay
- **Issue #25** (closed): T1 item 2: draw the SAR ADC layout and commit reproducibly-generated GDS with provenance
- **Issue #274** (closed): check:spec-coverage fails on main — 5 sim/ experiments orphaned from sim/spec-coverage.json, blocking CI on every PR
- **Issue #278** (closed): Dedup evidence.resolve_provenance() reinvention: run_mc.py, run_testbench.py
- **Issue #283** (closed): Dedup write_corners_record() post-provenance boilerplate: sampling-acquisition-settling, sequencer-logic-delay, cdac-bit-trial-settling
- **PR #271**: docs(chipalooza): re-verify VCM drive budget post-issue-#236, refresh rules-4.html check (issue #121)
- **PR #272**: Dedup layout/sampling-frontend/bin/render-record.py onto _record_common_strict
- **PR #273**: docs(chipalooza): cover full-conversion-transient campaign, refresh #103 blocker status (issue #121)
- **PR #275**: layout: bump klayout-tools to 0.5.0, retire sar-adc-top's SAR_ADC_TOP_KLT override (#103)
- **PR #276**: docs(chipalooza): re-point §3 and §4's Area row at the current top-level layout record (issue #121)
- **PR #277**: refactor(layout): dedup tap_shapes/_assert_well_isolation/_assert_column_pitch
- **PR #279**: fix(sim): index the five orphaned experiments in sim/spec-coverage.json
- **PR #282**: docs: re-point chipalooza sign-off-bar rows at current sar-adc-top record
- **PR #284**: refactor(sim): dedup evidence.resolve_provenance() reinvention in run_mc.py/run_testbench.py
- **PR #285**: docs(chipalooza): reflect PR #275's v0.5.0 LVS rebuild findings (issue #121)
- **PR #286**: refactor(sim): dedup write_corners_record() post-provenance boilerplate
- **PR #287**: layout(sar-adc-top): neutralise klayout-tools#1876 locally, leaving #1878 the only LVS blocker
- **PR #289**: refactor(sim): dedup xschem netlist_dut()/_preamble() reinvention onto sim/harness/toolchain.py

### 2026-09-14

- **Issue #31** (closed): T1 item 9: ship a testbench per claimed spec row with a documented cold-start invocation and pinned PDK revision
- **PR #134**: sim: index every claimed spec row to its testbench, cold start and pinned PDK (#31)

### 2026-09-12

- **Issue #263** (closed): design: SAR search applies no trial perturbation and never clears the CDAC between conversions -- conversion still does not converge after #257's capture-timing fix
- **Issue #265** (closed): Near-full-scale SAR conversions (±0.78·V_REF) still fail to converge under decision-directed CDAC switching
- **PR #268**: fix: confirm common-mode-headroom root cause for near-full-scale SAR saturation
- **PR #270**: fix: balance comparator output load and add a half-LSB quantizer offset

### 2026-09-11

- **Issue #254** (closed): sim: end-to-end full-conversion transient campaign on the transistor-level `sar_adc_top` (code-correctness at the DR-006 12 MHz clock + measured IDD) across the ratified 9-corner grid
- **Issue #257** (closed): design: closed-loop SAR conversion never converges -- comparator reset and bit-capture register share the same CLK edge
- **Issue #258** (closed): design/sar_sequencer.sch: VGND/VPWR omitted from its own .subckt port list, floating when nested inside design/sar_adc_top.spice
- **Issue #259** (closed): sim/full-conversion-transient record 20260910-190240-2d1d196: whole-ADC conversion saturates to code 1023 at all 9 ratified corners -- mechanism-probe evidence points at comparator-decision-capture timing
- **PR #260**: sim: end-to-end full-conversion transient campaign (issue #254) -- 0/9 corners code-correct, mechanism-probe points at comparator-capture timing
- **PR #261**: fix: declare VPWR/VGND global so nested std cells stay powered
- **PR #262**: sim: node-level trace pins the SAR saturation on the comparator reset / capture-edge ordering (#259)
- **PR #264**: fix: strobe the SAR comparator from CLKN so bit capture lands at the end of evaluate
- **PR #266**: fix: SAR trial perturbation, per-conversion clear timing, and decision-directed CDAC switching

### 2026-09-09

- **Issue #255** (closed): Dedup klt-gen invoke/JSON-check boilerplate across layout gen_blocks.py scripts
- **PR #256**: refactor(layout): dedup klt-gen invoke/JSON-check boilerplate in gen_blocks.py

### 2026-09-08

- **Issue #235** (closed): Dedup write_record() provenance preamble across 7 sim run.py scripts
- **Issue #236** (closed): design: sampling front end acquisition does not clear DR-006 12 MHz phase budget at any ratified PVT corner
- **Issue #241** (closed): Dedup write_corners_record() provenance preamble via evidence.resolve_provenance()
- **Issue #243** (closed): Dedup write_corners_decouple_record() provenance preamble via evidence.resolve_provenance()
- **Issue #245** (closed): design: re-derive VCM drive budget and re-verify sampling-frontend layout LVS after issue #236's Sa/Cmsw sizing change
- **Issue #248** (closed): layout(sampling-frontend-wells) / sim(vcm-drive-budget --corners): reconcile remaining post-issue-#236 staleness left out of #245's scope
- **Issue #251** (closed): Remove unused DOMAIN_TAP_NET import in sampling-frontend(-wells) gen_blocks.py
- **Issue #252** (closed): Dedup evidence-record provenance boilerplate in sim/comparator-decision/run.py via evidence.resolve_provenance()
- **PR #232**: docs: sync Chipalooza #4 proposal with PR #227's LVS pin-declaration fix (issue #121)
- **PR #233**: sim: take VCM drive budget's legacy-window C_decouple sweep to full PVT grid (issue #121)
- **PR #234**: docs(chipalooza): add klayout-tools#1557/#1560 to LVS blocker citations
- **PR #237**: docs(chipalooza): track sampling front-end acquisition design-fix as issue #236
- **PR #238**: docs(chipalooza): re-verify rules-4.html publish status is still unpublished
- **PR #239**: docs(chipalooza): re-point §4's Area row at the current top-level layout record
- **PR #240**: refactor(sim): dedup write_record() provenance preamble via evidence.resolve_provenance() (issue #235)
- **PR #242**: docs(chipalooza): correct three superseded layout-record citations
- **PR #244**: refactor(sim): dedup write_corners_record() provenance preamble via evidence.resolve_provenance()
- **PR #246**: design: fix sampling front end acquisition-window phase-budget failure (issue #236)
- **PR #247**: refactor(sim): dedup write_corners_decouple_record() provenance preamble via evidence.resolve_provenance()
- **PR #249**: design: re-verify sampling-frontend LVS and VCM drive budget post-#236
- **PR #250**: design(layout,sim): reconcile wells sub-block + --corners records post-issue-#236 (issue #248)
- **PR #253**: refactor(sim): dedup evidence-record provenance boilerplate in comparator-decision/run.py

### 2026-09-07

- **Issue #214** (closed): Dedup ratified OAT-grid construction in sequencer-logic-delay onto corners.ratified_oat_grid()
- **Issue #217** (closed): Dedup ratified_oat_grid() reinvented by sequencer-logic-delay --corners mode
- **Issue #218** (closed): Dedup remaining oat_grid stragglers: run_transfer.py and run_hold_kick.py
- **Issue #221** (closed): Dedup hwire()/vwire() Rect extension: sampling-frontend + sampling-frontend-wells build_layout.py
- **Issue #222** (closed): Dedup sampling-frontend run-flow.sh onto _flow_common.sh
- **Issue #228** (closed): Dedup two-arm MC draw loop: cdac-array-transfer/run_mc.py reimplements mc_runner._draw_n()'s shape
- **Issue #229** (closed): Dedup _parse_trig_targ / _TRIG_TARG_RE_TMPL across three sim testbenches
- **PR #215**: refactor(sim): dedup ratified OAT-grid construction in sequencer-logic-delay
- **PR #216**: sim: take CDAC-array bit-trial settling to full PVT grid (issue #121)
- **PR #219**: sim: dedup remaining oat_grid stragglers onto ratified_oat_grid() (issue #218)
- **PR #220**: sim: take VCM drive-impedance budget's bare R_source sweep to full PVT grid (issue #121)
- **PR #223**: layout: dedup Rect.hwire()/vwire() onto the shared _geometry_common base
- **PR #224**: layout: source _flow_common.sh in sampling-frontend's run-flow.sh
- **PR #225**: sim: take VCM drive budget's legacy-window R_source sweep to full PVT grid
- **PR #226**: sim: take VCM drive budget's worst-case-window C_decouple sweep to full PVT grid (issue #121)
- **PR #227**: fix: resolve top-level SAR ADC LVS pin declaration, surface new combine_devices blocker
- **PR #230**: refactor: dedup _parse_trig_targ onto shared measure.parse(anchored=False)
- **PR #231**: refactor: generalize mc_runner._draw_n() to a callback, dedup run_mc.py's loop

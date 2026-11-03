# `signoff/` — this block's T1 verdict of record

**`signoff/t1-report.json` is the verdict.** It is rendered mechanically by
`klt signoff --manifest signoff/block-manifest.json`, re-rendered by CI on every
push and pull request, and it supersedes every hand-written checkbox list of
this block's gap to T1. `docs/t1-gap.md` and the tracker issue (#23) now point
here rather than carrying their own item tables — the reason this file exists is
that a prose checklist goes stale the moment either the evidence or the
checklist moves, and **both moved**: the T1 checklist grew an eleventh item on
2026-09-17 (klayout-tools#2025), which invalidated every prior hand-read in the
fleet at a stroke.

Current verdict, at the committed report:

| | |
|---|---|
| block | `sky130-sar-adc` |
| kind | `mixed-signal` (22 rows: 11 items × 2 partitions) |
| tier | `null` — not T1 |
| T1 items met | **13 / 22** (items 2, 3, 8, 9, 10 on both partitions; item 1 on the analog partition; item 5 on the digital partition — **provisional, narrow; read "Item 5, digital" below** — and item 7 on the digital partition — **partial annotation, one macro cited; read "Item 7, digital" below**) |
| checklist graded against | `design-evidence-tiers.md` @ `sha256:a26b9026…` (the copy `klayout-tools==0.8.0` bundles) |
| grading build | `klt 0.8.0` (`git_tag v0.8.0`, `grading_ruleset_id sha256:46c446d8…`) |

**A mostly-`unmet` report is the correct result, not a failure of this
file.** 9 of 22 rows are `unmet` with a machine-readable `reason`, and that is
exactly the honest statement of the gap. Nothing here should be "improved" by
citing an envelope that does not actually support the item it is filed under.

<!-- markdownlint-disable-next-line MD026 -->
## Why `mixed-signal`, and what the partitions are

The kind was confirmed against the block, not taken from the issue that asked
for this manifest. The design genuinely partitions, inside one repo, into:

- **an analog partition** — the bootstrapped sampling front end, the
  differential charge-redistribution CDAC array, the StrongARM-class comparator,
  and the top-level half-LSB offset-injection network of DR-009. Transistor-level
  `sky130_fd_pr` primitives, captured in xschem, laid out by hand through the
  `klt gen` / `klt draw` flow.
- **a digital partition** — the walking-one ring sequencer and 10-bit SAR
  register, plus the top-level standard-cell bank (SELn/SELp drivers, the DR-008
  offset-binary recoding stage, the DR-009 enable pair). `sky130_fd_sc_hd`
  standard cells, **placed and routed by OpenROAD** via `klt place-and-route`.

That second half is what makes the block mixed-signal rather than analog: it is
not the doc's "full-custom digital sub-case" (hand-drawn, no P&R) — there is a
real P&R flow with a committed request and a PDN. The earlier hand-read recorded
in `docs/t1-gap.md` (2026-08-16) called this block `analog`; that was written
before `layout/sar-sequencer/` and `layout/seln-inverters/` existed, and it is
superseded by this manifest.

`design-evidence-tiers.md`'s "Block kind" section requires the claim to state
**which nets/pins/cells belong to which side**. That statement lives in the
manifest's `partition_boundary`, is echoed verbatim into the report (top level
and on every row), and names the boundary crossings too — a boundary is only
reviewable if its crossings are named. `klt signoff` reports it but cannot grade
it; `sim/tests/test_signoff_evidence_hashes.py` at least enforces that a
mixed-signal manifest does not ship without one.

## The eleven items, and what stands behind each

`met`/`unmet` below is the grader's verdict, copied from the committed report —
not a second opinion. The third column is what this repo is responsible for
saying, because the grader cannot.

| # | Item | Verdict | What is actually true here |
|---|------|---------|----------------------------|
| 1 | Design sources | analog **`met`**; digital `unmet` / `check_failed` | Cited through artifact-anchored generic envelopes (issue #676), one per partition, each pinned to its inventory under `signoff/attest/`. Analog: the schematics/symbols and `design/sar_adc_top.spice`. Digital: **`unmet`** because `layout/sar-sequencer/netlist/sar_sequencer.v` has fallen behind `design/sar_sequencer.sch` — see "What the item 1, 2, 9 and 10 citations assert".
| 2 | Layout | **`met`** (both) | One bare citation: a generic envelope pinning the composed top-level stream (`layout/sar-adc-top/reports/20261001-211249-1ca34e6/sar_adc_top.gds`) by path and sha256. Asserts nothing about item 4. See "What the item 1, 2, 9 and 10 citations assert".
| 3 | DRC clean | **`met`** (both) | `klt drc` on the composed top-level stream: `status: clean`, 0 violations, deck `sky130` @ `sha256:a1d90e06…` (see the cited `drc.json` for the authoritative deck hash and counts). Covers both partitions because the stream it ran on contains both partitions' geometry. **Coverage gaps are disclosed below — read them; a `met` here is not evidence they were disclosed.** |
| 4 | LVS clean | `unmet` / `check_failed` (both) | Cited deliberately even though it fails. `klt lvs` reports `status: "mismatch"` against the full-block reference; the authoritative mismatch, net, device and pin counts are in the cited `layout/sar-adc-top/reports/20261001-211249-1ca34e6/lvs.json` (`mismatch_count`, `category_counts`, `counts`) — read them there. Summary retained at that record only: 67 mismatches / 66 errors, 519/555 reference nets and 1046/1095 reference devices matched; categories 49 `device.unmatched`, 9 `net.merged`, 8 `net.split`, 1 `topology.flattened`. Pins read 21 layout / 22 reference / 22 matched: the reference carries `GND` and `VGND` as two ports of what the layout extracts as one net — the shared p-substrate (`GND\|VGND\|VSS`) — so one promoted layout pin answers both, which is why `layout < reference` here is not a missing pin; see [DR-012](../spec/decision-records/DR-012-analog-ground-pad.md). *Historical comparison, superseded:* the 2026-09-24 record (`reports/20260924-234053-66dca3c/`) read 88 mismatches / 87 errors, 411/444 nets and 803/869 devices; before issue #355 it read 98/97. Root cause is an upstream extraction-hierarchy gap, not a design defect — filed generically as klayout-tools#1878; see `layout/sar-adc-top/README.md`'s "LVS device/topology blocker". The full-block LVS still does not match. |
| 5 | Full corner verification | analog: `unmet` / `no_evidence`; digital: **`met`** (provisional) | Digital: the manifest's `5.digital` cites a `klt sta` report (routed `sar_sequencer`, four stock Liberty corners at 12 MHz, all `constrained`, no setup/hold violations). Under `klt 0.8.0` the row is compound: the manifest cites four reports (STA and `klt functional-verification` for each of `sar_sequencer` and `top_glue`), each graded `met`; citing the STA alone renders `unmet` / `partial_coverage` (`missing_kinds: functional-verification`). **`met` is the grader's verdict on those four reports; the spec table is DRAFT, 8 of the nine PVT points have no Liberty file, and the STA covers the digital partition's own boundary only — see "Item 5, digital" below.** Analog: no `klt sim` envelope exists — `sim/` campaigns mint this repo's own Markdown records — and the ENOB / INL-DNL **target values** are still DRAFT. |
| 6 | Statistical claims | `unmet` / `no_evidence` (both) | Five `klt yield` envelopes **do** exist and all report `status: "fail"` — see "Item 6" below for what they say and why none is cited. |
| 7 | Post-layout verification | analog `unmet` / `no_evidence`; digital `met` | **Analog:** no `klt pex` report exists for the composed top level or any partition; three comparator-level `pex.json` envelopes exist under `layout/comparator/reports/` but are not cited, because they cover the comparator block only and do not prove post-layout behaviour of the composed block. The analog half is blocked on item 4 (the top-level LVS mismatch, issue #103), mirroring `layout/sar-adc-top/README.md`. Item 7 on the analog partition accepts nothing else: a clean DRC or a pre-layout sim renders `wrong_kind`. Nothing to disclose about `body_bias` yet — that field is reported on a `pex` citation, and there is no `pex` citation in the manifest. **Digital:** cited since issue #679 — a `klt functional-verification` report with `options.sdf` set and `environment.sdf.annotated: true` on the routed `sar_sequencer`; see "Item 7, digital" below for what `met` does and does not assert. |
| 8 | Characterization report | **`met`** (both partitions, by two separate citations) | `8.analog`: `docs/characterization-report.md`; `8.digital`: `docs/characterization-report-digital.md` (frequency bracket, rail power and routed area at the nine ratified corners); each wrapped in its own `generic` envelope (the only kind item 8 accepts). **What `met` asserts is narrow — read "Item 8" below before quoting it.** The digital row is schematic-level and does not borrow the analog row's pass, nor the reverse. |
| 9 | Testbenches shipped | **`met`** (both) | One bare citation: the inventory of every testbench `sim/spec-coverage.json` indexes, the cold start and the PDK/tool pins. See "What the item 1, 2, 9 and 10 citations assert" for what was and was not executed when the envelope was minted.
| 10 | Repo hygiene | **`met`** (both) | One bare citation: README, LICENSE, `spec/target-spec.md` and the CI workflow are present and the workflow runs the declared audit commands. The commands themselves run in CI, not at mint. See "What the item 1, 2, 9 and 10 citations assert".
| 11 | Power delivery (structural) | `unmet` / `check_failed` (both) | Now **cited**, as a compound entry (`klt erc` run + the LVS report item 4 grades) — see "Item 11" below. Its supply-continuity half **passes**: all four declared supplies at one electrical island each, no `erc.unconnected_net` / `erc.supply_short`. Since issue #677 the n-well `ties[]` are declared and computed (klayout-tools#2169 is fixed in 0.6.0): `erc_status: violations`, 28 `erc.missing_tie` findings (the p-substrate half is still undeclared — klayout-tools#3750). It is `unmet` / `check_failed` for item 4's LVS mismatch, which the grader tests first. |

T2–T4 render as single `tier_not_supported` rows: this toolkit's closed loop
targets T1, and T2+ need commercial tools and fab access this repo has no
mechanism to check.

### Item 3: the DRC coverage disclosure

`klt signoff` grades item 3 on `status: "clean"` alone. A deck with rule-free
drawn layers or skipped rules grades `met` exactly like a fully-covering one, so
**the `met` verdict in the report is not evidence that the gaps below were
disclosed.** Discharging that obligation is what this section is:

- **Deck scope** — 17 chapters of the sky130 DRM are transcribed at all:
  `cap2m, capm, ct, difftap, li, licon, m1, m2, m3, m4, m5, nwell, poly, via,
  via2, via3, via4`. "Clean" was measured *inside* that scope. Everything the
  foundry DRM covers outside it (antenna, density, latch-up, ESD, substrate
  rules, …) was not checked here at all.
- **Drawn layers with no rule in the deck (23)** — `64/5, 64/16, 64/59, 65/44,
  66/5, 67/5, 67/16, 68/5, 68/16, 69/5, 69/16, 71/5, 72/5, 72/16, 78/44, 81/4, 83/44,
  93/44, 94/20, 95/20, 122/16, 235/4, 236/0`. These are drawn in this block's
  stream and the deck has nothing to say about them. Most are label/pin/text
  datatypes and marker layers, but the list is reproduced in full rather than
  triaged, because a triage is a judgement and this is a disclosure.
- **Rules the deck carries but this run did not evaluate (5)** —
  `capm2.enclosing.via4.1, capm2.separation.via4.1, capm2.space.1,
  capm2.width.1, met4.enclosing.capm2.1`. All five are `capm2` (the second MiM
  capacitor level). This design's MiM caps are `cap_mim_m3_1`, i.e. `capm`, not
  `capm2`, so no `capm2` geometry exists to check — the skips are vacuous here
  rather than hidden holes. That is a claim about this block, and it is exactly
  the kind of claim that must be written down rather than inferred from a green
  verdict.

The three lists are also carried verbatim in the report itself
(`items[].citation.coverage`), so a reviewer never has to re-open the DRC
envelope — but nothing compares them against what this section says, so read
both.

### Item 6: what the Monte Carlo evidence says, and why it is not cited

Status as of 2026-10-10 (issue #625). Five `klt yield` envelopes exist, all
`status: "fail"`:

- `sim/cdac-array-transfer/yield-reports/20260828-005006-0c70212.json` and
  `20261001-124049-5207381.json` — DNL/INL. The first: `dnl_max_lsb` over
  n=40, empirical yield 0.825 (Clopper–Pearson 95% CI 0.672–0.927) against a
  `±1 LSB`, `target_yield 0.99` limit. The second (n=40 for both
  `dnl_max_lsb` and `inl_max_lsb`) also fails.
- `sim/enob-estimate/yield-reports/20260828-005033-0c70212.json`,
  `20261001-124717-ba6875d.json`, `20261001-141249-7487784.json` — ENOB, each
  n=2 (far below the campaign's own `min_samples` intent), all fail and are
  under-sampled.

There is also a newer, adequately sized ENOB sample set with **no envelope**:
`sim/enob-estimate/yield-reports/20261008-233032-8bc3d1f.samples.json`
(`enob_bit`, n=40 per-draw, limit `min 7.5`, `target_yield 0.99`; DR-007's
unratified candidate value). Its record states the per-draw ENOB spans
7.755–9.101 bit, mean 8.531, but no `klt yield` verdict exists for it.

**Why no new envelope was minted (2026-10-10).** `klt yield` needs the
`klt_yield_native` extension. As of 2026-10-10 the newest published `klayout-tools` (0.7.0)
exposes it only as extra `yield`, which requires `klt-yield-native>=0.1.0,<0.2`;
that distribution is not on PyPI, so `pip install "klayout-tools[yield]==0.7.0"`
fails to resolve (0.6.0 and earlier have no such extra). The host `klt` fails
with "the klt_yield_native extension is not installed". The expected minting
environment is now a checked statement in `sim/yield-requirements.txt`, and
`sim/harness/evidence.py:run_klt_yield()` names that pin on stderr when the
extension is missing. Upstream: 2AMLogic/klayout-tools#2900. Once a wheel is
published, re-mint the ENOB envelope from the persisted samples file and the
CDAC envelope from `mc-draws/` as new derived records.

None is cited, for reasons about the **citation**, not about the campaign:

1. **None can be freshness-pinned.** `klt yield`'s report carries no
   `provenance` block, so `klt signoff` hashes the samples document the report
   names instead. Every envelope above names a `/tmp/tmp*.json` path that no
   longer exists and was never committed (the persisted `.samples.json`
   convention post-dates them). A pinned entry would render
   `unverifiable_provenance`; an unpinned one would be a citation with no
   freshness claim at all, which is what this manifest exists to avoid.
2. **One entry cannot represent two rows.** Item 6 accepts a single evidence
   entry, and this block has two statistical spec rows split across separate
   reports. Citing either alone would misstate the coverage. (Upstream
   klayout-tools#2467 additionally concerns graders rendering undersized yield
   as met.)

So item 6 renders `no_evidence` and the actual verdicts are recorded here. The
underlying campaign is issue #29's; its Markdown records stand unedited.

### Item 5, digital: what `met` asserts, and what it does not

**Provisional.** Item 5 requires a *ratified* spec. `spec/target-spec.md`'s
sample-rate row is still DRAFT (issue #1), so every verdict below is provisional
until it is ratified. Ratifying it is not part of the work behind this row, and
`klt signoff` does not check it: the `met` would read the same against a draft.

What stands behind the row (the reports were minted by `klt 0.6.0`, the build
that minted the evidence; the grader is `klt 0.8.0`; records are
append-only, see `sim/README.md`):

| Evidence | Where | Verdict |
|---|---|---|
| STA, routed `sar_sequencer`, 12 MHz | `sim/digital-sta/runs/20261017-194050-9522693/sar-sequencer.12mhz.json` (cited) | all four corners `constrained`, setup and hold slack positive, 0 violations |
| STA, routed `top_glue`, 12 MHz | `…/top-glue.12mhz.json` (cited) | same |
| Negative control: 6 GHz clock | `…/*.negative-control-6ghz.json` | setup fails at every corner of both macros; cited in place of the real report the grader renders it `unmet` / `check_failed` |
| Functional verification, `sar_sequencer` | `sim/digital-functional/runs/20261017-193811-9522693/sar-sequencer.json` (cited) | 8 / 8 tests pass; 5 / 5 netlist mutants killed |
| Functional verification, `top_glue` | `…/top-glue.json` (cited) | 6 / 6 tests pass; 6 / 6 mutants killed |

The tests are bit-exact against `sim/digital-functional/tb/sar_ref.py` (a
reference model written from the DR-006 / DR-008 / DR-009 text, with its own
self-check) on every output at every edge. They cover the cases the SPICE
campaign did not drive: all-ones, all-zeros, a mid-conversion asynchronous reset
at each of the 12 sequencer states, every one of the 1024 codes in closed loop,
and the whole `top_glue` input space.

Disclosures the grader cannot make:

- **What the grader checks about the four citations.** The `5.digital` entry is
  a list (as item 11's is). `klt 0.8.0` grades each cited report on its own
  (all four `met`) and requires both kinds, `klt sta` and `klt
  functional-verification`, to be present: with only the sequencer STA cited
  (the `0.6.0`-era shape, one slot) the row renders `unmet` / `partial_coverage`.
  It does not check that each macro has both kinds, nor the netlist-to-report
  linkage; `check_evidence_hashes.py` re-derives the sta DEF hash and, for
  functional verification, every netlist / model / testbench hash in the
  record's `inputs.sha256`.
- **Corner coverage: 1 of 9 points, and not exactly.** The nine PVT points the
  digital characterization uses are listed in `sim/digital-sta/corner-set.json`.
  `sky130_fd_sc_hd` ships Liberty files only for `tt_025C_1v80`, `tt_100C_1v80`,
  `ss_{n40C,100C}_*`, `ff_{n40C,100C}_*`: no `fs` / `sf` file at all, nothing at
  27 C other than the 25 C typical file, nothing at 1.62 / 1.98 V. Eight points
  are **declared gaps and were not timed**. `tt_27c_1.80v` is timed with the
  25 C file, a declared mapping (2 C apart), not an identity. The four timed
  corners include three stock extremes that are *not* among the nine
  (`tt_100C_1v80`, `ss_100C_1v60`, `ff_n40C_1v95`) and are never a substitute for
  a gap. The grader grades the corner set the run itself declared, so it cannot
  see the gaps.
- **Boundary STA only.** The analysis is of the digital partition's own routed
  netlists under stated assumptions (0.25 T input and output delays, ideal
  clock, unloaded outputs, no SPEF). It says nothing about the ADC's conversion
  rate, which also depends on the analog partition.
- **The routed `sar_sequencer` is not today's schematic (issue #680).** The netlist that was
  placed and routed, `layout/sar-sequencer/netlist/sar_sequencer.v`, has 36
  instances (issue #102). `design/sar_sequencer.sch` has 57: it gained the
  `COMP_EFF` xnor and per-conversion clear gating of issue #263 / DR-008. Both
  the functional tests and the STA cover the 36-instance netlist, so neither
  speaks for `COMP_EFF` or the clear gating.
- **Zero-delay functional run.** The item 5 functional reports carry no SDF; the SDF-annotated re-run is item 7 ("Item 7, digital" below).
- **PDK revision.** The reports were minted against open_pdks `f6eeac7`, the
  revision installed on the host, not the `c6d73a3` that `sim/pdk.json` pins
  (issue #669, the re-pin, is open).

### Item 7, digital: what `met` asserts

Item 7 asks for the functional suite re-run on the post-route gate-level netlist
with back-annotated SDF timing. The `7.digital` entry cites
`sim/digital-functional/runs/20261029-185640-5bb0e1e/sar-sequencer.ss_100C_1v60.json`:
the bit-exact `sar_sequencer` bench on
`layout/sar-sequencer/reports/20261021-104530-ddc1d72/sar_sequencer_post_route.v`
with the `ss_100C_1v60` SDF back-annotated (`environment.sdf.annotated: true`),
8 / 8 tests pass. Record: `sim/digital-functional/records/20261029-185640-5bb0e1e-sdf.md`;
SDF provenance (P&R record, corner, tool versions, annotation counts):
`sim/digital-sta/records/20261029-185629-5bb0e1e-sdf.md`.

| Evidence | Where | Verdict |
|---|---|---|
| SDF-annotated, `sar_sequencer`, `ss_100C_1v60` | `…/20261029-185640-5bb0e1e/sar-sequencer.ss_100C_1v60.json` (cited) | 8 / 8 pass |
| SDF-annotated, `sar_sequencer`, the other three corners | `…/sar-sequencer.{tt_025C_1v80,tt_100C_1v80,ff_n40C_1v95}.json` (not cited) | 8 / 8 pass each |
| SDF-annotated, `top_glue`, all four corners | `…/top-glue.<corner>.json` (not cited) | 6 / 6 pass each |
| Controls: same SDF, outputs sampled 0.1 ns after the edge | `…/*.control-short-settle.json` | every test fails (the delays are visible to the bench) |
| Controls: same models, no SDF, 0.1 ns settle | `…/*.control-no-sdf.json` | every test passes |

Disclosures the grader cannot make:

- **One report is graded.** The pinned grader takes a single entry for this item;
  a list renders `unmet` / `invalid_evidence` (filed generically as
  klayout-tools#4601). So `met` rests on the `sar_sequencer` report. The routed
  `top_glue` reports, and the other corners, pass and are committed in the same
  run but are not what the grader saw. `check_evidence_hashes.py` re-derives
  every input hash in that run's `inputs.sha256` (cell models, both routed
  netlists, all eight SDFs, the benches, the SDF run's own `inputs.sha256`).
- **Partial annotation.** Icarus does not implement SDF `TIMINGCHECK`, so the
  `sar_sequencer` reports carry `environment.sdf.partial: true` (21 sections
  dropped). The simulation applies IOPATH / INTERCONNECT delays only; it does not
  check setup, hold or pulse width. Those limits are covered only by
  `sim/digital-sta/` (ideal clock, no skew).
- **What the delays are.** The SDF is OpenSTA's `write_sdf` from the routed DEF
  plus a lumped-RC SPEF from `klt extract --parasitics` (one R and one C per net,
  not a distributed extraction), at the four item 5 Liberty corners, ideal clock.
  `spef_annotation.annotation_complete` is `false` in the STA reports: every
  design net is annotated (44/44 and 49/49) but the SPEF names other nets too.
- **Timing of the check.** 84 ns period (no tighter than the 12 MHz STA request's
  83.33 ns), outputs compared 40 ns after each edge or input change. It shows the
  outputs settle within 40 ns and match the model; it is not a measured maximum
  frequency.
- **Not the item 5 geometry by name, but by bytes.** The P&R records used
  (`20261021-104530-ddc1d72`, `20261021-104637-ddc1d72`) are newer than the
  `20261012-*` ones item 5 names; the DEFs, post-route netlists and GDS are
  byte-identical (the SDF script asserts the DEF hash against the item 5 request's).
- **Same netlist caveats as item 5:** the routed `sar_sequencer` is the
  36-instance netlist (issue #680); corners are the four stock Liberty files, the
  eight declared gaps are unchanged; the spec is DRAFT (issue #1).
- **Tool versions differ.** The item 5 reports were minted by `klt 0.6.0`; these
  by `klt 0.8.0` (the grader pin) with cocotb 2.1.0 / Icarus 13.0.
- **Analog half untouched.** Item 7 on the analog partition stays `unmet` /
  `no_evidence`, tracked on issue #103.

### Item 8: exactly what `met` asserts

Item 8's pass condition is about the **artifact**, not about the rows inside it:
"one aggregated, current artifact summarizing per-spec-row performance across
conditions, with the evidence record each verdict rests on". The generic
envelope asserts that and nothing more:

- `docs/characterization-report.md` covers **every** row of
  `spec/target-spec.md`'s Target table, including rows that fail or are
  unmeasured;
- every row names the evidence record(s) its verdict rests on;
- it is generated (`python3 sim/report/generate.py --write`), not hand-written,
  and its currency is gated on every push by `sim/report/generate.py --check`.

**It does not assert that the ADC meets its spec.** At the pinned revision that
report records ENOB and INL/DNL as DOES-NOT-MEET, and Sample rate and Power as
UNMEASURED. Those are items 5 and 6's subject.

Both DOES-NOT-MEET verdicts grade the **original pre-DR-007 DRAFT** values —
ENOB against the DRAFT baseline `> 9.0 bit` (stretch `> 9.5`), INL/DNL against
the DRAFT `≤ ±1 LSB` at `target_yield 0.99` — **not** DR-007's revised
candidates (`> 7.5 bit` / `≤ ±2.0 LSB`). DR-007 (proposed via #129) is still
unratified, and #505 / PR #508 deliberately left both rows grading their
pre-DR-007 values rather than moving a verdict onto an unratified line, which
is why these targets differ from the current `spec/target-spec.md` row text.
`sim/report/manifest.py`'s `enob` and `inl-dnl` rows are the authority for what
is actually graded; the long-form statement lives in
`signoff/evidence/characterization-report.generic.json`'s `_comment`. (#509
corrected this paragraph, which previously claimed the two verdicts graded
DR-007's candidates.)

**`8.digital` (issue #619)** is a separate citation, `signoff/evidence/
digital-characterization.generic.json`, wrapping `docs/characterization-report-
digital.md`. `python3 sim/report/generate.py` renders that document from the
immutable campaign `sim/digital-partition/runs/<record>/campaign.json` and
writes the envelope only when the campaign meets the item's digital
requirement (Fmax bracket or declared lower bound, rail power and energy per
conversion, and routed area, at every ratified corner, plus a too-fast-clock
negative control that must fail everywhere). What it asserts, and what it does
not:

- It asserts: all nine ratified corners have a measured clock-frequency bracket
  for the **digital partition alone** under stated interface loads and a
  deterministic comparator-data pattern; rail power / energy per conversion at
  the provisional 12 MHz operating point; routed area derived from the
  committed routed artifacts (cell, macro and composed-footprint figures
  labelled as such, never summed across overlapping boxes).
- It does **not** assert extracted or post-layout timing (this is schematic-
  level transistor SPICE), static timing, any spec row, or the ADC's sample
  rate: a digital clock bracket is not the conversion capability of the ADC.
  Nor does it assert coverage the campaign did not exercise: only four
  conversion codes are driven (no all-ones or all-zeros code), no
  mid-conversion asynchronous reset is injected, and clock-stopped static
  leakage is not measured (idle/reset power is taken with the clock running).
  The bracket holds only under the stated interface loads and an ideal
  COMP_OUT arriving 0.25 T after the launching edge; the document lists the
  numeric loads and these limits under "Declared limitations".
- Freshness is two-layered: `signoff/check_evidence_hashes.py` re-hashes the
  document the envelope wraps, and `sim/report/generate.py --check` fails if
  the digital-partition netlist text or the routed DEF/GDS / composed placement
  the campaign pinned changes without a regenerated campaign.
- The campaign ran on the batch fleet; the record discloses the runner/client
  `klt` version skew it was run under.

### Item 11: what the ERC run proves, and the two reasons it is still `unmet`

Item 11 is the only item whose manifest entry is a **compound** citation — a
JSON array, because the checklist asks for more than one artifact: the `klt erc`
supply-spec run *plus* the LVS report item 4 grades. Both parts here name the
same composed GDS by content hash
(`layout/sar-adc-top/reports/20261001-211249-1ca34e6/sar_adc_top.gds`,
`sha256:9d7c1a4c…`; the manifest pins the ERC part to the full hash), so the
pair is not two verdicts about two revisions. The September composed stream
(`20260924-234053-66dca3c`, `sha256:bbb9b537…`) is superseded history.

**What passes.** `layout/sar-adc-top/erc-reports/20261017-193237-9522693e/`
(`erc.json` + `record.md`, the run the manifest cites since issue #677) reports
all four supplies at one island with no `erc.unconnected_net` / `erc.supply_short`
(its `erc_status` is `violations` only because of the `erc.missing_tie` findings
below); the per-supply island table is `20261001-211722-1ca34e6`'s (same layout
GDS, spec `nets[]`/`stackup`/`vias` unchanged) and the September run it supersedes
(`20260925-044420-f039594`) read the same:

| Supply | Islands | `erc.unconnected_net` | `erc.supply_short` |
|---|---:|---|---|
| `VDD` | 1 | none | none |
| `GND` | 1 | none | none |
| `VPWR` | 1 | none | none |
| `VGND` | 1 | none | none |

That is new. Issue #344's first run had `VPWR` and `VGND` each resolving to
**two** disconnected islands — the two standard-cell macros' own self-contained
rails, neither reaching a top-level supply. Issue #355 fixed the *layout*, not
the gate, by tying both macros' met5 PDN straps together and out to two new
top-level supply pins, per
`spec/decision-records/DR-010-digital-supply-domain-partition.md`. That the
gate did not move is checkable rather than asserted: the spec's **graded**
fields (`stackup`, `vias`, `nets[]`, `ties_disclosure.kind` — the only content
`klt erc` reads) canonicalise to the same digest `7f48fd89…` on every run from
#344 to today, printed by `run-erc.sh` on each run. Issue **#364** refreshed
the spec's prose `_comment`s three times, now — once before issue #377's ground
mesh landed, again after, and a third time to correct two GDS-specific shape
counts a later Judge round found still described the superseded pre-mesh run —
since none of the three changed the *layout* this spec is graded against, only
the spec's prose, which moves its whole-file hash and nothing that digest
covers.

**Why it is still `unmet`, twice over — and in that order.** The rendered
reason is **`check_failed`** (both columns; `citation: null`, the grader's
ordinary rendering for any unmet item). The two causes are not
interchangeable, because `klt signoff`'s `_grade_power_delivery` evaluates them
in a fixed order and stops at the first:

1. **Item 4's LVS does not match** (`status: "mismatch"` in the cited `lvs.json`, klayout-tools#1878). The
   grading path resolves the cited LVS part and tests it *before* it looks at
   the supply spec, so this is the reason of record today — `check_failed` —
   and the clean continuity half is not what it is about.
2. **`erc.missing_tie` is now computed, and has findings** — latent, and what
   surfaces next once (1) clears. Since issue #677 the spec declares n-well
   `ties[]` (the `tool_limitation` disclosure is gone: klayout-tools#2169 is
   fixed in the pinned 0.6.0 and no false `erc.supply_short` appears), and
   `erc-reports/20261017-193237-9522693e/` reports 28 `erc.missing_tie`
   findings — 26 distinct wells, 2 of them with no tap on either rail; see that
   record's `record.md`. The p-substrate half is not declared
   (klayout-tools#3750). Item 11 stays `unmet` after #103 clears until those
   are resolved or filed.

So fixing the LVS alone would move the reason, not the verdict.

**Two things a reader should not over-read from the passing table.** `klt erc`
is a geometric wire/via model with no device recognition, so `GND: 1 island`
means the drawn `GND` conductor is one island, not that every NMOS body reaches
it — the substrate half is exactly what `erc.missing_tie` would cover, and
that half is still undeclared (klayout-tools#3750). And "one island" is not "reaches a pad" — the second half of that
warning is now discharged: analog `GND` had no top-level pin on this block at
all until issue #362 drew one (`spec/decision-records/DR-012-analog-ground-pad.md`),
and the ERC row read `1` both before and after, which is precisely why the gap
could only be closed by moving the layout. Every drawn supply now reaches a
top-level pin: `VDD` always did, `VPWR`/`VGND` since #355, `GND` since #362.
What does **not** follow from that, and DR-012 says so explicitly: `GND` and
`VGND` are not two electrical nodes. Bulk sky130 has no isolation between them,
and the composed extraction reports one net (`GND|VGND|VSS`) — two pads on one node,
so the return paths differ off-die, not on it.

### What the item 1, 2, 9 and 10 citations assert

No `klt` verb backs these four items, and `klt signoff` cannot judge topical
relevance of a bare passing envelope, so citing an unrelated one (the clean DRC,
say) would have been dishonest. Since klayout-tools 0.7.0 (issue #676; the grader pin is now
0.8.0, which grades them the same way) the tool grades an **artifact-anchored generic envelope**: it
declares `t1_item`, pins the audited artifact by path and sha256, and the
manifest pins the same hash; the row is `met` only while the artifact re-hashes
to it. This block's citations:

| Item | Envelope (`signoff/evidence/`) | Pinned artifact | Status |
|---|---|---|---|
| `1.analog` | `item-1-analog.attestation.generic.json` | `signoff/attest/item-1-analog.inventory.json` | pass |
| `1.digital` | `item-1-digital.attestation.generic.json` | `signoff/attest/item-1-digital.inventory.json` | **fail** |
| `2` (both) | `item-2-layout.generic.json` | `layout/sar-adc-top/reports/20261001-211249-1ca34e6/sar_adc_top.gds` | pass |
| `9` (both) | `item-9.attestation.generic.json` | `signoff/attest/item-9.inventory.json` | pass |
| `10` (both) | `item-10.attestation.generic.json` | `signoff/attest/item-10.inventory.json` | pass |

**Who wrote the verdict.** `klt signoff --attest` (klayout-tools#2844) is not in
a tagged release, so `signoff/mint_attest_envelopes.py` stands in. It writes the
inventories in the `--attest` `schema_version: 1` /
`kind: "t1-attestation-inventory"` format and derives each envelope's `status`
from the checks **it executes**, all listed in the envelope's `checks[]`. When a
release ships `--attest`, regenerate the item 1, 9 and 10 envelopes with it from
the same inventories. `npm run check:signoff-attest` fails if a committed
inventory or envelope differs from a fresh mint, so a `status` cannot be edited
by hand.

**What each `pass` asserts, and what it does not.**

- *Executed at mint (headless):* every inventoried path exists and is hashed;
  `design/sar_adc_top.spice`'s provenance header names each source schematic's
  *current* sha256; `layout/top-glue/bin/check-schematic-parity.py` passes; the
  declared CI commands appear in `.github/workflows/ci.yml`; the PDK revision and
  tool versions are pinned.
- *Declared but NOT executed at mint* (`"executed": false` in `checks[]`, with the
  CI job that runs it): `design/regen_netlist.sh --check` (needs xschem — CI job
  `pdk-smoke`), the item 9 cold start `source sim/env.sh && python3
  sim/run_corners.py --check-env` (needs ngspice and the PDK — `pdk-smoke`),
  `npm run check:ci` (CI job `checks`) and `bash signoff/run-signoff.sh --check`
  (CI job `signoff-check`). The header-hash comparison is a proxy for the
  regeneration check, not a replacement: it shows the netlist was made from the
  current schematic bytes, not that regenerating it reproduces it.
- *Item 9* attests that the benches the spec-coverage index names are committed
  with a cold start and pins. It says nothing about any bench's result or spec row.
- *Item 10* attests presence of the README, license, spec table and CI, and that
  CI runs the listed commands. It does not judge README content.
- *Item 2* attests that the composed stream is committed and byte-pinned, and
  that it is the stream items 3 and 11 cite. **It says nothing about item 4**:
  the top-level LVS mismatch stays tracked by #103 and item 4 stays `unmet`.
  Its `sar_sequencer` macro was routed from `sar_sequencer.v` as committed, which
  is stale (below), so item 2 does not say that macro matches the schematic.

**Item 1, digital: `unmet` (`check_failed`), on purpose.**
`layout/sar-sequencer/netlist/sar_sequencer.v` is a structural gate-level netlist
**transliterated by hand from `design/sar_sequencer.sch`**, not synthesized from
RTL (its header and `layout/sar-sequencer/README.md` say so). The freshness check
that binds it is `layout/sar-sequencer/bin/check-schematic-parity.py`: it
compares the Verilog, instance for instance and pin for pin, with the `.subckt
sar_sequencer` of `design/sar_adc_top.spice` (itself bound to the schematic by
the header hashes above and `regen_netlist.sh --check`), and it has negative
controls in `sim/tests/test_sar_sequencer_schematic_parity.py`. **It currently
fails on the committed Verilog**: 21 instances the schematic has are missing
(`xxnor_compeff`, the nine `xpre<i>` / `xclr<i>` pairs, `xor_g4`,
`xor_busybits`) and 18 pins differ (`xmux<i>.A1` is `COMP_OUT` where the
schematic has `COMP_EFF`; `xbreg<i>.D` is `MUXOUT<i>` where it has `DFEED<i>`).
Those are the per-conversion clear and decision-direction changes of issue #263;
the Verilog was never regenerated, so the sequencer macro in the committed
layout was routed from the older netlist. Because the check cannot pass, it is
**not** wired into `npm run check:ci` (that would turn CI red on a layout
re-spin this issue does not own) — wire it in the PR that regenerates the
Verilog and re-runs the sequencer, top-level composition, DRC and LVS flows (tracked by #680).
The item 1 digital envelope records `status: "fail"` rather than omitting the
citation, so the row reads `unmet` / `check_failed`. Separately, the checklist
text for a digital partition asks for RTL plus a synthesized netlist; this block
has neither, and relies on the "full-custom digital sub-case" wording for
item 1 (hand-captured schematics, every gate drawn).

If any pinned artifact changes, the row turns `unmet` and
`signoff/check_evidence_hashes.py` fails; re-mint with
`python3 signoff/mint_attest_envelopes.py`, re-render the report, and read the
diff.

## Freshness: two gates, and what each one catches

"Freshness is the point" — a passing report against last week's netlist is
evidence of nothing. Two independent, headless checks enforce it, and they catch
**different** failures:

| Gate | Command | Catches | Does **not** catch |
|---|---|---|---|
| Grader re-render | `bash signoff/run-signoff.sh --check` | Any change that alters a graded row: an edited manifest, a superseded evidence envelope, a pin that no longer matches the envelope's own hash, a checklist/grader change. | An artifact rewritten underneath a manifest and envelope that still agree with each other. |
| Artifact re-hash | `python3 signoff/check_evidence_hashes.py` | Exactly that: every cited envelope's recorded input hash is re-derived from the file on disk, including all four item 5 digital reports. | Grading changes — it does not know what the checklist says. |

The second gate exists because the first one structurally cannot do its job.
`klt signoff` compares the manifest's pin against the **envelope's own
self-reported** `provenance.input.content_hash`; both sides are statements about
a revision, neither is the revision. klayout-tools#2196 surfaces this as
`input_verified` on a met citation:

- the `generic` envelope (item 8) reports `input_verified: null` — by contract:
  a generic envelope's author chooses their own field names, so the grader
  cannot know `source` is the artifact and must not guess;
- the `klt drc` envelope (item 3) now reports **`input_verified: true`**. It did
  not before issue #355: `klt drc` records `file` as the path it was *invoked*
  with, and `layout/sar-adc-top/bin/run-flow.sh` used to invoke it with an
  absolute path inside the ephemeral agent worktree the flow ran in, which
  resolves from no other checkout. That was worse than merely unverifiable — it
  resolves on exactly **one** machine, so a report rendered there recorded
  `true` while CI's re-render of the same manifest recorded `null`, and
  `run-signoff.sh --check` failed on the drift (measured, not hypothesised).
  `run-flow.sh` and `run-erc.sh` now invoke `klt` from the repo root with
  repo-relative paths, so the recorded path resolves anywhere and the field is
  machine-independent.

The generic-envelope gap is a tool gap and is reported upstream as such. Either
way, verifying that a pin describes a committed artifact is **this repo's**
obligation, so `signoff/check_evidence_hashes.py` does it mechanically for every
citation — including the `erc` kind added for item 11, whose envelope is the one
kind that does *not* live beside the artifact it grades (an ERC record is a
verdict about some other record's GDS, so the checker re-roots the recorded path
under the repo root rather than looking beside the envelope). And
`sim/tests/test_signoff_evidence_hashes.py` proves the checker can fail, on a
fixture where the artifact changed while manifest and envelope still agree.

### Item 4's missing pin

Item 4's citation carries **no** `content_hash`, and that is deliberate — but
the premise first recorded here no longer holds. The envelope originally cited
was minted by klt 0.5.0, whose `klt lvs` wrote `provenance.input: null`, so
there was then no envelope-side hash for a manifest pin to match. The pinned
grader (`klayout-tools==0.8.0`, `signoff/requirements.txt`) writes one, and the
cited `layout/sar-adc-top/reports/20261001-211249-1ca34e6/lvs.json` carries
`provenance.input = {content_hash: sha256:b4fb2add24c1f4b5…, role: "netlist"}`
— the hash of the **layout-side** netlist (`sar_adc_top.extract.lvs.spice`),
equal to the envelope's own `environment.layout_sha256`. Nothing envelope-side
records a hash of the **reference** netlist: `environment.reference_sha256`
is still the only recorded statement about that side, so a pin would cover
one of the two digests and nothing could ever pin the other.

The pin stays omitted anyway, because it would still be decorative: it would
carry a digest the envelope's freshness is already verified against — and,
because `check_failed` is evaluated before the staleness gate, the grader
would never even consult it — while pinning the EXTRACTED NETLIST rather than
the GDS, which is the artifact items 3 and 11 already pin.

What the checker verifies instead, re-derived from the committed netlists on
every push, is **both** sides: for `lvs` citations the environment-digest leg
of `check_evidence_hashes.py` runs whether or not the envelope also records a
`provenance.input`. An input-hash envelope routes through the recorded-hash
leg for the layout side; if the environment leg were skipped there, the
reference side would silently lose its only verification:

- `environment.layout_sha256` vs `sar_adc_top.extract.lvs.spice` →
  `b4fb2add24c1f4b5…` ✓ (equal to `provenance.input.content_hash`, so the
  envelope's two statements of the layout digest are cross-checked)
- `environment.reference_sha256` vs `sar_adc_top.lvs-reference.spice` →
  `6cb0377eb6b2a1c2…` ✓

Item 11's second part is the same `lvs.json` and is unpinned for the same
reason; its first part (the `klt erc` envelope) **is** pinned, because `klt erc`
does write a `provenance.input.content_hash`.

## Running it

```bash
# One-time: the grader, in its own venv (pin: see signoff/requirements.txt).
python3 -m venv .venv-signoff
.venv-signoff/bin/pip install -r signoff/requirements.txt

# Verify the committed report still holds (what CI runs):
KLT=.venv-signoff/bin/klt bash signoff/run-signoff.sh --check
python3 signoff/check_evidence_hashes.py

# Re-render after changing the manifest or any cited evidence:
KLT=.venv-signoff/bin/klt bash signoff/run-signoff.sh

# Human-readable rendering of the same grading:
.venv-signoff/bin/klt signoff --manifest signoff/block-manifest.json \
  --format text --no-color
```

The grader pin (`klayout-tools==0.8.0`) deliberately diverges from
`layout/requirements.txt`'s pin (`0.6.0`; kept as a separate file by role): that one **mints** evidence and only moves
with a full re-run of every `layout/` flow, while this one **grades** it and is
a pure JSON+Markdown transform. `signoff/requirements.txt` documents the split
and why the grader needs at least 0.7.0 (it was 0.6.0 until issue #676). Re-rendered under the 0.8.0 pin and compared with the report on `main` before issue #676's citations: the eight rows for items 1, 2, 9 and 10 changed (item 1 digital `no_evidence` → `check_failed`; the other seven `unmet` / `no_evidence` → `met`) and every other row kept its status and reason. **Moving the grader pin is a claim change, not a
chore** — re-render, read the report diff row by row against this file, and
update both together.

## Where this is wired

- `.github/workflows/ci.yml` → job `signoff-check`, on every push and pull
  request: installs the pinned grader and runs `run-signoff.sh --check`.
- `npm run check:signoff-hashes` (inside `npm run check:ci`): the headless
  artifact re-hash, no `klt` needed; it also checks the anchored envelopes'
  `t1_item`, input path, inventory paths and netlist header hashes.
- `npm run check:signoff-attest` (inside `npm run check:ci`): re-mints the
  inventories and item 1, 2, 9, 10 envelopes and fails on any difference.
- `npm run test:unit`: `sim/tests/test_signoff_evidence_hashes.py`, including
  the negative controls.
- Fleet roll-up: `2AMLogic/2am#956` consumes `signoff/block-manifest.json`'s
  `block` field to identify this block's row.

# Work Log Archive — 2026-09

Sections moved byte-for-byte from [WORK_LOG.md](../WORK_LOG.md) by `loom-daemon work-docs archive`.

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

## DRC Report: /Users/rwalters/GitHub/sky130-sar-adc/.loom/worktrees/issue-2/layout/trivial-cell/reports/20260814-020537-98d9186/trivial_mos_array.gds
**Status:** ✅ clean
- Deck: sky130
- File: /Users/rwalters/GitHub/sky130-sar-adc/.loom/worktrees/issue-2/layout/trivial-cell/reports/20260814-020537-98d9186/trivial_mos_array.gds

No violations found.

## LVS Report: trivial_mos_array.gds vs reference.spice
**Status:** ✅ match
- Top: trivial_mos_array
- Engine: klayout

| Category | Severity | Side | Description |
| --- | --- | --- | --- |
| device.body_unverified | warning | layout | 8 NMOS device body terminal(s) were compared against the 'vsubs' deck-synthesized substrate net, not a real schematic net -- this deck draws no distinct NMOS substrate/tap layer (see docs/cli/extract.md, "Coverage") |
| topology | warning | both | nets were paired ambiguously; the comparer resolved it structurally (consider a hints.same_nets entry to pin this down) |
| topology | warning | both | nets were paired ambiguously; the comparer resolved it structurally (consider a hints.same_nets entry to pin this down) |
| topology | warning | both | nets were paired ambiguously; the comparer resolved it structurally (consider a hints.same_nets entry to pin this down) |
| topology | warning | both | nets were paired ambiguously; the comparer resolved it structurally (consider a hints.same_nets entry to pin this down) |
| topology | warning | both | nets were paired ambiguously; the comparer resolved it structurally (consider a hints.same_nets entry to pin this down) |
| topology | warning | both | nets were paired ambiguously; the comparer resolved it structurally (consider a hints.same_nets entry to pin this down) |
| topology | warning | both | nets were paired ambiguously; the comparer resolved it structurally (consider a hints.same_nets entry to pin this down) |
| topology | warning | both | nets were paired ambiguously; the comparer resolved it structurally (consider a hints.same_nets entry to pin this down) |
| topology | warning | both | nets were paired ambiguously; the comparer resolved it structurally (consider a hints.same_nets entry to pin this down) |
| topology | warning | layout | device class has no counterpart on the other side, but no devices of this class were extracted either -- not a real topology mismatch |
| topology | warning | layout | device class has no counterpart on the other side, but no devices of this class were extracted either -- not a real topology mismatch |

## DRC Report: /Users/rwalters/GitHub/sky130-sar-adc/.loom/worktrees/issue-2/layout/trivial-cell/reports/20260814-020537-98d9186/drc_violation_fixture.gds
**Status:** ❌ violations
- Deck: sky130
- File: /Users/rwalters/GitHub/sky130-sar-adc/.loom/worktrees/issue-2/layout/trivial-cell/reports/20260814-020537-98d9186/drc_violation_fixture.gds

| Rule | Cell | Layer | BBox | Description |
| --- | --- | --- | --- | --- |
| diff.width.1 | drc_violation_fixture | diff.drawing | (0,0)-(2000,50) | minimum diff width (approximates the official difftap.1 rule) |

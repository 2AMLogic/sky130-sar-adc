# `sampling-frontend-wells`: `met{1,2}.enclosing_adjacent.via.1` under klt 0.9.0 (issue #783)

Dated 2026-11-05. Adds a file; earlier notes are untouched.

## Before / after (both klt 0.9.0, klayout 0.30.12, curated `sky130` deck `sha256:029ef177c1f4e872c13cc81093f94a02a9bbfe1f51939a88194a83532d60bf7c`, PDK open_pdks f6eeac7d)

Run in a worktree-local `layout/.venv` (untracked) holding `klayout-tools==0.9.0` (the pin in `layout/requirements.txt` is unchanged at 0.6.0; this note does not bump it, #734 does).
The same venv, PDK and flow produced both records; only `build_layout.py` differs.

| record | `build_layout.py` | DRC | `met1...via.1` | `met2...via.1` | LVS |
|---|---|---|---|---|---|
| `reports/20261105-191430-bf27ff9d` (before, repo `bf27ff9d`) | unchanged | violations, 51 | 30 | 21 | match |
| `reports/20261105-191510-bf27ff9d` (after, working tree on `bf27ff9d`, change uncommitted at run time) | via1 pads 0.32 um | clean, 0 | 0 | 0 | match |

The 51 markers reproduce on 0.9.0 (not already gone), so a fix was needed. The "before" record's overall verdict is FAIL (only the composed-DRC line); the "after" record is PASS on every line, including the nwell negative control and both LVS negative controls.

## Source attribution

All 51 markers have `source_cell` `route__ROUTE`, i.e. geometry this repo draws in `build_layout.py`; none come from the `klt gen` blocks (which are DRC-clean in isolation in both records). No klayout-tools gap issue was needed.

## Cause and fix

At each via1 cut, `build_layout.py` drew a `WIRE_UM` = 0.30 um met1 pad over a 0.15 um via (0.075 um per side, below the 0.085 um adjacent-side enclosure), and met2 there was only the 0.30 um wide track wire. Now both met1 and met2 get a `VIA_PAD_UM` = 0.32 um (via + 2 x 0.085) square pad at each via1 cut, the same approach as #738. Nearest via columns are 0.66 um apart and tracks 0.50 um apart, so the wider pads clear m1.2/m2.2 (the after-run DRC is clean).

## Pinned-version verdict

Not re-run on the pinned klt 0.6.0; the 0.6.0 record (`reports/20261021-104743-ddc1d72`) is unchanged and was PASS. The geometry change is only a pad widening, but I did not measure it on 0.6.0.

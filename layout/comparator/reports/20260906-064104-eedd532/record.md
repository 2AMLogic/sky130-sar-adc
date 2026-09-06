# Comparator layout LVS re-check: 20260906-064104-eedd532

**This is not a layout run.** No geometry was generated, placed, routed or
DRC-checked here. It is the LVS re-check issue #175 owes: `design/comparator.sch`
changed topology under DR-004 Amendment A (the cross-coupled NMOS latch pair's
sources moved off hard-wired `GND` onto the input pair's own drain nodes
`DIP`/`DIN`, which gained their own CLK-gated PMOS precharge devices), and a
device-level topology change invalidates the LVS "match" verdict this block's
flow record carries. This record establishes **whether the drawn layout still
implements the schematic** — and it does not.

## Overall verdict: MISMATCH (expected, and the point of the check)

- [x] LVS against the **superseded** reference still reports **match** — the
      falsifiability control, see below
- [ ] LVS against the **amended** reference reports **mismatch** — the drawn
      geometry implements the pre-#175 topology

Both invocations run the identical `klt lvs` request against the identical
composed layout (`layout_sha256 = 1fb71e6b4f021dec…`, the `comparator.gds`
committed under `reports/20260825-135219-59f8e86/`), on one pinned toolchain,
in one sitting. The **only** thing that differs between them is which reference
netlist is compared against.

## Why the control is here rather than just the mismatch

A bare "LVS now mismatches" proves nothing on its own: a mismatch is also what
you get from a broken invocation, a wrong `top` cell, or a drifted tool. This
repo's layout flows already refuse to accept a *match* without showing
*mismatch* reachable (`layout/trivial-cell/`'s six-verdict discipline, issue
#2); the same rule read backwards says a *mismatch* is only meaningful once
*match* is shown reachable on the same run. It is — with the pre-amendment
reference.

That control earned its keep. A first attempt at this re-check used the `klt`
build that happened to be installed in the primary checkout's `layout/.venv`
(**0.2.0**) rather than `layout/requirements.txt`'s pin (**0.4.0**), and under
it the control **also** mismatched (64 mismatches, 0/9 devices matched) — i.e.
the setup, not the schematic, was the difference. Re-running both legs on the
pinned `klt 0.4.0` / `klayout 0.30.12` reproduced the recorded match exactly.
Without the control that first, invalid result would have looked like
confirmation of the expected answer.

## Results

| Leg | Reference | Status | mismatches | devices matched | nets matched |
| --- | --- | --- | --- | --- | --- |
| Control | `reference.superseded.spice` (9 devices, pre-#175) | **match** | 1 (`topology`, informational) | 9/9 | 8/8 |
| Re-check | `reference.amended.spice` (11 devices, DR-004 Amendment A) | **mismatch** | 13 | 3/11 | 3/10 |

Re-check mismatch categories: `device.unmatched` 8, `net.merged` 3,
`net.split` 1, `topology` 1 — exactly the signature of the amendment. The
layout draws 9 devices where the schematic now has 11 (the two `M_RST_DIP`/
`M_RST_DIN` precharge devices are simply not drawn), and the two nets the
amendment introduced (`DIP`, `DIN`) appear on the layout side merged into the
nets the old topology tied them to (`net.merged` 3 / `net.split` 1), because in
the drawn geometry the input pair's drains *are* the output nodes and the latch
NMOS sources *are* `GND`.

## Provenance

- `klt` version: klt 0.4.0 (`layout/requirements.txt`'s pin)
- KLayout engine: 0.30.12 (`layout/requirements.txt`'s pin)
- DRC/extraction deck: `sky130`
  (sha256:5afac7ab856154585…) — differs from the deck hash stamped in
  `reports/20260825-135219-59f8e86/record.md` (sha256:2e78949d63f03012…)
  because that record was produced on the earlier `klt 0.3.0` pin; the control
  leg above is what establishes that the difference does not change the verdict
  for the topology the layout was drawn against.
- Layout under test: `reports/20260825-135219-59f8e86/comparator.gds`, unmodified
  (`layout_sha256` identical to that record's own stamp)
- PDK: sky130A (open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b)

## Artefacts in this directory

| File | What it is |
| --- | --- |
| `lvs.request.json` | the request both legs ran, verbatim (identical for each) |
| `reference.amended.spice` | `layout/comparator/reference.spice` as of this commit (11 devices) |
| `reference.superseded.spice` | the same file at `HEAD` before #175 (9 devices) |
| `lvs.amended-reference.json` | full `klt lvs` envelope, re-check leg |
| `lvs.superseded-reference.json` | full `klt lvs` envelope, control leg |

## What this means, and what #175 deliberately does not do

The comparator layout is **superseded, not broken**: it is a DRC-clean,
LVS-clean realization of a topology this repo no longer intends to build. It
must be re-drawn against the amended schematic before any downstream claim
(`layout/sar-adc-top/`'s assembly, `layout/comparator/pex/`'s parasitic
extraction) can be said to describe the current design.

#175 does not re-draw it. That is a full sub-block layout job — a sixth
`klt gen` device block, `DIP`/`DIN` added to the mirror-symmetric routing plan
that `build_layout.py` lays out by explicit coordinate, and a fresh
six-verdict DRC/LVS proof — i.e. the same size of task as issue #101, which
drew the block in the first place. Bundling it into a topology-fix PR would
mean neither the fix nor the re-layout got a reviewable diff. It is filed as
its own issue, named from `layout/comparator/README.md`'s status section.

`reports/LATEST` is deliberately **left pointing at `20260825-135219-59f8e86`**:
that is still the most recent record of an actual flow run, and this record is
not one. `README.md` carries the status correction so a reader does not take
`LATEST`'s six PASS verdicts at face value.

---

Written by a manual `klt lvs` invocation pair (not `layout/comparator/bin/run-flow.sh`,
which regenerates geometry this record deliberately does not touch), issue #175.

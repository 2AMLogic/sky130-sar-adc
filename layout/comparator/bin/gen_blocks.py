#!/usr/bin/env python3
"""Generate the six `klt gen diff_pair`/`mos_array` sub-blocks that
layout/comparator/bin/run-flow.sh composes into the dynamic comparator
layout (issue #101, re-drawn for DR-004 Amendment A's 11-device topology in
issue #180).

Device sizing here is a 1:1 mirror of design/comparator.sch's own W/L per
device (sim/comparator-decision/testbench/comparator_core.spice is the
xschem-derived ground truth this script's params were checked against) --
see that file's header for the full device list. This script only decides
*how* each schematic device is drawn (matching topology, split count), never
*what* its electrical size is.

Matching strategy (the acceptance-criteria-critical decision, see
layout/comparator/README.md "Matching strategy" for the full writeup):

* **Input pair (M_INN/M_INP, `inpair`)** -- the one sub-circuit this issue's
  own acceptance criteria singles out as matching-critical for input-referred
  offset (tracked by #29) -- gets `klt gen diff_pair`'s strongest available
  treatment: `splits=2`, a true common-centroid cross-quad ("A B / B A")
  interleave of two W=2um legs per device (combining to the schematic's
  W=4um per device). This directly targets *gradient-induced* mismatch (a
  linear process gradient across the pair cancels to first order in a
  common-centroid layout, the textbook reason this topology exists), the
  dominant systematic-offset mechanism a plain side-by-side placement does
  not address.
* **Cross-coupled latch pairs (M_LATN_P/N, M_LATN_N; M_LATP_P/N), the
  reset pair (M_RST_P/N), and the DIP/DIN precharge pair added by DR-004
  Amendment A (M_RST_DIP/M_RST_DIN, `rstd`)** -- symmetric by schematic role
  (each pair's two devices are interchangeable under the OUTP<->OUTN /
  DIP<->DIN swap) but not the input-offset-critical net #29 tracks -- get
  `diff_pair`'s plain `splits=1` A/B placement: adjacent, identical
  orientation, single-instance per device at its full schematic width. This
  is proportionate effort: real symmetry (no gratuitous single-sided
  placement choice), without spending the interleaved-leg complexity budget
  on pairs whose own mismatch mainly affects regeneration symmetry/speed
  (the latch/reset pairs) or precharge-transient symmetry (the new DIP/DIN
  pair), not the static input offset this issue's acceptance criteria calls
  out by name. `rstd` is sized W=4um per device, matching the amended
  `reference.spice`/`comparator_core.spice` -- not the existing `rst`
  block's W=16um; "same class" means the same generator/`splits` treatment,
  not the same width.
* **Tail switch (M_TAIL, `tail`)** -- a single device, no matching partner --
  drawn via `mos_array` 1x1 (dummy=0): the array generator was chosen over a
  hand-rolled single-device draw only to reuse the same validated unit-device
  primitive (contact/landing-pad geometry) every other block already uses.

No guard ring on any block (`add_guard_ring: false` on every `diff_pair`
call): composing a closed guard/collector ring per block turned out to block
`klt gen-compose` from routing to almost any of that block's *other* ports
(see README's "Guard rings" note) -- every port not on the ring itself sits
inside a closed loop of ring metal that a two-pin/bundle route cannot legally
cross without shorting to the ring's own tap net. Dropping the ring means
every device's body terminal is the deck-synthesized `vsubs`/`vnwell` proxy
net documented in layout/trivial-cell/README.md's "device.body_unverified"
paragraph -- the exact same accepted, documented limitation the trivial-cell
proof already carries for `mos_array` with no ring, not a new one introduced
here.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "bin"))

from _gen_common import add_klt_pdk_args, run_gen, write_and_check  # noqa: E402

# (id, generator, cell_name, params) -- params intentionally spelled out in
# full (not derived from comparator_core.spice at runtime) so this script has
# no import-time dependency on the sim/ netlist fragment; the correspondence
# is asserted by run-flow.sh's own reference.spice cross-check instead.
BLOCKS = [
    (
        "tail",
        "mos_array",
        "TAIL",
        {
            "w_um": 8.0,
            "l_um": 0.5,
            "fingers": 1,
            "rows": 1,
            "cols": 1,
            "dummy": 0,
            "flavor": "nfet",
            "gate_contact": True,
        },
    ),
    (
        "inpair",
        "diff_pair",
        "INPAIR",
        {
            "w_um": 2.0,
            "l_um": 0.5,
            "splits": 2,
            "flavor": "nfet",
            "add_guard_ring": False,
            "gate_contact": True,
        },
    ),
    (
        "latn",
        "diff_pair",
        "LATN",
        {
            "w_um": 4.0,
            "l_um": 0.5,
            "splits": 1,
            "flavor": "nfet",
            "add_guard_ring": False,
            "gate_contact": True,
        },
    ),
    (
        "latp",
        "diff_pair",
        "LATP",
        {
            "w_um": 8.0,
            "l_um": 0.5,
            "splits": 1,
            "flavor": "pfet",
            "add_guard_ring": False,
            "gate_contact": True,
        },
    ),
    (
        "rst",
        "diff_pair",
        "RST",
        {
            "w_um": 16.0,
            "l_um": 0.5,
            "splits": 1,
            "flavor": "pfet",
            "add_guard_ring": False,
            "gate_contact": True,
        },
    ),
    (
        "rstd",
        "diff_pair",
        "RSTD",
        {
            "w_um": 4.0,
            "l_um": 0.5,
            "splits": 1,
            "flavor": "pfet",
            "add_guard_ring": False,
            "gate_contact": True,
        },
    ),
]


def main() -> int:
    parser = add_klt_pdk_args(argparse.ArgumentParser(description=__doc__))
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    block_ids = []
    for block_id, generator, cell_name, params in BLOCKS:
        gds_path = args.out_dir / f"{block_id}.gds"
        json_path = args.out_dir / f"{block_id}.json"
        stdout, stderr = run_gen(args.klt, args.pdk, generator, params, cell_name, gds_path)
        report = write_and_check(block_id, stdout, stderr, json_path)
        if report is None:
            return 1
        print(f"gen_blocks.py: wrote {json_path} ({report.get('device_count')} device(s))")
        block_ids.append(block_id)

    print(f"gen_blocks.py: generated {len(block_ids)} blocks in {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
